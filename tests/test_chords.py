import math
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from lamnhac.chords import (
    bar_start,
    build_tab,
    changes,
    chroma_per_unit,
    detect_key,
    label_probabilities,
    recognize,
    smooth,
    unit_boundaries,
)
from lamnhac.errors import ProcessingError
from lamnhac.models import (
    NO_CHORD,
    SAMPLE_RATE,
    AudioClip,
    ChordLabel,
    MusicKey,
    RhythmInfo,
    TimeSignature,
)

C = ChordLabel(0, False)
G = ChordLabel(7, False)
AM = ChordLabel(9, True)
F = ChordLabel(5, False)


def _rhythm(duration_s: float, interval: float = 0.5) -> RhythmInfo:
    n = int(duration_s / interval) + 2
    beats = tuple(i * interval for i in range(n))
    return RhythmInfo(120.0, beats, 0, TimeSignature(4, 4), "detected")


def _clip(samples: npt.NDArray[np.float32]) -> AudioClip:
    return AudioClip(samples, SAMPLE_RATE, len(samples) / SAMPLE_RATE, Path("dummy.wav"))


def _chroma_for(states: list[int], seed: int = 0) -> npt.NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    cols = []
    for s in states:
        v = np.zeros(12)
        root = s % 12
        third = 3 if s >= 12 else 4
        for pc in (0, third, 7):
            v[(root + pc) % 12] = 1.0
        v += rng.uniform(0, 0.25, 12)
        cols.append(v / np.linalg.norm(v))
    return np.stack(cols, axis=1)


def _decode(states: list[int]) -> list[ChordLabel]:
    return [NO_CHORD if s == 24 else ChordLabel(s % 12, s >= 12) for s in states]


def test_known_sequence_exact_labels() -> None:
    seq = [0, 0, 7, 7, 21, 21, 5, 5]  # C C G G Am Am F F
    chroma = _chroma_for(seq)
    silent = np.zeros(len(seq), dtype=np.bool_)
    path = smooth(label_probabilities(chroma, silent), 4)
    assert _decode(path) == [C, C, G, G, AM, AM, F, F]


def test_odd_unit_is_smoothed_away() -> None:
    chroma = _chroma_for([0] * 8)
    # a unit leaning towards G but still containing C: strong enough to be noise, not a change
    chroma[:, 4] = 0.55 * chroma[:, 4] + 0.45 * _chroma_for([7])[:, 0]
    chroma[:, 4] /= np.linalg.norm(chroma[:, 4])
    silent = np.zeros(8, dtype=np.bool_)
    path = smooth(label_probabilities(chroma, silent), 4)
    assert _decode(path) == [C] * 8


def test_silent_and_zero_columns_are_n() -> None:
    chroma = _chroma_for([0, 0, 0, 0])
    chroma[:, 2] = 0.0
    silent = np.array([False, False, True, False])
    prob = label_probabilities(chroma, silent)
    assert prob.shape == (25, 4)
    assert np.allclose(prob.sum(axis=0), 1.0)
    assert int(np.argmax(prob[:, 2])) == 24
    zero_only = label_probabilities(np.zeros((12, 1)), np.array([True]))
    assert smooth(zero_only, 4) == [24]


def _triad(freqs: list[float], seconds: float, detune: float) -> npt.NDArray[np.float64]:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    out = np.zeros_like(t)
    for f in freqs:
        out += 0.2 * np.sin(2 * np.pi * f * detune * t)
    return out


def _song(detune: float) -> npt.NDArray[np.float32]:
    c = _triad([130.81, 164.81, 196.00, 261.63], 2.0, detune)
    am = _triad([110.00, 130.81, 164.81, 220.00], 2.0, detune)
    return np.concatenate([c, am]).astype(np.float32)


@pytest.mark.parametrize("cents", [0.0, 30.0])
def test_recognize_c_then_am(cents: float) -> None:
    clip = _clip(_song(2 ** (cents / 1200)))
    labels = recognize(clip, _rhythm(clip.duration_s), 4)
    assert len(labels) == 8
    assert all(lab == C for lab in labels[:3])
    assert all(lab == AM for lab in labels[5:])


