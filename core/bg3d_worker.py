# -*- coding: utf-8 -*-
"""Chương trình con vẽ ảnh nền 3D (SDXL) rồi thoát.

Chạy riêng để Stable Diffusion không để lại gì trong chương trình chính (móc offload của
accelerate, bộ nhớ card...) làm OmniVoice nạp lỗi ("Tensor on device meta is not on the
expected device cuda:0"). Đọc danh sách việc (JSON) từ stdin:
[{"prompt", "size": [w, h], "seed", "path"}], in "START i" / "DONE i" ra stdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    jobs = json.loads(sys.stdin.read() or "[]")
    from core import bg3d
    for i, j in enumerate(jobs):
        print(f"START {i}", flush=True)
        img = bg3d.generate(j["prompt"], (int(j["size"][0]), int(j["size"][1])), int(j["seed"]))
        p = Path(j["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        img.save(p)
        print(f"DONE {i}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
