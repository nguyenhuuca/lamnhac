from pathlib import Path

import pytest

from lamnhac.errors import OutputError
from lamnhac.export_chords_txt import render, write
from lamnhac.models import (
    NO_CHORD,
    ChordChart,
    ChordLabel,
    MusicKey,
    RhythmInfo,
    TimeSignature,
)

C = ChordLabel(0, False)
D = ChordLabel(2, False)
G = ChordLabel(7, False)
AM = ChordLabel(9, True)
F = ChordLabel(5, False)
N = NO_CHORD
KEY_C = MusicKey(0, False)
TS44 = TimeSignature(4, 4)


def _chart(
    labels: list[ChordLabel],
    *,
    ts: TimeSignature = TS44,
    unit: int = 4,
    bar1: int = 0,
    capo: int = 0,
    key: MusicKey = KEY_C,
    tempo: float = 99.6,
) -> ChordChart:
    rhythm = RhythmInfo(tempo, tuple(i * 0.5 for i in range(1, 40)), 0, ts, "user")
    return ChordChart(rhythm, key, unit, tuple(labels), bar1, capo)


def test_header_and_four_bars_per_line() -> None:
    labels = [C, C, C, C, G, G, G, G, AM, AM, AM, AM, F, F, F, F, C, C, C, C]
    text = render(_chart(labels), "Song")
    assert text.splitlines() == [
        "# Song",
        "# giọng: Đô trưởng (C) · tempo: 100 BPM · nhịp: 4/4",
        "",
        "| C | G | Am | F |",
        "| C |",
    ]
    assert text.endswith("\n")


def test_repeats_merged_within_bar_but_each_bar_stands_alone() -> None:
    labels = [C, C, C, G, G, G, G, G, G, G, G, G, C, C, C, C]
    # bar 1: C C C G -> C G ; bar 2: all G ; bar 3: all G... units 4/bar
    text = render(_chart(labels), "t")
    assert text.splitlines()[-1] == "| C G | G | G | C |"


def test_no_chord_skipped_and_empty_bar_dash() -> None:
    labels = [C, N, C, N, N, N, N, N, G, G, G, G]
    assert render(_chart(labels), "t").splitlines()[-1] == "| C | - | G |"


def test_units_before_positive_bar1_skipped() -> None:
    labels = [F, C, C, C, C, G, G, G, G]
    text = render(_chart(labels, bar1=4), "t")
    assert text.splitlines()[-1] == "| C | G |"


def test_negative_bar1_keeps_all_units() -> None:
    labels = [F, C, C, C, C, G, G, G, G]
    text = render(_chart(labels, bar1=-4), "t")
    assert text.splitlines()[-1] == "| F C | C G | G |"


def test_capo_in_header_and_shifts_names() -> None:
    chart = _chart([D, D, D, D], capo=2, key=MusicKey(2, False))
    lines = render(chart, "t").splitlines()
    assert lines[1].endswith("· nhịp: 4/4 · capo 2")
    assert lines[-1] == "| C |"


def test_six_eight_groups_six_units_per_bar() -> None:
    labels = [C, C, C, G, G, G, AM, AM, AM, F, F, F]
    chart = _chart(labels, ts=TimeSignature(6, 8), unit=2)
    lines = render(chart, "t").splitlines()
    assert lines[1].endswith("nhịp: 6/8")
    assert lines[-1] == "| C G | Am F |"


def test_write_exact_content_no_tmp_left(tmp_path: Path) -> None:
    chart = _chart([C, C, C, C, G, G, G, G])
    out = tmp_path / "song.chords.txt"
    write(chart, "Song", out)
    assert out.read_bytes() == render(chart, "Song").encode("utf-8")
    assert b"\r" not in out.read_bytes()
    assert [p.name for p in tmp_path.iterdir()] == ["song.chords.txt"]


def test_write_failure_raises_output_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(OutputError):
        write(_chart([C, C, C, C]), "t", blocker / "out.txt")
