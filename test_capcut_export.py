# -*- coding: utf-8 -*-
"""Chạy thử Bước D: kiểm tra luồng xuất dự án CapCut qua module + API.

- dùng dự án mẫu thật (1021) làm template
- xuất thử một dự án mới từ projects/e2e_test
- kiểm tra nhánh lỗi "mã hoá" trả về đúng thông báo tiếng Việt
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# Windows console mặc định cp1252 không in được tiếng Việt/Hàn
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import capcut_export, config  # noqa: E402

CAPCUT_ROOT = Path(os.environ["LOCALAPPDATA"]) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
PROJECT = ROOT / "projects" / "e2e_test"

print("=" * 60)
print("1. Đường dẫn dự án CapCut:", config.capcut_drafts_root())
print("   Dự án có sẵn:", capcut_export.list_draft_names(CAPCUT_ROOT))

# --- Dùng dự án mẫu 1021 (dự án chị đã tạo, có video + audio + text) ---
template = CAPCUT_ROOT / "1021"
print("\n2. Kiểm tra dự án mẫu đọc được JSON:")
data = capcut_export.check_template_readable(template)
print("   OK — tracks:", len(data["tracks"]), "| materials.videos:", len(data["materials"]["videos"]))

# --- Nhánh lỗi: file mã hoá / không phải JSON ---
print("\n3. Nhánh lỗi file mã hoá:")
with tempfile.TemporaryDirectory() as td:
    bad = Path(td) / "bad_draft"
    bad.mkdir()
    (bad / "draft_content.json").write_bytes(b"\x00\x01\x02not-json-encrypted")
    try:
        capcut_export.check_template_readable(bad)
        print("   !! KHÔNG báo lỗi (sai)")
    except capcut_export.CapCutEncryptedError as e:
        print("   OK —", e)

# --- Xuất thật ---
print("\n4. Xuất dự án mới từ projects/e2e_test:")
exp = capcut_export.CapCutExporter(CAPCUT_ROOT, template)
folder = exp.export_project(PROJECT)
print("   TÊN DỰ ÁN:", folder.name)
print("   THƯ MỤC:", folder)

# --- Kiểm tra kết quả ---
print("\n5. Kiểm tra dự án vừa tạo:")
proj = json.loads((folder / "Timelines" / "project.json").read_text(encoding="utf-8"))
tid = proj["main_timeline_id"]
o = json.loads((folder / "Timelines" / tid / "draft_content.json").read_text(encoding="utf-8"))
print("   id khớp timeline:", o["id"] == tid)
for t in o["tracks"]:
    print(f'   track {t["type"]:<6} name={t.get("name")!r:<14} segments={len(t["segments"])}')
print("   media:", sorted(p.name for p in (folder / "media").glob("*")))
print("   video:", [p.name for p in folder.glob("*.mp4")])

# --- Đăng ký trong index? ---
rm = json.loads((CAPCUT_ROOT / "root_meta_info.json").read_text(encoding="utf-8"))
names = [x["draft_name"] for x in rm["all_draft_store"]]
print("   root_meta có dự án:", folder.name in names)
print("   root_meta:", names)
print("\nHOÀN TẤT.")
