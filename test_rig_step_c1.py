# -*- coding: utf-8 -*-
"""Bước C1: nhân vật từ ảnh tải lên — tách nền, ước khớp, uốn lưới, vẫy tay."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import soundfile as sf
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import config, rig as rig_mod, gestures as gmod  # noqa: E402
from core.photo_rig import PhotoCharacter  # noqa: E402

OUT_DIR = ROOT / "projects" / "e2e_test" / "out" / "rig_step_c1"
FPS = config.FPS
DURATION = 5.0

PHOTO = Path(r"C:\Users\balha\Downloads\photo.jpg")
AUDIO = ROOT / "projects" / "e2e_test" / "audio" / "line_000.wav"


def say(msg: str) -> None:
    print(msg, flush=True)


def build_audio(dst: Path) -> np.ndarray:
    wav, sr = sf.read(str(AUDIO), dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    n = int(DURATION * sr)
    reps = int(np.ceil(n / len(wav)))
    full = np.concatenate([wav] * reps)[:n]
    sf.write(str(dst), full, sr)
    say(f"  am thanh: {dst.name} ({len(full)/sr:.2f}s @ {sr}Hz)")
    return full


def mouth_envelope(wav: np.ndarray, sr: int) -> np.ndarray:
    n_frames = int(DURATION * FPS)
    per = int(sr / FPS)
    out = np.zeros(n_frames, dtype=bool)
    for i in range(n_frames):
        seg = wav[i * per:(i + 1) * per]
        if len(seg) == 0:
            continue
        out[i] = float(np.sqrt(np.mean(seg ** 2))) > 0.012
    return out


def render_video(out_path: Path, wav: np.ndarray, sr: int, char: PhotoCharacter) -> None:
    n_frames = int(DURATION * FPS)
    mouth = mouth_envelope(wav, sr)
    stage_w, stage_h = config.WIDTH, config.HEIGHT
    bg = Image.new("RGB", (stage_w, stage_h), (246, 243, 238))

    scale = stage_h * 0.75 / char.rgba.height

    raw = OUT_DIR / "tmp" / "rig_raw.mp4"
    raw.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = config.load_settings().get("ffmpeg_bin") or "ffmpeg"
    proc = subprocess.Popen(
        [ffmpeg, "-y", "-f", "rawvideo", "-pixel_format", "rgb24",
         "-video_size", f"{stage_w}x{stage_h}", "-framerate", str(FPS),
         "-i", "-", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
         "-preset", "medium", str(raw)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    t0 = time.time()
    for fi in range(n_frames):
        t = fi / FPS
        angles = rig_mod.merge(
            gmod.breathe_angles(t, 0),
            rig_mod.wave_angles(t, side="right"),
        )
        if mouth[fi]:
            angles = rig_mod.merge(angles, rig_mod.idle_arm_angles(t, 0))
        img = char.render(angles, mouth_open=bool(mouth[fi]))
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        frame = bg.copy()
        x = int(stage_w * 0.5) - img.width // 2
        y = int(stage_h * 0.88) - img.height
        frame.paste(img, (x, y), img)
        proc.stdin.write(frame.tobytes())
        if fi % max(1, n_frames // 10) == 0:
            say(f"  dung hinh {fi}/{n_frames} ({t:.1f}s)")

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg loi khi ghi video")
    say(f"  khung hinh xong sau {time.time()-t0:.1f}s")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-i", str(raw), "-i", str(OUT_DIR / "audio.wav"),
           "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        tail = [l for l in (r.stderr or "").splitlines() if l.strip()][-6:]
        raise RuntimeError("ffmpeg loi khi ghep am thanh:\n" + "\n".join(tail))
    say(f"  video: {out_path}")


if __name__ == "__main__":
    say("=" * 60)
    say("BUOC C1: anh tai len -> tach nen, uon luoi tam giac, vay tay")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    char = PhotoCharacter.load("photo", PHOTO)
    say(f"\n1. Anh: {PHOTO}")
    say(f"   Kich thuoc: {char.rgba.size}")
    say(f"   Nguon khop: {char.source}")
    say(f"   Anh dat (nguyen than): {char.valid}")
    say(f"   So khop: 14 (head, neck, 2 vai, 2 khuyu, 2 co tay, 2 hông, 2 goi, 2 mat ca)")

    say("\n2. Ghep am thanh 5 giay")
    wav = build_audio(OUT_DIR / "audio.wav")

    say("\n3. Render video thu 5 giay (vay tay phai + nep miệng theo gio)")
    out_path = OUT_DIR / "rig_step_c1_5s.mp4"
    render_video(out_path, wav, 24000, char)

    say("\nHOAN TAT.")
    say(f"VIDEO: {out_path}")
