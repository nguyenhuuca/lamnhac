"""convert pipeline: audio -> notes -> rhythm -> tab -> files (spec B14, B19, B21)."""

import logging
import sys
import time
from collections.abc import Callable, Sequence
from contextlib import redirect_stdout
from pathlib import Path
from typing import cast

from lamnhac import (
    audio,
    export_chords_txt,
    export_gp5,
    export_musicxml,
    rhythm,
    tab,
    transcribe,
)
from lamnhac import (
    chords as chords_mod,
)
from lamnhac.errors import OutputError
from lamnhac.models import (
    ChordChart,
    ChordFormat,
    ChordsOptions,
    ChordsResult,
    ConvertOptions,
    ConvertResult,
    Format,
    TabScore,
)

log = logging.getLogger("lamnhac")

_STEPS = 6


_WRITERS: dict[Format, tuple[str, Callable[[TabScore, Path], None]]] = {
    "gp5": ("gp5", export_gp5.write),
    "musicxml": ("musicxml", export_musicxml.write),
}


def _prepare_outputs(
    out_dir: Path, stem: str, targets: Sequence[tuple[str, str]], force: bool
) -> list[tuple[str, Path]]:
    """Create ``out_dir`` and refuse to overwrite unless ``force``; targets are (format, suffix)."""
    paths = [(fmt, out_dir / f"{stem}{suffix}") for fmt, suffix in targets]
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputError(f"không tạo được thư mục đầu ra: {out_dir}") from exc
    if not force:
        for _, path in paths:
            if path.exists():
                raise OutputError(f"file đã tồn tại: {path} (dùng --force để ghi đè)")
    return paths


def convert(opts: ConvertOptions, progress: Callable[[str], None]) -> ConvertResult:
    # B14: before any processing; gp5 before musicxml: stable order
    targets = _prepare_outputs(
        opts.out_dir,
        opts.input.stem,
        [(fmt, f".{_WRITERS[fmt][0]}") for fmt in sorted(opts.formats)],
        opts.force,
    )

    def step(k: int, label: str) -> float:
        progress(f"[{k}/{_STEPS}] {label}…")
        return time.perf_counter()

    def done(label: str, started: float) -> None:
        log.debug("step %s took %.2fs", label, time.perf_counter() - started)

    t = step(1, "đọc audio")
    clip = audio.load(opts.input)
    done("load", t)

    t = step(2, "nhận nốt")
    with redirect_stdout(sys.stderr):  # basic-pitch print()s to stdout; stdout is for paths only
        notes, warnings = transcribe.transcribe(
            clip,
            opts.tuning,
            filter_harmonics=opts.filter_harmonics,
            sensitivity=opts.sensitivity,
        )
    done("transcribe", t)

    t = step(3, "phân tích nhịp")
    info = rhythm.analyze(clip, notes, opts.tempo, opts.time_signature, opts.pickup_slots)
    done("analyze", t)
    if info.tempo_source == "detected":
        progress(f"tempo đoán được: {round(info.tempo_bpm)} BPM (dùng --tempo để sửa)")

    t = step(4, "lượng tử hoá")
    score = rhythm.quantize(notes, info)
    done("quantize", t)

    t = step(5, "gán tab")
    tab_score, tab_warnings = tab.assign(
        score, opts.tuning, title=opts.input.stem, max_fret=opts.max_fret
    )
    warnings += tab_warnings
    done("assign", t)

    t = step(6, "xuất file")
    outputs: list[Path] = []
    errors: list[str] = []
    for fmt, path in targets:
        try:
            _WRITERS[cast(Format, fmt)][1](tab_score, path)
            outputs.append(path)
        except OutputError as exc:
            log.debug("export %s failed: %s", fmt, exc)
            errors.append(f"{fmt}: {exc}")
    done("export", t)

    return ConvertResult(
        outputs=tuple(outputs),
        errors=tuple(errors),
        warnings=tuple(warnings),
        rhythm=info,
        note_count=len(notes),
    )


_CHORD_STEPS = 4
_CHORD_SUFFIXES: dict[ChordFormat, str] = {"gp5": ".chords.gp5", "txt": ".chords.txt"}


def chords(opts: ChordsOptions, progress: Callable[[str], None]) -> ChordsResult:
    """Song -> chord chart -> ``.chords.gp5`` / ``.chords.txt`` (spec C1-C4)."""
    # C2: outputs are checked before any processing; gp5 before txt.
    targets = _prepare_outputs(
        opts.out_dir,
        opts.input.stem,
        [(fmt, _CHORD_SUFFIXES[fmt]) for fmt in ("gp5", "txt") if fmt in opts.formats],
        opts.force,
    )
    stem = opts.input.stem

    def step(k: int, label: str) -> float:
        progress(f"[{k}/{_CHORD_STEPS}] {label}…")
        return time.perf_counter()

    def done(label: str, started: float) -> None:
        log.debug("step %s took %.2fs", label, time.perf_counter() - started)

    t = step(1, "đọc audio")
    clip = audio.load(opts.input)
    done("load", t)

    t = step(2, "phân tích nhịp")
    info = rhythm.analyze(
        clip, rhythm.onsets(clip), opts.tempo, opts.time_signature, opts.pickup_slots
    )
    done("analyze", t)
    if info.tempo_source == "detected":
        progress(f"tempo đoán được: {round(info.tempo_bpm)} BPM (dùng --tempo để sửa)")
    unit_slots = 16 // opts.time_signature.denominator

    t = step(3, "nhận hợp âm")
    labels = chords_mod.recognize(clip, info, unit_slots)
    key = chords_mod.detect_key(labels)
    bar1, dropped = chords_mod.bar_start(
        labels, info, unit_slots, pickup_given=opts.pickup_slots is not None
    )
    warnings: list[str] = []
    if dropped > 0:
        warnings.append(f"bỏ {dropped} phách không có hợp âm ở đầu bài")
    tab_score, diagrams, change_count = chords_mod.build_tab(
        labels, key, unit_slots, bar1, info, opts.capo, stem
    )
    chart = ChordChart(info, key, unit_slots, labels, bar1, opts.capo)
    done("recognize", t)

    t = step(4, "xuất file")
    outputs: list[Path] = []
    errors: list[str] = []
    for fmt, path in targets:
        try:
            if fmt == "gp5":
                export_gp5.write(tab_score, path, diagrams, key, opts.capo)
            else:
                export_chords_txt.write(chart, stem, path)
            outputs.append(path)
        except OutputError as exc:
            log.debug("export %s failed: %s", fmt, exc)
            errors.append(f"{fmt}: {exc}")
    done("export", t)

    return ChordsResult(
        outputs=tuple(outputs),
        errors=tuple(errors),
        warnings=tuple(warnings),
        chart=chart,
        change_count=change_count,
    )
