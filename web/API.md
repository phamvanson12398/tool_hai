# Hợp đồng API — Tool hoạt hình hài thoại

Tất cả endpoint trả JSON trừ khi ghi rõ. Server chạy ở `http://127.0.0.1:8766`.

## Lõi

### GET /api/meta
```json
{
  "languages": [{"code":"ko","label":"Tiếng Hàn"},{"code":"en","label":"Tiếng Anh"}],
  "expressions": ["neutral","happy","shocked", ...],
  "sfx": ["boing","ding", ...],
  "comedy_kinds": {"ko":[{"id":"ajae","name":"...","how":"..."}],"en":[...]},
  "markets": {"ko":{"label":"Hàn Quốc","trend_sources":[...]},"en":{...}},
  "subtitle_styles": ["yellow","white","green","pink"],
  "target_duration": [30,90]
}
```

### GET /api/settings
```json
{"gap_between_lines":0.1,"subtitle_style":"yellow","bgm_volume":0.0,
 "bgm_file":null,"sfx_volume":0.9,"title_text":""}
```

### POST /api/settings
Body: cùng shape với GET (partial ok). Trả settings đã lưu.

## Thư viện

### GET /api/library
```json
{
  "characters":[{"name":"지은","side":"left","mode":"single|set","image":"...","expressions":["happy"]}],
  "backgrounds":[{"id":"bg1","name":"phong khach","image":"..."}],
  "voices":[{"name":"지은","languages":{"ko":{"file":"...","duration":6.2,"text":"..."}}}]
}
```

### POST /api/library/character  (multipart)
- `files` — một hoặc nhiềi file ảnh
- `name` — tên nhân vật
- `side` — `left|center|right`
- Quy ước tên file: `지은.png` (đơn) hoặc `지은_shocked_mo.png` (bộ)
Trả: `{name, side, mode, expressions:[...], image, mouth_open, mouth_closed, warnings:[]}`

### POST /api/library/character/{name}/save
Lưu nhân vật vào thư viện để dùng lại. Trả `{ok:true}`

### POST /api/library/background (multipart)
- `files` — ảnh bối cảnh
Trả: `{id, name, image}`

### POST /api/library/voice (multipart)
- `file` — wav 5–15 giây
- `name` — tên nhân vật
- `language` — `ko|en`
- `text` — lời thoại đã sửa (tuỳ chọn; nếu trống thì Whisper tự nghe)
Trả: `{name, language, duration, text, file}`

### POST /api/library/voice/design
```json
{"name":"지은","language":"ko","instruct":"nữ, lớn tuổi, giọng trầm"}
```
OmniVoice tạo giọng mẫu. Trả: `{name, language, duration, file, resolved_instruct}`

### GET /api/library/voice/{name}/audio?lang=ko
Trả file wav (audio/mpeg hoặc audio/wav).

### GET /api/library/image/{id}
Trả ảnh (dùng chung cho nhân vật và bối cảnh).

## Dự án (mỗi tập = 1 project)

### POST /api/project
```json
{"title":"2026년 아기 이름","language":"ko","kind":"ajae"}
```
Trả: `{id, title, language, kind, state:"draft"}`

### GET /api/project/{id}
```json
{"id":"...","title":"...","language":"ko","kind":"ajae","script":"...",
 "parse":{"errors":[],"warnings":[],"beats":[...]},
 "assets":{"characters":[...],"background":{...},"voices":{...}},
 "estimate_duration":42.5,"state":"draft","history":[...]}
```

### POST /api/project/{id}/script
Body: `{"script":"<nội dung kịch bản>"}` — lưu nguyên văn và parse.

### POST /api/project/{id}/write
```json
{"title":"...","language":"ko","kind":"ajae","hints":"dài 40s, 2 nhân vật, bếp"}
```
Claude viết kịch bản. Trả: `{"script":"..."}` (đã đúng quy cách)

### POST /api/project/{id}/ideas
Body: `{"title":"...","language":"ko"}` → `{"ideas":[{"kind_id":"...","kind":"...","pitch":"..."}]}` (3 hướng)

### POST /api/project/{id}/trends
Body: `{"language":"ko"}` → `{"ideas":[{"title":"...","format":"...","why":"...","sources":["url"],"found_at":"2026-10-21"}]}`

### POST /api/project/{id}/review
Trả: `{"suggestions":[{"id":1,"category":"punchline|naturalness|length|character|policy|repeat","quote":"câu cụ thể","suggestion":"đề xuất sửa","severity":"low|medium|high"}]}`

### POST /api/project/{id}/apply
Body: `{"ids":[1,3]}` → áp dụng các góp ý đã chọn. Trả `{"script":"..."}`

### POST /api/project/{id}/assets (multipart)
- `characters` — nhiều file ảnh, tên file = tên nhân vật (hoặc `tên_biểu-cảm_mo.png`)
- `background` — 1 file bối cảnh
- `voices` — nhiều file wav, tên file = tên nhân vật

### POST /api/project/{id}/generate
Claude tạo phần còn thiếu: chọn bộ ghép nhân vật, vẽ bối cảnh, mô tả giọng.
Body: `{"characters":["지은","수아"],"background":"mô tả","voices":true}`
Trả: `{"characters":[...],"background":{...},"voices":{...}}`

### POST /api/project/{id}/render
Bắt đầu dựng video (job nền). Trả: `{"ok":true,"job":"..."}`

### GET /api/project/{id}/status
```json
{"state":"draft|review|rendering|done|error","progress":0.0,
 "message":"...","log":["..."],"video_ready":false}
```

### GET /api/project/{id}/video
Trả mp4 (video/mp4). 404 nếu chưa có.

### GET /api/project/{id}/pack
Trả zip: mp4 + file giọng từng câu + .srt + ảnh nhân vật + bối cảnh.

## Lịch sử

### GET /api/history
```json
[{"id":"...","title":"...","language":"ko","kind":"ajae","kind_name":"반전",
  "opening":"cách mở đầu","ending":"cách chốt","created_at":"..."}]
```

### POST /api/history
Lưu thông tin kiểu hài + cách mở đầu + cách chốt của tập vừa xong.

## Tài nguyên tĩnh
- `/` → giao diện
- `/static/*` → css/js
