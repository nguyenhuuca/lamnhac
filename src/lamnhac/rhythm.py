"""Beat tracking, tempo, downbeat choice and quantisation onto the slot grid (spec B5-B10)."""

import math
from collections.abc import Sequence
from itertools import pairwise

import librosa
import numpy as np

from lamnhac.errors import ProcessingError
from lamnhac.models import (
    AudioClip,
    GridNote,
    NoteEvent,
    OnsetLike,
    RhythmInfo,
    Score,
    Slot,
    TimeSignature,
)

DEFAULT_TEMPO = 120.0
MIN_TEMPO = 60.0
MAX_TEMPO = 200.0
SLOTS_PER_BEAT = 4
PICKUP_TOLERANCE = 0.5  # slots
DOWNBEAT_WINDOW = 1.0  # slots, B8
MIN_LAG_SAMPLES = 4  # B7a
LOCAL_WINDOW_BEATS = 4  # B7b: onsets attached to beats within +-4 beats
LOCAL_MIN_SAMPLES = 3  # B7b
_EPS = 1e-9


def grid_position(t: float, beat_times: Sequence[float]) -> float:
    """Map time `t` (s) to a slot position, following the real beats (B7).

    Beat i sits at slot 4*i. Outside the beats, extrapolate with the median beat interval.
    """
    beats = np.asarray(beat_times, dtype=np.float64)
    if beats.size < 2:
        raise ValueError("need at least 2 beats")
    median = float(np.median(np.diff(beats)))
    if t < beats[0]:
        return SLOTS_PER_BEAT * (t - float(beats[0])) / median
    if t >= beats[-1]:
        return SLOTS_PER_BEAT * ((beats.size - 1) + (t - float(beats[-1])) / median)
    i = int(np.searchsorted(beats, t, side="right")) - 1
    frac = (t - float(beats[i])) / float(beats[i + 1] - beats[i])
    return SLOTS_PER_BEAT * (i + frac)


def _fold_tempo(bpm: float, beats: Sequence[float]) -> tuple[float, list[float]]:
    """Fold a detected tempo into 60-200 BPM, folding the beat grid with it (B6).

    Halving the tempo keeps every other beat; doubling inserts the midpoint of each pair, so a
    grid beat is always one quarter note of the returned tempo.
    """
    grid = [float(b) for b in beats]
    while bpm < MIN_TEMPO:
        bpm *= 2
        mids = [(a + b) / 2 for a, b in pairwise(grid)]
        grid = [t for pair in zip(grid, mids, strict=False) for t in pair] + [grid[-1]]
    while bpm > MAX_TEMPO:
        bpm /= 2
        kept = grid[::2]
        if len(kept) < 2:
            kept = [grid[0], grid[0] + 2 * (grid[1] - grid[0])]
        grid = kept
    return bpm, grid


def _even_beats(start_s: float, tempo: float, duration_s: float) -> list[float]:
    interval = 60.0 / tempo
    count = max(2, math.ceil((duration_s - start_s) / interval) + 1)
    return [start_s + i * interval for i in range(count)]


def align_beats(beat_times: Sequence[float], onsets: Sequence[float]) -> tuple[float, ...]:
    """Remove the constant onset-envelope latency of the tracked beats (B7a).

    Offsets onset - nearest beat are taken for onsets within 1/4 median interval of a beat.
    With at least 4 of them, all beats shift by their median, clamped to +-1/8 interval.
    """
    beats = np.asarray(beat_times, dtype=np.float64)
    if beats.size < 2 or len(onsets) == 0:
        return tuple(float(b) for b in beats)
    interval = float(np.median(np.diff(beats)))
    on = np.asarray(onsets, dtype=np.float64)
    offsets = on - beats[np.abs(on[:, None] - beats[None, :]).argmin(axis=1)]
    near = offsets[np.abs(offsets) <= interval / 4 + _EPS]
    if near.size < MIN_LAG_SAMPLES:
        return tuple(float(b) for b in beats)
    limit = interval / 8
    shift = float(np.clip(np.median(near), -limit, limit))
    return tuple(float(b) + shift for b in beats)


