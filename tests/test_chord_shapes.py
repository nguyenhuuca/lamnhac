import pytest

from lamnhac.chord_shapes import shape

STRINGS = (40, 45, 50, 55, 59, 64)  # string 6 -> string 1
OPEN = {
    (0, False): [-1, 3, 2, 0, 1, 0],
    (2, False): [-1, -1, 0, 2, 3, 2],
    (4, False): [0, 2, 2, 1, 0, 0],
    (7, False): [3, 2, 0, 0, 0, 3],
    (9, False): [-1, 0, 2, 2, 2, 0],
    (9, True): [-1, 0, 2, 2, 1, 0],
    (2, True): [-1, -1, 0, 2, 3, 1],
    (4, True): [0, 2, 2, 0, 0, 0],
}
ALL = [(r, m) for r in range(12) for m in (False, True)]


@pytest.mark.parametrize(("root", "minor"), ALL)
def test_shape_sounds_exactly_the_chord_tones(root: int, minor: bool) -> None:
    s = shape(root, minor)
    third = 3 if minor else 4
    expected = {root % 12, (root + third) % 12, (root + 7) % 12}
    sounding = {(p + f) % 12 for p, f in zip(STRINGS, s.frets, strict=True) if f >= 0}
    assert sounding == expected


@pytest.mark.parametrize(("root", "minor"), ALL)
def test_shape_span_within_four_frets(root: int, minor: bool) -> None:
    fretted = [f for f in shape(root, minor).frets if f > 0]
    assert max(fretted) - min(fretted) <= 4


@pytest.mark.parametrize(("key", "frets"), list(OPEN.items()))
def test_open_shapes_match_table(key: tuple[int, bool], frets: list[int]) -> None:
    assert list(shape(*key).frets) == frets


def test_first_fret() -> None:
    assert shape(7, False).first_fret == 1
    f = shape(5, False)
    assert list(f.frets) == [1, 3, 3, 2, 1, 1]
    assert f.first_fret == 1
    bm = shape(11, True)
    assert list(bm.frets) == [-1, 2, 4, 4, 3, 2]
    assert bm.first_fret == 1  # max fret 4 -> C15 rule gives 1
    assert shape(1, False).first_fret == 4  # C#: A-shape at fret 4, max 6


def test_invalid_root_raises() -> None:
    with pytest.raises(ValueError):
        shape(12, False)
