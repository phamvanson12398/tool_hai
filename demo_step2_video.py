# -*- coding: utf-8 -*-
"""Bước 2b: dựng video mẫu đồng bộ (nhân vật + giọng + phụ đề + zoom)."""
import sys
from pathlib import Path

sys.path.insert(0, '.')
from core import pipeline, script_parser, config, character_kit as ck

# Kịch bản mẫu tiếng Hàn
script_text = """# tieu_de: 날씨 대화
# ngon_ngu: ko
# nhan_vat: 지은=trai, 수아=phai

수아 (happy): 와, 오늘 날씨 정말 좋다!
지은 (neutral): 응, 산책하기 딱 좋은데.
> 수아 (shocked, zoom, boing) 0.8
수아 (angry, zoom): 근데 너 우산 안 가져왔지?
지은 (embarrassed): 어… 깜빡했어.
"""

print("Phan tich kich ban...")
script = script_parser.parse_script(script_text)
if script.errors:
    print("LOI:", script.errors)
    sys.exit(1)
print(f"  {len(script.lines())} cau, {len(script.reacts())} nhip phan ung")

# Tạo nhân vật từ bộ phận
print("\nTao nhan vat tu bo phan...")
spec1 = ck.CharSpec(
    name='jieun',
    body='adult',
    skin='light',
    hair_style='wavy',
    hair_color='brown',
    shirt='blue',
    accessory='glasses',
    blush=True
)
spec2 = ck.CharSpec(
    name='sua',
    body='adult',
    skin='light',
    hair_style='long',
    hair_color='black',
    shirt='pink',
    accessory='none',
    blush=False
)

out_chars = Path('data/previews/demo_chars')
out_chars.mkdir(parents=True, exist_ok=True)

imgs1 = ck.build_sheet(spec1, out_chars / 'jieun',
                       ['neutral', 'happy', 'shocked', 'angry', 'embarrassed'])
imgs2 = ck.build_sheet(spec2, out_chars / 'sua',
                       ['neutral', 'happy', 'shocked', 'angry'])

chars_cfg = [
    {"name": "지은", "side": "left", "scale": 1.0, "images": imgs1},
    {"name": "수아", "side": "right", "scale": 1.0, "images": imgs2},
]

# Giọng nói (dùng voice design vì không có mẫu)
voices = {
    "지은": {"ko": {"instruct": "female, young adult, moderate pitch"}},
    "수아": {"ko": {"instruct": "female, young adult, high pitch"}},
}

# Bối cảnh đơn giản
print("Tao boi canh...")
from PIL import Image, ImageDraw
bg = Image.new("RGB", (1080, 1920), (135, 206, 235))
d = ImageDraw.Draw(bg)
d.rectangle([0, 1400, 1080, 1920], fill=(100, 180, 100))
bg_path = Path('data/previews/demo_bg.jpg')
bg.save(bg_path)

# Render
print("\nDung video...")
pdir = Path('data/previews/demo_project')
pdir.mkdir(parents=True, exist_ok=True)

settings = config.get_settings()
settings["title_text"] = ""
settings["gap_between_lines"] = 0.1
settings["subtitle_style"] = "yellow"

def prog(frac, msg):
    print(f"  [{int(frac*100):3d}%] {msg}")

result = pipeline.render_episode(pdir, script, chars_cfg, bg_path, voices, settings, progress=prog)

print(f"\nXong buoc 2b!")
print(f"  Video: {result['video']}")
print(f"  Do dai: {result['duration']:.2f}s")
print(f"  CapCut pack: {result['pack']}")
