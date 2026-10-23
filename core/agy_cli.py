# -*- coding: utf-8 -*-
"""Gọi Antigravity CLI (`agy`, headless) — dùng cho các việc phụ để đỡ tốn hạn
mức Claude.

Google đã ngừng cho Gemini CLI đăng nhập bằng tài khoản Google cá nhân
(IneligibleTierError) và chuyển sang Antigravity; `agy -p` chạy một câu lệnh
rồi thoát, câu trả lời ra stdout, lỗi và thông báo ra stderr.

Câu lệnh gửi thẳng trong --print: agy KHÔNG đọc stdin khi -p đã có chữ (gửi
qua stdin thì agy chỉ thấy câu dặn cuối và trả lời "chưa có yêu cầu nào").
Câu lệnh của các việc phụ ngắn (< 3.000 ký tự) nên không vướng giới hạn độ
dài dòng lệnh của Windows (32.767 ký tự).

Cài (PowerShell): irm https://antigravity.google/cli/install.ps1 | iex
rồi chạy `agy` một lần trong cửa sổ lệnh để đăng nhập Google.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from . import config

TAIL = ("Làm đúng yêu cầu ở trên và trả lời thẳng bằng chữ. KHÔNG dùng công cụ nào "
        "(không chạy lệnh, không đọc hay sửa file, không tìm web). Chỉ trả lời nội "
        "dung được yêu cầu.")
_DENIED_RE = re.compile(r"auto-denied|permission that headless|no output produced", re.I)

# Lỗi đăng nhập: lần sau trong phiên bỏ qua agy, dùng Claude luôn cho nhanh
_AUTH_ERROR: str | None = None
_AUTH_RE = re.compile(r"authenticat|not logged in|log ?in required|sign in|"
                      r"not eligible|ineligible|unauthori[sz]ed|credential", re.I)


def cli_path() -> str:
    """Lệnh agy: Cài đặt > biến môi trường AGY_BIN > "agy" (kể cả chỗ cài mặc
    định trên Windows: %LOCALAPPDATA%\\agy\\bin)."""
    s = (config.load_settings().get("agy_bin") or "").strip()
    name = s or os.environ.get("AGY_BIN", "agy") or "agy"
    found = shutil.which(name)
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local and not s:
        for exe in ("agy.exe", "agy.cmd"):
            p = Path(local) / "agy" / "bin" / exe
            if p.exists():
                return str(p)
    return name


def _workdir() -> str:
    # chạy trong thư mục riêng, để agy không đọc hay sửa mã nguồn của tool
    d = config.DATA / "tmp" / "agy"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def _short(text: str) -> str:
    """Bỏ phần dò lỗi (stack trace) dài dòng, giữ câu báo lỗi chính."""
    t = (text or "").strip()
    t = re.split(r"\s+at\s+\S+\s+\(|\n\s+at\s", t)[0]
    return t[:400]


def reset() -> None:
    """Gọi khi đổi cài đặt: thử lại agy dù trước đó lỗi đăng nhập."""
    global _AUTH_ERROR
    _AUTH_ERROR = None


def run(prompt: str, *, timeout: int = 300) -> str:
    """Chạy agy, trả về câu trả lời (chữ)."""
    global _AUTH_ERROR
    if _AUTH_ERROR:
        raise RuntimeError(_AUTH_ERROR)
    full = f"{prompt.strip()}\n\n---\n{TAIL}"
    if len(full) > 30000:
        raise RuntimeError("Câu lệnh quá dài để gửi cho Antigravity (giới hạn dòng lệnh Windows).")
    cmd = [cli_path(), f"--print={full}"]
    model = (config.load_settings().get("agy_model") or "").strip()
    if model:
        cmd.append(f"--model={model}")
    try:
        proc = subprocess.run(
            cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, cwd=_workdir(),
        )
    except FileNotFoundError:
        raise RuntimeError(
            "Không tìm thấy lệnh 'agy' (Antigravity CLI). Cài trong PowerShell: "
            "irm https://antigravity.google/cli/install.ps1 | iex — rồi mở lại "
            "cửa sổ lệnh, gõ agy một lần để đăng nhập Google."
        ) from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Antigravity chạy quá {timeout}s và bị dừng.") from None

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0 or not out:
        msg = _short(err or out) or f"mã lỗi {proc.returncode}"
        if _DENIED_RE.search(err + " " + out):
            raise RuntimeError(
                "Antigravity định dùng công cụ (chạy lệnh trên máy) nhưng khi chạy ngầm "
                "không được phép nên không trả lời. Việc này nên chọn Claude trong "
                "Cài đặt → Trợ lý AI cho từng việc.")
        if _AUTH_RE.search(err + " " + out):
            _AUTH_ERROR = ("Antigravity chưa đăng nhập được: " + msg.rstrip(".") + ". Mở cửa sổ lệnh, "
                           "gõ agy rồi đăng nhập Google một lần; xong bấm Lưu cài đặt "
                           "trong tool để thử lại.")
            raise RuntimeError(_AUTH_ERROR)
        raise RuntimeError(f"Antigravity lỗi (mã {proc.returncode}): {msg}")
    return out


def version() -> tuple[bool, str]:
    """(có chạy được không, phiên bản hoặc lỗi) — dùng cho nút Kiểm tra máy."""
    try:
        proc = subprocess.run([cli_path(), "--version"], capture_output=True,
                              text=True, timeout=20)
    except FileNotFoundError:
        return False, ("Không tìm thấy lệnh 'agy'. Cài trong PowerShell: "
                       "irm https://antigravity.google/cli/install.ps1 | iex")
    except Exception as e:  # noqa: BLE001
        return False, f"Không kiểm tra được: {e}"
    if proc.returncode == 0:
        return True, (proc.stdout or proc.stderr or "").strip()[:80]
    return False, "Lệnh chạy nhưng không trả về phiên bản."
