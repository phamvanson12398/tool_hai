# -*- coding: utf-8 -*-
"""Gọi Gemini CLI (headless) — dùng cho các việc phụ để đỡ tốn hạn mức Claude.

`gemini -p ... --output-format json` trả về {"response": "...", "stats": ...}.
Prompt gửi qua stdin (Gemini CLI ghép stdin vào trước nội dung -p) để không
vướng giới hạn độ dài dòng lệnh trên Windows và giữ nguyên xuống dòng.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

from . import config

TAIL = "Làm đúng yêu cầu ở trên. Chỉ trả lời nội dung được yêu cầu."


def cli_path() -> str:
    """Lệnh gemini: Cài đặt > biến môi trường GEMINI_BIN > "gemini".

    Trên Windows, npm cài lệnh dạng gemini.cmd; subprocess không tự tìm đuôi
    .cmd nên phải tra đường dẫn đầy đủ bằng shutil.which."""
    s = (config.load_settings().get("gemini_bin") or "").strip()
    name = s or os.environ.get("GEMINI_BIN", "gemini") or "gemini"
    return shutil.which(name) or name


def _workdir():
    # chạy trong thư mục riêng, để Gemini CLI không đọc mã nguồn của tool
    d = config.DATA / "tmp" / "gemini"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def run(prompt: str, *, timeout: int = 300) -> str:
    """Chạy Gemini CLI, trả về phần chữ của câu trả lời."""
    cmd = [cli_path(), "-p", TAIL, "--output-format", "json"]
    model = (config.load_settings().get("gemini_model") or "").strip()
    if model:
        cmd += ["-m", model]
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, cwd=_workdir(),
        )
    except FileNotFoundError:
        raise RuntimeError(
            "Không tìm thấy lệnh 'gemini'. Cài Gemini CLI: "
            "npm install -g @google/gemini-cli rồi chạy 'gemini' một lần để đăng nhập."
        ) from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Gemini CLI chạy quá {timeout}s và bị dừng.") from None

    out = (proc.stdout or "").strip()
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        err = data.get("error")
        if err:
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(f"Gemini CLI lỗi: {str(msg)[:500]}")
        text = data.get("response")
        if isinstance(text, str) and text.strip():
            return text.strip()
    if proc.returncode != 0 or not out:
        err = (proc.stderr or out or "").strip()
        raise RuntimeError(f"Gemini CLI lỗi (mã {proc.returncode}): {err[:500]}")
    return out


def version() -> tuple[bool, str]:
    """(có chạy được không, phiên bản hoặc lỗi) — dùng cho nút Kiểm tra máy."""
    try:
        proc = subprocess.run([cli_path(), "--version"], capture_output=True,
                              text=True, timeout=20)
    except FileNotFoundError:
        return False, "Không tìm thấy lệnh 'gemini'. Cài: npm install -g @google/gemini-cli"
    except Exception as e:  # noqa: BLE001
        return False, f"Không kiểm tra được: {e}"
    if proc.returncode == 0:
        return True, (proc.stdout or "").strip()[:80]
    return False, "Lệnh chạy nhưng không trả về phiên bản."
