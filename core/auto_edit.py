# -*- coding: utf-8 -*-
"""Edit tự động cho video Webtoon: tiếng động, chuyển cảnh, hiệu ứng nhấn — đa dạng, không lặp.

Tiếng động do tool tự tạo (không dùng file của ai), mỗi loại nhiều biến thể. Kế hoạch edit
chọn theo nội dung từng cảnh (đổi địa điểm, sốc, giận, cười, điện thoại, màn đen...) và theo
"hạt giống" edit_seed: bấm "Đổi kiểu edit" là ra một bản khác. Cùng hạt giống thì xem trước và
video dựng ra giống hệt nhau (mỗi chương trình con dựng song song đều tính ra cùng kế hoạch).
"""
from __future__ import annotations

import math
import random
import zlib

import numpy as np

SR = 24000

# ---------------------------------------------------------------- tiếng động

_CACHE: dict = {}


def _env(n: int, attack: float, sr: int = SR) -> np.ndarray:
    a = max(1, int(attack * sr))
    e = np.ones(n, np.float32)
    e[:a] = np.linspace(0, 1, a, dtype=np.float32)
    return e


def _lowpass(x: np.ndarray, cut: np.ndarray | float) -> np.ndarray:
    """Lọc thông thấp một cực, tần số cắt thay đổi theo thời gian được (Hz)."""
    cut = np.broadcast_to(np.asarray(cut, np.float32), x.shape)
    a = 1.0 - np.exp(-2 * math.pi * cut / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += float(a[i]) * (float(x[i]) - acc)
        y[i] = acc
    return y


def _tone(freq, dur: float, decay: float, shape: str = "sin") -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    f = np.broadcast_to(np.asarray(freq, np.float32), (n,)) if np.ndim(freq) else np.full(n, freq, np.float32)
    ph = 2 * math.pi * np.cumsum(f) / SR
    w = np.sin(ph) if shape == "sin" else np.sign(np.sin(ph)) * 0.5
    return (w * np.exp(-t / max(decay, 1e-3))).astype(np.float32)


def _norm(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return (x * (peak / m)).astype(np.float32)


def _make(name: str) -> np.ndarray:
    rnd = np.random.default_rng(zlib.crc32(name.encode()))
    noise = lambda d: rnd.uniform(-1, 1, int(d * SR)).astype(np.float32)  # noqa: E731
    if name.startswith("whoosh"):
        d, lo, hi = {"whoosh1": (0.45, 300, 4200), "whoosh2": (0.32, 600, 6000),
                     "whoosh3": (0.6, 200, 2600), "whoosh4": (0.38, 900, 7000)}[name]
        n = int(d * SR)
        u = np.linspace(0, 1, n, dtype=np.float32)
        bell = np.sin(np.pi * u) ** 2
        x = _lowpass(noise(d), lo + (hi - lo) * bell) - _lowpass(noise(d), lo * 0.5) * 0.3
        return _norm(x * bell, 0.8)
    if name.startswith("swish"):
        d = {"swish1": 0.18, "swish2": 0.24}[name]
        n = int(d * SR)
        u = np.linspace(0, 1, n, dtype=np.float32)
        x = _lowpass(noise(d), 1500 + 6000 * u)
        return _norm(x * np.sin(np.pi * u) ** 3, 0.6)
    if name.startswith("pop"):
        f0, f1 = {"pop1": (950, 320), "pop2": (1400, 600), "pop3": (700, 220)}[name]
        d = 0.09
        n = int(d * SR)
        f = np.geomspace(f0, f1, n).astype(np.float32)
        return _norm(_tone(f, d, 0.03) * _env(n, 0.003), 0.8)
    if name == "boing":
        d = 0.5
        n = int(d * SR)
        t = np.arange(n) / SR
        f = (220 + 90 * np.sin(2 * math.pi * 11 * t) * np.exp(-t * 4)).astype(np.float32)
        return _norm(_tone(f, d, 0.22) * _env(n, 0.004), 0.7)
    if name == "blip":
        a = _tone(660, 0.08, 0.04) * _env(int(0.08 * SR), 0.002)
        b = _tone(440, 0.14, 0.07) * _env(int(0.14 * SR), 0.002)
        return _norm(np.concatenate([a, np.zeros(int(0.05 * SR), np.float32), b]), 0.6)
    if name in ("impact1", "impact2", "thud"):
        d = {"impact1": 0.9, "impact2": 0.7, "thud": 0.4}[name]
        n = int(d * SR)
        f = np.geomspace({"impact1": 90, "impact2": 120, "thud": 70}[name], 38, n).astype(np.float32)
        body = _tone(f, d, {"impact1": 0.3, "impact2": 0.22, "thud": 0.1}[name])
        crack = np.zeros(n, np.float32)
        k = int(0.04 * SR)
        crack[:k] = _lowpass(noise(0.04), 3000 if name != "thud" else 900) * np.linspace(1, 0, k)
        return _norm(body + crack * 0.8, 0.95)
    if name == "sting":                                   # cú lật / phát hiện: đánh mạnh + âm cao chói
        d = 1.0
        n = int(d * SR)
        t = np.arange(n) / SR
        low = _tone(np.geomspace(110, 45, n).astype(np.float32), d, 0.35)
        high = sum(_tone(f, d, 0.45) for f in (1244, 1318, 1864)) / 3
        x = low + 0.35 * high * (1 - np.exp(-t * 60))
        return _norm(x, 0.9)
    if name.startswith("ding"):
        notes = {"ding1": ((1318, 0.0), (1760, 0.12)), "ding2": ((1568, 0.0),), "ding3": ((988, 0.0), (1318, 0.09), (1976, 0.18))}[name]
        d = 0.9
        x = np.zeros(int(d * SR), np.float32)
        for f, at in notes:
            k = int(at * SR)
            y = (_tone(f, d - at, 0.25) + 0.3 * _tone(f * 2.01, d - at, 0.12)) * _env(int((d - at) * SR), 0.002)
            x[k:k + len(y)] += y
        return _norm(x, 0.6)
    if name == "buzz":                                    # điện thoại rung
        d = 0.7
        n = int(d * SR)
        t = np.arange(n) / SR
        gate = ((t % 0.35) < 0.22).astype(np.float32)
        return _norm(_tone(150, d, 10, "sq") * gate, 0.5)
    if name == "heartbeat":
        x = np.zeros(int(1.5 * SR), np.float32)
        for at in (0.0, 0.22, 0.75, 0.97):
            y = _tone(np.geomspace(70, 45, int(0.18 * SR)).astype(np.float32), 0.18, 0.06)
            k = int(at * SR)
            x[k:k + len(y)] += y * (1.0 if at in (0.0, 0.75) else 0.7)
        return _norm(x, 0.95)
    if name.startswith("drone"):
        d = 1.8
        n = int(d * SR)
        t = np.arange(n) / SR
        base = {"drone1": 55, "drone2": 73}[name]
        x = sum(np.sin(2 * math.pi * f * t) for f in (base, base * 1.5, base * 2.01)) / 3
        x = x * (0.75 + 0.25 * np.sin(2 * math.pi * 3.2 * t))
        e = np.minimum(1, t / 0.5) * np.minimum(1, (d - t) / 0.7)
        return _norm((x * e).astype(np.float32), 0.6)
    if name.startswith("sparkle"):
        d = 0.7
        x = np.zeros(int(d * SR), np.float32)
        for k in range(7 if name == "sparkle1" else 5):
            at = k * (0.07 if name == "sparkle1" else 0.1)
            f = float(rnd.uniform(2200, 4200))
            y = _tone(f, 0.2, 0.05) * _env(int(0.2 * SR), 0.002)
            s = int(at * SR)
            x[s:s + len(y)] += y[: len(x) - s]
        return _norm(x, 0.45)
    if name == "chime":                                    # ấm áp, cảm động
        d = 1.4
        x = np.zeros(int(d * SR), np.float32)
        for k, f in enumerate((523, 659, 784, 1046)):
            s = int(k * 0.12 * SR)
            y = _tone(f, d - k * 0.12, 0.5) * _env(int((d - k * 0.12) * SR), 0.004)
            x[s:s + len(y)] += y
        return _norm(x, 0.45)
    if name == "scratch":                                  # dừng hình kiểu hài
        d = 0.35
        n = int(d * SR)
        u = np.linspace(0, 1, n, dtype=np.float32)
        f = (400 + 1600 * np.abs(np.sin(u * math.pi * 3))).astype(np.float32)
        x = _lowpass(noise(d), f) + 0.4 * _tone(f * 0.5, d, 1.0, "sq")
        return _norm(x * (1 - u), 0.6)
    raise KeyError(name)


def sound(name: str) -> np.ndarray:
    if name not in _CACHE:
        _CACHE[name] = _make(name)
    return _CACHE[name]


# độ to từng loại so với giọng (giọng đỉnh 0.8)
GAIN = {"whoosh": 0.32, "swish": 0.22, "pop": 0.35, "boing": 0.3, "blip": 0.3, "impact": 0.45, "thud": 0.4,
        "sting": 0.42, "ding": 0.3, "buzz": 0.3, "heartbeat": 0.5, "drone": 0.22, "sparkle": 0.25,
        "chime": 0.25, "scratch": 0.3}


def gain_of(name: str) -> float:
    for k, v in GAIN.items():
        if name.startswith(k):
            return v
    return 0.3


# ---------------------------------------------------------------- kế hoạch edit

SHOCK = {"shocked", "scared", "panic", "desperate"}
ANGER = {"angry", "glare"}
FUNNY = {"cringe", "deadpan", "disgusted", "smirk"}
HAPPY = {"happy", "laughing", "relieved"}
SAD = {"sad", "crying", "tired", "worried"}

BIG_TRANS = ("whip_left", "whip_right", "zoom", "circle", "dip_black", "fade", "slide_up", "blur")
SMALL_TRANS = ("cut", "cut", "cut", "fade", "zoom")
TRANS_DUR = {"cut": 0.0, "fade": 0.28, "whip_left": 0.26, "whip_right": 0.26, "zoom": 0.3, "circle": 0.42,
             "dip_black": 0.5, "slide_up": 0.3, "blur": 0.34, "flash": 0.24, "fade_in": 0.6}


def _pick(rnd: random.Random, pool, last: str = "", recent: tuple = ()) -> str:
    """Chọn ngẫu nhiên trong pool nhưng tránh lặp cái vừa dùng."""
    opts = [p for p in pool if p != last and p not in recent] or [p for p in pool if p != last] or list(pool)
    return rnd.choice(opts)


def plan(st: dict, rows: list[dict]) -> list[dict]:
    """Mỗi cảnh: {"trans": kiểu chuyển cảnh vào cảnh này, "tdur": giây, "emph": hiệu ứng nhấn,
    "sfx": [(giây tính từ đầu cảnh, tên tiếng)]}."""
    seed = int(st.get("edit_seed") or 0)
    on_fx = st.get("auto_fx", True) is not False
    on_sfx = st.get("sfx", True) is not False
    out = []
    last_t, last_e, recent_s = "", "", []
    since_sfx = 9
    for i, r in enumerate(rows):
        s = r["shot"]
        rnd = random.Random(zlib.crc32(f"{seed}:{s.get('id')}:{i}".encode()))
        prev = rows[i - 1]["shot"] if i else None
        expr = s.get("expr") or "neutral"
        typ = s.get("type")
        trans, emph, sfx = "cut", "", []

        def add(name_pool, at=0.0, force=False):
            nonlocal since_sfx
            if not on_sfx:
                return
            if not force and since_sfx < 1 and rnd.random() < 0.6:   # không dày quá
                return
            nm = _pick(rnd, name_pool, recent=tuple(recent_s[-2:]))
            sfx.append((at, nm))
            recent_s.append(nm)
            since_sfx = -1

        place_change = prev is not None and (prev.get("place") != s.get("place") or prev.get("type") == "black")
        if i == 0:
            trans = "fade_in"
        elif typ == "black":
            trans = "dip_black"
            add(("drone1", "drone2", "heartbeat"), 0.05, True)
        elif typ == "phone":
            trans = _pick(rnd, ("zoom", "slide_up", "whip_left", "whip_right"), last_t)
            add(("ding1", "ding2", "ding3", "buzz"), 0.12, True)
        elif place_change:
            trans = _pick(rnd, BIG_TRANS, last_t)
            if trans in ("whip_left", "whip_right", "slide_up", "zoom"):
                add(("whoosh1", "whoosh2", "whoosh3", "whoosh4"), 0.0, True)
            elif trans in ("circle", "blur") and rnd.random() < 0.6:
                add(("swish1", "swish2"), 0.0)
        else:
            trans = rnd.choice(SMALL_TRANS)
            if trans == "zoom" and rnd.random() < 0.5:
                add(("swish1", "swish2"), 0.0)

        if expr in SHOCK:
            emph = _pick(rnd, ("flash", "punch", "shake", "speedlines"), last_e)
            add(("impact1", "impact2", "sting") if expr != "scared" else ("heartbeat", "sting", "drone1"), 0.02, True)
        elif expr in ANGER:
            emph = _pick(rnd, ("vignette_red", "punch", "shake", "speedlines"), last_e)
            add(("thud", "impact2"), 0.02)
        elif expr in FUNNY:
            if rnd.random() < 0.6:
                emph = _pick(rnd, ("freeze_zoom", "punch", ""), last_e)
                add(("boing", "blip", "scratch", "pop3"), 0.05)
        elif expr in HAPPY:
            if rnd.random() < 0.55:
                emph = _pick(rnd, ("glow", "bounce"), last_e)
                add(("sparkle1", "sparkle2", "chime"), 0.05)
        elif expr in SAD:
            if rnd.random() < 0.5:
                emph = "vignette_dark"
                if expr == "crying" and rnd.random() < 0.5:
                    add(("chime",), 0.1)
        if s.get("choice"):
            add(("pop1", "pop2"), 0.05, True)
            add(("pop2", "pop3"), 0.2, True)
        if s.get("camera") == "shake" and not emph:
            emph = "shake"
        if not on_fx:
            trans = "fade_in" if i == 0 else "cut"
            emph = ""
        tdur = min(TRANS_DUR.get(trans, 0.0), max(0.0, r["dur"] * 0.35)) if trans != "fade_in" else 0.6
        out.append({"trans": trans, "tdur": tdur, "emph": emph, "sfx": sfx})
        last_t = trans if trans not in ("cut",) else last_t
        last_e = emph or last_e
        since_sfx += 1
    return out


def sfx_track(edits: list[dict], rows: list[dict], n: int, sr: int = SR) -> np.ndarray:
    mix = np.zeros(n, np.float32)
    for e, r in zip(edits, rows):
        for at, nm in e["sfx"]:
            y = sound(nm) * gain_of(nm)
            k = int((r["start"] + at) * sr)
            if k >= n:
                continue
            mix[k:k + len(y)] += y[: n - k]
    return mix


# ---------------------------------------------------------------- hình

def _ease(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def _shift(arr: np.ndarray, dx: int, dy: int = 0) -> np.ndarray:
    out = np.zeros_like(arr)
    H, W = arr.shape[:2]
    xs0, xd0 = (0, dx) if dx >= 0 else (-dx, 0)
    ys0, yd0 = (0, dy) if dy >= 0 else (-dy, 0)
    w, h = W - abs(dx), H - abs(dy)
    if w > 0 and h > 0:
        out[yd0:yd0 + h, xd0:xd0 + w] = arr[ys0:ys0 + h, xs0:xs0 + w]
    return out


def _zoom(arr: np.ndarray, z: float, cx: float = 0.5, cy: float = 0.5) -> np.ndarray:
    import cv2
    if abs(z - 1.0) < 1e-3:
        return arr
    H, W = arr.shape[:2]
    M = np.float32([[z, 0, W * cx - z * W * cx], [0, z, H * cy - z * H * cy]])
    return cv2.warpAffine(np.ascontiguousarray(arr), M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def _mix(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    return (a.astype(np.float32) * (1 - k) + b.astype(np.float32) * k).astype(np.uint8)


def transition(kind: str, a: np.ndarray | None, b: np.ndarray, lt: float, tdur: float) -> np.ndarray:
    """Khung ở giây lt của cảnh mới trong lúc chuyển cảnh: a = khung cuối cảnh trước, b = cảnh mới."""
    import cv2
    if kind == "fade_in":
        return _mix(np.zeros_like(b), b, _ease(lt / max(tdur, 1e-3)))
    if a is None or kind == "cut" or tdur <= 0 or lt >= tdur:
        return b
    u = _ease(lt / tdur)
    H, W = b.shape[:2]
    if kind == "fade":
        return _mix(a, b, u)
    if kind == "dip_black":
        blk = np.zeros_like(b)
        return _mix(a, blk, u * 2) if u < 0.5 else _mix(blk, b, (u - 0.5) * 2)
    if kind in ("whip_left", "whip_right"):
        sgn = -1 if kind == "whip_left" else 1
        off = int(u * W)
        fr = _shift(a, sgn * off)
        bb = _shift(b, sgn * (off - W))
        mask = np.zeros((H, W, 1), np.float32)
        edge = W - off if sgn < 0 else off
        if sgn < 0:
            mask[:, edge:] = 1
        else:
            mask[:, :edge] = 1
        fr = (fr * (1 - mask) + bb * mask).astype(np.uint8)
        k = int(10 + 70 * math.sin(math.pi * u))                  # nhoè chuyển động
        return cv2.blur(fr, (k, 1))
    if kind == "slide_up":
        off = int(u * H)
        fr = _shift(a, 0, -off)
        fr[H - off:] = b[:off] if off else fr[H - off:]
        return fr
    if kind == "zoom":                                  # phóng vào cảnh cũ rồi lùi ra ở cảnh mới
        if u < 0.5:
            za = _zoom(a, 1 + 0.5 * u)
            return za if u < 0.35 else _mix(za, _zoom(b, 1.25), (u - 0.35) / 0.15)
        return _zoom(b, 1.25 - 0.25 * (u - 0.5) * 2)
    if kind == "circle":
        r = int(u * math.hypot(W, H) / 2)
        m = np.zeros((H, W), np.uint8)
        cv2.circle(m, (W // 2, H // 2), max(1, r), 255, -1, cv2.LINE_AA)
        m = (m.astype(np.float32) / 255)[..., None]
        ring = (a * (1 - m) + b * m).astype(np.uint8)
        cv2.circle(ring, (W // 2, H // 2), max(1, r), (255, 255, 255), max(2, W // 300), cv2.LINE_AA)
        return ring
    if kind == "blur":
        k = int(1 + 40 * math.sin(math.pi * u)) | 1
        src = a if u < 0.5 else b
        return cv2.GaussianBlur(src, (k, k), 0)
    return b


_LINES: dict = {}


def emphasis(kind: str, arr: np.ndarray, lt: float, dur: float, seed: int = 0) -> np.ndarray:
    """Hiệu ứng nhấn đầu cảnh (sốc, giận, hài, vui, buồn)."""
    import cv2
    if not kind:
        return arr
    H, W = arr.shape[:2]
    if kind == "flash":
        if lt < 0.22:
            return _mix(arr, np.full_like(arr, 255), 0.85 * (1 - lt / 0.22))
        return arr
    if kind == "punch":
        if lt < 0.3:
            return _zoom(arr, 1.0 + 0.14 * (1 - _ease(lt / 0.3)), 0.5, 0.42)
        return arr
    if kind == "shake":
        if lt < 0.5:
            a = (1 - lt / 0.5)
            dx, dy = int(math.sin(lt * 70) * W * 0.014 * a), int(math.cos(lt * 53) * H * 0.012 * a)
            M = np.float32([[1.05, 0, W * 0.5 - 1.05 * W * 0.5 + dx], [0, 1.05, H * 0.5 - 1.05 * H * 0.5 + dy]])
            return cv2.warpAffine(np.ascontiguousarray(arr), M, (W, H), flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_REFLECT)
        return arr
    if kind == "speedlines":
        if lt > 0.7:
            return arr
        key = (W, H, seed % 4)
        if key not in _LINES:
            rnd = np.random.default_rng(seed % 4)
            m = np.zeros((H, W), np.uint8)
            cx, cy = W / 2, H * 0.45
            R = math.hypot(W, H) / 2
            for _ in range(90):
                ang = rnd.uniform(0, 2 * math.pi)
                r0 = R * rnd.uniform(0.55, 0.8)
                p0 = (int(cx + math.cos(ang) * r0), int(cy + math.sin(ang) * r0))
                p1 = (int(cx + math.cos(ang) * R * 1.1), int(cy + math.sin(ang) * R * 1.1))
                cv2.line(m, p0, p1, 255, int(rnd.uniform(2, 7) * W / 1920 + 1), cv2.LINE_AA)
            _LINES[key] = (m.astype(np.float32) / 255)[..., None]
        k = 0.9 * (1 - _ease(lt / 0.7))
        m = _LINES[key] * k
        return (arr * (1 - m) + 255 * m).astype(np.uint8)
    if kind in ("vignette_red", "vignette_dark"):
        key = ("v", W, H)
        if key not in _LINES:
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
            _LINES[key] = np.clip((d - 0.55) / 0.6, 0, 1)[..., None]
        m = _LINES[key]
        if kind == "vignette_red":
            k = 0.55 + 0.2 * math.sin(lt * 7)
            col = np.array((150, 10, 10), np.float32)
        else:
            k = 0.6 * min(1.0, lt / 0.6)
            col = np.array((10, 10, 25), np.float32)
        mm = m * k
        return (arr * (1 - mm) + col * mm).astype(np.uint8)
    if kind == "freeze_zoom":                             # hài: dừng hình, phóng vào mặt
        if 0.15 < lt < 0.9:
            return _zoom(arr, 1.0 + 0.18 * _ease((lt - 0.15) / 0.2), 0.5, 0.4)
        return arr
    if kind == "glow":
        k = 0.12 * math.sin(math.pi * min(1.0, lt / 0.8))
        if k <= 0:
            return arr
        soft = cv2.GaussianBlur(arr, (0, 0), W / 90)
        return np.clip(arr.astype(np.float32) + soft.astype(np.float32) * k, 0, 255).astype(np.uint8)
    if kind == "bounce":
        if lt < 0.45:
            return _zoom(arr, 1.0 + 0.05 * abs(math.sin(lt * 14)) * (1 - lt / 0.45), 0.5, 0.6)
        return arr
    return arr


def soft_limit(x: np.ndarray, knee: float = 0.85) -> np.ndarray:
    """Chặn mềm đỉnh tiếng (tiếng động chồng lên giọng không bị rè)."""
    a = np.abs(x)
    over = a > knee
    if not over.any():
        return x
    y = x.copy()
    y[over] = np.sign(x[over]) * (knee + (1 - knee) * np.tanh((a[over] - knee) / (1 - knee)))
    return y
