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
SKIN = {"light": (250, 222, 196), "fair": (246, 214, 186), "tan": (226, 186, 150),
        "dark": (182, 136, 104)}
HAIR = {"black": (36, 34, 38), "brown": (92, 62, 44), "gray": (150, 150, 152),
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


def _tube(path: list, w0: float, w1: float) -> list:
    """Ống thuôn dọc theo một đường (tay áo, cánh tay, chân)."""
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
    return left + right[::-1]


class Pen:
    """Bút vẽ theo đơn vị u lên lớp vẽ (đã nhân SS)."""

    def __init__(self, img: Image.Image, ox: float, oy: float, s: float, lw: float):
        self.img = img
        self.d = ImageDraw.Draw(img)
        self.ox, self.oy, self.s = ox, oy, s
        self.lw = max(1, int(round(lw)))
        self.rot = None                     # (cx, cy, cos, sin) xoay quanh điểm (đơn vị u)

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
        "sh_y": -heads + 1.28, "sh_w": sh,             # vai
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
        return rel(0.62, hc[1] + 1.3), rel(0.56, hc[1] + 0.6)
    if pose == "phone_look" and side == "r":
        return rel(sh[0] + 0.1, sh[1] + 1.3), rel(0.18, sh[1] + 0.85)
    if pose == "hand_head" and side == "l":
        return rel(0.62, hc[1] + 1.0), rel(0.5, hc[1] - 0.08)
    if pose == "hands_head":
        return rel(0.62, hc[1] + 1.0), rel(0.5, hc[1] - 0.06)
    if pose == "hands_face":
        return rel(sh[0] + 0.2, sh[1] + 1.1), rel(0.2, hc[1] + 0.25)
    if pose == "cross":
        return rel(sh[0] + 0.12, sh[1] + 1.15), rel(-0.35, sh[1] + 1.0)
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
        torso = [(-0.2, sy - 0.07), (-sw / 2 * 0.62, sy + 0.02), (-sw / 2 + 0.02, sy + 0.28),
                 (-sw / 2 - 0.01, sy + 0.75), (-side_w, wy), (-hw - 0.04, hy + 0.12),
                 (0.0, hy + 0.16),
                 (hw + 0.04, hy + 0.12), (side_w, wy), (sw / 2 + 0.01, sy + 0.75),
                 (sw / 2 - 0.02, sy + 0.28), (sw / 2 * 0.62, sy + 0.02), (0.2, sy - 0.07), (0.0, sy - 0.08)]
        if self.look.top == "dress":
            torso[5] = (-hw - 0.45, hy + 1.6)
            torso[6] = (0.0, hy + 1.65)
            torso[7] = (hw + 0.45, hy + 1.6)
        p.poly(_crs(torso, 7), self.top)
        # cổ
        nk = (b["neck"][0], b["neck"][1] + body_shift)
        p.poly([(-0.13, nk[1] - 0.12), (0.13, nk[1] - 0.12), (0.15, sy - 0.02), (-0.15, sy - 0.02)],
               self.skin)
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
            p.line(_crs([(-0.24, sy - 0.05), (0, sy + 0.16), (0.24, sy - 0.05)], 6, closed=False))
        return sy, body_shift

    def _shoe(self, p, x, y):
        p.poly(_crs([(x - 0.24, y), (x - 0.22, y - 0.16), (x + 0.2, y - 0.16), (x + 0.3, y),
                     (x + 0.05, y + 0.05)], 5), (50, 46, 46, 255))

    def _arm(self, p: Pen, st: State, side: str, sy: float, part: str = "all"):
        """Vẽ một tay: part "upper" (bắp tay, vẽ sau thân áo cho thân che đầu ống tay),
        "lower" (cẳng tay + bàn tay, vẽ trước thân) hoặc "all"."""
        b = self.b
        sgn = 1 if side == "l" else -1             # tay trái nhân vật = bên phải màn hình
        sh = (sgn * (b["sh_w"] / 2 - 0.17), sy + 0.36)
        e0, w0 = _arm_targets(st.pose_from, side, b)
        e1, w1 = _arm_targets(st.pose, side, b)
        k = max(0.0, min(1.0, st.pose_k))
        k = k * k * (3 - 2 * k)
        e, w = _lerp(e0, e1, k), _lerp(w0, w1, k)
        shift = sy - b["sh_y"] - 0.18 + 0.18
        el = (sgn * (abs(sh[0]) + e[0]) if True else 0, b["sh_y"] + e[1] + shift)
        el = (sgn * (b["sh_w"] / 2 + e[0] - 0.12 + 0.12), b["sh_y"] + e[1] + shift)
        wr = (sgn * (b["sh_w"] / 2 + w[0]), b["sh_y"] + w[1] + shift)
        # tay vào sát mặt / trước ngực: vẽ trước thân; tay buông: vẽ cạnh thân
        sleeve_short = self.look.top in ("tshirt", "dress")
        tw = 0.42 if self.look.age != "child" else 0.36
        path = _crs([sh, _lerp(sh, el, 0.5), el, _lerp(el, wr, 0.5), wr], 5, closed=False)
        mid = len(path) // 2                          # khuỷu tay
        up_path, lo_path = path[:mid + 2], path[mid - 1:]
        if part in ("upper", "all"):
            if sleeve_short:
                cut = max(2, len(up_path) * 8 // 10)
                p.poly(_crs(_tube(up_path[:cut], tw + 0.04, tw), 2), self.top)
                p.poly(_crs(_tube(up_path[cut - 1:], tw * 0.62, tw * 0.58), 2), self.skin)
            else:
                p.poly(_crs(_tube(up_path, tw, tw * 0.9), 2), self.top)
        if part in ("lower", "all"):
            if sleeve_short:
                p.poly(_crs(_tube(lo_path, tw * 0.58, tw * 0.5), 2), self.skin)
            else:
                p.poly(_crs(_tube(lo_path[:-2], tw * 0.9, tw * 0.82), 2), self.top)
            self._hand(p, wr, el, side, st)

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
        if phone:
            self._phone(p, wr, side, st)
            kind = "grip"
        elif pose in ("hand_head", "hands_head", "wave", "hands_face", "shrug", "hold_out"):
            kind = "open"
        elif pose in ("fist", "cross"):
            kind = "fist"
        else:
            kind = "relax"
        k_ = 1.9 if self.look.age != "child" else 1.5     # bàn tay to gần bằng mặt như người thật
        r = 0.085 * k_                              # nửa bề ngang bàn tay
        L = (0.15 if kind != "fist" else 0.1) * k_  # dài lòng bàn tay
        palm = [R(-0.02, -r), R(L, -r * 1.05), R(L + 0.02, r * 1.05), R(-0.02, r)]
        p.poly(_crs(palm, 4), self.skin)
        if kind == "fist":
            for k in range(4):
                yy = -r + k * r * 0.66 + r * 0.33
                p.poly(_ellipse(*R(L + 0.03 * k_, yy), 0.045 * k_, 0.034 * k_, 14), self.skin)
        elif kind == "grip" and pose == "phone_ear":
            # ngón tay cong ôm ngang qua điện thoại, hướng vào mặt
            for k in range(4):
                a0 = R(L * 0.15 + k * 0.075 * k_, r * 0.6)
                a1 = R(L * 0.15 + k * 0.075 * k_, -r * 1.9 + abs(k - 1.5) * 0.03 * k_)
                p.poly(_crs(_tube([a0, a1], 0.07 * k_, 0.062 * k_), 2), self.skin)
        else:
            spread = {"open": 0.5, "grip": 0.05, "relax": 0.15}[kind]
            fl = {"open": 0.17, "grip": 0.12, "relax": 0.15}[kind] * k_
            # ôm đầu: ngón ngả vào phía đầu, ôm lấy tóc
            curl = 0.75 if pose in ("hand_head", "hands_head") else 0.0
            for k in range(4):
                yy = -r * 0.85 + k * r * 0.57
                a = (k - 1.5) * spread * 0.35 - curl
                base = R(L - 0.01, yy)
                ln = fl * (0.88 if k in (0, 3) else 1.0)
                mid = R(L + ln * 0.5 * math.cos(a * 0.5), yy + ln * 0.5 * math.sin(a * 0.5))
                tip = R(L + ln * math.cos(a), yy + ln * math.sin(a))
                p.poly(_crs(_tube([base, mid, tip], 0.058 * k_, 0.05 * k_), 2), self.skin)
        # ngón cái
        th = R(L * 0.5, -r * 1.0 - (0.07 if kind == "open" else 0.03) * k_)
        p.poly(_crs(_tube([R(0.02, -r * 0.6), th], 0.062 * k_, 0.05 * k_), 2), self.skin)

    def _phone(self, p: Pen, wr, side, st):
        hc = self.b["head_c"]
        if st.pose == "phone_ear":
            cx, cy = -0.42, hc[1] + 0.14
            pts = [(cx - 0.12, cy - 0.27), (cx + 0.01, cy - 0.3), (cx + 0.14, cy + 0.26), (cx + 0.02, cy + 0.3)]
        else:
            cx, cy = wr[0] + 0.25, wr[1] - 0.15
            pts = [(cx - 0.17, cy - 0.3), (cx + 0.17, cy - 0.3), (cx + 0.17, cy + 0.3), (cx - 0.17, cy + 0.3)]
        p.poly(_crs(pts, 3), (150, 154, 162, 255))

    # ----- đầu
    def _head(self, p: Pen, st: State, body_shift: float):
        b, lk = self.b, self.look
        hc = (b["head_c"][0], b["head_c"][1] + body_shift + st.nod)
        nk = (b["neck"][0], b["neck"][1] + body_shift)
        ang = math.radians(st.tilt)
        p.rot = (nk[0], nk[1], math.cos(ang), math.sin(ang))
        X, Y = hc
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
        # tai
        for sx in (-1, 1):
            ex = X + sx * (hw + 0.01) - fx * 0.5 * sx * sx
            if yaw * sx > 0.6:
                continue
            p.poly(_crs([(ex, Y - 0.04), (ex + sx * 0.08, Y - 0.06), (ex + sx * 0.1, Y + 0.08),
                         (ex + sx * 0.05, Y + 0.2), (ex, Y + 0.18)], 4), self.skin)
        # mặt (quả trứng)
        jaw = 0.82 if lk.sex == "male" and not child else 0.74
        face = [(X, Y - 0.5), (X + hw * 0.92, Y - 0.38), (X + hw, Y - 0.05), (X + hw * 0.95, Y + 0.22),
                (X + hw * jaw, Y + 0.4), (X + 0.12, Y + 0.52), (X - 0.12, Y + 0.52),
                (X - hw * jaw, Y + 0.4), (X - hw * 0.95, Y + 0.22), (X - hw, Y - 0.05),
                (X - hw * 0.92, Y - 0.38)]
        p.poly(_crs(face, 6), self.skin)
        if lk.beard in ("stubble", "full"):
            sh = _shade(self.skin, 0.86)
            p.poly(_crs([(X - hw * 0.85, Y + 0.18), (X - 0.12, Y + 0.5), (X + 0.12, Y + 0.5),
                         (X + hw * 0.85, Y + 0.18), (X + 0.2, Y + 0.36), (X - 0.2, Y + 0.36)], 4),
                   sh, line=False)
        self._face(p, st, X + fx, Y, hw)
        self._hair(p, X, Y, hw, fx)
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
        by = Y - 0.09 + brow[0]
        thick = 0.042 if not fem else 0.03
        for sx in (-1, 1):
            xi, xo = X + sx * 0.07, X + sx * 0.3
            yi, yo = by - brow[1], by + brow[1] * 0.3
            pts = [(xi, yi), (xi + sx * 0.08, yi - 0.035), (xo - sx * 0.02, yo - 0.02), (xo, yo + 0.01),
                   (xo - sx * 0.03, yo + thick * 0.6), (xi + sx * 0.04, yi + thick)]
            p.poly(_crs(pts, 4), self.hair if lk.hair_color != "white" else (180, 178, 176, 255),
                   line=True, width=p.lw * 0.6)
        # ---- mắt
        open_ = {"shocked": 1.35, "scared": 1.25, "tired": 0.6, "happy": 0.0, "laughing": 0.0,
                 "sad": 0.85, "crying": 0.8, "angry": 0.85, "smirk": 0.7, "thinking": 0.9,
                 "desperate": 1.15}.get(e, 1.0)
        open_ *= (1.0 - max(0.0, min(1.0, st.blink)))
        lx, ly = st.look
        for sx in (-1, 1):
            cx, cy = X + sx * 0.19, Y + 0.04
            w, h = 0.085, 0.045 * open_
            if "bags" in st.extras or e in ("tired", "desperate"):
                p.poly(_ellipse(cx, cy + 0.07, 0.1, 0.045, 16, 0, math.pi), (140, 120, 120, 120), line=False)
            if h < 0.008:                       # nhắm / cười híp
                arc = -1 if e in ("happy", "laughing") else 1
                p.line(_crs([(cx - w, cy), (cx, cy + arc * 0.035 if arc < 0 else cy + 0.01), (cx + w, cy)],
                            6, closed=False))
                if fem:
                    p.line([(cx + sx * w, cy), (cx + sx * (w + 0.03), cy - 0.025)], width=p.lw * 0.8)
                continue
            eye = [(cx - w, cy), (cx - w * 0.4, cy - h), (cx + w * 0.4, cy - h), (cx + w, cy),
                   (cx + w * 0.4, cy + h * 0.9), (cx - w * 0.4, cy + h * 0.9)]
            p.poly(_crs(eye, 5), (255, 255, 255, 255))
            pr = 0.026 if e not in ("shocked", "scared") else 0.018
            px = cx + lx * 0.03 + (0.012 if e == "smirk" else 0)
            py = cy + ly * 0.015
            p.dot(px, py, min(pr, h * 0.95))
            if fem:                              # lông mi
                p.line([(cx + sx * w, cy - 0.005), (cx + sx * (w + 0.035), cy - 0.04)], width=p.lw * 0.9)
            if e == "angry":
                p.line([(cx - w, cy - h * 0.7 - (0.02 if sx > 0 else 0.04)),
                        (cx + w, cy - h * 0.7 - (0.04 if sx > 0 else 0.02))])
        # ---- mũi: hai nét dài + cánh mũi
        ny0, ny1 = Y + 0.02, Y + 0.22
        for sx in (-1, 1):
            p.line(_crs([(X + sx * 0.04, ny0), (X + sx * 0.035, ny1 - 0.06), (X + sx * 0.06, ny1)],
                        5, closed=False), width=p.lw * 0.85)
        p.line(_crs([(X - 0.06, ny1), (X - 0.03, ny1 + 0.025), (X, ny1 + 0.01), (X + 0.03, ny1 + 0.025),
                     (X + 0.06, ny1)], 4, closed=False), width=p.lw * 0.85)
        # nếp mũi – má (người lớn) và nếp nhăn
        if self.wrinkles or lk.sex == "male":
            for sx in (-1, 1):
                p.line(_crs([(X + sx * 0.11, ny1 - 0.02), (X + sx * 0.15, ny1 + 0.06), (X + sx * 0.16, ny1 + 0.13)],
                            4, closed=False), width=p.lw * 0.7)
        if self.wrinkles >= 2:
            for k in range(2):
                yy = Y - 0.28 + k * 0.06
                p.line(_crs([(X - 0.16, yy), (X, yy - 0.015), (X + 0.16, yy)], 4, closed=False), width=p.lw * 0.6)
            for sx in (-1, 1):
                p.line([(X + sx * 0.28, Y + 0.02), (X + sx * 0.33, Y + 0.0)], width=p.lw * 0.6)
        # ---- miệng
        my = Y + 0.33
        m = max(0.0, min(1.0, st.mouth))
        mw = {"shocked": 0.07, "scared": 0.08, "happy": 0.12, "laughing": 0.13, "angry": 0.1,
              "crying": 0.1, "desperate": 0.1}.get(e, 0.085)
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
                p.line(_crs([(X - mw, my - curve * 0.3), (X, my + curve), (X + mw, my - curve * 0.3)],
                            5, closed=False))
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
                   (X + hw - 0.02, Y + side), (X + hw - 0.04, Y - 0.1), (X + 0.2 + fx, Y - 0.17),
                   (X + fx, Y - 0.15), (X - 0.2 + fx, Y - 0.18), (X - hw + 0.03, Y - 0.1),
                   (X - hw + 0.02, Y + side)]
            if h == "bun":
                p.poly(_ellipse(X, Y - 0.66, 0.2, 0.15, 24), col)
            if h == "curly":
                pts = [(x + 0.03 * math.sin(i * 2.3), y + 0.03 * math.cos(i * 1.7)) for i, (x, y) in enumerate(pts)]
            p.poly(_crs(pts, 5), col)
            if h == "long_messy":
                for k in range(5):
                    x0 = X - hw + k * hw * 0.5
                    p.line(_crs([(x0, Y - 0.55), (x0 + 0.1, Y - 0.68), (x0 + 0.18, Y - 0.6)], 4, closed=False),
                           width=p.lw * 0.8)
            if h == "ponytail":
                p.poly(_crs([(X + hw * 0.6, Y - 0.4), (X + hw + 0.25, Y - 0.2), (X + hw + 0.3, Y + 0.4),
                             (X + hw + 0.15, Y + 0.45), (X + hw + 0.08, Y)], 4), col)
            return
        # tóc nam: khối trên đầu, mái nhọn rẽ một bên (giống video mẫu)
        top = Y - 0.66 if h != "side_part" else Y - 0.68
        pts = [(X - hw - 0.03, Y - 0.02), (X - hw - 0.06, Y - 0.3), (X - hw * 0.7, top + 0.08), (X, top),
               (X + hw * 0.75, top + 0.06), (X + hw + 0.06, Y - 0.32), (X + hw + 0.03, Y - 0.02),
               (X + hw - 0.03, Y - 0.08), (X + hw - 0.06, Y - 0.24), (X + 0.2 + fx, Y - 0.27),
               (X + 0.12 + fx, Y - 0.42), (X - 0.08 + fx, Y - 0.3), (X - hw + 0.08, Y - 0.22),
               (X - hw + 0.03, Y - 0.08)]
        if h == "short":
            pts[9], pts[10], pts[11] = (X + 0.2 + fx, Y - 0.34), (X + fx, Y - 0.36), (X - 0.2 + fx, Y - 0.34)
        p.poly(_crs(pts, 5), col)

    # ----- cả người
    def draw(self, p: Pen, st: State):
        raised = {"phone_ear": ("r",), "hand_head": ("l",), "hands_head": ("l", "r"),
                  "hands_face": ("l", "r")}
        up = set(raised.get(st.pose, ())) | set(raised.get(st.pose_from, ()))
        def under(sy_):
            for side in ("l", "r"):
                self._arm(p, st, side, sy_, "upper")
        sy, shift = self._body(p, st, under)
        for side in ("l", "r"):
            if side not in up:
                self._arm(p, st, side, sy, "lower")
        self._head(p, st, shift)
        for side in up:                              # tay đưa lên mặt / đầu: vẽ đè lên đầu
            self._arm(p, st, side, sy, "lower")


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
