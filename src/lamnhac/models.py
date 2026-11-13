"""Shared immutable data models. Time grid unit: slot = one sixteenth note."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt

SAMPLE_RATE = 22050
MAX_DURATION_S = 600.0
Format = Literal["gp5", "musicxml"]
TempoSource = Literal["detected", "user"]


@dataclass(frozen=True)
class AudioClip:
    samples: npt.NDArray[np.float32]
    sample_rate: int
    duration_s: float
    source: Path

    def __post_init__(self) -> None:
        if self.sample_rate != SAMPLE_RATE:
            raise ValueError(f"sample_rate must be {SAMPLE_RATE}")
        if not 0 < self.duration_s <= MAX_DURATION_S:
            raise ValueError(f"duration_s must be in (0, {MAX_DURATION_S:g}]")


@dataclass(frozen=True)
class NoteEvent:
    onset_s: float
    offset_s: float
    pitch: int
    velocity: float

    def __post_init__(self) -> None:
        if not self.offset_s > self.onset_s:
            raise ValueError("offset_s must be greater than onset_s")
        if not 0 <= self.pitch <= 127:
            raise ValueError("pitch must be in 0..127")
        if not 0.0 <= self.velocity <= 1.0:
            raise ValueError("velocity must be in 0..1")


@dataclass(frozen=True)
class Tuning:
    strings: tuple[int, ...]  # MIDI; index 0 = string 1 = highest

    def __post_init__(self) -> None:
        if len(self.strings) != 6:
            raise ValueError("tuning must have exactly 6 strings")
        if any(not 0 <= s <= 127 for s in self.strings):
            raise ValueError("tuning pitches must be in 0..127")


STANDARD_TUNING = Tuning((64, 59, 55, 50, 45, 40))


@dataclass(frozen=True)
class TimeSignature:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if self.denominator not in (2, 4, 8):
            raise ValueError("denominator must be 2, 4 or 8")
        if not 1 <= self.numerator <= 16:
            raise ValueError("numerator must be in 1..16")

    @property
    def bar_slots(self) -> int:
        return self.numerator * 16 // self.denominator


@dataclass(frozen=True)
class RhythmInfo:
    tempo_bpm: float  # quarter-note BPM
    beat_times_s: tuple[float, ...]
    downbeat_slot: int  # slot of the downbeat within a bar, 0 <= slot < bar_slots
    time_signature: TimeSignature
    tempo_source: TempoSource

    def __post_init__(self) -> None:
        if not 30 <= self.tempo_bpm <= 300:
            raise ValueError("tempo_bpm must be in 30..300")
        if len(self.beat_times_s) < 2:
            raise ValueError("beat_times_s needs at least 2 entries")
        if any(b <= a for a, b in zip(self.beat_times_s, self.beat_times_s[1:], strict=False)):
            raise ValueError("beat_times_s must be strictly increasing")
        if not 0 <= self.downbeat_slot < self.time_signature.bar_slots:
            raise ValueError("downbeat_slot must be in 0..bar_slots-1")


@dataclass(frozen=True)
class GridNote:
    pitch: int
    velocity: float


@dataclass(frozen=True)
class Slot:
    start: int
    length: int
    notes: tuple[GridNote, ...] = ()  # empty = rest

    def __post_init__(self) -> None:
        if self.length < 1:
            raise ValueError("length must be >= 1")


@dataclass(frozen=True)
class Score:
    rhythm: RhythmInfo
    slots: tuple[Slot, ...]

    def __post_init__(self) -> None:
        pos = 0
        for slot in self.slots:
            if slot.start != pos:
                raise ValueError("slots must be contiguous and non-overlapping")
            pos += slot.length
        if pos % self.rhythm.time_signature.bar_slots != 0:
            raise ValueError("total length must be a multiple of bar_slots")


@dataclass(frozen=True)
class TabNote:
    pitch: int
    string: int  # 1..6
    fret: int  # 0..24

    def __post_init__(self) -> None:
        if not 1 <= self.string <= 6:
            raise ValueError("string must be in 1..6")
        if not 0 <= self.fret <= 24:
            raise ValueError("fret must be in 0..24")


@dataclass(frozen=True)
class TabSlot:
    start: int
    length: int
    notes: tuple[TabNote, ...] = ()

    def __post_init__(self) -> None:
        strings = [n.string for n in self.notes]
        if len(set(strings)) != len(strings):
            raise ValueError("a string may appear at most once per slot")


@dataclass(frozen=True)
class TabScore:
    rhythm: RhythmInfo
    tuning: Tuning
    slots: tuple[TabSlot, ...]
    title: str = ""

    def __post_init__(self) -> None:
        for slot in self.slots:
            for note in slot.notes:
                if self.tuning.strings[note.string - 1] + note.fret != note.pitch:
                    raise ValueError(
                        f"string {note.string} fret {note.fret} does not give pitch {note.pitch}"
                    )


@dataclass(frozen=True)
class ConvertOptions:
    input: Path
    out_dir: Path
    formats: frozenset[Format]
    tempo: float | None
    tuning: Tuning
    time_signature: TimeSignature
    force: bool


@dataclass(frozen=True)
class ConvertResult:
    outputs: tuple[Path, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    rhythm: RhythmInfo
    note_count: int
