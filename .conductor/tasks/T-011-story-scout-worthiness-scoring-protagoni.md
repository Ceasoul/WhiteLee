---
id: T-011
title: 'Story scout: worthiness scoring, protagonist recommendation, roster'
status: done
priority: 1
depends: []
base: 07e9cd69ce22bf5390058ca53ea476681a9cac8a
---

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
