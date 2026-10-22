# -*- coding: utf-8 -*-
"""Bước 1: tạo mẫu nhân vật để chị xem phong cách bộ phận."""
import sys
from pathlib import Path

sys.path.insert(0, '.')
from core import character_kit as ck

# 3 nhân vật mẫu
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

spec3 = ck.CharSpec(
    name='minjun',
    body='child',
    skin='medium',
    hair_style='short',
    hair_color='black',
    shirt='red',
    accessory='none',
    blush=False
)

out = Path('data/previews')
out.mkdir(parents=True, exist_ok=True)

print("Tao anh xem truoc dan nhan vat...")
preview = ck.preview_cast([spec1, spec2, spec3], out / 'sample_cast.jpg')
print(f'Anh xem truoc: {preview}')

print("\nXuat bo anh day du cua jieun (4 bieu cam)...")
out_sheet = out / 'jieun_sheet'
images = ck.build_sheet(spec1, out_sheet, ['neutral', 'happy', 'shocked', 'angry'])
print(f'Bo anh cua jieun ({len(images)} bieu cam):')
for expr, paths in images.items():
    print(f'  {expr}: mo={Path(paths["mo"]).name}, dong={Path(paths["dong"]).name}')

print("\nXong buoc 1.")
