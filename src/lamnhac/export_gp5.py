"""Write a TabScore as a Guitar Pro 5 file (spec B15, B16, B17)."""

import os
import unicodedata
from collections.abc import Mapping
from pathlib import Path

import guitarpro
from guitarpro import models as gp

from lamnhac.durations import split
from lamnhac.errors import OutputError
from lamnhac.models import ChordDiagram, MusicKey, TabScore, TabSlot

_TITLE_MAX = 64
_TICKS_PER_SLOT = 240  # PyGuitarPro: quarter = 960 ticks, slot = sixteenth
_GUITAR_PROGRAM = 25
# slots -> (Duration.value, isDotted)
_DURATION = {
    16: (1, False),
    12: (2, True),
    8: (2, False),
    6: (4, True),
    4: (4, False),
    3: (8, True),
    2: (8, False),
    1: (16, False),
}
# major tonic pitch class -> sharps (+) / flats (-); pc 6 is F# (6 sharps)
_MAJOR_FIFTHS = (0, -5, 2, -3, 4, -1, 6, 1, -4, 3, -2, 5)
_NAMES_FLAT = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
_NAMES_SHARP = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_MAJOR = frozenset({5, 10, 3, 8, 1})  # F Bb Eb Ab Db (Gb major is written F#)
_FLAT_MINOR = frozenset({2, 7, 0, 5, 10, 3})  # D G C F Bb Eb


def key_symbol(key: MusicKey) -> str:
    """ASCII key symbol such as ``Am``, ``Bb``, ``F#m``."""
    flat = key.tonic in (_FLAT_MINOR if key.minor else _FLAT_MAJOR)
    names = _NAMES_FLAT if flat else _NAMES_SHARP
    return names[key.tonic] + ("m" if key.minor else "")


def key_fifths(key: MusicKey) -> int:
    """Signed number of sharps (+) or flats (-) of the key signature, -7..7."""
    if not key.minor:
        return _MAJOR_FIFTHS[key.tonic]
    if key.tonic == 3:  # Eb minor: 6 flats (relative major Gb)
        return -6
    return _MAJOR_FIFTHS[(key.tonic + 3) % 12]


def _key_signature(key: MusicKey) -> gp.KeySignature:
    # Look up by value: member names are misleading (GMajorFlat is Gb major).
    wanted = (key_fifths(key), int(key.minor))
    for member in gp.KeySignature:
        if member.value == wanted:
            return member
    raise ValueError(f"no key signature for {wanted}")


def ascii_title(s: str) -> str:
    """Fold ``s`` to printable ASCII (GP5 cannot store Vietnamese in cp1252), max 64 chars."""
    s = s.replace("đ", "d").replace("Đ", "D")
    out: list[str] = []
    for ch in unicodedata.normalize("NFKD", s):
        if unicodedata.combining(ch):
            continue
        out.append(ch if " " <= ch <= "~" else "_")
    return "".join(out)[:_TITLE_MAX]


def write(
    tab: TabScore,
    path: Path,
    diagrams: Mapping[int, ChordDiagram] | None = None,
    key: MusicKey | None = None,
    capo: int = 0,
) -> None:
    """Write ``tab`` to ``path`` atomically; any failure becomes ``OutputError``.

    ``diagrams`` (slot start -> chord diagram), ``key`` and ``capo`` are optional
    chord-chart extras (spec C14, C17, C17a); without them the output is unchanged.
    """
    tmp = path.with_name(f"{path.stem}.tmp-{os.getpid()}.gp5")
    try:
        guitarpro.write(_build(tab, diagrams, key, capo), str(tmp), version=(5, 1, 0))
        os.replace(tmp, path)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise OutputError(f"cannot write GP5: {exc}") from exc


def _build(
    tab: TabScore,
    diagrams: Mapping[int, ChordDiagram] | None = None,
    key: MusicKey | None = None,
    capo: int = 0,
) -> gp.Song:
    ts = tab.rhythm.time_signature
    bar_slots = ts.bar_slots
    total = max((s.start + s.length for s in tab.slots), default=0)
    bars = max(1, -(-total // bar_slots))

    song = gp.Song(title=ascii_title(tab.title), tempo=round(tab.rhythm.tempo_bpm))
    if key is not None:
        song.subtitle = f"Key: {key_symbol(key)}" + (f" (capo {capo})" if capo > 0 else "")
    song.measureHeaders = []
    song.tracks = []
    for i in range(bars):
        song.addMeasureHeader(
            gp.MeasureHeader(
                number=i + 1,
                start=gp.Duration.quarterTime + i * bar_slots * _TICKS_PER_SLOT,
                timeSignature=gp.TimeSignature(
                    numerator=ts.numerator, denominator=gp.Duration(value=ts.denominator)
                ),
            )
        )
        if key is not None:
            song.measureHeaders[-1].keySignature = _key_signature(key)

    track = gp.Track(song, number=1, name="Guitar")
    track.channel = gp.MidiChannel(channel=0, effectChannel=1, instrument=_GUITAR_PROGRAM)
    track.strings = [gp.GuitarString(i + 1, midi) for i, midi in enumerate(tab.tuning.strings)]
    track.fretCount = 24
    track.measures = [gp.Measure(track, h) for h in song.measureHeaders]
    song.tracks.append(track)

    pos = 0  # next free slot; every gap is filled so each voice is complete
    for slot in tab.slots:
        if slot.start > pos:
            _place(track, TabSlot(pos, slot.start - pos), bar_slots)
        _place(track, slot, bar_slots, (diagrams or {}).get(slot.start))
        pos = slot.start + slot.length
    if pos < bars * bar_slots:
        _place(track, TabSlot(pos, bars * bar_slots - pos), bar_slots)
    if capo > 0:
        track.measures[0].voices[0].beats[0].text = f"Capo {capo}"
    return song


def _chord(diagram: ChordDiagram) -> gp.Chord:
    label, shape = diagram.label, diagram.shape
    assert label.root is not None  # guaranteed by ChordDiagram
    intonation = "sharp" if diagram.sharp else "flat"
    return gp.Chord(
        length=7,
        name=diagram.name,
        show=True,
        root=gp.PitchClass(label.root, intonation=intonation),
        bass=gp.PitchClass(label.root, intonation=intonation),
        type=gp.ChordType.minor if label.minor else gp.ChordType.major,
        sharp=diagram.sharp,
        strings=[*reversed(shape.frets), -1],
        firstFret=shape.first_fret,
        newFormat=True,
    )


def _place(
    track: gp.Track, slot: TabSlot, bar_slots: int, diagram: ChordDiagram | None = None
) -> None:
    pos = slot.start
    for dur, _tied_next in split(slot.start, slot.length, bar_slots):
        measure = track.measures[pos // bar_slots]
        voice = measure.voices[0]
        value, dotted = _DURATION[dur]
        beat = gp.Beat(
            voice,
            start=measure.header.start + (pos % bar_slots) * _TICKS_PER_SLOT,
            duration=gp.Duration(value=value, isDotted=dotted),
        )
        if slot.notes:
            beat.status = gp.BeatStatus.normal
            kind = gp.NoteType.normal if pos == slot.start else gp.NoteType.tie
            for tn in slot.notes:
                beat.notes.append(
                    gp.Note(
                        beat,
                        value=tn.fret,
                        string=tn.string,
                        type=kind,
                        velocity=gp.Velocities.forte,
                    )
                )
        else:
            beat.status = gp.BeatStatus.rest
        if diagram is not None and pos == slot.start:
            beat.effect.chord = _chord(diagram)
        voice.beats.append(beat)
        pos += dur
