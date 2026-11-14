"""Generate deterministic audio fixtures (Karplus-Strong plucks) with ground-truth JSON.

Run from the repository root:

    uv run python tests/fixtures/make_fixtures.py

Writes scale_c, riff_97bpm, power_chord and chords_cgamf (.mp3 + .json) and stereo_short.mp3
next to this file.
"""

import json
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf

SR = 22050
SEED = 1234
OUT = Path(__file__).parent

Note = tuple[float, float, int, float]  # onset_s, offset_s, midi pitch, amplitude


def pluck(midi: int, dur_s: float, rng: np.random.Generator) -> npt.NDArray[np.float64]:
    """Karplus-Strong plucked string."""
    freq = 440.0 * 2 ** ((midi - 69) / 12)
    n = int(SR * dur_s)
    period = SR / freq
    size = int(period)
    frac = period - size
    buf = rng.uniform(-1.0, 1.0, size + 1)
    out = np.zeros(n)
    prev = 0.0
    for i in range(n):
        j = i % (size + 1)
        nxt = buf[(j + 1) % (size + 1)]
        cur = 0.996 * 0.5 * (buf[j] + nxt)
        buf[j] = cur
        # first-order allpass-free fractional tuning approximation via linear blend
        out[i] = cur * (1 - frac) + prev * frac
        prev = cur
    fade = min(int(0.02 * SR), n)
    out[-fade:] *= np.linspace(1.0, 0.0, fade)
    return out


def render(notes: list[Note], total_s: float, rng: np.random.Generator) -> npt.NDArray[np.float32]:
    mix = np.zeros(int(total_s * SR))
    for onset, offset, pitch, amp in notes:
        tone = pluck(pitch, offset - onset, rng) * amp
        start = int(onset * SR)
        mix[start : start + tone.size] += tone[: mix.size - start]
    peak = np.max(np.abs(mix))
    return (mix / peak * 0.8).astype(np.float32)


def write_mp3(path: Path, data: npt.NDArray[np.float32]) -> None:
    sf.write(str(path), data, SR, format="MP3")


def dump(path: Path, meta: dict[str, object]) -> None:
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def notes_json(notes: list[Note]) -> list[dict[str, float | int]]:
    return [
        {"onset_s": round(on, 4), "offset_s": round(off, 4), "pitch": p} for on, off, p, _ in notes
    ]


def make_scale(rng: np.random.Generator) -> None:
    pitches = [48, 50, 52, 53, 55, 57, 59, 60]
    notes: list[Note] = [(0.5 * i, 0.5 * i + 0.45, p, 1.0) for i, p in enumerate(pitches)]
    write_mp3(OUT / "scale_c.mp3", render(notes, 4.5, rng))
    dump(OUT / "scale_c.json", {"tempo_bpm": 120, "notes": notes_json(notes)})


def make_riff(rng: np.random.Generator) -> None:
    bpm = 97
    beat = 60.0 / bpm
    # (beat position, length in beats, pitches); 4 bars of 4/4
    pattern: list[tuple[float, float, tuple[int, ...]]] = [
        (0, 1, (40,)),
        (1, 0.5, (47,)),
        (1.5, 0.5, (52,)),
        (2, 1, (45, 52)),  # dyad
        (3, 0.5, (50,)),
        (3.5, 0.5, (52,)),
        (4, 1, (43,)),
        (5, 0.5, (50,)),
        (5.5, 0.5, (55,)),
        (6, 1, (47,)),
        (7, 1, (52,)),
        (8, 1, (45,)),
        (9, 0.5, (52,)),
        (9.5, 0.5, (57,)),
        (10, 1, (48, 55, 64)),  # chord
        (11, 1, (59,)),
        (12, 1, (40,)),
        (13, 0.5, (47,)),
        (13.5, 0.5, (52,)),
        (14, 1, (52,)),
        (15, 1, (64,)),
    ]
    notes: list[Note] = []
    for pos, length, chord in pattern:
        amp = 1.0 if pos % 4 == 0 else 0.6  # accent on each bar's beat 1
        for p in chord:
            notes.append((pos * beat, pos * beat + length * beat * 0.9, p, amp))
    total = 16 * beat  # ~9.9 s of notes + tail
    total_s = max(total + 0.5, 12.0)
    write_mp3(OUT / "riff_97bpm.mp3", render(notes, total_s, rng))
    dump(
        OUT / "riff_97bpm.json",
        {
            "tempo_bpm": bpm,
            "time_signature": [4, 4],
            "downbeat_time_s": 0.0,
            "notes": notes_json(notes),
        },
    )


