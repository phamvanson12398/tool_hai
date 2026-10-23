# -*- coding: utf-8 -*-
"""Dựng video 9:16 từ timeline: nhân vật, nhép miệng, nhún, zoom, phụ đề, tiếng động, nhạc nền.

Phương án: tạo từng khung hình bằng Pillow (nền + nhân vật + phụ đề), rồi ghép bằng ffmpeg.
Đây là cách chạy ổn định nhất trên Windows mà không cần GPU cho phần render.
"""
from __future__ import annotations

import json
import logging
import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from . import config

# Thêm import cho cử động (Bước D)
try:
    from . import rig as rig_mod
    from . import gestures as gmod
    from . import photo_rig
    from .character_kit import CharSpec
    RIG_AVAILABLE = True
except Exception:
    RIG_AVAILABLE = False

logger = logging.getLogger(__name__)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgunbd.ttf",   # tiếng Hàn, đậm
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
]


# Chữ tiếng Việt có dấu (ă â đ ê ô ơ ư và các dấu thanh) — font Hàn Malgun
# không vẽ đủ các chữ này nên phải dùng font Latin đầy đủ.
_VI_CHARS = re.compile(r"[ăâđêôơưĂÂĐÊÔƠƯ\u1ea0-\u1ef9]")


def has_vietnamese(text: str) -> bool:
    return bool(_VI_CHARS.search(text or ""))


def _sit_geom(anim) -> tuple[float, float, float, float] | None:
    """(cao khung gốc, hạ người bao nhiêu, mặt ghế ở đâu, vai ở đâu) khi ngồi
    hẳn, theo toạ độ khung gốc của nhân vật. Hạ người sao cho chân vẫn chạm
    sàn; mặt ghế ngay dưới hông; vai để đặt mặt bàn ngang khuỷu tay."""
    cached = getattr(anim, "_sit_cache", None)
    if cached is not None:
        return cached or None
    from .gestures import SIT_DUI_DEG
    a = math.radians(SIT_DUI_DEG)
    out = ()
    try:
        rig = getattr(anim, "rig", None)
        if rig is not None:                       # nhân vật bộ ghép
            from .gestures import mirror_left
            from .rig import CH
            sit = mirror_left({"dui_left": -a, "dui_right": -a, "goi_left": a, "goi_right": a})
            w0, w1 = rig.solve({}), rig.solve(sit)
            drop = max(w0[b]["pivot"][1] - w1[b]["pivot"][1]
                       for b in ("co_chan_left", "co_chan_right"))
            hip = w0["than"]["pivot"][1]
            out = (float(CH), drop, hip + drop + 0.03 * CH,
                   w0["vai_right"]["pivot"][1] + drop, hip)
        elif getattr(anim, "pchar", None) is not None:   # ảnh tải lên
            j = anim.pchar.joints
            fh = float(anim.pchar.rgba.size[1])
            thigh = math.dist(j.hip_r, j.knee_r)
            drop = thigh * (1 - math.cos(a))
            out = (fh, drop, j.hip_r[1] + drop + 0.03 * fh, j.shoulder_r[1] + drop,
                   float(j.hip_r[1]))
    except Exception:  # noqa: BLE001
        out = ()
    anim._sit_cache = out
    return out or None


# Mức quay khi hai người nói chuyện (1 = quay hẳn vào nhau)
TURN_TALK = 1.0
# Quay hẳn sang thì bề ngang người hẹp lại bấy nhiêu (trông như đứng nghiêng)
BODY_SQUEEZE = 0.16


def _sprite(img: Image.Image | None):
    """Cắt lớp trong suốt cỡ khung về sát nội dung: (ảnh, x, y) hoặc None."""
    if img is None:
        return None
    box = img.getbbox()
    if not box:
        return None
    return img.crop(box), box[0], box[1]


def find_font(bold: bool = True, vietnamese: bool = False) -> str:
    cands = [f for f in FONT_CANDIDATES if not (vietnamese and "malgun" in f)]
    for f in cands:
        if Path(f).exists():
            if bold and "bd" not in f and "bold" not in f and "b.ttf" not in f:
                continue
            return f
    for f in cands:
        if Path(f).exists():
            return f
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            if bold and "bd" not in f and "bold" not in f and "b.ttf" not in f:
                continue
            return f
    # fallback: bất kỳ font nào
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return f
    return FONT_CANDIDATES[0]


# ---------------------------------------------------------------- nhân vật

@dataclass
class Character:
    name: str
    side: str                       # "left" | "center" | "right"
    image: Path                     # ảnh mặc định (biểu cảm neutral, miệng ngậm)
    mouth_open: Path | None = None
    mouth_closed: Path | None = None
    mouth_pos: tuple[int, int] | None = None   # (x, y) tọa độ miệng trên ảnh
    scale: float = 1.0
    # {biểu cảm: {"mo": path, "dong": path}} — có khi dùng bộ ảnh hoặc bộ ghép
    images: dict[str, dict[str, str]] = field(default_factory=dict)
    # --- cử động (Bước D) ---
    rig_animator: object | None = None   # có render_frame(t, speaking, mouth_open)

    def frame(self, expression: str, speaking: bool) -> Path:
        """Ảnh đúng biểu cảm và trạng thái miệng.

        Nhân vật tải lên bằng 1 ảnh thì không có bảng `images`, nên luôn trả về
        ảnh đó (chỉ nhép miệng được, không đổi biểu cảm).
        """
        key = "mo" if speaking else "dong"
        if self.images:
            slot = self.images.get(expression) or self.images.get("neutral")
            if not slot:
                slot = next(iter(self.images.values()))
            p = slot.get(key) or slot.get("dong") or slot.get("mo")
            if p and Path(p).exists():
                return Path(p)
        if speaking and self.mouth_open:
            return self.mouth_open
        if not speaking and self.mouth_closed:
            return self.mouth_closed
        return self.image

    def all_images(self) -> list[Path]:
        """Mọi ảnh của nhân vật (để đóng gói cho CapCut)."""
        out: list[Path] = []
        for slot in self.images.values():
            for p in slot.values():
                if p:
                    out.append(Path(p))
        for p in (self.image, self.mouth_open, self.mouth_closed):
            if p:
                out.append(Path(p))
        return out


# ---------------------------------------------------------------- timeline

@dataclass
class Line:
    idx: int
    speaker: str
    text: str
    expression: str = "neutral"
    zoom: bool = False
    sfx: str | None = None
    start: float = 0.0
    duration: float = 0.0
    audio: Path | None = None
    words: list[tuple[str, float, float]] = field(default_factory=list)  # (từ, bắt đầu, kết thúc)
    zoom_target: str = ""           # zoom vào người này (nếu khác người nói)
    other_expr: dict[str, str] = field(default_factory=dict)  # Tên -> biểu cảm
    # --- cử động (Bước D) ---
    gestures: list[str] = field(default_factory=list)   # cử chỉ: vaytay, omdau...
    effects: list[str] = field(default_factory=list)    # hiệu ứng cả người
    scene: int = 0                  # bối cảnh của câu (chỉ số Script.scenes)
    props: dict[str, str] = field(default_factory=dict)  # đạo cụ đổi ở câu này
    shot: str = ""                  # góc máy ghi trong kịch bản ("" = tự chọn)


