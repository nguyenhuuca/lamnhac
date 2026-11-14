# Spec: Vòng hợp âm từ bài hát → Guitar Pro

**Status:** Approved (2026-11-14, rev 3) · **PRD:** docs/prd/PRD-chords-from-song.md · **ADRs:** không cần ADR mới (chỉ dùng librosa, numpy, PyGuitarPro đã có; ADR-0001 vẫn áp dụng) · **Date:** 2026-11-14

## Overview

Spec này thêm lệnh `lamnhac chords <file.mp3>`. Lệnh đọc một bài hát đầy đủ và cho ra `<tên>.chords.gp5`: một track guitar tuning chuẩn, mỗi phách gảy một hợp âm, có tên và sơ đồ hợp âm mỗi khi hợp âm đổi, và có ghi giọng của bài. Tuỳ chọn ghi thêm `<tên>.chords.txt` là bảng hợp âm theo ô nhịp.

Pipeline có 4 bước:
1. đọc audio: dùng lại `audio.load`;
2. phân tích nhịp: dùng lại `rhythm.analyze` trên các onset do librosa phát hiện;
3. nhận hợp âm: module mới `chords.py`, dùng chroma theo đơn vị gảy, so với mẫu 24 hợp âm cộng N, làm mượt bằng Viterbi, rồi đoán giọng;
4. xuất file: `export_gp5` mở rộng để ghi sơ đồ hợp âm và giọng, và module mới `export_chords_txt.py`.

Spec phủ R1–R10 của PRD.

**Vì sao không cần ADR mới:** spec không thêm thư viện, dịch vụ hay định dạng dữ liệu lâu dài nào. Cách nhận hợp âm nằm gọn trong `chords.py` và đổi được mà không chạm phần khác. Nếu bước đo cho thấy cần model học sâu hoặc tách nguồn, việc đó sẽ có ADR riêng, theo đúng PRD.

```
src/lamnhac/
  cli.py                 # + subcommand "chords"; tham số dùng chung tách thành helper
  pipeline.py            # + chords(opts, progress); _prepare_outputs tổng quát hoá
  models.py              # + Onset, OnsetLike, ChordLabel, MusicKey, ChordShape, ChordDiagram, ChordChart, ChordsOptions, ChordsResult
  rhythm.py              # + onsets(clip); analyze() nhận OnsetLike (NoteEvent vẫn hợp lệ)
  chords.py              # MỚI: chroma → nhãn theo đơn vị gảy → giọng → ô nhịp → tên hợp âm
  chord_shapes.py        # MỚI: bảng thế bấm cho 24 hợp âm (tuning chuẩn)
  export_gp5.py          # write(..., diagrams=None, key=None)
  export_chords_txt.py   # MỚI: ChordChart → .chords.txt
tests/eval/test_eval_chords.py  # MỚI: R10
tests/eval/answers.py           # MỚI: đọc file đáp án, Levenshtein, độ khớp (có unit test riêng)
```

## Data Model

Mọi dataclass đều `frozen=True` trong `models.py`.

| Kiểu | Trường | Ràng buộc |
|------|--------|-----------|
| `OnsetLike` (Protocol) | `onset_s: float`, `velocity: float` | `NoteEvent` đã thoả, không cần sửa |
| `Onset` | `onset_s: float`, `velocity: float` | `onset_s ≥ 0`, `0 ≤ velocity ≤ 1`. Dùng tên trường giống `NoteEvent` để code nhịp không phân biệt hai loại |
| `ChordLabel` | `root: int \| None`, `minor: bool` | `root` 0..11 (0 = C); `None` = không có hợp âm (N), khi đó `minor = False` |
| `MusicKey` | `tonic: int`, `minor: bool` | `tonic` 0..11. Đặt tên `MusicKey` để không trùng `Key` trong `tab.py` |
| `ChordChart` | `rhythm: RhythmInfo`, `key: MusicKey`, `unit_slots: int`, `labels: tuple[ChordLabel, ...]`, `bar1_slot: int`, `capo: int` | `labels[j]` là hợp âm của đơn vị gảy j, phủ các slot lưới `[j·unit_slots, (j+1)·unit_slots)`. `bar1_slot` là slot lưới bắt đầu ô 1, có thể âm (C11) |
| `ChordsOptions` | `input`, `out_dir`, `formats: frozenset[Literal["gp5","txt"]]`, `tempo`, `time_signature`, `pickup_slots`, `capo: int`, `force` | `capo` 0..11 |
| `ChordsResult` | `outputs`, `errors`, `warnings`, `chart: ChordChart`, `change_count: int` | `change_count` theo định nghĩa C11 |

