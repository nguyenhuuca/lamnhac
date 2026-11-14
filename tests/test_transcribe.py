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

    def fake(_clip: AudioClip, low: float, high: float, *_: Any) -> Sequence[Sequence[Any]]:
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
    notes, warnings = tr.transcribe(clip, STANDARD_TUNING)
    assert warnings == []
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
    def boom(_c: AudioClip, _l: float, _h: float, *_: Any) -> list[Any]:
        raise RuntimeError("tf exploded")

    monkeypatch.setattr(tr, "_predict", boom)
    with pytest.raises(ProcessingError) as info:
        tr.transcribe(clip, STANDARD_TUNING)
    assert isinstance(info.value.__cause__, RuntimeError)


@pytest.fixture(scope="module")
def scale_result() -> tuple[list[NoteEvent], float]:
    start = time.perf_counter()
    notes, _ = tr.transcribe(load(FIXTURES / "scale_c.mp3"), STANDARD_TUNING)
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


def _ev(on: float, off: float, pitch: int, vel: float) -> NoteEvent:
    return NoteEvent(on, off, pitch, vel)


@pytest.mark.parametrize("interval", sorted(tr.HARMONIC_INTERVALS))
def test_filter_drops_quieter_overtone(interval: int) -> None:
    base = _ev(0.0, 1.0, 40, 0.8)
    over = _ev(0.02, 1.0, 40 + interval, 0.4)
    kept, dropped = tr.filter_harmonics([base, over])
    assert kept == [base]
    assert dropped == 1


@pytest.mark.parametrize("interval", [5, 7, 11, 13])
def test_filter_keeps_other_intervals(interval: int) -> None:
    notes = [_ev(0.0, 1.0, 40, 0.8), _ev(0.0, 1.0, 40 + interval, 0.1)]
    assert tr.filter_harmonics(notes) == (notes, 0)


def test_filter_keeps_equal_velocity() -> None:
    notes = [_ev(0.0, 1.0, 40, 0.8), _ev(0.0, 1.0, 52, 0.8)]
    assert tr.filter_harmonics(notes) == (notes, 0)


def test_filter_ratio_boundary_is_inclusive() -> None:
    kept, dropped = tr.filter_harmonics([_ev(0.0, 1.0, 40, 1.0), _ev(0.0, 1.0, 52, 0.8)])
    assert dropped == 1
    assert [n.pitch for n in kept] == [40]


def test_filter_keeps_onset_100ms_apart() -> None:
    notes = [_ev(0.0, 1.0, 40, 0.8), _ev(0.1, 1.0, 52, 0.1)]
    assert tr.filter_harmonics(notes) == (notes, 0)


def test_filter_keeps_non_overlapping() -> None:
    notes = [_ev(0.0, 0.05, 40, 0.8), _ev(0.06, 1.0, 52, 0.1)]
    assert tr.filter_harmonics(notes) == (notes, 0)


def test_filter_keeps_overtone_below_base() -> None:
    notes = [_ev(0.0, 1.0, 40, 0.1), _ev(0.0, 1.0, 52, 0.8)]  # sorted by (onset, pitch)
    assert tr.filter_harmonics(notes[::-1]) == (notes, 0)


def test_filter_decides_on_original_list() -> None:
    # 64 is an overtone of 52 and of 40; 52 is dropped, yet 64 must still go (not cascade-kept)
    notes = [_ev(0.0, 1.0, 40, 1.0), _ev(0.0, 1.0, 52, 0.7), _ev(0.0, 1.0, 64, 0.9)]
    kept, dropped = tr.filter_harmonics(notes)
    assert [n.pitch for n in kept] == [40, 64]  # 64 vs 40: 24 apart, 0.9 > 0.8 -> kept
    assert dropped == 1


def test_filter_scales_to_many_notes() -> None:
    notes = [_ev(0.1 * i, 0.1 * i + 0.05, 40 + i % 12, 0.5) for i in range(20000)]
    start = time.perf_counter()
    tr.filter_harmonics(notes)
    assert time.perf_counter() - start < 5.0


def test_transcribe_warns_dropped_harmonics(
    monkeypatch: pytest.MonkeyPatch, clip: AudioClip
) -> None:
    _stub(monkeypatch, [(0.0, 1.0, 40, 0.8, None), (0.0, 1.0, 52, 0.3, None)])
    notes, warnings = tr.transcribe(clip, STANDARD_TUNING, filter_harmonics=True)
    assert [n.pitch for n in notes] == [40]
    assert warnings == ["bỏ 1 nốt hoạ âm"]


