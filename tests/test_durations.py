import pytest

from lamnhac.durations import split

ALLOWED = {16, 12, 8, 6, 4, 3, 2, 1}
DOTTED = {12, 6, 3}
BASE = {16: 16, 12: 8, 8: 8, 6: 4, 4: 4, 3: 2, 2: 2, 1: 1}


@pytest.mark.parametrize("bar_slots", [16, 12, 8])
def test_split_invariants_exhaustive(bar_slots: int) -> None:
    for start in range(2 * bar_slots):
        for length in range(1, 49):
            pieces = split(start, length, bar_slots)
            assert sum(d for d, _ in pieces) == length
            assert [t for _, t in pieces] == [True] * (len(pieces) - 1) + [False]
            pos = start
            for d, _ in pieces:
                assert d in ALLOWED
                in_bar = pos % bar_slots
                assert in_bar + d <= bar_slots  # no bar line crossed
                assert in_bar % BASE[d] == 0
                pos += d
                if d in DOTTED:  # last piece of its bar segment
                    assert pos == start + length or pos % bar_slots == 0


def test_whole_bar_44() -> None:
    assert split(0, 16, 16) == [(16, False)]


def test_dotted_half_fills_34_bar() -> None:
    assert split(0, 12, 12) == [(12, False)]


def test_crosses_bar_line() -> None:
    assert split(14, 4, 16) == [(2, True), (2, False)]


def test_single_slot() -> None:
    assert split(5, 1, 16) == [(1, False)]


@pytest.mark.parametrize(
    ("start", "length", "bar_slots", "expected"),
    [
        (2, 6, 16, [(2, True), (4, False)]),
        (4, 8, 16, [(4, True), (4, False)]),
        (0, 7, 16, [(4, True), (3, False)]),
        (0, 6, 16, [(6, False)]),
        (0, 12, 12, [(12, False)]),
        (0, 12, 16, [(12, False)]),
    ],
)
def test_dotted_only_when_filling_segment(
    start: int, length: int, bar_slots: int, expected: list[tuple[int, bool]]
) -> None:
    assert split(start, length, bar_slots) == expected


@pytest.mark.parametrize(
    ("start", "length", "bar_slots"),
    [(-1, 4, 16), (0, 0, 16), (0, -3, 16), (0, 4, 0)],
)
def test_invalid_input(start: int, length: int, bar_slots: int) -> None:
    with pytest.raises(ValueError):
        split(start, length, bar_slots)
