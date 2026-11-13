from pathlib import Path

import guitarpro
import pytest
from guitarpro import models as gp

from lamnhac import export_gp5
from lamnhac.errors import OutputError
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


def _rhythm(num: int = 4, den: int = 4, bpm: float = 97.2) -> RhythmInfo:
    return RhythmInfo(bpm, (0.0, 0.6), 0, TimeSignature(num, den), "user")


def _n(string: int, fret: int, tuning: Tuning = STANDARD_TUNING) -> TabNote:
    return TabNote(tuning.strings[string - 1] + fret, string, fret)


def _tab_44() -> TabScore:
    slots = (
        TabSlot(0, 4, (_n(2, 1),)),  # single note
        TabSlot(4, 4, (_n(3, 0), _n(4, 2), _n(5, 2))),  # chord
        TabSlot(8, 2),  # rest
        TabSlot(10, 10, (_n(1, 3),)),  # crosses the bar line at 16
        TabSlot(20, 2, (_n(6, 3),)),
        TabSlot(22, 6, (_n(2, 0),)),  # length 6 at position 2 in bar
        # bar 2 ends at 32: trailing gap of 4 slots must be filled with a rest
    )
    return TabScore(_rhythm(), STANDARD_TUNING, slots, title="Bài hát đầu tiên")


def _bar_ticks(song: gp.Song, i: int) -> int:
    ts = song.measureHeaders[i].timeSignature
    return ts.numerator * 3840 // ts.denominator.value


def _check_full(song: gp.Song) -> None:
    for i, ms in enumerate(song.tracks[0].measures):
        assert sum(b.duration.time for b in ms.voices[0].beats) == _bar_ticks(song, i)


def test_roundtrip_44(tmp_path: Path) -> None:
    out = tmp_path / "a.gp5"
    export_gp5.write(_tab_44(), out)
    song = guitarpro.parse(str(out))
    assert song.versionTuple == (5, 1, 0)
    assert song.tempo == 97
    assert song.title == "Bai hat dau tien"
    assert len(song.tracks) == 1
    track = song.tracks[0]
    assert track.name == "Guitar"
    assert track.channel.instrument == 25
    assert [s.value for s in track.strings] == [64, 59, 55, 50, 45, 40]
    assert len(track.measures) == 2
    _check_full(song)
    assert all(h.timeSignature.numerator == 4 for h in song.measureHeaders)

    m1 = track.measures[0].voices[0].beats
    assert [(n.string, n.value, n.type) for n in m1[0].notes] == [(2, 1, gp.NoteType.normal)]
    assert sorted((n.string, n.value) for n in m1[1].notes) == [(3, 0), (4, 2), (5, 2)]
    assert m1[2].status == gp.BeatStatus.rest and not m1[2].notes
    first = [b for b in m1[3:] if b.notes]
    assert first[0].notes[0].type == gp.NoteType.normal
    assert all(b.notes[0].type == gp.NoteType.tie for b in first[1:])
    assert all(n.string == 1 for b in first for n in b.notes)

    m2 = track.measures[1].voices[0].beats
    assert m2[0].notes[0].type == gp.NoteType.tie  # continuation across the bar line
    assert m2[0].notes[0].string == 1
    assert m2[-1].status == gp.BeatStatus.rest  # trailing filler
    assert m2[-1].duration.time == 960
    tail = [b for b in m2 if b.notes and b.notes[0].string == 2]  # slot 22, length 6
    assert [(b.duration.value, b.duration.isDotted) for b in tail] == [(8, False), (4, False)]
    assert [b.notes[0].type for b in tail] == [gp.NoteType.normal, gp.NoteType.tie]
    # no temp file left behind
    assert [p.name for p in tmp_path.iterdir()] == ["a.gp5"]


def test_roundtrip_34(tmp_path: Path) -> None:
    slots = (
        TabSlot(0, 12, (_n(1, 0),)),  # dotted half
        TabSlot(12, 3, (_n(2, 2),)),  # dotted eighth
        TabSlot(15, 1),
        TabSlot(16, 8, (_n(3, 5),)),
    )
    tab = TabScore(_rhythm(3, 4, 120), STANDARD_TUNING, slots)
    out = tmp_path / "b.gp5"
    export_gp5.write(tab, out)
    song = guitarpro.parse(str(out))
    assert song.tempo == 120
    assert len(song.tracks[0].measures) == 2
    assert [
        (h.timeSignature.numerator, h.timeSignature.denominator.value) for h in song.measureHeaders
    ] == [(3, 4)] * 2
    _check_full(song)
    first = song.tracks[0].measures[0].voices[0].beats[0]
    assert (first.duration.value, first.duration.isDotted) == (2, True)
    bar2 = song.tracks[0].measures[1].voices[0].beats
    assert (bar2[0].duration.value, bar2[0].duration.isDotted) == (8, True)
    assert bar2[1].status == gp.BeatStatus.rest and bar2[1].duration.value == 16


def test_six_eight(tmp_path: Path) -> None:
    tab = TabScore(_rhythm(6, 8), STANDARD_TUNING, (TabSlot(0, 12, (_n(1, 0),)),))
    out = tmp_path / "c.gp5"
    export_gp5.write(tab, out)
    song = guitarpro.parse(str(out))
    assert song.measureHeaders[0].timeSignature.denominator.value == 8
    _check_full(song)


def test_drop_d_tuning(tmp_path: Path) -> None:
    tab = TabScore(_rhythm(), DROP_D, (TabSlot(0, 16, (_n(6, 2, DROP_D),)),))
    out = tmp_path / "d.gp5"
    export_gp5.write(tab, out)
    track = guitarpro.parse(str(out)).tracks[0]
    assert [s.value for s in track.strings] == [64, 59, 55, 50, 45, 38]
    note = track.measures[0].voices[0].beats[0].notes[0]
    assert (note.string, note.value) == (6, 2)


def test_empty_score_writes_one_empty_bar(tmp_path: Path) -> None:
    out = tmp_path / "e.gp5"
    export_gp5.write(TabScore(_rhythm(), STANDARD_TUNING, ()), out)
    song = guitarpro.parse(str(out))
    assert len(song.tracks[0].measures) == 1
    _check_full(song)


def test_ascii_title() -> None:
    assert export_gp5.ascii_title("Bài hát đầu tiên") == "Bai hat dau tien"
    assert export_gp5.ascii_title("ĐÀN") == "DAN"
    assert export_gp5.ascii_title("a🎸b") == "a_b"
    assert export_gp5.ascii_title("日本") == "__"
    assert export_gp5.ascii_title("x" * 100) == "x" * 64
    assert export_gp5.ascii_title("") == ""


def test_failure_raises_output_error_and_leaves_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_song: object, path: str, **_k: object) -> None:
        Path(path).write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(guitarpro, "write", boom)
    out = tmp_path / "f.gp5"
    with pytest.raises(OutputError, match="disk full"):
        export_gp5.write(_tab_44(), out)
    assert list(tmp_path.iterdir()) == []


def test_unwritable_directory_raises_output_error(tmp_path: Path) -> None:
    with pytest.raises(OutputError):
        export_gp5.write(_tab_44(), tmp_path / "missing" / "g.gp5")
