# Report T-001: Dota 2 adapter: chat, gold-swing momentum, lane-phase events

generated: 2026-07-12 00:28 UTC

## Implementer notes

Implemented match-level chat extraction as SOCIAL events, gold-swing momentum reversals from radiant_gold_adv, and the 10-minute lane phase marker. Removed the dead match_chat placeholder and the dead loop in _player_events. Updated the Dota 2 fixture with chat lines and qualifying gold swings, and added test_chat_and_economy_events to verify SOCIAL importance, exactly two ECONOMY reversals, and the t=600 PHASE marker. Verification: python -m pytest tests/ -q -> 6 passed; ruff check retale/ -> clean; python -m retale.cli dota2 tests/fixtures/dota2_match.json --pov Ceaseless --dry-run -> success with chat summaries present in plan JSON. No open questions.

## Test output

```
......                                                                   [100%]
6 passed in 0.14s
```

## Diff vs HEAD

```diff
...001-dota-2-adapter-chat-gold-swing-momentum-.md |   2 +-
 retale/adapters/dota2_opendota.py                  | 119 +++++++++++++++++++--
 tests/fixtures/dota2_match.json                    |  39 ++++++-
 tests/test_pipeline.py                             |  22 ++++
 4 files changed, 174 insertions(+), 8 deletions(-)
warning: in the working copy of 'retale/adapters/dota2_opendota.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/fixtures/dota2_match.json', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_pipeline.py', LF will be replaced by CRLF the next time Git touches it


diff --git a/.conductor/tasks/T-001-dota-2-adapter-chat-gold-swing-momentum-.md b/.conductor/tasks/T-001-dota-2-adapter-chat-gold-swing-momentum-.md
index 6559b49..3690a1b 100644
--- a/.conductor/tasks/T-001-dota-2-adapter-chat-gold-swing-momentum-.md
+++ b/.conductor/tasks/T-001-dota-2-adapter-chat-gold-swing-momentum-.md
@@ -1,7 +1,7 @@
 ---
 id: T-001
 title: 'Dota 2 adapter: chat, gold-swing momentum, lane-phase events'
-status: todo
+status: in_progress
 priority: 1
 depends: []
 ---
diff --git a/retale/adapters/dota2_opendota.py b/retale/adapters/dota2_opendota.py
index 89f63eb..d9d440c 100644
--- a/retale/adapters/dota2_opendota.py
+++ b/retale/adapters/dota2_opendota.py
@@ -91,6 +91,9 @@ class Dota2OpenDotaAdapter(GameAdapter):
         ]
         events += self._objective_events(match)
         events += self._player_events(players, me, hero)
+        events += self._chat_events(match, players, me)
+        events += self._gold_swing_events(match)
+        events += self._lane_phase_events(match)
         events += self._teamfight_events(match, me, hero)
         events.append(NarrativeEvent(
             t=context.duration, kind=EventKind.MATCH_END, actor=handle,
@@ -180,11 +183,91 @@ class Dota2OpenDotaAdapter(GameAdapter):
                     actor=hero, target=item,
                     summary=f"{hero} completed {item.replace('_', ' ').title()}.",
                     importance=0.45, protagonist_involved=True))
-        # chat (SOCIAL flavor)
-        for c in (players[0].get("chat") if players else None) or match_chat(players):
-            pass  # chat lives at match level; handled below if present
         return out
 
+    def _chat_events(
+        self, match: dict[str, Any], players: list[dict], me: dict[str, Any]
+    ) -> list[NarrativeEvent]:
+        players_by_slot = {
+            int(player.get("player_slot", -1)): player
+            for player in players
+            if player.get("player_slot") is not None
+        }
+        protagonist_slot = int(me.get("player_slot", -1))
+        out: list[NarrativeEvent] = []
+
+        for line in match.get("chat", []) or []:
+            message = str(line.get("key", "")).strip()
+            if not message:
+                continue
+
+            actor, speaker_slot = self._chat_actor(line, players_by_slot)
+            protagonist_spoke = speaker_slot == protagonist_slot
+            truncated_message = message[:120]
+            summary = f"{actor}: {truncated_message}" if actor else truncated_message
+
+            out.append(NarrativeEvent(
+                t=float(line.get("time", 0)),
+                kind=EventKind.SOCIAL,
+                actor=actor or None,
+                summary=summary,
+                importance=0.35 if protagonist_spoke else 0.2,
+                protagonist_involved=protagonist_spoke,
+                data=line,
+            ))
+        return out
+
+    def _gold_swing_events(self, match: dict[str, Any]) -> list[NarrativeEvent]:
+        gold_advantage = match.get("radiant_gold_adv", []) or []
+        out: list[NarrativeEvent] = []
+
+        for minute in range(1, len(gold_advantage)):
+            current_advantage = gold_advantage[minute]
+            previous_advantage = gold_advantage[minute - 1]
+            if current_advantage is None or previous_advantage is None or minute < 3:
+                continue
+
+            current_sign = self._advantage_sign(current_advantage)
+            previous_sign = self._advantage_sign(previous_advantage)
+            if current_sign == 0 or previous_sign == 0 or current_sign == previous_sign:
+                continue
+
+            earlier_advantage = gold_advantage[minute - 3]
+            if earlier_advantage is None:
+                continue
+
+            swing = float(current_advantage) - float(earlier_advantage)
+            if abs(swing) <= 2000:
+                continue
+
+            favored_team = "Radiant" if current_sign > 0 else "Dire"
+            out.append(NarrativeEvent(
+                t=float(minute * 60),
+                kind=EventKind.ECONOMY,
+                summary=f"The tide of gold turns toward the {favored_team}.",
+                importance=0.55,
+                protagonist_involved=False,
+                data={
+                    "minute": minute,
+                    "radiant_gold_adv": current_advantage,
+                    "three_min_delta": swing,
+                },
+            ))
+        return out
+
+    def _lane_phase_events(self, match: dict[str, Any]) -> list[NarrativeEvent]:
+        if float(match.get("duration", 0)) <= 720:
+            return []
+        return [
+            NarrativeEvent(
+                t=600.0,
+                kind=EventKind.PHASE,
+                summary="The laning stage draws to a close.",
+                importance=0.35,
+                protagonist_involved=False,
+            )
+        ]
+
     def _teamfight_events(self, match: dict, me: dict, hero: str) -> list[NarrativeEvent]:
         out = []
         my_slot = me.get("player_slot", 0)
@@ -204,7 +287,31 @@ class Dota2OpenDotaAdapter(GameAdapter):
                 data={"end": tf.get("end"), "deaths": deaths}))
         return out
 
+    @staticmethod
+    def _chat_actor(
+        line: dict[str, Any], players_by_slot: dict[int, dict[str, Any]]
+    ) -> tuple[str, int | None]:
+        speaker_slot = line.get("player_slot", line.get("unit"))
+        if isinstance(speaker_slot, str) and speaker_slot.isdigit():
+            speaker_slot = int(speaker_slot)
+        if isinstance(speaker_slot, int):
+            player = players_by_slot.get(speaker_slot)
+            if player:
+                actor = str(
+                    player.get("personaname") or Dota2OpenDotaAdapter._hero_name(player)
+                )
+                return actor, speaker_slot
+            return f"slot_{speaker_slot}", speaker_slot
+
+        actor = str(line.get("unit", "")).strip()
+        if actor.startswith("npc_dota_hero_"):
+            actor = actor.replace("npc_dota_hero_", "").replace("_", " ").title()
+        return actor, None
 
-def match_chat(_players: list) -> list:
-    """Placeholder: OpenDota exposes chat at match level, wired in v0.2."""
-    return []
+    @staticmethod
+    def _advantage_sign(value: int | float) -> int:
+        if value > 0:
+            return 1
+        if value < 0:
+            return -1
+        return 0
diff --git a/tests/fixtures/dota2_match.json b/tests/fixtures/dota2_match.json
index 5058b34..a442b44 100644
--- a/tests/fixtures/dota2_match.json
+++ b/tests/fixtures/dota2_match.json
@@ -174,6 +174,43 @@
    "purchase_log": []
   }
  ],
+ "chat": [
+  {
+   "time": 120,
+   "player_slot": 0,
+   "type": "chat",
+   "key": "Steady lane, I'll take farm."
+  },
+  {
+   "time": 540,
+   "player_slot": 128,
+   "type": "chat",
+   "key": "Missing mid. Back up now."
+  },
+  {
+   "time": 1180,
+   "player_slot": 3,
+   "type": "chat",
+   "key": "Smoke after this wave and collapse on Roshan."
+  },
+  {
+   "time": 1740,
+   "player_slot": 0,
+   "type": "chat",
+   "key": "One more clean fight and the map is ours. Keep lanes shoved, hold buyback, and do not overextend beyond vision."
+  }
+ ],
+ "radiant_gold_adv": [
+  100,
+  800,
+  1600,
+  2600,
+  -1500,
+  -2200,
+  -1800,
+  900,
+  1400
+ ],
  "objectives": [
   {
    "time": 290,
@@ -349,4 +386,4 @@
    ]
   }
  ]
-}
\ No newline at end of file
+}
diff --git a/tests/test_pipeline.py b/tests/test_pipeline.py
index 6fc035a..100345f 100644
--- a/tests/test_pipeline.py
+++ b/tests/test_pipeline.py
@@ -38,6 +38,28 @@ def test_adapter_event_stream(extraction):
     assert any(e.protagonist_involved for e in extraction.events)
 
 
+def test_chat_and_economy_events(extraction):
+    social_events = [event for event in extraction.events if event.kind == EventKind.SOCIAL]
+    economy_events = [event for event in extraction.events if event.kind == EventKind.ECONOMY]
+    lane_phase_events = [
+        event
+        for event in extraction.events
+        if event.kind == EventKind.PHASE
+        and event.t == 600
+        and event.summary == "The laning stage draws to a close."
+    ]
+
+    assert len(social_events) >= 3
+    assert any(event.actor == "Ceaseless" and event.importance == 0.35 for event in social_events)
+    assert any(event.actor != "Ceaseless" and event.importance == 0.2 for event in social_events)
+    assert len(economy_events) == 2
+    assert [event.summary for event in economy_events] == [
+        "The tide of gold turns toward the Dire.",
+        "The tide of gold turns toward the Radiant.",
+    ]
+    assert len(lane_phase_events) == 1
+
+
 def test_planner_builds_arc(extraction):
     plan = Planner().plan(extraction.context, extraction.events)
     assert 3 <= len(plan.chapters) <= 9
warning: in the working copy of 'retale/adapters/dota2_opendota.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/fixtures/dota2_match.json', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_pipeline.py', LF will be replaced by CRLF the next time Git touches it
```

## Original spec

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
