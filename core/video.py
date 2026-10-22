# -*- coding: utf-8 -*-
"""Dựng video 9:16 từ timeline: nhân vật, nhép miệng, nhún, zoom, phụ đề, tiếng động, nhạc nền.

Phương án: tạo từng khung hình bằng Pillow (nền + nhân vật + phụ đề), rồi ghép bằng ffmpeg.
Đây là cách chạy ổn định nhất trên Windows mà không cần GPU cho phần render.
"""
from __future__ import annotations

import json
import logging
import math
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


def find_font(bold: bool = True) -> str:
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


@dataclass
class Timeline:
    lines: list[Line] = field(default_factory=list)
    beats: list[Beat] = field(default_factory=list)
    total: float = 0.0


# ---------------------------------------------------------------- khung hình

class Stage:
    """Khung 9:16: bối cảnh + nhân vật + phụ đề."""

    def __init__(self, width: int = config.WIDTH, height: int = config.HEIGHT):
        self.w, self.h = width, height
        self.bg: Image.Image | None = None
        self.title = ""
        self.subtitle_style = config.SUBTITLE_STYLES["yellow"]
        self.font = find_font(bold=True)
        self.font_small = find_font(bold=False)
        self._char_cache: dict[tuple, Image.Image] = {}

    def set_background(self, path: Path) -> None:
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
        self.bg = img.resize((tw, th), Image.LANCZOS)

    def blank(self) -> Image.Image:
        if self.bg:
            return self.bg.copy()
        img = Image.new("RGB", (self.w, self.h), (30, 30, 40))
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
        slots = layout_slots(n)
        base_y = int(self.h * 0.80)

        for i, ch in enumerate(chars):
            cx = int(self.w * slots[i])
            speaking = (ch.name == active)
            # --- CỬ ĐỘNG (Bước D): nếu nhân vật có rig animator thì render theo
            # khung xương (cử chỉ + thở + cử động tay khi nói), giữ đầu cứng
            # để gắn biểu cảm + miệng như cũ.
            if ch.rig_animator is not None:
                try:
                    im = ch.rig_animator.render_frame(
                        t, speaking=speaking, mouth_open=bool(speaking and mouth_open)
                    )
                    im = im.convert("RGBA")
                    # Scale theo quy ước cũ: cao ~50-58% khung
                    target_h = int(self.h * (0.50 if n < 3 else 0.42) * ch.scale)
                    im = im.resize(
                        (max(1, int(im.width * target_h / im.height)), target_h),
                        Image.LANCZOS,
                    )
                    bounce = int(2 * math.sin(t * 1.6))
                    x = cx - im.width // 2
                    y = base_y - im.height - bounce
                    img.paste(im, (x, y), im)
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
            img.paste(im, (x, y), im)
        return img

    def _scaled(self, path: Path, n: int, scale: float) -> Image.Image:
        """Ảnh nhân vật đã resize — cache theo (file, kích thước)."""
        target_h = int(self.h * (0.50 if n < 3 else 0.42) * scale)
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

    def draw_title(self, img: Image.Image) -> Image.Image:
        if not self.title:
            return img
        d = ImageDraw.Draw(img)
        f = ImageFont.truetype(self.font, 64)
        txt = self.title
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
        f = ImageFont.truetype(self.font, st["size"])
        # tự xuống dòng nếu dài
        max_w = self.w - 120
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
        lh = int(st["size"] * 1.25)
        total_h = lh * len(lines)
        y = int(self.h * 0.86) - total_h // 2
        for ln in lines:
            bbox = d.textbbox((0, 0), ln, font=f)
            tw = bbox[2] - bbox[0]
            x = (self.w - tw) // 2
            d.text((x, y), ln, font=f, fill=st["fill"],
                   stroke_width=5, stroke_fill=st["outline"])
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

def render_video(timeline: Timeline, chars: list[Character], out_path: Path,
                 stage: Stage, settings: dict, progress=None) -> Path:
    """Render timeline thành mp4 1080x1920, ghi thẳng RGB vào ffmpeg qua stdin."""
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
    frame_cache: dict[tuple, Image.Image] = {}

    # --- CỬ ĐỘNG (Bước D): gom rig animator theo tên nhân vật để áp cử chỉ
    # theo từng câu trong kịch bản.
    rig_animators: dict[str, object] = {}
    for ch in chars:
        if ch.rig_animator is not None:
            rig_animators[ch.name] = ch.rig_animator

    def _apply_gestures(line: Line) -> None:
        """Áp cử chỉ + hiệu ứng cả người của câu vào các rig animator."""
        if not rig_animators:
            return
        gesture = line.gestures[0] if line.gestures else None
        effect = line.effects[0] if line.effects else None
        for anim in rig_animators.values():
            try:
                anim.set_gesture(gesture, effect, line.start)
            except Exception:  # pragma: no cover - cố gắng thay thế
                pass

    # Theo dõi câu hiện tại để chỉ áp cử chỉ ở khung đầu của mỗi câu
    _current_line_idx: int | None = None

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
            # nhịp phản ứng: người đó đổi biểu cảm, không nói
            if cur.actor and cur.actor in held:
                held[cur.actor] = cur.expression
            zoom = cur.zoom and (cur.start <= t < cur.start + cur.duration)
            if cur.actor and cur.start <= t < cur.start + cur.duration:
                speaking = None

        # Tạo cache key: (biểu cảm từng nhân vật, người đang nói + miệng, zoom)
        char_state = tuple((c.name, held.get(c.name, "neutral"), c.name == speaking and mouth_open) for c in chars)
        cache_key = (char_state, zoom, zoom_focus)

        if cache_key in frame_cache:
            # dùng lại khung đã render
            img = frame_cache[cache_key].copy()
        else:
            # render khung mới
            img = stage.blank()
            img = stage.place_characters(img, chars, held, speaking, mouth_open, t)

            if zoom:
                focus = zoom_focus or speaking
                if focus is None and isinstance(cur, Beat):
                    focus = cur.actor
                if focus:
                    img = _zoom_speaker(img, chars, focus)

            frame_cache[cache_key] = img.copy()

        # Vẽ phụ đề và tiêu đề (không cache được vì text thay đổi mỗi khung)
        stage.draw_subtitle(img, sub)
        img = stage.draw_title(img)

        # Ghi frame ra ffmpeg stdin
        ffmpeg_proc.stdin.write(img.tobytes())
        if progress and fi % max(1, n_frames // 20) == 0:
            progress(fi / n_frames, f"đang dựng hình {fi}/{n_frames}")

    ffmpeg_proc.stdin.close()
    if ffmpeg_proc.wait() != 0:
        err = ffmpeg_proc.stderr.read().decode("utf-8", errors="replace")
        raise RuntimeError("ffmpeg lỗi khi ghi video:\n" + err[-500:])

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
