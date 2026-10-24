# -*- coding: utf-8 -*-
"""Cảnh chèn màn hình điện thoại cho truyện webtoon: hai bàn tay cầm điện thoại
giữa khung, trên màn hình là tin nhắn, cuộc gọi, danh sách wifi, thông báo,
cảnh báo chữ đỏ, gọi video (thấy mặt người bên kia), nhiễu sóng, màn hình khoá.
Vẽ bằng code nên chữ trên màn hình là chữ thật AI viết, đổi được theo truyện.

screen(kind, data) — data tuỳ loại:
  chat:   {"name": "Con gái", "msgs": [{"me": false, "text": "..."}, ...], "app": "kakao"|"sms"}
  call:   {"name": "Con gái", "state": "incoming"|"calling"|"talking", "time": "00:42"}
  wifi:   {"items": ["Free_WiFi", "KT_5G", ...], "pick": 0, "state": "connecting"|"connected"|""}
  notice: {"title": "Thông báo", "text": "...", "time": "04:52"}
  alert:  {"lines": ["...", "..."], "count": "04:59"}
  video:  {"who": "id nhân vật", "expr": "crying"} — người bên kia (vẽ bằng webtoon_art)
  noise | lock {"time": "04:52"} | app {"title": "...", "lines": [...]} | loading {"text": "..."}
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFont

from . import video

INK = (28, 26, 30, 255)


def font(size: int, bold: bool = False, lang: str = "vi") -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(video.find_font(bold, lang != "ko"), max(8, int(size)))
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def _wrap(d: ImageDraw.ImageDraw, text: str, f, maxw: float) -> list[str]:
    out, cur = [], ""
    for w in str(text or "").split():
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=f) <= maxw or not cur:
            cur = trial
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out or [""]


def screen(kind: str, data: dict, size: tuple[int, int], lang: str = "vi", t: float = 0.0,
           figures: dict | None = None) -> Image.Image:
    """Nội dung màn hình (dọc) kích thước size."""
    W, H = size
    u = W / 78.0                      # chữ to cho dễ đọc trên video
    img = Image.new("RGBA", size, (24, 26, 34, 255))
    d = ImageDraw.Draw(img)
    data = data or {}
    if kind == "chat":
        kakao = data.get("app", "kakao") == "kakao"
        bg = (186, 206, 224, 255) if kakao else (246, 246, 248, 255)
        d.rectangle([0, 0, W, H], fill=bg)
        d.rectangle([0, 0, W, 13 * u], fill=_shade(bg, 0.93))
        d.text((6 * u, 4 * u), data.get("name", ""), font=font(5.5 * u, True, lang), fill=(30, 30, 34))
        y = 18 * u
        f = font(5 * u, False, lang)
        msgs = data.get("msgs") or []
        n_show = len(msgs) if not data.get("typing") else len(msgs)
        for m in msgs[-7:n_show]:
            me = bool(m.get("me"))
            lines = _wrap(d, m.get("text", ""), f, W * 0.62)
            bw = max(d.textlength(ln, font=f) for ln in lines) + 6 * u
            bh = len(lines) * 6.5 * u + 3.5 * u
            x0 = W - bw - 5 * u if me else 5 * u
            col = (250, 230, 0, 255) if (me and kakao) else ((80, 150, 250, 255) if me else (255, 255, 255, 255))
            d.rounded_rectangle([x0, y, x0 + bw, y + bh], radius=3 * u, fill=col, outline=INK, width=max(1, int(u * 0.4)))
            for k, ln in enumerate(lines):
                d.text((x0 + 3 * u, y + 2 * u + k * 6.5 * u), ln, font=f,
                       fill=(255, 255, 255) if (me and not kakao) else (24, 24, 28))
            if m.get("unread", me):
                d.text((x0 - 3 * u if me else x0 + bw + 1 * u, y + bh - 5 * u), "1", font=font(3.5 * u, True, lang),
                       fill=(240, 200, 0))
            y += bh + 4 * u
    elif kind == "call":
        d.rectangle([0, 0, W, H], fill=(36, 40, 52, 255))
        d.ellipse([W / 2 - 16 * u, 22 * u, W / 2 + 16 * u, 54 * u], fill=(120, 126, 140, 255))
        d.ellipse([W / 2 - 7 * u, 28 * u, W / 2 + 7 * u, 42 * u], fill=(200, 204, 212, 255))
        d.pieslice([W / 2 - 13 * u, 40 * u, W / 2 + 13 * u, 64 * u], 180, 360, fill=(200, 204, 212, 255))
        _center(d, W, 62 * u, data.get("name", ""), font(7 * u, True, lang), (255, 255, 255))
        st = data.get("state", "talking")
        sub = data.get("time") if st == "talking" else {"incoming": "...", "calling": "..."}.get(st, "")
        _center(d, W, 72 * u, sub or "", font(4.5 * u, False, lang), (200, 204, 214))
        by = H - 30 * u
        if st == "incoming":
            for cx, col in ((W * 0.28, (230, 70, 70)), (W * 0.72, (70, 200, 100))):
                d.ellipse([cx - 9 * u, by - 9 * u, cx + 9 * u, by + 9 * u], fill=col)
        else:
            d.ellipse([W / 2 - 9 * u, by - 9 * u, W / 2 + 9 * u, by + 9 * u], fill=(230, 70, 70))
    elif kind == "wifi":
        d.rectangle([0, 0, W, H], fill=(246, 246, 248, 255))
        d.text((6 * u, 5 * u), data.get("title", "Wi-Fi"), font=font(6 * u, True, lang), fill=(24, 24, 28))
        f = font(4.6 * u, False, lang)
        y = 18 * u
        pick = data.get("pick", -1)
        for i, it in enumerate((data.get("items") or [])[:10]):
            if i == pick:
                d.rectangle([2 * u, y - 1.5 * u, W - 2 * u, y + 7 * u], fill=(220, 234, 255, 255))
            d.text((6 * u, y), str(it), font=f, fill=(24, 24, 28))
            _wifi_icon(d, W - 12 * u, y + 3 * u, 3.2 * u, locked=i != pick)
            y += 9.5 * u
        state = data.get("state", "")
        if state == "connecting":
            cx, cy = W / 2, H - 22 * u
            a = (t * 360) % 360
            d.arc([cx - 6 * u, cy - 6 * u, cx + 6 * u, cy + 6 * u], a, a + 270, fill=(60, 120, 230), width=int(1.5 * u))
    elif kind == "notice":
        _lock_bg(d, W, H, u)
        _center(d, W, 16 * u, data.get("time", "04:52"), font(16 * u, True, lang), (255, 255, 255))
        y = 44 * u
        f = font(4.4 * u, False, lang)
        lines = _wrap(d, data.get("text", ""), f, W - 22 * u)
        bh = 11 * u + len(lines) * 5.6 * u
        d.rounded_rectangle([5 * u, y, W - 5 * u, y + bh], radius=4 * u, fill=(250, 250, 252, 235))
        d.text((10 * u, y + 3 * u), data.get("title", ""), font=font(4.6 * u, True, lang), fill=(24, 24, 28))
        for k, ln in enumerate(lines):
            d.text((10 * u, y + 9.5 * u + k * 5.6 * u), ln, font=f, fill=(60, 60, 66))
    elif kind == "alert":
        d.rectangle([0, 0, W, H], fill=(8, 8, 10, 255))
        y = 28 * u
        if data.get("count"):
            _center(d, W, 14 * u, data["count"], font(13 * u, True, lang), (230, 40, 40))
            y = 38 * u
        f = font(5.2 * u, True, lang)
        for line in data.get("lines") or []:
            for ln in _wrap(d, line, f, W - 12 * u):
                _center(d, W, y, ln, f, (230, 40, 40))
                y += 7.5 * u
            y += 3 * u
    elif kind == "noise":
        rnd = random.Random(int(t * 24))
        px = img.load()
        step = max(2, int(u * 1.2))
        for yy in range(0, H, step):
            for xx in range(0, W, step):
                v = rnd.randint(30, 230)
                d.rectangle([xx, yy, xx + step, yy + step], fill=(v, v, v, 255))
    elif kind == "lock":
        _lock_bg(d, W, H, u)
        _center(d, W, 18 * u, data.get("time", "04:52"), font(18 * u, True, lang), (255, 255, 255))
    elif kind == "loading":
        d.rectangle([0, 0, W, H], fill=(24, 26, 34, 255))
        cx, cy = W / 2, H * 0.45
        a = (t * 300) % 360
        d.arc([cx - 7 * u, cy - 7 * u, cx + 7 * u, cy + 7 * u], a, a + 260, fill=(220, 220, 230), width=int(1.6 * u))
        d.rounded_rectangle([18 * u, cy + 14 * u, W - 18 * u, cy + 17 * u], radius=u, fill=(60, 64, 80))
        k = (t * 0.4) % 1.0
        d.rounded_rectangle([18 * u, cy + 14 * u, 18 * u + (W - 36 * u) * k, cy + 17 * u], radius=u,
                            fill=(70, 140, 240))
        if data.get("text"):
            _center(d, W, cy + 22 * u, data["text"], font(4.4 * u, False, lang), (220, 220, 230))
    elif kind == "video":
        from . import webtoon_art as wa
        d.rectangle([0, 0, W, H], fill=(50, 56, 74, 255))
        fig = (figures or {}).get(data.get("who"))
        if fig is not None:
            s = W * 0.62
            hc = fig.b["head_c"]
            st = wa.State(expr=data.get("expr", "crying"), extras=tuple(data.get("extras") or ("bruise",)),
                          mouth=float(data.get("mouth", 0.0)), blink=float(data.get("blink", 0.0)),
                          shake=t if data.get("shake", True) else 0.0)
            out = wa.render(fig, st, size, (W / 2, H * 0.36 - hc[1] * s), s, max(2, W / 160))
            img.alpha_composite(out)
        d = ImageDraw.Draw(img)
        d.ellipse([4 * u, 4 * u, 8 * u, 8 * u], fill=(230, 40, 40))
        d.text((10 * u, 3.4 * u), "LIVE", font=font(4 * u, True, lang), fill=(255, 255, 255))
    else:  # app: tiêu đề + dòng chữ
        d.rectangle([0, 0, W, H], fill=(246, 246, 248, 255))
        d.rectangle([0, 0, W, 13 * u], fill=(60, 110, 220, 255))
        d.text((6 * u, 4 * u), data.get("title", ""), font=font(5.5 * u, True, lang), fill=(255, 255, 255))
        y = 19 * u
        f = font(4.6 * u, False, lang)
        for line in data.get("lines") or []:
            for ln in _wrap(d, line, f, W - 12 * u):
                d.text((6 * u, y), ln, font=f, fill=(30, 30, 34))
                y += 6.4 * u
            y += 2.5 * u
    # thanh trạng thái
    d.text((4 * u, 1.2 * u), data.get("clock", ""), font=font(3.2 * u, True, lang), fill=(240, 240, 240))
    return img


def _center(d, W, y, text, f, fill):
    w = d.textlength(str(text), font=f)
    d.text(((W - w) / 2, y), str(text), font=f, fill=fill)


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c[:3]) + (255,)


def _lock_bg(d, W, H, u):
    for k in range(12):
        y0 = H * k / 12
        c = (30 + k * 6, 44 + k * 5, 90 + k * 6, 255)
        d.rectangle([0, y0, W, y0 + H / 12 + 1], fill=c)
    d.ellipse([W * 0.2, H * 0.55, W * 1.3, H * 1.2], fill=(70, 90, 160, 255))


def _wifi_icon(d, cx, cy, r, locked=True):
    for k in range(3):
        rr = r * (k + 1) / 3
        d.arc([cx - rr, cy - rr, cx + rr, cy + rr], 225, 315, fill=(40, 40, 44), width=max(1, int(r / 5)))
    if locked:
        d.rectangle([cx + r * 0.7, cy - r * 0.1, cx + r * 1.3, cy + r * 0.5], fill=(40, 40, 44))


def held(screen_img: Image.Image, size: tuple[int, int], skin=(246, 214, 186), lw: float = 3.0,
         tilt: float = 0.0) -> Image.Image:
    """Cảnh chèn: hai bàn tay cầm điện thoại giữa khung, màn hình là screen_img."""
    W, H = size
    SS = 2
    layer = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ph = H * 1.25 * SS                          # điện thoại to tràn khung như video mẫu
    pw = ph * 0.5
    cx, top = W * SS / 2, H * 0.05 * SS
    L = int(lw * SS)
    body = [cx - pw / 2, top, cx + pw / 2, top + ph]
    d.rounded_rectangle(body, radius=pw * 0.1, fill=(200, 204, 212, 255), outline=INK, width=L)
    inner = [body[0] + pw * 0.05, body[1] + pw * 0.05, body[2] - pw * 0.05, body[3] - pw * 0.04]
    sw, sh = int(inner[2] - inner[0]), int(inner[3] - inner[1])
    scr = screen_img.resize((sw, sh), Image.LANCZOS)
    mask = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, sw, sh], radius=pw * 0.07, fill=255)
    layer.paste(scr, (int(inner[0]), int(inner[1])), mask)
    d.rounded_rectangle(inner, radius=pw * 0.07, outline=INK, width=L)
    # tai thỏ
    d.rounded_rectangle([cx - pw * 0.16, inner[1] - 1, cx + pw * 0.16, inner[1] + pw * 0.06],
                        radius=pw * 0.03, fill=(200, 204, 212, 255), outline=INK, width=L)
    # hai bàn tay ôm hai bên
    sk = tuple(skin[:3]) + (255,)
    for sgn in (-1, 1):
        ex = body[0] if sgn < 0 else body[2]
        fingers = []
        for k in range(3):                         # ngón tay ôm mép máy (vẽ sau lòng bàn tay)
            fy = top + ph * (0.5 + k * 0.075)
            x0 = ex - sgn * pw * 0.09
            fingers.append([min(x0, ex + sgn * pw * 0.04), fy, max(x0, ex + sgn * pw * 0.04), fy + ph * 0.062])
        from .webtoon_art import _crs
        palm = _crs([(ex + sgn * pw * 0.02, top + ph * 0.42), (ex + sgn * pw * 0.2, top + ph * 0.44),
                     (ex + sgn * pw * 0.36, top + ph * 0.55), (ex + sgn * pw * 0.46, H * SS + 20),
                     (ex - sgn * pw * 0.04, H * SS + 20), (ex - sgn * pw * 0.03, top + ph * 0.6)], 6)
        d.polygon(palm, fill=sk)
        d.line(palm + [palm[0]], fill=INK, width=L, joint="curve")
        for fb in fingers:
            d.rounded_rectangle(fb, radius=pw * 0.04, fill=sk, outline=INK, width=L)
        # ngón cái trên mép màn hình
        tx = ex - sgn * pw * 0.02
        d.rounded_rectangle([min(tx, tx - sgn * pw * 0.2), top + ph * 0.52, max(tx, tx - sgn * pw * 0.2),
                             top + ph * 0.6], radius=pw * 0.05, fill=sk, outline=INK, width=L)
    if tilt:
        layer = layer.rotate(tilt, resample=Image.BICUBIC, center=(W * SS / 2, H * SS * 0.6))
    return layer.reduce(SS)
