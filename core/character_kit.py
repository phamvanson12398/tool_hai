# -*- coding: utf-8 -*-
"""Bộ ghép nhân vật: vẽ nhân vật bằng các bộ phận cùng phong cách.

Phong cách: màu đơn giản, nét phẳng (flat), viền đậm — khớp với bối cảnh.
Mỗi nhân vật = một bộ tham số (kiểu tóc, màu tóc, da, áo, phụ kiện, dáng
người lớn / trẻ con). Tool ráp ra đủ mọi biểu cảm × miệng mở/ngậm, luôn khớp.

Vẽ bằng Pillow nên không cần model ảnh, chạy tức thì và kết quả nhất quán
giữa các tập.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from .comedy_lib import VALID_EXPRESSIONS

# Khung ảnh nhân vật
W, H = 600, 1000
OUTLINE = (40, 36, 48, 255)
LW = 7                      # độ dày nét

# ---------------------------------------------------------------- bộ phận

SKIN_TONES = {
    "light": (255, 224, 196),
    "fair": (248, 208, 178),
    "medium": (232, 184, 146),
    "tan": (205, 150, 110),
    "deep": (150, 100, 70),
}

HAIR_COLORS = {
    "black": (40, 36, 44),
    "darkbrown": (74, 52, 40),
    "brown": (118, 80, 52),
    "chestnut": (150, 94, 58),
    "blonde": (226, 188, 110),
    "red": (186, 84, 56),
    "ash": (150, 146, 156),
    "pink": (226, 134, 168),
    "blue": (92, 120, 188),
}

HAIR_STYLES = [
    "short", "bob", "long", "ponytail", "twintails", "bun",
    "curly", "buzz", "wavy", "sidepart", "bowl",
]

SHIRT_COLORS = {
    "white": (248, 248, 250),
    "cream": (244, 232, 206),
    "red": (214, 84, 76),
    "blue": (84, 124, 200),
    "navy": (56, 70, 112),
    "green": (96, 168, 112),
    "yellow": (238, 198, 86),
    "pink": (238, 164, 188),
    "purple": (150, 122, 198),
    "gray": (158, 158, 166),
    "black": (62, 60, 70),
    "mint": (148, 212, 196),
}

ACCESSORIES = ["none", "glasses", "sunglasses", "earrings", "cap", "headband", "mask",
               "curlers", "visor"]

BODIES = ["adult", "child"]

# Kiểu vẽ:
#   stick  = người que đầu to, tay chân nét đen
#   box    = người que thân vuông mặc quần áo (đầu tròn to như người que)
#   kchibi = webtoon Hàn: đầu rất to, người ngắn, mặt kiểu meme Hàn (^^, ㅠㅠ, -_-)
#   flat   = hoạt hình phẳng kiểu cũ
STYLES = ["stick", "box", "kchibi", "flat"]

# Trang phục (dùng cho box và kchibi) — nhiều kiểu quen thuộc trong hài Hàn
OUTFITS = [
    "tshirt", "hoodie", "school_uniform", "suit", "apron", "hiking",
    "padding", "cardigan", "dress", "hanbok",
]

PANTS_COLORS = {
    "navy": (52, 62, 100),
    "black": (50, 50, 58),
    "gray": (128, 130, 140),
    "denim": (86, 120, 172),
    "beige": (210, 190, 150),
    "brown": (120, 86, 60),
    "green": (84, 120, 84),
}


@dataclass
class CharSpec:
    """Bộ tham số của một nhân vật."""
    name: str
    body: str = "adult"             # adult | child
    skin: str = "light"
    hair_style: str = "short"
    hair_color: str = "black"
    shirt: str = "blue"
    accessory: str = "none"
    blush: bool = False
    style: str = "flat"             # stick | box | kchibi | flat
    outfit: str = "tshirt"          # trang phục (box, kchibi)
    pants: str = "navy"             # màu quần (box, kchibi)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "body": self.body, "skin": self.skin,
            "hair_style": self.hair_style, "hair_color": self.hair_color,
            "shirt": self.shirt, "accessory": self.accessory,
            "blush": self.blush, "style": self.style,
            "outfit": self.outfit, "pants": self.pants,
        }

    @staticmethod
    def from_dict(d: dict) -> "CharSpec":
        return CharSpec(
            name=d.get("name", "char"),
            body=d.get("body", "adult"),
            skin=d.get("skin", "light"),
            hair_style=d.get("hair_style", "short"),
            hair_color=d.get("hair_color", "black"),
            shirt=d.get("shirt", "blue"),
            accessory=d.get("accessory", "none"),
            blush=bool(d.get("blush", False)),
            # nhân vật lưu từ trước chưa có style -> giữ kiểu phẳng như cũ
            style=d.get("style") if d.get("style") in STYLES else "flat",
            outfit=d.get("outfit") if d.get("outfit") in OUTFITS else "tshirt",
            pants=d.get("pants") if d.get("pants") in PANTS_COLORS else "navy",
        )


def options() -> dict:
    """Danh mục bộ phận cho Claude chọn."""
    return {
        "body": BODIES,
        "skin": list(SKIN_TONES),
        "hair_style": HAIR_STYLES,
        "hair_color": list(HAIR_COLORS),
        "shirt": list(SHIRT_COLORS),
        "accessory": ACCESSORIES,
        "outfit": OUTFITS,
        "pants": list(PANTS_COLORS),
        "expressions": sorted(VALID_EXPRESSIONS),
    }


# ------------------------------------------------------------- hình học

def _geom(body: str) -> dict:
    """Tỉ lệ cơ thể: người lớn đầu nhỏ, trẻ con đầu to."""
    if body == "child":
        return {
            "head_cx": W // 2, "head_cy": 300, "head_rx": 150, "head_ry": 160,
            "neck_w": 56, "shoulder_y": 470, "body_w": 300, "body_h": 420,
            "eye_dx": 58, "eye_y": 310, "eye_r": 22,
            "mouth_y": 390, "brow_y": 262,
        }
    return {
        "head_cx": W // 2, "head_cy": 250, "head_rx": 124, "head_ry": 140,
        "neck_w": 52, "shoulder_y": 400, "body_w": 330, "body_h": 520,
        "eye_dx": 48, "eye_y": 258, "eye_r": 18,
        "mouth_y": 326, "brow_y": 214,
    }


# ------------------------------------------------------------- biểu cảm

# Mỗi biểu cảm mô tả: mắt, lông mi/mày, má, mồ hôi, nước mắt
EXPRESSION_MAP = {
    "neutral":     dict(eye="open",   brow="flat",  mouth="small"),
    "happy":       dict(eye="smile",  brow="up",    mouth="smile", blush=True),
    "laughing":    dict(eye="closed", brow="up",    mouth="big_smile"),
    "proud":       dict(eye="smug",   brow="up",    mouth="smirk"),
    "smug":        dict(eye="smug",   brow="slant", mouth="smirk"),
    "sad":         dict(eye="sad",    brow="down",  mouth="frown", tear=True),
    "crying":      dict(eye="closed", brow="down",  mouth="open_frown", tear=True),
    "angry":       dict(eye="angry",  brow="angry", mouth="frown"),
    "annoyed":     dict(eye="half",   brow="angry", mouth="flat"),
    "shocked":     dict(eye="wide",   brow="up",    mouth="o", sweat=True),
    "surprised":   dict(eye="wide",   brow="up",    mouth="o"),
    "scared":      dict(eye="wide",   brow="worry", mouth="wiggle", sweat=True),
    "worried":     dict(eye="sad",    brow="worry", mouth="wiggle"),
    "confused":    dict(eye="half",   brow="slant", mouth="wiggle"),
    "thinking":    dict(eye="look_up", brow="flat", mouth="small"),
    "suspicious":  dict(eye="half",   brow="slant", mouth="flat"),
    "disgusted":   dict(eye="half",   brow="angry", mouth="wiggle"),
    "embarrassed": dict(eye="closed", brow="worry", mouth="wiggle", blush=True, sweat=True),
    "shy":         dict(eye="look_down", brow="worry", mouth="small", blush=True),
    "love":        dict(eye="heart",  brow="up",    mouth="smile", blush=True),
    "determined":  dict(eye="angry",  brow="angry", mouth="flat"),
    "tired":       dict(eye="half",   brow="down",  mouth="flat"),
    "bored":       dict(eye="half",   brow="flat",  mouth="flat"),
}


def _draw_body(d: ImageDraw.ImageDraw, spec: CharSpec, g: dict) -> None:
    skin = SKIN_TONES.get(spec.skin, SKIN_TONES["light"]) + (255,)
    shirt = SHIRT_COLORS.get(spec.shirt, SHIRT_COLORS["blue"]) + (255,)
    cx = g["head_cx"]

    # cổ
    d.rounded_rectangle(
        [cx - g["neck_w"] // 2, g["head_cy"] + g["head_ry"] - 20,
         cx + g["neck_w"] // 2, g["shoulder_y"] + 20],
        radius=18, fill=skin, outline=OUTLINE, width=LW,
    )
    # thân / áo
    bw, bh = g["body_w"], g["body_h"]
    d.rounded_rectangle(
        [cx - bw // 2, g["shoulder_y"], cx + bw // 2, g["shoulder_y"] + bh],
        radius=60, fill=shirt, outline=OUTLINE, width=LW,
    )
    # tay
    arm_w = 64 if spec.body == "adult" else 58
    for sgn in (-1, 1):
        ax = cx + sgn * (bw // 2 - 6)
        d.rounded_rectangle(
            [ax - arm_w // 2, g["shoulder_y"] + 30,
             ax + arm_w // 2, g["shoulder_y"] + bh - 60],
            radius=30, fill=shirt, outline=OUTLINE, width=LW,
        )
        # bàn tay
        d.ellipse([ax - 30, g["shoulder_y"] + bh - 90, ax + 30,
                   g["shoulder_y"] + bh - 30], fill=skin, outline=OUTLINE, width=LW)


def _draw_head(d: ImageDraw.ImageDraw, spec: CharSpec, g: dict) -> None:
    skin = SKIN_TONES.get(spec.skin, SKIN_TONES["light"]) + (255,)
    d.ellipse(
        [g["head_cx"] - g["head_rx"], g["head_cy"] - g["head_ry"],
         g["head_cx"] + g["head_rx"], g["head_cy"] + g["head_ry"]],
        fill=skin, outline=OUTLINE, width=LW,
    )


def _draw_hair(d: ImageDraw.ImageDraw, spec: CharSpec, g: dict) -> None:
    col = HAIR_COLORS.get(spec.hair_color, HAIR_COLORS["black"]) + (255,)
    cx, cy = g["head_cx"], g["head_cy"]
    rx, ry = g["head_rx"], g["head_ry"]
    st = spec.hair_style

    def cap():
        d.pieslice([cx - rx - 6, cy - ry - 10, cx + rx + 6, cy + ry * 0.5],
                   180, 360, fill=col, outline=OUTLINE, width=LW)

    if st == "buzz":
        d.pieslice([cx - rx, cy - ry, cx + rx, cy + ry * 0.2],
                   180, 360, fill=col, outline=OUTLINE, width=LW)
    elif st == "short":
        cap()
    elif st == "sidepart":
        cap()
        d.polygon([(cx - rx, cy - ry * 0.3), (cx + rx * 0.2, cy - ry - 4),
                   (cx + rx, cy - ry * 0.5), (cx - rx * 0.4, cy - ry * 0.1)],
                  fill=col, outline=OUTLINE)
    elif st == "bob":
        cap()
        for sgn in (-1, 1):
            d.rounded_rectangle(
                [cx + sgn * rx - 46 if sgn > 0 else cx - rx,
                 cy - ry * 0.4,
                 cx + rx if sgn > 0 else cx - rx + 46,
                 cy + ry * 0.9],
                radius=24, fill=col, outline=OUTLINE, width=LW)
    elif st in ("long", "wavy"):
        cap()                       # phần tóc dài phía sau vẽ ở _draw_back_hair
    elif st == "ponytail":
        cap()
        d.ellipse([cx + rx - 14, cy - ry * 0.2, cx + rx + 86, cy + ry * 1.1],
                  fill=col, outline=OUTLINE, width=LW)
    elif st == "twintails":
        cap()
        for sgn in (-1, 1):
            x = cx + sgn * (rx + 30)
            d.ellipse([x - 46, cy - ry * 0.1, x + 46, cy + ry * 1.0],
                      fill=col, outline=OUTLINE, width=LW)
    elif st == "bun":
        cap()
        d.ellipse([cx - 52, cy - ry - 78, cx + 52, cy - ry + 20],
                  fill=col, outline=OUTLINE, width=LW)
    elif st == "bowl":
        # tóc bát úp: phủ kín tới lông mày, mái cắt thẳng
        d.pieslice([cx - rx - 10, cy - ry - 14, cx + rx + 10, cy + ry * 0.36],
                   180, 360, fill=col, outline=OUTLINE, width=LW)
        d.rectangle([cx - rx - 10, cy - ry * 0.32, cx + rx + 10, cy - ry * 0.22], fill=col)
    elif st == "curly":
        cap()
        for i in range(7):
            a = math.pi * (0.08 + 0.14 * i)
            x = cx - math.cos(a) * (rx + 6)
            y = cy - math.sin(a) * (ry + 6)
            d.ellipse([x - 34, y - 34, x + 34, y + 34], fill=col,
                      outline=OUTLINE, width=max(2, LW - 3))
    else:
        cap()


def _draw_back_hair(d: ImageDraw.ImageDraw, spec: CharSpec, g: dict) -> None:
    """Tóc dài phía sau đầu — vẽ trước mặt để không che mặt."""
    if spec.hair_style not in ("long", "wavy"):
        return
    col = HAIR_COLORS.get(spec.hair_color, HAIR_COLORS["black"]) + (255,)
    cx, cy, rx, ry = g["head_cx"], g["head_cy"], g["head_rx"], g["head_ry"]
    d.rounded_rectangle([cx - rx - 10, cy - ry * 0.4, cx + rx + 10, cy + ry * 2.0],
                        radius=70, fill=col, outline=OUTLINE, width=LW)


def _draw_eyes(d: ImageDraw.ImageDraw, spec: CharSpec, g: dict, kind: str) -> None:
    cx, ey, dx, r = g["head_cx"], g["eye_y"], g["eye_dx"], g["eye_r"]
    white = (255, 255, 255, 255)
    for sgn in (-1, 1):
        x = cx + sgn * dx
        if kind == "closed":
            d.arc([x - r, ey - r, x + r, ey + r], 200, 340, fill=OUTLINE, width=LW)
        elif kind == "half":
            d.ellipse([x - r, ey - r, x + r, ey + r], fill=white, outline=OUTLINE, width=4)
            d.rectangle([x - r - 2, ey - r - 2, x + r + 2, ey], fill=(0, 0, 0, 0))
            d.line([x - r, ey, x + r, ey], fill=OUTLINE, width=LW)
            d.ellipse([x - r * 0.5, ey - r * 0.1, x + r * 0.5, ey + r * 0.7],
                      fill=OUTLINE)
        elif kind == "wide":
            rr = r * 1.4
            d.ellipse([x - rr, ey - rr, x + rr, ey + rr], fill=white,
                      outline=OUTLINE, width=5)
            d.ellipse([x - rr * 0.45, ey - rr * 0.45, x + rr * 0.45, ey + rr * 0.45],
                      fill=OUTLINE)
        elif kind == "smile":
            d.arc([x - r, ey - r * 1.2, x + r, ey + r * 0.8], 200, 340,
                  fill=OUTLINE, width=LW)
        elif kind == "sad":
            d.ellipse([x - r, ey - r, x + r, ey + r], fill=white, outline=OUTLINE, width=4)
            d.ellipse([x - r * 0.5, ey, x + r * 0.5, ey + r * 0.9], fill=OUTLINE)
        elif kind == "angry":
            d.ellipse([x - r, ey - r, x + r, ey + r], fill=white, outline=OUTLINE, width=4)
            d.ellipse([x - r * 0.5, ey - r * 0.2, x + r * 0.5, ey + r * 0.6], fill=OUTLINE)
        elif kind == "smug":
            d.arc([x - r, ey - r, x + r, ey + r * 0.6], 185, 355, fill=OUTLINE, width=LW)
            d.ellipse([x - r * 0.4, ey - r * 0.2, x + r * 0.4, ey + r * 0.5], fill=OUTLINE)
        elif kind == "heart":
            for off in (-1, 1):
                d.ellipse([x + off * r * 0.4 - r * 0.5, ey - r * 0.6,
                           x + off * r * 0.4 + r * 0.5, ey + r * 0.4],
                          fill=(226, 84, 120, 255))
            d.polygon([(x - r * 0.85, ey), (x + r * 0.85, ey), (x, ey + r)],
                      fill=(226, 84, 120, 255))
        elif kind in ("look_up", "look_down"):
            d.ellipse([x - r, ey - r, x + r, ey + r], fill=white, outline=OUTLINE, width=4)
            oy = -r * 0.45 if kind == "look_up" else r * 0.45
            d.ellipse([x - r * 0.45, ey + oy - r * 0.45,
                       x + r * 0.45, ey + oy + r * 0.45], fill=OUTLINE)
        else:  # open
            d.ellipse([x - r, ey - r, x + r, ey + r], fill=white, outline=OUTLINE, width=4)
            d.ellipse([x - r * 0.5, ey - r * 0.5, x + r * 0.5, ey + r * 0.5], fill=OUTLINE)


def _draw_brows(d: ImageDraw.ImageDraw, g: dict, kind: str) -> None:
    cx, by, dx = g["head_cx"], g["brow_y"], g["eye_dx"]
    span = 34
    for sgn in (-1, 1):
        x = cx + sgn * dx
        if kind == "up":
            d.line([x - span, by + 6, x + span, by - 8], fill=OUTLINE, width=LW)
        elif kind == "down":
            d.line([x - span, by - 6, x + span, by + 10], fill=OUTLINE, width=LW)
        elif kind == "angry":
            if sgn < 0:
                d.line([x - span, by - 10, x + span, by + 12], fill=OUTLINE, width=LW)
            else:
                d.line([x - span, by + 12, x + span, by - 10], fill=OUTLINE, width=LW)
        elif kind == "worry":
            if sgn < 0:
                d.line([x - span, by + 10, x + span, by - 6], fill=OUTLINE, width=LW)
            else:
                d.line([x - span, by - 6, x + span, by + 10], fill=OUTLINE, width=LW)
        elif kind == "slant":
            d.line([x - span, by + (4 if sgn < 0 else -4),
                    x + span, by + (-4 if sgn < 0 else 4)], fill=OUTLINE, width=LW)
        else:
            d.line([x - span, by, x + span, by], fill=OUTLINE, width=LW)


def _draw_mouth(d: ImageDraw.ImageDraw, g: dict, kind: str, open_mouth: bool) -> None:
    cx, my = g["head_cx"], g["mouth_y"]
    inner = (196, 84, 92, 255)
    if open_mouth:
        # miệng mở: hình bầu dục, to nhỏ tuỳ biểu cảm
        w = 52 if kind in ("o", "open_frown", "big_smile") else 40
        h = 46 if kind in ("o", "big_smile") else 34
        d.ellipse([cx - w, my - h // 2, cx + w, my + h], fill=inner,
                  outline=OUTLINE, width=LW)
        return
    if kind == "smile":
        d.arc([cx - 48, my - 32, cx + 48, my + 26], 10, 170, fill=OUTLINE, width=LW)
    elif kind == "big_smile":
        d.chord([cx - 56, my - 36, cx + 56, my + 32], 0, 180, fill=inner,
                outline=OUTLINE, width=LW)
    elif kind == "smirk":
        d.arc([cx - 20, my - 26, cx + 56, my + 18], 10, 150, fill=OUTLINE, width=LW)
    elif kind == "frown":
        d.arc([cx - 46, my - 6, cx + 46, my + 48], 190, 350, fill=OUTLINE, width=LW)
    elif kind == "open_frown":
        d.ellipse([cx - 40, my - 14, cx + 40, my + 36], fill=inner,
                  outline=OUTLINE, width=LW)
    elif kind == "o":
        d.ellipse([cx - 28, my - 24, cx + 28, my + 30], fill=inner,
                  outline=OUTLINE, width=LW)
    elif kind == "wiggle":
        pts = []
        for i in range(9):
            x = cx - 40 + i * 10
            y = my + (8 if i % 2 else -6)
            pts.append((x, y))
        d.line(pts, fill=OUTLINE, width=LW - 1, joint="curve")
    elif kind == "flat":
        d.line([cx - 36, my + 6, cx + 36, my + 6], fill=OUTLINE, width=LW)
    else:  # small
        d.line([cx - 22, my + 4, cx + 22, my + 4], fill=OUTLINE, width=LW)


def _draw_extras(d: ImageDraw.ImageDraw, spec: CharSpec, g: dict,
                 mood: dict) -> None:
    cx = g["head_cx"]
    # má hồng
    if mood.get("blush") or spec.blush:
        for sgn in (-1, 1):
            x = cx + sgn * (g["eye_dx"] + 42)
            d.ellipse([x - 26, g["eye_y"] + 30, x + 26, g["eye_y"] + 62],
                      fill=(240, 150, 160, 160))
    # mồ hôi
    if mood.get("sweat"):
        x = cx + g["head_rx"] - 10
        y = g["head_cy"] - g["head_ry"] + 50
        d.polygon([(x, y), (x + 20, y + 34), (x - 20, y + 34)],
                  fill=(140, 200, 240, 230), outline=OUTLINE)
    # nước mắt
    if mood.get("tear"):
        for sgn in (-1, 1):
            x = cx + sgn * g["eye_dx"]
            d.ellipse([x - 12, g["eye_y"] + 24, x + 12, g["eye_y"] + 72],
                      fill=(140, 200, 240, 230), outline=OUTLINE, width=3)

    # phụ kiện
    acc = spec.accessory
    if acc == "glasses":
        r = g["eye_r"] + 16
        for sgn in (-1, 1):
            x = cx + sgn * g["eye_dx"]
            d.ellipse([x - r, g["eye_y"] - r, x + r, g["eye_y"] + r],
                      outline=OUTLINE, width=6)
        d.line([cx - g["eye_dx"] + r, g["eye_y"], cx + g["eye_dx"] - r, g["eye_y"]],
               fill=OUTLINE, width=5)
    elif acc == "sunglasses":
        r = g["eye_r"] + 16
        for sgn in (-1, 1):
            x = cx + sgn * g["eye_dx"]
            d.ellipse([x - r, g["eye_y"] - r, x + r, g["eye_y"] + r],
                      fill=(44, 44, 54, 255), outline=OUTLINE, width=5)
        d.line([cx - g["eye_dx"] + r, g["eye_y"], cx + g["eye_dx"] - r, g["eye_y"]],
               fill=OUTLINE, width=6)
    elif acc == "earrings":
        for sgn in (-1, 1):
            x = cx + sgn * g["head_rx"]
            d.ellipse([x - 12, g["head_cy"] + 40, x + 12, g["head_cy"] + 64],
                      fill=(238, 198, 86, 255), outline=OUTLINE, width=3)
    elif acc == "cap":
        d.pieslice([cx - g["head_rx"] - 8, g["head_cy"] - g["head_ry"] - 24,
                    cx + g["head_rx"] + 8, g["head_cy"] - g["head_ry"] * 0.1],
                   180, 360, fill=(84, 124, 200, 255), outline=OUTLINE, width=LW)
        d.rounded_rectangle([cx - 10, g["head_cy"] - g["head_ry"] * 0.35,
                             cx + g["head_rx"] + 90, g["head_cy"] - g["head_ry"] * 0.05],
                            radius=14, fill=(84, 124, 200, 255),
                            outline=OUTLINE, width=LW)
    elif acc == "headband":
        d.arc([cx - g["head_rx"] - 6, g["head_cy"] - g["head_ry"] - 6,
               cx + g["head_rx"] + 6, g["head_cy"] + g["head_ry"] * 0.3],
              190, 350, fill=(226, 134, 168, 255), width=18)
    elif acc == "mask":
        d.rounded_rectangle([cx - 76, g["mouth_y"] - 46, cx + 76, g["mouth_y"] + 56],
                            radius=24, fill=(240, 244, 250, 255),
                            outline=OUTLINE, width=LW)
    elif acc == "curlers":
        # lô cuốn tóc kiểu ajumma (헤어롤)
        top = g["head_cy"] - g["head_ry"]
        for i, dx in enumerate((-0.55, 0.0, 0.55)):
            x = cx + dx * g["head_rx"]
            y = top + (26 if i != 1 else 4)
            d.rounded_rectangle([x - 30, y - 26, x + 30, y + 26], radius=14,
                                fill=(236, 140, 172, 255), outline=OUTLINE, width=5)
            for k in (-12, 0, 12):
                d.line([x + k, y - 22, x + k, y + 22], fill=(200, 96, 132, 255), width=3)
    elif acc == "visor":
        # mũ lưỡi trai nửa đầu (선캡): quai trắng quanh đầu, vành xanh ngay trên mắt
        rx, ry, cy = g["head_rx"], g["head_ry"], g["head_cy"]
        eb = g["eye_y"] - g["eye_r"] * 1.7           # mép dưới vành, trên mắt
        bt = eb - ry * 0.55
        d.arc([cx - rx - 6, cy - ry - 6, cx + rx + 6, cy + ry * 0.2], 190, 350,
              fill=(250, 250, 250, 255), width=16)
        d.chord([cx - rx * 0.95, bt, cx + rx * 0.95, eb], 0, 180,
                fill=(120, 190, 220, 230), outline=OUTLINE, width=5)


def render_character(spec: CharSpec, expression: str = "neutral",
                     mouth_open: bool = False) -> Image.Image:
    """Vẽ một nhân vật với biểu cảm và trạng thái miệng cho trước."""
    if spec.style in ("stick", "box", "kchibi"):
        # dựng từ bộ xương (cùng bộ phận với chế độ cử động)
        from .rig import render_still
        return render_still(spec, expression, mouth_open)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    g = _geom(spec.body)
    mood = EXPRESSION_MAP.get(expression, EXPRESSION_MAP["neutral"])

    _draw_body(d, spec, g)
    _draw_back_hair(d, spec, g)
    _draw_head(d, spec, g)
    _draw_hair(d, spec, g)
    _draw_brows(d, g, mood["brow"])
    _draw_eyes(d, spec, g, mood["eye"])
    _draw_mouth(d, g, mood["mouth"], mouth_open)
    _draw_extras(d, spec, g, mood)

    return img.crop(img.getbbox() or (0, 0, W, H))


def build_sheet(spec: CharSpec, out_dir: Path,
                expressions: list[str] | None = None) -> dict:
    """Ráp đủ biểu cảm × miệng mở/ngậm, lưu ra file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    exprs = expressions or sorted(EXPRESSION_MAP)
    result: dict[str, dict[str, str]] = {}
    safe = "".join(c for c in spec.name if c.isalnum() or c in "-_") or "char"
    for e in exprs:
        result[e] = {}
        for open_m, tag in ((False, "dong"), (True, "mo")):
            img = render_character(spec, e, open_m)
            p = out_dir / f"{safe}_{e}_{tag}.png"
            img.save(p)
            result[e][tag] = str(p)
    return result


def preview_cast(specs: list[CharSpec], out_path: Path) -> Path:
    """Ảnh xem trước cả dàn nhân vật để chị duyệt phong cách."""
    imgs = [render_character(s, "happy", False) for s in specs]
    pad = 40
    th = 760
    scaled = []
    for im in imgs:
        r = th / im.height
        scaled.append(im.resize((max(1, int(im.width * r)), th), Image.LANCZOS))
    tw = sum(i.width for i in scaled) + pad * (len(scaled) + 1)
    sheet = Image.new("RGBA", (tw, th + pad * 2), (248, 246, 242, 255))
    x = pad
    for im in scaled:
        sheet.alpha_composite(im, (x, pad))
        x += im.width + pad
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(out_path)
    return out_path
