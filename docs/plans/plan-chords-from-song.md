# Plan: Vòng hợp âm từ bài hát → Guitar Pro

**Status:** In progress (approved by owner via /swarm-execute, 2026-11-14) · **Date:** 2026-11-14 · **Inputs:** [PRD](../prd/PRD-chords-from-song.md), [spec rev 3](../specs/spec-chords-from-song.md), [sequence](../sequence/sequence-chords-from-song.md), [ADR-0001](../adr/0001-transcription-and-export-libraries.md)

## Goal

`uv run lamnhac chords bai.mp3` sinh ra `bai.chords.gp5` (và `bai.chords.txt` khi chọn `--format gp5,txt`) đúng spec C1–C21.

Hoàn thành khi:
- mọi gate xanh;
- test tích hợp trên fixture C–G–Am–F đạt;
- owner mở được file trong Guitar Pro 8 và thấy tên, sơ đồ hợp âm cùng giọng;
- eval chạy trên các bài thật của owner và có báo cáo.

## Facts

- `rhythm.py` khai kiểu `NoteEvent` ở nhiều chỗ: `rhythm.py:14` (import), `_pick_downbeat` `rhythm.py:124`, `_downbeat_from_pickup` `rhythm.py:155-156`, `analyze` `rhythm.py:172-174`.
  - Các hàm nhịp chỉ đọc `onset_s` và `velocity`. `quantize` (`rhythm.py:220`) còn đọc `offset_s` và `pitch`, nên **giữ** kiểu `NoteEvent`.
- `align_beats` (`rhythm.py:77`) và `align_beats_locally` (`rhythm.py:97`) đã nhận `Sequence[float]` onset, không cần đổi.
- `grid_position` (`rhythm.py:33`) ánh xạ thời gian → slot. Chưa có hàm ngược, nên C7 cần thêm `time_of_slot`.
- `pipeline.py:19` `_WRITERS` và `pipeline.py:25` `_prepare_outputs(opts: ConvertOptions)` gắn chặt với `Format` và `ConvertOptions`. C2 cần tổng quát hoá.
- `pipeline.py:16` có `_STEPS = 6`, đánh số tiến độ riêng cho `convert`.
- `cli.py:23` chỉ có subparser `convert`. Các helper `_parse_formats` (`cli.py:52`, gắn `_FORMATS` ở `cli.py:16`), `_parse_time` (`cli.py:60`), `_parse_pickup` (`cli.py:67`) dùng lại được. Dòng tổng kết và mã thoát nằm ở `cli.py:144-157`.
- `models.py:12` `Format = Literal["gp5", "musicxml"]`. `ConvertOptions` ở `models.py:170`, `ConvertResult` ở `models.py:189`.
- `export_gp5.write` ở `export_gp5.py:41`, `_build` ở `export_gp5.py:52`, `_place` ở `export_gp5.py:90` tạo `gp.Beat` cho từng mảnh trường độ. Sơ đồ hợp âm (C17) gắn vào beat đầu của slot ở đây. Prototype 2026-11-14 đã ghi và đọc lại được `gp.Chord` (tên và `strings`).
- `tests/fixtures/make_fixtures.py:24` (`pluck`), `:47` (`render`), `:57` (`write_mp3`), `:61` (`dump`) là các hàm sinh fixture dùng lại được cho fixture hợp âm.
- `sdlc.config.json:3` đặt `maxLoc` 400 dòng mỗi commit. Gate: `ruff check`, `ruff format --check`, `mypy src`, `pytest -m "not eval"`.
- `tests/eval/test_eval_real.py` là mẫu cho eval: `pytestmark = eval`, tìm cặp file trong `tests/fixtures/real/`, `skipif` khi không có dữ liệu.

## Tasks

