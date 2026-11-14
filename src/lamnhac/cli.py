"""Command line entry point: ``lamnhac convert`` and ``lamnhac chords``."""

import argparse
import io
import logging
import sys
import time
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar

from lamnhac import export_chords_txt, pipeline
from lamnhac.errors import LamnhacError
from lamnhac.models import ChordFormat, ChordsOptions, ConvertOptions, Format, TimeSignature
from lamnhac.names import key_name
from lamnhac.tab import parse_tuning

_F = TypeVar("_F", bound=str)
_FORMATS: tuple[Format, ...] = ("gp5", "musicxml")
_DEFAULT_FORMAT = "gp5,musicxml"
_CHORD_FORMATS: tuple[ChordFormat, ...] = ("gp5", "txt")
_DEFAULT_CHORD_FORMAT = "gp5"


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--out-dir", type=Path, help="default: directory of the input")
    p.add_argument("--tempo", type=float, help="quarter-note BPM, 30-300 (default: detect)")
    p.add_argument("--time", default="4/4", help="time signature N/D")
    p.add_argument(
        "--pickup",
        type=float,
        help="beats (of the --time denominator) before bar 1, e.g. 0, 1, 1.5 (default: detect)",
    )
    p.add_argument("--force", action="store_true", help="overwrite existing outputs")
    p.add_argument("-v", "--verbose", action="store_true", help="DEBUG logging, tracebacks")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lamnhac", description="MP3 guitar solo to tab.")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("convert", help="convert an MP3 to .gp5 / .musicxml")
    _add_common(c)
    c.add_argument("--format", default=_DEFAULT_FORMAT, help="comma list of gp5, musicxml")
    c.add_argument("--tuning", default="E A D G B E", help="6 note names, low to high")
    c.add_argument("--max-fret", type=int, default=24, help="highest fret used, 0-24")
    c.add_argument(
        "--filter-harmonics",
        action="store_true",
        help="drop overtone notes (good for single-note lines; may drop real octaves in chords)",
    )
    c.add_argument(
        "--sensitivity",
        choices=("low", "normal", "high"),
        default="normal",
        help="note detection: high catches more notes (and more junk), low fewer",
    )
    k = sub.add_parser("chords", help="extract a chord chart from an MP3 (.chords.gp5 / .txt)")
    _add_common(k)
    k.add_argument("--format", default=_DEFAULT_CHORD_FORMAT, help="comma list of gp5, txt")
    k.add_argument("--capo", type=int, default=0, help="capo fret, 0-11")
    return parser


def _parse_formats(text: str, allowed: tuple[_F, ...]) -> frozenset[_F]:
    names = [p.strip() for p in text.split(",")]
    chosen = [f for f in allowed if f in names]
    if len(chosen) != len(set(names)):
        raise ValueError(f"--format phải là danh sách con không rỗng của {', '.join(allowed)}")
    return frozenset(chosen)


def _parse_time(text: str) -> TimeSignature:
    num, sep, den = text.partition("/")
    if not sep or not num.isdecimal() or not den.isdecimal():
        raise ValueError(f"--time phải có dạng N/D, nhận được {text!r}")
    return TimeSignature(int(num), int(den))


def _parse_pickup(beats: float | None, time_sig: TimeSignature) -> int | None:
    """Pickup length in beats of the denominator note -> slots (sixteenths)."""
    if beats is None:
        return None
    slots = beats * 16 / time_sig.denominator
    if not (0 <= beats < time_sig.numerator and abs(slots - round(slots)) < 1e-9):
        raise ValueError(
            f"--pickup phải trong khoảng 0..{time_sig.numerator} (không gồm "
            f"{time_sig.numerator}) và là bội của một nốt móc kép, nhận được {beats:g}"
        )
    return round(slots)