def test_all_silent_raises() -> None:
    clip = _clip(np.zeros(SAMPLE_RATE * 4, dtype=np.float32))
    with pytest.raises(ProcessingError, match="không nhận được hợp âm nào"):
        recognize(clip, _rhythm(clip.duration_s), 4)


def test_unit_boundaries_count_and_limit() -> None:
    b = unit_boundaries(_rhythm(10.0), 4, 3.2)
    assert len(b) == math.ceil(3.2 / 0.5)
    assert b[:3] == pytest.approx([0.0, 0.5, 1.0])
    assert all(t < 3.2 for t in b)


def test_unit_boundaries_half_beats() -> None:
    b = unit_boundaries(_rhythm(10.0), 2, 2.0)
    assert b == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75])


def test_chroma_per_unit_columns_when_last_boundary_near_end() -> None:
    clip = _clip(_song(1.0)[: SAMPLE_RATE * 2])
    boundaries = [0.0, 0.5, 1.0, 1.5, clip.duration_s - 1e-4]
    chroma, silent = chroma_per_unit(clip, boundaries)
    assert chroma.shape == (12, 5)
    assert silent.shape == (5,)
    assert not silent[:4].any()


DM = ChordLabel(2, True)
E = ChordLabel(4, False)
D = ChordLabel(2, False)
EM = ChordLabel(4, True)


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        ([C, G, AM, F] * 4, MusicKey(0, False)),
        ([AM, DM, E, AM] * 4, MusicKey(9, True)),
        ([G, D, EM, C] * 4, MusicKey(7, False)),
        ([NO_CHORD] * 4, MusicKey(0, False)),
        ([], MusicKey(0, False)),
    ],
)
def test_detect_key(labels: list[ChordLabel], expected: MusicKey) -> None:
    assert detect_key(labels) == expected


def _rhythm_ts(num: int, den: int, downbeat: int = 0) -> RhythmInfo:
    beats = tuple(i * 0.5 for i in range(200))
    return RhythmInfo(120.0, beats, downbeat, TimeSignature(num, den), "detected")


def _beat2_labels() -> list[ChordLabel]:
    # 4 units per bar; the chord changes at unit 1 of every bar
    labels: list[ChordLabel] = []
    for i in range(8):
        labels += [G if i % 2 else C] * 4
    return [C, *labels[:-1]]


def test_changes_counts_chord_after_n() -> None:
    assert changes([NO_CHORD, C, C, NO_CHORD, C, G, G]) == [1, 4, 5]


def test_bar_start_picks_beat_two() -> None:
    bar1, dropped = bar_start(_beat2_labels(), _rhythm_ts(4, 4), 4, False)
    assert bar1 % 16 == 4
    assert dropped == 0


def test_bar_start_close_scores_fall_back() -> None:
    labels: list[ChordLabel] = []
    for _ in range(8):
        labels += [C, C, G, G]
    labels[5] = AM  # extra change: offsets 0 and 8 score 8 and 9
    assert bar_start(labels, _rhythm_ts(4, 4, 4), 4, False)[0] % 16 == 4


def test_bar_start_few_changes_fall_back() -> None:
    labels = [C] * 4 + [G] * 4 + [AM] * 4
    assert bar_start(labels, _rhythm_ts(4, 4, 8), 4, False)[0] % 16 == 8


def test_bar_start_pickup_given_uses_downbeat() -> None:
    assert bar_start(_beat2_labels(), _rhythm_ts(4, 4, 8), 4, True)[0] % 16 == 8


def test_bar_start_drops_leading_n() -> None:
    labels = [NO_CHORD] * 2 + [C] * 4 + [G] * 4
    bar1, dropped = bar_start(labels, _rhythm_ts(4, 4, 8), 4, True)
    assert bar1 == 8
    assert dropped == 2


