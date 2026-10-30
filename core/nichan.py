# -*- coding: utf-8 -*-
"""Truyện 2ch (kiểu video ngắn kể chuyện Nhật: 2ch / 昭和 / 感動 / スカッと), khung dọc 9:16.

Mỗi câu một cảnh: thanh tiêu đề đen cố định trên cùng (chữ cam phát sáng, 2 dòng), dưới
là chữ to viền trắng (lời kể xanh, câu nói trong 「」 màu theo người nói), giữa khung là
hình nhân vật kiểu sticker (viền trắng) trên nền mờ; giọng đọc tiếng Nhật liền mạch.

Hình mỗi cảnh ("visual"):
  {"type": "char", "cid": "...", "emo": "worried"}            một nhân vật
  {"type": "two", "cids": ["a", "b"], "emos": ["angry", "shocked"]}
  {"type": "sticker", "id": "canh_sat_bat"}                   ảnh nhân vật có sẵn / chị tải vào kho
  {"type": "object", "desc_en": "a brown paper envelope..."}  cận đồ vật (ảnh AI chị vẽ)
Ảnh nhân vật: ảnh AI chị vẽ theo câu lệnh tool soạn (mỗi nét mặt một ảnh); chưa có thì
tool tự vẽ nhân vật kiểu Mochi tròn mũm mĩm cùng nét mặt. Cảnh nào chị tải ảnh riêng thì
dùng ảnh đó.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import time
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import config, doodle

W, H = 1080, 1920
TOP = 420                     # thanh tiêu đề
FPS = 30
LEAD = 0.06                   # giọng bắt đầu sau khi đổi cảnh
GAP = 0.09                    # nghỉ sau câu: cả nhịp ~0,15 giây như video mẫu (đọc liền)
SPEEDS = {"normal": ("Bình thường", None), "fast": ("Hơi nhanh (như video mẫu)", 1.1)}
BGM_LEVELS = {"soft": ("Nhỏ", -27.0), "mid": ("Vừa", -23.0), "loud": ("To", -19.0)}
MUSIC = config.LIBRARY / "nhac_nen"            # nhạc nền chị tự bỏ vào (mp3, wav, m4a, ogg)
MUSIC_EXT = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac")
PICS_DIR = "2ch_pics"         # trong thư mục dự án: <cid>/<emo>.png, scenes/<sid>.png, bgs/<place>.png
AUDIO_DIR = "2ch_audio"
BUILTIN = config.LIBRARY / "2ch_co_san"       # nhân vật có sẵn đi kèm tool
MINE = config.LIBRARY / "2ch_kho"             # nhân vật chị tải thêm vào kho

EMOS = ("neutral", "happy", "sad", "cry", "angry", "shocked", "worried", "think", "sleep", "sly")
EMO_VI = {"neutral": "bình thường", "happy": "vui", "sad": "buồn", "cry": "khóc", "angry": "giận",
          "shocked": "sốc", "worried": "lo lắng", "think": "suy nghĩ", "sleep": "ngủ", "sly": "ranh mãnh"}
EMO_EN = {"neutral": "calm neutral expression, mouth closed", "happy": "big happy smile, eyes curved",
          "sad": "sad expression, eyebrows down, small frown", "cry": "crying with big tears streaming down",
          "angry": "angry expression, furrowed brows, gritted teeth, red face",
          "shocked": "shocked expression, wide eyes, open mouth", "worried": "worried expression, sweat drop",
          "think": "thinking expression, hand on chin, looking up", "sleep": "eyes closed, sleeping peacefully",
          "sly": "sly smirk, half-closed eyes"}
FX = ("", "sweat", "anger", "shock", "cry", "think", "shake", "sleep")
FX_VI = {"": "không", "sweat": "giọt mồ hôi", "anger": "nổi gân", "shock": "vạch sốc", "cry": "nước mắt rơi",
         "think": "dấu suy nghĩ", "shake": "rung hình", "sleep": "zzz"}
GENRES = {
    "kando": "Cảm động 感動 (gia đình, người tốt, hy sinh thầm lặng)",
    "showa": "Chuyện thời Showa 昭和 (lên Tokyo làm việc, nghèo khó, tình người)",
    "sukatto": "Trả đũa đã đời スカッと (kẻ xấu bị vạch mặt)",
    "giji": "Nhà chồng 義実家 / mẹ chồng nàng dâu",
    "shokuba": "Công sở 職場 (sếp, đồng nghiệp, công ty đen)",
    "kinjo": "Hàng xóm ご近所トラブル",
    "gakko": "Học đường 学校",
    "koi": "Tình cảm 恋愛 / 修羅場",
    "warai": "Chuyện cười 笑える話",
    "kowai": "Chuyện rợn người 怖い話",
}
VOICE_MODES = {"cast": "Mỗi nhân vật một giọng + giọng người kể", "one": "Một người kể đọc tất cả"}
# màu chữ: lời kể xanh, người nói theo thứ tự nhân vật
NARR_COLOR = (24, 48, 232)
SPEAK_COLORS = [(232, 40, 70), (0, 140, 150), (40, 150, 40), (150, 60, 200), (230, 120, 0), (220, 60, 150)]
# phong cách ảnh nhân vật AI: mô tả nét vẽ đứng đầu câu lệnh + cách tả từng nét mặt cho hợp nét
ARTS = {
    "flat": {
        "label": "Minh hoạ phẳng dễ thương (giống 5 hình có sẵn)",
        "prompt": ("Simple cute flat Japanese clip-art illustration style, like free stock illustrations used in "
                   "Japanese presentations and 2ch story videos: soft rounded shapes, a large round head with a "
                   "slightly wide face, compact body about 3.5 heads tall, short rounded limbs. Thin soft outlines "
                   "drawn in a darker shade of each fill color (NOT black lines), with a slightly rough "
                   "colored-pencil / crayon texture on edges and fills. Flat pastel colors with a subtle paper grain, "
                   "no shading, no gradients, no shine. Face: small solid black dot eyes (or simple curved lines "
                   "when smiling or crying), a tiny pinkish nose, round pink blush on both cheeks, simple small "
                   "mouth (open mouth shows red inside). Hair is a flat dark shape with a few lighter vertical "
                   "streaks. Simple clothes with only a few fold lines. Warm, gentle, friendly look."),
        "emo": {"neutral": "calm gentle face, dot eyes, small closed smile",
                "happy": "very happy, eyes closed as upward curved lines (^ ^), big open smiling mouth",
                "sad": "sad face, dot eyes looking down, eyebrows slanted up in the middle, small frown",
                "cry": "crying, eyes shut as downward curves, tears streaming down, wobbly open mouth",
                "angry": "angry face, thick eyebrows slanted down toward the center, dot eyes, frowning mouth",
                "shocked": "shocked face, small dot eyes wide apart, mouth open in a small oval, sweat lines",
                "worried": "worried face, eyebrows slanted up, dot eyes, wavy mouth, a blue sweat drop",
                "think": "thinking, hand on chin, dot eyes looking up, small closed mouth",
                "sleep": "eyes closed as simple curves, peaceful sleeping face",
                "sly": "sly face, half-closed eyes, one-sided smirk"},
    },
    "chibi": {
        "label": "Chibi anime (như video mẫu 昭和)",
        "prompt": ("Cute chibi anime illustration exactly like Japanese YouTube story shorts (2ch / 昭和 story videos): "
                   "large head about one third of the body height, big expressive brown eyes with white highlights, "
                   "rosy blush cheeks, soft cel shading, clean dark brown outlines, warm natural colors, detailed but "
                   "simple clothes."),
        "emo": EMO_EN,
    },
}
DEFAULT_ART = "flat"
STYLE_EN = ARTS["chibi"]["prompt"]


def art_of(st: dict | None) -> dict:
    return ARTS.get((st or {}).get("art") or DEFAULT_ART, ARTS[DEFAULT_ART])


def default_story() -> dict:
    return {"brief": "", "genre": "kando", "minutes": 3, "language": "ja", "title1": "", "title2": "",
            "cta": True, "voice_mode": "cast", "art": DEFAULT_ART, "speed": "normal", "bgm": "", "bgm_level": "soft", "narrator": {}, "characters": [], "places": [], "scenes": [],
            "pics": {}}


def slug(v) -> str:
    t = unicodedata.normalize("NFD", str(v or "").replace("đ", "d").replace("Đ", "D"))
    t = t.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:24] or "x"


# ---------------------------------------------------------------- kho nhân vật (sticker)

def stickers() -> list[dict]:
    """Nhân vật có sẵn + nhân vật chị tải vào kho: [{id, name, desc, people, builtin}]."""
    out = []
    for base, builtin in ((BUILTIN, True), (MINE, False)):
        try:
            items = json.loads((base / "meta.json").read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for it in items:
            if isinstance(it, dict) and (base / f"{it.get('id')}.png").exists():
                out.append(dict(it, builtin=builtin))
    return out


def sticker_path(sid: str) -> Path | None:
    if not re.fullmatch(r"[a-z0-9_]+", sid or ""):
        return None
    for base in (MINE, BUILTIN):
        if (base / f"{sid}.png").exists():
            return base / f"{sid}.png"
    return None


def add_sticker(src: Path, name: str, desc: str = "") -> str:
    from . import webtoon_pics as wpic
    name = (name or "").strip()[:80]
    if not name:
        raise ValueError("Cần đặt tên cho nhân vật / hình.")
    MINE.mkdir(parents=True, exist_ok=True)
    try:
        items = json.loads((MINE / "meta.json").read_text("utf-8"))
    except Exception:  # noqa: BLE001
        items = []
    taken = {it.get("id") for it in items} | {it["id"] for it in stickers()}
    sid, n = "k_" + slug(name), 2
    base = sid
    while sid in taken:
        sid, n = f"{base}_{n}", n + 1
    wpic._cutout(src).save(MINE / f"{sid}.png")
    items.append({"id": sid, "name": name, "desc": (desc or name).strip()[:300], "people": 1,
                  "created": time.strftime("%Y-%m-%d %H:%M")})
    (MINE / "meta.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return sid


def remove_sticker(sid: str) -> bool:
    try:
        items = json.loads((MINE / "meta.json").read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return False
    keep = [it for it in items if it.get("id") != sid]
    if len(keep) == len(items):
        return False
    (MINE / "meta.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    (MINE / f"{sid}.png").unlink(missing_ok=True)
    return True


# ---------------------------------------------------------------- dữ liệu

def clean_visual(v, ids: set, k_ok: set) -> dict:
    v = v if isinstance(v, dict) else {}
    t = v.get("type")
    if t == "two":
        cids = [c for c in (v.get("cids") or []) if c in ids][:2]
        emos = [e if e in EMOS else "neutral" for e in (list(v.get("emos") or []) + ["neutral", "neutral"])[:2]]
        if len(cids) == 2:
            return {"type": "two", "cids": cids, "emos": emos}
        t, v = "char", {"cid": cids[0] if cids else "", "emo": emos[0]}
    if t == "sticker" and v.get("id") in k_ok:
        return {"type": "sticker", "id": v["id"]}
    if t == "object" and str(v.get("desc_en") or "").strip():
        return {"type": "object", "desc_en": str(v["desc_en"]).strip()[:300]}
    cid = v.get("cid") if v.get("cid") in ids else ""
    return {"type": "char", "cid": cid, "emo": v.get("emo") if v.get("emo") in EMOS else "neutral"}


def clean_scene(s: dict, ids: set, places: set, k_ok: set, k: int) -> dict:
    who = s.get("who") if s.get("who") in ids or s.get("who") == "narr" else "narr"
    out = {"id": s.get("id") or f"c{k + 1:03d}", "text": str(s.get("text") or "").strip()[:120], "who": who,
           "visual": clean_visual(s.get("visual"), ids, k_ok),
           "place": s.get("place") if s.get("place") in places else (next(iter(places), "")),
           "fx": s.get("fx") if s.get("fx") in FX else ""}
    if s.get("img"):
        out["img"] = s["img"]
    return out


def clean_story(st: dict) -> dict:
    """Chuẩn hoá nhân vật, địa điểm, cảnh (sau khi AI viết / chị sửa)."""
    chars = []
    for c in st.get("characters") or []:
        if not isinstance(c, dict):
            continue
        cid = slug(c.get("id") or c.get("name"))
        if cid in {x["id"] for x in chars}:
            continue
        kit = doodle.clean_kit(dict(c.get("kit") or {}, species="human"))
        v = c.get("voice")
        v = {"instruct": v} if isinstance(v, str) else (v if isinstance(v, dict) else {})
        chars.append({"id": cid, "name": str(c.get("name") or cid)[:40], "kit": kit,
                      "desc_en": str(c.get("desc_en") or "").strip()[:400],
                      "voice": {"voice": str(v.get("voice") or ""), "instruct": str(v.get("instruct") or "").strip()}})
    st["characters"] = chars[:8]
    from . import scene_art
    pl = []
    for p in st.get("places") or []:
        if not isinstance(p, dict):
            continue
        pid = slug(p.get("id") or p.get("name"))
        if pid in {x["id"] for x in pl}:
            continue
        pl.append({"id": pid, "name": str(p.get("name") or pid)[:60],
                   "kind": p.get("kind") if p.get("kind") in scene_art.KINDS else "phong_khach",
                   "time": "dem" if p.get("time") == "dem" else "ngay",
                   "look": str(p.get("look") or "").strip()[:400]})
    st["places"] = pl[:10]
    ids, places = {c["id"] for c in chars}, {p["id"] for p in pl}
    k_ok = {k["id"] for k in stickers()}
    st["scenes"] = [clean_scene(s, ids, places, k_ok, k) for k, s in enumerate(st.get("scenes") or [])
                    if isinstance(s, dict) and str(s.get("text") or "").strip()][:400]
    narr = st.get("narrator") or {}
    if not narr.get("voice") and not (narr.get("instruct") or "").strip():
        st["narrator"] = dict(narrator_default(st), auto=True)      # tool tự mô tả (chị sửa được)
    n_ins = "" if st["narrator"].get("voice") else st["narrator"].get("instruct") or ""
    auto_voices(st["characters"], [", ".join(_voice_mod().parse_instruct(n_ins))]
                if n_ins else [])
    seen = set()
    for k, s in enumerate(st["scenes"]):                  # id cảnh không trùng
        if s["id"] in seen:
            s["id"] = f"c{k + 1:03d}x"
        seen.add(s["id"])
    return st


# ---------------------------------------------------------------- câu lệnh vẽ ảnh AI

def char_desc(c: dict) -> str:
    if c.get("desc_en"):
        return c["desc_en"]
    k = c.get("kit") or {}
    age = {"child": "8-year-old", "young": "20-year-old", "adult": "40-year-old", "old": "70-year-old"}.get(k.get("age"))
    who = ("girl" if k.get("age") == "child" else "woman") if k.get("sex") == "female" else \
        ("boy" if k.get("age") == "child" else "man")
    return f"a {age or ''} Japanese {who}, {k.get('hair_color', 'black')} {k.get('hair', 'short')} hair, " \
           f"{k.get('top_color', '')} {k.get('top', 'shirt')}".replace("_", " ")


def prompt_char(c: dict, emo: str, first: bool, art: dict | None = None) -> str:
    art = art or ARTS[DEFAULT_ART]
    ref = ("If a style sample image is attached, copy its drawing style exactly (line, color, texture, proportions), "
           "but draw a NEW character. " if first else
           "Use the attached image as the character reference: keep exactly the same face, hairstyle, clothes, "
           "colors and drawing style. ")
    return (f"{ref}{art['prompt']} Draw {char_desc(c)} ({c.get('name')}), "
            f"{art['emo'].get(emo, art['emo']['neutral'])}. "
            "Full body standing (or upper body if more natural), character centered and facing the viewer. "
            "Plain solid bright green (#00FF00) background like a green screen, nothing else in the image, "
            "no green on the character, no text, no frame. Vertical 3:4 image.")


def prompt_object(desc: str, art: dict | None = None) -> str:
    art = art or ARTS[DEFAULT_ART]
    look = art["prompt"].split(":")[0] if art is ARTS["chibi"] else \
        ("Simple cute flat Japanese clip-art illustration style: thin soft outlines in a darker shade of the fill "
         "color, slightly rough colored-pencil texture, flat pastel colors, no shading")
    return (f"{look}. Draw a close-up of {desc}, centered, single object. "
            "Plain solid bright green (#00FF00) background, nothing else, no text, no frame. Square image.")


def prompt_bg(p: dict) -> str:
    light = "warm evening light" if p.get("time") != "dem" else "night, soft lamp light"
    look = p.get("look") or f"{p.get('name')}, Japan"
    return (f"Create a background illustration for a vertical 9:16 video: soft painted anime background art, "
            f"{look}, {light}, slightly blurred depth of field, no people, no characters, no text. Vertical 9:16 image.")


def needed(st: dict) -> list[dict]:
    """Ảnh nhân vật kịch bản cần: mỗi nhân vật ảnh "bình thường" (vẽ trước, làm mẫu) + các nét mặt dùng."""
    have = st.get("pics") or {}
    cnt: dict = {}
    for s in st.get("scenes") or []:
        v = s.get("visual") or {}
        pairs = [(v.get("cid"), v.get("emo"))] if v.get("type") == "char" else \
            list(zip(v.get("cids") or [], v.get("emos") or [])) if v.get("type") == "two" else []
        for cid, emo in pairs:
            if cid:
                cnt[(cid, emo or "neutral")] = cnt.get((cid, emo or "neutral"), 0) + 1
    out = []
    art = art_of(st)
    for c in st.get("characters") or []:
        emos = ["neutral"] + sorted({e for (ci, e) in cnt if ci == c["id"] and e != "neutral"},
                                    key=lambda e: -cnt[(c["id"], e)])
        for e in emos:
            out.append({"cid": c["id"], "emo": e, "scenes": cnt.get((c["id"], e), 0),
                        "have": e in (have.get(c["id"]) or {}), "prompt": prompt_char(c, e, e == "neutral", art)})
    return out


def prompt_rows(st: dict, pdir: Path | None, kind: str, cid: str | None = None, missing: bool = True) -> list[dict]:
    """Câu lệnh vẽ theo đúng thứ tự các ô (để tải file câu lệnh / tải nhiều ảnh một lần).
    kind: chars (ảnh nhân vật), bgs (ảnh nền), objects (ảnh đồ vật). [{key, label, prompt, have}]."""
    rows = []
    if kind == "chars":
        names = {c["id"]: c.get("name") or c["id"] for c in st.get("characters") or []}
        for n in needed(st):
            if cid is None or n["cid"] == cid:
                rows.append({"key": f"{n['cid']}/{n['emo']}", "label": f"{names.get(n['cid'])} — {EMO_VI.get(n['emo'])}",
                             "prompt": n["prompt"], "have": n["have"]})
    elif kind == "bgs":
        for p in st.get("places") or []:
            have = bool(pdir and (Path(pdir) / PICS_DIR / "bgs" / f"{p['id']}.png").exists())
            rows.append({"key": p["id"], "label": p.get("name") or p["id"], "prompt": prompt_bg(p), "have": have})
    elif kind == "objects":
        for i, s in enumerate(st.get("scenes") or []):
            v = s.get("visual") or {}
            if v.get("type") == "object":
                rows.append({"key": s["id"], "label": f"Cảnh {i + 1}: {v['desc_en'][:40]}",
                             "prompt": prompt_object(v["desc_en"], art_of(st)), "have": bool(s.get("img"))})
    return [r for r in rows if not (missing and r["have"])]


# ---------------------------------------------------------------- AI viết

def write(st: dict, progress=None) -> dict:
    from . import claude_cli, scene_art
    say = progress or (lambda f, m: None)
    minutes = max(0.5, min(8.0, float(st.get("minutes") or 3)))
    n = max(8, int(minutes * 60 / 2.6))
    ks = stickers()
    opt = doodle.options()
    kit_cat = "\n".join(f"   {k}: {', '.join(opt[k])}" for k in ("age", "sex", "skin", "hair", "hair_color", "hat",
                                                                    "glasses", "facial", "top", "top_color",
                                                                    "bottom", "bottom_color"))
    cta = claude_cli._load_prompt("webtoon_cta", cta_who='người kể ("who":"narr")',
                                  cta_shot='"visual" là nhân vật chính với nét mặt chân thành',
                                  lang_label="tiếng Nhật") if st.get("cta", True) else ""
    say(0.05, "AI viết truyện, chia cảnh")
    data = claude_cli._run_json(claude_cli._load_prompt(
        "nichan_write", minutes=f"{minutes:g}", n=str(n), genre=GENRES.get(st.get("genre"), st.get("genre") or ""),
        brief=(st.get("brief") or "(tự nghĩ một chuyện hay theo thể loại)"),
        title_hint=(f"Tiêu đề chị đã đặt: {st.get('title1')} / {st.get('title2')} — giữ đúng."
                    if (st.get("title1") or "").strip() else ""),
        stickers="\n".join(f"   - {k['id']}: {k['desc']}" for k in ks) or "   (chưa có)",
        emos=", ".join(EMOS), fx=", ".join(f for f in FX if f),
        kinds=scene_art.kinds_catalog() if hasattr(scene_art, "kinds_catalog") else ", ".join(scene_art.KINDS),
        kit_cat=kit_cat, cta_block=cta), task="story", timeout=900)
    if not isinstance(data, dict) or not data.get("scenes"):
        raise RuntimeError("AI không viết được truyện.")
    st["title1"] = (st.get("title1") or "").strip() or str(data.get("title1") or "")[:20]
    st["title2"] = (st.get("title2") or "").strip() or str(data.get("title2") or "")[:20]
    keep_voice = {c["id"]: c.get("voice") for c in st.get("characters") or []
                  if (c.get("voice") or {}).get("voice")}           # giữ giọng Thư viện chị đã chọn
    if (st.get("narrator") or {}).get("auto"):
        st["narrator"] = {}                               # truyện mới: tool mô tả lại giọng người kể
    st["characters"] = data.get("characters") or []
    st["places"] = data.get("places") or []
    st["scenes"] = data.get("scenes") or []
    clean_story(st)
    for c in st["characters"]:
        if keep_voice.get(c["id"]):
            c["voice"] = keep_voice[c["id"]]
    say(1.0, "xong")
    return st


# ---------------------------------------------------------------- giọng

def speak_text(text: str) -> str:
    return re.sub(r"\s+", "", text.replace("「", "").replace("」", "").replace("\n", ""))


def _voice_mod():
    from . import voice
    return voice


PITCHES = ["very low pitch", "low pitch", "moderate pitch", "high pitch", "very high pitch"]


def auto_voices(chars: list, reserved: list | None = None) -> None:
    """Nhân vật chưa có giọng (không chọn giọng Thư viện, không mô tả): tool tự mô tả giọng theo
    tuổi, giới (chỉ dùng từ khoá bộ đọc giọng hiểu); hai người trùng mô tả thì đổi cao độ cho khác."""
    from . import story, voice
    used = list(reserved or [])                           # giọng người kể: nhân vật không trùng
    for c in chars:
        v = c.setdefault("voice", {})
        if v.get("voice"):
            continue
        parts = voice.parse_instruct(v.get("instruct") or "")
        if not parts:
            parts = story.default_voice(c.get("kit")).split(", ")
        pitch = next((p for p in parts if p in PITCHES), "moderate pitch")
        base = [p for p in parts if p not in PITCHES]
        i = PITCHES.index(pitch)
        for step in (0, 1, -1, 2, -2):                    # trùng người trước thì nhích cao độ
            j = max(0, min(len(PITCHES) - 1, i + step))
            cand = ", ".join(base + [PITCHES[j]])
            if cand not in used:
                break
        used.append(cand)
        v["instruct"] = cand


def narrator_default(st: dict) -> dict:
    """Giọng người kể mặc định như video mẫu: kể ngôi thứ nhất "俺 / 僕" thì nam trầm ấm; còn lại
    theo giới của nhân vật chính (nhân vật đầu tiên)."""
    text = "".join(sc.get("text", "") for sc in st.get("scenes") or [] if sc.get("who") == "narr")
    chars = st.get("characters") or []
    male = bool(re.search("俺|僕|オレ", text)) or not chars or (chars[0].get("kit") or {}).get("sex") != "female"
    if male:
        return {"instruct": "male, middle-aged, low pitch"}
    return {"instruct": "female, middle-aged, moderate pitch"}


def narrate(st: dict, pdir: Path, progress=None) -> dict:
    """Đọc từng câu bằng tiếng Nhật. {id cảnh: file wav}."""
    import soundfile as sf
    from . import film_render, voice
    chars = {c["id"]: c for c in st.get("characters") or []}
    one = st.get("voice_mode") == "one"
    scenes = [s for s in st.get("scenes") or [] if speak_text(s.get("text", ""))]
    speakers = {("narr" if one or s["who"] not in chars else s["who"]) for s in scenes}
    adir = pdir / AUDIO_DIR
    adir.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(0.0, "chọn giọng cho người kể và nhân vật")
    narr = dict(st.get("narrator") or {})
    narr.pop("auto", None)
    if not narr.get("voice") and not (narr.get("instruct") or "").strip():
        narr = narrator_default(st)
    if not narr.get("voice"):                    # chữ thêm này bộ đọc bỏ qua; để không bị đổi sang giọng khác
        narr["instruct"] = narr["instruct"] + ", storytelling voice"
    shim = {"characters": [{"id": c["id"], "voice": c.get("voice") or {}, "kit": c["kit"]} for c in chars.values()],
            "narrator": narr}
    speed = SPEEDS.get(st.get("speed") or "normal", SPEEDS["normal"])[1]
    got = film_render.cast(shim, pdir, "ja", [x for x in speakers if x != "narr"], narr="narr" in speakers)
    out = {}
    for k, s in enumerate(scenes):
        who = "narr" if one or s["who"] not in chars else s["who"]
        cfg, ref = got.get("nguoi_ke" if who == "narr" else f"nv_{who}") or ({"instruct": "female, young adult"}, {})
        text = speak_text(s["text"])
        key = hashlib.md5(json.dumps([text, ref.get("ref"), ref.get("ref_text"), cfg.get("instruct"), speed, "ja2"],
                                     ensure_ascii=False)
                          .encode("utf-8")).hexdigest()[:12]
        path = adir / f"{s['id']}_{key}.wav"
        if not path.exists():
            if progress:
                progress(k / max(1, len(scenes)), f"đọc câu {k + 1}/{len(scenes)}")
            wav, sr = voice.synthesize(text, "ja", ref_wav=Path(ref["ref"]) if ref.get("ref") else None,
                                       ref_text=ref.get("ref_text"),
                                       instruct=None if ref.get("ref") else cfg.get("instruct"),
                                       speed=speed, seed=int(key[:6], 16))
            wav = voice.trim_silence(np.asarray(wav, dtype=np.float32), sr)
            for old in adir.glob(f"{s['id']}_*.wav"):
                old.unlink(missing_ok=True)
            sf.write(str(path), wav, sr)
        out[s["id"]] = path
    return out


def timeline(st: dict, audio: dict) -> list[dict]:
    import soundfile as sf
    rows, t = [], 0.0
    for s in st.get("scenes") or []:
        a = audio.get(s["id"])
        d = 0.0
        if a and Path(a).exists():
            info = sf.info(str(a))
            d = info.frames / info.samplerate
        dur = max(0.8, d + LEAD + GAP) if d else max(1.6, 0.13 * len(speak_text(s["text"])) + 0.6)
        rows.append({"scene": s, "start": t, "dur": dur, "audio": a})
        t += dur
    return rows


# ---------------------------------------------------------------- chữ

_FONT_CANDS = [r"C:\Windows\Fonts\BIZ-UDGothicB.ttc", r"C:\Windows\Fonts\YuGothB.ttc",
               r"C:\Windows\Fonts\meiryob.ttc", r"C:\Windows\Fonts\msgothic.ttc",
               "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
               "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
               "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
               "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]


def ja_font(size: int) -> ImageFont.FreeTypeFont:
    for f in _FONT_CANDS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


_NO_START = set("、。，．・！？!?）」』ーぁぃぅぇぉっゃゅょァィゥェォッャュョ…")


def wrap(text: str, font, maxw: int) -> list[str]:
    """Xuống dòng theo chỗ AI ngắt (\\n), dòng nào dài quá thì ngắt theo chữ (không để dấu câu đầu dòng)."""
    out = []
    for para in text.split("\n"):
        line = ""
        for ch in para:
            if font.getlength(line + ch) > maxw and line and ch not in _NO_START:
                out.append(line)
                line = ch
            else:
                line += ch
        if line:
            out.append(line)
    return out or [""]


def _text_layer(lines, font, color, w, gap, stroke=12) -> Image.Image:
    lh = int(font.size * 1.18)
    img = Image.new("RGBA", (w, lh * len(lines) + gap * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        xy = (w // 2, gap + i * lh + lh // 2)
        d.text(xy, ln, font=font, anchor="mm", fill=(40, 40, 70), stroke_width=stroke + 5, stroke_fill=(40, 40, 70))
        d.text(xy, ln, font=font, anchor="mm", fill=color, stroke_width=stroke, stroke_fill=(255, 255, 255))
    return img


def caption(text: str, color) -> Image.Image:
    size = 104
    while True:
        f = ja_font(size)
        lines = wrap(text, f, W - 90)
        if len(lines) <= 3 or size <= 64:
            break
        size -= 8
    return _text_layer(lines, f, color, W, 10)


def title_bar(t1: str, t2: str) -> np.ndarray:
    """Thanh tiêu đề đen, chữ cam chuyển màu phát sáng (2 dòng)."""
    img = Image.new("RGB", (W, TOP), (0, 0, 0))
    for txt, size, y in ((t1, 148, 150), (t2, 112, 320)):
        if not txt:
            continue
        f = ja_font(size)
        while f.getlength(txt) > W - 60 and size > 60:
            size -= 8
            f = ja_font(size)
        m = Image.new("L", (W, TOP), 0)
        ImageDraw.Draw(m).text((W // 2, y), txt, font=f, anchor="mm", fill=255, stroke_width=16, stroke_fill=255)
        img.paste((150, 80, 30), (0, 0), m.filter(ImageFilter.GaussianBlur(16)))           # quầng sáng
        ImageDraw.Draw(img).text((W // 2, y), txt, font=f, anchor="mm", fill=(70, 34, 18), stroke_width=9,
                                 stroke_fill=(70, 34, 18))
        fill = Image.new("L", (W, TOP), 0)
        ImageDraw.Draw(fill).text((W // 2, y), txt, font=f, anchor="mm", fill=255)
        g = np.zeros((TOP, W, 3), np.uint8)
        top = y - size / 2
        for r in range(TOP):
            u = max(0.0, min(1.0, (r - top) / size))
            g[r] = (int(255 - 30 * u), int(224 - 110 * u), int(160 - 110 * u))
        img.paste(Image.fromarray(g), (0, 0), fill)
    return np.asarray(img)


# ---------------------------------------------------------------- hình

def sticker_style(im: Image.Image, border: int = 12) -> Image.Image:
    """Viền trắng + bóng mờ quanh hình (kiểu sticker như video mẫu)."""
    import cv2
    pad = border * 3
    a = np.asarray(im.getchannel("A"))
    a = np.pad(a, pad)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (border * 2 + 1, border * 2 + 1))
    big = cv2.dilate(a, k)
    out = np.zeros((a.shape[0], a.shape[1], 4), np.uint8)
    sh = cv2.GaussianBlur(big, (0, 0), border * 0.8)
    sh = np.roll(np.roll(sh, border // 2, 0), border // 3, 1)
    out[..., 3] = (sh * 0.35).astype(np.uint8)
    white = big > 0
    out[white] = (255, 255, 255, 255)
    rgba = np.zeros_like(out)
    rgba[pad:pad + im.height, pad:pad + im.width] = np.asarray(im.convert("RGBA"))
    al = rgba[..., 3:4].astype(np.float32) / 255
    out[..., :3] = (rgba[..., :3] * al + out[..., :3] * (1 - al)).astype(np.uint8)
    out[..., 3] = np.maximum(out[..., 3], rgba[..., 3])
    return Image.fromarray(out)


def rig_image(kit: dict, emo: str, T: float = 900.0) -> Image.Image:
    """Nhân vật tool tự vẽ (kiểu Mochi) khi chưa có ảnh AI: vẽ trên nền đen và trắng rồi
    tính độ trong suốt từ hai bản."""
    from . import film_act, film_rig
    sty = film_rig.clean_style(film_rig.CHAR_STYLES["mochi"])
    rig = film_rig.Rig(doodle.clean_kit(kit), T, 7, sty)
    cw, ch = int(T * 1.3), int(T * 1.08)
    cam = np.array([[1, 0, 0], [0, 1, 0]], float)
    act = {"cry": "cry", "think": "think", "angry": "angry", "shocked": "hands_up", "happy": "happy"}.get(emo, "idle")
    p = film_act.pose(act, 0.35, 7)
    p.update(x=cw / 2, y=ch - 4, dir=1, look=0.0, expr=emo, blink=False, mouth=emo == "shocked")
    if act == "hands_up":
        p["arms"] = [(40, 60), (40, 60)]
    bufs = []
    for bg in (0, 255):
        c = np.full((ch, cw, 3), bg, np.uint8)
        rig.draw(c, dict(p), cam, 1.0)
        bufs.append(c.astype(np.float32))
    af = np.clip(255.0 - (bufs[1] - bufs[0]).max(axis=2), 0, 255)
    rgb = np.clip(bufs[0] * 255.0 / np.maximum(af[..., None], 1.0), 0, 255).astype(np.uint8)
    a = af.astype(np.uint8)
    im = Image.fromarray(np.dstack([rgb, a]))
    box = im.getbbox()
    return im.crop(box) if box else im


def _fit(im: Image.Image, mw: int, mh: int) -> Image.Image:
    k = min(mw / im.width, mh / im.height)
    return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)


class Renderer:
    """Vẽ khung hình: chuẩn bị sẵn nền, hình, chữ của từng cảnh (cache), mỗi khung chỉ ghép."""

    def __init__(self, st: dict, pdir: Path | None):
        self.st, self.pdir = st, pdir
        self.chars = {c["id"]: c for c in st.get("characters") or []}
        self.places = {p["id"]: p for p in st.get("places") or []}
        self.colors = {c["id"]: SPEAK_COLORS[i % len(SPEAK_COLORS)] for i, c in enumerate(st.get("characters") or [])}
        self.title = title_bar(st.get("title1") or "", st.get("title2") or "")
        self._bg: dict = {}
        self._img: dict = {}
        self._cap: dict = {}
        self._vis: dict = {}
        self._head: dict = {}

    # --- ảnh
    def _file(self, *parts) -> Path | None:
        if self.pdir is None:
            return None
        p = Path(self.pdir) / PICS_DIR / Path(*parts)
        return p if p.exists() else None

    def char_img(self, cid: str, emo: str) -> Image.Image | None:
        key = ("c", cid, emo)
        if key in self._img:
            return self._img[key]
        c = self.chars.get(cid)
        im = None
        if c:
            have = (self.st.get("pics") or {}).get(cid) or {}
            for e in (emo, "neutral", *have.keys()):
                f = self._file(cid, f"{e}.png") if e in have else None
                if f:
                    im = Image.open(f).convert("RGBA")
                    break
            if im is None:
                im = rig_image(c["kit"], emo)
        self._img[key] = sticker_style(im) if im is not None else None
        return self._img[key]

    def visual(self, s: dict, last: list | None) -> list:
        """[(ảnh RGBA đã có viền, x giữa, y đáy, kiểu)]."""
        if s["id"] in self._vis:
            return self._vis[s["id"]]
        v = s.get("visual") or {}
        out = []
        own = self._file("scenes", f"{s['id']}.png") if s.get("img") else None
        if own:
            im = sticker_style(_fit(Image.open(own).convert("RGBA"), 900, 1000))
            out = [(im, W // 2, TOP + 120 + (H - TOP - 120) // 2 + im.height // 2, "float")]
        elif v.get("type") == "sticker":
            p = sticker_path(v.get("id"))
            if p:
                im = sticker_style(_fit(Image.open(p).convert("RGBA"), 980, 1060))
                out = [(im, W // 2, H - 60, "stand")]
        elif v.get("type") == "two":
            for i, (cid, emo) in enumerate(zip(v["cids"], v["emos"])):
                im = self.char_img(cid, emo)
                if im is not None:
                    im = _fit(im, 560, 1000)
                    out.append((im, int(W * (0.29 if i == 0 else 0.71)), H - 50, "stand"))
        elif v.get("type") == "char" and v.get("cid"):
            im = self.char_img(v["cid"], v.get("emo", "neutral"))
            if im is not None:
                out = [(_fit(im, 1000, 1080), W // 2, H - 40, "stand")]
        if not out:                                       # đồ vật chưa có ảnh: giữ hình cảnh trước
            out = last or []
            if not out and self.chars:
                first = next(iter(self.chars))
                out = [(_fit(self.char_img(first, "neutral"), 1000, 1080), W // 2, H - 40, "stand")]
        self._vis[s["id"]] = out
        return out

    def bg(self, pid: str) -> np.ndarray:
        if pid in self._bg:
            return self._bg[pid]
        from . import scene_art
        p = self.places.get(pid) or {"kind": "phong_khach", "time": "ngay"}
        bw, bh = int(W * 1.08), int((H - TOP) * 1.08)
        f = self._file("bgs", f"{pid}.png")
        if f:
            im = Image.open(f).convert("RGB")
            k = max(bw / im.width, bh / im.height)
            im = im.resize((int(im.width * k) + 1, int(im.height * k) + 1), Image.LANCZOS)
            x0, y0 = (im.width - bw) // 2, (im.height - bh) // 2
            im = im.crop((x0, y0, x0 + bw, y0 + bh)).filter(ImageFilter.GaussianBlur(3))
        else:
            im = scene_art.render_scene(p.get("kind", "phong_khach"), p.get("time", "ngay"), size=(bw, bh),
                                        seed=zlib_seed(pid)).convert("RGB").filter(ImageFilter.GaussianBlur(7))
        self._bg[pid] = np.asarray(im)
        return self._bg[pid]

    def cap(self, s: dict) -> np.ndarray:
        if s["id"] not in self._cap:
            col = NARR_COLOR if s["who"] == "narr" else self.colors.get(s["who"], NARR_COLOR)
            self._cap[s["id"]] = np.asarray(caption(s["text"], col))
        return self._cap[s["id"]]

    def head_of(self, im: Image.Image) -> tuple[float, float, float]:
        """Đầu trong ảnh (toạ độ ảnh): (x giữa, y tâm đầu, bán kính), đo từ viền hình: đỉnh hình,
        bề ngang lớn nhất ở phần trên."""
        key = id(im)
        if key not in self._head:
            a = np.asarray(im.getchannel("A")) > 40
            rows = np.where(a.any(axis=1))[0]
            if not len(rows):
                self._head[key] = (im.width / 2, im.height * 0.25, im.width * 0.2)
            else:
                top = rows[0]
                xt = np.where(a[top])[0]
                x0 = int((xt[0] + xt[-1]) / 2)
                best = (0, x0, x0)
                for yy in range(top, min(a.shape[0], top + int(im.height * 0.4))):
                    if not a[yy, x0]:
                        continue
                    lo = x0                                   # đoạn liền quanh giữa đầu (bỏ tay giơ riêng ra)
                    while lo > 0 and a[yy, lo - 1]:
                        lo -= 1
                    hi = x0
                    while hi < a.shape[1] - 1 and a[yy, hi + 1]:
                        hi += 1
                    if hi - lo > best[0] * 1.35 and best[0] and yy - top > (best[0] or 1) * 0.9:
                        break                                 # tới vai / tay: bề ngang vọt lên
                    if hi - lo > best[0]:
                        best = (hi - lo, lo, hi)
                r = min(best[0] / 2 * 0.92, im.width * 0.42, im.height * 0.3) or im.width * 0.2
                self._head[key] = (float((best[1] + best[2]) / 2), float(top + r * 0.98), float(r))
        return self._head[key]

    # --- một khung
    def frame(self, row: dict, t: float) -> np.ndarray:
        """Khung ở giây t của cảnh (gọi visual(cảnh, hình cảnh trước) trước khi vào cảnh)."""
        import cv2
        from . import film_rig
        s, dur = row["scene"], row["dur"]
        can = np.zeros((H, W, 3), np.uint8)
        can[:TOP] = self.title
        bg = self.bg(s.get("place"))
        z = 1.0 + 0.035 * min(1.0, t / max(dur, 0.1))         # máy quay đẩy vào chậm
        bh, bw = bg.shape[:2]
        cw, ch = int(bw / 1.08 / z * 1.0), int(bh / 1.08 / z)
        x0, y0 = (bw - cw) // 2, (bh - ch) // 2
        can[TOP:] = cv2.resize(bg[y0:y0 + ch, x0:x0 + cw], (W, H - TOP), interpolation=cv2.INTER_LINEAR)
        shake = s.get("fx") in ("shake", "shock") and t < 0.6
        vis = self.visual(s, None)
        for im, cx, by, kind in vis:
            u = min(1.0, t / 0.28)                              # nảy vào cảnh
            sc = 0.86 + 0.14 * (1 - (1 - u) ** 3) + 0.035 * math.sin(math.pi * u)
            sc *= 1.0 + 0.006 * math.sin(t * 2.4)              # thở nhẹ
            dx = int(14 * math.sin(t * 60)) if shake else 0
            arr = np.asarray(im)
            nw, nh = max(1, int(im.width * sc)), max(1, int(im.height * sc))
            arr = cv2.resize(arr, (nw, nh), interpolation=cv2.INTER_LINEAR)
            x = int(cx - nw / 2) + dx
            y = int(by - nh) if kind == "stand" else int(by - im.height / 2 - nh / 2)
            _blend(can, arr, x, max(TOP - 40, y))
            if s.get("fx") and len(vis) == 1:
                act = {"sweat": "tremble", "anger": "angry", "shock": "hands_up", "cry": "cry",
                       "think": "think", "sleep": "sleep"}.get(s["fx"])
                if act:                                     # dấu cảm xúc bám đúng đầu nhân vật
                    hx, hy, hr = self.head_of(im)
                    k = nw / im.width
                    film_rig.marks(can, act, t, (x + hx * k, max(y, TOP - 40) + hy * k, hr * k), 900, 1)
        capa = self.cap(s)
        _blend(can, capa, 0, TOP + 60)
        return can


def zlib_seed(s: str) -> int:
    import zlib
    return zlib.crc32((s or "x").encode()) % 997


def _blend(can: np.ndarray, rgba: np.ndarray, x: int, y: int) -> None:
    h, w = rgba.shape[:2]
    X0, Y0, X1, Y1 = max(0, x), max(0, y), min(can.shape[1], x + w), min(can.shape[0], y + h)
    if X1 <= X0 or Y1 <= Y0:
        return
    src = rgba[Y0 - y:Y1 - y, X0 - x:X1 - x]
    a = src[..., 3:4].astype(np.uint16)
    dst = can[Y0:Y1, X0:X1]
    dst[:] = ((src[..., :3].astype(np.uint16) * a + dst.astype(np.uint16) * (255 - a)) // 255).astype(np.uint8)


def preview(st: dict, i: int, pdir: Path | None = None, t: float = 0.6) -> Image.Image:
    scenes = st.get("scenes") or []
    if not scenes:
        return Image.new("RGB", (W // 2, H // 2), (20, 20, 24))
    i = max(0, min(len(scenes) - 1, i))
    r = Renderer(st, pdir)
    prev = None
    for s in reversed(scenes[:i]):          # đồ vật chưa có ảnh: dùng hình cảnh trước gần nhất
        if (s.get("visual") or {}).get("type") != "object" or s.get("img"):
            prev = r.visual(s, None)
            break
    r.visual(scenes[i], prev)
    can = r.frame({"scene": scenes[i], "dur": 2.0}, t)
    return Image.fromarray(can).resize((W // 2, H // 2), Image.LANCZOS)


# ---------------------------------------------------------------- dựng video

def render(st: dict, pdir: Path, audio: dict | None = None, progress=None, out_name: str = "video.mp4") -> Path:
    import soundfile as sf
    from . import video, webtoon_film as wf
    audio = audio or {}
    rows = timeline(st, audio)
    if not rows:
        raise RuntimeError("Chưa có cảnh nào.")
    total = sum(r["dur"] for r in rows) + 0.4
    out_dir = pdir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "2ch_video.mp4"
    ff = video._ffmpeg_path()
    enc = wf.NVENC if wf.gpu_encode(ff) else wf.X264
    proc = subprocess.Popen([ff, "-y", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{W}x{H}",
                             "-framerate", str(FPS), "-i", "-", *enc, str(raw)],
                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r = Renderer(st, pdir)
    n = int(total * FPS)
    try:
        k = 0
        r.visual(rows[0]["scene"], None)
        for f in range(n):
            t = f / FPS
            while k + 1 < len(rows) and t >= rows[k + 1]["start"]:
                k += 1
                r.visual(rows[k]["scene"], r.visual(rows[k - 1]["scene"], None))
            row = rows[k]
            proc.stdin.write(r.frame(row, t - row["start"]).tobytes())
            if progress and f % 60 == 0:
                progress(f / n, f"dựng hình {f}/{n}")
    finally:
        proc.stdin.close()
        proc.wait()
    sr = 24000
    mix = np.zeros(int(total * sr) + sr, dtype=np.float32)
    for row in rows:
        if not row.get("audio"):
            continue
        a, asr = sf.read(str(row["audio"]), dtype="float32", always_2d=False)
        if getattr(a, "ndim", 1) > 1:
            a = a.mean(axis=1)
        if asr != sr:
            x = np.linspace(0, len(a) - 1, int(len(a) * sr / asr))
            a = np.interp(x, np.arange(len(a)), a).astype(np.float32)
        a = a * (0.8 / (float(np.max(np.abs(a))) or 1.0))
        k0 = int((row["start"] + LEAD) * sr)
        mix[k0:k0 + len(a)] += a[: max(0, len(mix) - k0)]
    mix = _with_bgm(st, mix, sr, total)
    wav = out_dir / "2ch_audio.wav"
    sf.write(str(wav), np.clip(mix, -1, 1), sr)
    out = out_dir / out_name
    subprocess.run([ff, "-y", "-i", str(raw), "-i", str(wav), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                    "-shortest", str(out)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    raw.unlink(missing_ok=True)
    return out


def style_sample() -> Image.Image:
    """Ảnh mẫu nét vẽ (các hình có sẵn ghép trên nền trắng) để gửi kèm khi vẽ ảnh đầu tiên."""
    ims = []
    for it in stickers():
        if it.get("builtin"):
            im = Image.open(BUILTIN / f"{it['id']}.png").convert("RGBA")
            ims.append(_fit(im, 420, 420))
    if not ims:
        return Image.new("RGB", (400, 400), "white")
    out = Image.new("RGBA", (sum(i.width for i in ims) + 30 * (len(ims) + 1), 480), (255, 255, 255, 255))
    x = 30
    for im in ims:
        out.alpha_composite(im, (x, (480 - im.height) // 2))
        x += im.width + 30
    return out.convert("RGB")


# ---------------------------------------------------------------- nhạc nền

def music_list() -> list[dict]:
    if not MUSIC.exists():
        return []
    return [{"name": p.name, "size": p.stat().st_size} for p in sorted(MUSIC.iterdir())
            if p.suffix.lower() in MUSIC_EXT]


def music_path(name: str) -> Path | None:
    p = MUSIC / Path(name or "").name
    return p if name and p.exists() and p.suffix.lower() in MUSIC_EXT else None


def save_music(src: Path, filename: str) -> str:
    MUSIC.mkdir(parents=True, exist_ok=True)
    stem = slug(Path(filename).stem) or "nhac"
    ext = Path(filename).suffix.lower()
    if ext not in MUSIC_EXT:
        raise ValueError("Chỉ nhận file nhạc mp3, wav, m4a, ogg, flac, aac.")
    name, n = f"{stem}{ext}", 2
    while (MUSIC / name).exists():
        name, n = f"{stem}_{n}{ext}", n + 1
    Path(src).replace(MUSIC / name)
    return name


def _with_bgm(st: dict, voice_mix: np.ndarray, sr: int, total: float) -> np.ndarray:
    """Trộn nhạc nền (lặp lại cho đủ dài) nhỏ dưới giọng: tự giảm khi có lời, vào / ra nhỏ dần."""
    from . import video
    p = music_path(st.get("bgm") or "")
    if not p:
        return voice_mix
    raw = subprocess.run([video._ffmpeg_path(), "-v", "error", "-i", str(p), "-ac", "1", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True).stdout
    m = np.frombuffer(raw, dtype=np.float32)
    if len(m) < sr:
        return voice_mix
    n = len(voice_mix)
    m = np.tile(m, n // len(m) + 1)[:n].copy()
    m /= max(1e-4, float(np.sqrt(np.mean(m ** 2))) * 4)               # chuẩn hoá độ to
    db = BGM_LEVELS.get(st.get("bgm_level") or "soft", BGM_LEVELS["soft"])[1]
    gain = np.full(n, 10 ** (db / 20), dtype=np.float32)
    # giảm thêm 6 dB khi có giọng (bao mượt 0,15 giây)
    hop = int(sr * 0.05)
    env = np.abs(voice_mix[: n // hop * hop]).reshape(-1, hop).max(axis=1) > 0.02
    k = 3
    env = np.convolve(env.astype(float), np.ones(2 * k + 1) / (2 * k + 1), mode="same")
    duck = np.repeat(1.0 - 0.5 * np.clip(env * 1.5, 0, 1), hop)
    gain[: len(duck)] *= duck.astype(np.float32)
    fi, fo = int(sr * 1.0), int(sr * 2.5)
    end = min(n, int(total * sr))
    gain[:fi] *= np.linspace(0, 1, fi, dtype=np.float32)
    gain[max(0, end - fo):end] *= np.linspace(1, 0, end - max(0, end - fo), dtype=np.float32)
    gain[end:] = 0
    return voice_mix + m * gain
