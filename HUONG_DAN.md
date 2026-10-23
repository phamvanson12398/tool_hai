# Hướng dẫn dùng tool tạo video hoạt hình hài thoại

Tool biến một tiêu đề hoặc một kịch bản thành video hài thoại 9:16 hoàn chỉnh
(30–90 giây), giọng và hình khớp nhau, bằng tiếng Hàn hoặc tiếng Anh.

---

## 1. Cài lần đầu

Bấm đúp vào **`cai_dat.bat`**. Script sẽ tự:

1. Kiểm tra card NVIDIA
2. Cài PyTorch bản CUDA (vài GB)
3. Cài các thư viện còn lại
4. Tải mô hình giọng nói OmniVoice + Whisper (vài GB)

Cần có sẵn trên máy:

| Thành phần | Dùng để | Ghi chú |
|---|---|---|
| Card NVIDIA | Chạy OmniVoice và Whisper | Máy chị đã có (GTX 1080 Ti) |
| Python 3.11 | Chạy tool | Tải ở python.org, nhớ tick "Add to PATH" |
| ffmpeg | Dựng video | Tải ở gyan.dev/ffmpeg/builds, thêm vào PATH |
| Claude Code CLI | Viết, rà soát kịch bản; chọn nhân vật, bối cảnh, giọng | `npm install -g @anthropic-ai/claude-code` rồi chạy `claude` để đăng nhập |
| Dung lượng trống | Mô hình OmniVoice và Whisper | Vài GB, tải về lần đầu |

> Mỗi lần gọi Claude đều trừ vào hạn mức tài khoản của chị.

---

## 2. Mở tool

Bấm đúp **`chay_tool.bat`**. Trình duyệt tự mở `http://127.0.0.1:8766`.
Đóng cửa sổ đen là tắt tool.

---

## 3. Ba màn hình

### Tập mới
Nhập tiêu đề hoặc kịch bản, chọn ngôn ngữ; tải nhân vật, bối cảnh, giọng mẫu;
xem trước dàn nhân vật và bối cảnh; bấm Rà soát rồi Xác nhận; xem và tải video.

### Thư viện
Nhân vật, bối cảnh và giọng đã lưu. Nghe thử giọng ngay ở đây.

### Cài đặt
Khoảng cách giữa các câu, kiểu phụ đề, nhạc nền và âm lượng, đường dẫn lệnh,
và mục **Xuất dự án CapCut** (xem mục 10).

---

## 4. Quy trình làm một tập

Chị sửa và rà soát bao nhiêu lần cũng được. **Trước khi bấm Xác nhận, tool không
tốn thời gian chạy OmniVoice** — nên cứ thoải mái chỉnh.

Phần nào cũng có hai cách: chị tự đưa vào, hoặc để AI làm. Một tập trộn được cả hai.

| Phần | Chị tự đưa vào | AI làm |
|---|---|---|
| Kịch bản | Tự viết vào ô kịch bản | Claude viết từ tiêu đề, chị sửa |
| Nhân vật | Tải ảnh lên, tên file = tên nhân vật | Claude vẽ bằng bộ ghép theo nội dung |
| Bối cảnh | Tải lên ở ô riêng, tên file tuỳ ý | Claude vẽ theo nội dung |
| Giọng | Tải giọng mẫu, tên file = tên nhân vật | AI mô tả giọng, OmniVoice tạo giọng mẫu |
| Rà soát | Bỏ qua, xác nhận luôn | Claude góp ý, chị chọn nhận hay bỏ từng ý |

Nhân vật hoặc giọng nào chị không tải lên thì tool tự chuyển sang cách AI làm.

---

## 5. Quy cách viết kịch bản

```
# tieu_de: 2026년 아기 이름
# ngon_ngu: ko
# nhan_vat: 지은=trai, 수아=phai

수아 (happy): 와, 아기 진짜 귀엽다! 이름 정했어?
지은 (proud): 우리 아기 이름은… "와이파이"야.
> 수아 (shocked, zoom, boing) 0.8
수아 (angry, zoom): 왜?!
```

- **Trong ngoặc**: biểu cảm, có `zoom` hay không, tên tiếng động.
- **Dòng bắt đầu bằng `>`**: nhịp phản ứng không lời, kèm số giây. Đây là
  khoảng lặng có chủ đích.
