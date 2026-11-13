# Tech Strategy

The project's chosen technologies. Suggest an alternative only when the owner asks for one; otherwise build with what is listed here, at the latest stable version unless a version is pinned.

The installer fills the sections below from the stack packs it detected (`npx github:nguyenhuuca/agentic-sdlc init`). The owner confirms them with `/welcome`, which the first session offers; edit them freely afterwards: `update` never overwrites a file you changed.

<!-- sdlc:status confirmed 2026-11-13 -->

## Stack

<!-- sdlc:stack -->
| Area | Choice |
|------|--------|
| Language | Python 3.11 (pinned: basic-pitch 0.4.0 does not support 3.12; ADR-0001) |
| Project and packages | uv (`pyproject.toml` + `uv.lock`) |
| App type | Offline CLI on Windows (`lamnhac convert`), argparse |
| Note transcription | basic-pitch 0.4.0 (TensorFlow < 2.15.1 on Windows; ADR-0001) |
| Audio decode, tempo, beats | librosa |
| Guitar Pro export | PyGuitarPro 0.11 (`.gp5`; ADR-0001) |
| MusicXML export | music21 10.x (ADR-0001) |
| Tests | pytest; mir_eval for Note F1 |
| Lint, format, types | Ruff (lint + format), mypy `--strict` |
| Database | None |
| Deployment | None: runs locally with `uv run` |
<!-- /sdlc:stack -->

## Not Allowed

<!-- sdlc:prohibited -->
- No network calls at runtime: the tool runs fully offline (PRD R9).
- No `pip install` or hand-written `requirements.txt`: dependencies change only through `uv add` and `uv.lock`.
- No Python upgrade past 3.11 without a new ADR (basic-pitch compatibility).
<!-- /sdlc:prohibited -->
