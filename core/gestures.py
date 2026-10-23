# -*- coding: utf-8 -*-
"""Thư viện cử chỉ và hiệu ứng cả người cho nhân vật có khung xương (Bước B).

Cử chỉ lưu dạng JSON: mỗi cử chỉ là danh sách keyframe, mỗi keyframe là
{goc: {ten_xuong: goc_radian}, kieu: "mot_lan"|"giu"|"lap", thoi_luong: giay}.

Hiệu ứng cả người (nhun, nhay, rung, nghieng, quay, nga) tách riêng, áp
lên toàn thân cho mọi nhân vật.

Quy ước góc (thư viện bản 2): góc ghi theo tay/chân PHẢI; tay/chân TRÁI tự
lật dấu để cử chỉ đối xứng (góc âm = giơ ra ngoài / lên trên, góc dương =
khép vào trong người). Ngoài góc xương còn hai khoá dịch cả người:
"dich_x" (phần chiều rộng khung, âm = sang trái) và "dich_y" (phần chiều cao
khung, dương = lên trên).
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

# Kiểu chạy của cử chỉ
KIEU_MOT_LAN = "mot_lan"   # chạy một lần rồi về tư thế ban đầu
KIEU_GIU = "giu"           # giữ nguyên tư thế cuối
KIEU_LAP = "lap"           # lặp lại liên tục

# Phiên bản thư viện: tăng khi đổi cử chỉ mặc định để file cũ được tạo lại
LIBRARY_VERSION = 8

# Khoá dịch cả người (không phải xương)
OFFSET_KEYS = ("dich_x", "dich_y")

# Thời gian trở về tư thế đứng sau khi cử chỉ kết thúc (giây)
RETURN_TIME = 0.3

# Thư mục lưu thư viện cử chỉ
GESTURE_DIR = Path(__file__).resolve().parent.parent / "data" / "gestures"


# ------------------------------------------------------------------ cấu trúc

@dataclass
class Keyframe:
    """Một khoảnh thời gian của cử chỉ: góc của từng xương."""
    goc: dict[str, float] = field(default_factory=dict)
    thoi_luong: float = 0.3      # giây, thời lượng của khoảnh này
    kieu: str = KIEU_MOT_LAN

    def to_dict(self) -> dict:
        return {"goc": self.goc, "thoi_luong": self.thoi_luong, "kieu": self.kieu}

    @staticmethod
    def from_dict(d: dict) -> "Keyframe":
        return Keyframe(
            goc={k: float(v) for k, v in (d.get("goc") or {}).items()},
            thoi_luong=float(d.get("thoi_luong", 0.3)),
            kieu=d.get("kieu", KIEU_MOT_LAN),
        )


@dataclass
class Gesture:
    """Một cử chỉ: chuỗi keyframe + thông tin mô tả."""
    name: str
    label: str = ""                # tên tiếng Việt hiển thị
    mo_ta: str = ""                # mô tả cho Claude hiểu khi nào dùng
    keyframes: list[Keyframe] = field(default_factory=list)
    loop: bool = False             # cử chỉ lặp vô hạn (cho kiểu "lap")

    @property
    def duration(self) -> float:
        return sum(k.thoi_luong for k in self.keyframes)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "label": self.label, "mo_ta": self.mo_ta,
            "loop": self.loop,
            "keyframes": [k.to_dict() for k in self.keyframes],
        }

    @staticmethod
    def from_dict(d: dict) -> "Gesture":
        return Gesture(
            name=d.get("name", ""),
            label=d.get("label", ""),
            mo_ta=d.get("mo_ta", ""),
            keyframes=[Keyframe.from_dict(k) for k in d.get("keyframes", [])],
            loop=bool(d.get("loop", False)),
        )

    def sample(self, t: float) -> dict[str, float]:
        """Góc xương tại thời điểm t (giây) trong cử chỉ."""
        if not self.keyframes:
            return {}
        total = self.duration
        if total <= 0:
            return {}

        # Cử chỉ lặp: từ vòng thứ hai, khoảnh đầu nối tiếp từ khoảnh cuối
        # (không rơi về tư thế đứng rồi giơ lại)
        cycled = self.loop and t >= total
        if self.loop:
            t = t % total

        # Tìm khoảnh chứa t
        acc = 0.0
        for idx, k in enumerate(self.keyframes):
            end = acc + k.thoi_luong
            if t < end or idx == len(self.keyframes) - 1:
                if k.thoi_luong <= 0.02:
                    local = 1.0      # khoảnh gần 0 giây: đặt tư thế ngay (vd. đứng ngoài khung)
                else:
                    local = min(1.0, max(0.0, (t - acc) / k.thoi_luong))
                # nội suy mượt (smoothstep) cho chuyển động tự nhiên
                u = local * local * (3 - 2 * local)
                return self._lerp_between(idx, u, cycled)
            acc = end
        return {}

    def _lerp_between(self, idx: int, u: float, cycled: bool = False
                      ) -> dict[str, float]:
        """Nội suy từ tư thế trước tới tư thế của khoảnh idx."""
        k = self.keyframes[idx]
        if idx == 0 and not cycled:
            prev_goc: dict[str, float] = {}
        else:
            prev_goc = self.keyframes[idx - 1].goc   # idx 0 + cycled -> khoảnh cuối
        keys = set(k.goc) | set(prev_goc)
        return {kk: prev_goc.get(kk, 0.0) + (k.goc.get(kk, 0.0) - prev_goc.get(kk, 0.0)) * u
                for kk in keys}


# ------------------------------------------------------------------ thư viện

def _rad(deg: float) -> float:
    return math.radians(deg)


def _default_gestures() -> list[Gesture]:
    """17 cử chỉ theo đặc tả (góc ghi theo bên phải, bên trái tự đối xứng)."""

    def K(goc: dict[str, float], thoi_luong: float, kieu: str = KIEU_MOT_LAN) -> Keyframe:
        # góc nhập bằng độ cho dễ đọc; khoá dịch người giữ nguyên
        return Keyframe({k: (v if k in OFFSET_KEYS else _rad(v)) for k, v in goc.items()},
                        thoi_luong, kieu)

    def walk(x0: float, x1: float, steps: int, step_time: float,
             hold_end: bool) -> list[Keyframe]:
        """Đi ngang từ dich_x=x0 tới x1, chân bước so le, người nhấp nhô."""
        kfs = [K({"dich_x": x0}, 0.01)]
        for i in range(1, steps + 1):
            a = -14 if i % 2 else 8
            kfs.append(K({"dich_x": x0 + (x1 - x0) * i / steps,
                          "dich_y": 0.012 if i % 2 else 0.0,
                          "dui_left": a, "dui_right": -a,
                          "goi_left": -a * 0.6, "goi_right": a * 0.6,
                          "vai_left": a * 0.7, "vai_right": -a * 0.7}, step_time))
        kfs.append(K({"dich_x": x1}, 0.15, KIEU_GIU if hold_end else KIEU_MOT_LAN))
        return kfs

    g: list[Gesture] = []

    # 1. vaytay — giơ tay phải, cẳng tay đung đưa qua lại
    g.append(Gesture(
        name="vaytay", label="Vẫy tay", mo_ta="Vẫy tay chào bạn, tay giơ lên ngang vai.",
        keyframes=[
            K({"vai_right": -105, "khuyu_right": -55}, 0.25, KIEU_LAP),
            K({"vai_right": -105, "khuyu_right": -100}, 0.22, KIEU_LAP),
        ],
        loop=True,
    ))

    # 2. chitay — duỗi thẳng tay chỉ sang bên, giữ
    g.append(Gesture(
        name="chitay", label="Chỉ tay", mo_ta="Chỉ ngón tay về phía trước, như ra lệnh.",
        keyframes=[
            K({"vai_right": -88, "khuyu_right": -4}, 0.2),
            K({"vai_right": -84, "khuyu_right": -4, "co_tay_right": -10}, 0.6, KIEU_GIU),
        ],
    ))

    # 3. omdau — hai tay đưa lên ôm hai bên đầu, giữ
    g.append(Gesture(
        name="omdau", label="Ôm đầu", mo_ta="Ôm đầu bằng cả hai tay, vẻ hoang mang.",
        keyframes=[
            K({"vai_left": -95, "vai_right": -95,
               "khuyu_left": -125, "khuyu_right": -125}, 0.35),
            K({"vai_left": -98, "vai_right": -98,
               "khuyu_left": -128, "khuyu_right": -128, "dau": 3}, 0.6, KIEU_GIU),
        ],
    ))

    # 4. khoanhtay — hai cẳng tay khép ngang trước ngực, giữ
    g.append(Gesture(
        name="khoanhtay", label="Khoanh tay", mo_ta="Khoanh tay trước ngực, vẻ bình thản.",
        keyframes=[
            K({"vai_left": -22, "vai_right": -22,
               "khuyu_left": 128, "khuyu_right": 128}, 0.35),
            K({"vai_left": -22, "vai_right": -22,
               "khuyu_left": 128, "khuyu_right": 128}, 0.6, KIEU_GIU),
        ],
    ))

    # 5. giohaitay — giơ hai tay hình chữ V, giữ
    g.append(Gesture(
        name="giohaitay", label="Giơ hai tay", mo_ta="Giơ cả hai tay lên cao, vẻ vui mừng.",
        keyframes=[
            K({"vai_left": -150, "vai_right": -150,
               "khuyu_left": -10, "khuyu_right": -10}, 0.3),
            K({"vai_left": -156, "vai_right": -156,
               "khuyu_left": -14, "khuyu_right": -14, "dich_y": 0.01}, 0.5, KIEU_GIU),
        ],
    ))

    # 6. nhunvai — dang hai tay, ngửa cẳng tay, nhún một nhịp
    g.append(Gesture(
        name="nhunvai", label="Nhún vai", mo_ta="Nhún vai lên xuống, vẻ không biết.",
        keyframes=[
            K({"vai_left": -32, "vai_right": -32,
               "khuyu_left": -62, "khuyu_right": -62}, 0.22),
            K({"vai_left": -40, "vai_right": -40,
               "khuyu_left": -72, "khuyu_right": -72,
               "dau": 6, "dich_y": 0.008}, 0.16),
            K({"vai_left": -32, "vai_right": -32,
               "khuyu_left": -62, "khuyu_right": -62}, 0.5),
        ],
    ))

    # 7. voratay — hai tay khép vào giữa ngực rồi mở ra, lặp
    g.append(Gesture(
        name="voratay", label="Vỗ tay", mo_ta="Vỗ tay như đang vỗ nhau.",
        keyframes=[
            K({"vai_left": -30, "vai_right": -30,
               "khuyu_left": 135, "khuyu_right": 135}, 0.16, KIEU_LAP),
            K({"vai_left": -48, "vai_right": -48,
               "khuyu_left": 105, "khuyu_right": 105}, 0.16, KIEU_LAP),
        ],
        loop=True,
    ))

    # 8. gatdau — đầu cúi xuống rồi ngẩng lên hai nhịp
    g.append(Gesture(
        name="gatdau", label="Gật đầu", mo_ta="Gật đầu đồng ý.",
        keyframes=[
            K({"dau": 7}, 0.15),
            K({"dau": -2}, 0.15),
            K({"dau": 7}, 0.15),
            K({"dau": 0}, 0.18),
        ],
    ))

    # 9. lacdau — đầu nghiêng qua lại liên tục
    g.append(Gesture(
        name="lacdau", label="Lắc đầu", mo_ta="Lắc đầu từ chối.",
        keyframes=[
            K({"dau": -9}, 0.17, KIEU_LAP),
            K({"dau": 9}, 0.17, KIEU_LAP),
        ],
        loop=True,
    ))

    # 10. dibo — bước tại chỗ: chân so le, tay đánh ngược, người nhấp nhô
    g.append(Gesture(
        name="dibo", label="Đi bộ", mo_ta="Bước chân tại chỗ, như đang đi bộ.",
        keyframes=[
            K({"dui_left": -14, "dui_right": 8, "goi_left": 9, "goi_right": -5,
               "vai_left": 8, "vai_right": -10, "dich_y": 0.012}, 0.28, KIEU_LAP),
            K({"dui_left": 8, "dui_right": -14, "goi_left": -5, "goi_right": 9,
               "vai_left": -10, "vai_right": 8, "dich_y": 0.0}, 0.28, KIEU_LAP),
        ],
        loop=True,
    ))

    # 11-14. vào / ra khung hình: đi ngang thật sự
    g.append(Gesture(
        name="vao_trai", label="Vào từ trái", mo_ta="Bước vào khung hình từ bên trái.",
        keyframes=walk(-0.6, 0.0, 4, 0.2, False),
    ))
    g.append(Gesture(
        name="vao_phai", label="Vào từ phải", mo_ta="Bước vào khung hình từ bên phải.",
        keyframes=walk(0.6, 0.0, 4, 0.2, False),
    ))
    g.append(Gesture(
        name="ra_trai", label="Ra trái", mo_ta="Bước ra khỏi khung hình về bên trái.",
        keyframes=walk(0.0, -0.75, 4, 0.2, True)[1:],
    ))
    g.append(Gesture(
        name="ra_phai", label="Ra phải", mo_ta="Bước ra khỏi khung hình về bên phải.",
        keyframes=walk(0.0, 0.75, 4, 0.2, True)[1:],
    ))

    # 15. nhaylen — khuỵu gối, bật lên cao, tiếp đất
    g.append(Gesture(
        name="nhaylen", label="Nhảy lên", mo_ta="Nhảy lên một cái, vẻ hào hứng.",
        keyframes=[
            K({"dui_left": -10, "dui_right": -10, "goi_left": 20, "goi_right": 20,
               "dich_y": -0.012}, 0.16),
            K({"dui_left": 4, "dui_right": 4, "goi_left": -4, "goi_right": -4,
               "vai_left": -140, "vai_right": -140, "dich_y": 0.11}, 0.22),
            K({"dui_left": -8, "dui_right": -8, "goi_left": 16, "goi_right": 16,
               "vai_left": -40, "vai_right": -40, "dich_y": -0.01}, 0.2),
        ],
    ))

    # 16. ngangua — buông thõng tay, cúi đầu, người chùng xuống, giữ
    g.append(Gesture(
        name="ngangua", label="Ngang vai", mo_ta="Hạ vai xuống, vẻ chán nản.",
        keyframes=[
            K({"vai_left": 6, "vai_right": 6, "dau": 7, "dich_y": -0.008}, 0.35),
            K({"vai_left": 6, "vai_right": 6, "dau": 7, "dich_y": -0.008}, 0.5, KIEU_GIU),
        ],
    ))

    # 17. ve_tu_the — tay phải đưa ra diễn giải rồi về
    g.append(Gesture(
        name="ve_tu_the", label="Vẽ tư thế", mo_ta="Tự nhiên tạo tư thế tay, linh hoạt.",
        keyframes=[
            K({"vai_right": -55, "khuyu_right": -45, "co_tay_right": 15}, 0.3),
            K({"vai_right": -48, "khuyu_right": -75, "co_tay_right": -12}, 0.35),
            K({"vai_right": -55, "khuyu_right": -45}, 0.3),
        ],
    ))

    # ---------------- tư thế cầm đồ (tự dùng khi nhân vật cầm đạo cụ) -------------
    g.append(Gesture(
        name="xem_dt", label="Xem điện thoại", mo_ta="Cầm điện thoại trước ngực, cúi nhìn.",
        keyframes=[K({"vai_right": -8, "khuyu_right": 128, "dau": 4}, 0.3),
                   K({"vai_right": -8, "khuyu_right": 128, "dau": 4}, 0.4, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="cam_tai", label="Áp điện thoại lên tai", mo_ta="Nghe điện thoại, tay áp lên tai.",
        keyframes=[K({"vai_right": -38, "khuyu_right": -142, "dau": -5}, 0.3),
                   K({"vai_right": -38, "khuyu_right": -142, "dau": -5}, 0.4, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="bung", label="Bưng bằng hai tay", mo_ta="Hai tay bưng đồ trước bụng (nồi, hộp quà).",
        keyframes=[K({"vai_left": -6, "vai_right": -6, "khuyu_left": 72, "khuyu_right": 72}, 0.3),
                   K({"vai_left": -6, "vai_right": -6, "khuyu_left": 72, "khuyu_right": 72}, 0.4, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="cam_coc", label="Cầm đồ trước ngực", mo_ta="Cầm cốc, bát, sách trước ngực.",
        keyframes=[K({"vai_right": -14, "khuyu_right": 104}, 0.3),
                   K({"vai_right": -14, "khuyu_right": 104}, 0.4, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="gio_do", label="Giơ đồ lên", mo_ta="Giơ đồ vật lên cao cho người khác xem (vẻ ghê, tức).",
        keyframes=[K({"vai_right": -150, "khuyu_right": -8}, 0.3),
                   K({"vai_right": -154, "khuyu_right": -10}, 0.4, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="an", label="Ăn", mo_ta="Đưa đồ ăn lên miệng liên tục.",
        keyframes=[K({"vai_right": -18, "khuyu_right": 100, "dau": 0}, 0.22, KIEU_LAP),
                   K({"vai_right": -26, "khuyu_right": 150, "dau": 5}, 0.22, KIEU_LAP)],
        loop=True,
    ))

    # ---------------- tư thế đời thường (xoay cả người bằng xương thân) ----------
    g.append(Gesture(
        name="ngoi", label="Ngồi xổm", mo_ta="Ngồi xổm, hai tay đặt lên gối.",
        keyframes=[K({"dui_left": -38, "dui_right": -38, "goi_left": 82, "goi_right": 82,
                      "vai_left": -26, "vai_right": -26, "khuyu_left": 40, "khuyu_right": 40,
                      "dich_y": -0.085}, 0.35),
                   K({"dui_left": -38, "dui_right": -38, "goi_left": 82, "goi_right": 82,
                      "vai_left": -26, "vai_right": -26, "khuyu_left": 40, "khuyu_right": 40,
                      "dich_y": -0.085}, 0.4, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="om_goi", label="Ngồi bó gối", mo_ta="Ngồi bó gối, ôm chân (khóc, tủi thân).",
        keyframes=[K({"dui_left": -32, "dui_right": -32, "goi_left": 84, "goi_right": 84,
                      "vai_left": -16, "vai_right": -16, "khuyu_left": 118, "khuyu_right": 118,
                      "dau": 6, "dich_y": -0.1}, 0.4),
                   K({"dui_left": -32, "dui_right": -32, "goi_left": 84, "goi_right": 84,
                      "vai_left": -16, "vai_right": -16, "khuyu_left": 118, "khuyu_right": 118,
                      "dau": 3, "dich_y": -0.1}, 0.5, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="nam", label="Nằm dài", mo_ta="Nằm dài thư giãn, một tay gối đầu (nằm giường, sofa).",
        # tay TRÁI gối đầu, tay phải để tự do (cầm điện thoại khi có đạo cụ)
        keyframes=[K({"than": 90, "vai_left": -160, "khuyu_left": -70,
                      "dui_left": 26, "goi_left": -40, "dich_y": -0.12, "dich_x": -0.04}, 0.45),
                   K({"than": 90, "vai_left": -160, "khuyu_left": -70,
                      "dui_left": 26, "goi_left": -40, "dich_y": -0.12, "dich_x": -0.04}, 0.5, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="bo", label="Bò", mo_ta="Bò bằng hai tay hai chân (xin lỗi, bò đi).",
        keyframes=[K({"than": 72, "vai_right": -72, "vai_left": 52, "khuyu_right": 4,
                      "dui_right": -110, "dui_left": 96, "goi_right": 80, "goi_left": -64,
                      "dau": -40, "dich_y": -0.13, "dich_x": -0.12}, 0.25, KIEU_LAP),
                   K({"than": 72, "vai_right": -52, "vai_left": 72, "khuyu_right": -4,
                      "dui_right": -96, "dui_left": 110, "goi_right": 64, "goi_left": -80,
                      "dau": -40, "dich_y": -0.125, "dich_x": -0.12}, 0.25, KIEU_LAP)],
        loop=True,
    ))
    g.append(Gesture(
        name="nga_ngua", label="Ngã ngửa", mo_ta="Ngã ngửa ra sau, chân tay quơ quào (sốc, bị đẩy).",
        keyframes=[K({"than": -25, "vai_left": -120, "vai_right": -120, "dich_y": 0.02}, 0.15),
                   K({"than": -85, "vai_left": -150, "vai_right": -150, "dui_left": 40, "dui_right": -60,
                      "goi_left": -30, "goi_right": 20, "dich_y": -0.12}, 0.25),
                   K({"than": -85, "vai_left": -130, "vai_right": -160, "dui_left": 60, "dui_right": -40,
                      "goi_left": -10, "goi_right": 30, "dich_y": -0.12}, 0.4, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="voi", label="Với lên cao", mo_ta="Kiễng chân với tay lên cao (lấy đồ trên tủ).",
        keyframes=[K({"vai_left": -168, "vai_right": -168, "khuyu_left": -4, "khuyu_right": -4,
                      "dich_y": 0.025}, 0.3, KIEU_LAP),
                   K({"vai_left": -172, "vai_right": -162, "khuyu_left": -8, "khuyu_right": 0,
                      "dich_y": 0.035}, 0.3, KIEU_LAP)],
        loop=True,
    ))
    g.append(Gesture(
        name="chay", label="Chạy", mo_ta="Chạy tại chỗ thật nhanh, tay đánh mạnh (hoảng, đuổi theo).",
        keyframes=[K({"dui_left": -30, "dui_right": 18, "goi_left": 40, "goi_right": -10,
                      "vai_left": 30, "vai_right": -40, "khuyu_left": -60, "khuyu_right": -70,
                      "dich_y": 0.03}, 0.16, KIEU_LAP),
                   K({"dui_left": 18, "dui_right": -30, "goi_left": -10, "goi_right": 40,
                      "vai_left": -40, "vai_right": 30, "khuyu_left": -70, "khuyu_right": -60,
                      "dich_y": 0.0}, 0.16, KIEU_LAP)],
        loop=True,
    ))
    g.append(Gesture(
        name="dam_dat", label="Dậm chân", mo_ta="Dậm chân giận dỗi, hai tay nắm chặt.",
        keyframes=[K({"dui_right": -10, "goi_right": 50, "vai_left": -14, "vai_right": -14,
                      "khuyu_left": -40, "khuyu_right": -40, "dich_y": 0.0}, 0.14, KIEU_LAP),
                   K({"dui_right": 0, "goi_right": 0, "vai_left": -18, "vai_right": -18,
                      "khuyu_left": -50, "khuyu_right": -50, "dich_y": -0.01}, 0.14, KIEU_LAP)],
        loop=True,
    ))

    # ---------------- cử chỉ tay đời thường (làm được cả khi đang ngồi) ----------
    g.append(Gesture(
        name="chong_cam", label="Chống cằm",
        mo_ta="Tay chống cằm, đầu nghiêng (chán, nghĩ ngợi, nghe chuyện nhạt).",
        keyframes=[K({"vai_right": -24, "khuyu_right": -156, "dau": 8}, 0.35),
                   K({"vai_right": -24, "khuyu_right": -156, "dau": 9}, 0.4, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="chong_nanh", label="Chống nạnh",
        mo_ta="Hai tay chống nạnh (giận, ra oai, mắng).",
        keyframes=[K({"vai_left": -50, "vai_right": -50, "khuyu_left": 70, "khuyu_right": 70}, 0.3),
                   K({"vai_left": -50, "vai_right": -50, "khuyu_left": 70, "khuyu_right": 70,
                      "dau": -3}, 0.4, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="gai_dau", label="Gãi đầu",
        mo_ta="Gãi đầu ngượng ngùng, bối rối, cười trừ.",
        keyframes=[K({"vai_right": -112, "khuyu_right": -122, "dau": 6}, 0.25, KIEU_LAP),
                   K({"vai_right": -108, "khuyu_right": -138, "dau": 7}, 0.18, KIEU_LAP)],
        loop=True,
    ))
    g.append(Gesture(
        name="che_mieng", label="Che miệng",
        mo_ta="Tay che miệng (cười khúc khích, lỡ lời, sốc nhẹ).",
        keyframes=[K({"vai_right": -20, "khuyu_right": -162, "dau": 4}, 0.25),
                   K({"vai_right": -20, "khuyu_right": -162, "dau": 6}, 0.4, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="dap_ban", label="Đập bàn",
        mo_ta="Giơ hai tay đập mạnh xuống bàn (tức giận, phản đối). Hợp khi ngồi sau bàn.",
        keyframes=[K({"vai_left": -110, "vai_right": -110, "khuyu_left": -40, "khuyu_right": -40}, 0.18),
                   K({"vai_left": -24, "vai_right": -24, "khuyu_left": 42, "khuyu_right": 42,
                      "dau": 6}, 0.1),
                   K({"vai_left": -24, "vai_right": -24, "khuyu_left": 42, "khuyu_right": 42,
                      "dau": 4}, 0.5)],
    ))
    g.append(Gesture(
        name="go_phim", label="Gõ phím",
        mo_ta="Hai tay gõ bàn phím, mắt nhìn màn hình (đang làm việc, giả vờ bận).",
        keyframes=[K({"vai_right": -10, "khuyu_right": 72, "vai_left": -14, "khuyu_left": 62,
                      "dau": 5}, 0.14, KIEU_LAP),
                   K({"vai_right": -14, "khuyu_right": 62, "vai_left": -10, "khuyu_left": 72,
                      "dau": 5}, 0.14, KIEU_LAP)],
        loop=True,
    ))
    g.append(Gesture(
        name="gac_tay", label="Gác tay sau đầu",
        mo_ta="Hai tay gác sau gáy, thảnh thơi (lười, tự mãn, thư giãn).",
        keyframes=[K({"vai_left": -132, "vai_right": -132, "khuyu_left": -142, "khuyu_right": -142,
                      "dau": -4}, 0.35),
                   K({"vai_left": -134, "vai_right": -134, "khuyu_left": -144, "khuyu_right": -144,
                      "dau": -5}, 0.4, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="cui_dau", label="Cúi đầu",
        mo_ta="Cúi gằm mặt, tay buông thõng (buồn, xấu hổ, bị mắng).",
        keyframes=[K({"dau": 9, "co": 4, "vai_left": 4, "vai_right": 4}, 0.35),
                   K({"dau": 10, "co": 5, "vai_left": 4, "vai_right": 4}, 0.5, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="gio_tay", label="Giơ tay phát biểu",
        mo_ta="Giơ thẳng một tay lên (xin phát biểu, 'em ạ!', 'tôi!').",
        keyframes=[K({"vai_right": -168, "khuyu_right": -6}, 0.25),
                   K({"vai_right": -172, "khuyu_right": -4}, 0.5, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="lac_tay", label="Lắc ngón tay",
        mo_ta="Giơ tay lắc ngón 'không không không' (từ chối, chê).",
        keyframes=[K({"vai_right": -62, "khuyu_right": -112, "co_tay_right": -14, "dau": -4}, 0.16, KIEU_LAP),
                   K({"vai_right": -62, "khuyu_right": -112, "co_tay_right": 14, "dau": 4}, 0.16, KIEU_LAP)],
        loop=True,
    ))

    # ngồi ghế / sofa / ghế đá: chỉ gập chân, tay để tự do (cầm đồ, nói, ôm
    # đầu... vẫn ngồi). Người được hạ xuống cho chân chạm sàn, ghế vẽ theo bối
    # cảnh (core/furniture.py).
    sit = {"dui_left": -SIT_DUI_DEG, "dui_right": -SIT_DUI_DEG,
           "goi_left": SIT_DUI_DEG, "goi_right": SIT_DUI_DEG}
    g.append(Gesture(
        name="ngoi_ghe", label="Ngồi ghế",
        mo_ta="Ngồi trên ghế, sofa, ghế đá, mép giường (văn phòng, lớp học, quán, "
              "phòng khách). Đang ngồi vẫn làm cử chỉ tay được.",
        keyframes=[K(sit, 0.4), K(sit, 0.3, KIEU_GIU)],
    ))
    g.append(Gesture(
        name="dung_day", label="Đứng dậy",
        mo_ta="Đứng bật dậy khỏi ghế (sốc, giận, chuẩn bị đi), thôi tư thế ngồi/nằm.",
        keyframes=[K({"dich_y": 0.012}, 0.25), K({}, 0.2)],
    ))

    return g


# Góc gập đùi khi ngồi ghế (độ)
SIT_DUI_DEG = 62

# Tư thế cả người: giữ qua các câu sau cho tới khi có cử chỉ khác
POSTURES = {"ngoi", "om_goi", "nam", "bo", "nga_ngua", "ra_trai", "ra_phai", "khoanhtay",
            "ngoi_ghe"}
# Tư thế ngồi trên đồ đạc (người được hạ xuống, có ghế vẽ theo bối cảnh)
SEATED = {"ngoi_ghe"}
# Xương / khoá dịch làm thay đổi cả người (chân, thân, vị trí)
_BODY_KEYS = ("dui_", "goi_", "co_chan_", "dich_", "than")


def upper_body_only(g: "Gesture | None") -> bool:
    """Cử chỉ chỉ dùng tay/đầu/cổ — làm được khi đang ngồi, nằm."""
    if g is None or g.name == "dung_day":
        return False
    return all(not k.startswith(_BODY_KEYS) for kf in g.keyframes for k in kf.goc)


def switch_gesture(anim, name: str | None, effect: str | None, t: float) -> None:
    """Đổi cử chỉ cho một animator (nhân vật bộ ghép hoặc ảnh tải lên).

    Đang ngồi/nằm mà làm cử chỉ tay (ôm đầu, chỉ tay...) thì vẫn ngồi/nằm:
    tư thế cũ thành tư thế nền, cử chỉ tay chồng lên. Cử chỉ dùng cả người
    (đi, chạy, nhảy, đứng dậy...) thì bỏ tư thế nền. Cử chỉ cũ nhạt dần.
    """
    _, lib = ensure_library()
    new = lib.get(name) if name else None
    cur = getattr(anim, "current_gesture", None)
    base = getattr(anim, "base_posture", None)
    holding = base or (cur if cur is not None and cur.name in POSTURES
                       and not upper_body_only(cur) else None)
    keep_base = holding is not None and (new is None or upper_body_only(new))

    # cử chỉ cũ nhạt dần — trừ khi chính nó được giữ làm tư thế nền
    if cur is not None and anim.gesture_start is not None and not (keep_base and cur is holding):
        anim._fade_from = gesture_pose(cur, t - anim.gesture_start)
        anim._fade_t0 = t
        anim._fade_src = cur.name

    if keep_base and new is None:
        # thôi cử chỉ tay: về tư thế nền (đã ở tư thế cuối, không làm lại)
        anim.current_gesture = holding
        anim.gesture_start = t - holding.duration
        anim.base_posture = None
    elif keep_base:
        anim.base_posture = holding
        anim.current_gesture = new
        anim.gesture_start = t
    else:
        anim.base_posture = None
        anim.current_gesture = new
        anim.gesture_start = t if new is not None else None
    anim.current_effect = effect


def reset_pose(anim, t: float) -> None:
    """Về tư thế đứng (vd vào bối cảnh mới), bỏ cả tư thế ngồi/nằm đang giữ."""
    cur = getattr(anim, "current_gesture", None)
    if cur is not None and anim.gesture_start is not None:
        anim._fade_from = gesture_pose(cur, t - anim.gesture_start)
        anim._fade_t0 = t
        anim._fade_src = cur.name
    anim.base_posture = None
    anim.current_gesture = None
    anim.gesture_start = None
    anim.current_effect = None


def base_pose(anim) -> dict[str, float]:
    """Góc của tư thế nền (ngồi, nằm) đang giữ dưới cử chỉ tay."""
    b = getattr(anim, "base_posture", None)
    return gesture_angles(b, b.duration) if b is not None else {}


def sit_amount(anim, t: float) -> float:
    """Đang ngồi bao nhiêu (0 = đứng, 1 = ngồi hẳn), theo góc đùi khung vừa vẽ."""
    fading = t - getattr(anim, "_fade_t0", -99.0) < RETURN_TIME + 0.05
    names = {getattr(getattr(anim, "current_gesture", None), "name", None),
             getattr(getattr(anim, "base_posture", None), "name", None),
             getattr(anim, "_fade_src", None) if fading else None}
    if not names & SEATED:
        return 0.0
    a = (getattr(anim, "last_angles", None) or {}).get("dui_right", 0.0)
    return max(0.0, min(1.0, -a / math.radians(SIT_DUI_DEG)))


def fade_pose(pose: dict[str, float] | None, since: float, t: float) -> dict[str, float]:
    """Tư thế cũ nhạt dần về tư thế đứng trong RETURN_TIME giây (không giật)."""
    if not pose:
        return {}
    u = (t - since) / RETURN_TIME
    if u >= 1.0 or u < 0:
        return {}
    k = 1.0 - u * u * (3 - 2 * u)
    return {name: v * k for name, v in pose.items()}


def swap_sides(angles: dict[str, float]) -> dict[str, float]:
    """Đổi tay/chân phải <-> trái (tư thế cầm đồ tay trái dùng chung tư thế tay phải)."""
    out = {}
    for k, v in angles.items():
        if k.endswith("_right"):
            out[k[:-6] + "_left"] = v
        elif k.endswith("_left"):
            out[k[:-5] + "_right"] = v
        else:
            out[k] = v
    return out


# Hiệu ứng cả người: tên -> (nhãn, mô tả, hàm sinh góc)
EFFECT_NAMES = ["nhun", "nhay", "rung", "nghieng", "quay", "nga"]


def _effect_nhun(t: float, seed: int) -> dict[str, float]:
    """Nhún nhẹ toàn thân theo nhịp."""
    R = _rad
    ph = t * 5.0 + seed
    return {"than": R(1.4) * math.sin(ph), "co": R(1.0) * math.sin(ph)}


def _effect_nhay(t: float, seed: int) -> dict[str, float]:
    """Nhảy nhỏ tại chỗ."""
    R = _rad
    ph = t * 6.0 + seed
    hop = abs(math.sin(ph))
    return {
        "dui_left": R(-8) * hop,
        "dui_right": R(-8) * hop,
        "goi_left": R(14) * hop,
        "goi_right": R(14) * hop,
        "dich_y": 0.02 * (1 - hop),
    }


def _effect_rung(t: float, seed: int) -> dict[str, float]:
    """Rung nhẹ (như đang sợ)."""
    R = _rad
    ph = t * 26.0 + seed * 3
    return {
        "than": R(0.9) * math.sin(ph),
        "dau": R(1.3) * math.sin(ph + 1.0),
        "vai_left": R(0.8) * math.sin(ph + 0.4),
        "vai_right": R(0.8) * math.sin(ph + 0.9),
    }


def _effect_nghieng(t: float, seed: int) -> dict[str, float]:
    """Nghiêng người sang một bên."""
    R = _rad
    ph = t * 2.2 + seed
    return {
        "than": R(4.0) * math.sin(ph),
        "co": R(2.5) * math.sin(ph + 0.5),
        "dau": R(5.0) * math.sin(ph + 0.9),
    }


def _effect_quay(t: float, seed: int) -> dict[str, float]:
    """Xoay người (nhìn quanh)."""
    R = _rad
    ph = t * 1.8 + seed
    return {
        "than": R(7.0) * math.sin(ph),
        "co": R(4.0) * math.sin(ph + 0.4),
        "dau": R(8.0) * math.sin(ph + 0.8),
    }


def _effect_nga(t: float, seed: int) -> dict[str, float]:
    """Ngã ngửa lưng, mệt mỏi."""
    R = _rad
    ph = t * 1.6 + seed
    return {
        "than": R(-5.0) * math.sin(ph),
        "co": R(-3.5) * math.sin(ph + 0.5),
        "dau": R(-6.0) * math.sin(ph + 0.9),
    }


EFFECT_FUNCS = {
    "nhun": _effect_nhun,
    "nhay": _effect_nhay,
    "rung": _effect_rung,
    "nghieng": _effect_nghieng,
    "quay": _effect_quay,
    "nga": _effect_nga,
}

EFFECT_LABELS = {
    "nhun": ("Nhún", "Nhún nhẹ toàn thân."),
    "nhay": ("Nhảy", "Nhảy nhỏ tại chỗ."),
    "rung": ("Rung", "Rung nhẹ như đang sợ."),
    "nghieng": ("Nghiêng", "Nghiêng người sang bên."),
    "quay": ("Quay", "Xoay người nhìn quanh."),
    "nga": ("Ngả", "Ngả người, vẻ mệt."),
}


# ------------------------------------------------------------------ lưu/đọc

def save_library(path: Path, gestures: list[Gesture]) -> Path:
    """Lưu thư viện cử chỉ ra file JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": LIBRARY_VERSION,
        "gestures": [g.to_dict() for g in gestures],
        "effects": {
            name: {"label": EFFECT_LABELS[name][0], "mo_ta": EFFECT_LABELS[name][1]}
            for name in EFFECT_NAMES
        },
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_library(path: Path) -> dict[str, Gesture]:
    """Đọc thư viện cử chỉ từ file JSON."""
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {g["name"]: Gesture.from_dict(g) for g in data.get("gestures", [])}


