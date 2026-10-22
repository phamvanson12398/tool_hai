# -*- coding: utf-8 -*-
"""Tạo các file tiếng động mặc định trong data/sfx/.

Tiếng động tự tổng hợp bằng sóng (không cần file gốc, không vấn đề bản quyền):
mỗi hiệu ứng có một chất giọng riêng để nghe phân biệt được.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config  # noqa: E402

SR = 44100
OUT = config.SFX_DIR
OUT.mkdir(parents=True, exist_ok=True)


def _env(n: int, attack=0.005, release=0.08) -> np.ndarray:
    a = int(SR * attack)
    r = int(SR * release)
    e = np.ones(n, dtype=np.float32)
    if a > 0:
        e[:a] = np.linspace(0, 1, a)
    if r > 0 and r < n:
        e[-r:] = np.linspace(1, 0, r)
    return e


def tone(freq: float, dur: float, vol=0.5, kind="sine", sweep=1.0) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = freq * (sweep ** (t / max(dur, 1e-6)))
    ph = 2 * np.pi * np.cumsum(f) / SR
    if kind == "sine":
        w = np.sin(ph)
    elif kind == "square":
        w = np.sign(np.sin(ph))
    elif kind == "saw":
        w = 2 * ((ph / (2 * np.pi)) % 1.0) - 1
    else:
        w = np.sign(np.sin(ph)) * 0.5 + np.sin(ph) * 0.5
    return (w * _env(n) * vol).astype(np.float32)


def noise(dur: float, vol=0.4, decay=6.0) -> np.ndarray:
    n = int(SR * dur)
    rng = np.random.default_rng(7)
    x = rng.standard_normal(n).astype(np.float32)
    e = np.exp(-decay * np.arange(n) / SR)
    return (x * e * vol).astype(np.float32)


def sweep(f0: float, f1: float, dur: float, vol=0.5, kind="sine") -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = f0 + (f1 - f0) * (t / max(dur, 1e-6))
    ph = 2 * np.pi * np.cumsum(f) / SR
    w = np.sin(ph) if kind == "sine" else np.sign(np.sin(ph))
    return (w * _env(n) * vol).astype(np.float32)


def mix(*parts) -> np.ndarray:
    n = max(len(p) for p in parts)
    out = np.zeros(n, dtype=np.float32)
    for p in parts:
        out[: len(p)] += p
    peak = float(np.max(np.abs(out))) or 1.0
    return out / peak * 0.85


def save(name: str, data: np.ndarray) -> None:
    sf.write(str(OUT / f"{name}.wav"), data, SR, subtype="PCM_16")
    print(f"  {name}.wav  ({len(data)/SR:.2f}s)")


def build() -> None:
    # --- nhịp, bật, va chạm ---
    save("ding", mix(tone(880, 0.9, 0.4), tone(1320, 0.7, 0.2)))
    save("tada", mix(tone(523, 0.25, 0.4), tone(659, 0.25, 0.4, sweep=1.0),
                     tone(784, 0.6, 0.45)))
    save("pop", sweep(400, 1400, 0.09, 0.55))
    save("boing", sweep(700, 120, 0.42, 0.55, "square"))
    save("whoosh", noise(0.42, 0.35, 4.0))
    save("swoosh", mix(noise(0.35, 0.3, 5.0), sweep(300, 1200, 0.3, 0.25)))

    # --- vỡ, đập ---
    save("boom", mix(noise(0.7, 0.6, 5.0), tone(55, 0.6, 0.5, sweep=0.6)))
    save("crash", mix(noise(0.9, 0.5, 3.2), noise(0.3, 0.3, 12.0)))
    save("thud", mix(tone(90, 0.3, 0.6, sweep=0.5), noise(0.2, 0.25, 12.0)))
    save("slap", mix(noise(0.12, 0.55, 22.0), tone(300, 0.1, 0.3, sweep=0.4)))

    # --- hài, phản ứng ---
    save("horn", mix(tone(220, 0.55, 0.4, "saw"),
                     tone(233, 0.55, 0.35, "saw")))
    save("honk", mix(tone(196, 0.4, 0.4, "square"),
                     tone(247, 0.4, 0.3, "square")))
    save("gasp", mix(noise(0.3, 0.2, 9.0), sweep(700, 1000, 0.3, 0.25)))
    save("siren", mix(sweep(600, 1200, 0.9, 0.4),
                      sweep(1200, 600, 0.9, 0.35)))
    save("whistle", mix(tone(2100, 0.45, 0.3, "sine", sweep=1.12),
                        tone(3160, 0.4, 0.15)))
    save("meow", sweep(700, 480, 0.5, 0.4, "saw"))
    save("bark", mix(noise(0.12, 0.5, 18.0), tone(320, 0.1, 0.4, sweep=0.5)))
    save("beep", tone(1200, 0.16, 0.4, "square"))

    # --- hài hước bối cảnh ---
    save("laugh_track", mix(noise(0.7, 0.3, 2.4), tone(320, 0.6, 0.2, "saw")))
    save("applause", noise(1.4, 0.4, 1.4))
    save("boo", mix(tone(140, 0.7, 0.45, "saw"), tone(105, 0.7, 0.35, "saw")))
    save("record_scratch", mix(noise(0.55, 0.3, 1.8),
                               sweep(1400, 250, 0.5, 0.3, "square")))
    save("rimshot", mix(tone(180, 0.28, 0.4, "saw"),
                        noise(0.3, 0.3, 9.0)))
    save("drumroll", noise(0.85, 0.32, 0.9))
    save("sad_trombone", mix(sweep(392, 196, 0.85, 0.4, "saw"),
                             sweep(349, 175, 0.8, 0.3, "saw")))
    save("splash", mix(noise(0.45, 0.4, 4.5), sweep(900, 200, 0.4, 0.25)))


if __name__ == "__main__":
    print(f"Tao tieng dong vao {OUT}")
    build()
    print("Xong.")
