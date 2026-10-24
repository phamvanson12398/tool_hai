# -*- coding: utf-8 -*-
"""Bộ xương cho nhân vật con nhộng ở chế độ Phim: đầu, thân, hai tay, hai chân
ngắn (vẽ bằng nét dày viền đen như nét vẽ tay) để đi, chạy, vẫy, chỉ, ôm, ngồi,
nằm, cầm đồ vật...

Đầu và thân vẽ bằng doodle (cùng nét với chế độ Kể chuyện), cache theo biểu cảm /
miệng / mắt / hướng nhìn / độ phóng của máy quay. Tay chân vẽ mỗi khung bằng cv2
theo góc khớp, rồi mọi phần ghép bằng ma trận affine (kể cả máy quay), nên một
khung chỉ tốn vài mili giây mỗi nhân vật.

Quy ước góc (độ): tay / chân 0 = buông thẳng xuống, 90 = đưa ngang về phía trước
(hướng nhân vật đang nhìn), 180 = giơ thẳng lên, âm = ra sau. Khuỷu / gối cộng
thêm vào góc đoạn trên.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from . import doodle

OUT = doodle.OUT


def _aff(a, b):
    """Ghép hai ma trận 2x3: kết quả = a ∘ b (áp b trước)."""
    A = np.vstack([a, [0, 0, 1]])
    B = np.vstack([b, [0, 0, 1]])
    return (A @ B)[:2]


def _rot(deg, cx=0.0, cy=0.0):
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, -s, cx - c * cx + s * cy], [s, c, cy - s * cx - c * cy]], dtype=np.float64)


def _tr(dx, dy):
    return np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float64)


def _sc(sx, sy=None):
    return np.array([[sx, 0, 0], [0, sy if sy is not None else sx, 0]], dtype=np.float64)


def _pt(m, x, y):
    return (m[0, 0] * x + m[0, 1] * y + m[0, 2], m[1, 0] * x + m[1, 1] * y + m[1, 2])


def _premul(img: Image.Image) -> np.ndarray:
    a = np.asarray(img).astype(np.float32)
    a[..., :3] *= a[..., 3:4] / 255.0
    return np.clip(a + 0.5, 0, 255).astype(np.uint8)


def paste(canvas, arr, m, night=None):
    """Dán ảnh RGBA đã nhân alpha `arr` lên canvas theo ma trận m (ảnh -> canvas)."""
    import cv2
    h, w = arr.shape[:2]
    corners = [_pt(m, x, y) for x, y in ((0, 0), (w, 0), (0, h), (w, h))]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    H, W = canvas.shape[:2]
    x0, y0 = max(0, int(min(xs))), max(0, int(min(ys)))
    x1, y1 = min(W, int(math.ceil(max(xs)))), min(H, int(math.ceil(max(ys))))
    if x1 <= x0 or y1 <= y0:
        return
    M = (m - np.array([[0, 0, x0], [0, 0, y0]])).astype(np.float32)
    part = cv2.warpAffine(arr, M, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    inv = 255 - cv2.extractChannel(part, 3)
    reg = canvas[y0:y1, x0:x1]
    keep = cv2.multiply(reg, cv2.merge([inv, inv, inv]), scale=1 / 255.0)
    rgb = cv2.cvtColor(part, cv2.COLOR_RGBA2RGB)
    if night is not None:
        rgb = (rgb.astype(np.float32) * np.asarray(night, np.float32)).astype(np.uint8)
    canvas[y0:y1, x0:x1] = cv2.add(keep, rgb)


# ------------------------------------------------------------ đồ cầm tay

PROPS = {
    "bowl": "Bát cơm", "cup": "Chén nước", "letter": "Lá thư", "money": "Tiền",
    "basket": "Rổ, thúng", "stick": "Gậy", "book": "Quyển sách", "flower": "Bông hoa",
    "bag": "Tay nải", "bottle": "Chai, lọ", "knife": "Dao", "lamp": "Đèn dầu",
    "hoe": "Cái cuốc", "broom": "Chổi rơm", "axe": "Cái rìu", "sickle": "Cái liềm",
    "fan": "Quạt nan", "pipe": "Điếu cày", "pot": "Nồi", "pole": "Đòn gánh (hai thúng)",
}
# dụng cụ cầm cán: ảnh vẽ cán chĩa XUỐNG từ điểm cầm, khi vẽ xoay theo cẳng tay
TOOLS = {"hoe", "broom", "axe", "sickle", "fan", "knife", "stick"}


def prop_image(name: str, size: int) -> tuple[Image.Image, tuple[float, float]] | None:
    """Ảnh đồ vật + điểm cầm (toạ độ trong ảnh). size = cỡ tham chiếu (px)."""
    from . import doodle_parts
    s = max(8, int(size)) * doodle.SS
    W = H = int(s * 4.4)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pen = doodle._Pen(img, s * 3, 5)
    c = W / 2
    hold = (c, c)
    if name == "bowl":
        pen.shape(doodle._ellipse_pts(c, c - s * 0.1, s * 0.55, s * 0.4, 0, 180, 16), (236, 232, 222))
        pen.ell(c, c - s * 0.12, s * 0.55, s * 0.12, (250, 250, 246))
        pen.ell(c, c - s * 0.2, s * 0.42, s * 0.16, (252, 252, 252), outline=False)
        hold = (c, c + s * 0.15)
    elif name == "cup":
        pen.shape([(c - s * 0.25, c - s * 0.3), (c + s * 0.25, c - s * 0.3), (c + s * 0.18, c + s * 0.25),
                   (c - s * 0.18, c + s * 0.25)], (236, 232, 222))
        hold = (c, c + s * 0.05)
    elif name == "letter":
        pen.shape([(c - s * 0.45, c - s * 0.3), (c + s * 0.45, c - s * 0.3), (c + s * 0.45, c + s * 0.3),
                   (c - s * 0.45, c + s * 0.3)], (248, 244, 230))
        pen.line([(c - s * 0.45, c - s * 0.3), (c, c + s * 0.05), (c + s * 0.45, c - s * 0.3)])
        hold = (c - s * 0.3, c + s * 0.15)
    elif name == "money":
        for k in range(3):
            o = k * s * 0.08
            pen.shape([(c - s * 0.45 + o, c - s * 0.22 - o), (c + s * 0.45 + o, c - s * 0.22 - o),
                       (c + s * 0.45 + o, c + s * 0.22 - o), (c - s * 0.45 + o, c + s * 0.22 - o)],
                      (176, 210, 160))
        hold = (c - s * 0.3, c)
    elif name == "basket":
        pen.shape(doodle._ellipse_pts(c, c - s * 0.1, s * 0.7, s * 0.55, 0, 180, 16), (196, 160, 98))
        pen.ell(c, c - s * 0.1, s * 0.7, s * 0.14, (176, 140, 82))
        pen.line(doodle._ellipse_pts(c, c - s * 0.15, s * 0.6, s * 0.75, 180, 360, 14),
                 fill=(150, 116, 70))
        hold = (c, c - s * 0.85)
    elif name == "stick":
        pen.line([(c, c - s * 0.4), (c, c + s * 1.9)], width=int(s * 0.12), fill=(132, 94, 64))
    elif name == "hoe":                                  # cuốc: cán dài, lưỡi sắt ở đầu
        pen.line([(c, c - s * 0.3), (c, c + s * 2.0)], width=int(s * 0.13), fill=(150, 112, 74))
        pen.shape([(c + s * 0.06, c + s * 1.85), (c - s * 0.6, c + s * 1.75), (c - s * 0.7, c + s * 2.05),
                   (c + s * 0.06, c + s * 2.1)], (150, 156, 164))
    elif name == "broom":                                # chổi rơm
        pen.line([(c, c - s * 0.3), (c, c + s * 1.5)], width=int(s * 0.1), fill=(150, 112, 74))
        pen.shape([(c - s * 0.12, c + s * 1.45), (c + s * 0.12, c + s * 1.45), (c + s * 0.5, c + s * 2.1),
                   (c - s * 0.5, c + s * 2.1)], (214, 180, 100))
        for k in range(-2, 3):
            pen.line([(c + k * s * 0.05, c + s * 1.55), (c + k * s * 0.16, c + s * 2.05)],
                     width=max(1, int(s * 0.03)), fill=(170, 136, 70))
    elif name == "axe":                                  # rìu
        pen.line([(c, c - s * 0.2), (c, c + s * 1.4)], width=int(s * 0.12), fill=(150, 112, 74))
        pen.shape([(c + s * 0.05, c + s * 1.1), (c - s * 0.5, c + s * 1.0), (c - s * 0.55, c + s * 1.55),
                   (c + s * 0.05, c + s * 1.4)], (160, 166, 176))
    elif name == "sickle":                               # liềm
        pen.line([(c, c - s * 0.2), (c, c + s * 0.5)], width=int(s * 0.12), fill=(150, 112, 74))
        pen.line(doodle._ellipse_pts(c + s * 0.35, c + s * 0.55, s * 0.4, s * 0.45, 180, 360, 12),
                 width=int(s * 0.1), fill=(170, 176, 186))
    elif name == "fan":                                  # quạt nan
        pen.line([(c, c - s * 0.2), (c, c + s * 0.5)], width=int(s * 0.1), fill=(150, 112, 74))
        pen.shape(doodle._ellipse_pts(c, c + s * 0.95, s * 0.6, s * 0.55, 0, 360, 24), (222, 196, 140))
        for k in range(-3, 4):
            pen.line([(c, c + s * 0.45), (c + k * s * 0.17, c + s * 1.4)], width=max(1, int(s * 0.03)),
                     fill=(176, 146, 92))
    elif name == "pipe":                                 # điếu cày: ống tre dài, nõ điếu
        pen.shape([(c - s * 0.1, c - s * 1.5), (c + s * 0.1, c - s * 1.5), (c + s * 0.1, c + s * 0.6),
                   (c - s * 0.1, c + s * 0.6)], (190, 170, 110))
        pen.line([(c + s * 0.16, c + s * 0.2), (c + s * 0.45, c - s * 0.1)], width=int(s * 0.08),
                 fill=(150, 112, 74))
        pen.ell(c + s * 0.47, c - s * 0.12, s * 0.09, s * 0.06, (90, 80, 76))
        hold = (c, c - s * 0.1)
    elif name == "pot":                                  # nồi đất
        pen.shape(doodle._ellipse_pts(c, c, s * 0.6, s * 0.5, 0, 180, 16), (130, 96, 74))
        pen.ell(c, c, s * 0.6, s * 0.14, (110, 80, 62))
        hold = (c, c - s * 0.05)
    elif name == "basin":                                # chậu tắm: chậu nhôm, nước xanh, bọt xà phòng
        pen.shape([(c - s * 1.0, c), (c + s * 1.0, c), (c + s * 0.85, c + s * 0.28),
                   (c - s * 0.85, c + s * 0.28)], (176, 186, 196))       # chậu nông: chó đứng trong vẫn thấy rõ
        pen.ell(c, c, s * 1.0, s * 0.1, (196, 206, 214))
        for k in range(7):
            bx = c + (k - 3) * s * 0.26
            pen.ell(bx, c - s * 0.05 - (k % 2) * s * 0.05, s * 0.08, s * 0.07, (250, 252, 255))
        hold = (c, c)
    elif name == "pole":                                 # vẽ riêng ở Rig._pole
        return None
    elif name == "book":
        pen.shape([(c - s * 0.35, c - s * 0.45), (c + s * 0.35, c - s * 0.45), (c + s * 0.35, c + s * 0.45),
                   (c - s * 0.35, c + s * 0.45)], (150, 70, 60))
        pen.line([(c - s * 0.25, c - s * 0.45), (c - s * 0.25, c + s * 0.45)], fill=(230, 220, 200))
        hold = (c - s * 0.2, c + s * 0.2)
    elif name == "flower":
        pen.line([(c, c + s * 0.8), (c, c - s * 0.2)], fill=(90, 140, 70))
        for k in range(5):
            a = k * 72
            pen.ell(c + s * 0.22 * math.cos(math.radians(a)), c - s * 0.4 + s * 0.22 * math.sin(math.radians(a)),
                    s * 0.16, s * 0.16, (236, 140, 160))
        pen.ell(c, c - s * 0.4, s * 0.12, s * 0.12, (246, 210, 100))
        hold = (c, c + s * 0.5)
    elif name == "bag":
        pen.ell(c, c + s * 0.3, s * 0.55, s * 0.45, (160, 120, 80))
        pen.line([(c - s * 0.3, c + s * 0.0), (c, c - s * 0.6), (c + s * 0.3, c + s * 0.0)],
                 width=int(s * 0.1), fill=(120, 90, 60))
        hold = (c, c - s * 0.55)
    elif name == "bottle":
        pen.shape([(c - s * 0.22, c - s * 0.2), (c + s * 0.22, c - s * 0.2), (c + s * 0.22, c + s * 0.6),
                   (c - s * 0.22, c + s * 0.6)], (150, 190, 180))
        pen.shape([(c - s * 0.08, c - s * 0.55), (c + s * 0.08, c - s * 0.55), (c + s * 0.08, c - s * 0.2),
                   (c - s * 0.08, c - s * 0.2)], (150, 190, 180))
        hold = (c, c + s * 0.2)
    elif name == "knife":
        pen.shape([(c, c - s * 0.1), (c + s * 0.8, c - s * 0.2), (c + s * 0.8, c + s * 0.05), (c, c + s * 0.05)],
                  (210, 214, 220))
        pen.shape([(c - s * 0.4, c - s * 0.08), (c, c - s * 0.08), (c, c + s * 0.06), (c - s * 0.4, c + s * 0.06)],
                  (120, 84, 56))
        hold = (c - s * 0.2, c)
    elif name == "lamp":
        pen.shape([(c - s * 0.25, c + s * 0.1), (c + s * 0.25, c + s * 0.1), (c + s * 0.18, c + s * 0.5),
                   (c - s * 0.18, c + s * 0.5)], (200, 200, 190))
        pen.ell(c, c - s * 0.15, s * 0.18, s * 0.3, (236, 240, 240))
        pen.ell(c, c - s * 0.12, s * 0.06, s * 0.1, (255, 190, 80), outline=False)
        hold = (c, c + s * 0.3)
    else:
        p = doodle_parts.get(name)
        if not p or p.get("kind") != "prop":
            return None
        doodle_parts.draw_shapes(pen, p["shapes"], lambda x, y: (c + x * s, c + y * s), s)
        hx, hy = p.get("hold", (0.0, 0.0))
        hold = (c + hx * s, c + hy * s)
    img = img.resize((W // doodle.SS, H // doodle.SS), Image.LANCZOS)
    return img, (hold[0] / doodle.SS, hold[1] / doodle.SS)


def marks(canvas, act, t, head, T, face):
    """Dấu hiệu cảm xúc quanh đầu: nước mắt rơi, giọt mồ hôi, vạch sốc, dấu
    nổi gân, zzz, dấu suy nghĩ. head = (x, y mắt, bán kính đầu) trên canvas."""
    import cv2
    hx, hy, r = head
    lw = max(2, int(T * 0.012))
    if act == "cry":
        for k, sx in enumerate((-1, 1)):
            for j in range(2):
                u = ((t * 0.9 + j * 0.5 + k * 0.25) % 1.0)
                x = int(hx + sx * r * 0.42 + sx * u * r * 0.25)
                y = int(hy + r * 0.25 + u * r * 1.3)
                rr = max(2, int(r * 0.07 * (1 - u * 0.4)))
                cv2.circle(canvas, (x, y), rr, (150, 204, 240), -1, cv2.LINE_AA)
                cv2.circle(canvas, (x, y), rr, (60, 90, 120), max(1, lw // 2), cv2.LINE_AA)
    if act in ("hands_up", "tremble"):          # giọt mồ hôi chỉ khi hoảng sợ
        x, y = int(hx + r * 0.95), int(hy - r * 0.5 + 0.02 * T * math.sin(t * 3))
        pts = np.array([[x, y - int(r * 0.22)], [x - int(r * 0.1), y],
                        [x + int(r * 0.1), y]], np.int32)
        cv2.circle(canvas, (x, y + int(r * 0.03)), int(r * 0.1), (170, 214, 244), -1, cv2.LINE_AA)
        cv2.fillPoly(canvas, [pts], (170, 214, 244), cv2.LINE_AA)
        cv2.circle(canvas, (x, y + int(r * 0.03)), int(r * 0.1), (60, 90, 120), lw // 2 + 1, cv2.LINE_AA)
    if act == "hands_up" and t < 1.8:
        for k in (-1, 0, 1):
            ang = math.radians(-90 + k * 30)
            x0, y0 = hx + math.cos(ang) * r * 1.25, hy - r * 0.2 + math.sin(ang) * r * 1.25
            x1, y1 = hx + math.cos(ang) * r * 1.55, hy - r * 0.2 + math.sin(ang) * r * 1.55
            cv2.line(canvas, (int(x0), int(y0)), (int(x1), int(y1)), (40, 34, 38), lw, cv2.LINE_AA)
    if act == "angry" and (t % 1.2) < 0.9:
        x, y, s = int(hx - r * 0.75), int(hy - r * 0.75), int(r * 0.16)
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            cv2.ellipse(canvas, (x + dx * s, y + dy * s), (s, s), 0,
                        {(-1, -1): 0, (1, -1): 90, (-1, 1): 270, (1, 1): 180}[(dx, dy)],
                        {(-1, -1): 0, (1, -1): 90, (-1, 1): 270, (1, 1): 180}[(dx, dy)] + 90,
                        (210, 60, 60), lw + 1, cv2.LINE_AA)
    if act == "sleep":
        for j in range(3):
            u = (t * 0.5 + j / 3) % 1.0
            s = int(r * (0.12 + 0.1 * u))
            x = int(hx + r * (0.6 + 0.5 * u))
            y = int(hy - r * (0.8 + 0.9 * u))
            pts = np.array([[x - s, y - s], [x + s, y - s], [x - s, y + s], [x + s, y + s]], np.int32)
            cv2.polylines(canvas, [pts], False, (60, 60, 80), lw, cv2.LINE_AA)
    if act == "think":
        for j in range(3):
            if (t % 2.4) > j * 0.5:
                x = int(hx + (1 if face > 0 else -1) * r * (0.6 + 0.3 * j))
                y = int(hy - r * (1.2 + 0.25 * j))
                rr = int(r * (0.06 + 0.03 * j))
                cv2.circle(canvas, (x, y), rr, (250, 250, 250), -1, cv2.LINE_AA)
                cv2.circle(canvas, (x, y), rr, (40, 34, 38), max(1, lw // 2), cv2.LINE_AA)


# ------------------------------------------------------------ người

# Kiểu nhân vật: tỉ lệ đầu (bán kính / chiều cao), bề ngang thân, chân, tay, độ dày
# tay chân, kiểu mắt, độ dày nét viền, độ run nét
CHAR_STYLES = {
    "capsule": {"label": "Con nhộng tay chân ngắn (vẽ tay Hàn)", "head": 0.25, "body": 1.0,
                "leg": 0.15, "arm": 1.0, "limb": 1.0, "eyes": "dot", "outline": 1.0, "wobble": 1.0},
    "chibi": {"label": "Chibi đầu thật to, mắt tròn", "head": 0.31, "body": 1.05, "leg": 0.11,
              "arm": 0.9, "limb": 1.15, "eyes": "round", "outline": 1.15, "wobble": 1.0},
    "tall": {"label": "Người tỉ lệ cao (đầu nhỏ, chân tay dài)", "head": 0.16, "body": 0.82,
             "leg": 0.32, "arm": 1.75, "limb": 0.75, "eyes": "dot", "outline": 0.8, "wobble": 0.6},
    "anime": {"label": "Anime mắt to, nét mảnh", "head": 0.2, "body": 0.8, "leg": 0.27, "arm": 1.55,
              "limb": 0.68, "eyes": "big", "outline": 0.65, "wobble": 0.25},
    "simple": {"label": "Tối giản mắt chấm (kiểu meme)", "head": 0.24, "body": 0.95, "leg": 0.16,
               "arm": 1.05, "limb": 0.95, "eyes": "line", "outline": 1.1, "wobble": 1.2},
}
_RANGES = {"head": (0.12, 0.36), "body": (0.6, 1.3), "leg": (0.06, 0.38), "arm": (0.7, 2.0),
           "limb": (0.5, 1.4), "outline": (0.4, 1.6), "wobble": (0.0, 1.6), "belly": (0.0, 1.0)}
EYES = ("dot", "round", "big", "line")


def clean_style(d: dict | None) -> dict:
    """Thông số kiểu nhân vật hợp lệ (thiếu thì lấy kiểu con nhộng)."""
    out = {k: v for k, v in CHAR_STYLES["capsule"].items() if k != "label"}
    out["belly"] = 0.0
    for k, (lo, hi) in _RANGES.items():
        try:
            out[k] = max(lo, min(hi, float((d or {}).get(k, out[k]))))
        except (TypeError, ValueError):
            pass
    if (d or {}).get("eyes") in EYES:
        out["eyes"] = d["eyes"]
    return out


def style_of(st: dict) -> dict:
    """Kiểu nhân vật của truyện: kiểu chọn sẵn, hoặc rút từ ảnh nhân vật mẫu."""
    name = st.get("char_style") or "capsule"
    if name == "sample":
        return clean_style(((st.get("char_sample") or {}).get("style")))
    return clean_style(CHAR_STYLES.get(name, CHAR_STYLES["capsule"]))


class Rig:
    """Nhân vật người có tay chân. T = chiều cao (đơn vị thế giới, px ở góc rộng)."""

    def __init__(self, kit: dict, T: float, seed: int = 0, sty: dict | None = None):
        self.sty = clean_style(sty or kit.get("_sty"))
        sty = self.sty
        self.kit = doodle.clean_kit(kit)
        self.kit["_sty"] = sty
        self.seed = seed
        child = self.kit["age"] == "child"
        self.T = T * (0.8 if child else 1.0)
        T = self.T
        self.R = T * sty["head"] * (1.16 if child else 1.0)
        R = self.R
        self.Rb = T * 0.25 * sty["body"] * (1.06 if child else 1.0)    # "bán kính" bề ngang thân
        self.leg = T * sty["leg"] * (0.87 if child else 1.0)
        self.hip_h = self.leg * 0.82                      # hông cao hơn đất
        self.head_y = -T + R                              # tâm đầu (đất = 0)
        self.body_top = self.head_y + 0.78 * R
        self.body_bot = -self.hip_h + R * 0.12
        female = self.kit["sex"] == "female"
        Rb = self.Rb
        wt = Rb * (0.66 if female else 0.74)
        wb = Rb * (0.98 if self.kit["top"] == "dress" else (0.84 if female else 0.86))
        if child:
            wt, wb = wt * 0.92, wb * 0.92
        wb *= 1 + 0.3 * sty.get("belly", 0.0)            # bụng tròn: hông rộng ra
        self.wt, self.wb = wt, wb
        self.shoulder = (wt * 0.86, self.body_top + 0.36 * min(R, Rb))
        self.hipx = wb * 0.42
        a, lm = sty["arm"], sty["limb"]
        self.arm = (T * 0.12 * a, T * 0.11 * a, T * 0.062 * lm, T * 0.036 * max(0.8, lm))
        self.legd = (self.leg * 0.52, self.leg * 0.5, T * 0.075 * lm)
        top_c = doodle.CLOTH[self.kit["top_color"]]
        self.sleeve = top_c
        self.skin = doodle.SKINS[self.kit["skin"]]
        long_bottom = self.kit["top"] in ("dress", "robe", "ao_dai")
        self.pants = self.skin if long_bottom and self.kit["top"] == "dress" else \
            doodle.CLOTH[self.kit["bottom_color"]]
        self.short_sleeve = self.kit["top"] == "tshirt"          # áo cộc tay: cẳng tay màu da
        self.shorts = self.kit.get("bottom") == "shorts"        # quần soóc: cẳng chân màu da
        barefoot = self.kit["top"] in ("ao_nau", "ao_ba_ba") or self.kit["age"] == "child" or self.shorts
        self.foot = self.skin if barefoot else (70, 58, 54)
        self._cache: dict = {}

    # --- ảnh đầu, thân (cache)
    def sprites(self, expr, mouth, blink, look, k):
        """k = px ảnh trên 1 đơn vị thế giới. Trả về {hairback, body, head} =
        (ảnh đã nhân alpha, ma trận ảnh -> toạ độ cục bộ)."""
        kq = round(k * 8) / 8
        key = (expr, mouth, blink, round(look, 1), kq)
        if key in self._cache:
            return self._cache[key]
        if len(self._cache) > 120:
            self._cache.clear()
        S = doodle.SS * kq
        R = self.R * S
        kit = self.kit
        face_dir = 1 if look > 0.15 else (-1 if look < -0.15 else 0)
        # đầu + tóc trước + mũ (gốc = cổ)
        W, H = int(R * 3.6), int(R * 4.0)
        cx, hy = W / 2, R * 2.1
        head = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        hb = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pen = doodle._Pen(head, self.T * S, self.seed)
        pb = doodle._Pen(hb, self.T * S, self.seed)
        for pp in (pen, pb):
            pp.lw = max(1, int(pp.lw * self.sty["outline"]))
            pp.amp *= self.sty["wobble"]
        doodle._draw_head_parts(pb, kit, cx, hy, R, "back")
        doodle._draw_hair_back(pb, kit, cx, hy, R, face_dir or 1)
        pen.ell(cx, hy, R, R * 0.97, self.skin)
        doodle._draw_face(pen, kit, cx, hy, R, look, expr, mouth, blink)
        doodle._draw_hair_front(pen, kit, cx, hy, R, face_dir or 1)
        doodle._draw_hat(pen, kit, cx, hy, R)
        doodle._draw_head_parts(pen, kit, cx, hy, R, "front")
        neck = (cx, hy + 0.78 * R)
        sz = (int(W / doodle.SS), int(H / doodle.SS))
        head_m = _aff(_tr(0, self.body_top), _aff(_sc(1 / kq), _tr(-neck[0] / doodle.SS,
                                                                      -neck[1] / doodle.SS)))
        # thân (gốc = giữa hông)
        Rb = self.Rb * S
        bw = int(Rb * 2.6)
        top, bot = Rb * 0.15, Rb * 0.15 + (self.body_bot - self.body_top) * S
        body = Image.new("RGBA", (bw, int(bot + Rb * 0.2)), (0, 0, 0, 0))
        pbody = doodle._Pen(body, self.T * S, self.seed)
        pbody.lw = max(1, int(pbody.lw * self.sty["outline"]))
        pbody.amp *= self.sty["wobble"]
        doodle._draw_body(body, pbody, kit, bw / 2, top, bot, Rb, self.seed)
        body_m = _aff(_tr(0, self.body_top), _aff(_sc(1 / kq), _tr(-bw / 2 / doodle.SS,
                                                                      -top / doodle.SS)))
        hb_s = hb.resize(sz, Image.LANCZOS)
        out = {
            "hairback": (_premul(hb_s), head_m) if hb_s.getbbox() else None,
            "head": (_premul(head.resize(sz, Image.LANCZOS)), head_m),
            "body": (_premul(body.resize((max(1, bw // doodle.SS), max(1, body.height // doodle.SS)),
                                         Image.LANCZOS)), body_m),
        }
        self._cache[key] = out
        return out

    # --- vẽ một tư thế
    def draw(self, canvas, pose: dict, cam: np.ndarray, zoom: float, night=None):
        """pose: x, y (chân), dir (+1 nhìn phải / -1 trái), look, lean, head, bob,
        sy, rot, sit (0..1), arms [(vai, khuỷu)]x2, legs [(hông, gối)]x2, expr,
        mouth, blink, prop (tên, tay 0|1)."""
        import cv2
        d = 1 if pose.get("dir", 1) >= 0 else -1
        T = self.T
        sit = pose.get("sit", 0.0)
        # đất -> thế giới: xoay cả người (nằm), nhún
        G = _aff(_tr(pose["x"], pose["y"] - pose.get("bob", 0.0) * T), _rot(pose.get("rot", 0.0) * d))
        G = _aff(cam, G)
        # ngồi: hông hạ xuống ghế thấp, đùi đưa ngang
        seat = pose.get("seat_h")              # ngồi trên đồ đạc của cảnh (chõng, giường...)
        drop = sit * (self.hip_h - (seat if seat is not None else T * 0.07))
        hip = (0.0, -self.hip_h + drop)
        B = _aff(G, _aff(_tr(hip[0], hip[1]), _aff(_rot(pose.get("lean", 0.0) * d),
                                                  _sc(1.0, pose.get("sy", 1.0)))))
        Bl = _aff(B, _tr(0, self.hip_h))       # thân: toạ độ gốc đất -> dời về hông
        Hm = _aff(Bl, _aff(_tr(0, self.body_top + 0.0), _aff(_rot(pose.get("head", 0.0) * d),
                                                               _tr(0, -self.body_top))))
        lw = max(1, int(T * zoom * 0.016))
        if sit > 0.05 and seat is None:                      # ghế đẩu tre
            col = (176, 150, 96)
            p0 = _pt(G, -self.wb * 1.0, -T * 0.07)
            p1 = _pt(G, self.wb * 1.0, 0)
            x0, y0, x1, y1 = int(min(p0[0], p1[0])), int(min(p0[1], p1[1])), int(max(p0[0], p1[0])), int(max(p0[1], p1[1]))
            if sit > 0.5:
                cv2.rectangle(canvas, (x0, y0), (x1, y0 + max(2, (y1 - y0) // 4)), col, -1, cv2.LINE_AA)
                cv2.rectangle(canvas, (x0, y0), (x1, y0 + max(2, (y1 - y0) // 4)), OUT, lw, cv2.LINE_AA)
                for xx in (x0 + (x1 - x0) // 6, x1 - (x1 - x0) // 6):
                    cv2.line(canvas, (xx, y0), (xx, y1), OUT, lw * 3, cv2.LINE_AA)
                    cv2.line(canvas, (xx, y0), (xx, y1), col, lw, cv2.LINE_AA)
        spr = self.sprites(pose.get("expr", "neutral"), bool(pose.get("mouth")),
                           bool(pose.get("blink")), pose.get("look", 0.3 * d), zoom)
        legs = pose.get("legs") or [(0, 0), (0, 0)]
        if sit > 0.05:
            legs = [(a + 85 * sit, g - 85 * sit) for a, g in legs]
        arms = pose.get("arms") or [(8, 0), (8, 0)]
        Lm = _aff(G, _tr(0, drop))           # chân: không nghiêng theo thân, đứng trên đất
        prop = pose.get("prop")
        tm = pose.get("to_mouth")
        if tm and tm[1] > 0.01:                 # đưa chén / điếu / tay lên đúng miệng
            arms = list(arms)
            hi = tm[0] if tm[0] in (0, 1) else 0
            held = prop[0] if prop and (prop[1] if prop[1] in (0, 1) else 0) == hi else None
            a1, e1 = self._mouth_arm(hi, d, pose, held)
            a0, e0 = arms[hi]
            u = min(1.0, tm[1])
            arms[hi] = (a0 + (a1 - a0) * u, e0 + (e1 - e0) * u)
        tool_ang = pose.get("tool_ang")
        tool_behind = bool(prop and prop[0] in TOOLS and tool_ang is not None and tool_ang > 120)

        def hand_of(i):
            a, e = arms[i]
            sx = (1 if i == 0 else -1) * d * self.shoulder[0]
            t1, t2 = math.radians(a), math.radians(a + e)
            x1 = sx + d * self.arm[0] * math.sin(t1)
            y1 = self.shoulder[1] + self.arm[0] * math.cos(t1)
            x2, y2 = x1 + d * self.arm[1] * math.sin(t2), y1 + self.arm[1] * math.cos(t2)
            return _pt(Bl, x1, y1), _pt(Bl, x2, y2)

        def draw_tool():
            hi = prop[1] if prop[1] in (0, 1) else 0
            elbow, hand = hand_of(hi)
            self._prop(canvas, prop[0], hand, zoom, d, elbow, tool_ang)

        def draw_legs():
            for i, (a, g) in enumerate(legs):
                sx = (1 if i == 0 else -1) * d * self.hipx
                self._limb(canvas, Lm, (sx, -self.hip_h + 0.0), a, g, d, self.legd[0], self.legd[1],
                           self.legd[2], self.pants, zoom, foot=True, cover=0.85 if self.shorts else 1.0)
        if sit <= 0.5:
            draw_legs()                      # đứng: chân sau thân
        if tool_behind:                        # cuốc / rìu vác sau vai: sau lưng người
            draw_tool()
        if spr["hairback"]:
            paste(canvas, spr["hairback"][0], _aff(Hm, spr["hairback"][1]), night)
        paste(canvas, spr["body"][0], _aff(Bl, spr["body"][1]), night)
        if sit > 0.5:
            draw_legs()                      # ngồi: đùi nằm trên lòng, thấy rõ
        # tay (trước thân, kể cả che mặt khi khóc); giơ dụng cụ quá vai thì tay ra sau đầu
        hands, elbows = [], []

        def draw_arms():
            for i, (a, e) in enumerate(arms):
                sx = (1 if i == 0 else -1) * d * self.shoulder[0]
                hands.append(self._limb(canvas, Bl, (sx, self.shoulder[1]), a, e, d,
                                        self.arm[0], self.arm[1], self.arm[2], self.sleeve, zoom,
                                        hand=True, cover=0.55 if self.short_sleeve else 1.0))
                elbows.append(self._last_elbow)
        if tool_behind:
            draw_arms()
        paste(canvas, spr["head"][0], _aff(Hm, spr["head"][1]), night)
        if not tool_behind:
            draw_arms()
        if prop and not tool_behind:
            name, hi = prop
            hi = hi if hi in (0, 1) else 0
            if name == "pole":
                self._pole(canvas, Bl, zoom, d)
            elif name in TOOLS and tool_ang is not None:
                draw_tool()
            else:
                self._prop(canvas, name, hands[hi], zoom, d, elbows[hi])
        head_c = _pt(Hm, 0, self.head_y)
        return {"head": head_c, "r": self.R * zoom, "hands": hands}

    # điểm cầm -> miệng: (ra trước theo R, xuống dưới miệng theo T) cho từng đồ
    MOUTH_HOLD = {"cup": (0.2, 0.026), "pipe": (0.06, 0.28), "bowl": (0.25, 0.06), None: (0.16, 0.03)}

    def _mouth_arm(self, i, d, pose, held):
        """Góc (vai, khuỷu) để tay đưa đồ đang cầm chạm đúng miệng (IK hai đoạn)."""
        R = self.R
        H = _aff(_tr(0, self.body_top), _aff(_rot(pose.get("head", 0.0) * d), _tr(0, -self.body_top)))
        mx, my = _pt(H, pose.get("look", 0.3 * d) * 0.18 * R, self.head_y + 0.53 * R)
        fwd, down = self.MOUTH_HOLD.get(held, self.MOUTH_HOLD[None])
        tx, ty = mx + d * fwd * R, my + down * self.T
        sx, sy = (1 if i == 0 else -1) * d * self.shoulder[0], self.shoulder[1]
        l1, l2 = self.arm[0], self.arm[1]
        X, Y = (tx - sx) * d, ty - sy              # quy về hướng nhìn sang phải
        D = min(max(math.hypot(X, Y), abs(l1 - l2) + 1e-3), l1 + l2 - 1e-3)
        th = math.atan2(X, Y)
        al = math.acos(max(-1.0, min(1.0, (l1 * l1 + D * D - l2 * l2) / (2 * l1 * D))))
        t1 = th - al                               # khuỷu chĩa xuống
        ex, ey = l1 * math.sin(t1), l1 * math.cos(t1)
        t2 = math.atan2(X - ex, Y - ey)
        return math.degrees(t1), math.degrees(t2 - t1)

    def _limb(self, canvas, M, root, a, e, d, l1, l2, w, color, zoom, hand=False, foot=False,
              cover=1.0):
        """cover < 1: vải chỉ phủ phần trên (áo cộc tay, quần soóc), phần dưới màu da."""
        import cv2
        t1 = math.radians(a)
        t2 = math.radians(a + e)
        x0, y0 = root
        x1, y1 = x0 + d * l1 * math.sin(t1), y0 + l1 * math.cos(t1)
        x2, y2 = x1 + d * l2 * math.sin(t2), y1 + l2 * math.cos(t2)
        pts = [_pt(M, x0, y0), _pt(M, x1, y1), _pt(M, x2, y2)]
        self._last_elbow = pts[1]
        P = np.array([[int(px * 4), int(py * 4)] for px, py in pts], np.int32)
        wz = max(2, int(w * zoom))
        lw = max(1, int(self.T * zoom * 0.016 * self.sty["outline"]))
        cv2.polylines(canvas, [P], False, OUT, wz + 2 * lw, cv2.LINE_AA, shift=2)
        for p in P:
            cv2.circle(canvas, tuple(int(v) for v in p), (wz + 2 * lw) * 2, OUT, -1, cv2.LINE_AA, shift=2)
        if cover >= 1.0:
            cv2.polylines(canvas, [P], False, color, wz, cv2.LINE_AA, shift=2)
            for p in P[1:]:
                cv2.circle(canvas, tuple(int(v) for v in p), wz * 2, color, -1, cv2.LINE_AA, shift=2)
        else:
            cv2.polylines(canvas, [P], False, self.skin, wz, cv2.LINE_AA, shift=2)
            for p in P[1:]:
                cv2.circle(canvas, tuple(int(v) for v in p), wz * 2, self.skin, -1, cv2.LINE_AA, shift=2)
            mid = P[0] + (P[1] - P[0]) * cover
            Q = np.array([P[0], mid.astype(np.int32)], np.int32)
            cv2.polylines(canvas, [Q], False, color, wz + max(2, lw), cv2.LINE_AA, shift=2)
            cv2.circle(canvas, tuple(int(v) for v in P[0]), (wz + max(2, lw)) * 2, color, -1, cv2.LINE_AA, shift=2)
            m2 = tuple(int(v) for v in Q[1])
            nx, ny = -(P[1][1] - P[0][1]), (P[1][0] - P[0][0])       # mép tay áo / ống quần
            nn = max(1.0, math.hypot(nx, ny))
            hw = (wz + max(2, lw)) * 2.2
            a1 = (int(m2[0] + nx / nn * hw), int(m2[1] + ny / nn * hw))
            a2 = (int(m2[0] - nx / nn * hw), int(m2[1] - ny / nn * hw))
            cv2.line(canvas, a1, a2, OUT, max(1, lw), cv2.LINE_AA, shift=2)
        end = pts[-1]
        if hand:
            r = max(2, int(self.arm[3] * zoom))
            c = (int(end[0] * 4), int(end[1] * 4))
            cv2.circle(canvas, c, (r + lw) * 4, OUT, -1, cv2.LINE_AA, shift=2)
            cv2.circle(canvas, c, r * 4, self.skin, -1, cv2.LINE_AA, shift=2)
        if foot:
            # bàn chân nhìn về phía trước
            v = _pt(M, x2 + d * self.T * 0.03, y2)
            fx, fy = v
            rx, ry = max(2, int(self.T * 0.05 * zoom)), max(2, int(self.T * 0.028 * zoom))
            ang = math.degrees(math.atan2(M[1, 0], M[0, 0]))
            cv2.ellipse(canvas, (int(fx * 4), int(fy * 4)), ((rx + lw) * 4, (ry + lw) * 4), ang, 0, 360,
                        OUT, -1, cv2.LINE_AA, shift=2)
            cv2.ellipse(canvas, (int(fx * 4), int(fy * 4)), (rx * 4, ry * 4), ang, 0, 360,
                        self.foot, -1, cv2.LINE_AA, shift=2)
        return end

    def _pole(self, canvas, Bl, zoom, d):
        """Đòn gánh trên vai, hai thúng treo hai đầu."""
        import cv2
        T = self.T
        lw = max(1, int(T * zoom * 0.016))
        y = self.shoulder[1] + 0.04 * self.R
        a, b = _pt(Bl, -T * 0.42, y), _pt(Bl, T * 0.42, y)
        wood = (150, 112, 74)
        P = lambda p: (int(p[0] * 4), int(p[1] * 4))  # noqa: E731
        th = max(2, int(T * zoom * 0.03))
        cv2.line(canvas, P(a), P(b), OUT, (th + 2 * lw) * 4 // 4, cv2.LINE_AA, shift=2)
        cv2.line(canvas, P(a), P(b), wood, th, cv2.LINE_AA, shift=2)
        for end in (a, b):
            top = (end[0], end[1])
            bx, by = end[0], end[1] + T * zoom * 0.36
            cv2.line(canvas, P(top), P((bx - T * zoom * 0.1, by)), OUT, lw, cv2.LINE_AA, shift=2)
            cv2.line(canvas, P(top), P((bx + T * zoom * 0.1, by)), OUT, lw, cv2.LINE_AA, shift=2)
            pts = np.array([P((bx - T * zoom * 0.14, by)), P((bx + T * zoom * 0.14, by)),
                            P((bx + T * zoom * 0.1, by + T * zoom * 0.14)),
                            P((bx - T * zoom * 0.1, by + T * zoom * 0.14))], np.int32)
            cv2.fillPoly(canvas, [pts], (196, 160, 98), cv2.LINE_AA, shift=2)
            cv2.polylines(canvas, [pts], True, OUT, lw, cv2.LINE_AA, shift=2)

    def _prop(self, canvas, name, hand, zoom, d, elbow=None, tool_ang=None):
        key = ("prop", name, round(zoom * 8) / 8, d)
        if key not in self._cache:
            k = 0.2 if name in TOOLS or name == "pipe" else 0.11      # dụng cụ dài hơn bàn tay nhiều
            got = prop_image(name, self.T * k * zoom)
            if not got:
                self._cache[key] = None
            else:
                img, hold = got
                if d < 0:
                    img = img.transpose(Image.FLIP_LEFT_RIGHT)
                    hold = (img.width - hold[0], hold[1])
                self._cache[key] = (_premul(img), hold, d)
        got = self._cache[key]
        if not got:
            return
        arr, hold, _d = got
        if name in TOOLS and (tool_ang is not None or elbow is not None):
            if tool_ang is not None:
                # góc dụng cụ theo động tác (0 = chĩa xuống, + = về phía trước), lưỡi luôn
                # cùng một phía nên không lật ngang lật dọc
                ang = -tool_ang * d
            else:                              # cán nối dài cẳng tay
                vx, vy = hand[0] - elbow[0], hand[1] - elbow[1]
                ang = math.degrees(math.atan2(-vx, vy))
            m = _aff(_tr(hand[0], hand[1]), _aff(_rot(ang), _tr(-hold[0], -hold[1])))
            paste(canvas, arr, m)
            return
        paste(canvas, arr, _tr(hand[0] - hold[0], hand[1] - hold[1]))


class AnimalRig:
    """Chó, mèo, con vật vẽ thêm: một khối, đi bằng nhún / nghiêng."""

    def __init__(self, kit, T, seed=0):
        self.kit = doodle.clean_kit(kit)
        self.T = T
        self.seed = seed
        self._cache: dict = {}

    def draw(self, canvas, pose, cam, zoom, night=None):
        d = 1 if pose.get("dir", 1) >= 0 else -1
        expr = pose.get("expr", "neutral")
        tail = round(pose.get("tail", 0.0) / 7.0) * 7.0           # đuôi vẫy: 7 độ một nấc (cache)
        dip = round(pose.get("dip", 0.0), 2)
        key = (expr, bool(pose.get("mouth")), bool(pose.get("blink")), d, round(zoom * 8) / 8, tail, dip)
        if key not in self._cache:
            if len(self._cache) > 200:
                self._cache.clear()
            img, foot, eye = doodle.render(self.kit, expr, bool(pose.get("mouth")), bool(pose.get("blink")),
                                           0.6 * d, height=int(self.T * zoom), seed=self.seed, tail=tail,
                                           dip=dip)
            self._cache[key] = (_premul(img), foot, eye)
        arr, foot, eye = self._cache[key]
        pv = -d * pose.get("pivot", 0.0) * self.T          # điểm xoay (vd chân sau khi cúi ăn)
        G = _aff(cam, _aff(_tr(pose["x"], pose["y"] - pose.get("bob", 0.0) * self.T * 0.4),
                           _rot(pose.get("rot", 0.0) * d, pv, 0.0)))
        M = _aff(G, _aff(_sc(1 / zoom, pose.get("sy", 1.0) / zoom), _tr(-foot[0], -foot[1])))
        paste(canvas, arr, M, night)
        hx, hy = _pt(M, eye[0], eye[1])
        return {"head": (hx, hy), "r": eye[2] / zoom * zoom, "hands": []}
