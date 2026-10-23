# Hướng dẫn dùng tool tạo video hoạt hình hài thoại

Tool biến một tiêu đề hoặc một kịch bản thành video hài thoại 9:16 hoàn chỉnh
(30–90 giây), giọng và hình khớp nhau, bằng tiếng Hàn, tiếng Anh hoặc tiếng Việt.

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
| Antigravity CLI `agy` (nên có) | Các việc phụ: bắt trend, 3 hướng, chọn nhân vật, bối cảnh, giọng — đỡ tốn hạn mức Claude | Mở **PowerShell**, chạy `irm https://antigravity.google/cli/install.ps1 \| iex`, mở cửa sổ lệnh mới, gõ `agy` một lần và đăng nhập tài khoản Google |
| Dung lượng trống | Mô hình OmniVoice và Whisper | Vài GB, tải về lần đầu |

> Mỗi lần gọi Claude đều trừ vào hạn mức tài khoản của chị. Tool gọi Claude ở
> chế độ gọn (không kèm bản hướng dẫn lập trình dài của Claude Code, tắt công cụ,
> bỏ MCP) nên mỗi lần gọi rẻ hơn khoảng 10 lần so với gọi mặc định; Bắt trend chỉ
> tìm web tối đa 3 lần, không mở từng trang. Bước tốn nhất vẫn là **Bắt trend**
> (mỗi lần bấm) và **Viết kịch bản** (mỗi tập, tăng theo thời lượng).
> **Dựng video không tốn hạn mức AI**: giọng (OmniVoice), nghe giọng mẫu
> (Whisper), vẽ nhân vật, cử chỉ, bàn ghế, góc máy và ghép video đều chạy trên máy. Góc trên bên phải
> màn hình đếm số lần đã gọi Claude và Antigravity trong phiên.

### Trợ lý AI cho từng việc (Cài đặt → Trợ lý AI cho từng việc)

Mỗi việc chọn riêng dùng Claude hay Antigravity (model Gemini của Google). Mặc định:

| Việc | AI mặc định |
|---|---|
| Viết kịch bản (kể cả tự thêm/bớt cho đúng thời lượng) | Claude |
| Rà soát kịch bản | Claude |
| Áp dụng góp ý vào kịch bản | Claude |
| 3 hướng khác | Antigravity |
| Bắt trend | **Luôn Claude** — cần tìm trên web; Antigravity chạy ngầm không được phép dùng công cụ nên không tìm được |
| Chọn nhân vật, chọn bối cảnh, mô tả giọng | Antigravity |

- Nếu AI đã chọn lỗi, chưa cài hoặc hết hạn mức, tool **tự chuyển sang AI còn
  lại** (tắt được ở cùng mục). Các lần chuyển ghi vào `data/logs/ai_calls.log`.
- Chưa cài Antigravity thì mọi việc vẫn chạy bằng Claude như trước.
- Antigravity báo chưa đăng nhập: tool dùng Claude cho cả phiên đó (không thử
  lại mỗi lần cho chậm). Gõ `agy` trong cửa sổ lệnh để đăng nhập, rồi bấm **Lưu
  cài đặt** trong tool là dùng lại được.
- Ô **Model của Antigravity** để trống là dùng mặc định (vd có thể ghi
  `gemini-3.1-pro-high`).
- Nút **Kiểm tra máy** báo có Antigravity CLI chưa.

> **Vì sao không dùng Gemini CLI nữa?** Google đã ngừng cho Gemini CLI đăng nhập
> bằng tài khoản Google cá nhân (lỗi *IneligibleTierError … migrate to the
> Antigravity suite*) và chuyển sang Antigravity. Cài đặt cũ chọn "Gemini" được
> tự chuyển sang Antigravity.

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

### Khung video và thời lượng (mục 1)

- **Khung video**: 9:16 dọc (TikTok, Shorts, Reels), 16:9 ngang (YouTube) hoặc
  1:1 vuông. Mỗi tập chọn riêng, nên cùng một câu chuyện làm được hai bản cho
  hai nền tảng: dựng xong bản 9:16, đổi sang 16:9 rồi dựng lại.
  - Khung ngang: nhân vật to hơn và đứng gần nhau hơn, thấy rộng bối cảnh hơn.
  - Đổi khung thì các bối cảnh do AI vẽ được **tự vẽ lại** cho vừa khung mới.
    Ảnh chị tự tải lên thì được cắt cho vừa, nên nên tải ảnh đúng tỉ lệ.
  - Ô xem trước (mục 9) và dự án CapCut cũng đổi theo khung.
