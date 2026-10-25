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
OPEN_SUFFIX = ".open.png"           # ảnh miệng mở đi kèm (đã căn khớp với ảnh gốc)
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
    "hold_baby": "holding a sleeping baby wrapped in a soft yellow blanket in both arms in front of the chest",
    "hold_cup": "holding a white coffee mug in one hand in front of the chest",
    "hold_paper": "holding a sheet of paper / document with both hands in front of the chest, looking at it",
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
STYLE_EN = ("Korean webtoon style exactly like Korean YouTube story-animation channels (\"썰\" / 사연 animation): "
            "clean bold uniform black outlines, flat pastel colors, NO shading, no gradients, no textures, "
            "simple neat line art, natural adult proportions, large oval solid black pupils with a small white "
            "highlight, eyebrows as simple dark strokes, nose as one small line, small simple mouth, "
            "hair drawn as flat color with a few black strand lines, clothes with simple fold lines.")


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


def prompt_open() -> str:
    return ("Edit the attached image. Keep EVERYTHING exactly the same: same character, same pose, same "
            "framing and image size, same colors, same green background, head in exactly the same place. "
            "Change ONLY the mouth: open it naturally as if in the middle of speaking a word, upper teeth "
            "slightly visible. Do not move or resize anything else.")


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
                        "has_open": bool(((have.get(cid) or {}).get(k) or {}).get("open")),
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


def _skin_tone(rgb, alpha):
    h, w = alpha.shape
    reg = rgb[: int(h * 0.6)].reshape(-1, 3).astype(int)
    a = alpha[: int(h * 0.6)].reshape(-1)
    r, g, b = reg[:, 0], reg[:, 1], reg[:, 2]
    ok = (a > 200) & (r > 110) & (r >= g) & (g >= b - 5) & (r - b > 18) & (r - b < 150)
    px = reg[ok]
    if len(px) < 50:
        return None
    q = (px // 24)
    keys, cnt = np.unique(q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2], return_counts=True)
    top = keys[np.argmax(cnt)]
    sel = px[(q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]) == top]
    return np.median(sel, axis=0)

def _dark_eyes(rgb, tone, face):
    """Con ngươi = đốm tối tròn, dày (mở ảnh bằng nhân cỡ ~3% bề ngang mặt thì gọng kính,
    nét mí mắt mảnh biến mất, con ngươi còn lại), từng cặp cùng hàng trong nửa trên mặt."""
    import cv2
    fx, fy, fw, fh = face
    lum = rgb.astype(np.float32).mean(axis=2)
    dark = (lum < tone.mean() * 0.55).astype(np.uint8)
    box = np.zeros_like(dark); box[fy:fy + int(fh * 0.62), fx:fx + fw] = 1
    dark &= box
    k = max(2, int(round(fw * 0.03)))
    op = cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, lab, st, cen = cv2.connectedComponentsWithStats(op, connectivity=8)
    c = []
    for i in range(1, n):
        x, y, bw, bh, ar = st[i]
        if ar < k * k * 0.5 or bw > fw * 0.2 or bh > fh * 0.15 or bw / max(1, bh) > 2.6:
            continue
        c.append(dict(x=cen[i][0], y=cen[i][1], bw=bw, bh=bh, area=ar))
    best, sc = None, 0
    for a in range(len(c)):
        for b in range(a + 1, len(c)):
            p, q = c[a], c[b]
            dx, dy = abs(p['x'] - q['x']), abs(p['y'] - q['y'])
            if dy > fh * 0.05 or not (fw * 0.22 < dx < fw * 0.7):
                continue
            sim = min(p['area'], q['area']) / max(p['area'], q['area'])
            mid = (p['x'] + q['x']) / 2
            s = sim * (1 - abs(mid - (fx + fw / 2)) / fw) * (1 - dy / (fh * 0.05 + 1))
            if sim > 0.3 and s > sc:
                best, sc = ((p, q) if p['x'] < q['x'] else (q, p)), s
    return best


