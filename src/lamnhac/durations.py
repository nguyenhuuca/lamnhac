"""Split a span on the slot grid into notatable durations (spec B16).

Time grid unit: slot = one sixteenth note.
"""

_DURATIONS = (16, 12, 8, 6, 4, 3, 2, 1)
_DOTTED = frozenset({12, 6, 3})
_BASE = {16: 16, 12: 8, 8: 8, 6: 4, 4: 4, 3: 2, 2: 2, 1: 1}


def split(start: int, length: int, bar_slots: int) -> list[tuple[int, bool]]:
    """Split ``length`` slots beginning at ``start`` into ``(duration, tied_to_next)``.

    ``start`` counts slots from the beginning of bar 1. The span is first cut at
    bar lines; inside each bar, pieces are chosen greedily from the current
    position: the largest duration that fits in what remains of the segment and
    starts on a multiple of its base duration (position measured within the bar).
    A dotted duration (12, 6, 3) is chosen only when it equals the remaining
    length of the segment exactly (end of the note or bar line).
    Every piece except the last has ``tied_to_next=True``. Rests use the same
    function and ignore the tie flag.

    Raises ValueError if ``start < 0``, ``length < 1`` or ``bar_slots < 1``.
    """
    if start < 0 or length < 1 or bar_slots < 1:
        raise ValueError("start must be >= 0, length and bar_slots must be >= 1")
    pieces: list[int] = []
    pos = start
    end = start + length
    while pos < end:
        in_bar = pos % bar_slots
        segment_end = min(end, pos + bar_slots - in_bar)
        while pos < segment_end:
            in_bar = pos % bar_slots
            remaining = segment_end - pos
            d = next(
                d
                for d in _DURATIONS
                if d <= remaining
                and in_bar % _BASE[d] == 0
                and (d not in _DOTTED or d == remaining)
            )
            pieces.append(d)
            pos += d
    return [(d, i < len(pieces) - 1) for i, d in enumerate(pieces)]
