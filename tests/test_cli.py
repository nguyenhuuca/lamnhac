import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import guitarpro
import music21
import pytest

from lamnhac import pipeline, tab, transcribe
from lamnhac.cli import main
from lamnhac.errors import InputError, OutputError, ProcessingError
from lamnhac.models import ConvertOptions, ConvertResult, TabScore, TimeSignature, Tuning

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

    def fake(_clip: Any, _low: float, _high: float) -> Sequence[Sequence[Any]]:
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
    def no_events(_clip: Any, _low: float, _high: float) -> Sequence[Sequence[Any]]:
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
