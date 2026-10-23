# -*- coding: utf-8 -*-
"""Chế độ Phim: nhân vật con nhộng có tay chân tự diễn theo kịch bản phim.

Mỗi cảnh (một địa điểm) là một chuỗi nhịp (beat):
  {"t": "narr", "text": ...}                      người kể nối cảnh (ít thôi)
  {"t": "line", "who": id, "text": ..., "act": hành động khi nói, "to": id,
   "react": {id: hành động}}                     nhân vật nói (giọng riêng)
  {"t": "act", "who": id, "act": ..., "to": id | chỗ đứng, "prop": đồ vật}
                                                  hành động không lời
Hành động đặc biệt: walk / run (đi tới "to"), enter (đi vào khung), exit (đi ra),
sit / stand / lie (đổi tư thế, giữ tới khi đổi), give (đưa đồ đang cầm cho "to").

simulate() tính ai ở đâu, làm gì theo thời gian; FilmShot vẽ từng khung: nền
(vẽ tay hoặc 3D), bóng chân, nhân vật, dấu cảm xúc, máy quay tự chọn góc (toàn
cảnh, hai người, cận người nói, lia theo người đi).
"""
from __future__ import annotations

import math
import zlib

import numpy as np

from . import config, doodle, film_act, film_rig, scene_art

SPOTS = {"xa_trai": 0.12, "trai": 0.3, "giua": 0.5, "phai": 0.7, "xa_phai": 0.88,
         "ngoai_trai": -0.2, "ngoai_phai": 1.2}
SPOT_VI = {"xa_trai": "sát mép trái", "trai": "bên trái", "giua": "giữa", "phai": "bên phải",
           "xa_phai": "sát mép phải", "ngoai_trai": "ngoài khung trái",
           "ngoai_phai": "ngoài khung phải"}
SPECIAL = {"walk": "Đi tới", "run": "Chạy tới", "enter": "Đi vào khung", "exit": "Đi ra khỏi khung",
           "stand": "Đứng dậy"}
ACT_DUR = {"give": 2.0, "bow": 1.8, "hug": 2.6, "eat": 3.2, "drink": 2.6, "jump": 2.4,
           "sit": 1.0, "stand": 0.8, "lie": 1.6, "wave": 1.8, "hands_up": 1.6, "cry": 3.2,
           "laugh": 2.4, "nod": 1.4, "shake_head": 1.6, "clap": 1.8, "work": 3.0,
           "sleep": 3.0, "pat": 2.2, "beg": 2.6, "point": 1.8}
WALK = 1.0               # chiều cao T mỗi giây
RUN = 2.4
LEAD_IN = 1.2            # giây toàn cảnh đầu mỗi cảnh
TAIL = 0.7
BG_K = 1.6               # nền vẽ to hơn khung để máy quay phóng vẫn nét


def all_actions() -> dict:
    out = dict(film_act.ACTIONS)
    out.update(SPECIAL)
    return out


def default_dur(act: str) -> float:
    return ACT_DUR.get(act, 2.2)


# ---------------------------------------------------------------- mô phỏng

class Track:
    """Diễn biến của một nhân vật trong cảnh."""

    def __init__(self, cid, x, posture="stand", prop=None):
        self.cid = cid
        self.keys = [(0.0, x)]            # (t, x) – giữ nguyên giữa các lần đi
        self.moves = []                   # (t0, t1, x0, x1, run)
        self.postures = [(0.0, posture)]
        self.props = [(0.0, prop)]
        self.acts = []                    # (t0, t1, act, to)
        self.speak = []                   # (t0, t1, to, path)

    def x_at(self, t):
        for t0, t1, x0, x1, _r in self.moves:
            if t0 <= t <= t1:
                u = (t - t0) / max(1e-6, t1 - t0)
                return x0 + (x1 - x0) * u
        x = self.keys[0][1]
        for tk, xk in self.keys:
            if tk <= t:
                x = xk
        return x

    def moving(self, t):
        for m in self.moves:
            if m[0] <= t <= m[1]:
                return m
        return None

    def last(self, lst, t):
        v = lst[0][1]
        for tk, vk in lst:
            if tk <= t:
                v = vk
        return v

    def act_at(self, t):
        for t0, t1, a, to in self.acts:
            if t0 <= t < t1:
                return a, t - t0, to, t1 - t0
        return None

    def speaking(self, t):
        for s in self.speak:
            if s[0] <= t <= s[1]:
                return s
        return None


