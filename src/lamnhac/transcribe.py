"""Audio to note events with basic-pitch (spec B3, B4)."""

import os
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from typing import Any

from lamnhac.errors import ProcessingError
from lamnhac.models import AudioClip, NoteEvent, Sensitivity, Tuning

# (onset_threshold, frame_threshold, minimum_note_length ms) per --sensitivity (spec B3).
# Measured 2026-11-14 (docs/reports/eval-2026-11-14-g1.md): "high" was the old default and
# doubled the note count on a real song (F1 0.58); "normal" scored 0.89 there and 1.00 on the
# synthetic riff and scale.
THRESHOLDS: dict[Sensitivity, tuple[float, float, float]] = {
    "low": (0.85, 0.5, 128.0),
    "normal": (0.75, 0.5, 93.0),
    "high": (0.5, 0.3, 58.0),
}
LOW_MARGIN_SEMITONES = 1
HIGH_MARGIN_SEMITONES = 25  # highest string + 24 frets + 1 semitone of slack
HARMONIC_INTERVALS = frozenset({12, 19, 24, 28, 31, 36})
HARMONIC_ONSET_WINDOW_S = 0.08
HARMONIC_VELOCITY_RATIO = 0.8
_NO_NOTES_MSG = "không nhận được nốt nào — file có phải guitar không?"

_model: Any = None  # loaded basic_pitch Model, cached per process


def _hz(midi: float) -> float:
    return float(440.0 * 2.0 ** ((midi - 69) / 12))


def frequency_range(tuning: Tuning) -> tuple[float, float]:
    """Search band in Hz covering the open low string up to the highest fret."""
    low = _hz(min(tuning.strings) - LOW_MARGIN_SEMITONES)
    high = _hz(max(tuning.strings) + HIGH_MARGIN_SEMITONES)
    return low, high


def _predict(
    clip: AudioClip, low_hz: float, high_hz: float, sensitivity: Sensitivity
) -> Sequence[Sequence[Any]]:
    """Run basic-pitch and return its raw note events. Patched in unit tests."""
    global _model
    # Silence TensorFlow's C++ info/warning spam; must be set before the first TF import.
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    # Lazy: importing TensorFlow takes seconds and would slow `--help`.
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import Model, predict

    if _model is None:
        _model = Model(ICASSP_2022_MODEL_PATH)
    onset, frame, min_len_ms = THRESHOLDS[sensitivity]
    _, _, events = predict(
        str(clip.source),
        _model,
        onset_threshold=onset,
        frame_threshold=frame,
        minimum_note_length=min_len_ms,
        minimum_frequency=low_hz,
        maximum_frequency=high_hz,
    )
    return list(events)


def filter_harmonics(notes: Sequence[NoteEvent]) -> tuple[list[NoteEvent], int]:
    """Drop overtones of a louder, simultaneous lower note (spec B4a).

    Every drop is decided against the ORIGINAL list, not the already filtered one, so the
    result does not depend on processing order (a quiet note can still be the evidence that
    removes an even quieter overtone above it).
    """
    ordered = sorted(notes, key=lambda n: (n.onset_s, n.pitch))
    onsets = [n.onset_s for n in ordered]  # sorted: only the 80 ms window is compared
    kept: list[NoteEvent] = []
    for n in ordered:
        lo = bisect_left(onsets, n.onset_s - HARMONIC_ONSET_WINDOW_S)
        hi = bisect_right(onsets, n.onset_s + HARMONIC_ONSET_WINDOW_S)
        is_overtone = any(
            n.pitch - m.pitch in HARMONIC_INTERVALS
            and m.onset_s < n.offset_s
            and n.onset_s < m.offset_s
            and n.velocity <= HARMONIC_VELOCITY_RATIO * m.velocity
            for m in ordered[lo:hi]
        )
        if not is_overtone:
            kept.append(n)
    return kept, len(ordered) - len(kept)


_apply_filter = filter_harmonics  # transcribe()'s parameter of the same name shadows it


def transcribe(
    clip: AudioClip,
    tuning: Tuning,
    filter_harmonics: bool = False,
    sensitivity: Sensitivity = "normal",
) -> tuple[list[NoteEvent], list[str]]:
    low, high = frequency_range(tuning)
    try:
        raw = _predict(clip, low, high, sensitivity)
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
    warnings: list[str] = []
    if filter_harmonics:
        notes, dropped = _apply_filter(notes)
        if dropped:
            warnings.append(f"bỏ {dropped} nốt hoạ âm")
    if not notes:
        raise ProcessingError(_NO_NOTES_MSG)
    notes.sort(key=lambda n: (n.onset_s, n.pitch))
    return notes, warnings
