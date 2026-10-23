# -*- coding: utf-8 -*-
"""Chế độ Truyện kể: video dài 20–30 phút kể truyện (Lão Hạc, Tắt đèn...).

Chỉ có MỘT giọng người kể, hình là tranh minh hoạ (phong cách hoạt hình 2D...)
do chị tự vẽ bằng công cụ quen tay từ bộ câu lệnh vẽ tool xuất ra, rồi thả
ảnh vào; tool lo lời kể, giọng kể, chuyển động máy quay trên tranh, chuyển
cảnh, tên chương, nhạc nền và ghép video.

Quy trình:
  1. plan     — Claude chia chương + "kinh thánh hình ảnh" (nhân vật, địa điểm
                mô tả cố định bằng tiếng Anh để tranh nào cũng ra cùng người)
  2. chapters — Claude viết lời kể từng chương, chia cảnh (mỗi cảnh một tranh)
  3. prompts  — tool ghép câu lệnh vẽ: phong cách + mô tả cảnh + ngoại hình cố
                định của nhân vật có mặt + địa điểm + thời đại
  4. images   — chị thả ảnh scene_001.png... (ảnh thiếu thì dựng tạm khung chữ)
  5. narrate  — OmniVoice đọc lời kể bằng một giọng người kể cố định
  6. render   — core/story_render.py
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

import numpy as np

from . import claude_cli, config

logger = logging.getLogger(__name__)

# Phong cách tranh: (tên hiển thị, câu mở đầu cho câu lệnh vẽ)
STYLES = {
    "doodle": ("Vẽ tay webtoon Hàn (đầu tròn, thân con nhộng)",
               "hand-drawn Korean webtoon doodle style like a Korean storytime YouTube animation, "
               "simple cute chibi characters: big round head, tiny simple face with small dot eyes "
               "and short line eyebrows, small mouth, body is a simple rounded capsule or bell "
               "shape with NO visible arms and NO legs, clothing drawn as flat color blocks on the "
               "capsule body, thick slightly wobbly black marker outlines, flat muted pastel colors "
               "with no gradients and no shading, background drawn in the same hand-drawn line "
               "style with simple perspective, plain beige walls with a few short vertical scratch "
               "strokes, sparse simple furniture, subtle grainy paper texture over the whole "
               "image, characters standing on the floor at different depths, consistent "
               "character design"),
    "anim2d": ("Hoạt hình 2D",
               "2D animated film still, clean confident line art, soft cel shading, "
               "warm muted earthy palette, gentle storybook lighting, expressive faces, "
               "consistent character design"),
    "watercolor": ("Tranh màu nước",
                   "soft watercolor illustration, delicate washes, paper texture, "
                   "nostalgic muted colors, consistent character design"),
    "oil": ("Tranh sơn dầu",
            "oil painting illustration, visible brush strokes, rich deep colors, "
            "dramatic soft light, literary book illustration, consistent character design"),
    "book": ("Tranh minh hoạ sách",
             "classic Vietnamese textbook illustration, ink outlines, flat soft colors, "
             "simple shading, consistent character design"),
}
NEGATIVE = "no text, no letters, no watermark, no logo, no frame border"

# Gợi ý cho AI khi tả ngoại hình nhân vật theo từng phong cách
LOOK_HINTS = {
    "doodle": ("Phong cách này vẽ nhân vật đầu tròn, thân hình con nhộng KHÔNG có tay chân, "
               "nên mô tả ngoại hình tập trung vào thứ nhìn thấy được: kiểu tóc và màu tóc "
               "(búi, tóc ngắn, tóc bạc...), kính, râu, nếp nhăn, nét mặt thường trực, màu và "
               "kiểu áo, váy, quần (vd \"beige jacket with name tag, dark gray trousers\"); "
               "không tả dáng đi, cơ bắp, tay chân. Con vật vẽ tròn, đơn giản cùng kiểu."),
}

STYLE_REF = "style_ref.png"     # ảnh mẫu phong cách chị tải lên, gửi kèm mọi lần vẽ
_REF_EN = ("Match the art style of the attached style reference image exactly: same line "
           "weight, colors, character proportions and background drawing style")

CAMERAS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "still")

# Nhịp kể: chữ (âm tiết) mỗi phút khi viết lời kể; giọng kể đọc chậm hơn thoại
SYLLABLES_PER_MIN = 280
NARRATION_SPEED = 0.9

IMAGE_DIR = "story_images"
AUDIO_DIR = "story_audio"
_NUM = re.compile(r"(\d+)")


def default_story(title: str = "", author: str = "") -> dict:
    return {
        "title": title, "author": author, "source_text": "", "minutes": 25,
        "style": "doodle", "narrator": {"voice": "", "instruct": "male, elderly, low pitch"},
        "subtitles": False, "era": "", "characters": [], "places": [], "chapters": [],
    }


# ------------------------------------------------------------------ viết (AI)

def _split_source(text: str, n: int) -> list[str]:
    """Chia nguyên văn thành n phần gần bằng nhau theo đoạn văn."""
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text or "") if p.strip()]
    if not paras:
        return [""] * max(1, n)
    if n <= 1:
        return ["\n".join(paras)]
    total = sum(len(p) for p in paras)
    out, cur, acc, i = [], [], 0, 1
    for p in paras:
        cur.append(p)
        acc += len(p)
        if acc >= total * i / n and len(out) < n - 1:
            out.append("\n".join(cur))
            cur = []
            i += 1
    out.append("\n".join(cur))
    while len(out) < n:
        out.append("")
    return out


def chapter_count(minutes: float) -> int:
    return max(3, min(12, round(minutes / 3)))


def write_story(st: dict, progress=None) -> dict:
    """Claude chia chương, lập kinh thánh hình ảnh rồi viết lời kể từng chương.
    Ghi kết quả vào st và trả về st."""
    def say(f, m):
        if progress:
            progress(f, m)

    minutes = max(3.0, min(40.0, float(st.get("minutes") or 25)))
    n = chapter_count(minutes)
    style_vi = STYLES.get(st.get("style"), STYLES["anim2d"])[0]
    src = (st.get("source_text") or "").strip()
    source_block = (f"### Nguyên văn truyện\n{src}" if src else
                    "(Không có nguyên văn: kể lại theo đúng nội dung truyện mà bạn biết, "
                    "không bịa thêm.)")
    look_hint = LOOK_HINTS.get(st.get("style"), "")
    say(0.03, "AI chia chương và lập danh sách nhân vật, địa điểm")
    plan = claude_cli._run_json(claude_cli._load_prompt(
        "story_plan", minutes=str(int(minutes)), style_vi=style_vi,
        title=st.get("title") or "", author=st.get("author") or "(không rõ)",
        source_block=source_block, n_chapters=str(n), look_hint=look_hint),
        task="story", timeout=600)
    if not isinstance(plan, dict) or not plan.get("chapters"):
        raise RuntimeError("AI không lập được dàn chương.")
    chapters = plan["chapters"][:16]
    st["era"] = str(plan.get("era") or "")
    st["characters"] = [{"id": _slug(c.get("id") or c.get("name")), "name": str(c.get("name") or ""),
                         "look": str(c.get("look") or "")} for c in plan.get("characters") or []
                        if isinstance(c, dict)]
    st["places"] = [{"id": _slug(p.get("id") or p.get("name")), "name": str(p.get("name") or ""),
                     "look": str(p.get("look") or "")} for p in plan.get("places") or []
                    if isinstance(p, dict)]
    parts = _split_source(src, len(chapters)) if src else [""] * len(chapters)
    outline = "\n".join(f"{i + 1}. {c.get('title')}: {c.get('summary')}" for i, c in enumerate(chapters))
    chars_txt = "\n".join(f"- {c['id']}: {c['name']}" for c in st["characters"]) or "(không có)"
    places_txt = "\n".join(f"- {p['id']}: {p['name']}" for p in st["places"]) or "(không có)"
    per_min = minutes / len(chapters)
    out_chapters = []
    for i, c in enumerate(chapters):
        say(0.08 + 0.9 * i / len(chapters), f"AI viết chương {i + 1}/{len(chapters)}: {c.get('title')}")
        block = f"### Nguyên văn đoạn tương ứng\n{parts[i]}" if parts[i] else ""
        data = claude_cli._run_json(claude_cli._load_prompt(
            "story_chapter", title=st.get("title") or "", author=st.get("author") or "",
            outline=outline, characters=chars_txt, places=places_txt, index=str(i + 1),
            chapter_title=str(c.get("title") or ""), chapter_summary=str(c.get("summary") or ""),
            source_block=block, syllables=str(int(per_min * SYLLABLES_PER_MIN)),
            minutes=f"{per_min:.1f}"), task="story", timeout=600)
        scenes = data.get("scenes") if isinstance(data, dict) else None
        if not scenes:
            raise RuntimeError(f"AI không viết được chương {i + 1}.")
        out_chapters.append({"title": str(c.get("title") or f"Chương {i + 1}"),
                             "scenes": [_clean_scene(s) for s in scenes if isinstance(s, dict)]})
    st["chapters"] = out_chapters
    renumber(st)
    say(1.0, "xong")
    return st


def _slug(v) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", str(v or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "_", t.replace("đ", "d").replace("Đ", "D")).strip("_").lower()
    return t or "x"


def _clean_scene(s: dict) -> dict:
    cam = str(s.get("camera") or "zoom_in")
    return {"text": str(s.get("text") or "").strip(),
            "prompt": str(s.get("prompt") or "").strip(),
            "chars": [_slug(c) for c in (s.get("chars") or []) if c],
            "place": _slug(s.get("place")) if s.get("place") else "",
            "camera": cam if cam in CAMERAS else "zoom_in"}


def renumber(st: dict) -> None:
    """Đánh số cảnh 001, 002... theo thứ tự (khớp tên file ảnh scene_001.png)."""
    k = 0
    for ch in st.get("chapters") or []:
        for sc in ch.get("scenes") or []:
            k += 1
            sc["id"] = f"{k:03d}"


def all_scenes(st: dict) -> list[tuple[int, dict]]:
    return [(ci, sc) for ci, ch in enumerate(st.get("chapters") or [])
            for sc in ch.get("scenes") or []]


# ------------------------------------------------------------------ câu lệnh vẽ

def _aspect(fmt: str) -> str:
    return {"16:9": "wide 16:9 composition", "1:1": "square 1:1 composition"}.get(
        fmt, "vertical 9:16 composition")


def image_prompt(st: dict, sc: dict, fmt: str, ref: bool = False) -> str:
    style = STYLES.get(st.get("style"), STYLES["anim2d"])[1]
    if ref:
        style = _REF_EN + ". " + style
    looks = {c["id"]: c for c in st.get("characters") or []}
    places = {p["id"]: p for p in st.get("places") or []}
    parts = [style, sc.get("prompt") or ""]
    who = [looks[c] for c in sc.get("chars") or [] if c in looks]
    if who:
        parts.append("Characters: " + "; ".join(f"{c['name']} — {c['look']}" for c in who))
    if sc.get("place") in places:
        p = places[sc["place"]]
        parts.append(f"Setting: {p['name']} — {p['look']}")
    if st.get("era"):
        parts.append(st["era"])
    parts += [_aspect(fmt), NEGATIVE]
    return ". ".join(x.strip().rstrip(".") for x in parts if x and x.strip()) + "."


def character_prompt(st: dict, c: dict, ref: bool = False) -> str:
    style = STYLES.get(st.get("style"), STYLES["anim2d"])[1]
    if ref:
        style = _REF_EN + ". " + style
    return (f"{style}. Character reference sheet of {c['name']}: {c['look']}. "
            f"Full body, front view and three-quarter view, neutral pose, plain light background. "
            f"{st.get('era') or ''}. {NEGATIVE}.")


def prompts_text(st: dict, fmt: str, ref: bool = False) -> str:
    """Bộ câu lệnh vẽ để chị dán vào công cụ vẽ tranh (Midjourney, Gemini...).
    ref: chị đã tải ảnh mẫu phong cách -> nhắc gửi kèm ảnh đó mọi lần vẽ."""
    lines = [
        f"BỘ CÂU LỆNH VẼ — {st.get('title')} ({st.get('author') or ''})",
        f"Phong cách: {STYLES.get(st.get('style'), STYLES['anim2d'])[0]} · Khung: {fmt}",
        "",
        "CÁCH DÙNG:",
        "1. Vẽ ảnh NHÂN VẬT trước (char_...png). Chọn bản ưng nhất làm ảnh tham chiếu.",
        "2. Vẽ từng CẢNH: dán câu lệnh, đính kèm ảnh tham chiếu của nhân vật có mặt",
        "   (Midjourney: --cref; Gemini/ChatGPT: gửi kèm ảnh) để nhân vật giống nhau.",
        "3. Lưu ảnh đúng tên scene_001.png, scene_002.png... rồi bấm 'Tải ảnh lên' trong tool",
        "   (hoặc chép vào thư mục story_images của tập). Ảnh thiếu tool dựng tạm khung chữ.",
    ]
    if ref:
        lines += [
            "4. MỌI lần vẽ (nhân vật và cảnh) đều gửi kèm ảnh mẫu phong cách style_ref.png",
            "   (tải ở mục 4 của tool). Midjourney: --sref <link ảnh>; Gemini/ChatGPT: đính kèm",
            "   ảnh và giữ nguyên câu lệnh (câu lệnh đã dặn vẽ đúng phong cách ảnh đính kèm).",
        ]
    lines += [
        "",
        "=== NHÂN VẬT (ảnh tham chiếu) ===",
    ]
    for c in st.get("characters") or []:
        lines += [f"[char_{c['id']}.png] {c['name']}", character_prompt(st, c, ref), ""]
    lines.append("=== CẢNH ===")
    for ci, sc in all_scenes(st):
        ch = st["chapters"][ci]
        lines += [f"[scene_{sc['id']}.png] Chương {ci + 1}: {ch['title']} — camera: {sc.get('camera')}",
                  f"Lời kể: {sc.get('text')}",
                  image_prompt(st, sc, fmt, ref), ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ ảnh

def image_dir(pdir: Path) -> Path:
    d = pdir / IMAGE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def scene_images(pdir: Path) -> dict[str, Path]:
    """{"001": đường dẫn ảnh} — nhận theo số đầu tiên trong tên file
    (scene_001.png, 001.jpg, canh 1.webp...). Ảnh char_* bỏ qua."""
    out: dict[str, Path] = {}
    for p in sorted(image_dir(pdir).iterdir()):
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp") \
                or p.name.startswith("char_") or p.name == STYLE_REF:
            continue
        m = _NUM.search(p.stem)
        if m:
            out.setdefault(f"{int(m.group(1)):03d}", p)
    return out


# ------------------------------------------------------------------ giọng kể

def _sentences(text: str, limit: int = 200) -> list[str]:
    """Chia lời kể thành câu ngắn để OmniVoice đọc ổn định."""
    parts = re.split(r"(?<=[.!?…])\s+", (text or "").strip())
    out = []
    for p in parts:
        while len(p) > limit:
            cut = p.rfind(",", 0, limit)
            cut = cut if cut > 40 else limit
            out.append(p[:cut + 1].strip())
            p = p[cut + 1:].strip()
        if p:
            out.append(p)
    return out


def narrate(st: dict, pdir: Path, language: str = "vi", progress=None) -> dict[str, Path]:
    """Đọc lời kể từng cảnh bằng MỘT giọng người kể cố định. Cảnh nào lời kể
    không đổi thì dùng lại file cũ (dựng lại không phải đọc lại)."""
    import soundfile as sf
    from . import assets, pipeline, voice

    adir = pdir / AUDIO_DIR
    adir.mkdir(parents=True, exist_ok=True)
    nar = st.get("narrator") or {}
    ref = None
    if nar.get("voice"):
        lib = assets.voice_path(nar["voice"], language)
        if lib:
            ref = {"ref": str(lib), "ref_text": assets.voice_text(nar["voice"], language)}
    if ref is None:
        ref = pipeline.voice_anchor(pdir, "nguoi_ke", language, nar.get("instruct") or None)
    ref = ref or {}
    scenes = all_scenes(st)
    out: dict[str, Path] = {}
    pause = 0.35
    for k, (_ci, sc) in enumerate(scenes):
        text = sc.get("text") or ""
        key = hashlib.md5(json.dumps([text, ref.get("ref"), NARRATION_SPEED],
                                     ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        path = adir / f"scene_{sc['id']}_{key}.wav"
        if not path.exists():
            if progress:
                progress(k / max(1, len(scenes)), f"đọc lời kể cảnh {k + 1}/{len(scenes)}")
            chunks, sr = [], config.SAMPLE_RATE
            for j, sent in enumerate(_sentences(text)):
                wav, sr = voice.synthesize(sent, language, ref_wav=Path(ref["ref"]) if ref.get("ref") else None,
                                           ref_text=ref.get("ref_text"), speed=NARRATION_SPEED,
                                           seed=int(key[:6], 16) + j)
                wav = voice.trim_silence(np.asarray(wav, dtype=np.float32), sr)
                chunks += [wav, np.zeros(int(sr * pause), dtype=np.float32)]
            full = np.concatenate(chunks) if chunks else np.zeros(sr, dtype=np.float32)
            for old in adir.glob(f"scene_{sc['id']}_*.wav"):
                old.unlink(missing_ok=True)
            sf.write(str(path), full, sr)
        out[sc["id"]] = path
    return out