def _target_x(to, tracks, who, t, W, T):
    if to in SPOTS:
        return SPOTS[to] * W
    if to in tracks and to != who:
        tx = tracks[to].x_at(t)
        me = tracks[who].x_at(t)
        side = -1 if me < tx else 1
        return tx + side * T * 0.78
    return None


def simulate(scene: dict, chars: dict, W: float, T: float, durs: dict,
             lead: float = LEAD_IN) -> dict:
    """durs: {chỉ số beat: giây âm thanh}. Trả về {"tracks", "beats" (có t0, t1),
    "dur", "shots"}."""
    ids = [c for c in scene.get("chars") or [] if c in chars]
    start = scene.get("start") or {}
    n = len(ids)
    auto = [0.5] if n == 1 else [0.3 + 0.4 * i / max(1, n - 1) for i in range(n)] if n <= 3 else \
        [0.15 + 0.7 * i / (n - 1) for i in range(n)]
    tracks = {}
    for i, cid in enumerate(ids):
        sp = start.get(cid)
        x = SPOTS[sp] * W if sp in SPOTS else auto[i] * W
        posture = "sit" if (scene.get("posture") or {}).get(cid) == "sit" else "stand"
        tracks[cid] = Track(cid, x, posture)
    t = lead
    beats = []
    for i, b in enumerate(scene.get("beats") or []):
        kind = b.get("t")
        who = b.get("who")
        bt = dict(b, i=i, t0=t)
        if kind == "narr":
            d = durs.get(i, 2.5) + 0.4
        elif kind == "line" and who in tracks:
            a = durs.get(i, 2.0)
            d = a + 0.35
            tr = tracks[who]
            act = film_act.norm(b.get("act") or "talk") if b.get("act") not in ("walk", "run") else "talk"
            tr.speak.append((t + 0.15, t + 0.15 + a, b.get("to"), b.get("path")))
            tr.acts.append((t, t + d, act, b.get("to")))
            for rid, ract in (b.get("react") or {}).items():
                if rid in tracks and rid != who:
                    tracks[rid].acts.append((t, t + d, film_act.norm(ract), who))
        elif kind == "act" and who in tracks:
            tr = tracks[who]
            act = b.get("act") or "idle"
            to = b.get("to")
            x0 = tr.x_at(t)
            if b.get("prop"):
                tr.props.append((t, None if b["prop"] == "none" else b["prop"]))
            if act in ("walk", "run", "enter", "exit"):
                if act == "exit":
                    # ra phía không phải băng qua người khác
                    others = [o.x_at(t) for c, o in tracks.items() if c != who and 0 <= o.x_at(t) <= W]
                    ref = sum(others) / len(others) if others else W / 2
                    x1 = SPOTS["ngoai_trai"] * W if x0 < ref else SPOTS["ngoai_phai"] * W
                else:
                    x1 = _target_x(to, tracks, who, t, W, T)
                    if x1 is None:
                        x1 = W / 2
                    if act == "enter" and 0 <= x0 <= W:      # chưa ở ngoài: ra mép gần nhất
                        x0 = SPOTS["ngoai_trai"] * W if x1 < W / 2 else SPOTS["ngoai_phai"] * W
                        tr.keys.append((t, x0))
                run = act == "run"
                d = max(0.8, abs(x1 - x0) / (T * (RUN if run else WALK)))
                tr.moves.append((t, t + d, x0, x1, run))
                tr.keys.append((t + d, x1))
                d += 0.2
            elif act in ("sit", "stand", "lie"):
                d = default_dur(act)
                tr.postures.append((t + d * 0.5, act if act != "stand" else "stand"))
                if act == "lie":
                    tr.acts.append((t, t + d, "lie", None))
            else:
                act = film_act.norm(act)
                walk = 0.0
                if act in ("give", "hug", "pat") and to in tracks:     # tới gần trước
                    x1 = _target_x(to, tracks, who, t, W, T)
                    if x1 is not None and abs(x1 - x0) > T * 0.3:
                        walk = max(0.6, abs(x1 - x0) / (T * WALK))
                        tr.moves.append((t, t + walk, x0, x1, False))
                        tr.keys.append((t + walk, x1))
                d = walk + (float(b.get("dur") or 0) or default_dur(act))
                tr.acts.append((t + walk, t + d, act, to))
                if act == "give" and to in tracks:
                    got = tr.last(tr.props, t) or b.get("prop")
                    tr.props.append((t + d - 0.3, None))
                    if got:
                        tracks[to].props.append((t + d - 0.3, got))
            if b.get("text"):
                d = max(d, durs.get(i, 0) + 0.3)
        else:
            continue
        bt["t1"] = t + d
        beats.append(bt)
        t += d
    total = t + TAIL
    return {"tracks": tracks, "beats": beats, "dur": total, "W": W, "T": T}


