# -*- coding: utf-8 -*-
"""Bối cảnh 3D cho Truyện kể: AI vẽ ảnh trên máy bằng Stable Diffusion XL.

Dùng SDXL base 1.0 + SDXL-Lightning 8 bước (giấy phép CreativeML OpenRAIL++-M,
được dùng cho video kiếm tiền) + VAE fp16-fix. Card 11 GB (GTX 1080 Ti...) chạy
được; mỗi ảnh khoảng 20–60 giây. Mỗi địa điểm (ngày / đêm) chỉ vẽ MỘT lần rồi
dùng lại cho mọi cảnh ở đó, nên căn nhà giống nhau suốt truyện; nhân vật 2D đứng
trên nền này.

Cài một lần bằng cai_3d.bat (diffusers, accelerate, peft + tải mô hình ~7 GB).
Có thể đổi mô hình trong data/settings.json: bg3d_model, bg3d_lora_repo,
bg3d_lora_file, bg3d_steps (bg3d_lora_file để trống = không dùng Lightning,
khi đó nên đặt bg3d_steps 25–30).
"""
from __future__ import annotations

import gc
import importlib.util
import logging
import threading
from pathlib import Path

from PIL import Image, ImageFilter

from . import config

logger = logging.getLogger(__name__)

MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
LORA_REPO = "ByteDance/SDXL-Lightning"
LORA_FILE = "sdxl_lightning_8step_lora.safetensors"
VAE = "madebyollin/sdxl-vae-fp16-fix"
STEPS = 8
DIR = "story_bg3d"

STYLE = ("3D animated movie background, Pixar and Disney style environment, stylized 3D render, "
         "soft global illumination, warm cinematic lighting, gentle depth of field, highly detailed, "
         "cozy, rich textures")
EMPTY = ("wide establishing shot at eye level, empty open floor space in the center foreground, "
         "uninhabited empty scene")
NIGHT = "at night, dark blue moonlight, warm glow of an oil lamp"

_PIPE = None
_LOCK = threading.Lock()


def installed() -> bool:
    return all(importlib.util.find_spec(m) is not None
               for m in ("diffusers", "torch", "transformers", "accelerate"))


def check() -> tuple[bool, str]:
    """(dùng được không, lời nhắn) cho màn kiểm tra hệ thống."""
    if not installed():
        return False, "Chưa cài phần vẽ 3D — chạy cai_3d.bat (một lần)."
    try:
        import torch
        if not torch.cuda.is_available():
            return False, "Không thấy card NVIDIA (CUDA) — vẽ 3D cần card đồ hoạ."
        name = torch.cuda.get_device_name(0)
        mem = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
        return True, f"{name} {mem:.0f} GB"
    except Exception as e:  # noqa: BLE001
        return False, f"Lỗi kiểm tra card đồ hoạ: {e}"


def _settings():
    s = config.load_settings()
    return (s.get("bg3d_model") or MODEL, s.get("bg3d_lora_repo", LORA_REPO),
            s.get("bg3d_lora_file", LORA_FILE), int(s.get("bg3d_steps") or STEPS))


def _compat_transformers() -> None:
    """transformers 5 bỏ các hằng số Flax mà diffusers cũ còn import: thêm lại
    (chỉ là tên file, không dùng tới) để diffusers bản cũ vẫn chạy."""
    try:
        import transformers.utils as tu
    except Exception:  # noqa: BLE001
        return
    for name, val in (("FLAX_WEIGHTS_NAME", "flax_model.msgpack"),
                      ("FLAX_WEIGHTS_INDEX_NAME", "flax_model.msgpack.index.json")):
        if not hasattr(tu, name):
            setattr(tu, name, val)


def _load():
    global _PIPE
    if _PIPE is not None:
        return _PIPE
    if not installed():
        raise RuntimeError("Chưa cài phần vẽ 3D. Chạy cai_3d.bat một lần rồi mở lại tool.")
    import torch
    _compat_transformers()
    from diffusers import AutoencoderKL, EulerDiscreteScheduler, StableDiffusionXLPipeline
    if not torch.cuda.is_available():
        raise RuntimeError("Vẽ 3D cần card NVIDIA (CUDA).")
    model, lrepo, lfile, _steps = _settings()
    vae = AutoencoderKL.from_pretrained(VAE, torch_dtype=torch.float16)
    pipe = StableDiffusionXLPipeline.from_pretrained(
        model, vae=vae, torch_dtype=torch.float16, variant="fp16", use_safetensors=True)
    if lrepo and lfile:
        from huggingface_hub import hf_hub_download
        pipe.load_lora_weights(hf_hub_download(lrepo, lfile))
        pipe.fuse_lora()
        pipe.scheduler = EulerDiscreteScheduler.from_config(
            pipe.scheduler.config, timestep_spacing="trailing")
    # chung card với OmniVoice: chỉ đưa phần đang chạy lên GPU
    pipe.enable_model_cpu_offload()
    # giải mã ảnh từng mảnh cho đỡ tốn bộ nhớ card (diffusers mới gọi qua pipe.vae)
    try:
        if hasattr(pipe.vae, "enable_tiling"):
            pipe.vae.enable_tiling()
        else:
            pipe.enable_vae_tiling()
    except Exception:  # noqa: BLE001
        logger.info("Không bật được VAE tiling, bỏ qua.")
    try:
        pipe.set_progress_bar_config(disable=True)
    except Exception:  # noqa: BLE001
        pass
    _PIPE = pipe
    return pipe


