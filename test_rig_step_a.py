# -*- coding: utf-8 -*-
"""Bước A: dựng rig cho nhân vật vẽ bằng bộ ghép, xuất video thử 5 giây
vẫy tay + nhép miệng (dùng giọng có sẵn trong projects/e2e_test).

Chạy trong terminal:  python test_rig_step_a.py
"""
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

from core import config, rig as rig_mod  # noqa: E402
from core.character_kit import CharSpec  # noqa: E402

OUT_DIR = ROOT / "projects" / "e2e_test" / "out" / "rig_step_a"
FPS = config.FPS
DURATION = 5.0

# Nhân vật AI vẽ bằng bộ ghép: dùng lại bộ tham số của jieun cho khớp
# với ảnh đã có trong thư viện.
SPEC = CharSpec(
    name="jieun",
    body="adult",
    skin="fair",
    hair_style="long",
    hair_color="brown",
    shirt="pink",
    accessory="none",
)

AUDIO = ROOT / "projects" / "e2e_test" / "audio" / "line_000.wav"


def say(msg: str) -> None:
    print(msg, flush=True)


def build_audio(dst: Path) -> np.ndarray:
    """Ghép giọng thành đoạn 5 giây (lặp lại cho đủ dài)."""
    wav, sr = sf.read(str(AUDIO), dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    n = int(DURATION * sr)
    reps = int(np.ceil(n / len(wav)))
    full = np.concatenate([wav] * reps)[:n]
    sf.write(str(dst), full, sr)
    say(f"  âm thanh: {dst.name}  ({len(full)/sr:.2f}s @ {sr}Hz)")
    return full


def mouth_envelope(wav: np.ndarray, sr: int) -> np.ndarray:
    """Trả về mảng bool: khung nào miệng mở, theo RMS của từng khung."""
    n_frames = int(DURATION * FPS)
    per = int(sr / FPS)
    out = np.zeros(n_frames, dtype=bool)
    for i in range(n_frames):
        seg = wav[i * per:(i + 1) * per]
        if len(seg) == 0:
            continue
        rms = float(np.sqrt(np.mean(seg ** 2)))
        out[i] = rms > 0.012
    return out


def render_video(renderer: rig_mod.RigRenderer, wav: np.ndarray, sr: int, out_path: Path) -> None:
    """Render 5 giây: nhân vật vẫy tay + nhép miệng theo giọng."""
    n_frames = int(DURATION * FPS)
    mouth = mouth_envelope(wav, sr)

    stage_w, stage_h = config.WIDTH, config.HEIGHT
    bg = Image.new("RGB", (stage_w, stage_h), (246, 243, 238))

    # Kích thước nhân vật trên khung: cao ~62% khung
    target_h = int(stage_h * 0.62)
    scale = target_h / rig_mod.CH

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
            rig_mod.idle_angles(t),
            rig_mod.wave_angles(t, side="right"),
        )
        char = renderer.render(angles, mouth_open=bool(mouth[fi]))
        char = char.resize(
            (int(char.width * scale), int(char.height * scale)), Image.LANCZOS
        )

        frame = bg.copy()
        cx = int(stage_w * 0.5)
        x = cx - char.width // 2
        y = int(stage_h * 0.88) - char.height
        frame.paste(char, (x, y), char)

        proc.stdin.write(frame.tobytes())
        if fi % max(1, n_frames // 10) == 0:
            say(f"  dựng hình {fi}/{n_frames} ({fi/FPS:.1f}s)")

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg lỗi khi ghi video")
    say(f"  khung hình xong sau {time.time()-t0:.1f}s")

    # Ghép âm thanh
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-i", str(raw), "-i", str(OUT_DIR / "audio.wav"),
           "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        tail = [l for l in (r.stderr or "").splitlines() if l.strip()][-6:]
        raise RuntimeError("ffmpeg lỗi khi ghép âm thanh:\n" + "\n".join(tail))
    say(f"  video: {out_path}")


if __name__ == "__main__":
    say("=" * 60)
    say("BƯỚC A: khung xương + ghép bộ phận")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    say(f"\n1. Vẽ bộ phận và dựng rig.json cho '{SPEC.name}'")
    renderer_rig = rig_mod.build_rig(SPEC, OUT_DIR)
    say(f"   rig.json: {OUT_DIR / 'rig.json'}")
    say(f"   số xương: {len(renderer_rig.bones)}")
    for b in renderer_rig.bones:
        say(f"     {b.name:<12} cha={str(b.parent):<12} lớp={rig_mod.LAYER_NAMES.get(b.layer)}")

    say("\n2. Ghép âm thanh 5 giây")
    wav = build_audio(OUT_DIR / "audio.wav")

    say("\n3. Render video thử")
    renderer = rig_mod.RigRenderer(renderer_rig, OUT_DIR)
    out_path = OUT_DIR / "rig_step_a_5s.mp4"
    render_video(renderer, wav, 24000, out_path)

    say("\nHOÀN TẤT.")
    say(f"VIDEO: {out_path}")
