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
# đồ đạc trong cảnh: (nhãn, rộng theo T, cao mặt ngồi / nằm theo T, ngồi được, nằm được)
FURNITURE = {
    "bed": ("Giường tre / phản", 1.4, 0.17, True, True),
    "bench": ("Chõng tre / ghế dài", 1.5, 0.14, True, False),
    "chair": ("Ghế tựa", 0.36, 0.15, True, False),
    "table": ("Bàn gỗ", 0.75, 0.24, False, False),
    "mat": ("Chiếu trải đất", 1.2, 0.0, True, True),
    "stove": ("Bếp lửa (kiềng ba chân)", 0.42, 0.0, False, False),
    "jar": ("Chum nước", 0.32, 0.0, False, False),
}
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
        self.postures = [(0.0, posture, None, None)]     # (t, tư thế, cao mặt ghế, x ghế)
        self.props = [(0.0, prop)]
        self.acts = []                    # (t0, t1, act, to)
        self.speak = []                   # (t0, t1, to, path)
        self.reacts = set()               # thời điểm bắt đầu các phản ứng khi nghe

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

    def posture_at(self, t):
        cur = self.postures[0]
        for p in self.postures:
            if p[0] <= t:
                cur = p
        return cur

    def prev_posture(self, t):
        """Tư thế ngay trước tư thế hiện tại (để chuyển nằm <-> ngồi dậy cho mượt)."""
        k = 0
        for j, p in enumerate(self.postures):
            if p[0] <= t:
                k = j
        return self.postures[k - 1][1] if k > 0 else None

    def act_at(self, t):
        """Hành động đang làm: hành động bắt đầu muộn nhất còn hiệu lực (phản ứng
        ngắn đè lên việc đang làm dở, xong thì làm tiếp)."""
        best = None
        for t0, t1, a, to in self.acts:
            if t0 <= t < t1 and (best is None or t0 >= best[0]):
                best = (t0, t1, a, to)
        if not best:
            return None
        t0, t1, a, to = best
        return a, t - t0, to, t1 - t0

    def speaking(self, t):
        for s in self.speak:
            if s[0] <= t <= s[1]:
                return s
        return None


def _half(chars, cid, T):
    """Nửa bề ngang nhân vật (người / con vật) theo T."""
    kit = (chars.get(cid) or {}).get("kit") or {}
    return T * (0.3 if kit.get("species", "human") == "human" else 0.42)


def _target_x(to, tracks, who, t, W, T, chars=None):
    if to in SPOTS:
        return SPOTS[to] * W
    if to in tracks and to != who:
        tx = tracks[to].x_at(t)
        me = tracks[who].x_at(t)
        side = -1 if me < tx else 1
        gap = (_half(chars or {}, who, T) + _half(chars or {}, to, T) + T * 0.16) if chars else T * 0.78
        return tx + side * gap
    return None


def furniture_layout(scene: dict, W: float, T: float) -> list[dict]:
    """[{item, x, w, h}] theo toạ độ thế giới."""
    out = []
    for f in scene.get("furniture") or []:
        it = f.get("item")
        if it not in FURNITURE:
            continue
        at = f.get("at")
        x = SPOTS[at] * W if at in SPOTS else (float(f["x"]) * W if "x" in f else W / 2)
        _lab, w, h, _s, _l = FURNITURE[it]
        out.append({"item": it, "x": x, "w": w * T, "h": h * T})
    return out


def _arrange(furn, xs, W, T):
    """Đồ đạc nằm trọn trong khung, không chồng lên nhau; bếp, chum, bàn (không ngồi
    được) tránh chỗ nhân vật đứng để không ai ngồi lên lửa, chum không lòi sau lưng."""
    m = 0.03 * W
    for f in furn:
        f["x"] = min(max(f["x"], m + f["w"] / 2), W - m - f["w"] / 2)
    for f in sorted(furn, key=lambda g: FURNITURE[g["item"]][3]) * 2:
        seat = FURNITURE[f["item"]][3]

        def clear(x, f=f, seat=seat):
            gaps = [] if seat else [abs(x - cx) - (f["w"] / 2 + T * 0.45) for cx in xs]
            gaps += [abs(x - g["x"]) - (f["w"] + g["w"]) / 2 - T * 0.05 for g in furn if g is not f]
            return min(gaps) if gaps else 1e9
        if clear(f["x"]) >= 0:
            continue
        lo, hi = m + f["w"] / 2, W - m - f["w"] / 2
        cands = [lo + (hi - lo) * k / 24 for k in range(25)] if hi > lo else [W / 2]
        f["x"] = max(cands, key=lambda x: (min(clear(x), 0.0), -abs(x - f["x"])))
    return furn


def _slots(f, T):
    """Chỗ ngồi trên một món đồ (lệch so với tâm): mỗi người cách nhau 0.72T."""
    if f["item"] == "chair":
        return [0.0]
    n = max(1, round(f["w"] / (T * 0.72)))
    return [(k - (n - 1) / 2) * T * 0.72 for k in range(n)]


def _seat_for(furn, x, T, lie=False):
    """Đồ ngồi / nằm gần chỗ x nhất (trong khoảng 1.2T)."""
    best = None
    for f in furn:
        ok = FURNITURE[f["item"]][4] if lie else FURNITURE[f["item"]][3]
        if ok and abs(f["x"] - x) < T * 1.2 + f["w"] / 2:
            if best is None or abs(f["x"] - x) < abs(best["x"] - x):
                best = f
    return best


