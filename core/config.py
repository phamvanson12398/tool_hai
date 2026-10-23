# -*- coding: utf-8 -*-
"""Cấu hình dùng chung cho tool hoạt hình hài thoại."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROJECTS = ROOT / "projects"
LIBRARY = DATA / "library"
PREVIEWS = DATA / "previews"
LOGS = DATA / "logs"

for _d in (DATA, PROJECTS, LIBRARY, PREVIEWS, LOGS):
    _d.mkdir(parents=True, exist_ok=True)

# --- Khung video: 9:16 (TikTok/Shorts) mặc định, thêm 16:9 (YouTube), 1:1 ---
WIDTH = 1080
HEIGHT = 1920
FPS = 30
FORMATS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}
DEFAULT_FORMAT = "9:16"


def frame_size(fmt: str | None) -> tuple[int, int]:
    """Kích thước khung theo tỉ lệ ("9:16", "16:9", "1:1")."""
    return FORMATS.get(str(fmt or "").strip(), FORMATS[DEFAULT_FORMAT])


def stage_layout(w: int, h: int) -> dict:
    """Bố cục sân khấu theo khung: chân đứng ở floor*h, người cao
    height[0]*h (1-2 người) hoặc height[1]*h (3 người trở lên), vị trí
    ngang theo slots. Khung ngang để người to hơn và đứng gần nhau hơn
    (như phim hoạt hình YouTube); khung dọc như TikTok."""
    r = w / h
    if r >= 1.3:       # 16:9
        return {"floor": 0.90, "height": (0.68, 0.60),
                "slots": {1: [0.5], 2: [0.33, 0.67], 3: [0.24, 0.5, 0.76]}}
    if r >= 0.8:       # 1:1
        return {"floor": 0.88, "height": (0.62, 0.54),
                "slots": {1: [0.5], 2: [0.29, 0.71], 3: [0.2, 0.5, 0.8]}}
    return {"floor": 0.80, "height": (0.50, 0.42),
            "slots": {1: [0.5], 2: [0.27, 0.73], 3: [0.18, 0.5, 0.82]}}

# --- Mô hình ---
OMNIVOICE_MODEL = "k2-fsa/OmniVoice"
WHISPER_MODEL = "large-v3"

# --- Âm thanh ---
SAMPLE_RATE = 24000          # OmniVoice xuất 24 kHz
TARGET_SR = 48000            # chuẩn hoá cho ffmpeg
GAP_BETWEEN_LINES = 0.12     # giây, khoảng cách mặc định giữa các câu
MIN_LINE_SECONDS = 0.28      # không cho câu ngắn hơn thế này
TARGET_DURATION = (30, 90)   # khoảng độ dài tập (giây)

# --- Bố cục thời gian video ---
VIDEO_START_DELAY = 0.3      # giây, video bắt đầu sau đó
VIDEO_END_HOLD = 1.0         # giây, giữ khung cuối trước khi video kết thúc

# --- Nhịp phản ứng (dòng '>') mặc định ---
DEFAULT_REACT_SECONDS = 0.8

# --- Nhép miệng: ngưỡng RMS coi là "đang có tiếng" ---
MOUTH_RMS = 0.012

# --- Zoom vào người nói ở câu có zoom ---
ZOOM_SCALE = 1.35

# --- Ngôn ngữ ---
LANGUAGES = {
    "ko": {"label": "Tiếng Hàn", "market": "kr", "voice_lang": "Korean",
           "lang_label": "tiếng Hàn", "lang_name": "Hàn"},
    "en": {"label": "Tiếng Anh", "market": "us", "voice_lang": "English",
           "lang_label": "tiếng Anh", "lang_name": "Anh"},
    "vi": {"label": "Tiếng Việt", "market": "vn", "voice_lang": "Vietnamese",
           "lang_label": "tiếng Việt", "lang_name": "Việt"},
}


def lang_info(code: str) -> dict:
    """Thông tin một ngôn ngữ (mã lạ thì coi như tiếng Anh)."""
    return LANGUAGES.get(code, LANGUAGES["en"])

# --- Biểu cảm hỗ trợ ---
EXPRESSIONS = [
    "neutral", "happy", "sad", "angry", "shocked",
    "proud", "embarrassed", "smug", "worried", "tired",
]

# --- Tiếng động có sẵn (đặt tên file vào thư mục data/sfx) ---
SFX_DIR = DATA / "sfx"

# --- Nhạc nền / tiếng động ---
BGM_DB = -22.0                # âm lượng nền của nhạc nền
BGM_DUCK_DB = -8.0            # giảm thêm khi có giọng nói
BGM_FADE_OUT = 2.5            # giây, fade out ở cuối video
SFX_DB = -6.0                 # âm lượng tiếng động
SFX_AT_LINE_START = True      # tiếng động đặt ở đầu câu

# --- Màu / kiểu phụ đề mặc định ---
SUBTITLE_STYLES = {
    "yellow": {"fill": "#FFE500", "outline": "#000000", "size": 72},
    "white":  {"fill": "#FFFFFF", "outline": "#000000", "size": 72},
    "green":  {"fill": "#7CFC00", "outline": "#000000", "size": 72},
    "pink":   {"fill": "#FF6EC7", "outline": "#000000", "size": 72},
}

DEFAULT_SETTINGS = {
    "gap_between_lines": GAP_BETWEEN_LINES,
    "natural_pacing": True,     # nghỉ giữa câu như nói chuyện thật (core/pacing.py)
    "subtitle_style": "yellow",
    "subtitle_mode": "chunks",   # "chunks" = từng cụm ngắn, "full" = cả câu
    "bgm_volume": 0.0,          # 0 = không nhạc nền
    "bgm_file": None,
    "sfx_volume": 0.45,
    "title_text": "",
    "review_before_render": True,
    "claude_bin": "",           # rỗng = dùng mặc định "claude"
    "gemini_bin": "",           # rỗng = dùng mặc định "gemini"
    "gemini_model": "",         # rỗng = model mặc định của Gemini CLI
    # Trợ lý AI cho từng việc: {việc: "claude" | "gemini"}; thiếu việc nào thì
    # dùng mặc định trong core/claude_cli.AI_TASKS
    "ai_engines": {},
    "ai_fallback": True,        # AI đã chọn lỗi / chưa cài thì thử AI còn lại
    "ffmpeg_bin": "",           # rỗng = dùng mặc định "ffmpeg"
    "tts_engine": "",           # rỗng = dùng mặc định "omnivoice"
    # --- Cử động nhân vật (Bước D) ---
    "enable_rig": True,         # True = bật cử động bằng khung xương + cử chỉ + đạo cụ
    # kiểu nhân vật AI vẽ: auto (tiếng Hàn -> khand, tiếng Anh -> gray) | gray | khand | stick | box | kchibi | flat
    "char_style": "auto",
    "auto_camera": True,        # tự đổi góc máy (cận, qua vai, toàn cảnh) như phim
    "subtitle_position": "tren",  # tren (như video hoạt hình hài) | duoi
    # --- Xuất dự án CapCut (thử nghiệm) ---
    "capcut_drafts_root": "",   # rỗng = mặc định %LOCALAPPDATA%\\CapCut\\User Data\\Projects\\com.lveditor.draft
    "capcut_template_draft": "",  # tên dự án mẫu dùng để học cấu trúc
}


def capcut_drafts_root() -> Path:
    """Thư mục chứa các dự án CapCut trên máy."""
    s = load_settings()
    custom = str(s.get("capcut_drafts_root") or "").strip()
    if custom:
        p = Path(custom)
        if p.exists():
            return p
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    return Path.home() / "AppData" / "Local" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"


def capcut_template_draft() -> Path | None:
    """Thư mục dự án CapCut mẫu dùng để học cấu trúc, None nếu chưa chọn/chưa có."""
    s = load_settings()
    name = str(s.get("capcut_template_draft") or "").strip()
    if not name:
        return None
    p = capcut_drafts_root() / name
    if (p / "draft_content.json").exists():
        return p
    return None

# --- Thư viện kiểu hài theo thị trường ---
COMEDY_STYLES = {
    "kr": [
        "아재개그 / 말장난", "MZ vs 꼰대", "공감 개그", "눈치 / thứ bậc",
        "Nhại drama Hàn", "반전", "Phóng đại vô lý", "Meme và từ lóng mới",
    ],
    "us": [
        "Sarcasm / irony", "Deadpan", "Absurd / surreal",
        "POV / Tell me without telling me", "Gen Z vs Millennial / Boomer",
        "Observational", "Self-deprecating", "Office / parenting chaos",
        "Pun / wordplay", "Rule of three / callback",
    ],
}

AVOID_RULES = {
    "kr": [
        "Chê ngoại hình", "Phân biệt vùng miền", "Chính trị",
        "Đề tài nhạy cảm về lịch sử",
    ],
    "us": [
        "Khuôn mẫu về chủng tộc", "Tôn giáo", "Giới tính", "Chính trị đảng phái",
    ],
}

# Số tập gần nhất cần tránh lặp kiểu hài / cách chốt
RECENT_HISTORY = 5


class _Settings(dict):
    """Cho phép truy cập cả s["gap_between_lines"] và s.gap_between_lines."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e


