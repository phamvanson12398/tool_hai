# -*- coding: utf-8 -*-
"""Chương trình con dựng một đoạn khung hình của video webtoon (chạy song song nhiều cái
trên các nhân CPU). Đọc file việc JSON (st, rows, prevs, fi0, fi1, out, ffmpeg), dựng các
khung fi0..fi1-1 ghi thẳng ra file mp4 của đoạn, in "F <số khung đã xong>" để báo tiến độ."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    from core import webtoon_film as wf
    size = tuple(job["size"])
    proc = wf._ffmpeg_writer(job["ffmpeg"], size, Path(job["out"]), bool(job.get("gpu")))
    done = [0]

    def tick(m):
        done[0] += m
        print(f"F {done[0]}", flush=True)
    try:
        wf.render_range(job["st"], Path(job["pdir"]) if job.get("pdir") else None, size, job["rows"],
                        job["prevs"], int(job["fi0"]), int(job["fi1"]), proc.stdin.write, tick)
    finally:
        proc.stdin.close()
        code = proc.wait()
    print(f"F {int(job['fi1']) - int(job['fi0'])}", flush=True)
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
