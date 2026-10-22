# -*- coding: utf-8 -*-
"""Bước 2: kiểm tra giọng nói tiếng Hàn và tiếng Anh với OmniVoice."""
import sys
from pathlib import Path

sys.path.insert(0, '.')
from core import voice as voice_mod
import soundfile as sf

out = Path('data/previews')
out.mkdir(parents=True, exist_ok=True)

print("Kiem tra OmniVoice...")

def save(text, language, instruct, filename):
    print(f"\n  [{filename}] {instruct}...")
    a, sr = voice_mod.synthesize(text, language, instruct=instruct)
    sf.write(str(out / filename), a, sr)
    dur = len(a) / sr
    print(f"    OK ({dur:.2f}s)")

save("안녕하세요! 오늘 날씨가 정말 좋네요.", "ko",
     "female, young adult, moderate pitch", "voice_ko_sample.wav")

save("Hello! The weather is really nice today.", "en",
     "male, middle-aged, low pitch", "voice_en_sample.wav")

save("Oh my gosh, that's so funny!", "en",
     "female, young adult, high pitch", "voice_en_female.wav")

print("\nXong buoc 2. Hay nghe 3 file trong data/previews.")
