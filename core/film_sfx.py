# -*- coding: utf-8 -*-
"""Tiếng động cho chế độ Phim: bước chân, cuốc đất, quét chổi, bổ củi, vỗ tay,
ăn, rít điếu cày, cửa kẽo kẹt, gà gáy... và tiếng nền (chim hót, dế kêu ban
đêm, mưa). Tự tổng hợp bằng sóng (không cần file gốc, không lo bản quyền); tiếng
chó sủa, mèo kêu, há hốc lấy từ data/sfx có sẵn. Tạo một lần, lưu data/sfx/film/.
"""
from __future__ import annotations

import numpy as np

from . import config

SR = config.SAMPLE_RATE
DIR = config.SFX_DIR / "film"
LABELS = {
    "step": "Bước chân", "dig": "Cuốc đất", "sweep": "Quét chổi", "chop": "Bổ củi",
    "swish": "Vụt liềm", "clap": "Vỗ tay", "nom": "Nhai", "bubble": "Rít điếu / sôi nồi",
    "door": "Cửa kẽo kẹt", "knock": "Gõ cửa", "rooster": "Gà gáy", "thud": "Ngã phịch",
    "swoosh": "Vút (đưa đồ)", "bark": "Chó sủa", "meow": "Mèo kêu", "gasp": "Há hốc",
    "thunder": "Sấm", "birds": "Chim hót (nền)", "crickets": "Dế kêu (nền)",
    "rain": "Mưa (nền)", "wind": "Gió (nền)",
}
AMBIENT = {"birds", "crickets", "rain", "wind"}
_CACHE: dict = {}


def _rng(seed):
    return np.random.default_rng(seed)


def _env(n, a=0.004, r=0.1):
    e = np.ones(n, np.float32)
    na, nr = int(SR * a), int(SR * r)
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr and nr < n:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def _decay(n, k):
    return np.exp(-np.arange(n) / SR * k).astype(np.float32)


def _lp(x, a):
    """Lọc thông thấp một cực (a gần 1 = trầm)."""
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = a * acc + (1 - a) * v
        y[i] = acc
    return y


def _lpf(x, a):
    from scipy.signal import lfilter  # type: ignore
    return lfilter([1 - a], [1, -a], x).astype(np.float32)


def _filt(x, a):
    try:
        return _lpf(x, a)
    except Exception:  # noqa: BLE001 — không có scipy
        return _lp(x, a)


def _hp(x, a):
    return (x - _filt(x, a)).astype(np.float32)


