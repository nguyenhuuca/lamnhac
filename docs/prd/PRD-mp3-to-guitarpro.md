# PRD: MP3 → Guitar Pro (lamnhac)

**Status:** Approved · **Owner:** project owner · **Date:** 2026-11-13 · **PR-FAQ:** n/a (Medium size)

## Problem

Người chơi guitar có bản thu MP3 một cây guitar (tự thu, hoặc bản guitar solo) và muốn có tab để tập, sửa hoặc lưu lại trong Guitar Pro. Hiện nay họ phải nghe đi nghe lại để chép tay từng nốt vào Guitar Pro. Việc này mất hàng giờ cho một bài 3–4 phút và dễ sai nhịp.

Bằng chứng: nhu cầu của chính owner (người dùng đầu tiên). Repo chưa có code hay dữ liệu nào trước PRD này.

## Goals and Non-Goals

| Goal | Measure | Target |
|------|---------|--------|
| G1. Có bản nháp tab dùng được | Note F1 (onset ±50 ms + đúng cao độ, `mir_eval`) trên bộ test guitar solo | ≥ 0.70 *(assumption: đo trên GuitarSet hoặc bộ bản thu có tab chuẩn của owner)* |
| G2. Guitar Pro mở được file | Tỉ lệ file `.gp5` và MusicXML mở/import không lỗi trong Guitar Pro | 100% bộ test |
| G3. Tiết kiệm thời gian | Thời gian xử lý bài 3 phút trên CPU laptop | ≤ 3 phút *(assumption)* |
| G4. Tab chơi được | Tỉ lệ nốt có dây/phím hợp lệ (0–24, mỗi dây ≤ 1 nốt cùng lúc) | 100% |

**Not in scope (MVP):**
- Nhạc có cả ban nhạc / tách nguồn (source separation). Để giai đoạn sau.
- Kỹ thuật biểu diễn: bend, slide, hammer-on, pull-off, vibrato, palm mute.
- Web app, GUI, nhiều người dùng, server/cloud.
- Chord chart, lời bài hát, nhận dạng giọng hát.
- Xử lý thời gian thực.
- Độ chính xác "dùng ngay không cần sửa". Người dùng sẽ sửa tiếp trong Guitar Pro.

## Users and Stories

- Là người chơi guitar, tôi muốn đưa một file MP3 guitar solo vào và nhận file `.gp5` để mở thẳng trong Guitar Pro, sửa lại thay vì chép tay từ đầu.
- Là người chơi guitar, tôi muốn có thêm file MusicXML để mở bằng Guitar Pro 7/8 hoặc phần mềm khác (MuseScore).
- Là người chơi guitar, tôi muốn tự chỉnh tempo hoặc tuning khi phần mềm đoán sai, để bản nháp chia ô nhịp đúng hơn.

## Requirements

