# -*- coding: utf-8 -*-
"""Đồ vật đời thường cho bối cảnh: để phòng ốc, phố xá trông như thật.

Vẽ sau phần chính của từng mẫu (core/scene_art._draw_kind): đèn trần, điều
hoà, ổ điện, lịch treo tường, kệ sách, thảm, dép, lò vi sóng, nồi cơm, bảng
ghi chú, máy in, tủ mát, dây điện, xe máy... Mỗi mẫu có bố trí riêng cho
khung dọc và khung ngang (khung dọc hẹp, chỉ thấy ~2,3 m tường) để đồ không
chồng lên nhau; rng (theo tên cảnh) đổi màu sách, đồ trên kệ, có/không vài
món nhỏ nên các tập không giống hệt nhau.

Toạ độ như scene_art._Pen: cm, mốc "l"/"r"/"c", y tính từ chân tường.
"""
from __future__ import annotations

import math

OUT = (52, 46, 58)
BACK = 0.84

BOOK_COLS = [(220, 96, 84), (84, 124, 200), (238, 198, 86), (96, 168, 112),
             (150, 110, 190), (236, 150, 90), (90, 170, 180), (230, 230, 220)]


def _shade(c, k):
    return tuple(max(0, min(255, int(x * k))) for x in c[:3])


def depth(p, f: float) -> tuple[float, float]:
    """(tỉ lệ s, chân y px) cho đồ đứng trên sàn ở độ sâu f (0 = sát tường
    sau, 1 = ngang chỗ nhân vật đứng)."""
    return 1 + f * (1 / BACK - 1), p.base + f * (p.floor - p.base)


# ------------------------------------------------------------------ đồ trên tường / trần

def ceiling_light(p, a, x, night, wide=False):
    top = 260
    w = 70 if wide else 44
    p.rect(a, x - w / 2, top - 8, x + w / 2, top, (246, 246, 240), r=3)
    glow = (255, 236, 160) if night else (255, 252, 236)
    p.ell(a, x - w / 2 + 4, top - 14, x + w / 2 - 4, top - 4, glow)


def ceiling_fan(p, a, x):
    top = 260
    p.line(a, [(x, top), (x, top - 30)], width=max(3, p.L(3)))
    p.ell(a, x - 10, top - 38, x + 10, top - 26, (236, 236, 230))
    p.poly(a, [(x - 10, top - 32), (x - 70, top - 30), (x - 70, top - 36), (x - 10, top - 35)],
           (236, 236, 230))
    p.poly(a, [(x + 10, top - 32), (x + 70, top - 30), (x + 70, top - 36), (x + 10, top - 35)],
           (236, 236, 230))


