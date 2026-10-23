# -*- coding: utf-8 -*-
"""Kiểu video "Ảnh theo lời": voice đến đâu, ảnh đến đó.

Chị tải file giọng có sẵn (tự thu, ElevenLabs...) + kịch bản (không bắt buộc):
  1. Whisper nghe từng chữ kèm thời gian (faster-whisper, word_timestamps)
  2. chia thành từng câu / cụm câu 2–6 giây (có kịch bản thì lấy chữ kịch bản)
  3. AI viết câu lệnh vẽ cho từng câu, giữ nhân vật / bối cảnh nhất quán
  4. Stable Diffusion trên máy vẽ ảnh từng câu (core/bg3d.py)
  5. dựng video: ảnh đổi đúng lúc giọng đọc tới câu đó, máy quay chuyển động
     nhẹ, chuyển ảnh nhanh, phụ đề + nhạc nền tuỳ chọn.

Dữ liệu nằm trong truyện (st): st["sync"] = {audio, duration, style}, các câu là
"cảnh" của một chương duy nhất (id 001, 002...) nên ảnh, tải ảnh lên, câu lệnh
vẽ dùng chung đường với chế độ Kể chuyện.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import unicodedata
from pathlib import Path

import numpy as np

from . import config, story

logger = logging.getLogger(__name__)

DIR = "sync"
MIN_SEG, MAX_SEG = 1.5, 6.5         # giây mỗi ảnh
CHUNK = 60                          # số câu mỗi lần nhờ AI viết câu lệnh vẽ

STYLES = {
    "3d": ("Hoạt hình 3D (Pixar)", "3D animated movie still, Pixar and Disney style, stylized 3D render, "
           "soft global illumination, cinematic lighting, highly detailed"),
    "anime": ("Hoạt hình 2D / anime", "2D anime illustration, clean line art, cel shading, vibrant soft "
              "colors, detailed background, cinematic composition"),
    "doodle": ("Vẽ tay webtoon Hàn", "hand-drawn Korean webtoon doodle style, simple cute characters with "
               "big round heads, thick slightly wobbly black outlines, flat muted pastel colors, grainy "
               "paper texture"),
    "watercolor": ("Màu nước", "soft watercolor illustration, delicate washes, paper texture, gentle "
                   "nostalgic colors"),
    "realistic": ("Ảnh chân thực (điện ảnh)", "cinematic photograph, realistic, natural lighting, shallow "
                  "depth of field, 35mm film look, highly detailed"),
    "oil": ("Tranh sơn dầu", "oil painting, visible brush strokes, rich deep colors, dramatic soft light"),
}
CAMS = ["zoom_in", "pan_right", "zoom_out", "pan_left", "zoom_in", "pan_up"]


def sdir(pdir: Path) -> Path:
    d = Path(pdir) / DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- giọng

def save_audio(pdir: Path, src: Path) -> dict:
    """Đổi file giọng chị tải lên sang wav 24 kHz mono (ffmpeg đọc được mọi định dạng)."""
    import soundfile as sf
    from . import video
    out = sdir(pdir) / "voice.wav"
    r = subprocess.run([video._ffmpeg_path(), "-y", "-i", str(src), "-vn", "-ac", "1", "-ar",
                        str(config.SAMPLE_RATE), str(out)], capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError("Không đọc được file giọng (thử mp3, wav, m4a).")
    info = sf.info(str(out))
    return {"audio": str(out), "duration": round(info.duration, 2), "name": Path(src).name}


_ASR = None


def _whisper():
    global _ASR
    if _ASR is None:
        from faster_whisper import WhisperModel
        device = "cpu"
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:  # noqa: BLE001
            pass
        last = None
        # card đời cũ (GTX 10xx) không chạy float16: thử lần lượt
        for ct in (["float16", "int8_float32", "float32"] if device == "cuda" else ["int8"]):
            try:
                _ASR = WhisperModel(config.WHISPER_MODEL, device=device, compute_type=ct)
                break
            except Exception as e:  # noqa: BLE001
                last = e
        if _ASR is None:
            raise RuntimeError(f"Không nạp được Whisper: {last}")
    return _ASR


def unload_whisper():
    global _ASR
    _ASR = None
    import gc
    gc.collect()


def transcribe_words(audio: Path, language: str = "vi", progress=None) -> list[dict]:
    """[{w, t0, t1}] — mỗi chữ (tiếng Việt: mỗi âm tiết) kèm thời gian. Có cache."""
    audio = Path(audio)
    h = hashlib.md5(audio.read_bytes()).hexdigest()[:12]
    cache = audio.parent / f"words_{h}_{language}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    m = _whisper()
    segs, info = m.transcribe(str(audio), language=language or None, word_timestamps=True,
                              vad_filter=True, beam_size=5)
    words = []
    total = getattr(info, "duration", 0) or 1
    for s in segs:
        for w in s.words or []:
            words.append({"w": w.word.strip(), "t0": round(w.start, 3), "t1": round(w.end, 3)})
        if progress:
            progress(min(0.99, s.end / total), f"nghe giọng {int(s.end // 60)}:{int(s.end % 60):02d}")
    cache.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    return words


# ---------------------------------------------------------------- chia câu

def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if c.isalnum())


def _split_long(ws, i0, i1):
    """Cắt đoạn chữ ws[i0:i1] quá dài ở dấu phẩy / chỗ ngắt hơi gần giữa nhất."""
    t0, t1 = ws[i0]["t0"], ws[i1 - 1]["t1"]
    if t1 - t0 <= MAX_SEG or i1 - i0 < 4:
        return [(i0, i1)]
    mid = (t0 + t1) / 2
    best, score = None, None
    for k in range(i0 + 2, i1 - 1):
        gap = ws[k]["t0"] - ws[k - 1]["t1"]
        comma = ws[k - 1]["w"].endswith((",", ";", ":", "…"))
        sc = abs(ws[k]["t0"] - mid) - (1.5 if comma else 0) - gap * 4
        if score is None or sc < score:
            best, score = k, sc
    return _split_long(ws, i0, best) + _split_long(ws, best, i1)


def segment(words: list[dict], duration: float, script: str = "") -> list[dict]:
    """Chia thành các câu 2–6 giây: [{text, t0, t1}]. t0 câu đầu = 0, t1 câu cuối
    = hết giọng, các câu nối liền nhau (ảnh không bao giờ trống)."""
    if not words:
        return [{"text": script.strip()[:200], "t0": 0.0, "t1": duration}] if duration else []
    # 1. cắt theo câu (dấu câu Whisper ghi), rồi cắt câu dài, gộp câu ngắn
    bounds, start = [], 0
    for i, w in enumerate(words):
        if w["w"].endswith((".", "!", "?", "…")) or i == len(words) - 1:
            bounds.append((start, i + 1))
            start = i + 1
    parts = []
    for a, b in bounds:
        parts += _split_long(words, a, b)
    merged = []
    for a, b in parts:
        if merged and (words[b - 1]["t1"] - words[a]["t0"] < MIN_SEG or
                       words[merged[-1][1] - 1]["t1"] - words[merged[-1][0]]["t0"] < MIN_SEG) and \
                words[b - 1]["t1"] - words[merged[-1][0]]["t0"] <= MAX_SEG + 1.5:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    segs = [{"a": a, "b": b, "text": " ".join(w["w"] for w in words[a:b]).strip()} for a, b in merged]
    # 2. có kịch bản: thay chữ Whisper bằng chữ kịch bản (chia theo tỉ lệ âm tiết)
    toks = [t for t in re.split(r"\s+", script.strip()) if t] if script else []
    if toks:
        n_w = len(words)
        n_s = len(toks)
        for sgm in segs:
            ka = round(sgm["a"] * n_s / n_w)
            kb = round(sgm["b"] * n_s / n_w)
            sgm["text"] = " ".join(toks[ka:kb]).strip() or sgm["text"]
    out = []
    for k, sgm in enumerate(segs):
        t0 = 0.0 if k == 0 else round((words[sgm["a"] - 1]["t1"] + words[sgm["a"]]["t0"]) / 2, 3)
        t1 = duration if k == len(segs) - 1 else \
            round((words[sgm["b"] - 1]["t1"] + words[sgm["b"]]["t0"]) / 2, 3)
        out.append({"text": sgm["text"], "t0": t0, "t1": max(t0 + 0.5, t1)})
    return out


# ---------------------------------------------------------------- câu lệnh vẽ (AI)

def write_prompts(st: dict, segs: list[dict], progress=None) -> dict:
    """AI viết "kinh thánh hình ảnh" + câu lệnh vẽ tiếng Anh cho từng câu."""
    from . import claude_cli
    bible: dict = {}
    prompts: list[str] = [""] * len(segs)
    full = " ".join(s["text"] for s in segs)
    for c0 in range(0, len(segs), CHUNK):
        chunk = segs[c0:c0 + CHUNK]
        if progress:
            progress(c0 / max(1, len(segs)), f"AI viết câu lệnh vẽ {c0 + 1}–{c0 + len(chunk)}/{len(segs)}")
        lines = "\n".join(f"{c0 + i + 1}. {s['text']}" for i, s in enumerate(chunk))
        data = claude_cli._run_json(claude_cli._load_prompt(
            "sync_prompts", title=st.get("title") or "", style=STYLES.get(
                (st.get("sync") or {}).get("style"), STYLES["3d"])[0],
            script=full[:6000], bible=json.dumps(bible, ensure_ascii=False) if bible else "(chưa có — hãy lập)",
            lines=lines, first=str(c0 + 1), last=str(c0 + len(chunk))), task="story", timeout=600)
        if not isinstance(data, dict):
            raise RuntimeError("AI không trả về câu lệnh vẽ.")
        if not bible and isinstance(data.get("bible"), dict):
            bible = data["bible"]
        for p in data.get("prompts") or []:
            try:
                k = int(p.get("i")) - 1
            except (TypeError, ValueError, AttributeError):
                continue
            if 0 <= k < len(segs):
                prompts[k] = str(p.get("prompt") or "").strip()
    for k in range(len(prompts)):                      # câu AI bỏ sót: dùng câu trước
        if not prompts[k]:
            prompts[k] = prompts[k - 1] if k else segs[k]["text"]
    return {"bible": bible, "prompts": prompts}


def build(st: dict, pdir: Path, language: str = "vi", progress=None) -> dict:
    """Nghe giọng, chia câu, nhờ AI viết câu lệnh vẽ. Ghi vào st (một chương)."""
    def say(f, m):
        if progress:
            progress(f, m)
    sy = st.get("sync") or {}
    if not sy.get("audio") or not Path(sy["audio"]).exists():
        raise RuntimeError("Chưa tải file giọng.")
    say(0.02, "nạp Whisper, nghe giọng (lần đầu mất 1–2 phút)")
    words = transcribe_words(Path(sy["audio"]), language,
                             progress=lambda f, m: say(0.02 + 0.45 * f, m))
    unload_whisper()
    segs = segment(words, float(sy.get("duration") or (words[-1]["t1"] if words else 0)),
                   st.get("source_text") or "")
    if not segs:
        raise RuntimeError("Không nghe được chữ nào trong file giọng.")
    say(0.5, f"chia được {len(segs)} câu, AI viết câu lệnh vẽ")
    res = write_prompts(st, segs, progress=lambda f, m: say(0.5 + 0.48 * f, m))
    st["sync"] = dict(sy, bible=res["bible"])
    st["chapters"] = [{"title": st.get("title") or "", "scenes": [
        {"text": s["text"], "prompt": res["prompts"][k], "t0": s["t0"], "t1": s["t1"],
         "chars": [], "place": "", "camera": CAMS[k % len(CAMS)]}
        for k, s in enumerate(segs)]}]
    story.renumber(st)
    say(1.0, "xong")
    return st


def full_prompt(st: dict, sc: dict, fmt_size) -> str:
    style = STYLES.get((st.get("sync") or {}).get("style"), STYLES["3d"])[1]
    w, h = fmt_size
    aspect = "wide 16:9 composition" if w > h * 1.2 else ("vertical 9:16 composition" if h > w * 1.2
                                                          else "square composition")
    return f"{style}, {sc.get('prompt') or sc.get('text')}, {aspect}, no text, no watermark"


# ---------------------------------------------------------------- vẽ ảnh

def draw(st: dict, pdir: Path, fmt_size, only: list[str] | None = None, force: bool = False,
         progress=None) -> list[str]:
    """Stable Diffusion vẽ ảnh từng câu (story_images/scene_XXX.png). Ảnh đã có
    (vẽ trước hoặc chị tải lên) thì bỏ qua, trừ khi vẽ lại."""
    import zlib
    from . import bg3d
    have = story.scene_images(pdir)
    todo = [sc for _ci, sc in story.all_scenes(st)
            if (not only or sc["id"] in only) and (force or sc["id"] not in have)]
    size = bg3d.gen_size(fmt_size)
    made = []
    for k, sc in enumerate(todo):
        if progress:
            progress(k / max(1, len(todo)), f"vẽ ảnh {k + 1}/{len(todo)} (câu {sc['id']})")
        seed = zlib.crc32((sc.get("prompt") or sc["id"]).encode()) % 100000
        if force:
            seed = (seed + int(sc.get("redraw", 0)) * 7919 + 1) % 1000003
            sc["redraw"] = int(sc.get("redraw", 0)) + 1
        img = bg3d.generate(full_prompt(st, sc, fmt_size), size, seed)
        d = story.image_dir(pdir)
        for old in d.glob(f"scene_{sc['id']}.*"):
            old.unlink(missing_ok=True)
        img.save(d / f"scene_{sc['id']}.png")
        made.append(sc["id"])
    return made


# ---------------------------------------------------------------- dựng

def render(st: dict, pdir: Path, fmt: str, settings: dict, progress=None) -> Path:
    from PIL import Image
    from . import video
    from .story_render import FPS, _Shot, _mix, _over, _placeholder, _subtitle
    import soundfile as sf

    def say(f, m):
        if progress:
            progress(f, m)

    size = config.frame_size(fmt)
    W, H = size
    sy = st.get("sync") or {}
    if not sy.get("audio") or not Path(sy["audio"]).exists():
        raise RuntimeError("Chưa tải file giọng.")
    scs = [sc for _ci, sc in story.all_scenes(st)]
    if not scs:
        raise RuntimeError("Chưa chia câu — bấm 'Chia câu & viết câu lệnh vẽ' trước.")
    total = float(sy.get("duration") or sf.info(sy["audio"]).duration) + 0.6
    imgs = story.scene_images(pdir)
    out_dir = pdir / "out"
    tmp = out_dir / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    ff = video._ffmpeg_path()
    raw = tmp / "sync_video_only.mp4"
    proc = subprocess.Popen(
        [ff, "-y", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{W}x{H}",
         "-framerate", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "20",
         "-pix_fmt", "yuv420p", "-preset", "veryfast", str(raw)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shots: dict = {}

    def shot(i):
        if i not in shots:
            for k in [k for k in shots if k < i - 1]:
                del shots[k]
            sc = scs[i]
            p = imgs.get(sc["id"])
            try:
                im = Image.open(p) if p else _placeholder(size, sc["id"], sc.get("text") or "")
            except Exception:  # noqa: BLE001
                im = _placeholder(size, sc["id"], sc.get("text") or "")
            shots[i] = _Shot(im, size, sc.get("camera") or "zoom_in")
        return shots[i]

    sub_on = bool(st.get("subtitles"))
    subs: dict = {}
    fade = 0.18                                 # chuyển ảnh nhanh, đúng lúc lời tới
    n = int(total * FPS)
    i = 0
    try:
        for fi in range(n):
            t = fi / FPS
            while i < len(scs) - 1 and t >= float(scs[i + 1]["t0"]):
                i += 1
            sc = scs[i]
            t0 = float(sc["t0"])
            t1 = float(scs[i + 1]["t0"]) if i + 1 < len(scs) else total
            u = (t - t0) / max(0.1, t1 - t0)
            frame = shot(i).frame(min(1.0, max(0.0, u)))
            if i > 0 and t - t0 < fade:                 # mờ nhanh từ ảnh trước sang
                prev = shot(i - 1).frame(1.0)
                frame = _mix(prev, frame, (t - t0) / fade)
            if sub_on and sc.get("text"):
                if sc["id"] not in subs:
                    if len(subs) > 6:
                        subs.clear()
                    subs[sc["id"]] = _subtitle(size, sc["text"])
                frame = _over(frame, subs[sc["id"]])
            proc.stdin.write(np.ascontiguousarray(frame).tobytes())
            if fi % max(1, n // 60) == 0:
                say(0.05 + 0.85 * fi / n, f"dựng hình {int(t // 60)}:{int(t % 60):02d} / "
                                          f"{int(total // 60)}:{int(total % 60):02d}")
    finally:
        proc.stdin.close()
        proc.wait()
    say(0.93, "ghép giọng")
    mp4 = out_dir / "video.mp4"
    bgm = settings.get("bgm_file")
    vol = float(settings.get("bgm_volume") or 0)
    if bgm and Path(bgm).exists() and vol > 0:
        cmd = [ff, "-y", "-i", str(raw), "-i", str(sy["audio"]), "-stream_loop", "-1", "-i", str(bgm),
               "-filter_complex",
               f"[2:a]volume={vol * 0.3:.3f},afade=t=out:st={max(0, total - 4):.2f}:d=4[b];"
               f"[1:a][b]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]",
               "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-shortest", str(mp4)]
    else:
        cmd = [ff, "-y", "-i", str(raw), "-i", str(sy["audio"]), "-map", "0:v", "-map", "1:a",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg ghép tiếng lỗi: " + (r.stderr or "")[-400:])
    say(1.0, "xong")
    return mp4