PROP_ALIAS = {"bat": "bowl", "bát": "bowl", "bat_com": "bowl", "rice_bowl": "bowl", "chen": "cup",
              "chén": "cup", "coc": "cup", "cốc": "cup", "ly": "cup", "tea": "cup", "teacup": "cup",
              "chen_tra": "cup", "cuoc": "hoe", "cuốc": "hoe", "choi": "broom", "chổi": "broom",
              "riu": "axe", "rìu": "axe", "liem": "sickle", "liềm": "sickle", "quat": "fan",
              "quạt": "fan", "dieu": "pipe", "điếu": "pipe", "dieu_cay": "pipe", "sach": "book",
              "sách": "book", "tien": "money", "tiền": "money", "thu": "letter", "thư": "letter",
              "noi": "pot", "nồi": "pot", "gay": "stick", "gậy": "stick", "den": "lamp", "đèn": "lamp",
              "dao": "knife", "chai": "bottle", "hoa": "flower", "tui": "bag", "túi": "bag",
              "gio": "basket", "giỏ": "basket", "ro": "basket", "rổ": "basket", "don_ganh": "pole"}


def norm_prop(name):
    if not name:
        return name
    n = str(name).strip().lower()
    return PROP_ALIAS.get(n, PROP_ALIAS.get(n.replace(" ", "_"), str(name).strip()))


GAP_TURN = 0.45          # nghỉ giữa hai người nói khác nhau (biết ai nói câu nào)
ANIMAL_LIKE = ("pat", "feed", "hug", "give")