def test_transcribe_keeps_harmonics_by_default(
    monkeypatch: pytest.MonkeyPatch, clip: AudioClip
) -> None:
    _stub(monkeypatch, [(0.0, 1.0, 40, 0.8, None), (0.0, 1.0, 52, 0.3, None)])
    notes, warnings = tr.transcribe(clip, STANDARD_TUNING)
    assert [n.pitch for n in notes] == [40, 52]
    assert warnings == []


def _match(notes: list[NoteEvent], truth: list[dict[str, float]]) -> tuple[int, int]:
    """(truth notes found, detected notes matching some truth note), onset +-50 ms, same pitch."""
    found = sum(
        any(n.pitch == t["pitch"] and abs(n.onset_s - t["onset_s"]) <= 0.05 for n in notes)
        for t in truth
    )
    correct = sum(
        any(n.pitch == t["pitch"] and abs(n.onset_s - t["onset_s"]) <= 0.05 for t in truth)
        for n in notes
    )
    return found, correct


@pytest.fixture(scope="module")
def power_chord_notes() -> list[NoteEvent]:
    # "high" is the setting documented for chord-heavy playing: basic-pitch reports the
    # octave of a power chord weakly, and "normal"'s frame threshold (0.5) drops it.
    clip = load(FIXTURES / "power_chord.mp3")
    return tr.transcribe(clip, STANDARD_TUNING, sensitivity="high")[0]


@pytest.fixture(scope="module")
def riff_notes() -> list[NoteEvent]:
    return tr.transcribe(load(FIXTURES / "riff_97bpm.mp3"), STANDARD_TUNING, filter_harmonics=True)[
        0
    ]


_STRIKES = (0.0, 0.8, 1.6, 2.4)


def _e3_strikes(notes: list[NoteEvent]) -> int:
    return sum(any(n.pitch == 52 and abs(n.onset_s - t) <= 0.05 for n in notes) for t in _STRIKES)


def test_real_model_power_chord_octave_kept_without_filter(
    power_chord_notes: list[NoteEvent],
) -> None:
    # Filter off, high sensitivity: the real octave E3 of E2+B2+E3 survives.
    assert _e3_strikes(power_chord_notes) >= 3


def test_real_model_power_chord_root_and_fifth_at_normal() -> None:
    notes, _ = tr.transcribe(load(FIXTURES / "power_chord.mp3"), STANDARD_TUNING)
    for pitch in (40, 47):  # E2, B2 on every strike; E3 is the known loss at "normal"
        hits = sum(
            any(n.pitch == pitch and abs(n.onset_s - t) <= 0.05 for n in notes) for t in _STRIKES
        )
        assert hits == len(_STRIKES)


@pytest.mark.xfail(
    strict=True,
    reason="known limitation, why B4a is opt-in: basic-pitch reports the real E3 at ~0.5x "
    "the E2 velocity, so the 0.8 ratio cannot tell it from an overtone",
)
def test_real_model_power_chord_octave_kept_with_filter(
    power_chord_notes: list[NoteEvent],
) -> None:
    kept, _ = tr.filter_harmonics(power_chord_notes)
    assert _e3_strikes(kept) >= 3


def test_real_model_riff_precision_recall(riff_notes: list[NoteEvent]) -> None:
    truth = json.loads((FIXTURES / "riff_97bpm.json").read_text())["notes"]
    found, correct = _match(riff_notes, truth)
    recall = found / len(truth)
    precision = correct / len(riff_notes)
    print(f"riff precision {precision:.2f}, recall {recall:.2f}")
    assert precision >= 0.9
    assert recall == 1.0


def test_sensitivity_reaches_backend(monkeypatch: pytest.MonkeyPatch, clip: AudioClip) -> None:
    seen: list[Any] = []

    def fake(_c: AudioClip, _l: float, _h: float, sensitivity: Any) -> list[Any]:
        seen.append(sensitivity)
        return [(0.0, 0.5, 60, 0.5, None)]

    monkeypatch.setattr(tr, "_predict", fake)
    tr.transcribe(clip, STANDARD_TUNING)
    tr.transcribe(clip, STANDARD_TUNING, sensitivity="high")
    assert seen == ["normal", "high"]


def test_thresholds_ordered_from_strict_to_loose() -> None:
    low, normal, high = (tr.THRESHOLDS[k] for k in ("low", "normal", "high"))
    for i in range(3):  # onset, frame, minimum length: each is lower when more sensitive
        assert low[i] >= normal[i] >= high[i]
    assert low != normal != high


def test_high_sensitivity_finds_more_notes_on_real_model() -> None:
    clip = load(FIXTURES / "riff_97bpm.mp3")
    normal, _ = tr.transcribe(clip, STANDARD_TUNING)
    high, _ = tr.transcribe(clip, STANDARD_TUNING, sensitivity="high")
    assert len(high) > len(normal)
