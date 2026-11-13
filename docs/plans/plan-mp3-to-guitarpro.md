# Plan: MP3 → Guitar Pro CLI

**Status:** In progress · **Date:** 2026-11-13 · **Inputs:** [PRD](../prd/PRD-mp3-to-guitarpro.md), [spec rev 2](../specs/spec-mp3-to-guitarpro.md), [sequence](../sequence/sequence-mp3-to-guitarpro.md), [ADR-0001](../adr/0001-transcription-and-export-libraries.md)

## Goal

`uv run lamnhac convert bai.mp3` sinh ra `bai.gp5` và `bai.musicxml` đúng spec B1–B21. Hoàn thành khi tất cả gate đều xanh, eval G1 và G3 đã đo xong và có báo cáo, và owner mở được file mẫu trong Guitar Pro (G2).

## Facts

- Repo chưa có mã nguồn. Commit `49622f4` chỉ chứa scaffolding của agentic-sdlc và các tài liệu (PRD, ADR-0001, spec, sequence).
- `sdlc.config.json:4` có `"components": []`, tức chưa khai báo gate nào. T1 sẽ thêm.
- `sdlc.config.json:3` đặt `maxLoc` là 400, tức giới hạn khoảng 400 dòng thay đổi mỗi commit. Mỗi task bên dưới được chia để nằm trong giới hạn này.
- `.claude/rules/tech-strategy.md` quy định stack: Python 3.11, uv, basic-pitch, librosa, PyGuitarPro, music21, pytest, Ruff, mypy strict. Không cho gọi mạng lúc chạy, không cho `pip install`.
- Chưa có `TASKS.md` và `docs/tracking.md`. Plan này tạo cả hai.

## Tasks

