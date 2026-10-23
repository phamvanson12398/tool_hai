# -*- coding: utf-8 -*-
"""Khung xương và ghép bộ phận cho nhân vật vẽ bằng bộ ghép (Bước A).

Nhân vật vẽ bằng bộ ghép (core/character_kit.py) được tách thành các bộ
phận riêng, mỗi bộ phận là một ảnh PNG có điểm khớp (pivot). Các bộ phận
được ráp lại bằng phép xoay quanh khớp theo cây xương, đúng thứ tự lớp:
tay sau → chân → thân → đầu → tay trước.

Mỗi nhân vật có file `rig.json` mô tả cây xương:
  than → co → dau
  than → vai → khuyu → co_tay   (hai bên)
  than → dui → goi → co_chan     (hai bên)

Module này độc lập, CHƯA gắn vào luồng dựng chính.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from . import character_kit as ck
from .character_kit import CharSpec
from .gestures import (Gesture, breathe_angles, effect_angles,  # noqa: E402
                       ensure_library, fade_pose, gesture_pose, idle_arm_angles,
                       stable_seed)

# Khung vẽ bộ phận. Bộ phận được vẽ trên canvas 2x cho rộng rãi, khi
# xoay quanh khớp sẽ không bị cắt.
CW, CH = 600, 1000
PAD_X, PAD_Y = 300, 500          # lề thêm quanh khung gốc
PART_W, PART_H = CW + PAD_X * 2, CH + PAD_Y * 2

OUTLINE = (30, 30, 30, 255)
LW = 5
PANTS = (66, 70, 96, 255)
STICK_LW = 14                     # độ dày nét người que
STICK_INK = (34, 30, 40, 255)
SHOE = (48, 48, 60, 255)

# Thứ tự lớp: tay sau, chân, thân, đầu, tay trước
LAYER_TAY_SAU = 0
LAYER_CHAN = 1
LAYER_THAN = 2
LAYER_DAU = 3
LAYER_TAY_TRUOC = 4

LAYER_NAMES = {
    LAYER_TAY_SAU: "tay_sau",
    LAYER_CHAN: "chan",
    LAYER_THAN: "than",
    LAYER_DAU: "dau",
    LAYER_TAY_TRUOC: "tay_truoc",
}


# ------------------------------------------------------------------ hình học

@dataclass(frozen=True)
class Geometry:
    """Toạ độ khớp trong khung gốc 600x1000."""
    head_cx: int
    head_cy: int
    head_rx: int
    head_ry: int
    shoulder_y: int
    body_w: int
    body_h: int
    shoulder_dx: float
    arm_w: int
    upper_len: float
    fore_len: float
    hand_r: int
    hip_dx: float
    thigh_w: int
    thigh_len: float
    shin_len: float
    foot_w: int

    @property
    def hip(self) -> tuple[float, float]:
        return (float(self.head_cx), float(self.shoulder_y + self.body_h))

    @property
    def neck(self) -> tuple[float, float]:
        """Khớp cổ: giữa hai vai."""
        return (float(self.head_cx), float(self.shoulder_y))

    @property
    def chin(self) -> tuple[float, float]:
        """Điểm bám của đầu (dưới cằm)."""
        return (float(self.head_cx), float(self.head_cy + self.head_ry - 5))


def geometry(body: str = "adult", style: str = "flat") -> Geometry:
    """Tỉ lệ xương, bám theo _geom() của character_kit để ảnh khớp nhau.

    style="stick": người que đầu to — tay, chân mọc từ một đường thân.
    """
    if style == "gray":
        # kiểu TikTok Mỹ: đầu tròn xám to, thân mảnh dài, tay chân thon
        if body == "child":
            cy, rx, ry, sy, bh, bw = 270, 135, 128, 420, 210, 62
            up, fo, th, sh = 110.0, 100.0, 135.0, 125.0
        else:
            cy, rx, ry, sy, bh, bw = 205, 122, 116, 345, 290, 64
            up, fo, th, sh = 135.0, 125.0, 165.0, 150.0
        return Geometry(
            head_cx=300, head_cy=cy, head_rx=rx, head_ry=ry,
            shoulder_y=sy, body_w=bw, body_h=bh, shoulder_dx=bw * 0.32,
            arm_w=20, upper_len=up, fore_len=fo, hand_r=12,
            hip_dx=bw * 0.24, thigh_w=24, thigh_len=th, shin_len=sh, foot_w=26,
        )
    if style == "khand":
        # vẽ tay kiểu meme Hàn: đầu to có tai, bụng tròn, tay chân mũm mĩm
        if body == "child":
            cy, rx, ry, sy, bh, bw = 280, 160, 152, 455, 190, 190
            up, fo, th, sh = 92.0, 84.0, 95.0, 90.0
        else:
            cy, rx, ry, sy, bh, bw = 250, 150, 142, 420, 260, 220
            up, fo, th, sh = 115.0, 105.0, 112.0, 102.0
        return Geometry(
            head_cx=300, head_cy=cy, head_rx=rx, head_ry=ry,
            shoulder_y=sy, body_w=bw, body_h=bh, shoulder_dx=bw / 2 - 16,
            arm_w=46, upper_len=up, fore_len=fo, hand_r=27,
            hip_dx=bw * 0.24, thigh_w=60, thigh_len=th, shin_len=sh, foot_w=84,
        )
    if style == "kchibi":
        # webtoon Hàn: đầu rất to (gần nửa người), thân ngắn mũm mĩm
        if body == "child":
            cy, rx, ry, sy, bh, bw = 300, 185, 170, 480, 170, 180
            up, fo, th, sh = 80.0, 72.0, 95.0, 90.0
        else:
            cy, rx, ry, sy, bh, bw = 290, 180, 165, 470, 210, 200
            up, fo, th, sh = 95.0, 85.0, 110.0, 100.0
        return Geometry(
            head_cx=300, head_cy=cy, head_rx=rx, head_ry=ry,
            shoulder_y=sy, body_w=bw, body_h=bh, shoulder_dx=bw / 2 - 14,
            arm_w=44, upper_len=up, fore_len=fo, hand_r=26,
            hip_dx=bw * 0.22, thigh_w=54, thigh_len=th, shin_len=sh, foot_w=78,
        )
    if style == "box":
        # người que mặc áo: đầu tròn to như người que, thân hình hộp
        if body == "child":
            cy, r, sy, bh, bw = 280, 150, 470, 190, 140
            up, fo, th, sh = 100.0, 90.0, 135.0, 125.0
        else:
            cy, r, sy, bh, bw = 215, 125, 390, 250, 150
            up, fo, th, sh = 120.0, 110.0, 150.0, 140.0
        return Geometry(
            head_cx=300, head_cy=cy, head_rx=r, head_ry=r,
            shoulder_y=sy, body_w=bw, body_h=bh, shoulder_dx=bw / 2 - 9,
            arm_w=34, upper_len=up, fore_len=fo, hand_r=20,
            hip_dx=bw * 0.2, thigh_w=40, thigh_len=th, shin_len=sh, foot_w=60,
        )
    if style == "stick":
        if body == "child":
            head_cy, r, shoulder_y, body_h = 280, 155, 480, 190
            upper, fore, thigh, shin = 105.0, 95.0, 140.0, 135.0
        else:
            head_cy, r, shoulder_y, body_h = 215, 130, 400, 250
            upper, fore, thigh, shin = 125.0, 115.0, 150.0, 145.0
        return Geometry(
            head_cx=300, head_cy=head_cy, head_rx=r, head_ry=r,
            shoulder_y=shoulder_y, body_w=0, body_h=body_h,
            shoulder_dx=34.0, arm_w=STICK_LW, upper_len=upper, fore_len=fore,
            hand_r=19, hip_dx=4.0, thigh_w=STICK_LW, thigh_len=thigh,
            shin_len=shin, foot_w=54,
        )
    if body == "child":
        head_cx, head_cy, head_rx, head_ry = 300, 300, 150, 160
        shoulder_y, body_w, body_h = 470, 300, 420
    else:
        head_cx, head_cy, head_rx, head_ry = 300, 250, 124, 140
        shoulder_y, body_w, body_h = 400, 330, 520

    return Geometry(
        head_cx=head_cx, head_cy=head_cy, head_rx=head_rx, head_ry=head_ry,
        shoulder_y=shoulder_y, body_w=body_w, body_h=body_h,
        shoulder_dx=body_w / 2 - 4,
        arm_w=64 if body == "adult" else 58,
        upper_len=150.0, fore_len=140.0, hand_r=30,
        hip_dx=52.0, thigh_w=76, thigh_len=150.0, shin_len=150.0, foot_w=76,
    )


def _char_geom(g: Geometry) -> dict:
    """dict hình học mà các hàm vẽ của character_kit cần."""
    adult = g.head_cy == 250
    return {
        "head_cx": g.head_cx, "head_cy": g.head_cy,
        "head_rx": g.head_rx, "head_ry": g.head_ry,
        "neck_w": 52 if adult else 56,
        "shoulder_y": g.shoulder_y, "body_w": g.body_w, "body_h": g.body_h,
        "eye_dx": 48 if adult else 58,
        "eye_y": g.head_cy + (8 if adult else 10),
        "eye_r": 18 if adult else 22,
        "mouth_y": g.head_cy + (76 if adult else 90),
        "brow_y": g.head_cy + (-36 if adult else -38),
    }


# ------------------------------------------------------------------ vẽ bộ phận

def _blend(a: float) -> float:
    """0 khi góc nhỏ (giữ tư thế đứng), 1 khi góc từ 40° trở lên."""
    u = min(1.0, abs(a) / math.radians(40))
    return u * u * (3 - 2 * u)


def _new_canvas() -> Image.Image:
    """Canvas rộng rãi để vẽ và xoay không bị cắt."""
    return Image.new("RGBA", (PART_W, PART_H), (0, 0, 0, 0))


def _p(canvas_xy: tuple[float, float]) -> tuple[float, float]:
    """Đổi toạ độ khung gốc sang toạ độ canvas có lề."""
    return (canvas_xy[0] + PAD_X, canvas_xy[1] + PAD_Y)


def _crop_pivot(img: Image.Image, pivot_canvas: tuple[float, float]
                ) -> tuple[Image.Image, tuple[float, float]]:
    """Cắt ảnh theo bbox, giữ pivot tương đối đúng trong ảnh đã cắt."""
    bbox = img.getbbox()
    if bbox is None:
        return img, pivot_canvas
    cropped = img.crop(bbox)
    pivot = (pivot_canvas[0] - bbox[0], pivot_canvas[1] - bbox[1])
    return cropped, pivot


def draw_torso(spec: CharSpec, g: Geometry) -> Image.Image:
    """Thân + áo. Pivot ở hông (để xoay cả người quanh hông)."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    shirt = ck.SHIRT_COLORS.get(spec.shirt, ck.SHIRT_COLORS["blue"]) + (255,)
    cx = g.head_cx
    bottom = int(g.hip[1]) + 40
    d.rounded_rectangle(
        [_p((cx - g.body_w // 2, g.shoulder_y))[0], _p((0, g.shoulder_y))[1],
         _p((cx + g.body_w // 2, bottom))[0], _p((0, bottom))[1]],
        radius=60, fill=shirt, outline=OUTLINE, width=LW,
    )
    return img


def draw_neck(spec: CharSpec, g: Geometry) -> Image.Image:
    """Cổ. Pivot ở khớp cổ (giữa hai vai)."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    skin = ck.SKIN_TONES.get(spec.skin, ck.SKIN_TONES["light"]) + (255,)
    cx = g.head_cx
    x0, y0 = _p((cx - 26, g.chin[1] - 10))
    x1, y1 = _p((cx + 26, g.shoulder_y + 24))
    d.rounded_rectangle([x0, y0, x1, y1], radius=18, fill=skin,
                        outline=OUTLINE, width=LW)
    return img


def draw_head(spec: CharSpec, g: Geometry, mouth_open: bool,
              expression: str = "neutral", face: bool = True) -> Image.Image:
    """Đầu (tóc + mặt + phụ kiện). Pivot ở chỗ cổ bám vào.

    Tóc dài vẽ SAU mặt, mũ tóc vẽ trên trán — không che mắt, miệng.
    Mặt vẽ theo biểu cảm (mắt, mày, miệng như ảnh tĩnh của bộ ghép).
    """
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    cg = _char_geom(g)
    mood = ck.EXPRESSION_MAP.get("neutral", ck.EXPRESSION_MAP["neutral"])
    cx, cy = g.head_cx, g.head_cy
    rx, ry = g.head_rx, g.head_ry
    col = ck.HAIR_COLORS.get(spec.hair_color, ck.HAIR_COLORS["black"]) + (255,)

    def S(x, y):
        return _p((x, y))

    def rect(x0, y0, x1, y1):
        a, b = S(x0, y0)
        c, e = S(x1, y1)
        return [a, b, c, e]

    def ell(x0, y0, x1, y1):
        a, b = S(x0, y0)
        c, e = S(x1, y1)
        return [a, b, c, e]

    def pie(x0, y0, x1, y1):
        a, b = S(x0, y0)
        c, e = S(x1, y1)
        return [a, b, c, e]

    st = spec.hair_style

    # 1. tóc sau đầu (vẽ trước để mặt đè lên)
    if st in ("long", "wavy"):
        # webtoon đầu to: tóc dài tới vai thôi, không che hết thân
        hair_end = cy + ry * (1.15 if spec.style == "kchibi" else 1.8)
        d.rounded_rectangle(rect(cx - rx - 12, cy - ry * 0.5,
                                 cx + rx + 12, hair_end),
                            radius=70, fill=col, outline=OUTLINE, width=LW)
    elif st == "ponytail":
        d.ellipse(ell(cx + rx - 14, cy - ry * 0.2, cx + rx + 86, cy + ry * 1.1),
                  fill=col, outline=OUTLINE, width=LW)
    elif st == "twintails":
        for sgn in (-1, 1):
            x = cx + sgn * (rx + 30)
            d.ellipse(ell(x - 46, cy - ry * 0.1, x + 46, cy + ry * 1.0),
                      fill=col, outline=OUTLINE, width=LW)
    elif st == "bun":
        d.ellipse(ell(cx - 52, cy - ry - 78, cx + 52, cy - ry + 20),
                  fill=col, outline=OUTLINE, width=LW)

    # 2. mặt
    d.ellipse(ell(cx - rx, cy - ry, cx + rx, cy + ry),
              fill=ck.SKIN_TONES.get(spec.skin, ck.SKIN_TONES["light"]) + (255,),
              outline=OUTLINE, width=LW)

    # 3. mũ tóc (trán)
    if st == "buzz":
        d.pieslice(pie(cx - rx, cy - ry, cx + rx, cy + ry * 0.2),
                   180, 360, fill=col, outline=OUTLINE, width=LW)
    elif st == "bowl":
        d.pieslice(pie(cx - rx - 10, cy - ry - 14, cx + rx + 10, cy + ry * 0.36),
                   180, 360, fill=col, outline=OUTLINE, width=LW)
        d.rectangle(rect(cx - rx - 10, cy - ry * 0.32, cx + rx + 10, cy - ry * 0.22), fill=col)
    elif st == "curly":
        d.pieslice(pie(cx - rx - 6, cy - ry - 10, cx + rx + 6, cy - ry * 0.25),
                   180, 360, fill=col, outline=OUTLINE, width=LW)
        for i in range(7):
            a = math.pi * (0.08 + 0.14 * i)
            x = cx - math.cos(a) * (rx + 6)
            y = cy - math.sin(a) * (ry + 6)
            d.ellipse(ell(x - 34, y - 34, x + 34, y + 34), fill=col,
                      outline=OUTLINE, width=max(2, LW - 3))
    elif spec.style == "kchibi":
        # tóc webtoon: mái dày phủ tới gần lông mày, mái cắt răng cưa, tóc mai hai bên
        edge = cy - ry * 0.3
        bottom = 2 * edge - (cy - ry - 14)
        d.pieslice(pie(cx - rx - 10, cy - ry - 14, cx + rx + 10, bottom),
                   180, 360, fill=col, outline=OUTLINE, width=LW)
        n = 6
        for i in range(n):
            x0 = cx - rx * 0.8 + i * rx * 1.6 / n
            x1 = x0 + rx * 1.6 / n
            d.polygon([S(x0, edge - 2), S(x1, edge - 2), S((x0 + x1) / 2, edge + ry * 0.12)],
                      fill=col)
        for sgn in (-1, 1):
            x = cx + sgn * (rx - 6)
            d.rounded_rectangle(rect(x - 20, edge - 20, x + 20, cy + ry * 0.3),
                                radius=16, fill=col, outline=OUTLINE, width=LW - 2)
        if st == "sidepart":
            d.polygon([S(cx - rx * 0.9, edge), S(cx + rx * 0.3, cy - ry - 8),
                       S(cx + rx * 0.9, edge - ry * 0.25), S(cx - rx * 0.2, edge + ry * 0.05)],
                      fill=col, outline=OUTLINE)
        if st == "bob":
            for sgn in (-1, 1):
                x = cx + sgn * rx
                d.rounded_rectangle(rect(x - 50, cy - ry * 0.5, x + 46, cy + ry * 0.55),
                                    radius=24, fill=col, outline=OUTLINE, width=LW)
    else:
        d.pieslice(pie(cx - rx - 6, cy - ry - 10, cx + rx + 6, cy - ry * 0.30),
                   180, 360, fill=col, outline=OUTLINE, width=LW)
        if st == "sidepart":
            pts = [S(cx - rx, cy - ry * 0.3), S(cx + rx * 0.2, cy - ry - 4),
                   S(cx + rx, cy - ry * 0.5), S(cx - rx * 0.4, cy - ry * 0.1)]
            d.polygon(pts, fill=col, outline=OUTLINE)
        if st == "bob":
            for sgn in (-1, 1):
                x = cx + sgn * rx
                d.rounded_rectangle(rect(x - 46, cy - ry * 0.5, x + 46, cy + ry * 0.6),
                                    radius=24, fill=col, outline=OUTLINE, width=LW)

    # 4. chi tiết mặt theo biểu cảm + phụ kiện (cùng bộ vẽ với ảnh tĩnh)
    if face:
        _draw_face(img, spec, g, expression, mouth_open, accessories=True)
    return img


def draw_upper_arm(spec: CharSpec, g: Geometry, side: str) -> Image.Image:
    """Cánh tay trên (vai → khuỷu). Pivot ở vai."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    shirt = ck.SHIRT_COLORS.get(spec.shirt, ck.SHIRT_COLORS["blue"]) + (255,)
    sx = g.head_cx + (g.shoulder_dx if side == "right" else -g.shoulder_dx)
    sy = g.shoulder_y
    x0, y0 = _p((sx - g.arm_w // 2, sy))
    x1, y1 = _p((sx + g.arm_w // 2, sy + g.upper_len))
    d.rounded_rectangle([x0, y0, x1, y1], radius=30, fill=shirt,
                        outline=OUTLINE, width=LW)
    return img


def draw_forearm(spec: CharSpec, g: Geometry, side: str) -> Image.Image:
    """Cẳng tay (khuỷu → cổ tay). Pivot ở khuỷu."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    shirt = ck.SHIRT_COLORS.get(spec.shirt, ck.SHIRT_COLORS["blue"]) + (255,)
    sx = g.head_cx + (g.shoulder_dx if side == "right" else -g.shoulder_dx)
    ey = g.shoulder_y + g.upper_len
    w = g.arm_w - 6
    x0, y0 = _p((sx - w // 2, ey))
    x1, y1 = _p((sx + w // 2, ey + g.fore_len))
    d.rounded_rectangle([x0, y0, x1, y1], radius=26, fill=shirt,
                        outline=OUTLINE, width=LW)
    return img


def draw_hand(spec: CharSpec, g: Geometry, side: str) -> Image.Image:
    """Bàn tay. Pivot ở cổ tay."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    skin = ck.SKIN_TONES.get(spec.skin, ck.SKIN_TONES["light"]) + (255,)
    sx = g.head_cx + (g.shoulder_dx if side == "right" else -g.shoulder_dx)
    wy = g.shoulder_y + g.upper_len + g.fore_len
    r = g.hand_r
    x0, y0 = _p((sx - r, wy - r // 2))
    x1, y1 = _p((sx + r, wy + r))
    d.ellipse([x0, y0, x1, y1], fill=skin, outline=OUTLINE, width=LW)
    return img


def draw_thigh(spec: CharSpec, g: Geometry, side: str) -> Image.Image:
    """Đùi (hông → gối). Pivot ở hông."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    hx = g.head_cx + (g.hip_dx if side == "right" else -g.hip_dx)
    hy = g.hip[1]
    x0, y0 = _p((hx - g.thigh_w // 2, hy))
    x1, y1 = _p((hx + g.thigh_w // 2, hy + g.thigh_len))
    d.rounded_rectangle([x0, y0, x1, y1], radius=30, fill=PANTS,
                        outline=OUTLINE, width=LW)
    return img


def draw_shin(spec: CharSpec, g: Geometry, side: str) -> Image.Image:
    """Cẳng chân (gối → cổ chân). Pivot ở gối."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    hx = g.head_cx + (g.hip_dx if side == "right" else -g.hip_dx)
    ky = g.hip[1] + g.thigh_len
    w = g.thigh_w - 10
    x0, y0 = _p((hx - w // 2, ky))
    x1, y1 = _p((hx + w // 2, ky + g.shin_len))
    d.rounded_rectangle([x0, y0, x1, y1], radius=26, fill=PANTS,
                        outline=OUTLINE, width=LW)
    return img


def draw_foot(spec: CharSpec, g: Geometry, side: str) -> Image.Image:
    """Bàn chân. Pivot ở cổ chân."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    hx = g.head_cx + (g.hip_dx if side == "right" else -g.hip_dx)
    ay = g.hip[1] + g.thigh_len + g.shin_len
    w = g.foot_w
    x0, y0 = _p((hx - w // 2, ay - 14))
    x1, y1 = _p((hx + w // 2, ay + 30))
    d.rounded_rectangle([x0, y0, x1, y1], radius=18, fill=SHOE,
                        outline=OUTLINE, width=LW)
    return img


# ------------------------------------------------------------------ người que

def _stick_line(d: ImageDraw.ImageDraw, a, b, width: int = STICK_LW,
                fill=STICK_INK) -> None:
    """Nét thẳng đầu tròn (toạ độ khung gốc)."""
    pa, pb = _p(a), _p(b)
    d.line([pa, pb], fill=fill, width=width)
    r = width / 2
    for x, y in (pa, pb):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def _face_geom(g: Geometry, spec: CharSpec) -> dict:
    """dict hình học cho các hàm vẽ mặt của character_kit."""
    if spec.style == "kchibi":
        rx, ry, cy = g.head_rx, g.head_ry, g.head_cy
        return {
            "head_cx": g.head_cx, "head_cy": cy, "head_rx": rx, "head_ry": ry,
            "neck_w": 36, "shoulder_y": g.shoulder_y, "body_w": g.body_w,
            "body_h": g.body_h, "eye_dx": int(rx * 0.36), "eye_y": int(cy + ry * 0.12),
            "eye_r": int(rx * 0.09), "mouth_y": int(cy + ry * 0.45),
            "brow_y": int(cy - ry * 0.12),
        }
    if spec.style in ("stick", "box", "gray", "khand"):
        r = g.head_rx
        return {
            "head_cx": g.head_cx, "head_cy": g.head_cy,
            "head_rx": r, "head_ry": r, "neck_w": STICK_LW,
            "shoulder_y": g.shoulder_y, "body_w": 0, "body_h": g.body_h,
            "eye_dx": int(r * 0.38), "eye_y": int(g.head_cy - r * 0.05),
            "eye_r": int(r * 0.17), "mouth_y": int(g.head_cy + r * 0.42),
            "brow_y": int(g.head_cy - r * 0.38),
        }
    return _char_geom(g)


def _draw_face(img: Image.Image, spec: CharSpec, g: Geometry, expression: str,
               mouth_open: bool, accessories: bool) -> None:
    """Mắt, mày, miệng, má hồng/mồ hôi/nước mắt theo biểu cảm (bộ vẽ của
    character_kit), vẽ trên lớp riêng rồi đặt vào canvas có lề."""
    mood = ck.EXPRESSION_MAP.get(expression, ck.EXPRESSION_MAP["neutral"])
    fg = _face_geom(g, spec)
    layer = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ck._draw_brows(d, fg, mood["brow"])
    ck._draw_eyes(d, spec, fg, mood["eye"])
    ck._draw_mouth(d, fg, mood["mouth"], mouth_open)
    extras_spec = spec if accessories else CharSpec.from_dict({**spec.to_dict(), "accessory": "none"})
    ck._draw_extras(d, extras_spec, fg, mood)
    img.alpha_composite(layer, (PAD_X, PAD_Y))


def _stick_head(spec: CharSpec, g: Geometry, mouth_open: bool,
                expression: str) -> Image.Image:
    """Đầu người que: hình tròn to, tóc vẽ nguệch ngoạc, mặt theo biểu cảm."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    cx, cy, r = g.head_cx, g.head_cy, g.head_rx
    col = ck.HAIR_COLORS.get(spec.hair_color, ck.HAIR_COLORS["black"]) + (255,)
    skin = ck.SKIN_TONES.get(spec.skin, ck.SKIN_TONES["light"]) + (255,)
    st = spec.hair_style
    hw = 13                                    # độ dày nét tóc

    def P(x, y):
        return _p((x, y))

    def on_head(deg, k=1.0):
        a = math.radians(deg)
        return (cx + math.cos(a) * r * k, cy - math.sin(a) * r * k)

    def strand(pts, width=hw):
        d.line([P(*q) for q in pts], fill=col, width=width, joint="curve")
        for q in (pts[0], pts[-1]):
            x, y = P(*q)
            d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=col)

    def top_arc(a0=200, a1=340, width=30, k=1.0):
        box = [P(cx - r * k, cy - r * k), P(cx + r * k, cy + r * k)]
        d.arc([box[0][0], box[0][1], box[1][0], box[1][1]], a0, a1, fill=col, width=width)

    # 1. tóc phía sau đầu
    if st in ("long", "wavy"):
        for sgn in (-1, 1):
            x0 = cx + sgn * r * 0.92
            pts = [(x0, cy - r * 0.2)]
            for i in range(1, 7):
                wig = (14 if i % 2 else -14) if st == "wavy" else 0
                pts.append((x0 + sgn * 12 + wig, cy - r * 0.2 + i * r * 0.27))
            strand(pts, 16)
    elif st == "ponytail":
        x, y = on_head(20, 1.0)
        d.ellipse([*P(x - 10, y - 30), *P(x + 90, y + 110)], outline=col, width=hw)
    elif st == "twintails":
        for sgn in (-1, 1):
            x = cx + sgn * (r + 40)
            d.ellipse([*P(x - 38, cy - 10), *P(x + 38, cy + 120)], outline=col, width=hw)
            bx, by = P(x - sgn * 34, cy - 4)          # nơ hồng
            d.polygon([(bx, by), (bx - 22, by - 14), (bx - 22, by + 14)], fill=(236, 120, 160, 255))
            d.polygon([(bx, by), (bx + 22, by - 14), (bx + 22, by + 14)], fill=(236, 120, 160, 255))
    elif st == "bun":
        x, y = on_head(90, 1.0)
        d.ellipse([*P(x - 44, y - 82), *P(x + 44, y + 6)], fill=col, outline=STICK_INK, width=6)

    # 2. đầu
    d.ellipse([*P(cx - r, cy - r), *P(cx + r, cy + r)], fill=skin,
              outline=STICK_INK, width=STICK_LW - 4)

    # 3. tóc phía trước (trên đỉnh đầu)
    if st == "short":
        for deg in (55, 75, 95, 115, 130):
            bx, by = on_head(deg, 0.97)
            tx, ty = on_head(deg + 8, 1.32)
            strand([(bx, by), (tx, ty)])
    elif st == "buzz":
        x, y = on_head(95, 0.98)
        strand([(x, y), (x + 14, y - 34), (x + 34, y - 26), (x + 22, y - 10)], 10)
    elif st == "sidepart":
        top_arc(150, 330, 34)
        strand([on_head(150, 1.0), on_head(120, 1.18), on_head(70, 1.12), on_head(30, 0.92)], 18)
    elif st == "bob":
        top_arc(180, 360, 34)
        for sgn in (-1, 1):
            x = cx + sgn * r * 0.96
            strand([(x, cy - r * 0.1), (x + sgn * 6, cy + r * 0.55)], 22)
    elif st in ("long", "wavy", "ponytail", "twintails", "bun"):
        top_arc(185, 355, 34)
        if st in ("long", "wavy"):
            strand([on_head(95, 1.0), on_head(115, 0.72), on_head(140, 0.62)], 14)
    elif st == "bowl":
        top_arc(150, 390, 44, 0.93)
        strand([on_head(160, 0.86), on_head(20, 0.86)], 16)
    elif st == "curly":
        for deg in range(30, 160, 18):
            x, y = on_head(deg, 1.05)
            d.ellipse([*P(x - 22, y - 22), *P(x + 22, y + 22)], outline=col, width=9)
    else:
        top_arc(200, 340, 30)

    # 4. mặt + phụ kiện
    _draw_face(img, spec, g, expression, mouth_open, accessories=True)
    return img


def _stick_torso(spec: CharSpec, g: Geometry) -> Image.Image:
    """Đường thân + cà vạt màu áo (để phân biệt nhân vật)."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    cx, sy = g.head_cx, g.shoulder_y
    _stick_line(d, (cx, sy - 14), g.hip)
    for sgn in (-1, 1):                      # vai ngắn để tay mọc ra hai bên
        _stick_line(d, (cx, sy - 14), (cx + sgn * g.shoulder_dx, sy))
    tie = ck.SHIRT_COLORS.get(spec.shirt, ck.SHIRT_COLORS["blue"]) + (255,)
    k = 0.8 if spec.body == "child" else 1.0
    pts = [(cx, sy + 4), (cx - 22 * k, sy + 34 * k), (cx, sy + 118 * k), (cx + 22 * k, sy + 34 * k)]
    d.polygon([_p(q) for q in pts], fill=tie, outline=STICK_INK)
    d.line([_p(q) for q in pts + [pts[0]]], fill=STICK_INK, width=4)
    return img


def _stick_neck(spec: CharSpec, g: Geometry) -> Image.Image:
    img = _new_canvas()
    _stick_line(ImageDraw.Draw(img), g.chin, (g.head_cx, g.shoulder_y))
    return img


def _stick_limb(g: Geometry, a, b) -> Image.Image:
    img = _new_canvas()
    _stick_line(ImageDraw.Draw(img), a, b)
    return img


def _stick_hand(spec: CharSpec, g: Geometry, side: str) -> Image.Image:
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    skin = ck.SKIN_TONES.get(spec.skin, ck.SKIN_TONES["light"]) + (255,)
    sx = g.head_cx + (g.shoulder_dx if side == "right" else -g.shoulder_dx)
    wy = g.shoulder_y + g.upper_len + g.fore_len
    r = g.hand_r
    d.ellipse([*_p((sx - r, wy - 4)), *_p((sx + r, wy + 2 * r - 4))], fill=skin,
              outline=STICK_INK, width=6)
    return img


def _stick_foot(spec: CharSpec, g: Geometry, side: str) -> Image.Image:
    """Bàn chân hình giày nhỏ, mũi giày chĩa ra ngoài."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    sgn = 1 if side == "right" else -1
    hx = g.head_cx + sgn * g.hip_dx
    ay = g.hip[1] + g.thigh_len + g.shin_len
    x0, x1 = (hx - 14, hx + g.foot_w) if sgn > 0 else (hx - g.foot_w, hx + 14)
    d.ellipse([*_p((x0, ay - 12)), *_p((x1, ay + 22))], fill=STICK_INK)
    return img


# ------------------------------------------------------- người que mặc áo / webtoon Hàn

OUTFIT_COLORS = {
    # (màu áo chính lấy từ spec.shirt; đây là màu phụ cố định của từng bộ)
    "school_uniform": {"jacket": (44, 58, 104), "shirt": (250, 250, 252), "tie": (196, 54, 64)},
    "suit": {"jacket": (58, 62, 74), "shirt": (250, 250, 252), "tie": None},
    "apron": {"apron": (248, 200, 210)},
    "hiking": {"trim": (40, 40, 48)},
}


def _sleeve_color(spec: CharSpec) -> tuple:
    """Màu tay áo theo trang phục."""
    main = ck.SHIRT_COLORS.get(spec.shirt, ck.SHIRT_COLORS["blue"]) + (255,)
    if spec.outfit == "school_uniform":
        return OUTFIT_COLORS["school_uniform"]["jacket"] + (255,)
    if spec.outfit == "suit":
        return OUTFIT_COLORS["suit"]["jacket"] + (255,)
    return main


def _short_sleeve(spec: CharSpec) -> bool:
    return spec.outfit in ("tshirt", "dress")


def _legs_bare(spec: CharSpec) -> bool:
    """Váy/hanbok: chân không mặc quần (váy vẽ ở thân)."""
    return spec.outfit in ("dress", "hanbok")


def _box_torso(spec: CharSpec, g: Geometry) -> Image.Image:
    """Thân hình hộp mặc trang phục. Pivot ở hông."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    main = ck.SHIRT_COLORS.get(spec.shirt, ck.SHIRT_COLORS["blue"]) + (255,)
    cx = g.head_cx
    hw = g.body_w / 2
    top = g.shoulder_y - 12
    bot = g.hip[1] + 26
    rad = 34 if spec.style == "kchibi" else 22
    lw = LW + 1

    def R(x0, y0, x1, y1, fill, r=rad, outline=OUTLINE, width=lw):
        d.rounded_rectangle([*_p((x0, y0)), *_p((x1, y1))], radius=r, fill=fill,
                            outline=outline, width=width)

    def L(pts, fill=OUTLINE, width=lw):
        d.line([_p(q) for q in pts], fill=fill, width=width)

    def poly(pts, fill, outline=OUTLINE):
        d.polygon([_p(q) for q in pts], fill=fill, outline=outline)

    o = spec.outfit
    if o == "dress":
        poly([(cx - hw, top + 10), (cx + hw, top + 10), (cx + hw * 1.45, bot + 70),
              (cx - hw * 1.45, bot + 70)], main)
        R(cx - hw, top, cx + hw, top + (bot - top) * 0.45, main)
        L([(cx - hw * 0.4, top + 4), (cx, top + 30), (cx + hw * 0.4, top + 4)], width=5)
        return img
    if o == "hanbok":
        skirt = _shade4(main, 0.8)
        poly([(cx - hw * 0.9, top + (bot - top) * 0.35), (cx + hw * 0.9, top + (bot - top) * 0.35),
              (cx + hw * 1.6, bot + 90), (cx - hw * 1.6, bot + 90)], skirt)
        R(cx - hw, top, cx + hw, top + (bot - top) * 0.42, (250, 246, 236, 255))   # áo jeogori
        poly([(cx - 8, top + 30), (cx + 40, top + 60), (cx + 10, top + 64)], (210, 60, 90, 255))  # dải nơ
        L([(cx - hw * 0.5, top + 2), (cx + 6, top + 56)], width=6)
        return img

    jacket_like = o in ("school_uniform", "suit", "cardigan", "hiking", "padding")
    base = main
    if o in ("school_uniform", "suit"):
        base = OUTFIT_COLORS[o]["jacket"] + (255,)
    R(cx - hw, top, cx + hw, bot, base)
    if o == "padding":                                   # áo phao dài: vạch chần ngang
        R(cx - hw - 6, top, cx + hw + 6, bot + 70, base)
        for i in range(1, 6):
            y = top + (bot + 70 - top) * i / 6
            L([(cx - hw - 4, y), (cx + hw + 4, y)], fill=_shade4(base, 0.75), width=5)
        L([(cx, top + 8), (cx, bot + 66)], width=4)
        R(cx - hw * 0.7, top - 18, cx + hw * 0.7, top + 22, _shade4(base, 0.9), r=18)   # cổ áo
        return img
    if o in ("school_uniform", "suit"):
        oc = OUTFIT_COLORS[o]
        poly([(cx - hw * 0.42, top + 2), (cx + hw * 0.42, top + 2), (cx, top + (bot - top) * 0.55)],
             oc["shirt"] + (255,))
        tie = oc["tie"] + (255,) if oc["tie"] else main
        poly([(cx, top + 10), (cx - 14, top + 30), (cx, top + (bot - top) * 0.5),
              (cx + 14, top + 30)], tie)
        L([(cx - hw * 0.42, top + 2), (cx - 6, top + (bot - top) * 0.56)], width=5)
        L([(cx + hw * 0.42, top + 2), (cx + 6, top + (bot - top) * 0.56)], width=5)
        for k in (0.66, 0.8):
            d.ellipse([*_p((cx - 7, top + (bot - top) * k - 7)), *_p((cx + 7, top + (bot - top) * k + 7))],
                      fill=(230, 210, 120, 255))
        if o == "school_uniform":                          # phù hiệu túi ngực
            R(cx + hw * 0.35, top + (bot - top) * 0.32, cx + hw * 0.7, top + (bot - top) * 0.42,
              (230, 210, 120, 255), r=4, width=3)
    elif o == "hoodie":
        R(cx - hw * 0.75, top - 26, cx + hw * 0.75, top + 28, _shade4(main, 0.85), r=24)  # mũ trùm
        R(cx - hw * 0.55, top + (bot - top) * 0.55, cx + hw * 0.55, top + (bot - top) * 0.82,
          _shade4(main, 0.9), r=16, width=5)                                            # túi trước
        for sgn in (-1, 1):
            L([(cx + sgn * 18, top + 20), (cx + sgn * 22, top + 70)], fill=(250, 250, 250, 255), width=5)
    elif o == "apron":
        ac = OUTFIT_COLORS["apron"]["apron"] + (255,)
        R(cx - hw * 0.72, top + 22, cx + hw * 0.72, bot + 40, ac, r=18, width=5)
        L([(cx - hw * 0.5, top + 24), (cx - hw * 0.2, top - 6)], width=5)
        L([(cx + hw * 0.5, top + 24), (cx + hw * 0.2, top - 6)], width=5)
        R(cx - hw * 0.35, top + (bot - top) * 0.55, cx + hw * 0.35, top + (bot - top) * 0.8,
          _shade4(ac, 0.9), r=8, width=4)
        for k in range(5):                                 # hoa nhỏ
            x = cx - hw * 0.5 + k * hw * 0.25
            y = top + 50 + (k % 2) * 34
            d.ellipse([*_p((x - 7, y - 7)), *_p((x + 7, y + 7))], fill=(236, 110, 140, 255))
    elif o == "hiking":
        trim = OUTFIT_COLORS["hiking"]["trim"] + (255,)
        R(cx - hw, top + (bot - top) * 0.45, cx + hw, top + (bot - top) * 0.6, trim, r=6, width=4)
        L([(cx, top + 6), (cx, bot - 4)], fill=trim, width=6)                           # khoá kéo
        R(cx - hw * 0.5, top - 16, cx + hw * 0.5, top + 18, _shade4(main, 0.85), r=10)  # cổ đứng
    elif o == "cardigan":
        inner = (250, 248, 240, 255)
        R(cx - hw * 0.3, top + 4, cx + hw * 0.3, bot - 2, inner, r=10, width=4)
        for k in (0.3, 0.5, 0.7):
            d.ellipse([*_p((cx + hw * 0.36 - 6, top + (bot - top) * k - 6)),
                       *_p((cx + hw * 0.36 + 6, top + (bot - top) * k + 6))], fill=OUTLINE)
    else:  # tshirt
        L([(cx - hw * 0.35, top + 2), (cx, top + 28), (cx + hw * 0.35, top + 2)], width=5)
    if not jacket_like and o != "apron":
        pass
    return img


def _shade4(c, k: float) -> tuple:
    return tuple(max(0, min(255, int(v * k))) for v in c[:3]) + (255,)


def _box_neck(spec: CharSpec, g: Geometry) -> Image.Image:
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    skin = ck.SKIN_TONES.get(spec.skin, ck.SKIN_TONES["light"]) + (255,)
    cx = g.head_cx
    d.rounded_rectangle([*_p((cx - 18, g.chin[1] - 20)), *_p((cx + 18, g.shoulder_y + 6))],
                        radius=10, fill=skin, outline=OUTLINE, width=LW)
    return img


def _box_limb(g: Geometry, a, b, w: float, fill) -> Image.Image:
    """Tay/chân dày: thanh bo tròn từ a tới b (khung gốc, thẳng đứng)."""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    x = a[0]
    d.rounded_rectangle([*_p((x - w / 2, a[1] - w * 0.3)), *_p((x + w / 2, b[1] + w * 0.3))],
                        radius=int(w / 2), fill=fill, outline=OUTLINE, width=LW)
    return img


def _box_parts(spec: CharSpec, g: Geometry) -> dict:
    skin = ck.SKIN_TONES.get(spec.skin, ck.SKIN_TONES["light"]) + (255,)
    sleeve = _sleeve_color(spec)
    pants = ck.PANTS_COLORS.get(spec.pants, ck.PANTS_COLORS["navy"]) + (255,)
    leg_fill = skin if _legs_bare(spec) else pants
    leg_w = g.thigh_w * (0.55 if _legs_bare(spec) else 1.0)

    def sx(gg, side):
        return gg.head_cx + (gg.shoulder_dx if side == "right" else -gg.shoulder_dx)

    def hx(gg, side):
        return gg.head_cx + (gg.hip_dx if side == "right" else -gg.hip_dx)

    def upper(sp, gg, side):
        x = sx(gg, side)
        return _box_limb(gg, (x, gg.shoulder_y), (x, gg.shoulder_y + gg.upper_len), gg.arm_w, sleeve)

    def fore(sp, gg, side):
        x = sx(gg, side)
        ey = gg.shoulder_y + gg.upper_len
        fill = skin if _short_sleeve(sp) else sleeve
        return _box_limb(gg, (x, ey), (x, ey + gg.fore_len), gg.arm_w * 0.9, fill)

    def hand(sp, gg, side):
        img = _new_canvas()
        d = ImageDraw.Draw(img)
        x = sx(gg, side)
        wy = gg.shoulder_y + gg.upper_len + gg.fore_len
        r = gg.hand_r
        d.ellipse([*_p((x - r, wy - r * 0.4)), *_p((x + r, wy + r * 1.5))], fill=skin,
                  outline=OUTLINE, width=LW)
        return img

    def thigh(sp, gg, side):
        x = hx(gg, side)
        return _box_limb(gg, (x, gg.hip[1]), (x, gg.hip[1] + gg.thigh_len), leg_w, leg_fill)

    def shin(sp, gg, side):
        x = hx(gg, side)
        ky = gg.hip[1] + gg.thigh_len
        return _box_limb(gg, (x, ky), (x, ky + gg.shin_len), leg_w * 0.92, leg_fill)

    def foot(sp, gg, side):
        img = _new_canvas()
        d = ImageDraw.Draw(img)
        sgn = 1 if side == "right" else -1
        x = hx(gg, side)
        ay = gg.hip[1] + gg.thigh_len + gg.shin_len
        x0, x1 = (x - gg.foot_w * 0.45, x + gg.foot_w * 0.75) if sgn > 0 else \
            (x - gg.foot_w * 0.75, x + gg.foot_w * 0.45)
        shoe = (250, 250, 250, 255) if spec.outfit in ("hoodie", "padding") else SHOE
        d.rounded_rectangle([*_p((x0, ay - 10)), *_p((x1, ay + 26))], radius=14, fill=shoe,
                            outline=OUTLINE, width=LW)
        return img

    head = _stick_head if spec.style == "box" else _kchibi_head
    return {"torso": _box_torso, "neck": _box_neck, "head": head,
            "upper": upper, "fore": fore, "hand": hand,
            "thigh": thigh, "shin": shin, "foot": foot}


# ---------- mặt kiểu webtoon Hàn: ^^  ㅠㅠ  -_-  mắt trắng dã, nổi gân 💢, ///

KCHIBI_FACE = {
    # biểu cảm -> (mắt, mày, thêm)
    "neutral": ("dot", "flat", ""),
    "happy": ("arc_up", "up", ""),
    "laughing": ("x_squint", "up", ""),
    "proud": ("half", "up", ""),
    "smug": ("half", "slant", ""),
    "sad": ("dot_down", "worry", "tear"),
    "crying": ("tt", "worry", "rivers"),
    "angry": ("dot", "angry", "vein"),
    "annoyed": ("line", "angry", "sweat"),
    "shocked": ("blank", "up", "shock"),
    "surprised": ("big", "up", ""),
    "scared": ("blank", "worry", "shock_sweat"),
    "worried": ("dot", "worry", "sweat"),
    "confused": ("odd", "slant", "question"),
    "thinking": ("dot_up", "flat", ""),
    "suspicious": ("line", "slant", ""),
    "disgusted": ("line", "angry", "gloom"),
    "embarrassed": ("x_squint", "worry", "lines"),
    "shy": ("arc_up", "worry", "lines"),
    "love": ("heart", "up", ""),
    "determined": ("dot", "angry", "fire"),
    "tired": ("line", "down", "gloom"),
    "bored": ("line", "flat", ""),
}


def _kchibi_face(d: ImageDraw.ImageDraw, spec: CharSpec, fg: dict, expression: str,
                 mouth_open: bool) -> None:
    eye, brow, extra = KCHIBI_FACE.get(expression, KCHIBI_FACE["neutral"])
    cx, ey, dx, r = fg["head_cx"], fg["eye_y"], fg["eye_dx"], fg["eye_r"]
    ink = OUTLINE
    white = (255, 255, 255, 255)
    blue = (120, 190, 240, 235)
    w = LW + 1
    # má hồng luôn có (dễ thương kiểu webtoon), đậm hơn khi ngượng/yêu
    blush = (245, 150, 160, 190 if expression in ("embarrassed", "shy", "love", "happy") else 110)
    for sgn in (-1, 1):
        x = cx + sgn * (dx + r * 1.6)
        d.ellipse([x - r * 1.3, ey + r * 1.3, x + r * 1.3, ey + r * 2.3], fill=blush)
        if extra == "lines":
            for k in (-1, 0, 1):
                d.line([x + k * 12 - 8, ey + r * 2.1, x + k * 12 + 4, ey + r * 1.4], fill=(220, 90, 110, 255), width=4)
    for sgn in (-1, 1):
        x = cx + sgn * dx
        if eye == "dot":
            d.ellipse([x - r * 0.55, ey - r * 0.8, x + r * 0.55, ey + r * 0.8], fill=ink)
        elif eye == "dot_down":
            d.ellipse([x - r * 0.5, ey - r * 0.4, x + r * 0.5, ey + r * 0.9], fill=ink)
        elif eye == "dot_up":
            d.ellipse([x - r * 0.5, ey - r * 1.0, x + r * 0.5, ey + r * 0.3], fill=ink)
        elif eye == "arc_up":                                  # ^ ^
            d.arc([x - r * 1.1, ey - r * 0.6, x + r * 1.1, ey + r * 1.4], 200, 340, fill=ink, width=w)
        elif eye == "x_squint":                                # > <
            k = -sgn
            d.line([x - r * k, ey - r * 0.8, x + r * k, ey, x - r * k, ey + r * 0.8], fill=ink, width=w)
        elif eye == "half":
            d.line([x - r, ey, x + r, ey], fill=ink, width=w)
            d.chord([x - r * 0.8, ey - r * 0.4, x + r * 0.8, ey + r * 1.0], 0, 180, fill=ink)
        elif eye == "line":                                    # - -
            d.line([x - r * 1.1, ey, x + r * 1.1, ey], fill=ink, width=w)
        elif eye == "tt":                                      # ㅠ ㅠ
            d.line([x - r * 1.2, ey - r * 0.5, x + r * 1.2, ey - r * 0.5], fill=ink, width=w)
            for k in (-0.5, 0.5):
                d.line([x + r * k, ey - r * 0.4, x + r * k, ey + r * 0.9], fill=ink, width=w)
        elif eye in ("blank", "big"):
            rr = r * (1.45 if eye == "blank" else 1.25)
            d.ellipse([x - rr, ey - rr, x + rr, ey + rr], fill=white, outline=ink, width=5)
            pr = r * (0.22 if eye == "blank" else 0.55)
            d.ellipse([x - pr, ey - pr, x + pr, ey + pr], fill=ink)
        elif eye == "odd":
            rr = r * (1.2 if sgn < 0 else 0.7)
            d.ellipse([x - rr * 0.6, ey - rr, x + rr * 0.6, ey + rr], fill=ink)
        elif eye == "heart":
            hc = (230, 70, 110, 255)
            for off in (-1, 1):
                d.ellipse([x + off * r * 0.45 - r * 0.6, ey - r * 0.7, x + off * r * 0.45 + r * 0.6, ey + r * 0.4], fill=hc)
            d.polygon([(x - r * 1.0, ey - r * 0.05), (x + r * 1.0, ey - r * 0.05), (x, ey + r * 1.1)], fill=hc)
    # lông mày
    by = fg["brow_y"]
    span = r * 1.3
    for sgn in (-1, 1):
        x = cx + sgn * dx
        if brow == "up":
            d.arc([x - span, by - 6, x + span, by + 24], 200, 340, fill=ink, width=w - 2)
        elif brow == "angry":
            d.line([x - span * sgn, by - 12, x + span * sgn, by + 14], fill=ink, width=w)
        elif brow == "worry":
            d.line([x - span * sgn, by + 12, x + span * sgn, by - 8], fill=ink, width=w - 1)
        elif brow == "down":
            d.line([x - span, by + 4, x + span, by + 12], fill=ink, width=w - 2)
        elif brow == "slant":
            d.line([x - span, by + (6 if sgn < 0 else -6), x + span, by + (-6 if sgn < 0 else 6)],
                   fill=ink, width=w - 2)
        else:
            d.line([x - span * 0.8, by + 4, x + span * 0.8, by + 4], fill=ink, width=w - 2)
    # miệng (bộ vẽ chung)
    mood = ck.EXPRESSION_MAP.get(expression, ck.EXPRESSION_MAP["neutral"])
    ck._draw_mouth(d, fg, mood["mouth"], mouth_open)
    # thêm thắt
    rx, ry, hcy = fg["head_rx"], fg["head_ry"], fg["head_cy"]
    if extra == "rivers":                                      # dòng nước mắt dài
        for sgn in (-1, 1):
            x = cx + sgn * dx
            d.rounded_rectangle([x - 10, ey + r * 0.8, x + 10, ey + r * 6.5], radius=10, fill=blue)
    if extra == "tear":
        x = cx + dx
        d.ellipse([x - 9, ey + r, x + 9, ey + r * 2.4], fill=blue)
    if extra in ("sweat", "shock_sweat"):
        x, y = cx + rx * 0.78, hcy - ry * 0.55
        d.polygon([(x, y), (x + 20, y + 36), (x - 20, y + 36)], fill=blue, outline=ink)
        d.ellipse([x - 20, y + 22, x + 20, y + 56], fill=blue, outline=ink, width=3)
    if extra in ("shock", "shock_sweat"):                     # vạch tím trên trán
        for k in range(-3, 4):
            x = cx + k * rx * 0.16
            d.line([x, hcy - ry * 0.95, x, hcy - ry * 0.55], fill=(110, 90, 170, 200), width=6)
    if extra == "gloom":
        for k in range(-3, 4):
            x = cx + k * rx * 0.16
            d.line([x, hcy - ry * 0.9, x, hcy - ry * 0.6], fill=(90, 90, 120, 160), width=4)
    if extra == "vein":                                        # dấu nổi gân 💢
        x, y = cx + rx * 0.58, hcy - ry * 0.55
        vc = (220, 50, 60, 255)
        for a0 in (0, 90, 180, 270):
            d.arc([x - 34, y - 34, x + 34, y + 34], a0 + 20, a0 + 70, fill=vc, width=11)
    if extra == "question":
        x, y = cx + rx * 0.95, hcy - ry * 0.95
        d.arc([x - 22, y - 24, x + 22, y + 16], 180, 90, fill=ink, width=8)
        d.line([x, y + 16, x, y + 30], fill=ink, width=8)
        d.ellipse([x - 5, y + 40, x + 5, y + 50], fill=ink)
    if extra == "fire":
        x, y = cx - rx * 0.8, hcy - ry * 0.8
        d.polygon([(x, y - 40), (x + 20, y), (x, y + 10), (x - 20, y)], fill=(250, 140, 60, 230))


def _kchibi_head(spec: CharSpec, g: Geometry, mouth_open: bool,
                 expression: str = "neutral") -> Image.Image:
    """Đầu webtoon Hàn: tóc khối như kiểu phẳng, mặt kiểu meme Hàn."""
    img = draw_head(spec, g, mouth_open, "neutral", face=False)
    fg = _face_geom(g, spec)
    layer = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    _kchibi_face(d, spec, fg, expression, mouth_open)
    # phụ kiện (kính, mũ, lô cuốn…) dùng chung bộ vẽ, không vẽ lại cảm xúc
    ck._draw_extras(d, spec, fg, {})
    img.alpha_composite(layer, (PAD_X, PAD_Y))
    return img


# ============================================================ nét mềm (gray, khand)
# Bộ phận chỉ vẽ phần màu; viền đen do RigRenderer tự tạo quanh từng nhóm
# bộ phận cùng lớp (xem _outline_img) nên khuỷu tay, đầu gối, cổ tay liền
# một khối như nét vẽ tay, không lộ đường nối.

SOFT_STYLES = ("gray", "khand")
SOFT_OUTLINE = 8                       # độ dày viền tự tạo (px, khung 600x1000)
GRAY_SKIN = (198, 198, 202, 255)
GRAY_DARK = (150, 150, 156, 255)
INK = (24, 22, 28, 255)


def _outline_img(img: Image.Image, k: int = SOFT_OUTLINE) -> Image.Image:
    """Bóng viền đen quanh hình (nở rộng k px), lề thêm k px mỗi bên."""
    import numpy as np
    import cv2
    a = np.array(img.getchannel("A"))
    a = np.pad(a, k)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    m = cv2.dilate((a > 40).astype(np.uint8) * 255, kernel)
    m = cv2.GaussianBlur(m, (3, 3), 0)                 # mép viền mượt
    out = np.zeros((*m.shape, 4), dtype=np.uint8)
    out[..., :3] = INK[:3]
    out[..., 3] = m
    return Image.fromarray(out, "RGBA")


def _taper(d: ImageDraw.ImageDraw, a, b, w0: float, w1: float, fill) -> None:
    """Khối thon từ a (rộng w0) tới b (rộng w1), hai đầu tròn — toạ độ khung gốc."""
    (ax, ay), (bx, by) = _p(a), _p(b)
    r0, r1 = w0 / 2, w1 / 2
    d.ellipse([ax - r0, ay - r0, ax + r0, ay + r0], fill=fill)
    d.ellipse([bx - r1, by - r1, bx + r1, by + r1], fill=fill)
    d.polygon([(ax - r0, ay), (ax + r0, ay), (bx + r1, by), (bx - r1, by)], fill=fill)


def _soft_line(d, pts, width=6, fill=INK) -> None:
    """Nét đen đầu tròn, đi qua nhiều điểm (khung gốc)."""
    q = [_p(x) for x in pts]
    d.line(q, fill=fill, width=width, joint="curve")
    for x, y in (q[0], q[-1]):
        d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=fill)


def _soft_skin(spec: CharSpec):
    if spec.style == "gray":
        return GRAY_SKIN
    return ck.SKIN_TONES.get(spec.skin, ck.SKIN_TONES["light"]) + (255,)


def _soft_hair_col(spec: CharSpec):
    if spec.style == "gray":
        return INK                        # kiểu TikTok Mỹ: tóc luôn đen khối
    return ck.HAIR_COLORS.get(spec.hair_color, ck.HAIR_COLORS["black"]) + (255,)


# ---------------------------------------------------------------- mặt

# biểu cảm -> (cỡ mắt, hướng nhìn x/y, mày, miệng)
GRAY_FACE = {
    "neutral": (1.0, (0.0, 0.0), "flat", "line"),
    "happy": (1.0, (0.0, 0.0), "up", "smile"),
    "laughing": (0.0, (0, 0), "up", "laugh"),
    "proud": (0.9, (0.3, 0.0), "up", "smirk"),
    "smug": (0.8, (0.45, 0.0), "slant", "smirk"),
    "sad": (1.0, (0.0, 0.35), "worry", "frown"),
    "crying": (1.0, (0.0, 0.3), "worry", "cry"),
    "angry": (0.85, (0.0, 0.0), "angry", "teeth"),
    "annoyed": (0.75, (0.5, 0.0), "angry", "line"),
    "shocked": (1.35, (0.0, 0.0), "up", "o"),
    "surprised": (1.25, (0.0, -0.1), "up", "o"),
    "scared": (1.3, (-0.4, 0.0), "worry", "teeth"),
    "worried": (1.0, (-0.3, 0.1), "worry", "wavy"),
    "confused": (1.0, (0.35, -0.35), "slant", "wavy"),
    "thinking": (1.0, (0.35, -0.45), "flat", "line"),
    "suspicious": (0.65, (0.55, 0.0), "slant", "line"),
    "disgusted": (0.7, (0.4, 0.1), "angry", "wavy"),
    "embarrassed": (0.9, (-0.45, 0.2), "worry", "wavy"),
    "shy": (0.9, (-0.4, 0.35), "worry", "small"),
    "love": (1.1, (0.0, 0.0), "up", "smile"),
    "determined": (0.85, (0.0, 0.0), "angry", "line"),
    "tired": (0.6, (0.0, 0.3), "down", "line"),
    "bored": (0.6, (0.5, 0.15), "flat", "line"),
}


def _face_mouth(d, cx, my, kind: str, mouth_open: bool, scale: float, lips=None) -> None:
    """Miệng chung: nét đen (gray) hoặc môi dày hồng (khand)."""
    s = scale
    dark = (70, 30, 36, 255)
    if mouth_open or kind in ("o", "laugh", "cry", "teeth"):
        w = (34 if kind in ("o",) else 46) * s
        h = (40 if kind in ("o", "laugh", "cry") else 26) * s
        if not mouth_open and kind == "teeth":
            h = 20 * s
        if lips:
            d.ellipse([cx - w - 14 * s, my - h / 2 - 12 * s, cx + w + 14 * s, my + h / 2 + 12 * s],
                      fill=lips, outline=INK, width=6)
        d.ellipse([cx - w, my - h / 2, cx + w, my + h / 2], fill=dark, outline=INK, width=5)
        if kind == "teeth":
            d.rectangle([cx - w * 0.7, my - h / 2 + 2, cx + w * 0.7, my - h / 2 + h * 0.35],
                        fill=(250, 250, 250, 255))
        if kind in ("laugh", "cry") or mouth_open:
            d.chord([cx - w * 0.6, my, cx + w * 0.6, my + h / 2 - 2], 0, 180, fill=(220, 100, 110, 255))
        return
    if lips:                                      # môi dày (khand)
        top = my - 18 * s
        bot = my + 20 * s if kind in ("smile", "smirk") else my + 16 * s
        d.ellipse([cx - 44 * s, top, cx + 44 * s, bot], fill=lips, outline=INK, width=6)
        if kind in ("smile", "smirk"):
            d.arc([cx - 30 * s, my - 14 * s, cx + 30 * s, my + 8 * s], 15, 165, fill=INK, width=5)
        elif kind in ("frown", "wavy"):
            d.arc([cx - 30 * s, my - 2 * s, cx + 30 * s, my + 18 * s], 195, 345, fill=INK, width=5)
        else:
            d.line([cx - 30 * s, my, cx + 30 * s, my], fill=INK, width=5)
        return
    if kind == "smile":
        d.arc([cx - 30 * s, my - 22 * s, cx + 30 * s, my + 14 * s], 20, 160, fill=INK, width=6)
    elif kind == "smirk":
        d.arc([cx - 6 * s, my - 22 * s, cx + 34 * s, my + 10 * s], 20, 140, fill=INK, width=6)
    elif kind == "frown":
        d.arc([cx - 26 * s, my - 2 * s, cx + 26 * s, my + 24 * s], 200, 340, fill=INK, width=6)
    elif kind == "wavy":
        pts = [(cx - 26 * s + i * 13 * s, my + (5 if i % 2 else -4) * s) for i in range(5)]
        d.line(pts, fill=INK, width=5, joint="curve")
    elif kind == "small":
        d.line([cx - 10 * s, my, cx + 10 * s, my], fill=INK, width=6)
    else:
        d.line([cx - 20 * s, my, cx + 20 * s, my + 2], fill=INK, width=6)


def _face_brows(d, cx, by, dx, kind: str, span: float, width: int = 7) -> None:
    for sgn in (-1, 1):
        x = cx + sgn * dx
        if kind == "up":
            d.arc([x - span, by - 4, x + span, by + span * 0.9], 200, 340, fill=INK, width=width)
        elif kind == "angry":
            d.line([x - span * sgn, by - 10, x + span * sgn * 0.9, by + 12], fill=INK, width=width + 1)
        elif kind == "worry":
            d.line([x - span * sgn, by + 12, x + span * sgn * 0.9, by - 8], fill=INK, width=width)
        elif kind == "down":
            d.line([x - span, by + 8, x + span, by + 8], fill=INK, width=width)
        elif kind == "slant":
            d.line([x - span, by + (8 if sgn < 0 else -6), x + span, by + (-6 if sgn < 0 else 8)],
                   fill=INK, width=width)
        else:
            d.line([x - span, by + 2, x + span, by + 2], fill=INK, width=width)


def _gray_face(layer_d, g: Geometry, expression: str, mouth_open: bool) -> None:
    """Mặt kiểu TikTok Mỹ: mắt trắng to, con ngươi liếc, không mũi."""
    size, (lx, ly), brow, mouth = GRAY_FACE.get(expression, GRAY_FACE["neutral"])
    d = layer_d
    cx, cy, r = g.head_cx, g.head_cy, g.head_rx
    ex, ey = r * 0.33, cy - r * 0.04
    er = r * 0.3
    for sgn in (-1, 1):
        x = cx + sgn * ex
        if size <= 0:                                       # cười híp mắt
            d.arc([x - er, ey - er * 0.6, x + er, ey + er], 200, 340, fill=INK, width=8)
            continue
        rw, rh = er * 0.85 * size, er * 1.05 * size
        d.ellipse([x - rw, ey - rh, x + rw, ey + rh], fill=(255, 255, 255, 255), outline=INK, width=5)
        pr = er * (0.34 if size < 1.3 else 0.2)
        px = x + lx * (rw - pr - 3)
        py = ey + ly * (rh - pr - 3)
        d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=INK)
        if size < 0.8:                                      # mí mắt sụp (chán, nghi ngờ)
            d.chord([x - rw - 2, ey - rh - 2, x + rw + 2, ey + rh * 0.4], 180, 360, fill=GRAY_SKIN)
            d.line([x - rw, ey - rh * 0.3, x + rw, ey - rh * 0.3], fill=INK, width=5)
    _face_brows(d, cx, ey - er * 1.55 * max(size, 0.8), ex, brow, er * 0.9, 7)
    _face_mouth(d, cx, cy + r * 0.45, mouth, mouth_open, 0.9)
    if expression in ("crying", "sad"):
        for sgn in (-1, 1):
            x = cx + sgn * ex
            d.ellipse([x - 8, ey + er * 1.2, x + 8, ey + er * 2.4], fill=(140, 200, 240, 255))
    if expression in ("embarrassed", "worried", "scared"):
        x, y = cx + r * 0.78, cy - r * 0.55
        d.polygon([(x, y), (x + 14, y + 26), (x - 14, y + 26)], fill=(140, 200, 240, 255))
        d.ellipse([x - 14, y + 16, x + 14, y + 42], fill=(140, 200, 240, 255))


# biểu cảm -> (mắt, mày, miệng, thêm) cho kiểu vẽ tay Hàn
KHAND_FACE = {
    "neutral": ("round", "flat", "line", ""),
    "happy": ("arc", "up", "smile", ""),
    "laughing": ("squeeze", "up", "laugh", ""),
    "proud": ("half", "up", "smirk", ""),
    "smug": ("half", "slant", "smirk", ""),
    "sad": ("droop", "worry", "frown", "tear"),
    "crying": ("squeeze", "worry", "cry", "rivers"),
    "angry": ("small", "angry", "teeth", "vein"),
    "annoyed": ("half", "angry", "line", "sweat"),
    "shocked": ("huge", "up", "o", "sweat"),
    "surprised": ("huge", "up", "o", ""),
    "scared": ("huge", "worry", "teeth", "sweat"),
    "worried": ("round", "worry", "wavy", "sweat"),
    "confused": ("odd", "slant", "wavy", ""),
    "thinking": ("up", "flat", "line", ""),
    "suspicious": ("half", "slant", "line", ""),
    "disgusted": ("half", "angry", "wavy", ""),
    "embarrassed": ("squeeze", "worry", "wavy", "blush"),
    "shy": ("droop", "worry", "small", "blush"),
    "love": ("heart", "up", "smile", "blush"),
    "determined": ("small", "angry", "line", ""),
    "tired": ("half", "down", "line", ""),
    "bored": ("half", "flat", "line", ""),
}


def _khand_face(d, spec: CharSpec, g: Geometry, expression: str, mouth_open: bool) -> None:
    """Mặt vẽ tay kiểu meme Hàn: mắt lồi tròng nhỏ, mũi to, môi dày hồng."""
    eye, brow, mouth, extra = KHAND_FACE.get(expression, KHAND_FACE["neutral"])
    cx, cy, rx, ry = g.head_cx, g.head_cy, g.head_rx, g.head_ry
    skin = _soft_skin(spec)
    ex, ey, er = rx * 0.3, cy - ry * 0.12, rx * 0.17
    white = (255, 255, 255, 255)
    for sgn in (-1, 1):
        x = cx + sgn * ex
        if eye in ("round", "huge", "small", "droop", "up", "odd"):
            k = {"huge": 1.3, "small": 0.9, "odd": 1.15 if sgn < 0 else 0.8}.get(eye, 1.0)
            rr = er * k
            d.ellipse([x - rr, ey - rr, x + rr, ey + rr], fill=white, outline=INK, width=6)
            pr = rr * (0.18 if eye == "huge" else 0.3 if eye == "small" else 0.36)
            oy = {"droop": rr * 0.35, "up": -rr * 0.4}.get(eye, 0)
            ox = -sgn * rr * 0.1                       # hơi lác vào trong cho hài
            d.ellipse([x + ox - pr, ey + oy - pr, x + ox + pr, ey + oy + pr], fill=INK)
        elif eye == "arc":
            d.arc([x - er, ey - er * 0.7, x + er, ey + er], 200, 340, fill=INK, width=8)
        elif eye == "squeeze":                         # > <
            k = -sgn
            d.line([x - er * k, ey - er * 0.7, x + er * k, ey, x - er * k, ey + er * 0.7],
                   fill=INK, width=8, joint="curve")
        elif eye == "half":
            d.ellipse([x - er, ey - er, x + er, ey + er], fill=white, outline=INK, width=6)
            d.chord([x - er - 3, ey - er - 3, x + er + 3, ey + er * 0.2], 180, 360, fill=skin)
            d.line([x - er, ey - er * 0.1, x + er, ey - er * 0.1], fill=INK, width=6)
            d.ellipse([x - er * 0.3, ey + er * 0.1, x + er * 0.3, ey + er * 0.7], fill=INK)
        elif eye == "heart":
            hc = (230, 60, 100, 255)
            for off in (-1, 1):
                d.ellipse([x + off * er * 0.45 - er * 0.6, ey - er * 0.7,
                           x + off * er * 0.45 + er * 0.6, ey + er * 0.4], fill=hc)
            d.polygon([(x - er, ey - 4), (x + er, ey - 4), (x, ey + er * 1.1)], fill=hc)
    _face_brows(d, cx, ey - er * 1.75, ex, brow, er * 1.05, 9)
    # mũi to tròn: ở giữa, có lỗ mũi
    ny = cy + ry * 0.18
    nw, nh = rx * 0.2, ry * 0.17
    d.ellipse([cx - nw, ny - nh, cx + nw, ny + nh], fill=skin, outline=INK, width=6)
    d.arc([cx - nw * 0.95, ny - nh * 1.6, cx - nw * 0.2, ny + nh * 0.2], 260, 330, fill=INK, width=5)
    for sgn in (-1, 1):
        d.ellipse([cx + sgn * nw * 0.45 - 6, ny + nh * 0.2 - 5, cx + sgn * nw * 0.45 + 6, ny + nh * 0.2 + 5],
                  fill=INK)
    lips = (236, 128, 140, 255)
    _face_mouth(d, cx, cy + ry * 0.52, mouth, mouth_open, 1.0, lips=lips)
    blue = (120, 190, 240, 240)
    if extra == "tear":
        x = cx + ex
        d.ellipse([x - 9, ey + er, x + 9, ey + er * 2.2], fill=blue)
    if extra == "rivers":
        for sgn in (-1, 1):
            x = cx + sgn * ex
            d.rounded_rectangle([x - 11, ey + er * 0.6, x + 11, ey + er * 5.0], radius=11, fill=blue)
    if extra == "sweat":
        x, y = cx + rx * 0.72, cy - ry * 0.5
        d.polygon([(x, y), (x + 18, y + 32), (x - 18, y + 32)], fill=blue, outline=INK)
        d.ellipse([x - 18, y + 20, x + 18, y + 52], fill=blue, outline=INK, width=4)
    if extra == "blush":
        for sgn in (-1, 1):
            x = cx + sgn * rx * 0.58
            d.ellipse([x - 26, cy + ry * 0.2, x + 26, cy + ry * 0.38], fill=(240, 130, 140, 170))
    if extra == "vein":
        x, y = cx + rx * 0.5, cy - ry * 0.62
        for a0 in (0, 90, 180, 270):
            d.arc([x - 30, y - 30, x + 30, y + 30], a0 + 20, a0 + 70, fill=(210, 40, 50, 255), width=10)


def _soft_head(spec: CharSpec, g: Geometry, mouth_open: bool,
               expression: str = "neutral") -> Image.Image:
    """Đầu nét mềm: tóc khối + mặt theo kiểu (gray / khand). Chỉ màu, viền tự tạo."""
    img = _new_canvas()
    layer = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy, rx, ry = g.head_cx, g.head_cy, g.head_rx, g.head_ry
    skin = _soft_skin(spec)
    hair = _soft_hair_col(spec)
    st = spec.hair_style
    gray = spec.style == "gray"

    # tóc phía sau
    if st in ("long", "wavy"):
        d.rounded_rectangle([cx - rx - 6, cy - ry * 0.4, cx + rx + 6, cy + ry * (1.25 if gray else 1.1)],
                            radius=int(rx * 0.6), fill=hair)
    elif st == "ponytail":
        d.ellipse([cx + rx * 0.55, cy - ry * 0.95, cx + rx * 1.25, cy - ry * 0.25], fill=hair)
    elif st == "twintails":
        for sgn in (-1, 1):
            x = cx + sgn * rx * 1.0
            d.ellipse([x - rx * 0.3, cy - ry * 0.3, x + rx * 0.3, cy + ry * 0.7], fill=hair)
    elif st == "bun":
        d.ellipse([cx - rx * 0.32, cy - ry * 1.42, cx + rx * 0.32, cy - ry * 0.78], fill=hair)

    # tai (kiểu vẽ tay Hàn)
    if not gray:
        for sgn in (-1, 1):
            x = cx + sgn * rx * 0.98
            d.ellipse([x - rx * 0.16, cy - ry * 0.05, x + rx * 0.16, cy + ry * 0.33], fill=skin)
    # mặt: tròn, kiểu Hàn hơi bành ở má
    if gray:
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=skin)
    else:
        d.chord([cx - rx, cy - ry, cx + rx, cy + ry], 180, 360, fill=skin)
        d.ellipse([cx - rx * 1.02, cy - ry * 0.35, cx + rx * 1.02, cy + ry * 1.02], fill=skin)

    if expression == "__back__":
        # nhìn từ sau lưng (cảnh qua vai): tóc phủ nửa trên đầu, không mặt
        if st == "buzz" and not gray:
            for k in (-0.25, 0.0, 0.22):
                x = cx + k * rx
                d.arc([x - 28, cy - ry - 36, x + 28, cy - ry + 18], 200, 330, fill=INK, width=5)
        elif st == "curly":
            for i in range(14):
                a = math.pi * (-0.1 + 0.093 * i)
                x = cx - math.cos(a) * rx * 0.85
                y = cy - math.sin(a) * ry * 0.75
                d.ellipse([x - rx * 0.26, y - rx * 0.26, x + rx * 0.26, y + rx * 0.26], fill=hair)
        else:
            d.chord([cx - rx * 1.02, cy - ry * 1.04, cx + rx * 1.02, cy + ry * 0.5], 180, 360, fill=hair)
            d.rectangle([cx - rx * 0.98, cy - ry * 0.3, cx + rx * 0.98, cy - ry * 0.2], fill=hair)
            if st in ("long", "wavy", "bob"):
                d.rounded_rectangle([cx - rx * 0.98, cy - ry * 0.3, cx + rx * 0.98, cy + ry * 0.9],
                                    radius=int(rx * 0.4), fill=hair)
        img.alpha_composite(layer, (PAD_X, PAD_Y))
        return img

    # tóc phía trước
    if st == "buzz" and not gray:                      # hói, vài sợi tóc (kiểu ông bố)
        for k in (-0.25, 0.0, 0.22):
            x = cx + k * rx
            d.arc([x - 28, cy - ry - 36, x + 28, cy - ry + 18], 200, 330, fill=INK, width=5)
    elif st == "buzz":
        d.chord([cx - rx * 0.98, cy - ry * 1.02, cx + rx * 0.98, cy - ry * 0.1], 180, 360, fill=hair)
    elif st == "curly":                                 # tóc xoăn ajumma
        for i in range(9):
            a = math.pi * (0.02 + 0.12 * i)
            x = cx - math.cos(a) * rx * 0.92
            y = cy - math.sin(a) * ry * 0.9
            d.ellipse([x - rx * 0.24, y - rx * 0.24, x + rx * 0.24, y + rx * 0.24], fill=hair)
    else:
        # mũ tóc phủ đỉnh đầu, mép trước nham nhở (nét tay)
        edge = cy - ry * (0.35 if st != "bowl" else 0.18)
        d.chord([cx - rx * 1.02, cy - ry * 1.04, cx + rx * 1.02, 2 * edge - (cy - ry * 1.04)],
                180, 360, fill=hair)
        n = 7
        rnd = random.Random(sum(map(ord, spec.name or "x")))
        for i in range(n):
            x0 = cx - rx * 0.85 + i * rx * 1.7 / n
            x1 = x0 + rx * 1.7 / n
            dep = ry * (0.08 + 0.08 * rnd.random())
            d.polygon([(x0, edge - 2), (x1, edge - 2), ((x0 + x1) / 2 + rnd.uniform(-6, 6), edge + dep)],
                      fill=hair)
        if st == "sidepart":
            d.polygon([(cx - rx * 0.95, edge + 10), (cx + rx * 0.2, cy - ry * 1.05),
                       (cx + rx * 0.95, edge - ry * 0.25)], fill=hair)
        if st == "short" and gray:                      # tóc ngắn có chỏm (nam, ảnh mẫu)
            d.polygon([(cx - rx * 0.2, cy - ry * 0.98), (cx + rx * 0.45, cy - ry * 1.18),
                       (cx + rx * 0.5, cy - ry * 0.8)], fill=hair)
        if st == "bob":
            for sgn in (-1, 1):
                x = cx + sgn * rx * 0.9
                d.rounded_rectangle([x - rx * 0.22, edge - 10, x + rx * 0.22, cy + ry * 0.55],
                                    radius=24, fill=hair)

    # mặt + phụ kiện
    if gray:
        _gray_face(d, g, expression, mouth_open)
    else:
        _khand_face(d, spec, g, expression, mouth_open)
    fg = {"head_cx": cx, "head_cy": cy, "head_rx": rx, "head_ry": ry,
          "eye_dx": int(rx * 0.32), "eye_y": int(cy - ry * 0.1), "eye_r": int(rx * 0.18),
          "mouth_y": int(cy + ry * 0.5), "brow_y": int(cy - ry * 0.42)}
    if spec.accessory == "cap" and gray:               # mũ lưỡi trai xám đội ngược (ảnh mẫu)
        d.chord([cx - rx * 1.04, cy - ry * 1.1, cx + rx * 1.04, cy - ry * 0.02], 180, 360, fill=GRAY_DARK)
        d.rounded_rectangle([cx - rx * 1.45, cy - ry * 0.6, cx - rx * 0.5, cy - ry * 0.4],
                            radius=10, fill=GRAY_DARK)
    elif spec.accessory != "none":
        ck._draw_extras(d, spec, fg, {})
    img.alpha_composite(layer, (PAD_X, PAD_Y))
    return img


# ---------------------------------------------------------------- thân, tay, chân

def _soft_torso(spec: CharSpec, g: Geometry) -> Image.Image:
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    cx = g.head_cx
    top, hip = g.shoulder_y - 16, g.hip[1]
    hw = g.body_w / 2
    if spec.style == "gray":
        # thân xám mảnh hơi thon eo; nữ mặc váy xoè
        _taper(d, (cx, top + hw), (cx, hip), g.body_w, g.body_w * 0.9, GRAY_SKIN)
        if spec.outfit == "dress" or spec.hair_style in ("long", "ponytail", "twintails", "bun", "bob", "wavy"):
            d.polygon([_p((cx - hw * 0.9, hip - 70)), _p((cx + hw * 0.9, hip - 70)),
                       _p((cx + hw * 1.9, hip + 46)), _p((cx - hw * 1.9, hip + 46))], fill=GRAY_SKIN)
        return img
    # vẽ tay Hàn: bụng tròn trong áo cổ chữ V
    shirt = ck.SHIRT_COLORS.get(spec.shirt, ck.SHIRT_COLORS["blue"]) + (255,)
    skin = _soft_skin(spec)
    pants = ck.PANTS_COLORS.get(spec.pants, ck.PANTS_COLORS["navy"]) + (255,)
    belly = hw * 1.18
    d.ellipse([*_p((cx - belly, hip - belly * 1.5)), *_p((cx + belly, hip + belly * 0.35))], fill=shirt)
    d.rounded_rectangle([*_p((cx - hw, top)), *_p((cx + hw, hip - belly * 0.4))], radius=int(hw * 0.7), fill=shirt)
    # quần đùi
    d.chord([*_p((cx - belly * 0.95, hip - belly * 0.6)), *_p((cx + belly * 0.95, hip + belly * 0.5))],
            0, 180, fill=pants)
    # cổ áo chữ V (da) + nét
    v = [(cx - hw * 0.24, top + 4), (cx, top + hw * 0.42), (cx + hw * 0.24, top + 4)]
    d.polygon([_p(q) for q in v], fill=skin)
    _soft_line(d, v, 6)
    # nếp bụng
    d.arc([*_p((cx - belly * 0.45, hip - belly * 0.55)), *_p((cx + belly * 0.45, hip - belly * 0.05))],
          30, 150, fill=INK, width=5)
    return img


def _soft_neck(spec: CharSpec, g: Geometry) -> Image.Image:
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    w = g.body_w * (0.45 if spec.style == "gray" else 0.3)
    # cổ dừng ngay trên mép áo, không đè xuống ngực
    end = g.shoulder_y + (4 if spec.style == "gray" else -12)
    _taper(d, (g.head_cx, g.chin[1] - 16), (g.head_cx, end), w, w, _soft_skin(spec))
    return img


def _soft_parts(spec: CharSpec, g: Geometry) -> dict:
    skin = _soft_skin(spec)
    gray = spec.style == "gray"
    shirt = ck.SHIRT_COLORS.get(spec.shirt, ck.SHIRT_COLORS["blue"]) + (255,)
    pants = ck.PANTS_COLORS.get(spec.pants, ck.PANTS_COLORS["navy"]) + (255,)
    aw = g.arm_w

    def sx(gg, side):
        return gg.head_cx + (gg.shoulder_dx if side == "right" else -gg.shoulder_dx)

    def hx(gg, side):
        return gg.head_cx + (gg.hip_dx if side == "right" else -gg.hip_dx)

    def upper(sp, gg, side):
        img = _new_canvas()
        d = ImageDraw.Draw(img)
        x, y0 = sx(gg, side), gg.shoulder_y
        y1 = y0 + gg.upper_len
        _taper(d, (x, y0), (x, y1), aw, aw * 0.88, skin)
        if not gray:                                  # tay áo ngắn
            _taper(d, (x, y0), (x, y0 + gg.upper_len * 0.45), aw * 1.25, aw * 1.15, shirt)
        return img

    def fore(sp, gg, side):
        img = _new_canvas()
        x, y0 = sx(gg, side), gg.shoulder_y + gg.upper_len
        _taper(ImageDraw.Draw(img), (x, y0), (x, y0 + gg.fore_len), aw * 0.88, aw * 0.74, skin)
        return img

    def hand(sp, gg, side):
        img = _new_canvas()
        d = ImageDraw.Draw(img)
        sgn = 1 if side == "right" else -1
        x, wy = sx(gg, side), gg.shoulder_y + gg.upper_len + gg.fore_len
        r = gg.hand_r
        d.ellipse([*_p((x - r, wy - r * 0.2)), *_p((x + r, wy + r * 1.7))], fill=skin)
        if not gray:                                  # ngón cái
            tx0, tx1 = sorted((x - sgn * r * 1.25, x - sgn * r * 0.35))
            d.ellipse([*_p((tx0, wy + r * 0.1)), *_p((tx1, wy + r * 0.95))], fill=skin)
        return img

    def thigh(sp, gg, side):
        img = _new_canvas()
        d = ImageDraw.Draw(img)
        x, y0 = hx(gg, side), gg.hip[1]
        y1 = y0 + gg.thigh_len
        _taper(d, (x, y0), (x, y1), gg.thigh_w, gg.thigh_w * 0.85, skin)
        if not gray:                                  # ống quần đùi
            _taper(d, (x, y0), (x, y0 + gg.thigh_len * 0.5), gg.thigh_w * 1.3, gg.thigh_w * 1.2, pants)
        return img

    def shin(sp, gg, side):
        img = _new_canvas()
        x, y0 = hx(gg, side), gg.hip[1] + gg.thigh_len
        _taper(ImageDraw.Draw(img), (x, y0), (x, y0 + gg.shin_len), gg.thigh_w * 0.85,
               gg.thigh_w * 0.7, skin)
        return img

    def foot(sp, gg, side):
        img = _new_canvas()
        d = ImageDraw.Draw(img)
        sgn = 1 if side == "right" else -1
        x, ay = hx(gg, side), gg.hip[1] + gg.thigh_len + gg.shin_len
        if gray:                                      # chân nhọn nhỏ như ảnh mẫu
            d.ellipse([*_p((x - 14, ay - 12)), *_p((x + 14 + sgn * 10, ay + 16))], fill=skin)
            return img
        fw = gg.foot_w
        x0, x1 = (x - fw * 0.35, x + fw * 0.75) if sgn > 0 else (x - fw * 0.75, x + fw * 0.35)
        d.ellipse([*_p((x0, ay - 16)), *_p((x1, ay + 26))], fill=skin)
        tip = x1 if sgn > 0 else x0                   # ngón chân
        for k in range(4):
            tx = tip - sgn * (6 + k * fw * 0.16)
            d.ellipse([*_p((tx - 10, ay + 6)), *_p((tx + 10, ay + 28))], fill=skin)
        return img

    return {"torso": _soft_torso, "neck": _soft_neck, "head": _soft_head,
            "upper": upper, "fore": fore, "hand": hand,
            "thigh": thigh, "shin": shin, "foot": foot}


def _parts_for(spec: CharSpec, g: Geometry):
    """Bảng hàm vẽ bộ phận theo kiểu nhân vật."""
    if spec.style in SOFT_STYLES:
        return _soft_parts(spec, g)
    if spec.style in ("box", "kchibi"):
        return _box_parts(spec, g)
    if spec.style == "stick":
        def arm_up(sp, gg, side):
            sx = gg.head_cx + (gg.shoulder_dx if side == "right" else -gg.shoulder_dx)
            return _stick_limb(gg, (sx, gg.shoulder_y), (sx, gg.shoulder_y + gg.upper_len))

        def arm_fore(sp, gg, side):
            sx = gg.head_cx + (gg.shoulder_dx if side == "right" else -gg.shoulder_dx)
            ey = gg.shoulder_y + gg.upper_len
            return _stick_limb(gg, (sx, ey), (sx, ey + gg.fore_len))

        def thigh(sp, gg, side):
            hx = gg.head_cx + (gg.hip_dx if side == "right" else -gg.hip_dx)
            return _stick_limb(gg, (hx, gg.hip[1]), (hx, gg.hip[1] + gg.thigh_len))

        def shin(sp, gg, side):
            hx = gg.head_cx + (gg.hip_dx if side == "right" else -gg.hip_dx)
            ky = gg.hip[1] + gg.thigh_len
            return _stick_limb(gg, (hx, ky), (hx, ky + gg.shin_len))

        return {"torso": _stick_torso, "neck": _stick_neck, "head": _stick_head,
                "upper": arm_up, "fore": arm_fore, "hand": _stick_hand,
                "thigh": thigh, "shin": shin, "foot": _stick_foot}
    return {"torso": draw_torso, "neck": draw_neck, "head": draw_head,
            "upper": draw_upper_arm, "fore": draw_forearm, "hand": draw_hand,
            "thigh": draw_thigh, "shin": draw_shin, "foot": draw_foot}


def hold_angles(held: dict[str, str], since: dict[str, float], t: float) -> dict[str, float]:
    """Góc tay khi cầm đạo cụ (tư thế cầm mặc định của từng đạo cụ)."""
    if not held:
        return {}
    from . import props as props_mod
    from .gestures import swap_sides
    _, lib = ensure_library()
    out: dict[str, float] = {}
    for side, name in held.items():
        g = lib.get(props_mod.hold_pose(name))
        if g is None:
            continue
        pose = gesture_pose(g, t - since.get(side, 0.0)) or {}
        if side == "left":
            # góc đã là góc thực của tay phải: đổi sang tay trái và lật chiều
            pose = {k: (-v if k.endswith(("_left", "_right")) else v)
                    for k, v in swap_sides(pose).items()}
        out.update({k: v for k, v in pose.items() if k not in ("dich_x", "dich_y")})
    return out


def stick_arm_limits(angles: dict[str, float]) -> dict[str, float]:
    """Người que đầu to: không cho tay giơ chéo qua đầu.

    Cánh tay trên giơ tối đa 130°, cẳng tay (góc tổng) tối đa thẳng đứng —
    cử chỉ soạn cho nhân vật vai rộng vẫn đọc được mà tay không che mặt.
    """
    out = dict(angles)
    lim_up, lim_tot = math.radians(130), math.radians(185)
    for side, sgn in (("right", 1), ("left", -1)):
        up_k, lo_k = f"vai_{side}", f"khuyu_{side}"
        if up_k not in out and lo_k not in out:
            continue
        up = out.get(up_k, 0.0) * sgn          # quy về chiều tay phải
        lo = out.get(lo_k, 0.0) * sgn
        up2 = max(-lim_up, up)
        tot = max(-lim_tot, up2 + lo)
        if up_k in out or up2 != up:
            out[up_k] = up2 * sgn
        if lo_k in out or tot != up + lo:
            out[lo_k] = (tot - up2) * sgn
    return out


# Tư thế đứng mặc định của người que: tay dang nhẹ, chân hơi choãi
# (góc thực, tay/chân trái đã lật dấu).
STICK_REST = {"vai_right": math.radians(-24), "vai_left": math.radians(24),
              "dui_right": math.radians(-8), "dui_left": math.radians(8)}
REST_POSES = {
    "stick": STICK_REST,
    "gray": {"vai_right": math.radians(-17), "vai_left": math.radians(17),
             "dui_right": math.radians(-4), "dui_left": math.radians(4)},
    "khand": {"vai_right": math.radians(-20), "vai_left": math.radians(20),
              "khuyu_right": math.radians(-10), "khuyu_left": math.radians(10),
              "dui_right": math.radians(-7), "dui_left": math.radians(7)},
    "box": {"vai_right": math.radians(-12), "vai_left": math.radians(12)},
    "kchibi": {"vai_right": math.radians(-16), "vai_left": math.radians(16)},
}
# kiểu đầu to: tay vẽ sau đầu và giới hạn góc giơ tay để không che mặt
BIG_HEAD = ("stick", "box", "kchibi", "gray", "khand")


# ------------------------------------------------------------------ xương

@dataclass
class Bone:
    """Một xương: bộ phận ảnh + khớp + góc xoay tương đối so với xương cha."""
    name: str
    parent: str | None
    offset: tuple[float, float]     # lệch từ khớp cha tới khớp mình
    part: str                       # tên file ảnh trong thư mục parts/
    pivot: tuple[float, float]      # pivot trong ảnh (px)
    layer: float                    # thứ tự vẽ (lớn hơn vẽ sau, đè lên)
    angle: float = 0.0              # radian, góc tương đối so với cha

    def to_dict(self) -> dict:
        return {
            "name": self.name, "parent": self.parent,
            "offset": list(self.offset), "part": self.part,
            "pivot": list(self.pivot), "layer": self.layer,
            "layer_name": LAYER_NAMES.get(self.layer, str(self.layer)),
            "angle": self.angle,
        }

    @staticmethod
    def from_dict(d: dict) -> "Bone":
        return Bone(
            name=d["name"], parent=d.get("parent"),
            offset=tuple(d.get("offset", (0, 0))),
            part=d["part"], pivot=tuple(d.get("pivot", (0, 0))),
            layer=float(d.get("layer", 0)), angle=float(d.get("angle", 0.0)),
        )


@dataclass
class Rig:
    """Bộ khung xương của một nhân vật."""
    name: str
    root: str
    bones: list[Bone]
    spec: dict = field(default_factory=dict)
    parts_dir: str = ""

    def bone(self, name: str) -> Bone:
        for b in self.bones:
            if b.name == name:
                return b
        raise KeyError(f"Không có xương '{name}' trong rig của {self.name}")

    def to_dict(self) -> dict:
        return {
            "name": self.name, "root": self.root,
            "spec": self.spec, "parts_dir": self.parts_dir,
            "canvas": {"w": CW, "h": CH, "pad_x": PAD_X, "pad_y": PAD_Y},
            "bones": [b.to_dict() for b in self.bones],
        }

    @staticmethod
    def from_dict(d: dict) -> "Rig":
        return Rig(
            name=d["name"], root=d["root"],
            bones=[Bone.from_dict(b) for b in d["bones"]],
            spec=d.get("spec", {}), parts_dir=d.get("parts_dir", ""),
        )

    # ---------------------------------------------------------- toán học

    def _ordered(self) -> list[Bone]:
        """Xương theo thứ tự cha trước con, bắt đầu từ xương gốc."""
        by_name = {b.name: b for b in self.bones}
        by_parent: dict[str | None, list[Bone]] = {}
        for b in self.bones:
            by_parent.setdefault(b.parent, []).append(b)
        out: list[Bone] = []
        seen: set[str] = set()
        queue: list[str] = [self.root]
        while queue:
            n = queue.pop(0)
            if n in by_name and n not in seen:
                seen.add(n)
                out.append(by_name[n])
            for b in by_parent.get(n, []):
                queue.append(b.name)
        return out

    def solve(self, angles: dict[str, float] | None = None) -> dict[str, dict]:
        """Tính vị trí và góc toàn cục của từng xương.

        Trả về {tên xương: {"pivot": (x, y), "angle": radian, "layer": int}}
        Toạ độ trả về nằm trong khung gốc 600x1000 (đã bỏ lề).
        """
        angles = angles or {}
        world: dict[str, dict] = {}
        for b in self._ordered():
            if b.name in angles:
                # Góc cử chỉ tính từ tư thế buông thẳng. Xương có tư thế đứng
                # riêng (người que dang tay): cử động nhỏ cộng vào tư thế đó,
                # cử chỉ lớn ra đúng góc cử chỉ.
                a = angles[b.name]
                local = a + b.angle * (1.0 - _blend(a)) if b.angle else a
            else:
                local = b.angle
            if b.parent is None:
                wp = (b.offset[0], b.offset[1])
                wa = local
            else:
                p = world.get(b.parent)
                if p is None:
                    continue
                c, s = math.cos(p["angle"]), math.sin(p["angle"])
                dx, dy = b.offset
                wp = (p["pivot"][0] + dx * c - dy * s,
                      p["pivot"][1] + dx * s + dy * c)
                wa = p["angle"] + local
            world[b.name] = {"pivot": wp, "angle": wa, "layer": b.layer}
        return world


# ------------------------------------------------------------------ dựng rig

def _crop_head_pair(dong: Image.Image, mo: Image.Image,
                    pivot_canvas: tuple[float, float]):
    """Cắt hai ảnh đầu (miệng ngậm/mở) theo CÙNG một khung để chung pivot."""
    boxes = [b for b in (dong.getbbox(), mo.getbbox()) if b]
    if not boxes:
        return dong, mo, pivot_canvas
    box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
           max(b[2] for b in boxes), max(b[3] for b in boxes))
    pivot = (pivot_canvas[0] - box[0], pivot_canvas[1] - box[1])
    return dong.crop(box), mo.crop(box), pivot


def head_images(spec: CharSpec, expression: str = "neutral"):
    """(ảnh đầu miệng ngậm, ảnh miệng mở, pivot) theo biểu cảm."""
    g = geometry(spec.body, spec.style)
    draw = _parts_for(spec, g)["head"]
    return _crop_head_pair(draw(spec, g, False, expression),
                           draw(spec, g, True, expression), _p(g.chin))


def build_parts(spec: CharSpec, expression: str = "neutral"
                ) -> tuple[list[Bone], dict[str, Image.Image]]:
    """Vẽ mọi bộ phận (trong bộ nhớ). Trả về (danh sách xương, {tên file: ảnh})."""
    g = geometry(spec.body, spec.style)
    fn = _parts_for(spec, g)
    rest = REST_POSES.get(spec.style, {})
    bones: list[Bone] = []
    images: dict[str, Image.Image] = {}

    def add(name, parent, joint, offset, part_name, pivot_canvas, layer,
            img: Image.Image) -> None:
        cropped, pivot = _crop_pivot(img, pivot_canvas)
        images[part_name] = cropped
        bones.append(Bone(name=name, parent=parent, offset=offset,
                          part=part_name, pivot=pivot, layer=layer,
                          angle=rest.get(name, 0.0)))

    hip = g.hip
    neck = g.neck
    chin = g.chin

    # --- thân (root) ---
    add("than", None, hip, hip, "than.png", _p(hip), LAYER_THAN, fn["torso"](spec, g))

    # --- cổ, con của thân ---
    add("co", "than", neck, (neck[0] - hip[0], neck[1] - hip[1]),
        "co.png", _p(neck), LAYER_THAN, fn["neck"](spec, g))

    # --- đầu, con của cổ (hai ảnh miệng ngậm/mở chung pivot) ---
    dong, mo, hpivot = head_images(spec, expression)
    images["dau_dong.png"] = dong
    images["dau_mo.png"] = mo
    bones.append(Bone(name="dau", parent="co",
                      offset=(chin[0] - neck[0], chin[1] - neck[1]),
                      part="dau_dong.png", pivot=hpivot, layer=LAYER_DAU))

    # --- tay --- (người que: cả hai tay nằm sau đầu để không che mặt;
    # nét mềm: mỗi tay một lớp riêng trên thân để viền tách bạch khi khoanh tay)
    if spec.style in SOFT_STYLES:
        arm_layers = (("left", 2.5), ("right", 2.6))
    elif spec.style in BIG_HEAD:
        arm_layers = (("left", LAYER_THAN), ("right", LAYER_THAN))
    else:
        arm_layers = (("left", LAYER_TAY_SAU), ("right", LAYER_TAY_TRUOC))
    for side, layer in arm_layers:
        sgn = 1 if side == "right" else -1
        shoulder = (g.head_cx + sgn * g.shoulder_dx, float(g.shoulder_y))
        elbow = (shoulder[0], shoulder[1] + g.upper_len)
        wrist = (shoulder[0], elbow[1] + g.fore_len)
        add(f"vai_{side}", "than", shoulder,
            (shoulder[0] - hip[0], shoulder[1] - hip[1]),
            f"vai_{side}.png", _p(shoulder), layer, fn["upper"](spec, g, side))
        add(f"khuyu_{side}", f"vai_{side}", elbow,
            (elbow[0] - shoulder[0], elbow[1] - shoulder[1]),
            f"khuyu_{side}.png", _p(elbow), layer, fn["fore"](spec, g, side))
        add(f"co_tay_{side}", f"khuyu_{side}", wrist,
            (wrist[0] - elbow[0], wrist[1] - elbow[1]),
            f"co_tay_{side}.png", _p(wrist), layer, fn["hand"](spec, g, side))

    # --- chân --- (nét mềm: chân phải lớp trên chân trái để viền rõ khi bước)
    for side in ("left", "right"):
        sgn = 1 if side == "right" else -1
        leg_layer = (1.2 if side == "right" else 1.0) if spec.style in SOFT_STYLES else LAYER_CHAN
        hip_joint = (g.head_cx + sgn * g.hip_dx, g.hip[1])
        knee = (hip_joint[0], hip_joint[1] + g.thigh_len)
        ankle = (hip_joint[0], knee[1] + g.shin_len)
        add(f"dui_{side}", "than", hip_joint,
            (hip_joint[0] - hip[0], hip_joint[1] - hip[1]),
            f"dui_{side}.png", _p(hip_joint), leg_layer, fn["thigh"](spec, g, side))
        add(f"goi_{side}", f"dui_{side}", knee,
            (knee[0] - hip_joint[0], knee[1] - hip_joint[1]),
            f"goi_{side}.png", _p(knee), leg_layer, fn["shin"](spec, g, side))
        add(f"co_chan_{side}", f"goi_{side}", ankle,
            (ankle[0] - knee[0], ankle[1] - knee[1]),
            f"co_chan_{side}.png", _p(ankle), leg_layer, fn["foot"](spec, g, side))

    return bones, images


def build_rig(spec: CharSpec, out_dir: Path) -> Rig:
    """Vẽ các bộ phận, lưu ảnh + rig.json vào out_dir.

    out_dir sẽ chứa:
      rig.json
      parts/*.png
    """
    out_dir = Path(out_dir)
    parts_dir = out_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    bones, images = build_parts(spec)
    for name, img in images.items():
        img.save(parts_dir / name)
    rig = Rig(name=spec.name, root="than", bones=bones,
              spec=spec.to_dict(), parts_dir="parts")
    (out_dir / "rig.json").write_text(
        json.dumps(rig.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return rig


def render_still(spec: CharSpec, expression: str = "neutral",
                 mouth_open: bool = False) -> Image.Image:
    """Ảnh tĩnh một nhân vật ở tư thế đứng (dùng cho bộ ảnh biểu cảm).

    Cắt theo khung cố định của dáng người (không theo nội dung từng ảnh), để
    mọi biểu cảm cùng cỡ — đổi biểu cảm nhân vật không bị nhảy kích thước.
    """
    bones, images = build_parts(spec, expression)
    rig = Rig(name=spec.name, root="than", bones=bones, spec=spec.to_dict())
    rr = RigRenderer(rig, Path("."))
    rr._cache.update(images)
    img = rr.render({}, mouth_open=mouth_open, crop=False)
    g = geometry(spec.body, spec.style)
    top = g.head_cy - g.head_ry - 70
    bottom = g.hip[1] + g.thigh_len + g.shin_len + 30
    return img.crop((PAD_X - 60, PAD_Y + top, PAD_X + CW + 60, PAD_Y + bottom))


def load_rig(rig_path: Path) -> Rig:
    d = json.loads(Path(rig_path).read_text(encoding="utf-8"))
    return Rig.from_dict(d)


# ------------------------------------------------------------------ vẽ khung

class RigRenderer:
    """Ráp các bộ phận theo khung xương, xoay quanh khớp."""

    def __init__(self, rig: Rig, base_dir: Path):
        self.rig = rig
        self.base_dir = Path(base_dir)
        self.parts_dir = self.base_dir / rig.parts_dir if rig.parts_dir else self.base_dir
        self._cache: dict[str, Image.Image] = {}
        self._np_cache: dict[str, object] = {}
        # đầu theo biểu cảm, vẽ khi cần: tên file -> pivot
        self._head_pivots: dict[str, tuple[float, float]] = {}
        try:
            sp = CharSpec.from_dict(rig.spec) if rig.spec else None
            self._hand_r = geometry(sp.body, sp.style).hand_r if sp else 30
        except Exception:  # noqa: BLE001
            self._hand_r = 30
        # OpenCV tăng tốc render (nếu không có thì dùng đường PIL)
        self._cv = None
        self._np = None
        try:
            import cv2
            import numpy
            self._cv = cv2
            self._np = numpy
            self._cv_ok = True
        except Exception:
            self._cv_ok = False

    def _part(self, filename: str) -> Image.Image:
        img = self._cache.get(filename)
        if img is None:
            if filename.startswith("#prop:"):
                from . import props as props_mod
                img = props_mod.render(filename[6:])[0]
            elif filename.endswith("#o"):
                img = _outline_img(self._part(filename[:-2]))
            else:
                img = Image.open(self.parts_dir / filename).convert("RGBA")
            self._cache[filename] = img
        return img

    def _add_props(self, ordered: list["Bone"], world: dict, held: dict | None) -> list["Bone"]:
        """Thêm đạo cụ như xương tạm: đặt ở lòng bàn tay, đứng thẳng, vẽ ngay
        dưới cánh tay cầm nó (bàn tay che lên chỗ cầm)."""
        if not held:
            return ordered
        from . import props as props_mod

        def hand_center(side):
            w = world.get(f"co_tay_{side}")
            if w is None:
                return None
            a = w["angle"]
            dy = self._hand_r * 0.75
            return ((w["pivot"][0] - dy * math.sin(a), w["pivot"][1] + dy * math.cos(a)),
                    a, w["layer"])

        extra = []
        for side, name in held.items():
            if not name or name not in props_mod.PROPS:
                continue
            if side == "both":
                hr, hl = hand_center("right"), hand_center("left")
                if not hr or not hl:
                    continue
                pos = ((hr[0][0] + hl[0][0]) / 2, (hr[0][1] + hl[0][1]) / 2)
                tilt, lay = 0.0, min(hr[2], hl[2])
            else:
                hc = hand_center(side)
                if not hc:
                    continue
                pos, a, lay = hc
                tilt = max(-0.35, min(0.35, a * 0.2))
            torso_layer = world.get("than", {}).get("layer", LAYER_THAN)
            if side == "both":
                # đồ bưng hai tay: sau hai cánh tay (tay ôm hai bên)
                layer = lay - 0.01 if lay > torso_layer else lay + 0.01
            else:
                # đồ cầm một tay: cùng lớp cánh tay, xếp ngay trước bàn tay
                # (đè lên cẳng tay, dưới ngón tay) — xem _order_props
                layer = lay
            img, pivot = props_mod.render(name)
            bname = f"prop_{side}"
            extra.append(Bone(name=bname, parent=None, offset=(0, 0), part=f"#prop:{name}",
                              pivot=pivot, layer=layer))
            world[bname] = {"pivot": pos, "angle": tilt, "layer": layer}
        out = ordered + extra
        out.sort(key=lambda b: world[b.name]["layer"])
        return self._order_props(out)

    @staticmethod
    def _order_props(bones: list["Bone"]) -> list["Bone"]:
        """Đặt đạo cụ cầm một tay ngay trước bàn tay cầm nó."""
        out = [b for b in bones if not (b.name in ("prop_right", "prop_left"))]
        for side in ("right", "left"):
            pb = next((b for b in bones if b.name == f"prop_{side}"), None)
            if pb is None:
                continue
            idx = next((i for i, b in enumerate(out) if b.name == f"co_tay_{side}"), len(out))
            out.insert(idx, pb)
        return out

    def _sequence(self, ordered: list["Bone"], world: dict) -> list[tuple["Bone", bool]]:
        """Thứ tự vẽ (xương, là_viền). Kiểu nét mềm: mỗi lớp vẽ viền của mọi
        bộ phận trong lớp trước rồi mới tô màu, nên các khớp liền một khối."""
        if self.rig.spec.get("style") not in SOFT_STYLES:
            return [(b, False) for b in ordered]
        seq: list[tuple[Bone, bool]] = []
        i = 0
        while i < len(ordered):
            lay = world[ordered[i].name]["layer"]
            group = []
            while i < len(ordered) and world[ordered[i].name]["layer"] == lay:
                group.append(ordered[i])
                i += 1
            seq += [(b, True) for b in group if not b.name.startswith("prop_")]
            seq += [(b, False) for b in group]
        return seq

    def _resolve(self, b: "Bone", outline: bool, mouth_open: bool,
                 expression: str | None) -> tuple[str, tuple[float, float]]:
        filename, pivot = b.part, b.pivot
        if b.name == "dau":
            filename, pivot = self._head_part(b, mouth_open, expression)
        if outline:
            return filename + "#o", (pivot[0] + SOFT_OUTLINE, pivot[1] + SOFT_OUTLINE)
        return filename, pivot

    def _head_part(self, b: "Bone", mouth_open: bool, expression: str | None
                   ) -> tuple[str, tuple[float, float]]:
        """Ảnh đầu cho biểu cảm (vẽ lần đầu khi cần) và pivot của nó."""
        tag = "mo" if mouth_open else "dong"
        if not expression or expression == "neutral" or not self.rig.spec:
            return f"dau_{tag}.png", b.pivot
        name = f"dau_{expression}_{tag}.png"
        if name not in self._head_pivots:
            try:
                spec = CharSpec.from_dict(self.rig.spec)
                dong, mo, pivot = head_images(spec, expression)
            except Exception:  # noqa: BLE001 - lỗi vẽ -> mặt bình thường
                return f"dau_{tag}.png", b.pivot
            for t, im in (("dong", dong), ("mo", mo)):
                self._cache[f"dau_{expression}_{t}.png"] = im
                self._head_pivots[f"dau_{expression}_{t}.png"] = pivot
        return name, self._head_pivots[name]

    def render(self, angles: dict[str, float] | None = None,
               mouth_open: bool = False,
               crop: bool = True, expression: str | None = None,
               props: dict[str, str] | None = None) -> Image.Image:
        """Vẽ một khung nhân vật theo góc xương cho trước.

        Kết quả trả về trong khung gốc 600x1000 (nếu crop=True thì cắt sát
        nội dung, giữ nguyên tỉ lệ).
        """
        world = self.rig.solve(angles)
        ordered = self.rig._ordered()
        ordered.sort(key=lambda b: world[b.name]["layer"])
        ordered = self._add_props(ordered, world, props)

        if self._cv_ok:
            return self._render_cv(world, ordered, mouth_open, crop, expression)

        canvas = Image.new("RGBA", (PART_W, PART_H), (0, 0, 0, 0))

        for b, is_outline in self._sequence(ordered, world):
            filename, pivot_img = self._resolve(b, is_outline, mouth_open, expression)
            img = self._part(filename)
            angle = world[b.name]["angle"]

            # Xoay quanh khớp (PIL xoay ngược chiều kim đồng hồ)
            if abs(angle) > 1e-6:
                # đặt vào khung vuông tâm ở khớp rồi xoay, để không bị cắt
                r = int(math.ceil(max(math.hypot(cx - pivot_img[0], cy - pivot_img[1])
                                      for cx in (0, img.width)
                                      for cy in (0, img.height)))) + 2
                ox, oy = int(round(r - pivot_img[0])), int(round(r - pivot_img[1]))
                padded = Image.new("RGBA", (2 * r + 1, 2 * r + 1), (0, 0, 0, 0))
                padded.paste(img, (ox, oy))
                pivot_img = (pivot_img[0] + ox, pivot_img[1] + oy)
                img = padded.rotate(-math.degrees(angle), resample=Image.BICUBIC,
                                    center=pivot_img)

            # Khớp thế giới (khung 600x1000) -> khung canvas có lề
            wp = world[b.name]["pivot"]
            x = int(round(wp[0] + PAD_X - pivot_img[0]))
            y = int(round(wp[1] + PAD_Y - pivot_img[1]))
            canvas.alpha_composite(img, (x, y))

        if not crop:
            return canvas

        # Cắt sát nội dung rồi đưa về khung gốc 600x1000
        bbox = canvas.getbbox()
        if bbox is None:
            return Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        cropped = canvas.crop(bbox)
        # vị trí của khung gốc trong ảnh đã cắt
        ox, oy = bbox[0] - PAD_X, bbox[1] - PAD_Y
        out = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        out.alpha_composite(cropped, (-ox, -oy))
        return out

    # ------------------------------------------------------- render nhanh (OpenCV)

    def _render_cv(self, world: dict, ordered: list[Bone],
                   mouth_open: bool, crop: bool,
                   expression: str | None = None) -> Image.Image:
        """Render bằng OpenCV warpAffine + numpy — nhanh hơn PIL rotate nhiều lần.

        Mỗi bộ phận được xoay quanh khớp bằng phép biến đổi phẳng (affine)
        rồi trộn alpha trên mảng numpy. Kết quả giống hệt đường PIL.
        """
        cv2 = self._cv
        np = self._np
        canvas = np.zeros((PART_H, PART_W, 4), dtype=np.uint8)

        for b, is_outline in self._sequence(ordered, world):
            filename, pivot0 = self._resolve(b, is_outline, mouth_open, expression)
            angle = world[b.name]["angle"]
            if abs(angle) > 1e-6:
                # khung vuông tâm ở khớp: xoay góc nào cũng không bị cắt
                part, pivot_img = self._padded_np(filename, pivot0)
            else:
                part, pivot_img = self._part_np(filename), pivot0
            ph, pw = part.shape[:2]

            if abs(angle) > 1e-6:
                # PIL xoay ngược chiều kim đồng hồ -> cv2 dùng góc âm
                deg = -math.degrees(angle)
                M = cv2.getRotationMatrix2D((float(pivot_img[0]), float(pivot_img[1])),
                                            deg, 1.0)
                warped = cv2.warpAffine(part, M, (pw, ph),
                                        flags=cv2.INTER_LINEAR,
                                        borderMode=cv2.BORDER_CONSTANT,
                                        borderValue=(0, 0, 0, 0))
            else:
                warped = part

            # Khớp thế giới (khung 600x1000) -> khung canvas có lề
            wp = world[b.name]["pivot"]
            x = int(round(wp[0] + PAD_X - pivot_img[0]))
            y = int(round(wp[1] + PAD_Y - pivot_img[1]))

            # Cắt phần vẽ ra ngoài canvas rồi trộn alpha
            sx0, sy0 = max(0, -x), max(0, -y)
            dx0, dy0 = max(0, x), max(0, y)
            cw = min(pw - sx0, PART_W - dx0)
            chh = min(ph - sy0, PART_H - dy0)
            if cw <= 0 or chh <= 0:
                continue
            src = warped[sy0:sy0 + chh, sx0:sx0 + cw]
            dst = canvas[dy0:dy0 + chh, dx0:dx0 + cw]
            a = src[..., 3:4].astype(np.float32) / 255.0
            rgb = src[..., :3].astype(np.float32)
            dst_rgb = dst[..., :3].astype(np.float32)
            out_rgb = rgb * a + dst_rgb * (1.0 - a)
            out_a = src[..., 3].astype(np.float32) + dst[..., 3].astype(np.float32) * (1.0 - a[..., 0])
            dst[..., :3] = out_rgb.astype(np.uint8)
            dst[..., 3] = np.clip(out_a, 0, 255).astype(np.uint8)

        img = Image.fromarray(canvas, "RGBA")
        if not crop:
            return img

        bbox = img.getbbox()
        if bbox is None:
            return Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        cropped = img.crop(bbox)
        ox, oy = bbox[0] - PAD_X, bbox[1] - PAD_Y
        out = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        out.alpha_composite(cropped, (-ox, -oy))
        return out

    def _padded_np(self, filename: str, pivot: tuple[float, float]):
        """Bộ phận đặt giữa khung vuông có tâm ở khớp (cache).

        Trả về (mảng, pivot mới). Bán kính khung = khoảng cách xa nhất từ
        khớp tới góc ảnh, nên xoay quanh khớp không mất phần nào.
        """
        key = (filename, round(pivot[0], 2), round(pivot[1], 2))
        hit = self._np_cache.get(key)
        if hit is None:
            np = self._np
            part = self._part_np(filename)
            ph, pw = part.shape[:2]
            px, py = float(pivot[0]), float(pivot[1])
            r = int(math.ceil(max(math.hypot(cx - px, cy - py)
                                  for cx in (0, pw) for cy in (0, ph)))) + 2
            out = np.zeros((2 * r + 1, 2 * r + 1, 4), dtype=np.uint8)
            ox, oy = int(round(r - px)), int(round(r - py))
            out[oy:oy + ph, ox:ox + pw] = part
            hit = (out, (px + ox, py + oy))
            self._np_cache[key] = hit
        return hit

    def _part_np(self, filename: str):
        """Bộ phận dạng mảng numpy (cache)."""
        arr = self._np_cache.get(filename)
        if arr is None:
            arr = self._np.array(self._part(filename).convert("RGBA"))
            self._np_cache[filename] = arr
        return arr


# ------------------------------------------------------------------ cử chỉ

def wave_angles(t: float, side: str = "right", speed: float = 3.2,
                raise_deg: float = -115.0, swing_deg: float = 24.0) -> dict[str, float]:
    """Góc xương cho cử chỉ vẫy tay.

    - Cánh tay trên giơ lên (xoay quanh vai)
    - Cẳng tay đung đưa (xoay quanh khuỷu)
    """
    rad = math.radians
    swing = math.sin(t * speed) * rad(swing_deg)
    return {
        f"vai_{side}": rad(raise_deg),
        f"khuyu_{side}": swing,
        f"co_tay_{side}": swing * 0.35,
    }


def idle_angles(t: float) -> dict[str, float]:
    """Cử động nhẹ khi đứng yên: thở và nghiêng đầu rất nhẹ."""
    rad = math.radians
    return {
        "than": math.sin(t * 1.4) * rad(0.7),
        "co": math.sin(t * 1.4 + 0.4) * rad(1.2),
        "dau": math.sin(t * 1.1 + 0.7) * rad(1.6),
    }


def merge(*angle_dicts: dict[str, float]) -> dict[str, float]:
    """Gộp nhiều bộ góc, bộ sau ghi đè bộ trước."""
    out: dict[str, float] = {}
    for d in angle_dicts:
        out.update(d)
    return out


class CharacterAnimator:
    """Animator cho mot nhan vat co rig.

    Moi khung: gesture (neu co) + hieu ung ca nguoi + tho/idle + cu dong tay
    khi noi (seed co dinh theo ten nhan vat).
    """

    def __init__(self, rig: Rig, base_dir: Path, name: str):
        self.rig = rig
        self.renderer = RigRenderer(rig, base_dir)
        self.name = name
        self.seed = stable_seed(name)
        self.current_gesture: Gesture | None = None
        self.current_effect: str | None = None
        self.gesture_start: float | None = None
        # đạo cụ đang cầm: {"right"/"left"/"both": tên}, và lúc cầm lên
        self.props: dict[str, str] = {}
        self.prop_since: dict[str, float] = {}
        # gáy (cảnh qua vai) — chỉ kiểu nét mềm có hình sau lưng
        self.back_head = self._back_head if rig.spec.get("style") in SOFT_STYLES else None
        self._back_cache = None

    def _head_center(self, angles: dict[str, float]) -> tuple[float, float] | None:
        """Tâm đầu thật (toạ độ khung gốc 600x1000) — máy quay bám theo khi
        nhân vật nằm, bò, ngã."""
        try:
            w = self.rig.solve(angles).get("dau")
            spec = CharSpec.from_dict(self.rig.spec)
            ry = geometry(spec.body, spec.style).head_ry
            a = w["angle"]
            return (w["pivot"][0] + ry * 0.9 * math.sin(a), w["pivot"][1] - ry * 0.9 * math.cos(a))
        except Exception:  # noqa: BLE001
            return None

    def _back_head(self):
        """(ảnh gáy cắt sát, màu áo) cho cảnh qua vai."""
        if self._back_cache is None:
            spec = CharSpec.from_dict(self.rig.spec)
            dong, _mo, _pv = head_images(spec, "__back__")
            img = dong.crop(dong.getbbox()) if dong.getbbox() else dong
            img = _outline_img(img).copy()
            img.alpha_composite(dong.crop(dong.getbbox()), (SOFT_OUTLINE, SOFT_OUTLINE))
            shirt = (GRAY_SKIN if spec.style == "gray"
                     else ck.SHIRT_COLORS.get(spec.shirt, ck.SHIRT_COLORS["blue"]) + (255,))
            self._back_cache = (img, shirt)
        return self._back_cache

    def set_props(self, change: dict[str, str] | None, t: float) -> None:
        """Đổi đạo cụ đang cầm ("" = bỏ xuống). Không đổi thì giữ nguyên."""
        if not change:
            return
        for side, name in change.items():
            if side == "all":                      # bỏ hết đồ trên tay
                self.props.clear()
                continue
            if side == "both" and name:
                self.props.clear()
            elif name and "both" in self.props:
                self.props.pop("both", None)
            if name:
                if self.props.get(side) != name:
                    self.prop_since[side] = t
                self.props[side] = name
            else:
                self.props.pop(side, None)

    def set_gesture(self, name: str | None, effect: str | None,
                    start_time: float) -> None:
        """Thiet lap cu chi / hieu ung moi, bat dau tinh gio tu start_time.
        Cu chi cu nhat dan ve tu the dung (khong giat)."""
        if self.current_gesture is not None and self.gesture_start is not None:
            self._fade_from = gesture_pose(self.current_gesture,
                                           start_time - self.gesture_start)
            self._fade_t0 = start_time
        if name is None:
            self.current_gesture = None
            self.gesture_start = None
        else:
            _, lib = ensure_library()
            self.current_gesture = lib.get(name)
            self.gesture_start = start_time
        self.current_effect = effect

    def angles_at(self, t: float, speaking: bool, mouth_open: bool
                  ) -> dict[str, float]:
        """Goc xuong tai thoi diem t (giay) cua nhan vat nay."""
        angles: dict[str, float] = {}

        # 1. Tho nhe khi dung yen (luon co, rat nhe)
        angles = merge(angles, breathe_angles(t, self.seed))

        # 2. Cu dong tay nho khi dang noi (seed co dinh)
        if speaking:
            angles = merge(angles, idle_arm_angles(t, self.seed))

        # 3. Hieu ung ca nguoi (ap lien tuc)
        if self.current_effect:
            angles = merge(angles, effect_angles(self.current_effect, t, self.seed))

        # 3b. Tu the cam do (dien thoai truoc nguc, bung noi...) — cu chi de len
        angles = merge(angles, hold_angles(self.props, self.prop_since, t))

        # 4. Cu chi cu nhat dan + cu chi hien tai
        angles = merge(angles, fade_pose(getattr(self, "_fade_from", None),
                                         getattr(self, "_fade_t0", 0.0), t))
        if self.current_gesture is not None and self.gesture_start is not None:
            pose = gesture_pose(self.current_gesture, t - self.gesture_start)
            if pose:
                angles = merge(angles, pose)

        return angles

    def render_frame(self, t: float, speaking: bool, mouth_open: bool,
                     canvas_size: tuple[int, int] | None = None,
                     expression: str | None = None) -> Image.Image:
        """Render mot khung hinh nhan vat (trong khung goc 600x1000, scale ve
        canvas_size neu co). Goc vua dung luu o self.last_angles (gom ca
        dich_x/dich_y de dat vi tri nhan vat)."""
        angles = self.angles_at(t, speaking, mouth_open)
        if self.rig.spec.get("style") in BIG_HEAD:
            angles = stick_arm_limits(angles)
        self.last_angles = angles
        if canvas_size is None:
            # Không cắt về khung 600x1000 (tay giơ cao/dang rộng sẽ bị mất):
            # trả về ảnh sát nội dung, kèm vị trí khung gốc trong ảnh để
            # người đặt nhân vật giữ đúng chỗ đứng (frame_origin, frame_size).
            img = self.renderer.render(angles, mouth_open=mouth_open, crop=False,
                                       expression=expression, props=self.props)
            self.head_pos = self._head_center(angles)
            bbox = img.getbbox() or (PAD_X, PAD_Y, PAD_X + CW, PAD_Y + CH)
            self.frame_origin = (PAD_X - bbox[0], PAD_Y - bbox[1])
            self.frame_size = (CW, CH)
            return img.crop(bbox)
        img = self.renderer.render(angles, mouth_open=mouth_open, expression=expression,
                                   props=self.props)
        if img.size != canvas_size:
            img = img.resize(canvas_size, Image.LANCZOS)
        return img
