# -*- coding: utf-8 -*-
"""Nhân vật từ ảnh tải lên (Bước C1).

- Tách nền bằng morphology (ảnh vẽ nét đen trên nền trắng).
- Ước đoán vị trí khớp bằng mô hình nhận dáng người (nếu cài được pip package),
  không thì đặt khung xương mặc định theo hình dạng ảnh.
- Chia ảnh theo xương (mỗi điểm ảnh thuộc đoạn xương gần nhất), rồi xoay
  cứng từng đoạn tay/chân quanh khớp (đoạn con đi theo đoạn cha); đầu xoay
  nguyên khối quanh cổ.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from . import config
from .character_kit import CharSpec


# ------------------------------------------------------------------ tách nền

def _imread(img_path: Path):
    """Đọc ảnh BGR, chịu được tên file tiếng Hàn/tiếng Việt trên Windows
    (cv2.imread không mở được đường dẫn có ký tự Unicode)."""
    try:
        buf = np.fromfile(str(img_path), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(buf, cv2.IMREAD_COLOR) if buf.size else None


def remove_background_stick(img_path: Path) -> tuple[Image.Image, np.ndarray]:
    """Tách nền trắng của ảnh vẽ nét đen.

    Trả về (PIL Image RGBA đã tách nền, mask uint8 0/255 của vùng vẽ).
    """
    img = _imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Không đọc được ảnh: {img_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # vẽ đen = vùng vẽ (ít hơn 120)
    _, mask = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)
    # mở để nối nét đứt, đóng để lũy vết
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    # tô màu vẽ sang trắng
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    rgba[..., 3] = mask
    filled = np.full_like(gray, 255)
    rgba[..., 0] = filled
    rgba[..., 1] = filled
    rgba[..., 2] = filled
    pil = Image.fromarray(rgba, "RGBA")
    return pil, mask


# ------------------------------------------------------------------ ước đoán khớp

@dataclass
class PhotoJoints:
    """Vị trí các khớp trong toạ độ ảnh gốc (x, y)."""
    head: tuple[int, int]
    neck: tuple[int, int]
    shoulder_l: tuple[int, int]
    shoulder_r: tuple[int, int]
    elbow_l: tuple[int, int]
    elbow_r: tuple[int, int]
    wrist_l: tuple[int, int]
    wrist_r: tuple[int, int]
    hip_l: tuple[int, int]
    hip_r: tuple[int, int]
    knee_l: tuple[int, int]
    knee_r: tuple[int, int]
    ankle_l: tuple[int, int]
    ankle_r: tuple[int, int]

    def as_dict(self) -> dict[str, tuple[int, int]]:
        return {
            "head": self.head, "neck": self.neck,
            "shoulder_l": self.shoulder_l, "shoulder_r": self.shoulder_r,
            "elbow_l": self.elbow_l, "elbow_r": self.elbow_r,
            "wrist_l": self.wrist_l, "wrist_r": self.wrist_r,
            "hip_l": self.hip_l, "hip_r": self.hip_r,
            "knee_l": self.knee_l, "knee_r": self.knee_r,
            "ankle_l": self.ankle_l, "ankle_r": self.ankle_r,
        }


def _estimate_pose_mediapipe(img_rgb: np.ndarray) -> PhotoJoints | None:
    """Thử dùng mediapipe nếu có. Trả về None nếu không cài hoặc không phát hiện."""
    try:
        import mediapipe as mp  # type: ignore
    except Exception:
        return None
    mp_pose = mp.solutions.pose
    with mp_pose.Pose(static_image_mode=True,
                      model_complexity=1,
                      enable_segmentation=False) as pose:
        results = pose.process(img_rgb)
        if not results.pose_landmarks:
            return None
        lm = results.pose_landmarks.landmark
        h, w = img_rgb.shape[:2]
        def pt(idx):
            p = lm[idx]
            return (int(p.x * w), int(p.y * h))
        return PhotoJoints(
            head=pt(mp_pose.PoseLandmark.NOSE),
            neck=pt(mp_pose.PoseLandmark.NOSE),
            shoulder_l=pt(mp_pose.PoseLandmark.LEFT_SHOULDER),
            shoulder_r=pt(mp_pose.PoseLandmark.RIGHT_SHOULDER),
            elbow_l=pt(mp_pose.PoseLandmark.LEFT_ELBOW),
            elbow_r=pt(mp_pose.PoseLandmark.RIGHT_ELBOW),
            wrist_l=pt(mp_pose.PoseLandmark.LEFT_WRIST),
            wrist_r=pt(mp_pose.PoseLandmark.RIGHT_WRIST),
            hip_l=pt(mp_pose.PoseLandmark.LEFT_HIP),
            hip_r=pt(mp_pose.PoseLandmark.RIGHT_HIP),
            knee_l=pt(mp_pose.PoseLandmark.LEFT_KNEE),
            knee_r=pt(mp_pose.PoseLandmark.RIGHT_KNEE),
            ankle_l=pt(mp_pose.PoseLandmark.LEFT_ANKLE),
            ankle_r=pt(mp_pose.PoseLandmark.RIGHT_ANKLE),
        )


def estimate_joints(img_path: Path) -> tuple[PhotoJoints, str]:
    """Ước đoán khớp từ ảnh. Trả về (joints, nguồn: 'mediapipe'|'fallback')."""
    img = _imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Không đọc được ảnh: {img_path}")
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    joints = _estimate_pose_mediapipe(img_rgb)
    if joints is not None:
        return joints, "mediapipe"
    # Fallback: đặt khớp mặc định theo hình dạng ảnh (nguyên thân, giữa khung)
    h, w = img.shape[:2]
    cx = w // 2
    head = (cx, int(h * 0.13))
    neck = (cx, int(h * 0.20))
    shoulder_l = (int(cx * 0.55), int(h * 0.26))
    shoulder_r = (int(cx * 1.45), int(h * 0.26))
    elbow_l = (int(cx * 0.42), int(h * 0.38))
    elbow_r = (int(cx * 1.58), int(h * 0.38))
    wrist_l = (int(cx * 0.30), int(h * 0.45))
    wrist_r = (int(cx * 1.70), int(h * 0.45))
    hip_l = (int(cx * 0.50), int(h * 0.56))
    hip_r = (int(cx * 1.50), int(h * 0.56))
    knee_l = (int(cx * 0.46), int(h * 0.78))
    knee_r = (int(cx * 1.54), int(h * 0.78))
    ankle_l = (int(cx * 0.42), int(h * 0.95))
    ankle_r = (int(cx * 1.58), int(h * 0.95))
    return PhotoJoints(head, neck, shoulder_l, shoulder_r,
                       elbow_l, elbow_r, wrist_l, wrist_r,
                       hip_l, hip_r, knee_l, knee_r,
                       ankle_l, ankle_r), "fallback"


# ------------------------------------------------------------------ cử động theo xương

def _rot_mat(cx: float, cy: float, a: float) -> np.ndarray:
    """Ma trận 3x3 xoay góc a (rad) quanh (cx, cy), cùng chiều với rig.py
    (toạ độ ảnh y hướng xuống: góc dương = quay theo chiều kim đồng hồ)."""
    ca, sa = math.cos(a), math.sin(a)
    return np.array([[ca, -sa, cx - ca * cx + sa * cy],
                     [sa, ca, cy - sa * cx - ca * cy],
                     [0.0, 0.0, 1.0]])


def _seg_dist(xx: np.ndarray, yy: np.ndarray, p0, p1) -> np.ndarray:
    """Khoảng cách từ mỗi điểm ảnh tới đoạn thẳng p0→p1."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ll = dx * dx + dy * dy
    if ll < 1e-6:
        return np.hypot(xx - p0[0], yy - p0[1])
    t = np.clip(((xx - p0[0]) * dx + (yy - p0[1]) * dy) / ll, 0.0, 1.0)
    return np.hypot(xx - (p0[0] + t * dx), yy - (p0[1] + t * dy))


