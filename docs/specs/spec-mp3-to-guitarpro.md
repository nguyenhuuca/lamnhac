# Spec: MP3 → Guitar Pro

**Status:** Approved (2026-11-13, rev 2) · **PRD:** docs/prd/PRD-mp3-to-guitarpro.md · **ADRs:** ADR-0001 · **Date:** 2026-11-13

## Overview

`lamnhac` là CLI Python 3.11 chạy offline trên Windows. Lệnh `lamnhac convert` đọc một file MP3 guitar solo và cho ra file `.gp5` và/hoặc `.musicxml` chứa tab. Pipeline có 6 bước tuần tự: kiểm tra và giải mã audio → nhận nốt (basic-pitch) → phân tích phách (librosa) → lượng tử hoá vào ô nhịp → gán dây/phím → xuất file. Spec này phủ R1–R12 của PRD.

Bố cục mã nguồn (`src/` layout, quản lý bằng uv):

```
src/lamnhac/
  cli.py              # argparse, mã thoát, in tiến độ
  pipeline.py         # convert(): chạy các bước theo thứ tự
  models.py           # dataclass dùng chung (bên dưới)
  errors.py           # cây ngoại lệ LamnhacError
  audio.py            # kiểm tra file, decode theo khối
  transcribe.py       # adapter basic-pitch → list[NoteEvent]
  rhythm.py           # phách, tempo, nhịp mạnh, lượng tử hoá → Score
  durations.py        # tách độ dài slot thành trường độ ghi được
  tab.py              # gán dây/phím (beam search) → TabScore
  export_gp5.py       # TabScore → .gp5 (PyGuitarPro)
  export_musicxml.py  # TabScore → .musicxml (music21)
tests/
```

Mỗi bước chỉ phụ thuộc vào `models.py`. Riêng `transcribe.py`, `export_gp5.py` và `export_musicxml.py` được import thư viện ngoài của ADR-0001, nên có thể thay backend mà không chạm vào các bước khác.

## Data Model

Không có database. Các model nội bộ trong `models.py`, đều là `@dataclass(frozen=True)`. Đơn vị thời gian trên lưới là **slot = một nốt móc kép (1/16 nốt tròn)**, không phụ thuộc vào time signature.

| Model | Trường | Ràng buộc |
|-------|--------|-----------|
| `AudioClip` | `samples: np.ndarray` (mono float32), `sample_rate: int`, `duration_s: float`, `source: Path` | `sample_rate` = 22050, `0 < duration_s ≤ 600` |
| `NoteEvent` | `onset_s: float`, `offset_s: float`, `pitch: int` (MIDI), `velocity: float` (0–1) | `offset_s > onset_s`, `0 ≤ pitch ≤ 127` |
| `Tuning` | `strings: tuple[int, ...]` (MIDI, phần tử 0 = dây 1 = dây cao nhất) | 6 dây. Mặc định `(64, 59, 55, 50, 45, 40)` = E chuẩn |
| `TimeSignature` | `numerator: int`, `denominator: int`. Thuộc tính `bar_slots = numerator × 16 / denominator` | `denominator ∈ {2, 4, 8}`, `1 ≤ numerator ≤ 16` |
| `RhythmInfo` | `tempo_bpm: float` (**BPM của nốt đen**), `beat_times_s: tuple[float, ...]`, `downbeat_slot: int` (offset phách mạnh, đơn vị slot), `time_signature: TimeSignature`, `tempo_source: Literal["detected", "user"]` | `30 ≤ tempo_bpm ≤ 300`, `beat_times_s` tăng dần và có ≥ 2 phần tử |
| `GridNote` | `pitch: int`, `velocity: float` | – |
| `Slot` | `start: int`, `length: int` (đơn vị slot, tính từ đầu ô nhịp 1), `notes: tuple[GridNote, ...]` | `length ≥ 1`. `notes` rỗng = dấu lặng |
| `Score` | `rhythm: RhythmInfo`, `slots: tuple[Slot, ...]` | Các slot liền nhau, không chồng nhau, tổng độ dài là bội số của `bar_slots` |
| `TabNote` | `pitch: int`, `string: int` (1–6), `fret: int` (0–24) | `tuning.strings[string-1] + fret == pitch` |
| `TabSlot` | `start: int`, `length: int`, `notes: tuple[TabNote, ...]` | Mỗi dây xuất hiện tối đa một lần |
| `TabScore` | `rhythm: RhythmInfo`, `tuning: Tuning`, `slots: tuple[TabSlot, ...]`, `title: str` | – |
| `ConvertOptions` | `input: Path`, `out_dir: Path`, `formats: frozenset[Literal["gp5", "musicxml"]]`, `tempo: float \| None`, `tuning: Tuning`, `time_signature: TimeSignature`, `max_fret: int` (0–24, mặc định 24), `keep_harmonics: bool`, `force: bool` | Đã được `cli.py` kiểm tra |
| `ConvertResult` | `outputs: tuple[Path, ...]`, `errors: tuple[str, ...]` (lỗi ghi từng định dạng), `warnings: tuple[str, ...]`, `rhythm: RhythmInfo`, `note_count: int` | – |

