# Report T-002: CS2 adapter: outcome resolution, round stakes, clutch detection

generated: 2026-07-12 00:44 UTC

## Implementer notes

Architect review follow-up: the report tool previously omitted untracked files from the diff, which prevented review of tests/test_cs2_adapter.py; the tool is now fixed and this recollect is requested to include it. Overtime handling note: in overtime after 13-13, sides swap every 3 rounds. In those segments, fallback side inference can become inaccurate, so side ownership relies on the actual team fields present on kill rows as the safety net.

## Test output

```
..........                                                               [100%]
10 passed in 0.69s
```

## Diff vs HEAD

```diff
.conductor/reports/T-002-report.md                 | 343 +++++++++++++++++++++
 ...002-cs2-adapter-outcome-resolution-round-sta.md |   2 +-
 retale/adapters/cs2_demo.py                        | 219 ++++++++++++-
 tests/test_cs2_adapter.py                          | 210 +++++++++++++
 4 files changed, 765 insertions(+), 9 deletions(-)
warning: in the working copy of '.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/reports/T-002-report.md', CRLF will be replaced by LF the next time Git touches it


diff --git a/.conductor/reports/T-002-report.md b/.conductor/reports/T-002-report.md
new file mode 100644
index 0000000..29a20c3
--- /dev/null
+++ b/.conductor/reports/T-002-report.md
@@ -0,0 +1,343 @@
+# Report T-002: CS2 adapter: outcome resolution, round stakes, clutch detection
+
+generated: 2026-07-12 00:40 UTC
+
+## Implementer notes
+
+Implemented round outcome resolution in the CS2 adapter with normalized round winners (T/CT and 2/3), per-round PHASE summaries with running score, match-point markers, overtime-start marker, and context outcome resolution using protagonist side inference plus the halftime side swap at round 13. Added clutch detection as an approximation based on player_death rows: start from 5v5 alive counts, decrement by victim side on each death, open the clutch window once the protagonist side first falls behind on alive players, and count protagonist kills from that point onward; emit a TRIUMPH event at >=3 such kills. Kept demoparser2 as a lazy import inside extract. Added tests/test_cs2_adapter.py with synthetic pandas DataFrames and a fake demoparser2 module covering lazy import, victory, defeat, halftime side swap correctness, clutch detection, match-point marker, and overtime start. Verification: python -m pytest tests/ -q -> 10 passed; ruff check retale/ tests/ -> clean. No open questions.
+
+## Test output
+
+```
+..........                                                               [100%]
+10 passed in 0.68s
+```
+
+## Diff vs HEAD
+
+```diff
+...002-cs2-adapter-outcome-resolution-round-sta.md |   2 +-
+ retale/adapters/cs2_demo.py                        | 219 ++++++++++++++++++++-
+ 2 files changed, 212 insertions(+), 9 deletions(-)
+warning: in the working copy of '.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md', CRLF will be replaced by LF the next time Git touches it
+
+
+diff --git a/.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md b/.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md
+index ef6cdf0..b42a313 100644
+--- a/.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md
++++ b/.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md
+@@ -1,7 +1,7 @@
+ ---
+ id: T-002
+ title: 'CS2 adapter: outcome resolution, round stakes, clutch detection'
+-status: todo
++status: in_progress
+ priority: 2
+ depends: []
+ ---
+diff --git a/retale/adapters/cs2_demo.py b/retale/adapters/cs2_demo.py
+index 29590ad..abad9a1 100644
+--- a/retale/adapters/cs2_demo.py
++++ b/retale/adapters/cs2_demo.py
+@@ -10,6 +10,8 @@ map them onto the ReTale schema. Ticks are converted to seconds at
+ 
+ from __future__ import annotations
+ 
++from collections.abc import Iterable
++
+ from retale.adapters.base import ExtractionResult, GameAdapter
+ from retale.core.schema import (
+     EventKind,
+@@ -40,6 +42,8 @@ class CS2DemoAdapter(GameAdapter):
+         defuses = parser.parse_event("bomb_defused")
+ 
+         protagonist_name = self._resolve_protagonist(kills, protagonist_hint)
++        protagonist_round_sides = self._resolve_protagonist_round_sides(kills, protagonist_name)
++        starting_side = protagonist_round_sides.get(1) or self._first_known_side(protagonist_round_sides)
+ 
+         events: list[NarrativeEvent] = [
+             NarrativeEvent(t=0, kind=EventKind.MATCH_START,
+@@ -49,6 +53,7 @@ class CS2DemoAdapter(GameAdapter):
+                            importance=0.5, protagonist_involved=True)
+         ]
+ 
++        events += self._round_phase_events(rounds, protagonist_round_sides, starting_side)
+         for _, row in kills.iterrows():
+             t = float(row.get("tick", 0)) / TICK_RATE
+             attacker = str(row.get("attacker_name", "?"))
+@@ -65,13 +70,9 @@ class CS2DemoAdapter(GameAdapter):
+                 protagonist_involved=mine,
+                 data={"headshot": hs, "weapon": weapon}))
+ 
+-        for _, row in rounds.iterrows():
+-            t = float(row.get("tick", 0)) / TICK_RATE
+-            winner = row.get("winner", "")
+-            events.append(NarrativeEvent(
+-                t=t, kind=EventKind.PHASE,
+-                summary=f"Round ends - side {winner} takes it.",
+-                importance=0.5, data={"winner": winner}))
++        events += self._clutch_events(
++            kills, protagonist_name, protagonist_round_sides, starting_side
++        )
+ 
+         for df, phrase, kind in ((plants, "The bomb is planted.", EventKind.OBJECTIVE),
+                                  (defuses, "The bomb is defused.", EventKind.TRIUMPH)):
+@@ -92,7 +93,7 @@ class CS2DemoAdapter(GameAdapter):
+         context = MatchContext(
+             game="cs2",
+             protagonist=Protagonist(name=protagonist_name, persona="operator"),
+-            outcome="unknown",  # refined in v0.2 from team round tallies
++            outcome=self._resolve_outcome(rounds, protagonist_round_sides, starting_side),
+             duration=duration,
+             world={"map": header.get("map_name", "unknown"),
+                    "time_unit": "seconds"},
+@@ -110,3 +111,205 @@ class CS2DemoAdapter(GameAdapter):
+             # most frequent attacker = most active player
+             return max(set(map(str, names)), key=names.count)
+         return hint or "the operator"
++
++    @staticmethod
++    def _round_phase_events(rounds_df, protagonist_round_sides: dict[int, str], starting_side: str | None) -> list[NarrativeEvent]:
++        events: list[NarrativeEvent] = []
++        score = {"T": 0, "CT": 0}
++        match_point_markers: set[str] = set()
++        overtime_emitted = False
++
++        for fallback_round, row in enumerate(CS2DemoAdapter._rows(rounds_df), start=1):
++            round_number = CS2DemoAdapter._round_number(row, fallback_round)
++            winner = CS2DemoAdapter._normalize_side(row.get("winner"))
++            if winner is None:
++                continue
++
++            score[winner] += 1
++            t = float(row.get("tick", 0)) / TICK_RATE
++            events.append(NarrativeEvent(
++                t=t,
++                kind=EventKind.PHASE,
++                summary=(
++                    f"Round {round_number} goes to the {CS2DemoAdapter._side_label(winner)} "
++                    f"({score['CT']}-{score['T']})"
++                ),
++                importance=0.5,
++                protagonist_involved=(
++                    CS2DemoAdapter._protagonist_side_for_round(
++                        round_number, protagonist_round_sides, starting_side
++                    ) == winner
++                ),
++                data={"winner": winner, "round": round_number, "score": dict(score)},
++            ))
++
++            if score["T"] == 12 and score["CT"] == 12 and not overtime_emitted:
++                overtime_emitted = True
++                events.append(NarrativeEvent(
++                    t=t,
++                    kind=EventKind.PHASE,
++                    summary="Overtime begins at 12-12.",
++                    importance=0.6,
++                    data={"round": round_number, "score": dict(score)},
++                ))
++
++            for side in ("T", "CT"):
++                if score[side] == 12 and side not in match_point_markers:
++                    match_point_markers.add(side)
++                    events.append(NarrativeEvent(
++                        t=t,
++                        kind=EventKind.PHASE,
++                        summary=f"The {CS2DemoAdapter._side_label(side)} reach match point.",
++                        importance=0.6,
++                        data={"side": side, "round": round_number, "score": dict(score)},
++                    ))
++
++        return events
++
++    @staticmethod
++    def _clutch_events(kills_df, protagonist_name: str, protagonist_round_sides: dict[int, str], starting_side: str | None) -> list[NarrativeEvent]:
++        events: list[NarrativeEvent] = []
++        rows_by_round: dict[int, list[dict]] = {}
++
++        for fallback_round, row in enumerate(CS2DemoAdapter._rows(kills_df), start=1):
++            round_number = CS2DemoAdapter._round_number(row, fallback_round)
++            rows_by_round.setdefault(round_number, []).append(row)
++
++        for round_number, rows in rows_by_round.items():
++            protagonist_side = CS2DemoAdapter._protagonist_side_for_round(
++                round_number, protagonist_round_sides, starting_side
++            )
++            enemy_side = CS2DemoAdapter._opposite_side(protagonist_side)
++            if protagonist_side is None or enemy_side is None:
++                continue
++
++            alive = {"T": 5, "CT": 5}
++            clutch_window_open = False
++            clutch_kills = 0
++            clutch_tick: float | None = None
++
++            for row in sorted(rows, key=lambda item: float(item.get("tick", 0))):
++                attacker = str(row.get("attacker_name", ""))
++                victim_side = CS2DemoAdapter._normalize_side(row.get("user_team_name"))
++
++                if clutch_window_open and attacker == protagonist_name:
++                    clutch_kills += 1
++                    clutch_tick = float(row.get("tick", 0)) / TICK_RATE
++
++                if victim_side in alive and alive[victim_side] > 0:
++                    alive[victim_side] -= 1
++
++                if alive[protagonist_side] < alive[enemy_side]:
++                    clutch_window_open = True
++
++            if clutch_kills >= 3 and clutch_tick is not None:
++                events.append(NarrativeEvent(
++                    t=clutch_tick,
++                    kind=EventKind.TRIUMPH,
++                    actor=protagonist_name,
++                    summary=f"{protagonist_name} clutches the round.",
++                    importance=0.85,
++                    protagonist_involved=True,
++                    data={"round": round_number, "kills_after_disadvantage": clutch_kills},
++                ))
++
++        return events
++
++    @staticmethod
++    def _resolve_outcome(rounds_df, protagonist_round_sides: dict[int, str], starting_side: str | None) -> str:
++        if starting_side is None:
++            return "unknown"
++
++        protagonist_wins = 0
++        opponent_wins = 0
++        for fallback_round, row in enumerate(CS2DemoAdapter._rows(rounds_df), start=1):
++            round_number = CS2DemoAdapter._round_number(row, fallback_round)
++            winner = CS2DemoAdapter._normalize_side(row.get("winner"))
++            protagonist_side = CS2DemoAdapter._protagonist_side_for_round(
++                round_number, protagonist_round_sides, starting_side
++            )
++            if winner is None or protagonist_side is None:
++                continue
++            if winner == protagonist_side:
++                protagonist_wins += 1
++            else:
++                opponent_wins += 1
++
++        if protagonist_wins > opponent_wins:
++            return "victory"
++        if protagonist_wins < opponent_wins:
++            return "defeat"
++        if protagonist_wins or opponent_wins:
++            return "draw"
++        return "unknown"
++
++    @staticmethod
++    def _resolve_protagonist_round_sides(kills_df, protagonist_name: str) -> dict[int, str]:
++        sides: dict[int, str] = {}
++        for fallback_round, row in enumerate(CS2DemoAdapter._rows(kills_df), start=1):
++            round_number = CS2DemoAdapter._round_number(row, fallback_round)
++            side: str | None = None
++            if str(row.get("attacker_name", "")) == protagonist_name:
++                side = CS2DemoAdapter._normalize_side(row.get("attacker_team_name"))
++            elif str(row.get("user_name", "")) == protagonist_name:
++                side = CS2DemoAdapter._normalize_side(row.get("user_team_name"))
++            if side and round_number not in sides:
++                sides[round_number] = side
++        return sides
++
++    @staticmethod
++    def _protagonist_side_for_round(round_number: int, round_sides: dict[int, str], starting_side: str | None) -> str | None:
++        if round_number in round_sides:
++            return round_sides[round_number]
++        if starting_side is None:
++            return None
++        if round_number <= 12:
++            return starting_side
++        return CS2DemoAdapter._opposite_side(starting_side)
++
++    @staticmethod
++    def _first_known_side(round_sides: dict[int, str]) -> str | None:
++        if not round_sides:
++            return None
++        first_round = min(round_sides)
++        return round_sides[first_round]
++
++    @staticmethod
++    def _round_number(row: dict, fallback_round: int) -> int:
++        value = row.get("round_num", row.get("round", fallback_round))
++        try:
++            return int(value)
++        except (TypeError, ValueError):
++            return fallback_round
++
++    @staticmethod
++    def _rows(frame) -> Iterable[dict]:
++        for _, row in frame.iterrows():
++            yield row
++
++    @staticmethod
++    def _normalize_side(value: object) -> str | None:
++        if isinstance(value, str):
++            normalized = value.strip().upper()
++            if normalized in {"T", "TERRORIST", "TERRORISTS", "2"}:
++                return "T"
++            if normalized in {"CT", "COUNTER-TERRORIST", "COUNTER_TERRORIST", "COUNTERTERRORIST", "3"}:
++                return "CT"
++        elif isinstance(value, (int, float)):
++            if int(value) == 2:
++                return "T"
++            if int(value) == 3:
++                return "CT"
++        return None
++
++    @staticmethod
++    def _opposite_side(side: str | None) -> str | None:
++        if side == "T":
++            return "CT"
++        if side == "CT":
++            return "T"
++        return None
++
++    @staticmethod
++    def _side_label(side: str) -> str:
++        return "CTs" if side == "CT" else "Ts"
+warning: in the working copy of '.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md', CRLF will be replaced by LF the next time Git touches it
+```
+
+## Original spec
+
+## Context
+
+The CS2 adapter (`retale/adapters/cs2_demo.py`) leaves `outcome="unknown"` and
+ignores the economy - but round economy IS the dramatic stakes of CS, and clutches
+are the climaxes.
+
+## Scope
+
+You may touch: `retale/adapters/cs2_demo.py`, plus create
+`tests/test_cs2_adapter.py` with mocked demoparser2 output (pandas DataFrames).
+demoparser2 itself must remain an optional import; tests must NOT require a real
+.dem file - build DataFrames by hand. You may import pandas inside tests only.
+
+## Requirements
+
+1. **Outcome resolution**: track round wins per side from `round_end` (`winner`
+   column, values like "T"/"CT" or 2/3 depending on demoparser2 version - handle
+   both). Determine the protagonist's team from kill rows (`attacker_team_name` /
+   `user_team_name` if present; otherwise leave unknown). Set
+   `context.outcome` to victory/defeat/draw and add per-round PHASE summaries
+   like "Round 7 goes to the CTs (8-5)". Handle side swap at halftime (round 13
+   in MR12) when computing the protagonist's final team result.
+2. **Clutch detection**: within each round, if the protagonist gets >=3 kills
+   after the point where their side has fewer alive players than the enemy
+   (approximate: count deaths per side from player_death rows), emit
+   `EventKind.TRIUMPH` "X clutches the round" importance 0.85. If exact
+   alive-count is not derivable from available columns, document the
+   approximation you used in the report notes.
+3. **Match point / overtime markers**: emit PHASE events with importance 0.6
+   when either side reaches match point, and at overtime start.
+
+## Acceptance criteria
+
+- [ ] `tests/test_cs2_adapter.py` covers: outcome victory & defeat cases,
+      halftime side-swap correctness, one synthetic clutch detected, match-point
+      marker present. All with hand-built DataFrames, no .dem files.
+- [ ] Adapter still imports demoparser2 lazily (module import must not fail
+      without it) - add a test asserting `retale.adapters.cs2_demo` imports fine.
+- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
diff --git a/.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md b/.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md
index ef6cdf0..78f7baa 100644
--- a/.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md
+++ b/.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md
@@ -1,7 +1,7 @@
 ---
 id: T-002
 title: 'CS2 adapter: outcome resolution, round stakes, clutch detection'
-status: todo
+status: review
 priority: 2
 depends: []
 ---
diff --git a/retale/adapters/cs2_demo.py b/retale/adapters/cs2_demo.py
index 29590ad..abad9a1 100644
--- a/retale/adapters/cs2_demo.py
+++ b/retale/adapters/cs2_demo.py
@@ -10,6 +10,8 @@ map them onto the ReTale schema. Ticks are converted to seconds at
 
 from __future__ import annotations
 
+from collections.abc import Iterable
+
 from retale.adapters.base import ExtractionResult, GameAdapter
 from retale.core.schema import (
     EventKind,
@@ -40,6 +42,8 @@ class CS2DemoAdapter(GameAdapter):
         defuses = parser.parse_event("bomb_defused")
 
         protagonist_name = self._resolve_protagonist(kills, protagonist_hint)
+        protagonist_round_sides = self._resolve_protagonist_round_sides(kills, protagonist_name)
+        starting_side = protagonist_round_sides.get(1) or self._first_known_side(protagonist_round_sides)
 
         events: list[NarrativeEvent] = [
             NarrativeEvent(t=0, kind=EventKind.MATCH_START,
@@ -49,6 +53,7 @@ class CS2DemoAdapter(GameAdapter):
                            importance=0.5, protagonist_involved=True)
         ]
 
+        events += self._round_phase_events(rounds, protagonist_round_sides, starting_side)
         for _, row in kills.iterrows():
             t = float(row.get("tick", 0)) / TICK_RATE
             attacker = str(row.get("attacker_name", "?"))
@@ -65,13 +70,9 @@ class CS2DemoAdapter(GameAdapter):
                 protagonist_involved=mine,
                 data={"headshot": hs, "weapon": weapon}))
 
-        for _, row in rounds.iterrows():
-            t = float(row.get("tick", 0)) / TICK_RATE
-            winner = row.get("winner", "")
-            events.append(NarrativeEvent(
-                t=t, kind=EventKind.PHASE,
-                summary=f"Round ends - side {winner} takes it.",
-                importance=0.5, data={"winner": winner}))
+        events += self._clutch_events(
+            kills, protagonist_name, protagonist_round_sides, starting_side
+        )
 
         for df, phrase, kind in ((plants, "The bomb is planted.", EventKind.OBJECTIVE),
                                  (defuses, "The bomb is defused.", EventKind.TRIUMPH)):
@@ -92,7 +93,7 @@ class CS2DemoAdapter(GameAdapter):
         context = MatchContext(
             game="cs2",
             protagonist=Protagonist(name=protagonist_name, persona="operator"),
-            outcome="unknown",  # refined in v0.2 from team round tallies
+            outcome=self._resolve_outcome(rounds, protagonist_round_sides, starting_side),
             duration=duration,
             world={"map": header.get("map_name", "unknown"),
                    "time_unit": "seconds"},
@@ -110,3 +111,205 @@ class CS2DemoAdapter(GameAdapter):
             # most frequent attacker = most active player
             return max(set(map(str, names)), key=names.count)
         return hint or "the operator"
+
+    @staticmethod
+    def _round_phase_events(rounds_df, protagonist_round_sides: dict[int, str], starting_side: str | None) -> list[NarrativeEvent]:
+        events: list[NarrativeEvent] = []
+        score = {"T": 0, "CT": 0}
+        match_point_markers: set[str] = set()
+        overtime_emitted = False
+
+        for fallback_round, row in enumerate(CS2DemoAdapter._rows(rounds_df), start=1):
+            round_number = CS2DemoAdapter._round_number(row, fallback_round)
+            winner = CS2DemoAdapter._normalize_side(row.get("winner"))
+            if winner is None:
+                continue
+
+            score[winner] += 1
+            t = float(row.get("tick", 0)) / TICK_RATE
+            events.append(NarrativeEvent(
+                t=t,
+                kind=EventKind.PHASE,
+                summary=(
+                    f"Round {round_number} goes to the {CS2DemoAdapter._side_label(winner)} "
+                    f"({score['CT']}-{score['T']})"
+                ),
+                importance=0.5,
+                protagonist_involved=(
+                    CS2DemoAdapter._protagonist_side_for_round(
+                        round_number, protagonist_round_sides, starting_side
+                    ) == winner
+                ),
+                data={"winner": winner, "round": round_number, "score": dict(score)},
+            ))
+
+            if score["T"] == 12 and score["CT"] == 12 and not overtime_emitted:
+                overtime_emitted = True
+                events.append(NarrativeEvent(
+                    t=t,
+                    kind=EventKind.PHASE,
+                    summary="Overtime begins at 12-12.",
+                    importance=0.6,
+                    data={"round": round_number, "score": dict(score)},
+                ))
+
+            for side in ("T", "CT"):
+                if score[side] == 12 and side not in match_point_markers:
+                    match_point_markers.add(side)
+                    events.append(NarrativeEvent(
+                        t=t,
+                        kind=EventKind.PHASE,
+                        summary=f"The {CS2DemoAdapter._side_label(side)} reach match point.",
+                        importance=0.6,
+                        data={"side": side, "round": round_number, "score": dict(score)},
+                    ))
+
+        return events
+
+    @staticmethod
+    def _clutch_events(kills_df, protagonist_name: str, protagonist_round_sides: dict[int, str], starting_side: str | None) -> list[NarrativeEvent]:
+        events: list[NarrativeEvent] = []
+        rows_by_round: dict[int, list[dict]] = {}
+
+        for fallback_round, row in enumerate(CS2DemoAdapter._rows(kills_df), start=1):
+            round_number = CS2DemoAdapter._round_number(row, fallback_round)
+            rows_by_round.setdefault(round_number, []).append(row)
+
+        for round_number, rows in rows_by_round.items():
+            protagonist_side = CS2DemoAdapter._protagonist_side_for_round(
+                round_number, protagonist_round_sides, starting_side
+            )
+            enemy_side = CS2DemoAdapter._opposite_side(protagonist_side)
+            if protagonist_side is None or enemy_side is None:
+                continue
+
+            alive = {"T": 5, "CT": 5}
+            clutch_window_open = False
+            clutch_kills = 0
+            clutch_tick: float | None = None
+
+            for row in sorted(rows, key=lambda item: float(item.get("tick", 0))):
+                attacker = str(row.get("attacker_name", ""))
+                victim_side = CS2DemoAdapter._normalize_side(row.get("user_team_name"))
+
+                if clutch_window_open and attacker == protagonist_name:
+                    clutch_kills += 1
+                    clutch_tick = float(row.get("tick", 0)) / TICK_RATE
+
+                if victim_side in alive and alive[victim_side] > 0:
+                    alive[victim_side] -= 1
+
+                if alive[protagonist_side] < alive[enemy_side]:
+                    clutch_window_open = True
+
+            if clutch_kills >= 3 and clutch_tick is not None:
+                events.append(NarrativeEvent(
+                    t=clutch_tick,
+                    kind=EventKind.TRIUMPH,
+                    actor=protagonist_name,
+                    summary=f"{protagonist_name} clutches the round.",
+                    importance=0.85,
+                    protagonist_involved=True,
+                    data={"round": round_number, "kills_after_disadvantage": clutch_kills},
+                ))
+
+        return events
+
+    @staticmethod
+    def _resolve_outcome(rounds_df, protagonist_round_sides: dict[int, str], starting_side: str | None) -> str:
+        if starting_side is None:
+            return "unknown"
+
+        protagonist_wins = 0
+        opponent_wins = 0
+        for fallback_round, row in enumerate(CS2DemoAdapter._rows(rounds_df), start=1):
+            round_number = CS2DemoAdapter._round_number(row, fallback_round)
+            winner = CS2DemoAdapter._normalize_side(row.get("winner"))
+            protagonist_side = CS2DemoAdapter._protagonist_side_for_round(
+                round_number, protagonist_round_sides, starting_side
+            )
+            if winner is None or protagonist_side is None:
+                continue
+            if winner == protagonist_side:
+                protagonist_wins += 1
+            else:
+                opponent_wins += 1
+
+        if protagonist_wins > opponent_wins:
+            return "victory"
+        if protagonist_wins < opponent_wins:
+            return "defeat"
+        if protagonist_wins or opponent_wins:
+            return "draw"
+        return "unknown"
+
+    @staticmethod
+    def _resolve_protagonist_round_sides(kills_df, protagonist_name: str) -> dict[int, str]:
+        sides: dict[int, str] = {}
+        for fallback_round, row in enumerate(CS2DemoAdapter._rows(kills_df), start=1):
+            round_number = CS2DemoAdapter._round_number(row, fallback_round)
+            side: str | None = None
+            if str(row.get("attacker_name", "")) == protagonist_name:
+                side = CS2DemoAdapter._normalize_side(row.get("attacker_team_name"))
+            elif str(row.get("user_name", "")) == protagonist_name:
+                side = CS2DemoAdapter._normalize_side(row.get("user_team_name"))
+            if side and round_number not in sides:
+                sides[round_number] = side
+        return sides
+
+    @staticmethod
+    def _protagonist_side_for_round(round_number: int, round_sides: dict[int, str], starting_side: str | None) -> str | None:
+        if round_number in round_sides:
+            return round_sides[round_number]
+        if starting_side is None:
+            return None
+        if round_number <= 12:
+            return starting_side
+        return CS2DemoAdapter._opposite_side(starting_side)
+
+    @staticmethod
+    def _first_known_side(round_sides: dict[int, str]) -> str | None:
+        if not round_sides:
+            return None
+        first_round = min(round_sides)
+        return round_sides[first_round]
+
+    @staticmethod
+    def _round_number(row: dict, fallback_round: int) -> int:
+        value = row.get("round_num", row.get("round", fallback_round))
+        try:
+            return int(value)
+        except (TypeError, ValueError):
+            return fallback_round
+
+    @staticmethod
+    def _rows(frame) -> Iterable[dict]:
+        for _, row in frame.iterrows():
+            yield row
+
+    @staticmethod
+    def _normalize_side(value: object) -> str | None:
+        if isinstance(value, str):
+            normalized = value.strip().upper()
+            if normalized in {"T", "TERRORIST", "TERRORISTS", "2"}:
+                return "T"
+            if normalized in {"CT", "COUNTER-TERRORIST", "COUNTER_TERRORIST", "COUNTERTERRORIST", "3"}:
+                return "CT"
+        elif isinstance(value, (int, float)):
+            if int(value) == 2:
+                return "T"
+            if int(value) == 3:
+                return "CT"
+        return None
+
+    @staticmethod
+    def _opposite_side(side: str | None) -> str | None:
+        if side == "T":
+            return "CT"
+        if side == "CT":
+            return "T"
+        return None
+
+    @staticmethod
+    def _side_label(side: str) -> str:
+        return "CTs" if side == "CT" else "Ts"
diff --git a/tests/test_cs2_adapter.py b/tests/test_cs2_adapter.py
new file mode 100644
index 0000000..f77084c
--- /dev/null
+++ b/tests/test_cs2_adapter.py
@@ -0,0 +1,210 @@
+"""Tests for the CS2 adapter using synthetic demoparser2 outputs."""
+
+from __future__ import annotations
+
+import importlib
+import sys
+import types
+
+from retale.adapters.cs2_demo import CS2DemoAdapter
+from retale.core.schema import EventKind
+
+
+def _frame(rows: list[dict], columns: list[str] | None = None):
+    import pandas as pd
+
+    if rows:
+        return pd.DataFrame(rows)
+    return pd.DataFrame(columns=columns or [])
+
+
+def _round_rows(winners: list[object]) -> list[dict]:
+    return [
+        {"round_num": index, "tick": float(index * 6400), "winner": winner}
+        for index, winner in enumerate(winners, start=1)
+    ]
+
+
+def _install_fake_demoparser(monkeypatch, header: dict, kills_rows: list[dict], round_winners: list[object]):
+    fake_module = types.ModuleType("demoparser2")
+    events = {
+        "player_death": _frame(kills_rows),
+        "round_end": _frame(_round_rows(round_winners)),
+        "bomb_planted": _frame([], columns=["tick", "user_name"]),
+        "bomb_defused": _frame([], columns=["tick", "user_name"]),
+    }
+
+    class DemoParser:
+        def __init__(self, source: str):
+            self.source = source
+
+        def parse_header(self) -> dict:
+            return header
+
+        def parse_event(self, name: str):
+            return events[name]
+
+    fake_module.DemoParser = DemoParser
+    monkeypatch.setitem(sys.modules, "demoparser2", fake_module)
+
+
+def test_cs2_module_imports_without_demoparser(monkeypatch):
+    monkeypatch.delitem(sys.modules, "demoparser2", raising=False)
+    module = importlib.reload(importlib.import_module("retale.adapters.cs2_demo"))
+    assert module.CS2DemoAdapter.game_id == "cs2"
+
+
+def test_cs2_adapter_victory_clutch_and_match_point(monkeypatch):
+    round_winners = [2] * 6 + [3] * 6 + [3] * 7 + [2] * 5
+    kills_rows = [
+        {
+            "round_num": 1,
+            "tick": 640.0,
+            "attacker_name": "Hero",
+            "attacker_team_name": "T",
+            "user_name": "Enemy1",
+            "user_team_name": "CT",
+            "headshot": False,
+            "weapon": "ak47",
+        },
+        {
+            "round_num": 13,
+            "tick": 13 * 6400 + 640.0,
+            "attacker_name": "Hero",
+            "attacker_team_name": "CT",
+            "user_name": "Enemy2",
+            "user_team_name": "T",
+            "headshot": False,
+            "weapon": "m4a1_silencer",
+        },
+        {
+            "round_num": 19,
+            "tick": 19 * 6400 + 100.0,
+            "attacker_name": "Enemy3",
+            "attacker_team_name": "T",
+            "user_name": "Ally1",
+            "user_team_name": "CT",
+            "headshot": False,
+            "weapon": "ak47",
+        },
+        {
+            "round_num": 19,
+            "tick": 19 * 6400 + 200.0,
+            "attacker_name": "Hero",
+            "attacker_team_name": "CT",
+            "user_name": "Enemy4",
+            "user_team_name": "T",
+            "headshot": True,
+            "weapon": "m4a1_silencer",
+        },
+        {
+            "round_num": 19,
+            "tick": 19 * 6400 + 300.0,
+            "attacker_name": "Hero",
+            "attacker_team_name": "CT",
+            "user_name": "Enemy5",
+            "user_team_name": "T",
+            "headshot": False,
+            "weapon": "m4a1_silencer",
+        },
+        {
+            "round_num": 19,
+            "tick": 19 * 6400 + 400.0,
+            "attacker_name": "Enemy6",
+            "attacker_team_name": "T",
+            "user_name": "Ally2",
+            "user_team_name": "CT",
+            "headshot": False,
+            "weapon": "ak47",
+        },
+        {
+            "round_num": 19,
+            "tick": 19 * 6400 + 500.0,
+            "attacker_name": "Hero",
+            "attacker_team_name": "CT",
+            "user_name": "Enemy7",
+            "user_team_name": "T",
+            "headshot": False,
+            "weapon": "m4a1_silencer",
+        },
+    ]
+    _install_fake_demoparser(
+        monkeypatch,
+        header={"map_name": "de_ancient"},
+        kills_rows=kills_rows,
+        round_winners=round_winners,
+    )
+
+    extraction = CS2DemoAdapter().extract("synthetic.dem", protagonist_hint="Hero")
+    phase_summaries = [event.summary for event in extraction.events if event.kind == EventKind.PHASE]
+    clutch_events = [event for event in extraction.events if event.summary == "Hero clutches the round."]
+
+    assert extraction.context.outcome == "victory"
+    assert any(summary == "Round 13 goes to the CTs (7-6)" for summary in phase_summaries)
+    assert any("match point" in summary for summary in phase_summaries)
+    assert len(clutch_events) == 1
+    assert clutch_events[0].importance == 0.85
+
+
+def test_cs2_adapter_defeat_case(monkeypatch):
+    round_winners = ["CT"] * 5 + ["T"] * 7 + ["T"] * 6 + ["CT"] * 6
+    kills_rows = [
+        {
+            "round_num": 1,
+            "tick": 640.0,
+            "attacker_name": "Enemy1",
+            "attacker_team_name": "T",
+            "user_name": "Hero",
+            "user_team_name": "CT",
+            "headshot": False,
+            "weapon": "ak47",
+        },
+        {
+            "round_num": 13,
+            "tick": 13 * 6400 + 640.0,
+            "attacker_name": "Hero",
+            "attacker_team_name": "T",
+            "user_name": "Enemy2",
+            "user_team_name": "CT",
+            "headshot": False,
+            "weapon": "ak47",
+        },
+    ]
+    _install_fake_demoparser(
+        monkeypatch,
+        header={"map_name": "de_nuke"},
+        kills_rows=kills_rows,
+        round_winners=round_winners,
+    )
+
+    extraction = CS2DemoAdapter().extract("synthetic.dem", protagonist_hint="Hero")
+
+    assert extraction.context.outcome == "defeat"
+
+
+def test_cs2_adapter_marks_overtime_start(monkeypatch):
+    round_winners = [2, 3] * 12
+    kills_rows = [
+        {
+            "round_num": 1,
+            "tick": 640.0,
+            "attacker_name": "Hero",
+            "attacker_team_name": "T",
+            "user_name": "Enemy1",
+            "user_team_name": "CT",
+            "headshot": False,
+            "weapon": "ak47",
+        }
+    ]
+    _install_fake_demoparser(
+        monkeypatch,
+        header={"map_name": "de_mirage"},
+        kills_rows=kills_rows,
+        round_winners=round_winners,
+    )
+
+    extraction = CS2DemoAdapter().extract("synthetic.dem", protagonist_hint="Hero")
+    phase_summaries = [event.summary for event in extraction.events if event.kind == EventKind.PHASE]
+
+    assert extraction.context.outcome == "draw"
+    assert "Overtime begins at 12-12." in phase_summaries
warning: in the working copy of '.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/reports/T-002-report.md', CRLF will be replaced by LF the next time Git touches it
```

## Original spec

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
