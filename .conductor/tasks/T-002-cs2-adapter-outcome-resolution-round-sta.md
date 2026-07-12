---
id: T-002
title: 'CS2 adapter: outcome resolution, round stakes, clutch detection'
status: todo
priority: 2
depends: []
---

## Context

The CS2 adapter (`retale/adapters/cs2_demo.py`) leaves `outcome="unknown"` and
ignores the economy - but round economy IS the dramatic stakes of CS, and clutches
are the climaxes.

## Scope

You may touch: `retale/adapters/cs2_demo.py`, plus create
`tests/test_cs2_adapter.py` with mocked demoparser2 output (pandas DataFrames).
demoparser2 itself must remain an optional import; tests must NOT require a real
.dem file - build DataFrames by hand. You may import pandas inside tests only.

## Requirements

1. **Outcome resolution**: track round wins per side from `round_end` (`winner`
   column, values like "T"/"CT" or 2/3 depending on demoparser2 version - handle
   both). Determine the protagonist's team from kill rows (`attacker_team_name` /
   `user_team_name` if present; otherwise leave unknown). Set
   `context.outcome` to victory/defeat/draw and add per-round PHASE summaries
   like "Round 7 goes to the CTs (8-5)". Handle side swap at halftime (round 13
   in MR12) when computing the protagonist's final team result.
2. **Clutch detection**: within each round, if the protagonist gets >=3 kills
   after the point where their side has fewer alive players than the enemy
   (approximate: count deaths per side from player_death rows), emit
   `EventKind.TRIUMPH` "X clutches the round" importance 0.85. If exact
   alive-count is not derivable from available columns, document the
   approximation you used in the report notes.
3. **Match point / overtime markers**: emit PHASE events with importance 0.6
   when either side reaches match point, and at overtime start.

## Acceptance criteria

- [ ] `tests/test_cs2_adapter.py` covers: outcome victory & defeat cases,
      halftime side-swap correctness, one synthetic clutch detected, match-point
      marker present. All with hand-built DataFrames, no .dem files.
- [ ] Adapter still imports demoparser2 lazily (module import must not fail
      without it) - add a test asserting `retale.adapters.cs2_demo` imports fine.
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
