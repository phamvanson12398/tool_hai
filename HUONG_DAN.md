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

### Ra lệnh bằng một câu yêu cầu
Ô **Yêu cầu** ở đầu mục 1: gõ như nói với người làm phim, vd *"Làm đoạn phim về
chương 1 truyện Lão Hạc"*, *"Một ngày bình thường của Lão Hạc"*, *"Kể lại truyện
Tấm Cám cho trẻ con"*. AI tự hiểu nên **chuyển thể đúng một phần truyện** (bám
nguyên tác) hay **sáng tác tình huống mới** (nhiều việc đời thường) nhưng giữ đúng
tính cách, hoàn cảnh, thời đại, cách nói của nhân vật. Tên video AI tự đặt nếu để
trống; tên truyện, tác giả, nguyên văn không bắt buộc.

### Lối kể: Kể lại truyện hoặc Phân tích từng chi tiết
Ô **Lối kể** (mục 1, kiểu video Kể chuyện):
- **Kể lại truyện** (mặc định): người kể kể lại câu chuyện như trước.
- **Phân tích từng chi tiết**: kiểu kênh phân tích văn học (như video "Vợ nhặt" đi
  chậm từng chữ). Người kể xưng "mình", nói chuyện với "các bạn"; kể một đoạn rồi
  dừng lại soi một chi tiết: trích đúng chữ của tác giả, giải nghĩa từ cổ / phong tục
  (ngụ cư, cám khác trấu...), đưa bối cảnh lịch sử và số liệu, đọc ý đồ tác giả (vì
  sao nhân vật không có tên...), gieo chi tiết "xin nhớ giúp mình" rồi trả lại ở sau.
  Mạch video: chào + móc câu một sự thật gây sốc → bối cảnh thời đại → nhân vật và
  những chữ quan trọng → diễn biến (mỗi chặng dừng ở vài chi tiết đắt) → cao trào
  ("đây là chỗ mình muốn bạn nghe kỹ nhất") → kết: so sánh với tác phẩm khác, số phận
  tác phẩm, vài nét về tác giả, câu hỏi cho người xem, mời like / subscribe.
  - AI được dặn không bịa câu văn, tình tiết, số liệu; dán **nguyên văn** (nếu được
    phép) để trích chữ chính xác hơn.
  - Lối này không xen thoại: câu nói của nhân vật do người kể đọc trong ngoặc kép
    (ô Thoại nhân vật ẩn đi).
  - Đổi lối kể thì bấm **AI viết lời kể & chia cảnh** lại.

### Nội dung có đầu – thân – kết, mở bằng móc câu
AI dựng video theo mạch rõ ràng (cả Kể chuyện và Phim):
- **Móc câu (hook)** 15–30 giây đầu: hé lộ trước khoảnh khắc gay cấn / xúc động
  nhất (vd lão Hạc oà khóc "Cậu Vàng đi đời rồi ông giáo ạ!") hoặc một câu hỏi bí
  ẩn, không nói ra kết cục, rồi người kể dẫn về "Mọi chuyện bắt đầu từ...". Cảnh
  móc câu hơi nhạt màu, tối viền như đoạn trích; hết móc câu có tiếng "vút" rồi câu
  chuyện kể từ đầu (Kể chuyện: tên truyện hiện sau móc câu; Phim: không có chữ giới
  thiệu).
- **Mở đầu**: nhân vật, hoàn cảnh, gieo mầm mâu thuẫn. **Thân**: biến cố nối nhau
  theo nguyên nhân – kết quả, dồn lên **cao trào** (diễn trọn khoảnh khắc móc câu
  đã hé lộ); cuối mỗi chương để một gút cho người xem muốn xem tiếp.
- **Kết**: cởi nút, kết cục trọn vẹn, không bỏ lửng; nhịp chậm lại, hình ảnh cuối
  đọng lại kèm một câu người kể khép chuyện.
- Mục 3 ghi vai từng chương (Mở đầu / Thân / Cao trào / Kết) và đánh dấu cảnh
  **MÓC CÂU mở video**.
- **Cho hay, không đơn điệu**: AI được dặn mỗi cảnh phải có chuyện mới hoặc cảm
  xúc đổi chiều, vào thẳng chuyện, kết cảnh bằng câu / cử chỉ "đắt"; thoại mỗi người
  một giọng, có ẩn ý, không hỏi – đáp đều đều; nhịp căng – lắng – cười – nghẹn xen
  nhau, có chút hài đời thường; cho thấy bằng hành động, đồ vật thay vì kể; chi tiết
  thật của thời đại; gieo chi tiết sớm rồi trả lại ở kết; không lặp câu, lặp ý.
- Phim: tool tự đổi cử chỉ khi nói theo lời (hỏi thì gãi đầu / suy nghĩ, chào thì
  vẫy, cảm ơn thì cúi, "trời ơi" thì đập trán, "vâng" thì gật, "không" thì lắc đầu,
  cười "ha ha" thì cười ôm bụng...), không để ai chỉ "nói" mãi; người nghe thỉnh
  thoảng gật, suy nghĩ, sững sờ.

### Tab "Kiểu nhân vật"
Tab riêng trên thanh trên cùng, gồm:
- **Tạo kiểu nhân vật từ ảnh**: chọn ảnh một nhân vật mẫu (ảnh chụp màn hình phim hoạt
  hình, tranh vẽ...), đặt tên nếu muốn, bấm **Tạo kiểu nhân vật**. Claude xem nét vẽ (tỉ
  lệ đầu – thân – tay chân, kiểu mắt, nét viền, áo cộc / dài tay, quần dài / soóc, bụng
  tròn) và ngoại hình, rồi tool **vẽ thử đặt cạnh ảnh mẫu cho Claude so và chỉnh lại**
  (tối đa 2 lần, giống rồi thì thôi) — khoảng 1–3 phút. Ảnh nên rõ một nhân vật đứng
  thẳng thấy cả người. Kiểu đã tạo mà chưa giống: bấm **↻ Thiết kế lại theo ảnh mẫu**.
  Bộ vẽ có: mắt chấm / tròn / anime / meme / tròn trắng chấm đen giữa, mũi một nét / tròn có
  lỗ mũi / chấm, miệng một nét / môi hồng dày, tai hai bên, tóc (ngắn, mái, rối, rẽ ngôi,
  búi, dài, ngang vai, hói, bồng, bát úp, xoăn bồng, trọc có chỏm), áo (nâu, bà ba, cánh,
  váy, khoác, sơ mi, len, thụng, áo dài, phông cộc tay phồng), quần dài / soóc gấu tua rua,
  bụng tròn, tay dang ra hai bên, mặt Mochi / Webtoon, đầu bánh gạo / cằm V, cổ dài ngắn.
  Ảnh mẫu có nhiều nhân vật thì Claude ghi từng người (kèm
  biểu cảm) để dàn nhân vật xem trước giống đúng ảnh.
