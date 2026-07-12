---
id: T-001
title: 'Dota 2 adapter: chat, gold-swing momentum, lane-phase events'
status: todo
priority: 1
depends: []
---

## Context

ReTale's Dota 2 adapter (`retale/adapters/dota2_opendota.py`) currently extracts:
kills/deaths, big-item purchases, objectives, teamfights. Real matches expose
richer narrative material that we're leaving on the floor.

## Scope

You may touch: `retale/adapters/dota2_opendota.py`, `tests/fixtures/dota2_match.json`,
`tests/test_pipeline.py`. Nothing else. No new dependencies.

## Requirements

1. **Match-level chat**: OpenDota parsed matches have a top-level `chat` array
   (`{time, unit/player_slot, key, type}`). Map chat lines to `EventKind.SOCIAL`,
   importance 0.2 (0.35 if the protagonist spoke). Truncate each message to 120 chars.
   Remove the dead `match_chat()` placeholder function and the dead loop that
   references it in `_player_events`.
2. **Gold-swing events**: from top-level `radiant_gold_adv` (array indexed by
   minute), detect momentum reversals: minute m where the sign of the advantage
   flips AND |delta over previous 3 min| > 2000. Emit `EventKind.ECONOMY` at
   t = m*60, importance 0.55, summary like "The tide of gold turns toward the Dire."
   Set protagonist_involved=False.
3. **Lane phase marker**: emit one `EventKind.PHASE` at t=600 with summary
   "The laning stage draws to a close." importance 0.35. Only if match duration > 720s.
4. All new events must pass through the existing sort and appear in the planner
   output (no planner changes needed or allowed).

## Acceptance criteria

- [ ] Fixture updated to include a `chat` array (>=3 messages, >=1 from the
      protagonist) and a `radiant_gold_adv` array containing >=1 qualifying reversal.
- [ ] New test `test_chat_and_economy_events` asserts: SOCIAL events present with
      correct importance for protagonist vs others; exactly the expected number of
      ECONOMY reversal events for the fixture; the t=600 PHASE marker exists.
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
- [ ] `python -m retale.cli dota2 tests/fixtures/dota2_match.json --pov Ceaseless --dry-run`
      runs without error and the plan JSON includes at least one chat summary.
