"""Trích CSS gốc của app.css từ tool_result (Read output) trong session logs.

CSS gốc dùng biến `--maxw` và `--gutter` — đây là dấu hiệu không nằm trong các
bản template viết lại sau này. Script quét mọi chuỗi trong tool_result, giữ
chuỗi dài chứa các dấu hiệu đó, và ghi bản dài nhất ra file.
"""

import glob
import json
import os
import sys

SESS = os.path.expanduser(
    r"~\.claude\projects\c--Users-balha-Downloads-tool-hoat-hinh"
)
OUT = r"C:\Users\balha\Downloads\tool_hoat_hinh\_orig_app.css"

MARKERS = ("--maxw", "--gutter", ".stage-wrap")


def walk(obj, out):
    if isinstance(obj, dict):
        for v in obj.values():
            walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, out)
    elif isinstance(obj, str):
        out.append(obj)


def main():
    cands = []
    for path in glob.glob(os.path.join(SESS, "*.jsonl")):
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if "--maxw" not in line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                found = []
                walk(obj, found)
                for s in found:
                    if len(s) < 5000:
                        continue
                    if not all(m in s for m in MARKERS):
                        continue
                    cands.append(s)
    if not cands:
        print("KHONG TIM THAY CSS GOC")
        return 1
    best = max(cands, key=len)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(best)
    print("WROTE", len(best), "->", OUT)
    print("HEAD:", best[:90].encode("ascii", "replace").decode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
