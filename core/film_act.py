# -*- coding: utf-8 -*-
"""Thư viện hành động cho nhân vật con nhộng có tay chân (dùng chung cho chế độ
Kể chuyện và Phim).

pose(act, t, seed, ...) trả về tư thế (góc tay chân, nghiêng người, nhún...) ở
giây t của hành động. "idle" không đứng im: cứ vài giây đổi một động tác nhỏ
(nhìn quanh, chắp tay sau lưng, gãi đầu, chống cằm, đổi chân...), chuyển mượt.
Khi đang nói, tay vung theo nhịp nói.
"""
from __future__ import annotations

import math
import random

# tên -> (nhãn tiếng Việt, biểu cảm mặc định)
ACTIONS: dict[str, tuple[str, str]] = {
    "idle": ("Đứng (luôn cử động nhẹ)", "neutral"),
    "talk": ("Nói, vung tay theo lời", "neutral"),
    "walk": ("Đi bộ", "neutral"),
    "run": ("Chạy", "neutral"),
    "wave": ("Vẫy tay", "happy"),
    "point": ("Chỉ tay", "neutral"),
    "hands_up": ("Giơ tay hoảng hốt", "shocked"),
    "cry": ("Ôm mặt khóc", "cry"),
    "laugh": ("Cười ôm bụng", "happy"),
    "happy": ("Vui, đung đưa tay", "happy"),
    "angry": ("Giận, nắm tay dậm chân", "angry"),
    "facepalm": ("Đập tay lên trán", "worried"),
    "scratch_head": ("Gãi đầu", "worried"),
    "think": ("Chống cằm suy nghĩ", "think"),
    "cross_arms": ("Khoanh tay", "sly"),
    "hands_hips": ("Chống nạnh", "angry"),
    "bow": ("Cúi chào", "neutral"),
    "nod": ("Gật đầu", "neutral"),
    "shake_head": ("Lắc đầu", "sad"),
    "clap": ("Vỗ tay", "happy"),
    "hug": ("Dang tay ôm", "happy"),
    "give": ("Đưa đồ", "neutral"),
    "eat": ("Ăn", "happy"),
    "drink": ("Uống", "neutral"),
    "pat": ("Xoa đầu, vỗ về", "happy"),
    "beg": ("Chắp tay van xin", "sad"),
    "jump": ("Nhảy cẫng lên mừng", "happy"),
    "tremble": ("Run sợ", "worried"),
    "sad": ("Buồn rũ, cúi đầu", "sad"),
    "work": ("Làm việc (cuốc, quét...)", "neutral"),
    "sit": ("Ngồi", "neutral"),
    "sleep": ("Ngủ gật", "sleep"),
    "lie": ("Nằm (ốm, chết)", "sleep"),
}

# tên hành động cũ của chế độ Kể chuyện
ALIASES = {"hop": "jump", "shocked": "hands_up", "worried": "scratch_head", "shake": "shake_head",
           "sly": "cross_arms", "walk_in": "walk", "walk_out": "walk"}

REST = [(8.0, 4.0), (8.0, 4.0)]
STAND = [(0.0, 0.0), (0.0, 0.0)]


def norm(act: str) -> str:
    a = ALIASES.get(act, act)
    return a if a in ACTIONS else "idle"


def _s(x):
    return math.sin(x)


