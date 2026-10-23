# -*- coding: utf-8 -*-
"""Vẽ bối cảnh phẳng theo mẫu (phòng khách, bếp, đường phố, công viên...).

Mỗi mẫu là vài mảng màu + đồ vật đơn giản, viền đậm cùng phong cách nhân
vật. Đồ vật vẽ theo kích thước thật (cm) so với nhân vật: người cao ~160 cm
đứng ở vạch chân của khung (config.stage_layout), tường sau cao 260 cm lùi
vào trong một chút nên nhỏ hơn người một chút, sàn có phối cảnh hội tụ về
tầm mắt. Vẽ được cho mọi khung (9:16, 16:9, 1:1): đồ vật bám theo mép trái,
mép phải hoặc giữa khung nên khung ngang thấy rộng hơn chứ không bị kéo
méo. Vẽ bằng Pillow nên chạy tức thì, không cần model ảnh.

Claude chọn mẫu (kind), ban ngày/đêm (time) và có thể đổi màu chủ đạo.
"""
from __future__ import annotations

import math
import random
import zlib
from pathlib import Path

from PIL import Image, ImageDraw

from . import config

OUT = (52, 46, 58)   # màu viền
LW = 6

# Mẫu bối cảnh: tên -> (nhãn tiếng Việt, màu mặc định)
KINDS: dict[str, dict] = {
    "phong_khach": {"label": "Phòng khách", "wall": (236, 222, 200), "floor": (190, 146, 108), "accent": (120, 160, 196)},
    "bep":         {"label": "Nhà bếp", "wall": (226, 238, 232), "floor": (214, 200, 178), "accent": (232, 120, 96)},
    "phong_ngu":   {"label": "Phòng ngủ", "wall": (214, 210, 236), "floor": (176, 140, 120), "accent": (236, 160, 186)},
    "van_phong":   {"label": "Văn phòng", "wall": (222, 228, 234), "floor": (150, 156, 170), "accent": (96, 140, 200)},
    "lop_hoc":     {"label": "Lớp học", "wall": (240, 230, 196), "floor": (186, 150, 110), "accent": (60, 110, 84)},
    "quan_cafe":   {"label": "Quán cà phê", "wall": (204, 168, 132), "floor": (120, 88, 66), "accent": (250, 226, 170)},
    "cua_hang":    {"label": "Cửa hàng / siêu thị", "wall": (236, 240, 244), "floor": (206, 210, 214), "accent": (232, 96, 88)},
    "duong_pho":   {"label": "Đường phố", "wall": (168, 210, 240), "floor": (150, 150, 158), "accent": (226, 172, 120)},
    "cong_vien":   {"label": "Công viên", "wall": (170, 216, 246), "floor": (132, 196, 110), "accent": (88, 150, 84)},
    "bai_bien":    {"label": "Bãi biển", "wall": (150, 210, 246), "floor": (242, 220, 168), "accent": (70, 160, 210)},
    "trong":       {"label": "Nền trống (sân khấu)", "wall": (246, 214, 120), "floor": (232, 176, 96), "accent": (255, 240, 200)},
}

TIMES = ("ngay", "dem")

# Phong cách vẽ bối cảnh (lọc ảnh sau khi vẽ, không cần model ảnh)
ART_STYLES: dict[str, str] = {
    "flat": "Hoạt hình phẳng (mặc định) — màu tươi, nét viền rõ",
    "pastel": "Pastel dịu — màu nhạt, mềm, hợp chuyện gia đình, dễ thương",
    "watercolor": "Màu nước — loang màu, có vân giấy",
    "pencil": "Chì màu — nét chì, giấy vẽ tay",
    "comic": "Truyện tranh — ít mảng màu, viền đen đậm",
    "vintage": "Hoài cổ — ngả vàng nâu, hạt phim, tối góc",
    "night_neon": "Tối neon — tông tối, ánh tím xanh như phim",
    "blur": "Xoá phông — nền mờ nhẹ cho nhân vật nổi bật",
    "doodle": "Vẽ tay webtoon — nét run, màu dịu, vân giấy (hợp kể chuyện)",
}

OUTDOOR = {"duong_pho", "cong_vien", "bai_bien", "san_que", "duong_lang", "canh_dong"}


def kinds_catalog() -> str:
    """Danh mục mẫu cho prompt."""
    return ", ".join(f"{k} ({v['label']})" for k, v in KINDS.items())


def _rgb(v, default) -> tuple[int, int, int]:
    try:
        return tuple(max(0, min(255, int(x))) for x in v[:3])  # type: ignore[return-value]
    except (TypeError, ValueError, IndexError):
        return default


def _shade(c, k: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(x * k))) for x in c)  # type: ignore[return-value]


def _mix(a, b, t: float) -> tuple[int, int, int]:
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


PERSON_CM = 160.0     # chiều cao người quy ước
WALL_CM = 260.0       # trần nhà
BACK = 0.84           # tường sau lùi vào: nhỏ hơn mặt phẳng chỗ người đứng


