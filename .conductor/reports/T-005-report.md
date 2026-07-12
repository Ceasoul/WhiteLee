# Report T-005: Dota 2: chat filtering, building enrichment, pre-game ordering

generated: 2026-07-12 01:43 UTC

## Implementer notes

Implemented the T-005 Dota 2 narrative-quality fixes in the adapter only within the allowed scope. Chat filtering now emits SOCIAL events only for match-level chat entries whose type is 'chat' and whose key is not purely digits; chatwheel entries and digit-only payloads are dropped entirely. Building objective handling is now enriched for building_kill, CHAT_MESSAGE_TOWER_KILL, and CHAT_MESSAGE_BARRACKS_KILL by parsing the objective key to recover the building owner (the side that lost it), structure type, tier, and lane, skipping forts because MATCH_END already covers the Ancient/base finish. Tower summaries now render with owner + tier + lane and tower importance scales as 0.45 + 0.05 * tier; barracks remain at importance 0.7. When the objective unit is a hero slug, actor is resolved through the hero map and protagonist_involved is marked when it matches the protagonist hero. After building events are generated, runs of 3+ building events within a 60-second window for the same losing side are merged into one base-race event with summary 'The <winning side> tear through the <losing side> base - <N> structures fall.', importance 0.75, and merged_keys stored in data. Pre-game ordering is fixed by assigning MATCH_START after all other events are collected to min(0, earliest_event_t) - 1, so negative-time pre-game events stay intact but never precede MATCH_START. Updated the parsed fixture with two chatwheel numeric entries that must not surface, one typed pre-game chat at t=-40, one isolated tower kill, one isolated barracks kill, and a four-structure building burst for aggregation. Expanded tests to assert that digit-only SOCIAL payloads never appear, the t=-40 chat exists while MATCH_START remains chronologically first, the isolated tower summary includes owner+tier+lane and protagonist actor resolution, the four-event burst collapses to exactly one aggregated base-race event with four merged keys, and the isolated barracks keeps importance 0.7. Verification: python -m pytest tests/ -q -> 16 passed; ruff check retale/ tests/ -> clean. No open questions.

## Test output

```
................                                                         [100%]
16 passed in 0.77s
```

## Diff vs HEAD