## Interfaces

### CLI

```
lamnhac convert <input> [-o OUT_DIR] [--format gp5,musicxml] [--tempo BPM]
                [--tuning "E A D G B E"] [--time 4/4] [--max-fret N] [--keep-harmonics] [--force] [-v]
```

| Đối số | Mặc định | Kiểm tra |
|--------|----------|----------|
| `input` | bắt buộc | File tồn tại, đuôi `.mp3`, ≤ 50 MB, thời lượng ≤ 600 s (B1) |
| `-o/--out-dir` | thư mục chứa `input` | Tạo nếu chưa có. Phải ghi được |
| `--format` | `gp5,musicxml` | Danh sách con không rỗng của `{gp5, musicxml}` |
| `--tempo` | tự đoán | Số thực 30–300, **BPM của nốt đen** (với 6/8 đi chậm 60 nốt đen chấm/phút thì nhập 90) |
| `--tuning` | `E A D G B E` | 6 tên nốt viết **từ dây trầm đến dây cao**, mỗi tên khớp `^[A-G][#b]?$`. CLI đảo thứ tự khi tạo `Tuning`. Quãng tám suy ra theo B11 |
| `--time` | `4/4` | `N/D`, ràng buộc như `TimeSignature` |
| `--max-fret` | 24 | Số nguyên 0–24. Giới hạn phím cao nhất được dùng khi gán tab (B12) |
| `--keep-harmonics` | tắt | Tắt bộ lọc hoạ âm (B4a) |
| `--force` | tắt | Cho phép ghi đè file đầu ra đã có |
| `-v/--verbose` | tắt | Log mức DEBUG ra stderr |

| Mã thoát | Nghĩa | Ngoại lệ |
|----------|-------|----------|
| 0 | Thành công (có thể kèm cảnh báo) | – |
| 2 | Đối số sai | argparse / `UsageError` |
| 3 | Đầu vào không hợp lệ | `InputError` |
| 4 | Lỗi khi xử lý (môi trường không đọc được MP3, model lỗi, không tìm thấy nốt nào) | `ProcessingError` |
| 5 | Không ghi được đầu ra | `OutputError`, hoặc `ConvertResult.errors` khác rỗng |
| 1 | Lỗi không lường trước | các lỗi khác. Chỉ in một dòng, stack trace chỉ có khi bật `-v` |

stdout chỉ in đường dẫn các file đã tạo, mỗi file một dòng, để script khác dùng được. Tiến độ, cảnh báo và lỗi ra stderr.

### API nội bộ

| Hàm | Input | Output | Lỗi |
|-----|-------|--------|-----|
| `audio.load(path)` | `Path` | `AudioClip` | `InputError`, `ProcessingError` |
| `transcribe.transcribe(clip, tuning, filter_harmonics=True)` | `AudioClip`, `Tuning`, `bool` | `tuple[list[NoteEvent], list[str]]` (kèm cảnh báo) | `ProcessingError` |
| `rhythm.analyze(clip, notes, tempo, time_sig)` | `AudioClip`, `list[NoteEvent]`, `float \| None`, `TimeSignature` | `RhythmInfo` | `ProcessingError` |
| `rhythm.quantize(notes, rhythm)` | `list[NoteEvent]`, `RhythmInfo` | `Score` | – |
| `durations.split(start, length, bar_slots)` | `int`, `int`, `int` | `list[tuple[int, bool]]` (trường độ tính bằng slot, có tie với phần sau không) | – |
| `tab.assign(score, tuning, max_fret=24)` | `Score`, `Tuning`, `int` | `tuple[TabScore, list[str]]` (kèm cảnh báo) | – |
| `export_gp5.write(tab, path)` | `TabScore`, `Path` (đích cuối) | `None` | `OutputError` |
| `export_musicxml.write(tab, path)` | `TabScore`, `Path` (đích cuối) | `None` | `OutputError` |
| `pipeline.convert(opts, progress)` | `ConvertOptions`, `Callable[[str], None]` | `ConvertResult` | các lớp con của `LamnhacError` |