**Refactor trong `rhythm.py`** (commit riêng, không đổi hành vi):
- Chú thích kiểu của `analyze`, `_pick_downbeat`, `_downbeat_from_pickup`, `align_beats`, `align_beats_locally` đổi từ `NoteEvent` sang `OnsetLike`.
- Các hàm này vốn chỉ đọc `onset_s` và `velocity`, nên `pipeline.convert` và mọi test hiện có giữ nguyên, kể cả các lời gọi trong `tests/test_rhythm.py`.

## Interfaces

| Hàm / lệnh | Input | Output | Lỗi |
|------------|-------|--------|-----|
| `lamnhac chords FILE [-o DIR] [--format gp5,txt] [--tempo BPM] [--time N/D] [--pickup N] [--capo N] [--force] [-v]` | tham số dòng lệnh. `--tempo`, `--time`, `--pickup` giống hệt `convert` (pickup tính theo phách, nhận nửa phách) | stdout: đường dẫn các file đã ghi; stderr: tiến độ, bảng hợp âm, tổng kết | mã thoát như `convert`: 0, 2, 3, 4, 5, 1 |
| `rhythm.onsets(clip)` | `AudioClip` | `list[Onset]` | – |
| `chords.recognize(clip, rhythm, unit_slots)` | | `tuple[ChordLabel, ...]` theo đơn vị gảy | `ProcessingError` nếu mọi đơn vị đều là N |
| `chords.detect_key(labels)` | | `MusicKey` | – |
| `chords.bar_start(labels, rhythm, unit_slots)` | | `int`: `bar1_slot` | – |
| `chords.name(label, key, capo=0)` | | `str`, ví dụ `"Bb"`, `"F#m"`, `"N"` | – |
| `chords.key_name(key)` | | `str`, ví dụ `"La thứ (Am)"` | – |
| `chord_shapes.shape(root, minor)` | | `ChordShape(frets: tuple[int, ...]` dây 6→1, −1 = không gảy, `first_fret: int)` | – |
| `pipeline.chords(opts, progress)` | `ChordsOptions` | `ChordsResult` | các lớp con của `LamnhacError` |
| `export_gp5.write(tab, path, diagrams=None, key=None)` | `diagrams: Mapping[int, ChordDiagram] \| None` (khoá là slot bắt đầu của `TabSlot`); `key: MusicKey \| None` | – | `OutputError` |
| `export_chords_txt.write(chart, title, path)` | | – | `OutputError` |

`ChordShape(frets, first_fret)` và `ChordDiagram(name: str, label: ChordLabel, shape: ChordShape, sharp: bool)` là dataclass `frozen` trong `models.py`.

## Behavior

**Lệnh và đầu ra (R1, R7)**
- **C1. Tham số.** Subcommand `chords` dùng chung các helper của `convert` để đọc `-o`, `--tempo`, `--time`, `--pickup`, `--force`, `-v`, và dùng cùng thông báo lỗi. Tham số sai thì thoát mã 2.
  - `--format` nhận danh sách con không rỗng của `gp5,txt`, mặc định `gp5`. `_parse_formats` nhận thêm tham số là bộ định dạng hợp lệ.
  - `--capo` là số nguyên 0..11, mặc định 0.
  - `chords` không có `--tuning`, `--max-fret`, `--sensitivity`, `--filter-harmonics`.