def _options(parser: argparse.ArgumentParser, args: argparse.Namespace) -> ConvertOptions:
    try:
        if args.tempo is not None and not 30 <= args.tempo <= 300:  # also rejects NaN
            raise ValueError("--tempo phải nằm trong khoảng 30..300")
        if not 0 <= args.max_fret <= 24:
            raise ValueError("--max-fret phải nằm trong khoảng 0..24")
        formats = _parse_formats(args.format, _FORMATS)
        time_sig = _parse_time(args.time)
        tuning = parse_tuning(args.tuning)
        pickup_slots = _parse_pickup(args.pickup, time_sig)
    except ValueError as exc:
        parser.error(str(exc))  # exits with 2
    input_path: Path = args.input
    return ConvertOptions(
        input=input_path,
        out_dir=args.out_dir if args.out_dir is not None else input_path.resolve().parent,
        formats=formats,
        tempo=args.tempo,
        tuning=tuning,
        time_signature=time_sig,
        force=args.force,
        max_fret=args.max_fret,
        filter_harmonics=args.filter_harmonics,
        sensitivity=args.sensitivity,
        pickup_slots=pickup_slots,
    )


def _chords_options(parser: argparse.ArgumentParser, args: argparse.Namespace) -> ChordsOptions:
    try:
        if args.tempo is not None and not 30 <= args.tempo <= 300:  # also rejects NaN
            raise ValueError("--tempo phải nằm trong khoảng 30..300")
        if not 0 <= args.capo <= 11:
            raise ValueError("--capo phải nằm trong khoảng 0..11")
        formats = _parse_formats(args.format, _CHORD_FORMATS)
        time_sig = _parse_time(args.time)
        pickup_slots = _parse_pickup(args.pickup, time_sig)
    except ValueError as exc:
        parser.error(str(exc))  # exits with 2
    input_path: Path = args.input
    return ChordsOptions(
        input=input_path,
        out_dir=args.out_dir if args.out_dir is not None else input_path.resolve().parent,
        formats=formats,
        tempo=args.tempo,
        time_signature=time_sig,
        pickup_slots=pickup_slots,
        capo=args.capo,
        force=args.force,
    )


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _use_utf8() -> None:
    # Messages are Vietnamese; piped Windows streams default to a legacy code page.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def _report(outputs: Sequence[Path], warnings: Sequence[str], errors: Sequence[str]) -> None:
    for path in outputs:
        print(path, flush=True)
    for warning in warnings:
        print(f"cảnh báo: {warning}", file=sys.stderr)
    for error in errors:
        print(f"lỗi: {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    _use_utf8()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        opts = _chords_options(parser, args) if args.command == "chords" else _options(parser, args)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr, format="%(name)s %(message)s")
    started = time.perf_counter()
    try:
        if isinstance(opts, ChordsOptions):
            chords_result = pipeline.chords(opts, _progress)
        else:
            result = pipeline.convert(opts, _progress)
    except LamnhacError as exc:
        print(f"lỗi: {exc}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return exc.exit_code
    except Exception as exc:
        print(f"lỗi không lường trước: {type(exc).__name__}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1

    if isinstance(opts, ChordsOptions):
        _report(chords_result.outputs, chords_result.warnings, chords_result.errors)
        chart = chords_result.chart
        print(
            f"xong: {chords_result.change_count} lần đổi hợp âm, giọng {key_name(chart.key)}, "
            f"tempo {chart.rhythm.tempo_bpm:.0f} BPM ({chart.rhythm.tempo_source}), "
            f"{len(chords_result.warnings)} cảnh báo, {time.perf_counter() - started:.1f}s",
            file=sys.stderr,
        )
        print(export_chords_txt.render(chart, opts.input.stem), file=sys.stderr)
        return 5 if chords_result.errors else 0

    _report(result.outputs, result.warnings, result.errors)
    r = result.rhythm
    print(
        f"xong: {result.note_count} nốt, tempo {r.tempo_bpm:.0f} BPM ({r.tempo_source}), "
        f"{len(result.warnings)} cảnh báo, {time.perf_counter() - started:.1f}s",
        file=sys.stderr,
    )
    return 5 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
