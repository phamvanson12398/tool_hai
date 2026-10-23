# -*- coding: utf-8 -*-
"""Truyện kể kiểu "tool tự vẽ & diễn": mỗi cảnh ráp bối cảnh (scene_art, nét
vẽ tay) + nhân vật con nhộng (doodle) rồi cho cử động theo lời kể: thở, chớp
mắt, nhép miệng khi lời kể nhắc lại câu nói của nhân vật, khóc (nước mắt rơi),
cười nhún nhảy, giật mình, giận dỗi, ngủ, nằm, đi vào / đi ra khung...

Mỗi khung chỉ dán vài hình nhân vật đã vẽ sẵn (cache theo biểu cảm, miệng,
mắt) lên nền rồi warpAffine máy quay, nên video 25 phút vẫn dựng nhanh.
"""
from __future__ import annotations

import math
import re
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

from . import config, doodle, scene_art

# hành động -> (nhãn, biểu cảm, kiểu chuyển động)
ACTS = {
    "idle": ("Đứng yên (thở, chớp mắt)", "neutral", "breathe"),
    "happy": ("Vui, nhún nhảy", "happy", "bounce"),
    "hop": ("Mừng rỡ nhảy cẫng", "happy", "hop"),
    "sad": ("Buồn, cúi đầu", "sad", "droop"),
    "cry": ("Khóc", "cry", "tremble"),
    "angry": ("Giận dữ", "angry", "stomp"),
    "shocked": ("Giật mình, sững sờ", "shocked", "jolt"),
    "worried": ("Lo lắng", "worried", "sway"),
    "think": ("Suy nghĩ", "think", "tilt"),
    "sly": ("Ranh mãnh, cười nhếch", "sly", "lean"),
    "nod": ("Gật gù", "neutral", "nod"),
    "shake": ("Lắc đầu", "sad", "shake"),
    "sleep": ("Ngủ", "sleep", "sleep"),
    "lie": ("Nằm (ốm, chết)", "sleep", "lie"),
    "walk_in": ("Đi vào", "neutral", "walk_in"),
    "walk_out": ("Đi ra", "neutral", "walk_out"),
}

# đoán hành động từ lời kể khi AI chưa ghi
_ACT_WORDS = [
    (r"khóc|nước mắt|mếu|nức nở|sụt sùi|rưng rưng", "cry"),
    (r"chết|qua đời|tắt thở|vật vã|nằm|ốm|lăn lộn", "lie"),
    (r"giật mình|sững|hoảng|sợ|kinh ngạc|bàng hoàng|ngạc nhiên", "shocked"),
    (r"giận|tức|quát|chửi|gắt|cáu", "angry"),
    (r"cười|vui|mừng|hớn hở|phấn khởi", "happy"),
    (r"ngủ|thiếp đi", "sleep"),
    (r"lo |lo lắng|băn khoăn|day dứt|áy náy", "worried"),
    (r"buồn|thở dài|lặng lẽ|cúi|đau khổ|chua chát|ngậm ngùi|cô đơn", "sad"),
    (r"nghĩ|ngẫm|suy|tính toán", "think"),
    (r"gật", "nod"),
    (r"lắc đầu", "shake"),
    (r"bỏ đi|ra đi|đi mất|đi khỏi|rời", "walk_out"),
    (r"bước vào|đến nhà|sang chơi|chạy vào|đi vào|tới", "walk_in"),
]

_PLACE_WORDS = [
    (r"garden|yard|plot|banana|courtyard", "san_que"),
    (r"thatched|hut|mud", "nha_tranh"),
    (r"field|paddy|rice", "canh_dong"),
    (r"road|path|lane|village gate|market|banyan", "duong_lang"),
    (r"tile|teapot|study|books|house|room", "nha_ngoi"),
    (r"kitchen", "bep"), (r"school|class", "lop_hoc"), (r"office", "van_phong"),
    (r"street|city", "duong_pho"), (r"park", "cong_vien"), (r"beach|sea", "bai_bien"),
]


