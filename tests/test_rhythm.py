import json
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

from lamnhac.audio import load
from lamnhac.errors import ProcessingError
from lamnhac.models import (
    SAMPLE_RATE,
    AudioClip,
    NoteEvent,
    RhythmInfo,
    Slot,
    TimeSignature,
)
from lamnhac.rhythm import analyze, grid_position, quantize

FIXTURES = Path(__file__).parent / "fixtures"
T44 = TimeSignature(4, 4)


def _info(
    beats: list[float], downbeat: int = 0, ts: TimeSignature = T44, bpm: float = 120.0
) -> RhythmInfo:
    return RhythmInfo(bpm, tuple(beats), downbeat, ts, "detected")


def _even(n: int = 40, interval: float = 0.5) -> list[float]:
    return [i * interval for i in range(n)]


def _note(onset: float, offset: float, pitch: int = 40, velocity: float = 0.8) -> NoteEvent:
    return NoteEvent(onset, offset, pitch, velocity)


def _flat(slots: tuple[Slot, ...]) -> list[tuple[int, int, tuple[int, ...]]]:
    return [(s.start, s.length, tuple(n.pitch for n in s.notes)) for s in slots]


# --- grid_position -----------------------------------------------------------


def test_grid_position_even_beats() -> None:
    beats = _even()
    assert grid_position(0.0, beats) == pytest.approx(0.0)
    assert grid_position(0.5, beats) == pytest.approx(4.0)
    assert grid_position(0.625, beats) == pytest.approx(5.0)


def test_grid_position_drifting_beats_keep_notes_on_multiples_of_four() -> None:
    rng = np.random.default_rng(1)
    intervals = 0.5 * (1 + rng.uniform(-0.03, 0.03, 30))
    beats = [0.0, *np.cumsum(intervals).tolist()]
    for i, b in enumerate(beats):
        assert grid_position(b, beats) == pytest.approx(4 * i)


def test_grid_position_extrapolates_with_median_interval() -> None:
    beats = [1.0, 1.5, 2.0, 2.5]
    assert grid_position(0.5, beats) == pytest.approx(-4.0)
    assert grid_position(0.75, beats) == pytest.approx(-2.0)
    assert grid_position(3.0, beats) == pytest.approx(4 * 3 + 4.0)
    assert grid_position(2.5, beats) == pytest.approx(12.0)


def test_grid_position_needs_two_beats() -> None:
    with pytest.raises(ValueError):
        grid_position(0.0, [0.0])


# --- quantize ----------------------------------------------------------------


def test_chord_grouping_and_duplicate_pitch_keeps_louder() -> None:
    notes = [
        _note(0.0, 0.5, 40, 0.5),
        _note(0.0, 0.5, 47, 0.7),
        _note(0.0, 0.5, 40, 0.9),
    ]
    score = quantize(notes, _info(_even()))
    first = score.slots[0]
    assert (first.start, first.length) == (0, 4)
    assert {(n.pitch, n.velocity) for n in first.notes} == {(40, 0.9), (47, 0.7)}


def test_sustained_note_truncated_at_next_onset() -> None:
    notes = [_note(0.0, 1.5, 40), _note(0.5, 0.75, 45)]
    score = quantize(notes, _info(_even()))
    assert _flat(score.slots)[:2] == [(0, 4, (40,)), (4, 2, (45,))]


def test_rest_inserted_in_gap_and_last_bar_padded() -> None:
    notes = [_note(0.0, 0.25, 40), _note(1.0, 1.25, 45)]
    score = quantize(notes, _info(_even()))
    assert _flat(score.slots) == [
        (0, 2, (40,)),
        (2, 6, ()),
        (8, 2, (45,)),
        (10, 6, ()),
    ]


def test_no_extra_bar_when_last_note_ends_on_bar_line() -> None:
    score = quantize([_note(0.0, 2.0, 40)], _info(_even()))
    assert sum(s.length for s in score.slots) == 16


def test_pickup_bar_when_first_note_precedes_downbeat() -> None:
    # downbeat is beat 2 (t=1.0, slot 8); first note sits one beat before it.
    notes = [_note(0.5, 0.75, 40), _note(1.0, 1.5, 45)]
    score = quantize(notes, _info(_even(), downbeat=2))
    flat = _flat(score.slots)
    assert flat[0] == (0, 12, ())  # bar 1 starts one bar before the downbeat (slot 8 - 16)
    assert flat[1] == (12, 2, (40,))
    assert any(s[0] == 16 and s[2] == (45,) for s in flat)
    assert sum(s[1] for s in flat) % 16 == 0


def test_note_within_half_slot_before_downbeat_needs_no_pickup() -> None:
    # 0.06 s before the beat at 0.5 s is 0.48 slot early: bar 1 still starts at the downbeat.
    notes = [_note(0.44, 0.6, 40)]
    score = quantize(notes, _info(_even(), downbeat=1))
    assert score.slots[0].start == 0
    assert score.slots[0].notes


def test_empty_notes_give_one_rest_bar() -> None:
    score = quantize([], _info(_even()))
    assert _flat(score.slots) == [(0, 16, ())]