```diff
...005-dota-2-chat-filtering-building-enrichmen.md |   2 +-
 retale/adapters/dota2_opendota.py                  | 190 +++++++++++++++++++--
 tests/fixtures/dota2_match.json                    |  50 +++++-
 tests/test_pipeline.py                             |  29 +++-
 4 files changed, 254 insertions(+), 17 deletions(-)
warning: in the working copy of '.conductor/tasks/T-005-dota-2-chat-filtering-building-enrichmen.md', CRLF will be replaced by LF the next time Git touches it


diff --git a/.conductor/tasks/T-005-dota-2-chat-filtering-building-enrichmen.md b/.conductor/tasks/T-005-dota-2-chat-filtering-building-enrichmen.md
index d62a66d..1af5ec4 100644
--- a/.conductor/tasks/T-005-dota-2-chat-filtering-building-enrichmen.md
+++ b/.conductor/tasks/T-005-dota-2-chat-filtering-building-enrichmen.md
@@ -1,7 +1,7 @@
 ---
 id: T-005
 title: 'Dota 2: chat filtering, building enrichment, pre-game ordering'
-status: todo
+status: in_progress
 priority: 1
 depends:
 - T-004
diff --git a/retale/adapters/dota2_opendota.py b/retale/adapters/dota2_opendota.py
index 983ca4c..3f5c1b5 100644
--- a/retale/adapters/dota2_opendota.py
+++ b/retale/adapters/dota2_opendota.py
@@ -97,18 +97,19 @@ class Dota2OpenDotaAdapter(GameAdapter):
                        if (p.get("player_slot", 0) < 128) != is_radiant],
         )
 
-        events: list[NarrativeEvent] = [
-            NarrativeEvent(t=0, kind=EventKind.MATCH_START, actor=handle,
-                           summary=f"{hero} takes the field for the "
-                                   f"{context.world['team']}.",
-                           importance=0.5, protagonist_involved=True),
-        ]
-        events += self._objective_events(match)
+        events: list[NarrativeEvent] = []
+        events += self._objective_events(match, me, hero, hero_lookup)
         events += self._player_events(players, me, hero, hero_lookup)
         events += self._chat_events(match, players, me, hero_lookup)
         events += self._gold_swing_events(match)
         events += self._lane_phase_events(match)
         events += self._teamfight_events(match, me, hero)
+        match_start_time = min(0.0, min((event.t for event in events), default=0.0)) - 1.0
+        events.append(NarrativeEvent(
+            t=match_start_time, kind=EventKind.MATCH_START, actor=handle,
+            summary=f"{hero} takes the field for the "
+                    f"{context.world['team']}.",
+            importance=0.5, protagonist_involved=True))
         events.append(NarrativeEvent(
             t=context.duration, kind=EventKind.MATCH_END, actor=handle,
             summary=f"The Ancient falls. {context.outcome.capitalize()} "
@@ -212,9 +213,20 @@ class Dota2OpenDotaAdapter(GameAdapter):
             return "unknown"
         return "victory" if rw == is_radiant else "defeat"
 
-    def _objective_events(self, match: dict) -> list[NarrativeEvent]:
-        out = []
+    def _objective_events(
+        self,
+        match: dict,
+        me: dict[str, Any],
+        hero: str,
+        hero_lookup: dict[str, dict[Any, str]],
+    ) -> list[NarrativeEvent]:
+        out: list[NarrativeEvent] = []
         for obj in match.get("objectives", []) or []:
+            building_event = self._building_objective_event(obj, me, hero, hero_lookup)
+            if building_event is not None:
+                out.append(building_event)
+                continue
+
             kind, imp, phrase = _OBJECTIVE_MAP.get(
                 obj.get("type", ""), (EventKind.OBJECTIVE, 0.4, "objective event"))
             out.append(NarrativeEvent(
@@ -222,7 +234,7 @@ class Dota2OpenDotaAdapter(GameAdapter):
                 actor=str(obj.get("unit", "") or obj.get("team", "")),
                 target=str(obj.get("key", "")),
                 summary=phrase, importance=imp, data=obj))
-        return out
+        return self._aggregate_building_events(out)
 
     def _player_events(
         self,
@@ -285,8 +297,10 @@ class Dota2OpenDotaAdapter(GameAdapter):
         out: list[NarrativeEvent] = []
 
         for line in match.get("chat", []) or []:
+            if str(line.get("type", "")) != "chat":
+                continue
             message = str(line.get("key", "")).strip()
-            if not message:
+            if not message or message.isdigit():
                 continue
 
             actor, speaker_slot = self._chat_actor(line, players_by_slot, hero_lookup)
@@ -305,6 +319,160 @@ class Dota2OpenDotaAdapter(GameAdapter):
             ))
         return out
 
+    def _building_objective_event(
+        self,
+        obj: dict[str, Any],
+        me: dict[str, Any],
+        hero: str,
+        hero_lookup: dict[str, dict[Any, str]],
+    ) -> NarrativeEvent | None:
+        objective_type = str(obj.get("type", ""))
+        if objective_type not in {
+            "building_kill",
+            "CHAT_MESSAGE_TOWER_KILL",
+            "CHAT_MESSAGE_BARRACKS_KILL",
+        }:
+            return None
+
+        building = self._parse_building_key(str(obj.get("key", "")))
+        if building is None:
+            return None
+        if building["kind"] == "fort":
+            return None
+
+        actor = None
+        protagonist_involved = False
+        unit = str(obj.get("unit", ""))
+        if unit.startswith("npc_dota_hero_"):
+            actor = self._resolve_hero_slug(unit, hero_lookup)
+            protagonist_involved = unit == self._hero_slug(me, hero_lookup) or actor == hero
+
+        if building["kind"] == "tower":
+            descriptor = f"tier-{building['tier']} {building['lane']} tower" if building["lane"] else f"tier-{building['tier']} tower"
+            importance = 0.45 + 0.05 * int(building["tier"])
+        else:
+            lane_text = f" in {building['lane']} lane" if building["lane"] else ""
+            descriptor = f"{building['label']}{lane_text}"
+            importance = 0.7
+
+        return NarrativeEvent(
+            t=float(obj.get("time", 0)),
+            kind=EventKind.OBJECTIVE,
+            actor=actor,
+            target=str(obj.get("key", "")),
+            summary=f"The {building['owner']}'s {descriptor} falls.",
+            importance=importance,
+            protagonist_involved=protagonist_involved,
+            data={
+                **obj,
+                "building_owner": building["owner"],
+                "building_kind": building["kind"],
+                "building_lane": building["lane"],
+                "building_key": str(obj.get("key", "")),
+            },
+        )
+
+    @staticmethod
+    def _parse_building_key(key: str) -> dict[str, Any] | None:
+        if not key:
+            return None
+        tokens = key.split("_")
+        owner = None
+        if "goodguys" in tokens or key.startswith("radiant_"):
+            owner = "Radiant"
+        elif "badguys" in tokens or key.startswith("dire_"):
+            owner = "Dire"
+        elif key.startswith("goodguys_"):
+            owner = "Radiant"
+        elif key.startswith("badguys_"):
+            owner = "Dire"
+        elif key.startswith("dire_"):
+            owner = "Dire"
+        elif key.startswith("radiant_"):
+            owner = "Radiant"
+        if owner is None:
+            return None
+
+        lane = None
+        if key.endswith("_top"):
+            lane = "top"
+        elif key.endswith("_mid"):
+            lane = "mid"
+        elif key.endswith("_bot"):
+            lane = "bottom"
+
+        compact_tokens = {"t1", "t2", "t3", "t4"}
+        tier_token = next((token for token in tokens if token.startswith("tower")), None)
+        if tier_token:
+            tier_text = tier_token.replace("tower", "")
+            if tier_text.isdigit():
+                return {"owner": owner, "kind": "tower", "tier": int(tier_text), "lane": lane}
+
+        compact_tier = next((token for token in tokens if token in compact_tokens), None)
+        if compact_tier:
+            return {"owner": owner, "kind": "tower", "tier": int(compact_tier[1]), "lane": lane}
+
+        if "melee" in tokens and "rax" in tokens:
+            return {"owner": owner, "kind": "barracks", "label": "melee barracks", "lane": lane}
+        if "range" in tokens and "rax" in tokens:
+            return {"owner": owner, "kind": "barracks", "label": "ranged barracks", "lane": lane}
+        if "fort" in tokens:
+            return {"owner": owner, "kind": "fort", "lane": lane}
+        return None
+
+    @staticmethod
+    def _aggregate_building_events(events: list[NarrativeEvent]) -> list[NarrativeEvent]:
+        aggregated: list[NarrativeEvent] = []
+        building_buffer: list[NarrativeEvent] = []
+
+        def flush_buffer() -> None:
+            if not building_buffer:
+                return
+            if len(building_buffer) >= 3:
+                first = building_buffer[0]
+                owner = str(first.data.get("building_owner", "unknown"))
+                winning_side = "Radiant" if owner == "Dire" else "Dire"
+                aggregated.append(NarrativeEvent(
+                    t=first.t,
+                    kind=EventKind.OBJECTIVE,
+                    actor=first.actor if all(event.actor == first.actor for event in building_buffer) else None,
+                    summary=(
+                        f"The {winning_side} tear through the {owner} base - "
+                        f"{len(building_buffer)} structures fall."
+                    ),
+                    importance=0.75,
+                    protagonist_involved=any(event.protagonist_involved for event in building_buffer),
+                    data={
+                        "building_owner": owner,
+                        "merged_keys": [event.data.get("building_key", event.target) for event in building_buffer],
+                    },
+                ))
+            else:
+                aggregated.extend(building_buffer)
+            building_buffer.clear()
+
+        for event in sorted(events, key=lambda item: item.t):
+            is_building = event.kind == EventKind.OBJECTIVE and "building_owner" in event.data
+            if not is_building:
+                flush_buffer()
+                aggregated.append(event)
+                continue
+
+            if not building_buffer:
+                building_buffer.append(event)
+                continue
+
+            same_owner = event.data.get("building_owner") == building_buffer[0].data.get("building_owner")
+            within_window = event.t - building_buffer[0].t <= 60
+            if same_owner and within_window:
+                building_buffer.append(event)
+            else:
+                flush_buffer()
+                building_buffer.append(event)
+
+        flush_buffer()
+        return aggregated
+
     def _gold_swing_events(self, match: dict[str, Any]) -> list[NarrativeEvent]:
         gold_advantage = match.get("radiant_gold_adv", []) or []
         out: list[NarrativeEvent] = []
diff --git a/tests/fixtures/dota2_match.json b/tests/fixtures/dota2_match.json
index 944b505..babf292 100644
--- a/tests/fixtures/dota2_match.json
+++ b/tests/fixtures/dota2_match.json
@@ -165,6 +165,18 @@
   }
  ],
  "chat": [
+  {
+   "time": -83,
+   "player_slot": 3,
+   "type": "chatwheel",
+   "key": "71"
+  },
+  {
+   "time": -40,
+   "player_slot": 0,
+   "type": "chat",
+   "key": "Let's smoke when the horn fades."
+  },
   {
    "time": 120,
    "player_slot": 0,
@@ -188,6 +200,12 @@
    "player_slot": 0,
    "type": "chat",
    "key": "One more clean fight and the map is ours. Keep lanes shoved, hold buyback, and do not overextend beyond vision."
+  },
+  {
+   "time": 1810,
+   "player_slot": 128,
+   "type": "chatwheel",
+   "key": "93001"
   }
  ],
  "radiant_gold_adv": [
@@ -212,7 +230,7 @@
    "time": 900,
    "type": "CHAT_MESSAGE_TOWER_KILL",
    "unit": "npc_dota_hero_juggernaut",
-   "key": "dire_t1_mid"
+   "key": "npc_dota_badguys_tower1_mid"
   },
   {
    "time": 1600,
@@ -227,10 +245,34 @@
    "key": ""
   },
   {
-   "time": 2050,
+   "time": 1700,
    "type": "CHAT_MESSAGE_BARRACKS_KILL",
-   "unit": "Radiant",
-   "key": "dire_mid_rax"
+   "unit": "npc_dota_hero_juggernaut",
+   "key": "npc_dota_badguys_melee_rax_bot"
+  },
+  {
+   "time": 2010,
+   "type": "building_kill",
+   "unit": "npc_dota_hero_juggernaut",
+   "key": "npc_dota_badguys_tower3_mid"
+  },
+  {
+   "time": 2030,
+   "type": "building_kill",
+   "unit": "npc_dota_hero_juggernaut",
+   "key": "npc_dota_badguys_melee_rax_mid"
+  },
+  {
+   "time": 2050,
+   "type": "building_kill",
+   "unit": "npc_dota_hero_juggernaut",
+   "key": "npc_dota_badguys_range_rax_mid"
+  },
+  {
+   "time": 2060,
+   "type": "building_kill",
+   "unit": "npc_dota_hero_juggernaut",
+   "key": "npc_dota_badguys_tower4"
   }
  ],
  "teamfights": [
diff --git a/tests/test_pipeline.py b/tests/test_pipeline.py
index e91af9a..7252d86 100644
--- a/tests/test_pipeline.py
+++ b/tests/test_pipeline.py
@@ -123,6 +123,10 @@ def test_adapter_event_stream(extraction):
     # chronological
     ts = [e.t for e in extraction.events]
     assert ts == sorted(ts)
+    # MATCH_START must lead even with negative-time pre-game events.
+    assert extraction.events[0].kind == EventKind.MATCH_START
+    assert extraction.events[1].kind == EventKind.SOCIAL
+    assert extraction.events[1].t == -40
     # protagonist involvement is marked
     assert any(e.protagonist_involved for e in extraction.events)
 
@@ -137,8 +141,22 @@ def test_chat_and_economy_events(extraction):
         and event.t == 600
         and event.summary == "The laning stage draws to a close."
     ]
+    tower_events = [
+        event for event in extraction.events
+        if event.kind == EventKind.OBJECTIVE and "tier-1 mid tower" in event.summary
+    ]
+    barracks_events = [
+        event for event in extraction.events
+        if event.kind == EventKind.OBJECTIVE and "melee barracks" in event.summary
+    ]
+    aggregate_events = [
+        event for event in extraction.events
+        if event.summary == "The Radiant tear through the Dire base - 4 structures fall."
+    ]
 
-    assert len(social_events) >= 3
+    assert len(social_events) >= 4
+    assert all(not event.summary.split(": ", 1)[-1].isdigit() for event in social_events)
+    assert any(event.t == -40 for event in social_events)
     assert any(event.actor == "Ceaseless" and event.importance == 0.35 for event in social_events)
     assert any(event.actor != "Ceaseless" and event.importance == 0.2 for event in social_events)
     assert len(economy_events) == 2
@@ -146,6 +164,15 @@ def test_chat_and_economy_events(extraction):
         "The tide of gold turns toward the Dire.",
         "The tide of gold turns toward the Radiant.",
     ]
+    assert len(tower_events) == 1
+    assert tower_events[0].summary == "The Dire's tier-1 mid tower falls."
+    assert tower_events[0].actor == "Juggernaut"
+    assert tower_events[0].protagonist_involved is True
+    assert len(aggregate_events) == 1
+    assert aggregate_events[0].importance == 0.75
+    assert len(aggregate_events[0].data["merged_keys"]) == 4
+    assert len(barracks_events) == 1
+    assert barracks_events[0].importance == 0.7
     assert len(lane_phase_events) == 1
 
 
warning: in the working copy of '.conductor/tasks/T-005-dota-2-chat-filtering-building-enrichmen.md', CRLF will be replaced by LF the next time Git touches it
```

## Original spec

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