def place_kind(place: dict | None) -> str:
    p = place or {}
    if scene_art.valid_kind(p.get("kind")):
        return p["kind"]
    t = f"{p.get('look', '')} {p.get('name', '')}".lower()
    for pat, kind in _PLACE_WORDS:
        if re.search(pat, t):
            # nhà tranh nhìn từ ngoài (sân) hay bên trong
            if kind == "nha_tranh" and re.search(r"yard|outside|exterior|fence", t) and \
                    not re.search(r"interior|inside|dim", t):
                return "san_que"
            return kind
    return "nha_ngoi"


def guess_acts(text: str, chars: list[dict]) -> dict:
    """Ai làm gì theo lời kể: từ khoá đầu tiên tìm thấy gán cho nhân vật được
    nhắc tên gần nhất trước nó (không có thì nhân vật đầu tiên)."""
    out = {}
    low = (text or "").lower()
    humans = [c for c in chars if (c.get("kit") or {}).get("species", "human") == "human"]
    hits = sorted((m.start(), act) for pat, act in _ACT_WORDS for m in re.finditer(pat, low))
    for pos, act in hits:
        who, best = None, -1
        for c in chars:
            i = low.rfind((c.get("name") or "~").lower(), 0, pos + 1)
            if i > best:
                who, best = c, i
        who = who or (humans[0] if humans else (chars[0] if chars else None))
        if who and who["id"] not in out:
            out[who["id"]] = act
    for c in chars:                     # chó mèo mừng chủ
        sp = (c.get("kit") or {}).get("species")
        if sp in ("dog", "cat") and c["id"] not in out and re.search(r"vẫy đuôi|mừng|quấn", low):
            out[c["id"]] = "hop"
    return out


def guess_talk(text: str, chars: list[dict]) -> str:
    """Lời kể có trích lời (ngoặc kép) thì người được nhắc tên ngay trước đó nhép miệng."""
    q = re.search(r"[“\"«]", text or "")
    if not q:
        return ""
    low = text.lower()
    who, best = "", -1
    for c in chars:
        if (c.get("kit") or {}).get("species", "human") != "human":
            continue
        i = low.rfind((c.get("name") or "~").lower(), 0, q.start())
        if i > best:
            who, best = c["id"], i
    if not who:
        hs = [c["id"] for c in chars if (c.get("kit") or {}).get("species", "human") == "human"]
        who = hs[0] if len(hs) == 1 else ""
    return who


def scene_time(sc: dict, place: dict | None) -> str:
    if sc.get("time") in scene_art.TIMES:
        return sc["time"]
    if re.search(r"\bđêm\b|tối|trăng|đèn dầu|khuya", (sc.get("text") or "").lower()):
        return "dem"
    return (place or {}).get("time") if (place or {}).get("time") in scene_art.TIMES else "ngay"


def talk_windows(text: str, dur: float) -> list[tuple[float, float]]:
    """Khoảng thời gian (trong lời kể dài dur giây) đọc các câu có trích lời."""
    from .story import _sentences
    sents = _sentences(text or "")
    tot = sum(len(s) for s in sents) or 1
    out, acc = [], 0
    inside = False
    for s in sents:
        a = acc / tot * dur
        acc += len(s)
        b = acc / tot * dur
        opens = s.count("“") + s.count("«") + s.count('"') // 2 + (s.count('"') % 2)
        closes = s.count("”") + s.count("»")
        has_q = bool(re.search(r"[“\"«]", s)) or inside
        if has_q:
            out.append((a, b))
        if s.count('"') % 2 or opens > closes:
            inside = not inside if s.count('"') % 2 else True
        if closes > 0 and closes >= opens:
            inside = False
    return out


def envelope(path, fps: int) -> np.ndarray | None:
    """Độ to lời kể theo từng khung hình (0..1) để nhép miệng."""
    try:
        import soundfile as sf
        a, sr = sf.read(str(path), dtype="float32")
    except Exception:  # noqa: BLE001
        return None
    if a.ndim > 1:
        a = a.mean(axis=1)
    hop = max(1, int(sr / fps))
    n = len(a) // hop
    if n <= 0:
        return None
    rms = np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    peak = np.percentile(rms, 95) or 1.0
    return np.clip(rms / peak, 0, 1)


# ---------------------------------------------------------------- nền

