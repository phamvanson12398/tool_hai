# -*- coding: utf-8 -*-
"""Truyện webtoon (kiểu kênh kể chuyện 썰): danh sách cảnh quay -> video.

Mỗi cảnh quay ("shot") là một khung hình có người nói / im lặng:
  {"id": "s001", "type": "close" | "medium" | "wide" | "two" | "phone" | "black",
   "place": "id địa điểm", "time": "ngay" | "dem",
   "who": "id nhân vật chính", "with": ["id người thứ hai"]   (type "two" / "wide"),
   "expr": "worried", "pose": "phone_ear", "look": "left" | "right" | "down" | "",
   "extras": ["sweat"], "enter": "left" | "right" | "",        (đi vào khung)
   "camera": "push_in" | "pull_out" | "pan_left" | "pan_right" | "shake" | "still",
   "line": {"who": "id" | "narr", "text": "câu nói"},
   "phone": {"screen": "chat" | "call" | ..., "data": {...}},  (type "phone")
   "dur": 2.0}                                                 (khi không có câu nói)
Nhân vật: {"id", "name", "look": {webtoon_art.Look}, "voice": {"voice" | "instruct"}}.

Tool tự vẽ từng khung (webtoon_art) nên nhân vật nhép miệng đúng giọng, chớp mắt,
thở, lắc đầu nhẹ khi nói, tay chuyển dần sang tư thế mới, có thể đi vào khung;
máy quay đẩy / lia / rung; cận cảnh thì nền mờ tối như video mẫu.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import subprocess
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import scene_art, video, webtoon_art as wa, webtoon_phone as wp, webtoon_pics as wpic

logger = logging.getLogger(__name__)

FPS = 24
GAP = 0.25                  # nghỉ sau mỗi câu
LEAD = 0.12                 # câu bắt đầu sau khi cắt cảnh
AUDIO_DIR = "webtoon_audio"
SHOT_TYPES = ("close", "medium", "wide", "two", "phone", "black")
CAMERAS = ("push_in", "pull_out", "pan_left", "pan_right", "shake", "still")

PLACE_KINDS = {"spot": "Nền trơn có vòng sáng (lúc kể chuyện)",
               **{k: v["label"] for k, v in scene_art.KINDS.items()}}
STYLES = {"saeon": "Kể chuyện 사연 (nhân vật chính tự kể + thoại, như kênh 썰)",
          "drama": "Toàn thoại (rất ít lời kể)"}
FRONTS = ("table", "bed")


def default_story() -> dict:
    return {"title": "", "brief": "", "genre": "marriage", "language": "ko", "minutes": 4, "style": "saeon",
            "bg_mode": "2d",
            "part": 1, "subtitles": True, "characters": [], "places": [], "shots": []}


# ---------------------------------------------------------------- dữ liệu

def figures(st: dict) -> dict:
    out = {}
    for c in st.get("characters") or []:
        lk = wa.Look.from_dict(c.get("look"))
        lk.seed = zlib.crc32(str(c.get("id")).encode()) % 997
        out[c["id"]] = wa.Figure(lk)
    return out


def clean_shot(s: dict, ids: set, k: int) -> dict:
    s = dict(s or {})
    s["id"] = str(s.get("id") or f"s{k + 1:03d}")
    if s.get("type") not in SHOT_TYPES:
        s["type"] = "phone" if s.get("phone") else ("close" if s.get("who") else "wide")
    if s.get("who") not in ids:
        s["who"] = next(iter(ids), "") if s["type"] not in ("phone", "black") else s.get("who") or ""
    s["with"] = [w for w in (s.get("with") or []) if w in ids and w != s.get("who")][:2]
    if s.get("expr") not in wa.EXPRS:
        s["expr"] = "neutral"
    if s.get("pose") not in wa.POSES:
        s["pose"] = "down"
    if s.get("camera") not in CAMERAS:
        s["camera"] = "push_in" if s["type"] == "close" else "still"
    ln = s.get("line") or {}
    if ln and ln.get("text"):
        who = ln.get("who")
        s["line"] = {"who": who if (who in ids or who == "narr") else s.get("who") or "narr",
                     "text": str(ln["text"]).strip()[:300]}
    else:
        s["line"] = {}
    s["front"] = s.get("front") if s.get("front") in FRONTS else ""
    s["extras"] = [x for x in (s.get("extras") or []) if x in ("sweat", "tears", "blush", "bags",
                                                               "bruise", "shadow")]
    return s


def all_lines(st: dict) -> list[tuple[dict, dict]]:
    return [(s, s["line"]) for s in st.get("shots") or [] if (s.get("line") or {}).get("text")]


# ---------------------------------------------------------------- giọng

def narrate(st: dict, pdir: Path, progress=None) -> dict[str, Path]:
    """Đọc từng câu (mỗi nhân vật một giọng cố định). {id cảnh quay: file wav}."""
    import soundfile as sf
    from . import voice
    lang = st.get("language") or "ko"
    chars = {c["id"]: c for c in st.get("characters") or []}
    todo = all_lines(st)
    adir = pdir / AUDIO_DIR
    adir.mkdir(parents=True, exist_ok=True)
    if progress and todo:
        progress(0.0, "chọn giọng riêng cho từng nhân vật")
    nid = narrator_self(st)
    voices = cast_voices(st, pdir, lang, {(nid if ln["who"] == "narr" and nid else ln["who"]) for _s, ln in todo})
    out = {}
    for k, (s, ln) in enumerate(todo):
        who = nid if ln["who"] == "narr" and nid else ln["who"]     # lời kể = giọng nhân vật chính
        c = chars.get(who) or {}
        cfg, ref = voices.get(who) or ({"instruct": _instruct_of(c)}, {})
        key = hashlib.md5(json.dumps([ln["text"], ref.get("ref"), cfg.get("instruct")],
                                     ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        path = adir / f"{s['id']}_{key}.wav"
        if not path.exists():
            if progress:
                progress(k / max(1, len(todo)), f"đọc thoại {k + 1}/{len(todo)}: {c.get('name') or who}")
            wav, sr = voice.synthesize(ln["text"], lang,
                                       ref_wav=Path(ref["ref"]) if ref.get("ref") else None,
                                       ref_text=ref.get("ref_text"),
                                       instruct=None if ref.get("ref") else cfg.get("instruct"),
                                       seed=int(key[:6], 16))
            wav = voice.trim_silence(np.asarray(wav, dtype=np.float32), sr)
            for old in adir.glob(f"{s['id']}_*.wav"):
                old.unlink(missing_ok=True)
            sf.write(str(path), wav, sr)
        out[s["id"]] = path
    return out


def narrator_id(st: dict) -> str:
    """Kiểu 사연: id nhân vật chính — người tự kể chuyện."""
    nid = st.get("narrator_id") or ""
    return nid if nid in {c["id"] for c in st.get("characters") or []} else ""


NARR_VOICES = {"own": "Giọng riêng cho người kể (khác mọi nhân vật)",
               "self": "Lời kể dùng giọng nhân vật chính (nhép miệng khi kể)"}


def narrator_self(st: dict) -> str:
    """Lời kể đọc bằng chính giọng nhân vật chính (và nhân vật đó nhép miệng) — chỉ khi chị
    chọn "self"; mặc định người kể có giọng riêng. Trả id nhân vật chính hoặc ""."""
    return narrator_id(st) if st.get("narrator_voice") == "self" else ""


def _voice_cfg(c: dict) -> dict:
    """Giọng chị chọn (Thư viện / mô tả); để trống thì tool tự mô tả theo tuổi, giới."""
    v = c.get("voice") or {}
    if v.get("voice") or (v.get("instruct") or "").strip():
        return {"voice": v.get("voice") or "", "instruct": (v.get("instruct") or "").strip()}
    return {"instruct": _instruct_of(c)}


def cast_voices(st: dict, pdir: Path, lang: str, speakers: set) -> dict:
    """Mỗi nhân vật một giọng KHÁC NHAU, cố định cả truyện (dùng chung cách chọn giọng của
    tab Phim): hai người cùng mô tả thì đổi cao độ, đo cao độ giọng mẫu và tạo lại khi hai
    giọng nghe giống nhau; đàn ông không ra giọng cao như nữ / trẻ con; người kể khác hẳn
    nhân vật. Trả về {id | "narr": (cfg, ref)}."""
    from . import film_render
    chars = st.get("characters") or []
    narr = dict(st.get("narrator") or {})
    main = next((c for c in chars if c["id"] == narrator_id(st)), None)
    if main and not narr.get("voice") and not (narr.get("instruct") or "").strip():
        # 사연 có giọng kể riêng: lời kể vẫn là "저는..." của nhân vật chính nên cùng giới, cùng tuổi,
        # nhưng cao độ / chất giọng khác hẳn giọng thoại (tool còn đo cao độ để không trùng ai)
        base = _instruct_of(main)
        sex, age = base.split(", ")[:2]
        own = "low pitch" if "high pitch" in base else ("moderate pitch" if "low pitch" in base else "low pitch")
        narr["instruct"] = f"{sex}, {age}, {own}, soft calm storytelling voice"
    shim = {"characters": [{"id": c["id"], "voice": _voice_cfg(c),
                            "kit": {"species": "human", **(c.get("look") or {})}} for c in chars],
            "narrator": narr}
    ids = [c["id"] for c in chars if c["id"] in speakers]
    got = film_render.cast(shim, pdir, lang, ids, narr="narr" in speakers)
    out = {cid: got[f"nv_{cid}"] for cid in ids if f"nv_{cid}" in got}
    if "nguoi_ke" in got:
        out["narr"] = got["nguoi_ke"]
    return out


def _instruct_of(c: dict) -> str:
    """Mô tả giọng OmniVoice (chỉ dùng từ khoá OmniVoice hiểu) theo tuổi, giới."""
    lk = c.get("look") or {}
    sex = "female" if lk.get("sex") == "female" else "male"
    a = lk.get("age") or "adult"
    age = {"child": "child", "teen": "teenager", "young": "young adult", "adult": "young adult",
           "middle": "middle-aged", "old": "elderly"}.get(a, "young adult")
    if sex == "female":
        pitch = "high pitch" if a in ("child", "teen", "young") else "moderate pitch"
    else:
        pitch = {"child": "high pitch", "teen": "moderate pitch", "young": "moderate pitch"}.get(a, "low pitch")
    return f"{sex}, {age}, {pitch}"


# ---------------------------------------------------------------- mốc thời gian

def plan(st: dict, audio: dict) -> list[dict]:
    import soundfile as sf
    rows, t = [], 0.0
    for s in st.get("shots") or []:
        p = audio.get(s["id"])
        ad = sf.info(str(p)).duration if p and Path(p).exists() else 0.0
        if ad:
            dur = LEAD + ad + GAP
        else:
            dur = float(s.get("dur") or (2.2 if s["type"] == "phone" else 1.6))
            if (s.get("line") or {}).get("text"):            # chưa có giọng: ước lượng theo chữ
                ad = max(1.0, len(s["line"]["text"].split()) / 3.2)
                dur = LEAD + ad + GAP
        rows.append({"shot": s, "start": t, "dur": dur, "audio": p if ad and p else None,
                     "audio_dur": ad})
        t += dur
    return rows


def envelope(path, fps: int = FPS) -> np.ndarray | None:
    try:
        from .story_live import envelope as env
        return env(path, fps)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- dựng một cảnh quay

_BG_CACHE: dict = {}


def background(st: dict, s: dict, size, pdir: Path | None = None) -> Image.Image:
    """Bối cảnh của cảnh quay: ảnh nền 3D của địa điểm nếu đã có (tool vẽ / chị tải lên),
    không thì bối cảnh vẽ tay; cận cảnh thì mờ và tối (như video mẫu)."""
    from . import webtoon_bg
    W, H = size
    places = {p["id"]: p for p in st.get("places") or []}
    pl = places.get(s.get("place")) or {}
    kind = pl.get("kind") if pl.get("kind") in scene_art.KINDS else "phong_khach"
    time = webtoon_bg.shot_time(st, s)
    blur = {"close": 16, "medium": 6, "two": 4, "phone": 20}.get(s["type"], 0)
    p3 = webtoon_bg.path_for(pdir, s.get("place") or "", time) if pdir else None
    stamp = (p3.stat().st_mtime if p3 and p3.exists() else
             (webtoon_bg.path_for(pdir, s.get("place") or "", "ngay").stat().st_mtime
              if pdir and webtoon_bg.path_for(pdir, s.get("place") or "", "ngay").exists() else 0))
    if pl.get("kind") == "spot":
        key = ("spot", size)
        if key not in _BG_CACHE:
            _BG_CACHE[key] = spot_bg(size)
        return _BG_CACHE[key]
    key = (kind, time, size, blur, s.get("place"), str(pdir), stamp, st.get("bg_mode"))
    if key not in _BG_CACHE:
        seed = zlib.crc32(str(s.get("place") or kind).encode()) % 1000
        img = (webtoon_bg.image_for(pdir, s.get("place") or "", time, (W, H))
               if st.get("bg_mode") != "draw" else None)
        if img is None:
            img = scene_art.render_scene(kind, time, size=(W, H), seed=seed).convert("RGB")
        if blur:
            img = img.filter(ImageFilter.GaussianBlur(blur * W / 1280))
            img = Image.blend(img, Image.new("RGB", (W, H), (18, 20, 30)), 0.45 if s["type"] != "phone" else 0.55)
        if len(_BG_CACHE) > 12:
            _BG_CACHE.pop(next(iter(_BG_CACHE)))
        _BG_CACHE[key] = img
    return _BG_CACHE[key]


def spot_bg(size) -> Image.Image:
    """Nền trơn lúc nhân vật chính kể chuyện (như video mẫu): tím pastel nhạt, vòng sáng trắng
    lớn phía sau nhân vật."""
    W, H = size
    img = Image.new("RGB", (W, H), (244, 242, 252))
    S = 2
    big = Image.new("L", (W * S, H * S), 0)
    ImageDraw.Draw(big).ellipse([W * S * 0.07, H * S * 0.14, W * S * 0.93, H * S * 1.95], fill=255)
    mask = big.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(W / 900))
    img.paste((255, 255, 255), (0, 0), mask)
    return img


def draw_front(img: Image.Image, kind: str, xs: list, lw: float) -> None:
    """Vật che phía trước nhân vật (nét đen, màu phẳng như video mẫu): "table" mép bàn + cốc
    cà phê trước mỗi người; "bed" chăn đắp ngang người."""
    W, H = img.size
    S = 2
    lay = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    L = max(2, int(lw * S * 1.1))
    ink = (28, 26, 30, 255)
    if kind == "table":
        y0 = H * S * 0.8
        d.rectangle([-L, y0, W * S + L, H * S + L], fill=(196, 176, 152, 255), outline=ink, width=L)
        for x in xs:
            cx, cw, ch = x * W * S, W * S * 0.042, H * S * 0.12        # cốc nhỏ, cao vừa
            top = y0 - ch * 0.78
            hx = cx + cw
            d.ellipse([hx - cw * 0.25, top + ch * 0.18, hx + cw * 0.55, top + ch * 0.62], outline=ink, width=L)
            d.rounded_rectangle([cx - cw, top, cx + cw, top + ch], radius=cw * 0.5, fill=(255, 255, 255, 255),
                                outline=ink, width=L)
            d.rectangle([cx - cw + L, top, cx + cw - L, top + ch * 0.4], fill=(255, 255, 255, 255))
            d.ellipse([cx - cw, top - ch * 0.1, cx + cw, top + ch * 0.1], fill=(255, 255, 255, 255), outline=ink, width=L)
            d.ellipse([cx - cw * 0.82, top - ch * 0.055, cx + cw * 0.82, top + ch * 0.065], fill=(78, 52, 40, 255))
    elif kind == "bed":
        y0 = H * S * 0.66
        pts = [(-L, H * S + L), (-L, y0 + H * S * 0.06)]
        for i in range(21):
            u = i / 20
            pts.append((W * S * u, y0 - math.sin(math.pi * u) * H * S * 0.05 + (H * S * 0.03 if u in (0, 1) else 0)))
        pts += [(W * S + L, y0 + H * S * 0.06), (W * S + L, H * S + L)]
        d.polygon(pts, fill=(246, 236, 226, 255))
        d.line(pts[1:-1], fill=ink, width=L, joint="curve")
        d.line([(0, y0 + H * S * 0.14), (W * S, y0 + H * S * 0.12)], fill=(220, 206, 192, 255), width=L)
    img.alpha_composite(lay.resize((W, H), Image.LANCZOS))


def _ease(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


class Shot:
    """Vẽ một cảnh quay: frame(t) với t tính từ đầu cảnh."""

    def __init__(self, st: dict, row: dict, size, figs: dict, prev: dict | None = None,
                 pics: dict | None = None, pdir: Path | None = None):
        self.st, self.row, self.s = st, row, row["shot"]
        self.pics = pics or {}                   # ảnh AI chị tải lên: {id nhân vật: {key: Pic}}
        self.W, self.H = size
        self.figs = figs
        self.lang = st.get("language") or "ko"
        self.bg = background(st, self.s, size, pdir)
        self.env = envelope(row["audio"]) if row.get("audio") else None
        if self.env is not None and len(self.env):
            self.env = self.env / (float(np.percentile(self.env, 95)) + 1e-6)
        self.prev = prev or {}
        self.lw = max(2.0, self.W / 640)
        self.font = wp.font(int(self.H * 0.062), True, self.lang)
        self._layout()

    # --- nhép miệng
    def _mouth(self, cid: str, t: float) -> float:
        ln = self.s.get("line") or {}
        if ln.get("who") != cid and not (ln.get("who") == "narr" and cid and cid == narrator_self(self.st)):
            return 0.0
        a0, a1 = LEAD, LEAD + self.row["audio_dur"]
        if not (a0 <= t < a1):
            return 0.0
        if self.env is not None and len(self.env):
            k = int((t - a0) * FPS)
            if 0 <= k < len(self.env):
                return float(min(1.0, self.env[k] * 1.1))
            return 0.0
        return 0.5 + 0.5 * math.sin((t - a0) * 14)        # chưa có giọng: nhép giả

    def _state(self, cid: str, t: float, main: bool) -> wa.State:
        s = self.s
        seed = zlib.crc32(cid.encode()) % 97
        st = wa.State()
        st.expr = s.get("expr", "neutral") if main else (s.get("with_expr") or "neutral")
        st.pose = s.get("pose", "down") if main else (s.get("with_pose") or "down")
        st.pose_from = self.prev.get(cid, st.pose)
        st.pose_k = _ease(t / 0.45) if st.pose_from != st.pose else 1.0
        st.mouth = self._mouth(cid, t)
        # chớp mắt mỗi 2,5–4 giây
        per = 2.6 + (seed % 13) / 10
        ph = (t + seed * 0.37) % per
        st.blink = 1.0 if ph < 0.12 else 0.0
        st.breathe = (t * 0.28 + seed * 0.1) % 1.0
        talk = st.mouth > 0.05
        st.tilt = 1.4 * math.sin(t * 0.8 + seed) + (1.2 * math.sin(t * 5.5) if talk else 0.0)
        st.nod = (0.012 * math.sin(t * 9) if talk else 0.0)
        look = s.get("look") if main else ""
        st.yaw = {"left": -0.45, "right": 0.45}.get(look, 0.0) + 0.06 * math.sin(t * 0.5 + seed)
        st.look = {"left": (-1, 0), "right": (1, 0), "down": (0, 1), "up": (0, -1)}.get(look, (0, 0))
        st.extras = tuple(s.get("extras") or ()) if main else ()
        if st.expr in ("scared", "desperate") and main:
            st.shake = t
        return st

    def _place(self, cid, t, kind, x, main):
        fig = self.figs.get(cid)
        if fig is None:
            return None
        W, H = self.W, self.H
        b = fig.b
        if kind == "close":
            s = H * 0.64                         # miệng nằm trên vùng phụ đề
            hc_y = H * 0.45
            foot = (x * W, hc_y - b["head_c"][1] * s)
        elif kind in ("medium", "two"):
            s = H / (3.3 if kind == "medium" else 3.7)
            foot = (x * W, H * 0.34 - b["head_c"][1] * s)
        else:                                    # wide: cả người
            s = H * 0.6 / b["H"]
            foot = (x * W, H * 0.93)
        enter = self.s.get("enter") if main else ""
        if enter in ("left", "right"):
            k = _ease(t / 1.1)
            dx = (1 - k) * (0.65 * W) * (-1 if enter == "left" else 1)
            foot = (foot[0] + dx, foot[1] - abs(math.sin(t * 9)) * 0.01 * H * (1 - k))
        return fig, foot, s

    def _pic(self, img, cid, t, kind, x, main) -> bool:
        """Nhân vật có ảnh AI: dán ảnh đúng tư thế + nét mặt như một khung truyện tranh,
        chỉ nhép miệng, chớp mắt, nhún nhẹ khi nói."""
        st = self._state(cid, t, main)
        pic = wpic.pick(self.pics.get(cid) or {}, st.pose, st.expr)
        if pic is None:
            return False
        W, H = self.W, self.H
        if kind == "close":
            d, ey, bottom = H * 0.22, H * 0.458, None
        elif kind in ("medium", "two"):
            d, ey, bottom = H * (0.104 if kind == "medium" else 0.093), H * 0.34, H
        else:
            d, ey, bottom = H * 0.07, H * 0.36, H
        cx = x * W
        enter = self.s.get("enter") if main else ""
        if enter in ("left", "right"):
            k = _ease(t / 1.1)
            cx += (1 - k) * (0.65 * W) * (-1 if enter == "left" else 1)
        if st.mouth > 0.05:                      # nhún nhẹ theo nhịp nói
            ey += abs(math.sin(t * 7)) * H * 0.004
        ey += math.sin(st.breathe * 2 * math.pi) * H * 0.0015
        if st.shake:
            cx += math.sin(t * 40) * 0.004 * W
        pic.draw(img, cx, ey, d, st, max(self.lw, d * 0.02), bottom)
        return True

    def _layout(self) -> None:
        """Phần đứng yên suốt cảnh quay, tính / vẽ một lần (dựng nhanh): vị trí người, nền RGBA
        (kèm đầu giường, gối), lớp vật che phía trước đã cắt sát."""
        W, H = self.W, self.H
        s = self.s
        cast = [s.get("who")] + list(s.get("with") or [])
        if s["type"] == "close":
            xs = [0.5 + {"left": 0.06, "right": -0.06}.get(s.get("look"), 0.0)]
        elif s["type"] == "two" or len(cast) == 2:
            xs = [0.32, 0.68]
        elif len(cast) == 3:
            xs = [0.22, 0.5, 0.78]
        else:
            xs = [0.5]
        self.kind = s["type"] if s["type"] != "wide" or len(cast) < 2 else "wide"
        self.cast = cast[:1] if s["type"] == "close" else cast
        self.xs = xs
        base = self.bg.convert("RGBA")
        if s.get("front") == "bed" and s["type"] not in ("phone", "black"):   # đầu giường + gối sau người
            bd = ImageDraw.Draw(base)
            L = max(2, int(self.lw * 1.1))
            bd.rounded_rectangle([W * 0.07, H * 0.26, W * 0.93, H * 0.9], radius=W * 0.02,
                                 fill=(204, 182, 160, 255), outline=(28, 26, 30, 255), width=L)
            for x in xs[:max(1, len(self.cast))]:
                bd.rounded_rectangle([x * W - W * 0.17, H * 0.4, x * W + W * 0.17, H * 0.6], radius=W * 0.04,
                                     fill=(250, 248, 244, 255), outline=(28, 26, 30, 255), width=L)
        self.base = base
        self.front = None
        if s.get("front") in FRONTS and s["type"] not in ("phone", "black"):
            fl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            draw_front(fl, s["front"], [xs[min(i, len(xs) - 1)] for i in range(len(self.cast))], self.lw)
            bb = fl.getbbox()
            if bb:
                self.front = (fl.crop(bb), bb[:2])

    def frame(self, t: float) -> np.ndarray:
        W, H = self.W, self.H
        s = self.s
        img = self.base.copy()
        if s["type"] == "black":
            img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        elif s["type"] == "phone":
            ph = s.get("phone") or {}
            scr = wp.screen(ph.get("screen", "app"), ph.get("data") or {}, (int(H * 0.6), int(H * 1.2)),
                            self.lang, t, self.figs)
            img.alpha_composite(wp.held(scr, (W, H), lw=self.lw, tilt=0.6 * math.sin(t * 0.7)))
        else:
            cast, xs, kind = self.cast, self.xs, self.kind
            layer = None
            for i, cid in enumerate(cast):
                if not cid:
                    continue
                if cid in self.pics and self._pic(img, cid, t, kind, xs[min(i, len(xs) - 1)], i == 0):
                    continue
                got = self._place(cid, t, kind, xs[min(i, len(xs) - 1)], i == 0)
                if not got:
                    continue
                fig, foot, sc = got
                if layer is None:
                    layer = Image.new("RGBA", (W * wa.SS, H * wa.SS), (0, 0, 0, 0))
                st = self._state(cid, t, i == 0)
                if len(cast) >= 2 and i > 0:      # người thứ hai quay sang người nói
                    st.yaw = -0.4 if xs[i] > 0.5 else 0.4
                elif len(cast) >= 2:
                    st.yaw = 0.4 if xs[0] < 0.5 else -0.4
                lw = max(self.lw, sc * 0.0068)            # nét dày theo cỡ người như ảnh mẫu
                pen = wa.Pen(layer, foot[0] * wa.SS, foot[1] * wa.SS, sc * wa.SS, lw * wa.SS)
                if st.shake:
                    pen.ox += math.sin(t * 40) * 0.004 * W * wa.SS
                fig.draw(pen, st)
            if layer is not None:                          # chỉ thu nhỏ vùng có người (nhanh hơn cả khung)
                bb = layer.getbbox()
                if bb:
                    k = wa.SS
                    x0, y0 = bb[0] // k * k, bb[1] // k * k
                    x1, y1 = min(layer.width, -(-bb[2] // k) * k), min(layer.height, -(-bb[3] // k) * k)
                    img.alpha_composite(layer.crop((x0, y0, x1, y1)).reduce(k), (x0 // k, y0 // k))
            if self.front:
                img.alpha_composite(self.front[0], self.front[1])
        arr = np.asarray(img)[:, :, :3]
        arr = self._camera(arr, t)
        return np.ascontiguousarray(arr)

    def _camera(self, arr: np.ndarray, t: float) -> np.ndarray:
        import cv2
        cam = self.s.get("camera", "still")
        d = max(0.5, self.row["dur"])
        u = _ease(t / d)
        z, dx, dy = 1.0, 0.0, 0.0
        if cam == "push_in":
            z = 1.0 + 0.07 * u
        elif cam == "pull_out":
            z = 1.07 - 0.07 * u
        elif cam in ("pan_left", "pan_right"):
            z = 1.08
            dx = (0.035 if cam == "pan_left" else -0.035) * (u - 0.5) * 2 * self.W
        elif cam == "shake" and t < 0.6:
            z = 1.04
            dx = math.sin(t * 60) * 0.012 * self.W * (1 - t / 0.6)
            dy = math.cos(t * 47) * 0.01 * self.H * (1 - t / 0.6)
        if z == 1.0 and dx == 0 and dy == 0:
            return arr
        W, H = self.W, self.H
        M = np.float32([[z, 0, W / 2 - z * W / 2 + dx], [0, z, H / 2 - z * H / 2 + dy]])
        return cv2.warpAffine(np.ascontiguousarray(arr), M, (W, H), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT)

    def subtitle(self, arr: np.ndarray, t: float, name: str = "") -> np.ndarray:
        """Phụ đề như video mẫu: chữ trắng to, viền đen dày, không nền. Chữ cả cảnh như nhau
        nên vẽ một lần rồi chỉ trộn vào vùng chữ ở mỗi khung (dựng nhanh)."""
        ln = self.s.get("line") or {}
        if not ln.get("text") or not self.st.get("subtitles", True):
            return arr
        if not hasattr(self, "_sub"):
            lay = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            f = self.font
            lines = wp._wrap(d, ln["text"], f, self.W * 0.86)
            lh = int(self.H * 0.078)
            sw = max(2, int(self.H * 0.0075))
            y = self.H - int(self.H * 0.06) - lh * len(lines)
            for k, l in enumerate(lines):
                w = d.textlength(l, font=f)
                d.text(((self.W - w) / 2, y + k * lh), l, font=f, fill=(255, 255, 255), stroke_width=sw,
                       stroke_fill=(20, 20, 22))
            bb = lay.getbbox()
            if bb:
                a = np.asarray(lay.crop(bb)).astype(np.float32)
                self._sub = (bb, a[:, :, :3], a[:, :, 3:4] / 255.0)
            else:
                self._sub = None
        if not self._sub:
            return arr
        (x0, y0, x1, y1), rgb, al = self._sub
        out = np.array(arr, copy=True)
        reg = out[y0:y1, x0:x1].astype(np.float32)
        out[y0:y1, x0:x1] = (reg * (1 - al) + rgb * al).astype(np.uint8)
        return out


# ---------------------------------------------------------------- dựng video

_ENC: dict = {}
NVENC = ["-c:v", "h264_nvenc", "-preset", "fast", "-rc", "vbr", "-cq", "21", "-b:v", "0", "-pix_fmt", "yuv420p"]
X264 = ["-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-preset", "veryfast"]


def gpu_encode(ff: str) -> bool:
    """Card NVIDIA nén được video (NVENC) không — thử nén một khung (một lần). Cài đặt
    "video_encoder": "cpu" thì luôn nén bằng CPU."""
    if ff in _ENC:
        return _ENC[ff]
    ok = False
    try:
        from . import config
        if str(config.load_settings().get("video_encoder") or "auto").lower() != "cpu":
            r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                "color=c=black:s=320x240:d=0.2", *NVENC, "-f", "null", "-"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            ok = r.returncode == 0
    except Exception:  # noqa: BLE001
        ok = False
    _ENC[ff] = ok
    logger.info("Nén video bằng %s", "card NVIDIA (NVENC)" if ok else "CPU (libx264)")
    return ok


def _ffmpeg_writer(ff: str, size, out: Path, gpu: bool | None = None):
    W, H = size
    enc = NVENC if (gpu_encode(ff) if gpu is None else gpu) else X264
    return subprocess.Popen(
        [ff, "-y", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{W}x{H}",
         "-framerate", str(FPS), "-i", "-", *enc, str(out)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def prev_poses(rows: list[dict]) -> list[dict]:
    """Tư thế mỗi người ngay trước từng cảnh quay (để tay chuyển dần sang tư thế mới)."""
    out, cur = [], {}
    for r in rows:
        out.append(dict(cur))
        s = r["shot"]
        if s.get("who"):
            cur[s["who"]] = s.get("pose", "down")
    return out


def render_range(st: dict, pdir: Path | None, size, rows: list[dict], prevs: list[dict], fi0: int, fi1: int,
                 write, tick=None) -> None:
    """Dựng các khung fi0..fi1-1 (khung thứ fi ở giây fi / FPS), mỗi khung gọi write(bytes)."""
    import bisect
    figs = figures(st)
    pics = wpic.load(st, pdir)
    starts = [r["start"] for r in rows]
    cur, shot = -1, None
    for fi in range(fi0, fi1):
        t = fi / FPS
        i = max(0, bisect.bisect_right(starts, t) - 1)
        if i != cur:
            cur, shot = i, Shot(st, rows[i], size, figs, dict(prevs[i]), pics, pdir)
        lt = t - rows[i]["start"]
        write(shot.subtitle(shot.frame(lt), lt).tobytes())
        if tick and (fi - fi0) % 24 == 23:
            tick(24)


def workers_for(n_frames: int) -> int:
    """Số chương trình con dựng song song: theo số nhân CPU, video ngắn thì một."""
    import os
    if n_frames < FPS * 40:
        return 1
    return max(1, min(8, (os.cpu_count() or 2) - 1, n_frames // (FPS * 20)))


def render(st: dict, pdir: Path, size=(1920, 1080), audio: dict | None = None, progress=None,
           out_name: str = "webtoon.mp4") -> Path:
    """Dựng video: chia các khung cho nhiều chương trình con chạy song song trên các nhân CPU
    (mỗi đoạn một file), ghép lại, rồi trộn tiếng."""
    import soundfile as sf
    audio = audio or {}
    rows = plan(st, audio)
    total = sum(r["dur"] for r in rows) + 0.5
    out_dir = pdir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "webtoon_video.mp4"
    ff = video._ffmpeg_path()
    n = int(total * FPS)
    prevs = prev_poses(rows)
    gpu = gpu_encode(ff)
    k = workers_for(n) if rows else 1
    if gpu:
        k = min(k, 3)                     # card GeForce chỉ cho vài luồng NVENC cùng lúc
    if k <= 1 or not rows:
        proc = _ffmpeg_writer(ff, size, raw)
        done = [0]

        def tick(m):
            done[0] += m
            if progress and done[0] % 48 == 0:
                progress(done[0] / max(1, n), f"dựng hình {done[0]}/{n}")
        try:
            if rows:
                render_range(st, pdir, size, rows, prevs, 0, n, proc.stdin.write, tick)
        finally:
            proc.stdin.close()
            proc.wait()
    else:
        _render_parallel(st, pdir, size, rows, prevs, n, k, raw, ff, progress, gpu)
    # tiếng: mọi câu đặt đúng mốc
    sr = 24000
    mix = np.zeros(int(total * sr) + sr, dtype=np.float32)
    for r in rows:
        if not r.get("audio"):
            continue
        a, asr = sf.read(str(r["audio"]), dtype="float32", always_2d=False)
        if getattr(a, "ndim", 1) > 1:
            a = a.mean(axis=1)
        if asr != sr:
            x = np.linspace(0, len(a) - 1, int(len(a) * sr / asr))
            a = np.interp(x, np.arange(len(a)), a).astype(np.float32)
        peak = float(np.max(np.abs(a))) or 1.0
        a = a * (0.8 / peak)
        k0 = int((r["start"] + LEAD) * sr)
        mix[k0:k0 + len(a)] += a[: max(0, len(mix) - k0)]
    wav = out_dir / "webtoon_audio.wav"
    sf.write(str(wav), np.clip(mix, -1, 1), sr)
    out = out_dir / out_name
    subprocess.run([ff, "-y", "-i", str(raw), "-i", str(wav), "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "160k", "-shortest", str(out)], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True)
    raw.unlink(missing_ok=True)
    return out


def _render_parallel(st, pdir, size, rows, prevs, n, k, raw: Path, ff: str, progress, gpu: bool = False) -> None:
    import os
    import sys
    import tempfile
    import threading
    work = Path(tempfile.mkdtemp(prefix="wt_render_", dir=str(raw.parent)))
    bounds = [n * j // k for j in range(k + 1)]
    rows_j = [{"shot": r["shot"], "start": r["start"], "dur": r["dur"],
               "audio": str(r["audio"]) if r.get("audio") else None, "audio_dur": r.get("audio_dur", 0.0)}
              for r in rows]
    done = [0] * k
    procs, errs = [], []
    root = Path(__file__).resolve().parent.parent
    for j in range(k):
        job = work / f"job_{j}.json"
        job.write_text(json.dumps({"st": st, "pdir": str(pdir), "size": list(size), "rows": rows_j, "prevs": prevs,
                                   "fi0": bounds[j], "fi1": bounds[j + 1], "out": str(work / f"seg_{j:02d}.mp4"),
                                   "ffmpeg": ff, "gpu": gpu}, ensure_ascii=False), encoding="utf-8")
        ef = open(work / f"err_{j}.txt", "w", encoding="utf-8", errors="replace")
        errs.append(ef)
        procs.append(subprocess.Popen([sys.executable, "-m", "core.webtoon_render_worker", str(job)], cwd=str(root),
                                      stdout=subprocess.PIPE, stderr=ef, text=True))

    def reader(j, p):
        for line in p.stdout:
            if line.startswith("F "):
                try:
                    done[j] = int(line.split()[1])
                except ValueError:
                    pass
    threads = [threading.Thread(target=reader, args=(j, p), daemon=True) for j, p in enumerate(procs)]
    for th in threads:
        th.start()
    import time
    while any(p.poll() is None for p in procs):
        if progress:
            got = sum(done)
            progress(got / max(1, n), f"dựng hình {got}/{n} ({k} luồng song song"
                     + (", nén bằng card NVIDIA)" if gpu else ")"))
        time.sleep(1.0)
    for th in threads:
        th.join(timeout=5)
    for ef in errs:
        ef.close()
    bad = [j for j, p in enumerate(procs) if p.returncode != 0]
    if bad:
        tail = (work / f"err_{bad[0]}.txt").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-4:]
        raise RuntimeError("Dựng hình lỗi: " + " | ".join(tail))
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{(work / f'seg_{j:02d}.mp4').as_posix()}'\n" for j in range(k)), encoding="utf-8")
    subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(raw)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    for p_ in work.iterdir():
        p_.unlink(missing_ok=True)
    os.rmdir(work)


def preview(st: dict, shot_idx: int, size=(960, 540), t: float = 0.6, pdir: Path | None = None) -> Image.Image:
    rows = plan(st, {})
    if not rows:
        return Image.new("RGB", size, (20, 20, 24))
    shot_idx = max(0, min(len(rows) - 1, shot_idx))
    prev = {}
    for r in rows[:shot_idx]:
        s = r["shot"]
        if s.get("who"):
            prev[s["who"]] = s.get("pose", "down")
    sh = Shot(st, rows[shot_idx], size, figures(st), prev, wpic.load(st, pdir), pdir)
    return Image.fromarray(sh.subtitle(sh.frame(t), t))


# ---------------------------------------------------------------- AI viết

GENRES = {
    "marriage": "Hôn nhân / nhà chồng (사연: mẹ chồng, vợ chồng, việc nhà, tiền bạc, 사이다)",
    "thriller": "Giật gân / lừa đảo công nghệ (hack, lừa qua điện thoại, bắt cóc giả...)",
    "horror": "Kinh dị đời thường (nhà trọ lạ, tin nhắn lúc nửa đêm...)",
    "comedy": "Hài đời thường (hiểu lầm, sĩ diện, gia đình lầy...)",
    "romance": "Tình cảm (crush, người yêu cũ, hẹn hò...)",
    "family": "Gia đình cảm động (bố mẹ, con cái, hiểu lầm rồi thương)",
    "revenge": "Trả thù thoả mãn / 사이다 (kẻ xấu bị vạch mặt)",
    "office": "Công sở (sếp, đồng nghiệp, phỏng vấn...)",
    "school": "Học đường (bạn bè, thầy cô, thi cử...)",
    "mystery": "Bí ẩn / trinh thám (ai là thủ phạm)",
}
LANGS = {"ko": "tiếng Hàn", "vi": "tiếng Việt", "en": "tiếng Anh"}


def _catalog() -> dict:
    return {"hairs": " | ".join(wa.HAIRS), "hair_colors": " | ".join(wa.HAIR),
            "tops": " | ".join(wa.TOPS), "colors": " | ".join(wa.CLOTH),
            "kinds": ", ".join(f"{k} ({v})" for k, v in PLACE_KINDS.items()),
            "exprs": ", ".join(wa.EXPRS), "poses": ", ".join(wa.POSES)}


IDEA_ANGLES = (
    "ứng dụng hẹn hò", "shipper giao hàng", "chung cư / hàng xóm", "camera an ninh", "chatbot AI",
    "nhóm chat lớp / công ty", "đám cưới", "mẹ chồng nàng dâu", "livestream bán hàng", "taxi đêm",
    "bệnh viện", "nhập ngũ / đi lính", "du học", "tiền ảo / đầu tư", "thẻ ngân hàng bị khoá",
    "tin nhắn nhầm người", "tài khoản mạng xã hội bị hack", "phòng trọ giá rẻ", "đồ cũ mua trên mạng",
    "người yêu cũ", "con cái giấu bố mẹ", "bố mẹ giấu con cái", "phỏng vấn xin việc", "sếp mới",
    "kỳ thi đại học", "chuyến du lịch", "xe công nghệ", "bảo hiểm", "tiệm bánh / quán ăn nhỏ",
    "hội phụ huynh", "thú cưng", "người lạ tốt bụng", "trúng thưởng", "nhà vệ sinh công cộng",
    "thang máy", "cửa hàng tiện lợi ca đêm", "đi xem mắt", "bạn thân", "di chúc / tài sản",
    "điện thoại nhặt được", "định vị GPS", "tin nhắn lúc 3 giờ sáng", "đơn đặt hàng lạ",
)


def ideas(genre: str = "", lang: str = "ko", avoid: list | None = None, count: int = 6,
          style: str = "saeon") -> list[dict]:
    """AI nghĩ một loạt ý tưởng truyện để tham khảo; mỗi lần một góc nhìn ngẫu nhiên khác,
    tránh lặp các ý đã gợi ý (avoid = tên các ý trước)."""
    import random
    from . import claude_cli
    rnd = random.SystemRandom()
    angles = rnd.sample(IDEA_ANGLES, 5)
    g = GENRES.get(genre) or "Mọi thể loại: " + "; ".join(GENRES.values())
    avoid = [str(a)[:120] for a in (avoid or []) if a][-40:]
    data = claude_cli._run_json(claude_cli._load_prompt(
        "webtoon_ideas", lang_label=LANGS.get(lang, lang), genre=g, count=str(max(3, min(10, count))),
        angles="\n".join(f"- {a}" for a in angles), avoid="\n".join(f"- {a}" for a in avoid) or "(chưa có)",
        genre_ids=" | ".join(GENRES),
        style_hint=("Kiểu 사연: NHÂN VẬT CHÍNH tự kể chuyện đời mình (ngôi thứ nhất, tâm sự với người xem) — "
                    "chuyện hôn nhân, nhà chồng / nhà vợ, con cái, tiền bạc, công việc, bạn bè, hàng xóm...; "
                    "nhiều chuyện nhỏ có thật leo thang dần, cao trào nhân vật chính lên tiếng thẳng thắn (사이다), "
                    "kết có hậu cho nhân vật chính và một câu ngẫm nghĩ." if style == "saeon" else "")),
        task="story", timeout=300)
    out = []
    for it in (data.get("ideas") if isinstance(data, dict) else None) or []:
        if not isinstance(it, dict) or not it.get("brief"):
            continue
        out.append({"title": str(it.get("title") or "")[:160], "hook": str(it.get("hook") or "")[:300],
                    "brief": str(it.get("brief") or "")[:900], "why": str(it.get("why") or "")[:300],
                    "genre": it.get("genre") if it.get("genre") in GENRES else (genre if genre in GENRES else "thriller")})
    if not out:
        raise RuntimeError("AI chưa nghĩ được ý tưởng nào, bấm lại thử.")
    return out


def _cast_block(st: dict) -> str:
    """Làm series: nhân vật + địa điểm đã có ở các phần trước, dặn AI giữ nguyên."""
    if not (st.get("prev_summary") or "").strip() or not st.get("characters"):
        return ""
    cs = "\n".join(f"- {c['id']}: {c.get('name')} — {json.dumps(c.get('look') or {}, ensure_ascii=False)}"
                   f", home: {c.get('home') or ''}" for c in st.get("characters") or [])
    ps = "\n".join(f"- {p['id']}: {p.get('name')} — kind {p.get('kind')}, time {p.get('time')}, look: {p.get('look') or ''}"
                   for p in st.get("places") or [])
    return ("\n### Nhân vật và địa điểm ĐÃ CÓ từ phần trước — GIỮ NGUYÊN id, tên, look (chép y nguyên vào "
            "output), chỉ thêm người / nơi mới nếu truyện cần\n" + cs + ("\n" + ps if ps else ""))


def episode_summary(st: dict) -> str:
    """Tóm tắt tập vừa viết (để làm phần sau): tên tập + diễn biến từng đoạn + nhân vật."""
    segs = [str(s.get("summary") or "").strip() for s in st.get("segments") or []]
    segs = [x for x in segs if x]
    if not segs:
        return ""
    names = ", ".join(f"{c.get('name')} ({c['id']})" for c in st.get("characters") or [] if c.get("name"))
    head = f"Phần {int(st.get('part') or 1)}" + (f" – {st['title']}" if st.get("title") else "") + ":"
    tail = "Phần này dừng ở: " + segs[-1] if st.get("cliffhanger", True) else ""
    return " ".join([head] + segs[:-1] + ([] if tail else segs[-1:])) + (" " + tail if tail else "") + \
        (f" Nhân vật: {names}." if names else "")


def summarize_ai(st: dict) -> str:
    """Tập cũ chưa có tóm tắt: AI đọc thoại các cảnh rồi tóm tắt (tiếng Việt)."""
    from . import claude_cli
    lines = [f"{(s.get('line') or {}).get('who')}: {(s.get('line') or {}).get('text')}"
             for s in st.get("shots") or [] if (s.get("line") or {}).get("text")]
    if not lines:
        raise RuntimeError("Tập này chưa có thoại nào để tóm tắt.")
    names = "\n".join(f"- {c['id']}: {c.get('name')}" for c in st.get("characters") or [])
    p = ("Tóm tắt nội dung tập truyện dưới đây bằng TIẾNG VIỆT, 4–8 câu, đủ để viết tiếp phần sau: "
         "ai là ai, chuyện gì đã xảy ra, bí mật / manh mối nào đã lộ, tập DỪNG ở đâu (cú sốc cuối). "
         "Không thêm chi tiết không có trong thoại.\n"
         f"Tên tập: {st.get('title') or ''}\nNhân vật:\n{names}\nThoại:\n" + "\n".join(lines[:400]) +
         '\n\nOutput JSON đúng dạng: {"summary":"..."}')
    data = claude_cli._run_json(p, task="story", timeout=300)
    out = str((data or {}).get("summary") or "").strip() if isinstance(data, dict) else ""
    if not out:
        raise RuntimeError("AI chưa tóm tắt được, bấm lại thử.")
    return f"Phần {int(st.get('part') or 1)}" + (f" – {st['title']}" if st.get("title") else "") + ": " + out


def write(st: dict, progress=None) -> dict:
    """AI viết truyện: dàn ý + nhân vật + địa điểm, rồi phân cảnh từng đoạn."""
    from . import claude_cli
    say = progress or (lambda f, m: None)
    minutes = max(1.0, min(20.0, float(st.get("minutes") or 4)))
    lang = st.get("language") or "ko"
    cat = _catalog()
    part = int(st.get("part") or 1)
    prev = (st.get("prev_summary") or "").strip()
    saeon = (st.get("style") or "saeon") == "saeon"
    style_block = claude_cli._load_prompt("webtoon_style_saeon") if saeon else ""
    narrator_rule = ('id của NHÂN VẬT CHÍNH — người tự kể chuyện (bắt buộc, nhân vật chính đặt ĐẦU danh sách '
                     '"characters"; phần sau của series giữ đúng người kể cũ).' if saeon else
                     "true nếu cần người kể dẫn chuyện (ít câu), false nếu toàn thoại.")
    say(0.03, "AI nghĩ câu chuyện, nhân vật, địa điểm")
    plan_ = claude_cli._run_json(claude_cli._load_prompt(
        "webtoon_plan", minutes=f"{minutes:g}", part=str(part), lang_label=LANGS.get(lang, lang),
        brief=(st.get("brief") or "(tự nghĩ một chuyện hay theo thể loại)") +
              (f"\nTên tập đã chọn: \"{st['title']}\" — giữ đúng tên này, viết truyện khớp với tên."
               if (st.get("title") or "").strip() else ""),
        genre=GENRES.get(st.get("genre"), st.get("genre") or ""),
        prev_block=(f"### Tóm tắt các phần trước (viết tiếp, giữ đúng nhân vật)\n{prev}" if prev else "")
                   + _cast_block(st),
        ending_rule=("Đoạn cuối DỪNG ở cao trào / cú sốc, bỏ lửng cho người xem chờ phần sau."
                     if st.get("cliffhanger", True) else "Đoạn cuối kết trọn vẹn."),
        style_block=style_block, narrator_rule=narrator_rule,
        **cat), task="story", timeout=600)
    if not isinstance(plan_, dict) or not plan_.get("segments"):
        raise RuntimeError("AI không lập được dàn ý.")
    st["title"] = st.get("title") or str(plan_.get("title") or "")[:120]
    st["hook"] = str(plan_.get("hook") or "")[:300]
    old_c = {c["id"]: c for c in st.get("characters") or []} if prev else {}
    old_p = {p["id"]: p for p in st.get("places") or []} if prev else {}
    st["characters"] = [{"id": wa_slug(c.get("id") or c.get("name")), "name": str(c.get("name") or ""),
                         "look": wa.Look.from_dict(c.get("look")).to_dict(), "voice": c.get("voice") or {},
                         "home": wa_slug(c.get("home")) if c.get("home") else ""}
                        for c in plan_.get("characters") or [] if isinstance(c, dict)][:6]
    # làm series: nhân vật cũ giữ nguyên ngoại hình, giọng (ảnh AI, giọng mẫu gắn theo id)
    st["places"] = [{"id": wa_slug(p.get("id") or p.get("name")), "name": str(p.get("name") or ""),
                     "kind": p.get("kind") if p.get("kind") in PLACE_KINDS else "phong_khach",
                     "time": "dem" if p.get("time") == "dem" else "ngay",
                     "look": str(p.get("look") or "")[:500]}
                    for p in plan_.get("places") or [] if isinstance(p, dict)][:8]
    if old_c:
        st["characters"] = [dict(old_c[c["id"]], home=c.get("home") or old_c[c["id"]].get("home", ""))
                            if c["id"] in old_c else c for c in st["characters"]]
        st["characters"] += [c for cid, c in old_c.items()
                             if cid not in {x["id"] for x in st["characters"]}][:max(0, 8 - len(st["characters"]))]
    if old_p:
        st["places"] = [old_p[p["id"]] if p["id"] in old_p else p for p in st["places"]]
        st["places"] += [p for pid, p in old_p.items() if pid not in {x["id"] for x in st["places"]}]
        st["places"] = st["places"][:10]
    if saeon:
        if not any(p["id"] == "spot" for p in st["places"]):        # nền trơn có vòng sáng lúc kể chuyện
            st["places"].insert(0, {"id": "spot", "name": "Nền kể chuyện", "kind": "spot", "time": "ngay", "look": ""})
        ids0 = [c["id"] for c in st["characters"]]
        n = wa_slug(plan_.get("narrator")) if isinstance(plan_.get("narrator"), str) else ""
        keep = st.get("narrator_id") if prev and st.get("narrator_id") in ids0 else ""
        st["narrator_id"] = keep or (n if n in ids0 else (ids0[0] if ids0 else ""))
    else:
        st["narrator_id"] = ""
    segs = [s for s in plan_.get("segments") or [] if isinstance(s, dict)][:20]
    st["segments"] = segs
    st["summary"] = episode_summary(st)
    ids = {c["id"] for c in st["characters"]}
    chars_txt = "\n".join(f"- {c['id']}: {c['name']} — {c['look']['sex']}, {c['look']['age']}, "
                          f"{c['look']['hair']}, áo {c['look']['top_color']} — ở {c.get('home') or '?'}"
                          for c in st["characters"])
    places_txt = "\n".join(f"- {p['id']}: {p['name']} — {p['kind']}, {p['time']}" for p in st["places"])
    nid = st.get("narrator_id") or ""
    nname = next((c["name"] for c in st["characters"] if c["id"] == nid), nid)
    if saeon and nid:
        style_rule = (f"- KIỂU 사연: người kể là NHÂN VẬT CHÍNH {nname} (id {nid}), tự kể ở ngôi thứ nhất (저는..., đuôi -요), "
                      f"câu kể ghi \"line\":{{\"who\":\"narr\",...}}; khoảng 35–45% số câu là lời kể, xen kẽ với thoại — "
                      "kể một hai câu rồi cho nhân vật nói, không kể một mạch dài.\n"
                      f"- Câu kể: cảnh cận / nửa người {nname} (\"who\":\"{nid}\") với nét mặt đúng cảm xúc câu kể, HOẶC cảnh minh hoạ "
                      "đúng chuyện đang kể (ai đang làm gì, ở đâu). Mở đầu video và mỗi khi bắt đầu chuyện mới (tự giới thiệu, "
                      f"nhận xét, ngẫm nghĩ) dùng \"place\":\"spot\" (nền trơn có vòng sáng) cận {nname}.\n"
                      "- Hai người ngồi bàn (quán cà phê, bàn ăn) đối đáp: \"type\":\"two\", \"front\":\"table\"; "
                      "trên giường: \"front\":\"bed\".")
    else:
        style_rule = '- Người kể ("who":"narr") rất ít.'
    if nid:
        chars_txt = chars_txt.replace(f"- {nid}: ", f"- {nid} (NHÂN VẬT CHÍNH, người kể): ", 1)
    outline = "\n".join(f"{i + 1}. {s.get('summary')}" for i, s in enumerate(segs))
    per = minutes * 60 / max(1, len(segs))
    shots: list = []
    for i, sg in enumerate(segs):
        say(0.1 + 0.85 * i / len(segs), f"AI phân cảnh đoạn {i + 1}/{len(segs)}")
        before = [f"{(s.get('line') or {}).get('who')}: {(s.get('line') or {}).get('text')}"
                  for s in shots[-14:] if (s.get("line") or {}).get("text")]
        data = claude_cli._run_json(claude_cli._load_prompt(
            "webtoon_shots", lang_label=LANGS.get(lang, lang), title=st["title"], hook=st["hook"],
            outline=outline, characters=chars_txt, places=places_txt, index=str(i + 1),
            summary=str(sg.get("summary") or ""), seconds=str(int(per)), shots=str(max(6, int(per / 2.6))),
            segment_rule=("Mở video bằng MÓC CÂU." if i == 0 else "") +
                         (" Đây là đoạn CUỐI: dừng ở cú sốc, cảnh cuối là một câu bỏ lửng."
                          if i == len(segs) - 1 and st.get("cliffhanger", True) else ""),
            before_block=("### Thoại ngay trước đó (nối tiếp, không lặp lại)\n" + "\n".join(before)) if before else "",
            style_rule=style_rule, **cat), task="story", timeout=600)
        got = data.get("shots") if isinstance(data, dict) else None
        if not got:
            raise RuntimeError(f"AI không phân cảnh được đoạn {i + 1}.")
        shots += [s for s in got if isinstance(s, dict)]
    st["shots"] = [clean_shot(s, ids, k) for k, s in enumerate(shots)]
    fix_places(st)
    say(1.0, "xong")
    return st


def fix_places(st: dict) -> None:
    """Người nói qua điện thoại phải ở nơi của mình: cảnh cận mặt một người đang nghe gọi
    mà lại đặt ở nơi thường ở của người khác (trong khi người đó có nơi riêng) thì chuyển
    về nơi của người nói."""
    places = {p["id"] for p in st.get("places") or []}
    home = {c["id"]: c.get("home") for c in st.get("characters") or [] if c.get("home") in places}
    owner = {}
    for cid, pl in home.items():
        owner.setdefault(pl, set()).add(cid)
    first = (st.get("places") or [{}])[0].get("id")
    for s in st.get("shots") or []:
        if s.get("place") not in places:
            s["place"] = home.get(s.get("who")) or first
        who = s.get("who")
        if s.get("type") in ("close", "medium") and who in home and s.get("pose") in ("phone_ear", "phone_look"):
            here = owner.get(s["place"], set())
            if here and who not in here:          # đang ở "nhà" của người khác: về nơi của mình
                s["place"] = home[who]
    # cảnh "hai người" mà AI quên ghi người thứ hai: lấy người vừa nói gần nhất ở cùng chỗ
    shots = st.get("shots") or []
    for k, s in enumerate(shots):
        if s.get("type") != "two" or s.get("with"):
            continue
        for p in reversed(shots[:k]):
            o = (p.get("line") or {}).get("who") or p.get("who")
            if o and o != s.get("who") and o != "narr" and p.get("place") == s.get("place"):
                s["with"] = [o]
                break


def wa_slug(v) -> str:
    from .story import _slug
    return _slug(v)