def _features(rgb, alpha):
    """Tìm mắt + miệng trên ảnh: mảng da của mặt, con ngươi là đốm tối tròn (bỏ qua gọng
    kính, nét mảnh), miệng là đường tối rộng nằm giữa, dưới mắt. Hợp cả tranh hoạt hình lẫn
    tranh gần người thật. Trả dict hoặc None."""
    import cv2
    h, w = alpha.shape
    tone = _skin_tone(rgb, alpha)
    if tone is None:
        return None
    dist = np.abs(rgb.astype(int) - tone[None, None]).sum(axis=2)
    skin = ((dist < 75) & (alpha > 200)).astype(np.uint8)
    skin[int(h * 0.8):] = 0
    n, lab, st, cen = cv2.connectedComponentsWithStats(skin, connectivity=8)
    if n < 2:
        return None
    # mặt = mảng da lớn nhất (ưu tiên ở trên)
    i = max(range(1, n), key=lambda k: st[k][4] * (1.3 - st[k][1] / h))
    # gọng kính / tóc mái có thể cắt mặt thành nhiều mảng: khung mặt = các mảng da lớn quanh mảng chính
    x0, y0, x1, y1 = st[i][0], st[i][1], st[i][0] + st[i][2], st[i][1] + st[i][3]
    for k in range(1, n):
        x, y, bw, bh, ar = st[k]
        cx = x + bw / 2
        if k != i and ar > st[i][4] * 0.03 and st[i][0] - st[i][2] * 0.1 < cx < st[i][0] + st[i][2] * 1.1 \
                and y < y1 + st[i][3] * 1.2:
            x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x + bw), max(y1, y + bh)
    fx, fy, fw, fh = int(x0), int(y0), int(x1 - x0), int(y1 - y0)
    # lỗ bên trong mảng da = mắt, mày, miệng, lỗ mũi...
    # (tính trên mọi mảng da: mắt sau tròng kính nằm trong mảng da riêng của tròng kính)
    inv = np.pad((1 - skin).astype(np.uint8), 1, constant_values=1)
    m2 = np.zeros((h + 4, w + 4), np.uint8)
    cv2.floodFill(inv, m2, (0, 0), 2)
    holes = (inv[1:-1, 1:-1] == 1).astype(np.uint8)
    holes[:fy] = 0; holes[fy + fh:] = 0; holes[:, :fx] = 0; holes[:, fx + fw:] = 0
    # bỏ viền ngoài khung ảnh: lỗ phải nằm trong khung mặt
    n2, lab2, st2, cen2 = cv2.connectedComponentsWithStats(holes, connectivity=8)
    dark = rgb.max(axis=2) < tone.max() * 0.55          # tối hơn hẳn màu da
    blobs = []
    for k in range(1, n2):
        x, y, bw, bh, area = st2[k]
        if area < 6 or bw > fw * 0.6:
            continue
        dk = dark[y:y + bh, x:x + bw][lab2[y:y + bh, x:x + bw] == k].mean()
        blobs.append(dict(x=cen2[k][0], y=cen2[k][1], bw=bw, bh=bh, area=area, dark=dk, box=(x, y, bw, bh)))
    eyes2 = _dark_eyes(rgb, tone, (fx, fy, fw, fh))
    # mắt: cặp lỗ cùng hàng, cỡ gần nhau, có màu tối (con ngươi), ở nửa trên mặt
    best, sc = None, 0
    for a in range(len(blobs)):
        for b in range(a + 1, len(blobs)):
            p, q = blobs[a], blobs[b]
            if p['y'] > fy + fh * 0.75 or q['y'] > fy + fh * 0.75:
                continue
            mw = (p['bw'] + q['bw']) / 2
            dx, dy = abs(p['x'] - q['x']), abs(p['y'] - q['y'])
            if dy > max(p['bh'], q['bh']) * 0.8 + 2 or not (1.5 * mw < dx < 12 * mw) or dx < fw * 0.22 or dx > fw * 0.7:
                continue
            sim = min(p['area'], q['area']) / max(p['area'], q['area'])
            if sim < 0.35 or min(p['dark'], q['dark']) < 0.15:
                continue
            mid = (p['x'] + q['x']) / 2
            cent = 1 - abs(mid - (fx + fw / 2)) / fw
            s = sim * cent * (p['bw'] / max(1, p['bh']) > 0.8) * (1 + 0.3 * min(p['dark'], q['dark']))
            # mắt nằm dưới lông mày: cùng điểm thì ưu tiên cặp thấp hơn trong nửa trên
            s *= 1 + 0.2 * ((p['y'] - fy) / fh)
            if s > sc:
                best, sc = (p, q) if p['x'] < q['x'] else (q, p), s
    if eyes2:
        best = eyes2
    if not best:
        # mắt nhắm (cười híp...): tìm miệng mở to giữa nửa dưới mặt rồi suy ra chỗ mắt
        cx_f = fx + fw / 2
        big = [bl for bl in blobs if bl['bw'] >= fw * 0.16 and abs(bl['x'] - cx_f) < fw * 0.14
               and fy + fh * 0.4 < bl['y'] < fy + fh * 0.92 and bl['bw'] >= bl['bh'] * 1.05 and bl['dark'] > 0.2]
        if not big:
            return None
        mb = max(big, key=lambda bl: bl['bw'] * bl['bh'])
        d = fw * 0.45
        x, y, bw, bh = mb['box']
        mxy = [float(x + bw / 2), float(y + bh * 0.5)]
        ey = mxy[1] - 0.85 * d
        return dict(eyes=[[mxy[0] - d / 2, ey], [mxy[0] + d / 2, ey]], eye_w=float(d * 0.21), d=float(d),
                    face=(int(fx), int(fy), int(fw), int(fh)), mouth=mxy, mouth_w=float(bw), mouth_h=float(bh),
                    eyes_guess=True)
    L, R = best
    eyes = [[float(L['x']), float(L['y'])], [float(R['x']), float(R['y'])]]
    d = math.hypot(R['x'] - L['x'], R['y'] - L['y'])
    ex, ey = (L['x'] + R['x']) / 2, (L['y'] + R['y']) / 2
    # miệng: lỗ rộng nhất, nằm giữa, thấp hơn mắt 0.5d..1.3d
    mouth, mw = None, 0
    for bl in blobs:
        if not (ey + 0.5 * d < bl['y'] < ey + 1.35 * d) or abs(bl['x'] - ex) > 0.35 * d:
            continue
        if bl['bw'] < 0.18 * d or bl['bw'] < bl['bh'] * 1.2:
            continue
        s = bl['bw'] * (1 - abs(bl['x'] - ex) / d)
        if s > mw:
            mouth, mw = bl, s
    out = dict(eyes=eyes, eye_w=float((L['bw'] + R['bw']) / 4), d=float(d), face=(int(fx), int(fy), int(fw), int(fh)))
    if mouth:
        x, y, bw, bh = mouth['box']
        out['mouth'] = [float(x + bw / 2), float(y + bh * 0.5)]
        out['mouth_w'] = float(bw)
        out['mouth_h'] = float(bh)
    return out


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
    """Điểm mắt / miệng: lấy theo chị đánh dấu, thiếu thì tool tự tìm. "sure" = False khi tool
    không chắc (khi đó không vẽ miệng nhép, báo chị bấm đánh dấu)."""
    h, w = alpha.shape
    auto, sure, mouth_w, mouth_h, eyes_guess = True, True, None, None, False
    got = None if (eyes and len(eyes) == 2 and mouth and len(mouth) == 2) else _features(rgb, alpha)
    if eyes and len(eyes) == 2:
        auto = False
        eyes = sorted([[float(x), float(y)] for x, y in eyes])
    elif got:
        eyes = got["eyes"]
        eyes_guess = bool(got.get("eyes_guess"))
    else:
        old = _find_eyes(rgb, alpha)
        if old:
            eyes = old[0]
        else:                                    # không thấy: đoán theo khung người
            ys, xs = np.nonzero(alpha > 128)
            top, cx, fw = (ys.min() if len(ys) else 0), w / 2, w * 0.36
            eyes = [[cx - fw * 0.24, top + h * 0.2], [cx + fw * 0.24, top + h * 0.2]]
        sure = False
    d = math.hypot(eyes[1][0] - eyes[0][0], eyes[1][1] - eyes[0][1])
    if mouth and len(mouth) == 2:
        auto = False
        mouth = [float(mouth[0]), float(mouth[1])]
    else:
        ex, ey = (eyes[0][0] + eyes[1][0]) / 2, (eyes[0][1] + eyes[1][1]) / 2
        gm = got.get("mouth") if got else None
        if gm and ey + 0.45 * d < gm[1] < ey + 1.4 * d and abs(gm[0] - ex) < 0.4 * d:
            mouth, mouth_w, mouth_h = gm, got.get("mouth_w"), got.get("mouth_h")
        else:
            mouth, sure = [ex, ey + d * 0.8], False
    if not auto:
        sure = True
    skin = _skin(rgb, alpha, eyes, d)
    return {"eyes": eyes, "mouth": mouth, "eye_w": float(d * 0.21), "d": float(d),
            "mouth_w": float(mouth_w or d * 0.5), "mouth_h": float(mouth_h or d * 0.06), "skin": skin, "skin_m": _skin_near(rgb, alpha, mouth, d, skin),
            "auto": auto, "sure": sure, **({"eyes_guess": True} if eyes_guess and auto else {})}