def make_stereo(rng: np.random.Generator) -> None:
    left = render([(0.0, 0.9, 52, 1.0)], 1.0, rng)
    right = render([(0.0, 0.9, 64, 1.0)], 1.0, rng)
    sf.write(str(OUT / "stereo_short.mp3"), np.stack([left, right], axis=1), SR, format="MP3")


def make_power_chord(rng: np.random.Generator) -> None:
    """E2+B2+E3 struck together at equal amplitude, 4 times: E3 is a real note, not an overtone."""
    notes: list[Note] = [(0.8 * i, 0.8 * i + 0.7, p, 1.0) for i in range(4) for p in (40, 47, 52)]
    write_mp3(OUT / "power_chord.mp3", render(notes, 4.0, rng))
    dump(OUT / "power_chord.json", {"notes": notes_json(notes)})


def make_chords_cgamf(rng: np.random.Generator) -> None:
    """C-G-Am-F, one chord per 4/4 bar at 100 BPM: strummed triads, bass, kick and a sine melody."""
    bpm = 100
    beat = 60.0 / bpm
    bars = 4
    lead = 0.15  # the beat tracker needs an onset after t=0 to keep the first beat
    total_s = lead + bars * 4 * beat
    triads = {"C": (0, 4, 7), "G": (7, 11, 14), "Am": (9, 12, 16), "F": (5, 9, 12)}
    roots = {"C": 0, "G": 7, "Am": 9, "F": 5}
    # melody per bar: chord tones plus one passing non-chord tone (octave 5, C5 = 72)
    melody = {
        "C": (76, 79, 74, 72),
        "G": (74, 79, 77, 71),
        "Am": (76, 72, 74, 69),
        "F": (72, 77, 76, 69),
    }
    notes: list[Note] = []
    for bar, name in enumerate(["C", "G", "Am", "F"]):
        for b in range(4):
            on = lead + (bar * 4 + b) * beat
            for iv in triads[name]:
                notes.append((on, on + beat * 0.95, 60 + iv, 1.0))
            notes.append((on, on + beat * 0.95, 48 + roots[name], 0.4))
            if b % 2 == 0:
                notes.append((on, on + beat * 1.9, 36 + roots[name], 0.6))
    mix = render(notes, total_s, rng).astype(np.float64)
    t_kick = np.arange(int(0.08 * SR)) / SR
    kick = 0.5 * np.sin(2 * np.pi * 60 * t_kick) * np.exp(-t_kick / 0.03)
    for i in range(bars * 4):
        start = int((lead + i * beat) * SR)
        mix[start : start + kick.size] += kick
    for bar, name in enumerate(["C", "G", "Am", "F"]):
        for b, midi in enumerate(melody[name]):
            start = int((lead + (bar * 4 + b) * beat) * SR)
            n = int(beat * 0.9 * SR)
            t = np.arange(n) / SR
            tone = 0.08 * np.sin(2 * np.pi * 440.0 * 2 ** ((midi - 69) / 12) * t)
            tone *= np.minimum(1.0, np.minimum(t / 0.01, (n / SR - t) / 0.02))
            mix[start : start + n] += tone
    mix = mix / np.max(np.abs(mix)) * 0.8
    write_mp3(OUT / "chords_cgamf.mp3", mix.astype(np.float32))
    dump(
        OUT / "chords_cgamf.json",
        {
            "tempo_bpm": bpm,
            "time_signature": [4, 4],
            "chords": ["C", "G", "Am", "F"],
            "key": "C",
        },
    )


def main() -> None:
    rng = np.random.default_rng(SEED)
    make_scale(rng)
    make_riff(rng)
    make_stereo(rng)
    make_power_chord(rng)  # last: keeps the rng stream of the fixtures above unchanged
    make_chords_cgamf(rng)


if __name__ == "__main__":
    main()
