import json
import socket
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from lamnhac import audio, pipeline, transcribe
from lamnhac.errors import OutputError
from lamnhac.models import STANDARD_TUNING, ConvertOptions, Format, TabScore, TimeSignature

FIXTURES = Path(__file__).parent / "fixtures"
SCALE = FIXTURES / "scale_c.mp3"


def _opts(
    out_dir: Path,
    formats: frozenset[Format] = frozenset({"musicxml"}),
    force: bool = False,
    tempo: float | None = 120.0,
) -> ConvertOptions:
    return ConvertOptions(
        SCALE, out_dir, formats, tempo, STANDARD_TUNING, TimeSignature(4, 4), force
    )


@pytest.fixture
def stub_model(monkeypatch: pytest.MonkeyPatch) -> None:
    truth = json.loads((FIXTURES / "scale_c.json").read_text())

    def fake(_clip: Any, _low: float, _high: float) -> Sequence[Sequence[Any]]:
        return [(n["onset_s"], n["offset_s"], n["pitch"], 0.8, None) for n in truth["notes"]]

    monkeypatch.setattr(transcribe, "_predict", fake)


def test_convert_writes_musicxml_and_reports_progress(tmp_path: Path, stub_model: None) -> None:
    lines: list[str] = []
    result = pipeline.convert(_opts(tmp_path / "new" / "dir"), lines.append)
    assert result.outputs == (tmp_path / "new" / "dir" / "scale_c.musicxml",)
    assert result.outputs[0].stat().st_size > 0
    assert result.errors == ()
    assert result.note_count > 0
    steps = [ln for ln in lines if ln.startswith("[")]
    assert [s[:5] for s in steps] == [f"[{k}/6]" for k in range(1, 7)]
    assert not any("tempo đoán được" in ln for ln in lines)  # user tempo


def test_detected_tempo_message(tmp_path: Path, stub_model: None) -> None:
    lines: list[str] = []
    result = pipeline.convert(_opts(tmp_path, tempo=None), lines.append)
    assert result.rhythm.tempo_source == "detected"
    assert any(ln.startswith("tempo đoán được: ") and "--tempo" in ln for ln in lines)


def test_existing_output_fails_before_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "scale_c.musicxml").write_text("old")

    def boom(_p: Path) -> None:
        raise AssertionError("audio.load must not be called")

    monkeypatch.setattr(audio, "load", boom)
    lines: list[str] = []
    with pytest.raises(OutputError):
        pipeline.convert(_opts(tmp_path), lines.append)
    assert lines == []
    assert (tmp_path / "scale_c.musicxml").read_text() == "old"


def test_force_overwrites(tmp_path: Path, stub_model: None) -> None:
    target = tmp_path / "scale_c.musicxml"
    target.write_text("old")
    pipeline.convert(_opts(tmp_path, force=True), lambda _m: None)
    assert target.read_text() != "old"


def test_out_dir_uncreatable(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(OutputError):
        pipeline.convert(_opts(blocker / "sub"), lambda _m: None)


def test_one_format_failing_does_not_stop_the_other(
    tmp_path: Path, stub_model: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_t: TabScore, _p: Path) -> None:
        raise OutputError("disk full")

    monkeypatch.setitem(pipeline._WRITERS, "gp5", ("gp5", fail))
    result = pipeline.convert(_opts(tmp_path, frozenset({"gp5", "musicxml"})), lambda _m: None)
    assert result.outputs == (tmp_path / "scale_c.musicxml",)
    assert result.outputs[0].exists()
    assert result.errors == ("gp5: disk full",)


def test_real_model_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[object] = []

    def no_net(*a: Any, **_k: Any) -> None:
        attempts.append(a)
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", no_net)
    result = pipeline.convert(_opts(tmp_path), lambda _m: None)
    truth = json.loads((FIXTURES / "scale_c.json").read_text())
    assert result.note_count >= 0.8 * len(truth["notes"])
    assert result.outputs[0].exists()
    assert attempts == []


def test_transcribe_warnings_merged_and_options_forwarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    truth = json.loads((FIXTURES / "scale_c.json").read_text())
    events = [(n["onset_s"], n["offset_s"], n["pitch"], 0.8, None) for n in truth["notes"]]
    first = truth["notes"][0]  # quiet octave above the first note: a harmonic
    events.append((first["onset_s"], first["offset_s"], first["pitch"] + 12, 0.1, None))
    monkeypatch.setattr(transcribe, "_predict", lambda *_a: events)
    # Default: the filter is off (B4a is opt-in), so the overtone stays.
    result = pipeline.convert(_opts(tmp_path), lambda _m: None)
    assert "bỏ 1 nốt hoạ âm" not in result.warnings
    assert result.note_count == len(truth["notes"]) + 1

    filtered = replace(_opts(tmp_path, force=True), filter_harmonics=True)
    result = pipeline.convert(filtered, lambda _m: None)
    assert "bỏ 1 nốt hoạ âm" in result.warnings
    assert result.note_count == len(truth["notes"])
