#!/usr/bin/env python3
"""Test Bước D: render với cử động bật."""
import sys
import time
from pathlib import Path
import tempfile
import shutil

# Add parent to path để import core
sys.path.insert(0, str(Path(__file__).parent))

from core import pipeline, config
from core.script_parser import parse_script

def test_rig_render():
    """Tạo một video ngắn với cử động bật."""
    print("=== Test D: Render với cử động ===")

    # Tạo thư mục tạm
    tmpdir = Path(tempfile.mkdtemp(prefix="rig_render_"))
    print(f"Thư mục tạm: {tmpdir}")

    try:
        # Kịch bản ngắn
        script_text = """# Test cử động
Alice [neutral, vaytay]: Xin chào! [zoom]
Bob [happy, giodau]: Chào bạn.
>
Alice [excited, nhunvai]: Hẹn gặp lại!
"""
        script = parse_script(script_text)

        # Nhân vật kit (copy từ test_step_b.py)
        # Cần có thư mục data/characters/alice với parts + rig.json
        # Vì chưa chắc có, tạo nhân vật giả từ 1 ảnh tĩnh
        chars_cfg = [
            {
                "name": "Alice",
                "side": "left",
                "mode": "kit",
                "image": "data/characters/alice/dau_dong.png",  # giả sử có
                "spec": {
                    "dau": "dau", "thantren": "thantren", "tay": "tay"
                },
                "scale": 1.0,
            },
            {
                "name": "Bob",
                "side": "right",
                "mode": "kit",
                "image": "data/characters/bob/dau_dong.png",
                "spec": {"dau": "dau", "thantren": "thantren", "tay": "tay"},
                "scale": 1.0,
            }
        ]

        # Giọng
        voices = {"Alice": "vi-VN-HoaiMyNeural", "Bob": "vi-VN-NamMinhNeural"}

        # Settings: bật cử động
        settings = {
            "enable_rig": True,
            "gap_between_lines": 0.1,
            "title_text": "Test Cử Động",
            "subtitle_style": "yellow",
        }

        print("Bắt đầu render...")
        t0 = time.time()
        result = pipeline.render_episode(
            tmpdir, script, chars_cfg, bg_path=None, voices=voices,
            settings=settings, progress=None
        )
        elapsed = time.time() - t0

        mp4 = result.get("mp4")
        dur = result.get("duration", 0)
        print(f"\n✓ Render xong: {mp4}")
        print(f"  Thời gian: {elapsed:.1f}s")
        print(f"  Độ dài video: {dur:.1f}s")

        if mp4 and Path(mp4).exists():
            print(f"  Kích thước: {Path(mp4).stat().st_size // 1024} KB")

        # Đo tốc độ: video 60s nên dựng dưới 5 phút (300s)
        # Với test này (video ~5s), tốc độ tương đối là elapsed/dur
        if dur > 0:
            ratio = elapsed / dur
            print(f"  Tỉ lệ render: {ratio:.1f}x (mục tiêu <5 cho video 60s)")

    finally:
        # Dọn dẹp
        if tmpdir.exists():
            shutil.rmtree(tmpdir, ignore_errors=True)
        print("Đã dọn dẹp.")

if __name__ == "__main__":
    test_rig_render()