- **Thời lượng (giây)**: độ dài mong muốn của tập, từ 15 đến 600 giây. AI
  viết đủ số câu cho độ dài đó (khoảng 1 nhịp cho mỗi 4 giây), tập dài hơn
  được phép nhiều bối cảnh hơn. Để trống thì AI tự chọn 30–90 giây như trước.
  Ô “Mục tiêu” ở mục kịch bản đổi theo thời lượng này.
  - Giọng AI đọc nhanh nên tool báo cho Claude **số chữ cần viết** (âm tiết
    Hangul hoặc số từ tiếng Anh), không chỉ số giây. Viết xong mà ước tính
    lệch đích quá 10%, Claude tự thêm/bớt câu một lần.
  - Ô ước tính độ dài tính theo tốc độ đọc thật của OmniVoice và nhịp nghỉ
    tự nhiên, nên sát với video dựng ra.

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
- `# ngon_ngu`: `ko` (tiếng Hàn), `en` (tiếng Anh) hoặc `vi` (tiếng Việt).
  Kịch bản, giọng và phụ đề đều theo ngôn ngữ đó.
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
viết cho người Hàn, tập tiếng Anh viết cho người Mỹ, tập tiếng Việt viết cho người
Việt. Mỗi thị trường có thư viện kiểu hài, nguồn trend và điều cần tránh riêng.
Claude không dịch một truyện cười từ thị trường này sang thị trường kia.

**Hài Việt Nam** có sẵn các kiểu: chơi chữ / nói lái, chuyện gia đình Việt (con nhà
người ta, bố tiết kiệm điện), Tết và họ hàng, Gen Z vs phụ huynh, công sở, học sinh
– sinh viên, hài đồng cảm đời thường, bạn thân "lầy lội", phóng đại vô lý, cú lật
cuối, bắt trend. Tránh: chính trị, phân biệt vùng miền, chê ngoại hình, tôn giáo,
nói tục. Nhân vật tên Việt (Tuấn, Linh, bà Tư...), xưng hô đúng vai (mẹ – con,
anh – em, tao – mày giữa bạn thân); tập tiếng Việt không cần dòng dịch `//`.
Phụ đề tiếng Việt tự dùng font đủ dấu (Arial).

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

## 6a. Đạo cụ, tư thế, góc máy (như phim hoạt hình hài)

Ghi thêm trong ngoặc của câu thoại hoặc nhịp `>`:

```
## canh: phòng ngủ, buổi tối
민준 (happy, nam, cam=dienthoai): 아우~ 개 편해
## canh: nhà bếp
수아 (happy, cam=noi_mi): 밥이나 먹어야겠당
민준 (shocked, zoom, nhaylen): 뜨거워!!!
> 수아 (crying, om_goi, cam=bo) 1.0
수아 (sad, bo, goc=can): 진짜 미안해...
```

**Đạo cụ** — `cam=<đạo cụ>` (tay phải), `cam_trai=<đạo cụ>`, `cam=bo` bỏ hết đồ:
`dienthoai` (điện thoại), `noi_mi` (nồi mì, bưng hai tay), `coc`, `bat_com`,
`sach`, `tui` (túi xách), `tat` (chiếc tất), `banh`, `chai` (chai nước/soju),
`hop_qua` (hai tay), `remote`, `chao`. Nhân vật **giữ đồ qua các câu sau** cho
tới khi đổi; cầm đồ thì tay tự vào tư thế cầm (điện thoại trước ngực, bưng nồi).

**Tư thế đời thường** (ghi như cử chỉ): `nam` (nằm dài), `ngoi` (ngồi xổm),
`om_goi` (ngồi bó gối), `bo` (bò), `nga_ngua` (ngã ngửa), `voi` (với lên cao),
`chay`, `dam_dat` (dậm chân), `an`, `xem_dt`, `cam_tai` (nghe điện thoại),
`bung`, `gio_do`, `ngoi_ghe`, `dung_day`. Nằm/ngồi/bò/khoanh tay được **giữ qua các câu sau** cho tới khi
có cử chỉ khác; sang bối cảnh mới thì mọi người đứng dậy.