class _Pen:
    """Bút vẽ theo cm trên mặt phẳng tường sau.

    x tính từ một mốc: "l" mép trái (x dương đi vào trong), "r" mép phải
    (x âm đi vào trong), "c" giữa khung. y tính bằng cm từ chân tường lên.
    s = tỉ lệ xa gần (1 = mặt phẳng tường sau; <1 xa hơn, >1 gần hơn).
    """

    def __init__(self, img: Image.Image, layout_size: tuple[int, int] | None = None):
        """layout_size: khung video thật khi ảnh nền rộng hơn khung (sân khấu
        rộng ở khung dọc) — tỉ lệ người / đồ vật lấy theo khung thật."""
        self.img = img
        self.d = ImageDraw.Draw(img)
        self.w, self.h = img.size
        lay = config.stage_layout(*(layout_size or (self.w, self.h)))
        ch = self.h * lay["height"][0]          # khung nhân vật 1-2 người
        self.floor = self.h * lay["floor"]       # vạch chân người
        self.ppc = ch * 0.92 / PERSON_CM * BACK   # px / cm ở tường sau
        self.base = self.floor - ch * 0.10       # chân tường sau
        self.eye = self.floor - ch * 0.62        # tầm mắt (điểm hội tụ)
        self.u = min(self.w, self.h) / 1080
        self.lw = max(3, int(LW * self.u))

    # --- quy đổi toạ độ
    def X(self, x: float, a: str = "c", s: float = 1.0) -> int:
        o = {"l": 0.0, "r": float(self.w)}.get(a, self.w / 2)
        return int(o + x * self.ppc * s)

    def Y(self, y: float, s: float = 1.0, base: float | None = None) -> int:
        b = self.base if base is None else base
        return int(b - y * self.ppc * s)

    def L(self, cm: float, s: float = 1.0) -> int:
        return max(1, int(cm * self.ppc * s))

    def box(self, a, x0, y0, x1, y1, s=1.0, base=None):
        xa, xb = sorted((self.X(x0, a, s), self.X(x1, a, s)))
        ya, yb = sorted((self.Y(y0, s, base), self.Y(y1, s, base)))
        return [xa, ya, xb, yb]

    def rect(self, a, x0, y0, x1, y1, fill, r=0, s=1.0, base=None, outline=True):
        b = self.box(a, x0, y0, x1, y1, s, base)
        kw = {"fill": fill, "outline": OUT if outline else None,
              "width": self.lw if outline else 0}
        if r:
            self.d.rounded_rectangle(b, radius=self.L(r, s), **kw)
        else:
            self.d.rectangle(b, **kw)

    def ell(self, a, x0, y0, x1, y1, fill, s=1.0, base=None, outline=True):
        self.d.ellipse(self.box(a, x0, y0, x1, y1, s, base), fill=fill,
                       outline=OUT if outline else None,
                       width=self.lw if outline else 0)

    def circle(self, a, x, y, r, fill, s=1.0, base=None, outline=True):
        self.ell(a, x - r, y - r, x + r, y + r, fill, s, base, outline)

    def line(self, a, pts, fill=OUT, width=None, s=1.0, base=None):
        self.d.line([(self.X(x, a, s), self.Y(y, s, base)) for x, y in pts],
                    fill=fill, width=width or self.lw)

    def poly(self, a, pts, fill, s=1.0, base=None, outline=True):
        self.d.polygon([(self.X(x, a, s), self.Y(y, s, base)) for x, y in pts],
                       fill=fill, outline=OUT if outline else None)

    # --- mảng nền (px)
    def band(self, y0: float, y1: float, fill):
        self.d.rectangle([0, int(y0), self.w, int(y1)], fill=fill)

    def hline(self, y: float, fill=OUT, width=None):
        self.d.line([(0, int(y)), (self.w, int(y))], fill=fill, width=width or self.lw)

    def span_cm(self, s: float = 1.0) -> float:
        """Bề ngang khung tính bằng cm ở độ xa s."""
        return self.w / (self.ppc * s)


# ------------------------------------------------------------------ đồ vật
# Kích thước thật (cm). Tham số: mốc a, toạ độ x (cm, cạnh trái của đồ vật
# nếu không ghi khác), y = cao từ chân tường.

def _window(p: _Pen, a, x, w=120, sill=90, hgt=120, night=False, curtain=None):
    sky = (40, 52, 96) if night else (178, 222, 248)
    if curtain:
        p.rect(a, x - 28, sill - 30, x + 12, sill + hgt + 18, curtain, r=10)
        p.rect(a, x + w - 12, sill - 30, x + w + 28, sill + hgt + 18, curtain, r=10)
    p.rect(a, x, sill, x + w, sill + hgt, sky, r=4)
    if night:
        p.circle(a, x + w * 0.7, sill + hgt * 0.75, 9, (250, 240, 190), outline=False)
    else:
        p.ell(a, x + w * 0.12, sill + hgt * 0.68, x + w * 0.5, sill + hgt * 0.82,
              (255, 255, 255), outline=False)
    p.line(a, [(x + w / 2, sill), (x + w / 2, sill + hgt)])
    p.line(a, [(x, sill + hgt / 2), (x + w, sill + hgt / 2)])
    p.rect(a, x - 6, sill - 6, x + w + 6, sill, (246, 242, 234))       # bậu cửa
    if curtain:
        p.rect(a, x - 34, sill + hgt + 14, x + w + 34, sill + hgt + 22, (150, 116, 88))


def _door(p: _Pen, a, x, w=90, color=(176, 128, 92)):
    p.rect(a, x - 6, 0, x + w + 6, 216, (246, 242, 234))
    p.rect(a, x, 0, x + w, 210, color)
    p.rect(a, x + 12, 120, x + w - 12, 196, _shade(color, 0.9), r=3)
    p.rect(a, x + 12, 16, x + w - 12, 104, _shade(color, 0.9), r=3)
    p.circle(a, x + w - 14, 100, 4, (236, 200, 96))