def _skin_near(rgb, alpha, mouth, d, skin) -> list:
    """Màu da ngay quanh miệng (thường tối hơn má) để miếng che miệng cũ không lộ."""
    x, y = int(mouth[0]), int(mouth[1])
    rx, ry = int(d * 0.5), int(d * 0.35)
    box = rgb[max(0, y - ry):y + ry, max(0, x - rx):x + rx].reshape(-1, 3).astype(int)
    a = alpha[max(0, y - ry):y + ry, max(0, x - rx):x + rx].reshape(-1)
    if not len(box):
        return skin
    near = np.abs(box - np.array(skin)[None]).sum(axis=1) < 90
    ok = box[(a > 200) & near]
    return [int(v) for v in np.median(ok, axis=0)] if len(ok) > 20 else skin


def _cutout(src: Path) -> Image.Image:
    """Ảnh tải lên -> RGBA nền trong, cắt sát người, cao tối đa MAX_H."""
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
    return out


def process(src: Path, dst: Path) -> dict:
    """Ảnh tải lên -> PNG nền trong, cắt sát người, kèm điểm mắt / miệng."""
    out = _cutout(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst)
    arr = np.asarray(out)
    meta = marks(arr[..., :3], arr[..., 3], None, None)
    meta.update({"w": out.width, "h": out.height})
    return meta


