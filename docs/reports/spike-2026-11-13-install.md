# Spike T2: install and stack check (2026-11-13)

Environment: Windows 10 (win_amd64), Python 3.11, uv 0.13.8. Scripts are in `scratchpad/spike/` (git-ignored).

## Summary

| # | Question | Result | Evidence |
|---|----------|--------|----------|
| 1 | basic-pitch installs on Windows + 3.11 | YES, only after 3 pyproject changes (see "Surprises") | Plain `uv add` failed: `tensorflow-io-gcs-filesystem==0.37.1 ... doesn't have a source distribution or wheel for the current platform`. Same with `basic-pitch==0.4.0`. |
| 2 | `predict(...)` runs on the MP3 | YES | Returns `(model_output: dict, midi_data: PrettyMIDI, note_events: list[tuple])`. 18 events for the 6 synthesized notes. Wall time 31.7 s including TensorFlow import and model load (5 s clip). |
| 3 | soundfile reads MP3 without ffmpeg | YES | libsndfile 1.2.2; `sf.info` reports `format: MPEG-1/2 Audio [MP3]`, 44100 Hz, 1 ch, 5.000 s; `sf.blocks(p, blocksize=44100)` yielded 220500 frames. ffmpeg exists on this machine (`C:\ffmpeg\bin`), so the scripts were run with it stripped from PATH (`where ffmpeg` then finds nothing). `soundfile.write(..., format="MP3")` also works. |
| 4 | PyGuitarPro write/parse GP5 | YES (with notes) | Round trip OK: tempo 97, 1 track, strings 64/59/55/50/45/40, 4/4, 4 beats incl. a tie. Vietnamese title fails with the default encoding, works with `encoding="utf-8"` (see below). |
| 5 | music21 TAB MusicXML | PARTIAL | `<string>`, `<fret>`, `<sign>TAB</sign>`, `<staff-lines>6` present. `<staff-tuning>` NOT emitted (TODO in music21 source). Filename `x.tmp-123.musicxml` is kept exactly. |
| 6 | pip-audit | Advisories in 3 packages (lock export); none plausibly reachable via a bundled model and local audio files | See section 6. |

## 1. Resolved versions

basic-pitch 0.4.0, tensorflow 2.15.0, tensorflow-intel 2.15.0 (Windows only), keras 2.15.0, tensorflow-io-gcs-filesystem 0.31.0, librosa 0.11.0, soundfile 0.14.0, numpy 1.26.4, pyguitarpro 0.11, music21 10.5.2, scipy 1.17.1, resampy 0.4.2, pretty-midi 0.2.11.post0, setuptools 80.10.2.

## Surprises (pyproject changes that were needed)

