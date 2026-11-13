import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from music21 import articulations, chord, converter, note, stream

from lamnhac import export_musicxml
from lamnhac.errors import OutputError
from lamnhac.export_musicxml import write
from lamnhac.models import (
    STANDARD_TUNING,
    RhythmInfo,
    TabNote,
    TabScore,
    TabSlot,
    TimeSignature,
    Tuning,
)

DROP_D = Tuning((64, 59, 55, 50, 45, 38))


def rhythm(num: int = 4, den: int = 4) -> RhythmInfo:
    return RhythmInfo(97.0, (0.0, 0.6, 1.2), 0, TimeSignature(num, den), "user")


def tn(string: int, fret: int, tuning: Tuning = STANDARD_TUNING) -> TabNote:
    return TabNote(tuning.strings[string - 1] + fret, string, fret)


def sample_score(title: str = "Test") -> TabScore:
    slots = (
        TabSlot(0, 4, (tn(2, 1),)),  # single note C4
        TabSlot(4, 2, (tn(6, 0), tn(4, 2), tn(3, 0))),  # 3-note chord
        TabSlot(6, 2),  # rest
        TabSlot(8, 6, (tn(1, 0),)),  # length 6 at position 8
        TabSlot(14, 4, (tn(3, 2),)),  # crosses the bar line
        TabSlot(18, 14),  # rest to end of bar 2
    )
    return TabScore(rhythm(), STANDARD_TUNING, slots, title)


def measures(path: Path) -> list[stream.Measure]:
    parsed = converter.parse(str(path))
    return list(parsed.parts[0].getElementsByClass(stream.Measure))


def test_round_trip(tmp_path: Path) -> None:
    out = tmp_path / "a.musicxml"
    write(sample_score(), out)
    ms = measures(out)
    assert len(ms) == 2
    assert all(m.duration.quarterLength == 4 for m in ms)
    m1 = list(ms[0].notesAndRests)
    first = m1[0]
    assert isinstance(first, note.Note)
    assert first.pitch.midi == 60
    assert [type(a) for a in first.articulations] == [
        articulations.StringIndication,
        articulations.FretIndication,
    ]
    assert first.articulations[0].number == 2
    assert first.articulations[1].number == 1
    ch = m1[1]
    assert isinstance(ch, chord.Chord)
    # music21 parses chord technical marks onto the chord, in note order.
    nums = [a.number for a in ch.articulations]
    got = {
        (p.midi, string, fret)
        for p, string, fret in zip(ch.pitches, nums[0::2], nums[1::2], strict=True)
    }
    assert got == {(40, 6, 0), (52, 4, 2), (55, 3, 0)}
    assert m1[2].isRest and m1[2].quarterLength == 0.5
    assert m1[3].quarterLength == 1.5  # dotted piece of length 6 at position 8


def test_ties_across_bar_line(tmp_path: Path) -> None:
    out = tmp_path / "a.musicxml"
    write(sample_score(), out)
    ms = measures(out)
    last = list(ms[0].notes)[-1]
    nxt = next(iter(ms[1].notes))
    assert last.tie is not None and last.tie.type == "start"
    assert nxt.tie is not None and nxt.tie.type == "stop"
    assert last.pitch.midi == nxt.pitch.midi == 57
    assert list(ms[1].notesAndRests)[1].isRest


def test_split_pieces_tied_within_slot(tmp_path: Path) -> None:
    tab = TabScore(
        rhythm(),
        STANDARD_TUNING,
        (TabSlot(0, 5, (tn(1, 0),)), TabSlot(5, 11)),
    )
    out = tmp_path / "a.musicxml"
    write(tab, out)
    notes = list(measures(out)[0].notes)
    assert [n.quarterLength for n in notes] == [1.0, 0.25]
    assert notes[0].tie is not None and notes[0].tie.type == "start"
    assert notes[1].tie is not None and notes[1].tie.type == "stop"


def test_raw_xml_drop_d(tmp_path: Path) -> None:
    out = tmp_path / "a.musicxml"
    write(TabScore(rhythm(), DROP_D, (TabSlot(0, 16, (tn(6, 0, DROP_D),)),)), out)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<?xml")
    assert "<!DOCTYPE score-partwise" in text
    assert "<sign>TAB</sign>" in text
    assert "<staff-lines>6</staff-lines>" in text
    root = ET.fromstring(text.encode("utf-8"))
    tunings = {
        t.get("line"): (t.findtext("tuning-step"), t.findtext("tuning-octave"))
        for t in root.iter("staff-tuning")
    }
    assert tunings == {
        "1": ("D", "2"),
        "2": ("A", "2"),
        "3": ("D", "3"),
        "4": ("G", "3"),
        "5": ("B", "3"),
        "6": ("E", "4"),
    }
    assert any(s.get("tempo") == "97" for s in root.iter("sound"))


def test_tuning_alter(tmp_path: Path) -> None:
    flat = Tuning((63, 58, 54, 49, 44, 39))  # all one semitone down
    out = tmp_path / "a.musicxml"
    write(TabScore(rhythm(), flat, (TabSlot(0, 16),)), out)
    root = ET.parse(out).getroot()
    line1 = next(t for t in root.iter("staff-tuning") if t.get("line") == "1")
    assert line1.findtext("tuning-step") == "E"
    assert line1.findtext("tuning-alter") == "-1"
    assert line1.findtext("tuning-octave") == "2"


def test_three_four(tmp_path: Path) -> None:
    tab = TabScore(
        rhythm(3, 4),
        STANDARD_TUNING,
        (TabSlot(0, 8, (tn(1, 0),)), TabSlot(8, 8), TabSlot(16, 8, (tn(2, 0),))),
    )
    out = tmp_path / "a.musicxml"
    write(tab, out)
    ms = measures(out)
    assert len(ms) == 2
    assert all(m.duration.quarterLength == 3 for m in ms)


def test_no_temp_left_on_success(tmp_path: Path) -> None:
    write(sample_score(), tmp_path / "a.musicxml")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.musicxml"]


def test_failure_raises_output_error_and_cleans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(path: Path, tab: TabScore) -> None:
        raise ValueError("boom")

    monkeypatch.setattr(export_musicxml, "_postprocess", boom)
    with pytest.raises(OutputError) as info:
        write(sample_score(), tmp_path / "a.musicxml")
    assert isinstance(info.value.__cause__, ValueError)
    assert list(tmp_path.iterdir()) == []


def test_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(OutputError):
        write(sample_score(), tmp_path / "nope" / "a.musicxml")


def test_vietnamese_title(tmp_path: Path) -> None:
    title = "Bài hát đầu tiên"
    out = tmp_path / "a.musicxml"
    write(sample_score(title), out)
    assert title in out.read_text(encoding="utf-8")
    assert converter.parse(str(out)).metadata.bestTitle == title
