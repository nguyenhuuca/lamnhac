# PRD: Vòng hợp âm từ bài hát → Guitar Pro (lamnhac chords)

**Status:** Approved · **Owner:** project owner · **Date:** 2026-11-14 · **PR-FAQ:** n/a (Medium size)

## Problem

Người chơi guitar muốn đệm hát một bài có sẵn: bản MP3 đầy đủ có giọng hát và nhạc đệm. Hiện nay họ có hai cách:
- tìm hợp âm trên các trang hợp âm, nhưng hợp âm ở đó thường sai, bị đơn giản hoá hoặc khác tông với bản thu;
- tự dò bằng tai, rất mất thời gian với người chưa giỏi nghe.

Tool `lamnhac convert` hiện có chỉ chép **từng nốt** của **một cây guitar solo**. Với bài có ban nhạc nó cho kết quả kém, và PRD trước để "chord chart" ngoài phạm vi.

Bằng chứng: nhu cầu của owner, nêu ngày 2026-11-14 sau khi dùng `convert`. Phần nhận nhịp hiện có đã được đo trên 3 bài: 93–99% nốt đúng vị trí trong ô nhịp (`docs/reports/eval-2026-11-14-g1.md`). Tính năng mới dùng lại được phần này.

## Goals and Non-Goals

| Goal | Measure | Target |
|------|---------|--------|
| G1. Vòng hợp âm đúng | Độ khớp chuỗi hợp âm (xem định nghĩa dưới) trên bộ test của owner | ≥ 0.70 *(assumption)* |
| G2. Đúng giọng (key) | Tỉ lệ bài đoán đúng giọng, tính cả trưởng và thứ | ≥ 80% bộ test *(assumption)* |
| G3. Guitar Pro mở được file | Tỉ lệ `.gp5` mở được trong Guitar Pro 8 | 100% |
| G4. Nhanh | Thời gian xử lý bài 3 phút trên CPU laptop | ≤ 60 s *(assumption)* |

**Độ khớp chuỗi hợp âm (G1):**
- Chuỗi hợp âm của bài là danh sách hợp âm theo thứ tự xuất hiện, gộp các lần lặp liền nhau. Ví dụ: C C G G Am F → C G Am F.
- Độ khớp = 1 − khoảng cách Levenshtein ÷ độ dài chuỗi đáp án.
- Đáp án là hợp âm owner chép trên lời bài hát. Đáp án này không có thời gian chính xác, nên không đo theo từng giây.
- Hợp âm 7, sus… trong đáp án được rút về trưởng hoặc thứ (G7 → G, Am7 → Am).
- Báo cáo thêm độ khớp **sau khi dịch giọng** tốt nhất: hợp âm trên lời thường ghi ở tông khác bản thu, hoặc người đàn dùng capo. Hai con số được ghi riêng.

**Not in scope (bản đầu):**
- Track giai điệu (nốt của giọng hát) và tách giọng hát. Để giai đoạn sau.
- Hợp âm ngoài trưởng và thứ: 7, maj7, sus, dim, aug, hợp âm đảo (slash chord). Tool vẫn nhận các hợp âm này, nhưng ghi thành trưởng hoặc thứ gần nhất.
- Các kiểu đệm như quạt chả, rải, boston. Bản đầu chỉ gảy một lần mỗi phách.
- Lời bài hát trong file `.gp5`.
- Chép nốt từng cây đàn trong bài đầy đủ. Đó là việc của `convert` kết hợp tách nguồn, một hướng khác.
- Bài đổi giọng giữa chừng: hợp âm vẫn được nhận, nhưng tool chỉ báo một giọng cho cả bài.

## Users and Stories

- Là người đệm hát, tôi muốn đưa MP3 một bài hát vào và nhận file `.gp5` có tên hợp âm theo từng ô nhịp, để mở trong Guitar Pro và tập đệm theo bản thu.
- Là người đệm hát, tôi muốn biết bài ở giọng gì để chọn capo hoặc dịch giọng cho hợp với giọng mình.
- Là người dùng `convert`, tôi muốn dùng lại các tuỳ chọn đã quen (`--tempo`, `--time`, `--pickup`, `-o`, `--force`) khi nhịp hoặc ô nhịp bị đoán sai.

## Requirements

