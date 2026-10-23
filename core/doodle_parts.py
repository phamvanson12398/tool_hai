# -*- coding: utf-8 -*-
"""Bộ phận vẽ thêm bằng AI cho nhân vật con nhộng và bối cảnh Truyện kể.

Truyện cần thứ tool chưa có (mũ miện vua, áo long bào, con trâu, cung điện...)
thì AI (Claude hoặc Antigravity trên máy chị) mô tả hình bằng các khối đơn giản
(chữ nhật, elip, đa giác, nét) theo hệ toạ độ chuẩn; tool vẽ lại theo đúng nét
vẽ tay (viền đen hơi run, màu dịu) và lưu vào thư viện để truyện sau dùng lại.

Bốn loại:
  head   — đội / đeo trên đầu (mũ miện, mũ quan, khăn, mặt nạ...).
           Toạ độ theo bán kính đầu R: tâm đầu (0,0), đỉnh đầu y=-1, cằm y=0.97,
           mắt ở y=0.08, x=±0.36; x sang phải, y xuống dưới.
  body   — hoa văn / đồ khoác trên thân (rồng trên long bào, giáp, áo choàng...).
           x: -1 mép trái thân .. 1 mép phải; y: 0 vai .. 1 đáy. Tự cắt theo thân.
  animal — con vật mới, quay sang PHẢI. x: -1..1 (đơn vị = chiều cao con vật),
           y: 0 đỉnh .. 1 mặt đất. Có "eyes" và "mouth" để tool vẽ biểu cảm.
  scene  — bối cảnh mới, khung 16:9: x 0..1, y 0..1; chân tường / mặt đất ở
           y≈0.83, chân nhân vật ở y=0.9, người lớn cao ≈0.47.
"""
from __future__ import annotations

import json
import re
import threading
import zlib
from pathlib import Path

from PIL import Image, ImageDraw

from . import config

KINDS = {
    "head": "Đồ đội / đeo trên đầu",
    "body": "Hoa văn, đồ khoác trên áo",
    "animal": "Con vật",
    "scene": "Bối cảnh",
}
MAX_SHAPES = {"head": 60, "body": 60, "animal": 90, "scene": 220}
_LOCK = threading.Lock()


def _file() -> Path:
    return config.LIBRARY / "doodle_parts.json"


_CACHE: dict = {"mtime": None, "data": {}}


def load() -> dict[str, dict]:
    """Thư viện bộ phận (đọc lại khi file đổi)."""
    try:
        mt = _file().stat().st_mtime
    except OSError:
        return {}
    if _CACHE["mtime"] != mt:
        try:
            d = json.loads(_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        _CACHE.update(mtime=mt, data=d if isinstance(d, dict) else {})
    return _CACHE["data"]


def save_part(part: dict) -> None:
    with _LOCK:
        d = dict(load())
        d[part["id"]] = part
        _file().parent.mkdir(parents=True, exist_ok=True)
        _file().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def delete_part(pid: str) -> bool:
    with _LOCK:
        d = dict(load())
        if pid not in d:
            return False
        del d[pid]
        _file().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        return True


def ids(kind: str) -> list[str]:
    return [k for k, v in load().items() if v.get("kind") == kind]


def get(pid: str | None) -> dict | None:
    if not pid:
        return None
    return load().get(pid)


def slug(v) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", str(v or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "_", t.replace("đ", "d").replace("Đ", "D")).strip("_").lower()
    return ("x_" + t)[:40] if t and t[0].isdigit() else (t[:40] or "bo_phan")


# ------------------------------------------------------------ kiểm tra

def _num(v, lo=-4.0, hi=4.0, default=0.0) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def _color(v):
    if v is None or v == "none":
        return None
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        return tuple(int(_num(x, 0, 255)) for x in v[:3])
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(v).strip())
    if not m:
        return None
    h = m.group(1)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def clean_shapes(shapes, limit: int) -> list[dict]:
    out = []
    for s in shapes or []:
        if not isinstance(s, dict):
            continue
        t = str(s.get("t") or s.get("type") or "").lower()
        c = {"t": t, "fill": _color(s.get("fill")), "outline": s.get("outline", True) is not False}
        if s.get("layer") in ("back", "front"):
            c["layer"] = s["layer"]
        if t in ("rect", "box"):
            c.update(t="rect", x=_num(s.get("x")), y=_num(s.get("y")),
                     w=_num(s.get("w"), 0, 8), h=_num(s.get("h"), 0, 8), r=_num(s.get("r"), 0, 1))
        elif t in ("ellipse", "ell", "circle"):
            rx = _num(s.get("rx", s.get("r")), 0, 8)
            c.update(t="ellipse", x=_num(s.get("x")), y=_num(s.get("y")), rx=rx,
                     ry=_num(s.get("ry", rx), 0, 8))
        elif t in ("poly", "polygon"):
            pts = [(_num(p[0]), _num(p[1])) for p in s.get("pts") or []
                   if isinstance(p, (list, tuple)) and len(p) >= 2]
            if len(pts) < 3:
                continue
            c.update(t="poly", pts=pts[:40])
        elif t in ("line", "polyline"):
            pts = [(_num(p[0]), _num(p[1])) for p in s.get("pts") or []
                   if isinstance(p, (list, tuple)) and len(p) >= 2]
            if len(pts) < 2:
                continue
            c.update(t="line", pts=pts[:40], w=_num(s.get("w"), 0.002, 0.5, 0.02))
            c["fill"] = c["fill"] or (40, 34, 38)
        elif t == "band":
            c.update(y0=_num(s.get("y0", s.get("y")), 0, 1), y1=_num(s.get("y1"), 0, 1, 1.0))
        else:
            continue
        out.append(c)
        if len(out) >= limit:
            break
    return out


