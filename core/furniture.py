# -*- coding: utf-8 -*-
"""Đồ đạc để nhân vật ngồi: ghế, bàn, sofa, giường, ghế đá — theo bối cảnh.

Ảnh nền (core/scene_art.py) vẽ đồ ở tường sau. Đồ ở đây đặt ngay chỗ nhân
vật, chia hai lớp:
  * lớp sau  (vẽ trước nhân vật): lưng ghế, sofa, giường, ghế đá
  * lớp trước (vẽ sau nhân vật): bàn làm việc, bàn học, bàn quán — che chân
    như người thật ngồi sau bàn.
Kích thước tính theo cm (k = số px cho 1 cm, người cao 160 cm), mặt ghế đặt
đúng chỗ hông nhân vật đang ngồi nên vừa với mọi kiểu nhân vật.
"""
from __future__ import annotations

import re

from PIL import Image, ImageDraw

OUT = (52, 46, 58)   # cùng màu viền với bối cảnh và nhân vật

# Bối cảnh (scene_art.KINDS) -> loại chỗ ngồi
SEAT_BY_KIND = {
    "van_phong": "office",
    "lop_hoc": "school",
    "quan_cafe": "cafe",
    "phong_khach": "sofa",
    "phong_ngu": "bed",
    "cong_vien": "bench",
}
# Loại có bàn phía trước (từng người một bàn, bàn sát nhau thì liền thành một)
WITH_DESK = {"office", "school", "cafe"}
# Loại dùng chung một món dài cho cả nhóm
SHARED = {"sofa", "bed", "bench"}

# Nhận ra bối cảnh từ mô tả '## canh:' khi ảnh nền do chị tải lên
_KIND_WORDS = [
    ("van_phong", r"văn phòng|van phong|công ty|cong ty|công sở|phòng họp|office|사무실|회사|회의실"),
    ("lop_hoc", r"lớp học|lop hoc|lớp|trường|classroom|school|교실|학교"),
    ("quan_cafe", r"cà phê|ca phe|cafe|café|quán|nhà hàng|coffee|restaurant|카페|식당"),
    ("phong_ngu", r"phòng ngủ|phong ngu|giường|bedroom|침실|방에서"),
    ("phong_khach", r"phòng khách|phong khach|sofa|living room|거실"),
    ("cong_vien", r"công viên|cong vien|park|공원"),
]


def kind_from_desc(desc: str) -> str | None:
    t = (desc or "").lower()
    for kind, pat in _KIND_WORDS:
        if re.search(pat, t):
            return kind
    return None


def seat_type(kind: str | None) -> str | None:
    return SEAT_BY_KIND.get(kind or "")


def _shade(c, f):
    return tuple(max(0, min(255, int(x * f))) for x in c[:3])


class _Draw:
    def __init__(self, img: Image.Image, k: float):
        self.d = ImageDraw.Draw(img)
        self.k = k
        self.lw = max(3, int(round(k * 0.9)))

    def rect(self, x0, y0, x1, y1, fill, r=0.0):
        box = [int(min(x0, x1)), int(min(y0, y1)), int(max(x0, x1)), int(max(y0, y1))]
        if r:
            self.d.rounded_rectangle(box, radius=int(r * self.k), fill=fill + (255,),
                                     outline=OUT + (255,), width=self.lw)
        else:
            self.d.rectangle(box, fill=fill + (255,), outline=OUT + (255,), width=self.lw)

    def ell(self, x0, y0, x1, y1, fill):
        self.d.ellipse([int(x0), int(y0), int(x1), int(y1)], fill=fill + (255,),
                       outline=OUT + (255,), width=self.lw)


# ------------------------------------------------------------------ lớp sau