def _ease(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def _base(t, seed):
    ph = seed * 0.37
    return {"arms": [(8 + 2 * _s(t * 1.7 + ph), 4), (8 + 2 * _s(t * 1.5 + ph + 1), 4)],
            "legs": [(0, 0), (0, 0)], "lean": 0.0, "head": 0.0, "bob": 0.0,
            "sy": 1.0 + 0.012 * _s(2 * math.pi * t / 2.6 + ph), "rot": 0.0, "sit": 0.0}


def lerp(p: dict, q: dict, u: float) -> dict:
    """Trộn hai tư thế (u 0 -> p, 1 -> q) để chuyển động tác mượt."""
    u = _ease(u)
    out = dict(q)
    for k in ("lean", "head", "bob", "sy", "rot", "sit"):
        out[k] = p.get(k, 0.0 if k != "sy" else 1.0) * (1 - u) + q.get(k, 0.0 if k != "sy" else 1.0) * u
    for k in ("arms", "legs"):
        a, b = p.get(k) or STAND, q.get(k) or STAND
        out[k] = [(x0 * (1 - u) + x1 * u, y0 * (1 - u) + y1 * u) for (x0, y0), (x1, y1) in zip(a, b)]
    if u < 0.5:
        out["prop"] = p.get("prop", q.get("prop"))
    return out


# ------------------------------------------------------------ động tác nhỏ khi đứng

_IDLE = ["rest", "behind", "look_l", "look_r", "chin", "scratch", "shift", "rest", "hands_front"]


def _idle_micro(name, t, seed):
    p = _base(t, seed)
    if name == "behind":                       # chắp tay sau lưng
        p["arms"] = [(-28, 10), (-28, 10)]
        p["lean"] = -2
    elif name in ("look_l", "look_r"):
        p["head"] = 7 if name == "look_r" else -7
        p["look_shift"] = 0.6 if name == "look_r" else -0.6
    elif name == "chin":
        p["arms"] = [(150, 50), (60, 70)]
        p["head"] = 4
    elif name == "scratch":
        p["arms"] = [(165 + 6 * _s(t * 14), 35), (8, 4)]
        p["head"] = -4
    elif name == "shift":
        p["lean"] = 3 * _s(t * 0.9)
        p["legs"] = [(4, 0), (-4, 6)]
    elif name == "hands_front":                # đan tay trước bụng
        p["arms"] = [(38, 60), (38, 60)]
    return p


def idle(t, seed):
    """Đứng nhưng không đơ: mỗi 2.5–4.5 giây đổi động tác nhỏ."""
    rng = random.Random(seed)
    seg_t, acc, i = [], 0.0, 0
    while acc <= t + 5:
        d = rng.uniform(2.5, 4.5)
        seg_t.append((acc, d, rng.choice(_IDLE) if i else "rest"))
        acc += d
        i += 1
    for k, (s0, d, name) in enumerate(seg_t):
        if s0 <= t < s0 + d:
            cur = _idle_micro(name, t, seed)
            if t - s0 < 0.45 and k:
                prev = _idle_micro(seg_t[k - 1][2], t, seed)
                return lerp(prev, cur, (t - s0) / 0.45)
            return cur
    return _base(t, seed)


def talk(t, seed, base=None):
    """Vung tay theo nhịp nói (đổi động tác mỗi ~0.7 giây)."""
    p = dict(base or _base(t, seed))
    k = int(t / 0.7)
    rng = random.Random(seed * 131 + k)
    rng2 = random.Random(seed * 131 + k + 1)
    gest = [(rng.uniform(40, 95), rng.uniform(20, 60)), (rng.uniform(8, 50), rng.uniform(5, 40))]
    nxt = [(rng2.uniform(40, 95), rng2.uniform(20, 60)), (rng2.uniform(8, 50), rng2.uniform(5, 40))]
    u = _ease((t % 0.7) / 0.7)
    p["arms"] = [(a0 * (1 - u) + a1 * u, e0 * (1 - u) + e1 * u) for (a0, e0), (a1, e1) in zip(gest, nxt)]
    p["head"] = 3 * _s(t * 3.1)
    p["lean"] = 2 + 1.5 * _s(t * 1.3)
    return p


def walk_cycle(dist, t, run=False):
    """Chân bước theo quãng đường đã đi (không trượt)."""
    stride = 0.55 if run else 0.32         # đơn vị: phần chiều cao T
    ph = dist / stride * math.pi
    amp = 38 if run else 26
    s = _s(ph)
    p = {"arms": [(-amp * 0.9 * s, 20 + (25 if run else 8)), (amp * 0.9 * s, 20 + (25 if run else 8))],
         "legs": [(amp * s, 10 + 30 * max(0.0, -s)), (-amp * s, 10 + 30 * max(0.0, s))],
         "lean": 9 if run else 3, "head": 0.0, "bob": (0.05 if run else 0.025) * abs(_s(ph)),
         "sy": 1.0, "rot": 0.0, "sit": 0.0}
    return p


def pose(act: str, t: float, seed: int = 0, dur: float = 3.0, speaking: bool = False,
         posture: str = "stand") -> dict:
    """Tư thế của hành động `act` ở giây t (tính từ lúc bắt đầu hành động)."""
    act = norm(act)
    p = _base(t, seed)
    w = 2 * math.pi
    if act == "idle":
        p = idle(t, seed)
    elif act == "talk":
        p = talk(t, seed)
    elif act == "wave":
        p["arms"] = [(125 + 18 * _s(w * t * 1.6), 25 + 15 * _s(w * t * 1.6)), (8, 4)]
    elif act == "point":
        p["arms"] = [(95, -5), (10, 6)]
        p["lean"] = 4
    elif act == "hands_up":
        j = _ease(min(1.0, t / 0.25))
        p["arms"] = [(140 * j + 8, 30 * j), (140 * j + 8, 30 * j)]
        p["bob"] = 0.06 * math.sin(math.pi * min(1.0, t / 0.4)) if t < 0.4 else 0.0
        p["lean"] = -6
        p["legs"] = [(4, 0), (-4, 0)]
    elif act == "cry":
        p["arms"] = [(138, 62), (138, 62)]
        p["head"] = -6 + 2 * _s(w * t * 1.8)
        p["sy"] = 1 + 0.02 * max(0.0, _s(w * t / 1.1))
        p["lean"] = 5
    elif act == "laugh":
        p["arms"] = [(30, 70), (30, 70)]
        p["bob"] = 0.02 * abs(_s(w * t * 2.2))
        p["lean"] = -5 + 4 * _s(w * t * 1.1)
        p["head"] = -5
    elif act == "happy":
        p["arms"] = [(30 + 25 * _s(w * t * 1.2), 20), (30 - 25 * _s(w * t * 1.2), 20)]
        p["bob"] = 0.03 * abs(_s(w * t * 1.2))
    elif act == "angry":
        burst = (t % 2.0) < 0.8
        p["arms"] = [(55 + (15 * _s(w * t * 4) if burst else 0), 70), (40, 75)]
        p["legs"] = [(10 * abs(_s(w * t * 3)) if burst else 0, 0), (0, 0)]
        p["bob"] = 0.02 * abs(_s(w * t * 3)) if burst else 0.0
        p["lean"] = 7
    elif act == "facepalm":
        u = min(1.0, t / 0.35)
        p["arms"] = [(8 + 150 * _ease(u), 45 * _ease(u)), (10, 6)]
        p["head"] = -8 * _ease(u)
        p["lean"] = 6 * _ease(u)
    elif act == "scratch_head":
        p["arms"] = [(165 + 8 * _s(w * t * 3), 38), (8, 4)]
        p["head"] = -5
    elif act == "think":
        p["arms"] = [(150, 50), (60, 72)]
        p["head"] = 5 + 2 * _s(t)
    elif act == "cross_arms":
        p["arms"] = [(62, 82), (62, 82)]
        p["lean"] = -3
    elif act == "hands_hips":
        p["arms"] = [(-35, 95), (-35, 95)]
        p["lean"] = -2
    elif act == "bow":
        u = math.sin(math.pi * min(1.0, t / max(0.8, min(dur, 1.6))))
        p["lean"] = 24 * u
        p["head"] = 8 * u
        p["arms"] = [(10, 0), (10, 0)]
    elif act == "nod":
        p["head"] = 9 * max(0.0, _s(w * t * 1.4)) if (t % 2.4) < 1.4 else 0
        p["arms"] = [(38, 60), (38, 60)]
    elif act == "shake_head":
        p["head"] = 7 * _s(w * t * 2.2) if (t % 2.4) < 1.3 else 0
        p["arms"] = [(12, 6), (12, 6)]
    elif act == "clap":
        c = abs(_s(w * t * 2.5))
        p["arms"] = [(75, 40 + 25 * c), (75, 40 + 25 * c)]
        p["bob"] = 0.015 * c
    elif act == "hug":
        p["arms"] = [(88, 25), (88, 25)]
        p["lean"] = 6
    elif act == "give":
        u = _ease(min(1.0, t / 0.6))
        p["arms"] = [(15 + 70 * u, 10 * (1 - u)), (10, 6)]
        p["lean"] = 5 * u
    elif act == "eat":
        k = (t % 1.4) / 1.4
        lift = math.sin(math.pi * k)
        p["arms"] = [(40, 40), (60 + 75 * lift, 40 + 30 * lift)]
        p["prop_default"] = ("bowl", 0)
    elif act == "drink":
        lift = _ease(min(1.0, t / 0.6)) * (1.0 if (t % 3.0) < 2.0 else 0.4)
        p["arms"] = [(60 + 70 * lift, 40 + 30 * lift), (10, 6)]
        p["head"] = -6 * lift
        p["prop_default"] = ("cup", 0)
    elif act == "pat":
        p["arms"] = [(70, 35 + 10 * _s(w * t * 2)), (10, 6)]
        p["lean"] = 10
    elif act == "beg":
        p["arms"] = [(75, 75), (75, 75)]
        p["lean"] = 9 + 3 * _s(w * t)
        p["head"] = 4
    elif act == "jump":
        k = (t % 0.9) / 0.9
        up = math.sin(math.pi * k) if (t % 2.7) < 1.8 else 0.0
        p["bob"] = 0.13 * up
        p["arms"] = [(150 * up + 20, 20), (150 * up + 20, 20)]
        p["legs"] = [(15 * up, 30 * up), (-10 * up, 35 * up)]
        p["sy"] = 1 + 0.04 * up
    elif act == "tremble":
        p["arms"] = [(40, 80), (40, 80)]
        p["lean"] = -4 + 1.5 * _s(w * t * 11)
        p["sy"] = 0.97
    elif act == "sad":
        p["arms"] = [(4, 0), (4, 0)]
        p["head"] = 9
        p["lean"] = 5
        p["sy"] = 0.985 + 0.006 * _s(w * t / 3.2)
    elif act == "work":
        k = (t % 1.2) / 1.2
        sw = math.sin(math.pi * k)
        p["arms"] = [(40 + 100 * sw, 20), (30 + 90 * sw, 30)]
        p["lean"] = 6 + 10 * (1 - sw)
        p["prop_default"] = ("stick", 0)
    elif act == "sleep":
        p["head"] = 12 + 2 * _s(w * t / 3.5)
        p["arms"] = [(30, 50), (30, 50)]
        p["sy"] = 1 + 0.02 * _s(w * t / 3.5)
    elif act == "lie":
        p["rot"] = -90.0
        p["bob"] = 0.2                      # nhấc lên cho nằm trên mặt đất
        p["arms"] = [(5, 0), (5, 0)]
        p["sy"] = 1 + 0.01 * _s(w * t / 3.5)
    elif act == "sit":
        p = idle(t, seed)
    if posture == "sit" and act not in ("lie",):
        p["sit"] = 1.0
        if act in ("idle", "sit", "talk", "sad", "sleep"):
            p["arms"] = [(min(a, 60), e) for a, e in p["arms"]] if act != "talk" else p["arms"]
    if speaking and act in ("idle", "sit", "happy", "sad"):
        p = talk(t, seed, p if act != "idle" else None)
        if posture == "sit":
            p["sit"] = 1.0
    p["expr"] = ACTIONS[act][1]
    return p


def animal_pose(act: str, t: float, seed: int = 0, moving: bool = False) -> dict:
    """Chó mèo: nhún, nghiêng, nhảy."""
    act = norm(act)
    w = 2 * math.pi
    p = {"bob": 0.0, "rot": 0.0, "sy": 1 + 0.015 * _s(w * t / 1.8 + seed), "expr": "neutral"}
    if moving:
        p["bob"] = 0.06 * abs(_s(w * t * 2.2))
        p["rot"] = 3 * _s(w * t * 2.2)
    elif act in ("jump", "happy", "wave", "clap", "laugh"):
        p["bob"] = (0.25 if act == "jump" else 0.1) * abs(_s(w * t * 1.3))
        p["expr"] = "happy"
    elif act in ("sad", "cry", "beg"):
        p["sy"] = 0.95
        p["rot"] = -3
        p["expr"] = "cry" if act == "cry" else "sad"
    elif act in ("lie", "sleep"):
        p["sy"] = 0.85 + 0.02 * _s(w * t / 3)
        p["expr"] = "sleep"
    elif act in ("hands_up", "tremble"):
        p["expr"] = "shocked"
        p["rot"] = 2 * _s(w * t * 9)
    elif act == "angry":
        p["expr"] = "angry"
        p["bob"] = 0.03 * abs(_s(w * t * 4))
    else:
        p["rot"] = 2 * _s(w * t * 0.5 + seed)
    return p
