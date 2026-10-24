# -*- coding: utf-8 -*-
"""Nhân vật kiểu webtoon Hàn "người thật" (như các kênh kể chuyện 썰 trên
YouTube / TikTok): người lớn tỉ lệ thật, nét đen mảnh đều, màu phẳng, mắt
tròng trắng chấm đen, mũi hai nét, lông mày đen dày.

Vẽ bằng code từng khung hình nên mọi thứ cử động được: miệng mở theo giọng
(0..1), chớp mắt, đầu nghiêng / quay sang, thân thở, tay đổi tư thế (cầm điện
thoại áp tai, cầm xem, ôm đầu...), nét mặt đổi theo câu.

Toạ độ: đơn vị là chiều cao đầu (u). Nhân vật đứng: chân ở y = 0, đỉnh đầu ở
y ≈ -7. Tâm đầu ở HEAD_C. Màn hình: px = gốc + u * s (s = px / u), nét vẽ dày
cố định theo khung hình (không to ra khi máy quay phóng vào).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw

INK = (28, 26, 30, 255)
SS = 2                      # vẽ to gấp đôi rồi thu nhỏ cho nét mịn

# ---------------------------------------------------------------- bảng màu
SKIN = {"light": (252, 232, 214), "fair": (248, 224, 202), "tan": (230, 192, 158),
        "dark": (182, 136, 104)}
HAIR = {"black": (42, 42, 46), "brown": (92, 62, 44), "gray": (150, 150, 152),
        "white": (226, 224, 220), "blonde": (214, 178, 102), "red": (146, 62, 44)}
CLOTH = {"beige": (172, 150, 124), "brown": (128, 96, 72), "gray": (140, 142, 148),
         "navy": (52, 64, 98), "black": (48, 48, 54), "white": (238, 236, 232),
         "yellow": (228, 190, 64), "red": (186, 64, 60), "green": (88, 132, 92),
         "blue": (84, 124, 188), "pink": (232, 160, 176), "denim": (82, 104, 140),
         "khaki": (150, 140, 102), "purple": (124, 92, 150)}

HAIRS = ("short_part", "short", "buzz", "bald", "side_part", "long", "long_messy",
         "bob", "ponytail", "bun", "curly")
TOPS = ("sweater", "tshirt", "shirt", "jacket", "hoodie", "suit", "blouse", "dress")
EXPRS = ("neutral", "worried", "shocked", "scared", "sad", "crying", "angry", "happy",
         "laughing", "smirk", "tired", "thinking", "relieved", "desperate")
POSES = ("down", "phone_ear", "phone_look", "hand_head", "hands_head", "cross",
         "point", "wave", "hands_face", "hands_hips", "shrug", "fist", "hold_out")


@dataclass
class Look:
    """Ngoại hình cố định của một nhân vật."""
    sex: str = "male"               # male | female
    age: str = "adult"              # child | teen | young | adult | middle | old
    skin: str = "fair"
    hair: str = "short_part"
    hair_color: str = "black"
    top: str = "sweater"
    top_color: str = "beige"
    bottom_color: str = "navy"
    glasses: bool = False
    beard: str = ""                 # "" | stubble | mustache | full
    seed: int = 0

    @staticmethod
    def from_dict(d: dict | None) -> "Look":
        d = dict(d or {})
        lk = Look()
        for k in lk.__dataclass_fields__:
            if k in d and d[k] not in (None, ""):
                setattr(lk, k, d[k])
        if lk.hair not in HAIRS:
            lk.hair = "long" if lk.sex == "female" else "short_part"
        if lk.top not in TOPS:
            lk.top = "sweater"
        lk.glasses = bool(lk.glasses)
        return lk

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class State:
    """Trạng thái một khung hình."""
    expr: str = "neutral"
    mouth: float = 0.0              # 0 ngậm .. 1 há to (nhép theo giọng)
    blink: float = 0.0              # 0 mở .. 1 nhắm
    yaw: float = 0.0                # -1 quay sang trái màn hình .. 1 sang phải
    tilt: float = 0.0               # độ, đầu nghiêng
    nod: float = 0.0                # gật (đầu cúi xuống, đơn vị u)
    breathe: float = 0.0            # 0..1 nhịp thở
    pose: str = "down"
    pose_k: float = 1.0             # 0..1 chuyển dần sang tư thế mới
    pose_from: str = "down"
    look: tuple = (0.0, 0.0)        # hướng mắt nhìn (-1..1, -1..1)
    sit: bool = False
    shake: float = 0.0              # run rẩy
    extras: tuple = ()              # "sweat", "tears", "blush", "bags", "bruise", "shadow"


# ---------------------------------------------------------------- hình học

def _crs(pts: list, n: int = 10, closed: bool = True) -> list:
    """Đường cong Catmull-Rom đi qua các điểm."""
    P = [np.array(p, float) for p in pts]
    if len(P) < 3:
        return [tuple(p) for p in P]
    out = []
    m = len(P)
    rng = range(m) if closed else range(m - 1)
    for i in rng:
        p0 = P[(i - 1) % m] if closed or i > 0 else P[0]
        p1 = P[i]
        p2 = P[(i + 1) % m]
        p3 = P[(i + 2) % m] if closed or i + 2 < m else P[-1]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            q = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                       (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            out.append((q[0], q[1]))
    if not closed:
        out.append(tuple(P[-1]))
    return out


def _ellipse(cx, cy, rx, ry, n=36, a0=0.0, a1=2 * math.pi):
    return [(cx + rx * math.cos(a0 + (a1 - a0) * k / n), cy + ry * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(n + 1)]


def _tube(path: list, w0: float, w1: float, round_end: bool = False) -> list:
    """Ống thuôn dọc theo một đường (tay áo, cánh tay, chân, ngón tay).
    round_end: đầu cuối tròn (đầu ngón tay)."""
    P = np.array(path, float)
    n = len(P)
    left, right = [], []
    for i in range(n):
        a = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
        a = a / (np.linalg.norm(a) + 1e-9)
        nx, ny = -a[1], a[0]
        w = (w0 + (w1 - w0) * i / max(1, n - 1)) / 2
        left.append((P[i][0] + nx * w, P[i][1] + ny * w))
        right.append((P[i][0] - nx * w, P[i][1] - ny * w))
    if round_end and n >= 2:
        a = P[-1] - P[-2]
        base = math.atan2(a[1], a[0])
        w = w1 / 2
        cap = [(P[-1][0] + w * math.cos(base + math.pi / 2 - math.pi * k / 8),
                P[-1][1] + w * math.sin(base + math.pi / 2 - math.pi * k / 8)) for k in range(1, 8)]
        return left + cap + right[::-1]
    return left + right[::-1]


class Pen:
    """Bút vẽ theo đơn vị u lên lớp vẽ (đã nhân SS)."""

    def __init__(self, img: Image.Image, ox: float, oy: float, s: float, lw: float):
        self.img = img
        self.d = ImageDraw.Draw(img)
        self.ox, self.oy, self.s = ox, oy, s
        self.lw = max(1, int(round(lw)))
        self.rot = None                     # (cx, cy, cos, sin) xoay quanh điểm (đơn vị u)
        self._grp = None                    # khối liền đang gom (xem group / flush)

    def group(self):
        """Bắt đầu một khối liền (cánh tay + bàn tay + ngón...): các mảnh trong khối chỉ có
        viền ở mép ngoài, chỗ nối bên trong không có nét (khớp mềm, không tách rời)."""
        self._grp = []

    def flush(self, gaps=()):
        """Vẽ khối liền: viền dày trước, màu phủ sau; gaps = các nét mảnh giữa ngón tay."""
        grp, self._grp = self._grp or [], None
        for q, _f, w in grp:
            self.d.line(q + [q[0]], fill=INK, width=w * 2, joint="curve")
        for q, f, _w in grp:
            self.d.polygon(q, fill=f)
        for pts in gaps:
            self.line(pts, width=self.lw * 0.75)

    def P(self, x, y):
        if self.rot:
            cx, cy, c, s_ = self.rot
            dx, dy = x - cx, y - cy
            x, y = cx + dx * c - dy * s_, cy + dx * s_ + dy * c
        return (self.ox + x * self.s, self.oy + y * self.s)

    def poly(self, pts, fill, line=True, width=None):
        q = [self.P(x, y) for x, y in pts]
        if len(q) < 3:
            return
        if self._grp is not None and fill is not None and line:
            w = self.lw if width is None else max(1, int(round(width)))
            self._grp.append((q, fill, w))
            return
        if fill is not None:
            self.d.polygon(q, fill=fill)
        if line:
            w = self.lw if width is None else max(1, int(round(width)))
            self.d.line(q + [q[0]], fill=INK, width=w, joint="curve")

    def line(self, pts, width=None, fill=INK):
        q = [self.P(x, y) for x, y in pts]
        w = self.lw if width is None else max(1, int(round(width)))
        if len(q) >= 2:
            self.d.line(q, fill=fill, width=w, joint="curve")

    def dot(self, x, y, r, fill=INK):
        cx, cy = self.P(x, y)
        R = max(1.0, r * self.s)
        self.d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=fill)


# ---------------------------------------------------------------- kích thước

def build(look: Look) -> dict:
    """Tỉ lệ cơ thể theo tuổi, giới."""
    age, fem = look.age, look.sex == "female"
    heads = {"child": 5.2, "teen": 6.6, "young": 7.0, "adult": 7.0, "middle": 6.9, "old": 6.7}.get(age, 7.0)
    sh = {"child": 1.25, "teen": 1.6}.get(age, 1.55 if fem else 1.9)
    return {
        "H": heads,                                    # chiều cao (đơn vị đầu)
        "head_c": (0.0, -heads + 0.5),                 # tâm đầu
        "neck": (0.0, -heads + 1.02),                  # điểm xoay của đầu
        "sh_y": -heads + 1.16, "sh_w": sh,             # vai (cổ ngắn như webtoon)
        "waist_y": -heads * 0.47, "hip_y": -heads * 0.45,
        "hip_w": sh * (0.78 if fem else 0.66),
        "head_w": 0.4 if not fem else 0.38,
        "fem": fem,
    }


def skin_of(look):
    return SKIN.get(look.skin, SKIN["fair"]) + (255,)


def _col(name, table, default):
    c = table.get(name)
    if c is None and isinstance(name, (list, tuple)) and len(name) >= 3:
        c = tuple(int(v) for v in name[:3])
    return (c or default) + (255,)


# ---------------------------------------------------------------- tư thế tay
# Mỗi tay: (vai -> khuỷu -> cổ tay) theo toạ độ tương đối với vai (đơn vị u, x hướng ra ngoài).
# Tay "r" là tay phải của nhân vật = bên TRÁI màn hình.

def _arm_targets(pose: str, side: str, b: dict) -> tuple:
    """(khuỷu, cổ tay) tương đối vai, x dương = ra phía ngoài người."""
    hc = b["head_c"]
    sh = (b["sh_w"] / 2, b["sh_y"])
    def rel(x, y):                      # điểm tuyệt đối (x ra ngoài) -> tương đối vai
        return (x - sh[0], y - sh[1])
    down = ((0.18, 1.25), (0.22, 2.5))
    if pose == "phone_ear" and side == "r":
        return rel(1.05, hc[1] + 1.4), rel(0.555, hc[1] + 0.72)
    if pose == "phone_look" and side == "r":
        return rel(sh[0] + 0.25, sh[1] + 1.15), rel(0.3, sh[1] + 0.95)
    if pose == "hand_head" and side == "l":
        return rel(0.62, hc[1] + 1.0), rel(0.5, hc[1] - 0.08)
    if pose == "hands_head":
        return rel(0.62, hc[1] + 1.0), rel(0.5, hc[1] - 0.06)
    if pose == "hands_face":
        return rel(sh[0] + 0.2, sh[1] + 1.1), rel(0.2, hc[1] + 0.25)
    if pose == "cross":
        return rel(sh[0] + 0.22, sh[1] + 1.1), rel(-0.25, sh[1] + 1.05)
    if pose == "point" and side == "r":
        return rel(sh[0] + 0.55, sh[1] + 0.55), rel(sh[0] + 1.25, sh[1] + 0.45)
    if pose == "wave" and side == "r":
        return rel(sh[0] + 0.7, sh[1] + 0.3), rel(sh[0] + 0.85, hc[1] - 0.2)
    if pose == "hands_hips":
        return rel(sh[0] + 0.62, sh[1] + 0.95), rel(b["hip_w"] / 2 + 0.05, b["waist_y"] + 0.1)
    if pose == "shrug":
        return rel(sh[0] + 0.5, sh[1] + 0.9), rel(sh[0] + 0.75, sh[1] + 0.55)
    if pose == "fist" and side == "r":
        return rel(sh[0] + 0.3, sh[1] + 1.1), rel(sh[0] + 0.05, sh[1] + 0.35)
    if pose == "hold_out":
        return rel(sh[0] + 0.15, sh[1] + 1.15), rel(0.25, sh[1] + 1.35)
    return down


def _smoother(u):
    u = max(0.0, min(1.0, u))
    return u * u * u * (u * (u * 6 - 15) + 10)


def _back(u, s=1.2):
    """Đi tới đích, vượt nhẹ rồi dừng (tay người thật)."""
    u = max(0.0, min(1.0, u))
    v = u - 1
    return 1 + v * v * ((s + 1) * v + s)


def _lerp(a, b, k):
    return tuple(x + (y - x) * k for x, y in zip(a, b))


# ---------------------------------------------------------------- vẽ người

class Figure:
    """Một nhân vật: draw(pen, state) vẽ ở gốc chân (0,0) theo đơn vị u."""

    def __init__(self, look: Look):
        self.look = look
        self.b = build(look)
        self.skin = skin_of(look)
        self.hair = _col(look.hair_color, HAIR, HAIR["black"])
        self.top = _col(look.top_color, CLOTH, CLOTH["beige"])
        self.bottom = _col(look.bottom_color, CLOTH, CLOTH["navy"])
        lk = look
        self.wrinkles = {"middle": 1, "old": 2}.get(lk.age, 0)

    # ----- thân
    def _body(self, p: Pen, st: State, under=None):
        b = self.b
        br = 0.03 * math.sin(st.breathe * 2 * math.pi)
        sy, sw = b["sh_y"] + br, b["sh_w"]
        hip_y = b["hip_y"]
        fem = b["fem"]
        # chân
        if st.sit:
            hy = hip_y + 1.6
            for sx in (-1, 1):
                knee = (sx * b["hip_w"] * 0.32, hy + 0.55)
                foot = (sx * b["hip_w"] * 0.34, hy + 2.6)
                p.poly(_tube([(sx * b["hip_w"] * 0.22, hy - 0.2), knee], 0.62, 0.5), self.bottom)
                p.poly(_tube([knee, foot], 0.48, 0.4), self.bottom)
                self._shoe(p, foot[0], foot[1])
            body_shift = 1.6
        else:
            body_shift = 0.0
            for sx in (-1, 1):
                top = (sx * b["hip_w"] * 0.25, hip_y)
                foot = (sx * b["hip_w"] * 0.3, -0.18)
                p.poly(_tube([top, (sx * b["hip_w"] * 0.27, hip_y * 0.5), foot], 0.6, 0.42), self.bottom)
                self._shoe(p, foot[0], foot[1] + 0.1)
        if self.look.top == "dress":
            pass
        # thân áo
        sy += body_shift
        wy = b["waist_y"] + body_shift
        hy = hip_y + body_shift
        hw = b["hip_w"] / 2
        if under:
            under(sy)                                 # bắp tay sau thân áo
        side_w = sw / 2 * (0.78 if fem else 0.9)
        torso = [(-0.2, sy - 0.09), (-sw / 2 * 0.62, sy + 0.02), (-sw / 2 + 0.02, sy + 0.28),
                 (-sw / 2 - 0.01, sy + 0.75), (-side_w, wy), (-hw - 0.04, hy + 0.12),
                 (0.0, hy + 0.16),
                 (hw + 0.04, hy + 0.12), (side_w, wy), (sw / 2 + 0.01, sy + 0.75),
                 (sw / 2 - 0.02, sy + 0.28), (sw / 2 * 0.62, sy + 0.02), (0.2, sy - 0.09), (0.0, sy - 0.1)]
        if self.look.top == "dress":
            torso[5] = (-hw - 0.45, hy + 1.6)
            torso[6] = (0.0, hy + 1.65)
            torso[7] = (hw + 0.45, hy + 1.6)
        p.poly(_crs(torso, 7), self.top)
        # cổ
        nk = (b["neck"][0], b["neck"][1] + body_shift)
        # cổ to, ngắn; mép dưới chính là cổ áo tròn sát cổ (như ảnh mẫu)
        p.poly(_crs([(-0.15, nk[1] - 0.25), (0.15, nk[1] - 0.25), (0.165, nk[1] - 0.05), (0.25, sy - 0.075),
                     (0.12, sy - 0.045), (0.0, sy - 0.038), (-0.12, sy - 0.045), (-0.25, sy - 0.075),
                     (-0.165, nk[1] - 0.05)], 4), self.skin)
        # cổ áo
        t = self.look.top
        if t in ("shirt", "suit", "jacket", "blouse"):
            p.poly([(-0.27, sy - 0.06), (0.0, sy + 0.38), (0.27, sy - 0.06), (0.15, sy - 0.1),
                    (0.0, sy + 0.12), (-0.15, sy - 0.1)], (244, 244, 240, 255))
            if t == "suit":
                p.poly([(-0.06, sy + 0.1), (0.06, sy + 0.1), (0.04, sy + 0.9), (0, sy + 1.0),
                        (-0.04, sy + 0.9)], (150, 40, 50, 255))
            if t in ("jacket", "suit"):
                p.line([(0, sy + 0.38), (0, hy + 0.1)])
        elif t == "hoodie":
            p.poly(_crs([(-0.45, sy - 0.02), (0, sy + 0.25), (0.45, sy - 0.02), (0.3, sy - 0.2),
                         (-0.3, sy - 0.2)], 5), _shade(self.top, 0.9))
        else:
            p.line(_crs([(-0.27, sy - 0.08), (-0.12, sy - 0.045), (0, sy - 0.038), (0.12, sy - 0.045),
                         (0.27, sy - 0.08)], 8, closed=False))
        return sy, body_shift

    def _shoe(self, p, x, y):
        p.poly(_crs([(x - 0.24, y), (x - 0.22, y - 0.16), (x + 0.2, y - 0.16), (x + 0.3, y),
                     (x + 0.05, y + 0.05)], 5), (50, 46, 46, 255))

    def _arm(self, p: Pen, st: State, side: str, sy: float, part: str = "all", hand: bool = True):
        """Một cánh tay = bắp tay + khớp khuỷu tròn + cẳng tay + bàn tay, gộp thành KHỐI LIỀN
        (chỉ viền mép ngoài, khớp mềm, không gãy / thủng khi gập gắt).
        part "back": cả cánh tay (vẽ sau thân áo); "front": từ khuỷu trở xuống (cẳng tay
        + bàn tay đưa ra trước ngực / lên mặt); "all": cả tay."""
        if part == "upper":
            part = "back"
        if part == "lower":
            part = "front"
        b = self.b
        sgn = 1 if side == "l" else -1             # tay trái nhân vật = bên phải màn hình
        sh = (sgn * (b["sh_w"] / 2 - 0.2), sy + 0.4)
        e0, w0 = _arm_targets(st.pose_from, side, b)
        e1, w1 = _arm_targets(st.pose, side, b)
        # chuyển tư thế mềm: khuỷu đi trước, cổ tay theo sau và hơi vượt rồi dừng
        u = max(0.0, min(1.0, st.pose_k))
        ke = _smoother(min(1.0, u * 1.25))
        kw = _back(max(0.0, (u - 0.08) / 0.92))
        e, w = _lerp(e0, e1, ke), _lerp(w0, w1, kw)
        self._wr_off = (sgn * (w[0] - w1[0]), w[1] - w1[1])     # cổ tay còn cách đích bao nhiêu
        # đung đưa nhẹ theo nhịp thở cho tay không đứng đơ
        sway = 0.025 * math.sin(st.breathe * 2 * math.pi + (0.0 if side == "l" else 1.3))
        shift = sy - b["sh_y"]
        el = (sgn * (b["sh_w"] / 2 + e[0]) + sway * sgn, b["sh_y"] + e[1] + shift)
        wr = (sgn * (b["sh_w"] / 2 + w[0]) + sway * 1.6 * sgn, b["sh_y"] + w[1] + shift + abs(sway) * 0.5)
        sleeve_short = self.look.top in ("tshirt", "dress")
        tw = 0.42 if self.look.age != "child" else 0.36
        fore = _lerp(el, wr, 0.9)                    # ống tay dừng trước cổ tay
        p.group()
        if part in ("back", "all"):
            p.poly(_tube([sh, _lerp(sh, el, 0.5), el], tw, tw * 0.92), self.top)
            if sleeve_short:
                p.poly(_tube([_lerp(sh, el, 0.7), el], tw * 0.6, tw * 0.56), self.skin)
        elbow_col = self.skin if sleeve_short else self.top
        p.poly(_ellipse(el[0], el[1], tw * (0.3 if sleeve_short else 0.46), tw * (0.3 if sleeve_short else 0.46), 20),
               elbow_col)
        if sleeve_short:
            p.poly(_tube([el, _lerp(el, wr, 0.5), wr], tw * 0.58, tw * 0.48), self.skin)
        else:
            p.poly(_tube([el, _lerp(el, fore, 0.5), fore], tw * 0.88, tw * 0.8), self.top)
            p.poly(_tube([_lerp(el, wr, 0.8), wr], tw * 0.48, tw * 0.45), self.skin)   # cổ tay lẩn vào ống tay
        gaps, after = self._hand(p, wr, el, side, st) if hand else ([], None)
        p.flush(gaps)
        if after:
            after()

    def _hand(self, p: Pen, wr, el, side, st: State):
        """Bàn tay kiểu webtoon: lòng bàn tay + 4 ngón tròn đầu + ngón cái.
        Kiểu: grip (cầm điện thoại), open (xoè, ôm đầu / vẫy), fist (nắm), relax (buông)."""
        ang = math.atan2(wr[1] - el[1], wr[0] - el[0])
        c, s = math.cos(ang), math.sin(ang)
        sgn = -1 if side == "r" else 1
        def R(x, y):                      # x dọc theo cẳng tay, y ngang (đổi chiều theo tay)
            y *= sgn
            return (wr[0] + x * c - y * s, wr[1] + x * s + y * c)
        pose = st.pose if st.pose_k > 0.5 else st.pose_from
        phone = pose in ("phone_ear", "phone_look") and side == "r"
        gaps: list = []
        after = None
        if phone:
            kind = "grip"
            if pose == "phone_ear":
                return self._phone_ear(p, wr, st)
            after = lambda: self._phone(p, wr, side, st)      # điện thoại trước lòng bàn tay
        elif pose in ("hand_head", "hands_head", "wave", "hands_face", "shrug", "hold_out"):
            kind = "open"
        elif pose in ("fist", "cross"):
            kind = "fist"
        else:
            kind = "relax"
        k_ = 1.9 if self.look.age != "child" else 1.5     # bàn tay to gần bằng mặt như người thật
        r = 0.085 * k_                              # nửa bề ngang bàn tay
        L = (0.15 if kind != "fist" else 0.1) * k_  # dài lòng bàn tay
        palm = [R(-0.06, -r * 0.9), R(L * 0.5, -r * 1.08), R(L + 0.02, -r * 1.0), R(L + 0.04, r * 1.0),
                R(L * 0.5, r * 1.06), R(-0.06, r * 0.9)]
        p.poly(_crs(palm, 6), self.skin)
        if kind == "fist":
            for k in range(4):
                yy = -r + k * r * 0.66 + r * 0.33
                p.poly(_ellipse(*R(L + 0.03 * k_, yy), 0.045 * k_, 0.034 * k_, 14), self.skin)

        else:
            spread = {"open": 0.5, "grip": 0.05, "relax": 0.15}[kind]
            fl = {"open": 0.17, "grip": 0.12, "relax": 0.15}[kind] * k_
            # ôm đầu: ngón ngả vào phía đầu, ôm lấy tóc
            curl = 0.75 if pose in ("hand_head", "hands_head") else 0.0
            lines = []
            for k in range(4):
                yy = -r * 0.85 + k * r * 0.57
                a = (k - 1.5) * spread * 0.35 - curl
                base = R(L - 0.04, yy)
                ln = fl * (0.88 if k in (0, 3) else 1.0)
                mid = R(L + ln * 0.5 * math.cos(a * 0.5), yy + ln * 0.5 * math.sin(a * 0.5))
                tip = R(L + ln * math.cos(a), yy + ln * math.sin(a))
                p.poly(_tube(_crs([base, mid, tip], 6, closed=False), 0.064 * k_, 0.054 * k_, True), self.skin)
                lines.append((base, mid, tip))
            for (b0, m0, t0), (b1, m1, t1) in zip(lines, lines[1:]):        # nét mảnh giữa hai ngón
                gaps.append([_lerp(b0, b1, 0.5), _lerp(m0, m1, 0.5), _lerp(_lerp(m0, m1, 0.5), _lerp(t0, t1, 0.5), 0.6)])
        # ngón cái
        th = R(L * 0.5, -r * 1.0 - (0.07 if kind == "open" else 0.03) * k_)
        p.poly(_tube([R(0.02, -r * 0.6), _lerp(R(0.02, -r * 0.6), th, 0.5), th], 0.064 * k_, 0.054 * k_, True),
               self.skin)
        if kind == "fist":
            for k in range(3):
                yy = -r + (k + 1) * r * 0.5
                gaps.append([R(L * 0.8, yy), R(L + 0.05 * k_, yy)])
        return gaps, after

    def _phone(self, p: Pen, wr, side, st):
        hc = self.b["head_c"]
        if st.pose == "phone_ear":
            return
        else:
            cx, cy = wr[0] + 0.3, wr[1] - 0.2
            w_, h_, r_ = 0.17, 0.32, 0.05
            pts = []
            for (qx, qy, a0) in ((cx + w_ - r_, cy - h_ + r_, -90), (cx + w_ - r_, cy + h_ - r_, 0),
                                 (cx - w_ + r_, cy + h_ - r_, 90), (cx - w_ + r_, cy - h_ + r_, 180)):
                for k in range(5):
                    a = math.radians(a0 + 90 * k / 4)
                    pts.append((qx + r_ * math.cos(a), qy + r_ * math.sin(a)))
            p.poly(pts, (196, 199, 205, 255))
            inner = [(x * 0.86 + cx * 0.14, y * 0.9 + cy * 0.1) for x, y in pts]
            p.poly(inner, (64, 70, 86, 255), width=p.lw * 0.6)
            # ngón cái đè lên mép máy
            p.poly(_tube([(cx - w_ - 0.04, cy + 0.05), (cx - w_ + 0.06, cy - 0.02), (cx - w_ + 0.12, cy - 0.06)],
                         0.07, 0.06, True), self.skin)
            return

    # bàn tay áp điện thoại lên tai, can theo ảnh mẫu (đơn vị đầu, x = khoảng cách sang trái
    # màn hình tính từ tâm mặt, y tính từ ngang mắt)
    _EAR_PHONE = [(0.479, -0.102), (0.434, -0.125), (0.41, -0.109), (0.368, 0.028), (0.323, 0.178),
                  (0.287, 0.329), (0.303, 0.367), (0.368, 0.479), (0.436, 0.608), (0.468, 0.604),
                  (0.445, 0.479), (0.412, 0.39), (0.535, 0.256), (0.607, 0.145), (0.59, 0.078)]
    _EAR_EDGE = [(0.434, -0.125), (0.41, -0.109), (0.368, 0.028), (0.323, 0.178), (0.35, 0.18),
                 (0.393, 0.03), (0.437, -0.103)]
    _EAR_LOW = [(0.298, 0.358), (0.303, 0.367), (0.368, 0.479), (0.436, 0.608), (0.468, 0.604),
                (0.445, 0.479), (0.405, 0.392), (0.35, 0.352)]
    _EAR_LOW_EDGE = [(0.303, 0.367), (0.368, 0.479), (0.436, 0.608), (0.452, 0.606), (0.392, 0.474),
                     (0.33, 0.364)]
    _EAR_PALM = [(0.612, 0.134), (0.56, 0.1), (0.49, 0.135), (0.43, 0.2), (0.37, 0.255), (0.334, 0.29), (0.345, 0.345),
                 (0.412, 0.412), (0.44, 0.59), (0.445, 0.76), (0.665, 0.76), (0.662, 0.59),
                 (0.657, 0.434), (0.64, 0.278)]
    _EAR_FINGERS = [                     # (đường giữa ngón, rộng gốc, rộng đầu)
        ([(0.585, 0.17), (0.515, 0.05), (0.474, -0.068)], 0.072, 0.064),            # trỏ dựng dọc lưng máy
        ([(0.523, 0.19), (0.434, 0.095), (0.36, 0.076), (0.318, 0.1)], 0.078, 0.07),
        ([(0.479, 0.268), (0.39, 0.18), (0.33, 0.174), (0.293, 0.208)], 0.078, 0.07),
        ([(0.434, 0.335), (0.345, 0.283), (0.28, 0.303)], 0.07, 0.062),              # út
    ]

    def _phone_ear(self, p: Pen, wr, st):
        """Điện thoại áp tai: máy nghiêng thấy lưng + cạnh, ngón trỏ dựng dọc lưng máy, ba ngón
        còn lại ôm ngang qua máy, đầu ngón tròn chạm má. Đi theo đầu (đầu nghiêng thì máy theo);
        lúc tay đang đưa lên thì cả bàn tay lùi theo cổ tay. Trả (gaps, after) như _hand."""
        X, Y = self._hc
        rot0 = p.rot
        hrot = getattr(self, "_head_rot", None) or rot0
        k = self.b["head_w"] / 0.39
        ox, oy = getattr(self, "_wr_off", (0.0, 0.0))
        def T(pts):
            return [(X - x * k + ox, Y + y + oy) for x, y in pts]
        face, edge = (198, 200, 206, 255), (150, 153, 161, 255)
        grp, p._grp = p._grp, None
        p.rot = hrot
        p.poly(_crs(T(self._EAR_PHONE), 4), face)            # máy (sau các ngón)
        p.poly(T(self._EAR_EDGE), edge, width=p.lw * 0.6)
        p._grp = grp
        for path, w0, w1 in self._EAR_FINGERS:
            p.poly(_tube(_crs(T(path), 6, closed=False), w0 * k, w1 * k, True), self.skin)
        p.poly(_crs(T(self._EAR_PALM), 6), self.skin)
        p.rot = rot0
        def after():
            p.rot = hrot
            for (f0, _, _), (f1, _, _) in zip(self._EAR_FINGERS, self._EAR_FINGERS[1:]):
                # nếp giữa hai ngón: từ trong lòng bàn tay ra tới chỗ hai ngón tách nhau
                m0, m1 = _lerp(f0[0], f1[0], 0.5), _lerp(f0[1], f1[1], 0.5)
                p.line(T([_lerp(m0, m1, -0.15), _lerp(m0, m1, 0.62)]), width=p.lw * 0.75)
            p.poly(_crs(T(self._EAR_LOW), 4), face)          # đuôi máy thò ra dưới ngón út
            p.poly(T(self._EAR_LOW_EDGE), edge, width=p.lw * 0.6)
            p.rot = rot0
        return [], after

    # ----- đầu
    def _head(self, p: Pen, st: State, body_shift: float):
        b, lk = self.b, self.look
        hc = (b["head_c"][0], b["head_c"][1] + body_shift + st.nod)
        nk = (b["neck"][0], b["neck"][1] + body_shift)
        ang = math.radians(st.tilt)
        p.rot = (nk[0], nk[1], math.cos(ang), math.sin(ang))
        X, Y = hc
        self._hc = hc
        yaw = max(-1.0, min(1.0, st.yaw))
        fx = yaw * 0.1                               # mặt dịch theo hướng quay
        hw = b["head_w"]
        child = lk.age == "child"
        # tóc sau đầu (tóc dài)
        if lk.hair in ("long", "long_messy", "ponytail") and lk.sex == "female":
            L = 1.25 if lk.hair != "ponytail" else 0.7
            pts = [(X - hw - 0.12, Y - 0.15), (X - hw - 0.18, Y + L * 0.6), (X - hw - 0.05, Y + L),
                   (X + hw + 0.05, Y + L), (X + hw + 0.18, Y + L * 0.6), (X + hw + 0.12, Y - 0.15),
                   (X, Y - 0.6)]
            p.poly(_crs(pts, 6), self.hair)
        # tai (có nét vành tai trong)
        for sx in (-1, 1):
            if yaw * sx > 0.6:
                continue
            ex = X + sx * hw * 0.86 - fx * 0.4          # gốc tai lẩn dưới mép mặt: tai liền với mặt
            ear = [(ex, Y - 0.07), (ex + sx * 0.075, Y - 0.1), (ex + sx * 0.12, Y - 0.05),
                   (ex + sx * 0.115, Y + 0.07), (ex + sx * 0.08, Y + 0.16), (ex, Y + 0.19)]
            p.poly(_crs(ear, 8), self.skin)
            p.line(_crs([(ex + sx * 0.06, Y - 0.04), (ex + sx * 0.085, Y - 0.05), (ex + sx * 0.085, Y + 0.05),
                         (ex + sx * 0.06, Y + 0.1)], 6, closed=False), width=p.lw * 0.7)
        # mặt: má tròn, cằm thon mềm (đo theo video mẫu)
        k = hw / 0.39
        jw = 1.0 if lk.sex == "male" and not child else 0.92
        R_ = [(0.0, -0.56), (0.27, -0.52), (0.35, -0.32), (0.36, -0.1), (0.357, 0.08), (0.333, 0.22),
              (0.29 * jw, 0.33), (0.215 * jw, 0.43), (0.12 * jw, 0.508), (0.0, 0.535)]      # má thẳng, cằm tròn
        face = [(X + x * k, Y + y) for x, y in R_] + [(X - x * k, Y + y) for x, y in reversed(R_[1:-1])]
        p.poly(_crs(face, 10), self.skin)
        if lk.beard in ("stubble", "full"):
            sh = _shade(self.skin, 0.86)
            p.poly(_crs([(X - hw * 0.85, Y + 0.18), (X - 0.12, Y + 0.5), (X + 0.12, Y + 0.5),
                         (X + hw * 0.85, Y + 0.18), (X + 0.2, Y + 0.36), (X - 0.2, Y + 0.36)], 4),
                   sh, line=False)
        self._face(p, st, X + fx, Y, hw)
        self._hair(p, X, Y, hw, fx)
        self._head_rot = p.rot                       # tay áp điện thoại đi theo đầu
        if lk.glasses:
            for sx in (-1, 1):
                cx = X + fx + sx * 0.19
                p.line(_ellipse(cx, Y + 0.03, 0.12, 0.085, 24))
            p.line([(X + fx - 0.07, Y + 0.02), (X + fx + 0.07, Y + 0.02)])
        if "sweat" in st.extras:
            sx = X + hw * 0.9
            p.poly(_crs([(sx, Y - 0.3), (sx + 0.06, Y - 0.16), (sx, Y - 0.1), (sx - 0.06, Y - 0.16)], 4),
                   (150, 200, 240, 255))
        p.rot = None

    def _face(self, p: Pen, st: State, X: float, Y: float, hw: float):
        lk = self.look
        e = st.expr
        fem = lk.sex == "female"
        # ---- lông mày: (độ cao, góc trong) — góc dương: đầu trong nhướng lên (lo, buồn)
        brow = {"worried": (0.0, 0.07), "sad": (0.01, 0.08), "crying": (0.0, 0.09),
                "scared": (-0.04, 0.08), "shocked": (-0.07, 0.0), "desperate": (-0.02, 0.1),
                "angry": (0.03, -0.09), "happy": (-0.02, 0.0), "laughing": (-0.03, 0.0),
                "smirk": (0.0, -0.03), "thinking": (0.0, 0.04), "tired": (0.02, 0.03),
                "relieved": (0.0, 0.03)}.get(e, (0.0, 0.0))
        # lông mày dày, đầu trong tròn, đuôi ngoài thon cụp xuống (đo theo ảnh mẫu)
        thick = 1.0 if not fem else 0.62
        bcol = (40, 38, 42, 255) if lk.hair_color in ("black", "brown") else _shade(self.hair, 0.8)
        BR = [(0.085, -0.122), (0.19, -0.127), (0.28, -0.103), (0.298, -0.068), (0.19, -0.083),
              (0.085, -0.084), (0.07, -0.103)]
        for sx in (-1, 1):
            pts = []
            for x, y in BR:
                mid = -0.103
                y = mid + (y - mid) * thick                   # nữ: mày mảnh hơn
                inner = max(0.0, (0.3 - x) / 0.22)            # 1 ở đầu trong, 0 ở đuôi
                pts.append((X + sx * x, y + Y + brow[0] - brow[1] * inner + brow[1] * 0.3 * (1 - inner)))
            p.poly(_crs(pts, 6), bcol, line=True, width=p.lw * 0.5)
        # ---- mắt
        open_ = {"shocked": 1.35, "scared": 1.25, "tired": 0.6, "happy": 0.0, "laughing": 0.0,
                 "sad": 0.85, "crying": 0.8, "angry": 0.85, "smirk": 0.7, "thinking": 0.9,
                 "desperate": 1.15}.get(e, 1.0)
        open_ *= (1.0 - max(0.0, min(1.0, st.blink)))
        lx, ly = st.look
        for sx in (-1, 1):
            cx, cy = X + sx * 0.172, Y + 0.012
            w, h = 0.074, 0.037 * open_
            if "bags" in st.extras or e in ("tired", "desperate"):
                p.poly(_ellipse(cx, cy + 0.07, 0.1, 0.045, 16, 0, math.pi), (140, 120, 120, 120), line=False)
            if h < 0.008:                       # nhắm / cười híp
                arc = -1 if e in ("happy", "laughing") else 1
                p.line(_crs([(cx - w, cy), (cx, cy + arc * 0.035 if arc < 0 else cy + 0.01), (cx + w, cy)],
                            6, closed=False))
                if fem:
                    p.line([(cx + sx * w, cy), (cx + sx * (w + 0.03), cy - 0.025)], width=p.lw * 0.8)
                continue
            # mắt: lòng trắng, mí trên là nét đậm cong dài hơn mắt, mí dưới nét mảnh rời
            # hai đầu, con ngươi đen tròn (như ảnh mẫu)
            ii = -sx                                  # phía trong (gần mũi)
            up = [(cx - ii * w * 1.06, cy + h * 0.08), (cx - ii * w * 0.55, cy - h * 0.78), (cx, cy - h),
                  (cx + ii * w * 0.55, cy - h * 0.78), (cx + ii * w * 0.98, cy - h * 0.05)]
            lo = [(cx + ii * w * 0.98, cy - h * 0.05), (cx + ii * w * 0.5, cy + h * 0.85), (cx, cy + h * 1.08),
                  (cx - ii * w * 0.5, cy + h * 0.88), (cx - ii * w * 1.06, cy + h * 0.08)]
            p.poly(_crs(up + lo[1:-1], 8), (255, 255, 255, 255), line=False)
            pr = 0.027 if e not in ("shocked", "scared") else 0.019
            px = cx + lx * 0.03 + (0.012 if e == "smirk" else 0)
            py = cy - h * 0.05 + ly * 0.015
            p.dot(px, py, min(pr, h * 1.05))
            p.line(_crs(up, 8, closed=False), width=p.lw * 1.35)            # mí trên
            p.line(_crs(lo[1:-1], 6, closed=False), width=p.lw * 0.75)     # mí dưới
            if fem:                              # lông mi
                p.line([(cx + sx * w, cy - 0.005), (cx + sx * (w + 0.035), cy - 0.04)], width=p.lw * 0.9)
            if e == "angry":
                p.line([(cx - w, cy - h * 0.7 - (0.02 if sx > 0 else 0.04)),
                        (cx + w, cy - h * 0.7 - (0.04 if sx > 0 else 0.02))])
        # ---- mũi: hai nét dài hơi chụm + cánh mũi cong + nếp cười dài như dấu ngoặc
        for sx in (-1, 1):
            p.line(_crs([(X + sx * 0.042, Y - 0.07), (X + sx * 0.038, Y + 0.03), (X + sx * 0.04, Y + 0.11)],
                        8, closed=False), width=p.lw * 0.85)
            p.line(_crs([(X + sx * 0.06, Y + 0.105), (X + sx * 0.078, Y + 0.14), (X + sx * 0.06, Y + 0.172),
                         (X + sx * 0.025, Y + 0.17)], 8, closed=False), width=p.lw * 0.85)
        p.line(_crs([(X - 0.018, Y + 0.18), (X, Y + 0.186), (X + 0.018, Y + 0.18)], 6, closed=False),
               width=p.lw * 0.8)
        adult = lk.age in ("adult", "middle", "old")
        if adult and (self.wrinkles or lk.sex == "male"):
            for sx in (-1, 1):
                p.line(_crs([(X + sx * 0.1, Y + 0.19), (X + sx * 0.145, Y + 0.25), (X + sx * 0.16, Y + 0.32),
                             (X + sx * 0.15, Y + 0.37)], 8, closed=False), width=p.lw * 0.8)
        if self.wrinkles >= 2:
            for k in range(2):
                yy = Y - 0.28 + k * 0.06
                p.line(_crs([(X - 0.16, yy), (X, yy - 0.015), (X + 0.16, yy)], 4, closed=False), width=p.lw * 0.6)
            for sx in (-1, 1):
                p.line([(X + sx * 0.28, Y + 0.02), (X + sx * 0.33, Y + 0.0)], width=p.lw * 0.6)
        # ---- miệng
        my = Y + 0.28
        m = max(0.0, min(1.0, st.mouth))
        mw = {"shocked": 0.07, "scared": 0.08, "happy": 0.12, "laughing": 0.13, "angry": 0.1,
              "crying": 0.1, "desperate": 0.1}.get(e, 0.09)
        curve = {"happy": 0.04, "laughing": 0.05, "smirk": 0.02, "relieved": 0.015, "sad": -0.03,
                 "crying": -0.035, "worried": -0.015, "angry": -0.02, "scared": -0.02,
                 "desperate": -0.03}.get(e, 0.0)
        base_open = {"shocked": 0.55, "scared": 0.3, "laughing": 0.6, "crying": 0.25,
                     "desperate": 0.3}.get(e, 0.0)
        o = max(m, base_open)
        lip = (214, 120, 120, 255) if fem else None
        if o < 0.08:
            if e == "smirk":
                p.line(_crs([(X - mw, my), (X + 0.01, my + 0.01), (X + mw, my - 0.03)], 5, closed=False))
            else:
                # môi trên lượn nhẹ + môi dưới ngắn (như video mẫu)
                # môi trên hình chữ M nhẹ, khoé hơi nhếch; môi dưới một nét cong ngắn (như ảnh mẫu)
                cy0 = my - curve * 0.3 - 0.004
                p.line(_crs([(X - mw, cy0), (X - mw * 0.5, my - 0.009 + curve * 0.4), (X, my - 0.001 + curve),
                             (X + mw * 0.5, my - 0.009 + curve * 0.4), (X + mw, cy0)], 8, closed=False))
                if not fem:
                    p.line(_crs([(X - mw * 0.48, my + 0.06 + curve * 0.6), (X, my + 0.07 + curve * 0.8),
                                 (X + mw * 0.48, my + 0.06 + curve * 0.6)], 6, closed=False), width=p.lw * 0.85)
            if lip:
                p.line(_crs([(X - mw * 0.6, my + 0.02), (X, my + 0.035), (X + mw * 0.6, my + 0.02)],
                            4, closed=False), width=p.lw * 1.1, fill=lip)
        else:
            h = 0.02 + 0.11 * o
            top = my - h * 0.35 - curve * 0.3
            mouth = [(X - mw, my - curve * 0.3), (X - mw * 0.5, top), (X + mw * 0.5, top),
                     (X + mw, my - curve * 0.3), (X + mw * 0.6, my + h * 0.65 + curve),
                     (X - mw * 0.6, my + h * 0.65 + curve)]
            p.poly(_crs(mouth, 5), (88, 40, 44, 255))
            if o > 0.35:                                 # răng trên
                p.poly([(X - mw * 0.55, top + 0.004), (X + mw * 0.55, top + 0.004),
                        (X + mw * 0.45, top + 0.025), (X - mw * 0.45, top + 0.025)],
                       (250, 250, 248, 255), line=False)
                p.poly(_ellipse(X, my + h * 0.45, mw * 0.45, h * 0.2, 12, math.pi, 2 * math.pi),
                       (200, 100, 104, 255), line=False)
            if lip:
                p.line(mouth[3:] + mouth[:1], width=p.lw * 1.1, fill=lip)
        # ---- thêm
        if e in ("crying",) or "tears" in st.extras:
            for sx in (-1, 1):
                cx = X + sx * 0.19
                p.line(_crs([(cx - 0.04, Y + 0.08), (cx - 0.05, Y + 0.2), (cx - 0.045, Y + 0.3)], 4,
                            closed=False), width=p.s * 0.022, fill=(130, 190, 236, 230))
                p.dot(cx - 0.045, Y + 0.32, 0.016, (130, 190, 236, 230))
        if "blush" in st.extras or e in ("happy", "laughing") and fem:
            for sx in (-1, 1):
                p.poly(_ellipse(X + sx * 0.24, Y + 0.17, 0.06, 0.03, 12), (240, 150, 150, 110), line=False)
        if "bruise" in st.extras:
            p.poly(_ellipse(X + 0.24, Y + 0.15, 0.06, 0.04, 12), (130, 110, 120, 90), line=False)
            p.poly(_ellipse(X - 0.15, Y - 0.2, 0.045, 0.035, 12), (130, 110, 120, 80), line=False)
        if e in ("scared", "desperate") or "shadow" in st.extras:
            # mặt tái kiểu truyện tranh: mấy vạch sọc trên trán
            for k in range(5):
                x0 = X - 0.16 + k * 0.08
                p.line([(x0, Y - 0.24), (x0, Y - 0.13 - (k % 2) * 0.03)], width=p.lw * 0.7,
                       fill=(70, 80, 150, 200))

    def _hair(self, p: Pen, X, Y, hw, fx):
        lk = self.look
        h = lk.hair
        col = self.hair
        if h == "bald":
            if self.wrinkles:
                for sx in (-1, 1):
                    p.poly(_crs([(X + sx * (hw + 0.02), Y - 0.25), (X + sx * (hw + 0.04), Y + 0.02),
                                 (X + sx * (hw - 0.06), Y + 0.0), (X + sx * (hw - 0.06), Y - 0.22)], 4), col)
            return
        if h == "buzz":
            p.poly(_crs([(X - hw - 0.01, Y - 0.08), (X - hw * 0.95, Y - 0.42), (X, Y - 0.54),
                         (X + hw * 0.95, Y - 0.42), (X + hw + 0.01, Y - 0.08), (X + hw * 0.85, Y - 0.22),
                         (X, Y - 0.32), (X - hw * 0.85, Y - 0.22)], 5), col)
            return
        if lk.sex == "female" or h in ("long", "long_messy", "bob", "ponytail", "bun", "curly"):
            # mái + hai bên má
            side = 0.62 if h in ("long", "long_messy") else (0.35 if h == "bob" else 0.15)
            pts = [(X - hw - 0.1, Y + side), (X - hw - 0.1, Y - 0.2), (X - hw * 0.8, Y - 0.5), (X, Y - 0.62),
                   (X + hw * 0.8, Y - 0.5), (X + hw + 0.1, Y - 0.2), (X + hw + 0.1, Y + side),
                   (X + hw - 0.02, Y + side), (X + hw - 0.04, Y - 0.14), (X + 0.2 + fx, Y - 0.2),
                   (X + fx, Y - 0.185), (X - 0.2 + fx, Y - 0.21), (X - hw + 0.03, Y - 0.14),
                   (X - hw + 0.02, Y + side)]
            if h == "bun":
                p.poly(_ellipse(X, Y - 0.66, 0.2, 0.15, 24), col)
            if h == "curly":
                pts = [(x + 0.03 * math.sin(i * 2.3), y + 0.03 * math.cos(i * 1.7)) for i, (x, y) in enumerate(pts)]
            p.poly(_crs(pts, 9), col)
            if h == "long_messy":
                for k in range(5):
                    x0 = X - hw + k * hw * 0.5
                    p.line(_crs([(x0, Y - 0.55), (x0 + 0.1, Y - 0.68), (x0 + 0.18, Y - 0.6)], 4, closed=False),
                           width=p.lw * 0.8)
            if h == "ponytail":
                p.poly(_crs([(X + hw * 0.6, Y - 0.4), (X + hw + 0.25, Y - 0.2), (X + hw + 0.3, Y + 0.4),
                             (X + hw + 0.15, Y + 0.45), (X + hw + 0.08, Y)], 4), col)
            return
        # tóc nam: mũ tóc tròn đầy, mái lượn ngang trán lên tới một chỏm nhọn lệch phải rồi ôm
        # xuống thái dương tới tai, hai nét sợi tóc cong (đo theo ảnh mẫu)
        k = hw / 0.39
        mir = -1 if h == "side_part" else 1                 # rẽ ngôi bên kia
        # tóc ngắn gọn ôm đầu, không phồng hai bên; mép dưới dừng trên tai
        outer = [(-0.39, -0.12), (-0.425, -0.2), (-0.44, -0.3), (-0.42, -0.43), (-0.35, -0.54),
                 (-0.25, -0.6), (-0.12, -0.632), (0.0, -0.638), (0.13, -0.632), (0.26, -0.6), (0.36, -0.53),
                 (0.42, -0.42), (0.44, -0.29), (0.43, -0.19), (0.395, -0.12)]
        if h == "short":
            right = [(0.362, -0.12), (0.35, -0.2), (0.3, -0.29), (0.15, -0.37), (0.0, -0.385)]
            left = [(0.0, -0.385), (-0.15, -0.37), (-0.3, -0.29), (-0.35, -0.2), (-0.362, -0.12)]
            strands = []
        else:
            right = [(0.362, -0.12), (0.352, -0.18), (0.33, -0.24), (0.278, -0.308), (0.219, -0.382),
                     (0.171, -0.456)]
            left = [(0.171, -0.456), (0.137, -0.412), (0.07, -0.352), (-0.078, -0.323), (-0.226, -0.30),
                    (-0.30, -0.278), (-0.352, -0.22), (-0.362, -0.12)]
            strands = [[(-0.263, -0.293), (-0.236, -0.336), (-0.219, -0.37)],
                       [(-0.07, -0.323), (-0.042, -0.372), (-0.026, -0.414)]]
        def T(pts, dx=0.0):
            return [(X + (mir * x) * k + dx, Y + y) for x, y in pts]
        # ba đoạn cong riêng nối lại: giữ góc nhọn ở chỏm mái và hai bên thái dương
        poly = (_crs(T(outer), 6, closed=False) + _crs(T(right, fx * 0.5), 6, closed=False)
                + _crs(T(left, fx * 0.5), 6, closed=False))
        p.poly(poly, col)
        for st_ in strands:
            p.line(_crs(T(st_, fx * 0.5), 6, closed=False), width=p.lw * 0.8)

    # ----- cả người
    def draw(self, p: Pen, st: State):
        raised = {"phone_ear": ("r",), "hand_head": ("l",), "hands_head": ("l", "r"),
                  "hands_face": ("l", "r")}
        chest = {"phone_look": ("r",), "cross": ("l", "r"), "fist": ("r",), "hold_out": ("l", "r")}
        up = set(raised.get(st.pose, ())) | set(raised.get(st.pose_from, ()))
        front = (set(chest.get(st.pose, ())) | set(chest.get(st.pose_from, ()))) - up
        def under(sy_):                              # cánh tay sau thân áo: không lộ đường vai
            for side in ("l", "r"):
                self._arm(p, st, side, sy_, "back", hand=side not in up and side not in front)
        sy, shift = self._body(p, st, under)
        for side in front:                           # cẳng tay đưa ra trước ngực
            self._arm(p, st, side, sy, "front")
        self._head(p, st, shift)
        for side in up:                              # tay đưa lên mặt / đầu: vẽ đè lên đầu
            self._arm(p, st, side, sy, "front")


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c[:3]) + (c[3] if len(c) > 3 else 255,)


# ---------------------------------------------------------------- vẽ ra ảnh

def render(fig: Figure, st: State, size: tuple[int, int], foot: tuple[float, float],
           s: float, lw: float, bg: Image.Image | None = None) -> Image.Image:
    """Vẽ nhân vật lên ảnh: foot = toạ độ màn hình của gốc chân, s = px mỗi đơn vị đầu."""
    W, H = size
    layer = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    pen = Pen(layer, foot[0] * SS, foot[1] * SS, s * SS, lw * SS)
    if st.shake:
        pen.ox += math.sin(st.shake * 40) * 0.01 * s * SS
    fig.draw(pen, st)
    layer = layer.reduce(SS)
    base = bg.convert("RGBA") if bg is not None else Image.new("RGBA", (W, H), (0, 0, 0, 0))
    base.alpha_composite(layer)
    return base
