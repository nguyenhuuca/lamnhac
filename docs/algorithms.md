# Các thuật toán trong lamnhac

Tài liệu này giải thích *cách* lamnhac biến âm thanh thành tab và *vì sao* chọn cách đó. Quy tắc chính xác có mã số B1–B21 nằm trong [spec](specs/spec-mp3-to-guitarpro.md). Ở đây mỗi mục đều dẫn về mã số tương ứng.

```
MP3 ─[1]─► AudioClip ─[2]─► NoteEvent[] ─[3]─► RhythmInfo ─[4]─► Score ─[5]─► TabScore ─[6]─► .gp5 / .musicxml
     decode         nhận nốt          phách/tempo      lượng tử hoá    gán dây/phím      xuất file
```

Mỗi bước chỉ nhận và trả dữ liệu thuần định nghĩa trong `models.py`, nên có thể thay riêng một bước, ví dụ đổi model nhận nốt, mà không sửa các bước còn lại.

**Đơn vị thời gian:** sau bước 4, thời gian không còn đo bằng giây mà bằng **slot = một nốt móc kép (1/16 nốt tròn)**. Một phách nốt đen là 4 slot. Một ô nhịp có `numerator × 16 / denominator` slot: 4/4 là 16, còn 3/4 và 6/8 đều là 12.

---

## 1. Đọc và giải mã audio (`audio.py`, B1–B2)

**Mục tiêu:** ra tín hiệu mono 22 050 Hz dạng `float32`, đồng thời chặn file độc hại.

1. **Kiểm tra trước khi giải mã**, theo thứ tự và dừng ở lỗi đầu tiên: file có tồn tại không → có phải file thường không → đuôi có phải `.mp3` không → kích thước ≤ 50 MB → đọc được header không (`soundfile.info`) → thời lượng ghi trong header ≤ 600 s.
2. **Giải mã theo khối 1 giây** bằng `soundfile.blocks`, có đếm số mẫu. Header của MP3 VBR có thể khai sai thời lượng: một file khai 2 phút có thể chứa cả giờ âm thanh. Vì vậy vượt **605 s** thực tế là dừng ngay, kể cả khi header nói khác (chống tấn công làm cạn tài nguyên, CWE-400).
3. **Trộn stereo xuống mono** bằng trung bình hai kênh, rồi **resample** về 22 050 Hz bằng `librosa.resample`. 22 050 Hz là tần số basic-pitch dùng.

Bước này cố ý **không** fallback sang ffmpeg/audioread, để hành vi giống nhau trên mọi máy. libsndfile 1.2 đi kèm `soundfile` đã tự đọc được MP3.

## 2. Nhận nốt: chuyển âm thanh thành nốt (`transcribe.py`, B3–B4)

