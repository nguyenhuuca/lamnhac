"""Chord eval: chord accuracy and key accuracy against hand-written answers (spec C19-C21).

Put pairs `<name>.mp3` + `<name>.hopam.txt` (the chords of that recording, as in a chord
sheet) in `tests/fixtures/real/`. The folder is git-ignored. Run with
`uv run pytest -m eval -s tests/eval/test_eval_chords.py`.

The environment variable `LAMNHAC_EVAL_REAL_DIR` points the eval at another folder.
Optional comment lines in the answer file are passed to the tool:
`# time: 3/4`, `# tempo: 100`, `# pickup: 1` (beats, as `--pickup`). `# key: Am` is read by
`answers.py`. Output always goes to a temporary directory.
"""

import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from answers import Answer, Chord, accuracy, accuracy_transposed, chord_name, parse_answer

from lamnhac import audio, pipeline
from lamnhac.models import ChordsOptions, MusicKey, TimeSignature
from lamnhac.names import key_name

REAL = Path(
    os.environ.get("LAMNHAC_EVAL_REAL_DIR") or Path(__file__).parent.parent / "fixtures" / "real"
)
PAIRS = sorted(p for p in REAL.glob("*.mp3") if p.with_suffix(".hopam.txt").exists())
ACC_TARGET = 0.70  # spec C21
KEY_TARGET = 0.80  # PRD G2

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not PAIRS, reason=f"no <name>.mp3 + <name>.hopam.txt pairs in {REAL}"),
]

_DIRECTIVE = re.compile(r"^#\s*(time|tempo|pickup)\s*:\s*(\S+)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Outcome:
    acc: float
    key: MusicKey
    ref_key: Chord | None


_cache: dict[Path, Outcome] = {}


def _directives(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        m = _DIRECTIVE.match(line.strip())
        if m:
            found[m.group(1).lower()] = m.group(2)
    return found


def _options(mp3: Path, out_dir: Path, text: str) -> ChordsOptions:
    d = _directives(text)
    time_sig = TimeSignature(4, 4)
    if "time" in d:
        num, den = d["time"].split("/")
        time_sig = TimeSignature(int(num), int(den))
    pickup_slots = None
    if "pickup" in d:
        slots = float(d["pickup"]) * 16 / time_sig.denominator
        pickup_slots = round(slots)
    return ChordsOptions(
        input=mp3,
        out_dir=out_dir,
        formats=frozenset({"txt"}),
        tempo=float(d["tempo"]) if "tempo" in d else None,
        time_signature=time_sig,
        pickup_slots=pickup_slots,
        capo=0,
        force=True,
    )


def _run(mp3: Path, out_dir: Path) -> Outcome:
    if mp3 in _cache:
        return _cache[mp3]
    text = mp3.with_suffix(".hopam.txt").read_text(encoding="utf-8")
    answer: Answer = parse_answer(text)
    start = time.perf_counter()
    result = pipeline.chords(_options(mp3, out_dir, text), progress=lambda _m: None)
    secs = time.perf_counter() - start
    est: list[Chord | None] = [(c.root, c.minor) for c in result.chart.labels if c.root is not None]
    acc = accuracy(answer.chords, est)
    acc_t = accuracy_transposed(answer.chords, est)
    ref_name = chord_name(answer.key) if answer.key else "?"
    line = (
        f"\n{mp3.stem}: acc {acc:.3f} acc_transposed {acc_t:.3f} "
        f"key {key_name(result.chart.key)} (ref {ref_name}) {secs:.1f}s "
        f"audio {audio.load(mp3).duration_s:.1f}s"
    )
    # A cp1252 console cannot show Vietnamese letters; degrade instead of failing the test.
    enc = sys.stdout.encoding or "utf-8"
    print(line.encode(enc, "replace").decode(enc))
    outcome = Outcome(acc, result.chart.key, answer.key)
    _cache[mp3] = outcome
    return outcome


@pytest.mark.parametrize("mp3", PAIRS, ids=[p.stem for p in PAIRS])
def test_chord_accuracy(mp3: Path, tmp_path: Path) -> None:
    assert _run(mp3, tmp_path).acc >= ACC_TARGET


def test_key_accuracy_over_set(tmp_path: Path) -> None:
    outcomes = [_run(p, tmp_path) for p in PAIRS]
    keyed = [o for o in outcomes if o.ref_key is not None]
    if not keyed:
        pytest.skip("no answer file has a `# key:` line")
    right = sum(o.ref_key == (o.key.tonic, o.key.minor) for o in keyed)
    print(f"\nkey accuracy {right}/{len(keyed)}")
    assert right / len(keyed) >= KEY_TARGET
