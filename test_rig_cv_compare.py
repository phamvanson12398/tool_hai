#!/usr/bin/env python3
"""So sanh render PIL vs OpenCV cua rig."""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from core import rig as rig_mod

RIG_DIR = Path("projects/e2e_test/out/rig_step_b/rig_jieun")


def main():
    rig = rig_mod.load_rig(RIG_DIR / "rig.json")

    r = rig_mod.RigRenderer(rig, RIG_DIR)
    r._cv_ok = False
    angles = rig_mod.merge(rig_mod.idle_angles(1.7), rig_mod.wave_angles(1.7))
    pil_img = r.render(angles, mouth_open=True)

    r2 = rig_mod.RigRenderer(rig, RIG_DIR)
    r2._cv_ok = True
    cv_img = r2.render(angles, mouth_open=True)

    a = np.array(pil_img.convert("RGBA")).astype(np.int16)
    b = np.array(cv_img.convert("RGBA")).astype(np.int16)
    print("PIL size", pil_img.size, "CV size", cv_img.size)
    if a.shape != b.shape:
        print("DIFFERENT SIZE")
        return

    diff = np.abs(a - b)
    print("Max diff:", diff.max(), " Mean diff:", diff.mean())
    aa = (a[..., 3] > 10)
    ba = (b[..., 3] > 10)
    iou = (aa & ba).sum() / max(1, (aa | ba).sum())
    print("IoU alpha:", round(float(iou), 4))
    print("OK" if iou > 0.97 else "REVIEW")


if __name__ == "__main__":
    main()
