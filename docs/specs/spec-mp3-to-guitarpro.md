# Spec: MP3 → Guitar Pro

**Status:** Draft · **PRD:** docs/prd/PRD-mp3-to-guitarpro.md · **ADRs:** ADR-0001 · **Date:** 2026-11-13

## Overview

`lamnhac` là CLI Python 3.11 chạy offline trên Windows. Lệnh `lamnhac convert` đọc một file MP3 guitar solo và cho ra file `.gp5` và/hoặc `.musicxml` chứa tab. Pipeline có 6 bước tuần tự: kiểm tra và giải mã audio → nhận nốt (basic-pitch) → ước lượng tempo/phách (librosa) → lượng tử hoá vào ô nhịp → gán dây/phím → xuất file. Spec này phủ R1–R12 của PRD.

Bố cục mã nguồn (`src/` layout, quản lý bằng uv):

```
src/lamnhac/
  cli.py              # argparse, mã thoát, in tiến độ
  pipeline.py         # convert(): chạy các bước theo thứ tự
  models.py           # dataclass dùng chung (bên dưới)
  errors.py           # cây ngoại lệ LamnhacError
  audio.py            # kiểm tra file, đọc thời lượng, decode
  transcribe.py       # adapter basic-pitch → list[NoteEvent]
  rhythm.py           # tempo, phách, lượng tử hoá → Score
  tab.py              # gán dây/phím (Viterbi) → TabScore
  export_gp5.py       # TabScore → .gp5 (PyGuitarPro)
  export_musicxml.py  # TabScore → .musicxml (music21)
tests/
```

Mỗi bước chỉ phụ thuộc vào `models.py`. Riêng `transcribe.py`, `export_gp5.py` và `export_musicxml.py` được import thư viện ngoài của ADR-0001, nên có thể thay backend mà không chạm vào các bước khác.

## Data Model

Không có database. Các model nội bộ trong `models.py`, đều là `@dataclass(frozen=True)`:

| Model | Trường | Ràng buộc |
|-------|--------|-----------|
| `AudioClip` | `samples: np.ndarray` (mono float32), `sample_rate: int`, `duration_s: float`, `source: Path` | `sample_rate` = 22050 (giá trị basic-pitch dùng), `0 < duration_s ≤ 600` |
| `NoteEvent` | `onset_s: float`, `offset_s: float`, `pitch: int` (MIDI), `velocity: float` (0–1) | `offset_s > onset_s`, `0 ≤ pitch ≤ 127` |
| `Tuning` | `strings: tuple[int, ...]` (MIDI, dây 1 = cao nhất) | 6 dây. Mặc định `(64, 59, 55, 50, 45, 40)` = E chuẩn |
| `TimeSignature` | `numerator: int`, `denominator: int` | `denominator ∈ {2, 4, 8}`, `1 ≤ numerator ≤ 16` |
| `RhythmInfo` | `tempo_bpm: float`, `anchor_s: float`, `time_signature: TimeSignature`, `tempo_source: Literal["detected", "user"]` | `30 ≤ tempo_bpm ≤ 300` |
| `GridNote` | `pitch: int`, `velocity: float` | – |
| `Slot` | `start: int`, `length: int` (đơn vị: nốt móc kép = 1/16), `notes: tuple[GridNote, ...]` | `length ≥ 1`. `notes` rỗng = dấu lặng |
| `Score` | `rhythm: RhythmInfo`, `slots: tuple[Slot, ...]` | Các slot liền nhau, không chồng nhau, tổng độ dài là bội số của độ dài ô nhịp |
| `TabNote` | `pitch: int`, `string: int` (1–6), `fret: int` (0–24) | `tuning.strings[string-1] + fret == pitch` |
| `TabSlot` | `start: int`, `length: int`, `notes: tuple[TabNote, ...]` | Mỗi dây xuất hiện tối đa một lần |
| `TabScore` | `rhythm: RhythmInfo`, `tuning: Tuning`, `slots: tuple[TabSlot, ...]`, `title: str` | – |
| `ConvertOptions` | `input: Path`, `out_dir: Path`, `formats: frozenset[Literal["gp5", "musicxml"]]`, `tempo: float \| None`, `tuning: Tuning`, `time_signature: TimeSignature`, `force: bool` | Đã được `cli.py` kiểm tra |
| `ConvertResult` | `outputs: tuple[Path, ...]`, `errors: tuple[str, ...]` (lỗi ghi từng định dạng), `warnings: tuple[str, ...]`, `rhythm: RhythmInfo`, `note_count: int` | – |

