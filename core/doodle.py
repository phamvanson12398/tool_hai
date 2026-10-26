# -*- coding: utf-8 -*-
"""Nhân vật kiểu vẽ tay kể chuyện Hàn: đầu tròn to, thân hình con nhộng không
tay chân, viền đen nét bút hơi run, màu phẳng dịu. Có người (trẻ con, thanh
niên, người lớn, người già), chó, mèo; nhiều kiểu tóc, mũ nón (nón lá, khăn
vấn), kính, râu và các kiểu áo xưa (áo nâu, áo bà ba, áo cánh + váy...).

render(kit, ...) trả về ảnh RGBA của một tư thế; story_live ráp vào cảnh và
cho cử động (thở, chớp mắt, khóc, nhảy, đi...).
"""
from __future__ import annotations

import math
import random
import re
import zlib

from PIL import Image, ImageDraw

OUT = (40, 34, 38)
SS = 2                     # vẽ to gấp đôi rồi thu nhỏ cho nét mượt

SKINS = {"light": (252, 226, 212), "fair": (246, 214, 190), "tan": (226, 186, 150),
         "dark": (176, 130, 100)}
HAIR_COLORS = {"black": (42, 40, 46), "darkbrown": (72, 54, 42), "brown": (112, 80, 54),
               "gray": (150, 150, 152), "white": (226, 226, 222), "salt": (186, 186, 182)}
CLOTH = {
    "brown": (140, 104, 74), "darkbrown": (100, 74, 56), "indigo": (70, 82, 120),
    "navy": (52, 62, 96), "blue": (92, 128, 176), "lightblue": (164, 196, 222),
    "white": (240, 238, 230), "cream": (236, 222, 190), "beige": (214, 196, 158),
    "gray": (150, 150, 150), "darkgray": (82, 82, 86), "black": (52, 50, 54),
    "red": (204, 92, 84), "pink": (220, 176, 176), "green": (110, 150, 96),
    "olive": (128, 130, 84), "yellow": (232, 200, 104), "purple": (150, 120, 170),
    "orange": (224, 146, 80),
}
FUR = {"yellow": (228, 184, 96), "brown": (150, 104, 66), "black": (60, 56, 60),
       "white": (238, 234, 226), "gray": (160, 160, 164), "orange": (226, 150, 80),
       "spotted": (238, 234, 226)}

SPECIES = ("human", "dog", "cat")
AGES = ("child", "young", "adult", "old")
SEXES = ("male", "female")
HAIRS = ("short", "bangs", "messy", "side_part", "bun", "long", "bob", "bald", "balding",
         "wavy", "bowl", "curly", "curl_top", "perm", "twoblock", "longbang", "slick")
HATS = ("none", "non_la", "khan_van", "khan_dau", "hat")
GLASSES = ("none", "round", "square")
FACIAL = ("none", "mustache", "beard", "stubble", "goatee")
TOPS = ("ao_nau", "ao_ba_ba", "ao_cach", "dress", "jacket", "shirt", "sweater", "robe",
        "ao_dai", "tshirt", "shirt_tie", "suit", "blazer", "cardigan", "hoodie", "apron")
BOTTOMS = ("pants", "shorts", "skirt")  # quần dài / quần soóc (lộ chân) / chân váy xếp ly
EXPRESSIONS = ("neutral", "happy", "sad", "cry", "angry", "shocked", "worried", "sleep",
               "sly", "think")


def default_kit() -> dict:
    return {"species": "human", "age": "adult", "sex": "male", "skin": "light",
            "hair": "short", "hair_color": "black", "hat": "none", "glasses": "none",
            "facial": "none", "top": "ao_nau", "top_color": "brown", "bottom_color": "black",
            "patched": False, "fur": "yellow", "extra": "none", "bottom": "pants"}


def _custom(kind: str) -> list[str]:
    from . import doodle_parts
    return doodle_parts.ids(kind)


def clean_kit(k: dict | None) -> dict:
    """Giữ giá trị hợp lệ (kể cả bộ phận AI vẽ thêm), thiếu thì lấy mặc định."""
    out = default_kit()
    k = k or {}
    for key, ok in (("species", list(SPECIES) + _custom("animal")), ("age", AGES),
                    ("sex", SEXES), ("skin", SKINS),
                    ("hair", HAIRS), ("hair_color", HAIR_COLORS),
                    ("hat", list(HATS) + _custom("head")),
                    ("extra", ["none"] + _custom("head") + _custom("body")),
                    ("glasses", GLASSES), ("facial", FACIAL), ("top", TOPS),
                    ("top_color", CLOTH), ("bottom_color", CLOTH), ("fur", FUR),
                    ("bottom", BOTTOMS)):
        v = str(k.get(key, "")).strip().lower()
        if v in ok:
            out[key] = v
    out["patched"] = bool(k.get("patched"))
    if isinstance(k.get("_sty"), dict):            # kiểu nhân vật (film_rig.CHAR_STYLES)
        out["_sty"] = k["_sty"]
    return out


def options() -> dict:
    return {"species": list(SPECIES) + _custom("animal"), "age": list(AGES),
            "sex": list(SEXES), "skin": list(SKINS), "hair": list(HAIRS),
            "hair_color": list(HAIR_COLORS), "hat": list(HATS) + _custom("head"),
            "extra": ["none"] + _custom("head") + _custom("body"),
            "glasses": list(GLASSES), "facial": list(FACIAL),
            "top": list(TOPS), "top_color": list(CLOTH), "bottom_color": list(CLOTH),
            "bottom": list(BOTTOMS),
            "fur": list(FUR), "expressions": list(EXPRESSIONS)}


# ------------------------------------------------------------ đoán từ mô tả

_COLOR_WORDS = [
    ("dark brown", "darkbrown"), ("dark-brown", "darkbrown"), ("indigo", "indigo"),
    ("navy", "navy"), ("light blue", "lightblue"), ("dark gray", "darkgray"),
    ("dark grey", "darkgray"), ("brown", "brown"), ("blue", "blue"), ("white", "white"),
    ("cream", "cream"), ("beige", "beige"), ("khaki", "beige"), ("gray", "gray"),
    ("grey", "gray"), ("black", "black"), ("red", "red"), ("pink", "pink"),
    ("green", "green"), ("olive", "olive"), ("yellow", "yellow"), ("purple", "purple"),
    ("orange", "orange"), ("nâu", "brown"), ("chàm", "indigo"), ("trắng", "white"),
    ("đen", "black"),
]


def _color_in(text: str):
    best = None
    for w, c in _COLOR_WORDS:
        i = text.find(w)
        if i >= 0 and (best is None or i < best[0]):
            best = (i, c)
    return best[1] if best else None


def kit_from_look(name: str, look: str) -> dict:
    """Đoán bộ ghép từ mô tả ngoại hình tiếng Anh (khi AI chưa chọn sẵn)."""
    t = f" {(look or '').lower()} "
    n = f" {(name or '').lower()} "
    k = default_kit()
    if re.search(r"\bdog\b|puppy|\bchó\b", t + n) or "cậu vàng" in n:
        k["species"] = "dog"
    elif re.search(r"\bcat\b|kitten|\bmèo\b", t + n):
        k["species"] = "cat"
    if k["species"] != "human":
        k["fur"] = next((c for w, c in (("golden", "yellow"), ("yellow", "yellow"),
                                         ("orange", "orange"), ("black", "black"),
                                         ("white", "white"), ("gray", "gray"),
                                         ("grey", "gray"), ("spot", "spotted"),
                                         ("brown", "brown")) if w in t), "yellow")
        return k
    female = re.search(r"\b(woman|wife|girl|mother|grandmother|lady|female|she|her|"
                       r"daughter|sister|aunt|widow)\b", t) or re.search(
        r"\b(bà|chị|cô|mẹ|vợ|thị|o|cái)\b", n)
    k["sex"] = "female" if female else "male"
    m = re.search(r"(\d{2})s?\b", t)
    age_num = int(m.group(1)) if m else None
    if age_num and age_num >= 55:
        k["age"] = "old"
    elif age_num and age_num < 13:
        k["age"] = "child"
    elif age_num and age_num < 30:
        k["age"] = "young"
    elif age_num:
        k["age"] = "adult"
    elif re.search(r"\b(old|elderly|aged|grandfather|grandmother|senior)\b", t) or \
            re.search(r"^ (lão|cụ|ông lão|bà lão)\b", n):
        k["age"] = "old"
    elif re.search(r"\b(child|kid|little|boy|girl|toddler)\b", t):
        k["age"] = "child"
    elif re.search(r"\b(young|teen|youth)\b", t):
        k["age"] = "young"
    if re.search(r"tanned|sun-?burn|dark skin|weathered", t):
        k["skin"] = "tan"
    # tóc
    if re.search(r"\bbald\b", t):
        k["hair"] = "balding" if re.search(r"balding|thin", t) else "bald"
    elif "bun" in t:
        k["hair"] = "bun"
    elif re.search(r"long hair|long black hair|braid", t):
        k["hair"] = "long"
    elif "bob" in t:
        k["hair"] = "bob"
    elif re.search(r"messy|rough|shaggy|unkempt|tousled|spiky", t):
        k["hair"] = "messy"
    elif re.search(r"bangs|fringe", t):
        k["hair"] = "bangs"
    elif re.search(r"parted|side part|neat", t):
        k["hair"] = "side_part"
    elif re.search(r"wavy|curly|bushy|thick", t):
        k["hair"] = "wavy"
    else:
        k["hair"] = ("bun" if k["age"] in ("adult", "old") else "long") \
            if k["sex"] == "female" else "short"
    hm = re.search(r"(gray|grey|white|silver|salt|brown|black)[- ](?:\w+[- ])?hair", t)
    if hm:
        k["hair_color"] = {"grey": "gray", "silver": "white", "salt": "salt"}.get(hm.group(1), hm.group(1))
    elif k["age"] == "old":
        k["hair_color"] = "gray"
    if re.search(r"headscarf|head scarf|turban|khăn vấn|head wrap", t):
        k["hat"] = "khan_van"
    elif re.search(r"conical hat|nón lá|non la|palm-leaf hat", t):
        k["hat"] = "non_la"
    elif re.search(r"head ?towel|bandana|khăn", t):
        k["hat"] = "khan_dau"
    elif re.search(r"\bhat\b|\bcap\b", t):
        k["hat"] = "hat"
    if "glasses" in t or "spectacles" in t:
        k["glasses"] = "round" if "round" in t else "square"
    if re.search(r"beard", t):
        k["facial"] = "goatee" if re.search(r"sparse|thin|wispy|goatee", t) else "beard"
    elif re.search(r"mustache|moustache", t):
        k["facial"] = "mustache"
    elif "stubble" in t:
        k["facial"] = "stubble"
    # áo
    if re.search(r"bà ba|ba ba", t):
        k["top"] = "ao_ba_ba"
    elif re.search(r"áo dài|ao dai|tunic|long robe|robe", t):
        k["top"] = "ao_dai" if "dai" in t or "dài" in t else "robe"
    elif re.search(r"\bsuit\b|business attire", t):
        k["top"] = "suit"
    elif re.search(r"school uniform|blazer", t):
        k["top"] = "blazer"
    elif "cardigan" in t:
        k["top"] = "cardigan"
    elif "hoodie" in t:
        k["top"] = "hoodie"
    elif "apron" in t:
        k["top"] = "apron"
    elif re.search(r"\bdress\b", t) and k["sex"] == "female":
        k["top"] = "dress"
    elif "skirt" in t and k["sex"] == "female":
        k["top"] = "shirt"
    elif re.search(r"jacket|uniform|coat|blazer", t):
        k["top"] = "jacket"
    elif re.search(r"sweater|knit", t):
        k["top"] = "sweater"
    elif re.search(r"blouse|áo cánh|ao canh", t):
        k["top"] = "ao_cach" if k["sex"] == "female" else "ao_nau"
    elif re.search(r"long-sleeve shirt|white shirt|button|shirt", t) and \
            not re.search(r"peasant", t):
        k["top"] = "shirt"
    else:
        k["top"] = "dress" if k["sex"] == "female" and k["age"] == "old" else \
            ("ao_ba_ba" if k["sex"] == "female" else "ao_nau")
    tm = re.search(r"([\w -]{0,30}?)(shirt|jacket|blouse|tunic|sweater|coat|top|uniform|"
                   r"áo|robe|dress)", t)
    top_c = _color_in(tm.group(0)) if tm else None
    k["top_color"] = top_c or _color_in(t) or ("brown" if k["top"] == "ao_nau" else "beige")
    bm = re.search(r"([\w -]{0,25}?)(trousers|pants|skirt|shorts)", t)
    k["bottom_color"] = (_color_in(bm.group(0)) if bm else None) or \
        (k["top_color"] if k["top"] in ("dress", "robe", "ao_dai") else "black")
    if "skirt" in t and k["sex"] == "female" and k["top"] not in ("dress", "robe", "ao_dai", "ao_cach"):
        k["bottom"] = "skirt"
    k["patched"] = bool(re.search(r"patch|torn|ragged|worn", t))
    return k