## Behavior

**Đầu vào (R1, R2)**
- **B1.** Kiểm tra theo thứ tự, dừng ở lỗi đầu tiên: tồn tại → là file thường → đuôi `.mp3` (không phân biệt hoa thường) → kích thước ≤ 50 MB → `soundfile.info` đọc được header → thời lượng trong header ≤ 600 s. Mọi vi phạm sinh `InputError`, thông điệp nêu rõ điều kiện bị vi phạm và không lộ chi tiết nội bộ.
- **B2.** Header của MP3 VBR có thể khai sai thời lượng (CWE-400), nên decode bằng `soundfile.blocks` theo khối 1 s ở sample rate gốc và đếm số mẫu đã decode. Vượt 605 s thì dừng ngay và sinh `InputError`. Sau đó trộn xuống mono và `librosa.resample` về 22050 Hz. Decode lỗi hoặc ra 0 mẫu thì sinh `InputError("file audio hỏng hoặc rỗng")`. Nếu libsndfile không hỗ trợ MP3 (bản < 1.1) thì sinh `ProcessingError("môi trường không đọc được MP3 …")`. **Không** fallback sang audioread/ffmpeg.

**Nhận nốt (R3)**
- **B3.** `basic_pitch.inference.predict` nhận đường dẫn file, không nhận mảng audio, nên truyền `clip.source`. File vì vậy được decode hai lần: một lần ở B2 để kiểm tra an toàn và phân tích nhịp, một lần trong basic-pitch. Điều này chấp nhận được vì B2 đã loại file độc hại trước, còn thời gian decode nhỏ so với thời gian chạy model. Các tham số:
  - `onset_threshold=0.5`, `frame_threshold=0.3`, `minimum_note_length=58` (ms);
  - `minimum_frequency = hz(min(tuning.strings) − 1)` và `maximum_frequency = hz(max(tuning.strings) + 25)`, với `hz(m) = 440 × 2^((m−69)/12)`. Như vậy Drop D và các tuning thấp hơn vẫn được phủ.

  Hàm trả về `(model_output, midi_data, note_events)`. Mỗi `note_event` có dạng `(start_s, end_s, pitch, amplitude, pitch_bends)` và được đổi sang `NoteEvent(velocity=amplitude)`, sắp theo `onset_s`. Các ngưỡng là hằng số trong `transcribe.py` để chỉnh sau khi đo G1.
- **B4.** Không có nốt nào sau B3 thì sinh `ProcessingError("không nhận được nốt nào — file có phải guitar không?")`.
- **B4a. Lọc hoạ âm** (R13, bật mặc định). Bỏ nốt `n` nếu tồn tại nốt `m` sao cho: `n.pitch − m.pitch ∈ {12, 19, 24, 28, 31, 36}` (hoạ âm bậc 2, 3, 4, 5, 6, 8); `|n.onset − m.onset| ≤ 80 ms`; hai nốt vang chồng nhau; và `n.velocity ≤ 0.8 × m.velocity`. Ngưỡng 0.8 chọn theo đo đạc 2026-11-13: trên riff mẫu precision 0.71 → 0.92, recall giữ 1.00; trên testgod.mp3 bỏ 53/297 nốt. Lọc chạy trong `transcribe` sau khi đổi sang `NoteEvent`, trước B4 (nếu lọc xong không còn nốt thì vẫn báo B4). Số nốt bị bỏ được thêm vào cảnh báo: `bỏ N nốt hoạ âm`. `--keep-harmonics` tắt bước này.

**Nhịp (R4, R12)**

