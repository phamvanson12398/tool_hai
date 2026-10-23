# -*- coding: utf-8 -*-
"""Thư viện kiểu hài theo thị trường (Hàn / Mỹ) + điều cần tránh.

Bổ sung dần được. Mỗi tập chọn một thị trường; Claude chỉ dùng thư viện của
thị trường đó, không dịch truyện cười từ thị trường này sang thị trường kia.
"""

MARKETS = {
    "ko": {
        "label": "Hàn Quốc",
        "lang_id": "ko",
        "voice_lang": "Korean",
        "trend_sources": ["TikTok", "YouTube Shorts", "Reels", "cộng đồng mạng Hàn"],
        "avoid": [
            "chê ngoại hình",
            "phân biệt vùng miền",
            "chuyện chính trị",
            "đề tài nhạy cảm về lịch sử",
        ],
    },
    "en": {
        "label": "Mỹ",
        "lang_id": "en",
        "voice_lang": "English",
        "trend_sources": ["TikTok", "Reels", "Reddit", "X"],
        "avoid": [
            "khuôn mẫu về chủng tộc",
            "tôn giáo",
            "giới tính",
            "chính trị đảng phái",
        ],
    },
}

# Kiểu hài theo thị trường: id -> (tên hiển thị, cách gây cười)
COMEDY_KINDS = {
    "ko": {
        "ajae": ("아재개그 / 말장난 (chơi chữ kiểu chú)", "Chơi chữ trùng âm, càng 'nhạt' càng buồn cười."),
        "mz": ("MZ vs 꼰대 (Gen MZ vs người cổ hủ)", "Gen MZ và người lớn tuổi, sếp cũ nhìn cùng một chuyện khác nhau."),
        "gonggam": ("공감 개그 (hài đồng cảm)", "'~하는 사람 특징', tình huống ở trường, công ty, nhà mà ai cũng gặp."),
        "nunchi": ("눈치 / thứ bậc (đọc vị, trên dưới)", "Chuyện đọc vị, tiền bối – hậu bối, mẹ chồng – con dâu."),
        "drama": ("Nhại drama Hàn", "Chê các mô-típ quen: 재벌, 출생의 비밀, tát nước."),
        "banjeon": ("반전 (cú lật bất ngờ)", "Cú lật cuối bất ngờ."),
        "phongda": ("Phóng đại vô lý", "Đẩy một ý đời thường tới mức phi lý."),
        "meme": ("Meme và từ lóng mới", "Dùng đúng lúc các từ đang hot trên mạng Hàn."),
    },
    "en": {
        "sarcasm": ("Sarcasm / irony (mỉa mai)", "Nói ngược ý, mỉa mai nhẹ."),
        "deadpan": ("Deadpan (mặt tỉnh bơ)", "Nói chuyện vô lý với gương mặt tỉnh bơ."),
        "absurd": ("Absurd / surreal (phi lý, kỳ quặc)", "Logic kỳ quặc được coi là bình thường."),
        "pov": ("POV / 'Tell me without telling me' (góc nhìn, ẩn ý)", "Dùng format sketch đang phổ biến trên TikTok Mỹ."),
        "genz": ("Gen Z vs Millennial / Boomer (khác biệt thế hệ)", "Khác biệt thế hệ kiểu Mỹ."),
        "observational": ("Observational (soi chuyện đời thường)", "'Why do we…', soi những chuyện nhỏ hàng ngày."),
        "selfdep": ("Self-deprecating (tự giễu)", "Tự giễu bản thân."),
        "office": ("Office / parenting chaos (công sở, nuôi con)", "Châm biếm công sở, chuyện nuôi con."),
        "pun": ("Pun / wordplay (chơi chữ)", "Chơi chữ tiếng Anh."),
        "rule3": ("Rule of three / callback (lặp ba lần, nhắc lại)", "Lặp 3 lần leo thang, hoặc nhắc lại câu đầu ở câu chốt."),
    },
}

# Biểu cảm hợp lệ trong kịch bản (phần trong ngoặc)
VALID_EXPRESSIONS = {
    "happy", "sad", "angry", "shocked", "surprised", "proud", "neutral",
    "smug", "confused", "scared", "disgusted", "thinking", "laughing",
    "crying", "embarrassed", "annoyed", "worried", "tired", "suspicious",
    "love", "determined", "shy", "bored",
}

# Tiếng động hợp lệ
VALID_SFX = {
    "boing", "ding", "honk", "boom", "swoosh", "pop", "slap", "crash",
    "record_scratch", "tada", "drumroll", "sad_trombone", "rimshot",
    "boo", "gasp", "laugh_track", "applause", "whistle", "siren",
    "thud", "whoosh", "splash", "meow", "bark", "beep",
}

# Câu lệnh ghi đầu kịch bản
HEADER_KEYS = ("tieu_de", "ngon_ngu", "nhan_vat")


def market(code: str) -> dict:
    return MARKETS.get(code, MARKETS["en"])


def comedy_list(code: str) -> list[tuple[str, str, str]]:
    """Trả về [(id, tên, cách gây cười)] cho thị trường."""
    return [(k, v[0], v[1]) for k, v in COMEDY_KINDS.get(code, {}).items()]


def comedy_name(code: str, kind_id: str) -> str:
    m = COMEDY_KINDS.get(code, {})
    return m.get(kind_id, ("", ""))[0] if kind_id in m else ""
