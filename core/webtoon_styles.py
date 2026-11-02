# -*- coding: utf-8 -*-
"""Nét vẽ nhân vật cho tab Truyện webtoon.

Nhân vật webtoon là ảnh chị vẽ bằng Gemini / ChatGPT theo câu lệnh tool soạn; nét vẽ
quyết định đoạn mô tả phong cách đứng đầu mỗi câu lệnh. Có vài nét vẽ sẵn, chị thêm
được nét mới (tên + mô tả nét vẽ), lưu ở data/library/webtoon_styles.json nên mọi
truyện dùng lại được.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata

from . import config

FILE = config.LIBRARY / "webtoon_styles.json"
DEFAULT = "saeon"

PRESETS = {
    "saeon": {
        "label": "사연 썰툰 — người thật, nét đậm, màu phẳng (mặc định)",
        "note": "Như các kênh 썰 / 사연: người lớn tỉ lệ thật, viền đen đều, màu pastel phẳng, mắt đen to.",
        "genres": ["marriage", "revenge"],
        "prompt": ("Korean webtoon style exactly like Korean YouTube story-animation channels (\"썰\" / 사연 "
                   "animation): clean bold uniform black outlines, flat pastel colors, NO shading, no gradients, "
                   "no textures, simple neat line art, natural adult proportions, large oval solid black pupils "
                   "with a small white highlight, eyebrows as simple dark strokes, nose as one small line, small "
                   "simple mouth, hair drawn as flat color with a few black strand lines, clothes with simple "
                   "fold lines."),
    },
    "mochi": {
        "label": "Mochi 둥글이 — đầu bánh gạo, má hồng, mũm mĩm",
        "note": "Đầu tròn to bè ngang, mắt chấm có đốm sáng, má hồng, miệng mèo ω, thân nhỏ tay mũm mĩm.",
        "genres": ["comedy", "family"],
        "prompt": ("Cute round Korean \"dunggeuri\" (둥글이) character style like Korean 썰툰 story-animation "
                   "channels: chibi proportions about two heads tall, a very large round rice-cake shaped head "
                   "slightly wider than tall, small simple rounded body, short chubby arms with round hands, tiny "
                   "legs, thick soft dark rounded outlines, flat soft pastel colors, NO shading, no gradients, "
                   "small solid black oval eyes each with one tiny white highlight, pink round blush on both "
                   "cheeks, tiny cat-like \"ω\" mouth, no nose, eyebrows only when angry or sad, hair as one "
                   "simple flat color shape."),
    },
    "pretty": {
        "label": "Webtoon 웹툰 — người mảnh, mắt to long lanh",
        "note": "Người mảnh chân dài, mặt cằm V, có cổ, mắt to tròng nâu long lanh, lông mày mảnh, mũi một nét.",
        "genres": ["romance", "school", "office"],
        "prompt": ("Modern Korean webtoon (웹툰) romance-drama style: slim tall proportions, long legs, V-shaped "
                   "chin on an oval face, visible neck, big sparkling eyes with brown irises, black pupils, white "
                   "highlights and a bold upper eyelid (women have small eyelashes), thin straight eyebrows, nose "
                   "as one small line, small mouth, light pink blush, thin clean dark outlines, flat colors with "
                   "one simple soft cel-shade tone, glossy hair with a light highlight streak."),
    },
    "ssul_react": {
        "label": "썰툰 phản ứng — mặt cạn lời, nhăn mặt (như video 소개팅)",
        "note": ("Như video xem mắt: nét đen mảnh đều, màu phẳng sáng, da trắng hồng, mặt biểu cảm phóng đại "
                 "(mắt lờ đờ, lườm, nhăn), mỗi người một kiểu dễ nhớ (mập mặt tròn, đẹp trai sắc nét...)."),
        "genres": ["sogaeting", "romance", "office"],
        "prompt": ("Korean 썰툰 comedy-drama style exactly like popular Korean YouTube / TikTok story-animation "
                   "channels about blind dates and office life: clean thin uniform black outlines, flat bright "
                   "colors with NO shading, pale pinkish skin, simple line nose, eyes drawn as white ovals with "
                   "small black pupils that become exaggerated in reactions (heavy half-closed deadpan lids, "
                   "sharp glares, scrunched cringe, sweat drops, stress lines on the forehead), glossy hair with "
                   "a few strand lines, caricature body types that make each character instantly recognizable "
                   "(round chubby face, sharp handsome jaw, round glasses), simple modern clothes."),
    },
    "ssul_caricature": {
        "label": "썰툰 biếm hoạ hài — mặt phóng đại, nét dày (như video 동네 히어로)",
        "note": ("Như video chuyện hài tự kể: hoạt hình 2D biếm hoạ kiểu 병맛, màu phẳng, viền đen, mặt xấu-hài "
                 "phóng đại (mắt sụp lờ đờ, mũi bè, môi dày, nếp má sâu), da vàng tái, đầu to cổ ngắn."),
        "genres": ["funny_story", "comedy", "school"],
        "prompt": ("Korean B-grade comedy cartoon (병맛 썰툰) style like humorous Korean YouTube story-animation "
                   "channels: a flat 2D cartoon drawing, NOT realistic. Clean black ink outlines of medium "
                   "thickness, flat cel colors with only one simple darker shadow tone, no gradients, no "
                   "hatching. Ugly-funny caricature face: large head on a short stubby neck, droopy half-closed "
                   "sleepy eyelids with small dark pupils, a wide flat nose, thick lips, deep smile lines from "
                   "nose to mouth, sunken cheeks, sallow yellowish skin, messy thick black hair drawn as a flat "
                   "dark shape with a few spiky strands, simple everyday clothes with a few fold lines. Looks "
                   "like a funny comic panel, deadpan and awkward."),
        "avoid": ("Do NOT make it photorealistic or semi-realistic, no realistic skin texture, no cross-hatching "
                  "or pencil shading, no 3D, no anime big shiny eyes, no handsome idealized face."),
    },
    "manhwa": {
        "label": "Manhwa bán thực — mặt chi tiết, đổ bóng nhẹ",
        "note": "Tỉ lệ người thật, mặt đẹp chi tiết, mắt sắc, đổ bóng hai tông, thời trang Hàn hiện đại.",
        "genres": ["thriller", "mystery", "horror"],
        "prompt": ("Semi-realistic Korean manhwa drama style: realistic adult proportions, detailed attractive "
                   "faces, sharp expressive eyes, defined nose and lips, clean thin line art, soft two-tone cel "
                   "shading, natural muted colors, stylish modern Korean fashion."),
    },
}


def _custom() -> dict:
    try:
        data = json.loads(FILE.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict) and v.get("prompt")}


def all_styles() -> dict:
    out = {k: dict(v, custom=False) for k, v in PRESETS.items()}
    out.update({k: dict(v, custom=True) for k, v in _custom().items()})
    return out


def options() -> list[dict]:
    return [{"id": k, "label": v["label"], "note": v.get("note", ""), "genres": v.get("genres") or [],
             "prompt": v["prompt"], "custom": v["custom"]} for k, v in all_styles().items()]


def valid(sid: str) -> bool:
    return sid in all_styles()


def avoid_of(sid: str | None) -> str:
    """Điều cấm riêng của nét vẽ (đặt cuối câu lệnh để AI không vẽ lệch nét)."""
    return (all_styles().get(sid or DEFAULT) or {}).get("avoid", "")


def prompt_of(sid: str | None) -> str:
    s = all_styles()
    return (s.get(sid or DEFAULT) or s[DEFAULT])["prompt"]


def suggest(genre: str) -> str | None:
    """Nét vẽ hợp thể loại (nét chị tự thêm có chọn thể loại thì cũng tính)."""
    for k, v in all_styles().items():
        if genre in (v.get("genres") or []):
            return k
    return None


def _slug(s: str) -> str:
    t = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")[:28] or "net_ve"


def add(label: str, prompt: str, genres: list | None = None, note: str = "") -> str:
    """Thêm nét vẽ chị tự mô tả. Trả về id."""
    label, prompt = (label or "").strip()[:80], " ".join((prompt or "").split())[:1500]
    if not label or len(prompt) < 10:
        raise ValueError("Cần tên nét vẽ và mô tả nét vẽ (ít nhất vài chữ).")
    data = _custom()
    sid = "u_" + _slug(label)
    base, n = sid, 2
    while sid in data or sid in PRESETS:
        sid, n = f"{base}_{n}", n + 1
    data[sid] = {"label": label, "prompt": prompt, "note": (note or "").strip()[:200],
                 "genres": [g for g in (genres or []) if isinstance(g, str)][:12],
                 "created": time.strftime("%Y-%m-%d %H:%M")}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return sid


def remove(sid: str) -> bool:
    data = _custom()
    if sid not in data:
        return False
    data.pop(sid)
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return True
