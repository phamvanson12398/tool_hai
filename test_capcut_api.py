# -*- coding: utf-8 -*-
"""Kiểm tra API xuất dự án CapCut của web server (chạy server đã bật)."""
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8766"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


print("=== A) Chưa chọn dự án mẫu ===")
post("/api/settings", {"capcut_drafts_root": "", "capcut_template_draft": ""})
st, d = post("/api/project/e2e_test/capcut-export", {})
print(f"  HTTP {st}: {d.get('error')}")

print("\n=== B) Chọn dự án mẫu không tồn tại ===")
post("/api/settings", {"capcut_drafts_root": "", "capcut_template_draft": "KHONG_CO"})
st, d = post("/api/project/e2e_test/capcut-export", {})
print(f"  HTTP {st}: {d.get('error')}")

print("\n=== C) Chọn dự án mẫu hợp lệ (1021) ===")
post("/api/settings", {"capcut_drafts_root": "", "capcut_template_draft": "1021"})
st, d = post("/api/project/e2e_test/capcut-export", {})
print(f"  HTTP {st}: ok={d.get('ok')} name={d.get('name')}")
print(f"  path={d.get('path')}")
print(f"  message={d.get('message')}")

print("\n=== D) Tập chưa dựng xong ===")
st, d = post("/api/project/khong_ton_tai_abc/capcut-export", {})
print(f"  HTTP {st}: {d.get('error')}")

print("\n=== E) Trang chủ load được ===")
with urllib.request.urlopen(BASE + "/", timeout=30) as r:
    html = r.read().decode("utf-8")
for needle in ["btn-capcut-export", "s-capcut-root", "s-capcut-template",
               "btn-capcut-reload", "dl-mp4", "dl-pack"]:
    print(f"  {'OK ' if needle in html else 'THIẾU'} {needle}")