_LABEL_CACHE: dict = {}


def _bone_labels(h: int, w: int, j: PhotoJoints) -> np.ndarray:
    """Chia ảnh theo xương: mỗi điểm ảnh thuộc đoạn xương gần nó nhất.

    Thứ tự nhãn: 0 thân, 1 đầu, rồi (trên, dưới) của chân trái, chân phải,
    tay trái, tay phải. Kết quả được nhớ lại theo khung xương.
    """
    key = (h, w, tuple(j.as_dict().items()))
    if key in _LABEL_CACHE:
        return _LABEL_CACHE[key]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    hip_c = ((j.hip_l[0] + j.hip_r[0]) / 2, (j.hip_l[1] + j.hip_r[1]) / 2)
    segs = [(j.neck, hip_c), (j.neck, _extend(j.neck, j.head, 0.6))]
    for root, mid, end in ((j.hip_l, j.knee_l, j.ankle_l),
                           (j.hip_r, j.knee_r, j.ankle_r),
                           (j.shoulder_l, j.elbow_l, j.wrist_l),
                           (j.shoulder_r, j.elbow_r, j.wrist_r)):
        segs.append((root, mid))
        segs.append((mid, _extend(mid, end, 0.35)))
    dist = np.stack([_seg_dist(xx, yy, a, b) for a, b in segs])
    labels = np.argmin(dist, axis=0).astype(np.uint8)
    if len(_LABEL_CACHE) > 8:
        _LABEL_CACHE.clear()
    _LABEL_CACHE[key] = labels
    return labels


