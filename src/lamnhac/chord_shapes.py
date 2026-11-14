"""Guitar chord shapes for standard tuning (spec C15)."""

from lamnhac.models import ChordShape

_OPEN: dict[tuple[int, bool], tuple[int, ...]] = {
    (0, False): (-1, 3, 2, 0, 1, 0),
    (2, False): (-1, -1, 0, 2, 3, 2),
    (4, False): (0, 2, 2, 1, 0, 0),
    (7, False): (3, 2, 0, 0, 0, 3),
    (9, False): (-1, 0, 2, 2, 2, 0),
    (9, True): (-1, 0, 2, 2, 1, 0),
    (2, True): (-1, -1, 0, 2, 3, 1),
    (4, True): (0, 2, 2, 0, 0, 0),
}
_LOW_E = 4  # pitch class of string 6
_A = 9  # pitch class of string 5
_MAX_FRET_FOR_FIRST_1 = 4


def _barre(b: int, string6: bool, minor: bool) -> tuple[int, ...]:
    if string6:
        return (b, b + 2, b + 2, b if minor else b + 1, b, b)
    return (-1, b, b + 2, b + 2, b + 1 if minor else b + 2, b)


def _lowest_barre(root: int) -> int:
    # fret 0 would be an open string, so the barre sits at 12 instead
    return ((root - _LOW_E) % 12) or 12


def shape(root: int, minor: bool) -> ChordShape:
    if not 0 <= root <= 11:
        raise ValueError("root must be in 0..11")
    frets = _OPEN.get((root, minor))
    if frets is None:
        e_fret = _lowest_barre(root)
        a_fret = ((root - _A) % 12) or 12
        frets = _barre(e_fret, True, minor) if e_fret <= a_fret else _barre(a_fret, False, minor)
    first = 1 if max(frets) <= _MAX_FRET_FOR_FIRST_1 else min(f for f in frets if f > 0)
    return ChordShape(frets, first)
