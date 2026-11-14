import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import guitarpro
import music21
import pytest

from lamnhac import chords, pipeline, tab, transcribe
from lamnhac.cli import main
from lamnhac.errors import InputError, OutputError, ProcessingError
from lamnhac.models import (
    NO_CHORD,
    ChordLabel,
    ChordsOptions,
    ConvertOptions,
    ConvertResult,
    TabScore,
    TimeSignature,
    Tuning,
)

FIXTURES = Path(__file__).parent / "fixtures"
SCALE = FIXTURES / "scale_c.mp3"


def run(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "lamnhac.cli", *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )


def _stub_model(monkeypatch: pytest.MonkeyPatch) -> int:
    truth = json.loads((FIXTURES / "scale_c.json").read_text())

    def fake(_clip: Any, _low: float, _high: float, *_: Any) -> Sequence[Sequence[Any]]:
        return [(n["onset_s"], n["offset_s"], n["pitch"], 0.8, None) for n in truth["notes"]]

    monkeypatch.setattr(transcribe, "_predict", fake)
    return len(truth["notes"])


def _capture_options(monkeypatch: pytest.MonkeyPatch) -> list[ConvertOptions]:
    seen: list[ConvertOptions] = []

    def fake(opts: ConvertOptions, _progress: Any) -> ConvertResult:
        seen.append(opts)
        raise ProcessingError("stop")

    monkeypatch.setattr(pipeline, "convert", fake)
    return seen


def test_help_exits_zero() -> None:
    assert main(["--help"]) == 0


def test_bad_args_exit_two() -> None:
    assert main([]) == 2


