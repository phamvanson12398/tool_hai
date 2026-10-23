# -*- coding: utf-8 -*-
"""Bối cảnh làng quê Việt Nam xưa cho Truyện kể (Lão Hạc, Tắt đèn, Vợ nhặt...):
nhà tranh, nhà ngói, sân nhà quê, đường làng, cánh đồng lúa.

Vẽ bằng bút _Pen của scene_art (đơn vị cm, x theo mép trái/phải/giữa).
"""
from __future__ import annotations

import math

from . import scene_art as sa

OUT = sa.OUT

KINDS = {
    "nha_tranh": {"label": "Nhà tranh (bên trong)", "wall": (200, 172, 128),
                  "floor": (168, 138, 102), "accent": (122, 92, 62)},
    "nha_ngoi": {"label": "Nhà ngói xưa (bên trong)", "wall": (228, 208, 164),
                 "floor": (182, 120, 96), "accent": (92, 70, 60)},
    "san_que": {"label": "Sân nhà quê", "wall": (176, 214, 236),
                "floor": (196, 170, 122), "accent": (96, 150, 80)},
    "duong_lang": {"label": "Đường làng", "wall": (178, 216, 236),
                   "floor": (126, 170, 96), "accent": (84, 140, 76)},
    "canh_dong": {"label": "Cánh đồng lúa", "wall": (180, 218, 240),
                  "floor": (150, 190, 92), "accent": (110, 160, 70)},
}

STRAW = (204, 170, 104)
WOOD = (132, 94, 64)
BAMBOO = (176, 168, 98)


def _thatch_band(p, y0, y1, rng):
    """Mái rạ nhìn từ dưới lên (trần nhà tranh)."""
    p.band(y0, y1, sa._shade(STRAW, 0.82))
    for _ in range(int(p.w / (6 * p.u))):
        x = rng.random() * p.w
        p.d.line([(x, y0), (x + rng.uniform(-14, 14) * p.u, y1)],
                 fill=sa._shade(STRAW, rng.uniform(0.62, 0.95)), width=max(2, int(2 * p.u)))
    p.hline(y1)


def _post(p, a, x, top=260):
    p.rect(a, x - 8, 0, x + 8, top, WOOD)


