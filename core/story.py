# -*- coding: utf-8 -*-
"""Chế độ Truyện kể: video dài 20–30 phút kể truyện (Lão Hạc, Tắt đèn...).

Chỉ có MỘT giọng người kể. Hình có hai cách (st["visual"]):
  - "tool"   — tool tự vẽ bối cảnh + nhân vật con nhộng và cho cử động theo lời
               kể (core/story_live.py), không cần vẽ gì ở ngoài
  - "images" — chị tự vẽ tranh bằng công cụ khác từ bộ câu lệnh tool xuất ra
Tool lo lời kể, giọng kể, máy quay, chuyển cảnh, tên chương, nhạc nền, ghép video.

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
        "style": "doodle", "visual": "tool", "narrator": {"voice": "", "instruct": "male, elderly, low pitch"},
        "subtitles": False, "era": "", "characters": [], "places": [], "chapters": [],
        "dialogue": "some",
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
    tool = st.get("visual", "tool") == "tool"
    visual_block, scene_block = (_tool_blocks() if tool else ("", ""))
    say(0.03, "AI chia chương và lập danh sách nhân vật, địa điểm")
    plan = claude_cli._run_json(claude_cli._load_prompt(
        "story_plan", minutes=str(int(minutes)), style_vi=style_vi,
        title=st.get("title") or "", author=st.get("author") or "(không rõ)",
        source_block=source_block, n_chapters=str(n), look_hint=look_hint,
        visual_block=visual_block),
        task="story", timeout=600)
    if not isinstance(plan, dict) or not plan.get("chapters"):
        raise RuntimeError("AI không lập được dàn chương.")
    chapters = plan["chapters"][:16]
    st["era"] = str(plan.get("era") or "")
    if tool:
        _make_parts(plan.get("new_parts"), say)
    st["characters"] = [_clean_char(c) for c in plan.get("characters") or [] if isinstance(c, dict)]
    st["places"] = [_clean_place(p) for p in plan.get("places") or [] if isinstance(p, dict)]
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
            minutes=f"{per_min:.1f}", scene_block=scene_block,
            dialogue_block=DIALOGUE.get(st.get("dialogue", "some"), DIALOGUE["some"])[1]),
            task="story", timeout=600)
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


def _tool_blocks() -> tuple[str, str]:
    """Phần thêm vào câu lệnh khi tool tự vẽ: AI chọn bộ ghép nhân vật, mẫu
    bối cảnh và nhân vật làm gì trong từng cảnh."""
    from . import doodle, story_live
    opt = doodle.options()
    cat = "\n".join(f"     {k}: {', '.join(v)}" for k, v in opt.items() if k != "expressions")
    plan = (
        "4. Tool sẽ TỰ VẼ nhân vật kiểu hoạt hình đầu tròn, thân con nhộng (không tay chân) "
        "và tự vẽ bối cảnh. Nên mỗi nhân vật thêm \"kit\" chọn ĐÚNG giá trị trong danh mục:\n"
        f"{cat}\n"
        "   (species: human/dog/cat; con vật thì chỉ cần species và fur; top là kiểu áo: ao_nau áo "
        "nâu nông dân, ao_ba_ba, ao_cach áo cánh + váy, dress áo + váy, jacket, shirt sơ mi, "
        "sweater, robe áo dài thụng, ao_dai; hat: non_la nón lá, khan_van khăn vấn, khan_dau "
        "khăn quấn đầu; patched: true nếu áo vá)\n"
        "   Mỗi địa điểm thêm \"kind\" (mẫu bối cảnh) và \"time\" (ngay|dem). Mẫu bối cảnh: "
        f"{story_live.kinds_text()}\n"
        "   Ví dụ: {\"id\":\"lao_hac\",\"name\":\"Lão Hạc\",\"look\":\"...\",\"kit\":{\"species\":\"human\","
        "\"age\":\"old\",\"sex\":\"male\",\"hair\":\"messy\",\"hair_color\":\"gray\",\"facial\":\"goatee\","
        "\"top\":\"ao_nau\",\"top_color\":\"brown\",\"bottom_color\":\"black\",\"patched\":true}}; "
        "{\"id\":\"nha\",\"name\":\"Nhà Lão Hạc\",\"look\":\"...\",\"kind\":\"nha_tranh\",\"time\":\"ngay\"}\n"
        "5. Truyện cần thứ CHƯA CÓ trong danh mục (vd mũ miện vua, mũ cánh chuồn, áo long bào, "
        "con trâu, con hổ, cung điện, ngôi chùa, khu rừng...) thì khai báo thêm "
        "\"new_parts\": [{\"id\":\"vuong_mien\",\"kind\":\"head\",\"name\":\"Mũ miện vua\","
        "\"desc\":\"mô tả hình dáng, màu sắc\"}] rồi dùng đúng id đó: kind head (đội/đeo trên "
        "đầu) -> kit.hat; body (hoa văn, đồ khoác trên áo) -> kit.extra; animal (con vật) -> "
        "kit.species; scene (bối cảnh) -> kind của địa điểm. Tool sẽ tự vẽ các bộ phận này. "
        "Chỉ khai báo khi thật cần, tối đa 8; thứ gần giống có sẵn thì dùng cái có sẵn.\n")
    acts = ", ".join(f"{k} ({v[0]})" for k, v in story_live.ACTS.items())
    scene = (
        "### Tool tự vẽ và cho nhân vật cử động — mỗi cảnh thêm:\n"
        "- \"acts\": nhân vật có mặt đang làm gì, {id: hành động}, hành động là một trong: "
        f"{acts}. Chọn theo lời kể của cảnh (khóc thì cry, vui thì happy, chết/ốm thì lie, "
        "người mới đến thì walk_in, bỏ đi thì walk_out). Không ghi thì đứng yên.\n"
        "- \"talk\": id nhân vật có câu nói được trích trong lời kể của cảnh (nhân vật đó nhép "
        "miệng khi người kể đọc câu trích), không có thì \"\".\n"
        "- \"time\": \"ngay\" hoặc \"dem\" nếu khác giờ mặc định của địa điểm (không cần thì bỏ).\n"
        "- \"chars\" chỉ gồm người/vật THẤY trong cảnh (tối đa 4), người đang được nhắc tới "
        "nhưng không có mặt thì không đưa vào.\n"
        "Ví dụ: {\"text\":\"...\",\"prompt\":\"...\",\"chars\":[\"lao_hac\",\"cau_vang\"],"
        "\"place\":\"nha\",\"camera\":\"zoom_in\",\"acts\":{\"lao_hac\":\"cry\",\"cau_vang\":\"idle\"},"
        "\"talk\":\"lao_hac\"}\n")
    return plan, scene


# Thoại nhân vật xen giữa lời kể: (nhãn, phần thêm vào câu lệnh viết chương)
_DIALOGUE_RULE = (
    "- \"lines\": câu THOẠI của nhân vật có mặt trong cảnh, đọc bằng giọng riêng của nhân vật "
    "ngay sau lời kể của cảnh: [{{\"who\":\"id\",\"text\":\"câu nói ngắn, tự nhiên, đúng tính "
    "cách và cách xưng hô thời đó\"}}]. Có nguyên văn thì lấy đúng câu thoại trong truyện. Lời "
    "kể KHÔNG nhắc lại câu thoại đó (dẫn vào bằng \"lão bảo\", \"ông giáo hỏi\"... rồi để nhân "
    "vật tự nói). Mỗi câu thoại dưới 30 chữ, mỗi cảnh tối đa 3 câu. {freq}\n")
DIALOGUE = {
    "none": ("Không có thoại (chỉ người kể)", "- Không viết thoại nhân vật; mọi lời nói kể lại "
             "bằng lời người kể.\n"),
    "some": ("Thỉnh thoảng xen thoại", _DIALOGUE_RULE.format(
        freq="Chỉ thêm ở khoảng 1/4 số cảnh, ưu tiên lúc cảm xúc cao, đối đáp quan trọng; các "
             "cảnh khác không có \"lines\".")),
    "many": ("Nhiều thoại (đối đáp)", _DIALOGUE_RULE.format(
        freq="Thêm ở khoảng một nửa số cảnh, nhất là các đoạn hai người nói chuyện với nhau.")),
}


def default_voice(kit: dict | None) -> str:
    """Mô tả giọng OmniVoice theo tuổi, giới của nhân vật."""
    k = kit or {}
    female = k.get("sex") == "female"
    age = {"child": "child", "young": "young adult", "adult": "middle-aged",
           "old": "elderly"}.get(k.get("age"), "middle-aged")
    pitch = ("high pitch" if age in ("child", "young adult") else "moderate pitch") if female \
        else ("moderate pitch" if age in ("child", "young adult") else "low pitch")
    return f"{'female' if female else 'male'}, {age}, {pitch}"


def _make_parts(new_parts, say) -> list[str]:
    """Vẽ các bộ phận AI khai báo là còn thiếu (chưa có trong thư viện)."""
    from . import doodle_parts
    made = []
    todo = [p for p in (new_parts or []) if isinstance(p, dict)
            and p.get("kind") in doodle_parts.KINDS and (p.get("name") or p.get("id"))][:8]
    for k, p in enumerate(todo):
        pid = doodle_parts.slug(p.get("id") or p.get("name"))
        if doodle_parts.get(pid):
            continue
        say(0.04 + 0.03 * k / max(1, len(todo)), f"AI vẽ thêm: {p.get('name') or pid}")
        try:
            doodle_parts.design(p["kind"], str(p.get("name") or pid), str(p.get("desc") or ""),
                                pid=pid)
            made.append(pid)
        except Exception as e:  # noqa: BLE001
            logger.warning("Không vẽ được bộ phận %s: %s", pid, e)
    return made


def _clean_char(c: dict) -> dict:
    from . import doodle
    out = {"id": _slug(c.get("id") or c.get("name")), "name": str(c.get("name") or ""),
           "look": str(c.get("look") or "")}
    out["kit"] = doodle.clean_kit(c["kit"]) if isinstance(c.get("kit"), dict) and c["kit"] \
        else doodle.kit_from_look(out["name"], out["look"])
    v = c.get("voice") if isinstance(c.get("voice"), dict) else {}
    out["voice"] = {"voice": str(v.get("voice") or ""),
                    "instruct": str(v.get("instruct") or "") or default_voice(out["kit"])}
    return out


def _clean_place(p: dict) -> dict:
    from . import scene_art, story_live
    out = {"id": _slug(p.get("id") or p.get("name")), "name": str(p.get("name") or ""),
           "look": str(p.get("look") or "")}
    out["kind"] = p.get("kind") if scene_art.valid_kind(p.get("kind")) else story_live.place_kind(out)
    out["time"] = p.get("time") if p.get("time") in scene_art.TIMES else "ngay"
    return out


def _clean_scene(s: dict) -> dict:
    from . import story_live
    cam = str(s.get("camera") or "zoom_in")
    out = {"text": str(s.get("text") or "").strip(),
           "prompt": str(s.get("prompt") or "").strip(),
           "chars": [_slug(c) for c in (s.get("chars") or []) if c],
           "place": _slug(s.get("place")) if s.get("place") else "",
           "camera": cam if cam in CAMERAS else "zoom_in"}
    if isinstance(s.get("acts"), dict):
        out["acts"] = {_slug(k): story_live.act_of(v) for k, v in s["acts"].items()
                       if isinstance(v, str) and (v in story_live.ACTS or story_live.act_of(v) != "idle")}
    if "talk" in s:
        out["talk"] = _slug(s["talk"]) if s.get("talk") else ""
    if s.get("time") in ("ngay", "dem"):
        out["time"] = s["time"]
    lines = [{"who": _slug(x.get("who")), "text": str(x.get("text") or "").strip()}
             for x in (s.get("lines") or []) if isinstance(x, dict) and x.get("who")]
    lines = [x for x in lines if x["text"]][:3]
    if lines:
        out["lines"] = lines
        for x in lines:                     # người nói phải có mặt trong cảnh
            if x["who"] not in out["chars"] and len(out["chars"]) < 4:
                out["chars"].append(x["who"])
    return out


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


def _voice_ref(pdir: Path, key: str, language: str, cfg: dict) -> dict:
    """Giọng mẫu: giọng trong Thư viện nếu chọn, không thì tạo từ mô tả (cố định)."""
    from . import assets, pipeline
    if cfg.get("voice"):
        lib = assets.voice_path(cfg["voice"], language)
        if lib:
            return {"ref": str(lib), "ref_text": assets.voice_text(cfg["voice"], language)}
    return pipeline.voice_anchor(pdir, key, language, cfg.get("instruct") or None) or {}


def narrate_lines(st: dict, pdir: Path, language: str = "vi",
                  progress=None) -> dict[str, list[dict]]:
    """Đọc các câu thoại nhân vật (mỗi nhân vật một giọng cố định).
    Trả về {id cảnh: [{"who", "text", "path"}]}. Câu không đổi thì dùng lại."""
    import soundfile as sf
    from . import voice
    chars = {c["id"]: c for c in st.get("characters") or []}
    todo = [(sc, i, ln) for _ci, sc in all_scenes(st)
            for i, ln in enumerate(sc.get("lines") or []) if ln.get("text") and ln.get("who") in chars]
    out: dict[str, list[dict]] = {}
    if not todo:
        return out
    adir = pdir / AUDIO_DIR
    adir.mkdir(parents=True, exist_ok=True)
    refs: dict[str, dict] = {}
    for k, (sc, i, ln) in enumerate(todo):
        c = chars[ln["who"]]
        cfg = c.get("voice") or {"instruct": default_voice(c.get("kit"))}
        if ln["who"] not in refs:
            refs[ln["who"]] = _voice_ref(pdir, f"nv_{ln['who']}", language, cfg)
        ref = refs[ln["who"]]
        key = hashlib.md5(json.dumps([ln["text"], ref.get("ref"), cfg.get("instruct")],
                                     ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        path = adir / f"line_{sc['id']}_{i}_{key}.wav"
        if not path.exists():
            if progress:
                progress(k / len(todo), f"đọc thoại {k + 1}/{len(todo)}: {c.get('name')}")
            wav, sr = voice.synthesize(ln["text"], language,
                                       ref_wav=Path(ref["ref"]) if ref.get("ref") else None,
                                       ref_text=ref.get("ref_text"),
                                       instruct=None if ref.get("ref") else cfg.get("instruct"),
                                       seed=int(key[:6], 16))
            wav = voice.trim_silence(np.asarray(wav, dtype=np.float32), sr)
            for old in adir.glob(f"line_{sc['id']}_{i}_*.wav"):
                old.unlink(missing_ok=True)
            sf.write(str(path), wav, sr)
        out.setdefault(sc["id"], []).append({"who": ln["who"], "text": ln["text"],
                                             "name": c.get("name") or ln["who"], "path": path})
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
