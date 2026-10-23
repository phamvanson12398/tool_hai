# -*- coding: utf-8 -*-
"""Gọi Claude CLI (headless) để viết kịch bản, rà soát, bắt trend, vẽ mô tả.

Dùng `claude -p` (print mode) với --output-format json để lấy kết quả có cấu trúc.
Mọi lời gọi đều là subprocess, nên tool chạy được ngoài mạng tuần tự và an toàn.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from . import config
from .comedy_lib import COMEDY_KINDS, MARKETS
from .gestures import gesture_catalog_text  # noqa: E402

CLI = os.environ.get("CLAUDE_BIN", "claude")
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Timeout cho từng lời gọi (giây)
TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "300"))


def _cli_path() -> str:
    """Đường dẫn lệnh claude: ưu tiên cài đặt trong Cài đặt, rồi biến môi
    trường CLAUDE_BIN, cuối cùng mặc định "claude"."""
    try:
        s = config.load_settings().get("claude_bin")
        if s and str(s).strip():
            return str(s).strip()
    except Exception:
        pass
    return os.environ.get("CLAUDE_BIN", "claude") or "claude"


def _load_prompt(name: str, **kwargs) -> str:
    """Nạp prompt từ file .txt trong thư mục prompts/ và thay {{tên}}."""
    p = PROMPTS_DIR / f"{name}.txt"
    if not p.exists():
        raise RuntimeError(
            f"Không tìm thấy file prompt '{p}'. Kiểm tra lại thư mục prompts/."
        )
    text = p.read_text(encoding="utf-8")
    for key, value in kwargs.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text.strip()


def _run(prompt: str, *, allowed_tools: list[str] | None = None,
         append_system: str | None = None, timeout: int = TIMEOUT) -> str:
    """Chạy claude -p và trả về phần text của kết quả."""
    cmd = [_cli_path(), "-p", prompt, "--output-format", "text"]
    if allowed_tools is not None:
        cmd += ["--allowedTools", ",".join(allowed_tools)]
    if append_system:
        cmd += ["--append-system-prompt", append_system]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "Không tìm thấy lệnh 'claude'. Chị cần cài Claude Code CLI "
            "và đăng nhập trước."
        ) from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Claude CLI chạy quá {timeout}s và bị dừng."
        ) from None

    out = (proc.stdout or "").strip()
    if proc.returncode != 0 and not out:
        err = (proc.stderr or "").strip()
        raise RuntimeError(f"Claude CLI lỗi (mã {proc.returncode}): {err[:500]}")
    return out


def _extract_json(text: str) -> object:
    """Claude đôi khi bọc JSON trong ```json ... ``` hoặc kèm chữ. Bóc ra."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip()
        if t.endswith("```"):
            t = t[:-3].strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # thử tìm khối JSON đầu tiên trong text
    for opener, closer in (("{", "}"), ("[", "]")):
        start = t.find(opener)
        if start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[start:i + 1])
                    except json.JSONDecodeError:
                        break
    raise RuntimeError("Claude không trả về JSON hợp lệ:\n" + text[:800])


# --- đếm số lần gọi Claude trong phiên làm việc ---

_CALL_COUNT = 0
_CALL_COUNT_LOCK = threading.Lock()


def call_count() -> int:
    """Số lần đã gọi Claude trong phiên hiện tại của server."""
    with _CALL_COUNT_LOCK:
        return _CALL_COUNT


def reset_call_count() -> None:
    with _CALL_COUNT_LOCK:
        global _CALL_COUNT
        _CALL_COUNT = 0


def _run_json(prompt: str, *, timeout: int = TIMEOUT,
              allowed_tools: list[str] | None = None,
              retry_hint: str = "") -> object:
    """Gọi Claude, bóc JSON. Nếu JSON sai thì thử lại đúng 1 lần rồi mới báo lỗi."""
    global _CALL_COUNT
    last_error = ""

    for attempt in range(2):
        with _CALL_COUNT_LOCK:
            _CALL_COUNT += 1
        try:
            out = _run(prompt, timeout=timeout, allowed_tools=allowed_tools)
        except RuntimeError as e:
            last_error = str(e)
            if attempt == 0:
                continue
            raise RuntimeError(last_error) from None
        try:
            return _extract_json(out)
        except RuntimeError as e:
            last_error = str(e)
            if attempt == 0:
                # thử lại: nhắc Claude trả JSON đúng
                prompt = (prompt + "\n\n" + (retry_hint or
                          "Lần trước bạn trả về không đúng định dạng JSON. "
                          "Trả lại CHỈ JSON hợp lệ, không giải thích, không code fence."))

    raise RuntimeError(
        "Claude không trả về JSON hợp lệ sau 2 lần thử. Lỗi cuối: " + last_error[:600]
    )