def align_beats_locally(beat_times: Sequence[float], onsets: Sequence[float]) -> tuple[float, ...]:
    """Pull each beat onto the onsets around it (B7b).

    The tracker can lose phase over a long held note and come back a sixteenth late; one global
    shift (B7a) cannot fix that. Each onset is attached to its nearest beat when within 1/4
    interval; beat i moves by the median offset of the onsets attached to beats i-4..i+4, if
    there are at least 3, clamped to +-1/4 interval. Beats stay at least 1/4 interval apart.
    """
    beats = np.asarray(beat_times, dtype=np.float64)
    if beats.size < 2 or len(onsets) == 0:
        return tuple(float(b) for b in beats)
    interval = float(np.median(np.diff(beats)))
    on = np.asarray(onsets, dtype=np.float64)
    nearest = np.abs(on[:, None] - beats[None, :]).argmin(axis=1)
    offsets = on - beats[nearest]
    close = np.abs(offsets) <= interval / 4 + _EPS
    out = beats.copy()
    for i in range(beats.size):
        chosen = close & (np.abs(nearest - i) <= LOCAL_WINDOW_BEATS)
        if int(chosen.sum()) >= LOCAL_MIN_SAMPLES:
            limit = interval / 4
            out[i] += float(np.clip(np.median(offsets[chosen]), -limit, limit))
    for i in range(1, out.size):
        out[i] = max(out[i], out[i - 1] + interval / 4)
    return tuple(float(b) for b in out)


def _pick_downbeat(beats: Sequence[float], notes: Sequence[OnsetLike], bar_slots: int) -> int:
    """Return the downbeat as a slot offset in [0, bar_slots) (B8)."""
    if not notes:
        return 0
    positions = [(grid_position(n.onset_s, beats), n.velocity) for n in notes]
    first_p = grid_position(min(n.onset_s for n in notes), beats)
    lo = min(p for p, _ in positions) - DOWNBEAT_WINDOW
    hi = max(p for p, _ in positions) + DOWNBEAT_WINDOW
    step = 4 if bar_slots % 4 == 0 else 2
    scores: dict[int, float] = {}
    for o in range(0, bar_slots, step):
        total = 0.0
        for k in range(math.floor((lo - o) / bar_slots), math.ceil((hi - o) / bar_slots) + 1):
            centre = o + k * bar_slots
            # Max, not sum: a chord on a weak beat must not outweigh an accented single note.
            total += max(
                (v for p, v in positions if abs(p - centre) <= DOWNBEAT_WINDOW + _EPS),
                default=0.0,
            )
        scores[o] = total
    best = max(scores.values())
    tied = [o for o, sc in scores.items() if sc >= best - _EPS]

    def phase_distance(o: int) -> float:
        # Distance from the first onset to the nearest o + k*bar_slots, not to o itself.
        d = (first_p - o) % bar_slots
        return min(d, bar_slots - d)

    return min(tied, key=lambda o: (phase_distance(o), o))


def _downbeat_from_pickup(
    beats: Sequence[float], notes: Sequence[OnsetLike], bar_slots: int, pickup_slots: int
) -> int:
    """Downbeat slot when the user says how far before bar 1 the first note is (B8a).

    The pickup is added in seconds, not grid slots: the tracked beats are often irregular for
    the first few seconds. The result snaps to a candidate beat, as in B8, so a first onset
    detected a little late does not shift the whole score by a sixteenth.
    """
    if not notes:
        return 0
    seconds_per_slot = float(np.median(np.diff(beats))) / SLOTS_PER_BEAT
    downbeat_s = min(n.onset_s for n in notes) + pickup_slots * seconds_per_slot
    step = 4 if bar_slots % 4 == 0 else 2
    return (step * _round_half_up(grid_position(downbeat_s, beats) / step)) % bar_slots