def _on_gray(im: Image.Image) -> np.ndarray:
    bg = Image.new("RGBA", im.size, (128, 128, 128, 255))
    bg.alpha_composite(im)
    return np.asarray(bg.convert("L"), dtype=np.float32)


def process_open(src: Path, base_path: Path, meta: dict, dst: Path) -> dict:
    """Ảnh miệng mở (AI sửa từ ảnh gốc): tách nền như ảnh gốc, đưa về cùng cỡ, dò vùng mắt
    để căn khớp từng điểm ảnh với ảnh gốc rồi lưu. Trả {"dx", "dy", "score"} (score < 0.5:
    hai ảnh lệch nhau nhiều, nên tạo lại)."""
    import cv2
    base = Image.open(base_path).convert("RGBA")
    op = _cutout(src)
    if abs(op.width / op.height - base.width / base.height) < 0.08:
        op = op.resize(base.size, Image.LANCZOS)
    else:                                         # khác tỉ lệ: theo chiều cao
        op = op.resize((max(1, int(op.width * base.height / op.height)), base.height), Image.LANCZOS)
    d = float(meta.get("d") or base.width * 0.15)
    (x0, y0), (x1, y1) = meta["eyes"]
    tx0, ty0 = int(max(0, min(x0, x1) - 0.6 * d)), int(max(0, min(y0, y1) - 0.55 * d))
    tx1, ty1 = int(min(base.width, max(x0, x1) + 0.6 * d)), int(min(base.height, max(y0, y1) + 0.35 * d))
    g0, g1 = _on_gray(base), _on_gray(op)
    tpl = g0[ty0:ty1, tx0:tx1]
    r = int(0.6 * d)
    sx0, sy0 = max(0, tx0 - r), max(0, ty0 - r)
    win = g1[sy0:min(g1.shape[0], ty1 + r), sx0:min(g1.shape[1], tx1 + r)]
    dx = dy = 0
    score = 0.0
    if tpl.size and win.shape[0] >= tpl.shape[0] and win.shape[1] >= tpl.shape[1]:
        res = cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        dx, dy = sx0 + loc[0] - tx0, sy0 + loc[1] - ty0
    aligned = Image.new("RGBA", base.size, (0, 0, 0, 0))
    _paste(aligned, op, -int(dx), -int(dy))
    dst.parent.mkdir(parents=True, exist_ok=True)
    aligned.save(dst)
    return {"dx": int(dx), "dy": int(dy), "score": round(float(score), 3)}