# ---------------------------------------------------------------- máy quay

def shots(plan: dict) -> list[dict]:
    """Chọn góc máy cho từng nhịp: toàn cảnh / hai người / cận / lia theo."""
    first = plan["beats"][0]["t0"] if plan["beats"] else plan["dur"]
    out = [{"t0": 0.0, "t1": first, "kind": "wide", "focus": []}]
    run = 0
    for b in plan["beats"]:
        kind, who = b.get("t"), b.get("who")
        if kind == "line":
            to = b.get("to") if b.get("to") in plan["tracks"] else None
            if not to:
                others = [c for c in plan["tracks"] if c != who]
                if others:
                    me = plan["tracks"][who].x_at(b["t0"])
                    to = min(others, key=lambda c: abs(plan["tracks"][c].x_at(b["t0"]) - me))
            pat = run % 3
            run += 1
            if not to:
                out.append({"t0": b["t0"], "t1": b["t1"], "kind": "medium", "focus": [who]})
            elif pat == 0:
                out.append({"t0": b["t0"], "t1": b["t1"], "kind": "medium", "focus": [who, to]})
            else:
                out.append({"t0": b["t0"], "t1": b["t1"], "kind": "close", "focus": [who], "toward": to})
        elif kind == "act":
            run = 0
            if b.get("act") in ("walk", "run", "enter", "exit"):
                out.append({"t0": b["t0"], "t1": b["t1"], "kind": "follow", "focus": [who]})
            else:
                f = [who] + ([b["to"]] if b.get("to") in plan["tracks"] else [])
                out.append({"t0": b["t0"], "t1": b["t1"], "kind": "medium", "focus": f})
        else:
            run = 0
            out.append({"t0": b["t0"], "t1": b["t1"], "kind": "wide", "focus": []})
    out[-1]["t1"] = plan["dur"]
    return out


def camera(plan, shot, t, W, H, floor):
    """(tâm x, tâm y, zoom) của máy quay."""
    T = plan["T"]
    tr = plan["tracks"]
    kind = shot["kind"]
    tt = t if kind == "follow" else shot["t0"] + 0.01
    xs = [tr[c].x_at(tt) for c in shot.get("focus") or [] if c in tr]
    if kind == "wide" or not xs:
        z, cx = 1.0, W / 2
    elif kind == "close":
        cx = xs[0]
        if shot.get("toward") in tr:
            cx += (0.18 * T) * (1 if tr[shot["toward"]].x_at(tt) > xs[0] else -1)
        z = 1.85
    elif kind == "follow":
        cx, z = xs[0], 1.3
    else:
        span = max(xs) - min(xs)
        cx = (max(xs) + min(xs)) / 2
        z = max(1.0, min(1.55, W * 0.82 / (span + T * 1.3)))
    u = (t - shot["t0"]) / max(0.1, shot["t1"] - shot["t0"])
    z *= 1.0 + 0.025 * max(0.0, min(1.0, u))              # đẩy máy rất chậm cho đỡ đơ
    vh = H / z
    cy = floor - 0.36 * vh if z > 1.01 else H / 2
    vw = W / z
    cx = min(max(cx, vw / 2), W - vw / 2)
    cy = min(max(cy, vh / 2), H - vh / 2)
    return cx, cy, z


# ---------------------------------------------------------------- vẽ

_BG: dict = {}