def _frame(p: _Pen, a, x, y, w, h, color):
    p.rect(a, x, y, x + w, y + h, (250, 246, 236), r=2)
    p.rect(a, x + 5, y + 5, x + w - 5, y + h - 5, color, outline=False)
    p.poly(a, [(x + 5, y + 5), (x + w * 0.45, y + h * 0.62), (x + w - 5, y + 5)],
           _shade(color, 0.7), outline=False)


def _plant(p: _Pen, a, x, s=1.0, base=None, hgt=90):
    """Chậu cây cao hgt cm, x = tâm."""
    k = hgt / 90
    p.rect(a, x - 18 * k, 0, x + 18 * k, 30 * k, (200, 120, 84), r=4, s=s, base=base)
    for dx, dy in ((-16, 52), (0, 70), (16, 50)):
        p.ell(a, x + (dx - 16) * k, (dy - 18) * k, x + (dx + 16) * k, (dy + 20) * k,
              (96, 170, 96), s=s, base=base)


def _floor_lamp(p: _Pen, a, x, night, base=None, s=1.0):
    p.rect(a, x - 14, 0, x + 14, 4, OUT, s=s, base=base, outline=False)
    p.line(a, [(x, 0), (x, 140)], width=max(3, p.L(3, s)), s=s, base=base)
    shade = (255, 226, 140) if night else (250, 236, 200)
    p.poly(a, [(x - 24, 136), (x + 24, 136), (x + 15, 166), (x - 15, 166)], shade,
           s=s, base=base)


def _sofa(p: _Pen, a, x, w=200, color=(120, 160, 196)):
    p.rect(a, x, 40, x + w, 88, _shade(color, 0.88), r=14)          # lưng
    p.rect(a, x + 18, 18, x + w - 18, 46, color, r=8)                # đệm
    for i in range(1, 3):
        xx = x + 18 + (w - 36) * i / 3
        p.line(a, [(xx, 22), (xx, 44)], fill=_shade(color, 0.7), width=max(2, p.lw // 2))
    p.rect(a, x - 4, 10, x + 24, 62, _shade(color, 0.95), r=10)     # tay vịn
    p.rect(a, x + w - 24, 10, x + w + 4, 62, _shade(color, 0.95), r=10)
    for xx in (x + 10, x + w - 10):
        p.rect(a, xx - 4, 0, xx + 4, 10, (90, 70, 60))


def _tv_unit(p: _Pen, a, x, w=160, accent=(120, 160, 196)):
    p.rect(a, x, 0, x + w, 50, (176, 136, 104), r=3)
    p.line(a, [(x + w / 2, 6), (x + w / 2, 44)])
    p.rect(a, x + 14, 60, x + w - 14, 130, (40, 44, 56), r=3)        # TV 55 inch
    p.rect(a, x + 20, 66, x + w - 20, 124, _mix(accent, (30, 40, 60), 0.55), outline=False)
    p.rect(a, x + w / 2 - 6, 50, x + w / 2 + 6, 60, (40, 44, 56), outline=False)


def _table(p: _Pen, a, x, w=80, hgt=75, color=(176, 136, 104), s=1.0, base=None):
    p.rect(a, x, hgt - 5, x + w, hgt, color, r=2, s=s, base=base)
    for xx in (x + 6, x + w - 10):
        p.rect(a, xx, 0, xx + 4, hgt - 5, _shade(color, 0.8), s=s, base=base)


def _chair(p: _Pen, a, x, color=(150, 104, 72), s=1.0, base=None, back_right=False):
    p.rect(a, x, 43, x + 42, 47, color, s=s, base=base)
    for xx in (x + 3, x + 35):
        p.rect(a, xx, 0, xx + 4, 43, _shade(color, 0.8), s=s, base=base)
    bx = x + 36 if back_right else x + 2
    p.rect(a, bx, 47, bx + 4, 92, _shade(color, 0.8), s=s, base=base)
    p.rect(a, x, 80, x + 42, 92, color, r=2, s=s, base=base)


def _clock(p: _Pen, a, x, y):
    p.circle(a, x, y, 16, (250, 250, 250))
    p.line(a, [(x, y), (x, y + 10)])
    p.line(a, [(x, y), (x + 7, y - 2)])


def _tree(p: _Pen, a, x, s=1.0, base=None, leaf=(88, 160, 84), hgt=450):
    k = hgt / 450
    p.rect(a, x - 14 * k, 0, x + 14 * k, 220 * k, (140, 96, 64), s=s, base=base)
    for dx, dy, r in ((0, 330, 120), (-80, 270, 85), (80, 270, 85)):
        p.ell(a, x + (dx - r) * k, (dy - r * 0.7) * k, x + (dx + r) * k, (dy + r * 0.7) * k,
              leaf, s=s, base=base)


def _cloud(p: _Pen, cx, cy, r, col=(255, 255, 255)):
    for dx, k in ((-0.9, 0.7), (0.0, 1.0), (0.9, 0.7)):
        rr = r * k
        p.d.ellipse([cx + dx * r - rr, cy - rr * 0.56, cx + dx * r + rr, cy + rr * 0.56], fill=col)


def _stars(p: _Pen, y1, rng):
    for _ in range(int(40 * p.w / 1080)):
        x, y = rng.random() * p.w, rng.random() * y1
        r = rng.choice((2, 3, 4)) * max(1.0, p.u)
        p.d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 250, 220))


