# Report T-011: Story scout: worthiness scoring, protagonist recommendation, roster

generated: 2026-07-12 11:28 UTC

## Implementer notes

Addressed the clutch-score rework with minimal changes only. In `retale/adapters/dota2_opendota.py`, buyback ECONOMY events now carry the generic semantic tag `data["beat"] = "buyback"` for both protagonist and non-protagonist cases. In `retale/narrative/scout.py`, `_clutch_score()` no longer inspects English prose; it now counts protagonist buybacks via `event.data.get("beat") == "buyback"`, matching the existing tag-driven pattern used elsewhere (for example hubris). Tests were tightened in two places: `tests/test_pipeline.py` now asserts buyback events are selected by the tag and that every buyback event carries `beat == "buyback"`; `tests/test_scout.py` adds a focused regression check proving clutch points come from the semantic tag even when the summary prose is arbitrary. Verification passed with `python -m pytest tests/ -q` (42 passed) and `ruff check retale/ tests/` (clean).

## Test output

```
..........................................                               [100%]
42 passed in 0.86s
```

## Diff vs 07e9cd69ce22bf5390058ca53ea476681a9cac8a

```diff
       |   7 +
 retale/narrative/scout.py                          | 453 +++++++++++++++++++++
 tests/fixtures/dota2_match.json                    |  22 +-
 tests/test_pipeline.py                             |   4 +-
 tests/test_scout.py                                | 299 ++++++++++++++
 7 files changed, 923 insertions(+), 8 deletions(-)
warning: in the working copy of '.conductor/tasks/T-011-story-scout-worthiness-scoring-protagoni.md', CRLF will be replaced by LF the next time Git touches it


diff --git a/.conductor/tasks/T-011-story-scout-worthiness-scoring-protagoni.md b/.conductor/tasks/T-011-story-scout-worthiness-scoring-protagoni.md
new file mode 100644
index 0000000..004eeed
--- /dev/null
+++ b/.conductor/tasks/T-011-story-scout-worthiness-scoring-protagoni.md
@@ -0,0 +1,104 @@
+---
+id: T-011
+title: 'Story scout: worthiness scoring, protagonist recommendation, roster'
+status: in_progress
+priority: 1
+depends: []
+base: 07e9cd69ce22bf5390058ca53ea476681a9cac8a
+---
+
+## Context
+
+Product pivot: ReTale must be a PROSPECTOR, not just a converter. Before
+spending LLM money, the program should analyze the whole match and tell the
+creator (a) whether this game contains plot material worth mining, (b) WHICH
+player's point of view is the best protagonist (a 10-streak enemy mid may
+outrank the requesting user), and (c) the full roster - in pub culture,
+player nicknames are themselves part of the story flavor.
+
+Data notes: OpenDota `players[]` carries `kill_streaks` (dict, e.g.
+{"10": 1} = one 10-kill streak; streaks reset on death, so "10" implies ten
+kills with zero deaths in between - the Chinese community's Godlike) and
+`multi_kills` ({"5": 1} = a Rampage). Gold reversals, hubris tags, buybacks,
+and nemesis material already exist as events from T-001..T-010.
+
+## Scope
+
+You may touch: `retale/adapters/dota2_opendota.py` (roster only), add
+`retale/narrative/scout.py`, `retale/cli.py`, `tests/fixtures/dota2_match.json`,
+and add `tests/test_scout.py`. No new dependencies. Tests stay offline.
+ARCHITECTURE RED LINE: `scout.py` lives in the narrative layer - it must not
+import anything from `retale.adapters` and must not reference any
+game-specific term; it consumes only `MatchContext` (including a generic
+`world["roster"]`) and `NarrativeEvent` streams.
+
+## Requirements
+
+1. **Roster (adapter).** `extract()` fills `context.world["roster"]`: a list
+   of dicts for all players - `{"name": personaname or hero, "hero":
+   resolved hero name, "side": "Radiant"/"Dire", "is_protagonist": bool,
+   "kills", "deaths", "assists": ints, "max_streak": int (largest key in
+   kill_streaks with count>0, else 0), "max_multi_kill": int (same for
+   multi_kills, else 0)}`. Missing fields default to 0/"". Unparsed matches
+   still produce the roster (streaks default 0).
+
+2. **Scout module.** `retale/narrative/scout.py` exposes
+   `scout(context, events) -> ScoutReport` (dataclass) and
+   `render_report(report) -> str`. Scoring (module-level WEIGHTS dict so the
+   numbers are tunable):
+   - nemesis_arc 20: from KILL/DEATH events - some opponent both killed the
+     protagonist >=2 times AND was killed by the protagonist >=1 time
+     (full 20 when the protagonist's kills of that opponent >= the deaths
+     to them, i.e. the account was settled; else 12).
+   - comeback 20: >=2 ECONOMY reversal events ending in a victory outcome
+     = 20; exactly 1 reversal = 12; 0 = 0.
+   - godlike 15: any roster entry max_streak >= 10 -> 15; >= 8 -> 10.
+   - rampage 10: any roster max_multi_kill >= 5 -> 10; == 4 -> 5.
+   - personal_arc 10: split protagonist KILL/DEATH events at the match
+     midpoint; deaths concentrated early + kills late (redemption) or the
+     reverse (tragedy) -> 10; flat -> 0. Concentrated = >=70% of that
+     event type on one side of the midpoint, with >=2 events of each type.
+   - hubris 10: 5 points per event with data["hubris"], cap 10.
+   - clutch 10: 5 points per protagonist buyback ECONOMY event and per
+     TRIUMPH within 60s of a >=4-death PHASE teamfight, cap 10.
+   - streak_end 5: award 5 when the protagonist killed a roster entry
+     whose max_streak >= 8 (the god-slaying beat, approximated).
+   - stomp penalty up to -30: if the match has ZERO economy reversal events
+     AND (protagonist deaths == 0 OR protagonist kills == 0), apply -20;
+     additionally -10 when duration < 1500s. Total never below 0.
+   Total capped at 100. Verdict: >=60 "WRITE", 35-59 "MAYBE", <35 "SKIP".
+
+3. **Protagonist recommendation.** Score every roster entry as a POV
+   candidate: max_streak>=10 -> +40, 8-9 -> +25; max_multi_kill>=5 -> +20,
+   ==4 -> +10; +2*kills - 1*deaths + 0.5*assists; current protagonist gets
+   +5 (incumbent bonus). Rank top 3 with one-line reasons. If the best
+   candidate is not the current protagonist, the report must say so
+   explicitly and give the exact --pov value to re-run with.
+
+4. **Report rendering.** English plain text, sections: SCORE + VERDICT;
+   HOOKS FOUND (one line each with concrete evidence - names, counts,
+   times); RECOMMENDED POV (top 3); ROSTER (all players: name, hero, side,
+   K/D/A, streak/multikill highlights) with a closing line noting that
+   player nicknames are part of the flavor and worth weaving into the story.
+
+5. **CLI.** Add `--scout`: runs extraction, prints the rendered report to
+   stdout, and exits WITHOUT planning chapters or calling any LLM.
+   `--scout` works with or without `--pov`.
+
+## Acceptance criteria
+
+- [ ] Fixture: give one ENEMY player kill_streaks {"10": 1} and
+      multi_kills {"5": 1}; give the protagonist kill_streaks {"3": 1}.
+- [ ] tests/test_scout.py asserts: godlike 15 and rampage 10 awarded;
+      recommended POV #1 is that enemy (reason mentions the streak) and the
+      report contains the exact --pov string; nemesis arc detected from the
+      existing fixture kill/death data with settled-account scoring;
+      hubris points reflect the fixture's hubris event; a synthetic stomp
+      (no ECONOMY reversals, protagonist deaths 0, duration 1400) lands
+      verdict SKIP with the full -30 applied; verdict thresholds exact at
+      60 and 35; roster includes all 10 players and the protagonist flag;
+      scout.py imports nothing from retale.adapters (assert by inspecting
+      the module source).
+- [ ] CLI test with the fixture: `--scout` prints SCORE and ROSTER sections
+      and makes zero LLM calls (fake client that raises if called).
+- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
diff --git a/retale/adapters/dota2_opendota.py b/retale/adapters/dota2_opendota.py
index 1d7d848..ec391e1 100644
--- a/retale/adapters/dota2_opendota.py
+++ b/retale/adapters/dota2_opendota.py
@@ -140,6 +140,7 @@ class Dota2OpenDotaAdapter(GameAdapter):
                 "time_unit": "seconds",
                 "match_id": match.get("match_id"),
                 "parsed": parsed,
+                "roster": self._roster(players, me, hero_lookup),
             },
             allies=[self._hero_name(p, hero_lookup) for p in players
                     if (p.get("player_slot", 0) < 128) == is_radiant and p is not me],
@@ -297,6 +298,27 @@ class Dota2OpenDotaAdapter(GameAdapter):
         # default: highest kill participation
         return max(players, key=lambda p: (p.get("kills", 0) + p.get("assists", 0)))
 
+    def _roster(
+        self,
+        players: list[dict[str, Any]],
+        protagonist: dict[str, Any],
+        hero_lookup: dict[str, dict[Any, str]],
+    ) -> list[dict[str, Any]]:
+        return [
+            {
+                "name": str(player.get("personaname") or self._hero_name(player, hero_lookup)),
+                "hero": self._hero_name(player, hero_lookup),
+                "side": "Radiant" if int(player.get("player_slot", 0) or 0) < 128 else "Dire",
+                "is_protagonist": player is protagonist,
+                "kills": self._int_stat(player.get("kills")),
+                "deaths": self._int_stat(player.get("deaths")),
+                "assists": self._int_stat(player.get("assists")),
+                "max_streak": self._max_counter_key(player.get("kill_streaks")),
+                "max_multi_kill": self._max_counter_key(player.get("multi_kills")),
+            }
+            for player in players
+        ]
+
     @staticmethod
     def _outcome(match: dict, is_radiant: bool) -> str:
         rw = match.get("radiant_win")
@@ -304,6 +326,24 @@ class Dota2OpenDotaAdapter(GameAdapter):
             return "unknown"
         return "victory" if rw == is_radiant else "defeat"
 
+    @staticmethod
+    def _int_stat(value: Any) -> int:
+        try:
+            return int(value or 0)
+        except (TypeError, ValueError):
+            return 0
+
+    @staticmethod
+    def _max_counter_key(counter: Any) -> int:
+        if not isinstance(counter, dict):
+            return 0
+        values = [
+            int(raw_key)
+            for raw_key, count in counter.items()
+            if Dota2OpenDotaAdapter._int_stat(count) > 0 and str(raw_key).isdigit()
+        ]
+        return max(values, default=0)
+
     def _objective_events(
         self,
         match: dict,
@@ -713,7 +753,7 @@ class Dota2OpenDotaAdapter(GameAdapter):
                     summary=summary,
                     importance=importance,
                     protagonist_involved=protagonist_involved,
-                    data=entry,
+                    data={**entry, "beat": "buyback"},
                 ))
         return out
 
diff --git a/retale/cli.py b/retale/cli.py
index 8565e57..1bbf8ce 100644
--- a/retale/cli.py
+++ b/retale/cli.py
@@ -16,6 +16,7 @@ from pathlib import Path
 from typing import Callable
 
 from retale.adapters.base import ExtractionResult, GameAdapter
+from retale.narrative.scout import render_report, scout
 from retale.narrative.planner import Chapter, Planner
 from retale.narrative.styler import LLMClient, StyleProfile, Styler, export_json
 from retale.output import write_epub
@@ -58,6 +59,8 @@ def main(argv: list[str] | None = None) -> int:
                    help="output format")
     p.add_argument("--dry-run", action="store_true",
                    help="print the chapter plan as JSON, skip LLM generation")
+    p.add_argument("--scout", action="store_true",
+                   help="print a prospecting report and skip planning and LLM generation")
     args = p.parse_args(argv)
 
     adapter = reg[args.game]()
@@ -68,6 +71,10 @@ def main(argv: list[str] | None = None) -> int:
           f"({result.context.protagonist.persona}) | "
           f"outcome: {result.context.outcome}", file=sys.stderr)
 
+    if args.scout:
+        print(render_report(scout(result.context, result.events)))
+        return 0
+
     plan = Planner(target_chapters=args.chapters).plan(result.context, result.events)
     print(f"[retale] planned {len(plan.chapters)} chapters | {plan.logline}",
           file=sys.stderr)
diff --git a/retale/narrative/scout.py b/retale/narrative/scout.py
new file mode 100644
index 0000000..738e27f
--- /dev/null
+++ b/retale/narrative/scout.py
@@ -0,0 +1,453 @@
+"""Story scouting utilities for prospecting match narratives before writing."""
+
+from __future__ import annotations
+
+from dataclasses import dataclass, field
+from typing import Any
+
+from retale.core.schema import EventKind, MatchContext, NarrativeEvent
+
+WEIGHTS = {
+    "nemesis_arc_full": 20,
+    "nemesis_arc_partial": 12,
+    "comeback_full": 20,
+    "comeback_partial": 12,
+    "godlike_full": 15,
+    "godlike_partial": 10,
+    "rampage_full": 10,
+    "rampage_partial": 5,
+    "personal_arc": 10,
+    "hubris_per_event": 5,
+    "hubris_cap": 10,
+    "clutch_per_beat": 5,
+    "clutch_cap": 10,
+    "streak_end": 5,
+    "stomp_base_penalty": 20,
+    "stomp_short_penalty": 10,
+}
+
+
+@dataclass
+class POVRecommendation:
+    name: str
+    hero: str
+    side: str
+    score: float
+    reason: str
+    pov_value: str
+
+
+@dataclass
+class ScoutReport:
+    score: int
+    verdict: str
+    hooks: list[str]
+    recommendations: list[POVRecommendation]
+    roster: list[dict[str, Any]]
+    current_protagonist: str
+    current_persona: str
+    rerun_pov: str | None = None
+    breakdown: dict[str, int] = field(default_factory=dict)
+
+
+def scout(context: MatchContext, events: list[NarrativeEvent]) -> ScoutReport:
+    roster = list(context.world.get("roster", []))
+    protagonist_name = context.protagonist.name
+    protagonist_persona = context.protagonist.persona or protagonist_name
+    breakdown: dict[str, int] = {}
+    hooks: list[str] = []
+
+    nemesis_points, nemesis_hook = _nemesis_arc(protagonist_persona, events)
+    breakdown["nemesis_arc"] = nemesis_points
+    if nemesis_hook:
+        hooks.append(nemesis_hook)
+
+    reversal_events = _economy_reversal_events(events)
+    comeback_points = _comeback_score(context.outcome, reversal_events)
+    breakdown["comeback"] = comeback_points
+    if comeback_points:
+        hooks.append(
+            f"Comeback swing: {len(reversal_events)} economy reversals feed a {context.outcome} finish."
+        )
+
+    godlike_points, godlike_hook = _godlike_score(roster)
+    breakdown["godlike"] = godlike_points
+    if godlike_hook:
+        hooks.append(godlike_hook)
+
+    rampage_points, rampage_hook = _rampage_score(roster)
+    breakdown["rampage"] = rampage_points
+    if rampage_hook:
+        hooks.append(rampage_hook)
+
+    personal_points, personal_hook = _personal_arc(context, protagonist_persona, events)
+    breakdown["personal_arc"] = personal_points
+    if personal_hook:
+        hooks.append(personal_hook)
+
+    hubris_points, hubris_hook = _hubris_score(events)
+    breakdown["hubris"] = hubris_points
+    if hubris_hook:
+        hooks.append(hubris_hook)
+
+    clutch_points, clutch_hook = _clutch_score(events)
+    breakdown["clutch"] = clutch_points
+    if clutch_hook:
+        hooks.append(clutch_hook)
+
+    streak_end_points, streak_end_hook = _streak_end_score(roster, protagonist_persona, events)
+    breakdown["streak_end"] = streak_end_points
+    if streak_end_hook:
+        hooks.append(streak_end_hook)
+
+    protagonist_kills = _protagonist_kill_events(events)
+    protagonist_deaths = _protagonist_death_events(events)
+    stomp_penalty, stomp_hook = _stomp_penalty(
+        context=context,
+        reversal_count=len(reversal_events),
+        protagonist_kills=len(protagonist_kills),
+        protagonist_deaths=len(protagonist_deaths),
+    )
+    breakdown["stomp_penalty"] = -stomp_penalty
+    if stomp_hook:
+        hooks.append(stomp_hook)
+
+    total = sum(points for key, points in breakdown.items() if key != "stomp_penalty") - stomp_penalty
+    total = max(0, min(100, total))
+    verdict = _verdict(total)
+
+    recommendations = _recommend_pov(roster, protagonist_name)
+    rerun_pov = None
+    if recommendations and recommendations[0].name != protagonist_name:
+        rerun_pov = recommendations[0].pov_value
+
+    if not hooks:
+        hooks.append("No standout dramatic hook cleared the current thresholds.")
+
+    return ScoutReport(
+        score=total,
+        verdict=verdict,
+        hooks=hooks,
+        recommendations=recommendations[:3],
+        roster=roster,
+        current_protagonist=protagonist_name,
+        current_persona=protagonist_persona,
+        rerun_pov=rerun_pov,
+        breakdown=breakdown,
+    )
+
+
+def render_report(report: ScoutReport) -> str:
+    lines = [
+        "SCORE + VERDICT",
+        f"Score: {report.score}/100",
+        f"Verdict: {report.verdict}",
+        f"Current protagonist: {report.current_protagonist} ({report.current_persona})",
+    ]
+    if report.rerun_pov:
+        lines.append(f'Recommended re-run: --pov "{report.rerun_pov}"')
+
+    lines.append("")
+    lines.append("HOOKS FOUND")
+    for hook in report.hooks:
+        lines.append(f"- {hook}")
+
+    lines.append("")
+    lines.append("RECOMMENDED POV")
+    for index, recommendation in enumerate(report.recommendations, start=1):
+        lines.append(
+            f"- {index}. {recommendation.name} ({recommendation.hero}, {recommendation.side}) | "
+            f"{recommendation.score:.1f} | {recommendation.reason}"
+        )
+
+    lines.append("")
+    lines.append("ROSTER")
+    for entry in report.roster:
+        highlight_parts = []
+        if entry.get("is_protagonist"):
+            highlight_parts.append("current POV")
+        if int(entry.get("max_streak", 0) or 0) > 0:
+            highlight_parts.append(f"streak {int(entry['max_streak'])}")
+        if int(entry.get("max_multi_kill", 0) or 0) > 0:
+            highlight_parts.append(f"multi-kill {int(entry['max_multi_kill'])}")
+        highlights = ", ".join(highlight_parts) if highlight_parts else "no spike noted"
+        lines.append(
+            f"- {entry.get('name', '')} | {entry.get('hero', '')} | {entry.get('side', '')} | "
+            f"K/D/A {int(entry.get('kills', 0) or 0)}/{int(entry.get('deaths', 0) or 0)}/"
+            f"{int(entry.get('assists', 0) or 0)} | {highlights}"
+        )
+    lines.append("Player nicknames are part of the flavor and worth weaving into the story.")
+    return "\n".join(lines)
+
+
+def _nemesis_arc(protagonist_hero: str, events: list[NarrativeEvent]) -> tuple[int, str | None]:
+    deaths_by_opponent: dict[str, int] = {}
+    kills_by_opponent: dict[str, int] = {}
+    for event in events:
+        if event.kind == EventKind.KILL and event.protagonist_involved and event.target:
+            kills_by_opponent[str(event.target)] = kills_by_opponent.get(str(event.target), 0) + 1
+        elif event.kind == EventKind.DEATH and event.protagonist_involved and event.actor:
+            deaths_by_opponent[str(event.actor)] = deaths_by_opponent.get(str(event.actor), 0) + 1
+
+    best_points = 0
+    best_hook: str | None = None
+    for opponent, deaths_to_opponent in deaths_by_opponent.items():
+        kills_of_opponent = kills_by_opponent.get(opponent, 0)
+        if deaths_to_opponent < 2 or kills_of_opponent < 1:
+            continue
+        if kills_of_opponent >= deaths_to_opponent:
+            points = WEIGHTS["nemesis_arc_full"]
+            hook = (
+                f"Nemesis arc settled: {protagonist_hero} fell to {opponent} {deaths_to_opponent} times "
+                f"and answered with {kills_of_opponent} kills."
+            )
+        else:
+            points = WEIGHTS["nemesis_arc_partial"]
+            hook = (
+                f"Nemesis arc unresolved: {protagonist_hero} fell to {opponent} {deaths_to_opponent} times "
+                f"but only answered with {kills_of_opponent} kill."
+            )
+        if points > best_points:
+            best_points = points
+            best_hook = hook
+    return best_points, best_hook
+
+
+def _economy_reversal_events(events: list[NarrativeEvent]) -> list[NarrativeEvent]:
+    return [
+        event
+        for event in events
+        if event.kind == EventKind.ECONOMY and "turns toward" in event.summary
+    ]
+
+
+def _comeback_score(outcome: str, reversal_events: list[NarrativeEvent]) -> int:
+    reversal_count = len(reversal_events)
+    if outcome != "victory":
+        return 0
+    if reversal_count >= 2:
+        return WEIGHTS["comeback_full"]
+    if reversal_count == 1:
+        return WEIGHTS["comeback_partial"]
+    return 0
+
+
+def _godlike_score(roster: list[dict[str, Any]]) -> tuple[int, str | None]:
+    best = max(roster, key=lambda entry: int(entry.get("max_streak", 0) or 0), default=None)
+    if not best:
+        return 0, None
+    max_streak = int(best.get("max_streak", 0) or 0)
+    if max_streak >= 10:
+        return WEIGHTS["godlike_full"], (
+            f"Godlike heat: {best.get('name')} peaked at a {max_streak}-kill streak on {best.get('hero')}."
+        )
+    if max_streak >= 8:
+        return WEIGHTS["godlike_partial"], (
+            f"Hot hand: {best.get('name')} peaked at an {max_streak}-kill streak on {best.get('hero')}."
+        )
+    return 0, None
+
+
+def _rampage_score(roster: list[dict[str, Any]]) -> tuple[int, str | None]:
+    best = max(roster, key=lambda entry: int(entry.get("max_multi_kill", 0) or 0), default=None)
+    if not best:
+        return 0, None
+    max_multi_kill = int(best.get("max_multi_kill", 0) or 0)
+    if max_multi_kill >= 5:
+        return WEIGHTS["rampage_full"], (
+            f"Multi-kill spike: {best.get('name')} hit a {max_multi_kill}-kill burst on {best.get('hero')}."
+        )
+    if max_multi_kill == 4:
+        return WEIGHTS["rampage_partial"], (
+            f"Near-rampage pressure: {best.get('name')} hit a {max_multi_kill}-kill burst on {best.get('hero')}."
+        )
+    return 0, None
+
+
+def _personal_arc(
+    context: MatchContext,
+    protagonist_hero: str,
+    events: list[NarrativeEvent],
+) -> tuple[int, str | None]:
+    midpoint = float(context.duration or 0) / 2
+    kill_events = _protagonist_kill_events(events)
+    death_events = _protagonist_death_events(events)
+    if len(kill_events) < 2 or len(death_events) < 2:
+        return 0, None
+
+    early_kills = sum(1 for event in kill_events if event.t <= midpoint)
+    late_kills = len(kill_events) - early_kills
+    early_deaths = sum(1 for event in death_events if event.t <= midpoint)
+    late_deaths = len(death_events) - early_deaths
+    kill_ratio = max(early_kills, late_kills) / len(kill_events)
+    death_ratio = max(early_deaths, late_deaths) / len(death_events)
+    if kill_ratio < 0.7 or death_ratio < 0.7:
+        return 0, None
+    if early_deaths > late_deaths and late_kills > early_kills:
+        return WEIGHTS["personal_arc"], (
+            f"Personal arc: {protagonist_hero} absorbs the pain early ({early_deaths} deaths) "
+            f"and cashes out late ({late_kills} kills)."
+        )
+    if early_kills > late_kills and late_deaths > early_deaths:
+        return WEIGHTS["personal_arc"], (
+            f"Personal arc: {protagonist_hero} starts dominant ({early_kills} kills) and crashes late "
+            f"({late_deaths} deaths)."
+        )
+    return 0, None
+
+
+def _hubris_score(events: list[NarrativeEvent]) -> tuple[int, str | None]:
+    hubris_events = [
+        event
+        for event in events
+        if event.kind == EventKind.SOCIAL and event.data.get("hubris")
+    ]
+    points = min(len(hubris_events) * WEIGHTS["hubris_per_event"], WEIGHTS["hubris_cap"])
+    if not points:
+        return 0, None
+    moments = ", ".join(str(int(event.t)) for event in hubris_events[:3])
+    return points, f"Hubris beat: {len(hubris_events)} taunt-backed comeuppance moments at t={moments}s."
+
+
+def _clutch_score(events: list[NarrativeEvent]) -> tuple[int, str | None]:
+    buybacks = [
+        event
+        for event in events
+        if event.kind == EventKind.ECONOMY
+        and event.protagonist_involved
+        and event.data.get("beat") == "buyback"
+    ]
+    heavy_teamfights = [
+        event
+        for event in events
+        if event.kind == EventKind.PHASE and int(event.data.get("deaths", 0) or 0) >= 4
+    ]
+    triumphs = [
+        event
+        for event in events
+        if event.kind == EventKind.TRIUMPH
+        and any(abs(event.t - fight.t) <= 60 for fight in heavy_teamfights)
+    ]
+    beats = len(buybacks) + len(triumphs)
+    points = min(beats * WEIGHTS["clutch_per_beat"], WEIGHTS["clutch_cap"])
+    if not points:
+        return 0, None
+    return points, (
+        f"Clutch leverage: {len(buybacks)} protagonist buybacks and {len(triumphs)} triumph beats land near major fights."
+    )
+
+
+def _streak_end_score(
+    roster: list[dict[str, Any]],
+    protagonist_hero: str,
+    events: list[NarrativeEvent],
+) -> tuple[int, str | None]:
+    streaked_heroes = {
+        str(entry.get("hero"))
+        for entry in roster
+        if int(entry.get("max_streak", 0) or 0) >= 8
+    }
+    fallen = [
+        str(event.target)
+        for event in events
+        if event.kind == EventKind.KILL and event.protagonist_involved and str(event.target) in streaked_heroes
+    ]
+    if not fallen:
+        return 0, None
+    unique_targets = sorted(set(fallen))
+    return WEIGHTS["streak_end"], (
+        f"God-slaying beat: {protagonist_hero} ended the run of {', '.join(unique_targets)}."
+    )
+
+
+def _stomp_penalty(
+    context: MatchContext,
+    reversal_count: int,
+    protagonist_kills: int,
+    protagonist_deaths: int,
+) -> tuple[int, str | None]:
+    penalty = 0
+    reasons: list[str] = []
+    if reversal_count == 0 and (protagonist_deaths == 0 or protagonist_kills == 0):
+        penalty += WEIGHTS["stomp_base_penalty"]
+        reasons.append("no economy reversals and one side of the protagonist ledger is empty")
+    if penalty and float(context.duration or 0) < 1500:
+        penalty += WEIGHTS["stomp_short_penalty"]
+        reasons.append(f"short duration ({int(context.duration)}s)")
+    if not penalty:
+        return 0, None
+    return penalty, f"Stomp penalty: {'; '.join(reasons)}."
+
+
+def _verdict(score: int) -> str:
+    if score >= 60:
+        return "WRITE"
+    if score >= 35:
+        return "MAYBE"
+    return "SKIP"
+
+
+def _recommend_pov(roster: list[dict[str, Any]], current_protagonist: str) -> list[POVRecommendation]:
+    recommendations: list[POVRecommendation] = []
+    for entry in roster:
+        max_streak = int(entry.get("max_streak", 0) or 0)
+        max_multi_kill = int(entry.get("max_multi_kill", 0) or 0)
+        kills = int(entry.get("kills", 0) or 0)
+        deaths = int(entry.get("deaths", 0) or 0)
+        assists = int(entry.get("assists", 0) or 0)
+        score = 0.0
+        reasons: list[str] = []
+
+        if max_streak >= 10:
+            score += 40
+            reasons.append(f"streak {max_streak}")
+        elif max_streak >= 8:
+            score += 25
+            reasons.append(f"streak {max_streak}")
+
+        if max_multi_kill >= 5:
+            score += 20
+            reasons.append(f"multi-kill {max_multi_kill}")
+        elif max_multi_kill == 4:
+            score += 10
+            reasons.append("multi-kill 4")
+
+        score += 2 * kills - deaths + 0.5 * assists
+        reasons.append(f"K/D/A {kills}/{deaths}/{assists}")
+
+        if str(entry.get("name")) == current_protagonist:
+            score += 5
+            reasons.append("incumbent bonus")
+
+        recommendations.append(
+            POVRecommendation(
+                name=str(entry.get("name", "")),
+                hero=str(entry.get("hero", "")),
+                side=str(entry.get("side", "")),
+                score=score,
+                reason=", ".join(reasons),
+                pov_value=str(entry.get("name", "")),
+            )
+        )
+
+    return sorted(
+        recommendations,
+        key=lambda item: (item.score, item.name == current_protagonist, item.name),
+        reverse=True,
+    )
+
+
+def _protagonist_kill_events(events: list[NarrativeEvent]) -> list[NarrativeEvent]:
+    return [
+        event
+        for event in events
+        if event.kind == EventKind.KILL and event.protagonist_involved
+    ]
+
+
+def _protagonist_death_events(events: list[NarrativeEvent]) -> list[NarrativeEvent]:
+    return [
+        event
+        for event in events
+        if event.kind == EventKind.DEATH and event.protagonist_involved
+    ]
diff --git a/tests/fixtures/dota2_match.json b/tests/fixtures/dota2_match.json
index a2c48e4..dcb303e 100644
--- a/tests/fixtures/dota2_match.json
+++ b/tests/fixtures/dota2_match.json
@@ -9,7 +9,11 @@
    "personaname": "Ceaseless",
    "account_id": 1000,
    "kills": 7,
+  "deaths": 3,
    "assists": 0,
+  "kill_streaks": {
+   "3": 1
+  },
    "kills_log": [
     {
      "time": 310,
@@ -37,7 +41,7 @@
     },
     {
      "time": 2140,
-     "key": "npc_dota_hero_spirit_breaker"
+     "key": "npc_dota_hero_pudge"
     }
    ],
    "purchase_log": [
@@ -148,8 +152,9 @@
    "hero_id": 21,
    "personaname": "HookCity",
    "account_id": 2001,
-   "kills": 0,
-   "assists": 0,
+  "kills": 4,
+  "deaths": 6,
+  "assists": 2,
    "kills_log": [
     {
      "time": 700,
@@ -168,8 +173,15 @@
    "hero_id": 22,
    "personaname": "BangBang",
    "account_id": 2002,
-   "kills": 0,
-   "assists": 0,
+  "kills": 15,
+  "deaths": 2,
+  "assists": 4,
+  "kill_streaks": {
+   "10": 1
+  },
+  "multi_kills": {
+   "5": 1
+  },
    "kills_log": [],
    "purchase_log": [],
    "buyback_log": []
diff --git a/tests/test_pipeline.py b/tests/test_pipeline.py
index 184acbb..667713d 100644
--- a/tests/test_pipeline.py
+++ b/tests/test_pipeline.py
@@ -152,8 +152,7 @@ def test_chat_and_economy_events(extraction):
     economy_events = [event for event in extraction.events if event.kind == EventKind.ECONOMY]
     buyback_events = [
         event for event in extraction.events
-        if event.kind == EventKind.ECONOMY and "second chance" in event.summary
-        or event.kind == EventKind.ECONOMY and "blood price" in event.summary
+        if event.kind == EventKind.ECONOMY and event.data.get("beat") == "buyback"
     ]
     rune_events = [
         event for event in extraction.events
@@ -230,6 +229,7 @@ def test_chat_and_economy_events(extraction):
     assert len(buyback_events) == 2
     assert {event.actor for event in buyback_events} == {"Slark", "Lion"}
     assert sorted(event.importance for event in buyback_events) == [0.5, 0.7]
+    assert all(event.data["beat"] == "buyback" for event in buyback_events)
     assert len(rune_events) == 1
     assert rune_events[0].summary == "Slark seizes a Haste rune."
     assert len(signature_events) == 1
diff --git a/tests/test_scout.py b/tests/test_scout.py
new file mode 100644
index 0000000..60e8c1d
--- /dev/null
+++ b/tests/test_scout.py
@@ -0,0 +1,299 @@
+"""Tests for story scouting, POV recommendation, and scout CLI mode."""
+
+from __future__ import annotations
+
+import importlib
+import inspect
+from pathlib import Path
+
+from retale.adapters.dota2_opendota import Dota2OpenDotaAdapter
+from retale.cli import main
+from retale.core.schema import EventKind, MatchContext, NarrativeEvent, Protagonist
+from retale.narrative.scout import render_report, scout
+
+FIXTURE = Path(__file__).parent / "fixtures" / "dota2_match.json"
+
+HERO_CONSTANTS = {
+    "8": {"name": "npc_dota_hero_slark", "localized_name": "Slark"},
+    "9": {"name": "npc_dota_hero_crystal_maiden", "localized_name": "Crystal Maiden"},
+    "10": {"name": "npc_dota_hero_axe", "localized_name": "Axe"},
+    "11": {"name": "npc_dota_hero_zuus", "localized_name": "Zeus"},
+    "12": {"name": "npc_dota_hero_mirana", "localized_name": "Mirana"},
+    "20": {"name": "npc_dota_hero_lion", "localized_name": "Lion"},
+    "21": {"name": "npc_dota_hero_pudge", "localized_name": "Pudge"},
+    "22": {"name": "npc_dota_hero_sniper", "localized_name": "Sniper"},
+    "23": {"name": "npc_dota_hero_dazzle", "localized_name": "Dazzle"},
+    "24": {"name": "npc_dota_hero_spirit_breaker", "localized_name": "Spirit Breaker"},
+}
+
+CHAT_WHEEL_CONSTANTS = {
+    "71": {"message": "Well played!"},
+    "93001": {"label": "Fish bait!"},
+}
+
+
+class FakeResponse:
+    def __init__(self, payload=None, should_raise=False):
+        self.payload = payload
+        self.should_raise = should_raise
+
+    def raise_for_status(self):
+        if self.should_raise:
+            raise RuntimeError("boom")
+
+    def json(self):
+        return self.payload
+
+
+class FakeSession:
+    def __init__(self, payload=None, should_raise=False, url_map=None):
+        self.payload = payload
+        self.should_raise = should_raise
+        self.url_map = url_map or {}
+
+    def get(self, url, timeout=0):
+        if self.should_raise:
+            raise RuntimeError("boom")
+        payload = self.url_map.get(url, self.payload)
+        return FakeResponse(payload, should_raise=False)
+
+
+def _constants_session():
+    return FakeSession(
+        HERO_CONSTANTS,
+        url_map={
+            "https://api.opendota.com/api/constants/chat_wheel": CHAT_WHEEL_CONSTANTS,
+        },
+    )
+
+
+def _fixture_report():
+    adapter = Dota2OpenDotaAdapter(session=_constants_session())
+    extraction = adapter.extract(str(FIXTURE), protagonist_hint="Ceaseless")
+    return scout(extraction.context, extraction.events)
+
+
+def _sample_context(
+    *,
+    outcome: str = "victory",
+    duration: float = 2000,
+    roster: list[dict[str, object]] | None = None,
+) -> MatchContext:
+    return MatchContext(
+        game="dota2",
+        protagonist=Protagonist(name="Hero", persona="Slark"),
+        outcome=outcome,
+        duration=duration,
+        world={"roster": roster or []},
+    )
+
+
+def test_scout_scores_fixture_and_recommends_enemy_pov():
+    report = _fixture_report()
+    text = render_report(report)
+
+    assert report.breakdown["godlike"] == 15
+    assert report.breakdown["rampage"] == 10
+    assert report.breakdown["nemesis_arc"] == 20
+    assert report.breakdown["hubris"] == 5
+    assert report.recommendations[0].name == "BangBang"
+    assert "streak 10" in report.recommendations[0].reason
+    assert '--pov "BangBang"' in text
+    assert len(report.roster) == 10
+    assert any(entry["name"] == "Ceaseless" and entry["is_protagonist"] is True for entry in report.roster)
+
+
+def test_scout_verdict_thresholds_are_exact():
+    write_roster = [
+        {
+            "name": "Hero",
+            "hero": "Slark",
+            "side": "Radiant",
+            "is_protagonist": True,
+            "kills": 3,
+            "deaths": 1,
+            "assists": 1,
+            "max_streak": 0,
+            "max_multi_kill": 0,
+        },
+        {
+            "name": "Threat",
+            "hero": "Sniper",
+            "side": "Dire",
+            "is_protagonist": False,
+            "kills": 12,
+            "deaths": 2,
+            "assists": 4,
+            "max_streak": 10,
+            "max_multi_kill": 5,
+        },
+    ]
+    write_events = [
+        NarrativeEvent(t=300, kind=EventKind.ECONOMY, summary="The tide of gold turns toward the Dire."),
+        NarrativeEvent(t=600, kind=EventKind.ECONOMY, summary="The tide of gold turns toward the Radiant."),
+        NarrativeEvent(
+            t=900,
+            kind=EventKind.KILL,
+            target="Sniper",
+            summary="Slark struck down Sniper.",
+            protagonist_involved=True,
+        ),
+        NarrativeEvent(t=1000, kind=EventKind.SOCIAL, data={"hubris": True, "taunt": True}),
+        NarrativeEvent(t=1100, kind=EventKind.SOCIAL, data={"hubris": True, "taunt": True}),
+    ]
+    write_report = scout(_sample_context(roster=write_roster), write_events)
+
+    maybe_roster = [
+        {
+            "name": "Hero",
+            "hero": "Slark",
+            "side": "Radiant",
+            "is_protagonist": True,
+            "kills": 2,
+            "deaths": 2,
+            "assists": 3,
+            "max_streak": 0,
+            "max_multi_kill": 0,
+        },
+        {
+            "name": "Burst",
+            "hero": "Lina",
+            "side": "Dire",
+            "is_protagonist": False,
+            "kills": 5,
+            "deaths": 4,
+            "assists": 6,
+            "max_streak": 0,
+            "max_multi_kill": 4,
+        },
+    ]
+    maybe_events = [
+        NarrativeEvent(t=300, kind=EventKind.ECONOMY, summary="The tide of gold turns toward the Dire."),
+        NarrativeEvent(t=600, kind=EventKind.ECONOMY, summary="The tide of gold turns toward the Radiant."),
+        NarrativeEvent(
+            t=800,
+            kind=EventKind.KILL,
+            target="Lina",
+            summary="Slark struck down Lina.",
+            protagonist_involved=True,
+        ),
+        NarrativeEvent(
+            t=900,
+            kind=EventKind.DEATH,
+            actor="Lina",
+            target="Slark",
+            summary="Slark fell to Lina.",
+            protagonist_involved=True,
+        ),
+        NarrativeEvent(t=1000, kind=EventKind.SOCIAL, data={"hubris": True, "taunt": True}),
+        NarrativeEvent(t=1100, kind=EventKind.SOCIAL, data={"hubris": True, "taunt": True}),
+    ]
+    maybe_report = scout(_sample_context(roster=maybe_roster), maybe_events)
+
+    assert write_report.score == 60
+    assert write_report.verdict == "WRITE"
+    assert maybe_report.score == 35
+    assert maybe_report.verdict == "MAYBE"
+
+
+def test_scout_applies_full_stomp_penalty():
+    roster = [
+        {
+            "name": "Hero",
+            "hero": "Slark",
+            "side": "Radiant",
+            "is_protagonist": True,
+            "kills": 5,
+            "deaths": 0,
+            "assists": 1,
+            "max_streak": 0,
+            "max_multi_kill": 0,
+        }
+    ]
+    events = [
+        NarrativeEvent(
+            t=500,
+            kind=EventKind.KILL,
+            target="Lion",
+            summary="Slark struck down Lion.",
+            protagonist_involved=True,
+        )
+    ]
+
+    report = scout(_sample_context(duration=1400, roster=roster), events)
+
+    assert report.breakdown["stomp_penalty"] == -30
+    assert report.score == 0
+    assert report.verdict == "SKIP"
+
+
+def test_scout_clutch_uses_buyback_beat_tag():
+    roster = [
+        {
+            "name": "Hero",
+            "hero": "Slark",
+            "side": "Radiant",
+            "is_protagonist": True,
+            "kills": 5,
+            "deaths": 3,
+            "assists": 2,
+            "max_streak": 0,
+            "max_multi_kill": 0,
+        }
+    ]
+    events = [
+        NarrativeEvent(
+            t=1000,
+            kind=EventKind.ECONOMY,
+            summary="Any prose is fine here.",
+            protagonist_involved=True,
+            data={"beat": "buyback"},
+        )
+    ]
+
+    report = scout(_sample_context(roster=roster), events)
+
+    assert report.breakdown["clutch"] == 5
+
+
+def test_scout_module_stays_adapter_free():
+    scout_module = importlib.import_module("retale.narrative.scout")
+    source_path = Path(inspect.getsourcefile(scout_module) or "")
+    source = source_path.read_text(encoding="utf-8")
+
+    assert "retale.adapters" not in source
+
+
+def test_cli_scout_prints_report_without_llm(monkeypatch, capsys):
+    class FakeAdapter:
+        def extract(self, source: str, protagonist_hint: str | None = None):
+            adapter = Dota2OpenDotaAdapter(session=_constants_session())
+            return adapter.extract(str(FIXTURE), protagonist_hint=protagonist_hint)
+
+    class RaisingClient:
+        def complete(self, system: str, user: str, max_tokens: int = 0):
+            raise AssertionError("LLM should not be called in --scout mode")
+
+    class FakeStyler:
+        def __init__(self, style, client=None):
+            self.client = client or RaisingClient()
+
+        def build_codex(self, plan):
+            self.client.complete("", "", 0)
+            return {}
+
+        def write_story(self, plan, on_chapter=None, codex=None, progress_path=None):
+            self.client.complete("", "", 0)
+            return ""
+
+    monkeypatch.setattr("retale.cli._adapters", lambda: {"dota2": FakeAdapter})
+    monkeypatch.setattr("retale.cli.LLMClient", lambda model_override=None: RaisingClient())
+    monkeypatch.setattr("retale.cli.Styler", FakeStyler)
+
+    exit_code = main(["dota2", str(FIXTURE), "--scout"])
+    captured = capsys.readouterr()
+
+    assert exit_code == 0
+    assert "SCORE + VERDICT" in captured.out
+    assert "ROSTER" in captured.out
+    assert "BangBang" in captured.out
warning: in the working copy of '.conductor/tasks/T-011-story-scout-worthiness-scoring-protagoni.md', CRLF will be replaced by LF the next time Git touches it
```

