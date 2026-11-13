import subprocess
import sys
from pathlib import Path

import guitarpro
import music21
import numpy as np
import pytest
import soundfile as sf

from lamnhac.cli import main

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


def test_missing_file_exit_three(tmp_path: Path) -> None:
    proc = run("convert", tmp_path / "nope.mp3", "-o", tmp_path)
    assert proc.returncode == 3
    assert proc.stdout == ""
    assert "Traceback" not in proc.stderr


def test_existing_output_exit_five_without_force(tmp_path: Path) -> None:
    (tmp_path / "scale_c.musicxml").write_text("old")
    proc = run("convert", SCALE, "-o", tmp_path)
    assert proc.returncode == 5
    assert proc.stdout == ""
    assert "Traceback" not in proc.stderr
    assert "[1/6]" not in proc.stderr  # B14: nothing processed


def test_no_notes_exit_four(tmp_path: Path) -> None:
    silent = tmp_path / "silent.mp3"
    sf.write(str(silent), np.zeros(22050 * 3, dtype=np.float32), 22050, format="MP3")
    proc = run("convert", silent, "-o", tmp_path / "out")
    assert proc.returncode == 4
    assert proc.stdout == ""
    assert "Traceback" not in proc.stderr
    assert "guitar" in proc.stderr


def test_convert_end_to_end(tmp_path: Path) -> None:
    proc = run("convert", SCALE, "-o", tmp_path, "--tempo", "120")
    assert proc.returncode == 0, proc.stderr
    expected = [tmp_path / "scale_c.gp5", tmp_path / "scale_c.musicxml"]
    assert proc.stdout.splitlines() == [str(p) for p in expected]
    assert all(p.exists() for p in expected)
    assert guitarpro.parse(str(expected[0])).tracks[0].name == "Guitar"
    assert music21.converter.parse(str(expected[1])) is not None
    for k in range(1, 7):
        assert f"[{k}/6]" in proc.stderr
    assert "Traceback" not in proc.stderr
