"""G1 eval: Note F1 of the transcription against reference tabs (spec Testing, plan T11).

Put pairs `<name>.mp3` + `<name>.gp5` (a correct tab of that recording) in
`tests/fixtures/real/`. The folder is git-ignored: recordings and tabs stay on your machine.
Run with `uv run pytest -m eval -s`.

Metric: mir_eval Note F1, onset within 50 ms, pitch exact, offsets ignored. The recording may
start a little before or after the tab's first beat, so the best global shift in +-1 s is
applied first (one number per song, not per note).
"""

import time
from pathlib import Path

import guitarpro
import mir_eval
import numpy as np
import pytest

from lamnhac import tab
from lamnhac import transcribe as tr
from lamnhac.audio import load
from lamnhac.models import GridNote, RhythmInfo, Score, Sensitivity, Slot, TimeSignature, Tuning

REAL = Path(__file__).parent.parent / "fixtures" / "real"
PAIRS = sorted(p for p in REAL.glob("*.gp5") if p.with_suffix(".mp3").exists())
F1_TARGET = 0.70  # PRD G1
TAB_MATCH_TARGET = 0.85  # string+fret equal to the reference tab, given perfect notes
ONSET_TOLERANCE_S = 0.05
_PAD_S = 2.0  # keeps shifted intervals non-negative for mir_eval

pytestmark = pytest.mark.eval


def reference(gp5: Path) -> tuple[list[tuple[float, int]], Tuning]:
    """Onsets (s) and MIDI pitches of the first track, following tempo changes."""
    song = guitarpro.parse(str(gp5))
    track = song.tracks[0]
    tuning = Tuning(tuple(s.value for s in track.strings))
    tempo = float(song.tempo)
    t = 0.0
    notes: list[tuple[float, int]] = []
    for measure in track.measures:
        for beat in measure.voices[0].beats:
            mix = beat.effect.mixTableChange
            if mix and mix.tempo and mix.tempo.value > 0:
                tempo = float(mix.tempo.value)
            d = beat.duration
            quarters = 4.0 / d.value * (1.5 if d.isDotted else 1.0)
            quarters *= d.tuplet.times / d.tuplet.enters
            for note in beat.notes:
                if note.type in (guitarpro.NoteType.tie, guitarpro.NoteType.dead):
                    continue
                open_string = track.strings[note.string - 1].value
                if note.effect.grace:  # played just before the beat
                    notes.append((t - 60.0 / tempo / 8, note.effect.grace.fret + open_string))
                notes.append((t, note.value + open_string))
            t += quarters * 60.0 / tempo
    return sorted(notes), tuning


def note_f1(
    ref: list[tuple[float, int]], est: list[tuple[float, int]], shift: float
) -> tuple[float, float, float]:
    def arrays(notes: list[tuple[float, int]], dt: float) -> tuple[np.ndarray, np.ndarray]:
        on = np.array([o + dt + _PAD_S for o, _ in notes])
        hz = np.array([mir_eval.util.midi_to_hz(p) for _, p in notes])
        return np.stack([on, on + 0.1], axis=1), hz

    ri, rp = arrays(ref, 0.0)
    ei, ep = arrays(est, shift)
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(
        ri, rp, ei, ep, onset_tolerance=ONSET_TOLERANCE_S, offset_ratio=None
    )
    return float(p), float(r), float(f)


def best_shift(ref: list[tuple[float, int]], est: list[tuple[float, int]]) -> float:
    shifts = np.arange(-1.0, 1.0, 0.01)
    return float(shifts[int(np.argmax([note_f1(ref, est, s)[2] for s in shifts]))])


@pytest.mark.skipif(not PAIRS, reason=f"no .mp3 + .gp5 pairs in {REAL}")
@pytest.mark.parametrize("gp5", PAIRS, ids=[p.stem for p in PAIRS])
def test_note_f1(gp5: Path) -> None:
    ref, tuning = reference(gp5)
    clip = load(gp5.with_suffix(".mp3"))
    scores: dict[Sensitivity, tuple[float, float, float]] = {}
    for level in ("low", "normal", "high"):
        start = time.perf_counter()
        notes, _ = tr.transcribe(clip, tuning, sensitivity=level)
        elapsed = time.perf_counter() - start
        est = [(n.onset_s, n.pitch) for n in notes]
        shift = best_shift(ref, est)
        scores[level] = note_f1(ref, est, shift)
        p, r, f = scores[level]
        print(
            f"\n{gp5.stem} [{level}] ref {len(ref)} est {len(est)} shift {shift:+.2f}s "
            f"P {p:.3f} R {r:.3f} F1 {f:.3f} ({elapsed:.1f}s, audio {clip.duration_s:.1f}s)"
        )
    assert scores["normal"][2] >= F1_TARGET


def reference_beats(gp5: Path) -> tuple[list[list[tuple[int, int, int]]], Tuning]:
    """Struck notes per beat as (pitch, string 1..6, fret), first track."""
    song = guitarpro.parse(str(gp5))
    track = song.tracks[0]
    beats = []
    for measure in track.measures:
        for beat in measure.voices[0].beats:
            struck = [
                (n.value + track.strings[n.string - 1].value, n.string, n.value)
                for n in beat.notes
                if n.type not in (guitarpro.NoteType.tie, guitarpro.NoteType.dead)
            ]
            if struck:
                beats.append(struck)
    return beats, Tuning(tuple(s.value for s in track.strings))


@pytest.mark.skipif(not PAIRS, reason=f"no .mp3 + .gp5 pairs in {REAL}")
@pytest.mark.parametrize("gp5", PAIRS, ids=[p.stem for p in PAIRS])
def test_string_fret_match_with_reference_notes(gp5: Path) -> None:
    """Tab step alone: given the reference's own notes, how often is string+fret the same."""
    beats, tuning = reference_beats(gp5)
    bar = TimeSignature(4, 4).bar_slots
    slots = [Slot(i, 1, tuple(GridNote(p, 0.8) for p, _, _ in b)) for i, b in enumerate(beats)]
    slots += [Slot(i, 1) for i in range(len(slots), -(-len(slots) // bar) * bar)]
    rhythm = RhythmInfo(100.0, (0.0, 0.6), 0, TimeSignature(4, 4), "user")
    out, _ = tab.assign(Score(rhythm, tuple(slots)), tuning)
    same = total = 0
    for struck, chosen in zip(beats, out.slots, strict=False):
        got = {n.pitch: (n.string, n.fret) for n in chosen.notes}
        for pitch, string, fret in struck:
            total += 1
            same += got.get(pitch) == (string, fret)
    print(f"\n{gp5.stem}: same string+fret {same}/{total} ({same / total:.0%})")
    assert same / total >= TAB_MATCH_TARGET
