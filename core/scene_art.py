# -*- coding: utf-8 -*-
"""Vẽ bối cảnh phẳng theo mẫu (phòng khách, bếp, đường phố, công viên...).

Mỗi mẫu là vài mảng màu + đồ vật đơn giản, viền đậm cùng phong cách nhân
vật. Giữa khung luôn chừa trống cho nhân vật đứng (chân ở khoảng 80% chiều
cao), đồ vật dồn ra hai bên mép. Vẽ bằng Pillow nên chạy tức thì, không cần
model ảnh.

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


class _Pen:
    """Bút vẽ theo toạ độ tỉ lệ (0..1) trên khung 9:16."""

    def __init__(self, img: Image.Image):
        self.img = img
        self.d = ImageDraw.Draw(img)
        self.w, self.h = img.size

    def X(self, fx: float) -> int:
        return int(fx * self.w)

    def Y(self, fy: float) -> int:
        return int(fy * self.h)

    def box(self, x0, y0, x1, y1):
        return [self.X(x0), self.Y(y0), self.X(x1), self.Y(y1)]

    def rect(self, x0, y0, x1, y1, fill, r=0, outline=True, width=LW):
        b = self.box(x0, y0, x1, y1)
        kw = {"fill": fill, "outline": OUT if outline else None, "width": width if outline else 0}
        if r:
            self.d.rounded_rectangle(b, radius=r, **kw)
        else:
            self.d.rectangle(b, **kw)

    def ell(self, x0, y0, x1, y1, fill, outline=True, width=LW):
        self.d.ellipse(self.box(x0, y0, x1, y1), fill=fill,
                       outline=OUT if outline else None, width=width if outline else 0)

    def line(self, pts, fill=OUT, width=LW):
        self.d.line([(self.X(x), self.Y(y)) for x, y in pts], fill=fill, width=width)

    def poly(self, pts, fill, outline=True):
        self.d.polygon([(self.X(x), self.Y(y)) for x, y in pts], fill=fill,
                       outline=OUT if outline else None)


# ------------------------------------------------------------------ đồ vật

def _window(p: _Pen, x0, y0, x1, y1, night: bool, curtain=None):
    sky = (40, 52, 96) if night else (178, 222, 248)
    p.rect(x0, y0, x1, y1, sky, r=6)
    if night:
        p.ell(x0 + (x1 - x0) * 0.55, y0 + 0.02, x0 + (x1 - x0) * 0.85, y0 + 0.045, (250, 240, 190), outline=False)
    else:
        p.ell(x0 + (x1 - x0) * 0.15, y0 + 0.03, x0 + (x1 - x0) * 0.55, y0 + 0.05, (255, 255, 255), outline=False)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    p.line([(mx, y0), (mx, y1)])
    p.line([(x0, my), (x1, my)])
    if curtain:
        cw = (x1 - x0) * 0.28
        p.rect(x0 - 0.015, y0 - 0.01, x0 + cw, y1 + 0.03, curtain, r=10)
        p.rect(x1 - cw, y0 - 0.01, x1 + 0.015, y1 + 0.03, curtain, r=10)


def _frame(p: _Pen, x0, y0, x1, y1, color):
    p.rect(x0, y0, x1, y1, (250, 246, 236), r=4)
    p.rect(x0 + 0.012, y0 + 0.008, x1 - 0.012, y1 - 0.008, color, outline=False)
    p.poly([(x0 + 0.012, y1 - 0.008), ((x0 + x1) / 2, y0 + (y1 - y0) * 0.45),
            (x1 - 0.012, y1 - 0.008)], _shade(color, 0.7), outline=False)


def _plant(p: _Pen, x, base_y, s=1.0):
    p.rect(x - 0.04 * s, base_y - 0.05 * s, x + 0.04 * s, base_y, (200, 120, 84), r=8)
    for dx, dy in ((-0.04, -0.11), (0.0, -0.14), (0.04, -0.1)):
        p.ell(x + dx * s - 0.035 * s, base_y + dy * s - 0.03 * s,
              x + dx * s + 0.035 * s, base_y + dy * s + 0.04 * s, (96, 170, 96))


def _lamp(p: _Pen, x, base_y, night):
    p.line([(x, base_y), (x, base_y - 0.2)], width=8)
    p.rect(x - 0.012, base_y - 0.005, x + 0.012, base_y, OUT, outline=False)
    shade = (255, 226, 140) if night else (250, 236, 200)
    p.poly([(x - 0.05, base_y - 0.2), (x + 0.05, base_y - 0.2),
            (x + 0.03, base_y - 0.25), (x - 0.03, base_y - 0.25)], shade)


def _tree(p: _Pen, x, base_y, s=1.0, leaf=(88, 160, 84)):
    p.rect(x - 0.025 * s, base_y - 0.16 * s, x + 0.025 * s, base_y, (140, 96, 64))
    for dx, dy, r in ((0, -0.24, 0.11), (-0.07, -0.19, 0.08), (0.07, -0.19, 0.08)):
        p.ell(x + dx * s - r * s, base_y + dy * s - r * s * 0.56,
              x + dx * s + r * s, base_y + dy * s + r * s * 0.56, leaf)


def _cloud(p: _Pen, x, y, s=1.0, col=(255, 255, 255)):
    for dx, r in ((-0.05, 0.04), (0.0, 0.055), (0.05, 0.04)):
        p.ell(x + dx * s - r * s, y - r * s * 0.56, x + dx * s + r * s, y + r * s * 0.56, col, outline=False)


def _stars(p: _Pen, y1, rng):
    for _ in range(40):
        x, y = rng.random(), rng.random() * y1
        r = rng.choice((2, 3, 4))
        p.d.ellipse([p.X(x) - r, p.Y(y) - r, p.X(x) + r, p.Y(y) + r], fill=(255, 250, 220))


# ------------------------------------------------------------------ các mẫu

def _room_base(p: _Pen, wall, floor, horizon=0.66):
    p.rect(0, 0, 1, horizon, wall, outline=False)
    p.rect(0, horizon, 1, 1, floor, outline=False)
    # chân tường
    p.rect(0, horizon - 0.012, 1, horizon + 0.004, _shade(wall, 0.8), outline=False)
    p.line([(0, horizon), (1, horizon)])
    # ván sàn
    for i in range(1, 6):
        y = horizon + (1 - horizon) * i / 6
        p.line([(0, y), (1, y)], fill=_shade(floor, 0.86), width=3)


def _draw_kind(p: _Pen, kind: str, wall, floor, accent, night: bool, rng):
    if kind == "phong_khach":
        _room_base(p, wall, floor)
        _window(p, 0.05, 0.2, 0.3, 0.42, night, curtain=accent)
        _frame(p, 0.72, 0.22, 0.93, 0.34, accent)
        # sofa thò vào từ mép phải
        p.rect(0.8, 0.55, 1.05, 0.72, _shade(accent, 0.9), r=24)
        p.rect(0.76, 0.6, 0.86, 0.72, accent, r=20)
        _lamp(p, 0.1, 0.72, night)
        _plant(p, 0.9, 0.8)
    elif kind == "bep":
        _room_base(p, wall, floor, 0.68)
        for i in range(12):            # gạch men
            y = 0.44 + (i % 3) * 0.04
            x = (i // 3) * 0.25 + (0.12 if i % 2 else 0)
            p.rect(x, y, x + 0.12, y + 0.04, _shade(wall, 0.94), outline=False)
        _window(p, 0.36, 0.14, 0.64, 0.3, night)
        # tủ lạnh trái, quầy bếp phải
        p.rect(-0.02, 0.36, 0.2, 0.74, (238, 242, 246), r=14)
        p.line([(0.0, 0.5), (0.2, 0.5)])
        p.line([(0.17, 0.4), (0.17, 0.46)], width=8)
        p.line([(0.17, 0.54), (0.17, 0.62)], width=8)
        p.rect(0.78, 0.56, 1.02, 0.76, _shade(accent, 0.95), r=6)
        p.rect(0.76, 0.54, 1.02, 0.57, (220, 210, 196), r=4)
        p.ell(0.82, 0.5, 0.92, 0.545, (80, 80, 92))           # nồi
        for x in (0.72, 0.8, 0.88):                             # chảo treo
            p.line([(x, 0.08), (x, 0.16)], width=4)
            p.ell(x - 0.03, 0.16, x + 0.03, 0.2, (90, 90, 104))
    elif kind == "phong_ngu":
        _room_base(p, wall, floor)
        _window(p, 0.62, 0.16, 0.92, 0.38, night, curtain=accent)
        p.rect(-0.05, 0.56, 0.24, 0.74, (250, 250, 252), r=20)     # giường
        p.rect(-0.05, 0.62, 0.24, 0.74, accent, r=16)
        p.rect(-0.05, 0.44, 0.04, 0.74, (170, 120, 90), r=8)
        p.rect(0.06, 0.18, 0.22, 0.34, _shade(accent, 0.8), r=4)  # áp phích
        p.ell(0.1, 0.22, 0.18, 0.28, (255, 236, 150), outline=False)
        p.rect(0.84, 0.62, 0.98, 0.74, (186, 140, 106), r=6)      # tủ đầu giường
        _lamp(p, 0.91, 0.62, night)
    elif kind == "van_phong":
        _room_base(p, wall, floor, 0.68)
        _window(p, 0.06, 0.12, 0.42, 0.36, night)
        for i in range(8):                                          # rèm sáo
            y = 0.12 + i * 0.03
            p.line([(0.06, y), (0.42, y)], fill=_shade(wall, 0.75), width=3)
        p.ell(0.74, 0.12, 0.88, 0.2, (250, 250, 250))               # đồng hồ
        p.line([(0.81, 0.16), (0.81, 0.135)], width=5)
        p.line([(0.81, 0.16), (0.835, 0.165)], width=5)
        p.rect(0.76, 0.6, 1.04, 0.64, (176, 140, 108), r=4)        # bàn
        p.rect(0.8, 0.64, 0.83, 0.78, (150, 116, 88))
        p.rect(0.8, 0.46, 0.98, 0.58, (60, 66, 80), r=6)            # màn hình
        p.rect(0.815, 0.47, 0.965, 0.565, accent, outline=False)
        p.rect(0.88, 0.58, 0.9, 0.6, (60, 66, 80))
        _plant(p, 0.1, 0.8, 1.2)
    elif kind == "lop_hoc":
        _room_base(p, wall, floor)
        p.rect(0.12, 0.1, 0.88, 0.28, (186, 140, 96), r=8)          # bảng đen
        p.rect(0.14, 0.115, 0.86, 0.265, accent, outline=False)
        p.line([(0.2, 0.16), (0.42, 0.16)], fill=(240, 240, 230), width=4)
        p.line([(0.2, 0.2), (0.36, 0.2)], fill=(240, 240, 230), width=4)
        p.ell(0.62, 0.15, 0.72, 0.22, None, outline=True)
        for x in (0.02, 0.84):                                       # bàn học
            p.rect(x, 0.62, x + 0.16, 0.66, (196, 156, 112), r=4)
            p.line([(x + 0.02, 0.66), (x + 0.02, 0.76)], width=6)
            p.line([(x + 0.14, 0.66), (x + 0.14, 0.76)], width=6)
        p.ell(0.86, 0.32, 0.96, 0.38, (250, 250, 250))
    elif kind == "quan_cafe":
        _room_base(p, wall, floor, 0.66)
        p.rect(0.08, 0.1, 0.4, 0.3, (60, 56, 52), r=8)              # bảng menu
        for i in range(4):
            p.line([(0.12, 0.15 + i * 0.035), (0.34, 0.15 + i * 0.035)], fill=(240, 230, 210), width=4)
        for x in (0.55, 0.72, 0.89):                                 # đèn treo
            p.line([(x, 0.0), (x, 0.1)], width=4)
            p.poly([(x - 0.05, 0.14), (x + 0.05, 0.14), (x + 0.025, 0.1), (x - 0.025, 0.1)], accent)
            if night:
                p.ell(x - 0.03, 0.14, x + 0.03, 0.16, (255, 236, 160), outline=False)
        p.rect(0.76, 0.52, 1.04, 0.74, (150, 104, 72), r=8)         # quầy
        p.rect(0.74, 0.5, 1.04, 0.53, (230, 214, 190), r=4)
        p.rect(0.82, 0.45, 0.86, 0.5, (250, 250, 250), r=4)         # cốc
        p.rect(0.9, 0.44, 0.94, 0.5, accent, r=4)
        p.rect(-0.02, 0.6, 0.16, 0.63, (150, 104, 72), r=4)         # bàn nhỏ
        p.line([(0.07, 0.63), (0.07, 0.76)], width=8)
    elif kind == "cua_hang":
        _room_base(p, wall, floor, 0.7)
        cols = [accent, (96, 168, 112), (238, 198, 86), (84, 124, 200), (238, 164, 188)]
        for x0, x1 in ((-0.02, 0.24), (0.76, 1.02)):                # kệ hàng
            p.rect(x0, 0.2, x1, 0.74, (210, 200, 188), r=6)
            for j in range(4):
                y = 0.26 + j * 0.12
                p.line([(x0, y + 0.08), (x1, y + 0.08)])
                for k in range(4):
                    bx = x0 + 0.02 + k * (x1 - x0 - 0.04) / 4
                    p.rect(bx, y + 0.01, bx + (x1 - x0 - 0.06) / 4, y + 0.08,
                           cols[(j + k) % len(cols)], r=3)
        p.rect(0.32, 0.06, 0.68, 0.12, accent, r=10)                # biển hiệu
        p.line([(0.38, 0.09), (0.62, 0.09)], fill=(255, 255, 255), width=6)
    elif kind == "duong_pho":
        sky = (36, 44, 84) if night else wall
        p.rect(0, 0, 1, 0.7, sky, outline=False)
        if night:
            _stars(p, 0.3, rng)
        else:
            _cloud(p, 0.25, 0.1)
            _cloud(p, 0.75, 0.16, 0.8)
        for x0, x1, top, col in ((-0.02, 0.2, 0.22, accent), (0.2, 0.34, 0.34, _shade(accent, 0.85)),
                                 (0.7, 0.84, 0.3, _shade(accent, 0.9)), (0.84, 1.02, 0.18, _shade(accent, 0.75))):
            p.rect(x0, top, x1, 0.72, col)
            for wy in range(int((0.68 - top) / 0.07)):
                for wx in range(2):
                    xx = x0 + 0.025 + wx * (x1 - x0) / 2
                    yy = top + 0.04 + wy * 0.07
                    lit = (255, 226, 130) if night and rng.random() < 0.6 else (200, 226, 244)
                    p.rect(xx, yy, xx + (x1 - x0) / 2 - 0.05, yy + 0.04, lit, r=3)
        p.rect(0, 0.7, 1, 0.8, (196, 196, 204), outline=False)      # vỉa hè
        p.line([(0, 0.7), (1, 0.7)])
        p.rect(0, 0.8, 1, 1, floor, outline=False)                  # đường
        p.line([(0, 0.8), (1, 0.8)])
        for x in (0.05, 0.3, 0.55, 0.8):
            p.rect(x, 0.89, x + 0.13, 0.905, (250, 250, 250), outline=False)
        p.line([(0.92, 0.79), (0.92, 0.42)], width=8)              # cột đèn
        p.ell(0.89, 0.39, 0.95, 0.43, (255, 230, 150) if night else (240, 240, 240))
    elif kind == "cong_vien":
        sky = (36, 44, 84) if night else wall
        p.rect(0, 0, 1, 0.66, sky, outline=False)
        if night:
            _stars(p, 0.35, rng)
            p.ell(0.72, 0.06, 0.86, 0.13, (250, 240, 190), outline=False)
        else:
            p.ell(0.74, 0.05, 0.9, 0.14, (255, 214, 90), outline=False)
            _cloud(p, 0.25, 0.12)
        p.rect(0, 0.62, 1, 1, floor, outline=False)
        p.d.ellipse([p.X(-0.3), p.Y(0.56), p.X(0.6), p.Y(0.72)], fill=_shade(floor, 0.92))
        p.line([(0, 0.66), (1, 0.66)], fill=_shade(floor, 0.75), width=4)
        p.poly([(0.4, 1.0), (0.6, 1.0), (0.53, 0.66), (0.47, 0.66)], (226, 204, 160), outline=False)
        _tree(p, 0.1, 0.7, 1.3, accent)
        _tree(p, 0.92, 0.68, 1.1, accent)
        p.rect(0.72, 0.66, 0.9, 0.685, (176, 120, 80), r=4)         # ghế đá
        p.rect(0.72, 0.62, 0.9, 0.64, (176, 120, 80), r=4)
        p.line([(0.74, 0.685), (0.74, 0.73)], width=6)
        p.line([(0.88, 0.685), (0.88, 0.73)], width=6)
    elif kind == "bai_bien":
        sky = (40, 52, 100) if night else wall
        p.rect(0, 0, 1, 0.5, sky, outline=False)
        if night:
            _stars(p, 0.3, rng)
            p.ell(0.66, 0.08, 0.8, 0.15, (250, 240, 190), outline=False)
        else:
            p.ell(0.68, 0.06, 0.88, 0.17, (255, 210, 90), outline=False)
            _cloud(p, 0.22, 0.14)
        p.rect(0, 0.5, 1, 0.66, accent if not night else _shade(accent, 0.5), outline=False)
        for i in range(5):
            y = 0.54 + i * 0.025
            p.line([(0.05 + 0.1 * (i % 2), y), (0.25 + 0.1 * (i % 2), y)], fill=(240, 250, 255), width=3)
        p.rect(0, 0.64, 1, 1, floor, outline=False)
        p.d.chord([p.X(-0.1), p.Y(0.6), p.X(1.1), p.Y(0.68)], 0, 180, fill=(240, 250, 255))
        # cây dừa trái, dù phải
        p.line([(0.08, 0.76), (0.12, 0.36)], fill=(160, 112, 72), width=18)
        for ang in (200, 240, 300, 340):
            a = math.radians(ang)
            p.line([(0.12, 0.36), (0.12 + 0.14 * math.cos(a), 0.36 - 0.06 * math.sin(a) + 0.04)],
                   fill=(84, 160, 84), width=16)
        p.line([(0.86, 0.78), (0.86, 0.46)], width=8)
        p.d.pieslice([p.X(0.72), p.Y(0.4), p.X(1.0), p.Y(0.52)], 180, 360,
                     fill=(232, 96, 88), outline=OUT, width=LW)
    else:  # trong — nền sân khấu có tia sáng
        p.rect(0, 0, 1, 1, wall, outline=False)
        cx, cy = 0.5, 0.42
        for i in range(16):
            a0 = 2 * math.pi * i / 16
            a1 = a0 + math.pi / 16
            p.poly([(cx, cy), (cx + 1.5 * math.cos(a0), cy + 1.5 * math.sin(a0) * 0.6),
                    (cx + 1.5 * math.cos(a1), cy + 1.5 * math.sin(a1) * 0.6)],
                   accent if i % 2 else wall, outline=False)
        p.rect(0, 0.72, 1, 1, floor, outline=False)
        p.line([(0, 0.72), (1, 0.72)])


def render_scene(kind: str = "phong_khach", time: str = "ngay",
                 wall=None, floor=None, accent=None, seed: int = 0,
                 size: tuple[int, int] | None = None) -> Image.Image:
    """Vẽ một bối cảnh 9:16. Màu không truyền thì dùng màu mặc định của mẫu."""
    spec = KINDS.get(kind) or KINDS["phong_khach"]
    kind = kind if kind in KINDS else "phong_khach"
    night = time == "dem"
    wall = _rgb(wall, spec["wall"]) if wall is not None else spec["wall"]
    floor = _rgb(floor, spec["floor"]) if floor is not None else spec["floor"]
    accent = _rgb(accent, spec["accent"]) if accent is not None else spec["accent"]
    if night and kind not in ("duong_pho", "cong_vien", "bai_bien"):
        wall, floor = _mix(wall, (40, 44, 80), 0.45), _mix(floor, (30, 30, 50), 0.4)
    w, h = size or (config.WIDTH, config.HEIGHT)
    img = Image.new("RGB", (w, h), wall)
    _draw_kind(_Pen(img), kind, wall, floor, accent, night, random.Random(seed))
    if night:
        # phủ tối nhẹ cho cảnh đêm, giữ đồ vật vẫn rõ
        img = Image.blend(img, Image.new("RGB", (w, h), (20, 24, 60)), 0.18)
    return img


def save_scene(spec: dict, out_path: Path) -> Path:
    """Vẽ theo spec của Claude ({kind, time, wall, floor, accent}) và lưu file."""
    img = render_scene(spec.get("kind", "phong_khach"), spec.get("time", "ngay"),
                       spec.get("wall"), spec.get("floor"), spec.get("accent"),
                       seed=zlib.crc32(str(spec.get("name", "")).encode("utf-8")) % 1000)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path
