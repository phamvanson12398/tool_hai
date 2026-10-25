# -*- coding: utf-8 -*-
"""Bối cảnh 3D cho Truyện webtoon: mỗi địa điểm một ảnh nền 3D đúng bối cảnh truyện.

Mỗi địa điểm có "look" — AI tả cụ thể bằng tiếng Anh (vd "a small public restroom inside a
Seoul subway station, white tiles, stall doors, flickering fluorescent light"); chị sửa được.
Ảnh nền lấy từ một trong hai nguồn:
- tool vẽ trên máy bằng Stable Diffusion XL (core/bg3d, cần card NVIDIA, cài cai_3d.bat);
- chị tự vẽ bằng Gemini / ChatGPT theo câu lệnh tool đưa rồi tải lên.
Mỗi địa điểm vẽ MỘT lần cho ban ngày, MỘT lần cho ban đêm, dùng lại cho mọi cảnh ở đó nên
căn phòng giống nhau suốt truyện. Thiếu ảnh đêm thì lấy ảnh ngày tối đi; thiếu cả hai thì
dùng bối cảnh vẽ tay của tool như trước.
"""
from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np
from PIL import Image

DIR = "webtoon_bg"
STYLE = ("3D animated movie background, stylized 3D render like a modern animated film, "
         "soft global illumination, cinematic lighting, gentle depth of field, highly detailed, "
         "realistic modern South Korea")
EMPTY = "wide shot at eye level, empty scene with open space in the middle, no people, no text, no watermark"
LIGHT = {"ngay": "daytime, soft natural light",
         "dem": "at night, dark blue ambient light, warm practical lights glowing (lamps, screens, street lights)"}


KIND_EN = {"phong_khach": "a modern apartment living room", "bep": "a modern apartment kitchen",
           "phong_ngu": "a modern bedroom", "van_phong": "a modern open-plan office",
           "lop_hoc": "a high school classroom", "quan_cafe": "a cozy cafe", "cua_hang": "a convenience store",
           "duong_pho": "a city street with shops", "cong_vien": "a city park", "bai_bien": "a beach",
           "trong": "an empty studio stage", "nha_tranh": "inside a thatched cottage",
           "nha_ngoi": "inside an old traditional house", "san_que": "a countryside house yard",
           "duong_lang": "a village road", "canh_dong": "rice fields"}


def look_of(place: dict) -> str:
    """Tả bối cảnh để vẽ: AI / chị tả ("look"); thiếu thì dựa vào loại bối cảnh + tên."""
    lk = (place.get("look") or "").strip()
    if lk:
        return lk
    base = KIND_EN.get(place.get("kind"), "a room")
    return f"{base} in Seoul, South Korea ({place.get('name')})" if place.get("name") else f"{base} in Seoul, South Korea"


def prompt(place: dict, time: str, for_chat: bool = False) -> str:
    """Câu lệnh vẽ nền. for_chat: bản cho Gemini / ChatGPT (dặn thêm khổ ngang, không người)."""
    p = ", ".join([STYLE, look_of(place), LIGHT.get(time, LIGHT["ngay"]), EMPTY])
    if for_chat:
        p = ("Create a background image for an animated video. " + p +
             ". Landscape 16:9 image, no characters, no people, no text.")
    return p


def path_for(pdir: Path, place_id: str, time: str) -> Path:
    return Path(pdir) / DIR / f"{place_id}_{'dem' if time == 'dem' else 'ngay'}.png"


def shot_time(st: dict, s: dict) -> str:
    places = {p["id"]: p for p in st.get("places") or []}
    t = s.get("time") or (places.get(s.get("place")) or {}).get("time") or "ngay"
    return "dem" if t == "dem" else "ngay"


def needed(st: dict) -> list[tuple[dict, str]]:
    """Các (địa điểm, ngày / đêm) mà cảnh quay dùng tới, theo thứ tự xuất hiện."""
    places = {p["id"]: p for p in st.get("places") or []}
    seen, out = set(), []
    for s in st.get("shots") or []:
        if s.get("type") == "black":
            continue
        p = places.get(s.get("place"))
        if not p:
            continue
        k = (p["id"], shot_time(st, s))
        if k not in seen:
            seen.add(k)
            out.append((p, k[1]))
    for p in st.get("places") or []:                 # địa điểm chưa có cảnh nào: vẫn liệt kê
        k = (p["id"], "dem" if p.get("time") == "dem" else "ngay")
        if k not in seen:
            seen.add(k)
            out.append((p, k[1]))
    return out


def status(st: dict, pdir: Path | None) -> list[dict]:
    """Cho giao diện: từng (địa điểm, giờ) kèm đã có ảnh chưa + câu lệnh vẽ."""
    out = []
    for p, t in needed(st):
        have = bool(pdir) and path_for(pdir, p["id"], t).exists()
        out.append({"place": p["id"], "name": p.get("name") or p["id"], "time": t, "have": have,
                    "look": look_of(p), "prompt": prompt(p, t, for_chat=True)})
    return out


def save_upload(src: Path, dst: Path, size=(1920, 1080)) -> None:
    """Ảnh nền chị tải lên: phủ kín khung 16:9 rồi lưu."""
    from .bg3d import load_cover
    dst.parent.mkdir(parents=True, exist_ok=True)
    load_cover(src, size).save(dst)


def draw(st: dict, pdir: Path, only: list[str] | None = None, force: bool = False,
         progress=None) -> list[str]:
    """Tool vẽ nền 3D trên máy (SDXL) cho các địa điểm còn thiếu (only: chỉ các địa điểm này;
    force: vẽ lại, đổi hạt giống). Trả danh sách file đã vẽ."""
    from . import bg3d
    todo = [(p, t) for p, t in needed(st) if not only or p["id"] in only]
    made, reseeded = [], set()
    jobs, labels = [], []
    for p, t in todo:
        path = path_for(pdir, p["id"], t)
        if path.exists() and not force:
            continue
        if force and p["id"] not in reseeded:
            old = int(p.get("bg3d_seed") or zlib.crc32(p["id"].encode()) % 100000)
            p["bg3d_seed"] = (old * 7919 + 13) % 1000003
            reseeded.add(p["id"])
        seed = int(p.get("bg3d_seed") or zlib.crc32(p["id"].encode()) % 100000)
        jobs.append({"prompt": prompt(p, t), "size": [1344, 768], "seed": seed, "path": str(path)})
        labels.append(f"{p.get('name')}" + (" (đêm)" if t == "dem" else ""))
        made.append(path.name)
    labels = [f"vẽ nền 3D {i + 1}/{len(jobs)}: {lb}" for i, lb in enumerate(labels)]
    bg3d.run_jobs(jobs, progress, labels)                # chương trình con: không làm hỏng OmniVoice
    return made


def image_for(pdir: Path | None, place_id: str, time: str, size) -> Image.Image | None:
    """Ảnh nền 3D của địa điểm theo giờ; thiếu ảnh đêm thì lấy ảnh ngày tối đi."""
    if not pdir or not place_id:
        return None
    from .bg3d import load_cover
    p = path_for(pdir, place_id, time)
    darken = False
    if not p.exists() and time == "dem":
        p, darken = path_for(pdir, place_id, "ngay"), True
    if not p.exists():
        return None
    img = load_cover(p, tuple(size))
    if darken:
        a = np.asarray(img).astype(np.float32)
        a = a * np.array([0.42, 0.46, 0.62])         # tối, ám xanh như ban đêm
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return img