| ID | Task | Files | Acceptance criteria | Depends on |
|----|------|-------|---------------------|------------|
| C-T1 | **Refactor** kiểu onset của phần nhịp (không đổi hành vi) | `src/lamnhac/models.py` (+ `OnsetLike` Protocol, `Onset`), `src/lamnhac/rhythm.py` | `_pick_downbeat`, `_downbeat_from_pickup`, `analyze` nhận `Sequence[OnsetLike]`. `quantize` giữ `NoteEvent`. **Không sửa một dòng test nào**, mọi gate xanh. Commit riêng (Two Hats) | — |
| C-T2 | Model mới, `rhythm.onsets`, `time_of_slot`, `chord_shapes` | `models.py` (`ChordLabel`, `MusicKey`, `ChordShape`, `ChordDiagram`, `ChordChart`, `ChordsOptions`, `ChordsResult`), `rhythm.py`, `src/lamnhac/chord_shapes.py`, `tests/test_models.py`, `tests/test_rhythm.py`, `tests/test_chord_shapes.py` | Ràng buộc model kiểm khi tạo. `onsets`: tín hiệu click 120 BPM cho onset cách nhau 0.5 s ±20 ms; im lặng cho danh sách rỗng (C5). `time_of_slot(grid_position(t)) ≈ t`, kể cả ngoài các phách. `chord_shapes` (C15): 24 thế bấm đúng 3 pitch class, độ trải ≤ 4, thế mở đúng bảng, `first_fret` của G là 1 | C-T1 |
| C-T3 | `chords.recognize`: chroma, điểm, Viterbi | `src/lamnhac/chords.py`, `tests/test_chords.py` | C7–C10a. Chroma tổng hợp (có nhiễu) của chuỗi biết trước → đúng nhãn. Một đơn vị lạ giữa 8 đơn vị C vẫn ra C. Đơn vị im lặng hoặc chuẩn 0 → N. Mọi đơn vị N thì `ProcessingError`. Tín hiệu hợp âm tổng hợp lệch +30 cent vẫn ra đúng. Số cột bằng số đơn vị, biên vượt cuối bài được chặn, đơn vị 6/8 dài 2 slot | C-T2 |
| C-T4 | Giọng, tên hợp âm, capo | `chords.py`, `tests/test_chords.py` | C12–C14. C–G–Am–F → Đô trưởng; Am–Dm–E–Am → La thứ. Bb trong C trưởng, F# trong G trưởng, Bb trong F trưởng. `key_name` ra đúng chữ Việt. Capo 3 làm C hiện thành A và đặt tên theo giọng đã hạ | C-T2 |
| C-T5 | Ô nhịp theo hợp âm và dựng tab | `chords.py` (`bar_start`, `build_tab`, đếm lần đổi), `tests/test_chords.py` | C11, C16. Hợp âm đổi ở phách 2 mỗi ô (8 ô, 4/4) → `bar1_slot` ở phách 2. Điểm sát nhau (dưới 20%) hoặc ít hơn 4 lần đổi → giữ B8. Có pickup → giữ B8a. N ở đầu bị bỏ kèm cảnh báo. Đơn vị trước `bar1_slot` bị bỏ. Độ dài lần gảy đúng cho 4/4, 6/8, 2/2. N → dấu lặng. `diagrams` chỉ có ở lần đổi. Capo cộng N vào phím | C-T3, C-T4 |
| C-T6 | Xuất `.gp5` (sơ đồ, giọng) và `.txt` | `src/lamnhac/export_gp5.py`, `src/lamnhac/export_chords_txt.py`, `tests/test_export_gp5.py`, `tests/test_export_chords_txt.py` | C17, C17a, C18. Đọc lại bằng PyGuitarPro thấy `chord.name`, `strings`, `show`, `root`, `subtitle`, `keySignature` (tra theo giá trị `(fifths, minor)`). Không có `diagrams`/`key` thì file giống hệt trước, tức các test `convert` hiện có không đổi. `.txt`: định dạng dòng, gộp lặp, `-`, dòng đầu file, capo | C-T2 |
| C-T7 | `pipeline.chords` và subcommand CLI | `src/lamnhac/pipeline.py`, `src/lamnhac/cli.py`, `tests/test_pipeline.py`, `tests/test_cli.py` | C1–C4. `_prepare_outputs` tổng quát, `convert` không đổi hành vi. `chords` không import `transcribe`, có test kiểm `basic_pitch` chưa nạp. Mã thoát 2 (`--capo 12`, `--format musicxml`), 3, 4, 5 (file đã có; một định dạng ghi lỗi). stdout chỉ có đường dẫn. Dòng tổng kết có số lần đổi, giọng và cảnh báo | C-T5, C-T6 |
| C-T8 | Fixture hợp âm tổng hợp và test tích hợp | `tests/fixtures/make_fixtures.py`, `tests/fixtures/chords_cgamf.{mp3,json}`, `tests/test_pipeline.py` | Fixture 9.6 s: C–G–Am–F, 4/4, 100 BPM, có kick mỗi phách và "giọng" sine ở dải cao, file < 200 KB, seed cố định. `lamnhac chords --tempo 100` ra chuỗi C G Am F, ô 1 bắt đầu ở C, giọng Đô trưởng, `.gp5` đọc lại được | C-T7 |
| C-T9 | Đọc đáp án và phép đo | `tests/eval/answers.py`, `tests/test_answers.py` | C20, C21. Unit test chạy trong gate thường: đọc `Am7`, `G/B`, `Cmaj7`, `Cdim`, `Bbm`, `x2`, `Intro:`, `N.C.`, `# key:`; vượt 20% token lạ thì lỗi; Levenshtein; `acc` và `acc_transposed` với đáp án dịch giọng | — |
| C-T10 | Eval hợp âm | `tests/eval/test_eval_chords.py` | C19. Có `pytestmark = eval`, ghi vào `tmp_path`, đọc cặp `.mp3` + `.hopam.txt`, `skipif` khi không có dữ liệu. In `acc`, `acc_transposed`, giọng và thời gian. Assert từng bài ≥ 0.70 và tỉ lệ giọng đúng của cả bộ ≥ 0.80 | C-T7, C-T9 |
| C-T11 | Tài liệu | `README.md`, `docs/guide.md`, `docs/algorithms.md` | Có phần "Hợp âm": lệnh, tuỳ chọn, ví dụ, cách đặt file `.hopam.txt`, giới hạn; thuật toán chroma, Viterbi, giọng, ô nhịp. `mkdocs build --strict` xanh | C-T7 |
| C-T12 | Đo trên bài thật, chỉnh hằng số, báo cáo | `src/lamnhac/chords.py` (hằng số), `docs/reports/eval-<date>-chords.md` | Owner cung cấp 3–5 cặp `.mp3` + `.hopam.txt`. Báo cáo ghi `acc`, `acc_transposed`, giọng, thời gian bài 3 phút (G4) **trước và sau** khi chỉnh `BASS_WEIGHT`, `N_SCORE`, `TEMPERATURE`, `P_STAY`. Đổi hằng số chỉ khi owner đồng ý. Owner kiểm thủ công trong Guitar Pro 8 (spec Testing, dòng Thủ công) | C-T8, C-T10, owner data |