@pytest.mark.parametrize(("num", "den", "bar"), [(4, 4, 16), (3, 4, 12), (6, 8, 12)])
def test_total_is_multiple_of_bar_slots(num: int, den: int, bar: int) -> None:
    ts = TimeSignature(num, den)
    assert ts.bar_slots == bar
    notes = [_note(0.3 * i, 0.3 * i + 0.2, 40 + i) for i in range(11)]
    score = quantize(notes, _info(_even(), ts=ts))
    total = sum(s.length for s in score.slots)
    assert total % bar == 0
    assert total >= bar


# --- analyze -----------------------------------------------------------------


def _clip(samples: npt.NDArray[Any], duration: float) -> AudioClip:
    return AudioClip(samples.astype(np.float32), SAMPLE_RATE, duration, Path("x.mp3"))


def _clicks(bpm: float, seconds: float) -> AudioClip:
    interval = 60.0 / bpm
    y = np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)
    for i in range(int(seconds / interval)):
        s = int(i * interval * SAMPLE_RATE)
        y[s : s + 200] = np.sin(np.arange(200) * 0.3) * np.hanning(200)
    return _clip(y, seconds)


def test_analyze_empty_clip_raises() -> None:
    clip = _clip(np.zeros(1), 1.0)
    object.__setattr__(clip, "samples", np.zeros(0, dtype=np.float32))
    with pytest.raises(ProcessingError):
        analyze(clip, [], None, T44)


def test_analyze_silence_falls_back_to_even_grid() -> None:
    clip = _clip(np.zeros(SAMPLE_RATE * 4), 4.0)
    info = analyze(clip, [_note(0.25, 0.5)], None, T44)
    assert len(info.beat_times_s) >= 2
    assert info.beat_times_s[0] == pytest.approx(0.25)
    assert info.beat_times_s[-1] >= 3.75
    assert info.tempo_bpm == pytest.approx(120.0)


def test_user_tempo_override_sets_source_user() -> None:
    clip = _clicks(120, 8)
    info = analyze(clip, [], 90.0, T44)
    assert info.tempo_source == "user"
    assert info.tempo_bpm == 90.0
    assert analyze(clip, [], None, T44).tempo_source == "detected"


def test_user_tempo_out_of_range_raises() -> None:
    with pytest.raises(ProcessingError):
        analyze(_clicks(120, 4), [], 500.0, T44)


@pytest.mark.parametrize("offset", [0, 1, 2, 3])
def test_downbeat_follows_accents(offset: int) -> None:
    clip = _clicks(120, 10)
    notes = [_note(i * 0.5, i * 0.5 + 0.2, 40, 1.0 if i % 4 == offset else 0.4) for i in range(19)]
    info = analyze(clip, notes, 120.0, T44)
    t = info.beat_times_s[info.downbeat_index]
    accented = [n.onset_s for n in notes if n.velocity == 1.0]
    assert min(abs(t - a) for a in accented) < 0.1


def _riff() -> tuple[AudioClip, list[NoteEvent], dict[str, Any]]:
    clip = load(FIXTURES / "riff_97bpm.mp3")
    truth = json.loads((FIXTURES / "riff_97bpm.json").read_text(encoding="utf-8"))
    bar = 4 * 60.0 / truth["tempo_bpm"]
    notes = []
    for n in truth["notes"]:
        rel = (n["onset_s"] - truth["downbeat_time_s"]) / bar
        accent = 1.0 if abs(rel - round(rel)) < 0.02 else 0.6
        notes.append(_note(n["onset_s"], n["offset_s"], n["pitch"], accent))
    return clip, notes, truth


def test_riff_tempo_within_five_percent() -> None:
    clip, notes, truth = _riff()
    info = analyze(clip, notes, None, T44)
    print("riff detected tempo", info.tempo_bpm)
    assert info.tempo_bpm == pytest.approx(truth["tempo_bpm"], rel=0.05)
    assert info.tempo_source == "detected"


def test_scale_tempo_detected() -> None:
    clip = load(FIXTURES / "scale_c.mp3")
    truth = json.loads((FIXTURES / "scale_c.json").read_text(encoding="utf-8"))
    notes = [_note(n["onset_s"], n["offset_s"], n["pitch"]) for n in truth["notes"]]
    info = analyze(clip, notes, None, T44)
    print("scale detected tempo", info.tempo_bpm)
    assert 60 <= info.tempo_bpm <= 200


def test_riff_quantize_lands_on_expected_slots() -> None:
    clip, notes, truth = _riff()
    info = analyze(clip, notes, None, T44)
    score = quantize(notes, info)
    sixteenth = 60.0 / truth["tempo_bpm"] / 4
    expected = {
        round((n["onset_s"] - truth["downbeat_time_s"]) / sixteenth) for n in truth["notes"]
    }
    got = {s.start for s in score.slots if s.notes}
    # bar 1 may start a whole bar away from the true downbeat; allow bar-multiple shifts
    best = max(sum((e + shift) in got for e in expected) for shift in range(-32, 33, 16))
    print("riff slot match", best, "of", len(expected))
    assert best > len(expected) / 2
    assert sum(s.length for s in score.slots) % 16 == 0
