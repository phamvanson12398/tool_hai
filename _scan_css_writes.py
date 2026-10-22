"""Liệt kê mọi lần ghi web/static/app.css trong lịch sử session Claude Code.

Dự án không phải git repo; file app.css đã bị ghi đè nhầm. Script này quét
session logs, tìm các tool_use có file_path kết thúc bằng app.css, và ghi
lại (timestamp, session, tool, độ dài nội dung) ra file text thuần ASCII.
"""

import glob
import json
import os
import sys

SESS = os.path.expanduser(
    r"~\.claude\projects\c--Users-balha-Downloads-tool-hoat-hinh"
)
OUT = r"C:\Users\balha\Downloads\tool_hoat_hinh\_css_writes.txt"


def walk(obj, ts, sid, rows):
    if isinstance(obj, dict):
        if obj.get("type") == "tool_use":
            inp = obj.get("input") or {}
            fp = str(inp.get("file_path", ""))
            if fp.endswith("app.css"):
                cmd = inp.get("command") or (
                    "WRITE" if "content" in inp else "EDIT"
                )
                body = inp.get("content") or inp.get("new_string") or ""
                rows.append(
                    (ts[:19], sid[:8], cmd, len(body), body[:100])
                )
        for v in obj.values():
            walk(v, ts, sid, rows)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, ts, sid, rows)


def main():
    rows = []
    for path in glob.glob(os.path.join(SESS, "*.jsonl")):
        sid = os.path.basename(path)[:8]
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if "app.css" not in line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                walk(obj, line[:19], sid, rows)
    rows.sort(key=lambda r: r[0])
    with open(OUT, "w", encoding="utf-8") as fh:
        for ts, sid, cmd, n, body in rows:
            fh.write(
                "%s %s %-6s len=%-6d %s\n"
                % (ts, sid, cmd, n, body.encode("ascii", "replace").decode())
            )
        fh.write("TOTAL %d\n" % len(rows))
    print("wrote", OUT, "rows:", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
