# lamnhac

Chuyển một file **MP3 guitar solo** thành **tab Guitar Pro** (`.gp5`) và **MusicXML** có khuông tab. Tool chạy hoàn toàn offline trên máy cá nhân.

```
bai.mp3  ──►  lamnhac convert  ──►  bai.gp5  +  bai.musicxml
```

Kết quả là **bản nháp** để bạn mở trong Guitar Pro 8 rồi sửa tiếp, không phải bản chép hoàn chỉnh. Công cụ chạy tốt nhất với bản thu chỉ có một cây guitar, tiếng clean hoặc acoustic.

- 📖 Trang tài liệu: https://nguyenhuuca.github.io/lamnhac/
- Cách các bước bên trong hoạt động: [docs/algorithms.md](docs/algorithms.md)
- Yêu cầu sản phẩm: [docs/prd/PRD-mp3-to-guitarpro.md](docs/prd/PRD-mp3-to-guitarpro.md)
- Đặc tả kỹ thuật: [docs/specs/spec-mp3-to-guitarpro.md](docs/specs/spec-mp3-to-guitarpro.md)

---

## Cài đặt

Cần có:
- Windows 10/11 64-bit. Có thể chạy trên Linux/macOS nhưng chưa thử.
- [uv](https://docs.astral.sh/uv/), công cụ quản lý Python và thư viện. Cài bằng lệnh:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- Khoảng 2 GB đĩa trống, chủ yếu cho TensorFlow.
- **Không** cần ffmpeg, **không** cần GPU.

Cài thư viện cho dự án:

```powershell
cd D:\DO\lamnhac
uv sync
```

uv tự dùng Python 3.11. Dự án ghim đúng bản này vì basic-pitch chưa hỗ trợ 3.12 (xem [ADR-0001](docs/adr/0001-transcription-and-export-libraries.md)).

## Cách dùng

### Lệnh cơ bản

```powershell
uv run lamnhac convert "D:\nhac\bai.mp3"
```

Lệnh này tạo `bai.gp5` và `bai.musicxml` ngay cạnh file MP3. Tiến độ in ra màn hình như sau:

```
[1/6] đọc audio…
[2/6] nhận nốt…
[3/6] phân tích nhịp…
tempo đoán được: 96 BPM (dùng --tempo để sửa)
[4/6] lượng tử hoá…
[5/6] gán tab…
[6/6] xuất file…
xong: 34 nốt, tempo 96 BPM (detected), 0 cảnh báo, 10.8s
D:\nhac\bai.gp5
D:\nhac\bai.musicxml
```

Lần chạy đầu mất thêm khoảng 10 giây để nạp model TensorFlow. Một bài 3 phút thường xong trong vòng 1–3 phút trên CPU.

### Tuỳ chọn

| Tuỳ chọn | Mặc định | Ý nghĩa |
|----------|----------|---------|
| `-o, --out-dir DIR` | thư mục chứa file MP3 | Nơi ghi file kết quả. Thư mục chưa có thì được tạo |
| `--format LIST` | `gp5,musicxml` | Chọn định dạng đầu ra, ví dụ `--format gp5` |
| `--tempo BPM` | tự đoán | Tempo tính theo **nốt đen**, từ 30 đến 300. Dùng khi tempo đoán sai |
| `--tuning "E A D G B E"` | E chuẩn | 6 tên nốt viết **từ dây trầm đến dây cao**, ví dụ Drop D là `"D A D G B E"` |
| `--time N/D` | `4/4` | Số chỉ nhịp, ví dụ `3/4`, `6/8`, `2/2` |
| `--max-fret N` | 24 | Chỉ dùng phím 0..N khi gán tab. Nốt không bấm được trong vùng đó bị bỏ, kèm cảnh báo. Hữu ích khi biết người chơi chỉ ở vài ngăn đầu, và cũng loại được phần lớn hoạ âm |
| `--filter-harmonics` | tắt | Bỏ các nốt giả do hoạ âm (cao hơn 1–3 quãng tám, nhỏ hơn rõ rệt). Tốt cho câu lead đánh từng nốt, nhưng **có thể bỏ nhầm quãng tám thật** trong hợp âm |
| `--sensitivity LEVEL` | `normal` | Độ nhạy nhận nốt: `low`, `normal` hoặc `high`. Ra nhiều nốt thừa thì dùng `low`; sót nốt, hoặc bài nhiều hợp âm có quãng tám, thì dùng `high` |
| `--pickup N` | tự đoán | Số phách nằm **trước** ô nhịp 1 (nốt lấy đà). Phách tính theo mẫu số của `--time`: 4/4 là nốt đen, 6/8 là nốt móc đơn. N từ 0 đến tử số − 1, nhận nửa phách như `1.5`. `0` nghĩa là nốt đầu ở đúng phách 1. Dùng khi vạch ô nhịp bị lệch |
| `--force` | tắt | Cho phép ghi đè file đã có. Nếu không bật, lệnh sẽ dừng **trước khi** xử lý |
| `-v, --verbose` | tắt | In log chi tiết và stack trace khi có lỗi |

### Ví dụ

```powershell
# Drop D, nhịp 3/4, ghi ra thư mục khác
uv run lamnhac convert bai.mp3 --tuning "D A D G B E" --time 3/4 -o D:\tab

# Tempo đoán ra 192 nhưng thực tế là 96, nên nhập tay
uv run lamnhac convert bai.mp3 --tempo 96 --force

# Người chơi chỉ ở 5 ngăn đầu: giới hạn phím, loại bớt hoạ âm
uv run lamnhac convert bai.mp3 --max-fret 5

# Câu lead đánh từng nốt, có nhiều nốt giả do hoạ âm
uv run lamnhac convert bai.mp3 --filter-harmonics

# Ra quá nhiều nốt thừa: giảm độ nhạy. Sót nốt: tăng độ nhạy
uv run lamnhac convert bai.mp3 --sensitivity low
uv run lamnhac convert bai.mp3 --sensitivity high

# Vạch ô nhịp bị lệch: nốt đầu ở phách 1 (6/8), hoặc có 1.5 phách lấy đà (3/4)
uv run lamnhac convert bai.mp3 --time 6/8 --pickup 0
uv run lamnhac convert bai.mp3 --time 3/4 --pickup 1.5

# Chỉ cần file .gp5
uv run lamnhac convert bai.mp3 --format gp5
```

### Mở trong Guitar Pro 8

- **`.gp5`**: mở bằng *File → Open*.
- **`.musicxml`**: dùng *File → Import → MusicXML*. File này cũng mở được bằng MuseScore.

Tên bài trong file `.gp5` được bỏ dấu, ví dụ "Bài hát" thành "Bai hat", vì định dạng GP5 không ghi được tiếng Việt. File MusicXML vẫn giữ nguyên dấu.

### Mã thoát

Hữu ích khi gọi tool từ script khác. stdout chỉ in đường dẫn các file đã tạo; tiến độ, cảnh báo và lỗi đều ra stderr.

| Mã | Nghĩa |
|----|-------|
| 0 | Thành công (có thể kèm cảnh báo) |
| 2 | Tham số sai |
| 3 | File đầu vào không hợp lệ: không có, sai đuôi, lớn hơn 50 MB, dài hơn 10 phút, hoặc hỏng |
| 4 | Lỗi khi xử lý, ví dụ không nhận được nốt nào |
| 5 | Không ghi được đầu ra: file đã tồn tại mà không có `--force`, hoặc ghi một định dạng bị lỗi |
| 1 | Lỗi không lường trước. Chạy lại với `-v` để xem chi tiết |

## Giới hạn hiện tại

- Chỉ hỗ trợ **một cây guitar**. Nhạc có cả ban nhạc sẽ cho kết quả kém.
- Chỉ có **một bè**: nốt đang ngân bị cắt khi có nốt mới bắt đầu.
- Lưới nhỏ nhất là **nốt móc kép (1/16)**. Chưa có chùm ba, và cả bài dùng một tempo duy nhất.
- Không nhận kỹ thuật bend, slide, hammer-on, pull-off hay vibrato.
- Phách mạnh được đoán theo nốt được nhấn mạnh nhất. Nếu ô nhịp bị lệch, dùng `--pickup` (cách tìm N: nốt đầu ở phách k thì N = tử số − (k − 1); ở phách 1 thì N = 0).
- Tool không tự nhận ra số chỉ nhịp: bài 3/4 hay 6/8 cần truyền `--time`.
- Thường có nốt thừa do **hoạ âm** (tần số gấp 2, 3, 4… lần của nốt thật, sinh ra từ chính dây vừa gảy). Dùng `--max-fret` hoặc `--filter-harmonics` để giảm, xem [docs/algorithms.md](docs/algorithms.md#21-lọc-hoạ-âm-tuỳ-chọn).
- Ở mức `normal`, nốt quãng tám trong hợp âm (ví dụ E3 của power chord E2+B2+E3) có thể bị bỏ. Bài nhiều hợp âm thì thử `--sensitivity high`.
- File đầu vào giới hạn 50 MB và 10 phút.

## Đo độ chính xác

Muốn biết tool đúng đến đâu trên nhạc của bạn, đặt từng cặp file cùng tên vào `tests/fixtures/real/`:
- `<bài>.mp3`: bản thu;
- `<bài>.gp5`: tab **đúng** của bản thu đó, ví dụ bạn đã sửa tay trong Guitar Pro 8.

Thư mục này nằm trong `.gitignore`, nên file của bạn không bị đưa lên GitHub. Sau đó chạy:

```powershell
uv run pytest -m eval -s
```

Mỗi bài in ra Note F1 ở cả ba mức `--sensitivity`. Một nốt tính là đúng khi đúng cao độ và bắt đầu lệch không quá 50 ms so với tab. F1 = 1 là khớp hoàn toàn, mục tiêu là ≥ 0.70. Kết quả gần nhất nằm trong [báo cáo eval](docs/reports/eval-2026-11-14-g1.md).

## Phát triển

```powershell
uv sync                              # cài cả thư viện dev
uv run ruff check                    # lint
uv run ruff format --check           # kiểm tra format
uv run mypy src                      # kiểm tra kiểu (strict)
uv run pytest -m "not eval"          # test, khoảng 1 phút, có chạy model thật
uv run python tests/fixtures/make_fixtures.py   # sinh lại các file MP3 mẫu
uv run pytest -m eval -s             # đo Note F1 trên tests/fixtures/real/*.mp3 + .gp5 (dữ liệu cục bộ)
```

Bốn lệnh `ruff`, `mypy` và `pytest` ở trên là các gate, được khai trong `sdlc.config.json`. Mọi commit phải qua hết các gate này.

Bố cục mã nguồn. Mỗi bước là một module, chỉ trao đổi dữ liệu qua `models.py`:

```
src/lamnhac/
  cli.py              tham số dòng lệnh, mã thoát
  pipeline.py         chạy 6 bước theo thứ tự
  models.py           dataclass dùng chung
  errors.py           các lỗi và mã thoát tương ứng
  audio.py            [1] kiểm tra file và decode MP3
  transcribe.py       [2] nhận nốt bằng basic-pitch
  rhythm.py           [3][4] phách, tempo, lượng tử hoá
  tab.py              [5] gán dây/phím
  durations.py        tách trường độ (dùng khi xuất file)
  export_gp5.py       [6] ghi .gp5
  export_musicxml.py  [6] ghi .musicxml
tests/                pytest; tests/fixtures/ chứa MP3 tổng hợp kèm đáp án .json
docs/                 PRD, ADR, spec, sequence, plan, báo cáo
```

Thư viện chính: [basic-pitch](https://github.com/spotify/basic-pitch) (Spotify, Apache-2.0), [librosa](https://librosa.org), [soundfile](https://github.com/bastibe/python-soundfile), [PyGuitarPro](https://github.com/Perlence/PyGuitarPro), [music21](https://web.mit.edu/music21/).

> **Bảo mật:** TensorFlow 2.15 kéo theo các bản keras và protobuf đã có lỗ hổng công bố. Đánh giá hiện tại là các lỗ hổng này không bị khai thác được, vì tool chỉ nạp model đi kèm và file audio của bạn. Chi tiết trong [ADR-0001](docs/adr/0001-transcription-and-export-libraries.md).