# ------------------------------------------------------------ nét vẽ tay

def _noise(seed: int):
    r = random.Random(seed)
    ph = [(r.uniform(0, 6.28), r.uniform(0.6, 1.4)) for _ in range(3)]

    def f(x):
        return sum(math.sin(x * w * (i + 1) * 0.9 + p) / (i + 1) for i, (p, w) in enumerate(ph)) / 1.8
    return f


def _wob(pts, amp, seed, closed=True, step=6.0):
    """Làm run đường viền: chia nhỏ rồi dịch theo nhiễu mượt."""
    if len(pts) < 2:
        return pts
    seq = list(pts) + ([pts[0]] if closed else [])
    dense = []
    for (x0, y0), (x1, y1) in zip(seq, seq[1:]):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / (step * SS)))
        for i in range(n):
            u = i / n
            dense.append((x0 + (x1 - x0) * u, y0 + (y1 - y0) * u))
    if not closed:
        dense.append(seq[-1])
    fx, fy = _noise(seed), _noise(seed + 101)
    return [(x + fx(i * 0.08) * amp, y + fy(i * 0.08) * amp) for i, (x, y) in enumerate(dense)]


def _ellipse_pts(cx, cy, rx, ry, a0=0.0, a1=360.0, n=60):
    out = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        out.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return out


class _Pen:
    def __init__(self, img, T, seed):
        self.d = ImageDraw.Draw(img)
        self.T = T
        self.lw = max(2, int(T * 0.021))
        self.seed = seed
        self.amp = T * 0.0035
        self.k = 0

    def shape(self, pts, fill, outline=True, width=None, wob=True):
        self.k += 1
        p = _wob(pts, self.amp, self.seed + self.k) if wob else list(pts)
        if fill is not None:
            self.d.polygon(p, fill=fill)
        if outline:
            w = width or self.lw
            self.d.line(p + [p[0]], fill=OUT, width=w, joint="curve")
            r = w / 2
            for x, y in (p[0],):
                self.d.ellipse([x - r, y - r, x + r, y + r], fill=OUT)

    def line(self, pts, width=None, fill=OUT, wob=True):
        self.k += 1
        p = _wob(pts, self.amp * 0.7, self.seed + self.k, closed=False) if wob else pts
        w = width or self.lw
        self.d.line(p, fill=fill, width=w, joint="curve")
        r = w / 2
        for x, y in (p[0], p[-1]):
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

    def ell(self, cx, cy, rx, ry, fill, outline=True, width=None, wob=True):
        self.shape(_ellipse_pts(cx, cy, rx, ry), fill, outline, width, wob)

    def dot(self, x, y, r, fill=OUT):
        self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def _mix(c, d, u):
    """Pha màu c với d (u = 0..1 phần d) — dùng thay màu trong suốt (ảnh RGBA vẽ đè không pha)."""
    return tuple(int(a + (b - a) * u) for a, b in zip(c, d))


def _qbez(p0, c, p1, n=10):
    """Đường cong bậc hai p0 -> p1, điểm điều khiển c."""
    out = []
    for i in range(n + 1):
        t = i / n
        out.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0],
                    (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1]))
    return out


def _qpath(start, segs, n=10):
    """Nối các đoạn: (điểm điều khiển, điểm cuối) là đường cong, (x, y) là đoạn thẳng."""
    pts, cur = [start], start
    for seg in segs:
        if isinstance(seg[0], tuple):
            pts += _qbez(cur, seg[0], seg[1], n)[1:]
            cur = seg[1]
        else:
            pts.append(seg)
            cur = seg
    return pts


def _sty(kit) -> dict:
    return kit.get("_sty") or {}


def head_pts(cx, hy, R, shape="round"):
    """Khuôn mặt: tròn (mặc định), bánh gạo (mochi: bè ngang), trái xoan cằm V (webtoon)."""
    if shape == "mochi":
        return _ellipse_pts(cx, hy, R, 0.92 * R)
    if shape == "v":
        def P(x, y):
            return (cx + x * R, hy + y * R)
        return _qpath(P(-0.92, -0.15), [(P(-0.95, 0.55), P(-0.45, 0.95)), (P(0, 1.22), P(0.45, 0.95)),
                                        (P(0.95, 0.55), P(0.92, -0.15)), (P(0.9, -1.0), P(0, -1.0)),
                                        (P(-0.9, -1.0), P(-0.92, -0.15))], 8)
    return _ellipse_pts(cx, hy, R, R * 0.97)


def draw_head(pen: "_Pen", kit, cx, hy, R):
    """Cổ (kiểu nhân vật có cổ), tai nhỏ (mặt cằm V) rồi khuôn mặt màu da."""
    sty = _sty(kit)
    skin = SKINS[kit["skin"]]
    shape = sty.get("head_shape", "round")
    neck = float(sty.get("neck", 0.0) or 0.0)
    if neck > 0.02:                                 # cổ: từ dưới cằm xuống lẫn vào cổ áo
        w = 0.18 * R
        y1 = hy + (0.86 + neck) * R
        pen.shape([(cx - w, hy + 0.6 * R), (cx + w, hy + 0.6 * R), (cx + w, y1), (cx - w, y1)],
                  _shade(skin, 0.95), width=max(1, int(pen.lw * 0.85)), wob=False)
    if shape == "v" and not sty.get("ears"):
        for sx in (-1, 1):
            pen.ell(cx + sx * 0.93 * R, hy + 0.1 * R, 0.13 * R, 0.2 * R, skin)
    pen.shape(head_pts(cx, hy, R, shape), skin)


# ------------------------------------------------------------ người

def _belly_pts(cx, top, bottom, wt, wm, R, belly):
    """Thân bụng tròn: vai tròn, phình to nhất khoảng 60% chiều cao, đáy thu lại bo tròn."""
    h = bottom - top
    pts = _ellipse_pts(cx, top + 0.42 * R, wt, 0.42 * R, 180, 360, 20)
    right = []
    for k in range(1, 13):
        u = k / 12
        y = top + 0.42 * R + (h - 0.42 * R) * u
        w = wt + (wm - wt) * math.sin(math.pi * min(1.0, u / 0.72) / 2) ** 0.6 if u < 0.72 else \
            wm - (wm * (0.2 + 0.18 * belly)) * ((u - 0.72) / 0.28) ** 2
        right.append((cx + w, y))
    pts += right
    pts += [(cx - x + cx, y) for x, y in reversed(right)]
    return pts


def _body_pts(cx, top, bottom, wt, wb, R):
    """Thân con nhộng: vai tròn, đáy hơi loe, góc đáy bo."""
    pts = []
    pts += _ellipse_pts(cx, top + 0.42 * R, wt, 0.42 * R, 180, 270, 10)       # vai trái
    pts += _ellipse_pts(cx, top + 0.42 * R, wt, 0.42 * R, 270, 360, 10)       # vai phải
    r = 0.2 * R
    pts.append((cx + wb, bottom - r))
    pts += _ellipse_pts(cx + wb - r, bottom - r, r, r, 0, 90, 6)
    pts += _ellipse_pts(cx - wb + r, bottom - r, r, r, 90, 180, 6)
    pts.append((cx - wt, top + 0.42 * R))
    return pts