def ensure_library() -> tuple[Path, dict[str, Gesture]]:
    """Tạo thư viện cử chỉ mặc định nếu chưa có, rồi trả về (path, dict)."""
    path = GESTURE_DIR / "gestures.json"
    version = 0
    if path.exists():
        try:
            version = int(json.loads(path.read_text(encoding="utf-8")).get("version", 0))
        except (ValueError, OSError):
            version = 0
    if version < LIBRARY_VERSION:
        save_library(path, _default_gestures())
    return path, load_library(path)


def gesture_names() -> list[str]:
    """Danh sách tên cử chỉ hợp lệ (dùng cho validator và prompt)."""
    global _NAMES_CACHE
    if _NAMES_CACHE is None:
        _, lib = ensure_library()
        _NAMES_CACHE = sorted(lib.keys())
    return list(_NAMES_CACHE)


_NAMES_CACHE: list[str] | None = None


# ------------------------------------------------------------------ áp dụng

_MIRROR_PREFIXES = ("vai_", "khuyu_", "co_tay_", "dui_", "goi_", "co_chan_")


def mirror_left(angles: dict[str, float]) -> dict[str, float]:
    """Lật dấu góc tay/chân trái để cử chỉ ghi theo bên phải thành đối xứng."""
    return {k: (-v if k.endswith("_left") and k.startswith(_MIRROR_PREFIXES) else v)
            for k, v in angles.items()}


