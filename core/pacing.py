# -*- coding: utf-8 -*-
"""Nhịp nói tự nhiên và khớp thời lượng đích.

Hai việc:
  1. Khoảng nghỉ giữa các câu đổi theo ngữ cảnh như nói chuyện thật:
     bị ngắt lời thì gần như không nghỉ, câu hỏi thì người kia ngẫm một chút
     mới đáp, câu bỏ lửng "..." thì lặng lâu hơn, cùng người nói tiếp thì
     chỉ lấy hơi.
  2. Ước lượng độ dài theo tốc độ đọc thật của OmniVoice (đo từ các tập đã
     dựng) và, khi dựng, giãn nhẹ các khoảng nghỉ để video sát thời lượng
     chị đặt (không kéo chậm giọng).
"""
from __future__ import annotations

import re

# Tốc độ đọc đo từ các tập đã dựng bằng OmniVoice (sau khi cắt im lặng):
# mỗi câu tốn một phần cố định (lấy hơi, lề đầu/cuối) + thời gian theo số chữ
# + một chút cho mỗi chỗ ngắt trong câu (dấu phẩy, "...", hết câu giữa dòng).
# Tiếng Anh khớp đo đạc sai trung bình ~0,25 giây/câu; tiếng Hàn ít mẫu hơn.
EN_SEC_PER_WORD = 0.17
EN_SEC_PER_LINE = 0.65
KO_SEC_PER_SYLLABLE = 0.11
KO_SEC_PER_LINE = 0.45
SEC_PER_BREAK = 0.1

_HANGUL = re.compile(r"[가-힣]")
_WORD = re.compile(r"[A-Za-z0-9']+")

# Khoảng nghỉ thêm (giây) cộng vào khoảng cách cơ bản trong Cài đặt
INTERRUPT_GAP = 0.03        # câu trước kết thúc bằng "—" / "-": bị cắt lời
SAME_SPEAKER_EXTRA = 0.18   # cùng người nói tiếp: lấy hơi
TURN_EXTRA = 0.28           # đổi người nói bình thường
EXCLAIM_EXTRA = 0.22        # sau câu cảm thán: đáp nhanh
QUESTION_EXTRA = 0.42       # sau câu hỏi: người kia ngẫm rồi đáp
TRAIL_EXTRA = 0.6           # sau câu bỏ lửng "..." / "…"

# Giới hạn giãn thêm mỗi khoảng nghỉ khi khớp thời lượng đích
MAX_STRETCH_PER_GAP = 0.45
MAX_REACT_STRETCH = 0.5


def speech_seconds(text: str, language: str) -> float:
    """Ước lượng số giây OmniVoice đọc một câu."""
    t = text.strip()
    breaks = len(re.findall(r"[,，]|\.\.\.|…|[.?!](?=\s+\S)", t))
    if language == "ko":
        n = len(_HANGUL.findall(t))
        # chữ Latin lẫn trong câu tiếng Hàn: tính như từ tiếng Anh
        rest = len(_WORD.findall(_HANGUL.sub(" ", t)))
        sec = KO_SEC_PER_LINE + n * KO_SEC_PER_SYLLABLE + rest * EN_SEC_PER_WORD
    else:
        sec = EN_SEC_PER_LINE + len(_WORD.findall(t)) * EN_SEC_PER_WORD
    return max(0.4, sec + breaks * SEC_PER_BREAK)


def _ending(text: str) -> str:
    t = (text or "").strip().strip("\"'”’)」』")
    if not t:
        return ""
    if t.endswith(("—", "–", "-", "--")):
        return "cut"
    if t.endswith(("...", "…", "..", "~")):
        return "trail"
    if t.endswith("?") or t.endswith("?!") or t.endswith("!?"):
        return "question"
    if t.endswith("!"):
        return "exclaim"
    return "plain"


def natural_gap(prev_text: str, prev_speaker: str, next_speaker: str | None,
                base: float) -> float:
    """Khoảng nghỉ sau một câu, theo cách câu đó kết thúc và ai nói tiếp."""
    end = _ending(prev_text)
    if end == "cut":
        return INTERRUPT_GAP
    if next_speaker is None:
        return base
    if next_speaker == prev_speaker:
        extra = SAME_SPEAKER_EXTRA
        if end == "trail":
            extra = TRAIL_EXTRA
    else:
        extra = {"trail": TRAIL_EXTRA, "question": QUESTION_EXTRA,
                 "exclaim": EXCLAIM_EXTRA}.get(end, TURN_EXTRA)
    return base + extra


def next_speaker_of(beats, i: int) -> str | None:
    """Ai cất lời ở câu kế tiếp (bỏ qua nhịp phản ứng). None nếu hết."""
    for b in beats[i + 1:]:
        if b.kind == "line":
            return b.speaker
        return None   # có nhịp '>' chen giữa: nhịp đó đã là khoảng lặng
    return None


def fit_extra(target: float | None, total: float, gaps: list[float],
              reacts: list[float]) -> tuple[list[float], list[float]]:
    """Phần giãn thêm cho mỗi khoảng nghỉ / nhịp phản ứng để tổng sát đích.

    Chỉ giãn khi video ngắn hơn đích (không cắt lời, không kéo chậm giọng),
    giãn tỉ lệ với khoảng nghỉ sẵn có và có trần cho mỗi chỗ để không thành
    lặng thinh.
    """
    gx = [0.0] * len(gaps)
    rx = [0.0] * len(reacts)
    if not target or total >= target * 0.98:
        return gx, rx
    open_gaps = sum(1 for g in gaps if g > INTERRUPT_GAP)
    room = open_gaps * MAX_STRETCH_PER_GAP + len(reacts) * MAX_REACT_STRETCH
    if room <= 0:
        return gx, rx
    k = min(1.0, (target - total) / room)
    gx = [MAX_STRETCH_PER_GAP * k if g > INTERRUPT_GAP else 0.0 for g in gaps]
    rx = [MAX_REACT_STRETCH * k for _r in reacts]
    return gx, rx


def length_budget(duration: float, language: str) -> dict:
    """Số câu và lượng chữ cần cho một tập dài `duration` giây."""
    d = max(15, min(600, int(duration)))
    # ~76% thời lượng là tiếng nói, phần còn lại là nghỉ, nhịp phản ứng,
    # đầu/cuối video (đo từ các tập đã dựng với nhịp nghỉ tự nhiên)
    lines = max(5, round(d / 2.6))
    speech = d * 0.76
    if language == "ko":
        amount = round((speech - lines * KO_SEC_PER_LINE) / KO_SEC_PER_SYLLABLE)
        unit = "âm tiết Hangul (không tính dấu cách, dấu câu)"
    else:
        amount = round((speech - lines * EN_SEC_PER_LINE) / EN_SEC_PER_WORD)
        unit = "từ tiếng Anh"
    return {"seconds": d, "lines": lines, "amount": amount, "unit": unit}


def count_amount(text: str, language: str) -> int:
    if language == "ko":
        return len(_HANGUL.findall(text))
    return len(_WORD.findall(text))