# --------------------------------------------------------------- lịch sử

def _recent_history(n: int = config.RECENT_HISTORY) -> list[dict]:
    """Lấy n tập gần nhất để tránh lặp kiểu hài / cách chốt."""
    p = config.DATA / "history.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data[-n:] if isinstance(data, list) else []


def _history_block(lang: str) -> str:
    items = _recent_history()
    if not items:
        return "(chưa có tập nào trước đó — không có gì để tránh)"
    lines = []
    for h in items:
        if h.get("language") != lang:
            continue
        lines.append(
            f"- kiểu hài: {h.get('kind_name', h.get('kind'))} | "
            f"mở đầu: {h.get('opening')} | chốt: {h.get('ending')}"
        )
    if not lines:
        return "(chưa có tập nào trước đó của ngôn ngữ này)"
    return "\n".join(lines)


# ------------------------------------------------------------------ viết

def _comedy_block(lang: str) -> str:
    m = MARKETS.get(lang, MARKETS["en"])
    kinds = COMEDY_KINDS.get(lang, {})
    lines = [f"### Thư viện kiểu hài — khán giả {m['label']}"]
    for kid, (name, how) in kinds.items():
        lines.append(f"- `{kid}` — {name}: {how}")
    lines.append("### Điều cần tránh theo thị trường")
    for a in m["avoid"]:
        lines.append(f"- {a}")
    return "\n".join(lines)


def write_script(title: str, language: str, kind: str | None = None,
                 hints: str = "", *, cast: list[str] | None = None) -> str:
    """Claude viết kịch bản. Trả về nội dung kịch bản theo đúng quy cách."""
    lang_label = "tiếng Hàn" if language == "ko" else "tiếng Anh"
    kind_name = ""
    if kind and kind in COMEDY_KINDS.get(language, {}):
        kind_name = COMEDY_KINDS[language][kind][0]

    lang_name = "Korean" if language == "ko" else "English"
    if language == "ko":
        cast_hint = "Nhân vật nên có tên tiếng Hàn (ví dụ 지은, 수아)."
        sample = ("## canh: phòng khách, buổi sáng\n"
                  "수아 (happy, vaytay): 와, 아기 진짜 귀엽다! 이름 정했어?\n"
                  "지은 (proud, khoanhtay): 우리 아기 이름은… \"와이파이\"야.\n"
                  "> 수아 (shocked, zoom, boing) 0.8\n"
                  "수아 (angry, chitay, rung): 왜?!")
    else:
        cast_hint = "Characters should have natural English names."
        sample = ('## canh: phòng khách, buổi sáng\n'
                  'Sarah (happy, vaytay): Oh, the baby is so cute! Did we pick a name yet?\n'
                  'Mike (proud, khoanhtay): We named the baby... "WiFi".\n'
                  '> Sarah (shocked, zoom, boing) 0.8\n'
                  'Sarah (angry, chitay, rung): WHAT?!')

    cast_txt = ""
    if cast:
        cast_txt = (f"\nDàn nhân vật phải dùng đúng các tên sau: "
                    f"{', '.join(cast)}. Không thêm nhân vật mới.")

    prompt = _load_prompt(
        "write_script",
        comedy_block=_comedy_block(language),
        lang_label=lang_label,
        title=title,
        kind_name=kind_name or "tự chọn — phải khác kiểu của các tập gần đây",
        cast_txt=cast_txt,
        cast_hint=cast_hint,
        hints=hints or "(không có)",
        history_block=_history_block(language),
        language=language,
        gestures_block=gesture_catalog_text(),
        props_block=_props_catalog(),
        cast_header=("지은=trai, 수아=phai" if language == "ko"
                     else "Mike=left, Sarah=right"),
        sample=sample,
    )

    out = _run(prompt, timeout=TIMEOUT)
    return out.strip()