Tempo luôn tính theo nốt đen, và một slot luôn là một nốt móc kép. Giả định của MVP là xung mà beat tracker tìm được chính là nốt đen. Với 6/8, nếu tracker bắt theo nốt đen chấm thì người dùng sửa bằng `--tempo`.
- **B5. Tìm phách.** Gọi `librosa.beat.beat_track(y, sr, start_bpm=opts.tempo or 120, tightness=100 if opts.tempo else 50, units="time")`. Ép tempo trả về sang `float` vì các bản librosa mới trả `ndarray`. Nếu tìm được ít hơn 2 phách thì dựng lưới phách đều từ onset nốt đầu tiên, theo `opts.tempo` (nếu có) hoặc 120.
- **B6. Tempo ghi vào file.** Nếu có `--tempo` thì dùng giá trị đó (`tempo_source="user"`). Nếu không, tempo = `60 / median(diff(beat_times_s))`, sau đó đưa vào khoảng 60–200 BPM bằng cách nhân hoặc chia đôi. **Lưới phách phải đổi theo** để mỗi phách trên lưới luôn là một nốt đen của tempo ghi vào file: khi chia đôi tempo thì giữ một phách, bỏ một phách (`beat_times_s[::2]`); khi nhân đôi thì chèn điểm giữa mỗi cặp phách. Rồi in ra stderr: `tempo đoán được: N BPM (dùng --tempo để sửa)`.
- **B7. Ánh xạ thời gian → lưới, đi theo phách để không bị trôi.** Với thời điểm `t` nằm giữa hai phách `b_i ≤ t < b_{i+1}`, vị trí trên lưới là `p(t) = 4 × (i + (t − b_i) / (b_{i+1} − b_i))` (đơn vị slot). Ngoài khoảng các phách thì ngoại suy theo khoảng phách trung vị. Vì lưới bám theo từng phách thực, nếu người chơi nhanh hay chậm dần thì nốt vẫn rơi đúng phách, không bị lệch tích luỹ như khi dùng một tempo cố định.
- **B7a. Bù độ trễ phách.** Phách của librosa thường trễ đều 15–40 ms so với onset thật, do khung phân tích onset. Trước khi dùng `p(t)`, với mỗi nốt có onset nằm trong ±1/4 khoảng phách quanh phách gần nhất, lấy độ lệch `onset − phách`. Nếu có ≥ 4 độ lệch như vậy, dịch toàn bộ `beat_times_s` một lượng bằng trung vị các độ lệch, giới hạn trong ±1/8 khoảng phách trung vị. Nếu có ít hơn 4 thì không dịch.
- **B8. Phách mạnh.** Tính trên lưới slot (phách 0 = slot 0). Bước ứng viên `step = 4` nếu `bar_slots` chia hết cho 4, ngược lại `step = 2` (ví dụ 3/8, 5/8). Thử mọi offset `o ∈ {0, step, 2·step, …} < bar_slots`; điểm(o) = tổng, qua các vị trí `o + k × bar_slots`, của **velocity lớn nhất** trong các nốt có onset trong ±1 slot quanh vị trí đó. Dùng max chứ không cộng mọi nốt, để một hợp âm ở phách yếu không thắng một nốt đơn được nhấn ở phách 1. Hoà thì chọn offset gần onset nốt đầu tiên nhất, rồi offset nhỏ hơn. Lưu `downbeat_slot = o` (đơn vị slot, thay cho `downbeat_index` cũ). Ô nhịp 1 bắt đầu tại `o − m × bar_slots`, với `m ≥ 0` nhỏ nhất sao cho mọi nốt có `p(onset) ≥ start ô 1 − 0.5`. Như vậy nốt nằm trước phách mạnh tạo thành một ô "đảo phách" (pickup) được bù dấu lặng. Ví dụ: 6/8 có `bar_slots = 12`, các offset thử là 0, 4, 8 (3 phách đen mỗi ô).
- **B9. Lượng tử hoá.** `start = ⌊p(onset) − bar1 + 0.5⌋`, `end = ⌊p(offset) − bar1 + 0.5⌋` (làm tròn nửa lên, không dùng banker's rounding), `length = max(1, end − start)`. Các nốt có cùng `start` gộp thành một slot (hợp âm). Nếu cùng `start` có hai nốt trùng cao độ thì giữ nốt có `velocity` lớn hơn.
- **B10. Một bè.** Độ dài slot = `min(độ dài dài nhất trong nhóm, start slot kế − start slot này)`, nên nốt ngân qua onset kế tiếp bị cắt (giới hạn đã biết của MVP). Khoảng trống giữa hai slot thành slot dấu lặng. Ô nhịp cuối được bù dấu lặng cho đủ `bar_slots`.

**Gán tab (R5, R11)**
- **B11. Tuning.** Tên nốt trong `--tuning` được đổi sang MIDI bằng cách chọn quãng tám gần nhất với dây tương ứng của E chuẩn. Nếu hai quãng tám cách đều thì chọn quãng thấp hơn. Ví dụ `D A D G B E` cho dây 6 = D2 (38).
- **B12. Cách bấm hợp lệ.** Một nốt đặt được trên dây `s` khi `0 ≤ pitch − tuning[s] ≤ max_fret` (mặc định 24, đặt bằng `--max-fret`, R14). Nốt không đặt được trên dây nào thì bị bỏ, kèm cảnh báo `bỏ N nốt ngoài tầm cây đàn`. Mỗi slot liệt kê mọi cách gán mỗi nốt một dây khác nhau, tối đa 6! = 720 tổ hợp. Nếu slot có hơn 6 nốt, hoặc không có cách gán nào (ví dụ 40 và 41 chỉ đặt được trên dây 6), thì bỏ nốt có velocity thấp nhất và thử lại cho đến khi có cách gán, kèm cảnh báo. Ưu tiên các cách bấm có độ trải phím (các phím ≠ 0) ≤ 4. Nếu không có cách nào như vậy thì nhận cách có độ trải nhỏ nhất và cảnh báo.
- **B13. Beam search.** Trạng thái là một cách bấm của một slot có nốt. Slot dấu lặng bị bỏ qua.
  - `tâm(state)` = trung bình các phím ≠ 0, hoặc `None` nếu toàn dây buông. `tâm` chỉ phụ thuộc trạng thái, nên DP hợp lệ.
  - Chi phí trạng thái = `span + 0.3 × Σ max(0, fret − 12)`.
  - Chi phí chuyển = `|tâm_trước − tâm_này|`, bằng 0 nếu một trong hai là `None`.
  - Mỗi slot giữ 64 đường đi rẻ nhất (beam search, không phải Viterbi đầy đủ).
  - Hoà chi phí thì chọn theo thứ tự: tổng phím nhỏ hơn, rồi bộ `(string, fret)` nhỏ hơn theo thứ tự từ điển, để kết quả luôn xác định.

**Xuất file (R6, R7, R8)**
- **B14. Không ghi đè.** Tên file là `<stem đầu vào>.gp5` và `<stem>.musicxml` trong `out_dir`. Nếu file đã tồn tại mà không có `--force` thì sinh `OutputError` *trước khi* chạy bước xử lý nào, để không phí thời gian.
- **B15. Ghi an toàn.** Writer tự lo việc ghi file tạm: ghi ra `<stem>.tmp-<pid>.<ext>` cùng thư mục (giữ đúng đuôi để thư viện không đổi tên), rồi `os.replace` sang đích cuối. Mọi ngoại lệ trong writer (`OSError`, `UnicodeEncodeError`, `ValueError`, …) đều được xoá file tạm và bọc thành `OutputError`.
- **B16. Tách trường độ** (`durations.split`), dùng chung cho nốt và dấu lặng.
  - Đầu tiên cắt tại vạch nhịp.
  - Trong mỗi ô nhịp, đi tham lam từ vị trí đầu, mỗi lần chọn trường độ lớn nhất `d ∈ {16, 12, 8, 6, 4, 3, 2, 1}` slot sao cho `d ≤ phần còn lại` và vị trí hiện tại chia hết cho trường độ gốc của `d` (với `d` có chấm: 12 → 8, 6 → 4, 3 → 2). Cách này giữ các mảnh thẳng hàng với phách.
  - Trường độ có chấm (12, 6, 3) chỉ được chọn khi `d` **bằng đúng** phần còn lại của đoạn, tức là nó kết thúc nốt hoặc chạm vạch nhịp. Ví dụ: 6 ô từ vị trí 2 → 2+4 (không phải 3+1+2), 8 ô từ vị trí 4 → 4+4, 7 ô từ vị trí 0 → 4+3, 6 ô từ vị trí 0 → 6.
  - Các mảnh của cùng một nốt nối với nhau bằng tie. Dấu lặng thì không có tie.
- **B17. `.gp5`.**
  - Ghi bằng `guitarpro.write(song, path, version=(5, 1, 0))`.
  - Bài gồm một track "Guitar" (MIDI program 25), 6 dây theo `tuning`, một tempo (làm tròn sang số nguyên), time signature theo `rhythm`.
  - Velocity cố định ở mức *forte* (MVP).
  - Phần sau tie dùng `NoteType.tie`.
  - `title` = stem đầu vào sau khi gập về ASCII (NFKD, `đ/Đ → d/D`, bỏ dấu, ký tự khác ngoài ASCII in được thì thay bằng `_`), tối đa 64 ký tự, để tránh lỗi encoding cp1252 của định dạng GP5.
- **B18. `.musicxml`.**
  - Một part, khuông tab 6 dòng (TAB clef).
  - Mỗi nốt có cao độ cùng `<technical><string>` và `<fret>`, tách trường độ và tie như B16.
  - `<staff-details>` gồm `<staff-lines>6</staff-lines>` và một `<staff-tuning>` cho mỗi dây theo `tuning`.
  - Nếu spike cho thấy music21 không tự sinh `staff-details` hoặc TAB clef, thì `export_musicxml` chèn phần đó vào XML của chính mình bằng `xml.etree.ElementTree` trước khi ghi.
- **B19.** Một định dạng ghi lỗi thì vẫn thử ghi định dạng còn lại. `convert` không ném lỗi trong trường hợp này mà trả `ConvertResult` có `errors` khác rỗng. CLI vẫn in đường dẫn các file đã ghi thành công và thoát với mã 5.

**Vận hành (R9, R10)**
- **B20.** Pipeline không mở kết nối mạng nào. Weights model đọc từ package đã cài.
- **B21.** Trước mỗi bước in một dòng `[k/6] <bước>…` ra stderr. Cuối cùng in tóm tắt: số nốt, tempo kèm nguồn (detected/user), số cảnh báo, tổng thời gian.

## Non-Functional

- **Hiệu năng:** bài 3 phút xử lý xong trong ≤ 180 s trên CPU laptop 4 nhân, không cần GPU (G3). Basic-pitch chiếm phần lớn thời gian. Beam search tốn O(slots × 64 × 720), cỡ vài giây cho bài 3 phút. Nếu đo thấy chậm thì cắt bớt các cách bấm có độ trải > 7 trước khi tính.
- **Bộ nhớ:** audio 10 phút ở 22,05 kHz mono khoảng 53 MB float32. Tổng RAM dự kiến < 2 GB, chủ yếu do TensorFlow.
- **Độ chính xác:** Note F1 ≥ 0.70 (G1) trên bộ đánh giá ở mục Testing.
- **Bảo mật:**
  - Đầu vào là file cục bộ do chính người dùng chọn.
  - Giới hạn kích thước, thời lượng header và số mẫu thực decode (B1, B2) chặn file quá lớn hoặc header giả (CWE-400).
  - Không thực thi nội dung nào trong file. Không gọi mạng (B20).
  - Lỗi chỉ in thông điệp ngắn, không in stack trace trừ khi bật `-v` (CWE-209).
  - Phụ thuộc được quét bằng `pip-audit` (xem ADR-0001).
- **Quan sát:** dùng `logging` chuẩn (logger `lamnhac`) ra stderr. Mức INFO cho tiến độ, DEBUG cho tham số và thời gian từng bước. Không log nội dung audio.
- **Kiểu:** `mypy --strict` cho `src/`. Các thư viện không có type (`librosa`, `soundfile`, `basic_pitch`, `music21`, `guitarpro`, `mir_eval`) được khai `ignore_missing_imports` trong `pyproject.toml` và chỉ được dùng bên trong module adapter tương ứng.

## Testing

| Mức | Phạm vi | Behavior / PRD |
|-----|---------|----------------|
| Unit | `audio`: kiểm tra đường dẫn, đuôi, kích thước, thời lượng; file có header khai ngắn nhưng dữ liệu dài bị dừng ở 605 s | B1, B2 |
| Unit | `transcribe`: tính dải tần từ tuning chuẩn và Drop D (min ≤ 73,4 Hz). Đổi tuple sang `NoteEvent` với `predict` được thay bằng stub | B3, B4 |
| Unit | `rhythm`: ánh xạ `p(t)` với lưới phách đều và lưới phách trôi ±3%; chọn phách mạnh; ô pickup; hợp âm; cắt nốt ngân; bù dấu lặng. Có test cho 4/4, **3/4 và 6/8** | B5–B10, R12 |
| Unit | Độ chính xác tempo: chuỗi nốt gảy tổng hợp (Karplus–Strong) ở 97 BPM, tempo đoán sai ≤ 5% | B5, B6, R4 |
| Unit | `durations.split`: mọi `(start, length)` với `length` 1–48 trong 4/4, 3/4, 6/8. Tổng các mảnh đúng, mảnh thẳng hàng phách, không vắt qua vạch nhịp | B16 |
| Unit | `tab.assign`: thang âm, hợp âm mở (tâm `None`), nốt ngoài tầm, >6 nốt, cặp 40+41 (không gán được), Drop D, kết quả xác định. Kiểm tính hợp lệ của G4 trên dữ liệu ngẫu nhiên (property test) | B11–B13, R5, R11 |
| Unit | Gập tiêu đề: `"Bài hát đầu tiên"` → `"Bai hat dau tien"` | B17 |
| Integration | `export_gp5`: ghi rồi đọc lại bằng `guitarpro.parse`, so tempo, tuning, dây/phím, tổng trường độ từng ô. Không còn file `.tmp-*` | B15, B17 |
| Integration | `export_musicxml`: ghi rồi đọc lại bằng `music21.converter.parse`. XML có `staff-tuning` đúng với Drop D | B15, B18 |
| Integration | `pipeline.convert` với fixture MP3 khoảng 5 s trong repo (gảy tổng hợp, có tab chuẩn kèm theo), chạy basic-pitch thật. Kiểm "≥ 80% số nốt của fixture được nhận". Socket bị chặn bằng fixture monkeypatch `socket.socket.connect` | B3, B4, B14, B19, B20, R9 |
| E2E | Gọi CLI qua `subprocess`: mã thoát 0, 2, 3, 5, nội dung stdout và stderr (có các dòng `[k/6]`) | CLI, B14, B19, B21, R10 |
| Eval (`@pytest.mark.eval`, mặc định không chạy) | Note F1 bằng `mir_eval.transcription.precision_recall_f1_overlap(..., onset_tolerance=0.05, offset_ratio=None)` trên các bản solo của GuitarSet (CC BY 4.0), tải về ngoài repo. Đo thời gian bài 3 phút (G3) | G1, G3 |
| Thủ công | Mở các file mẫu trong Guitar Pro (phiên bản owner đang dùng) | R6, R7, G2 |

Gates sẽ ghi vào `sdlc.config.json`: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy --strict src`, `uv run pytest -m "not eval"`.

## Rollout

Công cụ cá nhân, không có migration hay feature flag. Thứ tự làm:
1. **Spike cài đặt (ADR-0001).** Đạt khi đủ cả năm điều kiện:
   - `uv add basic-pitch` resolve được trên Windows với Python 3.11;
   - `predict` chạy được trên file mẫu;
   - `soundfile` decode được MP3 mà không cần ffmpeg;
   - PyGuitarPro ghi được `.gp5` có title ASCII, và Guitar Pro mở được;
   - kiểm tra được music21 có tự sinh `staff-tuning` và TAB clef hay không (quyết định có cần nhánh xử lý XML ở B18).

   Nếu basic-pitch không cài được thì làm phương án onnxruntime và viết ADR mới.
2. Pipeline đầy đủ, chỉ xuất MusicXML.
3. Xuất `.gp5`.
4. Các tính năng could: R11, R12.

Muốn quay lại bản cũ thì checkout commit trước. Công cụ không có trạng thái lưu lại nào.

## Traceability

| PRD | Behavior | Sequence |
|-----|----------|----------|
| R1 | B1, B2 | §1 |
| R2 | B1, B2 | §2 |
| R3 | B3, B4 | §1, §3 |
| R4 | B5–B10 | §1 |
| R5 | B12, B13 | §1 |
| R6 | B14, B15, B16, B18, B19 | §1, §4 |
| R7 | B14, B15, B16, B17, B19 | §1, §4 |
| R8 | CLI, B14 | §1, §2, §4 |
| R9 | B20 | §1 |
| R10 | B21 | §1 |
| R11 | B3, B11, B12, B18 | – |
| R12 | Data Model `bar_slots`, B8, B16 | – |
| R13 | B4a, `--keep-harmonics` | §1 |
| R14 | B12, `--max-fret` | §1 |
