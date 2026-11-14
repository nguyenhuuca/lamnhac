import math
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from lamnhac.chords import (
    chroma_per_unit,
    detect_key,
    label_probabilities,
    recognize,
    smooth,
    unit_boundaries,
)
from lamnhac.errors import ProcessingError
from lamnhac.models import (
    NO_CHORD,
    SAMPLE_RATE,
    AudioClip,
    ChordLabel,
    MusicKey,
    RhythmInfo,
    TimeSignature,
)

C = ChordLabel(0, False)
G = ChordLabel(7, False)
AM = ChordLabel(9, True)
F = ChordLabel(5, False)


def _rhythm(duration_s: float, interval: float = 0.5) -> RhythmInfo:
    n = int(duration_s / interval) + 2
    beats = tuple(i * interval for i in range(n))
    return RhythmInfo(120.0, beats, 0, TimeSignature(4, 4), "detected")


def _clip(samples: npt.NDArray[np.float32]) -> AudioClip:
    return AudioClip(samples, SAMPLE_RATE, len(samples) / SAMPLE_RATE, Path("dummy.wav"))


def _chroma_for(states: list[int], seed: int = 0) -> npt.NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    cols = []
    for s in states:
        v = np.zeros(12)
        root = s % 12
        third = 3 if s >= 12 else 4
        for pc in (0, third, 7):
            v[(root + pc) % 12] = 1.0
        v += rng.uniform(0, 0.25, 12)
        cols.append(v / np.linalg.norm(v))
    return np.stack(cols, axis=1)


def _decode(states: list[int]) -> list[ChordLabel]:
    return [NO_CHORD if s == 24 else ChordLabel(s % 12, s >= 12) for s in states]


def test_known_sequence_exact_labels() -> None:
    seq = [0, 0, 7, 7, 21, 21, 5, 5]  # C C G G Am Am F F
    chroma = _chroma_for(seq)
    silent = np.zeros(len(seq), dtype=np.bool_)
    path = smooth(label_probabilities(chroma, silent), 4)
    assert _decode(path) == [C, C, G, G, AM, AM, F, F]


def test_odd_unit_is_smoothed_away() -> None:
    chroma = _chroma_for([0] * 8)
    # a unit leaning towards G but still containing C: strong enough to be noise, not a change
    chroma[:, 4] = 0.55 * chroma[:, 4] + 0.45 * _chroma_for([7])[:, 0]
    chroma[:, 4] /= np.linalg.norm(chroma[:, 4])
    silent = np.zeros(8, dtype=np.bool_)
    path = smooth(label_probabilities(chroma, silent), 4)
    assert _decode(path) == [C] * 8


def test_silent_and_zero_columns_are_n() -> None:
    chroma = _chroma_for([0, 0, 0, 0])
    chroma[:, 2] = 0.0
    silent = np.array([False, False, True, False])
    prob = label_probabilities(chroma, silent)
    assert prob.shape == (25, 4)
    assert np.allclose(prob.sum(axis=0), 1.0)
    assert int(np.argmax(prob[:, 2])) == 24
    zero_only = label_probabilities(np.zeros((12, 1)), np.array([True]))
    assert smooth(zero_only, 4) == [24]


def _triad(freqs: list[float], seconds: float, detune: float) -> npt.NDArray[np.float64]:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    out = np.zeros_like(t)
    for f in freqs:
        out += 0.2 * np.sin(2 * np.pi * f * detune * t)
    return out


def _song(detune: float) -> npt.NDArray[np.float32]:
    c = _triad([130.81, 164.81, 196.00, 261.63], 2.0, detune)
    am = _triad([110.00, 130.81, 164.81, 220.00], 2.0, detune)
    return np.concatenate([c, am]).astype(np.float32)


@pytest.mark.parametrize("cents", [0.0, 30.0])
def test_recognize_c_then_am(cents: float) -> None:
    clip = _clip(_song(2 ** (cents / 1200)))
    labels = recognize(clip, _rhythm(clip.duration_s), 4)
    assert len(labels) == 8
    assert all(lab == C for lab in labels[:3])
    assert all(lab == AM for lab in labels[5:])


def test_all_silent_raises() -> None:
    clip = _clip(np.zeros(SAMPLE_RATE * 4, dtype=np.float32))
    with pytest.raises(ProcessingError, match="không nhận được hợp âm nào"):
        recognize(clip, _rhythm(clip.duration_s), 4)


def test_unit_boundaries_count_and_limit() -> None:
    b = unit_boundaries(_rhythm(10.0), 4, 3.2)
    assert len(b) == math.ceil(3.2 / 0.5)
    assert b[:3] == pytest.approx([0.0, 0.5, 1.0])
    assert all(t < 3.2 for t in b)


def test_unit_boundaries_half_beats() -> None:
    b = unit_boundaries(_rhythm(10.0), 2, 2.0)
    assert b == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75])


def test_chroma_per_unit_columns_when_last_boundary_near_end() -> None:
    clip = _clip(_song(1.0)[: SAMPLE_RATE * 2])
    boundaries = [0.0, 0.5, 1.0, 1.5, clip.duration_s - 1e-4]
    chroma, silent = chroma_per_unit(clip, boundaries)
    assert chroma.shape == (12, 5)
    assert silent.shape == (5,)
    assert not silent[:4].any()


DM = ChordLabel(2, True)
E = ChordLabel(4, False)
D = ChordLabel(2, False)
EM = ChordLabel(4, True)


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        ([C, G, AM, F] * 4, MusicKey(0, False)),
        ([AM, DM, E, AM] * 4, MusicKey(9, True)),
        ([G, D, EM, C] * 4, MusicKey(7, False)),
        ([NO_CHORD] * 4, MusicKey(0, False)),
        ([], MusicKey(0, False)),
    ],
)
def test_detect_key(labels: list[ChordLabel], expected: MusicKey) -> None:
    assert detect_key(labels) == expected
