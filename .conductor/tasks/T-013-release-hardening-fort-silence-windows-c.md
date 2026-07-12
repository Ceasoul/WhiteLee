---
id: T-013
title: 'Release hardening: fort silence, Windows CI matrix, gitignore progress files'
status: todo
priority: 2
depends:
- T-012
---

## Context

Release-hardening leftovers: (1) fort/ancient building kills leak a naked
"destroyed a building" event (the key parser correctly identifies `fort`
for skipping, but unparsable/skipped building keys fall through to the
generic objective branch and emit anyway) - seen in real match 8879557061,
final chapter. (2) CI tests only ubuntu-latest while all development
happens on Windows - tonight's encoding incident proved this gap is real.
(3) `*.progress.json` checkpoints are transient and must not enter git.

Depends on T-012 (run against the renamed package).

## Scope

You may touch: `whitelee/adapters/dota2_opendota.py`,
`tests/fixtures/dota2_match.json`, `tests/test_pipeline.py`,
`.github/workflows/ci.yml`, `.gitignore`. Nothing else.

## Requirements

1. **Fort silence.** Objectives of building-kill type whose key parses to
   the fort/ancient (or any key the parser deliberately skips) must emit
   NO event at all - the MATCH_END event already covers the throne. Keys
   that fail to parse as buildings but belong to building-kill objective
   types emit the generic fallback ONLY when they are not fort keys.
2. **CI matrix.** Extend the workflow to
   `os: [ubuntu-latest, windows-latest]` x `python: ["3.10", "3.12"]`,
   `runs-on: ${{ matrix.os }}`. Keep ruff + pytest steps unchanged.
3. **.gitignore** gains `*.progress.json`.

## Acceptance criteria

- [ ] Fixture gains one building_kill objective with key
      `npc_dota_badguys_fort`; tests assert it produces zero events, while
      existing tower/rax assertions still pass and the event count math is
      updated accordingly.
- [ ] Workflow YAML contains both OS entries under a matrix and uses
      matrix.os (assert by reading the YAML in a test OR verify manually
      and paste the yaml block in notes).
- [ ] `python -m pytest tests/ -q` passes; `ruff check whitelee/` clean.