def _office_chair(p: _Draw, cx, seat, floor, color):
    k = p.k
    p.rect(cx - 3 * k, seat, cx + 3 * k, floor - 12 * k, _shade(color, 0.7))
    p.rect(cx - 30 * k, floor - 14 * k, cx + 30 * k, floor - 9 * k, _shade(color, 0.6), r=2)
    for x in (cx - 28 * k, cx, cx + 28 * k):
        p.ell(x - 4 * k, floor - 9 * k, x + 4 * k, floor - 1 * k, (40, 40, 46))
    p.rect(cx - 24 * k, seat - 58 * k, cx + 24 * k, seat - 4 * k, color, r=9)
    p.rect(cx - 27 * k, seat - 3 * k, cx + 27 * k, seat + 7 * k, _shade(color, 1.1), r=4)


def _wood_chair(p: _Draw, cx, seat, floor, color, round_back=False):
    k = p.k
    for x in (cx - 20 * k, cx + 20 * k):
        p.rect(x - 2.5 * k, seat - 44 * k, x + 2.5 * k, floor - 1 * k, _shade(color, 0.85))
    if round_back:
        p.ell(cx - 22 * k, seat - 50 * k, cx + 22 * k, seat - 24 * k, color)
    else:
        p.rect(cx - 22 * k, seat - 44 * k, cx + 22 * k, seat - 30 * k, color, r=3)
    p.rect(cx - 24 * k, seat - 3 * k, cx + 24 * k, seat + 5 * k, _shade(color, 1.08), r=2)


def _sofa(p: _Draw, x0, x1, seat, floor, color):
    k = p.k
    p.rect(x0 - 4 * k, seat - 50 * k, x1 + 4 * k, seat + 4 * k, _shade(color, 0.9), r=12)
    p.rect(x0, seat - 4 * k, x1, floor - 8 * k, color, r=6)
    p.rect(x0, seat - 4 * k, x1, seat + 10 * k, _shade(color, 1.08), r=6)
    for x in (x0 - 20 * k, x1):
        p.rect(x, seat - 24 * k, x + 20 * k, floor - 8 * k, _shade(color, 0.95), r=8)
    for x in (x0 - 12 * k, x1 + 12 * k):
        p.rect(x - 2 * k, floor - 9 * k, x + 2 * k, floor, (90, 70, 56))


def _bed(p: _Draw, x0, x1, seat, floor, color):
    k = p.k
    wood = (176, 136, 104)
    p.rect(x0 - 10 * k, seat - 75 * k, x0 + 6 * k, floor, wood, r=5)          # đầu giường
    p.rect(x0 - 4 * k, seat - 4 * k, x1 + 6 * k, seat + 14 * k, (246, 244, 240), r=6)
    p.rect(x0 + 8 * k, seat - 16 * k, x0 + 52 * k, seat - 2 * k, (250, 250, 252), r=7)
    p.rect(x0 + 40 * k, seat + 2 * k, x1 + 8 * k, seat + 26 * k, color, r=6)  # chăn
    p.rect(x0 - 4 * k, seat + 14 * k, x1 + 6 * k, floor - 4 * k, _shade(wood, 0.9))


def _bench(p: _Draw, x0, x1, seat, floor, color):
    k = p.k
    metal = (70, 72, 80)
    for x in (x0 + 6 * k, x1 - 6 * k):
        p.rect(x - 3 * k, seat - 44 * k, x + 3 * k, floor, metal)
    for y in (seat - 44 * k, seat - 31 * k):
        p.rect(x0 - 6 * k, y, x1 + 6 * k, y + 9 * k, color, r=2)
    p.rect(x0 - 8 * k, seat - 3 * k, x1 + 8 * k, seat + 6 * k, _shade(color, 1.08), r=2)


# ------------------------------------------------------------------ lớp trước