def three_ideas(title: str, language: str) -> list[dict]:
    """3 hướng ngắn theo 3 kiểu hài khác nhau."""
    kinds = list(COMEDY_KINDS.get(language, {}).items())
    picks = kinds[:3]
    kind_lines = "\n".join(
        f"- `{k}` ({v[0]}): {v[1]}" for k, v in picks
    )
    prompt = _load_prompt(
        "three_ideas",
        title=title,
        lang_label="tiếng Hàn" if language == "ko" else "tiếng Anh",
        kind_lines=kind_lines,
        history_block=_history_block(language),
    )
    data = _run_json(prompt, timeout=180)
    if isinstance(data, dict):
        data = data.get("ideas", [])
    if not isinstance(data, list):
        raise RuntimeError("Claude không trả về danh sách 3 ý tưởng.")
    return data[:3]


# ------------------------------------------------------------------ rà soát

def review_script(script: str, language: str) -> list[dict]:
    """Claude rà soát kịch bản, trả về danh sách góp ý (không tự sửa)."""
    m = MARKETS.get(language, MARKETS["en"])
    prompt = _load_prompt(
        "review_script",
        comedy_block=_comedy_block(language),
        script=script,
        lang_name="Hàn" if language == "ko" else "Anh",
        market_label=m['label'],
        history_block=_history_block(language),
    )
    data = _run_json(prompt, timeout=240)
    if isinstance(data, dict):
        data = data.get("suggestions", [])
    if not isinstance(data, list):
        return []
    # đánh số lại 1..n (Claude có thể tự ghi id dạng chữ, làm lệch khi áp dụng)
    out = [s for s in data if isinstance(s, dict)]
    for i, s in enumerate(out, 1):
        s["id"] = i
    return out


def apply_suggestions(script: str, suggestions: list[dict]) -> str:
    """Áp dụng các góp ý chị đã chọn (chỉ những cái được tick)."""
    if not suggestions:
        return script
    items = "\n".join(
        f"- [{s.get('category')}] trích: \"{s.get('quote','')}\" → đề xuất: {s.get('suggestion','')}"
        for s in suggestions
    )
    prompt = _load_prompt(
        "apply_suggestions",
        items=items,
        script=script,
    )
    return _run(prompt, timeout=240).strip()


# ------------------------------------------------------------------- trend

# Gợi ý phối đồ theo vai quen thuộc của hài Hàn (dùng khi tập tiếng Hàn)
KOREAN_CAST_HINT = """- Tập tiếng Hàn: phối theo các vai quen thuộc của hài Hàn để khán giả nhận ra ngay:
  · học sinh (학생): outfit=school_uniform, tóc bowl/short/ponytail, body="child" nếu nhỏ tuổi
  · nhân viên văn phòng (직장인 / 신입 / 부장님): outfit=suit, thêm glasses cho sếp
  · ajumma (아줌마): outfit=apron hoặc cardigan, hair_style=curly, accessory=curlers hoặc visor
  · ajeossi (아저씨): outfit=hiking, hair_style=buzz, accessory=sunglasses hoặc cap
  · bà cụ (할머니): outfit=hanbok hoặc cardigan, hair_style=bun, accessory=glasses
  · giới trẻ MZ: outfit=hoodie hoặc padding (áo phao dài), tóc sidepart/long
  · người yêu / bạn gái: outfit=dress hoặc cardigan
  Chọn vai đúng với nhân vật trong truyện, mỗi người một màu áo khác nhau."""

US_CAST_HINT = """- Phối outfit theo vai trong truyện (suit cho dân văn phòng, hoodie cho sinh viên,
  apron cho người nấu ăn, dress/cardigan cho buổi hẹn...), mỗi người một màu áo khác nhau."""


def _props_catalog() -> str:
    from .props import catalog_text
    return catalog_text()


