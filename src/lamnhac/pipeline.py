"""convert pipeline: audio -> notes -> rhythm -> tab -> files (spec B14, B19, B21)."""

import logging
import sys
import time
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path

from lamnhac import audio, export_gp5, export_musicxml, rhythm, tab, transcribe
from lamnhac.errors import OutputError
from lamnhac.models import ConvertOptions, ConvertResult, Format, TabScore

log = logging.getLogger("lamnhac")

_STEPS = 6


_WRITERS: dict[Format, tuple[str, Callable[[TabScore, Path], None]]] = {
    "gp5": ("gp5", export_gp5.write),
    "musicxml": ("musicxml", export_musicxml.write),
}


def _prepare_outputs(opts: ConvertOptions) -> list[tuple[Format, Path]]:
    stem = opts.input.stem
    targets = [
        (fmt, opts.out_dir / f"{stem}.{_WRITERS[fmt][0]}")
        for fmt in sorted(opts.formats)  # gp5 before musicxml: stable order
    ]
    try:
        opts.out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputError(f"không tạo được thư mục đầu ra: {opts.out_dir}") from exc
    if not opts.force:
        for _, path in targets:
            if path.exists():
                raise OutputError(f"file đã tồn tại: {path} (dùng --force để ghi đè)")
    return targets


def convert(opts: ConvertOptions, progress: Callable[[str], None]) -> ConvertResult:
    targets = _prepare_outputs(opts)  # B14: before any processing

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
            clip, opts.tuning, filter_harmonics=opts.filter_harmonics
        )
    done("transcribe", t)

    t = step(3, "phân tích nhịp")
    info = rhythm.analyze(clip, notes, opts.tempo, opts.time_signature)
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
            _WRITERS[fmt][1](tab_score, path)
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
