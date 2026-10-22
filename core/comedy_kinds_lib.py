# -*- coding: utf-8 -*-
"""Quản lý thư viện kiểu hài: nạp mặc định từ comedy_lib, cho phép user
tự thêm / sửa / xoá, lưu thành file JSON riêng cho từng ngôn ngữ
(data/library/comedy_kinds_ko.json, comedy_kinds_en.json).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config
from .comedy_lib import COMEDY_KINDS, MARKETS

_MAX_ID = 60


def _path(lang: str) -> Path:
    return config.LIBRARY / f"comedy_kinds_{lang}.json"


def _load_custom(lang: str) -> dict:
    p = _path(lang)
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {}


def _save_custom(lang: str, data: dict) -> None:
    _path(lang).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def list_kinds(lang: str) -> list[dict]:
    """Trả về danh sách {id, name, how, custom} cho một ngôn ngữ, sắp theo id."""
    base = COMEDY_KINDS.get(lang, {})
    out = []
    for kid, (nm, how) in base.items():
        out.append({"id": kid, "name": nm, "how": how, "custom": False})
    for kid, rec in _load_custom(lang).items():
        out.append({
            "id": kid,
            "name": str(rec.get("name", kid)),
            "how": str(rec.get("how", "")),
            "custom": True,
        })
    return out


def find_kind(lang: str, kind_id: str) -> dict | None:
    for k in list_kinds(lang):
        if k["id"] == kind_id:
            return k
    return None


def upsert_kind(lang: str, kind_id: str, name: str, how: str) -> dict:
    """Tạo mới hoặc ghi đè một kiểu hài. Chỉ thao tác trên bản custom."""
    kind_id = (kind_id or "").strip()[:_MAX_ID]
    name = (name or "").strip()[:80]
    if not kind_id or not name:
        raise ValueError("Thiếu id hoặc tên kiểu hài.")
    custom = _load_custom(lang)
    custom[kind_id] = {"name": name, "how": (how or "").strip()[:300]}
    _save_custom(lang, custom)
    return {"id": kind_id, "name": name, "how": (how or "").strip()[:300], "custom": True}


def delete_kind(lang: str, kind_id: str) -> bool:
    """Xoá một kiểu hài custom. Không cho xoá bản mặc định."""
    custom = _load_custom(lang)
    if kind_id not in custom:
        if kind_id in COMEDY_KINDS.get(lang, {}):
            raise ValueError("Đây là kiểu hài mặc định — không xoá được. Chỉ xoá kiểu do bạn tự thêm.")
        return False
    del custom[kind_id]
    _save_custom(lang, custom)
    return True