- **C2. File đầu ra.**
  - Tên file là `<stem>.chords.gp5` và `<stem>.chords.txt`.
  - `pipeline._prepare_outputs(out_dir, stem, targets, force)` nhận danh sách `(định dạng, hậu tố)`. `convert` gọi với `[("gp5", ".gp5"), ("musicxml", ".musicxml")]`, `chords` gọi với `[("gp5", ".chords.gp5"), ("txt", ".chords.txt")]`.
  - Kiểm tra trùng file và tạo thư mục **trước** khi xử lý, như B14. Có file mà không có `--force` thì thoát mã 5.
  - Một định dạng ghi lỗi thì vẫn ghi các định dạng còn lại, gom lỗi vào `errors`, và thoát mã 5, giống `convert`.
- **C3. Đầu vào và an toàn.** Đầu vào kiểm tra như B1–B2 (`audio.load`: chỉ `.mp3`, ≤ 50 MB, ≤ 600 s). Ghi file an toàn (tmp rồi `os.replace`) như B15. Chạy offline, không có lời gọi mạng nào. Lệnh `chords` không import `transcribe`, nên không nạp TensorFlow.
- **C4. Tiến độ và tổng kết.**
  - Tiến độ in ra stderr theo 4 bước: `[1/4] đọc audio…`, `[2/4] phân tích nhịp…`, `[3/4] nhận hợp âm…`, `[4/4] xuất file…`.
  - Dòng tổng kết có dạng `xong: 42 lần đổi hợp âm, giọng La thứ (Am), tempo 96 BPM (detected), 0 cảnh báo, 12.3s`.
  - **Cảnh báo duy nhất** là `bỏ N phách không có hợp âm ở đầu bài` khi C11 bỏ đoạn N ở đầu.
  - Nếu tempo là đoán thì in thêm dòng gợi ý như B19.

**Nhịp (R6)**
- **C5. Onset.** `rhythm.onsets(clip)`:
  1. tính `env = librosa.onset.onset_strength(y, sr)`;
  2. lấy `frames = librosa.onset.onset_detect(onset_envelope=env, sr=sr, units="frames", backtrack=False)`;
  3. trả về `Onset(frames_to_time(f), env[f] / env.max())`. Nếu `env.max() == 0` hoặc không có frame nào thì trả về danh sách rỗng, và `analyze` dùng lưới đều như B6.
- **C6. Phân tích nhịp.** `rhythm.analyze(clip, onsets, tempo, time_sig, pickup_slots)` chạy đúng các bước B5–B7b và B8/B8a của spec trước. `downbeat_slot` của bước này là giá trị dự phòng; C11 có thể thay.

**Nhận hợp âm (R2, R3)**
- **C7. Đơn vị gảy và lưới.**
  - Đơn vị gảy dài `unit_slots = 16 / denominator` slot: 4/4 và 3/4 là 4 slot (nốt đen); 6/8 là 2 slot (nốt móc đơn); 2/2 là 8 slot.
  - Biên các đơn vị tính bằng thời điểm của slot lưới `j·unit_slots`, nội suy giữa các phách như B7: `time_of_slot(p)` là hàm ngược của `grid_position`.
  - Hợp âm được nhận theo **đơn vị gảy**. Nhờ vậy ở 6/8 hợp âm đổi được ở slot 6, tức giữa một nốt đen của lưới.
  - Đơn vị đầu tiên bắt đầu ở phách lưới 0. Đoạn intro trước phách 0 bị bỏ.