def synth(name: str) -> np.ndarray:
    import zlib
    r = _rng(zlib.crc32(name.encode()) % 1000)
    if name == "step":                            # bước chân trên đất: tiếng "thụp" trầm ngắn
        n = int(SR * 0.12)
        x = _filt(r.normal(0, 1, n).astype(np.float32), 0.94) * _decay(n, 45)
        return x * 0.9
    if name == "dig":                             # cuốc bổ xuống đất: thụp + đất văng
        n = int(SR * 0.35)
        hit = _filt(r.normal(0, 1, n).astype(np.float32), 0.97) * _decay(n, 25) * 2.2
        dirt = _hp(r.normal(0, 1, n).astype(np.float32), 0.6) * _decay(n, 9) * 0.15
        return hit + dirt
    if name == "sweep":                           # chổi rơm quẹt: xào xạc
        n = int(SR * 0.45)
        t = np.arange(n) / SR
        env = np.sin(np.pi * np.clip(t / 0.45, 0, 1)) ** 1.5
        return _hp(r.normal(0, 1, n).astype(np.float32), 0.85) * env.astype(np.float32) * 0.35
    if name == "chop":                            # rìu bổ củi: cốc gỗ
        n = int(SR * 0.3)
        t = np.arange(n) / SR
        tone = (np.sin(2 * np.pi * 420 * t) + 0.6 * np.sin(2 * np.pi * 690 * t)) * _decay(n, 30)
        crack = _hp(r.normal(0, 1, n).astype(np.float32), 0.5) * _decay(n, 60) * 0.5
        return (tone * 0.6 + crack).astype(np.float32)
    if name == "swish":
        n = int(SR * 0.25)
        t = np.arange(n) / SR
        env = np.sin(np.pi * t / 0.25) ** 2
        return _hp(r.normal(0, 1, n).astype(np.float32), 0.7) * env.astype(np.float32) * 0.3
    if name == "clap":
        n = int(SR * 0.09)
        return _hp(r.normal(0, 1, n).astype(np.float32), 0.4) * _decay(n, 70) * 0.8
    if name == "nom":                             # nhai lóp bóp
        out = []
        for k in range(3):
            n = int(SR * 0.08)
            out += [_filt(r.normal(0, 1, n).astype(np.float32), 0.8) * _decay(n, 50) * 0.4,
                    np.zeros(int(SR * 0.07), np.float32)]
        return np.concatenate(out)
    if name == "bubble":                          # rít điếu cày / nồi sôi: lục bục
        out = np.zeros(int(SR * 0.9), np.float32)
        for k in range(10):
            f = r.uniform(180, 420)
            n = int(SR * 0.05)
            t = np.arange(n) / SR
            b = np.sin(2 * np.pi * f * t * (1 + 3 * t)) * _decay(n, 60)
            i = int(r.uniform(0, 0.8) * SR)
            out[i:i + n] += b.astype(np.float32) * 0.35
        return out
    if name == "door":                            # cửa gỗ kẽo kẹt
        n = int(SR * 0.9)
        t = np.arange(n) / SR
        f = 140 + 90 * np.sin(2 * np.pi * 1.3 * t) + 40 * r.normal(0, 1, n).cumsum() / np.sqrt(n)
        x = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * 0.08
        return (_filt(x.astype(np.float32), 0.6) * _env(n, 0.05, 0.2)).astype(np.float32)
    if name == "knock":
        out = []
        for _ in range(3):
            n = int(SR * 0.12)
            t = np.arange(n) / SR
            out += [(np.sin(2 * np.pi * 260 * t) * _decay(n, 40) * 0.7).astype(np.float32),
                    np.zeros(int(SR * 0.12), np.float32)]
        return np.concatenate(out)
    if name == "rooster":                         # ò ó o: ba nốt trượt
        parts = []
        for f0, f1, d in ((520, 760, 0.25), (760, 700, 0.3), (700, 420, 0.6)):
            n = int(SR * d)
            t = np.arange(n) / SR
            f = f0 + (f1 - f0) * t / d
            ph = 2 * np.pi * np.cumsum(f) / SR
            w = np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph)
            parts.append((w * _env(n, 0.02, 0.06) * 0.25).astype(np.float32))
        return np.concatenate(parts)
    if name == "thud":
        n = int(SR * 0.4)
        t = np.arange(n) / SR
        return ((np.sin(2 * np.pi * 70 * t) * 0.8 + _filt(r.normal(0, 1, n).astype(np.float32), 0.9))
                * _decay(n, 14) * 0.7).astype(np.float32)
    if name == "swoosh":
        n = int(SR * 0.3)
        t = np.arange(n) / SR
        env = np.sin(np.pi * t / 0.3) ** 2
        return _filt(r.normal(0, 1, n).astype(np.float32), 0.7) * env.astype(np.float32) * 0.4
    if name == "thunder":
        n = int(SR * 3.0)
        x = _filt(r.normal(0, 1, n).astype(np.float32), 0.995) * 8
        return (x * _env(n, 0.3, 1.5) * _decay(n, 0.8)).astype(np.float32)
    if name == "birds":                           # nền 12 giây: chim hót thưa
        out = np.zeros(int(SR * 12), np.float32)
        for _ in range(26):
            f = r.uniform(2200, 4200)
            k = int(r.integers(2, 5))
            i = int(r.uniform(0, 11.3) * SR)
            for j in range(k):
                n = int(SR * 0.07)
                t = np.arange(n) / SR
                ch = np.sin(2 * np.pi * (f + 900 * np.sin(2 * np.pi * 18 * t)) * t) * _env(n, 0.01, 0.03)
                s0 = i + j * int(SR * 0.1)
                out[s0:s0 + n] += ch[: max(0, len(out) - s0)].astype(np.float32) * 0.12
        return out
    if name == "crickets":                        # nền 10 giây: dế kêu ri ri
        n = int(SR * 10)
        t = np.arange(n) / SR
        chirp = np.sin(2 * np.pi * 4300 * t) * (np.sin(2 * np.pi * 30 * t) > 0.2)
        gate = (np.sin(2 * np.pi * 0.9 * t) > 0.0).astype(np.float32)
        chirp2 = np.sin(2 * np.pi * 3900 * t) * (np.sin(2 * np.pi * 26 * t + 1) > 0.3) * \
            (np.sin(2 * np.pi * 0.7 * t + 2) > 0.1)
        return ((chirp * gate + 0.6 * chirp2) * 0.035).astype(np.float32)
    if name == "rain":                            # nền 10 giây: mưa rào
        n = int(SR * 10)
        x = _filt(r.normal(0, 1, n).astype(np.float32), 0.75) * 0.18
        drops = np.zeros(n, np.float32)
        for _ in range(400):
            i = int(r.uniform(0, n - 400))
            drops[i:i + 300] += _hp(r.normal(0, 1, 300).astype(np.float32), 0.3) * _decay(300, 300) * 0.15
        return x + drops
    if name == "wind":
        n = int(SR * 10)
        x = _filt(r.normal(0, 1, n).astype(np.float32), 0.995) * 3
        mod = 0.6 + 0.4 * np.sin(2 * np.pi * 0.15 * np.arange(n) / SR)
        return (x * mod * 0.25).astype(np.float32)
    return np.zeros(int(SR * 0.1), np.float32)