def clean_part(d: dict, kind: str, name: str, desc: str) -> dict:
    if not isinstance(d, dict):
        raise RuntimeError("AI không trả về hình vẽ.")
    shapes = clean_shapes(d.get("shapes"), MAX_SHAPES[kind])
    if not shapes:
        raise RuntimeError("AI không trả về khối hình nào hợp lệ.")
    part = {"id": slug(d.get("id") or name), "kind": kind, "name": name, "desc": desc,
            "shapes": shapes}
    if kind == "animal":
        eyes = [(_num(e[0]), _num(e[1])) for e in d.get("eyes") or []
                if isinstance(e, (list, tuple)) and len(e) >= 2][:2]
        part["eyes"] = eyes or [(0.62, 0.32)]
        m = d.get("mouth") or [0.82, 0.5]
        part["mouth"] = (_num(m[0]), _num(m[1])) if isinstance(m, (list, tuple)) and len(m) >= 2 \
            else (0.82, 0.5)
        part["size"] = _num(d.get("size"), 0.08, 2.0, 0.45)
        part["eye_r"] = _num(d.get("eye_r"), 0.01, 0.2, 0.045)
    if kind == "scene":
        part["indoor"] = bool(d.get("indoor", True))
        part["sky"] = _color(d.get("sky")) or (230, 214, 176)
    return part


# ------------------------------------------------------------ vẽ

def draw_shapes(pen, shapes, tf, unit: float, layer: str | None = None) -> None:
    """Vẽ các khối lên bút của doodle (pen: doodle._Pen).
    tf(x, y) -> (px, py); unit = số px của 1 đơn vị (cho bề dày nét, bo góc)."""
    from .doodle import _ellipse_pts
    for s in shapes:
        if layer and s.get("layer", "front") != layer:
            continue
        fill, ol = s.get("fill"), s.get("outline", True)
        fill = tuple(fill) if fill else None
        t = s["t"]
        if t == "rect":
            x, y, w, h = s["x"], s["y"], s["w"], s["h"]
            r = min(s.get("r") or 0, w / 2, h / 2)
            if r > 0:
                pts = []
                for cx, cy, a0 in ((x + w - r, y + r, 270), (x + w - r, y + h - r, 0),
                                   (x + r, y + h - r, 90), (x + r, y + r, 180)):
                    pts += _ellipse_pts(cx, cy, r, r, a0, a0 + 90, 5)
            else:
                pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            pen.shape([tf(*p) for p in pts], fill, outline=ol)
        elif t == "ellipse":
            pts = _ellipse_pts(s["x"], s["y"], s["rx"], s["ry"], 0, 360, 36)
            pen.shape([tf(*p) for p in pts], fill, outline=ol)
        elif t == "poly":
            pen.shape([tf(*p) for p in s["pts"]], fill, outline=ol)
        elif t == "line":
            pen.line([tf(*p) for p in s["pts"]], width=max(1, int(s["w"] * unit)),
                     fill=fill or (40, 34, 38))