def pick_character_specs(names: list[str], script: str,
                         language: str) -> dict[str, dict]:
    """Claude chọn phần ghép cho từng vai từ bộ phận có sẵn."""
    from .character_kit import options

    opt = options()
    catalog = "\n".join(
        f"- {k}: {', '.join(v)}" for k, v in opt.items() if k != "expressions"
    )
    first = names[0] if names else "A"
    example = json.dumps({first: {
        "body": "adult", "skin": "light", "hair_style": "short", "hair_color": "black",
        "shirt": "blue", "accessory": "none", "outfit": "suit", "pants": "navy",
    }}, ensure_ascii=False)
    prompt = _load_prompt(
        "pick_character_specs",
        catalog=catalog,
        script=script[:3000],
        names=", ".join(names),
        example=example,
        market_hint=(KOREAN_CAST_HINT if language == "ko" else US_CAST_HINT),
    )
    data = _run_json(prompt, timeout=180)
    if not isinstance(data, dict):
        return {}
    # chỉ giữ giá trị hợp lệ
    clean: dict[str, dict] = {}
    for name, spec in data.items():
        if not isinstance(spec, dict):
            continue
        c = {}
        for key in ("body", "skin", "hair_style", "hair_color", "shirt", "accessory",
                    "outfit", "pants"):
            val = str(spec.get(key, "")).strip().lower()
            if val in opt.get(key, []):
                c[key] = val
        clean[name] = c
    return clean


def design_background(script: str, language: str, desc: str = "") -> dict:
    """Claude chọn mẫu bối cảnh (phòng khách, bếp, đường phố...), ngày/đêm
    và màu chủ đạo cho một cảnh. desc: mô tả cảnh (dòng '## canh:')."""
    from .scene_art import KINDS, TIMES, kinds_catalog

    prompt = _load_prompt(
        "design_background",
        script=script[:2000],
        desc=desc or "(cả tập dùng một bối cảnh — chọn theo nội dung kịch bản)",
        kinds=kinds_catalog(),
    )
    data = _run_json(prompt, timeout=150)
    if not isinstance(data, dict):
        return {}

    def rgb(v):
        if isinstance(v, list) and len(v) >= 3:
            try:
                return [max(0, min(255, int(x))) for x in v[:3]]
            except (TypeError, ValueError):
                return None
        return None

    kind = str(data.get("kind", "")).strip().lower()
    time = str(data.get("time", "ngay")).strip().lower()
    return {
        "name": str(data.get("name", "boi_canh"))[:40],
        "desc": str(data.get("desc", ""))[:200],
        "kind": kind if kind in KINDS else "phong_khach",
        "time": time if time in TIMES else "ngay",
        # tương thích bản cũ (sky = màu tường/trời)
        "wall": rgb(data.get("wall")) or rgb(data.get("sky")),
        "floor": rgb(data.get("floor")),
        "accent": rgb(data.get("accent")),
    }


def describe_voices(names: list[str], script: str,
                    language: str) -> dict[str, str]:
    """Claude mô tả giọng cho từng vai, dùng đúng từ vựng OmniVoice chấp nhận."""
    from .voice import _VALID_INSTRUCT_ITEMS

    vocab = ", ".join(_VALID_INSTRUCT_ITEMS)
    prompt = _load_prompt(
        "describe_voices",
        vocab=vocab,
        script=script[:2500],
        names=", ".join(names),
        accent_hint=('Nếu là tập tiếng Hàn, thêm "korean accent" khi phù hợp.'
                     if language == "ko" else ""),
        example='{{"{first}":"female, young adult, high pitch"}}'.replace(
            "{first}", names[0] if names else "A"
        ),
    )
    data = _run_json(prompt, timeout=150)
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}


def find_trends(language: str, title: str = "") -> list[dict]:
    """Tìm format/chủ đề hài đang lên gần đây theo thị trường của tập."""
    m = MARKETS.get(language, MARKETS["en"])
    sources = ", ".join(m["trend_sources"])
    topic = f"Chủ đề tham khảo: {title}\n" if title else ""
    prompt = _load_prompt(
        "find_trends",
        market_label=m['label'],
        sources=sources,
        topic=topic,
    )
    data = _run_json(prompt, timeout=300, allowed_tools=["WebSearch", "WebFetch"])
    if isinstance(data, dict):
        data = data.get("ideas", data.get("trends", []))
    if not isinstance(data, list):
        return []
    return data[:5]