| ID | Requirement | Priority | Acceptance |
|----|-------------|----------|------------|
| R1 | Lệnh mới `lamnhac chords <file.mp3>` tạo `<tên>.chords.gp5` cạnh file vào (hoặc trong `-o`), để không ghi đè `.gp5` của `convert` | must | Given `bai.mp3` hợp lệ, when chạy `lamnhac chords bai.mp3`, then có `bai.chords.gp5` và mã thoát 0 |
| R2 | Nhận hợp âm trong 24 hợp âm trưởng và thứ, cộng "không có hợp âm" (N) cho đoạn im lặng hoặc chỉ có trống | must | Given bộ test của owner, when chạy, then độ khớp chuỗi hợp âm ≥ 0.70 (G1) |
| R3 | Hợp âm đổi theo phách, có làm mượt: mỗi hợp âm kéo dài ít nhất một phách, và không nhảy qua lại liên tục | must | Given một đoạn giữ một hợp âm trong 2 ô nhịp, when chạy, then đoạn đó ra đúng một hợp âm, không chen hợp âm lạ ngắn hơn 1 phách |
| R4 | Đoán giọng của bài (ví dụ "La thứ"), in ra màn hình và ghi vào file. Tên hợp âm viết theo giọng: Bb chứ không phải A# khi bài ở giọng Fa trưởng | must | Given bộ test, when chạy, then giọng đúng ở ≥ 80% số bài (G2) |
| R5 | `.gp5` có một track guitar (tuning chuẩn): mỗi phách một hợp âm gảy đủ dây theo thế bấm thông dụng (thế mở hoặc chặn), kèm tên hợp âm và sơ đồ bấm trên khuông khi hợp âm đổi. Có tempo, số chỉ nhịp và ô nhịp | must | Given kết quả, when mở trong Guitar Pro 8, then thấy tên và sơ đồ hợp âm ở mỗi lần đổi, file mở không lỗi (G3) |
| R6 | Dùng chung phần nhịp của `convert`: `--tempo`, `--time`, `--pickup`, cùng bước dò phách (B5–B8, B7a, B7b) | must | Given `--time 3/4 --pickup 1`, when chạy, then ô nhịp tính như `convert` với cùng tuỳ chọn |
| R7 | Dùng chung các tuỳ chọn và hành vi của `convert`: `-o`, `--force`, `-v`, kiểm tra đầu vào (≤ 50 MB, ≤ 10 phút), ghi file an toàn, mã thoát 0–5, báo tiến độ, chạy offline | must | Given file đầu ra đã có và không có `--force`, when chạy, then thoát mã 5 trước khi xử lý; không có kết nối mạng nào lúc chạy |
| R8 | In ra chuỗi hợp âm dạng chữ theo ô nhịp, ví dụ `| C | G | Am | F |`, ra stderr, và ghi `--format txt` thành `<tên>.chords.txt` | should | Given `--format gp5,txt`, when chạy, then có thêm file `.txt` mỗi dòng 4 ô nhịp |
| R9 | `--capo N` (0–11): giữ âm thanh, nhưng tên và thế bấm hợp âm tính cho người kẹp capo ở ngăn N | could | Given bài ở giọng Đô trưởng và `--capo 3`, when chạy, then hợp âm C hiện là A (thế bấm A, kẹp ngăn 3) |
| R10 | Bộ đo `pytest -m eval` cho hợp âm: đọc các cặp `<bài>.mp3` + `<bài>.chords.txt` (hợp âm owner chép) trong `tests/fixtures/real/`, in độ khớp thường và độ khớp sau khi dịch giọng | must | Given 3 bài có đáp án, when chạy eval, then in 2 con số cho mỗi bài và test fail nếu độ khớp thường dưới 0.70 |

## Constraints and Risks

| Rủi ro | Giảm thiểu |
|--------|------------|
| Giọng hát lấn át nhạc đệm, làm sai hợp âm | Dùng phổ chroma chỉ lấy phần hoà âm (harmonic) và nhấn dải trầm, nơi bass và hợp âm nằm. Nếu đo không đạt G1 thì cân nhắc tách nguồn, kèm ADR |
| Bản thu không lên dây chuẩn A440 | Ước lượng độ lệch tuning trước khi tính chroma |
| Đáp án trên lời bị đơn giản hoá, sai, hoặc khác tông | Báo thêm độ khớp sau khi dịch giọng. Owner nghe lại các bài lệch nhiều |
| Nhạc Việt (bolero) dùng nhiều hợp âm 7 | Ghi thành trưởng hoặc thứ gần nhất, đã ghi trong Not in scope. Đo trước rồi mới mở rộng |
| Thêm thư viện hoặc model mới | Ưu tiên librosa và numpy đã có. Bất kỳ model mới nào cũng cần ADR và phải chạy offline (`tech-strategy.md`) |
| Bộ test nhỏ (3–5 bài) nên số đo chưa vững | Ghi rõ trong báo cáo eval, thêm bài khi có |

**Ràng buộc:** Windows, Python 3.11, chạy offline, mọi dependency qua `uv` (`tech-strategy.md`). Code chung với `convert` (đọc audio, nhịp, ghi file, CLI) phải được dùng lại, không chép sang module mới.

## Open Questions

- Owner chuẩn bị 3–5 bài cho bộ test: MP3 cùng file `<bài>.chords.txt` chép hợp âm theo thứ tự. **Đã chốt 2026-11-14:** mỗi dòng một đoạn, hợp âm cách nhau bằng dấu cách, không cần đánh dấu ô nhịp. (owner)
- ~~Gộp vào `convert` hay để lệnh riêng?~~ **Đã chốt 2026-11-14:** lệnh riêng `lamnhac chords` (R1).
- Mục tiêu G1 0.70 và G4 60 s là giả định, owner đồng ý dùng tạm (2026-11-14). Chỉnh lại sau lần đo đầu. (owner + dev)
- Cách nhận hợp âm: mẫu chroma kèm làm mượt bằng HMM/Viterbi dùng librosa, hay một model học sâu? Quyết định ở bước spec, kèm ADR nếu thêm thư viện. (dev)

## Changelog

- 2026-11-14: Owner duyệt PRD; các câu hỏi mở về định dạng đáp án, lệnh riêng và mục tiêu tạm đã chốt theo đề xuất.
- 2026-11-14: Draft từ `/scope`. Owner chọn: chỉ trưởng và thứ; mỗi phách gảy một lần, có tên và sơ đồ hợp âm; chưa làm giai điệu; đo bằng bài thật cộng hợp âm trên lời.