def render_scene(part: dict, size, night: bool = False) -> Image.Image:
    """Bối cảnh AI vẽ: khung thiết kế 16:9 đặt giữa khung thật (khung dọc thấy
    phần giữa, khung rộng hơn thì dải nền kéo ra hai bên)."""
    from .doodle import _Pen
    w, h = size
    sky = tuple(part.get("sky") or (230, 214, 176))
    img = Image.new("RGBA", (w, h), sky + (255,))
    wd = h * 16 / 9
    off = (w - wd) / 2
    pen = _Pen(img, h * 0.47, zlib.crc32(part["id"].encode()) % 1000)
    pen.lw = max(2, int(h * 0.006))
    pen.amp = h * 0.0015
    d = ImageDraw.Draw(img)
    for s in part["shapes"]:
        if s["t"] == "band":
            d.rectangle([0, s["y0"] * h, w, s["y1"] * h], fill=tuple(s.get("fill") or sky))
            if s.get("outline", True):
                d.line([(0, s["y0"] * h), (w, s["y0"] * h)], fill=(40, 34, 38), width=pen.lw)
        else:
            draw_shapes(pen, [s], lambda x, y: (off + x * wd, y * h), wd)
    img = img.convert("RGB")
    if night:
        img = Image.blend(img, Image.new("RGB", (w, h), (24, 28, 64)), 0.38)
    return img


# ------------------------------------------------------------ AI vẽ

_EXAMPLES = {
    "head": ('Mũ miện vua: {"shapes":[{"t":"poly","pts":[[-0.85,-0.55],[-0.95,-1.45],[-0.5,-1.05],'
             '[0,-1.6],[0.5,-1.05],[0.95,-1.45],[0.85,-0.55]],"fill":"#e6c35a"},'
             '{"t":"rect","x":-0.9,"y":-0.7,"w":1.8,"h":0.2,"fill":"#c99a3a"},'
             '{"t":"ellipse","x":0,"y":-0.6,"rx":0.09,"ry":0.07,"fill":"#c0453c"}]}'),
    "body": ('Hoa văn rồng vàng trên áo: {"shapes":[{"t":"line","pts":[[-0.6,0.2],[-0.2,0.35],'
             '[0.1,0.25],[0.45,0.45],[0.2,0.6]],"w":0.08,"fill":"#e6c35a"},'
             '{"t":"ellipse","x":-0.6,"y":0.2,"rx":0.12,"ry":0.09,"fill":"#e6c35a"},'
             '{"t":"rect","x":-1,"y":0.55,"w":2,"h":0.08,"fill":"#c99a3a","outline":false}]}'),
    "animal": ('Con gà mái (nhìn sang phải, cao 1): {"size":0.28,"eyes":[[0.38,0.25]],"eye_r":0.05,'
               '"mouth":[0.55,0.32],"shapes":[{"t":"ellipse","x":-0.1,"y":0.55,"rx":0.5,"ry":0.33,'
               '"fill":"#c98b52"},{"t":"poly","pts":[[-0.55,0.45],[-0.8,0.15],[-0.45,0.35]],'
               '"fill":"#8a5a34"},{"t":"ellipse","x":0.33,"y":0.3,"rx":0.22,"ry":0.22,"fill":"#c98b52"},'
               '{"t":"poly","pts":[[0.52,0.28],[0.7,0.33],[0.52,0.38]],"fill":"#e8b04a"},'
               '{"t":"ellipse","x":0.3,"y":0.07,"rx":0.09,"ry":0.07,"fill":"#d0483e"},'
               '{"t":"line","pts":[[-0.05,0.86],[-0.05,1.0]],"w":0.04,"fill":"#e8b04a"},'
               '{"t":"line","pts":[[0.12,0.86],[0.12,1.0]],"w":0.04,"fill":"#e8b04a"}]}'),
    "scene": ('Ngôi chùa làng (khung 16:9): {"indoor":false,"sky":"#bcdcef","shapes":['
              '{"t":"band","y0":0.83,"y1":1,"fill":"#cbb58a"},'
              '{"t":"rect","x":0.3,"y":0.45,"w":0.4,"h":0.38,"fill":"#d9c6a0"},'
              '{"t":"poly","pts":[[0.24,0.47],[0.76,0.47],[0.7,0.33],[0.3,0.33]],"fill":"#a8483c"},'
              '{"t":"poly","pts":[[0.28,0.34],[0.72,0.34],[0.66,0.22],[0.34,0.22]],"fill":"#a8483c"},'
              '{"t":"rect","x":0.46,"y":0.6,"w":0.08,"h":0.23,"fill":"#6b3b2a"},'
              '{"t":"ellipse","x":0.12,"y":0.45,"rx":0.11,"ry":0.16,"fill":"#6a9c5a"},'
              '{"t":"rect","x":0.115,"y":0.58,"w":0.02,"h":0.25,"fill":"#7a5a3a"}]}'),
}

