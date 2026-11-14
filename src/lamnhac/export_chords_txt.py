"""Plain-text chord chart: four bars per line (spec C18)."""

import os
from pathlib import Path

from lamnhac.errors import OutputError
from lamnhac.models import ChordChart
from lamnhac.names import chord_name, key_name

BARS_PER_LINE = 4


def _bars(chart: ChordChart) -> list[str]:
    bar_slots = chart.rhythm.time_signature.bar_slots
    bars: list[list[str]] = []
    for j, label in enumerate(chart.labels):
        start = j * chart.unit_slots
        if start < chart.bar1_slot:
            continue
        index = (start - chart.bar1_slot) // bar_slots
        while len(bars) <= index:
            bars.append([])
        if label.root is None:
            continue
        name = chord_name(label, chart.key, chart.capo)
        if not bars[index] or bars[index][-1] != name:
            bars[index].append(name)
    return [" ".join(names) if names else "-" for names in bars]


def render(chart: ChordChart, title: str) -> str:
    """Return the chord chart text: two header lines, a blank line, bar lines."""
    ts = chart.rhythm.time_signature
    info = (
        f"# giọng: {key_name(chart.key)} · tempo: {round(chart.rhythm.tempo_bpm)} BPM"
        f" · nhịp: {ts.numerator}/{ts.denominator}"
    )
    if chart.capo > 0:
        info += f" · capo {chart.capo}"
    bars = _bars(chart)
    lines = [
        "| " + " | ".join(bars[i : i + BARS_PER_LINE]) + " |"
        for i in range(0, len(bars), BARS_PER_LINE)
    ]
    return "\n".join([f"# {title}", info, "", *lines]) + "\n"


def write(chart: ChordChart, title: str, path: Path) -> None:
    """Write the chart to ``path`` atomically; any failure becomes ``OutputError``."""
    tmp = path.with_name(f"{path.stem}.tmp-{os.getpid()}.txt")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(render(chart, title))
        os.replace(tmp, path)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise OutputError(f"cannot write chord chart: {exc}") from exc
