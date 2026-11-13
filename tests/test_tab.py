import itertools
import random
import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lamnhac.models import (
    STANDARD_TUNING,
    GridNote,
    RhythmInfo,
    Score,
    Slot,
    TimeSignature,
    Tuning,
)
from lamnhac.tab import assign, parse_tuning

RHYTHM = RhythmInfo(120.0, (0.0, 0.5, 1.0), 0, TimeSignature(4, 4), "user")


def make_score(slots_pitches: list[list[int]], velocity: float = 0.8) -> Score:
    slots = [
        Slot(i, 1, tuple(GridNote(p, velocity) for p in pitches))
        for i, pitches in enumerate(slots_pitches)
    ]
    pad = (-len(slots)) % 16
    slots += [Slot(len(slots) + j, 1) for j in range(pad)]
    return Score(RHYTHM, tuple(slots))


def centre(notes: tuple) -> float | None:  # type: ignore[type-arg]
    frets = [n.fret for n in notes if n.fret != 0]
    return sum(frets) / len(frets) if frets else None


def test_c_major_scale_stays_compact() -> None:
    pitches = [60, 62, 64, 65, 67, 69, 71, 72]
    tab, warnings = assign(make_score([[p] for p in pitches]), STANDARD_TUNING)
    assert warnings == []
    centres = [centre(s.notes) for s in tab.slots[:8]]
    known = [c for c in centres if c is not None]
    assert max(abs(a - b) for a, b in itertools.pairwise(known)) <= 4


def test_open_e_major_chord() -> None:
    tab, warnings = assign(make_score([[40, 47, 52, 56, 59, 64]]), STANDARD_TUNING)
    assert warnings == []
    by_string = {n.string: n.fret for n in tab.slots[0].notes}
    assert [by_string[s] for s in (6, 5, 4, 3, 2, 1)] == [0, 2, 2, 1, 0, 0]


def test_out_of_range_note_warned_and_slot_becomes_rest() -> None:
    tab, warnings = assign(make_score([[30], [64]]), STANDARD_TUNING)
    assert warnings == ["bỏ 1 nốt ngoài tầm cây đàn"]
    assert tab.slots[0].notes == ()
    assert (tab.slots[0].start, tab.slots[0].length) == (0, 1)
    assert tab.slots[1].notes != ()


def test_out_of_range_aggregated_in_one_warning() -> None:
    _, warnings = assign(make_score([[30], [20], [120]]), STANDARD_TUNING)
    assert warnings == ["bỏ 3 nốt ngoài tầm cây đàn"]


def test_seven_notes_reduced_to_six() -> None:
    pitches = [40, 45, 50, 55, 59, 64, 67]
    score = Score(
        RHYTHM,
        (
            Slot(0, 1, tuple(GridNote(p, 0.5 + i / 100) for i, p in enumerate(pitches))),
            Slot(1, 15),
        ),
    )
    tab, warnings = assign(score, STANDARD_TUNING)
    assert len(tab.slots[0].notes) == 6
    assert 40 not in [n.pitch for n in tab.slots[0].notes]
    assert len(warnings) == 1


def test_pair_40_41_drops_lowest_velocity() -> None:
    score = Score(RHYTHM, (Slot(0, 1, (GridNote(40, 0.9), GridNote(41, 0.2))), Slot(1, 15)))
    tab, warnings = assign(score, STANDARD_TUNING)
    assert [n.pitch for n in tab.slots[0].notes] == [40]
    assert len(warnings) == 1


def test_drop_d_lowest_string() -> None:
    tuning = parse_tuning("D A D G B E")
    assert tuning.strings == (64, 59, 55, 50, 45, 38)
    tab, _ = assign(make_score([[38]]), tuning)
    note = tab.slots[0].notes[0]
    assert (note.string, note.fret) == (6, 0)


