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
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from . import character_kit as ck
from .character_kit import CharSpec
from .gestures import (Gesture, breathe_angles, effect_angles,  # noqa: E402
                       ensure_library, gesture_pose, idle_arm_angles,
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
              expression: str = "neutral") -> Image.Image:
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
        d.rounded_rectangle(rect(cx - rx - 12, cy - ry * 0.5,
                                 cx + rx + 12, cy + ry * 1.8),
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
    elif st == "curly":
        d.pieslice(pie(cx - rx - 6, cy - ry - 10, cx + rx + 6, cy - ry * 0.25),
                   180, 360, fill=col, outline=OUTLINE, width=LW)
        for i in range(7):
            a = math.pi * (0.08 + 0.14 * i)
            x = cx - math.cos(a) * (rx + 6)
            y = cy - math.sin(a) * (ry + 6)
            d.ellipse(ell(x - 34, y - 34, x + 34, y + 34), fill=col,
                      outline=OUTLINE, width=max(2, LW - 3))
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

    # 4. chi tiết mặt theo biểu cảm + phụ kiện
    _draw_face(img, spec, g, expression, mouth_open, accessories=False)
    _accessories(d, spec, cg, S, rect, ell, pie)
    return img


def _accessories(d, spec, cg, S, rect, ell, pie) -> None:
    """Kính, mũ, khăn, vòng tai — vẽ bằng toạ độ đã lề."""
    cx, ey, dx = cg["head_cx"], cg["eye_y"], cg["eye_dx"]
    rx, ry = cg["head_rx"], cg["head_ry"]
    cy = cg["head_cy"]
    acc = spec.accessory
    if acc == "glasses":
        r = cg["eye_r"] + 16
        for sgn in (-1, 1):
            x = cx + sgn * dx
            d.ellipse(ell(x - r, ey - r, x + r, ey + r), outline=OUTLINE, width=6)
        a, b = S(cx - dx + r, ey)
        c, e = S(cx + dx - r, ey)
        d.line([a, b, c, e], fill=OUTLINE, width=5)
    elif acc == "sunglasses":
        r = cg["eye_r"] + 16
        for sgn in (-1, 1):
            x = cx + sgn * dx
            d.ellipse(ell(x - r, ey - r, x + r, ey + r),
                      fill=(44, 44, 54, 255), outline=OUTLINE, width=5)
        a, b = S(cx - dx + r, ey)
        c, e = S(cx + dx - r, ey)
        d.line([a, b, c, e], fill=OUTLINE, width=6)
    elif acc == "earrings":
        for sgn in (-1, 1):
            x = cx + sgn * rx
            d.ellipse(ell(x - 12, cy + 40, x + 12, cy + 64),
                      fill=(238, 198, 86, 255), outline=OUTLINE, width=3)
    elif acc == "cap":
        d.pieslice(pie(cx - rx - 8, cy - ry - 24, cx + rx + 8, cy - ry * 0.1),
                   180, 360, fill=(84, 124, 200, 255), outline=OUTLINE, width=LW)
        d.rounded_rectangle(rect(cx - 10, cy - ry * 0.35, cx + rx + 90, cy - ry * 0.05),
                            radius=14, fill=(84, 124, 200, 255),
                            outline=OUTLINE, width=LW)
    elif acc == "headband":
        a, b = S(cx - rx - 6, cy - ry - 6)
        c, e = S(cx + rx + 6, cy + ry * 0.3)
        d.arc([a, b, c, e], 190, 350, fill=(226, 134, 168, 255), width=18)
    elif acc == "mask":
        my = cg["mouth_y"]
        d.rounded_rectangle(rect(cx - 76, my - 46, cx + 76, my + 56),
                            radius=24, fill=(240, 244, 250, 255),
                            outline=OUTLINE, width=LW)


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
    if spec.style == "stick":
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


def _parts_for(spec: CharSpec, g: Geometry):
    """Bảng hàm vẽ bộ phận theo kiểu nhân vật."""
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


# ------------------------------------------------------------------ xương

@dataclass
class Bone:
    """Một xương: bộ phận ảnh + khớp + góc xoay tương đối so với xương cha."""
    name: str
    parent: str | None
    offset: tuple[float, float]     # lệch từ khớp cha tới khớp mình
    part: str                       # tên file ảnh trong thư mục parts/
    pivot: tuple[float, float]      # pivot trong ảnh (px)
    layer: int
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
            layer=int(d.get("layer", 0)), angle=float(d.get("angle", 0.0)),
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
    rest = STICK_REST if spec.style == "stick" else {}
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

    # --- tay --- (người que: cả hai tay nằm sau đầu để không che mặt)
    arm_layers = (("left", LAYER_THAN), ("right", LAYER_THAN)) if spec.style == "stick" \
        else (("left", LAYER_TAY_SAU), ("right", LAYER_TAY_TRUOC))
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

    # --- chân ---
    for side in ("left", "right"):
        sgn = 1 if side == "right" else -1
        hip_joint = (g.head_cx + sgn * g.hip_dx, g.hip[1])
        knee = (hip_joint[0], hip_joint[1] + g.thigh_len)
        ankle = (hip_joint[0], knee[1] + g.shin_len)
        add(f"dui_{side}", "than", hip_joint,
            (hip_joint[0] - hip[0], hip_joint[1] - hip[1]),
            f"dui_{side}.png", _p(hip_joint), LAYER_CHAN, fn["thigh"](spec, g, side))
        add(f"goi_{side}", f"dui_{side}", knee,
            (knee[0] - hip_joint[0], knee[1] - hip_joint[1]),
            f"goi_{side}.png", _p(knee), LAYER_CHAN, fn["shin"](spec, g, side))
        add(f"co_chan_{side}", f"goi_{side}", ankle,
            (ankle[0] - knee[0], ankle[1] - knee[1]),
            f"co_chan_{side}.png", _p(ankle), LAYER_CHAN, fn["foot"](spec, g, side))

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
            img = Image.open(self.parts_dir / filename).convert("RGBA")
            self._cache[filename] = img
        return img

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
               crop: bool = True, expression: str | None = None) -> Image.Image:
        """Vẽ một khung nhân vật theo góc xương cho trước.

        Kết quả trả về trong khung gốc 600x1000 (nếu crop=True thì cắt sát
        nội dung, giữ nguyên tỉ lệ).
        """
        world = self.rig.solve(angles)
        ordered = self.rig._ordered()
        ordered.sort(key=lambda b: world[b.name]["layer"])

        if self._cv_ok:
            return self._render_cv(world, ordered, mouth_open, crop, expression)

        canvas = Image.new("RGBA", (PART_W, PART_H), (0, 0, 0, 0))

        for b in ordered:
            filename, pivot_img = b.part, b.pivot
            if b.name == "dau":
                filename, pivot_img = self._head_part(b, mouth_open, expression)
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

        for b in ordered:
            filename, pivot0 = b.part, b.pivot
            if b.name == "dau":
                filename, pivot0 = self._head_part(b, mouth_open, expression)
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

    def set_gesture(self, name: str | None, effect: str | None,
                    start_time: float) -> None:
        """Thiet lap cu chi / hieu ung moi, bat dau tinh gio tu start_time."""
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

        # 4. Cu chi (lap / giu tu the cuoi / ve tu tu, xem gesture_pose)
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
        if self.rig.spec.get("style") == "stick":
            angles = stick_arm_limits(angles)
        self.last_angles = angles
        if canvas_size is None:
            # Không cắt về khung 600x1000 (tay giơ cao/dang rộng sẽ bị mất):
            # trả về ảnh sát nội dung, kèm vị trí khung gốc trong ảnh để
            # người đặt nhân vật giữ đúng chỗ đứng (frame_origin, frame_size).
            img = self.renderer.render(angles, mouth_open=mouth_open, crop=False,
                                       expression=expression)
            bbox = img.getbbox() or (PAD_X, PAD_Y, PAD_X + CW, PAD_Y + CH)
            self.frame_origin = (PAD_X - bbox[0], PAD_Y - bbox[1])
            self.frame_size = (CW, CH)
            return img.crop(bbox)
        img = self.renderer.render(angles, mouth_open=mouth_open, expression=expression)
        if img.size != canvas_size:
            img = img.resize(canvas_size, Image.LANCZOS)
        return img
