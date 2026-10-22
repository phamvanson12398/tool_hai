# -*- coding: utf-8 -*-
"""Thư viện cử chỉ và hiệu ứng cả người cho nhân vật có khung xương (Bước B).

Cử chỉ lưu dạng JSON: mỗi cử chỉ là danh sách keyframe, mỗi keyframe là
{goc: {ten_xuong: goc_radian}, kieu: "mot_lan"|"giu"|"lap", thoi_luong: giay}.

Hiệu ứng cả người (nhun, nhay, rung, nghieng, quay, nga) tách riêng, áp
lên toàn thân cho mọi nhân vật.
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

        if self.loop:
            t = t % total

        # Tìm khoảnh chứa t
        acc = 0.0
        for k in self.keyframes:
            end = acc + k.thoi_luong
            if t < end or k is self.keyframes[-1]:
                span = max(1e-6, k.thoi_luong)
                local = min(1.0, max(0.0, (t - acc) / span))
                # nội suy mượt (smoothstep) cho chuyển động tự nhiên
                u = local * local * (3 - 2 * local)
                return self._lerp_between(k, u)
            acc = end
        return {}

    def _lerp_between(self, k: Keyframe, u: float) -> dict[str, float]:
        """Nội suy từ tư thế trước tới tư thế hiện tại."""
        idx = self.keyframes.index(k)
        if idx == 0:
            src = {kk: 0.0 for kk in k.goc}
        else:
            prev = self.keyframes[idx - 1]
            src = {kk: prev.goc.get(kk, 0.0) for kk in k.goc}
        return {kk: src.get(kk, 0.0) + (vv - src.get(kk, 0.0)) * u
                for kk, vv in k.goc.items()}


# ------------------------------------------------------------------ thư viện

def _rad(deg: float) -> float:
    return math.radians(deg)


def _default_gestures() -> list[Gesture]:
    """17 cử chỉ theo đặc tả, kèm hiệu ứng cả người."""
    R = _rad
    g: list[Gesture] = []

    # 1. vaytay — vẫy tay chào
    g.append(Gesture(
        name="vaytay", label="Vẫy tay", mo_ta="Vẫy tay chào bạn, tay giơ lên ngang vai.",
        keyframes=[
            Keyframe({"vai_right": R(-100), "khuyu_right": R(-30)}, 0.25, KIEU_MOT_LAN),
            Keyframe({"vai_right": R(-100), "khuyu_right": R(30)}, 0.25, KIEU_LAP),
            Keyframe({"vai_right": R(-100), "khuyu_right": R(-30)}, 0.25, KIEU_LAP),
        ],
        loop=True,
    ))

    # 2. chitay — chỉ tay
    g.append(Gesture(
        name="chitay", label="Chỉ tay", mo_ta="Chỉ ngón tay về phía trước, như ra lệnh.",
        keyframes=[
            Keyframe({"vai_right": R(-88), "khuyu_right": R(-5)}, 0.2, KIEU_MOT_LAN),
            Keyframe({"vai_right": R(-88), "khuyu_right": R(-5),
                      "co_tay_right": R(-12)}, 0.4, KIEU_GIU),
        ],
    ))

    # 3. omdau — ôm đầu
    g.append(Gesture(
        name="omdau", label="Ôm đầu", mo_ta="Ôm đầu bằng cả hai tay, vẻ hoang mang.",
        keyframes=[
            Keyframe({"vai_left": R(-70), "vai_right": R(-70),
                      "khuyu_left": R(-95), "khuyu_right": R(-95),
                      "co_tay_left": R(-30), "co_tay_right": R(30)}, 0.35, KIEU_MOT_LAN),
            Keyframe({"vai_left": R(-72), "vai_right": R(-72),
                      "khuyu_left": R(-95), "khuyu_right": R(-95),
                      "co_tay_left": R(-30), "co_tay_right": R(30)}, 0.5, KIEU_GIU),
        ],
    ))

    # 4. khoanhtay — khoanh tay
    g.append(Gesture(
        name="khoanhtay", label="Khoanh tay", mo_ta="Khoanh tay trước ngực, vẻ bình thản.",
        keyframes=[
            Keyframe({"vai_left": R(-62), "vai_right": R(-62),
                      "khuyu_left": R(-88), "khuyu_right": R(-88),
                      "co_tay_left": R(-38), "co_tay_right": R(38)}, 0.35, KIEU_MOT_LAN),
            Keyframe({"vai_left": R(-62), "vai_right": R(-62),
                      "khuyu_left": R(-88), "khuyu_right": R(-88),
                      "co_tay_left": R(-38), "co_tay_right": R(38)}, 0.6, KIEU_GIU),
        ],
    ))

    # 5. giohaitay — giơ hai tay
    g.append(Gesture(
        name="giohaitay", label="Giơ hai tay", mo_ta="Giơ cả hai tay lên cao, vẻ vui mừng.",
        keyframes=[
            Keyframe({"vai_left": R(-105), "vai_right": R(-105),
                      "khuyu_left": R(-12), "khuyu_right": R(-12)}, 0.3, KIEU_MOT_LAN),
            Keyframe({"vai_left": R(-108), "vai_right": R(-108),
                      "khuyu_left": R(-12), "khuyu_right": R(-12)}, 0.5, KIEU_GIU),
        ],
    ))

    # 6. nhunvai — nhún vai
    g.append(Gesture(
        name="nhunvai", label="Nhún vai", mo_ta="Nhún vai lên xuống, vẻ không biết.",
        keyframes=[
            Keyframe({"vai_left": R(-26), "vai_right": R(-26),
                      "co": R(-4)}, 0.18, KIEU_LAP),
            Keyframe({"vai_left": R(4), "vai_right": R(4),
                      "co": R(3)}, 0.18, KIEU_LAP),
        ],
        loop=True,
    ))

    # 7. voratay — vỗ tay
    g.append(Gesture(
        name="voratay", label="Vỗ tay", mo_ta="Vỗ tay như đang vỗ nhau.",
        keyframes=[
            Keyframe({"vai_left": R(-58), "vai_right": R(-58),
                      "khuyu_left": R(-72), "khuyu_right": R(-72)}, 0.2, KIEU_LAP),
            Keyframe({"vai_left": R(-48), "vai_right": R(-48),
                      "khuyu_left": R(-84), "khuyu_right": R(-84)}, 0.2, KIEU_LAP),
        ],
        loop=True,
    ))

    # 8. gatdau — gật đầu
    g.append(Gesture(
        name="gatdau", label="Gật đầu", mo_ta="Gật đầu đồng ý.",
        keyframes=[
            Keyframe({"dau": R(9)}, 0.16, KIEU_MOT_LAN),
            Keyframe({"dau": R(-7)}, 0.16, KIEU_MOT_LAN),
            Keyframe({"dau": R(4)}, 0.18, KIEU_MOT_LAN),
        ],
    ))

    # 9. lacdau — lắc đầu
    g.append(Gesture(
        name="lacdau", label="Lắc đầu", mo_ta="Lắc đầu từ chối.",
        keyframes=[
            Keyframe({"dau": R(0), "co": R(-7)}, 0.18, KIEU_LAP),
            Keyframe({"dau": R(0), "co": R(7)}, 0.18, KIEU_LAP),
        ],
        loop=True,
    ))

    # 10. dibo — dị bộ (bước chân tại chỗ)
    g.append(Gesture(
        name="dibo", label="Đi bộ", mo_ta="Bước chân tại chỗ, như đang đi bộ.",
        keyframes=[
            Keyframe({"dui_left": R(16), "goi_left": R(-14),
                      "dui_right": R(-16), "goi_right": R(14)}, 0.25, KIEU_LAP),
            Keyframe({"dui_left": R(-16), "goi_left": R(14),
                      "dui_right": R(16), "goi_right": R(-14)}, 0.25, KIEU_LAP),
        ],
        loop=True,
    ))

    # 11. vao_trai — bước vào từ trái
    g.append(Gesture(
        name="vao_trai", label="Vào từ trái", mo_ta="Bước vào khung hình từ bên trái.",
        keyframes=[
            Keyframe({"than": R(0)}, 0.6, KIEU_MOT_LAN),
        ],
    ))

    # 12. vao_phai — bước vào từ phải
    g.append(Gesture(
        name="vao_phai", label="Vào từ phải", mo_ta="Bước vào khung hình từ bên phải.",
        keyframes=[
            Keyframe({"than": R(0)}, 0.6, KIEU_MOT_LAN),
        ],
    ))

    # 13. ra_trai — bước ra trái
    g.append(Gesture(
        name="ra_trai", label="Ra trái", mo_ta="Bước ra khỏi khung hình về bên trái.",
        keyframes=[
            Keyframe({"than": R(0)}, 0.6, KIEU_MOT_LAN),
        ],
    ))

    # 14. ra_phai — bước ra phải
    g.append(Gesture(
        name="ra_phai", label="Ra phải", mo_ta="Bước ra khỏi khung hình về bên phải.",
        keyframes=[
            Keyframe({"than": R(0)}, 0.6, KIEU_MOT_LAN),
        ],
    ))

    # 15. nhaylen — nhảy lên
    g.append(Gesture(
        name="nhaylen", label="Nhảy lên", mo_ta="Nhảy lên một cái, vẻ hào hứng.",
        keyframes=[
            Keyframe({"than": R(0), "dui_left": R(10), "dui_right": R(-10),
                      "goi_left": R(-18), "goi_right": R(18)}, 0.18, KIEU_MOT_LAN),
            Keyframe({"than": R(0), "dui_left": R(-6), "dui_right": R(6),
                      "goi_left": R(14), "goi_right": R(-14)}, 0.26, KIEU_MOT_LAN),
        ],
    ))

    # 16. ngangua — ngang vai
    g.append(Gesture(
        name="ngangua", label="Ngang vai", mo_ta="Hạ vai xuống, vẻ chán nản.",
        keyframes=[
            Keyframe({"vai_left": R(16), "vai_right": R(16),
                      "co": R(6), "dau": R(4)}, 0.3, KIEU_MOT_LAN),
            Keyframe({"vai_left": R(16), "vai_right": R(16),
                      "co": R(6), "dau": R(4)}, 0.5, KIEU_GIU),
        ],
    ))

    # 17. ve_tu_the — vẽ tư thế (chỉ tay hoặc vẫy tay)
    g.append(Gesture(
        name="ve_tu_the", label="Vẽ tư thế", mo_ta="Tự nhiên tạo tư thế tay, linh hoạt.",
        keyframes=[
            Keyframe({"vai_right": R(-95), "khuyu_right": R(-25),
                      "co_tay_right": R(18)}, 0.3, KIEU_MOT_LAN),
            Keyframe({"vai_right": R(-88), "khuyu_right": R(20),
                      "co_tay_right": R(-14)}, 0.35, KIEU_MOT_LAN),
        ],
    ))

    return g


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
    return {
        "than": R(0.0),
        "dui_left": R(9) * math.sin(ph),
        "dui_right": R(-9) * math.sin(ph),
        "goi_left": R(-12) * math.sin(ph),
        "goi_right": R(12) * math.sin(ph),
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
        "version": 1,
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
    if not path.exists():
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

def gesture_angles(gesture: Gesture, t: float) -> dict[str, float]:
    """Góc xương của cử chỉ tại thời điểm t."""
    return gesture.sample(t)


def effect_angles(effect: str, t: float, seed: int = 0) -> dict[str, float]:
    """Góc xương của hiệu ứng cả người tại thời điểm t."""
    fn = EFFECT_FUNCS.get(effect)
    if fn is None:
        return {}
    return fn(t, seed)


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