# ------------------------------------------------------------------ nền

def _room_base(p: _Pen, wall, floor, boards=True):
    """Tường sau cao 260 cm, trần phía trên, sàn phối cảnh."""
    top = p.Y(WALL_CM)
    p.band(0, p.h, floor)
    p.band(max(0, top), p.base, wall)
    if top > 0:                                  # trần nhà
        p.band(0, top, _shade(wall, 0.9))
        p.hline(top, fill=_shade(wall, 0.72), width=max(2, p.lw // 2))
    # chân tường 10 cm
    p.band(p.Y(10), p.base, _shade(wall, 0.8))
    p.hline(p.base)
    if not boards:
        return
    # ván sàn hội tụ về tầm mắt giữa khung
    vx, vy = p.w / 2, p.eye
    step = 32 * p.ppc
    n = int(p.w / step) + 2
    col = _shade(floor, 0.86)
    for i in range(-n, n + 1):
        x0 = vx + i * step
        # kéo dài đường từ điểm hội tụ qua (x0, chân tường) tới đáy khung
        k = (p.h - vy) / max(1.0, p.base - vy)
        p.d.line([(x0, p.base), (vx + (x0 - vx) * k, p.h)], fill=col, width=max(2, p.lw // 2))
    y, gap = p.base, (p.h - p.base) * 0.12
    while y < p.h:
        y += gap
        gap *= 1.45
        p.hline(y, fill=_mix(col, floor, 0.4), width=max(1, p.lw // 3))


def _outdoor_ground(p: _Pen, ground, edge=None):
    p.band(p.base, p.h, ground)
    if edge is not None:
        p.band(p.base, p.base + max(4, p.L(6)), edge)
    p.hline(p.base)


def _sky(p: _Pen, sky, night, rng, y1=None):
    y1 = p.base if y1 is None else y1
    p.band(0, y1, sky)
    if night:
        _stars(p, y1 * 0.7, rng)
        p.d.ellipse([p.w * 0.78 - 40 * p.u, p.h * 0.06, p.w * 0.78 + 40 * p.u,
                     p.h * 0.06 + 80 * p.u], fill=(250, 240, 190))
    else:
        _cloud(p, p.w * 0.25, y1 * 0.14, 60 * p.u)
        _cloud(p, p.w * 0.74, y1 * 0.24, 46 * p.u)


def _draw_kind(p: _Pen, kind: str, wall, floor, accent, night: bool, rng):
    if kind == "phong_khach":
        _room_base(p, wall, floor)
        _window(p, "l", 30, 120, 90, 120, night, curtain=accent)
        _frame(p, "c", -45, 150, 90, 60, accent)
        _floor_lamp(p, "l", 200, night)
        _sofa(p, "r", -250, 210, accent)
        _plant(p, "r", -24)
    elif kind == "bep":
        _room_base(p, wall, floor)
        tile = _shade(wall, 0.94)
        for i in range(int(p.span_cm() / 30) + 2):        # gạch men sau bếp
            for j in range(2):
                x = i * 30 - (15 if j else 0)
                p.rect("l", x, 95 + j * 25, x + 28, 118 + j * 25, tile, outline=False)
        p.rect("l", -4, 0, 70, 182, (238, 242, 246), r=8)      # tủ lạnh 70x180
        p.line("l", [(-4, 120), (70, 120)])
        p.line("l", [(58, 130), (58, 165)], width=max(4, p.lw))
        p.line("l", [(58, 70), (58, 110)], width=max(4, p.lw))
        _window(p, "c", -50, 100, 120, 80, night)
        cab = _shade(accent, 0.95)
        p.rect("r", -260, 0, 4, 88, cab, r=3)                  # quầy bếp 90 cm
        p.rect("r", -266, 88, 4, 94, (220, 210, 196), r=2)
        for xx in range(-250, 0, 60):
            p.rect("r", xx, 10, xx + 54, 78, _shade(cab, 0.92), r=2)
            p.circle("r", xx + 27, 66, 3, OUT, outline=False)
        p.rect("r", -260, 150, 4, 222, cab, r=3)               # tủ treo
        # bếp ga, nồi cơm, lò vi sóng... vẽ ở core/scene_decor.py
    elif kind == "phong_ngu":
        _room_base(p, wall, floor)
        _window(p, "r", -150, 110, 100, 120, night, curtain=accent)
        p.rect("l", -10, 0, 12, 105, (170, 120, 90), r=4)      # đầu giường
        p.rect("l", -10, 20, 190, 52, (250, 250, 252), r=8)    # giường cao 50 cm
        p.rect("l", -10, 20, 190, 42, accent, r=8)
        p.rect("l", 18, 50, 70, 66, (255, 255, 255), r=8)      # gối
        p.rect("l", 210, 0, 255, 55, (186, 140, 106), r=3)     # tủ đầu giường
        p.rect("l", 222, 55, 244, 60, (60, 60, 70), outline=False)
        p.poly("l", [(218, 60), (248, 60), (240, 84), (226, 84)],
               (255, 226, 140) if night else (250, 236, 200))
        p.rect("l", 40, 140, 110, 200, _shade(accent, 0.8), r=2)  # áp phích
        p.circle("l", 75, 172, 16, (255, 236, 150), outline=False)
    elif kind == "van_phong":
        _room_base(p, wall, floor)
        _window(p, "l", 20, 160, 90, 130, night)
        for i in range(9):                                     # rèm sáo
            y = 214 - i * 14
            p.line("l", [(20, y), (180, y)], fill=_shade(wall, 0.75),
                   width=max(2, p.lw // 2))
        _clock(p, "c", 0, 215)
        desk = (176, 140, 108)
        p.rect("r", -200, 70, 6, 76, desk, r=2)                # bàn 75 cm
        p.rect("r", -190, 0, -184, 70, _shade(desk, 0.8))
        p.rect("r", -40, 0, -10, 70, _shade(desk, 0.8))
        p.rect("r", -150, 82, -60, 134, (60, 66, 80), r=3)     # màn hình 24"
        p.rect("r", -145, 87, -65, 129, accent, outline=False)
        p.rect("r", -110, 76, -100, 82, (60, 66, 80))
        p.rect("r", -46, 76, -36, 88, (250, 250, 250), r=2)    # cốc
        p.rect("r", -260, 0, -222, 120, (210, 226, 240), r=4)  # bình nước
        _plant(p, "l", 230, hgt=110)
    elif kind == "lop_hoc":
        _room_base(p, wall, floor)
        p.rect("c", -160, 90, 160, 210, (186, 140, 96), r=3)   # bảng 320x120
        p.rect("c", -154, 96, 154, 204, accent, outline=False)
        chalk = (240, 240, 230)
        p.line("c", [(-120, 175), (-20, 175)], fill=chalk, width=max(2, p.lw // 2))
        p.line("c", [(-120, 150), (-50, 150)], fill=chalk, width=max(2, p.lw // 2))
        p.circle("c", 80, 160, 22, None)
        _clock(p, "c", 0, 236)
        _door(p, "l", 20)
        desk = (196, 156, 112)
        _table(p, "r", -170, 110, 72, desk)
        _chair(p, "r", -150)
        _chair(p, "r", -90)
    elif kind == "quan_cafe":
        _room_base(p, wall, floor)
        p.rect("l", 30, 140, 170, 220, (60, 56, 52), r=3)      # bảng menu
        for i in range(4):
            y = 205 - i * 17
            p.line("l", [(46, y), (154, y)], fill=(240, 230, 210), width=max(2, p.lw // 2))
        top = WALL_CM
        for xx in (-120, 0, 120):                               # đèn thả
            p.line("c", [(xx, top), (xx, top - 50)], width=max(2, p.lw // 2))
            p.poly("c", [(xx - 22, top - 70), (xx + 22, top - 70), (xx + 10, top - 50),
                         (xx - 10, top - 50)], accent)
            if night:
                p.ell("c", xx - 14, top - 76, xx + 14, top - 68, (255, 236, 160), outline=False)
        wood = (150, 104, 72)
        p.rect("r", -230, 0, 6, 100, wood, r=3)                # quầy 105 cm
        p.rect("r", -236, 100, 6, 107, (230, 214, 190), r=2)
        p.rect("r", -190, 107, -175, 125, (250, 250, 250), r=2)
        p.rect("r", -150, 107, -136, 128, accent, r=2)
        p.rect("r", -80, 107, -40, 150, (70, 70, 80), r=4)     # máy pha
        _table(p, "l", 200, 70, 75, wood)
        _chair(p, "l", 160)
        _chair(p, "l", 270, back_right=True)
    elif kind == "cua_hang":
        _room_base(p, wall, floor)
        cols = [accent, (96, 168, 112), (238, 198, 86), (84, 124, 200), (238, 164, 188)]
        for a, x0 in (("l", -6), ("r", -194)):                 # kệ 180 cm
            x1 = x0 + 200
            p.rect(a, x0, 0, x1, 180, (210, 200, 188), r=3)
            for j in range(4):
                y = 12 + j * 42
                p.line(a, [(x0, y), (x1, y)])
                for k in range(6):
                    bx = x0 + 8 + k * 31
                    p.rect(a, bx, y + 2, bx + 24, y + 30 - (k % 2) * 6,
                           cols[(j + k) % len(cols)], r=2)
        p.rect("c", -110, 205, 110, 245, accent, r=6)          # biển hiệu
        p.line("c", [(-80, 225), (80, 225)], fill=(255, 255, 255), width=max(4, p.lw))
    elif kind == "duong_pho":
        # dãy nhà bên kia vỉa hè (xa hơn nên nhỏ hơn), thấy được tầng trên và trời
        bs = 0.55
        bb = p.base - p.L(35)
        _sky(p, (36, 44, 84) if night else wall, night, rng, bb)
        span = p.span_cm(bs)
        x, i = -20.0, 0
        while x < span:
            bw = rng.choice((300, 360, 420))
            col = _shade(accent, (1.0, 0.86, 0.94, 0.78)[i % 4])
            floors = rng.choice((1, 2, 2, 3))
            kw = {"s": bs, "base": bb}
            p.rect("l", x, 0, x + bw, floors * 300 + 40, col, **kw)
            p.rect("l", x - 6, floors * 300 + 20, x + bw + 6, floors * 300 + 50,
                   _shade(col, 0.8), **kw)
            for f in range(1, floors):
                for wx in range(3):
                    ww = (bw - 80) / 3
                    xx = x + 40 + wx * ww
                    lit = (255, 226, 130) if night and rng.random() < 0.6 else (200, 226, 244)
                    p.rect("l", xx + 10, f * 300 + 70, xx + ww - 10, f * 300 + 220, lit, r=3, **kw)
            # tầng trệt: cửa hàng có mái hiên, cửa ra vào 90x210
            glass = (255, 230, 160) if night else (196, 222, 240)
            p.rect("l", x + 30, 0, x + bw - 30, 230, glass, **kw)
            dx = x + bw / 2 - 45
            p.rect("l", dx, 0, dx + 90, 210, _shade(glass, 0.88), **kw)
            p.line("l", [(dx + 45, 0), (dx + 45, 210)], **kw)
            aw = (232, 96, 88) if i % 2 else (90, 150, 200)
            p.poly("l", [(x + 16, 290), (x + bw - 16, 290), (x + bw - 4, 244), (x + 4, 244)], aw, **kw)
            x += bw
            i += 1
        p.band(bb, p.h, floor)                                   # vỉa hè
        p.d.line([(0, bb), (p.w, bb)], fill=OUT, width=p.lw)
        col = _shade(floor, 0.88)
        for k in range(1, 5):
            p.hline(bb + (p.h - bb) * (k / 5) ** 1.4, fill=col, width=max(1, p.lw // 3))
        # cột đèn 4,7 m sát mép phải, thùng rác sát mép trái
        p.line("r", [(-40, 0), (-40, 470)], width=max(6, p.L(10)))
        p.line("r", [(-40, 470), (-110, 470)], width=max(6, p.L(8)))
        p.ell("r", -130, 448, -80, 468, (255, 230, 150) if night else (240, 240, 240))
        p.rect("l", 20, 0, 70, 90, (96, 140, 110), r=6)
        p.rect("l", 14, 86, 76, 96, _shade((96, 140, 110), 0.8), r=3)
    elif kind == "cong_vien":
        far = p.base - p.L(40)
        _sky(p, (36, 44, 84) if night else wall, night, rng, far)
        p.band(far, p.h, floor)
        for k in range(int(p.span_cm(0.4) / 200) + 2):            # hàng cây xa
            _tree(p, "l", k * 200 + rng.randint(-40, 40), s=0.4, base=far,
                  leaf=_shade(accent, 0.85), hgt=rng.choice((380, 450, 520)))
        p.d.line([(0, far), (p.w, far)], fill=_shade(floor, 0.75), width=max(2, p.lw // 2))
        # lối đi hội tụ về giữa
        vx = p.w / 2
        p.d.polygon([(vx - p.L(60), far), (vx + p.L(60), far),
                     (vx + p.L(260), p.h), (vx - p.L(260), p.h)], fill=(226, 204, 160))
        _tree(p, "l", 70, leaf=accent)
        _tree(p, "r", -60, leaf=accent, hgt=400)
        wood = (176, 120, 80)
        bx = -330 if p.w > p.h else -250
        p.rect("r", bx, 42, bx + 160, 48, wood, r=2)             # ghế đá
        p.rect("r", bx, 62, bx + 160, 80, wood, r=2)
        for xx in (bx + 10, bx + 144):
            p.rect("r", xx, 0, xx + 6, 42, (90, 90, 100))
    elif kind == "bai_bien":
        sea_top = p.eye
        _sky(p, (40, 52, 100) if night else wall, night, rng, sea_top)
        sea = accent if not night else _shade(accent, 0.5)
        p.band(sea_top, p.base, sea)
        for i in range(6):
            y = sea_top + (p.base - sea_top) * (i + 1) / 7
            x0 = (0.08 + 0.3 * (i % 3)) * p.w
            p.d.line([(x0, y), (x0 + 0.18 * p.w, y)], fill=(240, 250, 255),
                     width=max(2, p.lw // 2))
        p.band(p.base, p.h, floor)
        p.d.chord([-p.w * 0.1, p.base - p.L(14), p.w * 1.1, p.base + p.L(14)], 0, 180,
                  fill=(240, 250, 255))
        # dừa bên trái, dù bên phải
        trunk = (160, 112, 72)
        ps, pb = 0.55, p.base - p.L(25)              # cây dừa lùi ra xa
        pts = [(60 + 30 * (k / 6) ** 2, 360 * k / 6) for k in range(7)]
        p.line("l", pts, fill=trunk, width=p.L(28, ps), s=ps, base=pb)
        tx, ty = pts[-1]
        for ang, ln in ((195, 200), (225, 180), (270, 140), (315, 180), (345, 200)):
            a = math.radians(ang)
            p.line("l", [(tx, ty), (tx + ln * 0.5 * math.cos(a), ty + 30),
                         (tx + ln * math.cos(a), ty + ln * 0.45 * math.sin(a) + 20)],
                   fill=(84, 160, 84), width=p.L(26, ps), s=ps, base=pb)
        for dx in (-12, 12):
            p.circle("l", tx + dx, ty - 14, 12, (120, 90, 50), s=ps, base=pb)
        p.line("r", [(-120, 0), (-120, 210)], width=max(4, p.L(5)))
        b = p.box("r", -230, 190, -10, 250)
        p.d.pieslice([b[0], b[1], b[2], b[3] + (b[3] - b[1])], 180, 360,
                     fill=(232, 96, 88), outline=OUT, width=p.lw)
    else:  # trong — nền sân khấu có tia sáng
        p.band(0, p.h, wall)
        cx, cy = p.w / 2, p.eye - p.L(60)
        R = 2 * max(p.w, p.h)
        for i in range(16):
            a0 = 2 * math.pi * i / 16
            a1 = a0 + math.pi / 16
            p.d.polygon([(cx, cy), (cx + R * math.cos(a0), cy + R * math.sin(a0)),
                         (cx + R * math.cos(a1), cy + R * math.sin(a1))],
                        fill=accent if i % 2 else wall)
        p.band(p.base, p.h, floor)
        p.hline(p.base)


def render_scene(kind: str = "phong_khach", time: str = "ngay",
                 wall=None, floor=None, accent=None, seed: int = 0,
                 size: tuple[int, int] | None = None,
                 layout_size: tuple[int, int] | None = None,
                 art: str = "flat") -> Image.Image:
    """Vẽ một bối cảnh theo khung size (mặc định 9:16). Màu không truyền
    thì dùng màu mặc định của mẫu. layout_size: khung video thật khi size rộng
    hơn khung (sân khấu rộng, máy quay lia theo người nói)."""
    spec = KINDS.get(kind) or KINDS["phong_khach"]
    kind = kind if kind in KINDS else "phong_khach"
    night = time == "dem"
    wall = _rgb(wall, spec["wall"]) if wall is not None else spec["wall"]
    floor = _rgb(floor, spec["floor"]) if floor is not None else spec["floor"]
    accent = _rgb(accent, spec["accent"]) if accent is not None else spec["accent"]
    if night and kind not in OUTDOOR:
        wall, floor = _mix(wall, (40, 44, 80), 0.45), _mix(floor, (30, 30, 50), 0.4)
    w, h = size or (config.WIDTH, config.HEIGHT)
    img = Image.new("RGB", (w, h), wall)
    pen = _Pen(img, layout_size)
    if kind in _rural.KINDS:
        _rural.draw(pen, kind, wall, floor, accent, night, random.Random(seed))
    else:
        _draw_kind(pen, kind, wall, floor, accent, night, random.Random(seed))
    if art == "doodle" and kind not in OUTDOOR:
        _scratches(pen, wall, random.Random(seed + 3))
    # đồ đời thường (đèn trần, điều hoà, kệ, thảm, xe máy...) cho giống thật
    from . import scene_decor
    scene_decor.decorate(pen, kind, wall, floor, accent, night, random.Random(seed + 7))
    if night:
        # phủ tối nhẹ cho cảnh đêm, giữ đồ vật vẫn rõ
        img = Image.blend(img, Image.new("RGB", (w, h), (20, 24, 60)), 0.18)
    return stylize(img, art, layout_size)


def render_spec(spec: dict, size: tuple[int, int],
                layout_size: tuple[int, int] | None = None) -> Image.Image:
    """Vẽ lại bối cảnh từ spec đã lưu (cùng seed với lúc vẽ lần đầu)."""
    return render_scene(spec.get("kind", "phong_khach"), spec.get("time", "ngay"),
                        spec.get("wall"), spec.get("floor"), spec.get("accent"),
                        seed=zlib.crc32(str(spec.get("name", "")).encode("utf-8")) % 1000,
                        size=size, layout_size=layout_size, art=spec.get("art") or "flat")


def save_scene(spec: dict, out_path: Path,
               size: tuple[int, int] | None = None) -> Path:
    """Vẽ theo spec của Claude ({kind, time, wall, floor, accent}) và lưu file."""
    img = render_scene(spec.get("kind", "phong_khach"), spec.get("time", "ngay"),
                       spec.get("wall"), spec.get("floor"), spec.get("accent"),
                       seed=zlib.crc32(str(spec.get("name", "")).encode("utf-8")) % 1000,
                       size=size, art=spec.get("art") or "flat")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


# ------------------------------------------------------------ phong cách vẽ

def _np(img: Image.Image):
    import numpy as np
    return np.asarray(img.convert("RGB")).astype("float32")


def _vignette(a, layout_size, strength: float):
    """Tối dần ra mép. Ảnh rộng hơn khung (máy quay lia) thì chỉ tối trên,
    dưới để mép trái phải của khung không tối nhảy theo máy quay."""
    import numpy as np
    h, w = a.shape[:2]
    y = np.linspace(-1, 1, h)[:, None]
    wide = bool(layout_size and w > layout_size[0] * 1.05)
    x = np.zeros((1, w)) if wide else np.linspace(-1, 1, w)[None, :]
    d = np.clip(np.sqrt(x * x * 0.8 + y * y) - 0.55, 0, None)
    return a * (1 - strength * np.clip(d, 0, 1))[..., None]


def _paper(a, rng_seed: int, amount: float):
    """Vân giấy: nhiễu mờ nhân vào ảnh."""
    import cv2
    import numpy as np
    h, w = a.shape[:2]
    n = np.random.default_rng(rng_seed).normal(0, 1, (h // 4 + 1, w // 4 + 1)).astype("float32")
    n = cv2.resize(cv2.GaussianBlur(n, (0, 0), 1.2), (w, h), interpolation=cv2.INTER_CUBIC)
    return a * (1 + amount * n)[..., None]


def stylize(img: Image.Image, art: str | None, layout_size=None) -> Image.Image:
    """Lọc ảnh bối cảnh theo phong cách. art lạ hoặc 'flat' thì để nguyên."""
    if not art or art == "flat" or art not in ART_STYLES:
        return img
    import cv2
    import numpy as np
    a = _np(img)
    if art == "pastel":
        hsv = cv2.cvtColor(a.astype("uint8"), cv2.COLOR_RGB2HSV).astype("float32")
        hsv[..., 1] *= 0.55
        a = cv2.cvtColor(np.clip(hsv, 0, 255).astype("uint8"), cv2.COLOR_HSV2RGB).astype("float32")
        a = a * 0.78 + 255 * 0.22
        a = cv2.GaussianBlur(a, (0, 0), 1.2)
    elif art == "watercolor":
        u = cv2.stylization(a.astype("uint8"), sigma_s=60, sigma_r=0.45).astype("float32")
        u = cv2.GaussianBlur(u, (0, 0), 1.5) * 0.85 + 255 * 0.15
        a = _paper(u, 3, 0.05)
    elif art == "pencil":
        gray, _ = cv2.pencilSketch(a.astype("uint8"), sigma_s=40, sigma_r=0.07, shade_factor=0.03)
        hsv = cv2.cvtColor(a.astype("uint8"), cv2.COLOR_RGB2HSV).astype("float32")
        hsv[..., 1] *= 0.7
        a = cv2.cvtColor(hsv.astype("uint8"), cv2.COLOR_HSV2RGB).astype("float32")
        a = (a * 0.8 + 255 * 0.2) * (0.35 + 0.65 * gray.astype("float32") / 255.0)[..., None]
        a = _paper(a, 5, 0.04)
    elif art == "comic":
        u = a.astype("uint8")
        for _ in range(2):
            u = cv2.bilateralFilter(u, 9, 60, 9)
        q = np.minimum((u.astype("float32") // 40) * 40 + 20, 255)
        g = cv2.cvtColor(u, cv2.COLOR_RGB2GRAY)
        edges = cv2.adaptiveThreshold(cv2.medianBlur(g, 5), 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                      cv2.THRESH_BINARY, 9, 4)
        edges = cv2.erode(edges, np.ones((2, 2), np.uint8))
        a = q * (edges.astype("float32") / 255.0)[..., None]
        a = cv2.cvtColor(np.clip(a, 0, 255).astype("uint8"), cv2.COLOR_RGB2HSV).astype("float32")
        a[..., 1] = np.clip(a[..., 1] * 1.2, 0, 255)
        a = cv2.cvtColor(a.astype("uint8"), cv2.COLOR_HSV2RGB).astype("float32")
    elif art == "vintage":
        sep = np.array([[0.393, 0.769, 0.189], [0.349, 0.686, 0.168], [0.272, 0.534, 0.131]],
                       dtype="float32")
        a = a * 0.45 + (a @ sep.T) * 0.55
        a = a * 0.92 + np.array([18, 10, 0], dtype="float32")
        a += np.random.default_rng(11).normal(0, 7, a.shape[:2]).astype("float32")[..., None]
        a = _vignette(a, layout_size, 0.55)
    elif art == "night_neon":
        a = a * 0.55 * np.array([0.9, 0.85, 1.05], dtype="float32") + np.array([10, 4, 26], dtype="float32")
        glow = cv2.GaussianBlur(np.clip(a - 90, 0, None), (0, 0), 14)
        a = a + glow * np.array([0.9, 0.5, 1.0], dtype="float32")
        a = _vignette(a, layout_size, 0.45)
    elif art == "doodle":
        a = _wobble(a, max(1.2, a.shape[0] / 700), 5)
        hsv = cv2.cvtColor(np.clip(a, 0, 255).astype("uint8"), cv2.COLOR_RGB2HSV).astype("float32")
        hsv[..., 1] *= 0.78
        a = cv2.cvtColor(hsv.astype("uint8"), cv2.COLOR_HSV2RGB).astype("float32")
        a = a * 0.94 + np.array([14, 10, 2], dtype="float32")
        a = _paper(a, 9, 0.035)
    elif art == "blur":
        a = cv2.GaussianBlur(a, (0, 0), max(2.0, a.shape[0] / 300))
        a = a * 0.95 + 255 * 0.05
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"))


def _wobble(a, amp: float, seed: int):
    """Làm nét hơi run như vẽ tay: dịch điểm ảnh theo nhiễu mượt."""
    import cv2
    import numpy as np
    h, w = a.shape[:2]
    rng = np.random.default_rng(seed)
    small = (max(2, h // 40), max(2, w // 40))
    dx = cv2.resize(rng.normal(0, 1, small).astype("float32"), (w, h), interpolation=cv2.INTER_CUBIC)
    dy = cv2.resize(rng.normal(0, 1, small).astype("float32"), (w, h), interpolation=cv2.INTER_CUBIC)
    gx, gy = np.meshgrid(np.arange(w, dtype="float32"), np.arange(h, dtype="float32"))
    return cv2.remap(a, gx + dx * amp, gy + dy * amp, cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_REFLECT)


def _scratches(p: _Pen, wall, rng) -> None:
    """Vài vệt sọc dọc trên tường như tranh vẽ tay kể chuyện Hàn."""
    top = max(0, p.Y(WALL_CM))
    col = _shade(wall, 0.8)
    for _ in range(int(p.w / (70 * p.u))):
        x = rng.random() * p.w
        y = top + rng.random() * (p.base - top) * 0.8
        ln = rng.uniform(25, 70) * p.u
        for k in range(rng.choice((1, 2, 2, 3))):
            xx = x + k * 7 * p.u
            p.d.line([(xx, y), (xx + rng.uniform(-2, 2) * p.u, y + ln * rng.uniform(0.6, 1))],
                     fill=col, width=max(2, int(2.5 * p.u)))


from . import scene_rural as _rural  # noqa: E402  (vẽ bằng _Pen ở trên)

KINDS.update(_rural.KINDS)