- **C8. Chroma.**
  1. Tách phần hoà âm: `h = librosa.effects.harmonic(y, margin=3)`. Bước này bớt tiếng trống.
  2. Ước lượng tuning: `tuning = librosa.estimate_tuning(y=h, sr=sr, bins_per_octave=36)`, tính theo phần của một bin 36-bin/quãng tám, khớp với CQT ở bước 3.
  3. Tính một CQT duy nhất: `C = |librosa.cqt(h, sr, hop_length=512, fmin=note_to_hz("C2"), n_bins=216, bins_per_octave=36, tuning=tuning)|` (6 quãng tám, C2–B7).
  4. Chroma toàn dải: `chroma_cqt(C=C, bins_per_octave=36, n_chroma=12, norm=np.inf)`.
  5. Chroma dải trầm C2–B3 (65–247 Hz): `chroma_cqt(C=C[:72], bins_per_octave=36, n_chroma=12, norm=np.inf)`. Nốt bass thường là nốt gốc của hợp âm, còn giọng hát nằm ở dải cao. Lưu ý: ở 36 bin/quãng tám, bộ lọc thấp nhất dài khoảng 0.8 s, nên thay đổi ở dải bass bị nhoè. Chấp nhận ở bản đầu và đo ở R10.
  6. Gộp: `chroma = full + BASS_WEIGHT × bass`, với `BASS_WEIGHT = 0.5`.
  7. **Gộp theo đơn vị:**
     - `idx` = khung của từng biên đơn vị, chặn trong `[0, số khung]`;
     - `librosa.util.sync(chroma, idx, aggregate=np.median, pad=True)`;
     - bỏ cột 0 (phần trước biên đầu tiên), để cột j ứng với đơn vị j;
     - đơn vị không có khung nào (rỗng sau khi chặn) giữ cột 0 và được đánh dấu im lặng (thành N), để số cột luôn bằng số đơn vị. `util.sync` bỏ chỉ số trùng, nên chỉ đồng bộ các đơn vị có khung. *(Chỉnh khi build C-T3.)*
  8. Chuẩn hoá L2 từng cột. Cột có chuẩn 0 được đánh dấu im lặng.
  9. Đơn vị có RMS của `y` dưới −45 dBFS cũng được đánh dấu im lặng.
- **C9. Điểm cho từng nhãn.** Mỗi hợp âm có mẫu nhị phân 12 chiều: trưởng = {0, 4, 7}, thứ = {0, 3, 7}, xoay theo nốt gốc. Mẫu được chuẩn hoá L2, sau đó lấy cosine với chroma của đơn vị.
  - Nhãn N có điểm cố định `N_SCORE = 0.55`. Ở đơn vị im lặng, N được 1.0 và mọi hợp âm khác được 0.
  - Xác suất: `prob = softmax(điểm × TEMPERATURE)` theo trục trạng thái, với `TEMPERATURE = 20`. Ma trận có dạng `(25, số đơn vị)`, hàng 0–11 là trưởng C..B, hàng 12–23 là thứ, hàng 24 là N.
- **C10. Làm mượt (R3).**
  - Gọi `librosa.sequence.viterbi(prob, librosa.sequence.transition_loop(25, P_STAY))`, với `P_STAY = 0.85` khi `unit_slots ≥ 4`. Khi đơn vị ngắn hơn (6/8) thì dùng `P_STAY = 0.92`, vì có nhiều đơn vị hơn cho mỗi hợp âm.
  - Kết quả là một nhãn cho mỗi đơn vị, nên mọi hợp âm kéo dài ít nhất một đơn vị gảy.
- **C10a. Không có hợp âm nào.** Nếu mọi đơn vị đều là N thì sinh `ProcessingError("không nhận được hợp âm nào — bài có nhạc đệm không?")`, thoát mã 4.

Các hằng số `BASS_WEIGHT`, `N_SCORE`, `TEMPERATURE`, `P_STAY` là điểm khởi đầu. Chúng được chỉnh theo bước đo R10, giống cách ngưỡng của `--sensitivity` đã được chọn.

