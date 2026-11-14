"""Chord recognition per strum unit: chroma, template scores, Viterbi smoothing (spec C7-C10a)."""

import logging
from collections.abc import Sequence

import librosa
import numpy as np
import numpy.typing as npt

from lamnhac.chord_shapes import shape
from lamnhac.errors import ProcessingError
from lamnhac.models import (
    NO_CHORD,
    STANDARD_TUNING,
    AudioClip,
    ChordDiagram,
    ChordLabel,
    MusicKey,
    RhythmInfo,
    TabNote,
    TabScore,
    TabSlot,
)
from lamnhac.names import chord_name, chord_sharp
from lamnhac.rhythm import PICKUP_TOLERANCE, time_of_slot

log = logging.getLogger("lamnhac")

BASS_WEIGHT = 0.5
N_SCORE = 0.55
TEMPERATURE = 20.0
P_STAY = 0.85  # unit_slots >= 4
P_STAY_SHORT = 0.92  # shorter units (6/8): more units per chord
SILENCE_DB = -45.0

_HOP = 512
_BINS_PER_OCTAVE = 36
_N_BINS = 216
_BASS_BINS = 72  # C2-B3
_N_STATES = 25
_N_INDEX = 24
_NO_CHORD_MESSAGE = "không nhận được hợp âm nào — bài có nhạc đệm không?"

FloatArray = npt.NDArray[np.float64]

_KK_MAJOR = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
_KK_MINOR = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


def unit_boundaries(rhythm: RhythmInfo, unit_slots: int, duration_s: float) -> list[float]:
    """Start times of the strum units: grid slots j*unit_slots while the time is before the end."""
    out: list[float] = []
    j = 0
    while True:
        t = time_of_slot(float(j * unit_slots), rhythm.beat_times_s)
        if t >= duration_s:
            return out
        out.append(t)
        j += 1


def chroma_per_unit(
    clip: AudioClip, boundaries: list[float]
) -> tuple[FloatArray, npt.NDArray[np.bool_]]:
    """Unit-synchronous L2-normalised chroma (12, n_units) and a silent-unit mask (C8)."""
    n_units = len(boundaries)
    sr = clip.sample_rate
    y = clip.samples.astype(np.float32)
    h = librosa.effects.harmonic(y, margin=3)
    tuning = float(librosa.estimate_tuning(y=h, sr=sr, bins_per_octave=_BINS_PER_OCTAVE))
    cqt = np.abs(
        librosa.cqt(
            h,
            sr=sr,
            hop_length=_HOP,
            fmin=librosa.note_to_hz("C2"),
            n_bins=_N_BINS,
            bins_per_octave=_BINS_PER_OCTAVE,
            tuning=tuning,
        )
    )
    full = librosa.feature.chroma_cqt(
        C=cqt, bins_per_octave=_BINS_PER_OCTAVE, n_chroma=12, norm=np.inf
    )
    bass = librosa.feature.chroma_cqt(
        C=cqt[:_BASS_BINS], bins_per_octave=_BINS_PER_OCTAVE, n_chroma=12, norm=np.inf
    )
    chroma = full + BASS_WEIGHT * bass
    n_frames = chroma.shape[1]
    log.debug(
        "chroma: tuning=%.3f bins, BASS_WEIGHT=%s N_SCORE=%s TEMPERATURE=%s "
        "P_STAY=%s/%s SILENCE_DB=%s",
        tuning,
        BASS_WEIGHT,
        N_SCORE,
        TEMPERATURE,
        P_STAY,
        P_STAY_SHORT,
        SILENCE_DB,
    )

    out = np.zeros((12, n_units), dtype=np.float64)
    if n_units == 0:
        return out, np.ones(0, dtype=np.bool_)

    starts = np.clip(librosa.time_to_frames(boundaries, sr=sr, hop_length=_HOP), 0, n_frames)
    ends = np.append(starts[1:], n_frames)
    nonempty = starts < ends  # clamping can leave units with no frame at the end of the clip
    if nonempty.any():
        synced = librosa.util.sync(
            chroma, [int(s) for s in starts[nonempty]], aggregate=np.median, pad=True
        )
        if synced.shape[1] == int(nonempty.sum()) + 1:  # drop the part before the first boundary
            synced = synced[:, 1:]
        out[:, nonempty] = synced

    norms = np.linalg.norm(out, axis=0)
    nz = norms > 0
    out[:, nz] /= norms[nz]
    silent = ~nz

    sample_idx = np.clip(np.round(np.asarray(boundaries) * sr).astype(int), 0, y.size)
    sample_end = np.append(sample_idx[1:], y.size)
    for j in range(n_units):
        seg = y[sample_idx[j] : sample_end[j]]
        if seg.size == 0:
            silent[j] = True
            continue
        rms = float(np.sqrt(np.mean(np.square(seg, dtype=np.float64))))
        if 20.0 * np.log10(max(rms, 1e-12)) < SILENCE_DB:
            silent[j] = True
    return out, silent