**Thứ tự:**
- C-T1 → C-T2;
- sau C-T2: C-T3, C-T4, C-T6 chạy song song được (khác file, riêng C-T3 và C-T4 cùng sửa `chords.py`, nên chạy tuần tự);
- C-T5 → C-T7 → C-T8 → C-T11;
- C-T9 làm bất cứ lúc nào;
- C-T10 sau C-T7 và C-T9;
- C-T12 cuối cùng.

Mỗi task là một commit, dưới 400 dòng.

## Risks

| Rủi ro | Cách phát hiện |
|--------|----------------|
| Refactor C-T1 vô tình đổi hành vi `convert` | C-T1 không được sửa test nào. Chạy lại `pytest -m eval` cho 3 bài `convert` sau C-T1, F1 và vị trí ô nhịp phải giữ nguyên |
| Giọng hát lấn át nhạc đệm, F1 hợp âm thấp | Đo ở C-T12. Nếu dưới 0.70 sau khi chỉnh hằng số thì dừng, báo owner, và cân nhắc tách nguồn với ADR mới |
| Beat tracking kém trên bài có trống mạnh hoặc rubato | Test tích hợp C-T8 có kick. Eval C-T12 ghi tempo đoán được so với tempo thật |
| Guitar Pro 8 ẩn sơ đồ hoặc hiện sai tên dù PyGuitarPro đọc lại đúng | Bước kiểm thủ công của owner sau C-T8 trên file fixture |
| Thời gian HPSS + CQT vượt 60 s cho bài 3 phút | Eval C-T10 in thời gian. Nếu vượt thì đo riêng từng bước trước khi tối ưu (Two Hats) |
| Đổi `export_gp5` làm `.gp5` của `convert` khác đi | C-T6: test "không có `diagrams`/`key` thì file giống hệt trước", và các test `export_gp5` hiện có không sửa |

## Verification

- **Gates sau mỗi task:** `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`, `uv run pytest -m "not eval"`.
- **Eval:**
  - `uv run pytest -m eval -s` sau C-T10 và C-T12;
  - chạy lại eval của `convert` sau C-T1 và C-T6 để chắc không đổi kết quả.
- **Owner kiểm thủ công:**
  - sau C-T8: mở `chords_cgamf.chords.gp5` trong Guitar Pro 8, xem tên và sơ đồ hợp âm, sơ đồ G không ghi "2fr", giọng ở tiêu đề phụ và khoá nhạc;
  - sau C-T12: thử một bài thật kèm `--capo`.
