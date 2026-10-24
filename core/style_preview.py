# -*- coding: utf-8 -*-
"""Xem trước kiểu nhân vật (tab "Kiểu nhân vật").

Mỗi kiểu (kiểu vẽ sẵn trong film_rig.CHAR_STYLES, kiểu có sẵn đi kèm tool, kiểu
chị tạo từ ảnh mẫu) có:
- ảnh động: nhân vật chính diễn một chuỗi hành động (đứng, đi, vẫy tay, nói, nhảy
  mừng, ngồi, khóc, suy nghĩ...) — biết kiểu đó cử động trông thế nào;
- dàn nhân vật: nhân vật chính + vài người khác cùng nét vẽ + con chó.
Vẽ một lần rồi lưu ở data/previews/kieu/ (đổi kiểu thì tự vẽ lại).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import config, doodle, film_act, film_rig, style_lib

DIR = config.PREVIEWS / "kieu"
VERSION = 3
BG = (238, 228, 206)
FLOOR = (214, 196, 160)

DEFAULT_MAIN = {"species": "human", "age": "adult", "sex": "male", "skin": "fair", "hair": "short",
                "hair_color": "black", "top": "shirt", "top_color": "blue", "bottom_color": "navy"}
# người khác cùng nét vẽ trong dàn nhân vật
OTHERS = [
    {"species": "human", "age": "young", "sex": "female", "skin": "fair", "hair": "long",
     "hair_color": "black", "top": "ao_ba_ba", "top_color": "pink", "bottom_color": "black"},
    {"species": "human", "age": "old", "sex": "male", "skin": "tan", "hair": "messy",
     "hair_color": "gray", "facial": "goatee", "top": "ao_nau", "top_color": "brown",
     "bottom_color": "black"},
    {"species": "human", "age": "child", "sex": "male", "skin": "fair", "hair": "bangs",
     "hair_color": "black", "top": "shirt", "top_color": "yellow", "bottom_color": "blue"},
]
# chuỗi hành động trong ảnh động: (hành động, giây, ngồi?)
SEQ = [("idle", 1.2), ("walk", 1.6), ("wave", 1.4), ("talk", 1.6), ("jump", 1.6),
       ("sit", 1.6), ("cry", 1.6), ("think", 1.4), ("laugh", 1.4)]


def items() -> list[dict]:
    """Mọi kiểu nhân vật: [{id, name, kind (preset|builtin|saved), note, sample}]."""
    out = [{"id": k, "name": v["label"], "kind": "preset", "note": "", "sample": False}
           for k, v in film_rig.CHAR_STYLES.items()]
    for it in style_lib.items():
        got = style_lib.get(it["id"]) or {}
        out.append({"id": "lib:" + it["id"], "name": it["name"],
                    "kind": "builtin" if style_lib.is_builtin(it["id"]) else "saved",
                    "note": got.get("note", ""), "sample": bool(got.get("image")),
                    "created": it.get("created", "")})
    return out


def cast_kits(sid: str) -> list[dict] | None:
    """Các nhân vật trong ảnh mẫu (Claude liệt kê khi tạo kiểu): [{kit..., expr}]."""
    if sid.startswith("lib:"):
        got = style_lib.get(sid[4:]) or {}
        if isinstance(got.get("cast"), list) and got["cast"]:
            return [c for c in got["cast"] if isinstance(c, dict)][:6]
    return None


def resolve(sid: str) -> tuple[dict, dict] | None:
    """(thông số nét vẽ, bộ ghép nhân vật chính) của một kiểu."""
    if sid in film_rig.CHAR_STYLES:
        return film_rig.clean_style(film_rig.CHAR_STYLES[sid]), doodle.clean_kit(DEFAULT_MAIN)
    if sid.startswith("lib:"):
        got = style_lib.get(sid[4:])
        if got:
            kit = got.get("kit") if isinstance(got.get("kit"), dict) and got["kit"] else DEFAULT_MAIN
            return film_rig.clean_style(got.get("style")), doodle.clean_kit(kit)
    return None


def _sig(sid: str, sty: dict, kit: dict, what: str) -> Path:
    h = hashlib.md5(json.dumps([VERSION, sty, kit, what], sort_keys=True).encode()).hexdigest()[:10]
    safe = sid.replace(":", "_")
    return DIR / f"{safe}_{what}_{h}"


def _font(size):
    from PIL import ImageFont
    try:
        from . import video
        return ImageFont.truetype(video.find_font(False, True), size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def _stage(W, H, floor):
    a = np.zeros((H, W, 3), np.uint8)
    a[:] = BG
    a[floor:] = FLOOR
    a[floor:floor + 2] = (150, 130, 100)
    return a


def anim(sid: str) -> Path | None:
    """Ảnh động (webp) nhân vật chính diễn các hành động."""
    got = resolve(sid)
    if not got:
        return None
    sty, kit = got
    out = _sig(sid, sty, kit, "anim").with_suffix(".webp")
    if out.exists():
        return out
    W, H, fps = 440, 330, 12
    floor = H - 34
    T = 230.0
    rig = film_rig.Rig(kit, T, 5, sty)
    cam = np.array([[1, 0, 0], [0, 1, 0]], float)
    font = _font(16)
    frames = []
    t_all = 0.0
    for act, dur in SEQ:
        n = int(dur * fps)
        for k in range(n):
            t = k / fps
            img = _stage(W, H, floor)
            x, d = W * 0.5, 1
            if act == "walk":                     # đi từ trái sang phải giữa khung
                x = W * (0.32 + 0.36 * k / max(1, n - 1))
                p = film_act.walk_cycle((x - W * 0.32) / T, t)
                p["expr"] = "neutral"
            elif act == "sit":
                p = film_act.pose("talk", t, 5, dur, True, posture="sit")
                p["seat_h"] = None
            else:
                p = film_act.pose(act, t, 5, dur, act == "talk")
            if act == "talk":
                p["mouth"] = (int(t * 8) % 2 == 0)
            p.update(x=x, y=floor, dir=d, look=0.35, blink=(t_all + t) % 3.1 < 0.12)
            rig.draw(img, p, cam, 1.0)
            pil = Image.fromarray(img)
            ImageDraw.Draw(pil).text((10, 8), film_act.ACTIONS.get(act, (act,))[0], fill=(90, 70, 50),
                                     font=font)
            frames.append(pil)
        t_all += dur
    DIR.mkdir(parents=True, exist_ok=True)
    for old in DIR.glob(sid.replace(":", "_") + "_anim_*"):
        old.unlink(missing_ok=True)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0,
                   quality=70, method=4)
    return out


def cast(sid: str) -> Path | None:
    """Dàn nhân vật: nhân vật chính + người khác cùng nét vẽ + con chó."""
    got = resolve(sid)
    if not got:
        return None
    sty, kit = got
    mine = cast_kits(sid)
    out = _sig(sid, sty, {"kit": kit, "cast": mine}, "cast").with_suffix(".png")
    if out.exists():
        return out
    if mine:                                      # đúng các bạn trong ảnh mẫu, đúng biểu cảm
        kits = [doodle.clean_kit(c) for c in mine]
        exprs = [c.get("expr") or "neutral" for c in mine]
    else:
        kits = [kit] + [doodle.clean_kit(k) for k in OTHERS]
        exprs = ["happy", "neutral", "sad", "happy"]
    W, H = 170 * (len(kits) + 1), 320
    floor = H - 34
    img = _stage(W, H, floor)
    cam = np.array([[1, 0, 0], [0, 1, 0]], float)
    for i, k in enumerate(kits):
        rig = film_rig.Rig(k, 210.0, 11 + i, sty)
        p = film_act.pose("idle", 0.4 * i, 11 + i)
        p.update(x=85 + 170 * i, y=floor, dir=1 if i % 2 == 0 else -1, look=0.0 if mine else
                 (0.3 if i % 2 == 0 else -0.3), expr=exprs[i % len(exprs)])
        rig.draw(img, p, cam, 1.0)
    dog = film_rig.AnimalRig(doodle.clean_kit({"species": "dog", "fur": "yellow"}), 210.0, 3)
    pd = film_act.animal_pose("wag", 0.3)
    pd.update(x=85 + 170 * len(kits), y=floor, dir=-1)
    dog.draw(img, pd, cam, 1.0)
    DIR.mkdir(parents=True, exist_ok=True)
    for old in DIR.glob(sid.replace(":", "_") + "_cast_*"):
        old.unlink(missing_ok=True)
    Image.fromarray(img).save(out)
    return out


def compare(sample: str | Path, sty: dict, kit: dict) -> Image.Image:
    """Ảnh so sánh cho Claude chỉnh nét vẽ: TRÁI ảnh mẫu, PHẢI nhân vật tool vẽ (đứng thẳng
    + dáng đi), cùng chiều cao."""
    H = 520
    smp = Image.open(sample).convert("RGB")
    smp.thumbnail((620, H - 40))
    W = smp.width + 40 + 560
    out = Image.new("RGB", (W, H), (255, 255, 255))
    out.paste(smp, (20, (H - smp.height) // 2))
    floor = H - 40
    T = float(H - 90)
    stage = _stage(560, H, floor)
    cam = np.array([[1, 0, 0], [0, 1, 0]], float)
    rig = film_rig.Rig(doodle.clean_kit(kit), T, 5, sty)
    p = film_act.pose("idle", 0.0, 5)
    p.update(x=170, y=floor, dir=1, look=0.1)
    rig.draw(stage, p, cam, 1.0)
    w = film_act.walk_cycle(0.25, 0.0)
    w.update(x=420, y=floor, dir=1, look=0.5, expr="neutral")
    rig.draw(stage, w, cam, 1.0)
    out.paste(Image.fromarray(stage), (smp.width + 40, 0))
    d = ImageDraw.Draw(out)
    d.line([(smp.width + 30, 0), (smp.width + 30, H)], fill=(200, 60, 60), width=3)
    f = _font(18)
    d.text((24, 8), "ẢNH MẪU", fill=(200, 60, 60), font=f)
    d.text((smp.width + 52, 8), "TOOL ĐANG VẼ", fill=(200, 60, 60), font=f)
    return out