- `# ngon_ngu`: `ko` (tiếng Hàn) hoặc `en` (tiếng Anh). Kịch bản, giọng và phụ
  đề đều theo ngôn ngữ đó.
- `# nhan_vat`: `tên=trai`, `tên=phai`, `tên=giua`.
- **Dòng `## canh: <mô tả>`**: chuyển sang bối cảnh khác. Các câu phía sau
  thuộc cảnh đó (xem mục 6b).

### Biểu cảm dùng được
`neutral` `happy` `sad` `angry` `shocked` `surprised` `proud` `smug`
`confused` `scared` `disgusted` `thinking` `laughing` `crying`
`embarrassed` `annoyed` `worried` `tired` `suspicious` `love`
`determined` `shy` `bored`

### Tiếng động dùng được
`boing` `ding` `honk` `boom` `swoosh` `pop` `slap` `crash` `record_scratch`
`tada` `drumroll` `sad_trombone` `rimshot` `boo` `gasp` `laugh_track`
`applause` `whistle` `siren` `thud` `whoosh` `splash` `meow` `bark` `beep`

> Tiếng động chỉ phát khi có file tương ứng trong `data/sfx/` (ví dụ
> `data/sfx/boing.wav`). Chưa có file thì tool bỏ qua, không báo lỗi.

---

## 6. Đa dạng kiểu hài và bắt trend

Mỗi tập một kiểu hài khác nhau, không lặp mãi một khuôn.

**Hài theo từng thị trường.** Ngôn ngữ của tập quyết định khán giả: tập tiếng Hàn
viết cho người Hàn, tập tiếng Anh viết cho người Mỹ. Mỗi thị trường có thư viện
kiểu hài, nguồn trend và điều cần tránh riêng. Claude không dịch một truyện cười
từ thị trường này sang thị trường kia.

**Chống lặp khuôn.** Tool lưu lịch sử các tập đã làm (kiểu hài, cách mở đầu, cách
chốt). Khi viết, Claude tránh kiểu hài và cách chốt đã dùng trong 5 tập gần nhất,
trừ khi chị chỉ định.

- Ô **Kiểu hài**: chọn một kiểu cụ thể, hoặc để "Tự chọn".
- Nút **3 hướng khác**: Claude đưa 3 ý tưởng ngắn theo 3 kiểu hài khác nhau, chị
  chọn một rồi mới viết đầy đủ.
- Nút **Bắt trend**: Claude tìm trên web các format và chủ đề hài đang lên gần
  đây, tìm riêng theo thị trường của tập, đề xuất 3–5 ý tưởng kèm nguồn và ngày.
  Chỉ mượn ý tưởng và format; không chép nguyên câu thoại, nhân vật hay âm thanh
  có bản quyền. Trend thay đổi nhanh nên mỗi ý tưởng ghi rõ ngày tìm thấy.

---

## 6b. Nhiều bối cảnh trong một tập

Truyện diễn ra ở nhiều nơi thì thêm dòng `## canh:` vào kịch bản, mỗi lần đổi
chỗ một dòng:

```
# tieu_de: Hẹn hò lần đầu
# ngon_ngu: ko
# nhan_vat: 지은=trai, 수아=phai

## canh: phòng khách, buổi sáng
수아 (happy): 오늘 소개팅이야!
## canh: quán cà phê, buổi chiều
지은 (shocked, zoom): 어? 너야?
## canh: phòng khách, buổi sáng
수아 (crying): 망했어...
```

- Viết lại **đúng mô tả cũ** là quay về chỗ cũ, dùng lại cùng ảnh nền.
- Kịch bản không có dòng `## canh:` thì cả tập dùng một bối cảnh như trước.
- Claude tự thêm `## canh:` khi viết kịch bản nếu câu chuyện cần (tối đa 3 cảnh).
- Mục **8b. Bối cảnh từng cảnh** liệt kê các cảnh. Mỗi cảnh chị **tải ảnh lên**
  hoặc bấm **AI vẽ**; bấm vào ảnh nhỏ để xem trước cảnh đó. Cảnh chưa có ảnh
  riêng thì dùng bối cảnh chung của tập.
- AI vẽ theo các mẫu có sẵn: phòng khách, nhà bếp, phòng ngủ, văn phòng, lớp
  học, quán cà phê, cửa hàng, đường phố, công viên, bãi biển, nền sân khấu —
  có cả ban ngày và ban đêm, màu chọn theo không khí từng cảnh.
