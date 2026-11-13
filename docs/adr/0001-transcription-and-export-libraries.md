# ADR-0001: Transcription model and export libraries

**Status:** Accepted (2026-11-13) · **Deciders:** project owner · **Tags:** dependencies, audio, export

## Context

PRD `docs/prd/PRD-mp3-to-guitarpro.md` asks for an offline Windows CLI that turns a solo-guitar MP3 into a draft tab (Note F1 ≥ 0.70, G1) exported as `.gp5` (R7) and MusicXML (R6). Polyphonic note transcription (R3) and the proprietary `.gp5` format are the two parts we will not write ourselves. Swapping either later means rewriting the pipeline's input or output stage, so the choice gets an ADR.

PyPI facts, checked 2026-11-13:
- basic-pitch 0.4.0 (2024-08-16): Python 3.8–3.11. On Windows with Python ≥ 3.11 it requires `tensorflow>=2.4.1,<2.15.1`. No release since 2024.
- PyGuitarPro 0.11 (2026-05-03): Python ≥ 3.10, reads and writes GP3/4/5.
- music21 10.5.2 (2026-10-28): Python ≥ 3.11, writes MusicXML including tab staves.

## Options

### A. basic-pitch + PyGuitarPro + music21 (chosen)
- basic-pitch: a pretrained polyphonic model with pitch bends, CPU-friendly, Apache-2.0. Its TensorFlow dependency is about 500 MB and pins Python to 3.11. It has not had a release for two years.
- PyGuitarPro: the only maintained Python library for `.gp5`.
- music21: mature, with a full MusicXML writer.
- Reversal cost: moderate. Each library sits behind its own module (`transcribe`, `export_gp5`, `export_musicxml`) with a plain note-event model between them.

### B. Guitar-specific research models (e.g. TabCNN-style)
These predict string and fret directly. There are no maintained packages, training or porting would be needed, and accuracy on real-world recordings is unproven. Too much work for an MVP.

### C. Write our own `.gp5` / MusicXML writers
Full control and no dependencies, but `.gp5` is an undocumented binary format. This is high risk for no user benefit.

## Decision

Option A. It is the only combination that is installable on Windows, offline, free, and meets R3, R6 and R7 without research work. We give up Python 3.12+ and accept a large TensorFlow install.

## Consequences

- The project pins Python 3.11 (`.python-version`, `requires-python = ">=3.11,<3.12"`).
- The first plan task is an install spike: `uv add basic-pitch` on Windows/3.11 must resolve and transcribe a sample file. If it fails, fall back to running basic-pitch's ONNX model with `onnxruntime` directly, recorded in a new ADR.
- The pipeline modules exchange an internal `NoteEvent` model (pitch, onset, duration, velocity), so the transcription backend can be replaced without touching quantize, tab or export.
- Tests: a Note F1 regression test with `mir_eval` on a small fixture set, plus round-trip tests that read the `.gp5` back with PyGuitarPro and the MusicXML back with music21.
- Security: all three run locally. The model weights ship inside the basic-pitch package, so there are no runtime downloads (R9).

## Changelog

- 2026-11-13: created.