_BG_CACHE: dict = {}


def background(kind: str, time: str, size, seed: int) -> np.ndarray:
    key = (kind, time, tuple(size), seed)
    if key not in _BG_CACHE:
        if len(_BG_CACHE) > 6:
            _BG_CACHE.pop(next(iter(_BG_CACHE)))
        img = scene_art.render_scene(kind, time, size=tuple(size), seed=seed, art="doodle")
        _BG_CACHE[key] = np.asarray(img.convert("RGB")).copy()
    return _BG_CACHE[key]


def background3d(pdir, place_id: str, time: str, size):
    """Nền 3D AI vẽ (None nếu chưa vẽ); thiếu bản đêm thì làm tối bản ngày."""
    from . import bg3d
    p = bg3d.path_for(pdir, place_id, time)
    darken = False
    if not p.exists() and time == "dem":
        p, darken = bg3d.path_for(pdir, place_id, "ngay"), True
    if not p.exists():
        return None
    key = ("3d", str(p), p.stat().st_mtime, tuple(size), darken)
    if key not in _BG_CACHE:
        if len(_BG_CACHE) > 6:
            _BG_CACHE.pop(next(iter(_BG_CACHE)))
        a = np.asarray(bg3d.load_cover(p, tuple(size))).astype(np.float32)
        if darken:
            a = a * np.array([0.45, 0.5, 0.72], dtype=np.float32)
        _BG_CACHE[key] = np.clip(a, 0, 255).astype(np.uint8)
    return _BG_CACHE[key]


# ---------------------------------------------------------------- cảnh động

def _bump(t, a, b):
    if t <= a or t >= b:
        return 0.0
    return math.sin(math.pi * (t - a) / (b - a))


