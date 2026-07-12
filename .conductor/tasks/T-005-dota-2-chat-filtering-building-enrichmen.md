---
id: T-005
title: 'Dota 2: chat filtering, building enrichment, pre-game ordering'
status: todo
priority: 1
depends:
- T-004
---

## Context

First parsed real match (8879557061) exposed three narrative-quality bugs in
the Dota 2 adapter:

1. OpenDota's match-level `chat` array mixes `type: "chat"` (typed text) with
   `type: "chatwheel"` (numeric voice-line IDs like "71", "93001"). We emit
   both as SOCIAL, so stories get lines like "陆地神仙: 93003".
2. `building_kill` objectives all render as "destroyed a building" - the
   `key` field (e.g. `npc_dota_badguys_tower3_mid`, `npc_dota_goodguys_melee_rax_bot`)
   is never parsed, and base-race endgames produce 15 identical events.
3. Pre-game events carry negative times (t=-83 chat), which sort BEFORE the
   MATCH_START event, breaking the opening chapter's ordering.

## Scope

You may touch: `retale/adapters/dota2_opendota.py`,
`tests/fixtures/dota2_match.json`, `tests/test_pipeline.py`. Nothing else.
No new dependencies. Tests stay offline. This task depends on T-004's hero
map being merged - build on top of it.

## Requirements

1. **Chat type filtering.** Only emit SOCIAL events for entries whose
   `type` is `"chat"` AND whose `key` is not purely digits. Drop
   `chatwheel` entries and digit-only keys entirely (no placeholder events).

2. **Building kill enrichment.** Parse the objective `key` for
   `building_kill` / `CHAT_MESSAGE_TOWER_KILL` / `CHAT_MESSAGE_BARRACKS_KILL`:
   - owner: `goodguys` -> Radiant, `badguys` -> Dire (the building's OWNER,
     i.e. the side that LOST it);
   - kind: `tower{N}` -> "tier-{N} tower", `melee_rax`/`range_rax` ->
     "melee barracks"/"ranged barracks", `fort` -> skip (MATCH_END covers it);
   - lane: `_top`/`_mid`/`_bot` suffix -> "top/mid/bottom lane" when present.
   Summary format: "The Dire's tier-3 mid tower falls." Barracks keep
   importance 0.7, towers scale 0.45 + 0.05*tier. If the `unit` field names
   a hero (npc_dota_hero_*), resolve it via the T-004 hero map and set
   actor + protagonist_involved when it is the protagonist's hero.

3. **Base-race aggregation.** After building events are generated, merge
   any run of 3+ building events within a 60-second window into ONE event:
   "The <winning side> tear through the <losing side> base - <N> structures
   fall." at the time of the first event in the run, importance 0.75,
   data listing the merged keys. (Runs shorter than 3 stay as-is.)

4. **Pre-game ordering.** MATCH_START's time must precede every other
   event: set it to `min(0, earliest event t) - 1` after all events are
   collected. Do not clamp or drop negative-time events themselves.

## Acceptance criteria

- [ ] Fixture gains: 2 chatwheel entries (numeric keys) that must NOT
      appear as events; 1 typed chat at t=-40; a burst of 4 building_kill
      objectives within 60s (same side) plus 1 isolated tower kill.
- [ ] Tests assert: no SOCIAL event has a digit-only message; the t=-40
      chat exists AND MATCH_START is the chronologically first event;
      the isolated tower renders with owner+tier+lane in its summary;
      the 4-event burst becomes exactly one aggregated event with the
      correct count; barracks importance is 0.7.
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