| ID | Task | Files | Acceptance criteria | Depends on |
|----|------|-------|---------------------|------------|
| T1 | Dựng khung dự án, các model và cây ngoại lệ | `pyproject.toml`, `.python-version`, `uv.lock`, `src/lamnhac/{__init__,models,errors}.py`, `tests/test_models.py`, `sdlc.config.json`, `.gitattributes` | `uv sync` chạy được trên Python 3.11. Có entry point `lamnhac`. Kiểm tra ràng buộc của model khi tạo (ví dụ `TimeSignature(6,8).bar_slots == 12`, `Tuning` phải đủ 6 dây). Các gate `ruff check`, `ruff format --check`, `mypy --strict src` và `pytest` đều xanh. Gate được khai trong `sdlc.config.json`. Có override `ignore_missing_imports` cho các thư viện không có type | — |
| T2 | **Spike cài đặt** (ADR-0001, spec mục Rollout 1) | `pyproject.toml`, `uv.lock`, `scratchpad/spike/*` (không commit), `docs/reports/spike-2026-11-13-install.md`, ADR-0001 | Báo cáo trả lời có hoặc không, kèm output thật, cho 6 câu: (1) `uv add basic-pitch` resolve được trên Windows với 3.11; (2) `predict` chạy được trên một file mẫu; (3) `soundfile` đọc được MP3 mà không cần ffmpeg (ghi phiên bản libsndfile); (4) PyGuitarPro ghi được `.gp5` và đọc lại được; (5) music21 có tự sinh `<staff-tuning>` và TAB clef không; (6) kết quả `pip-audit`. Nếu (1) hoặc (2) thất bại thì dừng và hỏi owner (phương án onnxruntime cần ADR mới) | T1 |
| T3 | `audio.load` và fixture âm thanh | `src/lamnhac/audio.py`, `tests/fixtures/make_fixtures.py`, `tests/fixtures/*.mp3`, `tests/fixtures/*.json` (nốt chuẩn), `tests/test_audio.py` | Đúng B1 và B2. Test bao: không tồn tại, sai đuôi, > 50 MB (file sparse), header > 600 s, file hỏng, decode thực vượt 605 s thì dừng (bằng cách stub `soundfile.blocks`), stereo được trộn mono, ra đúng 22050 Hz. Fixture là bản gảy tổng hợp Karplus–Strong khoảng 5 s, sinh bằng script có seed cố định, mỗi file < 200 KB | T2 |
| T4 | `durations.split` | `src/lamnhac/durations.py`, `tests/test_durations.py` | Đúng B16. Kiểm hết mọi `(start, length)` với `length` 1–48 trong 4/4, 3/4 và 6/8: tổng các mảnh bằng `length`, không mảnh nào vắt qua vạch nhịp, mỗi mảnh bắt đầu tại bội số của trường độ gốc của nó, cờ tie đúng | T1 |
| T5 | `transcribe` | `src/lamnhac/transcribe.py`, `tests/test_transcribe.py` | Đúng B3 và B4. Dải tần tính từ tuning (với Drop D, min ≤ 73,4 Hz). Có test dùng stub `predict` cho việc đổi kiểu dữ liệu và lỗi không có nốt. Một test tích hợp chạy model thật trên fixture của T3 nhận được ≥ 80% số nốt chuẩn, so bằng onset ±50 ms và cao độ | T2, T3 |
| T6 | `rhythm.analyze` và `rhythm.quantize` | `src/lamnhac/rhythm.py`, `tests/test_rhythm.py` | Đúng B5–B10. Test bao: hàm `p(t)` với phách đều và phách trôi ±3% (nốt vẫn đúng ô), ngoại suy ngoài khoảng phách, chọn phách mạnh, ô pickup, gộp hợp âm, cắt nốt ngân, bù dấu lặng, chạy với 4/4, 3/4 và 6/8, `--tempo` ghi đè tempo. Với fixture 97 BPM, tempo đoán sai ≤ 5% (R4) | T3 |
| T7 | `tab.assign` | `src/lamnhac/tab.py`, `tests/test_tab.py` | Đúng B11–B13. Test bao: thang âm C (thế tay ổn định), hợp âm mở (tâm `None`), nốt ngoài tầm (có cảnh báo), > 6 nốt, cặp 40+41 (bỏ một nốt và cảnh báo), Drop D, cùng input luôn ra cùng output. Property test (hypothesis) 500 ca: mọi `TabNote` thoả `tuning + fret == pitch`, phím 0–24, mỗi dây tối đa một nốt mỗi slot (G4). Bài 3 phút giả lập (~2000 slot) chạy < 10 s | T1 |
| T8 | `export_musicxml` | `src/lamnhac/export_musicxml.py`, `tests/test_export_musicxml.py` | Đúng B15 và B18. Ghi rồi đọc lại bằng music21: cao độ, dây, phím, tie và tổng trường độ từng ô đều đúng. XML có `staff-lines=6` và `staff-tuning` đúng với Drop D (nếu cần thì chèn bằng ElementTree, theo kết quả T2). Không còn file `.tmp-*`. Lỗi ghi file được bọc thành `OutputError` | T2, T4 |
| T9 | `pipeline` và `cli` (chỉ xuất MusicXML) | `src/lamnhac/{pipeline,cli}.py`, `tests/test_pipeline.py`, `tests/test_cli.py` | Đúng B14, B19, B20, B21 và bảng CLI. E2E qua `subprocess` cho các mã thoát 0, 2, 3, 4, 5. stdout chỉ chứa đường dẫn file, stderr có các dòng `[k/6]`. Kiểm `--tuning` (đảo thứ tự, B11), `--time`, `--tempo`, `--force`. Một test chạy toàn pipeline với `socket.socket.connect` bị chặn (R9). Lỗi không lường trước chỉ in một dòng, trừ khi bật `-v` | T5, T6, T7, T8 |
| T10 | `export_gp5` và nối vào pipeline | `src/lamnhac/export_gp5.py`, `tests/test_export_gp5.py`, `src/lamnhac/pipeline.py` | Đúng B15, B17 và B19. Ghi rồi đọc lại bằng `guitarpro.parse`: version 5.1, tempo, tuning, dây/phím, `NoteType.tie`, tổng trường độ từng ô đều đúng. Tiêu đề tiếng Việt được gập về ASCII. Test B19: khi `.gp5` lỗi thì MusicXML vẫn được ghi và lệnh thoát với mã 5 | T9 |
| T11 | Eval G1 và G3, viết báo cáo | `tests/eval/test_eval_guitarset.py`, `scripts/fetch_guitarset.md` (hướng dẫn tải thủ công, không tải tự động), `docs/reports/eval-<date>-g1.md` | Chạy `pytest -m eval` trên các bản solo của GuitarSet. Báo cáo ghi Note F1 (`offset_ratio=None`, onset ±50 ms) so với mục tiêu 0.70, và thời gian chạy bài 3 phút so với mục tiêu 180 s. Nếu F1 < 0.70 thì đề xuất chỉnh ngưỡng B3, không tự chỉnh khi chưa hỏi owner | T10 |
| T12 | Lọc hoạ âm (B4a, R13) và `--max-fret` (B12, R14) | `src/lamnhac/{transcribe,tab,pipeline,cli,models}.py`, `tests/test_{transcribe,tab,pipeline,cli}.py`, `tests/fixtures/make_fixtures.py`, `tests/fixtures/power_chord.{mp3,json}` | Hàm lọc thuần, có unit test cho từng khoảng hoạ âm, ngưỡng 0.8, cửa sổ 80 ms, không chồng nhau thì giữ. Fixture power chord E2+B2+E3 (âm lượng ngang nhau): E3 **được giữ** khi chạy model thật. Riff mẫu: precision ≥ 0.9 và recall = 1.0. `--max-fret 5` → mọi phím ≤ 5, nốt ngoài vùng bị bỏ kèm cảnh báo. `--keep-harmonics` tắt lọc. Gate xanh. Chạy lại testgod.mp3 và báo số nốt, phím lớn nhất | T10 |