class LiveShot:
    """Một cảnh do tool vẽ: frame(u) như _Shot của story_render."""

    def __init__(self, st: dict, sc: dict, size, camera: str, dur: float,
                 audio=None, audio_at: float = 0.0, audio_dur: float = 0.0,
                 over: float = 1.15, fps: int = 24, pdir=None, speech=None):
        import cv2
        self.cv2 = cv2
        self.W, self.H = size
        self.bw, self.bh = int(self.W * over), int(self.H * over)
        self.camera = camera
        self.dur = max(0.1, dur)
        self.fps = fps
        self.scale = 1.0
        places = {p["id"]: p for p in st.get("places") or []}
        place = places.get(sc.get("place"))
        kind = place_kind(place)
        self.night = scene_time(sc, place) == "dem"
        seed = zlib.crc32(str(sc.get("place") or kind).encode()) % 1000
        self.base = None
        self.is3d = False
        if st.get("bg_mode") == "ai3d" and pdir is not None and place:
            # bối cảnh 3D AI đã vẽ cho địa điểm này (vẽ một lần, dùng lại)
            self.base = background3d(pdir, place["id"], "dem" if self.night else "ngay",
                                     (self.bw, self.bh))
            self.is3d = self.base is not None
        if self.base is None:
            self.base = background(kind, "dem" if self.night else "ngay", (self.bw, self.bh), seed)
        looks = {c["id"]: c for c in st.get("characters") or []}
        chars = [looks[c] for c in sc.get("chars") or [] if c in looks][:5]
        for c in chars:
            if not c.get("kit"):
                c["kit"] = doodle.kit_from_look(c.get("name", ""), c.get("look", ""))
        acts = sc.get("acts") if isinstance(sc.get("acts"), dict) else None
        if acts is None:
            acts = guess_acts(sc.get("text") or "", chars)
        talk = sc.get("talk") if "talk" in sc else guess_talk(sc.get("text") or "", chars)
        # lời kể bắt đầu ở audio_at (giây tính từ đầu cảnh)
        self.audio_at = audio_at
        self.env = envelope(audio, fps) if (audio and talk) else None
        self.talk_win = [(audio_at + a, audio_at + b) for a, b in
                         talk_windows(sc.get("text") or "", audio_dur)] if talk else []
        # thoại nhân vật: [{"who", "at" (giây từ đầu cảnh), "dur", "path"}]
        self.speech = []
        for sp in speech or []:
            if sp.get("who") in looks and looks[sp["who"]] not in chars and len(chars) < 5:
                c = looks[sp["who"]]
                c.setdefault("kit", doodle.kit_from_look(c.get("name", ""), c.get("look", "")))
                chars.append(c)
            self.speech.append(dict(sp, env=envelope(sp.get("path"), fps)))
        self._layout(chars, acts, talk, kind)
        self._cache: dict = {}
        self._shadows: dict = {}

    # --- bố cục: ai đứng đâu, quay về phía ai
    def _layout(self, chars, acts, talk, kind):
        lay = config.stage_layout(self.bw, self.bh)
        n = len(chars)
        floor = self.bh * lay["floor"]
        T = self.bh * lay["height"][0 if n <= 2 else 1] * 0.7
        slots = lay["slots"].get(n) or [0.12 + 0.76 * i / max(1, n - 1) for i in range(n)]
        self.T = T
        self.actors = []
        for i, c in enumerate(chars):
            act = acts.get(c["id"]) or "idle"
            if act not in ACTS:
                act = "idle"
            back = n >= 3 and i % 2 == 1
            x = slots[i] * self.bw if n else self.bw / 2
            self.actors.append({
                "c": c, "kit": doodle.clean_kit(c["kit"]), "act": act,
                "x": x, "y": floor - (self.bh * 0.03 if back else 0),
                "k": 0.93 if back else 1.0, "talk": c["id"] == talk,
                "seed": zlib.crc32(c["id"].encode()) % 997, "back": back,
            })
        for a in self.actors:
            others = [o["x"] for o in self.actors if o is not a]
            if others:
                tx = sum(others) / len(others)
                a["face"] = 0.65 if tx > a["x"] else -0.65
            else:
                a["face"] = 0.15 if a["x"] < self.bw / 2 else -0.15
        self.actors.sort(key=lambda a: (not a["back"], a["x"]))

    def _sprite(self, a, expr, mouth, blink):
        key = (a["c"]["id"], expr, mouth, blink, a["face"] > 0)
        if key not in self._cache:
            img, foot, eye = doodle.render(a["kit"], expr, mouth, blink, a["face"],
                                           height=int(self.T * a["k"]), seed=a["seed"])
            arr = np.asarray(img).astype(np.float32)
            if self.night:
                arr[..., :3] *= np.array([0.78, 0.8, 0.95], dtype=np.float32)
            arr[..., :3] *= arr[..., 3:4] / 255.0          # nhân trước alpha: trộn nhanh bằng cv2
            self._cache[key] = (np.clip(arr + 0.5, 0, 255).astype(np.uint8), foot, eye)
        return self._cache[key]

    # --- cử động
    def _motion(self, a, t):
        """(dx, dy, góc độ, sx, sy) — dx, dy tính theo phần của T."""
        m = ACTS[a["act"]][2]
        ph = a["seed"] / 97.0
        br = math.sin(2 * math.pi * t / 2.4 + ph)
        dx = dy = rot = 0.0
        sx = 1.0
        sy = 1.0 + 0.012 * br
        f = 1 if a["face"] > 0 else -1
        if m == "bounce":
            dy = -0.035 * abs(math.sin(math.pi * t / 0.45)) if (t + ph) % 2.6 < 1.4 else 0.0
        elif m == "hop":
            dy = -0.11 * abs(math.sin(math.pi * t / 0.55)) if (t + ph) % 3.0 < 1.6 else 0.0
            sy += 0.03 * (1 - abs(math.sin(math.pi * t / 0.55))) * (dy != 0)
        elif m == "droop":
            rot = -f * 4.0
            sy = 0.985 + 0.008 * math.sin(2 * math.pi * t / 3.2 + ph)
        elif m == "tremble":
            dx = 0.004 * math.sin(2 * math.pi * 11 * t)
            rot = -f * 3.0
            sy = 1.0 + 0.02 * max(0.0, math.sin(2 * math.pi * t / 1.1))     # nấc
        elif m == "stomp":
            if (t + ph) % 2.2 < 0.6:
                dx = 0.012 * math.sin(2 * math.pi * 9 * t)
                dy = -0.025 * abs(math.sin(2 * math.pi * 4 * t))
        elif m == "jolt":
            j = _bump(t, 0.15, 0.55)
            dy = -0.1 * j
            sy += 0.06 * j
            sx = 1 - 0.04 * j
            if t > 0.55:
                dx = 0.002 * math.sin(2 * math.pi * 13 * t)
        elif m == "sway":
            rot = 3.0 * math.sin(2 * math.pi * t / 1.8 + ph)
        elif m == "tilt":
            rot = -f * 5.0
        elif m == "lean":
            rot = f * 4.0 + 1.0 * math.sin(2 * math.pi * t / 2.0)
        elif m == "nod":
            if (t + ph) % 2.5 < 1.4:
                sy = 1 - 0.035 * max(0.0, math.sin(2 * math.pi * t / 0.7))
                rot = f * 2.0 * max(0.0, math.sin(2 * math.pi * t / 0.7))
        elif m == "shake":
            if (t + ph) % 2.6 < 1.2:
                rot = 4.0 * math.sin(2 * math.pi * t / 0.45)
        elif m == "sleep":
            sy = 1.0 + 0.025 * math.sin(2 * math.pi * t / 3.5)
        elif m == "lie":
            rot = 90.0 * f
            dy = -0.0
            sy = 1.0 + 0.01 * math.sin(2 * math.pi * t / 3.5)
        elif m in ("walk_in", "walk_out"):
            walk = min(3.0, max(1.6, self.dur * 0.35))
            if m == "walk_in":
                u = min(1.0, t / walk)
                moving = u < 1
            else:
                u = max(0.0, (t - (self.dur - walk)) / walk)
                moving = 0 < u < 1
            if moving:
                dy = -0.03 * abs(math.sin(math.pi * t / 0.28))
                rot = 3.0 * math.sin(math.pi * t / 0.28)
        return dx, dy, rot, sx, sy

    def _walk_x(self, a, t):
        m = ACTS[a["act"]][2]
        if m not in ("walk_in", "walk_out"):
            return a["x"]
        walk = min(3.0, max(1.6, self.dur * 0.35))
        off = -self.T * 0.8 if a["x"] < self.bw / 2 else self.bw + self.T * 0.8
        if m == "walk_in":
            u = min(1.0, t / walk)
            u = u * u * (3 - 2 * u)
            return off + (a["x"] - off) * u
        u = max(0.0, min(1.0, (t - (self.dur - walk)) / walk))
        u = u * u * (3 - 2 * u)
        return a["x"] + (off - a["x"]) * u

    def _mouth(self, a, t):
        for sp in self.speech:                  # đang nói câu thoại của mình
            if sp["who"] == a["c"]["id"] and sp["at"] <= t <= sp["at"] + sp["dur"]:
                env = sp.get("env")
                if env is not None:
                    i = int((t - sp["at"]) * self.fps)
                    return 0 <= i < len(env) and bool(env[i] > 0.3) and (i // 2) % 3 != 2
                return int(t * 8) % 2 == 0
        if not a["talk"] or not any(x0 <= t <= x1 for x0, x1 in self.talk_win):
            return False
        if self.env is not None:
            i = int((t - self.audio_at) * self.fps)
            if 0 <= i < len(self.env):
                return bool(self.env[i] > 0.3) and (i // 2) % 3 != 2
            return False
        return int(t * 8) % 2 == 0

    def _blink(self, a, t):
        if ACTS[a["act"]][1] in ("sleep", "cry", "happy"):
            return False
        per = 3.2 + (a["seed"] % 13) / 8.0
        return (t + a["seed"] / 50.0) % per < 0.13

    # --- vẽ
    def _paste(self, canvas, arr, foot, x, y, rot, sx, sy):
        cv2 = self.cv2
        h, w = arr.shape[:2]
        ang = math.radians(rot)
        ca, sa_ = math.cos(ang), math.sin(ang)
        # sprite -> canvas: dời chân về gốc, co giãn, xoay, đặt vào (x, y)
        A = np.array([[ca * sx, -sa_ * sy], [sa_ * sx, ca * sy]], dtype=np.float64)
        b = np.array([x, y]) - A @ np.array(foot)
        corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], dtype=np.float64) @ A.T + b
        x0, y0 = np.floor(corners.min(axis=0)).astype(int)
        x1, y1 = np.ceil(corners.max(axis=0)).astype(int)
        H, W = canvas.shape[:2]
        x0c, y0c, x1c, y1c = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if x1c <= x0c or y1c <= y0c:
            return
        M = np.hstack([A, (b - np.array([x0c, y0c]))[:, None]]).astype(np.float32)
        part = cv2.warpAffine(arr, M, (x1c - x0c, y1c - y0c), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        inv = 255 - part[..., 3]
        reg = canvas[y0c:y1c, x0c:x1c]
        keep = cv2.multiply(reg, cv2.merge([inv, inv, inv]), scale=1 / 255.0)
        canvas[y0c:y1c, x0c:x1c] = cv2.add(keep, np.ascontiguousarray(part[..., :3]))

    def _marks(self, canvas, a, t, head):
        cv2 = self.cv2
        act = a["act"]
        hx, hy, r = head
        T = self.T
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
        if act in ("worried", "shocked"):
            x, y = int(hx + r * 0.95), int(hy - r * 0.5 + 0.02 * T * math.sin(t * 3))
            pts = np.array([[x, y - int(r * 0.22)], [x - int(r * 0.1), y],
                            [x + int(r * 0.1), y]], np.int32)
            cv2.circle(canvas, (x, y + int(r * 0.03)), int(r * 0.1), (170, 214, 244), -1, cv2.LINE_AA)
            cv2.fillPoly(canvas, [pts], (170, 214, 244), cv2.LINE_AA)
            cv2.circle(canvas, (x, y + int(r * 0.03)), int(r * 0.1), (60, 90, 120), lw // 2 + 1, cv2.LINE_AA)
        if act == "shocked" and t < 1.8:
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
                    x = int(hx + (a["face"] > 0 and 1 or -1) * r * (0.6 + 0.3 * j))
                    y = int(hy - r * (1.2 + 0.25 * j))
                    rr = int(r * (0.06 + 0.03 * j))
                    cv2.circle(canvas, (x, y), rr, (250, 250, 250), -1, cv2.LINE_AA)
                    cv2.circle(canvas, (x, y), rr, (40, 34, 38), max(1, lw // 2), cv2.LINE_AA)

    def _shadow(self, canvas, x, y, w):
        """Bóng mờ dưới chân cho nhân vật đứng vững trên nền (nhất là nền 3D)."""
        cv2 = self.cv2
        rx, ry = int(w * 0.5), max(2, int(w * 0.09))
        x0, y0 = max(0, int(x) - rx - 2), max(0, int(y) - ry - 2)
        x1, y1 = min(canvas.shape[1], int(x) + rx + 2), min(canvas.shape[0], int(y) + ry + 2)
        if x1 <= x0 or y1 <= y0:
            return
        key = (rx, ry)
        if key not in self._shadows:
            m = np.zeros((2 * ry + 5, 2 * rx + 5), np.uint8)
            cv2.ellipse(m, (rx + 2, ry + 2), (rx, ry), 0, 0, 360, 255, -1, cv2.LINE_AA)
            m = cv2.GaussianBlur(m, (0, 0), max(1.0, ry * 0.5))
            self._shadows[key] = 255 - (m.astype(np.float32) * (0.32 if self.is3d else 0.18)).astype(np.uint8)
        m = self._shadows[key][y0 - (int(y) - ry - 2):, x0 - (int(x) - rx - 2):][: y1 - y0, : x1 - x0]
        reg = canvas[y0:y1, x0:x1]
        canvas[y0:y1, x0:x1] = cv2.multiply(reg, cv2.merge([m, m, m]), scale=1 / 255.0)

    def scene_frame(self, t: float) -> np.ndarray:
        canvas = self.base.copy()
        for a in self.actors:
            if ACTS[a["act"]][2] != "lie":
                w = self.T * a["k"] * (0.42 if a["kit"]["species"] == "human" else 0.5) * \
                    (doodle.char_height(a["kit"], 1.0) if a["kit"]["species"] != "human" else 1.0)
                self._shadow(canvas, self._walk_x(a, t), a["y"], w)
        for a in self.actors:
            expr = ACTS[a["act"]][1]
            arr, foot, eye = self._sprite(a, expr, self._mouth(a, t), self._blink(a, t))
            dx, dy, rot, sx, sy = self._motion(a, t)
            x = self._walk_x(a, t) + dx * self.T
            y = a["y"] + dy * self.T
            if ACTS[a["act"]][2] == "lie":
                y -= self.T * 0.18 * a["k"]
            self._paste(canvas, arr, foot, x, y, rot, sx, sy)
            # vị trí đầu trên khung (bỏ qua xoay nhỏ) để vẽ nước mắt, mồ hôi...
            if ACTS[a["act"]][2] != "lie":
                hx = x + (eye[0] - foot[0]) * sx
                hy = y + (eye[1] - foot[1]) * sy
                self._marks(canvas, a, t, (hx, hy, eye[2]))
            elif a["act"] == "lie":
                self._marks(canvas, a, t, (x, y - self.T * 0.25, self.T * 0.2))
        return canvas

    def frame(self, u: float) -> np.ndarray:
        """Như story_render._Shot.frame nhưng nền có nhân vật cử động; máy quay
        chuyển động nhẹ hơn để không cắt mất người."""
        from .story_render import _ease
        canvas = self.scene_frame(u * self.dur)
        e = _ease(u)
        c = self.camera
        z0 = z1 = 1.0
        cx = cy = 0.5
        if c == "zoom_in":
            z0, z1 = 1.0, 1.07
        elif c == "zoom_out":
            z0, z1 = 1.07, 1.0
        elif c in ("pan_left", "pan_right", "pan_up", "pan_down"):
            z0 = z1 = 1.06
        z = z0 + (z1 - z0) * e
        vw, vh = self.bw / z, self.bh / z
        if c == "pan_left":
            cx = 1 - e
        elif c == "pan_right":
            cx = e
        elif c == "pan_up":
            cy = 1 - e
        elif c == "pan_down":
            cy = e
        if c in ("zoom_in", "zoom_out") and self.actors:      # phóng vào chỗ có người
            cx = min(1.0, max(0.0, sum(a["x"] for a in self.actors) / len(self.actors) / self.bw))
            cy = 0.62
        vx, vy = (self.bw - vw) * cx, (self.bh - vh) * cy
        k = self.W / vw
        M = np.float32([[k, 0, -vx * k], [0, self.H / vh, -vy * self.H / vh]])
        return self.cv2.warpAffine(canvas, M, (self.W, self.H), flags=self.cv2.INTER_LINEAR)


def preview(st: dict, sc: dict, size, t: float = 1.0, pdir=None) -> Image.Image:
    """Ảnh xem trước một cảnh (khung giữa cảnh)."""
    shot = LiveShot(st, sc, size, "still", 6.0, pdir=pdir)
    return Image.fromarray(shot.frame(min(1.0, t / 6.0)))


def character_preview(c: dict, height: int = 360) -> Image.Image:
    kit = c.get("kit") or doodle.kit_from_look(c.get("name", ""), c.get("look", ""))
    img, _foot, _eye = doodle.render(kit, "neutral", facing=0.3, height=height)
    bg = Image.new("RGBA", img.size, (246, 238, 222, 255))
    bg.alpha_composite(img)
    return bg.convert("RGB")


def place_preview(p: dict, time: str, size) -> Image.Image:
    seed = zlib.crc32(str(p.get("id") or "").encode()) % 1000
    return Image.fromarray(background(place_kind(p), time, size, seed))


def kinds_text() -> str:
    from . import scene_rural
    rural = ", ".join(f"{k} ({v['label']})" for k, v in scene_rural.KINDS.items())
    other = ", ".join(f"{k} ({v['label']})" for k, v in scene_art.KINDS.items()
                      if k not in scene_rural.KINDS)
    from . import doodle_parts
    extra = ", ".join(f"{k} ({v['name']})" for k, v in doodle_parts.load().items()
                      if v.get("kind") == "scene")
    return f"{rural}; hiện đại: {other}" + (f"; đã vẽ thêm: {extra}" if extra else "")
