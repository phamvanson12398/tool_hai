# -*- coding: utf-8 -*-
"""Dựng video Truyện kể: tranh (hoặc cảnh tool tự vẽ, nhân vật cử động —
core/story_live.py) + chuyển động máy quay + chuyển cảnh mờ + thẻ tên
truyện / tên chương + lời kể + nhạc nền (+ phụ đề tuỳ chọn).

Video dài (20–30 phút ≈ 36.000 khung ở 24 hình/giây) nên mỗi khung chỉ là một
phép cv2.warpAffine trên tranh đã chuẩn bị sẵn, ghi thẳng vào ffmpeg; chữ (thẻ
chương, phụ đề) vẽ bằng Pillow một lần rồi dùng lại.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import config, story, video

logger = logging.getLogger(__name__)

FPS = 24
OVER = 1.15            # tranh phóng to hơn khung bấy nhiêu để có chỗ lia / phóng
FADE = 0.7             # giây chuyển mờ giữa hai cảnh
LEAD = 0.45            # giây lặng đầu cảnh trước khi người kể đọc
TAIL = 0.55            # giây lặng cuối cảnh
INTRO = 4.5            # thẻ tên truyện ở đầu video
CHAPTER_CARD = 2.8     # thẻ tên chương đầu mỗi chương
OUTRO = 2.5            # giữ cảnh cuối rồi tối dần


def _ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


class _Shot:
    """Một tranh đã chuẩn bị + cách máy quay chạy trên tranh."""

    def __init__(self, img: Image.Image, size: tuple[int, int], camera: str):
        import cv2
        self.cv2 = cv2
        W, H = size
        bw, bh = int(W * OVER), int(H * OVER)
        r = max(bw / img.width, bh / img.height)
        im = img.convert("RGB").resize((max(bw, int(img.width * r)), max(bh, int(img.height * r))),
                                       Image.LANCZOS)
        x0, y0 = (im.width - bw) // 2, (im.height - bh) // 2
        self.base = np.asarray(im.crop((x0, y0, x0 + bw, y0 + bh)))
        self.W, self.H, self.bw, self.bh = W, H, bw, bh
        self.camera = camera if camera in story.CAMERAS else "zoom_in"

    def frame(self, u: float) -> np.ndarray:
        """Khung hình ở tiến độ u (0..1) của cảnh."""
        e = _ease(u)
        c, z0, z1 = self.camera, 1.0, 1.0
        cx, cy = 0.5, 0.5
        pan = 1.08
        if c == "zoom_in":
            z0, z1 = 1.0, 1.12
        elif c == "zoom_out":
            z0, z1 = 1.12, 1.0
        elif c in ("pan_left", "pan_right", "pan_up", "pan_down"):
            z0 = z1 = pan
        z = z0 + (z1 - z0) * e
        vw, vh = self.bw / z, self.bh / z            # vùng nhìn trên tranh
        free_x, free_y = self.bw - vw, self.bh - vh
        if c == "pan_left":
            cx = 1 - e
        elif c == "pan_right":
            cx = e
        elif c == "pan_up":
            cy = 1 - e
        elif c == "pan_down":
            cy = e
        vx, vy = free_x * cx, free_y * cy
        k = self.W / vw
        M = np.float32([[k, 0, -vx * k], [0, self.H / vh, -vy * self.H / vh]])
        return self.cv2.warpAffine(self.base, M, (self.W, self.H), flags=self.cv2.INTER_LINEAR)


def _placeholder(size: tuple[int, int], sid: str, text: str) -> Image.Image:
    """Tranh tạm khi chưa có ảnh: nền tối + số cảnh + lời kể."""
    W, H = size
    img = Image.new("RGB", (W, H), (34, 38, 52))
    d = ImageDraw.Draw(img)
    f1 = ImageFont.truetype(video.find_font(True, True), int(min(W, H) * 0.07))
    f2 = ImageFont.truetype(video.find_font(False, True), int(min(W, H) * 0.035))
    d.text((W * 0.08, H * 0.1), f"Cảnh {sid} — chưa có tranh", font=f1, fill=(240, 200, 120))
    _wrap(d, text, f2, W * 0.08, H * 0.25, W * 0.84, (220, 224, 236))
    return img


def _wrap(d, text, font, x, y, maxw, fill, line_h=1.35):
    words, line = text.split(), ""
    lh = font.size * line_h
    for w in words:
        t = (line + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            line = t
        else:
            d.text((x, y), line, font=font, fill=fill)
            y += lh
            line = w
    if line:
        d.text((x, y), line, font=font, fill=fill)
    return y + lh


def _card(size, big: str, small: str = ""):
    """Lớp chữ thẻ tên (RGBA): nền tối mờ giữa khung + chữ."""
    W, H = size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, int(H * 0.32), W, int(H * 0.68)], fill=(10, 10, 16, 150))
    fb = ImageFont.truetype(video.find_font(True, True), int(min(W, H) * 0.075))
    fs = ImageFont.truetype(video.find_font(False, True), int(min(W, H) * 0.038))
    y = H * 0.5 - fb.size * (0.9 if small else 0.55)
    if small:
        tw = d.textlength(small, font=fs)
        d.text(((W - tw) / 2, y - fs.size * 1.6), small, font=fs, fill=(236, 210, 150, 255))
    # tên dài thì xuống dòng
    lines, cur = [], ""
    for w in big.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=fb) <= W * 0.86:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    for ln in lines:
        tw = d.textlength(ln, font=fb)
        d.text(((W - tw) / 2, y), ln, font=fb, fill=(252, 250, 244, 255),
               stroke_width=3, stroke_fill=(0, 0, 0, 255))
        y += fb.size * 1.2
    return _tight(np.asarray(img))


def _subtitle(size, text: str):
    W, H = size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(video.find_font(True, True), int(min(W, H) * 0.045))
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= W * 0.86:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    y = H * 0.9 - len(lines) * f.size * 1.25
    for ln in lines:
        tw = d.textlength(ln, font=f)
        d.text(((W - tw) / 2, y), ln, font=f, fill=(255, 255, 255, 255),
               stroke_width=4, stroke_fill=(0, 0, 0, 255))
        y += f.size * 1.25
    return _tight(np.asarray(img))


def _tight(layer: np.ndarray):
    """Lớp chữ cắt sát vùng có chữ: (rgb, alpha 0..1, y0, y1, x0, x1) — chỉ trộn
    vùng này mỗi khung (trộn cả khung 1080p mất ~60 ms, quá chậm cho video dài)."""
    ys, xs = np.nonzero(layer[..., 3])
    if not len(ys):
        return None
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    part = layer[y0:y1, x0:x1]
    return (part[..., :3].astype(np.float32), part[..., 3:4].astype(np.float32) / 255.0,
            y0, y1, x0, x1)


def _over(frame: np.ndarray, layer, alpha: float = 1.0) -> np.ndarray:
    if layer is None:
        return frame
    rgb, a, y0, y1, x0, x1 = layer
    a = a * alpha
    out = frame.copy() if not frame.flags.writeable else frame
    reg = out[y0:y1, x0:x1].astype(np.float32)
    out[y0:y1, x0:x1] = (reg * (1 - a) + rgb * a).astype(np.uint8)
    return out


def _mix(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    import cv2
    return cv2.addWeighted(a, 1.0 - k, b, k, 0.0)


def _dim(a: np.ndarray, k: float) -> np.ndarray:
    import cv2
    return cv2.convertScaleAbs(a, alpha=k)


def plan_timeline(st: dict, audio: dict[str, Path]) -> list[dict]:
    """Mốc thời gian từng cảnh: start, dur, audio_at, thẻ chương."""
    import soundfile as sf
    out, t = [], INTRO
    for ci, ch in enumerate(st.get("chapters") or []):
        for k, sc in enumerate(ch.get("scenes") or []):
            card = CHAPTER_CARD if k == 0 else 0.0
            p = audio.get(sc["id"])
            ad = sf.info(str(p)).duration if p and Path(p).exists() else 0.0
            dur = max(3.5, card + LEAD + ad + TAIL)
            out.append({"sc": sc, "chapter": ci, "card": card, "start": t, "dur": dur,
                        "audio": p, "audio_at": t + card + LEAD, "audio_dur": ad})
            t += dur
    return out


def render(st: dict, pdir: Path, fmt: str, settings: dict, audio: dict[str, Path],
           progress=None) -> Path:
    import soundfile as sf

    def say(f, m):
        if progress:
            progress(f, m)

    size = config.frame_size(fmt)
    W, H = size
    tl = plan_timeline(st, audio)
    if not tl:
        raise RuntimeError("Chưa có cảnh nào để dựng.")
    total = tl[-1]["start"] + tl[-1]["dur"] + OUTRO
    imgs = story.scene_images(pdir)
    out_dir = pdir / "out"
    tmp = out_dir / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    # ---- âm thanh: lời kể đặt đúng mốc (+ nhạc nền)
    say(0.02, "ghép lời kể")
    sr = config.SAMPLE_RATE
    track = np.zeros(int(total * sr) + sr, dtype=np.float32)
    for row in tl:
        if row["audio"] and Path(row["audio"]).exists():
            a, asr = sf.read(str(row["audio"]), dtype="float32")
            if a.ndim > 1:
                a = a.mean(axis=1)
            if asr != sr:
                a = np.interp(np.linspace(0, len(a), int(len(a) * sr / asr), endpoint=False),
                              np.arange(len(a)), a).astype(np.float32)
            i0 = int(row["audio_at"] * sr)
            track[i0:i0 + len(a)] += a[: max(0, len(track) - i0)]
    narr = tmp / "story_narration.wav"
    sf.write(str(narr), np.clip(track, -1, 1), sr)

    # ---- hình
    ff = video._ffmpeg_path()
    raw = tmp / "story_video_only.mp4"
    proc = subprocess.Popen(
        [ff, "-y", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{W}x{H}",
         "-framerate", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "20",
         "-pix_fmt", "yuv420p", "-preset", "veryfast", str(raw)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shots: dict = {}
    tool = st.get("visual", "tool") == "tool"

    def shot(i: int) -> _Shot:
        if i not in shots:
            for k in [k for k in shots if k < i - 1]:
                del shots[k]                      # chỉ giữ vài tranh trong bộ nhớ
            row = tl[i]
            sc = row["sc"]
            p = imgs.get(sc["id"])
            if not p and tool:
                # tool tự vẽ cảnh và cho nhân vật cử động theo lời kể
                from .story_live import LiveShot
                shots[i] = LiveShot(st, sc, size, sc.get("camera") or "zoom_in", row["dur"],
                                    audio=row["audio"], audio_at=row["card"] + LEAD,
                                    audio_dur=row["audio_dur"], over=OVER, fps=FPS, pdir=pdir)
                return shots[i]
            try:
                im = Image.open(p) if p else _placeholder(size, sc["id"], sc.get("text") or "")
            except Exception:  # noqa: BLE001
                im = _placeholder(size, sc["id"], sc.get("text") or "")
            shots[i] = _Shot(im, size, sc.get("camera") or "zoom_in")
        return shots[i]

    intro_card = _card(size, st.get("title") or "", st.get("author") or "")
    chapter_cards: dict = {}
    subs: dict = {}
    sub_on = bool(st.get("subtitles"))
    n_frames = int(total * FPS)
    i = 0
    try:
        for fi in range(n_frames):
            t = fi / FPS
            while i < len(tl) - 1 and t >= tl[i + 1]["start"]:
                i += 1
            row = tl[i]
            if t < row["start"]:                  # phần mở đầu: tranh đầu + tên truyện
                frame = shot(0).frame(0.0)
                a = min(1.0, t / 0.8, (INTRO - t) / 0.8)
                frame = _over(_dim(frame, 0.55), intro_card, max(0.0, a))
            else:
                u = (t - row["start"]) / row["dur"]
                frame = shot(i).frame(min(1.0, u))
                # chuyển mờ sang cảnh sau
                nxt = row["start"] + row["dur"]
                if i + 1 < len(tl) and t > nxt - FADE:
                    k = (t - (nxt - FADE)) / FADE
                    frame = _mix(frame, shot(i + 1).frame(0.0), k)
                # thẻ tên chương
                if row["card"] and t - row["start"] < row["card"]:
                    ci = row["chapter"]
                    if ci not in chapter_cards:
                        chapter_cards[ci] = _card(size, st["chapters"][ci]["title"], f"Chương {ci + 1}")
                    lt = t - row["start"]
                    frame = _over(frame, chapter_cards[ci], min(1.0, lt / 0.5, (row["card"] - lt) / 0.5))
                # phụ đề: câu đang đọc (chia thời lượng theo độ dài câu)
                if sub_on and row["audio_dur"] and row["audio_at"] <= t < row["audio_at"] + row["audio_dur"]:
                    sents = story._sentences(row["sc"].get("text") or "")
                    tot = sum(len(s) for s in sents) or 1
                    pos, acc = (t - row["audio_at"]) / row["audio_dur"] * tot, 0
                    for j, s in enumerate(sents):
                        acc += len(s)
                        if pos <= acc:
                            key = (row["sc"]["id"], j)
                            if key not in subs:
                                if len(subs) > 8:
                                    subs.clear()
                                subs[key] = _subtitle(size, s)
                            frame = _over(frame, subs[key])
                            break
                # tối dần ở cuối video
                end = total - OUTRO
                if t > end:
                    frame = _dim(frame, max(0.0, 1 - (t - end) / OUTRO))
            proc.stdin.write(np.ascontiguousarray(frame).tobytes())
            if fi % max(1, n_frames // 50) == 0:
                say(0.05 + 0.85 * fi / n_frames, f"dựng hình {int(t // 60)}:{int(t % 60):02d} / "
                                                  f"{int(total // 60)}:{int(total % 60):02d}")
    finally:
        proc.stdin.close()
        proc.wait()

    # ---- ghép tiếng + hình (nhạc nền nếu có)
    say(0.93, "ghép âm thanh")
    mp4 = out_dir / "video.mp4"
    bgm = settings.get("bgm_file")
    vol = float(settings.get("bgm_volume") or 0)
    if bgm and Path(bgm).exists() and vol > 0:
        cmd = [ff, "-y", "-i", str(raw), "-i", str(narr), "-stream_loop", "-1", "-i", str(bgm),
               "-filter_complex",
               f"[2:a]volume={vol * 0.35:.3f},afade=t=out:st={max(0, total - 4):.2f}:d=4[b];"
               f"[1:a][b]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]",
               "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-shortest", str(mp4)]
    else:
        cmd = [ff, "-y", "-i", str(raw), "-i", str(narr), "-map", "0:v", "-map", "1:a",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg ghép tiếng lỗi: " + (r.stderr or "")[-400:])
    say(1.0, "xong")
    return mp4