- Kiểu có sẵn **"Bé bụng phệ áo phông quần soóc"** vẽ lại từ ảnh mẫu đã gửi (6 bạn).
- Kiểu **Mochi** và **Webtoon** có dàn nhân vật mẫu riêng (nhân viên văn phòng, cô gái,
  아줌마 / mẹ chồng, học sinh, ông nội / sếp) giống bản mẫu đã duyệt.
- **Thẻ từng kiểu** (kiểu vẽ sẵn, kiểu có sẵn, kiểu chị tự tạo): ảnh động nhân vật diễn
  đủ hành động (đứng, đi, vẫy tay, nói, nhảy mừng, ngồi, khóc, suy nghĩ, cười), ảnh mẫu
  gốc và **dàn nhân vật** cùng nét (người già, người trẻ, trẻ con, con chó) để xem các
  nhân vật khác trong truyện sẽ trông thế nào. Kiểu tự tạo đổi tên, xoá được (xoá thì
  chuyển vào data/thung_rac, truyện đang dùng vẫn giữ nét vẽ).
- Kiểu tạo ở đây có ngay trong ô **Kiểu nhân vật** của mọi truyện (dòng "Đã lưu: ...").
  Màn hình Truyện kể không còn ô tải ảnh mẫu; bấm **Xem / tạo kiểu nhân vật →** để sang tab này.

### Kiểu nhân vật (Kể chuyện tool vẽ và Phim)
Ô **Kiểu nhân vật**:
- Chọn sẵn một kiểu: **Con nhộng tay chân ngắn** (vẽ tay Hàn, mặc định), **Chibi
  đầu thật to, mắt tròn**, **Người tỉ lệ cao** (đầu nhỏ, chân tay dài), **Anime mắt
  to, nét mảnh**, **Tối giản mắt chấm** (kiểu meme), và hai kiểu cho người Hàn xem
  hoạt hình:
  - **Mochi 둥글이** (kiểu 썰툰 / 사연): đầu bánh gạo bè ngang, mắt chấm đen có đốm sáng,
    má hồng luôn có, miệng mèo ω, không mũi, thân nhỏ tay mũm mĩm, viền mềm. Hợp truyện
    đời thường, hài, gia đình, cổ tích, bài học, thú cưng, truyện cho trẻ con.
  - **Webtoon 웹툰** (kiểu kênh 사연 / drama Hàn): người mảnh, chân dài, mặt trái xoan cằm V,
    có cổ, mắt to tròng nâu long lanh (nữ có lông mi), lông mày mảnh, mũi một nét, nét
    viền mảnh, áo đổ bóng một mảng. Hợp truyện nhà chồng – mẹ chồng, tình cảm, công sở,
    tài phiệt, học đường, phốt, báo thù, cảm động.
  Hai kiểu này có thêm đồ hiện đại: sơ mi + cà vạt, vest công sở, đồng phục học sinh
  (blazer có phù hiệu), áo len cài cúc, hoodie, tạp dề, chân váy xếp ly; tóc two-block
  nam Hàn, tóc dài mái thưa, vuốt ngược, xoăn ngắn kiểu 아줌마. Đủ biểu cảm (bình thường,
  vui, buồn, khóc có nước mắt, giận, sốc, lo, ngủ, lim dim, suy nghĩ) và mọi hành động
  của Phim (đi, ngồi, nằm, uống trà / hút thuốc chạm đúng miệng...). Người chân dài ngồi
  ghế đẩu cao tới gối.
- **Gợi ý theo thể loại**: gõ tên truyện / yêu cầu / nguyên văn có chữ như "nhà chồng",
  "công sở", "học đường" → dưới ô Kiểu nhân vật hiện gợi ý **Webtoon**; "cổ tích", "gia
  đình", "hài", "thú cưng" → gợi ý **Mochi**. Bấm **Dùng kiểu này** để đổi (không tự đổi).
- Chưa chọn kiểu → chọn **"Chưa chọn kiểu — theo ảnh nhân vật mẫu"** rồi tải ảnh
  một nhân vật mẫu lên: Claude xem ảnh, rút ra nét vẽ (tỉ lệ đầu – thân – chân – tay,
  độ dày tay chân, kiểu mắt, nét viền, độ run nét) và ngoại hình nhân vật đó. Khi
  viết, nhân vật chính dùng đúng ngoại hình mẫu, các nhân vật liên quan được thiết
  kế cùng nét vẽ, màu hài hoà nhưng phân biệt rõ. Ảnh xem trước ở mục 2 vẽ đúng kiểu.

### Hai kiểu video: Kể chuyện và Phim
Ô **Kiểu video** ở đầu mục 1:

- **Kể chuyện**: người kể đọc suốt, nhân vật diễn theo lời kể (có thể xen thoại).
  Với cách làm hình "Tool tự vẽ & nhân vật cử động", mỗi cảnh kể được **diễn bằng bộ
  máy của Phim**: nhân vật đi vào / đi ra, đi tới xoa đầu, đưa đồ, ôm, ngồi lên chõng,
  nằm trên giường, quay sang nhau, đứng nghe thì thỉnh thoảng đổi động tác; máy quay đổi
  góc (toàn cảnh, hai người, cận mặt) thay vì chỉ phóng chậm trên một khung đứng yên.
  Lời kể tả ai làm gì thì người đó làm đúng việc đó lúc đang kể. Cảnh nào lỗi thì tự
  quay về cách diễn tại chỗ như trước. (Cách "Tranh tự vẽ ở công cụ khác" vẫn là tranh
  tĩnh có máy quay lia / phóng.)
  Nhân vật có tay chân ngắn và **luôn cử động**: lúc đứng nghe cũng tự đổi động
  tác nhỏ mỗi vài giây (nhìn quanh, chắp tay sau lưng, gãi đầu, chống cằm, đổi chân...);
  khi lời kể nói "khóc, cười, ăn, uống, ôm, chỉ, vẫy, van xin, ngồi, nằm..." thì
  nhân vật làm đúng động tác đó; nhân vật đang nói vung tay theo nhịp.
- **Phim**: nhân vật tự nói chuyện với nhau bằng giọng riêng, đi lại, làm hành
  động; người kể chỉ thỉnh thoảng nối cảnh ("Mấy hôm sau..."). Đổi kiểu video thì
  bấm **AI viết lời kể & chia cảnh** lại để AI viết theo kiểu mới.

### Ảnh theo lời (voice đến đâu, ảnh đến đó)
Ô **Kiểu video** chọn **Ảnh theo lời**: chị có sẵn file giọng đọc (tự thu,
ElevenLabs...), tool chia thành từng câu và AI vẽ ảnh cho từng câu, ảnh đổi đúng
lúc giọng đọc tới câu đó.

1. Chọn **File giọng đọc có sẵn** (mp3, wav, m4a, mp4...) và **Phong cách ảnh AI vẽ**
   (hoạt hình 3D, anime 2D, vẽ tay webtoon, màu nước, ảnh chân thực, sơn dầu).
   Có kịch bản đúng như giọng đọc thì dán vào ô kịch bản (không bắt buộc) cho
   phụ đề đúng chữ hơn.