Dùng **[basic-pitch](https://github.com/spotify/basic-pitch)** của Spotify. Đây là một mạng neural nhỏ, khoảng 17 nghìn tham số, được huấn luyện để chép nhạc **đa âm**, tức nhận được nhiều nốt vang cùng lúc như hợp âm.

Cách hoạt động, ở mức tổng quát:
- Âm thanh được đổi sang biểu diễn **CQT có hoạ âm (harmonic CQT)**. CQT là phổ có trục tần số chia theo nửa cung giống phím đàn. Phiên bản "có hoạ âm" xếp chồng thêm các bản dịch theo bậc hoạ âm, nên một nốt và các hoạ âm của nó nằm thẳng hàng.
- Mạng xuất ra ba "bản đồ xác suất" theo thời gian và cao độ:
  - **onset**: chỗ nào có nốt *bắt đầu*;
  - **note/frame**: chỗ nào có nốt *đang vang*;
  - **contour**: đường cao độ chi tiết, dùng cho bend.
- Bước hậu xử lý ghép các vùng đó thành danh sách nốt `(bắt đầu, kết thúc, cao độ MIDI, cường độ)`.

lamnhac chỉnh basic-pitch như sau:

| Tham số | Giá trị | Lý do |
|---------|---------|-------|
| `onset_threshold` | theo `--sensitivity` (bảng dưới) | Ngưỡng tạo nốt mới. Cao hơn thì ít nốt thừa hơn nhưng dễ sót nốt |
| `frame_threshold` | theo `--sensitivity` | Ngưỡng coi nốt còn đang vang |
| `minimum_note_length` | theo `--sensitivity` | Bỏ các mẩu nốt quá ngắn, thường là nhiễu hoặc tiếng ngân bị nhận lại |
| `minimum_frequency` | tần số của *dây trầm nhất − 1 nửa cung* | Tính theo tuning, nên Drop D (D2 = 73,4 Hz) không bị cắt |
| `maximum_frequency` | tần số của *dây cao nhất + 25 nửa cung* | Đủ tới phím 24 cộng một nửa cung dư |

Giới hạn dải tần theo tuning giúp loại bớt hoạ âm cao và tiếng ồn trầm vốn không thể là nốt guitar. Model được nạp **một lần cho mỗi tiến trình**: lần đầu khoảng 11 giây do nạp TensorFlow, các lần sau dưới 1 giây.

### 2.0 Độ nhạy (`--sensitivity`)

Ba ngưỡng trên quyết định tool "nghe" nhạy đến đâu. Chúng được chọn bằng cách đo, không đoán:

| Mức | onset | frame | nốt ngắn nhất | Khi nào dùng |
|-----|-------|-------|---------------|--------------|
| `low` | 0.85 | 0.5 | 128 ms | Kết quả còn nhiều nốt thừa |
| **`normal`** (mặc định) | 0.75 | 0.5 | 93 ms | Đa số trường hợp |
| `high` | 0.5 | 0.3 | 58 ms | Tool sót nốt; bài nhiều hợp âm có quãng tám |

Số đo ngày 2026-11-14 (Note F1, xem [báo cáo](reports/eval-2026-11-14-g1.md)):

| Bài | low | normal | high |
|-----|-----|--------|------|
| Afternoon Tea (149 nốt, có tab chuẩn) | 0.92 | 0.89 | 0.58 |
| Riff tổng hợp 97 BPM | 1.00 | 1.00 | 0.83 |

Mức `high` từng là mặc định. Trên bài thật nó ra **gấp đôi** số nốt: tiếng ngân và tiếng vang bị nhận thành nốt mới, cộng thêm nốt lệch quãng tám. Đổi lại, `high` là mức duy nhất giữ được nốt quãng tám trong power chord (E2+B2+E3), vì basic-pitch báo nốt đó yếu và `frame_threshold` 0.5 làm rơi nó. Bài toàn hợp âm thì thử `--sensitivity high`.

### 2.1 Lọc hoạ âm (tùy chọn)

Khi gảy một dây, dây rung ở tần số gốc (nốt thật) **và** ở các tần số gấp 2, 3, 4, 5, 6, 8 lần, gọi là hoạ âm. Các hoạ âm này cao hơn nốt gốc 12, 19, 24, 28, 31, 36 nửa cung. Tai nghe tất cả thành một nốt, nhưng model đôi khi báo hoạ âm thành nốt riêng.

`--filter-harmonics` bỏ nốt `n` khi có nốt `m` trầm hơn đúng một trong các khoảng trên, bắt đầu cùng lúc (±80 ms), vang chồng lên nhau, và `n` nhỏ hơn hoặc bằng 80% `m`. Trên riff mẫu, cách này nâng tỉ lệ nốt đúng từ 0.71 lên 0.92 mà không mất nốt thật nào.

**Vì sao mặc định tắt:** trong hợp âm có quãng tám *thật* (power chord E2+B2+E3, hợp âm E mở), basic-pitch báo nốt quãng tám chỉ to khoảng 0.5 lần nốt trầm, giống hệt hoạ âm. Bộ lọc vì vậy bỏ nhầm E3 ở 3/4 lần gảy. Chỉ dựa vào độ to thì không tách được hai trường hợp, nên lọc chỉ bật khi người dùng yêu cầu.

**Cách thay thế an toàn:** `--max-fret N`. Hoạ âm thường nằm cao trên cần đàn (ví dụ E5 = phím 12 dây 1), nên khi biết người chơi chỉ ở vài ngăn đầu, giới hạn phím sẽ loại phần lớn hoạ âm mà không bao giờ bỏ một nốt bấm được.

## 3. Tìm phách và tempo (`rhythm.analyze`, B5–B8)

### 3.1 Theo dõi phách (beat tracking)

Dùng `librosa.beat.beat_track`, dựa trên thuật toán quy hoạch động của **Ellis (2007)**:
1. Tính **đường cường độ onset (onset strength)**: tại mỗi khung thời gian, năng lượng phổ tăng bao nhiêu so với khung trước. Đường này có đỉnh ở mỗi chỗ gảy đàn.
2. Ước lượng tempo toàn cục từ tự tương quan của đường đó.
3. Dùng **quy hoạch động** chọn chuỗi thời điểm phách sao cho (a) mỗi phách rơi vào đỉnh onset mạnh và (b) khoảng cách giữa các phách gần đều với tempo ước lượng. Tham số `tightness` quyết định mức "phạt" khi khoảng cách lệch khỏi tempo.

Khi người dùng nhập `--tempo`, lamnhac đưa giá trị đó vào làm `start_bpm` và tăng `tightness` lên 100, để tracker bám sát tempo được nhập.

**Tempo ghi vào file** là `60 / trung vị(khoảng cách giữa hai phách)`, sau đó nhân hoặc chia đôi cho tới khi nằm trong 60–200 BPM. Lý do là tracker hay nhầm gấp đôi hoặc giảm nửa tempo, ví dụ bắt theo nốt móc đơn thay vì nốt đen. **Lưới phách được đổi cùng lúc:** khi chia đôi tempo thì bỏ đi một nửa số phách (giữ phách 0, 2, 4…), khi nhân đôi thì chèn điểm giữa mỗi cặp phách. Nhờ vậy mỗi phách trên lưới luôn đúng là một nốt đen của tempo ghi trong file. Nếu chỉ đổi con số tempo mà giữ nguyên lưới, bài sẽ phát lại nhanh gấp đôi hoặc chậm một nửa.

### 3.2 Bù độ trễ phách (B7a)

Đường onset strength tính trên các khung dài 512 mẫu (khoảng 23 ms), nên các phách librosa trả về thường **trễ đều 15–40 ms** so với lúc gảy thật. lamnhac đo trực tiếp độ trễ này:
- Với mỗi nốt nằm gần một phách (trong ±1/4 khoảng phách), lấy độ lệch `onset − phách`.
- Nếu có ít nhất 4 độ lệch như vậy, dịch **toàn bộ** lưới phách đi một lượng bằng **trung vị** các độ lệch. Lượng dịch giới hạn trong ±1/8 phách.

Dùng trung vị thay vì trung bình để vài nốt thừa hoặc nốt đảo phách không kéo lệch kết quả. Trên file mẫu 97 BPM, sai số trung bình giảm xuống còn khoảng 6 ms.

### 3.3 Chọn phách mạnh (B8)

Beat tracker chỉ biết *phách*, không biết phách nào là **phách 1 của ô nhịp**. lamnhac thử lần lượt các vị trí bắt đầu ô nhịp `o` trên lưới slot. Mỗi ứng viên cách nhau một phách đen (4 slot); riêng các nhịp có độ dài ô không chia hết cho 4, như 3/8 hay 5/8, thì thử cách nhau 2 slot. Với mỗi ứng viên, xét các vị trí `o, o + L, o + 2L…` (L = số slot mỗi ô nhịp) và tính điểm:

> điểm(o) = Σ qua các vị trí đó của **velocity lớn nhất** trong các nốt quanh vị trí (±1 slot)

Ứng viên có điểm cao nhất được chọn làm phách 1. Nếu hoà thì chọn ứng viên gần nốt đầu tiên nhất. Ví dụ với 6/8, mỗi ô dài 12 slot nên chỉ có 3 ứng viên là 0, 4 và 8. Đây là lý do không được bước theo tử số "6": một ô 6/8 thực ra chỉ có 3 phách nốt đen.

Tại sao lấy **max** mà không cộng: phiên bản đầu cộng velocity của mọi nốt, nên một hợp âm 3 nốt đánh nhẹ ở phách 3 lại thắng một nốt đơn được nhấn mạnh ở phách 1, làm cả bài lệch nửa ô nhịp. Lấy max nghĩa là đo *độ nhấn* của phách, không đo *số nốt* trên phách.

Nếu có nốt nằm trước phách 1 đầu tiên, lamnhac thêm một **ô pickup (đảo phách)** ở đầu bài và bù bằng dấu lặng.

**Khi đoán sai: `--pickup N` (B8a).** Nhạc fingerstyle thường không nhấn rõ phách 1, nên cách chấm điểm trên có thể chọn nhầm. Ví dụ bài *Nhớ ơi* (6/8): tool đặt sai vạch ô nhịp, 0% nốt nằm đúng vị trí trong ô. Khi người dùng cho biết nốt đầu tiên nằm trước phách 1 bao nhiêu phách, lamnhac:
1. lấy thời điểm nốt đầu tiên, cộng N phách tính bằng **giây** theo khoảng phách trung vị;
2. đổi thời điểm đó ra vị trí trên lưới rồi **làm tròn về phách gần nhất**.

Hai chi tiết này sửa hai lỗi đã gặp khi đo:
- lưới phách vài giây đầu bị méo, vì beat tracker chưa bắt nhịp kịp, nên đếm theo slot từ nốt đầu sẽ sai;
- nốt bass đầu được nhận trễ khoảng 0.1 s, nên nếu không làm tròn thì cả bài lệch đi một ô móc kép.

Sau khi sửa, 96% nốt bài *Nhớ ơi* nằm đúng vị trí trong ô.

## 4. Lượng tử hoá: từ giây sang ô lưới (`rhythm.quantize`, B7, B9–B10)

### 4.1 Lưới bám theo phách (beat-synchronous grid)

Cách đơn giản là dùng một tempo cố định: `slot = (t − t0) / (60 / tempo / 4)`. Nhưng chỉ cần tempo sai 1% thì sau 3 phút đã lệch khoảng 1,8 s, đủ đẩy nốt sang ô nhịp khác. Người chơi thật cũng không giữ tempo tuyệt đối đều.

lamnhac thay vào đó **nội suy tuyến tính giữa hai phách thực** nằm hai bên nốt:

```
nếu b[i] ≤ t < b[i+1]:   p(t) = 4 · ( i + (t − b[i]) / (b[i+1] − b[i]) )
```

Mỗi nốt được định vị *tương đối với hai phách gần nhất*, nên lỗi không bị cộng dồn. Trước phách đầu và sau phách cuối thì ngoại suy theo khoảng phách trung vị.

### 4.2 Làm tròn và gộp

- `start = round(p(onset))` và `length = max(1, round(p(offset)) − start)`.
- Các nốt có cùng `start` gộp thành một **slot** (hợp âm). Nếu một cao độ xuất hiện hai lần thì giữ nốt có velocity lớn hơn.
- **Một bè:** nếu một nốt ngân qua thời điểm nốt sau bắt đầu, nó bị cắt tại đó. Đây là giới hạn đã chấp nhận của MVP.
- Khoảng trống giữa các slot thành **dấu lặng**. Ô nhịp cuối được bù dấu lặng cho đủ.

## 5. Gán dây và phím: beam search (`tab.py`, B11–B13)

Một cao độ có thể bấm ở nhiều chỗ: E4 (MIDI 64) là dây 1 buông, dây 2 phím 5, dây 3 phím 9… Mục tiêu là chọn một chuỗi thế bấm **dễ chơi**, tức tay ít phải chạy và không phải mở ngón quá rộng.

### 5.1 Các cách bấm hợp lệ cho một slot

- Nốt `p` đặt được trên dây `s` khi `0 ≤ p − tuning[s] ≤ max_fret`. Mặc định là 24, đặt bằng `--max-fret`.
- Mỗi nốt trong hợp âm phải nằm trên **một dây khác nhau**. lamnhac liệt kê mọi cách gán, tối đa 6! = 720 cách.
- Nếu không có cách nào hợp lệ (ví dụ hai nốt E2 và F2 chỉ đặt được trên dây 6), bỏ nốt có velocity thấp nhất rồi thử lại, kèm cảnh báo.
- Ưu tiên các thế có **độ trải** ≤ 4 phím (khoảng cách giữa phím bấm cao nhất và thấp nhất, không tính dây buông).

### 5.2 Hàm chi phí

| Thành phần | Công thức | Ý nghĩa |
|------------|-----------|---------|
| Chi phí của một thế | `độ trải + 0.3 × vị trí + 0.3 × Σ max(0, phím − 12)` | Phạt thế mở rộng tay, ưu tiên thế thấp gần đầu cần (vị trí = trung bình các phím bấm, không tính dây buông), phạt vùng phím cao |
| Chi phí chuyển giữa hai thế | `|tâm_trước − tâm_sau|` | Phạt việc tay phải chạy dọc cần đàn |

`tâm` là trung bình các phím bấm, không tính dây buông. Nếu một thế toàn dây buông thì `tâm = None` và chi phí chuyển bằng 0, vì tay đang tự do.

### 5.3 Beam search

Đây là bài toán tìm đường đi rẻ nhất qua một đồ thị nhiều tầng, mỗi slot là một tầng. Viterbi đầy đủ phải xét mọi cặp thế giữa hai tầng liền nhau, nên lamnhac dùng **beam search**:
- tại mỗi slot chỉ giữ **64 đường đi rẻ nhất**;
- vì chi phí chuyển chỉ phụ thuộc vào *tâm* của thế trước, mỗi giá trị tâm chỉ cần giữ một đường tốt nhất, nhờ đó số phép tính giảm mạnh;
- nếu hoà chi phí thì chọn tổng phím nhỏ hơn, rồi so bộ `(dây, phím)` theo thứ tự từ điển, để cùng một đầu vào luôn cho cùng một kết quả.

Đo thực tế: khoảng 2000 slot, tương đương một bài 3 phút, chạy mất **0,4 s**. Ví dụ, hợp âm E mở ra đúng thế quen thuộc 0-2-2-1-0-0.

### 5.4 Tuning

`--tuning "D A D G B E"` nhận tên nốt từ dây trầm đến dây cao. Quãng tám của mỗi dây được chọn **gần nhất với dây tương ứng của E chuẩn**, nếu cách đều thì chọn quãng thấp hơn. Ví dụ dây 6 "D" thành D2 (38).

## 6. Xuất file

### 6.1 Tách trường độ (`durations.py`, B16)

Một slot dài 6 ô bắt đầu ở vị trí 2 phải được viết thành các ký hiệu nốt có thật, nối với nhau bằng dấu nối (tie):
1. **Cắt tại vạch nhịp** trước tiên. Một nốt không bao giờ vắt qua hai ô.
2. Trong mỗi ô nhịp, đi **tham lam** từ trái sang. Mỗi lần chọn trường độ lớn nhất trong {tròn 16, trắng chấm 12, trắng 8, đen chấm 6, đen 4, móc đơn chấm 3, móc đơn 2, móc kép 1} thoả hai điều kiện:
   - **thẳng hàng với phách:** vị trí hiện tại chia hết cho trường độ gốc (nốt đen phải bắt đầu ở đầu phách);
   - **nốt có chấm chỉ dùng khi lấp vừa khít phần còn lại.**

Điều kiện thứ hai tránh những cách tách đúng về toán nhưng khó đọc:

| Vị trí, độ dài | Không có điều kiện 2 | Có điều kiện 2 (đang dùng) |
|----------------|----------------------|----------------------------|
| 2, 6 | 3 + 1 + 2 | **2 + 4** |
| 4, 8 | 6 + 2 | **4 + 4** |
| 0, 7 | 6 + 1 | **4 + 3** |
| 0, 6 | 6 | **6** (nốt đen chấm) |

Dấu lặng cũng tách theo cùng quy tắc, nhưng không có dấu nối.

### 6.2 `.gp5` (`export_gp5.py`, B17)

Dùng PyGuitarPro, ghi theo định dạng GP 5.1:
- một track "Guitar" (MIDI program 25), 6 dây theo tuning, một tempo;
- mỗi slot = 240 tick (một nốt đen = 960 tick);
- các mảnh nối tiếp được đánh `NoteType.tie`;
- mọi ô nhịp được lấp đầy bằng dấu lặng, vì Guitar Pro yêu cầu như vậy;
- tên bài được **gập về ASCII** ("Bài hát đầu tiên" thành "Bai hat dau tien"). Định dạng GP5 dùng bảng mã cp1252 nên không ghi được tiếng Việt.

### 6.3 `.musicxml` (`export_musicxml.py`, B18)

Dùng music21 dựng một part có khuông TAB 6 dòng. Mỗi nốt mang `<string>` và `<fret>`. music21 bỏ sót hai thứ, nên lamnhac **chèn thêm bằng ElementTree** sau khi music21 ghi file:
- `<staff-tuning>` cho từng dây. Thiếu phần này, Guitar Pro sẽ coi là tuning chuẩn.
- `<string>` và `<fret>` cho từng nốt *bên trong hợp âm*.

### 6.4 Ghi an toàn (B15)

Mỗi file được ghi ra `<tên>.tmp-<pid>.<đuôi>` trước, rồi `os.replace` sang tên thật. Nếu lỗi giữa chừng, file tạm bị xoá, nên không bao giờ còn file ghi dở. Một định dạng lỗi không ngăn định dạng kia được ghi (B19).

---

## Hiệu năng (đo trên file mẫu)

| Bước | Thời gian |
|------|-----------|
| Nạp TensorFlow và model (một lần) | khoảng 11 s |
| Nhận nốt cho 12 s audio | dưới 1 s |
| Phách, lượng tử hoá, gán tab, xuất file | dưới 1 s |

Độ chính xác: Note F1 0.89 trên bài Afternoon Tea ở mức `normal` (mục tiêu ≥ 0.70), xem [báo cáo eval](reports/eval-2026-11-14-g1.md) và mục 2.0.

## Tài liệu tham khảo

- R. Bittner et al., *A Lightweight Instrument-Agnostic Model for Polyphonic Note Transcription and Multipitch Estimation*, ICASSP 2022. Đây là bài báo về basic-pitch.
- D. P. W. Ellis, *Beat Tracking by Dynamic Programming*, Journal of New Music Research, 2007. Đây là thuật toán của `librosa.beat.beat_track`.
- C. Raffel et al., *mir_eval: A Transparent Implementation of Common MIR Metrics*, ISMIR 2014. Thư viện này được dùng để đo Note F1.