def _bar_window(p, a, x, w=90, sill=100, hgt=70, night=False, s=1.0, base=None):
    sky = (34, 40, 70) if night else (176, 214, 226)
    kw = {"s": s, "base": base}
    p.rect(a, x - 6, sill - 6, x + w + 6, sill + hgt + 6, WOOD, **kw)
    p.rect(a, x, sill, x + w, sill + hgt, sky, **kw)
    for k in range(1, 5):
        xx = x + w * k / 5
        p.rect(a, xx - 2.5, sill, xx + 2.5, sill + hgt, sa._shade(WOOD, 0.9), outline=False, **kw)
        p.line(a, [(xx - 2.5, sill), (xx - 2.5, sill + hgt)], width=max(2, p.lw // 2), **kw)


def _jar(p, a, x, s=1.0, color=(120, 84, 60)):
    """Chum nước, x = tâm."""
    p.ell(a, x - 34, 0, x + 34, 62, color, s=s)
    p.ell(a, x - 22, 54, x + 22, 66, sa._shade(color, 0.7), s=s)
    p.line(a, [(x - 26, 36), (x + 26, 36)], fill=sa._shade(color, 0.75),
           width=max(2, p.lw // 2), s=s)


def _pot(p, a, x, s=1.0, color=(150, 96, 70)):
    p.ell(a, x - 16, 0, x + 16, 26, color, s=s)
    p.rect(a, x - 10, 22, x + 10, 30, sa._shade(color, 0.8), s=s)


def _bamboo_bed(p, a, x, w=200, hgt=45):
    """Chõng tre / phản, x = mép trái."""
    p.rect(a, x, hgt - 8, x + w, hgt, BAMBOO)
    n = int(w / 14)
    for k in range(1, n):
        xx = x + w * k / n
        p.line(a, [(xx, hgt - 8), (xx, hgt)], fill=sa._shade(BAMBOO, 0.7),
               width=max(1, p.lw // 3))
    for xx in (x + 6, x + w - 14):
        p.rect(a, xx, 0, xx + 8, hgt - 8, sa._shade(BAMBOO, 0.8))
    p.line(a, [(x + 6, 14), (x + w - 6, 14)], fill=sa._shade(BAMBOO, 0.75), width=max(2, p.lw // 2))


def _chest(p, a, x, w=80, color=(110, 74, 50)):
    p.rect(a, x, 0, x + w, 50, color, r=3)
    p.rect(a, x - 3, 44, x + w + 3, 54, sa._shade(color, 1.12), r=2)
    p.rect(a, x + w / 2 - 6, 28, x + w / 2 + 6, 40, (210, 176, 96), outline=False)


def _oil_lamp(p, a, x, y, night):
    p.rect(a, x - 9, y, x + 9, y + 14, (200, 200, 190), r=4)
    p.rect(a, x - 5, y + 14, x + 5, y + 30, (230, 236, 236), r=3)
    if night:
        p.ell(a, x - 24, y + 14, x + 24, y + 62, (255, 230, 150), outline=False)
        p.ell(a, x - 4, y + 28, x + 4, y + 42, (255, 190, 80), outline=False)


def _basket(p, a, x, y, r=22):
    p.ell(a, x - r, y - r * 0.5, x + r, y + r * 0.5, (190, 156, 96))
    p.line(a, [(x - r * 0.8, y), (x + r * 0.8, y)], fill=(150, 116, 70), width=max(1, p.lw // 3))


def _banana(p, a, x, s=1.0, base=None, hgt=300):
    k = hgt / 300
    p.rect(a, x - 9 * k, 0, x + 9 * k, 200 * k, (150, 168, 96), s=s, base=base)
    leaf = (96, 160, 80)
    for ang, ln in ((150, 150), (200, 160), (110, 140), (250, 150), (60, 130), (20, 150)):
        t = math.radians(ang)
        tip = (x + ln * k * math.cos(t), 200 * k + ln * k * 0.55 * math.sin(t) + 40 * k)
        mid = (x + ln * k * 0.5 * math.cos(t), 200 * k + 60 * k)
        w = 22 * k
        p.poly(a, [(x, 200 * k), (mid[0], mid[1] + w), tip, (mid[0], mid[1] - w * 0.4)],
               leaf, s=s, base=base)
        p.line(a, [(x, 200 * k), mid, tip], fill=sa._shade(leaf, 0.75),
               width=max(1, p.lw // 3), s=s, base=base)


def _bamboo_clump(p, a, x, s=1.0, base=None, hgt=600, rng=None):
    k = hgt / 600
    green = (92, 150, 82)
    for j in range(5):
        dx = (j - 2) * 22 * k
        top = hgt * (0.8 + 0.2 * ((j * 37) % 5) / 4)
        p.line(a, [(x + dx, 0), (x + dx * 1.6, top)], fill=(110, 130, 70),
               width=max(2, p.L(6 * k, s)), s=s, base=base)
    for j in range(7):
        cx = x + (j - 3) * 45 * k
        cy = hgt * (0.55 + 0.35 * ((j * 53) % 7) / 6)
        r = (90 + 25 * (j % 3)) * k
        p.ell(a, cx - r, cy - r * 0.7, cx + r, cy + r * 0.7,
              sa._shade(green, 0.85 + 0.08 * (j % 3)), s=s, base=base)


def _fence(p, a, x0, x1, s=1.0, base=None, hgt=110):
    for y in (hgt * 0.35, hgt * 0.78):
        p.rect(a, x0, y - 3, x1, y + 3, sa._shade(BAMBOO, 0.85), s=s, base=base)
    x = x0
    while x < x1:
        p.rect(a, x, 0, x + 6, hgt + (8 if int(x / 14) % 2 else 0), BAMBOO, s=s, base=base)
        x += 14


def _hut_outside(p, a, x, w=420, s=1.0, base=None, night=False):
    """Nhà tranh nhìn từ sân, x = mép trái."""
    wall = (196, 168, 122)
    p.rect(a, x, 0, x + w, 210, wall, s=s, base=base)
    p.rect(a, x + w * 0.42, 0, x + w * 0.42 + 90, 180,
           (60, 46, 38) if not night else (230, 190, 110), s=s, base=base)
    _bar_window(p, a, x + 40, 80, 90, 60, night, s=s, base=base)
    p.poly(a, [(x - 40, 200), (x + w + 40, 200), (x + w - 30, 330), (x + 30, 330)],
           STRAW, s=s, base=base)
    for k in range(9):
        yy = 210 + k * 14
        p.line(a, [(x - 30 + k * 7, yy), (x + w + 30 - k * 7, yy)],
               fill=sa._shade(STRAW, 0.78), width=max(1, p.lw // 3), s=s, base=base)


def _haystack(p, a, x, s=1.0, base=None):
    p.ell(a, x - 90, 0, x + 90, 135, (214, 180, 100), s=s, base=base)
    p.rect(a, x - 4, 140, x + 4, 190, WOOD, s=s, base=base)
    for k in range(5):
        p.line(a, [(x - 50 + k * 25, 20), (x - 40 + k * 22, 120)], fill=(176, 140, 70),
               width=max(1, p.lw // 3), s=s, base=base)


def _hut_far(p, a, x, s, base):
    p.rect(a, x, 0, x + 260, 170, (190, 160, 118), s=s, base=base)
    p.poly(a, [(x - 30, 160), (x + 290, 160), (x + 220, 280), (x + 40, 280)], STRAW,
           s=s, base=base)
    p.rect(a, x + 100, 0, x + 160, 130, (70, 54, 44), s=s, base=base)


def draw(p, kind, wall, floor, accent, night, rng):
    if kind == "nha_tranh":
        sa._room_base(p, wall, floor, boards=False)
        top = p.Y(sa.WALL_CM)
        _thatch_band(p, 0, max(top, p.h * 0.08), rng)
        for _ in range(int(p.w / (30 * p.u))):                  # đất nện lốm đốm
            x, y = rng.random() * p.w, p.base + rng.random() * (p.h - p.base)
            r = rng.uniform(2, 5) * p.u
            p.d.ellipse([x - r, y - r * 0.5, x + r, y + r * 0.5], fill=sa._shade(floor, 0.88))
        _post(p, "l", 40)
        _post(p, "r", -40)
        p.rect("l", 70, 0, 160, 170, (250, 232, 180) if not night else (40, 36, 52))  # cửa thấp
        for k in range(8):                                       # mành tre
            yy = 170 - k * 12
            p.line("l", [(70, yy), (160, yy)], fill=BAMBOO, width=max(2, p.lw // 2))
        _bar_window(p, "c", -45, 90, 110, 70, night)
        _jar(p, "l", 215)
        _pot(p, "l", 272)
        _bamboo_bed(p, "r", -280, 220)
        if p.w > p.h:
            _chest(p, "c", -230)
        p.rect("c", 80, 150, 180, 158, WOOD)                     # giá gỗ trên tường
        _oil_lamp(p, "c", 110, 158, night)
        _basket(p, "c", 155, 172, 18)
        _basket(p, "r", -90, 190)
    elif kind == "nha_ngoi":
        sa._room_base(p, wall, floor, boards=False)
        tile = sa._shade(floor, 0.85)                           # gạch bát
        y, gap = p.base, (p.h - p.base) * 0.16
        while y < p.h:
            p.hline(y, fill=tile, width=max(1, p.lw // 3))
            y += gap
            gap *= 1.3
        vx = p.w / 2
        for i in range(-8, 9):
            x0 = vx + i * p.L(60)
            p.d.line([(x0, p.base), (vx + (x0 - vx) * 1.9, p.h)], fill=tile, width=max(1, p.lw // 3))
        p.band(0, max(0, p.Y(sa.WALL_CM)), sa._shade(WOOD, 0.95))   # xà gỗ
        _bar_window(p, "c", -15, 120, 110, 80, night)
        # bàn thờ treo + ảnh, bát hương
        p.rect("l", 40, 150, 170, 158, WOOD)
        p.rect("l", 80, 158, 130, 210, (236, 226, 200))
        p.rect("l", 86, 164, 124, 204, (150, 140, 128), outline=False)
        p.rect("l", 50, 158, 72, 172, (190, 150, 80), r=4)
        for xx in (56, 61, 66):
            p.line("l", [(xx, 172), (xx, 190)], fill=(170, 60, 50), width=max(1, p.lw // 3))
        # kệ sách
        p.rect("l", 190, 0, 270, 150, sa._shade(WOOD, 1.05))
        cols = [(150, 70, 60), (90, 110, 150), (110, 130, 80), (180, 150, 90), (120, 90, 130)]
        for j in range(3):
            yy = 10 + j * 48
            p.line("l", [(190, yy), (270, yy)])
            for k in range(5):
                bx = 196 + k * 14
                p.rect("l", bx, yy + 2, bx + 11, yy + 36 - (k % 2) * 6, cols[(j + k) % 5], r=1)
        # bàn gỗ thấp + ấm chén
        p.rect("c", -10, 50, 115, 58, (160, 116, 76))
        for xx in (-2, 103):
            p.rect("c", xx, 0, xx + 6, 50, sa._shade((160, 116, 76), 0.8))
        p.ell("c", 20, 58, 56, 84, (236, 232, 220))
        p.line("c", [(56, 74), (66, 82)], width=max(2, p.lw // 2))
        for xx in (72, 88):
            p.rect("c", xx, 58, xx + 10, 68, (236, 232, 220), r=2)
        # tủ gỗ tối
        dark = (92, 70, 64)
        p.rect("r", -150, 0, -10, 200, dark, r=2)
        p.line("r", [(-80, 10), (-80, 196)])
        p.line("r", [(-150, 100), (-10, 100)])
        for xx in (-90, -70):
            p.circle("r", xx, 150, 3, (200, 170, 90), outline=False)
    elif kind == "san_que":
        far = p.base - p.L(30)
        sa._sky(p, (34, 42, 80) if night else wall, night, rng, far)
        p.band(far, p.h, floor)
        bs = 0.6
        span = p.span_cm(bs)
        _bamboo_clump(p, "l", span * 0.15, s=0.4, base=far, hgt=700)
        _bamboo_clump(p, "l", span * 0.75, s=0.4, base=far, hgt=650)
        _fence(p, "l", -10, span + 10, s=bs, base=far)
        p.d.line([(0, far), (p.w, far)], fill=sa._shade(floor, 0.8), width=max(2, p.lw // 2))
        _hut_outside(p, "r", -640, 480, s=0.55, base=far, night=night)
        _banana(p, "l", 70, hgt=320)
        if p.w > p.h:
            _haystack(p, "l", 230, s=0.7, base=far)
        for _ in range(int(p.w / (60 * p.u))):
            x, y = rng.random() * p.w, far + rng.random() * (p.h - far)
            r = rng.uniform(2, 4) * p.u
            p.d.ellipse([x - r, y - r * 0.6, x + r, y + r * 0.6], fill=sa._shade(floor, 0.85))
    elif kind == "duong_lang":
        far = p.base - p.L(45)
        sa._sky(p, (34, 42, 80) if night else wall, night, rng, far)
        p.band(far, p.h, floor)
        span = p.span_cm(0.35)
        x = -100.0
        while x < span + 100:                                   # luỹ tre xa
            _bamboo_clump(p, "l", x, s=0.35, base=far, hgt=rng.choice((550, 650, 750)))
            x += rng.choice((260, 320, 380))
        _hut_far(p, "l", span * 0.55, 0.35, far)
        p.d.line([(0, far), (p.w, far)], fill=sa._shade(floor, 0.75), width=max(2, p.lw // 2))
        vx = p.w / 2
        road = (206, 178, 130)
        p.d.polygon([(vx - p.L(40), far), (vx + p.L(40), far),
                     (vx + p.L(240), p.h), (vx - p.L(240), p.h)], fill=road)
        for _ in range(int(p.w / (40 * p.u))):
            yy = far + rng.random() * (p.h - far)
            k = (yy - far) / max(1, p.h - far)
            xx = vx + rng.uniform(-1, 1) * (p.L(40) + k * p.L(200))
            r = rng.uniform(2, 4) * p.u
            p.d.ellipse([xx - r, yy - r * 0.5, xx + r, yy + r * 0.5], fill=sa._shade(road, 0.85))
        # cây đa đầu làng
        p.rect("l", 30, 0, 70, 260, (120, 90, 64))
        for dx, dy, r in ((50, 380, 170), (-60, 320, 120), (160, 320, 120), (50, 290, 140)):
            p.ell("l", dx - r, dy - r * 0.6, dx + r, dy + r * 0.6, sa._shade(accent, 0.95))
        _bamboo_clump(p, "r", -90, hgt=520)
    elif kind == "canh_dong":
        far = p.eye + p.L(30)
        sa._sky(p, (34, 42, 80) if night else wall, night, rng, far)
        # núi xa mờ
        pts = [(0, far)]
        for k in range(9):
            pts.append((p.w * k / 8, far - p.L(rng.uniform(40, 110))))
        pts.append((p.w, far))
        p.d.polygon(pts, fill=sa._mix(wall, (120, 150, 170), 0.35))
        span = p.span_cm(0.3)
        x = -50.0
        while x < span:
            _bamboo_clump(p, "l", x, s=0.25, base=far, hgt=600)
            x += rng.choice((300, 420, 520))
        p.band(far, p.h, floor)
        rows = sa._shade(floor, 0.82)
        y, gap = far, p.L(6)
        while y < p.h:
            p.hline(y, fill=rows, width=max(1, int(gap * 0.25)))
            y += gap
            gap *= 1.18
        # khóm lúa theo hàng: xa nhỏ, gần to (ruộng có lúa thì gặt mới hợp)
        rice = (96, 140, 52) if not night else (56, 82, 52)
        rice2 = (206, 180, 78) if not night else (110, 100, 60)          # bông lúa chín
        y, gap = far + p.L(4), p.L(7)
        while y < p.h:
            k = (y - far) / max(1, p.h - far)
            hgt = p.L(8 + 34 * k)
            step = p.L(10 + 28 * k)
            xx = rng.uniform(0, step)
            while xx < p.w:
                lo = p.w * 0.55 + (p.w * 0.17) * k - hgt * 0.3
                hi = p.w * 0.6 + (p.w * 0.35) * k + hgt * 0.3
                if not lo < xx < hi:                       # chừa bờ ruộng
                    wdt = max(2, int(p.lw * (0.5 + 0.9 * k)))
                    for dx in (-0.35, -0.12, 0.1, 0.32):
                        tip = (xx + dx * hgt + rng.uniform(-0.05, 0.05) * hgt, y - hgt * rng.uniform(0.8, 1.0))
                        p.d.line([(xx, y), tip], fill=rice if dx < 0.2 else rice2, width=wdt)
                xx += step * rng.uniform(0.85, 1.15)
            y += gap
            gap *= 1.22
        # bờ ruộng chéo
        p.d.polygon([(p.w * 0.55, far), (p.w * 0.6, far), (p.w * 0.95, p.h), (p.w * 0.72, p.h)],
                    fill=(170, 150, 104))
        p.d.line([(p.w * 0.55, far), (p.w * 0.72, p.h)], fill=OUT, width=max(2, p.lw // 2))
        p.d.line([(p.w * 0.6, far), (p.w * 0.95, p.h)], fill=OUT, width=max(2, p.lw // 2))
        _hut_far(p, "l", span * 0.2, 0.3, far)
