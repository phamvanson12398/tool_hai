# -*- coding: utf-8 -*-
"""TTS: tạo giọng bằng OmniVoice, đo độ dài thật, cắt bỏ im lặng.

Có hai đường:
  * upload  — chị tải mẫu giọng sẵn (data/library/voices/<ten>.wav)
  * instruct — AI mô tả giọng, OmniVoice tạo giọng mẫu (instruct)

Mô hình OmniVoice giữ trong RAM/VRAM ở toàn cục (lazy load) vì mỗi lần gọi
generate nhanh (~0.3–1s), nhưng load model mất vài chục giây.
"""
from __future__ import annotations

import io
import sys
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from . import config as C

# Windows console hay mã hoá sai tiếng Hàn/Trung -> ép UTF-8 khi in log.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

_LOCK = threading.Lock()
_MODEL = None
_ASRLoaded = False

_VALID_INSTRUCT_ITEMS = [
    "female", "male", "child", "teenager", "young adult", "middle-aged",
    "elderly", "very low pitch", "low pitch", "moderate pitch",
    "high pitch", "very high pitch", "whisper",
    "american accent", "australian accent", "british accent",
    "canadian accent", "chinese accent", "indian accent", "japanese accent",
    "korean accent", "portuguese accent", "russian accent",
]


def _model():
    global _MODEL
    if _MODEL is None:
        import torch
        from omnivoice import OmniVoice
        with _LOCK:
            if _MODEL is None:
                _MODEL = OmniVoice.from_pretrained(
                    C.OMNIVOICE_MODEL,
                    device_map="cuda:0",
                    dtype=torch.float16,
                )
    return _MODEL


def unload() -> None:
    """Bỏ OmniVoice khỏi card (lần đọc sau tự nạp lại) — nhường card cho vẽ 3D."""
    global _MODEL
    if _MODEL is None:
        return
    with _LOCK:
        _MODEL = None
    import gc
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def load_asr():
    global _ASRLoaded
    m = _model()
    if not _ASRLoaded:
        with _LOCK:
            if not _ASRLoaded:
                m.load_asr_model()
                _ASRLoaded = True
    return m


def parse_instruct(s: str) -> list[str]:
    """Giữ chỉ các cụm OmniVoice hỗ trợ, tách bằng dấu phẩy."""
    if not s:
        return []
    parts = [p.strip().lower() for p in s.replace("，", ",").split(",")]
    keep = []
    for p in parts:
        if p in _VALID_INSTRUCT_ITEMS:
            keep.append(p)
    return keep


def trim_silence(a: np.ndarray, sr: int, thresh: float = 0.02,
                 keep: float = 0.06) -> np.ndarray:
    """Cắt bỏ im lặng đầu/cuối theo ngưỡng amplitude, giữ `keep` giây biên."""
    if a.size == 0:
        return a
    amp = np.abs(a)
    # smoothing để tránh nhói do noise
    k = max(1, int(sr * 0.02))
    smooth = np.convolve(amp, np.ones(k) / k, mode="same")
    # ngưỡng theo độ to của chính câu đó: câu đọc nhỏ (thì thầm, nói nhẹ)
    # không bị coi là im lặng rồi cắt mất chữ
    thresh = min(thresh, 0.08 * float(smooth.max()))
    voiced = np.where(smooth > thresh)[0]
    if voiced.size == 0:
        return a
    lo = max(0, int(voiced[0]) - int(keep * sr))
    hi = min(a.size, int(voiced[-1]) + int(keep * sr))
    return a[lo:hi]


def synthesize(text: str, language: str, *, ref_wav: Optional[Path] = None,
               ref_text: Optional[str] = None,
               instruct: Optional[str] = None,
               speed: Optional[float] = None,
               seed: Optional[int] = None) -> tuple[np.ndarray, int]:
    """Tạo giọng một câu. Ưu tiên: ref_wav > instruct > mặc định.

    Trả về (waveform float32, sample_rate).
    """
    from .tts_plugin import get_engine

    engine = get_engine()
    audio, sr, err = engine.synthesize(
        text,
        language=language,
        ref_audio=str(ref_wav) if ref_wav is not None else None,
        ref_text=ref_text,
        instruct=instruct,
        speed=speed,
        seed=seed,
    )
    if err or audio is None:
        raise RuntimeError(err or "Không tạo được giọng.")
    return audio, sr


def transcribe_ref(wav: Path) -> str:
    """Dùng Whisper (tích hợp OmniVoice) nghe mẫu giọng, trả về lời thoại."""
    m = load_asr()
    with _LOCK:
        txt = m.transcribe(str(wav))
    if isinstance(txt, dict):
        txt = txt.get("text", "")
    return str(txt).strip()


def synthesize_design(text: str, language: str, instruct: str,
                      speed: Optional[float] = None) -> tuple[np.ndarray, int]:
    """Tạo giọng theo mô tả (voice design) — dùng khi chị không tải mẫu."""
    return synthesize(text, language, instruct=instruct, speed=speed)


def preview_instruct(instruct: str, language: str = "en",
                     sample: str = "Hello, this is a test of the voice.") -> tuple[np.ndarray, int]:
    """Tạo một câu nghe thử giọng mô tả, để chị duyệt trước khi xác nhận."""
    return synthesize(sample, language, instruct=instruct, speed=None)


def to_wav_bytes(a: np.ndarray, sr: int) -> bytes:
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, a, sr, format="WAV")
    return buf.getvalue()
