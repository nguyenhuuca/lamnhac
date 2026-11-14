# Tasks

## MP3 → Guitar Pro CLI ([plan](docs/plans/plan-mp3-to-guitarpro.md))

- [x] T1 Project scaffold, models, errors, gates (be9de6d)
- [x] T2 Install spike + report (basic-pitch, soundfile MP3, PyGuitarPro, music21, pip-audit) (263706f)
- [x] T3 `audio.load` + synthetic fixtures (ae66a20)
- [x] T4 `durations.split` (b8deb6f)
- [x] T5 `transcribe` (cd32b67)
- [x] T6 `rhythm.analyze` + `rhythm.quantize` (4679d48)
- [x] T7 `tab.assign` (7993603)
- [x] T8 `export_musicxml` (a0d8234)
- [x] T9 `pipeline` + `cli` (MusicXML only) (d1d0655)
- [x] T10 `export_gp5` + pipeline wiring (c185dc5)
- [x] T11 Eval G1 + report (G3 chưa đo: chưa có bài 3 phút có tab) (c073599)
- [x] T13 `--sensitivity` + new default thresholds (c073599)
- [x] T13b tab cost prefers low positions (e2b6e4b)
- [x] T15 `--pickup` (B8a, R16) (0ae3a40)
- [x] T16 per-beat alignment (B7b) (31e3fcc)
- [ ] T14 Eval thêm bản thu guitar thật, độ khớp dây/phím, G3 bài 3 phút
- [x] T12 Harmonic filter (B4a) + `--max-fret` (B12) (70ed456)

## Chords from song ([plan](docs/plans/plan-chords-from-song.md))

- [x] C-T1 Refactor rhythm to `OnsetLike` (no behavior change) (0e34d3a)
- [~] C-T2 Models, `rhythm.onsets`, `time_of_slot`, `chord_shapes`
- [ ] C-T3 `chords.recognize` (chroma, scores, Viterbi)
- [ ] C-T4 Key, chord names, capo
- [ ] C-T5 Bar start from chord changes + tab building
- [ ] C-T6 `.gp5` diagrams + key, `.chords.txt`
- [ ] C-T7 `pipeline.chords` + CLI subcommand
- [ ] C-T8 Synthetic chord fixture + integration test
- [x] C-T9 Answer parser + metrics (`tests/eval/answers.py`) (12c0d79)
- [ ] C-T10 Chord eval (`pytest -m eval`)
- [ ] C-T11 Docs (README, guide, algorithms)
- [ ] C-T12 Eval on owner songs, tune constants, report
