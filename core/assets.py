# -*- coding: utf-8 -*-
"""Quản lý tài sản: nhân vật, bối cảnh, giọng mẫu.

Quy ước tên file chị tải lên:
  * nhân vật 1 ảnh      : 지은.png
  * nhân vật bộ ảnh     : 지은_shocked_mo.png / 지은_shocked_dong.png
  * bối cảnh            : tên file tuỳ ý
  * giọng mẫu           : 지은.wav  (5–15 giây)
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path

from PIL import Image

from . import config
from .comedy_lib import VALID_EXPRESSIONS

CHAR_DIR = config.LIBRARY / "characters"
BG_DIR = config.LIBRARY / "backgrounds"
VOICE_DIR = config.LIBRARY / "voices"
for _d in (CHAR_DIR, BG_DIR, VOICE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}

# 지은_shocked_mo.png  ->  (지은, shocked, mo)
SET_RE = re.compile(r"^(?P<name>.+?)_(?P<expr>[a-zA-Z]+)_(?P<mouth>mo|dong|open|closed)$")


def _index_path(kind: str) -> Path:
    return config.LIBRARY / f"{kind}.json"


def _load_index(kind: str) -> dict:
    p = _index_path(kind)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_index(kind: str, data: dict) -> None:
    _index_path(kind).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ------------------------------------------------------------------ nhân vật

def parse_character_files(paths: list[Path]) -> dict:
    """Đọc danh sách file ảnh, suy ra nhân vật + biểu cảm.

    Trả về {name: {"mode": "single"|"set", "images": {...}, "warnings": [...]}}
    """
    chars: dict[str, dict] = {}
    warnings: list[str] = []

    for p in paths:
        if p.suffix.lower() not in IMAGE_EXT:
            warnings.append(f"Bỏ qua '{p.name}' — không phải ảnh.")
            continue
        stem = p.stem
        m = SET_RE.match(stem)
        if m:
            name = m.group("name")
            expr = m.group("expr").lower()
            mouth = m.group("mouth").lower()
            mouth = "mo" if mouth in ("mo", "open") else "dong"
            if expr not in VALID_EXPRESSIONS:
                warnings.append(
                    f"'{p.name}': biểu cảm '{expr}' không nằm trong danh sách hỗ trợ."
                )
            c = chars.setdefault(name, {"mode": "set", "images": {}, "single": None})
            c["mode"] = "set"
            c["images"].setdefault(expr, {})[mouth] = str(p)
        else:
            name = stem
            c = chars.setdefault(name, {"mode": "single", "images": {}, "single": None})
            if c["single"]:
                warnings.append(f"'{p.name}': nhân vật '{name}' đã có ảnh, bỏ qua file này.")
            else:
                c["single"] = str(p)

    # nhân vật có cả bộ ảnh thì ưu tiên bộ
    for name, c in chars.items():
        if c["images"]:
            c["mode"] = "set"
            missing = []
            for expr, mouths in c["images"].items():
                if "mo" not in mouths or "dong" not in mouths:
                    missing.append(expr)
            if missing:
                warnings.append(
                    f"'{name}': biểu cảm {', '.join(missing)} thiếu ảnh miệng mở hoặc ngậm."
                )
        elif c["single"]:
            c["mode"] = "single"

    return {"characters": chars, "warnings": warnings}


def extract_zip(zip_path: Path, dest: Path) -> list[Path]:
    """Giải nén bộ ảnh nhân vật."""
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if not name or Path(name).suffix.lower() not in IMAGE_EXT:
                continue
            target = dest / name
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            out.append(target)
    return out


def remove_background(src: Path, dst: Path) -> bool:
    """Tách nền ảnh nhân vật nếu cần (dùng rembg nếu có)."""
    try:
        from rembg import remove  # type: ignore
        data = src.read_bytes()
        dst.write_bytes(remove(data))
        return True
    except Exception:
        # không có rembg: nếu ảnh đã có alpha thì dùng luôn
        try:
            im = Image.open(src)
            if im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema()[0] < 250:
                im.save(dst)
                return True
            # ảnh nền trắng: làm trong suốt vùng trắng ở biên
            im = im.convert("RGBA")
            im.save(dst)
            return False
        except Exception:
            return False


def save_character(name: str, side: str, files: list[Path],
                   *, to_library: bool = True, mouth_pos: tuple[int, int] | None = None) -> dict:
    """Lưu nhân vật vào thư viện. Trả về bản ghi."""
    parsed = parse_character_files(files)
    chars = parsed["characters"]
    if name not in chars and len(chars) == 1:
        # tên file khác tên chị gõ: dùng file đã có
        only = next(iter(chars.values()))
        chars = {name: only}

    rec = chars.get(name)
    if not rec:
        raise ValueError(f"Không thấy ảnh nào cho nhân vật '{name}'.")

    dest = CHAR_DIR / config_slug(name)
    dest.mkdir(parents=True, exist_ok=True)

    out = {"name": name, "side": side or "center", "mode": rec["mode"],
           "expressions": [], "image": None, "images": {}, "mouth_pos": None}

    if rec["mode"] == "single" and rec["single"]:
        target = dest / f"{config_slug(name)}.png"
        src = Path(rec["single"])
        im = Image.open(src).convert("RGBA")
        im.save(target)
        out["image"] = str(target)
        # Lưu toạ độ miệng nếu có
        if mouth_pos:
            out["mouth_pos"] = list(mouth_pos)
    else:
        for expr, mouths in rec["images"].items():
            out["images"].setdefault(expr, {})
            for mouth, p in mouths.items():
                target = dest / f"{config_slug(name)}_{expr}_{mouth}.png"
                Image.open(p).convert("RGBA").save(target)
                out["images"][expr][mouth] = str(target)
            out["expressions"].append(expr)
        # ảnh đại diện
        first = next(iter(out["images"].values()))
        out["image"] = first.get("dong") or first.get("mo")

    if to_library:
        idx = _load_index("characters")
        idx[name] = out
        _save_index("characters", idx)
    return out


def config_slug(name: str) -> str:
    """Tên thư mục an toàn, giữ chữ Hàn."""
    safe = re.sub(r'[<>:"/\\|?*]', "_", name).strip()
    return safe or "char"


def list_characters() -> list[dict]:
    return list(_load_index("characters").values())


def list_backgrounds() -> list[dict]:
    return list(_load_index("backgrounds").values())


def list_voices() -> list[dict]:
    return list(_load_index("voices").values())


# ------------------------------------------------------------------ bối cảnh

def save_background(file_path: Path, name: str = "") -> dict:
    bid = uuid.uuid4().hex[:10]
    target = BG_DIR / f"{bid}.png"
    im = Image.open(file_path).convert("RGB")
    im.save(target)
    rec = {"id": bid, "name": name or file_path.stem, "image": str(target)}
    idx = _load_index("backgrounds")
    idx[bid] = rec
    _save_index("backgrounds", idx)
    return rec


# -------------------------------------------------------------------- giọng

def save_voice(name: str, language: str, file_path: Path,
               text: str = "") -> dict:
    """Lưu mẫu giọng. text rỗng -> Whisper tự nghe."""
    import soundfile as sf

    dest = VOICE_DIR / config_slug(name)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"{language}.wav"

    data, sr = sf.read(str(file_path), dtype="float32", always_2d=False)
    if getattr(data, "ndim", 1) > 1:
        data = data.mean(axis=1)
    sf.write(str(target), data, sr)
    duration = len(data) / float(sr) if sr else 0.0

    if not text:
        try:
            from . import voice as voice_mod
            text = voice_mod.transcribe_ref(target)
        except Exception as e:  # noqa: BLE001
            text = ""

    idx = _load_index("voices")
    rec = idx.get(name) or {"name": name, "languages": {}}
    rec["languages"][language] = {
        "file": str(target), "duration": round(duration, 2), "text": text,
    }
    idx[name] = rec
    _save_index("voices", idx)
    return rec


def voice_path(name: str, language: str) -> Path | None:
    idx = _load_index("voices")
    rec = idx.get(name)
    if not rec:
        return None
    info = rec.get("languages", {}).get(language)
    if not info:
        return None
    p = Path(info["file"])
    return p if p.exists() else None


def voice_text(name: str, language: str) -> str:
    idx = _load_index("voices")
    rec = idx.get(name) or {}
    return rec.get("languages", {}).get(language, {}).get("text", "")


def find_image(image_id: str) -> Path | None:
    """Tìm ảnh theo id/đường dẫn tương đối (dùng cho /api/library/image/<id>)."""
    for base in (CHAR_DIR, BG_DIR, config.PREVIEWS):
        cand = base / image_id
        if cand.exists():
            return cand
        for p in base.rglob(image_id):
            return p
    # id là tên file bối cảnh
    for p in BG_DIR.glob(f"{image_id}*"):
        return p
    return None


# ------------------------------------------------------- đổi tên / xoá

def _rmtree(p: Path) -> None:
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists():
        try:
            p.unlink()
        except OSError:
            pass


def rename_character(old: str, new: str) -> dict:
    """Đổi tên nhân vật trong thư viện (kéo theo thư mục ảnh)."""
    idx = _load_index("characters")
    if old not in idx:
        raise ValueError(f"Không có nhân vật '{old}' trong thư viện.")
    new = (new or "").strip()
    if not new:
        raise ValueError("Tên mới không được để trống.")
    if new in idx and new != old:
        raise ValueError(f"Đã có nhân vật '{new}' trong thư viện.")
    rec = dict(idx.pop(old))
    rec["name"] = new
    old_dir = CHAR_DIR / config_slug(old)
    new_dir = CHAR_DIR / config_slug(new)
    if old_dir.exists() and old_dir != new_dir:
        new_dir.parent.mkdir(parents=True, exist_ok=True)
        old_dir.rename(new_dir)
        for k, v in list(rec.get("images", {}).items()):
            rec["images"][k] = {
                mk: str(Path(p).parent / new_dir.name / Path(p).name)
                for mk, p in v.items()
            }
        if rec.get("image"):
            rec["image"] = str(Path(rec["image"]).parent / new_dir.name
                               / Path(rec["image"]).name)
    idx[new] = rec
    _save_index("characters", idx)
    return rec


def delete_character(name: str) -> bool:
    idx = _load_index("characters")
    if name not in idx:
        return False
    rec = idx.pop(name)
    _save_index("characters", idx)
    _rmtree(CHAR_DIR / config_slug(name))
    for p in (rec.get("image"),):
        if p:
            _rmtree(Path(p))
    for v in (rec.get("images") or {}).values():
        for p in v.values():
            _rmtree(Path(p))
    return True


def rename_background(bid: str, new: str) -> dict:
    """Đổi tên hiển thị của bối cảnh (file ảnh giữ nguyên)."""
    idx = _load_index("backgrounds")
    if bid not in idx:
        raise ValueError("Không có bối cảnh này trong thư viện.")
    new = (new or "").strip()
    if not new:
        raise ValueError("Tên mới không được để trống.")
    rec = dict(idx[bid])
    rec["name"] = new
    idx[bid] = rec
    _save_index("backgrounds", idx)
    return rec


def delete_background(bid: str) -> bool:
    idx = _load_index("backgrounds")
    if bid not in idx:
        return False
    rec = idx.pop(bid)
    _save_index("backgrounds", idx)
    if rec.get("image"):
        _rmtree(Path(rec["image"]))
    return True


def rename_voice(old: str, new: str) -> dict:
    idx = _load_index("voices")
    if old not in idx:
        raise ValueError(f"Không có giọng mẫu '{old}' trong thư viện.")
    new = (new or "").strip()
    if not new:
        raise ValueError("Tên mới không được để trống.")
    if new in idx and new != old:
        raise ValueError(f"Đã có giọng mẫu '{new}' trong thư viện.")
    rec = dict(idx.pop(old))
    rec["name"] = new
    old_dir = VOICE_DIR / config_slug(old)
    new_dir = VOICE_DIR / config_slug(new)
    if old_dir.exists() and old_dir != new_dir:
        old_dir.rename(new_dir)
        for lang, info in list((rec.get("languages") or {}).items()):
            if info.get("file"):
                info["file"] = str(new_dir / Path(info["file"]).name)
    idx[new] = rec
    _save_index("voices", idx)
    return rec


def delete_voice(name: str) -> bool:
    idx = _load_index("voices")
    if name not in idx:
        return False
    rec = idx.pop(name)
    _save_index("voices", idx)
    _rmtree(VOICE_DIR / config_slug(name))
    for info in (rec.get("languages") or {}).values():
        if info.get("file"):
            _rmtree(Path(info["file"]))
    return True


# ---------------------------------------------------------------- tiếng động

def list_sfx() -> list[dict]:
    """Liệt kê các file tiếng động trong data/sfx."""
    out = []
    if not config.SFX_DIR.exists():
        return out
    for p in sorted(config.SFX_DIR.glob("*.wav")):
        out.append({"name": p.stem, "file": str(p),
                    "size": p.stat().st_size})
    return out


def rename_sfx(old: str, new: str) -> dict:
    old = (old or "").strip()
    new = (new or "").strip()
    if not new:
        raise ValueError("Tên mới không được để trống.")
    src = config.SFX_DIR / f"{old}.wav"
    if not src.exists():
        raise ValueError(f"Không có tiếng động '{old}'.")
    if (config.SFX_DIR / f"{new}.wav").exists():
        raise ValueError(f"Đã có tiếng động '{new}'.")
    src.rename(config.SFX_DIR / f"{new}.wav")
    return {"name": new, "file": str(config.SFX_DIR / f"{new}.wav")}


def delete_sfx(name: str) -> bool:
    p = config.SFX_DIR / f"{(name or '').strip()}.wav"
    if not p.exists():
        return False
    p.unlink()
    return True

