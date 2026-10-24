# -*- coding: utf-8 -*-
"""Ảnh AI cho nhân vật webtoon (chị tự vẽ bằng Gemini / ChatGPT rồi tải lên).

Mỗi nhân vật có một bộ ảnh theo tư thế ("phone_ear", "down"...) và có thể thêm vài nét
mặt ("phone_ear__shocked"). Mỗi cảnh quay lấy ảnh đúng tư thế + nét mặt, đứng yên như một
khung truyện tranh; tool chỉ vẽ thêm miệng nhép theo giọng và mắt chớp lên ảnh.

- needed(st): những ảnh kịch bản cần (kèm câu lệnh vẽ tiếng Anh để dán vào công cụ vẽ).
- process(src, dst): tách nền trắng, cắt sát người, tự tìm hai mắt + miệng.
- Pic: ảnh đã xử lý + điểm mắt / miệng; draw(...) dán lên khung hình có nhép miệng, chớp mắt.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import webtoon_art as wa

PICS_DIR = "webtoon_pics"
INK = (28, 26, 30, 255)
MAX_H = 1600
SEP = "__"

# nét mặt gần "bình thường": dùng chung ảnh gốc của tư thế
CALM = {"neutral", "thinking", "tired", "relieved", "smirk", "sad"}

POSE_EN = {
    "down": "standing naturally, both arms relaxed down at the sides",
    "phone_ear": ("talking on a smartphone, holding the phone against his/her right ear with the right hand "
                  "(the hand is on the LEFT side of the image), fingers wrapped naturally around the phone, "
                  "the back of the phone visible"),
    "phone_look": "holding a smartphone in front of the chest with one hand and looking down at the screen",
    "hand_head": "one hand pressed against the forehead / hair in distress",
    "hands_head": "both hands holding the head in panic",
    "cross": "arms crossed over the chest",
    "point": "pointing forward at someone with one hand",
    "wave": "waving one hand raised next to the head",
    "hands_face": "covering the face with both hands, eyes still visible between the fingers",
    "hands_hips": "both hands on the hips",
    "shrug": "shrugging with both palms up",
    "fist": "one fist clenched and raised in front of the chest",
    "hold_out": "holding both hands out in front, offering something",
}
EXPR_EN = {
    "neutral": "calm neutral expression, mouth closed",
    "worried": "worried expression, eyebrows raised in the middle, mouth closed",
    "shocked": "shocked expression, eyes wide open, small pupils, mouth slightly open",
    "scared": "scared expression, eyes wide, pale, a drop of sweat, mouth slightly open",
    "sad": "sad expression, eyebrows tilted, mouth closed",
    "crying": "crying, tears running down the cheeks, mouth closed and trembling",
    "angry": "angry expression, eyebrows furrowed down, mouth closed tight",
    "happy": "happy gentle smile, mouth closed",
    "laughing": "laughing happily, eyes squinted",
    "smirk": "smirking with one corner of the mouth up",
    "tired": "tired expression, dark circles under the eyes, mouth closed",
    "thinking": "thinking expression, looking slightly up, mouth closed",
    "relieved": "relieved expression, soft smile, mouth closed",
    "desperate": "desperate expression, eyebrows raised, eyes teary, mouth slightly open",
}
STYLE_EN = ("Korean webtoon style like Korean YouTube story-animation channels (\"썰\" animation): "
            "clean uniform black outlines, flat cel-shaded colors, no gradients, no textures, "
            "simple realistic adult proportions, slightly large head, clean smooth anime-like face.")


def key_of(pose: str, expr: str = "") -> str:
    return pose if not expr or expr in CALM else f"{pose}{SEP}{expr}"


def split_key(key: str) -> tuple[str, str]:
    pose, _, expr = key.partition(SEP)
    return pose, expr or "neutral"


def describe(c: dict) -> str:
    """Mô tả ngoại hình nhân vật bằng tiếng Anh cho công cụ vẽ."""
    lk = wa.Look.from_dict(c.get("look"))
    fem = lk.sex == "female"
    age = {"child": "8-year-old", "teen": "16-year-old", "young": "25-year-old", "adult": "35-year-old",
           "middle": "50-year-old", "old": "70-year-old"}.get(lk.age, "35-year-old")
    who = {"child": "girl" if fem else "boy", "teen": "girl" if fem else "boy"}.get(
        lk.age, "woman" if fem else "man")
    hair = {"short_part": "short neat hair with a side-swept fringe", "short": "short hair",
            "buzz": "buzz cut", "bald": "bald head", "side_part": "short side-parted hair",
            "long": "long straight hair", "long_messy": "long messy hair", "bob": "bob haircut",
            "ponytail": "hair in a ponytail", "bun": "hair in a bun", "curly": "curly hair"}.get(lk.hair, "short hair")
    hc = lk.hair_color if isinstance(lk.hair_color, str) else "black"
    top = {"tshirt": "T-shirt", "shirt": "collared shirt", "jacket": "jacket", "hoodie": "hoodie",
           "suit": "suit with a tie", "blouse": "blouse", "dress": "dress", "sweater": "round-neck sweater"}.get(
        lk.top, "sweater")
    tc = lk.top_color if isinstance(lk.top_color, str) else ""
    extra = []
    if lk.glasses:
        extra.append("wearing glasses")
    if lk.beard:
        extra.append({"stubble": "light stubble", "mustache": "a mustache", "full": "a full beard"}.get(lk.beard, ""))
    skin = {"light": "light", "fair": "fair", "tan": "tanned", "dark": "dark"}.get(lk.skin, "fair")
    s = f"a {age} Korean {who}, {skin} skin, {hc} {hair}, {tc} {top}".replace("  ", " ")
    return s + (", " + ", ".join(x for x in extra if x) if extra else "")


def prompt(c: dict, key: str, first: bool) -> str:
    pose, expr = split_key(key)
    ref = ("" if first else "Use the attached image as the character reference: keep exactly the same face, "
           "hairstyle, clothes and colors. ")
    return (f"{ref}{STYLE_EN} Draw {describe(c)} ({c.get('name') or c.get('id')}), {POSE_EN.get(pose, POSE_EN['down'])}, "
            f"{EXPR_EN.get(expr, EXPR_EN['neutral'])}. Waist-up shot, character centered and facing the viewer, "
            "both eyes clearly visible, the whole head and hands inside the frame. "
            "Plain solid bright green (#00FF00) background like a green screen, nothing else in the image, "
            "no green on the character, no text, no frame. Vertical 3:4 image.")


def needed(st: dict) -> list[dict]:
    """Ảnh kịch bản cần, theo nhân vật: tư thế gốc (bắt buộc) + nét mặt mạnh (nên có)."""
    chars = {c["id"]: c for c in st.get("characters") or []}
    have = st.get("pics") or {}
    cnt: dict = {}
    for s in st.get("shots") or []:
        if s.get("type") in ("phone", "black"):
            continue
        for i, cid in enumerate([s.get("who")] + list(s.get("with") or [])):
            if cid not in chars:
                continue
            pose = s.get("pose", "down") if i == 0 else (s.get("with_pose") or "down")
            expr = s.get("expr", "neutral") if i == 0 else (s.get("with_expr") or "neutral")
            for k in {key_of(pose), key_of(pose, expr)}:
                cnt[(cid, k)] = cnt.get((cid, k), 0) + 1
    out = []
    for cid, c in chars.items():
        keys = sorted({k for (ci, k) in cnt if ci == cid}, key=lambda k: (SEP in k, -cnt[(cid, k)], k))
        keys = ["down"] + [k for k in keys if k != "down"]   # ảnh gốc vẽ trước, làm mẫu cho các ảnh sau
        for k in keys:
            pose, expr = split_key(k)
            out.append({"cid": cid, "key": k, "pose": pose, "expr": expr, "shots": cnt.get((cid, k), 0),
                        "required": SEP not in k, "have": k in (have.get(cid) or {}),
                        "prompt": prompt(c, k, k == "down")})
    return out


# ---------------------------------------------------------------- xử lý ảnh tải lên

def _remove_bg(rgb: np.ndarray) -> np.ndarray:
    """Alpha 0..255. Nền = màu giống mép ảnh, nối liền ra mép (nét đen chặn lại). Nền màu
    rực (phông xanh) thì bỏ cả những khoảng nền bị kẹt giữa tay và người, rồi khử viền xanh."""
    import cv2
    h, w = rgb.shape[:2]
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]).astype(np.int32)
    bg = np.median(border, axis=0)
    dist = np.abs(rgb.astype(np.int32) - bg[None, None]).sum(axis=2)
    chroma = float(bg.max() - bg.min()) > 90                 # nền xanh / hồng... (không phải trắng, xám)
    like = (dist < (110 if chroma else 60)).astype(np.uint8)
    n, lab = cv2.connectedComponents(like, connectivity=4)
    if chroma:
        bgm = like.astype(bool)                              # mọi chỗ cùng màu phông đều là nền
    else:
        edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
        bgm = np.isin(lab, list(edge)) if edge else np.zeros((h, w), bool)
    alpha = np.where(bgm, 0, 255).astype(np.uint8)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    if chroma:                                               # khử ám màu phông ở mép
        near = cv2.dilate((alpha == 0).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        c = int(np.argmax(bg))
        others = [i for i in range(3) if i != c]
        cap = rgb[..., others].max(axis=2)
        fix = near & (rgb[..., c] > cap)
        rgb[..., c] = np.where(fix, cap, rgb[..., c])
    return cv2.GaussianBlur(alpha, (3, 3), 0)


def _find_eyes(rgb: np.ndarray, alpha: np.ndarray) -> tuple[list, float] | None:
    """Hai mắt = hai đốm lòng trắng (có con ngươi đen bên trong) cùng hàng, cỡ gần bằng nhau,
    ở nửa trên người. Trả ([[x, y], [x, y]], nửa bề ngang mắt) hoặc None."""
    import cv2
    h, w = alpha.shape
    white = ((rgb.min(axis=2) > 215) & (alpha > 200)).astype(np.uint8)
    white[int(h * 0.6):] = 0
    n, lab, stats, cent = cv2.connectedComponentsWithStats(white, connectivity=4)
    dark = rgb.max(axis=2) < 90
    cands = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if not (w * 0.012 < bw < w * 0.2 and bh > 2 and 1.0 < bw / max(1, bh) < 5.5 and area > 12):
            continue
        # có con ngươi đen trong khung mắt (mở rộng chút vì con ngươi có thể chạm mí)
        x0, y0 = max(0, x - 1), max(0, y - 1)
        pupil = dark[y0:y + bh + 1, x0:x + bw + 1].mean()
        if pupil < 0.04:
            continue
        cands.append((cent[i][0], cent[i][1], bw, bh, area))
    best, score = None, 0.0
    for a in range(len(cands)):
        for b in range(a + 1, len(cands)):
            p, q = cands[a], cands[b]
            mw = (p[2] + q[2]) / 2
            dx, dy = abs(p[0] - q[0]), abs(p[1] - q[1])
            if dy > max(p[3], q[3]) * 0.9 or not (1.6 * mw < dx < 5.5 * mw):
                continue
            sim = min(p[4], q[4]) / max(p[4], q[4])
            if sim < 0.45:
                continue
            sc = sim * (1.0 - dy / (mw + 1)) * (1.2 - p[1] / h)
            if sc > score:
                L, R = (p, q) if p[0] < q[0] else (q, p)
                best, score = ([[float(L[0]), float(L[1])], [float(R[0]), float(R[1])]], mw / 2), sc
    return best


def _skin(rgb: np.ndarray, alpha: np.ndarray, eyes: list, d: float) -> list:
    (x0, y0), (x1, y1) = eyes
    pts = []
    for ex, ey in ((x0, y0), (x1, y1)):
        cx, cy = int(ex), int(ey + d * 0.45)
        r = max(2, int(d * 0.12))
        patch = rgb[max(0, cy - r):cy + r, max(0, cx - r):cx + r].reshape(-1, 3)
        a = alpha[max(0, cy - r):cy + r, max(0, cx - r):cx + r].reshape(-1)
        ok = patch[(a > 200) & (patch.max(axis=1) > 120)]
        if len(ok):
            pts.append(ok)
    if not pts:
        return [240, 216, 196]
    return [int(v) for v in np.median(np.concatenate(pts), axis=0)]


def marks(rgb: np.ndarray, alpha: np.ndarray, eyes: list | None, mouth: list | None) -> dict:
    """Điểm mắt / miệng: lấy theo chị đánh dấu, thiếu thì đoán theo khoảng cách hai mắt."""
    h, w = alpha.shape
    auto = True
    eye_w = None
    if eyes and len(eyes) == 2:
        auto = False
        eyes = sorted([[float(x), float(y)] for x, y in eyes])
    else:
        got = _find_eyes(rgb, alpha)
        if got:
            eyes, eye_w = got
        else:                                    # không thấy: đoán theo khung người
            ys, xs = np.nonzero(alpha > 128)
            top, cx, fw = (ys.min() if len(ys) else 0), w / 2, w * 0.36
            eyes = [[cx - fw * 0.24, top + h * 0.2], [cx + fw * 0.24, top + h * 0.2]]
    d = math.hypot(eyes[1][0] - eyes[0][0], eyes[1][1] - eyes[0][1])
    eye_w = eye_w or d * 0.22
    if mouth and len(mouth) == 2:
        auto = False
        mouth = [float(mouth[0]), float(mouth[1])]
    else:
        mouth = [(eyes[0][0] + eyes[1][0]) / 2, (eyes[0][1] + eyes[1][1]) / 2 + d * 0.8]
    return {"eyes": eyes, "mouth": mouth, "eye_w": float(eye_w), "d": float(d),
            "skin": _skin(rgb, alpha, eyes, d), "auto": auto}


def process(src: Path, dst: Path) -> dict:
    """Ảnh tải lên -> PNG nền trong, cắt sát người, kèm điểm mắt / miệng."""
    im = Image.open(src).convert("RGB")
    if im.height > MAX_H * 1.5:
        im = im.resize((int(im.width * MAX_H * 1.5 / im.height), int(MAX_H * 1.5)), Image.LANCZOS)
    rgb = np.array(im)
    alpha = _remove_bg(rgb)
    ys, xs = np.nonzero(alpha > 20)
    if len(xs):
        pad = 4
        x0, x1 = max(0, xs.min() - pad), min(rgb.shape[1], xs.max() + pad + 1)
        y0, y1 = max(0, ys.min() - pad), min(rgb.shape[0], ys.max() + pad + 1)
        rgb, alpha = rgb[y0:y1, x0:x1], alpha[y0:y1, x0:x1]
    out = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
    if out.height > MAX_H:
        out = out.resize((int(out.width * MAX_H / out.height), MAX_H), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst)
    arr = np.asarray(out)
    meta = marks(arr[..., :3], arr[..., 3], None, None)
    meta.update({"w": out.width, "h": out.height})
    return meta


def remark(path: Path, meta: dict, eyes=None, mouth=None) -> dict:
    arr = np.asarray(Image.open(path).convert("RGBA"))
    m = marks(arr[..., :3], arr[..., 3], eyes or meta.get("eyes"), mouth)
    m.update({"w": arr.shape[1], "h": arr.shape[0]})
    if eyes is None and mouth is None:
        m["auto"] = meta.get("auto", True)
    return m


# ---------------------------------------------------------------- dựng

class Pic:
    """Một ảnh nhân vật đã xử lý + điểm mắt / miệng (toạ độ px trong ảnh)."""

    def __init__(self, img: Image.Image, meta: dict):
        self.img = img
        self.meta = meta
        self.eyes = meta["eyes"]
        self.mouth = meta["mouth"]
        self.d = float(meta.get("d") or 1.0)
        self.eye_w = float(meta.get("eye_w") or self.d * 0.22)
        self.skin = tuple(meta.get("skin") or (240, 216, 196)) + (255,)
        self._cache: dict = {}

    def scaled(self, k: float) -> Image.Image:
        key = round(k, 4)
        if key not in self._cache:
            if len(self._cache) > 3:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = self.img.resize((max(1, int(self.img.width * k)), max(1, int(self.img.height * k))),
                                               Image.LANCZOS)
        return self._cache[key]

    def draw(self, canvas: Image.Image, cx: float, cy: float, d_px: float, st: wa.State, lw: float,
             bottom: float | None = None) -> None:
        """Dán ảnh lên canvas: trung điểm hai mắt ở (cx, cy), hai mắt cách nhau d_px.
        bottom: nếu chân ảnh còn cách đáy khung thì hạ ảnh xuống cho chạm đáy."""
        k = d_px / self.d
        im = self.scaled(k)
        ex = (self.eyes[0][0] + self.eyes[1][0]) / 2 * k
        ey = (self.eyes[0][1] + self.eyes[1][1]) / 2 * k
        ox, oy = cx - ex, cy - ey
        if bottom is not None and oy + im.height < bottom:
            oy = bottom - im.height
        ox, oy = int(round(ox)), int(round(oy))
        canvas.alpha_composite(im, (ox, oy)) if ox >= 0 and oy >= 0 else _paste(canvas, im, ox, oy)
        P = lambda x, y: (ox + x * k, oy + y * k)                # noqa: E731
        dd = self.d * k
        if st.blink > 0.5:
            for e in self.eyes:
                self._blink(canvas, *P(*e), self.eye_w * k, lw)
        if st.mouth > 0.08:
            self._mouth(canvas, *P(*self.mouth), dd, st.mouth, st.expr, lw)
        if "sweat" in st.extras or st.expr == "scared":
            x, y = P(self.eyes[1][0] + self.d * 0.75, self.eyes[1][1] - self.d * 0.45)
            _drop(canvas, x, y, dd * 0.09, lw)

    def _patch(self, canvas, box, fn):
        """Vẽ mịn (gấp 2) trong một ô nhỏ rồi dán lại."""
        S = 3
        x0, y0, x1, y1 = [int(v) for v in box]
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(canvas.width, x1), min(canvas.height, y1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            return
        layer = Image.new("RGBA", ((x1 - x0) * S, (y1 - y0) * S), (0, 0, 0, 0))
        fn(ImageDraw.Draw(layer), lambda x, y: ((x - x0) * S, (y - y0) * S), S)
        canvas.alpha_composite(layer.resize((x1 - x0, y1 - y0), Image.LANCZOS), (x0, y0))

    def _blink(self, canvas, x, y, ew, lw):
        def fn(d, P, S):
            rx, ry = ew * 1.25, ew * 0.62
            d.ellipse([*P(x - rx, y - ry), *P(x + rx, y + ry)], fill=self.skin)
            pts = [P(x - ew * 1.05 + 2 * ew * 1.05 * i / 12, y + math.sin(math.pi * i / 12) * ew * 0.22)
                   for i in range(13)]
            d.line(pts, fill=INK, width=max(1, int(lw * 1.3 * S)), joint="curve")
        self._patch(canvas, (x - ew * 1.6, y - ew, x + ew * 1.6, y + ew), fn)

    def _mouth(self, canvas, x, y, dd, o, expr, lw):
        """Miệng mở theo giọng, cùng kiểu nét với nhân vật vẽ (môi mỏng, khoang tối, răng trên)."""
        mw = dd * 0.25
        h = dd * (0.07 + 0.3 * min(1.0, o))
        curve = {"happy": 0.08, "laughing": 0.1, "sad": -0.06, "crying": -0.07, "worried": -0.03,
                 "angry": -0.04}.get(expr, 0.0) * dd

        def fn(d, P, S):
            # che miệng gốc bằng màu da
            d.ellipse([*P(x - dd * 0.33, y - dd * 0.07), *P(x + dd * 0.33, y + dd * 0.27)], fill=self.skin)
            top = y - h * 0.3 - curve * 0.3
            pts = wa._crs([(x - mw, y - curve * 0.3), (x - mw * 0.5, top), (x + mw * 0.5, top),
                           (x + mw, y - curve * 0.3), (x + mw * 0.6, y + h * 0.7 + curve),
                           (x - mw * 0.6, y + h * 0.7 + curve)], 6)
            q = [P(*p) for p in pts]
            d.polygon(q, fill=(88, 40, 44, 255))
            if o > 0.35:
                d.polygon([P(x - mw * 0.55, top + dd * 0.012), P(x + mw * 0.55, top + dd * 0.012),
                           P(x + mw * 0.45, top + dd * 0.07), P(x - mw * 0.45, top + dd * 0.07)],
                          fill=(250, 250, 248, 255))
                d.ellipse([*P(x - mw * 0.42, y + h * 0.35), *P(x + mw * 0.42, y + h * 0.75)],
                          fill=(200, 100, 104, 255))
            d.line(q + [q[0]], fill=INK, width=max(1, int(lw * S)), joint="curve")
        self._patch(canvas, (x - dd * 0.4, y - dd * 0.15, x + dd * 0.4, y + dd * 0.5), fn)


def _paste(canvas: Image.Image, im: Image.Image, ox: int, oy: int) -> None:
    """alpha_composite cho phép ảnh thò ra ngoài khung (toạ độ âm)."""
    sx, sy = max(0, -ox), max(0, -oy)
    crop = im.crop((sx, sy, min(im.width, canvas.width - ox), min(im.height, canvas.height - oy)))
    if crop.width > 0 and crop.height > 0:
        canvas.alpha_composite(crop, (max(0, ox), max(0, oy)))


def _drop(canvas, x, y, r, lw):
    d = ImageDraw.Draw(canvas)
    pts = [(x, y - r * 1.8), (x + r, y), (x, y + r), (x - r, y)]
    d.polygon(wa._crs(pts, 6), fill=(150, 200, 240, 255), outline=INK)


def load(st: dict, pdir: Path | None) -> dict:
    """{id nhân vật: {key: Pic}} từ các ảnh đã tải lên."""
    out: dict = {}
    if pdir is None:
        return out
    for cid, items in (st.get("pics") or {}).items():
        for key, meta in (items or {}).items():
            p = Path(pdir) / PICS_DIR / cid / f"{key}.png"
            if not p.exists() or not meta.get("eyes"):
                continue
            try:
                out.setdefault(cid, {})[key] = Pic(Image.open(p).convert("RGBA"), meta)
            except Exception:  # noqa: BLE001
                continue
    return out


def pick(pics: dict, pose: str, expr: str) -> Pic | None:
    """Ảnh hợp nhất: đúng tư thế + nét mặt > đúng tư thế > ảnh gốc (đúng nét mặt) > ảnh gốc > bất kỳ."""
    if not pics:
        return None
    for k in (key_of(pose, expr), key_of(pose), key_of("down", expr), "down"):
        if k in pics:
            return pics[k]
    return next(iter(pics.values()))
