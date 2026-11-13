import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lamnhac import audio
from lamnhac.audio import MAX_FILE_BYTES, load
from lamnhac.errors import InputError
from lamnhac.models import SAMPLE_RATE

FIXTURES = Path(__file__).parent / "fixtures"


def test_scale_fixture_loads() -> None:
    clip = load(FIXTURES / "scale_c.mp3")
    assert clip.sample_rate == SAMPLE_RATE == 22050
    assert clip.samples.dtype == np.float32
    assert clip.samples.ndim == 1
    assert clip.duration_s == pytest.approx(4.5, abs=0.2)
    assert clip.samples.size == pytest.approx(clip.duration_s * SAMPLE_RATE, abs=1)
    assert clip.source == FIXTURES / "scale_c.mp3"
    truth = json.loads((FIXTURES / "scale_c.json").read_text(encoding="utf-8"))
    assert [n["pitch"] for n in truth["notes"]] == [48, 50, 52, 53, 55, 57, 59, 60]


def test_riff_fixture_loads() -> None:
    clip = load(FIXTURES / "riff_97bpm.mp3")
    assert clip.duration_s == pytest.approx(12.0, abs=0.3)


def test_uppercase_suffix_accepted(tmp_path: Path) -> None:
    dst = tmp_path / "SONG.MP3"
    dst.write_bytes((FIXTURES / "stereo_short.mp3").read_bytes())
    assert load(dst).duration_s > 0


def test_stereo_mixed_to_mono() -> None:
    path = FIXTURES / "stereo_short.mp3"
    assert sf.info(str(path)).channels == 2
    clip = load(path)
    assert clip.samples.ndim == 1
    assert clip.samples.dtype == np.float32
    assert clip.duration_s == pytest.approx(1.0, abs=0.1)
    assert float(np.max(np.abs(clip.samples))) > 0.05


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="không tìm thấy") as exc:
        load(tmp_path / "nope.mp3")
    assert str(tmp_path) not in str(exc.value)


def test_directory(tmp_path: Path) -> None:
    d = tmp_path / "dir.mp3"
    d.mkdir()
    with pytest.raises(InputError, match="không phải file thường"):
        load(d)


def test_wrong_suffix(tmp_path: Path) -> None:
    p = tmp_path / "a.wav"
    p.write_bytes(b"x")
    with pytest.raises(InputError, match=r"\.mp3"):
        load(p)


def test_too_large_checked_before_decoding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "big.mp3"
    with p.open("wb") as f:
        f.truncate(MAX_FILE_BYTES + 1)

    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("must not read the file")

    monkeypatch.setattr(sf, "info", boom)
    monkeypatch.setattr(sf, "blocks", boom)
    with pytest.raises(InputError, match="50 MB"):
        load(p)


def test_header_duration_too_long(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeInfo:
        duration = 700.0
        samplerate = 44100

    monkeypatch.setattr(sf, "info", lambda *_a, **_k: FakeInfo())
    with pytest.raises(InputError, match="600"):
        load(FIXTURES / "scale_c.mp3")


def test_decoded_duration_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    produced = 0

    def endless(*_a: object, **_k: object):  # type: ignore[no-untyped-def]
        nonlocal produced
        block = np.zeros((22050, 1), dtype=np.float32)
        while True:
            produced += 1
            yield block

    monkeypatch.setattr(sf, "blocks", endless)
    start = time.monotonic()
    with pytest.raises(InputError, match="605"):
        load(FIXTURES / "scale_c.mp3")
    assert time.monotonic() - start < 10
    assert produced <= 607


def test_corrupt_file(tmp_path: Path) -> None:
    p = tmp_path / "bad.mp3"
    p.write_bytes(np.random.default_rng(0).bytes(5000))
    with pytest.raises(InputError) as exc:
        load(p)
    assert "Traceback" not in str(exc.value)
    assert str(tmp_path) not in str(exc.value)


def test_empty_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sf, "blocks", lambda *_a, **_k: iter(()))
    with pytest.raises(InputError, match="hỏng hoặc rỗng"):
        load(FIXTURES / "scale_c.mp3")


def test_decode_error_maps_to_input_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_a: object, **_k: object):  # type: ignore[no-untyped-def]
        raise sf.LibsndfileError(1, prefix="secret internal detail")
        yield  # pragma: no cover

    monkeypatch.setattr(sf, "blocks", broken)
    with pytest.raises(InputError, match="hỏng hoặc rỗng") as exc:
        load(FIXTURES / "scale_c.mp3")
    assert "secret" not in str(exc.value)


def test_no_mp3_support_is_processing_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from lamnhac.errors import ProcessingError

    def unsupported(*_a: object, **_k: object) -> None:
        raise sf.LibsndfileError(1, prefix="Format not recognised")

    monkeypatch.setattr(sf, "info", unsupported)
    monkeypatch.setattr(audio, "_libsndfile_has_mp3", lambda: False)
    with pytest.raises(ProcessingError, match="MP3"):
        load(FIXTURES / "scale_c.mp3")


def test_resamples_44100_to_22050(tmp_path: Path) -> None:
    t = np.arange(44100) / 44100
    tone = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    p = tmp_path / "tone44k.mp3"
    sf.write(str(p), tone, 44100, format="MP3")
    assert sf.info(str(p)).samplerate == 44100
    clip = load(p)
    assert clip.sample_rate == 22050
    assert clip.samples.dtype == np.float32
    assert clip.samples.size == pytest.approx(22050, rel=0.01)
