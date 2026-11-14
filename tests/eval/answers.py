"""Answer-file parser and metrics for the chord eval (spec C20, C21)."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

Chord = tuple[int, bool]  # (pitch class 0..11, minor)

_TOKEN = re.compile(r"^([A-G][#b]?)(.*)$")
_ROOTS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_IGNORED_SUFFIXES = ("7", "maj7", "m7", "sus2", "sus4", "add9", "6", "9")
_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_MAX_SKIPPED_RATIO = 0.20
_KEY_LINE = re.compile(r"^#\s*key\s*:\s*(\S+)\s*$", re.IGNORECASE)


def parse_token(tok: str) -> Chord | None:
    """Reduce a chord symbol to (pitch class, minor); None if it is not a chord."""
    m = _TOKEN.match(tok)
    if m is None:
        return None
    root, suffix = m.group(1), m.group(2)
    pc = _ROOTS[root[0]]
    if len(root) == 2:
        pc += 1 if root[1] == "#" else -1
    pc %= 12
    suffix = suffix.split("/", 1)[0]
    if suffix.startswith("dim"):
        return pc, True
    if suffix.startswith("aug"):
        return pc, False
    minor = suffix.startswith("m") and not suffix.startswith("maj")
    rest = suffix[1:] if minor else suffix
    if rest.startswith("maj"):
        rest = rest[3:]
    if rest == "" or rest in _IGNORED_SUFFIXES:
        return pc, minor
    return None


@dataclass(frozen=True)
class Answer:
    chords: tuple[Chord, ...]
    key: Chord | None
    skipped: int
    total: int


def parse_answer(text: str) -> Answer:
    chords: list[Chord] = []
    key: Chord | None = None
    skipped = 0
    total = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            km = _KEY_LINE.match(stripped)
            if km is not None:
                key = parse_token(km.group(1))
            continue
        for tok in stripped.replace("|", " ").split():
            total += 1
            chord = parse_token(tok)
            if chord is None:
                skipped += 1
            else:
                chords.append(chord)
    if total and skipped / total > _MAX_SKIPPED_RATIO:
        raise ValueError(
            f"answer file unreadable: {skipped} of {total} tokens are not chords (limit 20%)"
        )
    if not chords:
        raise ValueError("answer file has no chords")
    return Answer(tuple(chords), key, skipped, total)


def collapse(seq: Sequence[Chord | None]) -> list[Chord]:
    out: list[Chord] = []
    for c in seq:
        if c is None:
            continue
        if not out or out[-1] != c:
            out.append(c)
    return out


def levenshtein(a: Sequence[Chord], b: Sequence[Chord]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def accuracy(ref: Sequence[Chord | None], est: Sequence[Chord | None]) -> float:
    r = collapse(ref)
    if not r:
        return 0.0
    return max(0.0, 1 - levenshtein(r, collapse(est)) / len(r))


def accuracy_transposed(ref: Sequence[Chord | None], est: Sequence[Chord | None]) -> float:
    r = collapse(ref)
    return max(accuracy([((pc + s) % 12, mn) for pc, mn in r], est) for s in range(12))


def chord_name(c: Chord) -> str:
    return _NAMES[c[0]] + ("m" if c[1] else "")
