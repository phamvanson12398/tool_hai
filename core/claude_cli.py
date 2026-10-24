# -*- coding: utf-8 -*-
"""Gọi Claude CLI / Antigravity CLI (headless) để viết kịch bản, rà soát, bắt trend,
chọn nhân vật, bối cảnh, giọng. Mỗi việc chọn được AI riêng (AI_TASKS).

Dùng `claude -p` (print mode) với --output-format json để lấy kết quả có cấu trúc.
Mọi lời gọi đều là subprocess, nên tool chạy được ngoài mạng tuần tự và an toàn.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

from . import config, pacing
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


# --------------------------------------------------- chọn AI cho từng việc

# Việc nào dùng AI nào (Cài đặt > Trợ lý AI). Mặc định: Claude cho các bước
# quyết định chất lượng hài, Antigravity (model Gemini) cho việc phụ để đỡ tốn
# hạn mức Claude.
AI_TASKS = {
    "write": ("Viết kịch bản (kể cả tự thêm/bớt cho đúng thời lượng)", "claude"),
    "review": ("Rà soát kịch bản", "claude"),
    "apply": ("Áp dụng góp ý vào kịch bản", "claude"),
    "ideas": ("3 hướng khác", "agy"),
    "trends": ("Bắt trend (cần tìm web — chỉ Claude làm được an toàn)", "claude"),
    "characters": ("Chọn nhân vật (bộ ghép)", "agy"),
    "background": ("Chọn bối cảnh", "agy"),
    "voices": ("Mô tả giọng", "agy"),
    "story": ("Truyện kể: viết lời kể, chia cảnh", "claude"),
    "parts": ("Vẽ thêm nhân vật, con vật, bối cảnh cho Truyện kể", "claude"),
    "photo": ("Tạo nhân vật giống ảnh (cần xem ảnh — chỉ Claude)", "claude"),
}
ENGINES = {"claude": "Claude", "agy": "Antigravity (Gemini)"}
# cài đặt cũ ghi "gemini" (Gemini CLI, Google đã ngừng cho tài khoản cá nhân)
_LEGACY = {"gemini": "agy"}


# Việc phải tìm trên web: Antigravity chạy ngầm không được phép dùng công cụ
# (nó tự từ chối, không trả lời gì) và không có cách an toàn chỉ cho phép tìm
# web, còn Claude CLI có WebSearch chỉ đọc — nên những việc này luôn dùng Claude.
CLAUDE_ONLY = {"trends", "photo"}


def engines_for_task(task: str) -> list[str]:
    """Các AI chọn được cho một việc."""
    return ["claude"] if task in CLAUDE_ONLY else list(ENGINES)


def engine_for(task: str) -> str:
    """AI được chọn cho một việc (theo Cài đặt, không có thì mặc định)."""
    if task in CLAUDE_ONLY:
        return "claude"
    chosen = (config.load_settings().get("ai_engines") or {}).get(task)
    chosen = _LEGACY.get(chosen, chosen)
    if chosen in ENGINES:
        return chosen
    return AI_TASKS.get(task, ("", "claude"))[1]


def _run(prompt: str, *, task: str = "write",
         allowed_tools: list[str] | None = None,
         append_system: str | None = None, timeout: int = TIMEOUT,
         other_first: bool = False) -> str:
    """Chạy AI đã chọn cho việc `task`; lỗi (chưa cài, hết hạn mức...) thì
    tự chuyển sang AI còn lại nếu Cài đặt cho phép."""
    from . import agy_cli

    first = engine_for(task)
    order = [first]
    if config.load_settings().get("ai_fallback", True) and task not in CLAUDE_ONLY:
        order += [e for e in ENGINES if e != first]
        if other_first:            # lần trước AI này trả sai định dạng: hỏi AI kia trước
            order.reverse()
    errors = []
    for eng in order:
        if not (eng == "agy" and agy_cli._AUTH_ERROR):     # bỏ qua thì không đếm
            _count(eng)
        try:
            if eng == "agy":
                return agy_cli.run(prompt, timeout=timeout)
            return _run_claude(prompt, allowed_tools=allowed_tools,
                               append_system=append_system, timeout=timeout)
        except RuntimeError as e:
            errors.append(f"{ENGINES[eng]}: {e}")
            _log_fallback(task, eng, e)
    raise RuntimeError("\n".join(errors))


def _log_fallback(task: str, eng: str, err: Exception) -> None:
    try:
        d = config.DATA / "logs"
        d.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        with open(d / "ai_calls.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [{task}] {ENGINES[eng]} lỗi: "
                    f"{str(err)[:300]}\n")
    except Exception:  # noqa: BLE001
        pass


# Gọi Claude cho gọn để đỡ tốn hạn mức: Claude Code mặc định gửi kèm mỗi lần
# gọi một bản hướng dẫn rất dài (lập trình, công cụ, MCP, skill...). Tool chỉ
# cần Claude trả chữ, nên thay bằng một câu ngắn, tắt hết công cụ (trừ việc tìm
# web), bỏ MCP và skill, không lưu phiên. Bản Claude CLI cũ không hiểu các
# tuỳ chọn này thì tự quay về cách gọi cũ.
LEAN_SYSTEM = ("Bạn là biên tập viên kịch bản video hài ngắn. Làm đúng yêu cầu trong "
               "tin nhắn, trả lời thẳng đúng định dạng được yêu cầu, không giải thích thêm.")
_LEAN_OK = True


def _claude_dir() -> str:
    # thư mục riêng: Claude không tự đọc CLAUDE.md và mã nguồn của tool
    d = config.DATA / "tmp" / "claude"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def _claude_cmd(allowed_tools: list[str] | None, append_system: str | None,
                lean: bool) -> list[str]:
    cmd = [_cli_path(), "-p", "--output-format", "text"]
    if lean:
        cmd += ["--system-prompt", LEAN_SYSTEM + ("\n" + append_system if append_system else ""),
                "--tools", ",".join(allowed_tools) if allowed_tools else "",
                "--strict-mcp-config", "--disable-slash-commands",
                "--no-session-persistence"]
    elif append_system:
        cmd += ["--append-system-prompt", append_system]
    if allowed_tools:
        cmd += ["--allowedTools", ",".join(allowed_tools)]
    return cmd


def _run_claude(prompt: str, *, allowed_tools: list[str] | None = None,
                append_system: str | None = None, timeout: int = TIMEOUT) -> str:
    """Chạy claude -p (prompt gửi qua stdin) và trả về phần text của kết quả."""
    global _LEAN_OK
    for lean in ((True, False) if _LEAN_OK else (False,)):
        cmd = _claude_cmd(allowed_tools, append_system, lean)
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=_claude_dir(),
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
        err = (proc.stderr or "").strip()
        if lean and proc.returncode != 0 and re.search(
                r"unknown option|unrecognized|invalid option|error: option", err, re.I):
            _LEAN_OK = False            # bản Claude CLI cũ: dùng cách gọi cũ từ giờ
            continue
        if proc.returncode != 0 and not out:
            raise RuntimeError(f"Claude CLI lỗi (mã {proc.returncode}): {err[:500]}")
        return out
    raise RuntimeError("Claude CLI không chạy được.")


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
    raise RuntimeError("AI không trả về JSON hợp lệ:\n" + text[:800])


# --- đếm số lần gọi Claude / Antigravity trong phiên làm việc ---

_CALLS = {"claude": 0, "agy": 0}
_CALL_COUNT_LOCK = threading.Lock()


def _count(engine: str) -> None:
    with _CALL_COUNT_LOCK:
        _CALLS[engine] = _CALLS.get(engine, 0) + 1


def call_count() -> int:
    """Số lần đã gọi Claude trong phiên hiện tại của server."""
    with _CALL_COUNT_LOCK:
        return _CALLS["claude"]


def call_counts() -> dict:
    """Số lần gọi từng AI trong phiên hiện tại: {"claude": n, "agy": m}."""
    with _CALL_COUNT_LOCK:
        return dict(_CALLS)


def reset_call_count() -> None:
    with _CALL_COUNT_LOCK:
        for k in _CALLS:
            _CALLS[k] = 0


def _run_json(prompt: str, *, task: str, timeout: int = TIMEOUT,
              allowed_tools: list[str] | None = None,
              retry_hint: str = "") -> object:
    """Gọi AI, bóc JSON. Nếu JSON sai thì thử lại đúng 1 lần rồi mới báo lỗi."""
    last_error = ""

    for attempt in range(2):
        try:
            out = _run(prompt, task=task, timeout=timeout,
                       allowed_tools=allowed_tools, other_first=attempt > 0)
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
        "AI không trả về JSON hợp lệ sau 2 lần thử. Lỗi cuối: " + last_error[:600]
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


def length_hint(duration: float | None, language: str = "ko") -> tuple[str, int]:
    """Câu dặn độ dài cho prompt + số cảnh tối đa, theo số giây đích.

    Đưa cho Claude lượng chữ cụ thể (tính theo tốc độ đọc thật của OmniVoice)
    vì Claude đoán "giây" theo cảm tính thường viết thiếu lời."""
    if not duration:
        lo, hi = config.TARGET_DURATION
        return (f"{lo}–{hi} giây khi đọc lên. Khoảng 12–30 câu thoại.", 3)
    b = pacing.length_budget(duration, language)
    d = b["seconds"]
    lo, hi = int(b["lines"] * 0.85), int(b["lines"] * 1.15) + 1
    scenes = 3 if d <= 90 else (4 if d <= 180 else 6)
    txt = (f"{d} giây khi đọc lên (chênh tối đa 8%). Giọng AI đọc nhanh, nên cần "
           f"khoảng {lo}–{hi} câu thoại và TỔNG CỘNG khoảng {b['amount']} "
           f"{b['unit']} trên tất cả câu thoại (đừng viết thiếu). Trộn câu ngắn "
           f"1–3 chữ với câu dài vừa; nhịp '>' chỉ 2–5 cái cho cả tập.")
    if d > 120:
        txt += (" Tập dài: chia thành vài đoạn có mở đầu, leo thang, cú lật giữa tập "
                "và cú lật cuối; mỗi đoạn có một tình huống buồn cười riêng.")
    return txt, scenes


def _fix_length(script: str, language: str, duration: float | None) -> str:
    """Kịch bản lệch đích quá 10% thì nhờ Claude thêm/bớt lời một lần."""
    if not duration:
        return script
    from .script_parser import estimate_duration, parse_script

    try:
        s = parse_script(script)
        est = estimate_duration(s)
    except Exception:  # noqa: BLE001
        return script
    target = float(duration)
    if not s.beats or abs(est - target) <= target * 0.10:
        return script
    b = pacing.length_budget(target, language)
    have = sum(pacing.count_amount(x.text, language) for x in s.beats if x.kind == "line")
    if est < target:
        how = (f"QUÁ NGẮN: ước tính {est:.0f} giây, cần {target:.0f} giây. Hiện có "
               f"{have} {b['unit']}, cần khoảng {b['amount']}. Hãy THÊM câu thoại "
               f"(thêm phản ứng, hỏi vặn, leo thang tình huống, một cú lật nhỏ giữa "
               f"chừng), giữ nguyên mở đầu và câu chốt.")
    else:
        how = (f"QUÁ DÀI: ước tính {est:.0f} giây, cần {target:.0f} giây. Hiện có "
               f"{have} {b['unit']}, cần khoảng {b['amount']}. Hãy BỚT các câu "
               f"thừa, giữ nguyên mở đầu, cú lật và câu chốt.")
    prompt = (f"Sửa độ dài kịch bản hài dưới đây. {how}\n"
              f"Giữ đúng quy cách ghi, tên nhân vật, ngôn ngữ, giọng nói chuyện "
              f"đời thường, các dòng `## canh:` và dòng dịch `//`.\n"
              f"CHỈ output kịch bản hoàn chỉnh, không giải thích, không code fence.\n\n"
              f"{script}")
    try:
        fixed = _run(prompt, task="write", timeout=TIMEOUT).strip()
    except RuntimeError:
        return script
    try:
        s2 = parse_script(fixed)
    except Exception:  # noqa: BLE001
        return script
    if not s2.beats or len(s2.errors) > len(s.errors):
        return script
    new_est = estimate_duration(s2)
    return fixed if abs(new_est - target) < abs(est - target) else script


def write_script(title: str, language: str, kind: str | None = None,
                 hints: str = "", *, cast: list[str] | None = None,
                 duration: float | None = None) -> str:
    """Claude viết kịch bản. Trả về nội dung kịch bản theo đúng quy cách.

    duration: độ dài tập mong muốn (giây); không có thì 30–90 giây."""
    lang_label = config.lang_info(language)["lang_label"]
    kind_name = ""
    if kind and kind in COMEDY_KINDS.get(language, {}):
        kind_name = COMEDY_KINDS[language][kind][0]

    translation_rule = (
        "- Mỗi dòng thoại có thể kèm dòng bản dịch tiếng Việt bắt đầu bằng `//` "
        "ngay sau dòng đó (để chị dễ đọc).")
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
    if language == "vi":
        cast_hint = ("Nhân vật có tên Việt tự nhiên, ngắn gọn (ví dụ Tuấn, Linh, "
                     "bà Tư, chú Ba), xưng hô đúng vai: anh/em, mẹ/con, tao/mày "
                     "giữa bạn thân.")
        sample = ("## canh: phòng khách, buổi sáng\n"
                  "Linh (happy, vaytay): Trời ơi, em bé dễ thương quá! Đặt tên chưa?\n"
                  "Tuấn (proud, khoanhtay): Tên con là... \"Wifi\".\n"
                  "> Linh (shocked, zoom, boing) 0.8\n"
                  "Linh (angry, chitay, rung): Hả?! Sao lại Wifi?!")
        translation_rule = "- Kịch bản đã là tiếng Việt: KHÔNG thêm dòng dịch `//`."

    cast_txt = ""
    if cast:
        cast_txt = (f"\nDàn nhân vật phải dùng đúng các tên sau: "
                    f"{', '.join(cast)}. Không thêm nhân vật mới.")

    length_block, max_scenes = length_hint(duration, language)
    prompt = _load_prompt(
        "write_script",
        length_block=length_block,
        max_scenes=str(max_scenes),
        comedy_block=_comedy_block(language),
        lang_label=lang_label,
        title=title,
        kind_name=kind_name or "tự chọn — phải khác kiểu của các tập gần đây",
        cast_txt=cast_txt,
        cast_hint=cast_hint,
        hints=hints or "(không có)",
        history_block=_history_block(language),
        language=language,
        gestures_block=gesture_catalog_text(compact=True),
        props_block=_props_catalog(),
        cast_header={"ko": "지은=trai, 수아=phai", "vi": "Tuấn=trai, Linh=phai"}.get(
            language, "Mike=left, Sarah=right"),
        sample=sample,
        translation_rule=translation_rule,
    )

    out = _run(prompt, task="write", timeout=TIMEOUT).strip()
    return _fix_length(out, language, duration)


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
        lang_label=config.lang_info(language)["lang_label"],
        kind_lines=kind_lines,
        history_block=_history_block(language),
    )
    data = _run_json(prompt, task="ideas", timeout=180)
    if isinstance(data, dict):
        data = data.get("ideas", [])
    if not isinstance(data, list):
        raise RuntimeError("Claude không trả về danh sách 3 ý tưởng.")
    return data[:3]


# ------------------------------------------------------------------ rà soát

def review_script(script: str, language: str,
                  duration: float | None = None) -> list[dict]:
    """Claude rà soát kịch bản, trả về danh sách góp ý (không tự sửa).

    duration: thời lượng đích của tập (giây), để không góp ý cắt ngắn sai."""
    m = MARKETS.get(language, MARKETS["en"])
    if duration:
        length_rule = (f"thời lượng đích là {int(duration)} giây, tool tự đo độ dài "
                       f"khi đọc; KHÔNG góp ý cắt bớt cho ngắn hơn đích, chỉ góp ý "
                       f"đoạn nào lê thê hoặc thiếu nhịp.")
    else:
        lo, hi = config.TARGET_DURATION
        length_rule = f"độ dài dự kiến có nằm trong {lo}–{hi} giây không."
    prompt = _load_prompt(
        "review_script",
        comedy_block=_comedy_block(language),
        script=script,
        lang_name=config.lang_info(language)["lang_name"],
        market_label=m['label'],
        history_block=_history_block(language),
        length_rule=length_rule,
    )
    data = _run_json(prompt, task="review", timeout=240)
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
    return _run(prompt, task="apply", timeout=240).strip()


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

VN_CAST_HINT = """- Tập tiếng Việt: phối theo các vai quen thuộc của hài Việt để khán giả nhận ra ngay:
  · học sinh: outfit=school_uniform, body="child" nếu nhỏ tuổi
  · dân văn phòng / sếp: outfit=suit, thêm glasses cho sếp
  · mẹ, bà nội trợ: outfit=apron hoặc cardigan, hair_style=bun hoặc curly
  · bố, chú bác: outfit=tshirt hoặc hiking, hair_style=buzz
  · bà, ông: outfit=cardigan, hair_style=bun, accessory=glasses
  · giới trẻ Gen Z: outfit=hoodie, tóc sidepart/long
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
        market_hint={"ko": KOREAN_CAST_HINT, "vi": VN_CAST_HINT}.get(language, US_CAST_HINT),
    )
    data = _run_json(prompt, task="characters", timeout=180)
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