def _extend(p0, p1, k: float) -> tuple[float, float]:
    """Kéo dài đoạn p0→p1 thêm k lần độ dài (để ăn cả bàn tay, bàn chân)."""
    return (p1[0] + (p1[0] - p0[0]) * k, p1[1] + (p1[1] - p0[1]) * k)


def _over(dst: np.ndarray, src: np.ndarray) -> np.ndarray:
    """Chồng ảnh RGBA src lên dst (alpha over)."""
    sa = src[..., 3:4].astype(np.float32) / 255.0
    da = dst[..., 3:4].astype(np.float32) / 255.0
    out_a = sa + da * (1 - sa)
    rgb = (src[..., :3] * sa + dst[..., :3] * da * (1 - sa)) / np.maximum(out_a, 1e-6)
    out = np.empty_like(dst)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[..., 3:4] = np.clip(out_a * 255, 0, 255).astype(np.uint8)
    return out


def warp_by_bones(img_rgba: np.ndarray, joints: PhotoJoints,
                  angles: dict[str, float]) -> np.ndarray:
    """Cử động ảnh theo các góc xương cho trước.

    Mỗi điểm ảnh thuộc đoạn xương gần nó nhất; đoạn tay/chân được xoay cứng
    quanh khớp, đoạn con đi theo đoạn cha (vai → khuỷu, đùi → gối).
    angles: {ten_xuong: rad}. Các xương hỗ trợ: vai/khuyu, dui/goi, dau.
    Trả về ảnh RGBA đã cử động (cùng kích thước đầu vào).
    """
    h, w = img_rgba.shape[:2]
    j = joints
    # (khớp gốc, khớp giữa, xương trên, xương dưới), cùng thứ tự với _bone_labels
    chains = [
        (j.hip_l, j.knee_l, "dui_left", "goi_left"),
        (j.hip_r, j.knee_r, "dui_right", "goi_right"),
        (j.shoulder_l, j.elbow_l, "vai_left", "khuyu_left"),
        (j.shoulder_r, j.elbow_r, "vai_right", "khuyu_right"),
    ]
    a_dau = angles.get("dau", 0.0)
    head_moves = abs(a_dau) > math.radians(0.3)
    moving = [(i, c) for i, c in enumerate(chains)
              if abs(angles.get(c[2], 0.0)) > 1e-4 or abs(angles.get(c[3], 0.0)) > 1e-4]
    if not moving and not head_moves:
        return img_rgba.copy()

    labels = _bone_labels(h, w, j)
    alpha = img_rgba[..., 3]
    body = img_rgba.copy()
    layers: list[np.ndarray] = []

    def take(label: int, m3: np.ndarray) -> None:
        sel = labels == label
        part = img_rgba.copy()
        part[..., 3] = np.where(sel, alpha, 0)
        body[..., 3][sel] = 0
        layers.append(cv2.warpAffine(part, m3[:2], (w, h), flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_CONSTANT,
                                     borderValue=(0, 0, 0, 0)))

    for i, (root, mid, up_key, low_key) in moving:
        m_up = _rot_mat(root[0], root[1], angles.get(up_key, 0.0))
        m_low = m_up @ _rot_mat(mid[0], mid[1], angles.get(low_key, 0.0))
        take(2 + 2 * i, m_up)
        take(3 + 2 * i, m_low)
    if head_moves:
        take(1, _rot_mat(j.neck[0], j.neck[1], a_dau))

    result = body
    for layer in layers:
        result = _over(result, layer)
    return result


# ------------------------------------------------------------------ render khung

@dataclass
class PhotoCharacter:
    name: str
    img_path: Path
    rgba: Image.Image          # đã tách nền
    joints: PhotoJoints
    source: str                # 'mediapipe' | 'fallback'
    valid: bool = True         # ảnh đạt (nguyên thân) hay không

    @classmethod
    def load(cls, name: str, img_path: Path) -> "PhotoCharacter":
        rgba, mask = remove_background_stick(img_path)
        joints, source = estimate_joints(img_path)
        # Ảnh không đạt nếu ít hơn 5% pixel là vẽ (nửa người, lờ, v.v.)
        valid = float((mask > 0).mean()) > 0.005
        return cls(name, img_path, rgba, joints, source, valid)

    def render(self, angles: dict[str, float],
               mouth_open: bool = False,
               size: tuple[int, int] = (config.WIDTH, config.HEIGHT)
               ) -> Image.Image:
        """Render một khung: cử động theo angles."""
        arr = np.array(self.rgba.convert("RGBA"))
        warped = warp_by_bones(arr, self.joints, angles)
        img = Image.fromarray(warped, "RGBA")
        if img.size != size:
            img = img.resize(size, Image.LANCZOS)
        return img
