from pathlib import Path
from typing import Any

import numpy as np
import pytest

from lamnhac.errors import (
    InputError,
    LamnhacError,
    OutputError,
    ProcessingError,
    UsageError,
)
from lamnhac.models import (
    STANDARD_TUNING,
    AudioClip,
    NoteEvent,
    RhythmInfo,
    Score,
    Slot,
    TabNote,
    TabScore,
    TabSlot,
    TimeSignature,
    Tuning,
)

TS44 = TimeSignature(4, 4)


def rhythm(**kw: Any) -> RhythmInfo:
    args: dict[str, Any] = {
        "tempo_bpm": 120.0,
        "beat_times_s": (0.0, 0.5, 1.0),
        "downbeat_index": 0,
        "time_signature": TS44,
        "tempo_source": "user",
    }
    args.update(kw)
    return RhythmInfo(**args)


def clip(sr: int = 22050, dur: float = 1.0) -> AudioClip:
    return AudioClip(np.zeros(10, dtype=np.float32), sr, dur, Path("a.mp3"))


def test_audio_clip() -> None:
    assert clip().duration_s == 1.0
    assert clip(dur=600).duration_s == 600
    for bad in ({"sr": 44100}, {"dur": 0}, {"dur": 601}):
        with pytest.raises(ValueError, match="must be"):
            clip(**bad)


def test_note_event() -> None:
    NoteEvent(0.0, 0.1, 0, 0.0)
    NoteEvent(0.0, 0.1, 127, 1.0)
    for args in ((0.1, 0.1, 60, 0.5), (0, 1, -1, 0.5), (0, 1, 128, 0.5), (0, 1, 60, 1.1)):
        with pytest.raises(ValueError, match="must be"):
            NoteEvent(*args)


def test_tuning() -> None:
    assert STANDARD_TUNING.strings == (64, 59, 55, 50, 45, 40)
    with pytest.raises(ValueError, match="6 strings"):
        Tuning((64, 59, 55, 50, 45))


@pytest.mark.parametrize(("n", "d", "slots"), [(6, 8, 12), (3, 4, 12), (4, 4, 16), (2, 2, 16)])
def test_bar_slots(n: int, d: int, slots: int) -> None:
    assert TimeSignature(n, d).bar_slots == slots


@pytest.mark.parametrize(("n", "d"), [(4, 3), (0, 4), (17, 4)])
def test_time_signature_invalid(n: int, d: int) -> None:
    with pytest.raises(ValueError, match="must be"):
        TimeSignature(n, d)


def test_rhythm_info() -> None:
    assert rhythm().tempo_bpm == 120.0
    for kw in (
        {"tempo_bpm": 29.0},
        {"tempo_bpm": 301.0},
        {"beat_times_s": (0.0,)},
        {"beat_times_s": (0.0, 0.5, 0.5)},
        {"downbeat_index": -1},
    ):
        with pytest.raises(ValueError, match=r"must|needs"):
            rhythm(**kw)


def test_slot_and_score() -> None:
    with pytest.raises(ValueError, match="length"):
        Slot(0, 0)
    Score(rhythm(), (Slot(0, 10), Slot(10, 6)))
    with pytest.raises(ValueError, match="multiple"):
        Score(rhythm(), (Slot(0, 10),))
    with pytest.raises(ValueError, match="contiguous"):
        Score(rhythm(), (Slot(0, 8), Slot(9, 7)))


def test_tab_note_and_slot() -> None:
    TabNote(64, 1, 0)
    for args in ((64, 0, 0), (64, 7, 0), (64, 1, -1), (90, 1, 25)):
        with pytest.raises(ValueError, match="must be"):
            TabNote(*args)
    with pytest.raises(ValueError, match="at most once"):
        TabSlot(0, 1, (TabNote(64, 1, 0), TabNote(65, 1, 1)))


def test_tab_score_pitch_rule() -> None:
    ok = TabSlot(0, 16, (TabNote(69, 1, 5),))
    TabScore(rhythm(), STANDARD_TUNING, (ok,), "t")
    bad = TabSlot(0, 16, (TabNote(69, 1, 6),))
    with pytest.raises(ValueError, match="does not give pitch"):
        TabScore(rhythm(), STANDARD_TUNING, (bad,), "t")


def test_exit_codes() -> None:
    assert LamnhacError.exit_code == 1
    assert [c.exit_code for c in (UsageError, InputError, ProcessingError, OutputError)] == [
        2,
        3,
        4,
        5,
    ]
    assert issubclass(OutputError, LamnhacError)