**Thứ tự chạy:** T1 → T2 → (T3, T4, T7 song song được) → (T5, T6 sau T3; T8 sau T4) → T9 → T10 → T11. Mỗi task là một commit riêng.

## Risks

| Rủi ro | Cách phát hiện |
|--------|----------------|
| basic-pitch hoặc TensorFlow 2.15 không cài được trên Windows với 3.11 | T2, câu (1)–(2). Nếu thất bại thì dừng và hỏi owner |
| libsndfile đi kèm `soundfile` không đọc được MP3 | T2, câu (3). Phương án dự phòng (ffmpeg hoặc thư viện decode khác) cần owner duyệt vì đi ngược quyết định trong B2 |
| TensorFlow cũ có advisory nghiêm trọng liên quan | T2, câu (6). Nếu có advisory liên quan đến đường dùng của tool thì quyết định lại ADR-0001 |
| Fixture tổng hợp quá "sạch", test qua nhưng bản thu thật thì tệ | T11 đo trên GuitarSet là dữ liệu thật. Owner thử thêm vài bản thu của mình |
| Basic-pitch nhận nốt kém trên fixture tổng hợp, làm T5 không ổn định | Ngưỡng ≥ 80% và seed cố định. Nếu vẫn không ổn định thì đổi fixture sang một đoạn GuitarSet ngắn (giấy phép CC BY 4.0, có ghi nguồn) |
| Chọn sai phách mạnh làm lệch ô nhịp | Test T6 với dữ liệu có nhấn ở phách 1. Giới hạn đã biết, người dùng sửa trong Guitar Pro |
| Beam search chậm với hợp âm 6 nốt | Benchmark trong T7 (< 10 s cho ~2000 slot) |
| Guitar Pro mở file lỗi dù test đọc lại bằng thư viện đều qua | Owner kiểm thủ công sau T8 và T10 |
| Repo phình vì fixture | Mỗi fixture < 200 KB. Dữ liệu GuitarSet để ngoài repo |

## Verification

- **Gates sau mỗi task:** `uv run ruff check`, `uv run ruff format --check`, `uv run mypy --strict src`, `uv run pytest -m "not eval"`.
- **Eval (T11):** `uv run pytest -m eval` với GuitarSet tải về thủ công.
- **Owner kiểm thủ công:**
  - sau T8: mở `.musicxml` mẫu trong Guitar Pro;
  - sau T10: mở `.gp5` mẫu;
  - sau T11: thử với 2–3 bản thu thật của chính bạn.
- **Môi trường kiểm thủ công:** Guitar Pro 8 (owner xác nhận 2026-11-13).
