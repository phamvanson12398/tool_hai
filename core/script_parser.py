# -*- coding: utf-8 -*-
"""Parse kịch bản theo quy cách:

    # tieu_de: 2026년 아기 이름
    # ngon_ngu: ko
    # nhan_vat: 지은=trai, 수아=phai

    수아 (happy): 와, 아기 진짜 귀엽다! 이름 정했어?
    지은 (proud): 우리 아기 이름은… "와이파이"야.
    > 수아 (shocked, zoom, boing) 0.8
    수아 (angry, zoom): 왜?!
    수아 (angry, zoom, 지은=happy, pause=0.5): 왜?!
    수아 (angry, zoom=지은): 왜?!
    // Ôi, sao lại thế nhỉ?

    ## canh: quán cà phê, buổi chiều
    지은 (shocked): 여기서 또 만나네!

Trong ngoặc: biểu cảm, có zoom hay không, tiếng động, thay đổi biểu cảm
người nghe (Tên=biểu_cảm), zoom vào người khác (zoom=Tên), nghỉ thêm
(pause=0.5).
Dòng bắt đầu bằng '>' là nhịp phản ứng không lời, kèm số giây.
Dòng bắt đầu bằng '//' là bản dịch tiếng Việt, chỉ hiện trong ô soạn.
Dòng '## canh: <mô tả>' chuyển sang bối cảnh mới; các câu phía sau thuộc
bối cảnh đó. Cùng mô tả = cùng bối cảnh (quay lại chỗ cũ dùng lại ảnh nền).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .comedy_lib import VALID_EXPRESSIONS, VALID_SFX
from .gestures import gesture_names, EFFECT_NAMES  # noqa: E402

HEADER_RE = re.compile(r"^\s*#\s*([A-Za-z_]+)\s*:\s*(.*)$")
# '## canh: phòng khách' — chuyển bối cảnh
SCENE_RE = re.compile(r"^\s*##\s*(?:canh|cảnh|boi_canh|bối cảnh|scene)\s*:\s*(.*)$",
                      re.IGNORECASE)
LINE_RE = re.compile(
    r"^\s*(?P<name>[^():]+?)\s*"
    r"(?:\((?P<mods>[^)]*)\))?\s*:\s*(?P<text>.*)$"
)
# '> 수아 (shocked, zoom, boing) 0.8'  — ngoặc và dấu ':' đều không bắt buộc
REACT_MODS_RE = re.compile(r"\(\s*([^)]*)\s*\)")
DUR_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:s|giây|giay)?\s*$")
# tuỳ chọn dạng key=value trong ngoặc: pause=0.5, 지은=happy, zoom=수아
KV_RE = re.compile(r"^([^=]+)=(.*)$")


@dataclass
class Beat:
    """Một nhịp trong kịch bản: câu nói hoặc nhịp phản ứng không lời."""

    kind: str                      # "line" | "react"
    speaker: str = ""
    expression: str = "neutral"
    zoom: bool = False
    sfx: str = ""
    text: str = ""                 # rỗng nếu là react
    duration: float = 0.0          # chỉ dùng cho react (giây)
    line_no: int = 0
    pause: float = 0.0             # nghỉ thêm sau câu này (giây)
    zoom_target: str = ""          # zoom vào người này (nếu khác người nói)
    other_expr: dict[str, str] = field(default_factory=dict)  # Tên -> biểu cảm
    translation: str = ""          # bản dịch tiếng Việt (dòng '//')
    gestures: list[str] = field(default_factory=list)   # cử chỉ: vaytay, omdau...
    effects: list[str] = field(default_factory=list)    # hiệu ứng cả người
    scene: int = 0                 # chỉ số bối cảnh (Script.scenes)
    props: dict[str, str] = field(default_factory=dict)  # tay -> đạo cụ ("" = bỏ)
    shot: str = ""                 # góc máy: toan | trung | can | sieucan | quavai

    def mods(self) -> list[str]:
        out = [self.expression]
        if self.zoom:
            out.append("zoom")
        if self.sfx:
            out.append(self.sfx)
        out.extend(self.gestures)
        out.extend(self.effects)
        for name, expr in self.other_expr.items():
            out.append(f"{name}={expr}")
        if self.zoom_target:
            out.append(f"zoom={self.zoom_target}")
        if self.pause:
            out.append(f"pause={self.pause:g}")
        for side, name in self.props.items():
            key = {"right": "cam", "left": "cam_trai", "both": "cam", "all": "cam"}[side]
            out.append(f"{key}={name or 'bo'}")
        if self.shot:
            out.append(f"goc={self.shot}")
        return out


@dataclass
class Script:
    title: str = ""
    language: str = "ko"           # "ko" | "en"
    cast: list[str] = field(default_factory=list)      # thứ tự xuất hiện
    sides: dict[str, str] = field(default_factory=dict)  # tên -> trai|phai|giua
    beats: list[Beat] = field(default_factory=list)
    # mô tả từng bối cảnh theo thứ tự xuất hiện ("" = bối cảnh chung của tập)
    scenes: list[str] = field(default_factory=list)
    # ai có mặt ở từng bối cảnh (None = mọi nhân vật), song song với scenes
    scene_cast: list[list[str] | None] = field(default_factory=list)
    raw: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def lines(self) -> list[Beat]:
        return [b for b in self.beats if b.kind == "line"]

    def reacts(self) -> list[Beat]:
        return [b for b in self.beats if b.kind == "react"]

    def scene_of(self, idx: int) -> str:
        """Mô tả bối cảnh theo chỉ số ("" nếu không có)."""
        return self.scenes[idx] if 0 <= idx < len(self.scenes) else ""

    def cast_of(self, idx: int) -> list[str] | None:
        """Nhân vật có mặt ở bối cảnh idx (None = tất cả)."""
        if 0 <= idx < len(self.scene_cast):
            return self.scene_cast[idx]
        return None

    def present(self, idx: int) -> list[str]:
        c = self.cast_of(idx)
        return [n for n in self.cast if c is None or n in c] or list(self.cast)

    def speakers_in_order(self) -> list[str]:
        seen: list[str] = []
        for b in self.beats:
            if b.speaker and b.speaker not in seen:
                seen.append(b.speaker)
        return seen


def _split_cast(spec: str) -> tuple[list[str], dict[str, str]]:
    names: list[str] = []
    sides: dict[str, str] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            name, side = part.split("=", 1)
            name, side = name.strip(), side.strip().lower()
        else:
            name, side = part, ""
        if name:
            names.append(name)
            if side:
                sides[name] = side
    return names, sides


# Góc máy (khung hình) cho từng câu
SHOT_ALIASES = {
    "toan": "toan", "toan_canh": "toan", "wide": "toan", "rong": "toan",
    "trung": "trung", "nua_nguoi": "trung", "medium": "trung", "vua": "trung",
    "can": "can", "can_mat": "can", "close": "can", "closeup": "can",
    "sieucan": "sieucan", "sieu_can": "sieucan", "extreme": "sieucan",
    "quavai": "quavai", "qua_vai": "quavai", "ots": "quavai", "over_shoulder": "quavai",
}

# Tên dễ nhớ / viết khác của cử chỉ
GESTURE_ALIASES = {
    "votay": "voratay", "vo_tay": "voratay", "clap": "voratay",
    "wave": "vaytay", "vay_tay": "vaytay", "point": "chitay", "chi_tay": "chitay",
    "om_dau": "omdau", "khoanh_tay": "khoanhtay", "gio_hai_tay": "giohaitay",
    "nhun_vai": "nhunvai", "shrug": "nhunvai", "gat_dau": "gatdau", "nod": "gatdau",
    "lac_dau": "lacdau", "di_bo": "dibo", "walk": "dibo", "nhay_len": "nhaylen",
    "jump": "nhaylen",
}


def _guess_mod(tok: str, valid_gestures: set[str]) -> tuple[str, str] | None:
    """Đoán tên đúng cho một tuỳ chọn viết sai. Trả về (loại, tên) hoặc None."""
    import difflib

    if tok in GESTURE_ALIASES and GESTURE_ALIASES[tok] in valid_gestures:
        return "gesture", GESTURE_ALIASES[tok]
    pools = [("gesture", sorted(valid_gestures)), ("expr", sorted(VALID_EXPRESSIONS)),
             ("effect", list(EFFECT_NAMES)), ("sfx", sorted(VALID_SFX))]
    flat = tok.replace("_", "").replace(" ", "").replace("-", "")
    for kind, names in pools:                       # khác nhau mỗi dấu gạch
        for n in names:
            if n.replace("_", "") == flat:
                return kind, n
    best = None
    for kind, names in pools:
        for n in difflib.get_close_matches(flat, names, n=1, cutoff=0.75):
            r = difflib.SequenceMatcher(None, flat, n).ratio()
            if best is None or r > best[0]:
                best = (r, kind, n)
    return (best[1], best[2]) if best else None


def _parse_mods(mods: str, beat: Beat, errors: list[str], warnings: list[str],
                line_no: int) -> None:
    """Parse tuỳ chọn trong ngoặc: biểu cảm, zoom, tiếng động, cử chỉ,
    hiệu ứng cả người, Tên=biểu cảm, zoom=Tên, pause=0.5.
    """
    valid_gestures = set(gesture_names())
    for raw in (mods or "").split(","):
        tok = raw.strip()
        if not tok:
            continue
        kv = KV_RE.match(tok)
        if kv:
            key = kv.group(1).strip().lower()
            val = kv.group(2).strip()
            if key in ("cam", "cam_phai", "cam_trai", "tay", "do", "prop"):
                from . import props as props_mod
                side = "left" if key == "cam_trai" else "right"
                if val.lower() in props_mod.DROP_WORDS:
                    # cam=bo: bỏ hết đồ trên tay; cam_trai=bo: chỉ tay trái
                    beat.props["left" if key == "cam_trai" else "all"] = ""
                    continue
                name = props_mod.resolve(val)
                if not name:
                    warnings.append(f"Dòng {line_no}: không có đạo cụ '{val}', bỏ qua. "
                                    f"Đạo cụ: {props_mod.catalog_text()}.")
                elif props_mod.two_handed(name):
                    beat.props["both"] = name
                else:
                    if name != val.lower():
                        warnings.append(f"Dòng {line_no}: tool hiểu đạo cụ '{val}' là '{name}'.")
                    beat.props[side] = name
                continue
            if key in ("goc", "khung", "shot", "camera"):
                shot = SHOT_ALIASES.get(val.lower().replace(" ", "_"))
                if shot:
                    beat.shot = shot
                else:
                    warnings.append(f"Dòng {line_no}: góc máy '{val}' không có (dùng: "
                                    f"toan, trung, can, sieucan, quavai), bỏ qua.")
                continue
            if key == "pause":
                try:
                    beat.pause = max(0.0, float(val.replace(",", ".")))
                except ValueError:
                    errors.append(f"Dòng {line_no}: pause=... phải là số (giây).")
            elif key == "zoom":
                beat.zoom_target = val
            elif val.lower() in VALID_EXPRESSIONS:
                # Tên=biểu_cảm: đổi biểu cảm người nghe khi câu bắt đầu
                beat.other_expr[key] = val.lower()
            else:
                warnings.append(
                    f"Dòng {line_no}: bỏ qua tuỳ chọn '{tok}' (không nhận ra hoặc biểu cảm sai)."
                )
            continue
        # không có dấu '=', xét từng loại
        tok_lower = tok.lower()
        if tok_lower == "zoom":
            beat.zoom = True
        elif tok_lower in VALID_EXPRESSIONS:
            beat.expression = tok_lower
        elif tok_lower in VALID_SFX:
            beat.sfx = tok_lower
        elif tok_lower in ("sfx", "sound"):
            continue
        elif tok_lower in valid_gestures:
            beat.gestures.append(tok_lower)
        elif tok_lower in EFFECT_NAMES:
            beat.effects.append(tok_lower)
        elif tok_lower in ("gesture", "cu_chi", "gestures"):
            continue
        else:
            # Viết sai (thường do AI gõ nhầm, vd 'vortay'): sửa về tên gần nhất
            # nếu đủ giống; không thì bỏ qua. Chỉ cảnh báo, không chặn dựng.
            fixed = _guess_mod(tok_lower, valid_gestures)
            if fixed:
                kind, name = fixed
                if kind == "expr":
                    beat.expression = name
                elif kind == "sfx":
                    beat.sfx = name
                elif kind == "gesture":
                    beat.gestures.append(name)
                else:
                    beat.effects.append(name)
                warnings.append(f"Dòng {line_no}: '{tok}' không có, tool hiểu là '{name}'.")
            else:
                warnings.append(
                    f"Dòng {line_no}: bỏ qua '{tok}' (không phải biểu cảm, tiếng động "
                    f"hay cử chỉ). Biểu cảm: {', '.join(sorted(VALID_EXPRESSIONS))}. "
                    f"Cử chỉ: {', '.join(sorted(valid_gestures))}. "
                    f"Hiệu ứng cả người: {', '.join(EFFECT_NAMES)}."
                )


def parse_script(text: str) -> Script:
    s = Script(raw=text)
    if not text or not text.strip():
        s.errors.append("Kịch bản trống.")
        return s

    lines = text.splitlines()
    in_body = False
    cur_scene: int | None = None   # chưa có '## canh' nào
    home: dict[str, int] = {}      # nhân vật -> nơi người đó được gắn ('| tên')

    def scene_index(speaker: str = "") -> int:
        nonlocal cur_scene
        if cur_scene is None:          # câu trước mọi '## canh': bối cảnh chung
            s.scenes.append("")
            s.scene_cast.append(None)
            cur_scene = 0
        # người nói không có mặt ở cảnh hiện tại nhưng đã được gắn vào nơi
        # khác (vd gọi điện thoại) -> tự cắt sang nơi của người đó
        here = s.scene_cast[cur_scene]
        if speaker and here is not None and speaker not in here and speaker in home:
            cur_scene = home[speaker]
        return cur_scene

    for i, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip()
        if not line.strip():
            continue

        # dòng bản dịch tiếng Việt: gán vào beat trước đó
        if line.lstrip().startswith("//"):
            translation = line.lstrip()[2:].strip()
            if s.beats:
                s.beats[-1].translation = translation
            else:
                s.warnings.append(
                    f"Dòng {i}: dòng '//' không có câu nào phía trước để gán bản dịch."
                )
            continue

        sm = SCENE_RE.match(line)
        if sm:
            desc = sm.group(1).strip()
            if not desc:
                s.errors.append(f"Dòng {i}: '## canh:' cần mô tả bối cảnh (vd '## canh: bếp').")
                continue
            # 'phòng khách | 민준, 수아': chỉ những người này có mặt
            who: list[str] | None = None
            if "|" in desc:
                desc, _, names = desc.partition("|")
                desc = desc.strip()
                who = [n.strip() for n in re.split(r"[,&+]", names) if n.strip()] or None
                if not desc:
                    s.errors.append(f"Dòng {i}: '## canh:' cần mô tả bối cảnh trước dấu '|'.")
                    continue
            # cùng mô tả (và cùng người) với cảnh đã có -> quay lại cảnh đó
            key = (desc.lower(), tuple(who) if who else None)
            keys = [(x.strip().lower(), tuple(c) if c else None)
                    for x, c in zip(s.scenes, s.scene_cast)]
            if key in keys:
                cur_scene = keys.index(key)
            else:
                s.scenes.append(desc)
                s.scene_cast.append(who)
                cur_scene = len(s.scenes) - 1
            for n in who or []:
                home[n] = cur_scene
            continue

        m = HEADER_RE.match(line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key == "tieu_de":
                s.title = val
            elif key == "ngon_ngu":
                lang = val.lower()
                if lang in ("ko", "kr", "kor", "korean", "hàn", "한국어"):
                    s.language = "ko"
                elif lang in ("en", "eng", "english", "anh", "tiếng anh"):
                    s.language = "en"
                else:
                    s.warnings.append(
                        f"Dòng {i}: ngôn ngữ '{val}' không rõ, mặc định tiếng Hàn."
                    )
            elif key == "nhan_vat":
                s.cast, s.sides = _split_cast(val)
            else:
                s.warnings.append(f"Dòng {i}: khóa '#{key}' không dùng, bỏ qua.")
            continue

        if line.lstrip().startswith("#"):
            s.warnings.append(f"Dòng {i}: dòng '#' không đọc được, bỏ qua.")
            continue

        in_body = True

        if line.lstrip().startswith(">"):
            beat = Beat(kind="react", line_no=i)
            rest = line.lstrip()[1:].strip()

            # tách phần trong ngoặc (biểu cảm, zoom, tiếng động)
            mm = REACT_MODS_RE.search(rest)
            if mm:
                _parse_mods(mm.group(1), beat, s.errors, s.warnings, i)
                before = rest[: mm.start()].strip()
                after = rest[mm.end():].strip()
            else:
                before, after = rest, ""

            # số giây: ở cuối dòng (sau ngoặc), nếu không thì ở cuối phần trước
            beat.speaker = before.rstrip(":").strip()
            dm = DUR_RE.search(after) or DUR_RE.search(before)
            if dm:
                try:
                    beat.duration = float(dm.group(1).replace(",", "."))
                except ValueError:
                    pass
                if not after and dm.start() > 0:
                    beat.speaker = before[: dm.start()].rstrip(":").strip()
            beat.scene = scene_index(beat.speaker)
            if not dm:
                s.errors.append(
                    f"Dòng {i}: nhịp phản ứng '>' phải kèm số giây "
                    f"(vd '> 수아 (shocked) 0.8')."
                )
            elif beat.duration <= 0:
                s.errors.append(f"Dòng {i}: số giây phải lớn hơn 0.")
            s.beats.append(beat)
            continue

        lm = LINE_RE.match(line)
        if lm:
            beat = Beat(kind="line", line_no=i)
            beat.speaker = lm.group("name").strip()
            beat.scene = scene_index(beat.speaker)
            _parse_mods(lm.group("mods") or "", beat, s.errors, s.warnings, i)
            beat.text = lm.group("text").strip()
            if not beat.text:
                s.errors.append(f"Dòng {i}: câu nói trống.")
            s.beats.append(beat)
            continue

        s.errors.append(f"Dòng {i}: không đọc được — {line[:60]}")

    # Kiểm tra nhân vật
    for b in s.beats:
        if b.speaker and b.speaker not in s.cast:
            s.warnings.append(
                f"Dòng {b.line_no}: nhân vật '{b.speaker}' chưa có trong # nhan_vat."
            )

    for idx, who in enumerate(s.scene_cast):
        for n in who or []:
            if s.cast and n not in s.cast:
                s.warnings.append(
                    f"Bối cảnh '{s.scenes[idx]}': '{n}' chưa có trong # nhan_vat."
                )
    for b in s.beats:
        who = s.cast_of(b.scene)
        if who is not None and b.speaker and b.speaker not in who:
            s.warnings.append(
                f"Dòng {b.line_no}: '{b.speaker}' nói nhưng không có mặt ở "
                f"bối cảnh '{s.scene_of(b.scene)}' (thêm vào sau dấu '|')."
            )

    if not s.cast and s.beats:
        s.errors.append("Thiếu dòng '# nhan_vat:' khai báo dàn nhân vật.")

    if not s.beats:
        s.errors.append("Không có câu thoại nào trong kịch bản.")

    # Gán vị trí mặc định nếu chưa khai
    if s.cast and not s.sides:
        for idx, name in enumerate(s.cast):
            if len(s.cast) == 1:
                s.sides[name] = "giua"
            elif len(s.cast) == 2:
                s.sides[name] = "trai" if idx == 0 else "phai"
            else:
                s.sides[name] = ["trai", "giua", "phai"][min(idx, 2)]

    return s


def serialize_script(s: Script) -> str:
    """Viết lại kịch bản thành đúng quy cách (dùng khi lưu)."""
    out = ["# tieu_de: " + s.title, "# ngon_ngu: " + s.language]
    cast = ", ".join(
        f"{n}={s.sides[n]}" if n in s.sides else n for n in s.cast
    )
    out.append("# nhan_vat: " + cast)
    out.append("")
    last_scene = 0 if (s.scenes and s.scenes[0] == "") else None
    for b in s.beats:
        if b.scene != last_scene and s.scene_of(b.scene):
            who = s.cast_of(b.scene)
            tail = (" | " + ", ".join(who)) if who else ""
            out.append(f"## canh: {s.scene_of(b.scene)}{tail}")
        last_scene = b.scene
        mods = ", ".join(b.mods())
        if b.kind == "react":
            out.append(f"> {b.speaker} ({mods}) {b.duration:g}")
        else:
            out.append(f"{b.speaker} ({mods}): {b.text}")
        if b.translation:
            out.append(f"// {b.translation}")
    return "\n".join(out) + "\n"


def estimate_duration(s: Script) -> float:
    """Ước lượng độ dài video (giây): giọng + nhịp phản ứng + khoảng cách."""
    from .config import get_settings

    st = get_settings()
    total = 0.0
    for b in s.beats:
        if b.kind == "react":
            total += b.duration
        else:
            # ~4.5 ký tự/giây cho tiếng Hàn, ~15 ký tự/giây cho tiếng Anh
            cps = 4.5 if s.language == "ko" else 15.0
            total += max(0.8, len(b.text) / cps)
        total += st.gap_between_lines
    return total