def _templates() -> FloatArray:
    t = np.zeros((_N_INDEX, 12), dtype=np.float64)
    for root in range(12):
        for k, third in enumerate((4, 3)):
            for pc in (0, third, 7):
                t[12 * k + root, (root + pc) % 12] = 1.0
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    return t


def label_probabilities(chroma: FloatArray, silent: npt.NDArray[np.bool_]) -> FloatArray:
    """Softmax over 25 states per unit: 12 major, 12 minor, N (C9)."""
    n = chroma.shape[1]
    norms = np.linalg.norm(chroma, axis=0)
    unit = chroma / np.where(norms > 0, norms, 1.0)
    score = np.zeros((_N_STATES, n), dtype=np.float64)
    score[:_N_INDEX] = _templates() @ unit
    score[_N_INDEX] = N_SCORE
    score[:, silent] = 0.0
    score[_N_INDEX, silent] = 1.0
    z = score * TEMPERATURE
    z -= z.max(axis=0, keepdims=True)
    e = np.exp(z)
    result: FloatArray = e / e.sum(axis=0, keepdims=True)
    return result


def smooth(prob: FloatArray, unit_slots: int) -> list[int]:
    """Viterbi path over the label probabilities (C10)."""
    p_stay = P_STAY if unit_slots >= 4 else P_STAY_SHORT
    path = librosa.sequence.viterbi(prob, librosa.sequence.transition_loop(_N_STATES, p_stay))
    return [int(s) for s in path]


def _label(state: int) -> ChordLabel:
    if state == _N_INDEX:
        return NO_CHORD
    return ChordLabel(state % 12, state >= 12)


def recognize(clip: AudioClip, rhythm: RhythmInfo, unit_slots: int) -> tuple[ChordLabel, ...]:
    """One chord label per strum unit, starting at grid beat 0 (C7-C10a)."""
    boundaries = unit_boundaries(rhythm, unit_slots, clip.duration_s)
    chroma, silent = chroma_per_unit(clip, boundaries)
    states = smooth(label_probabilities(chroma, silent), unit_slots)
    labels = tuple(_label(s) for s in states)
    if all(label == NO_CHORD for label in labels):
        raise ProcessingError(_NO_CHORD_MESSAGE)
    return labels


def detect_key(labels: Sequence[ChordLabel]) -> MusicKey:
    """Key whose Krumhansl-Kessler profile best matches the chord histogram (C12)."""
    hist = np.zeros(12, dtype=np.float64)
    for label in labels:
        if label.root is None:
            continue
        third = 3 if label.minor else 4
        for interval in (0, third, 7):
            hist[(label.root + interval) % 12] += 1.0
        hist[label.root] += 0.5
    if not hist.any() or np.ptp(hist) == 0:
        return MusicKey(0, False)
    best = MusicKey(0, False)
    best_r = -2.0
    # Order major before minor, low tonic first: strict ">" keeps the first on ties.
    for minor, profile in ((False, _KK_MAJOR), (True, _KK_MINOR)):
        for tonic in range(12):
            rotated = np.roll(np.asarray(profile), tonic)
            r = float(np.corrcoef(hist, rotated)[0, 1])
            if r > best_r + 1e-12:
                best, best_r = MusicKey(tonic, minor), r
    return best


