---
id: T-008
title: 'Combat texture: teamfight ability/item usage, buybacks, runes, damage signature'
status: done
priority: 2
depends: []
base: b92ce1881ff1aaa11ee9d5e3ce9e98d872d5b247
---

## Context

Reader feedback on the first full story: skill casts have no timing/effect
texture, and item usage is entirely absent - yet clutch item timing and
decisive (or disastrous) casts are what players remember. OpenDota cannot
give per-cast timestamps or ult target counts (that is .dem combat-log
territory, deferred to the replay-parsing spike), but it DOES expose four
unmined sources at teamfight granularity:

- `match.teamfights[].players[i]` (index-aligned with `match.players[i]`):
  per-fight `ability_uses`, `item_uses`, `deaths`, `damage`, `buybacks`
- `players[].buyback_log`: timestamped buybacks
- `players[].runes_log`: timestamped rune pickups (`key` = rune id)
- `players[].damage_inflictor`: match-total damage per ability/item

## Scope

You may touch: `retale/adapters/dota2_opendota.py`,
`tests/fixtures/dota2_match.json`, `tests/test_pipeline.py`. Nothing else -
explicitly DO NOT touch `retale/narrative/` (T-007 is editing styler.py in
parallel). No new dependencies. Tests stay offline.

## Requirements

1. **Name prettifier.** Add a helper that turns internal ability/item slugs
   into display names: strip a leading `item_` prefix; if an ability name
   starts with the protagonist's hero slug tail + `_` (e.g. `slark_pounce`),
   strip that prefix; then `_`->space, Title Case. `black_king_bar` ->
   "Black King Bar", `slark_dark_pact` -> "Dark Pact".

2. **Teamfight combat texture.** In `_teamfight_events`, when the
   protagonist participated (existing detection), enrich the event:
   - collect his `ability_uses` for that fight, take the top 2 by count;
   - intersect his `item_uses` with a curated clutch set
     `{black_king_bar, blink, glimmer_cape, ghost, sheepstick, refresher,
       satanic, lotus_orb, sphere (Linken's Sphere), cyclone (Eul's)}`;
   - note his `damage` and whether his `deaths` for the fight is 0.
   Extend the summary, e.g.:
   "A team fight erupts - 4 heroes fall. Slark opens his Black King Bar and
   strikes with Pounce and Dark Pact (3100 damage), walking out untouched."
   Vary the tail: "...falls in the exchange." when his fight deaths > 0.
   Put the structured details into `data` (abilities, clutch_items, damage,
   died). Importance: +0.05 when a clutch item was used (cap 0.95).
   Guard index misalignment: if `teamfights[].players` length differs from
   `match['players']`, fall back to the current unenriched summary.

3. **Buyback events.** From every player's `buyback_log`, emit
   `EventKind.ECONOMY` events: protagonist buybacks importance 0.7,
   `protagonist_involved=True`, summary
   "Slark pays the blood price and buys his life back."; other players'
   buybacks importance 0.5 with the hero's name, phrased from the outside
   ("Invoker returns from death, gold spent for a second chance.").

4. **Rune events.** From the protagonist's `runes_log`, emit importance-0.35
   AMBIENT events for power runes only, mapping key ids:
   0 Double Damage, 1 Haste, 3 Invisibility, 4 Regeneration, 6 Arcane,
   8 Shield (other ids: skip). Summary: "Slark seizes a Haste rune."

5. **Damage signature.** Compute the protagonist's top entry in
   `damage_inflictor` (prettified, ability or item). Emit ONE AMBIENT event
   at t = duration - 1, importance 0.3, summary like
   "Across the whole battle, no weapon of his drew more blood than
   Essence Shift." Also store `context.world["signature"]` =
   {"name": <pretty>, "damage": <int>}. Skip both when the field is absent.

6. **Unparsed matches** (no teamfights/kills) must be unaffected: no new
   events, no crashes, `world["signature"]` absent.

## Acceptance criteria

- [ ] Fixture: extend teamfights[].players with index-aligned ability_uses /
      item_uses / deaths / damage for all 10 players (protagonist uses
      black_king_bar + slark_pounce x2 + slark_dark_pact x3 in one fight with
      deaths 0, and in another fight has deaths 1 and no clutch item);
      add protagonist buyback_log (1 entry), one enemy buyback,
      runes_log with one Haste (key 1) and one bounty (key 5, must be
      skipped), and damage_inflictor with a clear top ability.
- [ ] Tests assert: enriched fight summary contains "Black King Bar",
      "Pounce", "Dark Pact", the damage number, and the untouched phrasing;
      the deaths>0 fight uses the fallen phrasing; exactly 2 buyback events
      with correct importances and actors; exactly 1 rune event (Haste);
      signature event exists once and world["signature"]["name"] matches;
      misaligned teamfights players array falls back without raising;
      unparsed fixture emits none of the new event types.
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