## Interfaces

### CLI

```
lamnhac convert <input> [-o OUT_DIR] [--format gp5,musicxml] [--tempo BPM]
                [--tuning "E A D G B E"] [--time 4/4] [--force] [-v]
```

| Đối số | Mặc định | Kiểm tra |
|--------|----------|----------|
| `input` | bắt buộc | File tồn tại, đuôi `.mp3`, ≤ 50 MB, thời lượng ≤ 600 s |
| `-o/--out-dir` | thư mục chứa `input` | Tạo nếu chưa có. Phải ghi được |
| `--format` | `gp5,musicxml` | Danh sách con không rỗng của `{gp5, musicxml}` |
| `--tempo` | tự đoán | Số thực 30–300 |
| `--tuning` | `E A D G B E` | 6 tên nốt từ dây trầm đến dây cao, mỗi tên khớp `^[A-G][#b]?$`, quãng tám suy ra theo B11 |
| `--time` | `4/4` | `N/D`, ràng buộc như `TimeSignature` |
| `--force` | tắt | Cho phép ghi đè file đầu ra đã có |
| `-v/--verbose` | tắt | Log mức DEBUG ra stderr |

| Mã thoát | Nghĩa | Ngoại lệ |
|----------|-------|----------|
| 0 | Thành công (có thể kèm cảnh báo) | – |
| 2 | Đối số sai | argparse / `UsageError` |
| 3 | Đầu vào không hợp lệ | `InputError` |
| 4 | Lỗi khi xử lý (decode, model, không tìm thấy nốt nào) | `ProcessingError` |
| 5 | Không ghi được đầu ra | `OutputError` |
| 1 | Lỗi không lường trước | các lỗi khác. Chỉ in một dòng, stack trace chỉ có khi bật `-v` |

stdout chỉ in đường dẫn các file đã tạo, mỗi file một dòng, để script khác dùng được. Tiến độ, cảnh báo và lỗi ra stderr.

### API nội bộ

| Hàm | Input | Output | Lỗi |
|-----|-------|--------|-----|
| `audio.load(path)` | `Path` | `AudioClip` | `InputError` |
| `transcribe.transcribe(clip)` | `AudioClip` | `list[NoteEvent]` | `ProcessingError` |
| `rhythm.analyze(clip, tempo, time_sig)` | `AudioClip`, `float \| None`, `TimeSignature` | `RhythmInfo` | `ProcessingError` |
| `rhythm.quantize(notes, rhythm)` | `list[NoteEvent]`, `RhythmInfo` | `Score` | – |
| `tab.assign(score, tuning)` | `Score`, `Tuning` | `tuple[TabScore, list[str]]` (kèm cảnh báo) | – |
| `export_gp5.write(tab, path)` | `TabScore`, `Path` | `None` | `OutputError` |
| `export_musicxml.write(tab, path)` | `TabScore`, `Path` | `None` | `OutputError` |
| `pipeline.convert(opts, progress)` | `ConvertOptions`, `Callable[[str], None]` | `ConvertResult` | các lớp con của `LamnhacError` |

## Behavior

**Đầu vào (R1, R2)**
- **B1.** Kiểm tra theo thứ tự, dừng ở lỗi đầu tiên: tồn tại → là file thường → đuôi `.mp3` (không phân biệt hoa thường) → kích thước ≤ 50 MB → đọc được header (`soundfile.info`) → thời lượng ≤ 600 s. Mọi vi phạm sinh `InputError`, thông điệp nêu rõ điều kiện bị vi phạm và không lộ chi tiết nội bộ.
- **B2.** Decode bằng `librosa.load(path, sr=22050, mono=True)`. Stereo được trộn xuống mono. Decode lỗi hoặc ra 0 mẫu thì sinh `InputError("file audio hỏng hoặc rỗng")`.

**Nhận nốt (R3)**
- **B3.** Gọi `basic_pitch.inference.predict` với model ICASSP-2022 đóng gói sẵn trong package, các tham số `onset_threshold=0.5`, `frame_threshold=0.3`, `minimum_note_length=58` (ms), `minimum_frequency=75`, `maximum_frequency=1400` (Hz, phủ E2–E6). Các ngưỡng là hằng số trong `transcribe.py` để chỉnh sau khi đo G1. Kết quả được đổi sang `NoteEvent`, sắp theo `onset_s`.
- **B4.** Không có nốt nào sau B3 thì sinh `ProcessingError("không nhận được nốt nào — file có phải guitar không?")`.

