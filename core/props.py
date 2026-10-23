# -*- coding: utf-8 -*-
"""Đạo cụ cầm trên tay (điện thoại, nồi mì, cốc, bát cơm, sách, túi...).

Đạo cụ vẽ bằng Pillow, nét đậm cùng phong cách nhân vật. Mỗi đạo cụ có
điểm cầm (pivot) nằm trong lòng bàn tay; khi dựng, đạo cụ đặt ở bàn tay và
luôn đứng thẳng như cầm đồ thật (không xoay lộn ngược theo cẳng tay).

Kịch bản ghi trong ngoặc: `cam=dienthoai` (tay phải), `cam_trai=coc`,
`cam=bo` để bỏ đồ xuống. Đạo cụ hai tay (nồi, thùng) đặt giữa hai bàn tay.
Nhân vật giữ đạo cụ qua các câu sau cho tới khi đổi hoặc bỏ.
"""
from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw

INK = (24, 22, 28, 255)
OUT_W = 7

# tên -> (nhãn, cầm hai tay?, tư thế cầm mặc định)
PROPS: dict[str, tuple[str, bool, str]] = {
    "dienthoai": ("Điện thoại", False, "xem_dt"),
    "noi_mi": ("Nồi mì", True, "bung"),
    "coc": ("Cốc / ly", False, "cam_coc"),
    "bat_com": ("Bát cơm", False, "cam_coc"),
    "sach": ("Sách / vở", False, "cam_coc"),
    "tui": ("Túi xách", False, ""),
    "tat": ("Chiếc tất", False, "gio_do"),
    "banh": ("Bánh mì", False, "cam_coc"),
    "chai": ("Chai nước / soju", False, "cam_coc"),
    "hop_qua": ("Hộp quà", True, "bung"),
    "remote": ("Điều khiển TV", False, "cam_coc"),
    "chao": ("Chảo", False, "gio_do"),
}

ALIASES = {
    "phone": "dienthoai", "dt": "dienthoai", "dien_thoai": "dienthoai",
    "noi": "noi_mi", "ramen": "noi_mi", "mi": "noi_mi", "noimi": "noi_mi",
    "cup": "coc", "ly": "coc", "bat": "bat_com", "bowl": "bat_com",
    "book": "sach", "vo": "sach", "bag": "tui", "tuixach": "tui", "sock": "tat",
    "bread": "banh", "banhmi": "banh", "bottle": "chai", "soju": "chai",
    "gift": "hop_qua", "qua": "hop_qua", "hopqua": "hop_qua", "pan": "chao",
}

DROP_WORDS = ("bo", "khong", "none", "het", "tha")


def resolve(name: str) -> str | None:
    """Tên đạo cụ hợp lệ (chấp nhận tên khác/viết sai nhẹ), None nếu không có."""
    import difflib

    n = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    if n in PROPS:
        return n
    if n in ALIASES:
        return ALIASES[n]
    flat = n.replace("_", "")
    for k in PROPS:
        if k.replace("_", "") == flat:
            return k
    m = difflib.get_close_matches(flat, [k.replace("_", "") for k in PROPS], n=1, cutoff=0.75)
    if m:
        for k in PROPS:
            if k.replace("_", "") == m[0]:
                return k
    return None


def two_handed(name: str) -> bool:
    return bool(PROPS.get(name, ("", False, ""))[1])


def hold_pose(name: str) -> str:
    return PROPS.get(name, ("", False, ""))[2]


def catalog_text() -> str:
    return ", ".join(f"{k} ({v[0]})" for k, v in PROPS.items())


# ------------------------------------------------------------------ vẽ

def _with_outline(img: Image.Image) -> Image.Image:
    """Thêm viền đen quanh hình (nở rộng OUT_W px)."""
    import numpy as np
    import cv2

    a = np.array(img.getchannel("A"))
    k = OUT_W
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    m = cv2.GaussianBlur(cv2.dilate((a > 40).astype(np.uint8) * 255, kernel), (3, 3), 0)
    out = np.zeros((*m.shape, 4), dtype=np.uint8)
    out[..., :3] = INK[:3]
    out[..., 3] = m
    base = Image.fromarray(out, "RGBA")
    base.alpha_composite(img)
    return base