@dataclass
class Beat:
    """Nhịp phản ứng không lời (dòng '>')."""
    idx: int
    actor: str = ""                 # ai phản ứng
    expression: str = "shocked"
    zoom: bool = False
    sfx: str | None = None
    start: float = 0.0
    duration: float = 0.8
    scene: int = 0
    gestures: list[str] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)
    props: dict[str, str] = field(default_factory=dict)
    shot: str = ""


@dataclass
class Timeline:
    lines: list[Line] = field(default_factory=list)
    beats: list[Beat] = field(default_factory=list)
    total: float = 0.0
    # ai có mặt ở từng bối cảnh (None = mọi nhân vật), theo chỉ số cảnh
    scene_cast: list = field(default_factory=list)

    def present(self, scene: int, names: list[str]) -> list[str]:
        """Tên những người có mặt ở bối cảnh này (giữ thứ tự names)."""
        who = self.scene_cast[scene] if 0 <= scene < len(self.scene_cast) else None
        out = [n for n in names if who is None or n in who]
        return out or list(names)


# ---------------------------------------------------------------- khung hình

class Stage:
    """Khung hình (9:16, 16:9 hoặc 1:1): bối cảnh + nhân vật + phụ đề."""

    def __init__(self, width: int = config.WIDTH, height: int = config.HEIGHT):
        self.w, self.h = width, height
        self.layout = config.stage_layout(width, height)
        self.unit = min(width, height) / 1080     # cỡ chữ, viền... theo cạnh ngắn
        self.bg: Image.Image | None = None
        # nhiều bối cảnh: chỉ số cảnh -> ảnh nền (cảnh không có thì dùng self.bg)
        self.scene_bgs: dict[int, Image.Image] = {}
        self.scene = 0
        # máy quay ảo: (độ phóng, tâm x, tâm y) theo toạ độ khung gốc
        self.cam = (1.0, width / 2, height / 2)
        self.ots: tuple | None = None        # (nhân vật quay lưng, bên trái?) cho cảnh qua vai
        self.title = ""
        self.subtitle_style = config.SUBTITLE_STYLES["yellow"]
        self.subtitle_pos = "tren"          # tren | duoi
        self.font = find_font(bold=True)
        self.font_small = find_font(bold=False)
        self.font_vi = find_font(bold=True, vietnamese=True)
        self._char_cache: dict[tuple, Image.Image] = {}
        # chỗ ngồi theo bối cảnh: chỉ số cảnh -> loại (office, sofa...), màu
        self.scene_seats: dict[int, str] = {}
        self.scene_colors: dict[int, tuple] = {}
        self.seat_fallback = False            # ngồi ở cảnh không có ghế: tự đặt ghế gỗ
        self.t = 0.0                          # thời điểm khung đang dựng
        self._seat_cache: dict = {}
        self._sprite_cache: dict = {}

    # ------------------------------------------------------ chỗ ngồi
    def _seating(self, chars: list["Character"]) -> dict | None:
        """Đồ đạc + độ hạ người khi ngồi cho các nhân vật ở cảnh hiện tại.

        Cảnh không có bàn ghế mà có người ngồi (kịch bản ghi ngoi_ghe): đặt
        một chiếc ghế gỗ dưới đúng người đang ngồi."""
        seat = self.scene_seats.get(self.scene)
        sitting = None
        if not seat and self.seat_fallback:
            from .gestures import sit_amount
            sitting = tuple(c.name for c in chars if c.rig_animator is not None
                            and sit_amount(c.rig_animator, self.t) > 0)
            if not sitting:
                return None
            seat = "chair"
        key = (self.scene, seat, tuple(c.name for c in chars), sitting)
        if key in self._seat_cache:
            return self._seat_cache[key]
        out = None
        n = len(chars)
        rows = []
        if seat and n:
            slots = self.slots(n)
            base_y = self.floor_y
            for i, ch in enumerate(chars):
                if sitting is not None and ch.name not in sitting:
                    continue
                g = _sit_geom(ch.rig_animator) if ch.rig_animator is not None else None
                if not g:
                    continue
                fh, drop, seat_c, sh_c, hip_c = g
                th = self.char_h(n, ch.scale)
                sc = th / fh
                rows.append([ch.name, self.w * slots[i], base_y - th + seat_c * sc,
                             drop * sc, th, base_y - th + sh_c * sc,
                             base_y - th + hip_c * sc])
        if rows:
            from . import furniture
            standing = seat in furniture.STANDING
            if standing:                # quầy: cao ngang hông người đứng
                for r in rows:
                    r[2] = r[6]
            if seat in furniture.SHARED:
                top = min(r[2] for r in rows)
                for r in rows:          # cùng một mặt sofa: người thấp ngồi cao lên
                    r[3] += top - r[2]
                    r[5] += top - r[2]
                    r[2] = top
            k = sum(r[4] for r in rows) / len(rows) / 160.0
            back, front = furniture.draw(seat, [(r[1], r[2], r[5]) for r in rows], k,
                                         self.floor_y, (self.w, self.h),
                                         self.scene_colors.get(self.scene))
            out = {"drops": {} if standing else {r[0]: r[3] for r in rows},
                   "back": _sprite(back), "front": _sprite(front)}
        self._seat_cache[key] = out
        return out

    def seat_drop(self, ch: "Character", chars: list["Character"]) -> float:
        """Người đang ngồi được hạ xuống bao nhiêu px (theo mức đang ngồi)."""
        anim = ch.rig_animator
        if anim is None:
            return 0.0
        from .gestures import sit_amount
        p = sit_amount(anim, self.t)
        if p <= 0:
            return 0.0
        lay = self._seating(chars)
        if lay and ch.name in lay["drops"]:
            return p * lay["drops"][ch.name]
        g = _sit_geom(anim)            # ngồi ở cảnh không có đồ đạc
        if not g:
            return 0.0
        return p * g[1] * self.char_h(len(chars), ch.scale) / g[0]

    def draw_furniture(self, img: Image.Image, chars: list["Character"],
                       layer: str) -> Image.Image:
        """Vẽ lớp đồ đạc 'back' (ghế, sofa) hoặc 'front' (bàn) theo góc máy."""
        lay = self._seating(chars)
        sp = lay.get(layer) if lay else None
        if not sp:
            return img
        im, x0, y0 = sp
        s = self.cam[0]
        if s > 1.001:
            key = (id(im), round(s, 3))
            hit = self._sprite_cache.get(key)
            if hit is None:
                if len(self._sprite_cache) > 64:
                    self._sprite_cache.clear()
                hit = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))),
                                Image.BILINEAR)
                self._sprite_cache[key] = hit
            im = hit
        img.paste(im, self._cam_map(x0, y0), im)
        return img

    # ------------------------------------------------------ bố cục theo khung
    def slots(self, n: int) -> list[float]:
        return self.layout["slots"].get(n) or [(i + 1) / (n + 1) for i in range(n)]

    @property
    def floor_y(self) -> int:
        return int(self.h * self.layout["floor"])

    def char_h(self, n: int, scale: float = 1.0) -> int:
        """Chiều cao người (khung gốc nhân vật) trên khung hình."""
        hi, lo = self.layout["height"]
        return int(self.h * (hi if n < 3 else lo) * scale)

    def set_background(self, path: Path) -> None:
        self.bg = self._fit(path)

    def set_scene_backgrounds(self, paths: dict[int, Path]) -> None:
        """Ảnh nền cho từng bối cảnh (theo chỉ số cảnh trong kịch bản)."""
        self.scene_bgs = {i: self._fit(Path(p)) for i, p in paths.items()
                          if p and Path(p).exists()}

    def background_for(self, scene: int) -> Image.Image | None:
        return self.scene_bgs.get(scene) or self.bg

    def _fit(self, path: Path) -> Image.Image:
        img = Image.open(path).convert("RGB")
        # cắt và căn cho đầy khung 9:16
        tw, th = self.w, self.h
        ir = img.width / img.height
        tr = tw / th
        if ir > tr:
            nw = int(img.height * tr)
            x = (img.width - nw) // 2
            img = img.crop((x, 0, x + nw, img.height))
        else:
            nh = int(img.width / tr)
            y = (img.height - nh) // 2
            img = img.crop((0, y, img.width, y + nh))
        return img.resize((tw, th), Image.LANCZOS)

    def blank(self, scene: int | None = None, prev_scene: int | None = None,
              mix: float = 1.0) -> Image.Image:
        """Nền của khung: ảnh của cảnh hiện tại, chuyển mờ từ cảnh trước
        nếu mix < 1."""
        cur = self.background_for(self.scene if scene is None else scene)
        img = cur.copy() if cur else Image.new("RGB", (self.w, self.h), (30, 30, 40))
        if prev_scene is not None and mix < 1.0:
            prev = self.background_for(prev_scene)
            if prev is not None and prev is not cur:
                img = Image.blend(prev, img, max(0.0, min(1.0, mix)))
        s, cx, cy = self.cam
        if s > 1.001:
            w, h = self.w / s, self.h / s
            box = (int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2))
            img = img.crop(box).resize((self.w, self.h), Image.BILINEAR)
        return img

    # ------------------------------------------------------ máy quay ảo
    def _cam_map(self, x: float, y: float) -> tuple[int, int]:
        s, cx, cy = self.cam
        return int((x - cx) * s + self.w / 2), int((y - cy) * s + self.h / 2)

    def anchors(self, chars: list["Character"]) -> dict[str, tuple[float, float, float]]:
        """Vị trí từng nhân vật trên sân khấu: {tên: (x giữa, y đầu, cao người)}."""
        n = len(chars)
        out = {}
        if not n:
            return out
        slots = self.slots(n)
        base_y = self.floor_y
        for i, ch in enumerate(chars):
            target_h = self.char_h(n, ch.scale)
            ratio = 0.22
            anim = ch.rig_animator
            spec = getattr(getattr(anim, "rig", None), "spec", None)
            if spec:
                try:
                    from .rig import geometry, CH
                    g = geometry(spec.get("body", "adult"), spec.get("style", "flat"))
                    ratio = g.head_cy / CH
                except Exception:  # noqa: BLE001
                    pass
            last = getattr(anim, "last_angles", None) or {}
            x = self.w * slots[i] + last.get("dich_x", 0.0) * self.w
            head_y = base_y - target_h + ratio * target_h - last.get("dich_y", 0.0) * self.h
            hp = getattr(anim, "head_pos", None)
            if hp:
                # vị trí đầu thật của khung trước (nằm, bò, ngã vẫn quay trúng mặt)
                from .rig import CH, CW
                k = target_h / CH
                x += (hp[0] - CW / 2) * k
                head_y = base_y - target_h + hp[1] * k - last.get("dich_y", 0.0) * self.h
            out[ch.name] = (x, head_y + self.seat_drop(ch, chars), target_h)
        return out

    def _shot(self, shot: str) -> tuple[float, float]:
        """(độ phóng, tâm máy thấp hơn đầu bao nhiêu px) cho khung này.

        SHOTS chỉnh theo khung dọc 9:16. Khung khác (người to hơn so với
        chiều cao khung) phóng ít hơn để mặt to như nhau, và giữ đầu ở cùng
        độ cao trên màn hình, nên phụ đề phía trên không đè lên mặt."""
        s, dy = SHOTS[shot]
        portrait = 0.50
        k = portrait / self.layout["height"][0]
        s_eff = max(1.05, s * k)
        head_screen = 0.5 - dy * portrait * s          # vị trí đầu trên màn hình (0..1)
        return s_eff, (0.5 - head_screen) * self.h / s_eff

    def set_camera(self, shot: str, focus: str | None, chars: list["Character"],
                   other: str | None = None) -> None:
        """Đặt góc máy: toan (toàn cảnh), trung (nửa người), can (cận mặt),
        sieucan (siêu cận), quavai (qua vai người nghe)."""
        self.ots = None
        an = self.anchors(chars)
        if shot not in SHOTS or shot == "toan" or focus not in an:
            self.cam = (1.0, self.w / 2, self.h / 2)
            return
        s, off = self._shot(shot)
        x, head_y, th = an[focus]
        cx, cy = x, head_y + off
        if shot == "quavai" and other in an and other != focus:
            left = an[other][0] < x
            ch_other = next(c for c in chars if c.name == other)
            if getattr(ch_other.rig_animator, "back_head", None):
                self.ots = (ch_other, left)
                cx += (-1 if left else 1) * min(self.w, self.h) * 0.14 / s   # chừa chỗ cho gáy người nghe
            else:
                s, off = self._shot("can")
                cy = head_y + off
        hw, hh = self.w / (2 * s), self.h / (2 * s)
        cx = min(max(cx, hw), self.w - hw)
        cy = min(max(cy, hh), self.h - hh)
        self.cam = (s, cx, cy)

    def draw_ots(self, img: Image.Image) -> Image.Image:
        """Cảnh qua vai: gáy + vai người nghe to ở tiền cảnh, một bên dưới khung."""
        if not self.ots:
            return img
        ch, left = self.ots
        try:
            head, shirt = ch.rig_animator.back_head()
        except Exception:  # noqa: BLE001
            return img
        m = min(self.w, self.h)
        hw = int(m * 0.66)
        sc = hw / head.width
        head = head.resize((hw, max(1, int(head.height * sc))), Image.LANCZOS)
        x0 = int(-m * 0.16) if left else int(self.w - hw + m * 0.16)
        top = int(self.h - m * 0.78)
        d = ImageDraw.Draw(img)
        sx0, sx1 = x0 - int(m * 0.15), x0 + hw + int(m * 0.15)
        d.rounded_rectangle([sx0, top + int(head.height * 0.8), sx1, self.h + 200],
                            radius=int(m * 0.18), fill=shirt[:3], outline=(24, 22, 28),
                            width=max(4, int(10 * self.unit)))
        img.paste(head, (x0, top), head)
        return img

    def place_characters(self, img: Image.Image, chars: list[Character],
                         expressions: dict[str, str], active: str | None,
                         mouth_open: bool, t: float) -> Image.Image:
        """Đặt nhân vật theo bố cục; nhún nhẹ khi nói.

        2 người: trái và phải. 3 người: trái, giữa, phải và thu nhỏ một chút.
        """
        n = len(chars)
        if n == 0:
            return img
        slots = self.slots(n)
        base_y = self.floor_y

        for i, ch in enumerate(chars):
            cx = int(self.w * slots[i])
            speaking = (ch.name == active)
            # --- CỬ ĐỘNG (Bước D): nếu nhân vật có rig animator thì render theo
            # khung xương (cử chỉ + thở + cử động tay khi nói), giữ đầu cứng
            # để gắn biểu cảm + miệng như cũ.
            if ch.rig_animator is not None:
                try:
                    im = ch.rig_animator.render_frame(
                        t, speaking=speaking, mouth_open=bool(speaking and mouth_open),
                        expression=expressions.get(ch.name, "neutral"),
                    )
                    im = im.convert("RGBA")
                    anim = ch.rig_animator
                    # Khung gốc của nhân vật (không tính phần tay/chân giơ ra
                    # ngoài) cao ~50% khung hình, chân đứng ở base_y.
                    fw, fh = getattr(anim, "frame_size", None) or im.size
                    ox, oy = getattr(anim, "frame_origin", None) or (0, 0)
                    target_h = self.char_h(n, ch.scale)
                    sc = target_h / fh
                    cam_s = self.cam[0]
                    # quay sang người kia: ép hẹp bề ngang cả người như đứng nghiêng
                    sq = 1.0 - BODY_SQUEEZE * min(1.0, abs(getattr(anim, "turn", 0.0)))
                    im = im.resize((max(1, int(im.width * sc * cam_s * sq)),
                                    max(1, int(im.height * sc * cam_s))), Image.LANCZOS)
                    bounce = int(2 * math.sin(t * 1.6))
                    # dịch cả người theo cử chỉ (vào/ra khung, nhảy lên...)
                    last = getattr(anim, "last_angles", None) or {}
                    x = (cx - int(fw * sc * sq) // 2 - int(ox * sc * sq)
                         + int(last.get("dich_x", 0.0) * self.w))
                    y = (base_y - target_h - int(oy * sc) - bounce
                         - int(last.get("dich_y", 0.0) * self.h)
                         + int(self.seat_drop(ch, chars)))
                    img.paste(im, self._cam_map(x, y), im)
                    continue
                except Exception as e:  # lỗi cử động -> quay về ảnh tĩnh
                    from . import config as _cfg
                    _cfg.log_render(
                        f"Cử động lỗi cho nhân vật '{ch.name}': {e}. "
                        f"Quay lại cách dựng cũ (ảnh tĩnh).", "warning")
                    logger.warning(
                        "Cử động lỗi cho nhân vật '%s' (%s), quay lại ảnh tĩnh.",
                        ch.name, e,
                    )

            expr = expressions.get(ch.name, "neutral")
            # miệng chỉ mở khi người đó đang nói VÀ có tiếng
            path = ch.frame(expr, speaking and mouth_open)
            im = self._scaled(path, n, ch.scale)
            # nhún nhẹ khi nói, thở nhẹ khi im
            if speaking:
                bounce = int(7 * abs(math.sin(t * 7.5)))
            else:
                bounce = int(2 * math.sin(t * 1.6))

            # Nhân vật 1 ảnh: vẽ miệng đè lên + nhún nhẹ theo nhịp miệng
            if ch.mouth_pos and speaking:
                # Co giãn dọc 2-3% theo nhịp miệng
                scale_factor = 1.0 + (0.025 if mouth_open else -0.02)
                w, h = im.size
                new_h = int(h * scale_factor)
                im_scaled = im.resize((w, new_h), Image.LANCZOS)

                # Vẽ miệng đơn giản đè lên
                mouth_layer = Image.new("RGBA", im_scaled.size, (0, 0, 0, 0))
                d = ImageDraw.Draw(mouth_layer)
                mx, my = ch.mouth_pos
                # Toạ độ miệng scale theo resize ảnh nhân vật
                ow, oh = self._orig_size(path)
                mx = int(mx * w / ow)
                my = int(my * new_h / oh)

                # Miệng tối màu, kích thước theo tỉ lệ đầu (~5% chiều rộng ảnh)
                mouth_w = int(w * 0.05)
                mouth_h = int(mouth_w * (1.2 if mouth_open else 0.6))

                if mouth_open:
                    d.ellipse([mx - mouth_w, my - mouth_h//2,
                              mx + mouth_w, my + mouth_h//2],
                             fill=(60, 50, 50, 220))
                else:
                    d.line([mx - mouth_w, my, mx + mouth_w, my],
                          fill=(60, 50, 50, 220), width=max(2, mouth_w//4))

                im = Image.alpha_composite(im_scaled.convert("RGBA"), mouth_layer)

            x = cx - im.width // 2
            y = base_y - im.height - bounce
            if self.cam[0] > 1.001:
                im = im.resize((max(1, int(im.width * self.cam[0])),
                                max(1, int(im.height * self.cam[0]))), Image.LANCZOS)
            img.paste(im, self._cam_map(x, y), im)
        return img

    def _scaled(self, path: Path, n: int, scale: float) -> Image.Image:
        """Ảnh nhân vật đã resize — cache theo (file, kích thước)."""
        target_h = self.char_h(n, scale)
        key = (str(path), target_h)
        hit = self._char_cache.get(key)
        if hit is not None:
            return hit
        im = Image.open(path).convert("RGBA")
        ratio = target_h / im.height
        im = im.resize((max(1, int(im.width * ratio)), target_h), Image.LANCZOS)
        self._char_cache[key] = im
        return im

    def _orig_size(self, path: Path) -> tuple[int, int]:
        """Kích thước ảnh gốc (không resize) để quy đổi tọa độ miệng."""
        key = ("orig", str(path))
        hit = self._char_cache.get(key)
        if isinstance(hit, tuple):
            return hit  # type: ignore[return-value]
        with Image.open(path) as im:
            size = im.size
        self._char_cache[key] = size
        return size

    def _font_for(self, text: str) -> str:
        """Font Hàn mặc định; chữ tiếng Việt có dấu thì dùng font Latin đủ dấu."""
        return self.font_vi if has_vietnamese(text) else self.font

    def draw_title(self, img: Image.Image) -> Image.Image:
        if not self.title:
            return img
        d = ImageDraw.Draw(img)
        txt = self.title
        f = ImageFont.truetype(self._font_for(txt), max(24, int(64 * self.unit)))
        bbox = d.textbbox((0, 0), txt, font=f)
        tw = bbox[2] - bbox[0]
        x = (self.w - tw) // 2
        y = int(self.h * 0.06)
        # nền mờ để chữ nổi
        pad = 18
        box = [x - pad, y - pad, x + tw + pad, y + (bbox[3] - bbox[1]) + pad]
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rounded_rectangle(box, radius=18, fill=(0, 0, 0, 150))
        img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), (0, 0))
        d = ImageDraw.Draw(img)
        d.text((x, y), txt, font=f, fill=(255, 255, 255),
               stroke_width=3, stroke_fill=(0, 0, 0))
        return img

    def draw_subtitle(self, img: Image.Image, text: str) -> None:
        if not text:
            return
        d = ImageDraw.Draw(img)
        st = self.subtitle_style
        size = max(24, int(st["size"] * self.unit))
        f = ImageFont.truetype(self._font_for(text), size)
        # tự xuống dòng nếu dài (khung ngang: không trải hết bề ngang)
        max_w = min(self.w - 120, int(self.h * 1.25))
        words = text.split(" ")
        lines, cur = [], ""
        for wd in words:
            trial = (cur + " " + wd).strip()
            if d.textlength(trial, font=f) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        lh = int(size * 1.25)
        total_h = lh * len(lines)
        if self.subtitle_pos == "tren":
            # phía trên (như các kênh hoạt hình hài): dưới tiêu đề nếu có
            y = int(self.h * (0.15 if self.title else 0.085))
        else:
            y = int(self.h * 0.86) - total_h // 2
        for ln in lines:
            bbox = d.textbbox((0, 0), ln, font=f)
            tw = bbox[2] - bbox[0]
            x = (self.w - tw) // 2
            d.text((x, y), ln, font=f, fill=st["fill"],
                   stroke_width=max(2, int(5 * self.unit)), stroke_fill=st["outline"])
            y += lh


def _ffmpeg_path() -> str:
    """Đường dẫn lệnh ffmpeg: ưu tiên cài đặt, rồi mặc định "ffmpeg"."""
    try:
        s = config.load_settings().get("ffmpeg_bin")
        if s and str(s).strip():
            return str(s).strip()
    except Exception:
        pass
    return "ffmpeg"


# ---------------------------------------------------------------- render

SCENE_FADE = 0.35   # giây chuyển mờ khi đổi bối cảnh

# góc máy -> (độ phóng, tâm dọc lệch xuống so với đầu, theo chiều cao người)
SHOTS = {
    "toan": (1.0, 0.0),
    "trung": (1.5, 0.3),
    "can": (2.05, 0.13),
    "sieucan": (2.7, 0.03),
    "quavai": (1.85, 0.16),
}
# cử chỉ cần thấy cả người -> toàn cảnh; cử chỉ phần trên -> nửa người
_FULL_BODY = {"nam", "bo", "ngoi", "om_goi", "nga_ngua", "nhaylen", "dibo", "chay",
              "vao_trai", "vao_phai", "ra_trai", "ra_phai", "voi", "dam_dat"}
_UPPER = {"vaytay", "chitay", "omdau", "khoanhtay", "giohaitay", "voratay", "nhunvai",
          "xem_dt", "cam_tai", "bung", "cam_coc", "gio_do", "an", "ve_tu_the"}
_STRONG = {"shocked", "scared", "angry", "crying", "surprised", "disgusted"}


def plan_shots(timeline: "Timeline", n_chars: int, auto: bool = True,
               names: list[str] | None = None) -> dict:
    """Chọn góc máy cho từng câu / nhịp như phim hoạt hình hài ngắn.

    Kịch bản ghi goc=... thì theo kịch bản. Tự chọn: mở đầu toàn cảnh; cử chỉ
    cả người -> toàn cảnh; cử chỉ tay / cầm đồ -> nửa người; câu zoom hoặc
    phản ứng mạnh -> cận/siêu cận; hội thoại xen kẽ qua vai và cận mặt; cứ
    vài câu lại về toàn cảnh cho khán giả định vị. Vào cảnh mới -> toàn
    cảnh; cắt qua lại giữa hai nơi (gọi điện) thì không bắt về toàn cảnh.
    Cảnh chỉ có một số người: chỉ đếm và qua vai người có mặt ở đó.
    Trả về {("line"|"beat", idx): (góc, người được quay, người nghe)}.
    """
    events = sorted([(ln.start, "line", ln) for ln in timeline.lines] +
                    [(b.start, "beat", b) for b in timeline.beats], key=lambda e: e[0])
    out: dict = {}
    prev_scene, since_wide = None, 0
    visited: set = set()
    last_in: dict = {}          # cảnh -> người nói gần nhất ở cảnh đó
    total_n = n_chars
    for i, (_, kind, ev) in enumerate(events):
        who = ev.speaker if kind == "line" else ev.actor
        here = timeline.present(ev.scene, names) if names else None
        n_chars = len(here) if here is not None else total_n
        prev_here = last_in.get(ev.scene)
        other = prev_here if prev_here and prev_here != who else None
        first_visit = ev.scene not in visited
        visited.add(ev.scene)
        # chỉ cử chỉ MỚI cả người mới cần toàn cảnh; đang nằm/bò giữ nguyên thì
        # máy quay vẫn cận được (bám theo vị trí đầu thật)
        g = ev.gestures[0] if ev.gestures else ""
        expr = ev.expression
        shot = ev.shot
        if not shot and not auto:
            shot = "can" if ev.zoom else "toan"
        if not shot:
            if i == 0 or n_chars == 0 or (ev.scene != prev_scene and first_visit):
                shot = "toan"
            elif g in _FULL_BODY:
                shot = "toan"
            elif ev.zoom:
                shot = "sieucan" if expr in _STRONG else "can"
            elif kind == "beat":
                shot = "sieucan" if expr in _STRONG else "can"
            elif g in _UPPER or ev.props:
                shot = "trung"
            elif since_wide >= 5:
                shot = "toan"
            elif n_chars >= 2 and other:
                shot = "quavai" if i % 2 else "can"
            else:
                shot = "trung"
        since_wide = 0 if shot == "toan" else since_wide + 1
        out[(kind, ev.idx)] = (shot, who, other)
        prev_scene = ev.scene
        last_in[ev.scene] = who
    return out

def render_video(timeline: Timeline, chars: list[Character], out_path: Path,
                 stage: Stage, settings: dict, progress=None) -> Path:
    """Render timeline thành mp4 (kích thước theo stage), ghi thẳng RGB vào ffmpeg qua stdin."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.parent / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    fps = config.FPS
    total = timeline.total
    n_frames = max(1, int(round(total * fps)))

    # đo âm lượng từng câu để biết miệng mở hay ngậm
    envelopes: dict[int, "np.ndarray"] = {}
    thresholds: dict[int, float] = {}
    for ln in timeline.lines:
        if ln.audio and Path(ln.audio).exists():
            env = _envelope(Path(ln.audio), fps)
            envelopes[ln.idx] = env
            # ngưỡng mở miệng: 25% RMS lớn nhất của câu đó
            if len(env) > 0:
                thresholds[ln.idx] = float(env.max()) * 0.25
            else:
                thresholds[ln.idx] = 0.0

    # biểu cảm hiện tại của mỗi nhân vật — giữ tới khi có nhịp khác đổi
    held: dict[str, str] = {c.name: "neutral" for c in chars}

    # gộp sự kiện theo thứ tự thời gian
    events: list[tuple[float, float, object]] = []
    for ln in timeline.lines:
        events.append((ln.start, ln.duration, ln))
    for b in timeline.beats:
        events.append((b.start, b.duration, b))
    events.sort(key=lambda e: e[0])

    # Cache khung hình theo trạng thái: (biểu cảm, miệng mở/ngậm, camera)
    # góc máy từng câu / nhịp
    names = [c.name for c in chars]
    shots = plan_shots(timeline, len(chars), bool(settings.get("auto_camera", True)),
                       names)
    # nhân vật có mặt ở từng cảnh (vd gọi điện: mỗi người một nơi)
    _cast_cache: dict = {}

    def chars_in(scene: int) -> list[Character]:
        if scene not in _cast_cache:
            here = set(timeline.present(scene, names))
            _cast_cache[scene] = [c for c in chars if c.name in here]
        return _cast_cache[scene]

    # bối cảnh đang hiện và cảnh trước đó (để chuyển mờ)
    cur_scene: int | None = None
    prev_scene: int | None = None
    scene_since = 0.0
    seen_scenes: set = set()        # cảnh đã vào: quay lại thì cắt thẳng

    # --- CỬ ĐỘNG (Bước D): gom rig animator theo tên nhân vật để áp cử chỉ
    # theo từng câu trong kịch bản.
    rig_animators: dict[str, object] = {}
    for ch in chars:
        if ch.rig_animator is not None:
            rig_animators[ch.name] = ch.rig_animator

    from .gestures import POSTURES as _POSTURES
    from .gestures import reset_pose as _reset_pose
    _last_scene = None
    _entered: set = set()
    auto_seat = bool(settings.get("auto_seat", True))

    def _enter_scene(scene: int, t0: float) -> None:
        """Vào bối cảnh lần đầu: ở chỗ có ghế (văn phòng, lớp, quán, phòng
        khách...) mọi người đã ngồi sẵn; chỗ khác thì đứng."""
        _entered.add(scene)
        here = set(timeline.present(scene, list(rig_animators)))
        from .furniture import STANDING
        seat = stage.scene_seats.get(scene)
        sit = auto_seat and bool(seat) and seat not in STANDING
        for nm, anim in rig_animators.items():
            if nm not in here:
                continue
            try:
                _reset_pose(anim, t0)
                if sit:
                    # bắt đầu sớm 1 giây để vào cảnh là đã ngồi xong
                    anim.set_gesture("ngoi_ghe", None, t0 - 1.0)
                    anim._fade_from = None
            except Exception:  # pragma: no cover
                pass

    def _apply_gestures(ev) -> None:
        """Áp cử chỉ, hiệu ứng, đạo cụ của câu (hoặc nhịp '>') cho NGƯỜI ĐÓ.

        - Có cử chỉ mới: làm cử chỉ đó (cử chỉ cũ nhạt dần, không giật).
        - Không có: giữ tư thế cả người (nằm, ngồi, bò, khoanh tay, đứng
          ngoài khung...), còn cử chỉ khác thì thả tay về.
        - Người khác: giữ tư thế cả người, thôi các cử chỉ lặp (vẫy tay...).
        """
        if not rig_animators:
            return
        nonlocal _last_scene
        if ev.scene != _last_scene and ev.scene not in _entered:
            # vào bối cảnh mới lần đầu: đứng, hoặc ngồi sẵn nếu chỗ đó có ghế;
            # cắt qua lại giữa hai nơi thì ai đang nằm/ngồi vẫn giữ nguyên
            _enter_scene(ev.scene, ev.start)
        _last_scene = ev.scene
        who = getattr(ev, "speaker", None) or getattr(ev, "actor", "")
        gesture = ev.gestures[0] if ev.gestures else None
        effect = ev.effects[0] if ev.effects else None
        for name, anim in rig_animators.items():
            try:
                cur = getattr(anim, "current_gesture", None)
                keep = cur is not None and cur.name in _POSTURES
                if name == who:
                    if getattr(ev, "props", None) and hasattr(anim, "set_props"):
                        anim.set_props(ev.props, ev.start)
                    if gesture:
                        anim.set_gesture(gesture, effect, ev.start)
                    elif keep:
                        anim.current_effect = effect
                    else:
                        anim.set_gesture(None, effect, ev.start)
                elif not keep and cur is not None:
                    anim.set_gesture(None, None, ev.start)
            except Exception:  # pragma: no cover - cố gắng thay thế
                pass

    # cảnh đầu tiên: ngồi sẵn ngay từ khung đầu (trước câu thoại đầu tiên)
    if rig_animators and events:
        _first = getattr(events[0][2], "scene", 0)
        _enter_scene(_first, 0.0)
        _last_scene = _first

    # Góc nghiêng 3/4: ai nhìn ai khi nói chuyện
    three_quarter = bool(settings.get("three_quarter", True))
    _last_talker: dict[str, str] = {}      # người nói -> người vừa nói trước đó
    _prev_talker: list = [None]

    def _set_turns(vis: list[Character], talker: str | None) -> None:
        """Người nghe quay về phía người đang nói; người nói quay về phía
        người vừa nói với mình (không có thì người đứng gần nhất)."""
        anims = [c for c in vis if c.rig_animator is not None
                 and hasattr(c.rig_animator, "turn_target")]
        if not anims:
            return
        if not three_quarter or len(vis) < 2:
            for c in anims:
                c.rig_animator.turn_target = 0.0
            return
        if talker is None:
            return                         # khoảng lặng: giữ hướng nhìn cũ
        if talker != _prev_talker[0]:
            if _prev_talker[0] is not None:
                _last_talker[talker] = _prev_talker[0]
            _prev_talker[0] = talker
        xs = dict(zip([c.name for c in vis], stage.slots(len(vis))))
        if talker not in xs:
            return
        for c in anims:
            if c.name == talker:
                other = _last_talker.get(talker)
                if other not in xs or other == talker:
                    others = [n for n in xs if n != talker]
                    other = min(others, key=lambda n: abs(xs[n] - xs[talker]))
            else:
                other = talker
            d = xs[other] - xs[c.name]
            c.rig_animator.turn_target = TURN_TALK * (1 if d > 0 else -1 if d < 0 else 0)

    # Theo dõi câu hiện tại để chỉ áp cử chỉ ở khung đầu của mỗi câu
    _current_line_idx: object = None

    # Trạng thái miệng từng khung (đã giữ tối thiểu 2 khung cho mỗi lần đổi)
    mouth_states = {
        idx: _mouth_states(env, thresholds[idx])
        for idx, env in envelopes.items()
    }

    # Mở ffmpeg sẵn để ghi thẳng từng khung RGB vào stdin
    raw_video = tmp / "video_only.mp4"
    ffmpeg_proc = subprocess.Popen(
        [
            _ffmpeg_path(), "-y", "-f", "rawvideo",
            "-pixel_format", "rgb24",
            "-video_size", f"{stage.w}x{stage.h}",
            "-framerate", str(fps),
            "-i", "-",  # stdin
            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
            "-preset", "medium",
            str(raw_video),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,  # quan trọng: nếu đọc pipe stderr mà không drain sẽ deadlock
    )

    for fi in range(n_frames):
        t = fi / fps

        cur = None
        for (st, dur, obj) in events:
            if st <= t < st + dur:
                cur = obj
                break
        if cur is None and events:
            # giữa hai câu (khoảng 0,1 giây): giữ nguyên trạng thái câu trước
            past = [e for e in events if e[0] <= t]
            cur = past[-1][2] if past else None

        # bối cảnh: theo câu/nhịp hiện tại; trước câu đầu dùng cảnh của câu đầu
        scene = getattr(cur, "scene", None)
        if scene is None:
            scene = getattr(events[0][2], "scene", 0) if events else 0
        if scene != cur_scene:
            prev_scene, cur_scene, scene_since = cur_scene, scene, t
            if scene in seen_scenes:
                prev_scene = None          # quay lại nơi cũ: cắt thẳng, không mờ
            seen_scenes.add(scene)
        mix = min(1.0, (t - scene_since) / SCENE_FADE) if prev_scene is not None else 1.0
        vis = chars_in(cur_scene)
        stage.scene, stage.t = cur_scene, t

        speaking = None
        mouth_open = False
        zoom = False
        zoom_focus = None
        sub = ""

        if isinstance(cur, Line):
            in_line = cur.start <= t < cur.start + cur.duration
            # Áp cử chỉ ở khung đầu của mỗi câu
            if in_line and cur.idx != _current_line_idx:
                _current_line_idx = cur.idx
                _apply_gestures(cur)
            held[cur.speaker] = cur.expression
            # đổi biểu cảm người nghe ngay khi câu bắt đầu
            if in_line and cur.other_expr:
                for nm, ex in cur.other_expr.items():
                    if nm in held:
                        held[nm] = ex
            zoom = cur.zoom and in_line
            if zoom and cur.zoom_target:
                zoom_focus = cur.zoom_target
            if in_line:
                speaking = cur.speaker
                states = mouth_states.get(cur.idx)
                if states is not None and len(states):
                    k = min(len(states) - 1, max(0, int((t - cur.start) * fps)))
                    mouth_open = states[k]
                else:
                    mouth_open = True
                sub = _current_phrase(cur, t)
        elif isinstance(cur, Beat):
            # nhịp phản ứng: áp cử chỉ/đạo cụ ở khung đầu của nhịp
            if (cur.start <= t < cur.start + cur.duration
                    and ("beat", cur.idx) != _current_line_idx):
                _current_line_idx = ("beat", cur.idx)
                _apply_gestures(cur)
            # nhịp phản ứng: người đó đổi biểu cảm, không nói
            if cur.actor and cur.actor in held:
                held[cur.actor] = cur.expression
            zoom = cur.zoom and (cur.start <= t < cur.start + cur.duration)
            if cur.actor and cur.start <= t < cur.start + cur.duration:
                speaking = None

        if isinstance(cur, Line):
            _set_turns(vis, cur.speaker)
        elif isinstance(cur, Beat) and cur.actor:
            _set_turns(vis, cur.actor)
        else:
            _set_turns(vis, None)

        # Dựng khung mới mỗi lần: nhân vật thở, nhún, làm cử chỉ theo thời
        # gian nên không dùng lại khung cũ được (trước đây cache theo biểu
        # cảm làm cử động bị đứng hình).
        # góc máy của câu/nhịp hiện tại (trước câu đầu: góc của câu đầu)
        ev = cur if cur is not None else (events[0][2] if events else None)
        if ev is not None:
            key = ("line" if isinstance(ev, Line) else "beat", ev.idx)
            shot, who, other = shots.get(key, ("toan", None, None))
            if zoom_focus:
                who = zoom_focus
            stage.set_camera(shot, who, vis, other)
        img = stage.blank(cur_scene, prev_scene, mix)
        img = stage.draw_furniture(img, vis, "back")
        img = stage.place_characters(img, vis, held, speaking, mouth_open, t)
        img = stage.draw_furniture(img, vis, "front")
        img = stage.draw_ots(img)

        # Vẽ phụ đề và tiêu đề (không cache được vì text thay đổi mỗi khung)
        stage.draw_subtitle(img, sub)
        img = stage.draw_title(img)

        # Ghi frame ra ffmpeg stdin
        ffmpeg_proc.stdin.write(img.tobytes())
        if progress and fi % max(1, n_frames // 20) == 0:
            progress(fi / n_frames, f"đang dựng hình {fi}/{n_frames}")

    ffmpeg_proc.stdin.close()
    if ffmpeg_proc.wait() != 0:
        # stderr đã chuyển vào DEVNULL (tránh treo) nên không đọc được chi tiết
        raise RuntimeError("ffmpeg lỗi khi ghi video (mã "
                           f"{ffmpeg_proc.returncode}). Kiểm tra lại ffmpeg trong Cài đặt.")

    # ghép âm thanh vào
    _assemble(raw_video, timeline, out_path, settings, progress)
    return out_path


def _envelope(wav: Path, fps: int) -> "np.ndarray":
    """RMS theo từng khung hình, để biết lúc nào có tiếng."""
    import numpy as np
    import soundfile as sf

    a, sr = sf.read(str(wav), dtype="float32", always_2d=False)
    if getattr(a, "ndim", 1) > 1:
        a = a.mean(axis=1)
    hop = max(1, int(sr / fps))
    n = len(a) // hop
    if n == 0:
        return np.zeros(1, dtype="float32")
    return np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(axis=1))


def _mouth_states(env: "np.ndarray", threshold: float) -> list[bool]:
    """Trạng thái miệng từng khung theo ngưỡng; mỗi trạng thái giữ ít nhất 2 khung.

    Ngưỡng = 25% RMS lớn nhất của câu đó, nên câu nhỏ tiếng vẫn nhép miệng
    đúng nhịp, không phụ thuộc âm lượng cố định.
    """
    raw = [bool(v >= threshold) for v in env]
    if not raw:
        return raw

    # gom thành các đoạn liên tiếp cùng trạng thái
    runs: list[list] = []   # [gia_tri, do_dai]
    for v in raw:
        if runs and runs[-1][0] == v:
            runs[-1][1] += 1
        else:
            runs.append([v, 1])

    # đoạn nào chỉ dài 1 khung thì gộp vào đoạn kế để giữ tối thiểu 2 khung
    i = 0
    while i < len(runs):
        if runs[i][1] < 2 and len(runs) > 1:
            if i + 1 < len(runs):
                runs[i + 1][1] += runs[i][1]
            else:
                runs[i - 1][1] += runs[i][1]
            del runs[i]
            continue
        i += 1
    # trường hợp chỉ còn 1 đoạn thì kéo dài tối thiểu 2 khung
    if len(runs) == 1 and runs[0][1] < 2:
        runs[0][1] = 2

    out: list[bool] = []
    for val, length in runs:
        out.extend([val] * length)
    return out


def layout_slots(n: int) -> list[float]:
    """Vị trí ngang của nhân vật theo số người (tỉ lệ 0..1)."""
    return {
        1: [0.5],
        2: [0.27, 0.73],
        3: [0.18, 0.5, 0.82],
    }.get(n, [(i + 1) / (n + 1) for i in range(n)])


def _zoom_speaker(img: Image.Image, chars: list[Character],
                  focus: str) -> Image.Image:
    """Zoom vào nhân vật đang nói (hoặc đang phản ứng)."""
    target = None
    for i, ch in enumerate(chars):
        if ch.name == focus:
            target = i
            break
    if target is None:
        return img
    slots = layout_slots(len(chars))
    cx = int(img.width * slots[target])
    z = config.ZOOM_SCALE
    cw, chh = int(img.width / z), int(img.height / z)
    x = max(0, min(img.width - cw, cx - cw // 2))
    # căn lên phía trên một chút để lấy mặt, không lấy chân
    y = max(0, min(img.height - chh, int(img.height * 0.42) - chh // 2))
    return img.crop((x, y, x + cw, y + chh)).resize(
        (img.width, img.height), Image.LANCZOS)


def _current_phrase(line: Line, t: float) -> str:
    """Cụm từ đang được nói tại thời điểm t (phụ đề nhảy theo lời).

    Ghép tối đa 3 từ, từ từ đang nói trở đi, và dừng ở ranh giới câu để
    không bắt cầu sang câu kế tiếp.
    """
    if not line.words:
        return line.text

    # từ đang nói (hoặc vừa nói xong)
    idx = None
    for i, (w, ws, we) in enumerate(line.words):
        if ws <= t < we + 0.06:
            idx = i
            break
    if idx is None:
        return ""

    # lấy tối đa 3 từ, ưu tiên 2 từ trước + từ đang nói
    lo = max(0, idx - 2)
    return " ".join(w for (w, _, _) in line.words[lo: idx + 1])


def _run_ffmpeg(cmd: list[str], what: str) -> None:
    """Chạy ffmpeg, nếu lỗi thì báo rõ dòng lỗi cuối cùng của ffmpeg."""
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = [l for l in (proc.stderr or "").splitlines() if l.strip()][-6:]
        raise RuntimeError(
            f"ffmpeg lỗi khi {what}:\n" + "\n".join(tail)
        )


def _assemble(raw_video: Path, timeline: Timeline, out_path: Path,
              settings: dict, progress=None) -> None:
    """Ghép âm thanh vào video đã dựng (video_only.mp4) thành mp4 hoàn chỉnh."""
    tmp = out_path.parent / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    # 1. ghép âm thanh: các câu + tiếng động
    # Input 0 là video (không có audio), nên audio bắt đầu từ input 1.
    audio_parts: list[str] = []
    filter_parts: list[str] = []
    idx = 0                      # số nhánh audio đã thêm

    # Tiếng động: -6 dB, đặt ở đầu câu
    sfx_db = config.SFX_DB
    sfx_vol = 10 ** (sfx_db / 20.0)

    def add_audio(path: Path, start: float, volume: float | None = None) -> None:
        nonlocal idx
        audio_parts.extend(["-i", str(path)])
        ms = max(0, int(start * 1000))
        chain = f"adelay={ms}|{ms}"
        if volume is not None and abs(volume - 1.0) > 1e-3:
            chain += f",volume={volume}"
        # input index trong ffmpeg = idx + 1 (vì input 0 là video)
        filter_parts.append(f"[{idx + 1}:a]{chain}[a{idx}]")
        idx += 1

    for ln in timeline.lines:
        if ln.audio and Path(ln.audio).exists():
            add_audio(Path(ln.audio), ln.start)
        # Tiếng động đặt ở đầu câu
        if ln.sfx and config.SFX_AT_LINE_START:
            p = config.SFX_DIR / ln.sfx
            if p.exists():
                add_audio(p, ln.start, sfx_vol)
    for b in timeline.beats:
        if b.sfx:
            p = config.SFX_DIR / b.sfx
            if p.exists():
                add_audio(p, b.start, sfx_vol)

    if idx == 0:
        # không có âm thanh
        _run_ffmpeg([
            _ffmpeg_path(), "-y", "-i", str(raw_video),
            "-c", "copy", str(out_path),
        ], "xuất video không tiếng")
        return

    mix = "".join(f"[a{i}]" for i in range(idx))
    # normalize=0: giữ nguyên âm lượng từng câu, không bị nhỏ dần khi nhiều nhánh
    filter_parts.append(
        f"{mix}amix=inputs={idx}:duration=longest:normalize=0,"
        f"apad,atrim=0:{timeline.total:.3f},alimiter=limit=0.95[out]"
    )
    af = ";".join(filter_parts)

    cmd = [_ffmpeg_path(), "-y", "-i", str(raw_video)] + audio_parts + [
        "-filter_complex", af,
        "-map", "0:v", "-map", "[out]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]
    _run_ffmpeg(cmd, "ghép giọng vào video")

    # 3. nhạc nền (nếu có): -22 dB, ducking khi có giọng, fade out 2.5s cuối
    bgm = settings.get("bgm_file")
    if bgm and Path(bgm).exists() and settings.get("bgm_volume", 0) > 0:
        final = tmp / "final.mp4"

        # Âm lượng nền: -22 dB
        bgm_db = config.BGM_DB
        bgm_vol = 10 ** (bgm_db / 20.0)

        # Ducking: giảm thêm -8 dB khi có giọng nói
        # Tạo map các đoạn có giọng (lines)
        voice_ranges = []
        for ln in timeline.lines:
            voice_ranges.append((ln.start, ln.start + ln.duration))

        # Fade out cuối video
        fade_start = max(0, timeline.total - config.BGM_FADE_OUT)

        # Filter phức tạp: BGM loop + volume + ducking + fade out
        bgm_filter = (
            f"[1:a]volume={bgm_vol},"
            f"afade=t=out:st={fade_start:.3f}:d={config.BGM_FADE_OUT:.3f}"
        )

        # Sidechaining ducking: giảm BGM khi có giọng nói
        # Dùng sidechaincompress: voice audio làm trigger để nén BGM
        _run_ffmpeg([
            _ffmpeg_path(), "-y", "-i", str(out_path),
            "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex",
            f"{bgm_filter}[bgm];"
            f"[0:a][bgm]sidechaincompress=threshold=0.01:ratio=4:attack=10:release=100[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(final),
        ], "trộn nhạc nền với ducking")
        final.replace(out_path)

    if progress:
        progress(1.0, "xong")


def write_srt(timeline: Timeline, out_path: Path) -> Path:
    """Xuất phụ đề .srt để chỉnh trong CapCut."""
    def ts(t: float) -> str:
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int((t % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    items = []
    for ln in timeline.lines:
        items.append((ln.start, ln.start + ln.duration, f"{ln.speaker}: {ln.text}"))
    # nhịp phản ứng là khoảng lặng không lời -> không đưa vào phụ đề.
    # Chỉ ghi phụ đề khi có tiếng động để chị biết có hiệu ứng đang phát.
    for b in timeline.beats:
        if b.sfx:
            items.append((b.start, b.start + b.duration, b.sfx.replace("_", " ")))
    items.sort(key=lambda x: x[0])

    lines = []
    for i, (s, e, txt) in enumerate(items, 1):
        lines.append(f"{i}\n{ts(s)} --> {ts(e)}\n{txt}\n")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
