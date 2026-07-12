# Contributing to WhiteLee

## The highest-value contribution: a new game adapter

1. Read `whitelee/adapters/base.py` — the contract is one method,
   `extract(source, protagonist_hint) -> ExtractionResult`.
2. Copy `whitelee/adapters/dota2_opendota.py` as a template.
3. Map your game's events onto the `EventKind` vocabulary in
   `whitelee/core/schema.py`. Resist adding new kinds — nuance belongs in
   `summary` and `data`. Set `protagonist_involved` and `importance`
   carefully; they drive chapter segmentation.
4. Add a fixture (a small anonymized replay/JSON) under `tests/fixtures/`
   and a test mirroring `tests/test_pipeline.py`.
5. `pytest -q && ruff check whitelee/`, then open a PR.

Extraction must respect game ToS: official APIs, replay files, save
files, screenshots and log files only. No client injection.

## Style profiles

Drop a YAML in `styles/` (see existing ones). Any language, any genre.
Include a sample output in the PR description.

## Code style

Python ≥3.10, type hints, ruff (line length 100). Keep the narrative
layer game-agnostic — if your PR imports a game name inside
`whitelee/narrative/`, something is wrong.