def _canvas(w: int, h: int):
    img = Image.new("RGBA", (w + 2 * OUT_W + 4, h + 2 * OUT_W + 4), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), OUT_W + 2


@lru_cache(maxsize=64)
def render(name: str) -> tuple[Image.Image, tuple[float, float]]:
    """(ảnh đạo cụ, điểm cầm) — toạ độ theo khung nhân vật 600x1000."""
    fn = _DRAW.get(name)
    if fn is None:
        raise KeyError(name)
    img, pivot = fn()
    return _with_outline(img), pivot


def _phone():
    img, d, o = _canvas(64, 112)
    d.rounded_rectangle([o, o, o + 64, o + 112], radius=12, fill=(190, 194, 204, 255))
    d.rounded_rectangle([o + 6, o + 10, o + 58, o + 96], radius=6, fill=(120, 200, 240, 255))
    d.line([o + 12, o + 18, o + 30, o + 36], fill=(220, 244, 255, 255), width=5)
    d.ellipse([o + 27, o + 100, o + 37, o + 108], fill=(120, 124, 134, 255))
    return img, (o + 32, o + 80)


def _pot():
    img, d, o = _canvas(250, 130)
    rim = (150, 104, 60, 255)
    d.rounded_rectangle([o + 20, o + 30, o + 230, o + 130], radius=26, fill=(176, 122, 70, 255))
    for x in (o, o + 222):                                    # quai nồi
        d.rounded_rectangle([x, o + 44, x + 28, o + 66], radius=10, fill=rim)
    d.ellipse([o + 16, o + 10, o + 234, o + 56], fill=rim)
    d.ellipse([o + 30, o + 16, o + 220, o + 50], fill=(232, 96, 50, 255))   # nước mì
    for i in range(9):                                        # sợi mì vàng
        x = o + 46 + i * 19
        d.arc([x - 16, o + 18, x + 16, o + 46], 200 + (i % 3) * 30, 360 + (i % 2) * 40,
              fill=(250, 214, 90, 255), width=5)
    return img, (o + 125, o + 80)


def _cup():
    img, d, o = _canvas(62, 78)
    d.polygon([(o, o + 4), (o + 62, o + 4), (o + 54, o + 78), (o + 8, o + 78)], fill=(250, 250, 250, 255))
    d.rectangle([o + 4, o + 22, o + 58, o + 40], fill=(214, 84, 76, 255))
    d.ellipse([o, o, o + 62, o + 12], fill=(120, 80, 50, 255))
    return img, (o + 31, o + 50)


def _bowl():
    img, d, o = _canvas(110, 70)
    d.ellipse([o + 6, o, o + 104, o + 34], fill=(250, 250, 250, 255))       # cơm
    for i in range(6):
        d.ellipse([o + 16 + i * 14, o + 4 + (i % 2) * 6, o + 26 + i * 14, o + 14 + (i % 2) * 6],
                  fill=(236, 236, 230, 255))
    d.chord([o, o + 10, o + 110, o + 70], 0, 180, fill=(90, 130, 200, 255))
    return img, (o + 55, o + 46)


def _book():
    img, d, o = _canvas(110, 84)
    d.rounded_rectangle([o, o, o + 110, o + 84], radius=6, fill=(214, 84, 76, 255))
    d.rectangle([o + 52, o, o + 58, o + 84], fill=(160, 50, 50, 255))
    d.rectangle([o + 8, o + 6, o + 48, o + 78], fill=(250, 246, 230, 255))
    for k in range(5):
        d.line([o + 12, o + 18 + k * 12, o + 44, o + 18 + k * 12], fill=(170, 170, 170, 255), width=3)
    return img, (o + 55, o + 60)


def _bag():
    img, d, o = _canvas(96, 140)
    d.arc([o + 18, o, o + 78, o + 70], 180, 360, fill=(120, 70, 50, 255), width=9)
    d.rounded_rectangle([o, o + 34, o + 96, o + 140], radius=18, fill=(226, 134, 168, 255))
    d.rectangle([o + 38, o + 60, o + 58, o + 76], fill=(238, 198, 86, 255))
    return img, (o + 48, o + 8)