**Ô nhịp (R6)**
- **C11. Chọn ô nhịp 1.**
  - **Lần đổi hợp âm** là đơn vị j có nhãn khác N và khác nhãn của đơn vị j−1. Đơn vị đầu tiên có hợp âm, và đơn vị đầu tiên sau một đoạn N, cũng tính là lần đổi. `change_count` đếm theo định nghĩa này.
  - **Có `--pickup`:** dùng `downbeat_slot` của B8a, không đổi gì.
  - **Không có `--pickup`:**
    - Ứng viên là `o ∈ {0, step, 2·step, …} < bar_slots`, với `step` như B8 (4, hoặc 2 khi `bar_slots % 4 ≠ 0`).
    - Điểm(o) = số lần đổi hợp âm có slot bắt đầu `≡ o (mod bar_slots)`.
    - Ứng viên tốt nhất chỉ thay `downbeat_slot` của B8 khi điểm của nó **lớn hơn ứng viên thứ hai ít nhất 20%** và có ít nhất 4 lần đổi. Nếu không thì giữ B8.
    - Lý do: hợp âm gần như luôn đổi ở phách 1, nhưng với hai hợp âm mỗi ô, phách 3 cũng có nhiều lần đổi. Ngưỡng 20% giúp tránh chọn nhầm; khi hai ứng viên sát nhau, tool quay về B8.
    - *Đây là phần thêm so với "tính như convert" của R6. Owner đã xác nhận khi duyệt spec (2026-11-14).*
  - `bar1_slot` tính đúng như `rhythm.quantize`:
    - bắt đầu từ `downbeat_slot`;
    - lùi từng `bar_slots` cho tới khi `bar1_slot ≤ slot của đơn vị có hợp âm đầu tiên + 0.5`. Đây là ô pickup.
  - Các đơn vị N đứng trước `bar1_slot` bị bỏ, kèm cảnh báo ở C4.

**Giọng và tên hợp âm (R4)**
- **C12. Đoán giọng.**
  1. Lập histogram 12 chiều theo số đơn vị: mỗi đơn vị có hợp âm cộng 1 vào 3 nốt của hợp âm đó, nốt gốc được cộng thêm 0.5.
  2. Tính tương quan Pearson giữa histogram và 24 profile giọng Krumhansl–Kessler (12 trưởng, 12 thứ).
  3. Giọng có tương quan cao nhất được chọn. Hoà thì chọn giọng trưởng, rồi chọn tonic nhỏ hơn.