@pytest.mark.parametrize(("num", "den", "unit"), [(4, 4, 4), (6, 8, 2), (2, 2, 8)])
def test_build_tab_slot_lengths(num: int, den: int, unit: int) -> None:
    rhythm = _rhythm_ts(num, den)
    labels = [C, C, NO_CHORD, G, G]
    tab, diagrams, count = build_tab(labels, MusicKey(0, False), unit, 0, rhythm, 0, "t")
    assert all(s.length == unit for s in tab.slots[:5])
    assert sum(s.length for s in tab.slots) % rhythm.time_signature.bar_slots == 0
    assert tab.slots[2].notes == ()
    assert sorted(diagrams) == [0, 3 * unit]
    assert count == 2


def test_build_tab_skips_units_before_bar1() -> None:
    tab, _, _ = build_tab([NO_CHORD, C, G], MusicKey(0, False), 4, 4, _rhythm_ts(4, 4), 0, "t")
    assert tab.slots[0].start == 0
    assert tab.slots[0].notes != ()


def test_build_tab_open_c_notes() -> None:
    tab, diagrams, _ = build_tab([C], MusicKey(0, False), 4, 0, _rhythm_ts(4, 4), 0, "t")
    frets = {(n.string, n.fret) for n in tab.slots[0].notes}
    assert frets == {(5, 3), (4, 2), (3, 0), (2, 1), (1, 0)}
    assert diagrams[0].name == "C"


def test_build_tab_capo_shifts_frets() -> None:
    eb = ChordLabel(3, False)
    tab, diagrams, _ = build_tab([eb], MusicKey(3, False), 4, 0, _rhythm_ts(4, 4), 3, "t")
    frets = {(n.string, n.fret) for n in tab.slots[0].notes}
    assert frets == {(5, 6), (4, 5), (3, 3), (2, 4), (1, 3)}
    assert diagrams[0].name == "C"


def test_bar_start_skips_whole_bars_of_leading_no_chord() -> None:
    # 4/4, unit 4: 10 N units (2.5 bars) then C on every beat; downbeat 0, no pickup search hit.
    beats = tuple(i * 0.5 for i in range(80))
    rhythm = RhythmInfo(120.0, beats, 0, TimeSignature(4, 4), "user")
    labels = [NO_CHORD] * 10 + [ChordLabel(0, False)] * 22
    bar1, dropped = bar_start(labels, rhythm, 4, pickup_given=True)
    assert bar1 == 32  # the bar containing unit 10 (slot 40) starts at slot 32
    assert dropped == 8


def test_bar_start_backs_up_for_pickup_before_downbeat() -> None:
    labels = [C] * 3 + [G] * 2
    bar1, dropped = bar_start(labels, _rhythm_ts(4, 4, 8), 4, True)
    assert bar1 == -8
    assert dropped == 0


def test_build_tab_negative_bar1_slots_are_contiguous_and_whole_bars() -> None:
    # Regression: the tail rest was placed by summed length, overlapping real slots.
    labels = [C] * 3 + [G] * 2
    tab, _, _ = build_tab(labels, MusicKey(0, False), 4, -8, _rhythm_ts(4, 4, 8), 0, "t")
    assert tab.slots[0].start == 8
    for prev, cur in zip(tab.slots, tab.slots[1:], strict=False):
        assert cur.start == prev.start + prev.length
    end = tab.slots[-1].start + tab.slots[-1].length
    assert end % 16 == 0


def test_smooth_short_units_hold_longer() -> None:
    # One unit 40000x more G than C inside C: the switch costs ~18500x at P_STAY 0.85
    # and ~76000x at 0.92, so long units switch and short (6/8) units keep C.
    prob = np.full((25, 9), 1e-9)
    prob[0, :] = 0.9
    prob[7, 4], prob[0, 4] = 0.9, 0.9 / 40000
    prob /= prob.sum(axis=0, keepdims=True)
    assert smooth(prob, 4)[4] == 7
    assert smooth(prob, 2) == [0] * 9


def test_recognize_zero_units_raises() -> None:
    rhythm = RhythmInfo(120.0, (5.0, 5.5), 0, TimeSignature(4, 4), "detected")
    with pytest.raises(ProcessingError):
        recognize(_clip(np.zeros(22050, dtype=np.float32)), rhythm, 4)