_RULES = {
    "head": "Toạ độ theo bán kính đầu R: tâm đầu (0,0), đỉnh đầu y=-1, cằm y=0.97, mắt y=0.08 "
            "x=±0.36, tai x=±1. Mũ nằm trên đỉnh đầu (y từ khoảng -0.5 lên tới -1.8). "
            "Khối có \"layer\":\"back\" vẽ sau đầu (vd tóc dài, dải mũ phía sau).",
    "body": "Thân hình con nhộng không tay chân: x từ -1 (mép trái) tới 1 (mép phải), y từ 0 (vai) "
            "tới 1 (đáy). Chỉ vẽ phần thêm lên áo sẵn có (hoa văn, giáp, đai, khuy, áo choàng...); "
            "phần vẽ ra ngoài thân sẽ bị cắt.",
    "animal": "Con vật quay sang PHẢI, kiểu hoạt hình tròn trịa đơn giản, chân ngắn. Khung: chiều "
              "cao 1 đơn vị, y=0 đỉnh, y=1 mặt đất (chân chạm y=1), x từ -1 tới 1. KHÔNG vẽ mắt và "
              "miệng (tool tự vẽ để có biểu cảm) — chỉ cho vị trí \"eyes\" (1-2 điểm) và \"mouth\". "
              "\"size\": chiều cao so với người lớn (gà 0.25, chó 0.42, trâu 0.75, voi 1.3).",
    "scene": "Khung 16:9: x 0..1, y 0..1. Dùng \"band\" (dải ngang hết khung, y0..y1) cho trời, tường, "
             "đất. Chân tường / đường chân trời gần ở y≈0.83 (trong nhà) hoặc 0.55–0.8 (ngoài trời); "
             "nhân vật đứng ở y=0.9 cao ≈0.47 nên cửa cao ≈0.5, bàn ≈0.17. Để trống khoảng "
             "x 0.2–0.8 phía dưới cho nhân vật đứng (đồ vật thấp hoặc ở xa thì được). Vẽ đủ chi "
             "tiết thật (15–60 khối): đồ vật, cây cối, mái, cột, cửa sổ... đúng thời đại.",
}


def design(kind: str, name: str, desc: str = "", engine_task: str = "parts",
           pid: str | None = None) -> dict:
    """AI vẽ một bộ phận mới, kiểm tra, lưu vào thư viện và trả về."""
    from . import claude_cli
    if kind not in KINDS:
        raise RuntimeError("Loại bộ phận không hợp lệ.")
    prompt = claude_cli._load_prompt(
        "doodle_part", kind=kind, kind_vi=KINDS[kind], part_name=name, desc=desc or name,
        rules=_RULES[kind], example=_EXAMPLES[kind], limit=str(MAX_SHAPES[kind]))
    data = claude_cli._run_json(prompt, task=engine_task, timeout=300)
    part = clean_part(data, kind, name, desc)
    part["id"] = slug(pid or name)
    save_part(part)
    return part


def preview(part: dict, size=(360, 360)) -> Image.Image:
    from . import doodle
    if part["kind"] == "scene":
        return render_scene(part, (480, 270))
    kit = doodle.default_kit()
    if part["kind"] == "head":
        kit.update(hat=part["id"], hair="short")
    elif part["kind"] == "body":
        kit.update(extra=part["id"], top="robe", top_color="red")
    else:
        kit.update(species=part["id"])
    img, _f, _e = doodle.render(kit, "neutral", facing=0.3,
                                height=300 if part["kind"] != "animal" else int(300 / max(0.3, part.get("size", 0.5))))
    bg = Image.new("RGBA", img.size, (246, 238, 222, 255))
    bg.alpha_composite(img)
    return bg.convert("RGB")