- Trong video, đổi cảnh có chuyển mờ ngắn (khoảng 0,35 giây).

---

## 7. Nhân vật

### Kiểu nhân vật AI vẽ
Ở **Cài đặt → Cử động nhân vật → Kiểu nhân vật AI vẽ**:

| Kiểu | Trông thế nào |
|---|---|
| **Tự chọn theo ngôn ngữ** (mặc định) | Tập tiếng Anh → người xám TikTok, tập tiếng Hàn → vẽ tay kiểu Hàn |
| **Người xám kiểu TikTok Mỹ** | Đầu tròn xám, tóc đen khối, mắt trắng to con ngươi liếc ngang, thân xám mảnh; nữ có váy xoè; mũ lưỡi trai xám đội ngược |
| **Vẽ tay kiểu Hàn** | Mắt lồi tròng nhỏ, mũi to, môi dày hồng, có tai, bụng tròn trong áo cổ V, quần đùi, chân trần có ngón; tóc ngắn nham nhở, ông bố hói vài sợi (`buzz`), ajumma tóc xoăn (`curly`) |
| **Webtoon Hàn** | Đầu rất to, người ngắn; mặt kiểu meme Hàn: `^^` vui, `ㅠㅠ` khóc có dòng nước mắt, `-_-` chán, mắt trắng dã + vạch tím khi sốc, dấu nổi gân 💢 khi giận, `///` khi ngượng |
| **Người que mặc áo** | Đầu tròn to như người que, thân vuông có quần áo, tay áo, quần, giày |
| **Người que nét đen** | Tay chân là nét kẻ, cà vạt màu áo |
| **Hoạt hình phẳng** | Kiểu cũ |

**Trang phục** (webtoon Hàn và người que mặc áo): áo phông, hoodie, đồng phục
học sinh (교복), vest công sở (직장인), tạp dề ajumma (앞치마), áo leo núi
ajeossi (등산복), áo phao dài (롱패딩), cardigan, váy, hanbok. Thêm phụ kiện
**lô cuốn tóc** và **mũ lưỡi trai nửa đầu** (선캡), kiểu tóc **bát úp**.

Với tập tiếng Hàn, Claude phối đồ theo các vai quen thuộc: học sinh, nhân viên
văn phòng / sếp, ajumma, ajeossi, bà cụ, giới trẻ MZ, người yêu.

Hai kiểu người xám và vẽ tay Hàn có **viền tự tạo quanh cả khối**, nên khuỷu
tay, đầu gối liền mạch khi cử động, tay chân thon dần như nét vẽ tay.

Đổi kiểu xong, bấm **Vẽ lại** ở nhân vật đã có để vẽ theo kiểu mới.

### Chị tải lên
Tên file = tên nhân vật trong kịch bản.

- **1 ảnh** (ví dụ `지은.png`): tool tự tách nền nếu cần. Nhân vật nhép miệng và
  nhún nhẹ khi nói. **Không đổi được biểu cảm.**
- **Bộ ảnh đầy đủ** theo quy ước `tên_biểu-cảm_mo.png` / `tên_biểu-cảm_dong.png`
  (ví dụ `지은_shocked_mo.png`), tải từng file hoặc nén zip: nhép miệng và đổi
  biểu cảm đầy đủ.

### Claude vẽ bằng bộ ghép
Bộ phận cùng phong cách: kiểu tóc, màu tóc, mặt, quần áo, phụ kiện, dáng người
lớn hoặc trẻ con, biểu cảm. Claude chọn phần ghép cho từng vai, tool ráp ra đủ
mọi biểu cảm × miệng mở/ngậm, luôn khớp nhau.

- Bố cục tự đổi: 2 người đứng trái và phải; 3 người đứng trái, giữa, phải và thu
  nhỏ một chút.
- Nhân vật ưng ý bấm **Lưu vào thư viện** để dùng lại ở các tập sau.

---

## 8. Giọng đọc

- **Chị tải giọng mẫu**: tên file = tên nhân vật (ví dụ `지은.wav`), dài 5–15
  giây, giọng rõ, không nhạc nền. Whisper tự nghe và ghi lại lời của đoạn mẫu;
  chị sửa nếu sai.
