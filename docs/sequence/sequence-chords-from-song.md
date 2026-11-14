# Sequence Diagrams: Vòng hợp âm từ bài hát

- **PRD:** [PRD-chords-from-song](../prd/PRD-chords-from-song.md)
- **ADR:** — (dùng lại thư viện của [ADR-0001](../adr/0001-transcription-and-export-libraries.md))
- **Spec:** [spec-chords-from-song](../specs/spec-chords-from-song.md)
- **Status:** Draft

## 1. Đường chính: `lamnhac chords bai.mp3 --format gp5,txt`

Người dùng đưa vào một bài hát đầy đủ và nhận về `bai.chords.gp5` và `bai.chords.txt`. Giọng và bảng hợp âm in ra stderr.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant CLI as cli.main
    participant P as pipeline.chords
    participant A as audio.load
    participant R as rhythm
    participant C as chords
    participant S as chord_shapes
    participant G as export_gp5.write
    participant T as export_chords_txt.write

    U->>CLI: lamnhac chords bai.mp3 --format gp5,txt
    CLI->>CLI: parse + validate (C1)
    CLI->>P: chords(ChordsOptions, progress)
    P->>P: _prepare_outputs: mkdir, check existing (C2)
    P->>A: load(path)
    A-->>P: AudioClip (mono 22.05 kHz)
    P->>R: onsets(clip) (C5)
    R-->>P: list[Onset]
    P->>R: analyze(clip, onsets, tempo, time_sig, pickup) (C6)
    R-->>P: RhythmInfo (beats, tempo, downbeat_slot)
    P->>C: recognize(clip, rhythm, unit_slots) (C7–C10)
    C-->>P: labels per strum unit
    P->>C: detect_key(labels) (C12)
    C-->>P: Key
    P->>C: bar_start(labels, rhythm, unit_slots) (C11)
    C-->>P: bar1_slot
    P->>S: shape(root, minor) per chord (C15)
    S-->>P: ChordShape
    P->>P: build TabScore + diagrams (C16, C17)
    P->>G: write(tab, bai.chords.gp5, diagrams, key) (C17a)
    G-->>P: ok (tmp + os.replace)
    P->>T: write(chart, title, bai.chords.txt) (C18)
    T-->>P: ok
    P-->>CLI: ChordsResult
    CLI-->>U: stderr: key, chord chart, summary · stdout: 2 paths · exit 0
```

## 2. Ô nhịp: có `--pickup` và không có `--pickup`

Khi người dùng khai pickup, ô nhịp tính theo B8a. Khi không khai, ô nhịp tính theo chỗ hợp âm đổi.

```mermaid
sequenceDiagram
    autonumber
    participant P as pipeline.chords
    participant R as rhythm.analyze
    participant C as chords.bar_start

    P->>R: analyze(..., pickup_slots)
    alt pickup given
        R-->>P: downbeat_slot from B8a
        P->>C: bar_start(labels, rhythm, unit_slots)
        C-->>P: bar1_slot from B8a downbeat
    else no pickup
        R-->>P: downbeat_slot from B8 (fallback)
        P->>C: bar_start(labels, rhythm, unit_slots)
        C->>C: count chord changes per candidate offset (C11)
        alt best beats runner-up by >= 20% and >= 4 changes
            C-->>P: bar1_slot from chord changes
        else close call
            C-->>P: bar1_slot from B8 downbeat
        end
    end
```

## 3. Lỗi: không nhận được hợp âm nào

Ví dụ một file chỉ có tiếng trống hoặc gần như im lặng.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant CLI as cli.main
    participant P as pipeline.chords
    participant C as chords.recognize

    U->>CLI: lamnhac chords drums.mp3
    CLI->>P: chords(opts, progress)
    P->>C: recognize(clip, rhythm)
    C->>C: every unit is N (C10a)
    C-->>P: ProcessingError
    P-->>CLI: ProcessingError
    CLI-->>U: stderr "lỗi: không nhận được hợp âm nào — bài có nhạc đệm không?" · exit 4
```

## 4. Lỗi: file đầu ra đã có

Tool dừng trước khi decode, để không tốn thời gian xử lý.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant CLI as cli.main
    participant P as pipeline.chords

    U->>CLI: lamnhac chords bai.mp3 (bai.chords.gp5 exists, no --force)
    CLI->>P: chords(opts, progress)
    P->>P: _prepare_outputs finds existing file (C2)
    P-->>CLI: OutputError
    CLI-->>U: stderr "lỗi: file đã tồn tại: … (dùng --force để ghi đè)" · exit 5
```

## Trace

| Requirement | Behavior | Diagram |
|-------------|----------|---------|
| R1 lệnh `chords`, file `.chords.gp5` | C1, C2 | 1, 4 |
| R2 24 hợp âm + N | C7, C8, C9, C10a | 1, 3 |
| R3 đổi theo phách, làm mượt | C10 | 1 |
| R4 giọng, tên theo giọng, giọng trong file | C12, C13, C13a, C17a, C18 | 1 |
| R5 `.gp5` có thế bấm, tên, sơ đồ | C15, C16, C17 | 1 |
| R6 dùng chung phần nhịp, `--pickup` | C5, C6, C11 | 1, 2 |
| R7 tuỳ chọn chung, an toàn, offline | C1–C4 | 1, 4 |
| R8 bảng chữ, `--format txt` | C18 | 1 |
| R9 `--capo` | C14 | – |
| R10 bộ đo eval | C19, C20, C21 | – |
