"""Write a TabScore as MusicXML with a 6-line tab staff (spec B15, B16, B18)."""

import os
import xml.etree.ElementTree as ET
from pathlib import Path

from music21 import (
    articulations,
    chord,
    clef,
    layout,
    metadata,
    meter,
    note,
    pitch,
    stream,
    tempo,
    tie,
)

from lamnhac.durations import split
from lamnhac.errors import OutputError
from lamnhac.models import TabScore, TabSlot, Tuning


def write(tab: TabScore, path: Path) -> None:
    """Write ``tab`` to ``path`` atomically; any failure becomes ``OutputError``."""
    tmp = path.with_name(f"{path.stem}.tmp-{os.getpid()}.musicxml")
    try:
        score = _build(tab)
        score.write("musicxml", fp=str(tmp))
        _postprocess(tmp, tab)
        os.replace(tmp, path)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise OutputError(f"cannot write MusicXML: {exc}") from exc


def _build(tab: TabScore) -> stream.Score:
    ts = tab.rhythm.time_signature
    bar_slots = ts.bar_slots
    part = stream.Part()
    measures: dict[int, stream.Measure] = {}

    def measure_at(index: int) -> stream.Measure:
        if index not in measures:
            m = stream.Measure(number=index + 1)
            measures[index] = m
            part.append(m)
        return measures[index]

    for slot in tab.slots:
        pos = slot.start
        for dur, tied_next in split(slot.start, slot.length, bar_slots):
            measure_at(pos // bar_slots).append(
                _element(slot, dur, tied_next, first=pos == slot.start)
            )
            pos += dur

    first = measure_at(0)
    first.insert(0, clef.TabClef())
    first.insert(0, layout.StaffLayout(staffLines=6))
    first.insert(0, meter.TimeSignature(f"{ts.numerator}/{ts.denominator}"))
    first.insert(0, tempo.MetronomeMark(number=round(tab.rhythm.tempo_bpm)))

    score = stream.Score()
    md = metadata.Metadata()
    md.title = tab.title
    score.insert(0, md)
    score.insert(0, part)
    return score


def _element(slot: TabSlot, dur: int, tied_next: bool, first: bool) -> note.GeneralNote:
    ql = dur / 4
    if not slot.notes:
        return note.Rest(quarterLength=ql)
    notes = []
    for tn in slot.notes:
        n = note.Note(midi=tn.pitch, quarterLength=ql)
        n.articulations.append(articulations.StringIndication(tn.string))
        n.articulations.append(articulations.FretIndication(tn.fret))
        notes.append(n)
    el: note.GeneralNote
    if len(notes) == 1:
        el = notes[0]
    else:
        el = chord.Chord(notes)
        el.quarterLength = ql
    if tied_next:
        el.tie = tie.Tie("start" if first else "continue")
    elif not first:
        el.tie = tie.Tie("stop")
    return el


_STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _postprocess(path: Path, tab: TabScore) -> None:
    """Patch our own file: music21 emits no <staff-tuning> and drops per-note
    string/fret inside chords, so both are inserted with ElementTree."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    root = ET.fromstring(raw)
    _insert_staff_tuning(root, tab.tuning)
    _insert_chord_technical(root, tab)
    # ElementTree drops the declaration and DOCTYPE; keep the original ones.
    prefix = text[: text.index("<score-partwise")]
    body = ET.tostring(root, encoding="unicode")
    path.write_bytes(f"{prefix}{body}\n".encode())


def _insert_staff_tuning(root: ET.Element, tuning: Tuning) -> None:
    details = root.find(".//staff-details")
    if details is None:
        raise ValueError("music21 produced no staff-details")
    lines = details.find("staff-lines")
    index = list(details).index(lines) + 1 if lines is not None else len(details)
    # MusicXML line 1 = lowest string; our tuning index 0 = highest.
    for line, midi in enumerate(reversed(tuning.strings), start=1):
        p = pitch.Pitch(midi=midi)
        el = ET.Element("staff-tuning", {"line": str(line)})
        ET.SubElement(el, "tuning-step").text = p.step
        alter = int(p.accidental.alter) if p.accidental is not None else 0
        if alter:
            ET.SubElement(el, "tuning-alter").text = str(alter)
        ET.SubElement(el, "tuning-octave").text = str(p.octave)
        details.insert(index, el)
        index += 1


def _midi_of(note_el: ET.Element) -> int:
    step = note_el.findtext("pitch/step", "")
    alter = int(float(note_el.findtext("pitch/alter", "0")))
    octave = int(note_el.findtext("pitch/octave", "0"))
    return 12 * (octave + 1) + _STEP_SEMITONES[step] + alter


def _insert_chord_technical(root: ET.Element, tab: TabScore) -> None:
    bar_slots = tab.rhythm.time_signature.bar_slots
    chords = [
        {n.pitch: n for n in s.notes}
        for s in tab.slots
        if len(s.notes) > 1
        for _ in split(s.start, s.length, bar_slots)
    ]
    groups: list[list[ET.Element]] = []
    for note_el in root.iter("note"):
        if note_el.find("pitch") is None:
            continue
        if note_el.find("chord") is None:
            groups.append([])
        groups[-1].append(note_el)
    multi = [g for g in groups if len(g) > 1]
    if len(multi) != len(chords):
        raise ValueError("chord count mismatch after export")
    for group, by_pitch in zip(multi, chords, strict=True):
        for note_el in group:
            tab_note = by_pitch[_midi_of(note_el)]
            notations = note_el.find("notations")
            if notations is None:
                notations = ET.SubElement(note_el, "notations")
            technical = ET.SubElement(notations, "technical")
            ET.SubElement(technical, "string").text = str(tab_note.string)
            ET.SubElement(technical, "fret").text = str(tab_note.fret)