**Bàn ghế theo bối cảnh, nhân vật ngồi sẵn** — ở **văn phòng** (ghế xoay + bàn
làm việc có laptop), **lớp học** (ghế + bàn học), **quán cà phê** (ghế + bàn có
khăn, cốc), **phòng khách** (sofa), **phòng ngủ** (ngồi mép giường), **công viên**
(ghế đá), tool tự vẽ đồ đạc ngay chỗ nhân vật: ghế ở sau lưng, bàn ở trước che
chân như người thật. Vào cảnh là mọi người đã ngồi. Nhà bếp, đường phố, cửa hàng,
bãi biển thì đứng như trước.

- `dung_day`: đứng bật dậy (sốc, giận, bỏ đi). `ngoi_ghe`: ngồi xuống (cả ở cảnh
  không có bàn ghế).
- **Đang ngồi vẫn làm cử chỉ tay** (`omdau`, `chitay`, `vaytay`, cầm đồ...) mà
  không đứng dậy. Cử chỉ dùng cả người (`dibo`, `chay`, `nhaylen`...) thì đứng lên.
- **Nhà bếp** có quầy bếp (thớt, nồi), **cửa hàng** có quầy thu ngân trước người
  đứng bên phải — mọi người đứng. **Phòng khách** có thêm bàn trà trước sofa.
- Ghi rõ việc đang làm trong `## canh:` để có đúng đồ đạc: "phòng khách, **ăn
  cơm**" → bàn ăn có bát đũa; "**phòng họp**" → bàn họp dài; "**trạm xe buýt**"
  → ghế chờ; "**quầy thu ngân**" → quầy tính tiền.
- Ảnh nền chị tự tải lên: tool đoán loại cảnh từ dòng `## canh:` (vd "văn phòng",
  "quán cà phê", "phòng khách").
- Tắt ở **Cài đặt → Cử động nhân vật → Bàn ghế theo bối cảnh**.

```
## canh: văn phòng, buổi sáng
Linh (worried, omdau): Họp lúc... năm phút nữa.
Tuấn (shocked, dung_day, zoom): Hả?!
```

**Cử chỉ đời thường mới** (làm được cả khi đang ngồi): `go_phim` (gõ phím),
`chong_cam` (chống cằm), `dap_ban` (đập bàn), `gac_tay` (gác tay sau đầu),
`cui_dau` (cúi đầu), `gio_tay` (giơ tay phát biểu), `gai_dau` (gãi đầu ngượng),
`che_mieng` (đưa tay lên miệng), `chong_nanh` (chống nạnh), `lac_tay` (lắc ngón tay
"không không").

**Sân khấu rộng, máy quay lia theo người nói (khung dọc 9:16)** — bối cảnh rộng
gấp khoảng 2,3 lần khung hình, các nhân vật đứng giãn ra chứ không chen nhau; ai
nói thì máy quay lia mượt (~0,45 giây) sang người đó, người kia ló ở mép khung.
Nhịp phản ứng `>` thì lia sang người phản ứng; sang cảnh mới thì máy đặt ngay chỗ
người nói đầu tiên. Bối cảnh AI vẽ được vẽ lại bản rộng (đồ đạc trải dài như khung
ngang); ảnh chị tự tải lên thì được phóng và cắt cho vừa, nên nên dùng ảnh ngang.
Khung 16:9 và 1:1 vốn đã rộng nên giữ như cũ. Tắt ở **Cài đặt → Cử động nhân vật
→ Sân khấu rộng ở khung dọc**.

**Quay vào nhau khi nói chuyện** — khi hai người trở lên nói chuyện, người nghe
quay hẳn về phía người đang nói, người nói quay về phía người vừa nói với mình:
mặt vẽ lại theo hướng nhìn (mắt mũi miệng dồn sang, tai phía đó khuất), người
hẹp lại như đứng nghiêng và hơi ngả về phía nhau, quay dần trong ~0,3 giây.
Cảnh một người thì nhìn thẳng. Tắt ở
**Cài đặt → Cử động nhân vật → Góc nghiêng 3/4**.

**Góc máy** — tool **tự đổi góc như phim** (mở cảnh toàn cảnh, câu thường xen kẽ
cận mặt và qua vai có gáy người nghe ở tiền cảnh, phản ứng mạnh thì siêu cận,
cử chỉ cả người thì toàn cảnh). Muốn chỉ định: `goc=toan`, `goc=trung`,
`goc=can`, `goc=sieucan`, `goc=quavai`. Tắt tự đổi ở **Cài đặt → Góc máy**.