2. Bấm **Nghe giọng, chia câu & viết câu lệnh vẽ**: Whisper nghe từng chữ kèm thời
   gian, chia thành câu / cụm câu khoảng 1,5–6,5 giây (câu dài tự cắt ở dấu phẩy
   hoặc chỗ ngắt hơi), AI viết câu lệnh vẽ tiếng Anh cho từng câu và giữ nhân vật
   giống nhau ở mọi ảnh.
3. Bấm **AI vẽ ảnh còn thiếu** (cần cài **cai_3d.bat**; GTX 1080 mỗi ảnh khoảng
   20–60 giây, video 10 phút ≈ 150 ảnh nên để máy chạy một lúc). Ảnh nào chưa ưng
   thì sửa câu lệnh rồi bấm **Vẽ lại ảnh** ở câu đó; muốn dùng ảnh riêng thì tải
   lên đúng số câu (scene_012.png) ở mục 4.
4. Bấm **Dựng video**: ảnh còn thiếu được vẽ trước, rồi ghép đúng mốc lời đọc, máy
   quay chuyển động nhẹ trên ảnh, chuyển ảnh nhanh, phụ đề và nhạc nền tuỳ chọn.

### Chế độ Phim
- AI chuyển truyện thành **kịch bản phim**: mỗi chương nhiều cảnh, mỗi cảnh ở một
  địa điểm, gồm các **nhịp**:
  - **Thoại**: ai nói, nói gì, cử chỉ khi nói (khóc, vẫy, chỉ tay...), nói với
    ai; người nghe có thể phản ứng (sững sờ, gật đầu...).
  - **Hành động**: đi / chạy tới ai hoặc chỗ nào, đi vào / đi ra khung, ngồi
    xuống / đứng dậy / nằm, đưa đồ (đồ chuyển sang tay người nhận), ôm, xoa đầu,
    ăn, uống, cúi chào, vỗ tay, làm việc... cùng đồ cầm tay (bát, chén, thư, tiền,
    rổ, gậy, sách, hoa, tay nải, chai, dao, đèn dầu — thiếu thì "Vẽ thêm bằng AI"
    loại **Đồ vật cầm tay**).
  - **Người kể**: một câu nối cảnh.
- **Kín thoại, ít khoảng trống**: AI được dặn khoảng 3/4 số nhịp là thoại, không để quá 2
  hành động liền nhau mà không ai nói; vừa làm việc vừa nói, người nghe đáp lại ngắn,
  vai phụ chen câu. Cử chỉ khi nói nằm ngay trong câu thoại. Hành động không lời (đi
  vào, ngồi xuống, rít điếu...) diễn song song với câu sau, không bắt cả phim đứng chờ.
  Riêng đưa đồ, ôm, cho ăn thì đợi gần xong mới tới câu sau, để người nhận cảm ơn sau khi
  đã cầm đồ. Đo thử phim Lão Hạc 3 chương: thời gian không có tiếng còn khoảng 25%
  (trước đây 50–60%), phần còn lại là khoảng nghỉ tự nhiên giữa hai người nói.
- **Hài duyên, không xuyên tạc**: mỗi cảnh có 1–2 câu gây cười (tính lẩm cẩm, sĩ diện,
  cãi vặt, con chó phá đám, tục ngữ nói chệch...), nêm chút cách nói hài đang thịnh trên
  mạng (chủ yếu qua người kể và vai phụ), nhưng không đổi tình tiết, kết cục, tính cách;
  cảnh bi, cảnh cao trào giữ nghiêm. Chương sau biết thoại chương trước nên không lặp câu.
- **Rà soát hình khớp lời** (hai lớp): AI soát lại từng câu (cử chỉ đúng cảm xúc câu nói,
  không mâu thuẫn tư thế, đúng người làm, đồ cầm hợp việc, đúng lúc), rồi tool tự soát
  lời kể: lời kể nhắc ai (ở chỗ chủ ngữ) làm gì (khóc, gật gù, rít điếu, xoa đầu, đứng
  dậy, bỏ đi...) mà AI quên thì tool tự thêm hành động đó cùng lúc với lời kể. Đi tới xoa
  đầu / ôm / đưa đồ xong thì lùi ra, không đứng dính vào người kia.
- **Việc đang làm** (cuốc đất, quét sân, bổ củi, gặt lúa, gánh hàng, hút điếu cày,
  phe phẩy quạt, đọc sách, nấu ăn, cho gà ăn...): nhân vật làm việc đó lúc không ai
  nói; **lúc có người nói chuyện thì mọi người ngừng tay** (chống cuốc xuống đất,
  thôi rít điếu, thôi uống) để nói / nghe cho khỏi vung cuốc vào người hay vừa ngậm
  điếu vừa nói; nói xong lại làm tiếp, tới khi có hành động khác. Đồ đang cầm không
  tự biến mất: làm việc khác thì một tay vẫn cầm, chống xuống. Đạo cụ tự có theo việc: cuốc, chổi, rìu,
  liềm, đòn gánh hai thúng, điếu cày, quạt nan, sách, nồi...
- **Đồ đạc của cảnh** (dòng "+ Đồ đạc"): giường tre, chõng, ghế tựa, bàn (có ấm
  chén), chiếu, bếp lửa (lửa bập bùng), chum nước. Nhân vật **nằm** (ốm, ngủ, chết)
  tự đi tới nằm lên giường / chiếu (cảnh chưa có thì tool tự kê), **ngồi** tự ngồi
  lên chõng / ghế gần nhất. Kể chuyện cũng nằm trên giường / chiếu.
- **Âm thanh** chỉ có giọng nói (thoại + người kể): không lồng tiếng động, tiếng nền.
  Muốn có nhạc nền thì chọn ở Cài đặt → Nhạc nền, hoặc thêm trong CapCut.
- **Xuất CapCut** (nút cạnh "Tải mp4" khi phim đã dựng): tạo dự án CapCut gồm video
  không tiếng, **mỗi câu thoại một đoạn giọng**, mỗi nhân vật (và người kể) một track
  riêng, phụ đề thành track chữ sửa được (khi chưa bật phụ đề in sẵn lên hình). Cần
  chọn dự án CapCut mẫu ở Cài đặt như khi xuất phim hài. Đóng CapCut rồi mở lại để
  thấy dự án mới.
- **Xoá truyện / phim**: nút **🗑 Xoá** cạnh "+ Truyện mới" chuyển truyện đang mở vào
  **thùng rác** (data/thung_rac), khôi phục được trong **30 ngày**: chọn trong ô
  "Thùng rác" rồi bấm **↩ Khôi phục**. Quá 30 ngày mới xoá hẳn. Đang dựng thì không xoá.
- **Kiểu nhân vật đã lưu**: mỗi lần tải ảnh nhân vật mẫu, nét vẽ và ngoại hình Claude
  rút ra được lưu riêng vào thư viện (data/library/kieu_nhan_vat), không nằm trong
  truyện nữa — xoá truyện không mất. Ô **Kiểu nhân vật** của mọi truyện có thêm các
  dòng **"Đã lưu: ..."** để chọn lại, khỏi tải ảnh và chờ Claude xem lại. Truyện cũ
  có ảnh mẫu được tự lưu vào thư viện khi mở màn hình Truyện kể.
