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

Trong ngoặc: biểu cảm, có zoom hay không, tiếng động, thay đổi biểu cảm
người nghe (Tên=biểu_cảm), zoom vào người khác (zoom=Tên), nghỉ thêm
(pause=0.5).
Dòng bắt đầu bằng '>' là nhịp phản ứng không lời, kèm số giây.
Dòng bắt đầu bằng '//' là bản dịch tiếng Việt, chỉ hiện trong ô soạn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .comedy_lib import VALID_EXPRESSIONS, VALID_SFX
from .gestures import gesture_names, EFFECT_NAMES  # noqa: E402

HEADER_RE = re.compile(r"^\s*#\s*([A-Za-z_]+)\s*:\s*(.*)$")
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
        return out


@dataclass
class Script:
    title: str = ""
    language: str = "ko"           # "ko" | "en"
    cast: list[str] = field(default_factory=list)      # thứ tự xuất hiện
    sides: dict[str, str] = field(default_factory=dict)  # tên -> trai|phai|giua
    beats: list[Beat] = field(default_factory=list)
    raw: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def lines(self) -> list[Beat]:
        return [b for b in self.beats if b.kind == "line"]

    def reacts(self) -> list[Beat]:
        return [b for b in self.beats if b.kind == "react"]

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
            # Tên biểu cảm / cử chỉ viết sai -> báo lỗi tiếng Việt kèm số dòng
            errors.append(
                f"Dòng {line_no}: không nhận ra '{tok}' (không phải biểu cảm, "
                f"tiếng động hay cử chỉ). "
                f"Biểu cảm hợp lệ: {', '.join(sorted(VALID_EXPRESSIONS))}. "
                f"Các cử chỉ hợp lệ: {', '.join(sorted(valid_gestures))}. "
                f"Hiệu ứng cả người: {', '.join(EFFECT_NAMES)}."
            )


def parse_script(text: str) -> Script:
    s = Script(raw=text)
    if not text or not text.strip():
        s.errors.append("Kịch bản trống.")
        return s

    lines = text.splitlines()
    in_body = False

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
    for b in s.beats:
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