1. `tensorflow-io-gcs-filesystem` 0.37.x has no Windows wheel. Fix: `[tool.uv] constraint-dependencies = ["tensorflow-io-gcs-filesystem<=0.31.0; sys_platform == 'win32'"]`.
2. The lock resolved `tensorflow` 2.15.0 without `tensorflow-intel` (on Windows the `tensorflow` wheel is a stub that depends on `tensorflow-intel`; uv took the metadata of another platform's wheel). `import tensorflow` then failed with `ModuleNotFoundError`, and `import basic_pitch` failed with the misleading `NameError: name '_default_model_type' is not defined` (basic_pitch falls through silently when no backend imports). Fix: direct dependency `tensorflow-intel==2.15.0 ; sys_platform == 'win32'`.
3. `resampy` 0.4.2 imports `pkg_resources`, which is gone from setuptools 84. Fix: constraint `setuptools<81`. This pins setuptools below the fixes for PYSEC-2026-3447 (fix 83.0.0) and GHSA-xmj3-9gf7-h52w (fix 84.1.0); setuptools is only used at build/import time here, so low risk, but revisit when resampy or basic-pitch updates.
4. `import basic_pitch` logs warnings about missing coremltools, tflite-runtime and onnxruntime. Harmless; the TensorFlow backend is used.
5. First `predict` call takes about 30 s (imports plus model load). Not measured here, but loading the model once and reusing it should avoid paying this per call (basic_pitch accepts a `Model` object as its model argument; verify when implementing T3).

## 2. predict()

Call: `predict(path, onset_threshold=0.5, frame_threshold=0.3, minimum_note_length=58, minimum_frequency=70, maximum_frequency=1400)`.

- Return: `model_output` is a `dict` (arrays `note`, `onset`, `contour`), `midi_data` is `pretty_midi.PrettyMIDI`, `note_events` is a `list` of 5-tuples `(start_s: float, end_s: float, pitch_midi: int, amplitude: float, pitch_bend: list[int])`. Example: `(2.9967, 4.4840, 64, 0.677, [1, 1, ..., 1])`; the bend list has one entry per frame of the note.
- Synthesized (additive tones with 4 harmonics, 0.6 s apart): E2 40, A2 45, D3 50, G3 55, B3 59, E4 64. Detected: all six fundamentals at the right onsets (E2 0.01 s, A2 0.58, D3 1.2, G3 1.8, B3 2.38, E4 3.0). Extra events are harmonics (A3 57, D4 62, G4 67, B4 71, E5 76, A4 69, G5 79) and fragments (D3 split in two, A2 split in two). Expect harmonic and duplicate events from real recordings; the pipeline needs filtering by amplitude and overlap.

## 3. soundfile and ffmpeg

See the table. soundfile bundles libsndfile 1.2.2, which has MP3 support, so no ffmpeg is needed. Verified with ffmpeg removed from PATH. librosa is not needed for decoding.

## 4. PyGuitarPro 0.11 API notes (for export_gp5, T8)

- `import guitarpro as gp; from guitarpro import models as m`. Models are `attrs` classes.
- `gp.write(song, path_or_stream, version=(5, 1, 0), encoding='cp1252')`; `gp.parse(path_or_stream, encoding='cp1252')`.
- `m.Song(title=..., artist=..., tempo=97)`: tempo is a plain `int` on the Song (no Tempo class). The spike cleared `song.measureHeaders = []` and `song.tracks = []` and rebuilt them.
- Header: `h = m.MeasureHeader(number=1, timeSignature=m.TimeSignature(numerator=4, denominator=m.Duration(value=4)))`; `song.addMeasureHeader(h)`. `h.start` defaults to 960 (`Duration.quarterTime`).
- Track: `tr = m.Track(song, number=1, name="Guitar")`; `tr.strings = [m.GuitarString(number, midi_value)]` with string 1 = highest. Standard tuning: 64, 59, 55, 50, 45, 40. `tr.fretCount = 24`; `tr.measures = []`.
- `ms = m.Measure(tr, h)`; `v = ms.voices[0]`; `b = m.Beat(v, start=...)`; `b.duration = m.Duration(value=4)` (4 = quarter; `isDotted`, `tuplet` also exist; ticks = `b.duration.time`); `n = m.Note(b, value=fret, string=string_number, type=m.NoteType.normal, velocity=95)`; `b.notes.append(n)`; `v.beats.append(b)`; `tr.measures.append(ms)`; `song.tracks.append(tr)`. `NoteType` members: rest, normal, tie, dead.
- Round trip preserves tempo, tuning, time signature, string/fret and beat starts (960-tick steps). A `NoteType.tie` note comes back with `value 0` (GP5 does not store the fret of tied notes), so compare tie notes by string and type only.
- Vietnamese title "Bài hát đầu tiên": default `cp1252` raises `UnicodeEncodeError` (đ and ầ are not in cp1252); `cp1258` also fails (ầ). `encoding="utf-8"` writes and reads back correctly only if the same encoding is passed to `parse`; reading with the default cp1252 gives mojibake. Guitar Pro itself expects a legacy 8-bit codepage, so non-ASCII text may look garbled in the real application (not tested). Decision for the spec: write utf-8 and accept that risk, or ASCII-fold the title in the GP5 file.

## 5. music21 10.5.2 API notes (for export_musicxml, T10)

- `stream.Part`, `part.insert(0, clef.TabClef())`, `meter.TimeSignature("4/4")`, `tempo.MetronomeMark(number=97)`, `stream.Measure(number=1)`, `note.Note("D2", quarterLength=1)`.
- Fret and string: `n.articulations.append(articulations.StringIndication(6))` and `articulations.FretIndication(0)` produce `<technical><string>6</string><fret>0</fret></technical>`.
- Staff lines: `measure.insert(0, layout.StaffLayout(staffLines=6))` produces `<staff-details print-object="yes"><staff-lines>6</staff-lines>`.
- Staff tuning: NOT supported (`m21ToXml.py` has `# TODO: staff-tuning`). Workaround verified with `xml.etree.ElementTree` (`scratchpad/spike/q5b.py`): after writing, append `<staff-tuning line="N"><tuning-step>D</tuning-step><tuning-octave>2</tuning-octave></staff-tuning>` (line 1 = lowest string; Drop D: D2 A2 D3 G3 B3 E4) to `staff-details` after `staff-lines`. Only our own file is parsed.
- `score.write("musicxml", "x.tmp-123.musicxml")` keeps the exact filename and returns its path, so an atomic write (tmp name, then `os.replace`) works.

## 6. pip-audit

`uv run --with pip-audit pip-audit --local` reported "No known vulnerabilities found", but it audited uv's temporary environment, so I do not trust it. Auditing the lock instead (`uv export --no-hashes --no-emit-project`, then `uvx pip-audit -r req.txt --no-deps --disable-pip`) found 28 entries (16 unique IDs) in 3 packages:

| Package | Ids | Fixed in | Applies? |
|---------|-----|----------|----------|
| keras 2.15.0 | CVE-2025-12060, PYSEC-2025-76 (fix 3.11.0), PYSEC-2025-121 (no fix listed), PYSEC-2026-1487, -2324, -2547, -3629 to -3634, -3856 | 3.12.0 to 3.15.0 | Fixes are Keras 3.x, but TF 2.15 requires keras 2.15, so not upgradeable. I did not read the advisory texts; I expect them to concern loading untrusted model files. We load only the bundled basic-pitch model, so likely not reachable unless user-supplied models are ever loaded. |
| protobuf 4.25.9 | PYSEC-2026-1805 | 5.29.6, 6.33.5 | Pinned below 5 by TF 2.15. Concerns parsing untrusted protobuf data (not verified); we only parse the bundled model. |
| setuptools 80.10.2 | PYSEC-2026-3447, GHSA-xmj3-9gf7-h52w | 83.0.0, 84.1.0 | Caused by our `setuptools<81` constraint (surprise 3). Build/install time only. |

Note for ADR-0001: TF 2.15 (Dec 2023) is old and pins keras and protobuf. basic-pitch also ships ONNX and TFLite models, which would avoid TensorFlow; that is the owner's call.

## Gates

`uv run ruff check`: pass. `uv run ruff format --check`: pass (61 files). `uv run mypy src`: pass. `uv run pytest -m "not eval"`: 55 passed.
