#!/usr/bin/env python3
"""Test Bước D: render qua pipeline.render_episode với enable_rig=True."""
import sys
import time
import shutil
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from core import pipeline, config
from core.script_parser import parse_script
from core.character_kit import CharSpec
from core import rig as rig_mod

PROJECT = Path("projects/e2e_test")
RIG_JIEUN = PROJECT / "out" / "rig_step_b" / "rig_jieun"
RIG_SUA = PROJECT / "out" / "rig_step_b" / "rig_sua"

def make_voice_audio(wav_path, duration, sr=24000):
    """Tạo âm thanh giả (sinusoid) nếu không có file giọng."""
    t = np.arange(int(duration * sr)) / sr
    audio = 0.3 * np.sin(2 * np.pi * 440 * t)
    return audio

def main():
    print("=== BƯỚC D: render qua pipeline với enable_rig ===")
    outdir = Path("projects/e2e_test/out") / "rig_step_d"
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    script_text = """# tieu_de: 테스트
# ngon_ngu: ko
# nhan_vat: 지은=trai, 수아=phai

지은 (happy): 안녕하세요, 저예요!
수아 (happy, 지은=proud): 그래, 반가워!
지은 (shocked): 정말요?
수아 (laughing): 장난이에요!
"""
    script = parse_script(script_text)
    if script.errors:
        print("LỖI parse:", script.errors)
        return
    print(f"Parse OK: {len(script.beats)} nhịp")

    # Nâng chars_cfg thành kit với rig từ Bước B
    chars_cfg = [
        {
            "name": "지은",
            "side": "left",
            "mode": "kit",
            "spec": {"body": "adult", "skin": "fair", "hair_style": "long",
                     "hair_color": "brown", "shirt": "pink"},
            "image": str(RIG_JIEUN / "parts" / "dau_dong.png"),
            "scale": 1.0,
        },
        {
            "name": "수아",
            "side": "right",
            "mode": "kit",
            "spec": {"body": "adult", "skin": "light", "hair_style": "short",
                     "hair_color": "black", "shirt": "blue"},
            "image": str(RIG_SUA / "parts" / "dau_dong.png"),
            "scale": 1.0,
        },
    ]

    # Giọng giả (không cần gọi Claude, dùng file audio có sẵn)
    voices = {
        "지은": {"ref": str(PROJECT / "audio" / "line_000.wav")},
        "수아": {"ref": str(PROJECT / "audio" / "line_001.wav")},
    }

    settings = {
        "enable_rig": True,
        "gap_between_lines": 0.1,
        "title_text": "테스트",
        "subtitle_style": "yellow",
    }

    print("Bắt đầu render (enable_rig=True)...")
    t0 = time.time()
    try:
        result = pipeline.render_episode(
            outdir, script, chars_cfg, bg_path=None,
            voices=voices, settings=settings, progress=None,
        )
        elapsed = time.time() - t0
        print(f"\n✓ Render XONG:")
        print(f"  Video: {result['video']}")
        print(f"  Thời gian: {elapsed:.1f}s")
        print(f"  Độ dài video: {result['duration']:.1f}s")
        print(f"  Số câu: {result['lines']}")
        if Path(result['video']).exists():
            print(f"  Kích thước: {Path(result['video']).stat().st_size // 1024} KB")
        # Ước lượng tốc độ cho video 60s
        if result['duration'] > 0:
            ratio = elapsed / result['duration']
            print(f"  Tỷ lệ render: {ratio:.1f}x")
            est60 = ratio * 60
            print(f"  Dự kiến video 60s: {est60:.0f}s (mục tiêu <300s)")
    except Exception as e:
        import traceback
        print(f"✗ LỖI render: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
