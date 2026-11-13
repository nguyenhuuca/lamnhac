import json
from itertools import pairwise
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
from lamnhac.rhythm import (
    _fold_tempo,
    _pick_downbeat,
    align_beats,
    analyze,
    grid_position,
    quantize,
)

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
    score = quantize(notes, _info(_even(), downbeat=8))
    flat = _flat(score.slots)
    assert flat[0] == (0, 12, ())  # bar 1 starts one bar before the downbeat (slot 8 - 16)
    assert flat[1] == (12, 2, (40,))
    assert any(s[0] == 16 and s[2] == (45,) for s in flat)
    assert sum(s[1] for s in flat) % 16 == 0


def test_note_within_half_slot_before_downbeat_needs_no_pickup() -> None:
    # 0.06 s before the beat at 0.5 s is 0.48 slot early: bar 1 still starts at the downbeat.
    notes = [_note(0.44, 0.6, 40)]
    score = quantize(notes, _info(_even(), downbeat=4))
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
    t = info.beat_times_s[info.downbeat_slot // 4]
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
    # All onsets land exactly once the downbeat is right (B8 uses max velocity per beat).
    assert best == len(expected)
    assert sum(s.length for s in score.slots) % 16 == 0


def test_align_beats_removes_constant_lag() -> None:
    beats = [0.03 + 0.5 * i for i in range(10)]
    onsets = [0.5 * i for i in range(1, 9)]
    assert align_beats(beats, onsets) == pytest.approx(tuple(0.5 * i for i in range(10)))


def test_align_beats_fewer_than_four_offsets_unchanged() -> None:
    beats = [0.03 + 0.5 * i for i in range(10)]
    assert align_beats(beats, [0.5, 1.0, 1.5]) == tuple(beats)
    assert align_beats(beats, []) == tuple(beats)


def test_align_beats_clamps_to_eighth_of_interval() -> None:
    beats = [0.5 * i for i in range(10)]
    onsets = [0.5 * i + 0.12 for i in range(1, 9)]  # within 1/4 (0.125) but beyond 1/8
    shifted = align_beats(beats, onsets)
    assert shifted[0] - beats[0] == pytest.approx(0.5 / 8)


def test_align_beats_ignores_onsets_outside_quarter_window() -> None:
    beats = [0.5 * i for i in range(10)]
    near = [0.5 * i - 0.02 for i in range(1, 5)]
    far = [0.5 * i + 0.25 for i in range(1, 8)]  # off-beat notes, beyond +-1/4
    shifted = align_beats(beats, near + far)
    assert shifted[0] - beats[0] == pytest.approx(-0.02)


def test_riff_beats_land_on_true_grid() -> None:
    clip, notes, truth = _riff()
    info = analyze(clip, notes, None, T44)
    interval = 60.0 / truth["tempo_bpm"]
    b = np.asarray(info.beat_times_s)
    err = np.abs(b - np.round(b / interval) * interval)
    print("riff mean beat error ms", err.mean() * 1000)
    assert err.mean() < 0.010


def test_downbeat_prefers_accented_single_note_over_weak_beat_chord() -> None:
    # Beats every 0.5 s. Accented single notes on beats 0, 4, 8; 3-note chords on beats 2, 6.
    beats = [0.5 * i for i in range(12)]
    notes: list[NoteEvent] = []
    for b in (0, 4, 8):
        notes.append(NoteEvent(b * 0.5, b * 0.5 + 0.4, 52, 1.0))
    for b in (2, 6):
        notes += [NoteEvent(b * 0.5, b * 0.5 + 0.4, p, 0.6) for p in (48, 55, 64)]
    assert _pick_downbeat(beats, notes, 16) == 0


def _accents(period_beats: int, count: int, offset: int = 0) -> list[NoteEvent]:
    return [
        _note(i * 0.5, i * 0.5 + 0.2, 40, 1.0 if i % period_beats == offset else 0.4)
        for i in range(count)
    ]


def test_downbeat_6_8_accent_every_three_quarters() -> None:
    # 6/8: bar_slots 12, offsets 0, 4, 8. Accents every 3 beats (12 slots) at beat 1 (slot 4).
    beats = _even(30)
    notes = _accents(3, 24, offset=1)
    assert _pick_downbeat(beats, notes, 12) == 4


def test_downbeat_2_2_bar_of_eight_slots() -> None:
    # 2/2: bar_slots 8, step 4. Accent every 2 beats at beat 1.
    assert _pick_downbeat(_even(30), _accents(2, 24, offset=1), 8) == 4


def test_downbeat_3_8_uses_step_two() -> None:
    # 3/8: bar_slots 6, step 2. Notes every 6 slots (1.5 beats) with accent at slot 2 of the bar.
    beats = _even(30)
    notes = []
    for i in range(12):
        t = i * 0.75 + 0.25  # 0.25 s = 2 slots at 0.5 s per beat
        notes.append(_note(t, t + 0.1, 40, 1.0))
        notes.append(_note(t + 0.25, t + 0.3, 40, 0.3))
    assert _pick_downbeat(beats, notes, 6) == 2


def test_downbeat_slot_is_less_than_bar_slots() -> None:
    assert 0 <= _pick_downbeat(_even(), _accents(4, 19, offset=3), 16) < 16


def test_quantize_rounds_half_up() -> None:
    # onset exactly 2.5 slots after beat 0 -> slot 3 (banker's round gives 2); end 4.5 -> 5.
    beats = _even()
    t = 0.5 * 2.5 / 4
    notes = [_note(t, 0.5 * 4.5 / 4, 40)]
    score = quantize(notes, _info(beats))
    assert _flat(score.slots)[1] == (3, 2, (40,))


def test_fold_halving_keeps_every_other_beat() -> None:
    beats = [0.25 * i for i in range(21)]  # 240 BPM
    bpm, grid = _fold_tempo(240.0, beats)
    assert bpm == pytest.approx(120.0)
    assert grid == beats[::2]


def test_fold_doubling_inserts_midpoints() -> None:
    beats = [1.5 * i for i in range(5)]  # 40 BPM
    bpm, grid = _fold_tempo(40.0, beats)
    assert bpm == pytest.approx(80.0)
    assert grid == pytest.approx([0.75 * i for i in range(9)])


def test_fold_keeps_two_beats() -> None:
    _, grid = _fold_tempo(400.0, [0.0, 0.15])
    assert len(grid) >= 2


def test_detected_fast_tempo_notes_land_four_slots_apart_after_fold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import librosa

    beats = np.array([0.25 * i for i in range(40)])  # tracker reports 240 BPM
    monkeypatch.setattr(librosa.beat, "beat_track", lambda **_: (240.0, beats))
    notes = [_note(0.5 * i, 0.5 * i + 0.2, 40 + i) for i in range(6)]  # every other tracked beat
    info = analyze(_clip(np.zeros(SAMPLE_RATE * 10), 10.0), notes, None, T44)
    assert info.tempo_bpm == pytest.approx(120.0)
    starts = [s.start for s in quantize(notes, info).slots if s.notes]
    assert [b - a for a, b in pairwise(starts)] == [4] * 5


def test_downbeat_tie_break_uses_bar_phase() -> None:
    # Equal-velocity notes on every beat -> all offsets tie. The first note sits at slot 36
    # (bar 2, beat 2 in 4/4); the tie must go to offset 4 (same phase), not offset 12
    # (closest to 36 in absolute terms among 0..12).
    beats = [0.5 * i for i in range(20)]
    notes = [NoteEvent(0.5 * b, 0.5 * b + 0.4, 60, 0.8) for b in range(9, 17)]
    assert _pick_downbeat(beats, notes, 16) == 4
