# -*- coding: utf-8 -*-
"""OmniVoice + Whisper: tạo giọng từng câu, đo độ dài thật, nhận diện mẫu giọng.

Thiết kế: tải mô hình một lần rồi giữ trong bộ nhớ (lazy singleton) vì
mỗi lần tải mất ~10 giây và chiếm ~3.5 GB VRAM.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from . import config as C

_lock = threading.Lock()
_model = None
_asr = None
_load_error: Optional[str] = None

# Từ vựng "instruct" mà OmniVoice chấp nhận (đã kiểm chứng trên máy này).
VALID_INSTRUCT_ITEMS = [
    "female", "male", "child", "teenager", "young adult", "middle-aged",
    "elderly", "low pitch", "moderate pitch", "high pitch",
    "very low pitch", "very high pitch", "whisper",
    "american accent", "australian accent", "british accent", "canadian accent",
    "chinese accent", "indian accent", "japanese accent", "korean accent",
    "portuguese accent", "russian accent",
]


def _resolve_instruct(text: str) -> str:
    """Lọc mô tả giọng về đúng từ vựng OmniVoice chấp nhận.

    Chị có thể gõ tự do ("nữ, trẻ, giọng cao, vui tươi") nhưng OmniVoice chỉ
    hiểu một tập từ hữu hạn, nên ta giữ lại các từ khớp và bỏ phần còn lại.
    """
    if not text:
        return ""
    keep = []
    for part in re.split(r"[,\n]", text):
        p = part.strip().lower()
        if not p:
            continue
        if p in VALID_INSTRUCT_ITEMS:
            keep.append(p)
            continue
        # cho phép "giọng trầm" -> "low pitch", "trẻ" -> "young adult" ...
        for item in VALID_INSTRUCT_ITEMS:
            if item in p:
                keep.append(item)
                break
    # bỏ trùng, giữ thứ tự
    seen, out = set(), []
    for k in keep:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return ", ".join(out)


def load_model(force: bool = False):
    """Tải OmniVoice lên GPU. Trả về (model, None) hoặc (None, lỗi)."""
    global _model, _load_error
    with _lock:
        if _model is not None and not force:
            return _model, None
        if _load_error and not force:
            return None, _load_error
        try:
            import torch
            from omnivoice import OmniVoice

            if not torch.cuda.is_available():
                return None, "Không thấy GPU NVIDIA. OmniVoice cần CUDA."
            _model = OmniVoice.from_pretrained(
                "k2-fsa/OmniVoice", device_map="cuda:0", dtype=torch.float16
            )
            _load_error = None
            return _model, None
        except Exception as e:  # noqa: BLE001
            _load_error = f"{type(e).__name__}: {e}"
            return None, _load_error


def is_ready() -> bool:
    return _model is not None


# ---------------------------------------------------------------- giọng đọc

def synthesize(
    text: str,
    *,
    language: str = "en",
    ref_audio: Optional[str] = None,
    ref_text: Optional[str] = None,
    instruct: Optional[str] = None,
    speed: Optional[float] = None,
    seed: Optional[int] = None,
) -> tuple[Optional[np.ndarray], int, Optional[str]]:
    """Tạo giọng cho một câu. Trả về (waveform, sample_rate, lỗi).

    seed: cố định độ ngẫu nhiên của mô hình (cùng seed + cùng đầu vào -> cùng
    giọng), dùng để giọng mẫu tạo từ mô tả không đổi giữa các lần dựng.

    Ba chế độ, ưu tiên theo thứ tự:
      1. ref_audio  -> nhân giọng từ mẫu (chính xác nhất, dùng mặc định)
      2. instruct   -> AI mô tả giọng (chỉ tiếng Anh/Trung, từ vựng hạn chế)
      3. không cả hai -> mô hình tự chọn giọng
    """
    model, err = load_model()
    if err:
        return None, 0, err

    lang_name = C.LANGUAGES.get(language, {}).get("voice_lang", "English")
    kwargs = {"language": lang_name}
    if speed:
        kwargs["speed"] = speed

    if ref_audio and Path(ref_audio).exists():
        kwargs["ref_audio"] = ref_audio
        if ref_text:
            kwargs["ref_text"] = ref_text
    elif instruct:
        resolved = _resolve_instruct(instruct)
        if not resolved:
            return None, 0, (
                "Mô tả giọng không khớp từ vựng OmniVoice. "
                f"Dùng một trong: {', '.join(VALID_INSTRUCT_ITEMS[:8])}..."
            )
        kwargs["instruct"] = resolved

    try:
        if seed is not None:
            import torch
            torch.manual_seed(int(seed))
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(int(seed))
        out = model.generate(text=text, **kwargs)
        audio = out[0] if isinstance(out, (list, tuple)) else out
        audio = np.asarray(audio, dtype=np.float32)
        return audio, C.SAMPLE_RATE, None
    except Exception as e:  # noqa: BLE001
        return None, 0, f"{type(e).__name__}: {e}"


# ------------------------------------------------------------- nhận diện giọng

def transcribe(ref_audio: str, language: Optional[str] = None) -> tuple[str, Optional[str]]:
    """Whisper tự nghe và ghi lại lời của đoạn mẫu giọng."""
    global _asr
    try:
        if _asr is None:
            from faster_whisper import WhisperModel

            device = "cuda"
            try:
                import torch
                if not torch.cuda.is_available():
                    device = "cpu"
            except Exception:  # noqa: BLE001
                device = "cpu"
            _asr = WhisperModel("large-v3", device=device, compute_type="float16"
                                if device == "cuda" else "int8")
        segments, _info = _asr.transcribe(
            ref_audio,
            language=language,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        return text, None
    except Exception as e:  # noqa: BLE001
        return "", f"{type(e).__name__}: {e}"


# ------------------------------------------------------------------ tiện ích

def trim_silence(audio: np.ndarray, sr: int, threshold_db: float = -45.0,
                 keep: float = 0.06) -> np.ndarray:
    """Cắt im lặng ở đầu và cuối (giữ lại một chút để không bị cụt)."""
    if audio.size == 0:
        return audio
    peak = float(np.max(np.abs(audio))) or 1.0
    thresh = peak * (10 ** (threshold_db / 20.0))
    idx = np.where(np.abs(audio) >= thresh)[0]
    if idx.size == 0:
        return audio
    pad = int(keep * sr)
    a = max(0, int(idx[0]) - pad)
    b = min(audio.size, int(idx[-1]) + pad)
    return audio[a:b]


def duration_of(audio: np.ndarray, sr: int) -> float:
    return len(audio) / float(sr) if sr else 0.0