**Phụ đề** mặc định ở **phía trên** như các kênh hoạt hình hài; đổi ở
**Cài đặt → Vị trí phụ đề**.

> Đạo cụ, tư thế và góc máy cần **bật cử động** (Cài đặt → Cử động nhân vật,
> nay mặc định bật).

---

## 6a2. Phong cách bối cảnh AI vẽ

Ở **Tập mới → mục 8 → Phong cách bối cảnh AI vẽ** (riêng cho từng tập):

| Phong cách | Trông thế nào |
|---|---|
| **Hoạt hình phẳng** (mặc định) | Màu tươi, nét viền rõ |
| **Pastel dịu** | Màu nhạt, mềm, hợp chuyện gia đình, dễ thương |
| **Màu nước** | Màu loang, có vân giấy |
| **Chì màu** | Nét chì, giấy vẽ tay |
| **Truyện tranh** | Ít mảng màu, viền đen đậm |
| **Hoài cổ** | Ngả vàng nâu, hạt phim, tối góc |
| **Tối neon** | Tông tối, ánh tím xanh như phim |
| **Xoá phông** | Nền mờ nhẹ cho nhân vật nổi bật |

Đổi phong cách thì mọi nền do tool vẽ trong tập được vẽ lại ngay (không tốn lượt
AI); ảnh nền chị tự tải lên giữ nguyên. Bàn ghế nhân vật ngồi vẫn vẽ kiểu phẳng.

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
- Mỗi cảnh có **đồ đời thường như thật**: đèn trần, điều hoà, ổ điện, công tắc,
  thảm, dép, khung ảnh gia đình, kệ sách, lịch treo tường; bếp có bếp ga, hút
  mùi, lò vi sóng, nồi cơm, ống đũa, móc treo dụng cụ; văn phòng có bảng trắng,
  bảng ghim giấy nhớ, máy in; lớp học có quạt trần, tủ sách, chổi; quán cà phê
  có kệ ly, dây đèn trang trí; cửa hàng có tủ mát nước ngọt; đường phố có dây
  điện chằng chịt, xe tay ga, cục nóng điều hoà, biển hiệu; công viên có hàng
  rào, cột đèn, bụi hoa; bãi biển có ghế nằm, thuyền buồm, bóng. Đồ được xếp
  riêng cho khung dọc và khung ngang, màu sách và đồ trên kệ đổi theo từng cảnh
  nên các tập không giống hệt nhau.
- Trong video, vào cảnh mới có chuyển mờ ngắn (khoảng 0,35 giây); quay lại
  nơi đã có thì cắt thẳng.

### Mỗi người một nơi (gọi điện, nhắn tin...)

Mặc định cảnh nào cũng có mặt mọi nhân vật. Muốn cảnh chỉ có vài người thì
ghi tên sau dấu `|`:

```
## canh: đường phố, buổi tối | 민준
민준 (happy, cam_tai, cam=dienthoai): 여보세요?
## canh: phòng khách, buổi tối | 수아
수아 (angry): 지금 몇 시야?!
민준 (scared): 미안...
수아 (angry): 빨리 와!
## canh: phòng khách, buổi tối
민준 (happy): 나 왔어~
```

- Người đã được gắn vào một nơi (`| tên`) thì mỗi khi người đó nói, video tự
  cắt sang nơi của người đó. Không cần viết `## canh:` trước từng câu.
- Cảnh chỉ có một người thì người đó đứng giữa khung.
- Ghi lại `## canh:` không có `|` là mọi người lại cùng một chỗ (vd về nhà).

---

## 7. Nhân vật

### Kiểu nhân vật AI vẽ
Chọn ngay ở **Tập mới → mục 8 → Kiểu nhân vật** (riêng cho từng tập). Để
"Theo Cài đặt" thì dùng mặc định ở **Cài đặt → Cử động nhân vật → Kiểu nhân vật
AI vẽ**. Đổi kiểu ở mục 8 thì các nhân vật bộ ghép đã có của tập được ghép lại
ngay theo kiểu mới (giữ nguyên tóc, áo, trang phục), không tốn lượt AI.

| Kiểu | Trông thế nào |
|---|---|
| **Tự chọn theo ngôn ngữ** (mặc định) | Tập tiếng Anh, tiếng Việt → người xám TikTok, tập tiếng Hàn → vẽ tay kiểu Hàn |
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

