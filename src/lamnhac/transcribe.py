"""Audio to note events with basic-pitch (spec B3, B4)."""

import os
from collections.abc import Sequence
from typing import Any

from lamnhac.errors import ProcessingError
from lamnhac.models import AudioClip, NoteEvent, Tuning

ONSET_THRESHOLD = 0.5
FRAME_THRESHOLD = 0.3
MIN_NOTE_LENGTH_MS = 58.0
LOW_MARGIN_SEMITONES = 1
HIGH_MARGIN_SEMITONES = 25  # highest string + 24 frets + 1 semitone of slack
_NO_NOTES_MSG = "không nhận được nốt nào — file có phải guitar không?"

_model: Any = None  # loaded basic_pitch Model, cached per process


def _hz(midi: float) -> float:
    return float(440.0 * 2.0 ** ((midi - 69) / 12))


def frequency_range(tuning: Tuning) -> tuple[float, float]:
    """Search band in Hz covering the open low string up to the highest fret."""
    low = _hz(min(tuning.strings) - LOW_MARGIN_SEMITONES)
    high = _hz(max(tuning.strings) + HIGH_MARGIN_SEMITONES)
    return low, high


def _predict(clip: AudioClip, low_hz: float, high_hz: float) -> Sequence[Sequence[Any]]:
    """Run basic-pitch and return its raw note events. Patched in unit tests."""
    global _model
    # Silence TensorFlow's C++ info/warning spam; must be set before the first TF import.
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    # Lazy: importing TensorFlow takes seconds and would slow `--help`.
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import Model, predict

    if _model is None:
        _model = Model(ICASSP_2022_MODEL_PATH)
    _, _, events = predict(
        str(clip.source),
        _model,
        onset_threshold=ONSET_THRESHOLD,
        frame_threshold=FRAME_THRESHOLD,
        minimum_note_length=MIN_NOTE_LENGTH_MS,
        minimum_frequency=low_hz,
        maximum_frequency=high_hz,
    )
    return list(events)


def transcribe(clip: AudioClip, tuning: Tuning) -> list[NoteEvent]:
    low, high = frequency_range(tuning)
    try:
        raw = _predict(clip, low, high)
        notes = [
            NoteEvent(
                onset_s=float(ev[0]),
                offset_s=float(ev[1]),
                pitch=int(ev[2]),
                velocity=min(1.0, max(0.0, float(ev[3]))),
            )
            for ev in raw
            if float(ev[1]) > float(ev[0]) and 0 <= int(ev[2]) <= 127
        ]
    except Exception as exc:
        raise ProcessingError("lỗi khi nhận dạng nốt nhạc") from exc
    if not notes:
        raise ProcessingError(_NO_NOTES_MSG)
    notes.sort(key=lambda n: (n.onset_s, n.pitch))
    return notes