**Nhịp (R4, R12)**
- **B5.** Nếu có `--tempo`, dùng giá trị đó (`tempo_source="user"`). Nếu không, `librosa.beat.beat_track` trên `clip` cho tempo, sau đó đưa vào khoảng 60–200 BPM bằng cách nhân hoặc chia đôi, và in ra stderr: `tempo đoán được: N BPM (dùng --tempo để sửa)`.
- **B6.** Mốc thời gian `anchor_s` = phách đầu tiên librosa tìm được, nếu không tìm được phách thì bằng onset nốt đầu tiên. Lùi `anchor_s` từng độ dài ô nhịp cho đến khi `anchor_s ≤ onset nốt đầu tiên`. Các ô nhịp trước nốt đầu tiên bị bỏ, nên bản nhạc bắt đầu ở ô chứa nốt đầu tiên.
- **B7.** Lưới là nốt móc kép: `step_s = 60 / tempo / 4 × (4 / denominator)`. Vị trí lưới của một nốt là `start = round((onset_s − anchor_s) / step_s)`, độ dài là `max(1, round((offset_s − onset_s) / step_s))`.
- **B8.** Các nốt có cùng `start` gộp thành một slot (hợp âm). Nếu cùng `start` có hai nốt trùng cao độ thì giữ nốt có `velocity` lớn hơn.
- **B9.** Bản nhạc chỉ có một bè. Độ dài slot = `min(độ dài dài nhất trong nhóm, start slot kế − start slot này)`, nên nốt ngân qua onset kế tiếp bị cắt (giới hạn đã biết của MVP). Khoảng trống giữa hai slot thành slot dấu lặng. Ô nhịp cuối được bù dấu lặng cho đủ.

**Gán tab (R5, R11)**
- **B10.** Một nốt đặt được trên dây `s` khi `0 ≤ pitch − tuning[s] ≤ 24`. Nốt không đặt được trên dây nào thì bị bỏ, kèm cảnh báo `bỏ N nốt ngoài tầm cây đàn`. Slot có nhiều hơn 6 nốt thì giữ 6 nốt có velocity cao nhất, kèm cảnh báo.
- **B11.** Tên nốt trong `--tuning` được đổi sang MIDI bằng cách chọn quãng tám gần nhất với dây tương ứng của E chuẩn. Ví dụ `D A D G B E` cho dây 6 = D2 (38).
- **B12.** Gán bằng Viterbi qua các slot có nốt. Trạng thái là một cách bấm hợp âm: mỗi nốt một dây khác nhau, các phím ≠ 0 trải không quá 4 phím. Hợp âm không có cách bấm nào trải ≤ 4 phím thì nới giới hạn và ghi cảnh báo. Chi phí của trạng thái = `span + 0.3 × Σ max(0, fret − 12)`, cộng thêm `|tâm_trước − tâm_này|` khi chuyển trạng thái. `tâm` là trung bình các phím ≠ 0. Dây buông không làm đổi `tâm`. Mỗi slot giữ tối đa 64 trạng thái rẻ nhất. Hoà chi phí thì chọn trạng thái có phím thấp hơn.

**Xuất file (R6, R7, R8)**
- **B13.** Tên file là `<stem đầu vào>.gp5` và `<stem>.musicxml` trong `out_dir`. Nếu file đã tồn tại mà không có `--force` thì sinh `OutputError` *trước khi* chạy bước xử lý nào, để không phí thời gian. Mỗi file được ghi ra file tạm `*.tmp` cùng thư mục rồi `os.replace`, nên không bao giờ để lại file ghi dở.
- **B14.** `.gp5`: một bài với một track "Guitar" (MIDI program 25, acoustic steel), 6 dây theo `tuning`, một tempo, time signature theo `rhythm`. Mỗi `TabSlot` có độ dài `L` được tách thành các trường độ biểu diễn được (1, 2, 4, 8, 16, có hoặc không có chấm), nối bằng tie. Slot vắt qua vạch nhịp cũng được tách và tie. Các phần sau tie dùng `NoteType.tie`.
- **B15.** `.musicxml`: một part, khuông tab 6 dòng. Mỗi nốt có cao độ cùng `<technical><string>` và `<fret>`, tách trường độ và tie như B14. Tuning được ghi trong `<staff-details>`.
- **B16.** Một định dạng ghi lỗi thì vẫn thử ghi định dạng còn lại. `convert` không ném lỗi trong trường hợp này mà trả `ConvertResult` có `errors` khác rỗng. CLI vẫn in đường dẫn các file đã ghi thành công và thoát với mã 5.