_SPEC_KEYS = ("body", "skin", "hair_style", "hair_color", "shirt", "accessory",
              "outfit", "pants")


def spec_from_photo(image: Path, name: str) -> dict:
    """Claude xem ảnh (công cụ Read) rồi chọn bộ ghép giống ảnh nhất.
    Trả về các giá trị hợp lệ + "note" (Claude tả ngoại hình)."""
    from .character_kit import options

    opt = options()
    catalog = "\n".join(
        f"- {k}: {', '.join(v)}" for k, v in opt.items() if k != "expressions"
    )
    prompt = _load_prompt("character_from_photo", image=str(image), char_name=name,
                          catalog=catalog)
    data = _run_json(prompt, task="photo", timeout=180, allowed_tools=["Read"])
    if not isinstance(data, dict):
        return {}
    out = {}
    for key in _SPEC_KEYS:
        val = str(data.get(key, "")).strip().lower()
        if val in opt.get(key, []):
            out[key] = val
    if data.get("note"):
        out["note"] = str(data["note"])[:200]
    return out


def style_from_photo(image: Path, rounds: int = 2, progress=None) -> dict:
    """Claude xem ảnh nhân vật mẫu: trả về tham số nét vẽ + bộ ghép + ghi chú.
    Sau lần đầu, tool vẽ thử nhân vật đặt cạnh ảnh mẫu cho Claude so và chỉnh lại
    (tối đa `rounds` lần, giống rồi thì thôi) để nét vẽ khớp ảnh mẫu."""
    from . import doodle, film_rig, style_preview
    opt = doodle.options()
    catalog = "\n".join(f"- {k}: {', '.join(v)}" for k, v in opt.items()
                        if k not in ("expressions", "extra"))
    data = _run_json(_load_prompt("char_style_from_photo", image=str(image), catalog=catalog),
                     task="photo", timeout=240, allowed_tools=["Read"])
    if not isinstance(data, dict):
        return {}

    def clean(d, base=None):
        base = base or {}
        sty = d.get("style") if isinstance(d.get("style"), dict) else base.get("style") or {}
        kit = d.get("kit") if isinstance(d.get("kit"), dict) else base.get("kit") or {}
        return {"style": film_rig.clean_style(sty), "kit": doodle.clean_kit(kit),
                "note": str(d.get("note") or base.get("note") or "")[:300]}
    cur = clean(data)
    for k in range(rounds):
        if progress:
            progress(f"So nhân vật tool vẽ với ảnh mẫu, chỉnh lần {k + 1}")
        cmp = Path(_claude_dir()) / f"so_sanh_{os.getpid()}_{k}.png"
        try:
            style_preview.compare(image, cur["style"], cur["kit"]).save(cmp)
            got = _run_json(_load_prompt("char_style_refine", image=str(cmp), catalog=catalog,
                                         current=json.dumps({"style": cur["style"], "kit": {
                                             x: y for x, y in cur["kit"].items() if not x.startswith("_")}},
                                             ensure_ascii=False)),
                            task="photo", timeout=240, allowed_tools=["Read"])
        except Exception as e:  # noqa: BLE001 — chỉnh không được thì giữ kết quả lần trước
            print(f"[claude_cli] Không chỉnh được kiểu nhân vật: {e}", file=sys.stderr)
            break
        finally:
            cmp.unlink(missing_ok=True)
        if not isinstance(got, dict):
            break
        try:
            score = float(got.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        if score >= 8.5:                                       # đã giống: giữ nguyên
            break
        cur = clean(got, cur)
    return cur


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
    data = _run_json(prompt, task="background", timeout=150)
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
        accent_hint={"ko": 'Nếu là tập tiếng Hàn, thêm "korean accent" khi phù hợp.',
                     "vi": "Tập tiếng Việt: KHÔNG dùng cụm accent nào."}.get(language, ""),
        example='{{"{first}":"female, young adult, high pitch"}}'.replace(
            "{first}", names[0] if names else "A"
        ),
    )
    data = _run_json(prompt, task="voices", timeout=150)
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
    # chỉ cho tìm web (không mở từng trang) — mỗi trang mở ra là thêm rất nhiều
    # chữ phải gửi lại ở các lượt sau, tốn hạn mức nhất
    data = _run_json(prompt, task="trends", timeout=300, allowed_tools=["WebSearch"])
    if isinstance(data, dict):
        data = data.get("ideas", data.get("trends", []))
    if not isinstance(data, list):
        return []
    return data[:5]
