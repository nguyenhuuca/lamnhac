# Sequence Diagrams: MP3 → Guitar Pro

- **PRD:** [PRD-mp3-to-guitarpro](../prd/PRD-mp3-to-guitarpro.md)
- **ADR:** [0001-transcription-and-export-libraries](../adr/0001-transcription-and-export-libraries.md)
- **Spec:** [spec-mp3-to-guitarpro](../specs/spec-mp3-to-guitarpro.md)
- **Status:** Draft

## 1. Convert thành công

Người dùng chạy `lamnhac convert bai.mp3` không truyền `--tempo`. Kết quả là `bai.gp5` và `bai.musicxml`.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant CLI as cli.main
    participant P as pipeline.convert
    participant A as audio.load
    participant T as transcribe.transcribe
    participant BP as basic_pitch (TF)
    participant R as rhythm
    participant TB as tab.assign
    participant G as export_gp5.write
    participant X as export_musicxml.write
    participant FS as File system

    U->>CLI: lamnhac convert bai.mp3
    CLI->>CLI: parse + validate args → ConvertOptions
    CLI->>P: convert(opts, progress)
    P->>FS: check bai.gp5 / bai.musicxml do not exist (B13)
    P->>A: load(bai.mp3)  [1/6]
    A->>FS: stat + soundfile.info (size ≤ 50 MB, ≤ 600 s)
    A-->>P: AudioClip (22050 Hz mono)
    P->>T: transcribe(clip)  [2/6]
    T->>BP: predict(path, thresholds B3)
    BP-->>T: note_events
    T-->>P: list[NoteEvent]
    P->>R: analyze(clip, tempo=None, 4/4)  [3/6]
    R-->>P: RhythmInfo(tempo, anchor, source=detected)
    P->>R: quantize(notes, rhythm)  [4/6]
    R-->>P: Score(slots)
    P->>TB: assign(score, tuning)  [5/6]
    TB-->>P: TabScore, warnings
    P->>G: write(tab, bai.gp5.tmp)  [6/6]
    G->>FS: write + os.replace → bai.gp5
    P->>X: write(tab, bai.musicxml.tmp)
    X->>FS: write + os.replace → bai.musicxml
    P-->>CLI: ConvertResult(outputs, warnings, rhythm)
    CLI-->>U: stdout: 2 paths · stderr: summary · exit 0
```

## 2. Đầu vào không hợp lệ

File không tồn tại, sai đuôi, lớn hơn 50 MB, dài hơn 10 phút, hoặc hỏng (B1, B2).

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant CLI as cli.main
    participant P as pipeline.convert
    participant A as audio.load

    U->>CLI: lamnhac convert dai.mp3
    CLI->>P: convert(opts, progress)
    P->>A: load(dai.mp3)
    A-->>P: raise InputError("file dài 742 s, tối đa 600 s")
    P-->>CLI: InputError
    CLI-->>U: stderr: "lỗi: file dài 742 s, tối đa 600 s" · exit 3
```

## 3. Không nhận được nốt nào

Ví dụ file chỉ có tiếng ồn hoặc im lặng (B4).

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant CLI as cli.main
    participant P as pipeline.convert
    participant T as transcribe.transcribe
    participant BP as basic_pitch (TF)

    U->>CLI: lamnhac convert im_lang.mp3
    CLI->>P: convert(opts, progress)
    P->>T: transcribe(clip)
    T->>BP: predict(...)
    BP-->>T: [] (no notes)
    T-->>P: raise ProcessingError("không nhận được nốt nào")
    P-->>CLI: ProcessingError
    CLI-->>U: stderr: error message · exit 4
```

## 4. Đầu ra đã tồn tại, hoặc một định dạng ghi lỗi

Có hai nhánh. Nhánh a: file đã có và không truyền `--force`, nên dừng trước khi xử lý (B13). Nhánh b: có `--force`, nhưng `.gp5` ghi lỗi trong khi MusicXML vẫn ghi được (B16).

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant CLI as cli.main
    participant P as pipeline.convert
    participant G as export_gp5.write
    participant X as export_musicxml.write
    participant FS as File system

    alt a. bai.gp5 already exists, no --force
        U->>CLI: lamnhac convert bai.mp3
        CLI->>P: convert(opts)
        P->>FS: exists(bai.gp5) → true
        P-->>CLI: raise OutputError("bai.gp5 đã tồn tại, dùng --force")
        CLI-->>U: stderr: error · exit 5 (no processing done)
    else b. --force, writing .gp5 fails
        U->>CLI: lamnhac convert bai.mp3 --force
        CLI->>P: convert(opts)
        Note over P: steps 1–5 as in §1
        P->>G: write(tab, bai.gp5.tmp)
        G->>FS: write → PermissionError
        G-->>P: raise OutputError (tmp removed)
        P->>X: write(tab, bai.musicxml.tmp)
        X->>FS: write + os.replace → bai.musicxml
        P-->>CLI: ConvertResult(outputs=[bai.musicxml], errors=[gp5])
        CLI-->>U: stdout: bai.musicxml · stderr: gp5 error · exit 5
    end
```
