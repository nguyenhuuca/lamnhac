import pytest

from lamnhac.cli import main


def test_help_exits_zero() -> None:
    assert main(["--help"]) == 0


def test_bad_args_exit_two() -> None:
    assert main([]) == 2


def test_convert_stub(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["convert", "x.mp3"]) == 2
    assert "not implemented" in capsys.readouterr().err