| ID | Requirement | Priority | Acceptance |
|----|-------------|----------|------------|
| R1 | Đọc file MP3 (mono/stereo, 44.1/48 kHz, dài ≤ 10 phút) | must | Given một MP3 guitar solo hợp lệ, when chạy lệnh convert, then audio được giải mã và chuyển sang bước nhận nốt, không lỗi |
| R2 | Từ chối đầu vào không hợp lệ với thông báo rõ ràng | must | Given file không tồn tại, không phải audio, hỏng, hoặc dài > 10 phút, when chạy, then thoát với mã ≠ 0 và một thông báo lỗi ngắn, không in stack trace |
| R3 | Nhận nốt: cao độ, thời điểm bắt đầu, độ dài, hỗ trợ đa âm (nhiều nốt cùng lúc) | must | Given bộ test guitar solo có ground truth, when transcribe, then Note F1 ≥ 0.70 (G1) |
| R4 | Ước lượng tempo và phách, lượng tử hoá nốt vào ô nhịp (mặc định 4/4) | must | Given bản thu có tempo ổn định, when convert, then tempo đoán sai ≤ 5% so với thực tế, hoặc người dùng ghi đè bằng `--tempo`, và mọi nốt nằm trong ô nhịp đúng tổng trường độ |
| R5 | Gán dây/phím cho từng nốt, ưu tiên thế tay dễ chơi (ít di chuyển tay) | must | Given danh sách nốt, when gán tab, then mọi nốt có phím 0–24, không hai nốt cùng lúc trên một dây, và nốt ngoài tầm cây đàn được bỏ qua kèm cảnh báo |
| R6 | Xuất MusicXML có khuông tab (string/fret) | must | Given kết quả convert, when import file `.musicxml` vào Guitar Pro 8, then hiện đủ nốt với đúng dây/phím như R5 |
| R7 | Xuất file `.gp5` | must | Given kết quả convert, when mở `.gp5` trong Guitar Pro, then mở không lỗi, có 1 track guitar, tempo và tuning đúng |
| R8 | Giao diện dòng lệnh: `lamnhac convert <input.mp3> -o <out_dir> [--tempo N] [--format gp5,musicxml]` | must | Given lệnh với đối số hợp lệ, when chạy, then tạo file trong `out_dir` và in đường dẫn file đã tạo |
| R9 | Chạy offline hoàn toàn, không gọi dịch vụ ngoài | must | Given máy không có mạng (sau khi cài đặt), when convert, then thành công như khi có mạng |
| R10 | Báo tiến độ theo từng bước (decode, transcribe, quantize, tab, export) | should | Given bài 3 phút, when chạy, then mỗi bước in một dòng trạng thái và tổng thời gian ≤ 3 phút (G3) |
| R11 | Hỗ trợ tuning khác chuẩn (Drop D, Eb chuẩn…) qua `--tuning` | could | Given `--tuning "D A D G B E"`, when convert, then tab gán theo tuning đó và file đầu ra ghi đúng tuning |
| R12 | Cho phép đặt time signature (`--time 3/4`) | could | Given `--time 3/4`, when convert, then ô nhịp chia theo 3/4 |
| R13 | Lọc hoạ âm: bỏ nốt giả do hoạ âm của một nốt trầm hơn | should | Given bản thu có dây trầm buông ngân, when convert, then hoạ âm (+12, +19, +24, +28, +31, +36 nửa cung, cùng lúc, nhỏ hơn rõ rệt) không thành nốt riêng, còn quãng tám thật trong power chord vẫn giữ; tắt được bằng `--keep-harmonics` |
| R14 | Giới hạn vùng phím `--max-fret N` | should | Given `--max-fret 5`, when convert, then mọi nốt trong tab có phím ≤ 5, nốt không bấm được trong vùng đó bị bỏ kèm cảnh báo |

## Constraints and Risks

**Constraints:** chạy trên máy cá nhân Windows, miễn phí, offline, không có deadline cứng.

| Risk | Mitigation |
|------|------------|
| Nhận nốt đa âm (hợp âm) kém chính xác | Dùng model pretrained cho transcription *(assumption: Spotify Basic Pitch, Apache-2.0)*, chốt trong ADR. Đo F1 sớm trên bộ test và đặt mục tiêu ở mức bản nháp |
| Tempo/phách đoán sai làm lệch toàn bộ ô nhịp | Cho ghi đè `--tempo` (R4) và in tempo đoán được để người dùng kiểm tra |
| Định dạng `.gp5` là định dạng đóng, được dịch ngược | Dùng thư viện đã được kiểm chứng *(assumption: PyGuitarPro)*. Test mở file thật trong Guitar Pro. Luôn xuất thêm MusicXML làm phương án dự phòng |
| Guitar distortion/hiệu ứng làm nhận nốt sai | Ghi rõ MVP hỗ trợ tốt nhất với guitar clean/acoustic. Đo riêng trên bản distortion |
| Gán dây/phím không tự nhiên | Thuật toán tối ưu thế tay (ví dụ quy hoạch động theo chi phí di chuyển). Người dùng sửa trong Guitar Pro |
| Model/thư viện nặng, cài đặt khó trên Windows | Chọn phụ thuộc có wheel cho Windows, đóng gói và có hướng dẫn cài đặt. Chốt khi đề xuất tech stack |
| Bản quyền bài hát | Công cụ cá nhân, xử lý cục bộ, không phân phối nội dung |

## Open Questions

- ~~Owner dùng Guitar Pro phiên bản nào?~~ Guitar Pro 8 (trả lời 2026-11-13).
- Bản thu chủ yếu là acoustic, electric clean hay electric distortion? (owner)
- Có sẵn vài bản thu kèm tab đúng để làm bộ test cho G1 không, hay dùng dataset công khai (GuitarSet)? (owner)
- Ngoài MP3 có cần nhận WAV/FLAC không? Gần như không tốn thêm công. (owner)
- Tech stack (ngôn ngữ, model transcription, thư viện xuất file) sẽ chốt qua `/welcome` và một ADR sau khi PRD được duyệt. (Claude đề xuất, owner quyết)

## Changelog

- 2026-11-13: R13, R14 thêm sau khi chạy thử bản thu thật (testgod.mp3) thấy dư hoạ âm và người chơi chỉ dùng vài ngăn đầu.
