"""Guitar tab assignment: choose string/fret per note with a beam search (B11-B13)."""

import re
from dataclasses import dataclass

from lamnhac.models import (
    GridNote,
    Score,
    Slot,
    TabNote,
    TabScore,
    TabSlot,
    Tuning,
)

MAX_FRET = 24
MAX_SPAN = 4
BEAM_WIDTH = 64
HIGH_FRET_WEIGHT = 0.3

_NAME_RE = re.compile(r"^[A-G][#b]?$")
_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_STANDARD_HIGH_TO_LOW = (64, 59, 55, 50, 45, 40)

# A fingering is a tuple of (string index 0..5, fret), sorted by string.
Fingering = tuple[tuple[int, int], ...]
Key = tuple[tuple[int, int], ...]


def parse_tuning(names: str) -> Tuning:
    """Parse 6 note names written low to high (e.g. "D A D G B E") into a Tuning."""
    parts = names.split()
    if len(parts) != 6:
        raise ValueError(f"tuning cần đúng 6 tên nốt, nhận được {len(parts)}: {names!r}")
    for part in parts:
        if not _NAME_RE.match(part):
            raise ValueError(f"tên nốt không hợp lệ: {part!r} (cần dạng A-G, tùy chọn # hoặc b)")
    strings: list[int] = []
    for name, ref in zip(reversed(parts), _STANDARD_HIGH_TO_LOW, strict=True):
        pc = _PITCH_CLASS[name[0]]
        if len(name) == 2:
            pc += 1 if name[1] == "#" else -1
        delta = (pc - ref) % 12
        if delta >= 6:  # 6 is equidistant: take the lower octave
            delta -= 12
        strings.append(ref + delta)
    return Tuning(tuple(strings))


def _assignments(pitches: list[int], tuning: tuple[int, ...]) -> list[Fingering]:
    """All ways to give each pitch a distinct string, as (string, fret) sorted by string."""
    options = [
        [(s, p - t) for s, t in enumerate(tuning) if 0 <= p - t <= MAX_FRET] for p in pitches
    ]
    results: list[Fingering] = []

    def rec(i: int, used: int, acc: list[tuple[int, int]]) -> None:
        if i == len(options):
            results.append(tuple(sorted(acc)))
            return
        for s, f in options[i]:
            if not used >> s & 1:
                acc.append((s, f))
                rec(i + 1, used | 1 << s, acc)
                acc.pop()

    rec(0, 0, [])
    return results


def _span(f: Fingering) -> int:
    frets = [fr for _, fr in f if fr != 0]
    return max(frets) - min(frets) if frets else 0


def _centre(f: Fingering) -> float | None:
    frets = [fr for _, fr in f if fr != 0]
    return sum(frets) / len(frets) if frets else None


def _state_cost(f: Fingering) -> float:
    return _span(f) + HIGH_FRET_WEIGHT * sum(max(0, fr - 12) for _, fr in f)


def _key(f: Fingering) -> Key:
    return tuple((s + 1, fr) for s, fr in f)


@dataclass
class _Prepared:
    notes: list[GridNote]  # kept notes; empty means the slot is a rest
    states: list[Fingering]


def _prepare(slot: Slot, tuning: tuple[int, ...], counts: dict[str, int]) -> _Prepared:
    notes: list[GridNote] = []
    for n in slot.notes:
        if any(0 <= n.pitch - t <= MAX_FRET for t in tuning):
            notes.append(n)
        else:
            counts["range"] += 1
    notes.sort(key=lambda n: (n.pitch, n.velocity))

    def drop_lowest() -> None:
        victim = min(notes, key=lambda n: (n.velocity, n.pitch))
        notes.remove(victim)
        counts["unassignable"] += 1

    while len(notes) > 6:
        drop_lowest()
    while notes:
        fingerings = _assignments([n.pitch for n in notes], tuning)
        if fingerings:
            compact = [f for f in fingerings if _span(f) <= MAX_SPAN]
            if compact:
                return _Prepared(notes, compact)
            best = min(_span(f) for f in fingerings)
            counts["span"] += 1
            return _Prepared(notes, [f for f in fingerings if _span(f) == best])
        drop_lowest()
    return _Prepared([], [])


@dataclass
class _Path:
    cost: float
    fret_sum: int
    key: Key
    state: Fingering
    prev: "_Path | None"

    def order(self) -> tuple[float, int, Key]:
        return (self.cost, self.fret_sum, self.key)


def _beam_search(slots: list[list[Fingering]]) -> list[Fingering]:
    beam: list[_Path] = []
    for index, states in enumerate(slots):
        # Transition cost depends only on the previous centre: keep the best path per centre.
        by_centre: dict[float | None, _Path] = {}
        for p in beam:
            c = _centre(p.state)
            cur = by_centre.get(c)
            if cur is None or p.order() < cur.order():
                by_centre[c] = p
        new_beam: list[_Path] = []
        for st in states:
            own = _state_cost(st)
            fsum = sum(fr for _, fr in st)
            if index == 0:
                new_beam.append(_Path(own, fsum, _key(st), st, None))
                continue
            centre = _centre(st)
            best: _Path | None = None
            best_order: tuple[float, int, Key] = (0.0, 0, ())
            for c, p in by_centre.items():
                trans = 0.0 if c is None or centre is None else abs(c - centre)
                cand = (p.cost + trans, p.fret_sum, p.key)
                if best is None or cand < best_order:
                    best, best_order = p, cand
            if best is None:
                continue
            new_beam.append(_Path(best_order[0] + own, best.fret_sum + fsum, _key(st), st, best))
        new_beam.sort(key=_Path.order)
        beam = new_beam[:BEAM_WIDTH]
    if not beam:
        return []
    node: _Path | None = min(beam, key=_Path.order)
    out: list[Fingering] = []
    while node is not None:
        out.append(node.state)
        node = node.prev
    out.reverse()
    return out


def assign(score: Score, tuning: Tuning, title: str = "") -> tuple[TabScore, list[str]]:
    """Assign string and fret to every note. Returns the tab and Vietnamese warnings."""
    t = tuning.strings
    counts = {"range": 0, "unassignable": 0, "span": 0}
    prepared = [_prepare(s, t, counts) for s in score.slots]
    chosen = _beam_search([p.states for p in prepared if p.notes])

    out: list[TabSlot] = []
    it = iter(chosen)
    for slot, prep in zip(score.slots, prepared, strict=True):
        if not prep.notes:
            out.append(TabSlot(slot.start, slot.length))
            continue
        tab_notes = tuple(TabNote(t[s] + fr, s + 1, fr) for s, fr in next(it))
        out.append(TabSlot(slot.start, slot.length, tab_notes))

    warnings: list[str] = []
    if counts["range"]:
        warnings.append(f"bỏ {counts['range']} nốt ngoài tầm cây đàn")
    if counts["unassignable"]:
        warnings.append(
            f"bỏ {counts['unassignable']} nốt không thể gán dây khác nhau trong cùng slot"
        )
    if counts["span"]:
        warnings.append(f"{counts['span']} slot có độ trải phím lớn hơn {MAX_SPAN}")
    return TabScore(score.rhythm, tuning, tuple(out), title), warnings