def test_parse_tuning_standard_and_accidentals() -> None:
    assert parse_tuning("E A D G B E") == STANDARD_TUNING
    assert parse_tuning("Eb Ab Db Gb Bb Eb").strings == (63, 58, 54, 49, 44, 39)
    assert parse_tuning("D# A D G B E").strings[5] == 39


def test_parse_tuning_equidistant_takes_lower_octave() -> None:
    # Reference for string 6 is 40 (E2); A#/Bb is 6 away both ways -> 34 (lower).
    assert parse_tuning("Bb A D G B E").strings[5] == 34
    # String 1 reference 64 (E4); Bb4=70 vs Bb3=58 equidistant -> 58.
    assert parse_tuning("E A D G B Bb").strings[0] == 58


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "E A D G B",
        "E A D G B E E",
        "E A D G B H",
        "E A D G B e",
        "E A D G B E#b",
        "E A D G B B##",
    ],
)
def test_parse_tuning_invalid(bad: str) -> None:
    with pytest.raises(ValueError, match=r"tuning|tên nốt"):
        parse_tuning(bad)


def test_deterministic() -> None:
    rng = random.Random(1)
    score = make_score([rng.sample(range(40, 80), rng.randint(1, 4)) for _ in range(40)])
    assert assign(score, STANDARD_TUNING) == assign(score, STANDARD_TUNING)


@settings(max_examples=500, deadline=None)
@given(st.lists(st.lists(st.integers(30, 100), min_size=1, max_size=6), min_size=1, max_size=8))
def test_tab_notes_are_valid(slots_pitches: list[list[int]]) -> None:
    tab, _ = assign(make_score(slots_pitches), STANDARD_TUNING)
    for slot in tab.slots:
        strings = [n.string for n in slot.notes]
        assert len(set(strings)) == len(strings)
        for n in slot.notes:
            assert STANDARD_TUNING.strings[n.string - 1] + n.fret == n.pitch
            assert 0 <= n.fret <= 24


def test_custom_tuning_validity() -> None:
    tuning = Tuning((64, 59, 55, 50, 45, 38))
    tab, _ = assign(make_score([[38, 45, 50, 54, 57, 62]]), tuning)
    for n in tab.slots[0].notes:
        assert tuning.strings[n.string - 1] + n.fret == n.pitch


def test_performance_2000_slots() -> None:
    rng = random.Random(7)
    slots = []
    for _ in range(2000):
        size = rng.randint(1, 6)
        base = rng.randint(40, 64)
        slots.append(sorted({base + rng.randint(0, 24) for _ in range(size)}))
    score = make_score(slots)
    start = time.perf_counter()
    tab, _ = assign(score, STANDARD_TUNING)
    elapsed = time.perf_counter() - start
    print(f"assign 2000 slots: {elapsed:.2f}s")
    assert len(tab.slots) == len(score.slots)
    assert elapsed < 10.0


def test_max_fret_limits_frets() -> None:
    pitches = [[p] for p in (40, 45, 50, 55, 60, 64, 67)]
    tab, warnings = assign(make_score(pitches), STANDARD_TUNING, max_fret=5)
    frets = [n.fret for s in tab.slots for n in s.notes]
    assert len(frets) == len(pitches) and max(frets) <= 5
    assert warnings == []


def test_max_fret_drops_note_only_playable_above_limit() -> None:
    tab, warnings = assign(make_score([[64], [76]]), STANDARD_TUNING, max_fret=5)
    assert [len(s.notes) for s in tab.slots[:2]] == [1, 0]
    assert warnings == ["bỏ 1 nốt ngoài tầm cây đàn (phím ≤ 5)"]


def test_default_range_warning_has_no_fret_limit() -> None:
    _, warnings = assign(make_score([[30]]), STANDARD_TUNING)
    assert warnings == ["bỏ 1 nốt ngoài tầm cây đàn"]


def test_max_fret_out_of_range_rejected() -> None:
    with pytest.raises(ValueError):
        assign(make_score([[64]]), STANDARD_TUNING, max_fret=25)
