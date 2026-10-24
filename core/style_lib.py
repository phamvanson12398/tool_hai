# -*- coding: utf-8 -*-
"""Thư viện kiểu nhân vật đã lưu (theo ảnh nhân vật mẫu).

Mỗi lần tải ảnh nhân vật mẫu, nét vẽ Claude rút ra (tỉ lệ đầu – thân – tay chân,
kiểu mắt, nét viền) và bộ ghép ngoại hình được lưu ở data/library/kieu_nhan_vat/,
tách khỏi thư mục truyện: xoá truyện không mất kiểu nhân vật, truyện khác chọn lại
được trong ô "Kiểu nhân vật"."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
import unicodedata
from pathlib import Path

from . import config

DIR = config.LIBRARY / "kieu_nhan_vat"
BUILTIN = config.LIBRARY / "kieu_co_san"      # kiểu có sẵn đi kèm tool (không xoá được)


def _slug(s: str) -> str:
    t = (s or "").replace("đ", "d").replace("Đ", "D")
    t = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "_", t).strip("_").lower()
    return t[:32] or "kieu"


def _hash(path: Path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()[:8]


def save(sample: dict, image: str | Path, name: str = "") -> str | None:
    """Lưu kiểu nhân vật (ảnh mẫu + nét vẽ + bộ ghép). Cùng ảnh thì không lưu trùng.
    Trả về id."""
    image = Path(image)
    if not image.exists() or not isinstance(sample, dict):
        return None
    h = _hash(image)
    for meta in DIR.glob("*/meta.json"):
        try:
            if json.loads(meta.read_text("utf-8")).get("hash") == h:
                return meta.parent.name
        except Exception:  # noqa: BLE001
            continue
    label = (name or sample.get("note") or "Kiểu nhân vật").strip()
    sid = f"{_slug(label)}_{h}"
    d = DIR / sid
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image, d / "sample.png")
    meta = {"name": label[:80], "note": sample.get("note", ""), "style": sample.get("style"),
            "kit": sample.get("kit"), "hash": h, "created": time.strftime("%Y-%m-%d %H:%M")}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return sid


def items() -> list[dict]:
    out = []
    for meta in sorted(BUILTIN.glob("*/meta.json")) + sorted(DIR.glob("*/meta.json")):
        try:
            m = json.loads(meta.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        out.append({"id": meta.parent.name, "name": m.get("name") or meta.parent.name,
                    "created": m.get("created", "")})
    return out


def get(sid: str) -> dict | None:
    """{note, style, kit, image, lib} để gán vào st["char_sample"]."""
    if not re.fullmatch(r"[a-z0-9_]+", sid or ""):
        return None
    base = next((b for b in (DIR, BUILTIN) if (b / sid / "meta.json").exists()), None)
    if base is None:
        return None
    m = json.loads((base / sid / "meta.json").read_text("utf-8"))
    return {"note": m.get("note", ""), "style": m.get("style"), "kit": m.get("kit"),
            "image": str(base / sid / "sample.png"), "lib": sid}


def backup(st: dict, title: str = "") -> bool:
    """Truyện có ảnh mẫu mà chưa lưu vào thư viện thì lưu luôn. True nếu st đổi."""
    smp = st.get("char_sample") or {}
    if not smp.get("image") or smp.get("lib") or not Path(smp["image"]).exists():
        return False
    sid = save(smp, smp["image"], smp.get("note") or title)
    if not sid:
        return False
    smp["lib"] = sid
    st["char_sample"] = smp
    return True


def is_builtin(sid: str) -> bool:
    return (BUILTIN / sid / "meta.json").exists() and not (DIR / sid / "meta.json").exists()


def rename(sid: str, name: str) -> bool:
    """Đổi tên kiểu chị đã tạo (kiểu có sẵn của tool thì không đổi)."""
    meta = DIR / sid / "meta.json"
    if not re.fullmatch(r"[a-z0-9_]+", sid or "") or not meta.exists() or not name.strip():
        return False
    m = json.loads(meta.read_text("utf-8"))
    m["name"] = name.strip()[:80]
    meta.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def remove(sid: str) -> bool:
    """Xoá kiểu chị đã tạo: chuyển vào data/thung_rac/kieu_nhan_vat (lấy lại được bằng tay)."""
    d = DIR / sid
    if not re.fullmatch(r"[a-z0-9_]+", sid or "") or not (d / "meta.json").exists():
        return False
    trash = config.DATA / "thung_rac" / "kieu_nhan_vat"
    trash.mkdir(parents=True, exist_ok=True)
    dest = trash / sid
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    shutil.move(str(d), str(dest))
    return True


def update(sid: str, sample: dict) -> bool:
    """Ghi lại nét vẽ / bộ ghép mới cho kiểu chị đã tạo (thiết kế lại theo ảnh mẫu)."""
    meta = DIR / sid / "meta.json"
    if not re.fullmatch(r"[a-z0-9_]+", sid or "") or not meta.exists():
        return False
    m = json.loads(meta.read_text("utf-8"))
    m.update({"style": sample.get("style"), "kit": sample.get("kit"),
              "note": sample.get("note") or m.get("note", "")})
    meta.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    return True