**Vận hành (R9, R10)**
- **B17.** Pipeline không mở kết nối mạng nào. Weights model đọc từ package đã cài.
- **B18.** Trước mỗi bước in một dòng `[k/6] <bước>…` ra stderr. Cuối cùng in tóm tắt: số nốt, tempo, các cảnh báo, tổng thời gian.

## Non-Functional

- **Hiệu năng:** bài 3 phút xử lý xong trong ≤ 180 s trên CPU laptop 4 nhân, không cần GPU (G3). Basic-pitch chiếm phần lớn thời gian. Viterbi tốn O(slots × 64 × 64), không đáng kể.
- **Bộ nhớ:** audio 10 phút ở 22,05 kHz mono khoảng 53 MB float32. Tổng RAM dự kiến < 2 GB, chủ yếu do TensorFlow.
- **Độ chính xác:** Note F1 ≥ 0.70 (G1) trên bộ đánh giá ở mục Testing.
- **Bảo mật:** đầu vào là file cục bộ do chính người dùng chọn. Giới hạn kích thước và thời lượng (B1) chặn file quá lớn. Không thực thi nội dung nào trong file. Không gọi mạng (B17). Lỗi chỉ in thông điệp ngắn, không in stack trace trừ khi bật `-v`.
- **Quan sát:** dùng `logging` chuẩn (logger `lamnhac`) ra stderr. Mức INFO cho tiến độ, DEBUG cho tham số và thời gian từng bước. Không log nội dung audio.

## Testing

| Mức | Phạm vi | Behavior |
|-----|---------|----------|
| Unit | `audio`: kiểm tra đường dẫn, đuôi, kích thước, thời lượng, dùng file sinh trong `tmp_path` | B1, B2 |
| Unit | `rhythm.quantize`: nốt tổng hợp → slot, hợp âm, cắt nốt ngân, bù dấu lặng, `anchor` | B6–B9 |
| Unit | `rhythm.analyze`: tempo do người dùng nhập, đưa tempo về 60–200 | B5 |
| Unit | `tab.assign`: thang âm, hợp âm mở, nốt ngoài tầm, >6 nốt, Drop D, tính hợp lệ (G4) | B10–B12 |
| Unit | Tách trường độ và tie: mọi `L` từ 1 đến 32 tách được đúng | B14, B15 |
| Integration | `export_gp5`: ghi rồi đọc lại bằng `guitarpro.parse`, so tempo, tuning, dây/phím, tổng trường độ | B14 |
| Integration | `export_musicxml`: ghi rồi đọc lại bằng `music21.converter.parse` | B15 |
| Integration | `pipeline.convert` với một MP3 tổng hợp ngắn trong repo (thang âm C sinh bằng sine, khoảng 5 s), chạy basic-pitch thật | B3, B4, B13, B16, B18 |
| E2E | Gọi CLI qua `subprocess`: mã thoát 0, 2, 3, 5, nội dung stdout và stderr | CLI, B13, B16 |
| Eval (`@pytest.mark.eval`, mặc định không chạy) | Note F1 bằng `mir_eval.transcription` trên các bản solo của GuitarSet (CC BY 4.0), tải về ngoài repo | G1 |
| Thủ công | Mở các file mẫu trong Guitar Pro (phiên bản owner đang dùng) | R6, R7, G2 |

Gates sẽ ghi vào `sdlc.config.json`: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy --strict src`, `uv run pytest -m "not eval"`.

## Rollout

Công cụ cá nhân, không có migration hay feature flag. Thứ tự làm:
1. Spike cài đặt (ADR-0001): `uv add basic-pitch` trên Windows với Python 3.11, transcribe được file mẫu, và xác nhận soundfile decode MP3 mà không cần ffmpeg. Nếu thất bại thì làm phương án onnxruntime và viết ADR mới.
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
| R4 | B5–B9 | §1 |
| R5 | B10, B12 | §1 |
| R6 | B13, B15, B16 | §1, §4 |
| R7 | B13, B14, B16 | §1, §4 |
| R8 | CLI, B13 | §1, §2, §4 |
| R9 | B17 | §1 |
| R10 | B18 | §1 |
| R11 | B11, B12 | – |
| R12 | B7, `--time` | – |
