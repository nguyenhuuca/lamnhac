"""MP3 loading with input validation (spec B1, B2). Decodes with libsndfile only."""

from pathlib import Path

import librosa
import numpy as np
import numpy.typing as npt
import soundfile as sf

from lamnhac.errors import InputError, ProcessingError
from lamnhac.models import MAX_DURATION_S, SAMPLE_RATE, AudioClip

MAX_FILE_BYTES = 50 * 1024 * 1024
# Header durations can lie on VBR files (CWE-400): hard cap on what is really decoded.
MAX_DECODED_S = MAX_DURATION_S + 5.0
_CORRUPT_MSG = "file audio hỏng hoặc rỗng"
_NO_MP3_MSG = "môi trường không đọc được MP3 (libsndfile cần bản >= 1.1)"


def _libsndfile_has_mp3() -> bool:
    return "MP3" in sf.available_formats()


def _validate(path: Path) -> int:
    """Run the ordered B1 checks; return the native sample rate."""
    name = path.name
    if not path.exists():
        raise InputError(f"không tìm thấy file: {name}")
    if not path.is_file():
        raise InputError(f"đường dẫn không phải file thường: {name}")
    if path.suffix.lower() != ".mp3":
        raise InputError(f"file phải có đuôi .mp3: {name}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise InputError(f"file lớn hơn {MAX_FILE_BYTES // (1024 * 1024)} MB: {name}")
    try:
        info = sf.info(str(path))
    except (sf.SoundFileError, RuntimeError, OSError):
        if not _libsndfile_has_mp3():
            raise ProcessingError(_NO_MP3_MSG) from None
        raise InputError(f"không đọc được header audio: {name}") from None
    if info.duration > MAX_DURATION_S:
        raise InputError(f"thời lượng vượt {MAX_DURATION_S:g} giây: {name}")
    return int(info.samplerate)


def load(path: Path) -> AudioClip:
    """Validate and decode an MP3 into a mono float32 clip at SAMPLE_RATE."""
    rate = _validate(path)
    name = path.name
    chunks: list[npt.NDArray[np.float32]] = []
    frames = 0
    try:
        for block in sf.blocks(str(path), blocksize=rate, dtype="float32", always_2d=True):
            frames += len(block)
            if frames / rate > MAX_DECODED_S:
                raise InputError(f"thời lượng giải mã vượt {MAX_DECODED_S:g} giây: {name}")
            chunks.append(np.asarray(block, dtype=np.float32).mean(axis=1))
    except (sf.SoundFileError, RuntimeError, OSError):
        raise InputError(_CORRUPT_MSG) from None
    if frames == 0:
        raise InputError(_CORRUPT_MSG)

    mono = np.concatenate(chunks)
    if rate != SAMPLE_RATE:
        mono = librosa.resample(mono, orig_sr=rate, target_sr=SAMPLE_RATE)
    samples = np.ascontiguousarray(mono, dtype=np.float32)
    duration = samples.size / SAMPLE_RATE
    if duration > MAX_DURATION_S:
        raise InputError(f"thời lượng vượt {MAX_DURATION_S:g} giây: {name}")
    return AudioClip(samples=samples, sample_rate=SAMPLE_RATE, duration_s=duration, source=path)
