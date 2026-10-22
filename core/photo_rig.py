# -*- coding: utf-8 -*-
"""Nhân vật từ ảnh tải lên (Bước C1).

- Tách nền bằng morphology (ảnh vẽ nét đen trên nền trắng).
- Ước đoán vị trí khớp bằng mô hình nhận dáng người (nếu cài được pip package),
  không thì đặt khung xương mặc định theo hình dạng ảnh.
- Uốn lưới tam giác theo khung xương (SCIPY affine trên từng vùng tam giác).
- Phần ĐẦU luôn giữ cứng để gắn biểu cảm và miệng như cũ.

Module độc lập, chưa gắn vào luồng dựng chính.
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

def remove_background_stick(img_path: Path) -> tuple[Image.Image, np.ndarray]:
    """Tách nền trắng của ảnh vẽ nét đen.

    Trả về (PIL Image RGBA đã tách nền, mask uint8 0/255 của vùng vẽ).
    """
    img = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
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
    img = cv2.imread(str(img_path))
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


# ------------------------------------------------------------------ uốn lưới tam giác

def _tri_warp(src: np.ndarray, dst: np.ndarray,
              src_tri: np.ndarray, dst_tri: np.ndarray,
              out_shape: tuple[int, int]) -> np.ndarray:
    """Warp một vùng tam giác từ src_tri sang dst_tri bằng affine (scipy)."""
    from scipy.ndimage import affine_transform
    M = cv2.getAffineTransform(src_tri.astype(np.float32),
                               dst_tri.astype(np.float32))
    Minv = cv2.invertAffineTransform(M)
    out = np.zeros((out_shape[0], out_shape[1], 4), dtype=np.uint8)
    for ch in range(4):
        out[..., ch] = affine_transform(src[..., ch], Minv[:2, :2],
                                        offset=Minv[:2, 2],
                                        output_shape=out_shape,
                                        order=1, mode="constant", cval=0)
    return out


def warp_by_bones(img_rgba: np.ndarray, joints: PhotoJoints,
                  angles: dict[str, float]) -> np.ndarray:
    """Uớn lưới tam giác theo các góc xương cho trước.

    angles: {ten_xuong: rad}. Các xương hỗ trợ: vai->khuyu->co_tay,
    dui->goi->co_chan, dau, co, than.
    Trả về ảnh RGBA đã uốn (cùng kích thước đầu vào).
    """
    h, w = img_rgba.shape[:2]
    R = math.radians

    def rot(px, py, cx, cy, a):
        ca, sa = math.cos(a), math.sin(a)
        dx, dy = px - cx, py - cy
        return (cx + dx * ca - dy * sa, cy + dx * sa + dy * ca)

    result = img_rgba.copy()

    def warp_segment(result_in, p0, p1, p2, ang_deg):
        """Warp tam giác (p0,p1,p2) xoay góc ang_deg quanh p0, trả về ảnh mới."""
        a = R(ang_deg)
        q0 = p0
        q1 = rot(p1[0], p1[1], p0[0], p0[1], a)
        q2 = rot(p2[0], p2[1], p0[0], p0[1], a)
        src_tri = np.array([p0, p1, p2], dtype=np.float32)
        dst_tri = np.array([q0, q1, q2], dtype=np.float32)
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillConvexPoly(mask, np.array([p0, p1, p2], dtype=np.int32), 255)
        src_tri_masked = cv2.bitwise_and(result_in, result_in, mask=mask)
        warped = _tri_warp(src_tri_masked, result_in, src_tri, dst_tri, (h, w))
        mask2 = np.zeros((h, w), dtype=np.uint8)
        cv2.fillConvexPoly(mask2, np.array([q0, q1, q2], dtype=np.int32), 255)
        cleared = cv2.bitwise_and(result_in, result_in, mask=cv2.bitwise_not(mask2))
        return cv2.add(cleared, cv2.bitwise_and(warped, warped, mask=mask2))

    # Tay phải
    if "vai_right" in angles:
        result = warp_segment(result, joints.shoulder_r, joints.elbow_r,
                              joints.wrist_r, math.degrees(angles["vai_right"]))
    if "khuyu_right" in angles:
        result = warp_segment(result, joints.elbow_r, joints.wrist_r,
                              (joints.wrist_r[0] + 20, joints.wrist_r[1]),
                              math.degrees(angles["khuyu_right"]))
    # Tay trái
    if "vai_left" in angles:
        result = warp_segment(result, joints.shoulder_l, joints.elbow_l,
                              joints.wrist_l, math.degrees(angles["vai_left"]))
    if "khuyu_left" in angles:
        result = warp_segment(result, joints.elbow_l, joints.wrist_l,
                              (joints.wrist_l[0] - 20, joints.wrist_l[1]),
                              math.degrees(angles["khuyu_left"]))
    # Chân
    if "dui_right" in angles:
        result = warp_segment(result, joints.hip_r, joints.knee_r,
                              joints.ankle_r, math.degrees(angles["dui_right"]))
    if "goi_right" in angles:
        result = warp_segment(result, joints.knee_r, joints.ankle_r,
                              (joints.ankle_r[0], joints.ankle_r[1] + 40),
                              math.degrees(angles["goi_right"]))
    if "dui_left" in angles:
        result = warp_segment(result, joints.hip_l, joints.knee_l,
                              joints.ankle_l, math.degrees(angles["dui_left"]))
    if "goi_left" in angles:
        result = warp_segment(result, joints.knee_l, joints.ankle_l,
                              (joints.ankle_l[0], joints.ankle_l[1] + 40),
                              math.degrees(angles["goi_left"]))
    # Đầu giữ cứng — chỉ áp nếu góc dau đủ lớn
    if "dau" in angles and abs(angles["dau"]) > math.radians(2):
        result = warp_segment(result, joints.neck, joints.head,
                              (joints.head[0] + 60, joints.head[1]),
                              math.degrees(angles["dau"]))

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
        """Render một khung: uốn lưới theo angles, đầu giữ cứng."""
        arr = np.array(self.rgba.convert("RGBA"))
        warped = warp_by_bones(arr, self.joints, angles)
        img = Image.fromarray(warped, "RGBA")
        if img.size != size:
            img = img.resize(size, Image.LANCZOS)
        return img