def ac_unit(p, a, x, y=205, w=82):
    """Điều hoà treo tường (x = mép trái)."""
    p.rect(a, x, y, x + w, y + 28, (248, 248, 246), r=6)
    p.line(a, [(x + 6, y + 8), (x + w - 6, y + 8)], fill=_shade((248, 248, 246), 0.75),
           width=max(2, p.lw // 2))
    p.circle(a, x + w - 10, y + 19, 1.6, (90, 200, 120), outline=False)


def outlet(p, a, x, y=30):
    p.rect(a, x, y, x + 9, y + 12, (246, 244, 236), r=1)
    for dx in (3, 6):
        p.rect(a, x + dx - 0.6, y + 4, x + dx + 0.6, y + 8, OUT, outline=False)


def switch(p, a, x, y=120):
    p.rect(a, x, y, x + 8, y + 12, (246, 244, 236), r=1)
    p.rect(a, x + 2.5, y + 3, x + 5.5, y + 9, (226, 222, 214), r=1)


def calendar(p, a, x, y=140, accent=(220, 80, 70)):
    p.line(a, [(x + 14, y + 40), (x + 14, y + 44)], width=max(2, p.lw // 2))
    p.rect(a, x, y, x + 28, y + 40, (252, 252, 248), r=1)
    p.rect(a, x, y + 30, x + 28, y + 40, accent, outline=False)
    for i in range(3):
        for j in range(4):
            p.rect(a, x + 3 + j * 6, y + 4 + i * 8, x + 7 + j * 6, y + 9 + i * 8,
                   (200, 200, 196), outline=False)


def photos(p, a, x, y, rng, n=3):
    """Cụm khung ảnh gia đình (x = mép trái)."""
    for i in range(n):
        w, h = rng.choice(((22, 28), (28, 22), (18, 24)))
        yy = y + rng.randint(-6, 6)
        col = rng.choice(BOOK_COLS)
        p.rect(a, x, yy, x + w, yy + h, (176, 128, 92), r=1)
        p.rect(a, x + 3, yy + 3, x + w - 3, yy + h - 3, _shade(col, 1.1), outline=False)
        p.circle(a, x + w / 2, yy + h * 0.55, min(w, h) * 0.18, (250, 220, 190), outline=False)
        x += w + 6


def wall_shelf(p, a, x, y, w, rng):
    """Kệ treo tường có sách, chậu cây nhỏ, lọ."""
    p.rect(a, x, y, x + w, y + 4, (176, 128, 92), r=1)
    xx = x + 3
    while xx < x + w - 10:
        kind = rng.random()
        if kind < 0.6:
            bw = rng.choice((4, 5, 6))
            bh = rng.choice((18, 20, 23))
            p.rect(a, xx, y + 4, xx + bw, y + 4 + bh, rng.choice(BOOK_COLS))
            xx += bw
        elif kind < 0.8:
            p.rect(a, xx + 1, y + 4, xx + 11, y + 13, (200, 120, 84), r=2)
            p.ell(a, xx - 1, y + 11, xx + 13, y + 24, (96, 170, 96))
            xx += 14
        else:
            p.rect(a, xx + 1, y + 4, xx + 9, y + 16, (190, 220, 236), r=2)
            xx += 12
        xx += 1


def bookshelf(p, a, x, w, h, rng, color=(176, 128, 92), sf=1.0, base=None):
    """Kệ sách đứng trên sàn (x = mép trái)."""
    kw = {"s": sf, "base": base}
    p.rect(a, x, 0, x + w, h, color, r=2, **kw)
    n = max(3, int(h / 42))
    for j in range(n):
        y0 = 6 + j * (h - 10) / n
        p.rect(a, x + 4, y0, x + w - 4, y0 + (h - 10) / n - 4, _shade(color, 0.7), outline=False, **kw)
        xx = x + 6
        while xx < x + w - 10:
            if rng.random() < 0.12:
                p.rect(a, xx, y0, xx + 12, y0 + 10, (230, 230, 220), r=2, **kw)   # hộp
                xx += 14
                continue
            bw = rng.choice((4, 5, 6, 7))
            bh = (h - 10) / n - 4 - rng.choice((2, 4, 7))
            p.rect(a, xx, y0, xx + bw, y0 + bh, rng.choice(BOOK_COLS), **kw)
            xx += bw + (2 if rng.random() < 0.15 else 0)


def wardrobe(p, a, x, w=100, h=200, color=(214, 186, 150)):
    p.rect(a, x, 0, x + w, h, color, r=3)
    p.line(a, [(x + w / 2, 4), (x + w / 2, h - 4)])
    for dx in (-6, 4):
        p.rect(a, x + w / 2 + dx, h * 0.5 - 8, x + w / 2 + dx + 2, h * 0.5 + 8, OUT, outline=False)
    p.rect(a, x, 0, x + w, 8, _shade(color, 0.8))


def whiteboard(p, a, x, y, w, h, rng):
    p.rect(a, x, y, x + w, y + h, (250, 250, 252), r=2)
    for i in range(3):
        yy = y + h - 12 - i * 12
        p.line(a, [(x + 8, yy), (x + 8 + rng.randint(30, int(w * 0.6)), yy)],
               fill=(70, 110, 200), width=max(2, p.lw // 2))
    # biểu đồ cột nhỏ
    bx = x + w - 46
    for k, hh in enumerate((10, 18, 14, 24)):
        p.rect(a, bx + k * 9, y + 8, bx + k * 9 + 6, y + 8 + hh, (220, 96, 84), outline=False)
    for k in range(rng.randint(2, 4)):                         # giấy nhớ
        nx = x + 10 + k * 16
        p.rect(a, nx, y + 6, nx + 12, y + 18, rng.choice(((250, 230, 110), (250, 170, 190),
                                                            (160, 220, 250))), outline=False)
    p.rect(a, x, y - 3, x + w, y, (180, 184, 190), outline=False)


def corkboard(p, a, x, y, w, h, rng):
    p.rect(a, x, y, x + w, y + h, (196, 150, 104), r=2)
    for _ in range(int(w * h / 500)):
        px = x + 4 + rng.random() * (w - 20)
        py = y + 4 + rng.random() * (h - 20)
        col = rng.choice(((252, 252, 248), (250, 230, 110), (250, 170, 190), (160, 220, 250)))
        p.rect(a, px, py, px + 14, py + 14, col, outline=False)
        p.circle(a, px + 7, py + 12, 1.5, (220, 60, 60), outline=False)


def poster(p, a, x, y, w, h, col):
    p.rect(a, x, y, x + w, y + h, (250, 248, 240), r=1)
    p.rect(a, x + 4, y + h * 0.45, x + w - 4, y + h - 4, col, outline=False)
    for i in range(2):
        p.line(a, [(x + 5, y + 8 + i * 7), (x + w - 8, y + 8 + i * 7)],
               fill=_shade(col, 0.7), width=max(2, p.lw // 2))


# ------------------------------------------------------------------ đồ đứng trên sàn

def side_table_lamp(p, a, x, night):
    p.rect(a, x, 0, x + 40, 50, (186, 140, 106), r=3)
    p.line(a, [(x + 4, 25), (x + 36, 25)])
    p.rect(a, x + 16, 50, x + 24, 72, (90, 90, 100))
    shade = (255, 226, 140) if night else (250, 236, 200)
    p.poly(a, [(x + 8, 70), (x + 32, 70), (x + 27, 92), (x + 13, 92)], shade)


def filing_cabinet(p, a, x, w=46, h=100):
    col = (170, 176, 186)
    p.rect(a, x, 0, x + w, h, col, r=2)
    for j in range(3):
        y0 = 6 + j * (h - 8) / 3
        p.rect(a, x + 4, y0, x + w - 4, y0 + (h - 8) / 3 - 4, _shade(col, 1.06), r=1)
        p.rect(a, x + w / 2 - 6, y0 + (h - 8) / 6 - 2, x + w / 2 + 6, y0 + (h - 8) / 6 + 1, OUT,
               outline=False)


def printer(p, a, x, y):
    p.rect(a, x, y, x + 46, y + 22, (236, 236, 240), r=3)
    p.rect(a, x + 6, y + 22, x + 40, y + 26, (252, 252, 252))
    p.rect(a, x + 6, y + 6, x + 40, y + 9, (60, 60, 70), outline=False)


def trash_bin(p, a, x, sf=1.0, base=None, col=(110, 120, 130)):
    p.poly(a, [(x, 34), (x + 28, 34), (x + 24, 0), (x + 4, 0)], col, s=sf, base=base)
    p.rect(a, x - 2, 32, x + 30, 36, _shade(col, 0.8), s=sf, base=base)


def water_dispenser(p, a, x):
    p.rect(a, x, 0, x + 32, 100, (236, 240, 244), r=3)
    p.rect(a, x + 4, 100, x + 28, 140, (180, 214, 240), r=6)
    for dx, c in ((9, (90, 140, 220)), (21, (220, 90, 80))):
        p.rect(a, x + dx - 2, 72, x + dx + 2, 80, c, outline=False)


def drink_cooler(p, a, x, w, h, rng):
    """Tủ mát cửa kính đầy chai lon."""
    p.rect(a, x, 0, x + w, h, (226, 232, 240), r=3)
    p.rect(a, x + 5, 8, x + w - 5, h - 16, (196, 226, 244), r=2)
    p.rect(a, x, h - 14, x + w, h, (220, 70, 70), r=2)
    rows = int((h - 30) / 30)
    for j in range(rows):
        y0 = 12 + j * 30
        p.line(a, [(x + 5, y0), (x + w - 5, y0)], fill=(160, 170, 180), width=max(2, p.lw // 2))
        xx = x + 8
        while xx < x + w - 14:
            c = rng.choice(((220, 70, 70), (90, 170, 90), (240, 190, 70), (80, 120, 210),
                            (250, 250, 250)))
            p.rect(a, xx, y0 + 1, xx + 7, y0 + 20 + rng.choice((0, 4)), c, r=2)
            xx += 10


def rug(p, f0, f1, half_w, color, pattern=True, cx=0.0):
    """Thảm trên sàn: từ độ sâu f0 tới f1, rộng 2*half_w cm, tâm cx (cm từ giữa)."""
    s0, b0 = depth(p, f0)
    s1, b1 = depth(p, f1)
    pts = [(p.X(cx - half_w, "c", s0), b0), (p.X(cx + half_w, "c", s0), b0),
           (p.X(cx + half_w, "c", s1), b1), (p.X(cx - half_w, "c", s1), b1)]
    p.d.polygon(pts, fill=color, outline=OUT)
    p.d.line(pts + [pts[0]], fill=OUT, width=p.lw)
    if pattern:
        inner = _shade(color, 0.86)
        k = 0.12
        q = [(pts[0][0] + (pts[2][0] - pts[0][0]) * k * 0.6, pts[0][1] + (pts[2][1] - pts[0][1]) * k),
             (pts[1][0] + (pts[3][0] - pts[1][0]) * k * 0.6, pts[1][1] + (pts[3][1] - pts[1][1]) * k),
             (pts[2][0] + (pts[0][0] - pts[2][0]) * k * 0.6, pts[2][1] + (pts[0][1] - pts[2][1]) * k),
             (pts[3][0] + (pts[1][0] - pts[3][0]) * k * 0.6, pts[3][1] + (pts[1][1] - pts[3][1]) * k)]
        p.d.polygon(q, outline=inner, width=max(2, p.lw))


def slippers(p, a, x, f=0.25, col=(236, 120, 140)):
    sf, base = depth(p, f)
    for dx in (0, 14):
        p.ell(a, x + dx, 0, x + dx + 12, 5, col, s=sf, base=base)


def floor_basket(p, a, x, f, col=(196, 150, 98), sf_extra=1.0):
    sf, base = depth(p, f)
    sf *= sf_extra
    p.rect(a, x, 0, x + 36, 30, col, r=4, s=sf, base=base)
    for i in range(1, 3):
        p.line(a, [(x + 3, i * 10), (x + 33, i * 10)], fill=_shade(col, 0.75),
               width=max(2, p.lw // 2), s=sf, base=base)
    p.ell(a, x + 4, 26, x + 32, 40, (236, 236, 230), s=sf, base=base)


# ------------------------------------------------------------------ đồ bếp

def kitchen_extras(p, a, x0, rng, night):
    """Trên quầy bếp 90 cm (x0 = mép trái đoạn quầy còn trống): bếp ga, hút
    mùi, lò vi sóng, nồi cơm, giá bát, ống đũa; móc treo dụng cụ."""
    top = 94
    p.rect(a, x0, 136, x0 + 70, 148, (190, 196, 204), r=2)            # hút mùi (dưới tủ treo)
    p.poly(a, [(x0 + 6, 136), (x0 + 64, 136), (x0 + 56, 128), (x0 + 14, 128)], (210, 214, 220))
    p.rect(a, x0 + 4, top, x0 + 66, top + 4, (60, 60, 68))             # bếp ga
    for dx in (18, 50):
        p.ell(a, x0 + dx - 9, top + 3, x0 + dx + 9, top + 7, (40, 40, 46))
    p.rect(a, x0 + 80, top, x0 + 124, top + 26, (238, 238, 240), r=3)  # lò vi sóng
    p.rect(a, x0 + 84, top + 4, x0 + 110, top + 22, (60, 66, 78), r=2)
    p.circle(a, x0 + 117, top + 15, 2, (120, 200, 140), outline=False)
    p.ell(a, x0 + 132, top, x0 + 156, top + 20, (250, 250, 248))       # nồi cơm điện
    p.rect(a, x0 + 134, top + 16, x0 + 154, top + 22, (220, 90, 80), r=3)
    p.rect(a, x0 + 164, top, x0 + 172, top + 18, (176, 128, 92))       # ống đũa
    for dx in (166, 168, 170):
        p.line(a, [(x0 + dx, top + 18), (x0 + dx, top + 26)], fill=(150, 104, 60),
               width=max(2, p.lw // 2))
    p.line(a, [(x0 + 80, 142), (x0 + 170, 142)], width=max(3, p.L(2)))  # móc treo
    for k, dx in enumerate((88, 110, 132, 154)):
        p.line(a, [(x0 + dx, 142), (x0 + dx, 134)], width=max(2, p.lw // 2))
        if k % 2:
            p.ell(a, x0 + dx - 6, 122, x0 + dx + 6, 134, (150, 156, 166))
        else:
            p.rect(a, x0 + dx - 2, 120, x0 + dx + 2, 134, (176, 128, 92), outline=False)


# ------------------------------------------------------------------ ngoài trời

def power_lines(p, rng, y_top):
    """Dây điện chằng chịt vắt ngang phố (rất quen ở Việt Nam)."""
    for i in range(rng.randint(3, 5)):
        y0 = y_top + i * p.L(9) + rng.randint(-6, 6)
        sag = p.L(rng.randint(10, 28))
        pts = [(x, y0 + sag * math.sin(math.pi * x / p.w)) for x in range(0, p.w + 20, 20)]
        p.d.line(pts, fill=(40, 40, 46), width=max(2, int(2.5 * p.u)))


def motorbike(p, a, x, sf, base, col):
    """Xe tay ga dựng trên vỉa hè (x = mép trái, dài ~130 cm)."""
    k = {"s": sf, "base": base}
    dark = (44, 44, 50)
    p.poly(a, [(x + 8, 34), (x + 22, 22), (x + 62, 22), (x + 70, 40), (x + 66, 56),
               (x + 24, 58), (x + 8, 48)], col, **k)                          # thân sau
    p.rect(a, x + 60, 20, x + 96, 28, _shade(col, 0.8), **k)                 # sàn để chân
    p.poly(a, [(x + 92, 22), (x + 108, 22), (x + 116, 78), (x + 102, 82)], col, **k)  # yếm
    p.rect(a, x + 20, 56, x + 66, 64, dark, r=4, **k)                        # yên
    p.line(a, [(x + 104, 82), (x + 106, 92)], width=max(3, p.L(3, sf)), **k)
    p.line(a, [(x + 96, 92), (x + 122, 92)], width=max(3, p.L(3, sf)), **k)  # tay lái
    p.ell(a, x + 106, 68, x + 120, 80, (255, 240, 180), **k)                 # đèn
    for wx in (x + 26, x + 106):
        p.circle(a, wx, 15, 15, dark, **k)
        p.circle(a, wx, 15, 6, (190, 190, 196), **k)


def facade_ac(p, a, x, y, sf, base):
    p.rect(a, x, y, x + 70, y + 46, (236, 236, 232), r=3, s=sf, base=base)
    p.circle(a, x + 46, y + 23, 16, (200, 200, 196), s=sf, base=base)


def sign_board(p, a, x, y, w, h, col, sf, base):
    p.rect(a, x, y, x + w, y + h, col, r=3, s=sf, base=base)
    for i in range(2):
        p.line(a, [(x + w * 0.12, y + h * (0.35 + i * 0.3)), (x + w * (0.88 - i * 0.2),
                                                           y + h * (0.35 + i * 0.3))],
               fill=(255, 255, 255), width=max(3, p.L(5, sf)), s=sf, base=base)


def lamp_post(p, a, x, sf=1.0, base=None, night=False):
    k = {"s": sf, "base": base}
    p.line(a, [(x, 0), (x, 360)], width=max(4, p.L(7, sf)), **k)
    p.ell(a, x - 18, 352, x + 18, 386, (255, 236, 160) if night else (246, 246, 240), **k)


def bush(p, a, x, w, sf=1.0, base=None, col=(96, 160, 90)):
    k = {"s": sf, "base": base}
    n = max(2, int(w / 40))
    for i in range(n):
        cx = x + (i + 0.5) * w / n
        p.ell(a, cx - 30, 0, cx + 30, 46 + (i % 2) * 10, col, **k)
    for i in range(n):
        cx = x + (i + 0.5) * w / n
        p.circle(a, cx, 30, 4, (240, 120, 150), outline=False, **k)


def fence(p, a, x0, x1, sf, base, col=(236, 236, 230)):
    k = {"s": sf, "base": base}
    p.rect(a, x0, 40, x1, 46, col, **k)
    p.rect(a, x0, 18, x1, 24, col, **k)
    xx = x0
    while xx <= x1:
        p.rect(a, xx, 0, xx + 5, 56, col, **k)
        xx += 26


def beach_chair(p, a, x, sf, base, col):
    k = {"s": sf, "base": base}
    p.poly(a, [(x, 20), (x + 90, 20), (x + 120, 70), (x + 108, 74), (x + 82, 30), (x, 30)], col, **k)
    for dx in (6, 80):
        p.rect(a, x + dx, 0, x + dx + 4, 20, (176, 128, 84), **k)


def ball(p, a, x, sf, base):
    k = {"s": sf, "base": base}
    p.circle(a, x, 14, 14, (250, 250, 250), **k)
    p.poly(a, [(x - 13, 14), (x, 27), (x, 1)], (230, 80, 80), outline=False, **k)
    p.circle(a, x, 14, 14, None, **k)


def boat(p, a, x, sf, base):
    k = {"s": sf, "base": base}
    p.poly(a, [(x, 20), (x + 120, 20), (x + 100, 0), (x + 16, 0)], (236, 236, 230), **k)
    p.line(a, [(x + 60, 20), (x + 60, 110)], width=max(2, p.L(3, sf)), **k)
    p.poly(a, [(x + 62, 108), (x + 62, 30), (x + 110, 30)], (250, 250, 250), **k)


def gulls(p, rng, y1):
    for _ in range(rng.randint(2, 4)):
        x, y = rng.random() * p.w, rng.random() * y1 * 0.6 + y1 * 0.1
        r = 14 * p.u
        p.d.arc([x - r, y - r / 2, x, y + r / 2], 200, 340, fill=OUT, width=max(2, int(3 * p.u)))
        p.d.arc([x, y - r / 2, x + r, y + r / 2], 200, 340, fill=OUT, width=max(2, int(3 * p.u)))


# ------------------------------------------------------------------ theo từng mẫu

def decorate(p, kind: str, wall, floor, accent, night: bool, rng) -> None:
    """Thêm đồ đời thường cho mẫu bối cảnh `kind` (sau phần vẽ chính)."""
    land = p.w > p.h
    fn = _KINDS.get(kind)
    if fn:
        fn(p, land, wall, floor, accent, night, rng)


def _living(p, land, wall, floor, accent, night, rng):
    ceiling_light(p, "c", 0, night, wide=True)
    rug(p, 0.3, 2.4, 120 if land else 95, _shade(accent, 1.05) if rng.random() < 0.5
        else (214, 120, 96))
    outlet(p, "l", 186)
    switch(p, "r", -16)
    slippers(p, "l", 26, 0.3, rng.choice(((236, 120, 140), (110, 160, 220))))
    if land:
        ac_unit(p, "l", 331, 212)
        photos(p, "l", 341, 112, rng)
        side_table_lamp(p, "l", 236, night)
        wall_shelf(p, "l", 462, 150, 70, rng)
    else:
        ac_unit(p, "r", -96, 222, 78)
        photos(p, "r", -54, 160, rng, n=1)


def _kitchen(p, land, wall, floor, accent, night, rng):
    ceiling_light(p, "c", 0, night)
    if land:
        kitchen_extras(p, "r", -250, rng, night)
        calendar(p, "l", 120, 140, accent=(220, 80, 70))
        trash_bin(p, "l", 90)
    else:
        kitchen_extras(p, "r", -184, rng, night)
        trash_bin(p, "l", 84)
    p.ell("r", -40, 94, -8, 104, (236, 180, 90))                       # đĩa hoa quả
    rug(p, 0.6, 1.6, 60, (120, 150, 196), pattern=False, cx=-40 if land else 0)
    outlet(p, "l", 76, 110)


def _bedroom(p, land, wall, floor, accent, night, rng):
    ceiling_light(p, "c", 0, night)
    rug(p, 0.6, 2.4, 85, _shade(accent, 1.08), cx=20)
    slippers(p, "l", 200 if land else 120, 0.45, (250, 250, 250))
    if land:
        wardrobe(p, "r", -260, 100, 200)
        ac_unit(p, "c", -40, 214)
        wall_shelf(p, "l", 124, 150, 84, rng)
        floor_basket(p, "r", -130, 0.15)
        p.circle("l", 238, 176, 12, (250, 250, 250))                    # đồng hồ
    else:
        ac_unit(p, "r", -84, 226, 70)
        wall_shelf(p, "r", -150, 120, 60, rng)
    outlet(p, "l", 270 if land else 214, 70)


def _office(p, land, wall, floor, accent, night, rng):
    for x in ((-150, 0, 150) if land else (-60, 60)):
        p.rect("c", x - 45, 252, x + 45, 260, (250, 250, 246), r=1)      # đèn tuýp
    if land:
        whiteboard(p, "l", 345, 145, 150, 70, rng)
        printer(p, "l", 343, 76)
        corkboard(p, "l", 196, 140, 52, 56, rng)
        ac_unit(p, "r", -84, 222, 78)
        trash_bin(p, "l", 322)
    else:
        trash_bin(p, "l", 190)
        poster(p, "r", -50, 150, 34, 46, accent)
        calendar(p, "r", -46, 96, accent=(220, 80, 70))
    outlet(p, "l", 186, 30)
    rug(p, 0.8, 2.2, 75, (110, 120, 140), pattern=False)


def _classroom(p, land, wall, floor, accent, night, rng):
    for x in ((-140, 140) if land else (0,)):
        ceiling_fan(p, "c", x)
    if land:
        corkboard(p, "r", -100, 140, 80, 64, rng)
        trash_bin(p, "l", 240)
        p.line("l", [(274, 0), (290, 86)], fill=(176, 128, 84), width=max(3, p.L(3)))  # chổi
        p.poly("l", [(268, 0), (282, 0), (276, 14)], (220, 190, 120))
        bookshelf(p, "l", 122, 66, 84, rng)
    else:
        trash_bin(p, "r", -40)
    outlet(p, "l", 120, 30)


def _cafe(p, land, wall, floor, accent, night, rng):
    if land:
        wall_shelf(p, "r", -110, 168, 100, rng)
        wall_shelf(p, "r", -110, 200, 100, rng)
        poster(p, "l", 300, 140, 46, 60, accent)
    # dây đèn trang trí dọc trần
    y = p.Y(246)
    pts = [(x, y + 10 * p.u * math.sin(x / (60 * p.u))) for x in range(0, p.w + 20, 20)]
    p.d.line(pts, fill=(60, 56, 52), width=max(2, int(2 * p.u)))
    for i, (x, yy) in enumerate(pts[::3]):
        c = (255, 226, 130) if night or i % 2 else (250, 250, 240)
        p.d.ellipse([x - 5 * p.u, yy, x + 5 * p.u, yy + 12 * p.u], fill=c, outline=OUT)
    rug(p, 0.8, 2.2, 75, (150, 104, 72), pattern=False)


def _shop(p, land, wall, floor, accent, night, rng):
    for x in ((-150, 0, 150) if land else (-60, 60)):
        p.rect("c", x - 45, 252, x + 45, 260, (250, 250, 246), r=1)
    if land:
        drink_cooler(p, "c", -60, 120, 190, rng)
        poster(p, "c", 80, 150, 50, 50, (232, 96, 88))
        floor_basket(p, "c", 70, 0.4, col=(220, 80, 80))
    else:
        floor_basket(p, "l", 8, 0.5, col=(220, 80, 80))


def _street(p, land, wall, floor, accent, night, rng):
    bs, bb = 0.55, p.base - p.L(35)
    power_lines(p, rng, int(p.h * 0.16))
    span = p.span_cm(bs)
    x = 60.0
    while x < span - 80:
        facade_ac(p, "l", x, 480 + rng.choice((0, 300)), bs, bb)
        x += rng.choice((380, 520, 640))
    x = 20.0
    while x < span - 100:
        sign_board(p, "l", x + 30, 300, rng.choice((180, 240)), 60,
                   rng.choice(((220, 60, 60), (60, 120, 200), (240, 190, 60), (60, 160, 100))),
                   bs, bb)
        x += rng.choice((360, 420))
    # xe máy dựng trên vỉa hè
    sf, base = 0.82, bb + (p.floor - bb) * 0.25
    cols = [(220, 60, 60), (60, 60, 70), (240, 240, 240), (60, 120, 200)]
    n = 2 if land else 1
    picks = rng.sample(cols, n)
    for i in range(n):
        motorbike(p, "l", 140 + i * 170 if land else 90, sf, base, picks[i])
    if land:
        bush(p, "r", -200, 100, sf, base)


def _park(p, land, wall, floor, accent, night, rng):
    far = p.base - p.L(40)
    sf, base = 0.7, far + (p.floor - far) * 0.15
    fence(p, "l", 0, p.span_cm(sf) + 10, sf, base)
    lamp_post(p, "l", 160 if land else 16, 0.9, far + (p.floor - far) * 0.35, night)
    bush(p, "c", -60, 120, 0.85, far + (p.floor - far) * 0.3)
    trash_bin(p, "r", -100 if land else -60, 0.95, far + (p.floor - far) * 0.4, (90, 140, 110))
    gulls(p, rng, far * 0.6)


def _beach(p, land, wall, floor, accent, night, rng):
    gulls(p, rng, p.eye)
    sea_y = p.eye + (p.base - p.eye) * 0.4
    boat(p, "c", 60 if land else 20, 0.35, sea_y)
    sf, base = 1.0, p.base + (p.floor - p.base) * 0.3
    beach_chair(p, "l", 30 if land else 10, sf, base, (90, 170, 220))
    if land:
        beach_chair(p, "c", 40, sf, base, (240, 190, 70))
    ball(p, "r", -60, 1.05, p.base + (p.floor - p.base) * 0.55)
    p.rect("l", 140 if land else 120, 0, 190 if land else 160, 4, (230, 80, 90),
           s=1.05, base=p.base + (p.floor - p.base) * 0.6)                 # khăn tắm


_KINDS = {
    "phong_khach": _living, "bep": _kitchen, "phong_ngu": _bedroom, "van_phong": _office,
    "lop_hoc": _classroom, "quan_cafe": _cafe, "cua_hang": _shop, "duong_pho": _street,
    "cong_vien": _park, "bai_bien": _beach,
}
