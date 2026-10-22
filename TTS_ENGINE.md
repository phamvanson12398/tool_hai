# Hướng dẫn thêm TTS Engine mới

Tool hiện dùng **OmniVoice** làm engine TTS mặc định. Để thay bằng engine khác (edge-tts, ElevenLabs, v.v.), làm theo các bước sau:

## 1. Tạo class engine mới

Tạo file `core/tts_<tên>.py`, ví dụ `core/tts_edge.py`:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Optional
import numpy as np
from .tts_plugin import TTSEngine

class EdgeTTSEngine(TTSEngine):
    """Edge TTS (Microsoft Text-to-Speech)."""

    def __init__(self):
        self._voices = {}  # cache giọng đã tải

    def synthesize(
        self,
        text: str,
        *,
        language: str = "en",
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        instruct: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> tuple[Optional[np.ndarray], int, Optional[str]]:
        """Tạo giọng bằng Edge TTS."""
        try:
            import edge_tts
            import asyncio
            # Logic tạo giọng ở đây...
            # Trả về (waveform, sample_rate, None) nếu thành công
            # hoặc (None, 0, "lỗi...") nếu thất bại
        except Exception as e:
            return None, 0, f"Edge TTS lỗi: {e}"

    def is_ready(self) -> bool:
        """Kiểm tra edge_tts đã cài chưa."""
        try:
            import edge_tts
            return True
        except ImportError:
            return False

    def load(self) -> tuple[bool, Optional[str]]:
        """Edge TTS không cần load model trước."""
        return self.is_ready(), None if self.is_ready() else "Chưa cài edge-tts"
```

## 2. Đăng ký engine

Mở `core/tts_plugin.py`, thêm vào `_ENGINES`:

```python
from .tts_edge import EdgeTTSEngine  # import class mới

_ENGINES: dict[str, type[TTSEngine]] = {
    "omnivoice": OmniVoiceEngine,
    "edge-tts": EdgeTTSEngine,      # <-- thêm dòng này
}
```

## 3. Chọn engine

### Cách 1: Biến môi trường

```bash
export TTS_ENGINE=edge-tts
python web/server.py
```

### Cách 2: File cài đặt

Thêm vào `data/settings.json`:

```json
{
  "tts_engine": "edge-tts",
  ...
}
```

### Cách 3: Gọi trực tiếp trong code

```python
from core.tts_plugin import get_engine

engine = get_engine("edge-tts")
audio, sr, err = engine.synthesize("Hello world", language="en")
```

## 4. Cập nhật core/voice.py (nếu cần)

Nếu muốn toàn bộ tool dùng engine mới, sửa `core/voice.py`:

```python
from .tts_plugin import get_engine

def synthesize(text: str, language: str, **kwargs):
    engine = get_engine()  # đọc từ settings/env
    return engine.synthesize(text, language=language, **kwargs)
```

## Engine hiện có

- **omnivoice** (mặc định): AI TTS chất lượng cao, cần GPU, hỗ trợ voice cloning
- *(Thêm engine khác ở đây khi có)*

## Ví dụ engine khác có thể thêm

- **edge-tts**: Microsoft TTS miễn phí, không cần GPU, nhiều giọng
- **elevenlabs**: Chất lượng cao nhất, trả phí, API key
- **coqui-tts**: Open source, local, nhiều model
- **pyttsx3**: Offline, dùng giọng hệ thống, đơn giản