@pytest.mark.parametrize(
    "extra",
    [
        ["--tempo", "29"],
        ["--tempo", "301"],
        ["--tempo", "nan"],
        ["--tempo", "abc"],
        ["--time", "4"],
        ["--time", "4/3"],
        ["--time", "17/4"],
        ["--time", "a/b"],
        ["--tuning", "E A D G B"],
        ["--tuning", "E A D G B H"],
        ["--format", ""],
        ["--format", "wav"],
        ["--format", "gp5,wav"],
    ],
)
def test_invalid_arguments_exit_two(
    extra: list[str], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert main(["convert", str(SCALE), "-o", str(tmp_path), *extra]) == 2
    assert "Traceback" not in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("case", ["missing", "wrong_suffix", "corrupt"])
def test_bad_input_exit_three(
    case: str, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    bad = tmp_path / {"missing": "nope.mp3", "wrong_suffix": "a.wav", "corrupt": "bad.mp3"}[case]
    if case == "wrong_suffix":
        bad.write_bytes(b"RIFF")
    elif case == "corrupt":
        bad.write_bytes(b"this is not an mp3 at all" * 50)
    assert main(["convert", str(bad), "-o", str(tmp_path / "out")]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert "lỗi:" in captured.err


def test_existing_output_exit_five_without_force(tmp_path: Path) -> None:
    (tmp_path / "scale_c.musicxml").write_text("old")
    proc = run("convert", SCALE, "-o", tmp_path)
    assert proc.returncode == 5
    assert proc.stdout == ""
    assert "Traceback" not in proc.stderr
    assert "[1/6]" not in proc.stderr  # B14: nothing processed


def test_no_notes_exit_four(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def no_events(_clip: Any, _low: float, _high: float, *_: Any) -> Sequence[Sequence[Any]]:
        return []

    monkeypatch.setattr(transcribe, "_predict", no_events)
    assert main(["convert", str(SCALE), "-o", str(tmp_path / "out")]) == 4
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert "guitar" in captured.err


def test_gp5_writer_failure_exit_five_keeps_musicxml(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _stub_model(monkeypatch)

    def fail(_t: TabScore, _p: Path) -> None:
        raise OutputError("disk full")

    monkeypatch.setitem(pipeline._WRITERS, "gp5", ("gp5", fail))
    assert main(["convert", str(SCALE), "-o", str(tmp_path), "--tempo", "120"]) == 5
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [str(tmp_path / "scale_c.musicxml")]
    assert (tmp_path / "scale_c.musicxml").exists()
    assert "gp5" in captured.err
    assert "disk full" in captured.err


@pytest.mark.parametrize(
    ("extra", "field", "expected"),
    [
        (["--tuning", "D A D G B E"], "tuning", Tuning((64, 59, 55, 50, 45, 38))),
        (["--time", "3/4"], "time_signature", TimeSignature(3, 4)),
        (["--time", "6/8"], "time_signature", TimeSignature(6, 8)),
        (["--tempo", "96"], "tempo", 96.0),
        (["--force"], "force", True),
        (["--max-fret", "5"], "max_fret", 5),
        (["--max-fret", "0"], "max_fret", 0),
        (["--filter-harmonics"], "filter_harmonics", True),
        (["--sensitivity", "high"], "sensitivity", "high"),
        (["--sensitivity", "low"], "sensitivity", "low"),
        (["--pickup", "0"], "pickup_slots", 0),
        (["--pickup", "1.5", "--time", "3/4"], "pickup_slots", 6),
        (["--pickup", "1", "--time", "6/8"], "pickup_slots", 2),
        (["--pickup", "0.5", "--time", "6/8"], "pickup_slots", 1),
        (["--pickup", "1", "--time", "2/2"], "pickup_slots", 8),
        (["--format", "gp5"], "formats", frozenset({"gp5"})),
    ],
)
def test_valid_options_reach_pipeline(
    extra: list[str],
    field: str,
    expected: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seen = _capture_options(monkeypatch)
    assert main(["convert", str(SCALE), "-o", str(tmp_path), *extra]) == 4
    assert getattr(seen[0], field) == expected


def test_default_options_and_out_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture_options(monkeypatch)
    main(["convert", str(SCALE)])
    opts = seen[0]
    assert opts.out_dir == SCALE.resolve().parent
    assert opts.tempo is None
    assert opts.force is False
    assert opts.max_fret == 24
    assert opts.filter_harmonics is False
    assert opts.sensitivity == "normal"
    assert opts.pickup_slots is None
    assert opts.formats == frozenset({"gp5", "musicxml"})


def test_unexpected_error_exit_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def boom(_o: ConvertOptions, _p: Any) -> ConvertResult:
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline, "convert", boom)
    assert main(["convert", str(SCALE), "-o", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert len(err.strip().splitlines()) == 1
    assert "Traceback" not in err

    assert main(["convert", str(SCALE), "-o", str(tmp_path), "-v"]) == 1
    assert "Traceback" in capsys.readouterr().err


def test_known_error_verbose_prints_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def bad(_o: ConvertOptions, _p: Any) -> ConvertResult:
        raise InputError("hỏng")

    monkeypatch.setattr(pipeline, "convert", bad)
    assert main(["convert", str(SCALE), "-o", str(tmp_path), "-v"]) == 3
    assert "Traceback" in capsys.readouterr().err


def test_summary_line_and_warnings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    note_count = _stub_model(monkeypatch)
    real_assign = tab.assign

    def assign_with_warning(*args: Any, **kwargs: Any) -> Any:
        score, warnings = real_assign(*args, **kwargs)
        return score, [*warnings, "nốt thử nghiệm bị bỏ"]

    monkeypatch.setattr(tab, "assign", assign_with_warning)
    assert main(["convert", str(SCALE), "-o", str(tmp_path), "--tempo", "96"]) == 0
    err = capsys.readouterr().err
    assert "cảnh báo: nốt thử nghiệm bị bỏ" in err
    summary = next(ln for ln in err.splitlines() if ln.startswith("xong:"))
    assert f"{note_count} nốt" in summary
    assert "tempo 96 BPM (user)" in summary
    assert "1 cảnh báo" in summary


def test_convert_end_to_end(tmp_path: Path) -> None:
    proc = run("convert", SCALE, "-o", tmp_path, "--tempo", "120")
    assert proc.returncode == 0, proc.stderr
    expected = [tmp_path / "scale_c.gp5", tmp_path / "scale_c.musicxml"]
    assert proc.stdout.splitlines() == [str(p) for p in expected]
    assert all(p.exists() for p in expected)
    song = guitarpro.parse(str(expected[0]))
    assert song.tracks[0].name == "Guitar"
    assert song.tempo == 120
    assert len(song.tracks[0].measures) >= 2
    assert music21.converter.parse(str(expected[1])) is not None
    for k in range(1, 7):
        assert f"[{k}/6]" in proc.stderr
    assert "Traceback" not in proc.stderr


@pytest.mark.parametrize("value", ["25", "-1", "abc"])
def test_bad_max_fret_exit_two(value: str, tmp_path: Path) -> None:
    assert main(["convert", str(SCALE), "-o", str(tmp_path), "--max-fret", value]) == 2


def test_bad_sensitivity_exit_two(tmp_path: Path) -> None:
    assert main(["convert", str(SCALE), "-o", str(tmp_path), "--sensitivity", "max"]) == 2


@pytest.mark.parametrize(
    "extra",
    [
        ["--pickup", "4"],  # a whole 4/4 bar
        ["--pickup", "-1"],
        ["--pickup", "0.3"],  # not a multiple of a sixteenth
        ["--pickup", "0.25", "--time", "6/8"],  # a 32nd note
        ["--pickup", "nan"],
        ["--pickup", "abc"],
    ],
)
def test_bad_pickup_exit_two(extra: list[str], tmp_path: Path) -> None:
    assert main(["convert", str(SCALE), "-o", str(tmp_path), *extra]) == 2


# --- chords (C-T7) ---


def _stub_recognize(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = (NO_CHORD, *(ChordLabel(r, False) for r in (0, 0, 7, 7, 9, 9, 5, 5)))
    monkeypatch.setattr(chords, "recognize", lambda *_a: labels)


@pytest.mark.parametrize(
    "extra",
    [["--capo", "12"], ["--capo", "-1"], ["--format", "musicxml"], ["--format", ""]],
)
def test_chords_invalid_arguments_exit_two(
    extra: list[str], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert main(["chords", str(SCALE), "-o", str(tmp_path), *extra]) == 2
    assert "Traceback" not in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("case", ["missing", "wrong_suffix"])
def test_chords_bad_input_exit_three(
    case: str, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    bad = tmp_path / {"missing": "nope.mp3", "wrong_suffix": "a.wav"}[case]
    if case == "wrong_suffix":
        bad.write_bytes(b"RIFF")
    assert main(["chords", str(bad), "-o", str(tmp_path / "out")]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "lỗi:" in captured.err


def test_chords_processing_error_exit_four(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def boom(*_a: Any) -> Any:
        raise ProcessingError("không nhận ra hợp âm")

    monkeypatch.setattr(chords, "recognize", boom)
    assert main(["chords", str(SCALE), "-o", str(tmp_path), "--tempo", "120"]) == 4
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "không nhận ra hợp âm" in captured.err


def test_chords_existing_output_exit_five(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _stub_recognize(monkeypatch)
    (tmp_path / "scale_c.chords.gp5").write_text("old")
    assert main(["chords", str(SCALE), "-o", str(tmp_path)]) == 5
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[1/4]" not in captured.err


def test_chords_stdout_paths_and_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _stub_recognize(monkeypatch)
    argv = ["chords", str(SCALE), "-o", str(tmp_path), "--tempo", "96", "--format", "gp5,txt"]
    assert main(argv) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        str(tmp_path / "scale_c.chords.gp5"),
        str(tmp_path / "scale_c.chords.txt"),
    ]
    summary = next(ln for ln in captured.err.splitlines() if ln.startswith("xong:"))
    assert "lần đổi hợp âm" in summary
    assert "giọng" in summary
    assert "tempo 96 BPM (user)" in summary
    assert "# giọng:" in captured.err  # chart text follows the summary


def test_chords_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[ChordsOptions] = []

    def fake(opts: ChordsOptions, _progress: Any) -> Any:
        seen.append(opts)
        raise ProcessingError("stop")

    monkeypatch.setattr(pipeline, "chords", fake)
    assert main(["chords", str(SCALE)]) == 4
    opts = seen[0]
    assert opts.formats == frozenset({"gp5"})
    assert opts.capo == 0
    assert opts.pickup_slots is None
    assert opts.tempo is None
    assert opts.force is False
    assert opts.out_dir == SCALE.resolve().parent
