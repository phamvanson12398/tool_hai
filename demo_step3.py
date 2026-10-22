# -*- coding: utf-8 -*-
"""Bước 3: video mẫu đủ độ dài (30-60s) để chị duyệt."""
import sys
from pathlib import Path

sys.path.insert(0, '.')
from core import pipeline, script_parser, config, character_kit as ck

# Kịch bản đủ dài
script_text = """# tieu_de: 피카츄의 하루
# ngon_ngu: ko
# nhan_vat: 피카츄=trai, 잠만보=phai

피카츄 (happy): 안녕! 나는 피카츄야!
잠만보 (tired): 하아... 피곤해...
피카츄 (proud): 전기 기술 보여줄까?
> 잠만보 (shocked, zoom, boing) 0.8
잠만보 (angry, zoom): 안돼! 자고 싶어!
피카츄 (happy, zoom): 그럼 같이 자자!
잠만보 (embarrassed): 음... 그래...
피카츄 (smug): 근데 나 코고 자는 거 알아?
> 잠만보 (shocked, zoom, gasp) 0.6
잠만보 (worried): 뭐? 진짜?!
피카츄 (laughing, zoom): 장난이야! 각성하지 마!
잠만보 (neutral): 하... 재미있구나.
피카츄 (proud): 그럼 어디 한번 더 보여줄까?
> 잠만보 (embarrassed, zoom, thud) 0.5
잠만보 (tired): 이제 정말 자야겠어...
피카츄 (tired): 알았어... 나도 졸려...
피카츄 (neutral): 그럼 내일 보자!
잠만보 (neutral): 잘 자...
> 피카츄 (happy, zoom, ding) 0.4
"""

print("Phan tich kich ban...")
script = script_parser.parse_script(script_text)
if script.errors:
    print("LOI:", script.errors)
    sys.exit(1)
print(f"  {len(script.lines())} cau, {len(script.reacts())} nhip phan ung")

# Tạo nhân vật
print("\nTao nhan vat...")
spec1 = ck.CharSpec(
    name='pikachu',
    body='child',
    skin='light',
    hair_style='short',
    hair_color='yellow',
    shirt='yellow',
    accessory='none',
    blush=True
)

spec2 = ck.CharSpec(
    name='snorlax',
    body='adult',
    skin='medium',
    hair_style='short',
    hair_color='black',
    shirt='blue',
    accessory='none',
    blush=False
)

out_chars = Path('data/previews/demo3_chars')
out_chars.mkdir(parents=True, exist_ok=True)

# Tạo đủ bộ biểu cảm
exprs1 = ['neutral', 'happy', 'proud', 'shocked', 'angry', 'laughing',
          'embarrassed', 'smug', 'worried', 'tired']
exprs2 = ['neutral', 'tired', 'shocked', 'angry', 'embarrassed', 'worried']

imgs1 = ck.build_sheet(spec1, out_chars / 'pikachu', exprs1)
imgs2 = ck.build_sheet(spec2, out_chars / 'snorlax', exprs2)

chars_cfg = [
    {"name": "피카츄", "side": "left", "scale": 1.0, "images": imgs1},
    {"name": "잠만보", "side": "right", "scale": 1.1, "images": imgs2},
]

# Giọng
voices = {
    "피카츄": {"ko": {"instruct": "child, female, high pitch"}},
    "잠만보": {"ko": {"instruct": "male, middle-aged, low pitch"}},
}

# Bối cảnh
print("Tao boi canh...")
from PIL import Image, ImageDraw
bg = Image.new("RGB", (1080, 1920), (180, 220, 180))
d = ImageDraw.Draw(bg)
d.rectangle([0, 1400, 1080, 1920], fill=(120, 160, 100))
bg_path = Path('data/previews/demo3_bg.jpg')
bg.save(bg_path)

# Render
print("\nDung video 30+ giay...")
pdir = Path('data/previews/demo3_project')
pdir.mkdir(parents=True, exist_ok=True)

settings = config.get_settings()
settings["title_text"] = "피카츄의 하루"
settings["gap_between_lines"] = 0.12
settings["subtitle_style"] = "yellow"

def prog(frac, msg):
    print(f"  [{int(frac*100):3d}%] {msg}")

result = pipeline.render_episode(pdir, script, chars_cfg, bg_path, voices, settings, progress=prog)

print(f"\n{'='*60}")
print(f"XONG BƯỚC 3!")
print(f"  Video: {result['video']}")
print(f"  Độ dài: {result['duration']:.2f}s")
print(f"  CapCut pack: {result['pack']}")
print(f"{'='*60}\n")
print("Hãy mở file video để kiểm tra:")
print(f"  {Path(result['video']).absolute()}")