def get_settings() -> _Settings:
    return _Settings(load_settings())


def load_settings() -> dict:
    p = DATA / "settings.json"
    if p.exists():
        try:
            return {**DEFAULT_SETTINGS, **json.loads(p.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(s: dict) -> None:
    (DATA / "settings.json").write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def project_dir(pid: str) -> Path:
    d = PROJECTS / pid
    for sub in ("assets", "audio", "frames", "out", "tmp"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


# --- Log dựng video (tiếng Việt) ---
RENDER_LOG = LOGS / "render.log"
_log_ready = False


def setup_logging() -> None:
    """Ghi log vào data/logs/render.log (tiếng Việt, không trùng handler)."""
    global _log_ready
    if _log_ready:
        return
    import logging
    LOGS.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not any(getattr(h, "_tool_hoat_hinh", False) for h in root.handlers):
        try:
            fh = logging.FileHandler(RENDER_LOG, encoding="utf-8")
        except OSError:
            return
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        fh._tool_hoat_hinh = True  # type: ignore[attr-defined]
        root.addHandler(fh)
        if root.level == logging.NOTSET or root.level > logging.INFO:
            root.setLevel(logging.INFO)
    _log_ready = True


def log_render(message: str, level: str = "info") -> None:
    """Ghi một dòng log tiếng Việt vào data/logs/render.log."""
    import logging
    setup_logging()
    getattr(logging.getLogger("tool_hoat_hinh.render"), level)(message)
