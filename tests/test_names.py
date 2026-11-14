import pytest

from lamnhac.models import NO_CHORD, ChordLabel, MusicKey
from lamnhac.names import chord_name, chord_sharp, key_name, note_name

C_MAJOR = MusicKey(0, False)
A_MINOR = MusicKey(9, True)
F_MAJOR = MusicKey(5, False)
D_MINOR = MusicKey(2, True)
G_MAJOR = MusicKey(7, False)


@pytest.mark.parametrize(
    ("pc", "key", "expected"),
    [
        (10, C_MAJOR, "Bb"),
        (3, C_MAJOR, "Eb"),
        (8, A_MINOR, "Ab"),
        (6, C_MAJOR, "F#"),
        (1, C_MAJOR, "C#"),
        (10, F_MAJOR, "Bb"),
        (10, D_MINOR, "Bb"),
        (6, G_MAJOR, "F#"),
    ],
)
def test_note_name(pc: int, key: MusicKey, expected: str) -> None:
    assert note_name(pc, key) == expected


def test_no_sharp_in_flat_keys() -> None:
    for key in (F_MAJOR, D_MINOR, MusicKey(10, False), MusicKey(3, True)):
        assert all("#" not in note_name(pc, key) for pc in range(12))


def test_chord_name_minor_and_no_chord() -> None:
    assert chord_name(ChordLabel(9, True), C_MAJOR) == "Am"
    assert chord_name(NO_CHORD, C_MAJOR) == "N"


def test_chord_name_with_capo_uses_shifted_key() -> None:
    assert chord_name(ChordLabel(0, False), C_MAJOR, capo=3) == "A"
    assert chord_name(ChordLabel(3, False), C_MAJOR, capo=3) == "C"
    # Bb major shifted by 2 is Ab major: flats
    assert chord_name(ChordLabel(10, False), MusicKey(10, False), capo=2) == "Ab"


def test_chord_sharp() -> None:
    assert chord_sharp(ChordLabel(6, False), C_MAJOR)
    assert not chord_sharp(ChordLabel(10, False), C_MAJOR)
    assert not chord_sharp(NO_CHORD, C_MAJOR)


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (A_MINOR, "La thứ (Am)"),
        (MusicKey(10, False), "Si giáng trưởng (Bb)"),
        (MusicKey(6, True), "Fa thăng thứ (F#m)"),
        (C_MAJOR, "Đô trưởng (C)"),
        (MusicKey(3, True), "Mi giáng thứ (Ebm)"),
    ],
)
def test_key_name(key: MusicKey, expected: str) -> None:
    assert key_name(key) == expected