def analyze(
    clip: AudioClip,
    notes: Sequence[OnsetLike],
    tempo: float | None,
    time_sig: TimeSignature,
    pickup_slots: int | None = None,
) -> RhythmInfo:
    if clip.samples.size == 0:
        raise ProcessingError("không phân tích được nhịp: audio rỗng")
    if tempo is not None and not 30 <= tempo <= 300:
        raise ProcessingError("tempo phải nằm trong khoảng 30..300 BPM")

    _, beat_arr = librosa.beat.beat_track(
        y=clip.samples,
        sr=clip.sample_rate,
        start_bpm=tempo or DEFAULT_TEMPO,
        tightness=100 if tempo else 50,
        units="time",
    )
    beats = [float(b) for b in np.atleast_1d(beat_arr)]

    if len(beats) < 2:
        first = min((n.onset_s for n in notes), default=0.0)
        beats = _even_beats(first, tempo or DEFAULT_TEMPO, clip.duration_s)
    # applied to the fallback grid too: it is anchored on the first onset, so the median
    # offset is ~0 and the shift is harmless
    onsets = [n.onset_s for n in notes]
    beats = list(align_beats_locally(align_beats(beats, onsets), onsets))

    bar_slots = time_sig.bar_slots
    if pickup_slots is not None and not 0 <= pickup_slots < bar_slots:
        raise ProcessingError("pickup phải ngắn hơn một ô nhịp")

    def downbeat(grid: Sequence[float]) -> int:
        if pickup_slots is None:
            return _pick_downbeat(grid, notes, bar_slots)
        return _downbeat_from_pickup(grid, notes, bar_slots, pickup_slots)

    if tempo is not None:
        return RhythmInfo(float(tempo), tuple(beats), downbeat(beats), time_sig, "user")
    bpm, beats = _fold_tempo(60.0 / float(np.median(np.diff(beats))), beats)
    return RhythmInfo(bpm, tuple(beats), downbeat(beats), time_sig, "detected")


def _round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def quantize(notes: Sequence[NoteEvent], rhythm: RhythmInfo) -> Score:
    bar_slots = rhythm.time_signature.bar_slots
    beats = rhythm.beat_times_s
    placed = [(grid_position(n.onset_s, beats), grid_position(n.offset_s, beats), n) for n in notes]

    bar1 = float(rhythm.downbeat_slot)
    if placed:
        first_p = min(p for p, _, _ in placed)
        m = max(0, math.ceil((bar1 - PICKUP_TOLERANCE - first_p) / bar_slots - _EPS))
        bar1 -= m * bar_slots

    groups: dict[int, dict[int, float]] = {}  # start -> pitch -> velocity
    longest: dict[int, int] = {}
    for p_on, p_off, note in placed:
        start = max(0, _round_half_up(p_on - bar1))
        length = max(1, _round_half_up(p_off - bar1) - start)
        pitches = groups.setdefault(start, {})
        if pitches.get(note.pitch, -1.0) < note.velocity:
            pitches[note.pitch] = note.velocity
        longest[start] = max(longest.get(start, 0), length)

    slots: list[Slot] = []
    pos = 0
    starts = sorted(groups)
    for i, start in enumerate(starts):
        if start > pos:
            slots.append(Slot(pos, start - pos))
        length = longest[start]
        if i + 1 < len(starts):
            length = min(length, starts[i + 1] - start)
        grid_notes = tuple(GridNote(pitch, vel) for pitch, vel in sorted(groups[start].items()))
        slots.append(Slot(start, length, grid_notes))
        pos = start + length

    total = max(bar_slots, math.ceil(pos / bar_slots) * bar_slots)
    if total > pos:
        slots.append(Slot(pos, total - pos))
    return Score(rhythm=rhythm, slots=tuple(slots))