def _sock():
    img, d, o = _canvas(70, 120)
    d.rounded_rectangle([o + 10, o, o + 50, o + 90], radius=16, fill=(240, 240, 236, 255))
    d.rounded_rectangle([o + 10, o + 70, o + 70, o + 112], radius=20, fill=(240, 240, 236, 255))
    d.rectangle([o + 10, o + 8, o + 50, o + 20], fill=(84, 124, 200, 255))
    for k in range(3):                                         # vết bẩn
        d.ellipse([o + 20 + k * 14, o + 84 + (k % 2) * 8, o + 30 + k * 14, o + 94 + (k % 2) * 8],
                  fill=(140, 150, 90, 200))
    return img, (o + 30, o + 10)


def _bread():
    img, d, o = _canvas(130, 56)
    d.rounded_rectangle([o, o, o + 130, o + 56], radius=28, fill=(222, 164, 92, 255))
    for k in range(4):
        x = o + 26 + k * 26
        d.line([x - 8, o + 14, x + 8, o + 30], fill=(176, 116, 60, 255), width=5)
    return img, (o + 30, o + 30)


def _bottle():
    img, d, o = _canvas(52, 140)
    d.rounded_rectangle([o + 16, o, o + 36, o + 36], radius=6, fill=(110, 190, 120, 230))
    d.rounded_rectangle([o, o + 30, o + 52, o + 140], radius=16, fill=(110, 190, 120, 230))
    d.rectangle([o + 4, o + 70, o + 48, o + 104], fill=(250, 250, 250, 255))
    d.rectangle([o + 14, o - 4, o + 38, o + 8], fill=(60, 120, 70, 255))
    return img, (o + 26, o + 96)


def _gift():
    img, d, o = _canvas(150, 120)
    d.rectangle([o, o + 24, o + 150, o + 120], fill=(236, 120, 150, 255))
    d.rectangle([o - 6, o + 14, o + 156, o + 38], fill=(246, 150, 176, 255))
    d.rectangle([o + 66, o + 14, o + 84, o + 120], fill=(250, 214, 90, 255))
    d.ellipse([o + 40, o, o + 74, o + 22], outline=(250, 214, 90, 255), width=9)
    d.ellipse([o + 76, o, o + 110, o + 22], outline=(250, 214, 90, 255), width=9)
    return img, (o + 75, o + 76)


def _remote():
    img, d, o = _canvas(40, 120)
    d.rounded_rectangle([o, o, o + 40, o + 120], radius=12, fill=(60, 60, 70, 255))
    d.ellipse([o + 12, o + 10, o + 28, o + 26], fill=(220, 60, 60, 255))
    for k in range(3):
        for j in range(2):
            d.ellipse([o + 6 + j * 16, o + 40 + k * 20, o + 18 + j * 16, o + 52 + k * 20],
                      fill=(180, 180, 190, 255))
    return img, (o + 20, o + 90)


def _pan():
    img, d, o = _canvas(170, 70)
    d.rounded_rectangle([o + 100, o + 26, o + 170, o + 42], radius=8, fill=(70, 50, 40, 255))
    d.ellipse([o, o, o + 110, o + 66], fill=(64, 64, 72, 255))
    d.ellipse([o + 12, o + 8, o + 98, o + 56], fill=(96, 96, 106, 255))
    d.ellipse([o + 36, o + 18, o + 70, o + 44], fill=(250, 220, 120, 255))   # trứng
    d.ellipse([o + 46, o + 24, o + 60, o + 38], fill=(250, 170, 40, 255))
    return img, (o + 150, o + 34)


_DRAW = {
    "dienthoai": _phone, "noi_mi": _pot, "coc": _cup, "bat_com": _bowl, "sach": _book,
    "tui": _bag, "tat": _sock, "banh": _bread, "chai": _bottle, "hop_qua": _gift,
    "remote": _remote, "chao": _pan,
}


def preview_sheet() -> Image.Image:
    """Ảnh xem tất cả đạo cụ (dùng khi kiểm tra)."""
    ims = [render(k)[0] for k in PROPS]
    w = sum(i.width for i in ims) + 20 * (len(ims) + 1)
    h = max(i.height for i in ims) + 40
    sheet = Image.new("RGBA", (w, h), (246, 240, 230, 255))
    x = 20
    for im in ims:
        sheet.alpha_composite(im, (x, 20))
        x += im.width + 20
    return sheet

