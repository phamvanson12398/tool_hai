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


def geometry(body: str = "adult") -> Geometry:
    """Tỉ lệ xương, bám theo _geom() của character_kit để ảnh khớp nhau."""
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


def draw_head(spec: CharSpec, g: Geometry, mouth_open: bool) -> Image.Image:
    """Đầu (tóc + mặt + phụ kiện). Pivot ở chỗ cổ bám vào.

    Tóc dài vẽ SAU mặt, mũ tóc vẽ trên trán — không che mắt, miệng.
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

    # 4. chi tiết mặt + phụ kiện — vẽ bằng toạ độ đã lề
    _face_details(d, spec, cg, mouth_open, S, rect, ell, pie)
    _accessories(d, spec, cg, S, rect, ell, pie)
    return img


def _face_details(d, spec, cg, mouth_open, S, rect, ell, pie) -> None:
    """Mắt, lông mày, miệng — vẽ bằng toạ độ đã lề."""
    cx, ey, dx, r = cg["head_cx"], cg["eye_y"], cg["eye_dx"], cg["eye_r"]
    white = (255, 255, 255, 255)
    for sgn in (-1, 1):
        x = cx + sgn * dx
        d.ellipse(ell(x - r, ey - r, x + r, ey + r), fill=white,
                  outline=OUTLINE, width=4)
        d.ellipse(ell(x - r * 0.5, ey - r * 0.5, x + r * 0.5, ey + r * 0.5),
                  fill=OUTLINE)
    # lông mày
    by = cg["brow_y"]
    for sgn in (-1, 1):
        x = cx + sgn * dx
        a, b = S(x - 34, by)
        c, e = S(x + 34, by)
        d.line([a, b, c, e], fill=OUTLINE, width=LW)
    # miệng
    my = cg["mouth_y"]
    if mouth_open:
        d.ellipse(ell(cx - 40, my - 17, cx + 40, my + 17),
                  fill=(196, 84, 92, 255), outline=OUTLINE, width=LW)
    else:
        a, b = S(cx - 22, my + 4)
        c, e = S(cx + 22, my + 4)
        d.line([a, b, c, e], fill=OUTLINE, width=LW)


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
            local = angles.get(b.name, b.angle)
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

def build_rig(spec: CharSpec, out_dir: Path) -> Rig:
    """Vẽ các bộ phận, lưu ảnh + rig.json vào out_dir.

    out_dir sẽ chứa:
      rig.json
      parts/*.png
    """
    out_dir = Path(out_dir)
    parts_dir = out_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    g = geometry(spec.body)
    bones: list[Bone] = []

    def add(name, parent, joint, offset, part_name, pivot_canvas, layer,
            img: Image.Image) -> None:
        cropped, pivot = _crop_pivot(img, pivot_canvas)
        cropped.save(parts_dir / part_name)
        bones.append(Bone(name=name, parent=parent, offset=offset,
                          part=part_name, pivot=pivot, layer=layer))

    hip = g.hip
    neck = g.neck
    chin = g.chin

    # --- thân (root) ---
    add("than", None, hip, hip, "than.png", _p(hip), LAYER_THAN,
        draw_torso(spec, g))

    # --- cổ, con của thân ---
    add("co", "than", neck,
        (neck[0] - hip[0], neck[1] - hip[1]),
        "co.png", _p(neck), LAYER_THAN, draw_neck(spec, g))

    # --- đầu, con của cổ ---
    add("dau", "co", chin,
        (chin[0] - neck[0], chin[1] - neck[1]),
        "dau_dong.png", _p(chin), LAYER_DAU, draw_head(spec, g, False))
    head_open, _ = _crop_pivot(draw_head(spec, g, True), _p(chin))
    head_open.save(parts_dir / "dau_mo.png")

    # --- tay ---
    for side, layer in (("left", LAYER_TAY_SAU), ("right", LAYER_TAY_TRUOC)):
        sgn = 1 if side == "right" else -1
        shoulder = (g.head_cx + sgn * g.shoulder_dx, float(g.shoulder_y))
        elbow = (shoulder[0], shoulder[1] + g.upper_len)
        wrist = (shoulder[0], elbow[1] + g.fore_len)

        add(f"vai_{side}", "than", shoulder,
            (shoulder[0] - hip[0], shoulder[1] - hip[1]),
            f"vai_{side}.png", _p(shoulder), layer,
            draw_upper_arm(spec, g, side))
        add(f"khuyu_{side}", f"vai_{side}", elbow,
            (elbow[0] - shoulder[0], elbow[1] - shoulder[1]),
            f"khuyu_{side}.png", _p(elbow), layer,
            draw_forearm(spec, g, side))
        add(f"co_tay_{side}", f"khuyu_{side}", wrist,
            (wrist[0] - elbow[0], wrist[1] - elbow[1]),
            f"co_tay_{side}.png", _p(wrist), layer,
            draw_hand(spec, g, side))

    # --- chân ---
    for side in ("left", "right"):
        sgn = 1 if side == "right" else -1
        hip_joint = (g.head_cx + sgn * g.hip_dx, g.hip[1])
        knee = (hip_joint[0], hip_joint[1] + g.thigh_len)
        ankle = (hip_joint[0], knee[1] + g.shin_len)

        add(f"dui_{side}", "than", hip_joint,
            (hip_joint[0] - hip[0], hip_joint[1] - hip[1]),
            f"dui_{side}.png", _p(hip_joint), LAYER_CHAN,
            draw_thigh(spec, g, side))
        add(f"goi_{side}", f"dui_{side}", knee,
            (knee[0] - hip_joint[0], knee[1] - hip_joint[1]),
            f"goi_{side}.png", _p(knee), LAYER_CHAN,
            draw_shin(spec, g, side))
        add(f"co_chan_{side}", f"goi_{side}", ankle,
            (ankle[0] - knee[0], ankle[1] - knee[1]),
            f"co_chan_{side}.png", _p(ankle), LAYER_CHAN,
            draw_foot(spec, g, side))

    rig = Rig(name=spec.name, root="than", bones=bones,
              spec=spec.to_dict(), parts_dir="parts")
    (out_dir / "rig.json").write_text(
        json.dumps(rig.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return rig


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

    def render(self, angles: dict[str, float] | None = None,
               mouth_open: bool = False,
               crop: bool = True) -> Image.Image:
        """Vẽ một khung nhân vật theo góc xương cho trước.

        Kết quả trả về trong khung gốc 600x1000 (nếu crop=True thì cắt sát
        nội dung, giữ nguyên tỉ lệ).
        """
        world = self.rig.solve(angles)
        ordered = self.rig._ordered()
        ordered.sort(key=lambda b: world[b.name]["layer"])

        if self._cv_ok:
            return self._render_cv(world, ordered, mouth_open, crop)

        canvas = Image.new("RGBA", (PART_W, PART_H), (0, 0, 0, 0))

        for b in ordered:
            filename = b.part
            if b.name == "dau":
                filename = "dau_mo.png" if mouth_open else "dau_dong.png"
            img = self._part(filename)
            angle = world[b.name]["angle"]
            pivot_img = b.pivot

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
                   mouth_open: bool, crop: bool) -> Image.Image:
        """Render bằng OpenCV warpAffine + numpy — nhanh hơn PIL rotate nhiều lần.

        Mỗi bộ phận được xoay quanh khớp bằng phép biến đổi phẳng (affine)
        rồi trộn alpha trên mảng numpy. Kết quả giống hệt đường PIL.
        """
        cv2 = self._cv
        np = self._np
        canvas = np.zeros((PART_H, PART_W, 4), dtype=np.uint8)

        for b in ordered:
            filename = b.part
            if b.name == "dau":
                filename = "dau_mo.png" if mouth_open else "dau_dong.png"
            angle = world[b.name]["angle"]
            if abs(angle) > 1e-6:
                # khung vuông tâm ở khớp: xoay góc nào cũng không bị cắt
                part, pivot_img = self._padded_np(filename, b.pivot)
            else:
                part, pivot_img = self._part_np(filename), b.pivot
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
                     canvas_size: tuple[int, int] | None = None
                     ) -> Image.Image:
        """Render mot khung hinh nhan vat (trong khung goc 600x1000, scale ve
        canvas_size neu co). Goc vua dung luu o self.last_angles (gom ca
        dich_x/dich_y de dat vi tri nhan vat)."""
        angles = self.angles_at(t, speaking, mouth_open)
        self.last_angles = angles
        if canvas_size is None:
            # Không cắt về khung 600x1000 (tay giơ cao/dang rộng sẽ bị mất):
            # trả về ảnh sát nội dung, kèm vị trí khung gốc trong ảnh để
            # người đặt nhân vật giữ đúng chỗ đứng (frame_origin, frame_size).
            img = self.renderer.render(angles, mouth_open=mouth_open, crop=False)
            bbox = img.getbbox() or (PAD_X, PAD_Y, PAD_X + CW, PAD_Y + CH)
            self.frame_origin = (PAD_X - bbox[0], PAD_Y - bbox[1])
            self.frame_size = (CW, CH)
            return img.crop(bbox)
        img = self.renderer.render(angles, mouth_open=mouth_open)
        if img.size != canvas_size:
            img = img.resize(canvas_size, Image.LANCZOS)
        return img