- **AI mô tả giọng**: OmniVoice tạo câu nghe thử; chị ưng thì lưu làm giọng mẫu.
- Mọi câu đều nhân bản theo giọng mẫu, nên giọng nhất quán giữa các câu và các tập.
- Mỗi nhân vật có giọng mẫu riêng cho tiếng Hàn và tiếng Anh.

> **Mô tả giọng chỉ nhận một số cụm cố định** mà OmniVoice hiểu được:
> `female` `male` · `child` `teenager` `young adult` `middle-aged` `elderly` ·
> `very low pitch` `low pitch` `moderate pitch` `high pitch` `very high pitch` ·
> `whisper` · `korean accent` `american accent` `british accent` và vài accent khác.
> Gõ "vui tươi" hay "giọng ấm" thì OmniVoice không hiểu, tool sẽ bỏ qua cụm đó.
> Muốn giọng có cảm xúc riêng thì nên **tải giọng mẫu** thay vì dùng mô tả.

---

## 9. Dựng video

1. Tạo giọng từng câu, đo độ dài thật, cắt bỏ khoảng im ở đầu và cuối.
2. Xếp câu sau ngay sau câu trước, cách 0,1 giây; chỉ dừng lâu hơn ở nhịp `>`.
3. Miệng mở khi có tiếng, ngậm khi im (đo theo âm lượng giọng).
4. Đổi biểu cảm, zoom vào người nói ở câu có zoom, chèn tiếng động.
5. Tiêu đề cố định trên cùng; phụ đề vàng viền đen, từng cụm ngắn nhảy theo lời.

### Đầu ra
- Video **mp4 dọc 1080×1920**, đăng được luôn.
- Kèm **bộ file rời** để chỉnh trong CapCut: giọng từng câu, phụ đề `.srt`,
  ảnh nhân vật và bối cảnh.
- Hoặc **xuất thẳng thành dự án CapCut** để mở lên là có sẵn các track
  (xem mục 10).

---

## 10. Xuất dự án CapCut (thử nghiệm)

Sau khi dựng xong một tập, ở mục **Xác nhận & dựng** có thêm nút
**“Xuất dự án CapCut (thử nghiệm)”** — nằm ngay cạnh nút “Tải mp4”.
Bấm nút này tool tạo một **dự án CapCut mới** trong thư mục dự án của CapCut.
Mở CapCut lên là thấy ngay các track, đúng mốc thời gian:

| Track | Nội dung |
|---|---|
| Hình | `video_khong_tieng.mp4` — video đã tách tiếng |
| Giọng | mỗi nhân vật một track riêng, mỗi câu là một clip |
| Tiếng động | boing / whoosh… đặt đúng vị trí |
| Nhạc nền | có nếu tập có nhạc nền |
| Chữ | phụ đề từng câu, chị bật/tắt được |

mp4 và bộ file zip cũ **vẫn giữ nguyên** — tính năng này chỉ thêm vào,
không thay gì cả.

### Chuẩn bị một lần
Ở trang **Cài đặt**, mục **Xuất dự án CapCut (thử nghiệm)**:

1. **Thư mục dự án CapCut** — để trống là dùng mặc định
   `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`.
   Chỉ chỉnh khi CapCut của chị lưu ở chỗ khác.
2. **Chọn dự án CapCut mẫu** — đây là bước quan trọng:
   - Mở CapCut, tự tạo một dự án (nên có **1 video, 1 audio, 1 text** để tool
     học đúng định dạng; thiếu phần nào tool tự dùng khung mặc định), lưu lại.
   - Quay lại tool, chọn dự án đó trong ô này, bấm **Lưu cài đặt**.
   - Tool đọc dự án mẫu để khớp đúng **phiên bản CapCut** của máy chị.

### Lưu ý
- **Đóng CapCut trước khi bấm Xuất**, hoặc mở lại CapCut sau khi xuất, để
  dự án mới hiện ra trong danh sách.
- Tên dự án tự đặt theo ngày giờ; nếu trùng thì tool tự thêm số.
- Dự án nào chị tạo thật trong CapCut thì **không bao giờ bị sửa hay ghi đè** —
  tool chỉ đọc dự án mẫu và tạo dự án mới riêng.
- Lỗi (nếu có) ghi vào `data/logs/capcut_export.log` và hiện ngay trên giao
  diện bằng tiếng Việt.
