"""Pitch spelling, chord names and Vietnamese key names (spec C13, C13a, C14)."""

from lamnhac.models import ChordLabel, MusicKey

# major tonic pitch class -> sharps (+) / flats (-); pc 6 is F# (6 sharps)
_MAJOR_FIFTHS = (0, -5, 2, -3, 4, -1, 6, 1, -4, 3, -2, 5)
_NAMES_FLAT = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
_NAMES_SHARP = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_MAJOR = frozenset({5, 10, 3, 8, 1})  # F Bb Eb Ab Db (Gb major is written F#)
_FLAT_MINOR = frozenset({2, 7, 0, 5, 10, 3})  # D G C F Bb Eb
_VI_LETTER = {"C": "Đô", "D": "Rê", "E": "Mi", "F": "Fa", "G": "Sol", "A": "La", "B": "Si"}


def uses_flats(key: MusicKey) -> bool:
    """True when the key is written with flats (C13)."""
    return key.tonic in (_FLAT_MINOR if key.minor else _FLAT_MAJOR)


def _is_plain(key: MusicKey) -> bool:
    return (key.tonic, key.minor) in ((0, False), (9, True))


def note_name(pc: int, key: MusicKey) -> str:
    """Spell pitch class ``pc`` for ``key``: flats in flat keys, sharps otherwise (C13)."""
    pc %= 12
    if uses_flats(key):
        return _NAMES_FLAT[pc]
    if _is_plain(key) and pc in (3, 8, 10):
        return _NAMES_FLAT[pc]
    return _NAMES_SHARP[pc]


def _shifted(key: MusicKey, capo: int) -> MusicKey:
    return MusicKey((key.tonic - capo) % 12, key.minor)


def chord_name(label: ChordLabel, key: MusicKey, capo: int = 0) -> str:
    """Chord name; with a capo, the shape's name from the key lowered by ``capo`` (C13, C14)."""
    if label.root is None:
        return "N"
    shape_key = _shifted(key, capo) if capo > 0 else key
    root = (label.root - capo) % 12 if capo > 0 else label.root
    return note_name(root, shape_key) + ("m" if label.minor else "")


def chord_sharp(label: ChordLabel, key: MusicKey, capo: int = 0) -> bool:
    """Whether the spelled chord name uses a sharp."""
    return "#" in chord_name(label, key, capo)


def key_symbol(key: MusicKey) -> str:
    """ASCII key symbol such as ``Am``, ``Bb``, ``F#m``."""
    names = _NAMES_FLAT if uses_flats(key) else _NAMES_SHARP
    return names[key.tonic] + ("m" if key.minor else "")


def key_fifths(key: MusicKey) -> int:
    """Signed number of sharps (+) or flats (-) of the key signature, -7..7."""
    if not key.minor:
        return _MAJOR_FIFTHS[key.tonic]
    if key.tonic == 3:  # Eb minor: 6 flats (relative major Gb)
        return -6
    return _MAJOR_FIFTHS[(key.tonic + 3) % 12]


def key_name(key: MusicKey) -> str:
    """Vietnamese key name with symbol, e.g. ``La thứ (Am)`` (C13a)."""
    symbol = key_symbol(key)
    tonic = symbol.removesuffix("m") if key.minor else symbol
    name = _VI_LETTER[tonic[0]]
    if tonic.endswith("#"):
        name += " thăng"
    elif tonic.endswith("b"):
        name += " giáng"
    return f"{name} {'thứ' if key.minor else 'trưởng'} ({symbol})"