**Đồng phục nghề** (mọi kiểu nhân vật): shipper (áo xanh sọc phản quang, mũ bảo
hiểm, thùng hàng sau lưng), bác sĩ (áo blouse trắng, ống nghe), y tá (áo trắng chữ
thập đỏ, mũ y tá), công an (đồng phục, phù hiệu, mũ kê-pi), đầu bếp (áo trắng hai
hàng cúc, mũ đầu bếp), công nhân (áo phản quang cam, mũ bảo hộ vàng), bảo vệ (áo
xanh nhạt, phù hiệu, mũ). Nhân vật có nghề rõ trong kịch bản thì AI bắt buộc cho
mặc đồng phục; nếu AI lỗi, tool tự đoán nghề theo tên (vd "Anh Shipper", "Bác sĩ
Hùng") hoặc theo cách người kia gọi khi chỉ có hai người ("anh shipper ơi",
"chú bảo vệ"). Các nhân vật luôn khác màu áo và kiểu tóc. Tập đã làm xong: bấm
**Vẽ lại** ở nhân vật đó để mặc đồng phục.

Với tập tiếng Hàn, Claude phối đồ theo các vai quen thuộc: học sinh, nhân viên
văn phòng / sếp, ajumma, ajeossi, bà cụ, giới trẻ MZ, người yêu.

Hai kiểu người xám và vẽ tay Hàn có **viền tự tạo quanh cả khối**, nên khuỷu
tay, đầu gối liền mạch khi cử động, tay chân thon dần như nét vẽ tay.

Đổi kiểu ở Cài đặt thì chỉ áp dụng cho tập mới; tập đang làm thì đổi ở mục 8.