def gesture_angles(gesture: Gesture, t: float) -> dict[str, float]:
    """Góc xương của cử chỉ tại thời điểm t (đã đối xứng bên trái)."""
    return mirror_left(gesture.sample(t))


def gesture_pose(gesture: Gesture | None, elapsed: float) -> dict[str, float] | None:
    """Tư thế của cử chỉ sau `elapsed` giây kể từ lúc bắt đầu.

    - Cử chỉ lặp: chạy mãi.
    - Khoảnh cuối kiểu "giu": giữ tư thế cuối cho tới cử chỉ sau.
    - Còn lại: về tư thế đứng từ từ trong RETURN_TIME giây.
    Trả về None khi cử chỉ đã kết thúc hẳn.
    """
    if gesture is None or elapsed < 0 or not gesture.keyframes:
        return None
    if gesture.loop or elapsed < gesture.duration:
        return gesture_angles(gesture, elapsed)
    end = gesture_angles(gesture, gesture.duration)
    if gesture.keyframes[-1].kieu == KIEU_GIU:
        return end
    u = (elapsed - gesture.duration) / RETURN_TIME
    if u >= 1.0:
        return None
    k = 1.0 - u * u * (3 - 2 * u)
    return {name: v * k for name, v in end.items()}


def effect_angles(effect: str, t: float, seed: int = 0) -> dict[str, float]:
    """Góc xương của hiệu ứng cả người tại thời điểm t."""
    fn = EFFECT_FUNCS.get(effect)
    if fn is None:
        return {}
    return mirror_left(fn(t, seed))