def _draw_body(img, pen: _Pen, kit, cx, top, bottom, R, seed):
    female = kit["sex"] == "female"
    wt = R * (0.66 if female else 0.74)
    wb = R * (0.84 if female else 0.86)
    if kit["top"] == "dress":
        wb = R * 0.98
    if kit["age"] == "child":
        wt, wb = wt * 0.92, wb * 0.92
    face = _sty(kit).get("face") or "default"
    if face == "webtoon" and kit["top"] != "dress":    # vai rộng vuông, eo thon
        wt, wb = wt * 1.12, wb * 0.92
    belly = float((kit.get("_sty") or {}).get("belly", 0.0) or 0.0)
    if belly > 0.05:                                # bụng tròn: vai hẹp, phình ở dưới, thu lại ở đáy
        wt *= 1 - 0.18 * belly
        pts = _belly_pts(cx, top, bottom, wt, wb * (1 + 0.42 * belly), R, belly)
        wb = wb * (1 + 0.42 * belly)
    else:
        pts = _body_pts(cx, top, bottom, wt, wb, R)
    top_c = CLOTH[kit["top_color"]]
    bot_c = CLOTH[kit["bottom_color"]]
    t_ = kit["top"]
    h = bottom - top
    split = {"dress": 0.46, "robe": 1.2, "ao_dai": 0.86, "jacket": 0.62, "sweater": 0.6,
             "ao_ba_ba": 0.62, "ao_cach": 0.5, "tshirt": 0.74}.get(kit["top"], 0.64)
    if kit["top"] == "tshirt" and kit.get("bottom") == "shorts":
        split = 0.78                                # áo phông trùm bụng, quần soóc chỉ là dải dưới
    if face in ("mochi", "webtoon") and t_ not in ("dress", "robe", "ao_dai"):
        split = 0.72 if face == "mochi" else 0.9    # mochi: dải quần dưới; webtoon: áo tới hông
    # lớp thân: tô áo, phần dưới tô quần/váy, cắt theo hình thân
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    wp = _wob(pts, pen.amp, seed + 7)
    ld.polygon(wp, fill=top_c)
    ys = top + h * split
    if face == "webtoon":                           # đổ bóng một mảng bên phải
        ld.polygon([(cx + 0.3 * wt, top), (cx + wb * 1.6, top), (cx + wb * 1.6, ys), (cx + 0.45 * wb, ys)],
                   fill=_shade(top_c, 0.93))
    if split < 1 and belly > 0.5 and t_ == "tshirt":
        # vạt áo phông cong theo bụng phệ: giữa võng xuống, quần soóc lộ hai bên
        arc = [(x, ys + 0.07 * R * (1 - ((x - cx) / (wb * 1.5)) ** 2)) for x in
               [cx - wb * 1.5 + wb * 3.0 * k / 20 for k in range(21)]]
        ld.polygon(arc + [(cx + wb * 1.6, bottom + 10), (cx - wb * 1.6, bottom + 10)], fill=bot_c)
        ld.line(arc, fill=OUT, width=max(1, int(pen.lw * 0.8)))
    elif split < 1:
        ld.rectangle([0, ys, img.size[0], bottom + 10], fill=bot_c)
        ld.line([(0, ys), (img.size[0], ys)], fill=OUT, width=max(1, int(pen.lw * 0.55)))
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(wp, fill=255)
    img.paste(layer, (0, 0), mask)
    d = pen.d
    thin = max(1, int(pen.lw * 0.55))
    t = kit["top"]
    neck_y = top + 0.14 * R
    if t in ("ao_nau", "ao_ba_ba", "ao_cach", "sweater", "tshirt"):
        pen.line(_ellipse_pts(cx, neck_y, 0.26 * R, 0.16 * R, 20, 160, 10), width=thin)
    if t == "tshirt":                               # cổ áo khoét chữ U thấy da
        skin = SKINS[kit["skin"]]
        pen.shape(_ellipse_pts(cx, neck_y + 0.08 * R, 0.32 * R, 0.42 * R, 0, 180, 14), skin, width=thin)
    if belly > 0.5:                                  # nếp bụng phệ dưới vạt áo
        pen.line(_ellipse_pts(cx, ys - 0.1 * R, wb * 0.55, 0.12 * R, 20, 160, 10), width=thin)
    if t == "sweater" and face == "default":
        pen.line([(cx - wb, ys - 0.05 * R), (cx + wb, ys - 0.05 * R)], width=int(pen.lw * 1.6),
                 fill=_shade(bot_c, 0.6))
        pen.shape([(cx - 0.12 * R, ys - 0.17 * R), (cx + 0.12 * R, ys - 0.17 * R),
                   (cx + 0.12 * R, ys + 0.07 * R), (cx - 0.12 * R, ys + 0.07 * R)],
                  (60, 56, 52), width=thin)
    if t in ("ao_nau", "ao_ba_ba"):
        for i in range(4):                                   # cúc áo
            yy = neck_y + 0.26 * R + i * (ys - neck_y - 0.3 * R) / 4
            if t == "ao_ba_ba":
                pen.dot(cx, yy, 0.035 * R, _shade(top_c, 0.55))
            else:
                pen.line([(cx - 0.07 * R, yy), (cx + 0.07 * R, yy)], width=thin,
                         fill=_shade(top_c, 0.55))
    if t == "ao_cach":                                       # cổ chéo, khuy tết
        pen.line([(cx - 0.18 * R, neck_y + 0.1 * R), (cx + 0.1 * R, ys)], width=thin)
        for i in range(3):
            yy = neck_y + 0.3 * R + i * 0.22 * R
            pen.line([(cx - 0.02 * R, yy), (cx + 0.14 * R, yy)], width=thin)
    if t == "dress":
        pen.line(_ellipse_pts(cx, neck_y, 0.24 * R, 0.14 * R, 20, 160, 10), width=thin)
        pen.line([(cx, neck_y + 0.15 * R), (cx, ys)], width=thin)
        for i in range(3):
            yy = neck_y + 0.3 * R + i * 0.2 * R
            pen.line([(cx - 0.06 * R, yy), (cx + 0.06 * R, yy)], width=thin)
        for dx in (-0.45, 0.0, 0.45):                         # nếp váy
            pen.line([(cx + dx * R * 0.7, ys + 0.12 * R), (cx + dx * R * 0.95, bottom - 0.1 * R)],
                     width=thin)
    if t == "jacket":
        pen.shape([(cx - 0.3 * R, neck_y - 0.02 * R), (cx, neck_y + 0.36 * R),
                   (cx + 0.3 * R, neck_y - 0.02 * R), (cx + 0.1 * R, neck_y + 0.04 * R),
                   (cx, neck_y + 0.16 * R), (cx - 0.1 * R, neck_y + 0.04 * R)],
                  (238, 236, 230), width=thin)
        pen.line([(cx, neck_y + 0.36 * R), (cx, ys)], width=thin)
        pen.shape([(cx + 0.22 * R, neck_y + 0.42 * R), (cx + 0.56 * R, neck_y + 0.42 * R),
                   (cx + 0.56 * R, neck_y + 0.56 * R), (cx + 0.22 * R, neck_y + 0.56 * R)],
                  (246, 244, 236), width=thin)
        for sx in (-1, 1):
            pen.line([(cx + sx * 0.28 * R, ys + 0.12 * R), (cx + sx * 0.6 * R, ys + 0.12 * R)],
                     width=thin)
    if t == "shirt":
        pen.shape([(cx - 0.26 * R, neck_y - 0.02 * R), (cx, neck_y + 0.24 * R),
                   (cx - 0.04 * R, neck_y + 0.02 * R)], _shade(top_c, 1.05), width=thin)
        pen.shape([(cx + 0.26 * R, neck_y - 0.02 * R), (cx, neck_y + 0.24 * R),
                   (cx + 0.04 * R, neck_y + 0.02 * R)], _shade(top_c, 1.05), width=thin)
        for i in range(3):
            pen.dot(cx, neck_y + 0.4 * R + i * 0.2 * R, 0.03 * R, _shade(top_c, 0.55))
    if t in ("robe", "ao_dai"):
        pen.line([(cx, neck_y + 0.1 * R), (cx, bottom - 0.1 * R)], width=thin)
        pen.line(_ellipse_pts(cx, neck_y, 0.22 * R, 0.12 * R, 20, 160, 8), width=thin)
    if t in ("shirt_tie", "suit", "blazer"):
        tie = (61, 90, 153) if face == "mochi" else (176, 58, 72)
        if t != "shirt_tie":                                  # sơ mi trắng cổ chữ V
            pen.shape([(cx - 0.3 * R, top + 0.02 * R), (cx, top + 0.78 * R), (cx + 0.3 * R, top + 0.02 * R)],
                      (246, 246, 244), width=thin, wob=False)
        else:
            for sx in (-1, 1):
                pen.shape([(cx + sx * 0.3 * R, neck_y - 0.04 * R), (cx, neck_y + 0.2 * R),
                           (cx + sx * 0.05 * R, neck_y)], _shade(top_c, 1.04), width=thin, wob=False)
        n0 = neck_y + 0.04 * R
        pen.shape([(cx, n0), (cx - 0.09 * R, n0 + 0.1 * R), (cx, n0 + 0.66 * R), (cx + 0.09 * R, n0 + 0.1 * R)],
                  tie, width=thin, wob=False)
        if t != "shirt_tie":                                  # ve áo
            for sx in (-1, 1):
                pen.line([(cx + sx * 0.3 * R, top + 0.02 * R), (cx + sx * 0.09 * R, top + 0.9 * R),
                          (cx + sx * wb * 0.95, ys)], width=thin, wob=False)
        if t == "blazer":                                     # phù hiệu trường
            pen.shape([(cx - 0.62 * R, top + 0.4 * R), (cx - 0.38 * R, top + 0.4 * R),
                       (cx - 0.38 * R, top + 0.57 * R), (cx - 0.62 * R, top + 0.57 * R)],
                      (245, 211, 107), width=max(1, thin // 2 + 1), wob=False)
    if t == "cardigan":                                       # cổ tròn, hàng cúc
        pen.shape(_qbez((cx - 0.26 * R, top + 0.02 * R), (cx, top + 0.34 * R), (cx + 0.26 * R, top + 0.02 * R), 8),
                  (255, 248, 238), width=thin, wob=False)
        pen.line([(cx, top + 0.2 * R), (cx, bottom)], width=thin, wob=False)
        for i in range(4):
            yy = top + 0.4 * R + i * (ys - top - 0.5 * R) / 3.5
            pen.ell(cx + 0.08 * R, yy, 0.05 * R, 0.05 * R, (255, 255, 255), width=max(1, thin // 2), wob=False)
    if t == "hoodie":                                         # mũ trùm sau gáy + hai dây
        pen.line(_qbez((cx - 0.5 * R, top + 0.04 * R), (cx, top + 0.42 * R), (cx + 0.5 * R, top + 0.04 * R), 10),
                 width=thin, wob=False)
        for sx in (-1, 1):
            pen.line([(cx + sx * 0.12 * R, top + 0.24 * R), (cx + sx * 0.12 * R, top + 0.62 * R)],
                     width=max(1, thin), fill=(250, 250, 250), wob=False)
        pen.line([(cx - wb * 0.95, ys - 0.06 * R), (cx + wb * 0.95, ys - 0.06 * R)], width=thin, wob=False)
    if t == "apron":                                          # tạp dề
        a0 = top + 0.5 * R
        pen.shape([(cx - 0.42 * R, a0), (cx + 0.42 * R, a0), (cx + 0.56 * R, bottom - 0.04 * R), (cx - 0.56 * R, bottom - 0.04 * R)],
                  (255, 244, 224), width=thin, wob=False)
        for sx in (-1, 1):
            pen.line([(cx + sx * 0.42 * R, a0), (cx + sx * 0.24 * R, top + 0.02 * R)], width=thin, wob=False)
    if kit.get("bottom") == "skirt" and split < 1:           # chân váy xếp ly
        for k in (-0.6, -0.2, 0.2, 0.6):
            pen.line([(cx + k * wb * 0.9, ys + 0.06 * R), (cx + k * wb * 1.0, bottom)], width=max(1, thin // 2 + 1),
                     fill=_shade(bot_c, 0.7), wob=False)
    if kit.get("patched"):                                    # áo vá
        rr = random.Random(seed)
        for _ in range(2):
            px = cx + rr.uniform(-0.45, 0.35) * R
            py = top + rr.uniform(0.35, 0.8) * (ys - top)
            s = 0.16 * R
            pen.shape([(px, py), (px + s, py + 0.02 * R), (px + s * 0.95, py + s),
                       (px - 0.02 * R, py + s * 0.9)], _shade(top_c, 1.18), width=thin)
            d.line([(px + s * 0.2, py + s * 0.3), (px + s * 0.8, py + s * 0.3)],
                   fill=_shade(top_c, 0.7), width=max(1, thin // 2))
    body_part = _part(kit.get("extra"), "body")
    if body_part:
        from . import doodle_parts
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        lp = _Pen(lay, pen.T, seed + 31)
        doodle_parts.draw_shapes(lp, body_part["shapes"],
                                 lambda x, y: (cx + x * wb, top + y * h), wb)
        img.paste(lay, (0, 0), Image.composite(lay.getchannel("A"),
                                               Image.new("L", img.size, 0), mask))
    pen.shape(pts, None, outline=True)
    return wt


def _part(pid, kind):
    if not pid or pid == "none":
        return None
    from . import doodle_parts
    p = doodle_parts.get(pid)
    return p if p and p.get("kind") == kind else None


def _draw_head_parts(pen: _Pen, kit, cx, hy, R, layer):
    from . import doodle_parts
    for pid in (kit.get("hat"), kit.get("extra")):
        p = _part(pid, "head")
        if p:
            doodle_parts.draw_shapes(pen, p["shapes"], lambda x, y: (cx + x * R, hy + y * R),
                                     R, layer=layer)


def _hair_cap(cx, hy, R, side_deg, fringe_y, teeth=0, asym=0.0, rad=1.07):
    """Mảng tóc úp trên đầu: cung tròn từ -side_deg tới +side_deg (0 = đỉnh),
    rồi viền trán quay về (răng cưa nếu teeth > 0)."""
    pts = []
    for i in range(31):
        a = math.radians(-side_deg + 2 * side_deg * i / 30)
        pts.append((cx + rad * R * math.sin(a), hy - rad * R * math.cos(a)))
    xr, yr = pts[-1]
    xl, yl = pts[0]
    n = max(2, teeth * 2) if teeth else 8
    for i in range(1, n):
        u = i / n
        x = xr + (xl - xr) * u
        base = fringe_y + asym * R * (u - 0.5)
        if teeth:
            y = base + (0.12 * R if i % 2 else -0.02 * R)
        else:
            y = base - 0.05 * R * math.sin(math.pi * u)
        # hai bên má: tóc xuống thấp hơn
        edge = min(u, 1 - u)
        if edge < 0.18:
            y = y + (1 - edge / 0.18) * ((yr if u < 0.5 else yl) - y) * 0.6
        pts.append((x, y))
    return pts


def _draw_hair_back(pen: _Pen, kit, cx, hy, R, face_dir):
    col = HAIR_COLORS[kit["hair_color"]]
    h = kit["hair"]
    if h == "long" and _sty(kit).get("head_shape") == "mochi":     # tóc dài ôm hai má
        def P(x, y):
            return (cx + x * R, hy + y * R)
        pen.shape(_qpath(P(-1.02, -0.1), [(P(-1.1, 1.2), P(-0.85, 1.55)), P(0.85, 1.55),
                                          (P(1.1, 1.2), P(1.02, -0.1))]), col)
    elif h == "long":
        pen.shape([(cx - 1.02 * R, hy - 0.2 * R), (cx + 1.02 * R, hy - 0.2 * R),
                   (cx + 1.0 * R, hy + 1.5 * R), (cx - 1.0 * R, hy + 1.5 * R)], col)
    if h == "longbang":                                       # tóc dài thẳng chấm lưng
        def P(x, y):
            return (cx + x * R, hy + y * R)
        pen.shape(_qpath(P(-1.0, -0.2), [(P(-1.15, 1.6), P(-0.9, 2.35)), P(0.9, 2.35),
                                         (P(1.15, 1.6), P(1.0, -0.2))]), col)
    if h == "bun" and kit["hat"] != "khan_van":
        bx = cx - face_dir * 0.55 * R
        pen.ell(bx, hy - 0.86 * R, 0.34 * R, 0.3 * R, col)


def _draw_hair_front(pen: _Pen, kit, cx, hy, R, face_dir):
    col = HAIR_COLORS[kit["hair_color"]]
    h = kit["hair"]
    dark = _shade(col, 0.82)
    if h == "bald" or (kit["hat"] == "khan_van" and h in ("bun", "long", "bob")):
        if kit["hat"] == "khan_van":
            pen.shape(_hair_cap(cx, hy, R, 92, hy - 0.5 * R), col)
        return
    if h == "balding":
        for sx in (-1, 1):
            pen.ell(cx + sx * 0.9 * R, hy - 0.12 * R, 0.2 * R, 0.3 * R, col)
        return
    m = face_dir or 1

    def P(x, y):                                              # mái lệch theo hướng nhìn
        return (cx + m * x * R, hy + y * R)
    shine = _mix(col, (255, 255, 255), 0.3)                   # vệt bóng tóc webtoon
    if h == "twoblock":                                       # mái dày rủ trán, hai bên cắt ngắn
        pen.shape(_qpath(P(-0.95, -0.05), [(P(-1.05, -1.25), P(0.1, -1.18)), (P(1.05, -1.1), P(0.95, -0.05)),
                                           (P(0.75, -0.3), P(0.55, -0.18)), P(0.35, -0.42), P(0.12, -0.2),
                                           P(-0.12, -0.45), P(-0.38, -0.22), P(-0.6, -0.4),
                                           (P(-0.8, -0.2), P(-0.95, -0.05))]), col)
        pen.line(_qbez(P(-0.3, -0.95), P(0, -1.05), P(0.4, -0.85), 8), width=int(pen.lw * 1.3), fill=shine,
                 wob=False)
        return
    if h == "longbang":                                       # tóc dài, mái thưa
        pen.shape(_qpath(P(-0.98, 0.1), [(P(-1.08, -1.22), P(0, -1.15)), (P(1.08, -1.22), P(0.98, 0.1)),
                                          (P(0.8, -0.35), P(0.5, -0.38)), P(0.35, -0.2), P(0.15, -0.42),
                                          P(-0.05, -0.2), P(-0.25, -0.42), P(-0.45, -0.22), P(-0.6, -0.4),
                                          (P(-0.85, -0.35), P(-0.98, 0.1))]), col)
        pen.line(_qbez(P(-0.45, -0.98), P(0, -1.08), P(0.45, -0.98), 8), width=int(pen.lw * 1.3), fill=shine,
                 wob=False)
        return
    if h == "slick":                                          # vuốt ngược, lộ trán
        pen.shape(_qpath(P(-0.95, -0.05), [(P(-1.0, -1.2), P(0, -1.16)), (P(1.0, -1.2), P(0.95, -0.05)),
                                           (P(0.85, -0.65), P(0.2, -0.72)), (P(-0.7, -0.72), P(-0.95, -0.05))]), col)
        pen.line(_qbez(P(-0.4, -0.98), P(0.1, -1.06), P(0.5, -0.9), 8), width=int(pen.lw * 1.1), fill=shine,
                 wob=False)
        return
    if h == "perm":                                           # tóc xoăn ngắn bà bác (아줌마 펌)
        for a in range(190, 360, 24):
            t = math.radians(a)
            pen.ell(cx + R * 0.95 * math.cos(t), hy - R * 0.15 + R * 0.95 * math.sin(t), 0.33 * R, 0.33 * R, col)
        pen.shape(_qpath(P(-0.9, -0.2), [(P(0, -1.25), P(0.9, -0.2)), (P(0, -0.55), P(-0.9, -0.2))]), col,
                  outline=False)
        return
    if _sty(kit).get("head_shape") == "mochi" and h in ("side_part", "long", "short"):
        if h == "long":                                       # mái thưa chia hai bên
            pts = _qpath(P(-0.98, 0.1), [(P(-1.05, -1.12), P(0, -1.05)), (P(1.05, -1.12), P(0.98, 0.1)),
                                         (P(0.7, -0.45), P(0.35, -0.35)), (P(0, -0.55), P(-0.35, -0.35)),
                                         (P(-0.7, -0.45), P(-0.98, 0.1))])
        else:                                                 # rẽ ngôi, mái chéo
            pts = _qpath(P(-0.98, 0.05), [(P(-1.05, -1.1), P(0, -1.04)), (P(1.05, -1.1), P(0.98, 0.05)),
                                          (P(0.8, -0.5), P(0.2, -0.5)), (P(-0.3, -0.25), P(-0.75, -0.3)),
                                          (P(-0.9, -0.1), P(-0.98, 0.05))])
        pen.shape(pts, col)
        return
    if h == "curl_top":                                       # đầu trọc, một chỏm tóc xoăn
        pts = []                                      # 3 lọn lượn sóng trên đỉnh đầu
        for k in range(25):
            u = k / 24
            pts.append((cx + (u - 0.5) * 0.62 * R,
                        hy - 1.07 * R - 0.06 * R * math.sin(u * math.pi * 6) - 0.04 * R * math.sin(u * math.pi)))
        pen.line(pts, width=int(pen.lw * 2.2), fill=col)
        return
    if h == "curly":                                          # tóc xoăn bồng: nhiều lọn tròn
        for k in range(11):
            a = math.radians(-200 + k * 22)
            pen.ell(cx + math.cos(a) * 0.98 * R, hy - 0.05 * R + math.sin(a) * 0.98 * R,
                    0.24 * R, 0.24 * R, col)
        pen.shape(_hair_cap(cx, hy, R, 100, hy - 0.45 * R, rad=1.1), col)
        return
    if h == "short":
        pts = _hair_cap(cx, hy, R, 96, hy - 0.42 * R)
    elif h == "bowl":                                         # tóc bát úp: mái bằng ngang trán
        pts = _hair_cap(cx, hy, R, 84, hy - 0.36 * R, rad=1.08)
    elif h == "side_part":
        pts = _hair_cap(cx, hy, R, 98, hy - 0.4 * R, asym=0.3 * face_dir)
    elif h == "bangs":
        pts = _hair_cap(cx, hy, R, 120, hy - 0.08 * R, teeth=5)
    elif h == "messy":
        pts = _hair_cap(cx, hy, R, 112, hy - 0.2 * R, teeth=4, rad=1.12)
    elif h == "wavy":
        pts = _hair_cap(cx, hy, R, 104, hy - 0.36 * R, rad=1.13)
    elif h == "bob":
        pts = _hair_cap(cx, hy, R, 124, hy - 0.3 * R)
    elif h == "long":
        pts = _hair_cap(cx, hy, R, 112, hy - 0.42 * R)
    else:                                    # bun: chải ngược ra sau
        pts = _hair_cap(cx, hy, R, 98, hy - 0.5 * R)
    old_amp = pen.amp
    if h in ("wavy", "messy"):
        pen.amp = old_amp * 2.4
    pen.shape(pts, col)
    pen.amp = old_amp
    if h in ("short", "side_part", "wavy", "bun"):            # vài nét tóc
        for i in (-1, 1):
            x0 = cx + i * 0.25 * R + face_dir * 0.1 * R
            pen.line([(x0, hy - 0.95 * R), (x0 + i * 0.12 * R, hy - 0.62 * R)],
                     width=max(1, pen.lw // 2), fill=dark)


def _draw_hat(pen: _Pen, kit, cx, hy, R):
    hat = kit["hat"]
    if hat == "non_la":
        straw = (226, 204, 150)
        pen.shape([(cx, hy - 1.95 * R), (cx + 1.55 * R, hy - 0.52 * R),
                   (cx - 1.55 * R, hy - 0.52 * R)], straw)
        for k in range(1, 4):
            u = k / 4
            pen.line([(cx - 1.55 * R * u, hy - 1.95 * R + 1.43 * R * u),
                      (cx + 1.55 * R * u, hy - 1.95 * R + 1.43 * R * u)],
                     width=max(1, pen.lw // 2), fill=_shade(straw, 0.7))
    elif hat == "khan_van":
        band = (66, 58, 62)
        pts = _ellipse_pts(cx, hy - 0.52 * R, 1.04 * R, 0.5 * R, 180, 360, 24)
        pts += _ellipse_pts(cx, hy - 0.44 * R, 1.06 * R, 0.28 * R, 0, 180, 24)
        pen.shape(pts, band)
        for dx in (-0.5, -0.1, 0.3):
            pen.line([(cx + dx * R, hy - 0.86 * R), (cx + (dx + 0.25) * R, hy - 0.3 * R)],
                     width=max(1, pen.lw // 2), fill=(126, 114, 120))
    elif hat == "khan_dau":
        cloth = (200, 70, 60) if kit["sex"] == "male" else (226, 196, 120)
        pts = _ellipse_pts(cx, hy - 0.42 * R, 1.08 * R, 0.62 * R, 180, 360, 24)
        pts += [(cx + 1.08 * R, hy - 0.3 * R), (cx - 1.08 * R, hy - 0.3 * R)]
        pen.shape(pts, cloth)
    elif hat == "hat":
        col = (110, 92, 72)
        pen.ell(cx, hy - 0.62 * R, 1.35 * R, 0.24 * R, col)
        pen.shape([(cx - 0.75 * R, hy - 0.66 * R), (cx - 0.68 * R, hy - 1.3 * R),
                   (cx + 0.68 * R, hy - 1.3 * R), (cx + 0.75 * R, hy - 0.66 * R)], col)
        pen.line([(cx - 0.74 * R, hy - 0.8 * R), (cx + 0.74 * R, hy - 0.8 * R)],
                 width=int(pen.lw * 1.4), fill=(60, 50, 44))


MOUTH_RED = (138, 47, 58)
TEAR = (158, 211, 245)


def _tear(pen, x, y, R, k=1.0):
    """Giọt nước mắt dài chảy xuống má."""
    top, bot = (x, y), (x, y + 0.44 * R * k)
    pts = _qbez(top, (x - 0.1 * R * k, y + 0.34 * R * k), bot, 8) + \
        _qbez(bot, (x + 0.1 * R * k, y + 0.34 * R * k), top, 8)[1:]
    pen.shape(pts, TEAR, outline=False, wob=False)


def _face_mochi(pen: _Pen, kit, cx, hy, R, f, expr, mouth_open, blink):
    """Mặt Mochi 둥글이: mắt chấm đen có đốm sáng, má hồng luôn có, miệng mèo ω,
    không mũi, chỉ có lông mày khi giận / buồn."""
    fx = cx + f * 0.15 * R
    ey = hy + 0.05 * R
    sep = 0.44 * R * (1 - 0.1 * abs(f))
    lw = max(2, int(pen.lw * 0.9))
    thin = max(1, int(pen.lw * 0.7))
    skin = SKINS[kit["skin"]]
    shut = blink or expr == "sleep"
    for sx in (-1, 1):
        ex = fx + sx * sep
        if expr == "happy" and not blink:                      # ^ ^
            pen.line(_qbez((ex - 0.115 * R, ey + 0.04 * R), (ex, ey - 0.115 * R), (ex + 0.115 * R, ey + 0.04 * R), 8),
                     width=lw, wob=False)
        elif expr == "cry" or shut:                            # mắt nhắm cong xuống
            pen.line(_qbez((ex - 0.115 * R, ey - 0.025 * R), (ex, ey + 0.09 * R), (ex + 0.115 * R, ey - 0.025 * R), 8),
                     width=lw, wob=False)
        elif expr == "shocked":                                # mắt tròn trắng, con ngươi nhỏ
            pen.ell(ex, ey, 0.128 * R, 0.128 * R, (255, 255, 255), width=thin, wob=False)
            pen.dot(ex, ey, 0.045 * R)
        else:
            dy = 0.03 * R if expr in ("sad", "worried") else (-0.04 * R if expr == "think" else 0.0)
            px = ex + f * 0.03 * R
            pen.ell(px, ey + dy, 0.077 * R, 0.1 * R, OUT, outline=False, wob=False)
            pen.dot(px + 0.026 * R, ey + dy - 0.038 * R, 0.026 * R, (255, 255, 255))
            if expr == "sly":                                  # mắt lim dim
                pen.shape(_ellipse_pts(px, ey + dy, 0.1 * R, 0.13 * R, 180, 360, 10), skin, outline=False, wob=False)
                pen.line([(px - 0.1 * R, ey + dy), (px + 0.1 * R, ey + dy)], width=thin, wob=False)
        if expr == "angry":                                    # lông mày xếch vào trong
            pen.line([(ex - 0.154 * R, ey - 0.18 * R + sx * 0.064 * R),
                      (ex + 0.154 * R, ey - 0.18 * R - sx * 0.064 * R)], width=lw, wob=False)
        elif expr in ("sad", "worried", "cry"):
            pen.line([(ex - 0.13 * R, ey - 0.17 * R - sx * 0.05 * R),
                      (ex + 0.13 * R, ey - 0.17 * R + sx * 0.05 * R)], width=thin, wob=False)
        if expr == "cry":
            _tear(pen, ex, ey + 0.077 * R, R)
    for sx in (-1, 1):                                         # má hồng
        pen.ell(fx + sx * 0.62 * R * (1 - 0.1 * abs(f)), hy + 0.28 * R, 0.14 * R, 0.077 * R,
                _mix(skin, (255, 159, 168), 0.8), outline=False, wob=False)
    mx, my = fx + f * 0.03 * R, hy + 0.36 * R
    if expr == "shocked":
        pen.ell(mx, my + 0.05 * R, 0.115 * R, 0.154 * R, MOUTH_RED, width=thin, wob=False)
    elif expr == "cry":
        pts = _qbez((mx - 0.154 * R, my + 0.1 * R), (mx, my - 0.077 * R), (mx + 0.154 * R, my + 0.1 * R), 10)
        pen.shape(pts, MOUTH_RED, width=thin, wob=False)
    elif mouth_open:
        if expr in ("happy", "sly"):                           # cười há miệng
            pen.shape(_ellipse_pts(mx, my - 0.02 * R, 0.13 * R, 0.13 * R, 0, 180, 12), MOUTH_RED, width=thin,
                      wob=False)
        else:
            pen.ell(mx, my + 0.03 * R, 0.085 * R, 0.08 * R, MOUTH_RED, width=thin, wob=False)
    elif expr in ("angry", "sad", "worried"):
        pen.line(_qbez((mx - 0.128 * R, my + 0.077 * R), (mx, my - 0.026 * R), (mx + 0.128 * R, my + 0.077 * R), 8),
                 width=lw, wob=False)
    elif expr == "sleep":
        pen.ell(mx, my + 0.02 * R, 0.04 * R, 0.035 * R, MOUTH_RED, width=thin, wob=False)
    else:                                                      # miệng mèo ω
        pts = _qbez((mx - 0.1 * R, my), (mx - 0.05 * R, my + 0.08 * R), (mx, my), 6) + \
            _qbez((mx, my), (mx + 0.05 * R, my + 0.08 * R), (mx + 0.1 * R, my), 6)[1:]
        pen.line(pts, width=thin, wob=False)
    g = kit["glasses"]
    if g != "none":
        gw = max(1, int(pen.lw * 0.7))
        for sx in (-1, 1):
            ex = fx + sx * sep
            if g == "round":
                pen.line(_ellipse_pts(ex, ey, 0.19 * R, 0.19 * R), width=gw, wob=False)
            else:
                pen.line([(ex - 0.2 * R, ey - 0.15 * R), (ex + 0.2 * R, ey - 0.15 * R), (ex + 0.2 * R, ey + 0.15 * R),
                          (ex - 0.2 * R, ey + 0.15 * R), (ex - 0.2 * R, ey - 0.15 * R)], width=gw, wob=False)
        pen.line([(fx - sep + 0.19 * R, ey), (fx + sep - 0.19 * R, ey)], width=gw, wob=False)
    if kit["facial"] in ("mustache", "beard", "goatee"):      # ria nhỏ gọn
        hc = HAIR_COLORS[kit["hair_color"]]
        for sx in (-1, 1):
            pen.ell(mx + sx * 0.08 * R, my - 0.06 * R, 0.08 * R, 0.035 * R, hc, width=thin, wob=False)


def _face_webtoon(pen: _Pen, kit, cx, hy, R, f, expr, mouth_open, blink):
    """Mặt Webtoon 웹툰: mắt to long lanh (tròng nâu, đốm sáng, mí trên đậm, nữ có
    lông mi), lông mày mảnh thẳng, mũi một nét, má hồng nhạt, miệng nhỏ."""
    fx = cx + f * 0.12 * R
    ey = hy + 0.12 * R
    sep = 0.36 * R * (1 - 0.1 * abs(f))
    fem = kit["sex"] == "female"
    old = kit["age"] == "old"
    lw = max(2, int(pen.lw))
    thin = max(1, int(pen.lw * 0.7))
    skin = SKINS[kit["skin"]]
    iris = (110, 74, 50) if kit["hair_color"] in ("brown", "darkbrown") else (90, 60, 46)
    closed = blink or expr in ("sleep", "cry") or (expr == "happy")
    rx, ry = 0.15 * R, 0.2 * R * (1.15 if expr == "shocked" else 1.0)
    for sx in (-1, 1):
        ex = fx + sx * sep
        if expr == "happy" and not blink:                      # mắt cười ∩
            pen.line(_qbez((ex - 0.17 * R, ey + 0.04 * R), (ex, ey - 0.14 * R), (ex + 0.17 * R, ey + 0.04 * R), 8),
                     width=lw, wob=False)
        elif closed:                                           # nhắm ∪
            pen.line(_qbez((ex - 0.17 * R, ey - 0.02 * R), (ex, ey + 0.1 * R), (ex + 0.17 * R, ey - 0.02 * R), 8),
                     width=lw, wob=False)
            if fem:
                pen.line([(ex + sx * 0.17 * R, ey - 0.02 * R), (ex + sx * 0.23 * R, ey - 0.06 * R)], width=thin,
                         wob=False)
        else:
            pen.ell(ex, ey, rx, ry, (255, 255, 255), width=thin, wob=False)
            k = 0.55 if expr == "shocked" else 0.8
            ix = ex + f * 0.04 * R
            iy = ey + ry * 0.12 + (ry * 0.1 if expr in ("sad", "worried") else 0.0) - \
                (ry * 0.18 if expr == "think" else 0.0)
            pen.ell(ix, iy, rx * (0.55 if expr == "shocked" else 0.82), ry * k, iris, outline=False, wob=False)
            pen.ell(ix, iy + ry * 0.03, rx * 0.4, ry * 0.42, OUT, outline=False, wob=False)
            pen.dot(ix - rx * 0.3, iy - ry * 0.32, rx * 0.28, (255, 255, 255))
            if expr == "sly":                                  # lim dim: mí che nửa trên
                pen.shape(_ellipse_pts(ex, ey, rx * 1.2, ry * 1.25, 180, 360, 10), skin, outline=False, wob=False)
                pen.line([(ex - rx * 1.1, ey), (ex + rx * 1.1, ey)], width=lw, wob=False)
            else:                                              # mí trên đậm
                pen.line(_qbez((ex - rx * 1.15, ey - ry * 0.55), (ex, ey - ry * 1.25), (ex + rx * 1.15, ey - ry * 0.55), 8),
                         width=int(lw * (1.25 if fem else 1.0)), wob=False)
                if fem:
                    pen.line([(ex + sx * rx * 1.1, ey - ry * 0.6), (ex + sx * (rx * 1.1 + 0.06 * R), ey - ry * 0.6 - 0.05 * R)],
                             width=thin, wob=False)
        # lông mày mảnh
        x0, x1 = fx + sx * 0.2 * R, fx + sx * 0.52 * R
        if expr == "angry":
            y0, y1 = ey - 0.22 * R, ey - 0.34 * R
        elif expr in ("cry", "worried", "sad"):
            y0, y1 = ey - 0.36 * R, ey - 0.27 * R
        elif expr == "shocked":
            y0, y1 = ey - 0.42 * R, ey - 0.42 * R
        else:
            y0, y1 = ey - 0.33 * R, ey - 0.34 * R
        hc = HAIR_COLORS[kit["hair_color"]]
        brow = (58, 44, 44) if kit["hair_color"] == "black" else _shade(hc, 0.8)
        pen.line([(x0, y0), (x1, y1)], width=lw, fill=brow, wob=False)
        if expr == "cry":
            _tear(pen, ex, ey + 0.1 * R, R, 0.95)
        if old and not closed:                                 # nếp nhăn đuôi mắt
            ox = ex + sx * 0.26 * R
            pen.line([(ox, ey - 0.02 * R), (ox + sx * 0.06 * R, ey + 0.06 * R)], width=thin, wob=False)
    for sx in (-1, 1):                                         # má hồng nhạt
        pen.ell(fx + sx * 0.55 * R, hy + 0.5 * R, 0.14 * R, 0.06 * R, _mix(skin, (255, 170, 170), 0.55),
                outline=False, wob=False)
    nx = fx + 0.03 * R + f * 0.05 * R                          # mũi một nét
    pen.line([(nx, hy + 0.42 * R), (nx - 0.05 * R, hy + 0.52 * R)], width=thin, fill=(200, 143, 127), wob=False)
    mx, my = fx + f * 0.03 * R, hy + 0.72 * R
    if expr == "shocked":
        pen.ell(mx, my + 0.04 * R, 0.08 * R, 0.11 * R, (154, 58, 70), width=thin, wob=False)
    elif expr == "happy" or (mouth_open and expr == "sly"):    # cười há miệng chữ D
        pts = _qbez((mx - 0.16 * R, my - 0.02 * R), (mx, my + 0.18 * R), (mx + 0.16 * R, my - 0.02 * R), 10)
        pen.shape(pts, (196, 80, 92), width=thin, wob=False)
    elif mouth_open:
        pen.ell(mx, my + 0.02 * R, 0.07 * R, 0.06 * R, (154, 58, 70), width=thin, wob=False)
    elif expr in ("cry", "angry", "sad"):
        pen.line(_qbez((mx - 0.12 * R, my + 0.06 * R), (mx, my - 0.04 * R), (mx + 0.12 * R, my + 0.06 * R), 8),
                 width=lw, wob=False)
    elif expr == "worried":
        pen.line([(mx - 0.1 * R, my + 0.02 * R), (mx - 0.03 * R, my - 0.01 * R), (mx + 0.03 * R, my + 0.03 * R),
                  (mx + 0.1 * R, my)], width=lw, wob=False)
    elif expr == "sly":
        pen.line(_qbez((mx - 0.1 * R, my + 0.02 * R), (mx + 0.02 * R, my + 0.05 * R), (mx + 0.12 * R, my - 0.04 * R), 8),
                 width=lw, wob=False)
    else:
        pen.line(_qbez((mx - 0.08 * R, my), (mx, my + 0.05 * R), (mx + 0.08 * R, my), 8), width=lw, wob=False)
    facial = kit["facial"]
    hc = HAIR_COLORS[kit["hair_color"]] if kit["hair_color"] != "black" else (70, 60, 62)
    if facial in ("mustache", "beard", "goatee"):
        pen.shape(_qbez((mx - 0.16 * R, my - 0.04 * R), (mx, my - 0.16 * R), (mx + 0.16 * R, my - 0.04 * R), 8),
                  hc, width=thin, wob=False)
    if facial in ("beard", "goatee"):
        pen.shape(_qbez((mx - 0.1 * R, my + 0.14 * R), (mx, my + 0.42 * R), (mx + 0.1 * R, my + 0.14 * R), 8),
                  hc, width=thin, wob=False)
    elif facial == "stubble":
        rr = random.Random(7)
        for _ in range(14):
            pen.dot(mx + rr.uniform(-0.35, 0.35) * R, my + rr.uniform(0.08, 0.36) * R, 0.014 * R, _shade(skin, 0.7))
    g = kit["glasses"]
    if g != "none":
        gw = max(1, int(pen.lw * 0.85))
        for sx in (-1, 1):
            ex = fx + sx * sep
            if g == "round":
                pen.line(_ellipse_pts(ex, ey, 0.22 * R, 0.21 * R), width=gw, wob=False)
            else:
                x0, x1, y0, y1, r = ex - 0.24 * R, ex + 0.24 * R, ey - 0.2 * R, ey + 0.16 * R, 0.08 * R
                pen.line(_qpath((x0 + r, y0), [(x1 - r, y0), ((x1, y0), (x1, y0 + r)), (x1, y1 - r),
                                               ((x1, y1), (x1 - r, y1)), (x0 + r, y1), ((x0, y1), (x0, y1 - r)),
                                               (x0, y0 + r), ((x0, y0), (x0 + r, y0))], 4), width=gw, wob=False)
        pen.line([(fx - sep + 0.22 * R, ey - 0.04 * R), (fx + sep - 0.22 * R, ey - 0.04 * R)], width=gw, wob=False)


def _draw_face(pen: _Pen, kit, cx, hy, R, f, expr, mouth_open, blink):
    """f = hướng nhìn (-1 trái .. 1 phải)."""
    face = _sty(kit).get("face")
    if face == "mochi":
        return _face_mochi(pen, kit, cx, hy, R, f, expr, mouth_open, blink)
    if face == "webtoon":
        return _face_webtoon(pen, kit, cx, hy, R, f, expr, mouth_open, blink)
    fx = cx + f * 0.18 * R
    ey = hy + 0.08 * R
    sep = 0.36 * R * (1 - 0.12 * abs(f))
    lw = pen.lw
    thin = max(1, int(lw * 0.6))
    old = kit["age"] == "old"
    eye_r = (0.15 * R, 0.11 * R)
    if expr == "shocked":
        eye_r = (0.19 * R, 0.17 * R)
    closed = blink or expr in ("sleep", "cry", "happy")
    sty = kit.get("_sty") or {}
    eye_style = sty.get("eyes", "dot")
    for sx in (-1, 1):
        ex = fx + sx * sep
        if eye_style == "ring" and not closed:         # mắt tròn viền trắng, con ngươi chấm giữa
            rr = 0.14 * R * (1.25 if expr == "shocked" else 1.0)
            pen.ell(ex, ey, rr, rr, (255, 255, 255), width=thin)
            pen.dot(ex + f * 0.03 * R, ey + (0.02 * R if expr in ("sad", "worried") else 0.0),
                    0.055 * R * (0.8 if expr == "shocked" else 1.0))
        elif closed:
            if expr == "happy":                                # ^ ^
                pen.line([(ex - 0.13 * R, ey + 0.04 * R), (ex, ey - 0.08 * R),
                          (ex + 0.13 * R, ey + 0.04 * R)], width=lw)
            elif expr == "cry":                                # mắt nhắm chặt
                pen.line([(ex - 0.14 * R, ey - 0.04 * R), (ex, ey + 0.04 * R),
                          (ex + 0.14 * R, ey - 0.04 * R)], width=lw)
            else:
                pen.line(_ellipse_pts(ex, ey - 0.02 * R, 0.13 * R, 0.07 * R, 10, 170, 8),
                         width=lw)
        elif eye_style == "line":                         # mắt chấm đen kiểu meme
            rr = 0.07 * R * (1.4 if expr == "shocked" else 1.0)
            pen.dot(ex + f * 0.04 * R, ey, rr)
        elif eye_style == "big":                          # mắt anime: tròng to, đốm sáng
            ry = eye_r[1] * 2.0
            rx = eye_r[0] * 1.1
            pen.ell(ex, ey, rx, ry, (255, 255, 255), width=thin)
            iris = HAIR_COLORS.get(kit.get("hair_color"), OUT) if kit.get("hair_color") not in \
                ("white", "gray", "salt") else (90, 70, 60)
            pen.ell(ex + f * 0.04 * R, ey + ry * 0.12, rx * 0.72, ry * 0.8, iris, width=thin,
                    wob=False)
            pen.dot(ex + f * 0.04 * R, ey + ry * 0.15, rx * 0.38)
            pen.dot(ex + f * 0.04 * R - rx * 0.3, ey - ry * 0.25, rx * 0.22, (255, 255, 255))
            pen.line(_ellipse_pts(ex, ey + ry * 0.05, rx * 1.15, ry * 1.1, 200, 340, 8),
                     width=int(lw * 1.4))
        elif eye_style == "round":                        # mắt tròn to kiểu chibi
            r0 = eye_r[0] * 1.35
            pen.ell(ex, ey, r0, r0, (255, 255, 255), width=thin)
            pen.dot(ex + f * 0.07 * R, ey + 0.02 * R, r0 * 0.55)
            pen.dot(ex + f * 0.07 * R - r0 * 0.2, ey - r0 * 0.2, r0 * 0.2, (255, 255, 255))
        else:
            pen.ell(ex, ey, eye_r[0], eye_r[1], (255, 255, 255), width=thin)
            pr = 0.055 * R if expr != "shocked" else 0.04 * R
            py = ey + (0.03 * R if expr in ("sad", "worried") else 0.0)
            pen.dot(ex + f * 0.06 * R, py, pr)
            if expr in ("neutral", "sad", "sly", "think", "worried") and eye_style == "dot":   # mí mắt nặng
                k = 0.55 if expr == "sly" else 0.0
                pen.line(_ellipse_pts(ex, ey - k * eye_r[1], eye_r[0] * 1.05, eye_r[1] * 1.1,
                                      200, 340, 8), width=lw)
        # lông mày
        by = ey - 0.27 * R
        inner, outer = ex - sx * 0.12 * R, ex + sx * 0.12 * R
        dy_in, dy_out = 0.0, 0.0
        if expr == "angry":
            dy_in, dy_out = 0.09 * R, -0.04 * R
        elif expr in ("sad", "worried", "cry"):
            dy_in, dy_out = -0.07 * R, 0.04 * R
        elif expr == "shocked":
            dy_in = dy_out = -0.08 * R
        brow = HAIR_COLORS["gray"] if old else OUT
        if eye_style == "ring":                          # mắt tròn: lông mày ngắn, mảnh
            inner, outer = ex - sx * 0.07 * R, ex + sx * 0.07 * R
            pen.line([(inner, by - 0.02 * R + dy_in), (outer, by - 0.02 * R + dy_out)], width=thin, fill=brow)
        else:
            pen.line([(inner, by + dy_in), (outer, by + dy_out)], width=lw, fill=brow)
        if old and not closed:                                 # nếp nhăn đuôi mắt
            ox = ex + sx * 0.24 * R
            pen.line([(ox, ey - 0.06 * R), (ox + sx * 0.05 * R, ey + 0.02 * R)], width=thin)
            pen.line([(ox - sx * 0.01 * R, ey + 0.06 * R), (ox + sx * 0.03 * R, ey + 0.12 * R)],
                     width=thin)
    if expr == "cry":                                          # dòng nước mắt
        for sx in (-1, 1):
            ex = fx + sx * sep
            pen.line([(ex, ey + 0.06 * R), (ex + sx * 0.02 * R, ey + 0.55 * R)],
                     width=int(lw * 1.6), fill=(140, 196, 236), wob=False)
    if expr in ("happy",) or (kit["sex"] == "female" and kit["age"] in ("child", "young")):
        for sx in (-1, 1):
            pen.ell(fx + sx * (sep + 0.06 * R), ey + 0.24 * R, 0.1 * R, 0.05 * R,
                    (240, 170, 160), outline=False, wob=False)
    # mũi
    nx = fx + f * 0.06 * R
    nose = sty.get("nose", "line")
    if nose == "round":                                        # mũi tròn to, hai lỗ mũi
        skin = SKINS[kit["skin"]]
        pen.ell(nx, hy + 0.3 * R, 0.14 * R, 0.1 * R, _shade(skin, 0.94), width=thin)
        for sx in (-1, 1):
            pen.dot(nx + sx * 0.05 * R, hy + 0.31 * R, 0.022 * R, (60, 40, 40))
    elif nose == "dot":
        pen.dot(nx, hy + 0.3 * R, 0.03 * R, _shade(SKINS[kit["skin"]], 0.6))
    else:
        pen.line(_ellipse_pts(nx, hy + 0.3 * R, 0.05 * R, 0.05 * R, -60 if f >= 0 else 60,
                              90 if f >= 0 else 240, 6), width=thin)
    if old:                                                    # rãnh má
        for sx in (-1, 1):
            pen.line([(nx + sx * 0.2 * R, hy + 0.32 * R), (nx + sx * 0.26 * R, hy + 0.52 * R)],
                     width=thin)
    # ria, râu
    my = hy + 0.53 * R
    facial = kit["facial"]
    hc = HAIR_COLORS[kit["hair_color"]] if kit["hair_color"] != "black" else OUT
    if facial == "mustache":
        pen.shape(_ellipse_pts(fx - 0.11 * R, my - 0.1 * R, 0.12 * R, 0.05 * R) , hc, width=thin)
        pen.shape(_ellipse_pts(fx + 0.11 * R, my - 0.1 * R, 0.12 * R, 0.05 * R), hc, width=thin)
    elif facial in ("beard", "goatee"):
        if facial == "beard":
            pen.shape(_ellipse_pts(fx, hy + 0.66 * R, 0.5 * R, 0.3 * R, 0, 180, 16) +
                      [(fx - 0.5 * R, hy + 0.6 * R)], hc, width=thin)
        else:
            pen.shape([(fx - 0.12 * R, hy + 0.7 * R), (fx + 0.12 * R, hy + 0.7 * R),
                       (fx + 0.02 * R, hy + 1.05 * R), (fx - 0.04 * R, hy + 1.05 * R)], hc,
                      width=thin)
        pen.shape(_ellipse_pts(fx - 0.1 * R, my - 0.1 * R, 0.11 * R, 0.04 * R), hc, width=thin)
        pen.shape(_ellipse_pts(fx + 0.1 * R, my - 0.1 * R, 0.11 * R, 0.04 * R), hc, width=thin)
    elif facial == "stubble":
        rr = random.Random(7)
        for _ in range(16):
            a = rr.uniform(0.15, 0.85) * math.pi
            r = rr.uniform(0.55, 0.85) * R
            pen.dot(fx + r * math.cos(a) * 0.8, hy + r * math.sin(a) * 0.95, 0.018 * R,
                    _shade(OUT, 1.6))
    # miệng
    mw = 0.13 * R
    lips = sty.get("mouth") == "lips"
    if lips:                                                   # môi hồng dày
        lip, dark = (238, 150, 156), (140, 44, 56)
        if mouth_open or expr in ("shocked", "cry"):
            big = expr in ("shocked", "cry")
            ry = 0.15 * R if big else 0.09 * R
            mx2 = mw * (1.55 if big else 1.25)
            pen.ell(fx, my + 0.03 * R, mx2, ry + 0.04 * R, lip, width=thin)
            pen.ell(fx, my + 0.03 * R, mx2 * 0.68, ry * 0.78, dark, outline=False, wob=False)
            pen.ell(fx, my + 0.03 * R + ry * 0.4, mw * 0.5, ry * 0.3, (226, 110, 120),
                    outline=False, wob=False)
        elif expr in ("happy", "sly"):
            pen.shape(_ellipse_pts(fx, my - 0.02 * R, mw * 1.2, 0.09 * R, 0, 180, 12), lip, width=thin)
        elif expr in ("sad", "angry", "worried"):
            pen.shape(_ellipse_pts(fx, my + 0.08 * R, mw * 1.1, 0.07 * R, 180, 360, 12), lip, width=thin)
        else:
            pen.ell(fx, my, mw * 1.5, 0.085 * R, lip, width=thin)
            pen.line([(fx - mw * 1.0, my), (fx + mw * 1.0, my)], width=max(1, thin // 2))
    elif mouth_open or expr == "shocked":
        ry = 0.1 * R if expr == "shocked" else 0.07 * R
        pen.ell(fx, my + 0.02 * R, mw * (0.7 if expr == "shocked" else 1.0), ry,
                (150, 60, 66), width=thin)
        pen.ell(fx, my + 0.02 * R + ry * 0.45, mw * 0.5, ry * 0.4, (226, 120, 120),
                outline=False, wob=False)
    elif expr == "happy" or expr == "sly":
        a0, a1 = (20, 160) if expr == "happy" else (30, 120)
        pen.line(_ellipse_pts(fx, my - 0.06 * R, mw * 1.1, 0.1 * R, a0, a1, 10), width=lw)
    elif expr in ("sad", "cry", "angry"):
        pen.line(_ellipse_pts(fx, my + 0.08 * R, mw, 0.08 * R, 200, 340, 10), width=lw)
    elif expr == "worried":
        pen.line([(fx - mw, my), (fx - mw * 0.4, my - 0.03 * R), (fx + mw * 0.2, my + 0.02 * R),
                  (fx + mw, my - 0.02 * R)], width=lw)
    else:
        pen.line([(fx - mw * 0.8, my), (fx + mw * 0.8, my + 0.01 * R)], width=lw)
    # kính
    g = kit["glasses"]
    if g != "none":
        gw = int(lw * 0.9)
        for sx in (-1, 1):
            ex = fx + sx * sep
            if g == "round":
                pen.line(_ellipse_pts(ex, ey, 0.22 * R, 0.2 * R), width=gw)
            else:
                pen.line([(ex - 0.24 * R, ey - 0.16 * R), (ex + 0.24 * R, ey - 0.16 * R),
                          (ex + 0.22 * R, ey + 0.16 * R), (ex - 0.22 * R, ey + 0.16 * R),
                          (ex - 0.24 * R, ey - 0.16 * R)], width=gw)
        pen.line([(fx - sep + 0.22 * R, ey - 0.04 * R), (fx + sep - 0.22 * R, ey - 0.04 * R)],
                 width=gw)


def draw_ears(pen: _Pen, kit, cx, hy, R):
    """Tai hai bên đầu (kiểu nhân vật có tai to, thấy rõ) — vẽ trước mặt để đầu che bớt."""
    if not (kit.get("_sty") or {}).get("ears"):
        return
    skin = SKINS[kit["skin"]]
    for sx in (-1, 1):
        pen.ell(cx + sx * 0.98 * R, hy + 0.14 * R, 0.2 * R, 0.25 * R, skin)
        pen.line(_ellipse_pts(cx + sx * 1.0 * R, hy + 0.14 * R, 0.09 * R, 0.13 * R,
                              90 - sx * 90, 270 - sx * 90, 8), width=max(1, pen.lw // 2))


def _human(kit, T, expr, mouth_open, blink, facing, seed):
    child = kit["age"] == "child"
    R = T * (0.29 if child else 0.25)
    W, H = int(T * 1.15), int(T * 1.32)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pen = _Pen(img, T, seed)
    cx, bottom = W / 2, H - T * 0.02
    hy = bottom - T + R
    face_dir = 1 if facing > 0.15 else (-1 if facing < -0.15 else 0)
    _draw_head_parts(pen, kit, cx, hy, R, "back")
    _draw_hair_back(pen, kit, cx, hy, R, face_dir or 1)
    _draw_body(img, pen, kit, cx, hy + (0.78 + float(_sty(kit).get("neck", 0.0) or 0.0)) * R, bottom, R, seed)
    draw_ears(pen, kit, cx, hy, R)
    draw_head(pen, kit, cx, hy, R)
    _draw_face(pen, kit, cx, hy, R, facing, expr, mouth_open, blink)
    _draw_hair_front(pen, kit, cx, hy, R, face_dir or 1)
    _draw_hat(pen, kit, cx, hy, R)
    _draw_head_parts(pen, kit, cx, hy, R, "front")
    return img, (cx, bottom), (cx + facing * 0.18 * R, hy + 0.08 * R, R)


def _custom_animal(kit, part, T, expr, mouth_open, blink, facing, seed):
    """Con vật AI vẽ thêm: thân từ các khối, mắt + miệng tool vẽ để có biểu cảm."""
    from . import doodle_parts
    W, H = int(T * 2.3), int(T * 1.3)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pen = _Pen(img, T * 1.6, seed)
    bottom = H - T * 0.03
    cx = W / 2

    def tf(x, y):
        return cx + x * T, bottom - (1 - y) * T
    doodle_parts.draw_shapes(pen, part["shapes"], tf, T)
    er = part.get("eye_r", 0.045) * T
    for ex, ey in part.get("eyes") or []:
        x, y = tf(ex, ey)
        if blink or expr in ("sleep", "happy", "cry"):
            if expr == "happy":
                pen.line([(x - er * 1.3, y + er * 0.4), (x, y - er * 0.9), (x + er * 1.3, y + er * 0.4)])
            else:
                pen.line(_ellipse_pts(x, y, er * 1.2, er * 0.7, 10, 170, 8))
        else:
            rr = er * (1.4 if expr == "shocked" else 1.0)
            pen.dot(x, y, rr)
            pen.dot(x + rr * 0.35, y - rr * 0.35, rr * 0.35, (255, 255, 255))
        if expr in ("sad", "worried", "cry", "angry"):
            k = 1 if expr == "angry" else -1
            pen.line([(x - er * 1.4, y - er * 2.2 - k * er * 0.5), (x + er * 1.4, y - er * 2.2 + k * er * 0.5)],
                     width=max(1, pen.lw // 2))
        if expr == "cry":
            pen.line([(x, y + er), (x, y + er * 6)], width=int(pen.lw * 1.4),
                     fill=(140, 196, 236), wob=False)
    mx, my = tf(*part.get("mouth", (0.8, 0.5)))
    if mouth_open or expr in ("happy", "shocked"):
        pen.ell(mx, my + er * 0.5, er * 1.6, er * (1.4 if mouth_open or expr == "shocked" else 0.9),
                (170, 70, 76), width=max(1, pen.lw // 2))
    else:
        pen.line([(mx - er * 1.4, my), (mx, my + er * 0.6), (mx + er * 1.2, my)],
                 width=max(1, pen.lw // 2))
    eyes = part.get("eyes") or [(0.6, 0.3)]
    hx, hy = tf(*eyes[0])
    if facing < -0.15:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
        hx = W - hx
    return img, (cx, bottom), (hx, hy, T * 0.22)


# ------------------------------------------------------------ chó, mèo

def _animal(kit, T, expr, mouth_open, blink, facing, seed, tail=0.0, dip=0.0):
    """Vẽ quay phải rồi lật nếu quay trái. T = chiều cao con vật. tail = góc đuôi (độ,
    dương = vểnh lên / vẫy ra sau, âm = cụp xuống)."""
    cat = kit["species"] == "cat"
    W, H = int(T * 2.0), int(T * 1.35)                 # rộng hơn thân: đuôi vẫy không bị cắt
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pen = _Pen(img, T * 1.6, seed)
    fur = FUR[kit["fur"]]
    dark = _shade(fur, 0.72)
    bottom = H - T * 0.03
    bx = W / 2 - T * 0.12
    body_top = bottom - T * 0.6
    # đuôi (xoay quanh gốc đuôi để vẫy)
    a = math.radians(tail)
    ox, oy = bx - T * 0.48, bottom - T * 0.4

    def turn(pts):
        return [(ox + (x - ox) * math.cos(a) - (y - oy) * math.sin(a),
                 oy + (x - ox) * math.sin(a) + (y - oy) * math.cos(a)) for x, y in pts]
    if cat:
        tl = turn([(bx - T * 0.5, bottom - T * 0.3), (bx - T * 0.72, bottom - T * 0.55),
                   (bx - T * 0.68, bottom - T * 0.85)])
        pen.line(tl, width=int(pen.lw * 2.4), fill=OUT)
        pen.line(tl, width=int(pen.lw * 1.4), fill=fur)
    else:
        pen.shape(turn(_ellipse_pts(bx - T * 0.6, bottom - T * 0.55, T * 0.14, T * 0.2, 0, 360, 20)),
                  fur)
    # chân ngắn
    for dx in (-0.36, -0.18, 0.2, 0.38):
        x = bx + dx * T
        pen.shape([(x - T * 0.07, bottom - T * 0.2), (x + T * 0.07, bottom - T * 0.2),
                   (x + T * 0.07, bottom), (x - T * 0.07, bottom)], fur)
    # thân
    pen.ell(bx, bottom - T * 0.32, T * 0.56, T * 0.28, fur)
    if kit["fur"] == "spotted":
        pen.ell(bx - T * 0.2, bottom - T * 0.38, T * 0.13, T * 0.09, (90, 74, 64), outline=False)
    # đầu
    hx, hy, r = bx + T * 0.5, bottom - T * 0.66, T * 0.3
    if dip:                                    # cúi đầu (ăn): đầu hạ xuống sát đất trước chân
        hx, hy = hx + T * 0.1 * dip, hy + T * 0.34 * dip
    if cat:
        for sx in (-1, 1):
            ex = hx + sx * r * 0.62
            pen.shape([(ex - r * 0.3, hy - r * 0.6), (ex + sx * r * 0.08, hy - r * 1.3),
                       (ex + r * 0.3, hy - r * 0.6)], fur)
    else:
        droop = expr in ("sad", "cry")
        for sx in (-1, 1):
            ex = hx + sx * r * 0.82
            if droop:
                pen.shape([(ex - r * 0.18, hy - r * 0.5), (ex + r * 0.18, hy - r * 0.5),
                           (ex + sx * r * 0.2, hy + r * 0.45)], dark)
    pen.ell(hx, hy, r, r * 0.92, fur)
    if not cat and not expr in ("sad", "cry"):
        for sx in (-1, 1):                                       # tai cụp nhẹ
            ex = hx + sx * r * 0.7
            pen.shape([(ex - r * 0.22, hy - r * 0.78), (ex + r * 0.22, hy - r * 0.78),
                       (ex + sx * r * 0.38, hy - r * 0.05)], dark)
    # mõm
    mx, my = hx + r * 0.32, hy + r * 0.28
    pen.ell(mx, my, r * 0.42, r * 0.3, _shade(fur, 1.12) if kit["fur"] != "white"
            else (250, 248, 244))
    pen.ell(mx + r * 0.2, my - r * 0.12, r * 0.11, r * 0.08, OUT, outline=False, wob=False)
    # mắt
    for k, ex in enumerate((hx - r * 0.2, hx + r * 0.42)):
        ey = hy - r * 0.18
        if blink or expr in ("sleep", "happy", "cry"):
            if expr == "happy":
                pen.line([(ex - r * 0.12, ey + r * 0.04), (ex, ey - r * 0.08),
                          (ex + r * 0.12, ey + r * 0.04)])
            else:
                pen.line(_ellipse_pts(ex, ey - r * 0.02, r * 0.11, r * 0.06, 10, 170, 8))
        else:
            rr = r * (0.13 if expr == "shocked" else 0.09)
            pen.dot(ex, ey, rr)
            pen.dot(ex + rr * 0.35, ey - rr * 0.35, rr * 0.35, (255, 255, 255))
        if expr in ("sad", "worried", "cry"):
            # lông mày buồn: đầu trong (phía mắt kia) nhếch LÊN, đầu ngoài thấp — không cau có
            inner_right = k == 0
            yl = ey - r * 0.2 + (r * 0.05 if inner_right else -r * 0.05)
            yr = ey - r * 0.2 + (-r * 0.05 if inner_right else r * 0.05)
            pen.line([(ex - r * 0.12, yl), (ex + r * 0.12, yr)], width=max(1, pen.lw // 2))
    if expr == "cry":
        pen.line([(hx - r * 0.2, hy - r * 0.08), (hx - r * 0.2, hy + r * 0.4)],
                 width=int(pen.lw * 1.4), fill=(140, 196, 236), wob=False)
    # miệng
    if mouth_open or expr == "happy":
        pen.shape(_ellipse_pts(mx + r * 0.05, my + r * 0.24, r * 0.17, r * 0.13, 0, 180, 10),
                  (170, 70, 76), width=max(1, pen.lw // 2))
        if expr == "happy" and not cat:                          # thè lưỡi
            pen.ell(mx + r * 0.05, my + r * 0.42, r * 0.1, r * 0.13, (236, 120, 130),
                    width=max(1, pen.lw // 2))
    else:
        pen.line([(mx - r * 0.1, my + r * 0.2), (mx + r * 0.05, my + r * 0.26),
                  (mx + r * 0.2, my + r * 0.2)], width=max(1, pen.lw // 2))
    if cat:
        for sy in (-0.05, 0.08):
            pen.line([(mx + r * 0.35, my + sy * r), (mx + r * 0.7, my + sy * r * 2)],
                     width=max(1, pen.lw // 3))
    if facing < -0.15:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
        hx = W - hx
    return img, (W / 2, bottom), (hx, hy - r * 0.18, r)


# ------------------------------------------------------------ vào ra

def char_height(kit: dict, T: float) -> float:
    """Chiều cao vẽ của nhân vật so với người lớn cao T."""
    sp = kit.get("species")
    p = _part(sp, "animal")
    if p:
        return T * p.get("size", 0.45)
    if sp == "dog":
        return T * 0.42
    if sp == "cat":
        return T * 0.32
    return T * (0.8 if kit.get("age") == "child" else 1.0)


def render(kit: dict, expr: str = "neutral", mouth_open: bool = False, blink: bool = False,
           facing: float = 0.0, height: int = 400, seed: int | None = None, tail: float = 0.0,
           dip: float = 0.0):
    """Ảnh RGBA của nhân vật cao `height` px (người lớn; trẻ con, chó mèo nhỏ hơn).
    Trả về (ảnh, (x, y) điểm chân giữa, (x, y, r) vị trí mắt để vẽ nước mắt...)."""
    kit = clean_kit(kit)
    if expr not in EXPRESSIONS:
        expr = "neutral"
    if seed is None:
        seed = zlib.crc32(repr(sorted(kit.items())).encode()) % 10000
    T = char_height(kit, height) * SS
    if kit["species"] == "human":
        img, foot, eye = _human(kit, T, expr, mouth_open, blink, facing, seed)
    elif _part(kit["species"], "animal"):
        img, foot, eye = _custom_animal(kit, _part(kit["species"], "animal"), T, expr,
                                        mouth_open, blink, facing, seed)
    else:
        img, foot, eye = _animal(kit, T, expr, mouth_open, blink, facing, seed, tail, dip)
    w, h = img.size
    img = img.resize((max(1, w // SS), max(1, h // SS)), Image.LANCZOS)
    return img, (foot[0] / SS, foot[1] / SS), (eye[0] / SS, eye[1] / SS, eye[2] / SS)
