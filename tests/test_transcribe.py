import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from lamnhac import transcribe as tr
from lamnhac.audio import load
from lamnhac.errors import ProcessingError
from lamnhac.models import STANDARD_TUNING, AudioClip, NoteEvent, Tuning

FIXTURES = Path(__file__).parent / "fixtures"
DROP_D = Tuning((64, 59, 55, 50, 45, 38))


def _hz(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69) / 12)


@pytest.fixture
def clip() -> AudioClip:
    return load(FIXTURES / "scale_c.mp3")


def _stub(
    monkeypatch: pytest.MonkeyPatch, events: Sequence[Sequence[Any]]
) -> list[tuple[float, float]]:
    seen: list[tuple[float, float]] = []

    def fake(_clip: AudioClip, low: float, high: float) -> Sequence[Sequence[Any]]:
        seen.append((low, high))
        return events

    monkeypatch.setattr(tr, "_predict", fake)
    return seen


def test_frequency_range_standard() -> None:
    low, high = tr.frequency_range(STANDARD_TUNING)
    assert low == pytest.approx(_hz(39))
    assert high == pytest.approx(_hz(89))


def test_frequency_range_drop_d() -> None:
    low, high = tr.frequency_range(DROP_D)
    assert low <= 73.4
    assert low == pytest.approx(_hz(37))
    assert high >= _hz(64 + 24)


def test_conversion_sort_clamp_drop(monkeypatch: pytest.MonkeyPatch, clip: AudioClip) -> None:
    seen = _stub(
        monkeypatch,
        [
            (1.0, 1.5, 60, 0.5, None),
            (0.0, 0.5, 64, 1.7, None),
            (0.0, 0.5, 62, -0.2, None),
            (2.0, 2.0, 50, 0.5, None),
            (3.0, 2.5, 50, 0.5, None),
        ],
    )
    notes = tr.transcribe(clip, STANDARD_TUNING)
    assert notes == [
        NoteEvent(0.0, 0.5, 62, 0.0),
        NoteEvent(0.0, 0.5, 64, 1.0),
        NoteEvent(1.0, 1.5, 60, 0.5),
    ]
    assert seen == [tr.frequency_range(STANDARD_TUNING)]


def test_empty_raises(monkeypatch: pytest.MonkeyPatch, clip: AudioClip) -> None:
    _stub(monkeypatch, [])
    with pytest.raises(ProcessingError, match="guitar"):
        tr.transcribe(clip, STANDARD_TUNING)


def test_only_zero_length_raises(monkeypatch: pytest.MonkeyPatch, clip: AudioClip) -> None:
    _stub(monkeypatch, [(1.0, 1.0, 60, 0.5, None)])
    with pytest.raises(ProcessingError):
        tr.transcribe(clip, STANDARD_TUNING)


def test_backend_exception_wrapped(monkeypatch: pytest.MonkeyPatch, clip: AudioClip) -> None:
    def boom(_c: AudioClip, _l: float, _h: float) -> list[Any]:
        raise RuntimeError("tf exploded")

    monkeypatch.setattr(tr, "_predict", boom)
    with pytest.raises(ProcessingError) as info:
        tr.transcribe(clip, STANDARD_TUNING)
    assert isinstance(info.value.__cause__, RuntimeError)


@pytest.fixture(scope="module")
def scale_result() -> tuple[list[NoteEvent], float]:
    start = time.perf_counter()
    notes = tr.transcribe(load(FIXTURES / "scale_c.mp3"), STANDARD_TUNING)
    return notes, time.perf_counter() - start


def test_real_model_scale_c(scale_result: tuple[list[NoteEvent], float]) -> None:
    notes, elapsed = scale_result
    truth = json.loads((FIXTURES / "scale_c.json").read_text())["notes"]
    hits = sum(
        any(n.pitch == t["pitch"] and abs(n.onset_s - t["onset_s"]) <= 0.05 for n in notes)
        for t in truth
    )
    rate = hits / len(truth)
    print(f"scale_c match rate {rate:.2f} ({hits}/{len(truth)}), {elapsed:.1f}s")
    assert rate >= 0.8