def unload() -> None:
    """Trả bộ nhớ card cho OmniVoice sau khi vẽ xong."""
    global _PIPE
    _PIPE = None
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def run_jobs(jobs: list[dict], progress=None, labels: list[str] | None = None) -> None:
    """Vẽ nhiều ảnh trong một chương trình con (core/bg3d_worker) rồi cho nó thoát, để
    Stable Diffusion không làm hỏng OmniVoice chạy sau trong chương trình chính (lỗi
    "Tensor on device meta..."), và trả sạch bộ nhớ card. jobs: [{prompt, size, seed, path}]."""
    import json
    import subprocess
    import sys
    import tempfile
    if not jobs:
        return
    try:                                   # nhường card: bỏ OmniVoice đang nạp sẵn (lần đọc sau tự nạp lại)
        from . import voice
        voice.unload()
    except Exception:  # noqa: BLE001
        pass
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as err:
        proc = subprocess.Popen([sys.executable, "-m", "core.bg3d_worker"], cwd=str(root),
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                                text=True, encoding="utf-8", errors="replace")
        proc.stdin.write(json.dumps(jobs, ensure_ascii=False))
        proc.stdin.close()
        for line in proc.stdout:
            parts = line.split()
            if len(parts) == 2 and parts[0] == "START" and parts[1].isdigit() and progress:
                i = int(parts[1])
                progress(i / len(jobs), (labels or [])[i] if labels and i < len(labels) else f"vẽ ảnh {i + 1}/{len(jobs)}")
        code = proc.wait()
        if code != 0:
            err.seek(0)
            text = err.read()
            try:                                   # ghi đủ lỗi để gửi lại cho người sửa
                config.LOGS.mkdir(parents=True, exist_ok=True)
                (config.LOGS / "bg3d_loi.log").write_text(text, encoding="utf-8")
            except OSError:
                pass
            lines = [ln for ln in text.splitlines() if ln.strip()]
            last = lines[-1] if lines else f"mã {code}"      # dòng cuối = tên lỗi thật
            raise RuntimeError(f"Vẽ 3D lỗi: {last.strip()} (chi tiết: data/logs/bg3d_loi.log)")


def download() -> None:
    """Tải sẵn mô hình (cai_3d.bat gọi)."""
    _load()
    unload()


def gen_size(fmt_size: tuple[int, int]) -> tuple[int, int]:
    w, h = fmt_size
    r = w / h
    if r > 1.3:
        return 1344, 768
    if r < 0.77:
        return 768, 1344
    return 1024, 1024


def prompt_for(place: dict, time: str, era: str = "") -> str:
    parts = [STYLE, place.get("look") or place.get("name") or "a room", era or "",
             NIGHT if time == "dem" else "daytime, soft natural light", EMPTY]
    return ", ".join(p.strip().rstrip(".") for p in parts if p and p.strip())


NEGATIVE = "people, person, character, text, watermark, blurry, lowres"


def generate(prompt: str, size: tuple[int, int], seed: int) -> Image.Image:
    import torch
    with _LOCK:
        pipe = _load()
        _model, _r, lfile, steps = _settings()
        w, h = size
        cfg = 0.0 if lfile else 6.0
        g = torch.Generator("cpu").manual_seed(int(seed))
        try:
            out = pipe(prompt=prompt, width=w, height=h, num_inference_steps=steps,
                       guidance_scale=cfg, negative_prompt=None if lfile else NEGATIVE, generator=g)
        except Exception as e:  # noqa: BLE001
            if "token" not in repr(e).lower() and "encode" not in "".join(_tb(e)).lower():
                raise
            # bộ tách chữ của transformers lỗi (vài bản transformers 5): tự tách chữ, tự tính
            # vector câu lệnh rồi đưa thẳng vào SDXL
            logger.warning("Bộ tách chữ transformers lỗi (%s), dùng bộ tách chữ riêng.", e)
            g = torch.Generator("cpu").manual_seed(int(seed))
            emb, pooled = _embed(pipe, prompt)
            kw = {}
            if cfg > 1.0:
                kw["negative_prompt_embeds"], kw["negative_pooled_prompt_embeds"] = _embed(pipe, NEGATIVE)
            out = pipe(prompt_embeds=emb, pooled_prompt_embeds=pooled, width=w, height=h,
                       num_inference_steps=steps, guidance_scale=cfg, generator=g, **kw)
        return out.images[0]


def _tb(e: BaseException) -> list[str]:
    import traceback
    return traceback.format_exception(type(e), e, e.__traceback__)


_TOKS: dict = {}