def get(name: str) -> np.ndarray | None:
    """Tiếng động (24 kHz mono float32), tạo lần đầu rồi lưu file."""
    if name in _CACHE:
        return _CACHE[name]
    import soundfile as sf
    a = None
    for p in (DIR / f"{name}.wav", config.SFX_DIR / f"{name}.wav"):
        if p.exists():
            a, sr = sf.read(str(p), dtype="float32")
            if a.ndim > 1:
                a = a.mean(axis=1)
            if sr != SR:
                a = np.interp(np.linspace(0, len(a), int(len(a) * SR / sr), endpoint=False),
                              np.arange(len(a)), a).astype(np.float32)
            break
    if a is None:
        if name not in LABELS or name in ("bark", "meow", "gasp"):
            return None
        a = synth(name)
        m = float(np.max(np.abs(a))) or 1.0
        a = (a / m * 0.8).astype(np.float32) if name not in AMBIENT else a.astype(np.float32)
        try:
            DIR.mkdir(parents=True, exist_ok=True)
            sf.write(str(DIR / f"{name}.wav"), a, SR)
        except OSError:
            pass
    _CACHE[name] = a
    return a


def put(track: np.ndarray, name: str, at: float, vol: float = 0.5) -> None:
    a = get(name)
    if a is None:
        return
    i0 = int(at * SR)
    if i0 >= len(track) or i0 < 0:
        return
    seg = a[: len(track) - i0]
    track[i0:i0 + len(seg)] += seg * vol


def loop(track: np.ndarray, name: str, t0: float, t1: float, vol: float = 0.15) -> None:
    """Tiếng nền lặp từ t0 tới t1, có mờ vào / mờ ra."""
    a = get(name)
    if a is None or t1 <= t0:
        return
    i0, i1 = int(t0 * SR), min(len(track), int(t1 * SR))
    n = i1 - i0
    if n <= 0:
        return
    reps = int(np.ceil(n / len(a))) + 1
    off = int((int(t0 * 7) % 7) * SR) % len(a)
    seg = np.tile(a, reps)[off:off + n]
    f = min(n // 2, int(SR * 0.8))
    env = np.ones(n, np.float32)
    if f > 0:
        env[:f] = np.linspace(0, 1, f)
        env[-f:] = np.linspace(1, 0, f)
    track[i0:i1] += seg * env * vol