def background(st, scene, pdir, size):
    """Nền to (BG_K lần khung) cho máy quay phóng: 3D nếu có, không thì vẽ tay."""
    from . import story_live
    W, H = size
    big = (int(W * BG_K), int(H * BG_K))
    places = {p["id"]: p for p in st.get("places") or []}
    place = places.get(scene.get("place"))
    time = scene.get("time") if scene.get("time") in scene_art.TIMES else \
        ((place or {}).get("time") or "ngay")
    key = (scene.get("place"), time, big, st.get("bg_mode"))
    if key in _BG:
        return _BG[key], time == "dem"
    img = None
    if st.get("bg_mode") == "ai3d" and pdir is not None and place:
        img = story_live.background3d(pdir, place["id"], time, big)
    if img is None:
        kind = story_live.place_kind(place)
        seed = zlib.crc32(str(scene.get("place") or kind).encode()) % 1000
        img = np.asarray(scene_art.render_scene(kind, time, size=big, seed=seed, art="doodle",
                                                layout_size=big)).copy()
    if len(_BG) > 5:
        _BG.pop(next(iter(_BG)))
    _BG[key] = img
    return img, time == "dem"


class FilmShot:
    """Vẽ một cảnh phim: frame(t) với t tính từ đầu cảnh."""

    def __init__(self, st, scene, plan, size, pdir=None, fps=24):
        import cv2
        self.cv2 = cv2
        self.W, self.H = size
        self.plan = plan
        self.fps = fps
        self.bg, self.night = background(st, scene, pdir, size)
        self.floor = self.H * config.stage_layout(self.W, self.H)["floor"]
        chars = {c["id"]: c for c in st.get("characters") or []}
        self.rigs = {}
        for cid in plan["tracks"]:
            c = chars[cid]
            kit = doodle.clean_kit(c.get("kit") or doodle.kit_from_look(c.get("name", ""), c.get("look", "")))
            seed = zlib.crc32(cid.encode()) % 997
            self.rigs[cid] = (film_rig.Rig(kit, plan["T"], seed) if kit["species"] == "human"
                              else film_rig.AnimalRig(kit, plan["T"], seed), kit, seed)
        self.shots = shots(plan)
        self.env = {}
        for cid, tr in plan["tracks"].items():
            for s in tr.speak:
                if s[3]:
                    from .story_live import envelope
                    self.env[(cid, s[0])] = envelope(s[3], fps)
        self.speakers = {}

    def _shot(self, t):
        for s in self.shots:
            if s["t0"] <= t < s["t1"]:
                return s
        return self.shots[-1]

    def _face(self, cid, t):
        tr = self.plan["tracks"]
        me = tr[cid]
        x = me.x_at(t)
        m = me.moving(t)
        if m:
            return 1 if m[3] > m[2] else -1, 0.7 if m[3] > m[2] else -0.7
        sp = me.speaking(t)
        target = sp[2] if sp and sp[2] in tr else None
        if not target:
            a = me.act_at(t)
            if a and a[2] in tr:
                target = a[2]
        if not target:                       # nghe người đang nói
            for oc, ot in tr.items():
                if oc != cid and ot.speaking(t):
                    target = oc
                    break
        if not target:
            others = [(abs(ot.x_at(t) - x), oc) for oc, ot in tr.items()
                      if oc != cid and -0.1 * self.W < ot.x_at(t) < 1.1 * self.W]
            target = min(others)[1] if others else None
        if not target:
            return (1 if x < self.W / 2 else -1), 0.15 if x < self.W / 2 else -0.15
        d = 1 if tr[target].x_at(t) > x else -1
        return d, 0.65 * d

    def _mouth(self, cid, t):
        sp = self.plan["tracks"][cid].speaking(t)
        if not sp:
            return False
        env = self.env.get((cid, sp[0]))
        if env is not None:
            i = int((t - sp[0]) * self.fps)
            return 0 <= i < len(env) and bool(env[i] > 0.3) and (i // 2) % 3 != 2
        return int(t * 8) % 2 == 0

    def pose(self, cid, t):
        tr = self.plan["tracks"][cid]
        rig, kit, seed = self.rigs[cid]
        x = tr.x_at(t)
        posture = tr.last(tr.postures, t)
        m = tr.moving(t)
        speaking = tr.speaking(t) is not None
        cur = tr.act_at(t)
        act, lt, dur = (cur[0], cur[1], cur[3]) if cur else ("idle", t, 3.0)
        if posture == "lie":
            act = "lie"
        human = kit["species"] == "human"
        if not human:
            p = film_act.animal_pose(act, t, seed, bool(m))
        elif m:
            dist = abs(x - m[2]) / self.plan["T"]
            p = film_act.walk_cycle(dist, t, run=m[4])
            p["expr"] = "neutral"
        else:
            p = film_act.pose(act, lt if cur else t, seed, dur, speaking,
                              posture="sit" if posture == "sit" else "stand")
        d, look = self._face(cid, t)
        per = 3.2 + (seed % 13) / 8.0
        blink = (t + seed / 50.0) % per < 0.13 and p.get("expr") not in ("sleep", "cry", "happy")
        prop = tr.last(tr.props, t)
        p.update(x=x, y=self.floor, dir=d, look=look, mouth=self._mouth(cid, t), blink=blink)
        if prop:
            p["prop"] = (prop, 0)
        elif p.get("prop_default"):
            p["prop"] = p["prop_default"]
        p["_act"] = act
        return p

    def frame(self, t: float) -> np.ndarray:
        cv2 = self.cv2
        W, H = self.W, self.H
        cx, cy, z = camera(self.plan, self._shot(t), t, W, H, self.floor)
        # nền: thế giới -> màn hình = z * (w - c) + tâm khung; ảnh nền to BG_K lần
        k = z / BG_K
        M = np.float32([[k, 0, W / 2 - z * cx], [0, k, H / 2 - z * cy]])
        frame = cv2.warpAffine(self.bg, M, (W, H), flags=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)
        cam = np.array([[z, 0, W / 2 - z * cx], [0, z, H / 2 - z * cy]], dtype=np.float64)
        poses = {cid: self.pose(cid, t) for cid in self.plan["tracks"]}
        order = sorted(poses, key=lambda c: (poses[c]["_act"] == "lie", poses[c]["x"]))
        T = self.plan["T"]
        for cid in order:                                    # bóng chân
            p = poses[cid]
            if p["_act"] == "lie" or not (-0.2 * W < p["x"] < 1.2 * W):
                continue
            kit = self.rigs[cid][1]
            w = T * (0.42 if kit["species"] == "human" else 0.5 * doodle.char_height(kit, 1.0)) * z
            sx, sy = cam[0, 0] * p["x"] + cam[0, 2], cam[1, 1] * p["y"] + cam[1, 2]
            self._shadow(frame, sx, sy, w)
        night = (0.78, 0.8, 0.95) if self.night else None
        for cid in order:
            p = poses[cid]
            if not (-0.25 * W < p["x"] < 1.25 * W):
                continue
            rig = self.rigs[cid][0]
            info = rig.draw(frame, p, cam, z, night)
            hx, hy = info["head"]
            film_rig.marks(frame, p["_act"], t, (hx, hy + 0.08 * info["r"], info["r"]), T * z,
                           p.get("dir", 1))
        return frame

    def _shadow(self, frame, x, y, w):
        cv2 = self.cv2
        rx, ry = int(w * 0.5), max(2, int(w * 0.09))
        x0, y0 = max(0, int(x) - rx - 2), max(0, int(y) - ry - 2)
        x1, y1 = min(frame.shape[1], int(x) + rx + 2), min(frame.shape[0], int(y) + ry + 2)
        if x1 <= x0 or y1 <= y0:
            return
        reg = frame[y0:y1, x0:x1]
        m = np.zeros(reg.shape[:2], np.uint8)
        cv2.ellipse(m, (int(x) - x0, int(y) - y0), (rx, ry), 0, 0, 360, 70, -1, cv2.LINE_AA)
        inv = 255 - m
        frame[y0:y1, x0:x1] = cv2.multiply(reg, cv2.merge([inv, inv, inv]), scale=1 / 255.0)


def char_T(size) -> float:
    W, H = size
    lay = config.stage_layout(W, H)
    return H * lay["height"][0] * 0.66


def preview(st, scene, size, pdir=None, at: float | None = None):
    from PIL import Image
    chars = {c["id"]: c for c in st.get("characters") or []}
    plan = simulate(scene, chars, size[0], char_T(size), {})
    shot = FilmShot(st, scene, plan, size, pdir)
    t = at if at is not None else min(plan["dur"] * 0.4, LEAD_IN + 1.5)
    return Image.fromarray(shot.frame(t))