def remark(path: Path, meta: dict, eyes=None, mouth=None) -> dict:
    arr = np.asarray(Image.open(path).convert("RGBA"))
    """Tính lại điểm mắt / miệng: chị đánh dấu thì theo chị; không đưa điểm nào thì tool tự tìm lại."""
    m = marks(arr[..., :3], arr[..., 3], eyes, mouth)
    if meta.get("open"):
        m["open"] = meta["open"]
    m.update({"w": arr.shape[1], "h": arr.shape[0]})
    return m


# ---------------------------------------------------------------- dựng

class Pic:
    """Một ảnh nhân vật đã xử lý + điểm mắt / miệng (toạ độ px trong ảnh)."""

    def __init__(self, img: Image.Image, meta: dict, open_img: Image.Image | None = None):
        self.img = img
        self.open_img = open_img                 # cùng ảnh nhưng miệng mở (AI sửa), đã căn khớp
        self.meta = meta
        self.eyes = meta["eyes"]
        self.mouth = meta["mouth"]
        self.d = float(meta.get("d") or 1.0)
        self.eye_w = float(meta.get("eye_w") or self.d * 0.22)
        self.skin = tuple(meta.get("skin") or (240, 216, 196)) + (255,)
        self.mouth_w = float(meta.get("mouth_w") or self.d * 0.5)
        self.mouth_h = float(meta.get("mouth_h") or self.d * 0.06)
        # tranh vẽ sẵn miệng mở (cười to, sốc...): miệng cao rõ so với mắt và so với bề ngang miệng
        self.open_orig = self.mouth_h > self.d * 0.13 and self.mouth_h > self.mouth_w * 0.28
        self.no_blink = bool(meta.get("eyes_guess"))      # mắt nhắm sẵn (cười híp): không vẽ chớp mắt
        self.skin_m = tuple(meta.get("skin_m") or meta.get("skin") or (240, 216, 196)) + (255,)
        self.sure = meta.get("sure", True) is not False
        self._cache: dict = {}
        self._open_cache: dict = {}

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
        _paste(canvas, im, ox, oy)
        P = lambda x, y: (ox + x * k, oy + y * k)                # noqa: E731
        dd = self.d * k
        if st.blink > 0.5 and not self.no_blink:
            for e in self.eyes:
                self._blink(canvas, *P(*e), self.eye_w * k, lw)
        if st.mouth > 0.08 and self.open_img is not None:
            self._open_mouth(canvas, k, ox, oy, st.mouth)
        elif st.mouth > 0.08 and self.sure and self.open_orig:
            self._jaw(canvas, k, ox, oy, st.mouth)  # miệng vẽ sẵn đã mở: giữ miệng thật, chỉ hạ hàm theo giọng
        elif st.mouth > 0.08 and self.sure:          # tool không chắc chỗ miệng: thà không vẽ còn hơn vẽ sai
            self._mouth(canvas, *P(*self.mouth), dd, st.mouth, st.expr, lw, self.mouth_w * k, self.mouth_h * k)
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

    def _open_mouth(self, canvas, k, ox, oy, o):
        """Nói: lấy vùng miệng của ảnh miệng mở hoà dần vào (mở càng to khi giọng càng to)."""
        key = round(k, 4)
        if key not in self._open_cache:
            if len(self._open_cache) > 2:
                self._open_cache.pop(next(iter(self._open_cache)))
            d = self.d
            mx, my = self.mouth
            rx, ry = max(self.mouth_w * 0.75, d * 0.38), d * 0.42
            box = [int(mx - rx * 1.2), int(my - ry * 0.75), int(mx + rx * 1.2), int(my + ry * 1.45)]
            box = [max(0, box[0]), max(0, box[1]), min(self.open_img.width, box[2]), min(self.open_img.height, box[3])]
            if box[2] - box[0] < 4 or box[3] - box[1] < 4:
                self._open_cache[key] = None
                return
            crop = self.open_img.crop(box)
            mask = Image.new("L", crop.size, 0)
            ImageDraw.Draw(mask).ellipse([mx - rx - box[0], my - ry * 0.55 - box[1], mx + rx - box[0],
                                          my + ry * 1.25 - box[1]], fill=255)
            from PIL import ImageFilter
            mask = mask.filter(ImageFilter.GaussianBlur(max(1.0, d * 0.06)))
            W_, H_ = max(1, int(crop.width * k)), max(1, int(crop.height * k))
            self._open_cache[key] = (crop.resize((W_, H_), Image.LANCZOS), mask.resize((W_, H_), Image.LANCZOS),
                                     box[0] * k, box[1] * k)
        got = self._open_cache[key]
        if not got:
            return
        crop, mask, bx, by = got
        a = min(1.0, max(0.0, (o - 0.1) * 6.0))           # chuyển nhanh, không lồng hai miệng
        m = mask if a >= 0.99 else mask.point(lambda v: int(v * a))
        piece = crop.copy()
        piece.putalpha(Image.fromarray(np.minimum(np.asarray(crop.getchannel("A")), np.asarray(m))))
        _paste(canvas, piece, int(round(ox + bx)), int(round(oy + by)))

    def _jaw(self, canvas, k, ox, oy, o):
        """Tranh đã vẽ miệng mở: kéo dãn vùng miệng xuống một chút theo giọng (hàm hạ xuống,
        miệng mở rộng thêm) — vẫn là nét vẽ gốc, không vẽ miệng mới đè lên."""
        from PIL import ImageFilter
        d = self.d
        mx, my = self.mouth
        rx = max(self.mouth_w * 0.62, d * 0.2)
        top, bot = my - self.mouth_h * 0.55, my + self.mouth_h * 0.62 + d * 0.04   # chỉ vùng miệng, không lấn cằm
        box = [int(mx - rx), int(top), int(mx + rx), int(bot)]
        box = [max(0, box[0]), max(0, box[1]), min(self.img.width, box[2]), min(self.img.height, box[3])]
        if box[2] - box[0] < 4 or box[3] - box[1] < 4:
            return
        f = 1.0 + 0.2 * min(1.0, o)
        crop = self.img.crop(box)
        W_, H_ = max(1, int(crop.width * k)), max(1, int(crop.height * k * f))
        piece = crop.resize((W_, H_), Image.LANCZOS)
        mk = Image.new("L", (W_, H_), 0)
        ImageDraw.Draw(mk).ellipse([W_ * 0.04, H_ * 0.06, W_ * 0.96, H_ * 0.97], fill=255)
        mk = mk.filter(ImageFilter.GaussianBlur(max(1.0, d * k * 0.05)))
        piece.putalpha(Image.fromarray(np.minimum(np.asarray(piece.getchannel("A")), np.asarray(mk))))
        _paste(canvas, piece, int(round(ox + box[0] * k)), int(round(oy + box[1] * k)))

    def _mouth(self, canvas, x, y, dd, o, expr, lw, mouth_px=None, mouth_hpx=None):
        """Miệng mở theo giọng, cùng kiểu nét với nhân vật vẽ (môi mỏng, khoang tối, răng trên);
        rộng theo miệng thật trong ảnh, mở vừa phải như người nói (không há to)."""
        mw = min(dd * 0.26, max(dd * 0.14, (mouth_px or dd * 0.5) * 0.4))
        h = dd * (0.035 + 0.15 * min(1.0, o))
        curve = {"happy": 0.04, "laughing": 0.05, "sad": -0.03, "crying": -0.035, "worried": -0.015,
                 "angry": -0.02}.get(expr, 0.0) * dd

        # che miệng gốc bằng màu da quanh miệng, mép mờ dần cho khỏi lộ viền
        cw = max(dd * 0.24, (mouth_px or dd * 0.5) * 0.56)
        mh = max(dd * 0.05, mouth_hpx or 0.0)
        from PIL import ImageFilter
        bx0, by0 = int(x - cw - dd * 0.12), int(y - mh - dd * 0.12)
        bw_, bh_ = int(2 * cw + dd * 0.24) + 1, int(mh * 2 + dd * 0.5) + 1
        mk = Image.new("L", (bw_, bh_), 0)
        ImageDraw.Draw(mk).ellipse([x - cw - bx0, y - mh * 0.75 - dd * 0.03 - by0, x + cw - bx0,
                                    y + mh * 0.8 + dd * 0.24 - by0], fill=255)
        mk = mk.filter(ImageFilter.GaussianBlur(max(1.0, dd * 0.035)))
        cover = Image.new("RGBA", (bw_, bh_), self.skin_m)
        cover.putalpha(mk)
        _paste(canvas, cover, bx0, by0)

        def fn(d, P, S):
            top = y - h * 0.3 - curve * 0.3
            pts = wa._crs([(x - mw, y - curve * 0.3), (x - mw * 0.5, top), (x + mw * 0.5, top),
                           (x + mw, y - curve * 0.3), (x + mw * 0.6, y + h * 0.7 + curve),
                           (x - mw * 0.6, y + h * 0.7 + curve)], 6)
            q = [P(*p) for p in pts]
            d.polygon(q, fill=(88, 40, 44, 255))
            if o > 0.45:
                th = h * 0.28
                d.polygon([P(x - mw * 0.55, top + th * 0.15), P(x + mw * 0.55, top + th * 0.15),
                           P(x + mw * 0.45, top + th), P(x - mw * 0.45, top + th)],
                          fill=(250, 250, 248, 255))
                d.ellipse([*P(x - mw * 0.4, y + h * 0.4), *P(x + mw * 0.4, y + h * 0.72)],
                          fill=(200, 100, 104, 255))
            d.line(q + [q[0]], fill=INK, width=max(1, int(lw * 0.85 * S)), joint="curve")
        self._patch(canvas, (x - cw - dd * 0.05, y - dd * 0.15, x + cw + dd * 0.05, y + dd * 0.5), fn)