def _clip_tokenizers():
    """Hai bộ tách chữ CLIP của SDXL đọc thẳng từ file mô hình (không qua transformers)."""
    if _TOKS:
        return _TOKS["a"], _TOKS["b"]
    import json as _json
    from huggingface_hub import hf_hub_download
    from .clip_tok import ClipTokenizer
    model = _settings()[0]
    out = []
    for sub in ("tokenizer", "tokenizer_2"):
        def get(name, sub=sub):
            try:
                return hf_hub_download(model, f"{sub}/{name}", local_files_only=True)
            except Exception:  # noqa: BLE001
                return hf_hub_download(model, f"{sub}/{name}")
        tok = ClipTokenizer(get("vocab.json"), get("merges.txt"))
        try:
            pad = _json.loads(Path(get("special_tokens_map.json")).read_text("utf-8")).get("pad_token")
            pad = pad.get("content") if isinstance(pad, dict) else pad
            if pad in tok.encoder:
                tok.pad = tok.encoder[pad]
        except Exception:  # noqa: BLE001
            pass
        out.append(tok)
    _TOKS["a"], _TOKS["b"] = out
    return out[0], out[1]


def _embed(pipe, text: str):
    """(prompt_embeds, pooled_prompt_embeds) của SDXL tính bằng bộ tách chữ riêng."""
    import torch
    ta, tb = _clip_tokenizers()
    dev = getattr(pipe, "_execution_device", None) or pipe.device
    embs, pooled = [], None
    with torch.no_grad():
        for tok, enc in ((ta, pipe.text_encoder), (tb, pipe.text_encoder_2)):
            ids = torch.tensor([tok(text)], dtype=torch.long, device=dev)
            o = enc(ids, output_hidden_states=True)
            embs.append(o.hidden_states[-2])
            if enc is pipe.text_encoder_2:
                pooled = o[0]
    emb = torch.cat(embs, dim=-1).to(dtype=pipe.unet.dtype)
    return emb, pooled.to(dtype=pipe.unet.dtype)


# ------------------------------------------------------------ theo truyện

def bg_dir(pdir: Path) -> Path:
    d = Path(pdir) / DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def path_for(pdir: Path, place_id: str, time: str) -> Path:
    return bg_dir(pdir) / f"{place_id}_{time}.png"


def needed(st: dict) -> list[tuple[dict, str]]:
    """Các (địa điểm, giờ) có cảnh dùng tới."""
    from .story import all_scenes
    from .story_live import scene_time
    places = {p["id"]: p for p in st.get("places") or []}
    seen, out = set(), []
    for _ci, sc in all_scenes(st):
        p = places.get(sc.get("place"))
        if not p:
            continue
        key = (p["id"], scene_time(sc, p))
        if key not in seen:
            seen.add(key)
            out.append((p, key[1]))
    return out


def draw_story(st: dict, pdir: Path, fmt_size, only: list[str] | None = None,
               force: bool = False, progress=None) -> list[str]:
    """Vẽ bối cảnh 3D cho các địa điểm của truyện. Trả về danh sách file đã vẽ."""
    import zlib
    todo = [(p, t) for p, t in needed(st) if not only or p["id"] in only]
    if only:                       # vẽ lại cả địa điểm chưa có cảnh nào
        have = {p["id"] for p, _t in todo}
        todo += [(p, p.get("time") or "ngay") for p in st.get("places") or []
                 if p["id"] in only and p["id"] not in have]
    made, reseeded = [], set()
    size = gen_size(fmt_size)
    jobs, labels = [], []
    for k, (p, t) in enumerate(todo):
        path = path_for(pdir, p["id"], t)
        if path.exists() and not force:
            continue
        if force and p["id"] not in reseeded:      # vẽ lại: đổi hạt giống (ngày, đêm dùng chung)
            old = int(p.get("bg3d_seed") or zlib.crc32(p["id"].encode()) % 100000)
            p["bg3d_seed"] = (old * 7919 + 13) % 1000003
            reseeded.add(p["id"])
        seed = int(p.get("bg3d_seed") or zlib.crc32(p["id"].encode()) % 100000)
        jobs.append({"prompt": prompt_for(p, t, st.get("era") or ""), "size": list(size), "seed": seed,
                     "path": str(path)})
        labels.append(f"vẽ bối cảnh 3D {len(jobs)}/?: {p.get('name')}" + (" (đêm)" if t == "dem" else ""))
        made.append(path.name)
    labels = [lb.replace("/?", f"/{len(jobs)}") for lb in labels]
    run_jobs(jobs, progress, labels)
    return made


def load_cover(path: Path, size: tuple[int, int]) -> Image.Image:
    """Mở ảnh nền và phóng / cắt cho phủ kín khung (giữ tỉ lệ)."""
    img = Image.open(path).convert("RGB")
    w, h = size
    r = max(w / img.width, h / img.height)
    img = img.resize((max(w, int(img.width * r + 0.5)), max(h, int(img.height * r + 0.5))),
                     Image.LANCZOS)
    x0, y0 = (img.width - w) // 2, (img.height - h) // 2
    img = img.crop((x0, y0, x0 + w, y0 + h))
    if r > 1.2:                     # phóng to nhiều: làm nét lại một chút
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    return img