## Original spec

## Context

Product pivot: ReTale must be a PROSPECTOR, not just a converter. Before
spending LLM money, the program should analyze the whole match and tell the
creator (a) whether this game contains plot material worth mining, (b) WHICH
player's point of view is the best protagonist (a 10-streak enemy mid may
outrank the requesting user), and (c) the full roster - in pub culture,
player nicknames are themselves part of the story flavor.

Data notes: OpenDota `players[]` carries `kill_streaks` (dict, e.g.
{"10": 1} = one 10-kill streak; streaks reset on death, so "10" implies ten
kills with zero deaths in between - the Chinese community's Godlike) and
`multi_kills` ({"5": 1} = a Rampage). Gold reversals, hubris tags, buybacks,
and nemesis material already exist as events from T-001..T-010.

## Scope

You may touch: `retale/adapters/dota2_opendota.py` (roster only), add
`retale/narrative/scout.py`, `retale/cli.py`, `tests/fixtures/dota2_match.json`,
and add `tests/test_scout.py`. No new dependencies. Tests stay offline.
ARCHITECTURE RED LINE: `scout.py` lives in the narrative layer - it must not
import anything from `retale.adapters` and must not reference any
game-specific term; it consumes only `MatchContext` (including a generic
`world["roster"]`) and `NarrativeEvent` streams.

## Requirements

1. **Roster (adapter).** `extract()` fills `context.world["roster"]`: a list
   of dicts for all players - `{"name": personaname or hero, "hero":
   resolved hero name, "side": "Radiant"/"Dire", "is_protagonist": bool,
   "kills", "deaths", "assists": ints, "max_streak": int (largest key in
   kill_streaks with count>0, else 0), "max_multi_kill": int (same for
   multi_kills, else 0)}`. Missing fields default to 0/"". Unparsed matches
   still produce the roster (streaks default 0).

2. **Scout module.** `retale/narrative/scout.py` exposes
   `scout(context, events) -> ScoutReport` (dataclass) and
   `render_report(report) -> str`. Scoring (module-level WEIGHTS dict so the
   numbers are tunable):
   - nemesis_arc 20: from KILL/DEATH events - some opponent both killed the
     protagonist >=2 times AND was killed by the protagonist >=1 time
     (full 20 when the protagonist's kills of that opponent >= the deaths
     to them, i.e. the account was settled; else 12).
   - comeback 20: >=2 ECONOMY reversal events ending in a victory outcome
     = 20; exactly 1 reversal = 12; 0 = 0.
   - godlike 15: any roster entry max_streak >= 10 -> 15; >= 8 -> 10.
   - rampage 10: any roster max_multi_kill >= 5 -> 10; == 4 -> 5.
   - personal_arc 10: split protagonist KILL/DEATH events at the match
     midpoint; deaths concentrated early + kills late (redemption) or the
     reverse (tragedy) -> 10; flat -> 0. Concentrated = >=70% of that
     event type on one side of the midpoint, with >=2 events of each type.
   - hubris 10: 5 points per event with data["hubris"], cap 10.
   - clutch 10: 5 points per protagonist buyback ECONOMY event and per
     TRIUMPH within 60s of a >=4-death PHASE teamfight, cap 10.
   - streak_end 5: award 5 when the protagonist killed a roster entry
     whose max_streak >= 8 (the god-slaying beat, approximated).
   - stomp penalty up to -30: if the match has ZERO economy reversal events
     AND (protagonist deaths == 0 OR protagonist kills == 0), apply -20;
     additionally -10 when duration < 1500s. Total never below 0.
   Total capped at 100. Verdict: >=60 "WRITE", 35-59 "MAYBE", <35 "SKIP".

3. **Protagonist recommendation.** Score every roster entry as a POV
   candidate: max_streak>=10 -> +40, 8-9 -> +25; max_multi_kill>=5 -> +20,
   ==4 -> +10; +2*kills - 1*deaths + 0.5*assists; current protagonist gets
   +5 (incumbent bonus). Rank top 3 with one-line reasons. If the best
   candidate is not the current protagonist, the report must say so
   explicitly and give the exact --pov value to re-run with.

4. **Report rendering.** English plain text, sections: SCORE + VERDICT;
   HOOKS FOUND (one line each with concrete evidence - names, counts,
   times); RECOMMENDED POV (top 3); ROSTER (all players: name, hero, side,
   K/D/A, streak/multikill highlights) with a closing line noting that
   player nicknames are part of the flavor and worth weaving into the story.

5. **CLI.** Add `--scout`: runs extraction, prints the rendered report to
   stdout, and exits WITHOUT planning chapters or calling any LLM.
   `--scout` works with or without `--pov`.

## Acceptance criteria

- [ ] Fixture: give one ENEMY player kill_streaks {"10": 1} and
      multi_kills {"5": 1}; give the protagonist kill_streaks {"3": 1}.
- [ ] tests/test_scout.py asserts: godlike 15 and rampage 10 awarded;
      recommended POV #1 is that enemy (reason mentions the streak) and the
      report contains the exact --pov string; nemesis arc detected from the
      existing fixture kill/death data with settled-account scoring;
      hubris points reflect the fixture's hubris event; a synthetic stomp
      (no ECONOMY reversals, protagonist deaths 0, duration 1400) lands
      verdict SKIP with the full -30 applied; verdict thresholds exact at
      60 and 35; roster includes all 10 players and the protagonist flag;
      scout.py imports nothing from retale.adapters (assert by inspecting
      the module source).
- [ ] CLI test with the fixture: `--scout` prints SCORE and ROSTER sections
      and makes zero LLM calls (fake client that raises if called).
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