def _paste(canvas: Image.Image, im: Image.Image, ox: int, oy: int) -> None:
    """alpha_composite chỉ phần ảnh nằm trong khung: ảnh thò ra ngoài (toạ độ âm, quá mép
    phải / dưới) hoặc còn nằm hẳn ngoài khung (nhân vật đang đi vào) đều không lỗi."""
    x0, y0 = max(0, -ox), max(0, -oy)
    x1, y1 = min(im.width, canvas.width - ox), min(im.height, canvas.height - oy)
    if x1 <= x0 or y1 <= y0:
        return
    canvas.alpha_composite(im.crop((x0, y0, x1, y1)), (ox + x0, oy + y0))


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
            po = p.with_name(f"{key}{OPEN_SUFFIX}")
            try:
                op = Image.open(po).convert("RGBA") if meta.get("open") and po.exists() else None
                out.setdefault(cid, {})[key] = Pic(Image.open(p).convert("RGBA"), meta, op)
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


def prompts_text(st: dict, cid: str | None = None, missing: bool = True) -> str:
    """File câu lệnh vẽ: mỗi dòng một câu lệnh (để tạo hàng loạt), theo đúng thứ tự các ô;
    missing=True chỉ lấy những ảnh còn thiếu."""
    rows = [n for n in needed(st) if (cid is None or n["cid"] == cid) and not (missing and n["have"])]
    return "\n".join(" ".join(n["prompt"].split()) for n in rows) + ("\n" if rows else "")


def refresh(st: dict, pdir: Path) -> bool:
    """Ảnh tải lên từ bản cũ (điểm mắt / miệng do bộ tìm cũ đoán, có thể sai): tìm lại một
    lần bằng bộ tìm mới; điểm chị tự đánh dấu thì giữ nguyên. Trả True nếu có thay đổi."""
    changed = False
    for cid, items in (st.get("pics") or {}).items():
        for key, meta in list((items or {}).items()):
            if ("sure" in meta and "mouth_h" in meta) or not meta.get("auto", True):
                continue
            p = Path(pdir) / PICS_DIR / cid / f"{key}.png"
            if not p.exists():
                continue
            try:
                items[key] = remark(p, meta)
                changed = True
            except Exception:  # noqa: BLE001
                continue
    return changed
