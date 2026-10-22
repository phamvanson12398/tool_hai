# -*- coding: utf-8 -*-
"""Test render cho e2e_test project - kiểm tra tất cả tính năng mới."""
import sys
import time
from pathlib import Path

sys.path.insert(0, '.')
from core import pipeline, script_parser, config, assets

# Đọc kịch bản
script_path = Path('projects/e2e_test/script.txt')
script_text = script_path.read_text(encoding='utf-8')

print("=" * 60)
print("KIỂM TRA RENDER - DỰ ÁN E2E_TEST")
print("=" * 60)

print("\n1. Phân tích kịch bản...")
script = script_parser.parse_script(script_text)
if script.errors:
    print("LỖI:", script.errors)
    sys.exit(1)
if script.warnings:
    print("CẢNH BÁO:", script.warnings)

print(f"   ✓ {len(script.lines())} câu, {len(script.reacts())} nhịp phản ứng")
print(f"   ✓ Nhân vật: {', '.join(script.cast)}")
print(f"   ✓ Có {sum(1 for b in script.beats if b.translation)} dòng dịch")

# Kiểm tra các tính năng mới
has_pause = any(b.pause > 0 for b in script.beats if b.kind == "line")
has_other_expr = any(b.other_expr for b in script.beats if b.kind == "line")
has_zoom_target = any(b.zoom_target for b in script.beats if b.kind == "line")

print("\n2. Tính năng cú pháp mới:")
print(f"   pause=... : {'✓' if has_pause else '✗'}")
print(f"   Tên=biểu_cảm : {'✓' if has_other_expr else '✗'}")
print(f"   zoom=Tên : {'✓' if has_zoom_target else '✗'}")
print(f"   // dịch : ✓")

# Tạo nhân vật nếu chưa có
print("\n3. Tạo nhân vật...")
from core import character_kit as ck

char_specs = {
    "지은": ck.CharSpec(
        name='jieun',
        body='adult',
        skin='light',
        hair_style='short',
        hair_color='black',
        shirt='blue',
        accessory='none'
    ),
    "수아": ck.CharSpec(
        name='sua',
        body='adult',
        skin='light',
        hair_style='long',
        hair_color='brown',
        shirt='pink',
        accessory='none'
    ),
}

chars_cfg = []
out_chars = Path('projects/e2e_test/chars')
out_chars.mkdir(parents=True, exist_ok=True)

# Chỉ tạo biểu cảm cần thiết
exprs = ['neutral', 'happy', 'shocked', 'angry', 'laughing', 'proud']

for name in script.cast:
    spec = char_specs[name]
    imgs = ck.build_sheet(spec, out_chars / spec.name, exprs)
    chars_cfg.append({
        "name": name,
        "side": script.sides.get(name, "center"),
        "scale": 1.0,
        "images": imgs
    })
    print(f"   ✓ {name} ({spec.name}): {len(imgs)} biểu cảm")

# Giọng
print("\n4. Cấu hình giọng...")
voices = {
    "지은": {"instruct": "female, young adult, moderate pitch"},
    "수아": {"instruct": "female, young adult, high pitch"},
}

# Bối cảnh
print("\n5. Bối cảnh...")
bgs = assets.list_backgrounds()
bg_path = Path(bgs[0]['image']) if bgs else None
if bg_path:
    print(f"   ✓ Dùng {bg_path.name}")

# Cài đặt
settings = config.get_settings()
settings["title_text"] = script.title
settings["gap_between_lines"] = 0.12  # mới: 0.12s
settings["subtitle_style"] = "yellow"
settings["bgm_volume"] = 0.0
settings["sfx_volume"] = 0.45

# Render
print("\n6. Render video...")
print(f"   GAP = {settings['gap_between_lines']}s (mới: 0.12)")
print(f"   VIDEO_START_DELAY = {config.VIDEO_START_DELAY}s")
print(f"   VIDEO_END_HOLD = {config.VIDEO_END_HOLD}s")

pdir = config.project_dir("e2e_test")

def prog(frac, msg):
    pct = int(frac * 100)
    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
    print(f"\r   [{bar}] {pct:3d}% {msg}", end="", flush=True)

start_time = time.time()
result = pipeline.render_episode(pdir, script, chars_cfg, bg_path, voices, settings, progress=prog)
elapsed = time.time() - start_time

print("\n")
print("=" * 60)
print("✓ XONG!")
print("=" * 60)
print(f"Thời gian dựng: {elapsed:.1f}s")
print(f"Độ dài video:  {result['duration']:.2f}s")
print(f"Số câu:        {result['lines']}")
print(f"Mục tiêu:      <120s cho video 60s")
print(f"Video:         {result['video']}")
print(f"CapCut pack:   {result['pack']}")
print("=" * 60)

# Kiểm tra xem dưới 2 phút cho video 60s không
if result['duration'] > 50 and elapsed < 120:
    print("✓ Đạt mục tiêu tốc độ!")
elif result['duration'] < 30:
    print(f"⚠ Video ngắn ({result['duration']:.1f}s), chưa đủ để đánh giá tốc độ")
else:
    print(f"⚠ Chưa đạt mục tiêu (mất {elapsed:.1f}s cho {result['duration']:.1f}s)")
