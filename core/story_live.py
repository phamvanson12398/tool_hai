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

from . import config, doodle, film_act, film_rig, scene_art

# hành động -> (nhãn, biểu cảm). Dùng chung thư viện của chế độ Phim; tên cũ
# (hop, shocked, worried, shake, sly) vẫn hiểu được.
ACTS = {k: v for k, v in film_act.ACTIONS.items() if k not in ("walk", "run")}
ACTS["walk_in"] = ("Đi vào", "neutral")
ACTS["walk_out"] = ("Đi ra", "neutral")


def act_of(name: str) -> str:
    if name in ("walk_in", "walk_out"):
        return name
    return film_act.norm(name)


# đoán hành động từ lời kể khi AI chưa ghi
_ACT_WORDS = [
    (r"khóc|nước mắt|mếu|nức nở|sụt sùi|rưng rưng", "cry"),
    (r"chết|qua đời|tắt thở|vật vã|nằm|ốm|lăn lộn", "lie"),
    (r"giật mình|sững|hoảng|kinh ngạc|bàng hoàng|ngạc nhiên", "hands_up"),
    (r"run|sợ hãi|sợ", "tremble"),
    (r"giận|tức|quát|chửi|gắt|cáu", "angry"),
    (r"cười to|cười ha|cười ngặt", "laugh"),
    (r"cười|vui|mừng|hớn hở|phấn khởi", "happy"),
    (r"vỗ tay", "clap"),
    (r"vẫy", "wave"),
    (r"chỉ tay|chỉ vào|trỏ", "point"),
    (r"ôm", "hug"),
    (r"ăn|xới cơm|gắp", "eat"),
    (r"uống|nhấp", "drink"),
    (r"van xin|lạy|cầu xin|chắp tay", "beg"),
    (r"đưa|trao|biếu|gửi", "give"),
    (r"xoa đầu|vỗ về|vuốt ve", "pat"),
    (r"gãi đầu|bối rối|lúng túng", "scratch_head"),
    (r"khoanh tay", "cross_arms"),
    (r"chống nạnh", "hands_hips"),
    (r"cúi chào|vái", "bow"),
    (r"cuốc|quét|cày|làm lụng|gánh|đào", "work"),
    (r"ngồi", "sit"),
    (r"ngủ|thiếp đi", "sleep"),
    (r"lo |lo lắng|băn khoăn|day dứt|áy náy", "scratch_head"),
    (r"buồn|thở dài|lặng lẽ|cúi|đau khổ|chua chát|ngậm ngùi|cô đơn", "sad"),
    (r"nghĩ|ngẫm|suy|tính toán", "think"),
    (r"gật", "nod"),
    (r"lắc đầu", "shake_head"),
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
            out[c["id"]] = "jump"
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
        self.outdoor = kind in scene_art.OUTDOOR
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
        self.sty = film_rig.style_of(st)
        self._layout(chars, acts, talk, kind)
        self._shadows: dict = {}
        self.cam = np.array([[1.0, 0, 0], [0, 1.0, 0]])

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
            act = act_of(acts.get(c["id"]) or "idle")
            back = n >= 3 and i % 2 == 1
            x = slots[i] * self.bw if n else self.bw / 2
            kit = doodle.clean_kit(c["kit"])
            seed = zlib.crc32(c["id"].encode()) % 997
            k = 0.93 if back else 1.0
            rig = film_rig.Rig(kit, T * k, seed, self.sty) if kit["species"] == "human" \
                else film_rig.AnimalRig(kit, T * k, seed)
            self.actors.append({
                "c": c, "kit": kit, "act": act, "rig": rig,
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

    def _walking(self, a, t):
        """Đang đi (vào / ra khung) không."""
        m = a["act"]
        if m not in ("walk_in", "walk_out"):
            return False
        walk = min(3.0, max(1.6, self.dur * 0.35))
        return t < walk if m == "walk_in" else (self.dur - walk) < t < self.dur

    def _walk_x(self, a, t):
        m = a["act"]
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

    def _speaking(self, a, t):
        for sp in self.speech:
            if sp["who"] == a["c"]["id"] and sp["at"] <= t <= sp["at"] + sp["dur"]:
                return True
        return a["talk"] and any(x0 <= t <= x1 for x0, x1 in self.talk_win)

    def _blink(self, a, t):
        if ACTS.get(a["act"], ("", "neutral"))[1] in ("sleep", "cry", "happy"):
            return False
        per = 3.2 + (a["seed"] % 13) / 8.0
        return (t + a["seed"] / 50.0) % per < 0.13

    # --- vẽ
    def _marks(self, canvas, a, t, head):
        film_rig.marks(canvas, a["act"], t, head, self.T, a["face"])

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

    def _pose(self, a, t):
        """Tư thế nhân vật ở giây t: đi vào/ra, hành động của cảnh, vung tay khi nói."""
        speaking = self._speaking(a, t)
        moving = self._walking(a, t)
        x = self._walk_x(a, t)
        human = a["kit"]["species"] == "human"
        act = "idle" if a["act"] in ("walk_in", "walk_out") else a["act"]
        if not human:
            p = film_act.animal_pose(act, t, a["seed"], moving)
        elif moving:
            dist = abs(x - a["x"]) / self.T
            p = film_act.walk_cycle(dist, t)
            p["expr"] = "neutral"
        else:
            p = film_act.pose(act, t, a["seed"], self.dur, speaking,
                              posture="sit" if act == "sit" else "stand")
        d = 1 if a["face"] > 0 else -1
        if moving:
            d = 1 if (self._walk_x(a, t + 0.05) - x) > 0 else -1
        p.update(x=x, y=a["y"], dir=d,
                 look=max(-1.0, min(1.0, a["face"] + p.get("look_shift", 0.0) * 0.4)),
                 mouth=self._mouth(a, t), blink=self._blink(a, t))
        if p.get("prop_default") and not p.get("prop"):
            p["prop"] = p["prop_default"]
        return p

    def scene_frame(self, t: float) -> np.ndarray:
        canvas = self.base.copy()
        poses = [self._pose(a, t) for a in self.actors]
        for a, p in zip(self.actors, poses):
            if a["act"] != "lie":
                w = self.T * a["k"] * (0.42 if a["kit"]["species"] == "human" else 0.5) * \
                    (doodle.char_height(a["kit"], 1.0) if a["kit"]["species"] != "human" else 1.0)
                self._shadow(canvas, p["x"], a["y"], w)
        night = (0.78, 0.8, 0.95) if self.night else None
        for a, p in zip(self.actors, poses):
            if a["act"] == "lie":                 # nằm trên giường (trong nhà) / chiếu (ngoài trời)
                from . import film
                item = "mat" if self.outdoor else "bed"
                key = ("furn", item)
                if key not in self._shadows:
                    self._shadows[key] = film.furniture_image(item, self.T * a["k"])
                arr, (ax, ay) = self._shadows[key]
                bx = p["x"] - 0.5 * self.T * a["k"]
                film_rig.paste(canvas, arr, film_rig._tr(bx - ax, a["y"] - ay), night)
                p["y"] = a["y"] - (film.furn_info(item) or (0, 0, 0))[2] * self.T * a["k"]
                p["dir"] = 1                          # đầu về phía gối
            info = a["rig"].draw(canvas, p, self.cam, 1.0, night)
            hx, hy = info["head"]
            self._marks(canvas, a, t, (hx, hy + 0.08 * info["r"], info["r"]))
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


def character_preview(c: dict, height: int = 360, sty: dict | None = None) -> Image.Image:
    """Ảnh xem trước nhân vật đúng kiểu nhân vật của truyện (có tay chân)."""
    kit = doodle.clean_kit(c.get("kit") or doodle.kit_from_look(c.get("name", ""), c.get("look", "")))
    W = H = int(height * 1.15)
    canvas = np.full((H, W, 3), (246, 238, 222), np.uint8)
    cam = np.array([[1.0, 0, 0], [0, 1.0, 0]])
    if kit["species"] == "human":
        rig = film_rig.Rig(kit, height * 0.95, 3, sty)
        p = film_act.pose("idle", 0.5, 3)
        p.update(x=W / 2, y=H - height * 0.06, dir=1, look=0.3)
    else:
        rig = film_rig.AnimalRig(kit, height * 1.4, 3)
        p = {"x": W / 2, "y": H - height * 0.06, "dir": 1}
    rig.draw(canvas, p, cam, 1.0)
    return Image.fromarray(canvas)


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