def simulate(scene: dict, chars: dict, W: float, T: float, durs: dict,
             lead: float = LEAD_IN, indoor: bool = True) -> dict:
    """durs: {chỉ số beat: giây âm thanh}. Trả về {"tracks", "beats" (có t0, t1),
    "dur", "shots"}."""
    ids = [c for c in scene.get("chars") or [] if c in chars]
    start = scene.get("start") or {}
    n = len(ids)
    auto = [0.5] if n == 1 else [0.3 + 0.4 * i / max(1, n - 1) for i in range(n)] if n <= 3 else \
        [0.15 + 0.7 * i / (n - 1) for i in range(n)]
    furn = furniture_layout(scene, W, T)
    src = [dict(b, i=k) for k, b in enumerate(scene.get("beats") or [])]
    for b in src:
        if b.get("prop") and b["prop"] != "none":
            b["prop"] = norm_prop(b["prop"])
    species = {c: ((chars.get(c) or {}).get("kit") or {}).get("species", "human") for c in ids}
    # vị trí đầu cảnh; ai ở ngoài khung mà không có nhịp đi vào thì đứng sẵn trong khung
    entering = {b.get("who") for b in src if b.get("t") == "act" and b.get("act") in ("enter", "walk", "run")}
    xs0 = {}
    for i, cid in enumerate(ids):
        sp = start.get(cid)
        x = SPOTS[sp] * W if sp in SPOTS else auto[i] * W
        if not (0 <= x <= W) and cid not in entering:
            x = auto[i] * W
        xs0[cid] = x
    # mọi người đều ở ngoài khung: cho người đầu tiên đi vào ngay, khỏi cảnh trống
    if ids and all(not (0 <= x <= W) for x in xs0.values()):
        k = next((j for j, b in enumerate(src) if b.get("t") == "act" and b.get("act") == "enter"), None)
        if k is not None:
            src.insert(0, src.pop(k))
            lead = min(lead, 0.3 + (lead - LEAD_IN if lead > LEAD_IN else 0.0))
    # nằm / ngồi mà cảnh chưa có giường, chõng: tự kê
    need_lie = [b.get("who") for b in src if b.get("act") == "lie"] + \
        [c for c, p in (scene.get("posture") or {}).items() if p == "lie"]
    if need_lie and not any(FURNITURE[f["item"]][4] for f in furn):
        it = "bed" if indoor else "mat"
        lx = xs0.get(need_lie[0], SPOTS["phai"] * W)
        furn.append({"item": it, "x": lx, "w": FURNITURE[it][1] * T, "h": FURNITURE[it][2] * T,
                     "auto": True})
    _arrange(furn, [x for x in xs0.values() if 0 <= x <= W], W, T)
    tracks = {cid: Track(cid, xs0[cid]) for cid in ids}
    occ: dict = {}                            # (đồ, chỗ) -> người đang ngồi / nằm

    def free_seat(cid):
        for k in [k for k, v in occ.items() if v == cid]:
            del occ[k]

    def take_seat(cid, x, lie):
        """Chỗ ngồi / nằm trống gần nhất: (đồ, x chỗ ngồi) hoặc None."""
        free_seat(cid)
        best = None
        for fi, f in enumerate(furn):
            if not FURNITURE[f["item"]][4 if lie else 3] or (fi, "lie") in occ:
                continue
            if lie:
                if any(k[0] == fi for k in occ):
                    continue
                cand = [(abs(f["x"] - x), fi, "lie", f["x"])]
            else:
                cand = [(abs(f["x"] + o - x), fi, k, f["x"] + o) for k, o in enumerate(_slots(f, T))
                        if (fi, k) not in occ]
            for c in cand:
                if best is None or c[0] < best[0]:
                    best = c
        if best is None and lie:                  # giường đã có người: trải chiếu
            mx = min(max(x, 0.15 * W), 0.85 * W)
            furn.append({"item": "mat", "x": mx, "w": FURNITURE["mat"][1] * T, "h": 0.0, "auto": True})
            best = (0.0, len(furn) - 1, "lie", mx)
        if best is None:
            return None
        occ[(best[1], best[2])] = cid
        return furn[best[1]], best[3]

    def stool_x(x, cid=None, t=0.0):
        """Ngồi ghế đẩu: đừng ngồi lên bếp, chum, bàn hay sát vào người khác."""
        def bad(xx):
            hit = [f["w"] / 2 + T * 0.3 - abs(xx - f["x"]) for f in furn]
            hit += [T * 0.72 - abs(xx - o.x_at(t)) for c, o in tracks.items() if c != cid]
            return max([h for h in hit if h > 0], default=0.0)
        if bad(x) <= 0:
            return min(max(x, T * 0.3), W - T * 0.3)
        cands = [T * 0.3 + (W - T * 0.6) * k / 40 for k in range(41)]
        return min(cands, key=lambda c: (bad(c) > 0, bad(c), abs(c - x)))

    def rise(cid, t):
        """Đang ngồi / nằm mà phải đi: ngồi dậy rồi đứng lên. Trả về số giây trễ."""
        tr = tracks[cid]
        _t, pst, h, sx = tr.postures[-1]
        free_seat(cid)
        if pst == "lie":
            tr.acts = [(a0, min(a1, t) if a == "lie" else a1, a, to) for a0, a1, a, to in tr.acts]
            tr.postures.append((t, "sit", h, sx))
            tr.postures.append((t + 0.9, "stand", None, None))
            if sx is not None:
                tr.keys.append((t + 0.9, sx))
            return 1.1
        if pst == "sit":
            tr.postures.append((t + 0.1, "stand", None, None))
            return 0.4
        return 0.0

    for cid in ids:
        pst = (scene.get("posture") or {}).get(cid)
        if pst not in ("sit", "lie"):
            continue
        got = take_seat(cid, xs0[cid], pst == "lie")
        f, sx = got if got else (None, stool_x(xs0[cid], cid))
        tracks[cid].keys = [(0.0, sx)]
        tracks[cid].postures = [(0.0, pst, f["h"] if f else None, sx)]
        if pst == "lie":
            tracks[cid].acts.append((0.0, 1e9, "lie", None))
    activity: dict = {}                       # việc đang làm dở của từng người
    auto_prop: dict = {}                      # đồ tự cầm theo việc (cuốc khi cuốc đất...)
    sfx: list = []                            # (t, tên, âm lượng)
    floor: list = []                          # đồ đặt dưới đất: (từ lúc, x, tên) — bát cơm cho chó

    def hold(cid, t, act):
        """Việc cần đồ: cầm từ lúc bắt đầu tới khi đổi việc; đổi việc thì bỏ xuống."""
        tr = tracks[cid]
        want = film_act.ACT_PROP.get(act)
        cur = tr.last(tr.props, t)
        cur = None if cur == "none" else cur
        if want and (cur is None or cur == auto_prop.get(cid)):
            if cur != want:
                tr.props.append((t, want))
            auto_prop[cid] = want
        elif not want and cur is not None and cur == auto_prop.get(cid) and act not in ("talk", "idle"):
            tr.props.append((t, None))
            auto_prop.pop(cid, None)

    t = lead
    beats = []
    last_speaker = None
    for i, b in enumerate(src):
        kind = b.get("t")
        who = b.get("who")
        if kind == "line" and who in tracks and last_speaker and last_speaker != who:
            t += GAP_TURN
        bt = dict(b, t0=t)
        if kind == "narr":
            d = durs.get(bt["i"], 2.5) + 0.4
            last_speaker = "_narr"
        elif kind == "line" and who in tracks:
            a = durs.get(bt["i"], 2.0)
            d = a + 0.35
            last_speaker = who
            tr = tracks[who]
            act = film_act.norm(b.get("act") or "talk") if b.get("act") not in ("walk", "run") else "talk"
            tr.speak.append((t + 0.15, t + 0.15 + a, b.get("to"), b.get("path")))
            if not (act == "talk" and activity.get(who)):          # đang làm dở thì vừa làm vừa nói
                tr.acts.append((t, t + d, act, b.get("to")))
                if act in film_act.CONTINUOUS:
                    activity[who] = act
                    hold(who, t, act)
                elif act != "talk":
                    activity.pop(who, None)
            for rid, ract in (b.get("react") or {}).items():
                if rid in tracks and rid != who:
                    tracks[rid].acts.append((t, t + d, film_act.norm(ract), who))
                    tracks[rid].reacts.add(t)
        elif kind == "sfx":
            name = b.get("name") or b.get("act")
            d = float(b.get("dur") or 0.8)
            if name:
                sfx.append((t + 0.05, name, float(b.get("vol") or 0.6)))
        elif kind == "act" and who in tracks:
            tr = tracks[who]
            act = b.get("act") or "idle"
            to = b.get("to")
            activity.pop(who, None)
            if b.get("prop"):
                tr.props.append((t, None if b["prop"] == "none" else b["prop"]))
                auto_prop.pop(who, None)
            if act in ("walk", "run", "enter", "exit"):
                t_go = t + rise(who, t)
                x0 = tr.x_at(t_go)
                if act == "exit":
                    # ra phía không phải băng qua người khác
                    others = [o.x_at(t) for c, o in tracks.items() if c != who and 0 <= o.x_at(t) <= W]
                    ref = sum(others) / len(others) if others else W / 2
                    x1 = SPOTS["ngoai_trai"] * W if x0 < ref else SPOTS["ngoai_phai"] * W
                else:
                    x1 = _target_x(to, tracks, who, t, W, T, chars)
                    if x1 is None:
                        x1 = W / 2
                    elif to in tracks and activity.get(to) in film_act.TOOL_ACTS:   # đứng xa tầm cuốc
                        x1 += (T * 0.45) * (1 if x1 > tracks[to].x_at(t) else -1)
                        x1 = min(max(x1, T * 0.3), W - T * 0.3)
                    if act == "enter" and 0 <= x0 <= W:      # chưa ở ngoài: ra mép gần nhất
                        x0 = SPOTS["ngoai_trai"] * W if x1 < W / 2 else SPOTS["ngoai_phai"] * W
                        tr.keys.append((t_go, x0))
                run = act == "run"
                d = max(0.8, abs(x1 - x0) / (T * (RUN if run else WALK)))
                tr.moves.append((t_go, t_go + d, x0, x1, run))
                tr.keys.append((t_go + d, x1))
                d += 0.2 + (t_go - t)
            elif act in ("sit", "stand", "lie"):
                walk = 0.0
                if act == "stand":
                    walk = rise(who, t)
                    if walk == 0.0:
                        tr.postures.append((t, "stand", None, None))
                    tr.acts.append((t, t + 0.01, "idle", None))
                    d = walk + default_dur(act)
                else:
                    pre = rise(who, t) if tr.postures[-1][1] != "stand" else 0.0
                    x0 = tr.x_at(t + pre)
                    got = take_seat(who, x0, act == "lie")
                    f, sx = got if got else (None, stool_x(x0, who, t))
                    t1 = t + pre
                    if abs(sx - x0) > T * 0.05:
                        walk = max(0.6, abs(sx - x0) / (T * WALK))
                        tr.moves.append((t1, t1 + walk, x0, sx, False))
                    tr.keys.append((t1 + walk, sx))
                    walk += pre
                    d = walk + default_dur(act)
                    if act == "lie":
                        tr.postures.append((t + walk + 0.1, "sit", f["h"] if f else None, sx))
                        tr.postures.append((t + walk + 0.8, "lie", f["h"] if f else None, sx))
                        tr.acts.append((t + walk + 0.8, 1e9, "lie", None))
                        sfx.append((t + walk + 0.9, "thud", 0.3))
                        d += 0.8
                        if tr.last(tr.props, t + walk):                 # nằm thì bỏ đồ xuống
                            tr.props.append((t + walk, None))
                            auto_prop.pop(who, None)
                    else:
                        tr.postures.append((t + walk + (d - walk) * 0.4, "sit", f["h"] if f else None, sx))
            else:
                act = film_act.norm(act)
                walk = 0.0
                if act in ("give", "hug", "pat", "feed") and to in tracks:     # tới gần trước
                    x0 = tr.x_at(t)
                    x1 = _target_x(to, tracks, who, t, W, T, chars)
                    if x1 is not None and abs(x1 - x0) > T * 0.3:
                        pre = rise(who, t)
                        walk = max(0.6, abs(x1 - x0) / (T * WALK))
                        tr.moves.append((t + pre, t + pre + walk, x0, x1, False))
                        tr.keys.append((t + pre + walk, x1))
                        walk += pre
                d = walk + (float(b.get("dur") or 0) or default_dur(act))
                tr.acts.append((t + walk, t + d, act, to))
                hold(who, t, act)
                if act in film_act.CONTINUOUS:
                    activity[who] = act
                if act == "eat" and species.get(who) != "human" and \
                        not any(abs(fx - tr.x_at(t + walk)) < T * 0.6 for _t0, fx, _n in floor):
                    ax = tr.x_at(t + walk)                       # chó tự ăn: có bát trước mõm
                    near = [o.x_at(t) for c, o in tracks.items() if c != who]
                    side = (1 if near and min(near, key=lambda v: abs(v - ax)) > ax else -1) if near else \
                        (1 if ax < W / 2 else -1)
                    floor.append((t + walk, ax + side * T * 0.3, "bowl"))
                if act == "feed" and to in tracks and species.get(to) != "human":
                    # cho chó / mèo ăn: chìa bát, đặt xuống đất trước mõm, con vật mừng rồi cúi ăn
                    put = t + walk + 0.9
                    tracks[to].acts.append((t + walk, put, "happy", who))
                    tracks[to].acts.append((put, 1e9, "eat", who))
                    tracks[to].reacts.add(t + walk)
                    ax, hx = tracks[to].x_at(put), tracks[who].x_at(put)
                    floor.append((put, ax + (T * 0.3 if hx > ax else -T * 0.3), "bowl"))
                    tr.props.append((put, "none"))               # bát đã đặt xuống, tay không
                    auto_prop.pop(who, None)
                    sfx.append((put, "thud", 0.12))
                elif act in ANIMAL_LIKE and to in tracks and species.get(to) != "human" and \
                        not any(x[2] == "eat" and x[0] <= t + walk for x in tracks[to].acts):
                    tracks[to].acts.append((t + walk, t + d, "happy", who))   # chó được vuốt ve thì mừng
                    tracks[to].reacts.add(t + walk)
                if act == "give" and to in tracks:
                    got = tr.last(tr.props, t) or b.get("prop")
                    tr.props.append((t + d - 0.3, None))
                    if got:
                        tracks[to].props.append((t + d - 0.3, got))
                    sfx.append((t + d - 0.4, "swoosh", 0.3))
            if b.get("text"):
                d = max(d, durs.get(bt["i"], 0) + 0.3)
            last_speaker = None if not b.get("text") else "_narr"
        else:
            continue
        bt["t1"] = t + d
        beats.append(bt)
        t += d
    total = t + TAIL
    # việc làm dở kéo dài tới khi người đó có hành động / bước đi khác
    for cid, tr in tracks.items():
        acts = sorted(tr.acts, key=lambda a: a[0])
        new = []
        for k, (t0, t1, a, to) in enumerate(acts):
            if a == "eat" and t1 >= 1e8:          # con vật ăn tới khi có việc khác
                nxt = [x[0] for x in acts[k + 1:] if x[0] > t0 and x[0] not in tr.reacts]
                stops = [m[0] for m in tr.moves if m[0] > t0]
                t1 = min(nxt + stops) if nxt + stops else total
            if a in film_act.CONTINUOUS and t1 < 1e8:
                # phản ứng ngắn khi nghe người khác nói không cắt việc đang làm
                # (act_at chọn cái bắt đầu muộn nhất, xong phản ứng thì làm tiếp)
                nxt = [x[0] for x in acts[k + 1:] if x[0] >= t1 - 1e-6 and x[2] != "talk"
                       and x[0] not in tr.reacts]
                stops = [m[0] for m in tr.moves if m[0] >= t1 - 1e-6] + \
                        [p[0] for p in tr.postures if p[0] >= t1 - 1e-6]
                ends = nxt + stops
                t1 = min(ends) if ends else total
            new.append((t0, t1, a, to))
        tr.acts = new
    # lúc có người nói: tiếng làm việc nhỏ hẳn và thưa ra để nghe rõ lời
    talk_spans = sorted((s[0] - 0.2, s[1] + 0.2) for tr in tracks.values() for s in tr.speak)
    talk_spans += [(b["t0"], b["t1"]) for b in beats if b.get("t") == "narr"]

    def talking(k):
        return any(a <= k <= b for a, b in talk_spans)
    # tiếng động theo động tác, bước chân, chó sủa...
    for cid, tr in tracks.items():
        sp = species.get(cid, "human")
        for t0, t1, run in [(m[0], m[1], m[4]) for m in tr.moves]:
            step = 0.24 if run else 0.34
            k = t0 + 0.1
            while k < t1:
                sfx.append((k, "step", 0.22 if sp == "human" else 0.12))
                k += step
        for t0, t1, a, _to in tr.acts:
            t1 = min(t1, total)
            if sp != "human" and a == "eat":
                k = t0 + 0.1
                while k < t1:
                    sfx.append((k, "nom", 0.12 if talking(k) else 0.3))
                    k += 0.9
                continue
            if sp in ("dog", "cat") and a in ("jump", "happy", "angry", "wave", "hands_up"):
                sfx.append((t0 + 0.15, "bark" if sp == "dog" else "meow", 0.55))
                continue
            if a == "hands_up":
                sfx.append((t0 + 0.05, "gasp", 0.35))
            if a == "cry" and sp == "human":
                k = t0 + 0.4
                while k < t1:
                    if not talking(k):
                        sfx.append((k, "sniff", 0.35))
                    k += 1.6
            rule = film_act.SFX.get(a)
            if rule and sp == "human":
                name, per, ph = rule
                k = t0 + ph
                n_hit = 0
                while k < t1:
                    if talking(k):
                        if n_hit % 3 == 0:
                            sfx.append((k, name, 0.12))
                    else:
                        sfx.append((k, name, 0.45 if name not in ("bubble", "nom") else 0.3))
                    n_hit += 1
                    k += per
        for s0, _s1, _to, _p in tr.speak:                 # chó mèo "nói" = sủa / kêu
            if sp in ("dog", "cat"):
                sfx.append((s0, "bark" if sp == "dog" else "meow", 0.55))
    if any(b.get("act") == "enter" for b in src) and indoor:
        for b in beats:
            if b.get("act") == "enter":
                sfx.append((b["t0"], "door", 0.25))
    sfx.sort()
    return {"tracks": tracks, "beats": beats, "dur": total, "W": W, "T": T, "furniture": furn,
            "sfx": sfx, "floor": floor}


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
    if z > 1.01:
        # đừng cắt ai làm đôi ở mép khung: lấy trọn người đó hoặc đẩy hẳn ra ngoài
        half = T * 0.45                 # cả con chó (dài hơn người) cũng lấy trọn
        focus = xs or [cx]
        for _ in range(3):
            moved = False
            for c, o in tr.items():
                x = o.x_at(tt)
                for edge, sgn in ((cx - vw / 2, 1), (cx + vw / 2, -1)):
                    if abs(x - edge) >= half:
                        continue
                    opts = sorted([(x - half) - edge if sgn > 0 else (x + half) - edge,
                                   (x + half) - edge if sgn > 0 else (x - half) - edge], key=abs)
                    for sh in opts:
                        ncx = min(max(cx + sh, vw / 2), W - vw / 2)
                        if all(ncx - vw / 2 + half * 0.6 <= f <= ncx + vw / 2 - half * 0.6 for f in focus):
                            if abs(ncx - cx) > 1e-3:
                                cx, moved = ncx, True
                            break
            if not moved:
                break
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
            self.rigs[cid] = (film_rig.Rig(kit, plan["T"], seed, film_rig.style_of(st)) if kit["species"] == "human"
                              else film_rig.AnimalRig(kit, plan["T"], seed), kit, seed)
        self.shots = shots(plan)
        self.env = {}
        for cid, tr in plan["tracks"].items():
            for s in tr.speak:
                if s[3]:
                    from .story_live import envelope
                    self.env[(cid, s[0])] = envelope(s[3], fps)
        self.speakers = {}
        self._furn: dict = {}
        self.rain = scene.get("weather") == "rain"
        self.tags: dict = {}                 # {id: (t0, t1)} thẻ tên, film_render đặt
        self._tags: dict = {}
        self.names = {c["id"]: c.get("name") or c["id"] for c in st.get("characters") or []}

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
        a = me.act_at(t)
        if a and a[0] in film_act.TOOL_ACTS:
            # đang cuốc / bổ / quét: quay lưỡi về phía trống, không bổ vào người, vào chó
            near = [(abs(ot.x_at(t) - x), ot.x_at(t)) for oc, ot in tr.items()
                    if oc != cid and abs(ot.x_at(t) - x) < self.plan["T"] * 1.6]
            if near:
                d = -1 if min(near)[1] > x else 1
                return d, -0.3 * d
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
        if env is not None and len(env):
            i = int((t - sp[0]) * self.fps)
            if not 0 <= i < len(env):
                return False
            # nhép theo tiếng: ngưỡng thấp để câu nói nhỏ vẫn mở miệng, có tiếng là mấp máy
            return bool(env[i] > 0.15) and (i // 2) % 3 != 2
        return int(t * 8) % 2 == 0

    def pose(self, cid, t):
        tr = self.plan["tracks"][cid]
        rig, kit, seed = self.rigs[cid]
        x = tr.x_at(t)
        pt0, posture, seat_h, seat_x = tr.posture_at(t)
        prev = tr.prev_posture(t)
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
        y = self.floor
        T = self.plan["T"]
        u = 1.0
        if human and not m and posture in ("lie", "sit") and \
                (posture == "lie" and prev == "sit" or posture == "sit" and prev == "lie"):
            # nằm xuống / ngồi dậy từ từ chứ không bật thẳng
            u = film_act._ease(min(1.0, (t - pt0) / 0.6))
            if posture == "sit":
                u = 1.0 - u
            if u > 0.0 and posture == "sit":
                p = film_act.pose("lie", t, seed)
        if posture == "lie" and not m or (posture == "sit" and u > 0.0 and prev == "lie" and human and not m):
            d = 1                                        # nằm: không lật qua lật lại
            if human:
                p["rot"] = -90.0 * u
                p["bob"] = 0.13 * u
                p["sit"] = 1.0 - u
                p["seat_h"] = seat_h
            if seat_x is not None:                       # nằm trên giường / chiếu
                x = seat_x + 0.5 * T * u
            y = self.floor - (seat_h or 0.0) * u
            if not human:
                y = self.floor - (seat_h or 0.0)
        elif posture == "sit" and not m:
            if seat_x is not None:
                x = seat_x
            if seat_h is not None:
                p["seat_h"] = seat_h
        p.update(x=x, y=y, dir=d, look=look, mouth=self._mouth(cid, t) or bool(p.get("chew")), blink=blink)
        dflt = p.get("prop_default")
        if prop == "none":                          # vừa đặt đồ xuống: tay không
            p.pop("prop_default", None)
        elif prop:
            p["prop"] = dflt if dflt and dflt[0] == prop else (prop, 0)
        elif dflt and posture != "lie":
            p["prop"] = dflt
        if posture == "lie":
            p.pop("prop", None)
        pr = p.get("prop")
        if human and pr and pr[0] in film_rig.TOOLS and p.get("tool_ang") is None:
            # cầm cuốc / chổi mà không làm: chống xuống đất cạnh người (đi thì xách chếch),
            # không xoay theo tay lung tung
            arms = list(p.get("arms") or [(8, 0), (8, 0)])
            arms[pr[1] if pr[1] in (0, 1) else 0] = (30, 10) if m else (22, 8)
            p["arms"] = arms
            p["tool_ang"] = 28.0 if m else 6.0
        p["_act"] = act
        p["_lie"] = posture == "lie" and u >= 1.0 and not m
        p["_human"] = human
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
        for f in self.plan.get("furniture") or []:           # đồ đạc sau nhân vật
            self._furniture(frame, f, cam, z, t)
        poses = {cid: self.pose(cid, t) for cid in self.plan["tracks"]}
        # người nằm vẽ trước, rồi con vật, rồi người (bát, điếu luôn ở trước con chó)
        order = sorted(poses, key=lambda c: (not poses[c]["_lie"], poses[c]["_human"], poses[c]["x"]))
        T = self.plan["T"]
        vx0, vx1 = cx - W / (2 * z), cx + W / (2 * z)        # vùng thế giới đang thấy
        for cid in order:                                    # bóng chân
            p = poses[cid]
            if p["_act"] == "lie" or not (-0.2 * W < p["x"] < 1.2 * W):
                continue
            kit = self.rigs[cid][1]
            w = T * (0.42 if kit["species"] == "human" else 0.5 * doodle.char_height(kit, 1.0)) * z
            sx, sy = cam[0, 0] * p["x"] + cam[0, 2], cam[1, 1] * p["y"] + cam[1, 2]
            self._shadow(frame, sx, sy, w)
        night = (0.78, 0.8, 0.95) if self.night else None
        floor_done = False
        for cid in order:
            p = poses[cid]
            if p["_human"] and not floor_done:               # bát cơm dưới đất: trước người, mõm chó
                floor_done = True                            # thì cắm vào bát
                for t0, fx, name in self.plan.get("floor") or []:
                    if t >= t0:
                        self._floor_item(frame, name, fx, cam, z)
            cxw = p["x"] - (0.5 * T if p["_lie"] else 0.0)
            if not (vx0 - 0.05 * T < cxw < vx1 + 0.05 * T):   # ở ngoài khung: cả người lẫn đồ cầm
                continue
            rig = self.rigs[cid][0]
            info = rig.draw(frame, p, cam, z, night)
            if p["_lie"] and p["_human"]:
                self._blanket(frame, p, cam, z, rig)
            hx, hy = info["head"]
            film_rig.marks(frame, p["_act"], t, (hx, hy + 0.08 * info["r"], info["r"]), T * z,
                           p.get("dir", 1))
            tag = self.tags.get(cid)
            if tag and tag[0] <= t < tag[1]:
                self._tag(frame, cid, hx, hy - info["r"] * 1.25, t - tag[0], tag[1] - t)
        if not floor_done:
            for t0, fx, name in self.plan.get("floor") or []:
                if t >= t0:
                    self._floor_item(frame, name, fx, cam, z)
        if self.rain:
            self._rain(frame, t)
        return frame

    # --- chăn, thẻ tên, đồ đạc, mưa
    def _blanket(self, frame, p, cam, z, rig):
        """Chăn đắp từ chân lên tới ngực người nằm."""
        cv2 = self.cv2
        T = rig.T * z
        fx, fy = cam[0, 0] * p["x"] + cam[0, 2], cam[1, 1] * p["y"] + cam[1, 2]
        x0, x1 = fx - (rig.T - rig.R * 1.6) * z, fx + T * 0.06      # từ ngực tới quá chân
        hgt = (rig.T * 0.13 + rig.wb * 1.08) * z
        bot = fy - T * 0.005
        top = [(x0 + (x1 - x0) * k / 16, bot - hgt * (1 - (2 * k / 16 - 1) ** 6)) for k in range(17)]
        pts = np.array([(x0 - T * 0.02, bot)] + top + [(x1 + T * 0.02, bot)], np.float32)
        P = (pts * 4).astype(np.int32)
        lw = max(1, int(T * 0.016))
        col = (178, 112, 104) if not self.night else (140, 88, 84)
        cv2.fillPoly(frame, [P], col, cv2.LINE_AA, shift=2)
        cv2.polylines(frame, [P], True, film_rig.OUT, lw, cv2.LINE_AA, shift=2)
        for k in (0.3, 0.62):                                # nếp chăn
            xx = x0 + (x1 - x0) * k
            fold = np.array([[xx, bot - hgt * 0.85], [xx + T * 0.03, bot - T * 0.02]], np.float32)
            cv2.polylines(frame, [(fold * 4).astype(np.int32)], False, (150, 90, 84), max(1, lw // 2),
                          cv2.LINE_AA, shift=2)

    def _floor_item(self, frame, name, x, cam, z):
        key = ("floor", name, round(z * 8) / 8)
        if key not in self._furn:
            got = film_rig.prop_image(name, self.plan["T"] * 0.16 * z)
            if got:
                img = got[0]
                bb = img.getbbox() or (0, 0, img.width, img.height)
                got = (film_rig._premul(img), ((bb[0] + bb[2]) / 2, bb[3]))
            self._furn[key] = got
        got = self._furn[key]
        if not got:
            return
        arr, (ax, ay) = got
        sx, sy = cam[0, 0] * x + cam[0, 2], cam[1, 1] * self.floor + cam[1, 2]
        film_rig.paste(frame, arr, film_rig._tr(sx - ax, sy - ay + 2),
                       (0.78, 0.8, 0.95) if self.night else None)

    def _tag(self, frame, cid, x, y, since, left):
        """Thẻ tên nhỏ trên đầu lúc nhân vật mới xuất hiện (biết ai là ai)."""
        from PIL import Image, ImageDraw, ImageFont
        from . import video
        if cid not in self._tags:
            name = self.names.get(cid) or cid
            f = ImageFont.truetype(video.find_font(True, True), max(12, int(self.H * 0.032)))
            tw = int(ImageDraw.Draw(Image.new("RGBA", (4, 4))).textlength(name, font=f))
            pad = int(f.size * 0.4)
            img = Image.new("RGBA", (tw + pad * 2, int(f.size * 1.5)), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=pad, fill=(255, 250, 236, 235),
                                outline=(60, 50, 44, 255), width=2)
            d.text((pad, int(f.size * 0.18)), name, font=f, fill=(50, 40, 36, 255))
            self._tags[cid] = film_rig._premul(img)
        arr = self._tags[cid]
        a = max(0.0, min(1.0, since / 0.3, left / 0.3))
        if a <= 0:
            return
        h, w = arr.shape[:2]
        x0 = int(min(max(x - w / 2, 4), self.W - w - 4))
        y0 = int(min(max(y - h, 4), self.H - h - 4))
        film_rig.paste(frame, (arr.astype(np.float32) * a).astype(np.uint8), film_rig._tr(x0, y0))

    def _furniture(self, frame, f, cam, z, t):
        import cv2
        key = (f["item"], round(z * 8) / 8)
        if key not in self._furn:
            self._furn[key] = furniture_image(f["item"], self.plan["T"] * z)
        got = self._furn[key]
        if got is None:
            return
        arr, (ax, ay) = got
        sx, sy = cam[0, 0] * f["x"] + cam[0, 2], cam[1, 1] * self.floor + cam[1, 2]
        film_rig.paste(frame, arr, film_rig._tr(sx - ax, sy - ay),
                       (0.78, 0.8, 0.95) if self.night else None)
        if f["item"] == "stove":                         # lửa bập bùng
            T = self.plan["T"] * z
            for k in range(3):
                fl = 0.5 + 0.5 * math.sin(t * 11 + k * 2.1)
                cx, cy = int(sx + (k - 1) * T * 0.07), int(sy - T * 0.09)
                h = int(T * (0.1 + 0.05 * fl))
                pts = np.array([[cx - int(T * 0.04), cy], [cx, cy - h], [cx + int(T * 0.04), cy]], np.int32)
                cv2.fillPoly(frame, [pts], (250, 150 + int(60 * fl), 50), cv2.LINE_AA)

    def _rain(self, frame, t):
        import cv2
        H, W = frame.shape[:2]
        frame[:] = (frame * 0.86).astype(np.uint8)
        rng = np.random.default_rng(int(t * 24))
        n = 160
        xs = rng.uniform(0, W, n)
        ys = rng.uniform(0, H, n)
        ln = H * 0.04
        for x, y in zip(xs, ys):
            cv2.line(frame, (int(x), int(y)), (int(x - ln * 0.25), int(y + ln)), (200, 210, 230), 1, cv2.LINE_AA)

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


def furniture_image(item: str, wpx: float):
    """Ảnh đồ đạc (đã nhân alpha) + điểm đặt (giữa chân đồ vật). wpx = T màn hình."""
    from PIL import Image
    if item not in FURNITURE:
        return None
    T = wpx * doodle.SS
    _lab, wk, hk, _s, _l = FURNITURE[item]
    w, h = wk * T, max(hk, 0.05) * T
    W, H = int(w + T * 0.3), int(T * 0.75)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pen = doodle._Pen(img, T, 11)
    cx, gy = W / 2, H - T * 0.03
    wood, bamboo = (150, 108, 72), (190, 168, 104)
    if item == "bed":
        top = gy - h
        pen.shape([(cx - w / 2, top), (cx + w / 2, top), (cx + w / 2, top + T * 0.04),
                   (cx - w / 2, top + T * 0.04)], bamboo)
        for k in range(1, 12):
            xx = cx - w / 2 + w * k / 12
            pen.line([(xx, top + T * 0.005), (xx, top + T * 0.035)], width=max(1, pen.lw // 3),
                     fill=(150, 130, 80))
        for xx in (cx - w / 2 + T * 0.03, cx + w / 2 - T * 0.06):
            pen.shape([(xx, top + T * 0.04), (xx + T * 0.03, top + T * 0.04), (xx + T * 0.03, gy),
                       (xx, gy)], wood)
        pen.shape([(cx - w / 2 + T * 0.02, top - T * 0.05), (cx - w / 2 + T * 0.22, top - T * 0.05),
                   (cx - w / 2 + T * 0.22, top), (cx - w / 2 + T * 0.02, top)], (236, 232, 220))  # gối
    elif item == "bench":
        top = gy - h
        pen.shape([(cx - w / 2, top), (cx + w / 2, top), (cx + w / 2, top + T * 0.03),
                   (cx - w / 2, top + T * 0.03)], bamboo)
        for xx in (cx - w / 2 + T * 0.04, cx + w / 2 - T * 0.06):
            pen.shape([(xx, top + T * 0.03), (xx + T * 0.025, top + T * 0.03), (xx + T * 0.025, gy),
                       (xx, gy)], bamboo)
    elif item == "chair":
        top = gy - h
        pen.shape([(cx - w / 2, top), (cx + w / 2, top), (cx + w / 2, top + T * 0.025),
                   (cx - w / 2, top + T * 0.025)], wood)
        pen.shape([(cx + w / 2 - T * 0.03, top - T * 0.2), (cx + w / 2, top - T * 0.2), (cx + w / 2, gy),
                   (cx + w / 2 - T * 0.03, gy)], wood)
        pen.shape([(cx - w / 2, top), (cx - w / 2 + T * 0.025, top), (cx - w / 2 + T * 0.025, gy),
                   (cx - w / 2, gy)], wood)
    elif item == "table":
        top = gy - h
        pen.shape([(cx - w / 2, top), (cx + w / 2, top), (cx + w / 2, top + T * 0.035),
                   (cx - w / 2, top + T * 0.035)], wood)
        for xx in (cx - w / 2 + T * 0.03, cx + w / 2 - T * 0.06):
            pen.shape([(xx, top + T * 0.035), (xx + T * 0.03, top + T * 0.035), (xx + T * 0.03, gy),
                       (xx, gy)], (130, 92, 60))
        pen.ell(cx - w * 0.15, top - T * 0.03, T * 0.06, T * 0.03, (236, 232, 222))     # ấm chén
        pen.shape([(cx + w * 0.1, top - T * 0.03), (cx + w * 0.16, top - T * 0.03), (cx + w * 0.15, top),
                   (cx + w * 0.11, top)], (236, 232, 222))
    elif item == "mat":
        pen.shape([(cx - w / 2, gy - T * 0.015), (cx + w / 2, gy - T * 0.015), (cx + w / 2 + T * 0.04, gy + T * 0.01),
                   (cx - w / 2 - T * 0.04, gy + T * 0.01)], (214, 190, 130))
    elif item == "stove":
        for k in (-1, 0, 1):
            pen.shape([(cx + k * T * 0.12 - T * 0.04, gy - T * 0.08), (cx + k * T * 0.12 + T * 0.04, gy - T * 0.08),
                       (cx + k * T * 0.12 + T * 0.05, gy), (cx + k * T * 0.12 - T * 0.05, gy)], (150, 90, 70))
        pen.shape(doodle._ellipse_pts(cx, gy - T * 0.12, T * 0.15, T * 0.08, 0, 180, 14), (90, 70, 62))
        pen.ell(cx, gy - T * 0.12, T * 0.15, T * 0.03, (70, 56, 50))
    elif item == "jar":
        pen.ell(cx, gy - T * 0.15, T * 0.15, T * 0.15, (120, 84, 60))
        pen.ell(cx, gy - T * 0.29, T * 0.09, T * 0.025, (90, 64, 48))
    img = img.resize((max(1, W // doodle.SS), max(1, H // doodle.SS)), Image.LANCZOS)
    return film_rig._premul(img), (cx / doodle.SS, gy / doodle.SS)


def char_T(size) -> float:
    W, H = size
    lay = config.stage_layout(W, H)
    return H * lay["height"][0] * 0.66


def preview(st, scene, size, pdir=None, at: float | None = None):
    from PIL import Image
    chars = {c["id"]: c for c in st.get("characters") or []}
    from .film_render import ambience
    plan = simulate(scene, chars, size[0], char_T(size), {}, indoor=ambience(st, scene)[1])
    shot = FilmShot(st, scene, plan, size, pdir)
    t = at if at is not None else min(plan["dur"] * 0.4, LEAD_IN + 1.5)
    return Image.fromarray(shot.frame(t))