### Tạo nhân vật giống ảnh
Ở **Tập mới → mục 8 → Tạo nhân vật giống ảnh**: chọn nhân vật (hoặc "+ Tên
khác…"), chọn một ảnh tham khảo (người thật, ảnh diễn viên, tranh vẽ...) rồi bấm
nút. Claude xem ảnh, chọn kiểu tóc, màu tóc, màu da, màu áo, quần, trang phục,
phụ kiện (kính, mũ, khẩu trang...) gần nhất trong bộ ghép, rồi tool ghép nhân
vật theo **Kiểu nhân vật** đang chọn, đủ mọi biểu cảm. Dưới nút hiện câu Claude
tả ảnh để chị biết nó thấy gì.

- Nhân vật là "giống ảnh" theo kiểu hoạt hình (tóc, màu, trang phục), không vẽ
  lại y hệt khuôn mặt.
- Việc này cần xem ảnh nên luôn dùng Claude (1 lượt, ảnh được thu nhỏ cho đỡ tốn).
  Claude lỗi thì tool tự lấy màu áo và màu tóc trong ảnh.
- Ảnh gốc lưu ở `projects/<tập>/assets/ref/`.

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
- Nhân vật **chưa có giọng mẫu** (chỉ có mô tả giọng): tool tự tạo **một đoạn
  giọng mẫu cố định** (~5 giây, theo mô tả, cố định theo tên nhân vật) rồi mọi
  câu nhân bản từ đoạn đó — không còn cảnh mỗi câu một giọng. Đoạn mẫu lưu ở
  `projects/<tập>/audio/giong_mau/`; dựng lại vẫn đúng giọng cũ, đổi mô tả giọng
  thì tool tạo lại. Ưng giọng nào có thể tải đoạn đó lên Thư viện làm giọng mẫu
  để dùng cho các tập sau.
- Mỗi nhân vật có giọng mẫu riêng cho tiếng Hàn, tiếng Anh và tiếng Việt.
- Tập tiếng Việt: nên **tải giọng mẫu tiếng Việt** (5–15 giây) để giọng tự nhiên
  nhất; mô tả giọng vẫn dùng được nhưng không có cụm accent cho tiếng Việt.

> **Mô tả giọng chỉ nhận một số cụm cố định** mà OmniVoice hiểu được:
> `female` `male` · `child` `teenager` `young adult` `middle-aged` `elderly` ·
> `very low pitch` `low pitch` `moderate pitch` `high pitch` `very high pitch` ·
> `whisper` · `korean accent` `american accent` `british accent` và vài accent khác.
> Gõ "vui tươi" hay "giọng ấm" thì OmniVoice không hiểu, tool sẽ bỏ qua cụm đó.
> Muốn giọng có cảm xúc riêng thì nên **tải giọng mẫu** thay vì dùng mô tả.

---

## 9. Dựng video

1. Tạo giọng từng câu, đo độ dài thật, cắt bỏ khoảng im ở đầu và cuối.
2. Xếp câu theo **nhịp nói chuyện thật**: bị cắt lời (câu kết thúc bằng `—`)
   thì nối ngay; sau câu hỏi người kia ngẫm một chút rồi đáp; câu bỏ lửng `...`
   lặng lâu hơn; cùng người nói tiếp thì chỉ lấy hơi. Nhịp `>` là khoảng lặng
   có chủ đích. Nếu video vẫn ngắn hơn **Thời lượng** đã đặt, tool giãn nhẹ
   các chỗ nghỉ (tối đa ~0,45 giây mỗi chỗ) cho sát đích, không kéo chậm giọng.
3. Miệng mở khi có tiếng, ngậm khi im (đo theo âm lượng giọng).
4. Đổi biểu cảm, zoom vào người nói ở câu có zoom, chèn tiếng động.
5. Tiêu đề cố định trên cùng; phụ đề vàng viền đen, từng cụm ngắn nhảy theo lời.

### Đầu ra
- Video **mp4** theo khung đã chọn: dọc 1080×1920, ngang 1920×1080 hoặc
  vuông 1080×1080, đăng được luôn.
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

- Video hài: nhân vật cử động theo khung xương (cử chỉ, ngồi, quay mặt); Truyện
  kể: nhân vật con nhộng không tay chân nên chỉ diễn bằng biểu cảm và cả thân.
- Nhân vật tải lên bằng 1 ảnh thì không đổi được biểu cảm.
- Chất lượng giọng tiếng Hàn của OmniVoice cần nghe thử trước khi làm nhiều tập.
- Bối cảnh do AI vẽ là tranh phẳng 2D (không 3D), nhưng đồ vật vẽ theo kích
  thước thật so với người (cửa 2,1 m, sofa 85 cm, bàn 75 cm, trần 2,6 m) và
  sàn có chiều sâu. Khung dọc hẹp (khoảng 2,4 m bề ngang) nên thấy ít đồ hơn
  khung ngang.
- Xuất dự án CapCut là tính năng **thử nghiệm**: phụ thuộc cấu trúc file của
  đúng phiên bản CapCut, và CapCut cập nhật có thể làm nó ngừng hoạt động.

---

## 12. Thư mục

```
tool_hoat_hinh/
  cai_dat.bat        cài lần đầu
  cai_3d.bat         cài phần vẽ bối cảnh 3D (không bắt buộc)
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

---

## 11. Truyện kể (video dài 20–30 phút, chỉ có giọng người kể)

Tab **Truyện kể** làm video kể chuyện kiểu kênh YouTube văn học (Lão Hạc, Tắt
đèn, truyện cổ tích...): **một giọng người kể** đọc suốt, không có thoại nhân vật;
hình có hai cách (ô **Cách làm hình**):

- **Tool tự vẽ & nhân vật cử động** (mặc định, miễn phí): tool tự vẽ bối cảnh và
  nhân vật, không cần vẽ gì ở ngoài. Xem mục *Tool tự vẽ* ngay dưới.
- **Tranh tự vẽ ở công cụ khác**: chị vẽ tranh (Midjourney, Gemini, ChatGPT...) từ
  **bộ câu lệnh vẽ** tool xuất ra rồi tải lên.

### Tool tự vẽ & nhân vật cử động
- **Nhân vật** kiểu vẽ tay kể chuyện Hàn: đầu tròn to, thân con nhộng không tay
  chân, viền đen nét bút, màu dịu. Có người (trẻ con, thanh niên, trung niên, già),
  chó, mèo. Chọn được tóc (búi, rối, rẽ ngôi, hói...), màu tóc, nón lá, khăn vấn,
  kính, râu, áo (áo nâu, áo bà ba, áo cánh + váy, sơ mi, áo dài...), màu áo, màu
  quần, áo vá. AI chọn sẵn khi viết lời kể; chị sửa ở mục 2, ảnh xem trước vẽ lại
  ngay.
- **Bối cảnh** nét vẽ tay có vân giấy: nhà tranh, nhà ngói xưa, sân nhà quê, đường
  làng, cánh đồng lúa (và các mẫu hiện đại: phòng khách, bếp, đường phố...), ngày
  hoặc đêm. Lời kể nhắc "đêm, tối, đèn dầu" thì cảnh tự thành ban đêm.
- **Diễn theo lời kể** (mục 3, mỗi cảnh chọn cho từng nhân vật): đứng thở chớp mắt,
  vui nhún nhảy, mừng rỡ nhảy cẫng, buồn cúi đầu, khóc (nước mắt rơi, nấc), giận
  (rung người, dấu nổi gân), giật mình (bật lên, vạch sốc, giọt mồ hôi), lo lắng
  (lắc lư), suy nghĩ (dấu ...), ranh mãnh, gật gù, lắc đầu, ngủ (zzz), nằm (ốm,
  chết), đi vào, đi ra. Chọn **Nhép miệng** cho nhân vật có câu nói được trích
  trong lời kể: nhân vật đó mấp máy môi theo giọng khi người kể đọc câu trong ngoặc
  kép.
- Nhân vật tự quay mặt về phía nhau; máy quay phóng nhẹ vào chỗ có người hoặc lia
  ngang.
- **Bối cảnh 3D** (ô **Bối cảnh** → "3D — AI vẽ trên máy"): nhân vật vẫn 2D con
  nhộng, còn nền là tranh kiểu phim hoạt hình 3D (Pixar) do Stable Diffusion XL vẽ
  ngay trên máy chị, không tốn tiền, không cần mạng sau khi tải mô hình.
  - Cài một lần: bấm đúp **cai_3d.bat** (tải khoảng 7 GB). Cần card NVIDIA 8 GB trở
    lên; GTX 1080 11 GB vẽ mỗi ảnh khoảng 20–60 giây.
  - Mỗi địa điểm (ngày / đêm) chỉ vẽ **một lần** rồi dùng lại cho mọi cảnh ở đó,
    nên căn nhà giống nhau suốt truyện. AI vẽ theo mô tả tiếng Anh của địa điểm ở
    mục 2 (sửa mô tả rồi bấm **Vẽ lại 3D** nếu chưa ưng; mỗi lần vẽ lại ra bố cục
    khác).
  - Bấm **Vẽ bối cảnh 3D còn thiếu** để vẽ trước và xem, hoặc cứ bấm **Dựng video**:
    tool tự vẽ phần còn thiếu trước rồi mới đọc lời kể (vẽ xong tự trả bộ nhớ card
    cho giọng đọc).
  - Thiếu bản ban đêm thì tool làm tối bản ban ngày; địa điểm chưa vẽ 3D (hoặc vẽ
    lỗi) thì dùng bối cảnh vẽ tay.
  - Nhân vật có bóng mờ dưới chân để đứng vững trên nền 3D.
  - Đổi mô hình (vd mô hình 3D khác trên Hugging Face): sửa `bg3d_model`,
    `bg3d_lora_repo`, `bg3d_lora_file`, `bg3d_steps` trong `data/settings.json`.
- Muốn một cảnh đặc biệt đẹp hơn: tải tranh lên đúng số cảnh (scene_012.png),
  tranh đó thay cảnh tool vẽ.
- **Vẽ thêm bằng AI** (mục 2, khung dưới cùng): truyện cần thứ tool chưa có — mũ
  miện vua, mũ cánh chuồn, áo long bào, áo giáp, con trâu, con hổ, cung điện, ngôi
  chùa, khu rừng... — chọn loại (đồ đội đầu / hoa văn trên áo / con vật / bối
  cảnh), gõ tên (thêm mô tả nếu muốn) rồi bấm **AI vẽ thêm**. AI trên máy chị
  (Claude, hoặc Antigravity nếu chọn trong Cài đặt → Trợ lý AI → "Vẽ thêm nhân
  vật, con vật, bối cảnh") vẽ bằng các khối hình, tool vẽ lại theo đúng nét vẽ tay
  và lưu vào thư viện (`data/library/doodle_parts.json`), truyện sau dùng lại.
  Thứ vẽ thêm có dấu ★ trong các ô chọn: đồ đội đầu ở ô **Mũ nón** hoặc **Thêm**,
  hoa văn áo ở ô **Thêm**, con vật ở ô **Loài**, bối cảnh ở ô mẫu bối cảnh của địa
  điểm. Chưa ưng thì bấm **Vẽ lại** (có thể thêm mô tả), không dùng thì **Xoá**.
- Khi bấm **AI viết lời kể**, AI tự khai báo những thứ truyện cần mà chưa có (tối
  đa 8) và tool vẽ thêm luôn trước khi viết lời kể — không cần nhờ ai.
- Con vật vẽ thêm vẫn có biểu cảm (chớp mắt, vui, buồn, khóc, giật mình, há miệng)
  và cử động như chó mèo có sẵn.
- Truyện làm từ trước khi có tính năng này: tool tự đoán bộ ghép nhân vật và bối
  cảnh từ mô tả tiếng Anh; bấm **AI viết lời kể** lại để AI chọn hành động từng cảnh.

### Các bước (cách tranh tự vẽ)
1. **Truyện:** tên truyện, tác giả, thời lượng (phút), khung (16:9 cho YouTube),
   phong cách tranh (mặc định **Vẽ tay webtoon Hàn**: nhân vật đầu tròn, thân
   con nhộng không tay chân, viền đen nét bút, màu phẳng nhạt, nền vẽ tay có vân
   giấy, giống các kênh kể chuyện Hàn), giọng người kể (chọn giọng trong
   Thư viện, hoặc mô tả giọng), có/không phụ đề. Có thể **dán nguyên văn** để AI
   bám sát truyện gốc.
2. Bấm **AI viết lời kể & chia cảnh**: Claude chia chương, lập danh sách nhân vật
   và địa điểm với **mô tả ngoại hình cố định**, rồi viết lời kể từng chương, chia
   thành cảnh (mỗi cảnh 8–15 giây = một tranh). Truyện 25 phút ≈ 8 chương, 120–180
   cảnh; mất vài phút. Lời kể, mô tả tranh, kiểu máy quay đều **sửa được** rồi bấm
   Lưu.
3. **Tải bộ câu lệnh vẽ (.txt)**: có câu lệnh vẽ **ảnh nhân vật** (char_...) để
   làm ảnh tham chiếu, và câu lệnh từng **cảnh** (scene_001...). Mỗi câu lệnh cảnh
   đã ghép sẵn phong cách + mô tả cảnh + ngoại hình cố định của nhân vật có mặt +
   địa điểm + thời đại, nên tranh nào cũng ra cùng một Lão Hạc, cùng một cậu Vàng.
   Khi vẽ, gửi kèm ảnh tham chiếu nhân vật (Midjourney `--cref`; Gemini/ChatGPT gửi
   kèm ảnh) để giống nhau hơn nữa.
   **Ảnh mẫu phong cách** (mục 4, không bắt buộc): tải lên một khung hình có bối
   cảnh và nhân vật đúng kiểu chị muốn. Bộ câu lệnh sẽ dặn vẽ đúng phong cách ảnh
   đó và nhắc gửi kèm ảnh mọi lần vẽ (Midjourney `--sref`; Gemini/ChatGPT đính kèm
   ảnh), tranh ra giống mẫu hơn hẳn so với chỉ tả bằng chữ.
4. **Tải ảnh lên**: chọn nhiều ảnh một lúc; tên file có số cảnh (scene_001.png,
   001.jpg, "Cảnh 4.png"... đều được). Cảnh chưa có tranh vẫn dựng được (khung chữ
   tạm) để nghe thử nhịp kể trước.
5. **Dựng video**: OmniVoice đọc lời kể (giọng cố định, đọc chậm hơn thoại), máy
   quay chuyển động trên tranh (phóng vào, lùi ra, lia ngang/dọc), chuyển cảnh mờ,
   thẻ tên truyện ở đầu, thẻ tên chương, nhạc nền (Cài đặt → Nhạc nền), tối dần ở
   cuối. Video 25 phút dựng khoảng 15–20 phút (đọc lời kể + ghép hình); dựng lại
   sau khi sửa thì cảnh nào lời kể không đổi không phải đọc lại.

### Bản quyền
Nam Cao (mất 1951), Ngô Tất Tố (1954)... đã hết thời hạn bảo hộ ở Việt Nam nên
dùng nguyên văn được — vẫn nên ghi tên tác giả. Truyện của tác giả còn sống hoặc
mất chưa đủ 50 năm thì **đừng dán nguyên văn**; để trống cho AI kể lại bằng lời
khác, hoặc chọn truyện dân gian, cổ tích.

### Đỡ tốn hạn mức
Viết lời kể là bước tốn nhất (truyện dài, nhiều chương). Cài đặt → Trợ lý AI →
"Truyện kể: viết lời kể, chia cảnh" chọn được Antigravity; lỗi thì tự chuyển sang
Claude.