- Nếu hiện thông báo *“Phiên bản CapCut này mã hoá file dự án nên chưa xuất
  được”* thì phiên bản CapCut của chị đang mã hoá file dự án; khi đó chị dùng
  mp4 và bộ file rời như bình thường.

> **CapCut cập nhật có thể làm tính năng này ngừng hoạt động.** Nếu bản mới
> của CapCut đổi cấu trúc file, chị báo lại để cập nhật tool.

### Ghi cử chỉ trong kịch bản (Bước D)

Trong ngoặc, sau biểu cảm, có thể ghi thêm **cử chỉ** và **hiệu ứng cả người**,
cách nhau bằng dấu phẩy, ví dụ:

```
수아 (shocked, omdau, boing): 뭐라고?!
> 수아 (deadpan, khoanhtay) 0.8
```

**Cử chỉ hợp lệ** (keyframe góc xương): `vaytay`, `chitay`, `omdau`, `khoanhtay`,
`giohaitay`, `nhunvai`, `voratay`, `gatdau`, `lacdau`, `dibo`, `vao_trai`,
`vao_phai`, `ra_trai`, `ra_phai`, `nhaylen`, `ngangua`, `ve_tu_the`.

**Hiệu ứng cả người** (áp cho toàn thân): `nhun`, `nhay`, `rung`, `nghieng`,
`quay`, `nga`. Nhân vật đứng yên vẫn có chuyển động thở rất nhẹ; người đang nói
có cử động tay nhỏ (seed cố định theo tên) để không bị đơ.

Validator báo lỗi tiếng Việt nếu sai tên cử chỉ. Claude biết danh sách cử chỉ khi
viết kịch bản (gửi kèm trong prompt).

### Công tắc "Bật cử động" (Cài đặt)

Trong màn **Cài đặt**, mục **Cử động nhân vật** có công tắc:

- **Tắt** (mặc định): dựng theo cách cũ — ảnh tĩnh, nhép miệng, nhún nhẹ.
- **Bật**: nhân vật vẽ bằng bộ ghép dùng cử chỉ theo kịch bản (vẫy tay, ôm đầu…),
  thở nhẹ và đổi mặt theo biểu cảm; nhân vật tải lên 1 ảnh cử động theo khung
  xương chị đã kéo ở tab Dựng xương.

Nếu phần cử động lỗi (thiếu rig.json, ảnh không đạt, lỗi render…) tool tự quay
về cách dựng cũ, ghi vào `data/logs/capcut_export.log` (hoặc log render) và tiếp
tục dựng video.

### Màn hình "Dựng khung xương"

Cho nhân vật tải lên 1 ảnh: hiện ảnh với các chấm khớp có tên, người dùng kéo
hoặc bấm để sửa **một lần** rồi lưu. Có nút xem thử vẫy tay và đi bộ ngay trên
màn hình đó. Ảnh không đạt (nửa người, tay khoanh) thì báo và chỉ dùng hiệu
ứng cả người.

---

## 11. Giới hạn của bản đầu

- Nhân vật chỉ đổi biểu cảm, nhép miệng, nhún nhẹ và zoom; chưa có cử động như
  đi lại hay vẫy tay.
- Nhân vật tải lên bằng 1 ảnh thì không đổi được biểu cảm.
- Chất lượng giọng tiếng Hàn của OmniVoice cần nghe thử trước khi làm nhiều tập.
- Bối cảnh do AI vẽ hiện là nền phẳng đơn giản (trời / sàn / khối trang trí),
  chưa phải tranh chi tiết.
- Xuất dự án CapCut là tính năng **thử nghiệm**: phụ thuộc cấu trúc file của
  đúng phiên bản CapCut, và CapCut cập nhật có thể làm nó ngừng hoạt động.

---

## 12. Thư mục

```
tool_hoat_hinh/
  cai_dat.bat        cài lần đầu
  chay_tool.bat      mở tool
  core/              lõi: kịch bản, giọng, bộ ghép nhân vật, dựng video,
                     capcut_export.py (xuất dự án CapCut)
  web/               giao diện và server
  data/
    library/         nhân vật, bối cảnh, giọng đã lưu
    sfx/             file tiếng động (chị tự thêm)
    logs/            log lỗi, gồm capcut_export.log
    history.json     lịch sử các tập, dùng để chống lặp khuôn
    settings.json    cài đặt
  projects/          mỗi tập một thư mục, có video và file rời
```