- **Máy quay tự đổi góc**: toàn cảnh khi mở cảnh và khi người kể nói, hai người
  khi đối đáp, cận mặt người đang nói, lia theo người đi lại; đẩy máy rất chậm
  cho đỡ đơ.
- Mục 3 hiện từng cảnh với ảnh xem trước, địa điểm, ngày / đêm và danh sách nhịp:
  đổi loại, người, hành động, "với ai / tới đâu", đồ cầm, câu nói; **↑** đưa nhịp
  lên trước, **✕** bỏ, **+ Nhịp** thêm. Bấm **Lưu thay đổi** để ảnh xem trước vẽ lại.
- Bối cảnh vẽ tay hoặc 3D, giọng từng nhân vật, phụ đề, nhạc nền dùng như Kể
  chuyện. Chỗ đứng: sát mép trái, bên trái, giữa, bên phải, sát mép phải, ngoài
  khung trái / phải (để đi vào sau).
- **Cho hình hợp lý** (sửa theo danh sách lỗi phim Lão Hạc):
  - Nằm: duỗi thẳng trên giường / chiếu, **đắp chăn**; đứng dậy thì **ngồi dậy
    trước** rồi mới đứng, nằm xuống cũng ngồi rồi ngả lưng từ từ.
  - Ngồi: mỗi chõng **2 chỗ**, ghế 1 chỗ, ai cũng ngồi đúng chỗ trên chõng (không
    ngồi trên không, không ngồi đè lên nhau); hết chỗ thì ngồi ghế đẩu tre, cách
    xa người khác. Đang ngồi / nằm mà phải đi thì đứng dậy trước.
  - Bếp lửa, chum nước, bàn tự dời ra chỗ không ai đứng / ngồi, nằm trọn trong khung.
  - Cuốc, rìu, chổi: lưỡi luôn đúng chiều, giơ cao thì ra sau đầu (không xuyên
    mặt); đang làm thì **quay lưỡi về phía trống**, không bổ vào người hay con chó;
    người khác đi tới thì đứng ngoài tầm cuốc. Cầm mà không làm thì chống xuống đất.
  - Đạo cụ theo việc cầm từ lúc bắt đầu tới khi đổi việc (không lúc có lúc không),
    tên đồ được chuẩn hoá (bát luôn là cùng một cái bát); nằm thì bỏ đồ xuống.
  - Chó được cho ăn, vuốt ve thì vui (không cau mày); chó vẽ trước người nên bát,
    điếu luôn ở trước chó; người đứng cách nhau theo bề ngang (chó dài hơn người).
  - Máy quay không cắt ai làm đôi ở mép khung; người ngoài khung không lòi đồ cầm vào mép.
  - Chuyển cảnh **mờ qua màn đen** (không còn "bóng ma" hai cảnh chồng nhau).
  - **Không có chữ giới thiệu** tên truyện hay thẻ chương: vào thẳng cảnh đầu, các
    chương nối liền mạch. Nhân vật lần đầu lên hình có **thẻ tên** nhỏ trên đầu 2,5 giây.
  - Uống trà: chén đưa kề đúng miệng; hút điếu cày: miệng kề đúng đầu ống điếu;
    ăn: tay và lên tận miệng.
  - **AI kiểm tra hình khớp lời**: viết xong mỗi chương, AI đọc lại từng câu thoại và
    lời kể: câu nào tả ai làm gì thì phải có đúng hành động đó của đúng người đó (diễn cùng
    lúc nếu cần), người được nhắc phải có mặt, đồ vật được nhắc phải có (đồ cầm tay / đồ
    đạc trong cảnh). Thiếu thì AI tự thêm nhịp hành động, thêm nhân vật. Bước này chỉ thêm
    / sửa hành động, đồ vật — không đổi lời thoại, lời kể.
  - **Bối cảnh thiếu gì thì tool vẽ thêm**: cảnh cần đồ chưa có (bàn thờ, chuồng chó, giếng
    nước, cối giã gạo, cây khế, xe đạp, bát hương...) thì AI tự vẽ thêm đồ đó (loại **Đồ đạc,
    vật dựng trong cảnh** hoặc **Đồ vật cầm tay**), đặt vào cảnh và lưu vào thư viện cho
    truyện sau dùng lại. Tự vẽ thêm bằng tay ở mục "Vẽ thêm bằng AI" cũng được; đồ đạc AI
    vẽ có trong danh sách "+ Đồ đạc" của từng cảnh (đánh dấu "AI vẽ").
  - **Hành động khớp lời**: lời kể nhắc tên ai (vd "Thằng Mục với thằng Xiên xông ra
    túm lấy cậu Vàng...") thì nhịp hành động ngay sau của đúng người đó được diễn
    **cùng lúc** với lời kể, không đợi kể xong. AI được dặn: lời kể / thoại nói ai làm
    gì thì phải có người đó trong cảnh và có hành động đúng việc đó; thiếu vai phụ (thằng
    Mục, thằng Xiên...) thì AI tự thêm nhân vật. Nhịp có "with_prev" diễn cùng lúc nhịp trước.
  - Động tác bắt / bế: **túm lấy** (grab: xông tới chồm túm, con vật giãy giụa, người bị
    túm thì run), **bế lên** (lift: con vật nằm trước ngực, đi đâu bế theo đó), **dốc
    ngược** (lift_upside: túm hai chân sau, con vật treo đầu chúc xuống, giãy giụa).
    Nhiều người cùng xông tới một chỗ thì tự đứng tách ra, không chồng lên nhau.
  - **Tắm cho chó / mèo** (hành động "bathe"): người đi lại sát con vật, cúi kỳ cọ;
    con vật đứng trong chậu nước, bọt xà phòng bay lăn tăn, lâu lâu rùng mình. "Làm việc
    bằng tay" (work) không còn tự cầm cuốc nữa — cuốc chỉ có khi cuốc đất.
  - **Chó mèo vẫy đuôi**: đuôi vẫy tít khi vui, được vuốt ve, ăn, tắm hay đi lại; đứng
    yên thì phe phẩy chậm; buồn, sợ thì cụp đuôi. Có thêm hành động "wag" (vẫy đuôi
    mừng, mông lắc theo) cho AI hoặc chị chọn ở nhịp.
  - Người xoa đầu, cho ăn, tắm, ôm, đưa đồ thì **đứng sát** con vật / người kia để tay
    chạm tới (trước đây đứng xa quá).
  - **Hút thuốc lào**: rít một hơi khoảng 2 giây rồi hạ điếu, 9–13 giây sau mới rít
    tiếp (không rít liên tục). **Uống trà**: nhấp một ngụm rồi hạ chén, 7–9 giây sau
    mới nhấp tiếp.
  - **Cho chó / mèo ăn**: người chìa bát, đặt bát xuống đất trước mõm, con vật mừng
    rồi cúi đầu ăn (thân đứng yên, chỉ đầu cúi xuống bát), nhai nhóp nhép (ăn tới khi có việc khác, vuốt ve cũng không làm
    nó bỏ ăn). Nhịp "eat" cho chó mèo tự ăn thì tool tự đặt bát trước mõm.
  - Tên chương có "đêm / tối" thì cảnh là ban đêm (trừ lời kể nói rõ sáng, trưa).
  - Cảnh không bao giờ trống: ai cũng đến sau thì người đầu tiên đi vào ngay.
  - Cánh đồng có lúa (gặt mới hợp).
- **Âm thanh**:
  - Mỗi nhân vật **một giọng khác hẳn**: tool đo cao độ giọng mẫu, đàn ông không
    ra giọng cao như nữ / trẻ con, các giọng không trùng cao độ (thử giọng khác nếu
    trùng). Hai nhân vật cùng kiểu (vd hai ông trung niên) tự đổi cao độ.
  - **Người kể** chưa chọn giọng riêng thì dùng giọng nữ trầm ấm (truyện nhiều
    nhân vật nam) để không lẫn với nhân vật. Muốn giọng khác: chọn ở mục 1.
  - Mọi câu thoại, lời kể **to ngang nhau**; câu nói lúc khóc run run, nghẹn, có
    tiếng sụt sịt.
  - Hai người nói qua lại có **khoảng nghỉ** để biết ai nói câu nào; miệng nhép cả
    lúc nói nhỏ.
- AI viết kịch bản theo thêm luật: khách / hàng xóm không làm việc nhà người khác,
  mỗi câu thoại đúng một người nói, nhân vật đã bán / chết / đi xa không xuất hiện
  lại (trừ hồi tưởng), người đang ngủ không nói.

### Thoại nhân vật xen giữa lời kể
Kể suốt dễ chán, nên ô **Thoại nhân vật** (mục 1) cho AI chèn câu nói của nhân vật:
**Thỉnh thoảng** (mặc định, khoảng 1/4 số cảnh, lúc cảm xúc cao), **Nhiều** (đối
đáp, khoảng nửa số cảnh) hoặc **Không**. Có nguyên văn thì AI lấy đúng câu thoại
trong truyện.

- Câu thoại đọc bằng **giọng riêng của nhân vật** (khác giọng người kể), ngay sau
  lời kể của cảnh; lời kể dẫn vào ("lão bảo...") rồi để nhân vật tự nói.
- Giọng mỗi nhân vật chọn ở mục 2: giọng trong Thư viện, hoặc mô tả giọng (tool
  tự đặt theo tuổi, giới: vd lão Hạc "male, elderly, low pitch"). Một nhân vật
  giữ một giọng suốt truyện.
- Mỗi cảnh ở mục 3 có danh sách câu thoại: đổi người nói, sửa câu, **+ Câu thoại**
  để thêm, ✕ để bỏ. Người nói chưa có trong cảnh thì tự được đưa vào cảnh.
- Lúc nhân vật nói: nhân vật đó nhép miệng theo giọng, phụ đề hiện "Tên: câu nói".
- Con vật không có thoại.

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

---

## 13. Truyện webtoon (tab riêng)

Truyện tranh động kiểu kênh kể chuyện webtoon Hàn ("썰"): nhân vật vẽ kiểu **người
thật** (tỉ lệ người lớn, nét đen mảnh, màu phẳng, mắt trắng chấm đen, mũi hai nét),
phần lớn là **cận mặt**, đối thoại liên tục, hay chèn **màn hình điện thoại**. Video 16:9.

### Các bước
1. **Câu chuyện:** gõ **Yêu cầu** (vd *"Một ông bố nối wifi miễn phí ở công viên rồi bị
   lừa là con gái bị bắt cóc"*), chọn **Thể loại** (giật gân / lừa đảo, kinh dị, hài, tình
   cảm, gia đình, trả thù thoả mãn, công sở, học đường, bí ẩn), **Ngôn ngữ thoại** (mặc định
   **tiếng Hàn**: tên tập, thoại, tin nhắn trên điện thoại đều bằng tiếng Hàn; chọn được Việt, Anh), **Thời lượng**, **Phần số**. **Cuối phần**: *bỏ lửng ở cao trào* để làm
   series (phần 2 thì dán tóm tắt các phần trước vào ô dưới), hoặc *kết trọn vẹn*.
   - **Ý tưởng tham khảo** (ngay dưới ô Yêu cầu): chọn thể loại (hoặc Mọi thể loại), bấm
     **Gợi ý ý tưởng mới** — AI nghĩ 6 ý tưởng khác nhau (tên tập, câu móc, diễn biến, cú lật).
     Mỗi lần bấm là một loạt mới, tool nhớ các ý đã gợi ý để không lặp lại. Bấm **Dùng ý này**
     để điền vào ô Yêu cầu.
2. Bấm **AI viết truyện & phân cảnh**. AI:
   - nghĩ câu chuyện, tên tập, móc câu mở đầu;
   - tạo nhân vật (ngoại hình cố định, mỗi người một vẻ) và địa điểm (người gọi điện ở chỗ
     khác thì có nơi riêng);
   - viết **danh sách cảnh quay**: mỗi câu thoại một cảnh, ghi ai nói, ở đâu, nét mặt, tư thế
     tay, hướng nhìn, góc máy, chỗ chèn màn hình điện thoại và nội dung trên màn hình.
3. **Nhân vật & địa điểm** (mục 2): đổi giới, tuổi, kiểu tóc, màu tóc, áo, màu áo, quần, da,
   kính; ảnh nhỏ vẽ lại ngay. Ô **Giọng** là mô tả giọng (vd `female, young adult, moderate pitch`).
4. **Phân cảnh** (mục 3): mỗi dòng một cảnh quay — loại cảnh (cận mặt, nửa người, toàn cảnh,
   hai người, màn hình điện thoại, màn đen), địa điểm, nhân vật, nét mặt, tư thế, hướng
   nhìn, góc máy, người nói và câu nói. Cảnh màn hình điện thoại có ô nội dung (dạng JSON):
   tin nhắn, cuộc gọi, danh sách wifi, thông báo, cảnh báo chữ đỏ có đếm ngược, gọi video
   (thấy mặt người bên kia), nhiễu sóng, màn hình khoá, đang tải. **↑** đưa lên, **✕** bỏ,
   **+ Cảnh quay** thêm. Bấm **Lưu**; bấm ảnh nhỏ để xem lớn.
5. **Dựng video**: OmniVoice đọc từng câu, tool vẽ từng khung. **Mỗi nhân vật một giọng
   khác nhau**, giữ nguyên cả truyện: ô Giọng để trống thì tool tự chọn theo tuổi, giới; hai
   người cùng tuổi cùng giới thì tool đổi cao độ, đo giọng mẫu và tạo lại nếu hai giọng nghe
   giống nhau; đàn ông không bị giọng cao như nữ; người kể khác hẳn giọng nhân vật. Muốn giọng
   cụ thể thì gõ mô tả (vd `male, elderly, very low pitch`) hoặc chọn giọng trong Thư viện.

### Cách kể: 사연 (mặc định) hoặc toàn thoại
- **Kể chuyện 사연** (như các kênh 썰 Hàn): nhân vật chính tự kể chuyện đời mình ở ngôi thứ
  nhất ("저는 결혼 4년차...", đuôi -요), lời kể chiếm khoảng 35–45% số câu, xen kẽ thoại của
  nhiều người (mẹ chồng, chồng, đồng nghiệp...). Truyện có nhiều chuyện nhỏ leo thang → nhân
  vật chính lên tiếng (사이다) → kết và một câu ngẫm nghĩ. **Lời kể đọc bằng chính giọng nhân
  vật chính** và nhân vật đó nhép miệng khi kể — nếu ô **Giọng lời kể** chọn *Lời kể dùng giọng
  nhân vật chính*. Mặc định là *Giọng riêng cho người kể*: người kể có giọng riêng khác hẳn mọi
  nhân vật (cùng giới, cùng tuổi với nhân vật chính vì vẫn kể "저는...", nhưng cao độ / chất
  giọng khác; tool đo cao độ để không trùng ai), lúc kể nhân vật không nhép miệng (như lồng tiếng).
- Mở đầu / chuyển chuyện mới: cảnh cận nhân vật chính trên **nền trơn có vòng sáng** (địa
  điểm "Nền kể chuyện", tool tự vẽ). Hai người ngồi bàn: **mép bàn + cốc cà phê** che phía
  trước; trên giường: **đầu giường, gối, chăn đắp**.
- **Đạo cụ** (AI tự chọn đúng chuyện đang kể; sửa ở ô *Đạo cụ* của từng cảnh quay):
  bàn cà phê + cốc, **bàn ăn** (bát cơm, bát canh, đũa, đĩa thức ăn), **giường** (đầu giường,
  gối, chăn), **trong xe** (ghế, khung cửa, vô lăng trước người lái), **bàn làm việc + laptop**,
  **ghế sofa + bàn trà**. Đồ cầm tay qua tư thế: **bế con**, **cầm cốc**, **cầm giấy tờ**,
  áp / xem điện thoại. Câu lệnh vẽ ảnh AI nhân vật cũng có các tư thế này.
- **Toàn thoại**: kiểu cũ, gần như chỉ có thoại.
- Thể loại mới **Hôn nhân / nhà chồng (사연)**; ô Ý tưởng tham khảo cũng gợi ý theo kiểu kể đã chọn.
- Ô **Nền** mặc định **Tranh nền 2D kiểu webtoon** (phẳng, nét mảnh, màu pastel như video
  mẫu); chọn *Nền 3D* nếu muốn. Đổi kiểu nền thì vẽ lại ảnh nền.
- Câu lệnh vẽ ảnh nhân vật (mục 2b) đã dặn đúng nét như video mẫu: viền đen rõ, màu phẳng,
  mắt bầu dục đen to, không đổ bóng. Phụ đề: chữ trắng to viền đen.

### Làm series (phần 2, 3...)
- Viết xong truyện, ô **Nội dung tập này** tự có tóm tắt tập đó (tên tập, diễn biến, tập dừng
  ở đâu, nhân vật). Chị sửa thêm được. Tập làm từ bản cũ chưa có thì bấm **Tóm tắt bằng AI**.
- Bấm **Làm phần tiếp theo →**: tool tạo tập mới, **phần số +1**, ô *Tóm tắt các phần trước*
  = tóm tắt cũ + nội dung tập này, ô Yêu cầu ghi sẵn "viết tiếp". Tập mới **giữ nguyên**
  nhân vật (ngoại hình, giọng đọc), địa điểm, ảnh AI nhân vật và nền 3D của tập trước.
- Khi viết phần sau, AI được dặn giữ y nguyên nhân vật và địa điểm cũ, chỉ thêm người / nơi
  mới nếu truyện cần.

### Nền 3D đúng bối cảnh (mục 2, phần địa điểm)
- Khi viết truyện, AI tả **từng địa điểm đúng như trong truyện** bằng tiếng Anh (ô dưới tên
  địa điểm, vd *a small public restroom inside a Seoul subway station, white tiled walls,
  flickering fluorescent light*). Chị sửa ô này cho đúng ý rồi bấm **Lưu**.
- Ô **Nền**: *Nền 3D* (mặc định) hoặc *Nền vẽ tay của tool (2D)*.
- Mỗi địa điểm có ô ảnh nền **ban ngày / ban đêm** (theo cảnh dùng tới). Hai cách có nền 3D:
  - **Tool tự vẽ trên máy** (cần card NVIDIA, đã chạy `cai_3d.bat`): bấm **Tool vẽ 3D** từng
    ô, hoặc **Vẽ nền 3D cho mọi địa điểm còn thiếu**; khi **Dựng video** tool cũng tự vẽ chỗ
    còn thiếu. Mỗi ảnh 20–60 giây. Chưa ưng thì **Tool vẽ lại** (ra ảnh khác).
  - **Tự vẽ bằng Gemini / ChatGPT**: bấm **Chép câu lệnh nền**, dán vào, tải ảnh về rồi
    **Tải ảnh nền**.
- Mỗi địa điểm chỉ một ảnh ngày, một ảnh đêm, dùng lại cho mọi cảnh ở đó nên căn phòng giống
  nhau suốt truyện. Thiếu ảnh đêm thì tool lấy ảnh ngày làm tối đi; chưa có ảnh nào thì dùng
  nền vẽ tay. Cận mặt thì nền tự mờ, tối như video mẫu.

### Lời mời chia sẻ cuối video (mục 1, mặc định: Có)
AI viết thêm 2–3 câu cuối, do người kể nói, để người xem muốn chia sẻ và bình luận. Câu
viết khéo và gắn với đúng câu chuyện vừa kể:
- Cho người xem lý do để chia sẻ: giúp người thân tránh chuyện tương tự, gửi cho người
  mình thương, rủ bạn bè cùng phân xử ai đúng ai sai.
- Có một câu hỏi người xem muốn trả lời ("Nếu là bạn, bạn có tha thứ không?").
- Truyện bỏ lửng thì vẫn hẹn phần sau trước rồi mới mời chia sẻ.
- Không dùng câu cụt kiểu "like, share, subscribe", không lặp câu giữa các video.
Không muốn có đoạn này thì chọn **Không**. Câu viết ra sửa được trong danh sách cảnh quay
như mọi câu thoại khác.

### Nét vẽ nhân vật (mục 1, ô "Nét vẽ nhân vật")
Chọn nét vẽ cho ảnh nhân vật AI của truyện. Câu lệnh vẽ ở mục 2b (và file câu lệnh) đổi
theo nét đã chọn:
- **사연 썰툰** (mặc định): người thật, viền đen đều, màu phẳng — như các kênh 썰 / 사연.
- **Mochi 둥글이**: đầu bánh gạo to, mắt chấm, má hồng, miệng ω, thân nhỏ mũm mĩm.
- **Webtoon 웹툰**: người mảnh chân dài, mặt cằm V, mắt to long lanh, đổ bóng một tông.
- **Manhwa bán thực**: tỉ lệ người thật, mặt chi tiết, mắt sắc, đổ bóng hai tông.
- **Gợi ý theo thể loại**: chọn thể loại thì dưới ô hiện gợi ý (Hài, Gia đình → Mochi;
  Tình cảm, Học đường, Công sở → Webtoon; Giật gân, Kinh dị, Bí ẩn → Manhwa; Nhà chồng,
  Trả thù → 사연 썰툰). Bấm **Dùng nét này** mới đổi.
- **Thêm nét vẽ mới**: mở **＋ Thêm nét vẽ mới**, đặt tên, mô tả nét vẽ (nên viết tiếng
  Anh, vd "cute 3D Pixar style, big round eyes, soft lighting"), tick thể loại hợp rồi
  **Lưu nét vẽ**. Nét này có ngay trong ô của mọi truyện webtoon (dấu ★), xoá được ở
  cùng chỗ. Lưu ở data/library/webtoon_styles.json.
- Đổi nét khi đã có ảnh: ảnh cũ vẫn giữ, nhưng được đánh dấu **"Ảnh vẽ theo nét cũ"** —
  chép câu lệnh mới vẽ lại để cả truyện cùng một nét. Làm phần tiếp theo thì giữ nét cũ.
- Nhân vật chưa có ảnh AI thì tool vẫn tự vẽ bằng nét webtoon có sẵn như trước.

### Ảnh nhân vật vẽ bằng AI (mục 2b, không bắt buộc)
Muốn nhân vật đẹp như tranh thật thì dùng ảnh vẽ bằng Gemini / ChatGPT; mỗi cảnh là một
khung tranh đứng yên, tool chỉ **nhép miệng** theo giọng và **chớp mắt** (kiểu kênh 썰).
1. Sau khi AI viết phân cảnh, mục 2b liệt kê đúng những ảnh cần cho từng nhân vật:
   mỗi tư thế dùng trong truyện (áp điện thoại, xem điện thoại, ôm đầu...) và vài nét mặt
   mạnh (sốc, khóc, giận... — ghi "nên có"). Ô **Tay buông** là ảnh gốc, vẽ trước tiên.
2. Bấm **Chép câu lệnh vẽ**, dán vào Gemini / ChatGPT. Từ ảnh thứ hai trở đi **gửi kèm ảnh
   gốc** để AI giữ đúng khuôn mặt, tóc, quần áo. Câu lệnh đã dặn nền **xanh lá** (phông xanh):
   tool xoá nền sạch cả những khoảng hở giữa tay và người.
3. Bấm **Tải ảnh lên**: tool tự xoá nền, cắt sát người, tự tìm hai mắt và miệng.
   Bấm vào ảnh để kiểm tra: vòng xanh là mắt, vòng hồng là miệng; sai thì **Bấm lại từ đầu**
   rồi bấm lần lượt mắt bên trái, mắt bên phải, giữa miệng → **Lưu điểm**.
   Tool tìm được cả mắt sau kính và tranh vẽ kiểu gần người thật. Không chắc chỗ miệng thì
   ô ảnh báo chữ cam và tool **không vẽ miệng nhép** (thà không nhép còn hơn vẽ sai chỗ) —
   bấm vào ảnh để đánh dấu là xong.
   - **Ảnh miệng mở** (không bắt buộc, nên dùng với tranh kiểu người thật): bấm **Chép câu
     lệnh miệng mở**, gửi KÈM ảnh gốc của ô đó cho Gemini / ChatGPT để AI sửa đúng ảnh đó cho
     mở miệng, rồi bấm **Tải ảnh miệng mở**. Tool tự căn khớp hai ảnh; khi nói, tool lấy miệng
     thật trong ảnh này hoà vào thay cho miệng vẽ — trông tự nhiên hơn hẳn. Báo "lệch nhiều"
     thì nhờ AI sửa lại, dặn giữ nguyên khung hình.
4. Dựng video như thường. Cảnh nào thiếu ảnh đúng tư thế thì tool lấy ảnh gần nhất của nhân
   vật đó (cùng tư thế → ảnh gốc); nhân vật chưa có ảnh nào thì tool tự vẽ như cũ.
- Mẹo: ảnh nhìn thẳng, thấy rõ hai mắt, miệng ngậm; nhân vật không mặc đồ màu xanh lá.

### Trên hình có gì
- **Nhép miệng** theo giọng từng câu, **chớp mắt**, **thở**, đầu **lắc / nghiêng** nhẹ khi nói.
- **Tay mềm, khớp liền**: cả cánh tay + bàn tay là một khối, chỉ có viền ngoài; khuỷu tay
  tròn; giữa các ngón chỉ có nét mảnh. Đổi tư thế thì khuỷu đi trước, bàn tay theo sau hơi
  vượt rồi dừng; tay đung đưa nhẹ theo nhịp thở.
- **Tay đổi tư thế mượt** khi sang câu khác: áp điện thoại lên tai, cầm xem điện thoại, ôm
  đầu, hai tay ôm đầu, che mặt, khoanh tay, chỉ, vẫy, chống nạnh, nhún vai...
- Nét mặt: lo lắng, sốc, sợ hãi (run, vạch sọc trên trán), buồn, khóc (nước mắt), giận, vui,
  cười to, nhếch mép, mệt mỏi, suy nghĩ, tuyệt vọng; thêm mồ hôi, quầng thâm, vết bầm, má hồng.
- Người **đi vào khung**; **máy quay** đẩy vào, lùi ra, lia, rung khi sốc.
- Cận cảnh thì **nền mờ tối** như video mẫu; phụ đề trắng nền đen phía dưới.
- Gọi điện: mỗi câu cận mặt người đang nói ở đúng nơi của người đó.

### Lưu ý
- **Dựng nhanh:** tool chia video cho nhiều nhân CPU vẽ song song (tối đa 8), rồi ghép lại;
  máy có card NVIDIA thì **nén video bằng card (NVENC)** cho CPU rảnh để vẽ (khi đó tối đa 3
  luồng vì card GeForce chỉ cho vài luồng nén cùng lúc). Muốn luôn nén bằng CPU: đặt
  `"video_encoder": "cpu"` trong data/settings.json. Phần vẽ nhân vật / nét vẽ luôn chạy
  trên CPU. Cảnh dùng ảnh AI nhân vật dựng nhanh hơn hẳn nhân vật tool tự vẽ.
- Bối cảnh dùng các mẫu vẽ có sẵn của tool (phòng khách, phòng ngủ, văn phòng, đường phố,
  công viên...). Thứ chưa có (ga tàu, bệnh viện, xe hơi...) thì chọn mẫu gần nhất.

## 14. 2ch (tab riêng): video dọc 9:16 kiểu Shorts Nhật

Giống các video Shorts Nhật kiểu 2ch / 昭和 / 感動: thanh tiêu đề đen 2 dòng chữ cam phát
sáng cố định ở trên, mỗi câu một hình (nhân vật viền trắng kiểu sticker trên nền mờ), chữ
to viền trắng (lời kể màu xanh, câu nói trong 「」 màu theo người nói), giọng đọc tiếng Nhật
liền mạch, hình nảy nhẹ khi đổi cảnh, máy quay đẩy vào chậm.

1. **Câu chuyện**: gõ yêu cầu (tiếng Việt cũng được), chọn thể loại (感動, 昭和, スカッと,
   義実家, 職場…), thời lượng, giọng đọc (mỗi nhân vật một giọng, hoặc một người kể đọc tất
   cả), lời mời chia sẻ cuối video. Tiêu đề 2 dòng để trống thì AI đặt. Bấm **AI viết
   truyện & chia cảnh**: AI viết tiếng Nhật theo khuôn hook → hoàn cảnh → chi tiết cài cắm →
   cú lật, mỗi câu một cảnh, tự chọn hình cho từng câu.
2. **Nhân vật & ảnh vẽ bằng AI**: mỗi nhân vật liệt kê các nét mặt truyện dùng. Bấm
   **Chép câu lệnh vẽ** → dán vào Gemini / ChatGPT (vẽ ảnh "bình thường" trước; các nét mặt
   sau gửi kèm ảnh đó để giữ đúng mặt) → **Tải ảnh lên** (tool tự xoá nền xanh / trắng).
   Nét mặt nào chưa có ảnh thì dùng ảnh khác của nhân vật đó; chưa có ảnh nào thì tool tự
   vẽ nhân vật kiểu Mochi tròn mũm mĩm đúng nét mặt.
3. **Kho nhân vật có sẵn**: 5 hình đi kèm tool (dìu bà cụ, bố dạy con học, chơi bóng rổ,
   giành đồ chơi, cảnh sát bắt người). Thêm hình vào kho: đặt tên, tả hình, bấm **+ Thêm
   hình vào kho** rồi chọn ảnh. AI viết truyện tự dùng hình trong kho khi đúng nội dung câu.
   Hình chị thêm lưu ở data/library/2ch_kho/.
4. **Địa điểm**: nền tool tự vẽ (làm mờ). Muốn nền đẹp: **Chép câu lệnh nền** (ảnh dọc
   9:16) → vẽ bằng AI → **Tải ảnh nền**.
5. **Các cảnh**: sửa câu (Enter để xuống dòng), người nói, hình (nhân vật / hai người / hình
   trong kho / đồ vật), nét mặt, địa điểm, hiệu ứng (giọt mồ hôi, nổi gân, rung hình, nước
   mắt, suy nghĩ, zzz). Cảnh đồ vật: **Chép câu lệnh vẽ đồ vật** rồi **Tải ảnh riêng cho
   cảnh** (chưa có ảnh thì giữ hình cảnh trước). Cảnh nào cũng tải được ảnh riêng. Bấm ảnh
   nhỏ để xem lớn. Sửa xong bấm **Lưu các cảnh**.
6. **Dựng video**: đọc giọng tiếng Nhật rồi dựng video 1080×1920.
8. **Phong cách ảnh nhân vật** (mục 2): mặc định **Minh hoạ phẳng dễ thương** — giống 5 hình
   có sẵn (đầu tròn, mắt chấm, má hồng, viền màu mềm có vân bút chì, màu phẳng không đổ
   bóng). Hoặc chọn **Chibi anime** như video mẫu 昭和. Bấm **Tải ảnh mẫu nét vẽ** (5 hình có
   sẵn ghép lại): khi vẽ ảnh **bình thường** của mỗi nhân vật, gửi kèm ảnh mẫu này rồi dán câu
   lệnh để AI vẽ đúng nét; các nét mặt sau gửi kèm ảnh bình thường của chính nhân vật đó.
9. **Giọng và nhạc nền giống video mẫu**:
   - **Giọng người kể**: để trống thì tool tự chọn như video mẫu — giọng **nam trưởng thành,
     trầm ấm kể chuyện** (truyện xưng 俺 / 僕, hoặc nhân vật chính là nam); nhân vật chính là nữ
     thì giọng nữ ấm. Muốn giọng riêng: chọn giọng có sẵn trong **Thư viện** (ô Giọng người kể)
     hoặc gõ mô tả. Từng nhân vật cũng chọn được giọng trong Thư viện (mục 2).
   - **Mô tả giọng do tool tự điền**: sau khi AI viết truyện, ô mô tả giọng của người kể và
     từng nhân vật được điền sẵn (giới, tuổi, cao độ — vd ông chủ "male, elderly, low pitch", người
     mẹ "female, middle-aged, moderate pitch"), không ai trùng giọng ai, không trùng người kể.
     Sửa được; xoá trống thì tool tự điền lại. Bộ đọc giọng chỉ hiểu các từ: male / female,
     child / teenager / young adult / middle-aged / elderly, very low / low / moderate / high /
     very high pitch, whisper.
   - **+ Tải giọng mẫu** (cạnh ô Giọng người kể và ở từng nhân vật): chọn file giọng (wav / mp3,
     5–15 giây, một người nói rõ, không nhạc), đặt tên — tool tự nghe chữ trong đoạn mẫu, lưu
     vào Thư viện giọng và chọn luôn. Lần sau chọn lại trong ô, dùng cho mọi video.
   - **Nhịp đọc liền** như video mẫu: nghỉ giữa các câu khoảng 0,15 giây. Ô **Tốc độ đọc**:
     Bình thường / Hơi nhanh.
   - **Nhạc nền** (mặc định không có): bấm **+ Thêm nhạc** chọn file mp3 / wav / m4a / ogg
     (nhạc chị có quyền dùng), chọn bài trong ô **Nhạc nền**, **▶ Nghe** để nghe thử, chọn
     **Âm lượng nhạc**. Nhạc phát nhỏ dưới giọng, tự nhỏ đi khi có lời, vào / ra nhỏ dần, lặp
     lại cho đủ dài. Nhạc lưu ở data/library/nhac_nen/, dùng cho mọi video.
   - Không nên lấy giọng từ video của kênh khác để nhân bản — dùng bản thu của chị hoặc
     giọng có bản quyền rồi tải vào Thư viện giọng.
7. **Tải tất cả câu lệnh một lần** (như tab Webtoon): mục Nhân vật (tất cả nhân vật, hoặc
   từng nhân vật), mục Địa điểm (ảnh nền) và mục Các cảnh (ảnh đồ vật) đều có nút **Tải file
   câu lệnh** — mỗi dòng một câu lệnh, chỉ những ảnh còn thiếu, đúng thứ tự các ô — để dán
   vào công cụ tạo hàng loạt. Vẽ xong bấm **Tải nhiều ảnh cùng lúc**, chọn hết các ảnh: ảnh
   tải về trước điền vào dòng trước.