def breathe_angles(t: float, seed: int = 0) -> dict[str, float]:
    """Chuyển động thở rất nhẹ khi đứng yên."""
    R = _rad
    ph = t * 1.3 + seed * 0.7
    return {
        "than": R(0.7) * math.sin(ph),
        "co": R(1.1) * math.sin(ph + 0.4),
        "dau": R(1.5) * math.sin(ph + 0.8),
    }


def idle_arm_angles(t: float, seed: int = 0) -> dict[str, float]:
    """Cử động tay nhỏ khi đang nói, seed cố định để không bị đơ.

    Seed cố định theo tên nhân vật nên mỗi người có kiểu cử động riêng,
    nhưng chạy lại vẫn ra đúng một kết quả.
    """
    R = _rad
    rng = random.Random(seed)
    # 3 tần số khác nhau để cử động không tuần hoàn
    f1, f2, f3 = (rng.uniform(0.8, 1.4), rng.uniform(1.6, 2.4),
                  rng.uniform(2.8, 3.9))
    p1, p2, p3 = (rng.uniform(0, 6.28) for _ in range(3))
    amp = R(rng.uniform(3.0, 6.0))
    return {
        "vai_right": amp * math.sin(t * f1 + p1),
        "khuyu_right": amp * 0.6 * math.sin(t * f2 + p2),
        "vai_left": amp * 0.8 * math.sin(t * f3 + p3),
        "khuyu_left": amp * 0.5 * math.sin(t * f2 + p1 + 1.1),
    }


def stable_seed(name: str) -> int:
    """Seed cố định từ tên nhân vật (không phụ thuộc thứ tự dict)."""
    h = 0
    for ch in name:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return h % 100000


def merge_angles(*dicts: dict[str, float]) -> dict[str, float]:
    """Gộp các bộ góc, bộ sau ghi đè bộ trước."""
    out: dict[str, float] = {}
    for d in dicts:
        out.update(d)
    return out


def gesture_catalog_text() -> str:
    """Mô tả thư viện cử chỉ + hiệu ứng để đưa vào prompt viết kịch bản."""
    _, lib = ensure_library()
    lines = ["DANH SÁCH CỬ CHỈ DÙNG ĐƯỢC (viết trong ngoặc, cách nhau bằng dấu phẩy):"]
    for name in sorted(lib):
        g = lib[name]
        lines.append(f"  - {name}: {g.label} — {g.mo_ta}")
    lines.append("")
    lines.append("HIỆU ỨNG CẢ NGƯỜI (áp cho toàn thân, dùng cùng cú pháp):")
    for name in EFFECT_NAMES:
        label, mo_ta = EFFECT_LABELS[name]
        lines.append(f"  - {name}: {label} — {mo_ta}")
    return "\n".join(lines)