def _desk(p: _Draw, x0, x1, top, floor, kind, color, items):
    k = p.k
    if kind == "cafe":
        p.rect(x0, top + 4 * k, x1, floor - 16 * k, color, r=4)           # khăn bàn
        p.rect(x0 - 4 * k, top, x1 + 4 * k, top + 6 * k, (120, 84, 62), r=3)
    else:
        panel = _shade(color, 0.86) if kind == "office" else (104, 132, 112)
        for x in (x0 + 2 * k, x1 - 6 * k):
            p.rect(x, top, x + 4 * k, floor, _shade(color, 0.7))
        p.rect(x0 + 5 * k, top + 5 * k, x1 - 5 * k, floor - 10 * k, panel, r=2)
        p.rect(x0 - 3 * k, top, x1 + 3 * k, top + 6 * k, color, r=2)
    for (cx, side) in items:
        if kind == "office":                                              # lưng laptop
            x = cx + side * 30 * k
            p.rect(x - 16 * k, top - 22 * k, x + 16 * k, top + 1 * k, (186, 190, 198), r=2)
            p.ell(x - 3 * k, top - 13 * k, x + 3 * k, top - 7 * k, (236, 238, 242))
        elif kind == "school":                                            # quyển sách
            x = cx + side * 26 * k
            p.rect(x - 12 * k, top - 4 * k, x + 12 * k, top + 1 * k, (220, 96, 84), r=1)
        else:                                                             # cốc cà phê
            x = cx + side * 22 * k
            p.rect(x - 4.5 * k, top - 10 * k, x + 4.5 * k, top + 1 * k, (250, 250, 248), r=2)


def _merge(spans: list[tuple[float, float]], gap: float) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def draw(seat: str, seats: list[tuple[float, float, float]], k: float, floor: float,
         size: tuple[int, int], color=None) -> tuple[Image.Image | None, Image.Image | None]:
    """Vẽ đồ đạc cho các chỗ ngồi [(x giữa, y mặt ghế, y vai khi ngồi)] trên
    khung `size`.

    Trả về (lớp sau, lớp trước) cùng cỡ khung, nền trong suốt."""
    if not seats:
        return None, None
    back = Image.new("RGBA", size, (0, 0, 0, 0))
    pb = _Draw(back, k)
    mid = size[0] / 2
    xs = [x for x, _, _ in seats]
    if seat in SHARED:
        top = min(y for _, y, _ in seats)
        x0, x1 = min(xs) - 45 * k, max(xs) + 45 * k
        if seat == "sofa":
            _sofa(pb, x0, x1, top, floor, tuple(color or (120, 160, 196)))
        elif seat == "bed":
            _bed(pb, x0 - 20 * k, x1 + 20 * k, top, floor, tuple(color or (236, 160, 186)))
        else:
            _bench(pb, x0, x1, top, floor, (176, 128, 84))
        return back, None

    chair_col = {"office": (64, 68, 82), "school": (196, 150, 98), "cafe": (150, 104, 72),
                 "chair": (176, 128, 84)}[seat]
    for x, y, _ in seats:
        if seat == "office":
            _office_chair(pb, x, y, floor, chair_col)
        else:
            _wood_chair(pb, x, y, floor, chair_col, round_back=(seat == "cafe"))
    if seat not in WITH_DESK:          # ghế lẻ (cảnh không có bàn ghế)
        return back, None

    front = Image.new("RGBA", size, (0, 0, 0, 0))
    pf = _Draw(front, k)
    half = {"office": 52, "school": 40, "cafe": 38}[seat] * k
    desk_col = {"office": (226, 214, 196), "school": (214, 176, 120),
                "cafe": tuple(color or (236, 226, 206))}[seat]
    for a, b in _merge([(x - half, x + half) for x in xs], gap=6 * k):
        members = [(x, y, sh) for x, y, sh in seats if a <= x <= b]
        # mặt bàn ngang khuỷu tay: ~40% quãng từ mặt ghế lên vai
        top = min(y - max(12 * k, min(30 * k, 0.4 * (y - sh))) for x, y, sh in members)
        items = [(x, 1 if x >= mid else -1) for x, _, _ in members]
        _desk(pf, a, b, top, floor, seat, desk_col, items)
    return back, front
