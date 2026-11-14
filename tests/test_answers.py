"""Unit tests for tests/eval/answers.py (loaded by path: tests/ has no packages)."""

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).parent / "eval" / "answers.py"
_spec = importlib.util.spec_from_file_location("answers", _PATH)
assert _spec is not None and _spec.loader is not None
answers = importlib.util.module_from_spec(_spec)
sys.modules["answers"] = answers  # dataclass needs the module registered
_spec.loader.exec_module(answers)


@pytest.mark.parametrize(
    ("tok", "want"),
    [
        ("Am7", (9, True)),
        ("G/B", (7, False)),
        ("Cmaj7", (0, False)),
        ("Cdim", (0, True)),
        ("Caug", (0, False)),
        ("Bbm", (10, True)),
        ("Dsus4", (2, False)),
        ("F#", (6, False)),
        ("Em", (4, True)),
        ("Gadd9", (7, False)),
        ("x2", None),
        ("Intro:", None),
        ("N.C.", None),
        ("am", None),
        ("the", None),
        ("Hello", None),
    ],
)
def test_parse_token(tok: str, want: tuple[int, bool] | None) -> None:
    assert answers.parse_token(tok) == want


def test_parse_answer_key_bars_comments() -> None:
    a = answers.parse_answer("# key: Am\n# just a note\n| Am | G |\nF E\n")
    assert a.key == (9, True)
    assert a.chords == ((9, True), (7, False), (5, False), (4, False))
    assert (a.skipped, a.total) == (0, 4)


def test_parse_answer_counts_skipped() -> None:
    a = answers.parse_answer("Intro: C G Am F C G Am F C G\n")
    assert (a.skipped, a.total) == (1, 11)
    assert len(a.chords) == 10


def test_parse_answer_too_much_junk() -> None:
    with pytest.raises(ValueError, match="not chords"):
        answers.parse_answer("C G la la la\n")


def test_parse_answer_empty() -> None:
    with pytest.raises(ValueError):
        answers.parse_answer("# key: C\n")


def test_levenshtein() -> None:
    a, b, c = (0, False), (2, False), (9, True)
    assert answers.levenshtein([], []) == 0
    assert answers.levenshtein([a, b], []) == 2
    assert answers.levenshtein([], [a]) == 1
    assert answers.levenshtein([a, b], [a, b]) == 0
    assert answers.levenshtein([a, b], [a, c, b]) == 1
    assert answers.levenshtein([a, c, b], [a, b]) == 1
    assert answers.levenshtein([a, b], [a, c]) == 1


def test_collapse() -> None:
    a, b = (0, False), (7, False)
    assert answers.collapse([a, a, None, a, b, b, None]) == [a, b]


def test_accuracy() -> None:
    ref = [(0, False), (7, False), (9, True), (5, False)]
    assert answers.accuracy(ref, ref) == 1.0
    est = [(0, False), (7, False), (9, True), (4, False)]
    assert answers.accuracy(ref, est) == 0.75
    assert (
        answers.accuracy(
            ref, [(2, False), (3, False), (1, True), (8, False), (6, True), (10, True)]
        )
        == 0.0
    )


def test_accuracy_transposed() -> None:
    ref = [(0, False), (7, False), (9, True), (5, False)]
    est = [((pc + 3) % 12, mn) for pc, mn in ref]
    assert answers.accuracy(ref, est) < 0.5
    assert answers.accuracy_transposed(ref, est) == 1.0


def test_chord_name() -> None:
    assert answers.chord_name((6, True)) == "F#m"
    assert answers.chord_name((0, False)) == "C"
