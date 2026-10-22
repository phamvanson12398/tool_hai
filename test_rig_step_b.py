# -*- coding: utf-8 -*-
"""Bước B: dựng video thử từ kịch bản ngắn 2 nhân vật, dùng nhiều cử chỉ.

Nhân vật dùng rig từ Bước A. Render trong terminal, in tiến độ theo %.
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

from core import config, rig as rig_mod, gestures as gmod  # noqa: E402
from core.character_kit import CharSpec  # noqa: E402

OUT_DIR = ROOT / "projects" / "e2e_test" / "out" / "rig_step_b"
FPS = config.FPS
DURATION = 6.0

JIEUN = CharSpec(name="jieun", body="adult", skin="fair", hair_style="long",
                 hair_color="brown", shirt="pink")
SUA = CharSpec(name="sua", body="adult", skin="light", hair_style="short",
               hair_color="black", shirt="blue")

AUDIO_FILES = [ROOT / "projects" / "e2e_test" / "audio" / f"line_{i:03d}.wav"
               for i in (0, 0, 1, 1)]


def say(msg: str) -> None:
    print(msg, flush=True)


def build_audio(dst: Path) -> np.ndarray:
    """Ghép 4 đoạn giọng (2 câu cho mỗi nhân vật) thành 6s."""
    parts: list[np.ndarray] = []
    sr = None
    for p in AUDIO_FILES:
        wav, sr = sf.read(str(p), dtype="float32")
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        parts.append(wav)
    full = np.concatenate(parts)
    if sr is None:
        sr = 24000
    n = int(DURATION * sr)
    full = full[:n] if len(full) >= n else np.pad(full, (0, n - len(full)))
    sf.write(str(dst), full, sr)
    say(f"  am thanh: {dst.name}  ({len(full)/sr:.2f}s @ {sr}Hz)")
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


def render_video(out_path: Path, wav: np.ndarray, sr: int) -> None:
    n_frames = int(DURATION * FPS)
    mouth = mouth_envelope(wav, sr)

    stage_w, stage_h = config.WIDTH, config.HEIGHT
    bg = Image.new("RGB", (stage_w, stage_h), (246, 243, 238))

    # Dùng rig của Bước A (jieun) cho cả hai nhân vật; scale khác nhau để phân biệt
    rig_j = rig_mod.build_rig(JIEUN, OUT_DIR / "rig_jieun")
    rig_s = rig_mod.build_rig(SUA, OUT_DIR / "rig_sua")
    anim_j = rig_mod.CharacterAnimator(rig_j, OUT_DIR / "rig_jieun", "jieun")
    anim_s = rig_mod.CharacterAnimator(rig_s, OUT_DIR / "rig_sua", "sua")

    # Lịch trình cử chỉ theo thời gian (giây): (nhân vật, cử chỉ, hiệu ứng, bắt đầu)
    schedule = [
        (1.0, "jieun", "khoanhtay", None),
        (2.0, "sua", "vaytay", None),
        (3.0, "jieun", "omdau", "nhay"),
        (4.0, "sua", "chitay", "rung"),
    ]

    scale_j = stage_h * 0.55 / rig_mod.CH
    scale_s = stage_h * 0.45 / rig_mod.CH

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
    prev = None
    for fi in range(n_frames):
        t = fi / FPS
        i = fi
        mj = bool(mouth[i])

        #áp dụng cử chỉ theo schedule
        for st, nm, gesture, effect in schedule:
            if t >= st and (prev is None or prev < st):
                if nm == "jieun":
                    anim_j.set_gesture(gesture, effect, st)
                else:
                    anim_s.set_gesture(gesture, effect, st)
        prev = t

        # Mỗi câu dài ~1.5s: 0 jieun, 1 sua, 2 jieun, 3 sua
        idx = int(t // 1.5)
        speaking_j = idx in (0, 2)
        speaking_s = idx in (1, 3)
        mj = bool(mouth[i]) if speaking_j else False
        ms = bool(mouth[i]) if speaking_s else False

        cj = anim_j.render_frame(t, speaking_j, mj)
        cs = anim_s.render_frame(t, speaking_s, ms)
        cj = cj.resize((int(cj.width * scale_j), int(cj.height * scale_j)), Image.LANCZOS)
        cs = cs.resize((int(cs.width * scale_s), int(cs.height * scale_s)), Image.LANCZOS)

        frame = bg.copy()
        # jieun bên trái, sua bên phải
        xj = int(stage_w * 0.30) - cj.width // 2
        xs = int(stage_w * 0.70) - cs.width // 2
        yj = int(stage_h * 0.88) - cj.height
        ys = int(stage_h * 0.90) - cs.height
        frame.paste(cj, (xj, yj), cj)
        frame.paste(cs, (xs, ys), cs)

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
    say("BUOC B: thu vien cu chi + hieu ung ca nguoi + video thu 2 nhan vat")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    say(f"\n1. Thu vien cu chi: {gmod.GESTURE_DIR / 'gestures.json'}")
    say(f"   So cu chi: {len(gmod.ensure_library()[1])}")
    say(f"   Hieu ung ca nguoi: {', '.join(gmod.EFFECT_NAMES)}")

    say("\n2. Ghep am thanh")
    wav = build_audio(OUT_DIR / "audio.wav")

    say("\n3. Render video thu 6 giay")
    out_path = OUT_DIR / "rig_step_b_6s.mp4"
    render_video(out_path, wav, 24000)

    say("\nHOAN TAT.")
    say(f"VIDEO: {out_path}")
