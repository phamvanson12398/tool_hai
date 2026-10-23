# -*- coding: utf-8 -*-
"""Thư viện kiểu hài theo thị trường (Hàn / Mỹ / Việt Nam) + điều cần tránh.

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
    "vi": {
        "label": "Việt Nam",
        "lang_id": "vi",
        "voice_lang": "Vietnamese",
        "trend_sources": ["TikTok", "Facebook Reels", "YouTube Shorts", "cộng đồng mạng Việt"],
        "avoid": [
            "chính trị, lãnh đạo, chủ quyền",
            "phân biệt vùng miền (Bắc – Trung – Nam), chê giọng địa phương",
            "chê ngoại hình, body shaming",
            "tôn giáo, tín ngưỡng, chuyện tâm linh nhạy cảm",
            "nói tục, chửi thề",
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
    "vi": {
        "choichu": ("Chơi chữ / nói lái", "Đồng âm, nói lái, hiểu sai nghĩa một từ; càng 'nhạt' càng buồn cười."),
        "giadinh": ("Chuyện gia đình Việt", "Mẹ so sánh với 'con nhà người ta', bố tiết kiệm điện, bà nội ép ăn, họ hàng hỏi 'bao giờ cưới'."),
        "tet": ("Tết và họ hàng", "Hỏi lương, hỏi người yêu, lì xì, dọn nhà, mâm cỗ, câu hỏi khó đỡ ngày Tết."),
        "genz": ("Gen Z vs phụ huynh", "Thế hệ trẻ và bố mẹ nhìn cùng một chuyện khác nhau: điện thoại, công việc, yêu đương."),
        "congso": ("Công sở, sếp và đồng nghiệp", "Họp hành, deadline, sếp nhắn lúc nửa đêm, đồng nghiệp 'ké' công."),
        "hocsinh": ("Học sinh, sinh viên", "Kiểm tra bài cũ, thi cử, cô giáo chủ nhiệm, ở trọ, cuối tháng hết tiền."),
        "dongcam": ("Hài đồng cảm đời thường", "Tình huống ai cũng gặp: kẹt xe, shipper gọi, đi chợ mặc cả, mất điện."),
        "banbe": ("Bạn thân 'lầy lội'", "Hai đứa bạn cà khịa nhau, bày trò, hứa rồi 'bùng kèo'."),
        "phongdai": ("Phóng đại vô lý", "Đẩy một chuyện nhỏ đời thường tới mức phi lý."),
        "lattay": ("Cú lật cuối", "Dẫn khán giả nghĩ một đằng, câu chốt lật một nẻo."),
        "trend": ("Bắt trend, câu nói hot", "Dùng đúng lúc câu nói, meme, từ lóng đang hot trên mạng Việt."),
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