- **C13. Viết tên hợp âm theo từng hợp âm.**
  - **Giọng dùng dấu giáng** (F, Bb, Eb, Ab, Db, Gb trưởng; D, G, C, F, Bb, Eb thứ): mọi nốt gốc viết bằng dấu giáng.
  - **Giọng dùng dấu thăng** (G, D, A, E, B, F# trưởng; E, B, F#, C#, G# thứ): mọi nốt gốc viết bằng dấu thăng.
  - **Giọng không dấu** (C trưởng, A thứ): pitch class 3, 8, 10 viết Eb, Ab, Bb (các hợp âm bIII, bVI, bVII hay gặp); pitch class 1, 6 viết C#, F#.
  - Hợp âm thứ thêm hậu tố `m`.
  - Có capo thì giọng dùng để đặt tên là **giọng đã hạ** N nửa cung (giọng của thế bấm).
- **C13a. Tên giọng.** Tên giọng in dạng Việt kèm ký hiệu: Đô, Rê, Mi, Fa, Sol, La, Si; ví dụ "Si giáng trưởng (Bb)", "Fa thăng thứ (F#m)".

**Capo (R9, could)**
- **C14.** Khi `capo = N > 0`:
  - Tên và thế bấm lấy từ hợp âm hạ N nửa cung. Âm thanh không đổi.
  - Phím ghi vào tab = phím của thế bấm + N, tức phím tuyệt đối.
  - Ô nhịp 1 có ghi chú văn bản `Capo N`. Không dùng `Track.offset`, vì chưa kiểm cách Guitar Pro 8 hiển thị trường này.
  - Giọng in ra và ghi vào file là giọng thật của bài, kèm "(thế bấm theo capo N)".

**Thế bấm (R5)**
- **C15. Bảng thế bấm.** `chord_shapes.shape(root, minor)` trả về thế bấm cho tuning chuẩn:
  - Thế mở (dây 6→1, −1 = không gảy; đã kiểm đúng nốt): C `[-1,3,2,0,1,0]`, D `[-1,-1,0,2,3,2]`, E `[0,2,2,1,0,0]`, G `[3,2,0,0,0,3]`, A `[-1,0,2,2,2,0]`, Am `[-1,0,2,2,1,0]`, Dm `[-1,-1,0,2,3,1]`, Em `[0,2,2,0,0,0]`.
  - Các hợp âm khác dùng thế chặn: kiểu E (nốt gốc trên dây 6) hoặc kiểu A (nốt gốc trên dây 5), chọn thế có ngăn chặn thấp hơn. Ví dụ F = E-shape ngăn 1, Bm = A-shape ngăn 2.
  - `first_fret = 1` khi phím lớn nhất ≤ 4. Ngược lại, `first_fret` là phím nhỏ nhất khác 0.
  - Có test: mọi thế bấm cho đúng 3 pitch class của hợp âm và độ trải ≤ 4 ngăn.

**Dựng tab và xuất file (R4, R5, R8)**
- **C16. Dựng tab.**
  - Mỗi đơn vị j có `j·unit_slots ≥ bar1_slot` là một `TabSlot(start = j·unit_slots − bar1_slot, length = unit_slots)`. Các đơn vị trước `bar1_slot` (start âm) bị bỏ qua tường minh, có test.
  - Nhãn N thành dấu lặng. Nhãn hợp âm thành các dây có trong thế bấm, `pitch = tuning + phím (+ capo)`.
  - Ô cuối được bù dấu lặng cho đủ.
  - Kết quả là một `TabScore` (title = stem), xuất bằng `export_gp5`.
- **C17. Sơ đồ hợp âm trong `.gp5`.**
  - `diagrams` gồm các `TabSlot` nơi xảy ra một lần đổi hợp âm (C11).
  - `export_gp5` gắn `gp.Chord(length=7)` lên beat đầu của slot đó với:
    - `name`: tên hợp âm, tối đa 22 byte ASCII;
    - `show=True`;
    - `root=PitchClass(root)`, `bass=PitchClass(root)`, `type=ChordType.major/minor`, `sharp` theo C13;
    - `strings`: 7 phần tử, theo thứ tự dây 1→6 rồi −1, là phím **của thế bấm** (tính từ capo). Khi có capo, sơ đồ hiện thế A dưới tên "A", còn nốt trong tab là phím tuyệt đối (C14). Kiểm lại ở bước thủ công trong Guitar Pro 8;
    - `firstFret`, `newFormat=True`.
  - Khi `diagrams` là `None`, `export_gp5` giữ đúng hành vi hiện tại, để `convert` không đổi.
- **C17a. Giọng trong `.gp5` (R4).** Khi `key` khác `None`, `export_gp5`:
  - ghi `song.subtitle = "Key: Am"` (ký hiệu ASCII, thêm `" (capo N)"` nếu có capo);
  - đặt `keySignature` của mọi `MeasureHeader` theo giọng thật. Giá trị tính từ tonic dưới dạng `(fifths, minor)` (ví dụ La thứ = `(0, 1)`, Fa trưởng = `(-1, 0)`), rồi tra enum theo **giá trị**, không theo tên thành viên, vì tên enum dễ nhầm (`GMajorFlat` là Gb trưởng).

  Có test đọc lại cả hai trường.
- **C18. Bảng chữ (R8).** `export_chords_txt.write(chart, title, path)`:
  - Mỗi ô nhịp là danh sách hợp âm theo thứ tự xuất hiện, gộp các lần lặp liền nhau; N bỏ qua; ô không có hợp âm ghi `-`.
  - Mỗi dòng 4 ô, dạng `| C | G | Am F | F |`.
  - Đầu file có hai dòng `# <title>` và `# giọng: <key_name> · tempo: … BPM · nhịp: N/D[ · capo N]`.
  - Cùng nội dung được in ra stderr sau dòng tổng kết.

**Đo (R10)**
- **C19. Bộ đo.** `tests/eval/test_eval_chords.py` có `pytestmark = eval`.
  - **File đáp án** đặt tên `<bài>.hopam.txt`, khác hậu tố `.chords.txt` của tool, để tool không ghi đè đáp án. Dữ liệu là các cặp `<bài>.mp3` + `<bài>.hopam.txt` trong `tests/fixtures/real/`.
  - Eval luôn ghi đầu ra vào thư mục tạm (`tmp_path`), không ghi vào `tests/fixtures/real/`.
- **C20. Đọc đáp án** (`tests/eval/answers.py`):
  - dòng bắt đầu bằng `#` và dấu `|` bị bỏ qua;
  - token khớp `^([A-G][#b]?)(.*)$`; phần đuôi bắt đầu bằng `m` mà không phải `maj` là hợp âm thứ;
  - phần đuôi `7`, `maj7`, `m7`, `sus2`, `sus4`, `add9`, `6`, `9` và `/bass` bị bỏ;
  - `dim` tính là thứ, `aug` tính là trưởng;
  - token không khớp (`x2`, `Intro:`, `N.C.`, lời bài hát) bị bỏ qua và đếm. Nếu bị bỏ hơn 20% số token thì test báo lỗi đọc file.
  - Dòng `# key: Am` (tuỳ chọn) khai giọng đúng.
- **C21. Phép đo.**
  - Gộp các lần lặp liền nhau của cả đáp án lẫn kết quả, bỏ N.
  - `acc = max(0, 1 − levenshtein(ref, est) / len(ref))`. Hai hợp âm bằng nhau khi cùng pitch class và cùng trưởng/thứ. Levenshtein viết tay trong `answers.py`, không thêm thư viện.
  - `acc_transposed` = giá trị lớn nhất của `acc` khi dịch đáp án qua 12 bán cung.
  - **Mỗi bài:** in `acc`, `acc_transposed` và giọng; assert `acc ≥ 0.70`.
  - **Cả bộ:** một test riêng tính tỉ lệ bài đoán đúng giọng, trong số các bài có dòng `# key:`, và assert ≥ 0.80 (G2).

## Non-Functional

- **Hiệu năng (G4):** bài 3 phút ≤ 60 s trên CPU laptop. HPSS và một lần CQT tốn thời gian nhất. Ước tính 10–20 s là **giả định, sẽ đo** trong eval.
- **Bảo mật:** dùng lại `audio.load`: chặn decode quá 605 s, chỉ nhận MP3, giới hạn kích thước. Không có đầu vào mới nào đi vào shell hay đường dẫn ngoài `out_dir/<stem>.chords.*`. Tên hợp âm do tool sinh ra, không lấy từ đầu vào.
- **Kiểu:** `mypy --strict`. Các lời gọi librosa nằm trong `chords.py` và `rhythm.py`.
- **Log:** với `-v`, ghi thời gian từng bước, `tuning` ước lượng và các hằng số C8–C10 ở mức DEBUG.

## Testing

| Loại | Nội dung | Behavior |
|------|----------|----------|
| Unit | `chord_shapes`: 24 thế bấm cho đúng 3 pitch class, độ trải ≤ 4, thế mở đúng bảng, `first_fret` của G là 1 | C15 |
| Unit | `chords.name`: thăng/giáng theo giọng; Bb trong C trưởng; capo hạ N nửa cung và đặt tên theo giọng đã hạ; `key_name` tiếng Việt | C13, C13a, C14 |
| Unit | `detect_key`: C–G–Am–F → Đô trưởng; Am–Dm–E–Am → La thứ | C12 |
| Unit | Điểm và Viterbi trên chroma tổng hợp: chuỗi biết trước (có nhiễu) → đúng nhãn; một đơn vị **nhiễu** (lẫn C và G) giữa 8 đơn vị C vẫn ra C. Một đơn vị G sạch thì **được giữ**, vì đó có thể là hợp âm thật dài một phách; R3 chỉ cấm hợp âm ngắn hơn một đơn vị *(làm rõ khi build C-T3)*; đơn vị im lặng hoặc chuẩn 0 → N | C9, C10 |
| Unit | Chroma: tín hiệu tổng hợp lệch +30 cent vẫn ra đúng hợp âm (`estimate_tuning` với 36 bin) | C8 |
| Unit | Gộp theo đơn vị: số cột bằng số đơn vị; biên vượt quá cuối bài được chặn; 6/8 có đơn vị 2 slot | C7, C8 |
| Unit | `bar_start`: đổi ở phách 2 mỗi ô (4/4, 8 ô) → `bar1_slot` ở phách 2; hai hợp âm mỗi ô với điểm sát nhau → giữ B8; có `pickup` → giữ B8a; N ở đầu bị bỏ kèm cảnh báo | C11 |
| Unit | Dựng tab: 4/4, 6/8, 2/2 cho đúng độ dài đơn vị; N → dấu lặng; đơn vị trước `bar1_slot` bị bỏ; `diagrams` chỉ có ở lần đổi | C16, C17 |
| Unit | `export_gp5` với `diagrams` và `key`: đọc lại thấy `chord.name`, `strings`, `show`, `root`, `subtitle`, `keySignature`; không có hai tham số này thì file giống hệt trước | C17, C17a |
| Unit | `export_chords_txt`: định dạng dòng, gộp lặp, `-`, dòng đầu file, capo | C18 |
| Unit | `answers.py`: đọc `Am7`, `G/B`, `Cmaj7`, `Cdim`, `Bbm`, `x2`, `Intro:`, `N.C.`, `# key:`; vượt 20% token lạ thì lỗi; Levenshtein; `acc_transposed` với đáp án dịch giọng | C20, C21 |
| Unit | Refactor `rhythm`: toàn bộ test hiện có pass mà không sửa | Data Model |
| Integration | Fixture MP3 tổng hợp **9.6 s**: vòng C–G–Am–F, 4/4, 100 BPM, mỗi hợp âm một ô, có tiếng kick ở mỗi phách để dò phách, có thêm "giọng" sine ở dải cao. Sinh bằng `tests/fixtures/make_fixtures.py`, đáp án lưu ở `.json` như các fixture khác. Chạy với `--tempo 100`. Kết quả: chuỗi C G Am F, ô 1 bắt đầu ở C, `.gp5` đọc lại được | C5–C17a |
| CLI | Mã thoát 2 (`--capo 12`, `--format musicxml`), 3, 4 (C10a), 5 (file đã có; một định dạng ghi lỗi); stdout chỉ có đường dẫn | C1–C4, C10a |
| Thủ công | Owner mở `.chords.gp5` của fixture và một bài thật trong Guitar Pro 8. Kiểm: tên và sơ đồ hợp âm hiện đúng ở chỗ đổi, sơ đồ của G không bị ghi "2fr", giọng hiện ở tiêu đề phụ và ở khoá nhạc | C17, C17a, G3 |
| Eval | `pytest -m eval` với bài thật của owner | C19–C21 |

## Traceability

| Requirement | Behavior |
|-------------|----------|
| R1 | C1, C2 |
| R2 | C7, C8, C9, C10a |
| R3 | C10 |
| R4 | C12, C13, C13a, C17a, C18 |
| R5 | C15, C16, C17 |
| R6 | C5, C6, C11 |
| R7 | C1–C4 |
| R8 | C18 |
| R9 | C14 |
| R10 | C19, C20, C21 |

## Rollout

- `convert` không đổi hành vi. Phần refactor `OnsetLike` là commit riêng, chạy toàn bộ test hiện có trước khi thêm tính năng.
- `export_gp5.write` có hai tham số mới với mặc định `None`, nên tương thích ngược.
- PRD R10 đổi tên file đáp án từ `<bài>.chords.txt` thành `<bài>.hopam.txt` (C19), ghi trong changelog của PRD.
- Rollback: bỏ subcommand `chords` và các module mới. Không có dữ liệu hay migration nào phải hoàn tác.
- README, trang Hướng dẫn và Thuật toán thêm phần "Hợp âm" trong cùng đợt.