MIN_CHANGES_FOR_BAR_SEARCH = 4
BAR_SCORE_MARGIN = 1.2


def changes(labels: Sequence[ChordLabel]) -> list[int]:
    """Unit indices where a chord starts: not N and different from the previous unit (C11)."""
    return [
        j
        for j, label in enumerate(labels)
        if label != NO_CHORD and (j == 0 or label != labels[j - 1])
    ]


def _chord_downbeat(
    labels: Sequence[ChordLabel], rhythm: RhythmInfo, unit_slots: int, bar_slots: int
) -> int:
    change_units = changes(labels)
    if len(change_units) < MIN_CHANGES_FOR_BAR_SEARCH:
        return rhythm.downbeat_slot
    step = 4 if bar_slots % 4 == 0 else 2
    scores = sorted(
        (
            (sum(1 for j in change_units if (j * unit_slots) % bar_slots == o), -o, o)
            for o in range(0, bar_slots, step)
        ),
        reverse=True,
    )
    best = scores[0][0]
    second = scores[1][0] if len(scores) > 1 else 0
    if best >= MIN_CHANGES_FOR_BAR_SEARCH and best >= BAR_SCORE_MARGIN * second:
        return scores[0][2]
    return rhythm.downbeat_slot


def bar_start(
    labels: Sequence[ChordLabel], rhythm: RhythmInfo, unit_slots: int, pickup_given: bool
) -> tuple[int, int]:
    """Grid slot where bar 1 starts and the count of leading N units dropped (C11)."""
    bar_slots = rhythm.time_signature.bar_slots
    if pickup_given:
        bar1 = rhythm.downbeat_slot
    else:
        bar1 = _chord_downbeat(labels, rhythm, unit_slots, bar_slots)
    first = next((j for j, label in enumerate(labels) if label != NO_CHORD), None)
    if first is None:
        return bar1, 0
    first_slot = first * unit_slots
    while bar1 > first_slot + PICKUP_TOLERANCE:
        bar1 -= bar_slots
    # Unlike quantize, skip whole bars of N before the first chord (a drum or spoken intro):
    # a chord chart has nothing to show there.
    while bar1 + bar_slots <= first_slot + PICKUP_TOLERANCE:
        bar1 += bar_slots
    dropped = sum(1 for j in range(first) if j * unit_slots < bar1)
    return bar1, dropped


def build_tab(
    labels: Sequence[ChordLabel],
    key: MusicKey,
    unit_slots: int,
    bar1_slot: int,
    rhythm: RhythmInfo,
    capo: int,
    title: str,
) -> tuple[TabScore, dict[int, ChordDiagram], int]:
    """Tab with one slot per strum unit, chord diagrams at changes and the change count (C16)."""
    bar_slots = rhythm.time_signature.bar_slots
    change_set = set(changes(labels))
    slots: list[TabSlot] = []
    diagrams: dict[int, ChordDiagram] = {}
    change_count = 0
    for j, label in enumerate(labels):
        if j * unit_slots < bar1_slot:
            continue
        start = j * unit_slots - bar1_slot
        if label.root is None:
            slots.append(TabSlot(start, unit_slots))
            continue
        chord_shape = shape((label.root - capo) % 12, label.minor)
        notes = tuple(
            TabNote(STANDARD_TUNING.strings[5 - i] + fret + capo, 6 - i, fret + capo)
            for i, fret in enumerate(chord_shape.frets)
            if fret != -1
        )
        slots.append(TabSlot(start, unit_slots, notes))
        if j in change_set:
            change_count += 1
            diagrams[start] = ChordDiagram(
                chord_name(label, key, capo), label, chord_shape, chord_sharp(label, key, capo)
            )
    total = sum(s.length for s in slots)
    if total % bar_slots:
        slots.append(TabSlot(total, bar_slots - total % bar_slots))
    return TabScore(rhythm, STANDARD_TUNING, tuple(slots), title), diagrams, change_count
