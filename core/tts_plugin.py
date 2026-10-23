# -*- coding: utf-8 -*-
"""Lớp trừu tượng cho TTS engine, cho phép thay OmniVoice bằng engine khác
(edge-tts, ElevenLabs...) mà không cần sửa code gọi.

Để thêm engine mới:
1. Tạo class kế thừa TTSEngine
2. Implement các method: synthesize, is_ready, load
3. Đăng ký trong TTSRegistry
4. Chọn engine qua biến môi trường TTS_ENGINE hoặc settings
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import numpy as np


class TTSEngine(ABC):
    """Giao diện chung cho TTS engine."""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        *,
        language: str = "en",
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        instruct: Optional[str] = None,
        speed: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> tuple[Optional[np.ndarray], int, Optional[str]]:
        """Tạo giọng cho một câu.

        Returns:
            (waveform float32, sample_rate, error_message)
            Nếu thành công: (ndarray, sr, None)
            Nếu thất bại: (None, 0, "lỗi...")
        """
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Engine đã tải xong chưa."""
        pass

    @abstractmethod
    def load(self) -> tuple[bool, Optional[str]]:
        """Tải engine (nếu cần). Returns (success, error)."""
        pass

    def trim_silence(
        self, audio: np.ndarray, sr: int, threshold_db: float = -45.0, keep: float = 0.06
    ) -> np.ndarray:
        """Cắt im lặng ở đầu và cuối."""
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

    def duration_of(self, audio: np.ndarray, sr: int) -> float:
        return len(audio) / float(sr) if sr else 0.0


class OmniVoiceEngine(TTSEngine):
    """OmniVoice TTS (mặc định hiện tại)."""

    def __init__(self):
        self._model = None
        self._asr = None
        self._load_error: Optional[str] = None

    def synthesize(
        self,
        text: str,
        *,
        language: str = "en",
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        instruct: Optional[str] = None,
        speed: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> tuple[Optional[np.ndarray], int, Optional[str]]:
        from . import tts as tts_mod

        return tts_mod.synthesize(
            text,
            language=language,
            ref_audio=ref_audio,
            ref_text=ref_text,
            instruct=instruct,
            speed=speed,
            seed=seed,
        )

    def is_ready(self) -> bool:
        from . import tts as tts_mod

        return tts_mod.is_ready()

    def load(self) -> tuple[bool, Optional[str]]:
        from . import tts as tts_mod

        model, err = tts_mod.load_model()
        return (model is not None, err)


# Registry: đăng ký các engine có sẵn
_ENGINES: dict[str, type[TTSEngine]] = {
    "omnivoice": OmniVoiceEngine,
    # Thêm engine mới ở đây, VD:
    # "edge-tts": EdgeTTSEngine,
    # "elevenlabs": ElevenLabsEngine,
}


def get_engine(name: Optional[str] = None) -> TTSEngine:
    """Lấy engine theo tên. None = dùng mặc định từ settings/env."""
    if not name:
        from . import config

        try:
            name = config.load_settings().get("tts_engine")
        except Exception:
            pass
        if not name:
            name = os.environ.get("TTS_ENGINE", "omnivoice")
    name = (name or "omnivoice").lower().strip()
    cls = _ENGINES.get(name)
    if not cls:
        raise ValueError(
            f"TTS engine '{name}' không tồn tại. Các engine có sẵn: {', '.join(_ENGINES.keys())}"
        )
    return cls()


def list_engines() -> list[str]:
    """Danh sách tên engine đã đăng ký."""
    return list(_ENGINES.keys())
