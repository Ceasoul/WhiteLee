"""Story scouting utilities for prospecting match narratives before writing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from retale.core.schema import EventKind, MatchContext, NarrativeEvent

WEIGHTS = {
    "nemesis_arc_full": 20,
    "nemesis_arc_partial": 12,
    "comeback_full": 20,
    "comeback_partial": 12,
    "godlike_full": 15,
    "godlike_partial": 10,
    "rampage_full": 10,
    "rampage_partial": 5,
    "personal_arc": 10,
    "hubris_per_event": 5,
    "hubris_cap": 10,
    "clutch_per_beat": 5,
    "clutch_cap": 10,
    "streak_end": 5,
    "stomp_base_penalty": 20,
    "stomp_short_penalty": 10,
}


@dataclass
class POVRecommendation:
    name: str
    hero: str
    side: str
    score: float
    reason: str
    pov_value: str


@dataclass
class ScoutReport:
    score: int
    verdict: str
    hooks: list[str]
    recommendations: list[POVRecommendation]
    roster: list[dict[str, Any]]
    current_protagonist: str
    current_persona: str
    rerun_pov: str | None = None
    breakdown: dict[str, int] = field(default_factory=dict)


def scout(context: MatchContext, events: list[NarrativeEvent]) -> ScoutReport:
    roster = list(context.world.get("roster", []))
    protagonist_name = context.protagonist.name
    protagonist_persona = context.protagonist.persona or protagonist_name
    breakdown: dict[str, int] = {}
    hooks: list[str] = []

    nemesis_points, nemesis_hook = _nemesis_arc(protagonist_persona, events)
    breakdown["nemesis_arc"] = nemesis_points
    if nemesis_hook:
        hooks.append(nemesis_hook)

    reversal_events = _economy_reversal_events(events)
    comeback_points = _comeback_score(context.outcome, reversal_events)
    breakdown["comeback"] = comeback_points
    if comeback_points:
        hooks.append(
            f"Comeback swing: {len(reversal_events)} economy reversals feed a {context.outcome} finish."
        )

    godlike_points, godlike_hook = _godlike_score(roster)
    breakdown["godlike"] = godlike_points
    if godlike_hook:
        hooks.append(godlike_hook)

    rampage_points, rampage_hook = _rampage_score(roster)
    breakdown["rampage"] = rampage_points
    if rampage_hook:
        hooks.append(rampage_hook)

    personal_points, personal_hook = _personal_arc(context, protagonist_persona, events)
    breakdown["personal_arc"] = personal_points
    if personal_hook:
        hooks.append(personal_hook)

    hubris_points, hubris_hook = _hubris_score(events)
    breakdown["hubris"] = hubris_points
    if hubris_hook:
        hooks.append(hubris_hook)

    clutch_points, clutch_hook = _clutch_score(events)
    breakdown["clutch"] = clutch_points
    if clutch_hook:
        hooks.append(clutch_hook)

    streak_end_points, streak_end_hook = _streak_end_score(roster, protagonist_persona, events)
    breakdown["streak_end"] = streak_end_points
    if streak_end_hook:
        hooks.append(streak_end_hook)

    protagonist_kills = _protagonist_kill_events(events)
    protagonist_deaths = _protagonist_death_events(events)
    stomp_penalty, stomp_hook = _stomp_penalty(
        context=context,
        reversal_count=len(reversal_events),
        protagonist_kills=len(protagonist_kills),
        protagonist_deaths=len(protagonist_deaths),
    )
    breakdown["stomp_penalty"] = -stomp_penalty
    if stomp_hook:
        hooks.append(stomp_hook)

    total = sum(points for key, points in breakdown.items() if key != "stomp_penalty") - stomp_penalty
    total = max(0, min(100, total))
    verdict = _verdict(total)

    recommendations = _recommend_pov(roster, protagonist_name)
    rerun_pov = None
    if recommendations and recommendations[0].name != protagonist_name:
        rerun_pov = recommendations[0].pov_value

    if not hooks:
        hooks.append("No standout dramatic hook cleared the current thresholds.")

    return ScoutReport(
        score=total,
        verdict=verdict,
        hooks=hooks,
        recommendations=recommendations[:3],
        roster=roster,
        current_protagonist=protagonist_name,
        current_persona=protagonist_persona,
        rerun_pov=rerun_pov,
        breakdown=breakdown,
    )


def render_report(report: ScoutReport) -> str:
    lines = [
        "SCORE + VERDICT",
        f"Score: {report.score}/100",
        f"Verdict: {report.verdict}",
        f"Current protagonist: {report.current_protagonist} ({report.current_persona})",
    ]
    if report.rerun_pov:
        lines.append(f'Recommended re-run: --pov "{report.rerun_pov}"')

    lines.append("")
    lines.append("HOOKS FOUND")
    for hook in report.hooks:
        lines.append(f"- {hook}")

    lines.append("")
    lines.append("RECOMMENDED POV")
    for index, recommendation in enumerate(report.recommendations, start=1):
        lines.append(
            f"- {index}. {recommendation.name} ({recommendation.hero}, {recommendation.side}) | "
            f"{recommendation.score:.1f} | {recommendation.reason}"
        )

    lines.append("")
    lines.append("ROSTER")
    for entry in report.roster:
        highlight_parts = []
        if entry.get("is_protagonist"):
            highlight_parts.append("current POV")
        if int(entry.get("max_streak", 0) or 0) > 0:
            highlight_parts.append(f"streak {int(entry['max_streak'])}")
        if int(entry.get("max_multi_kill", 0) or 0) > 0:
            highlight_parts.append(f"multi-kill {int(entry['max_multi_kill'])}")
        highlights = ", ".join(highlight_parts) if highlight_parts else "no spike noted"
        lines.append(
            f"- {entry.get('name', '')} | {entry.get('hero', '')} | {entry.get('side', '')} | "
            f"K/D/A {int(entry.get('kills', 0) or 0)}/{int(entry.get('deaths', 0) or 0)}/"
            f"{int(entry.get('assists', 0) or 0)} | {highlights}"
        )
    lines.append("Player nicknames are part of the flavor and worth weaving into the story.")
    return "\n".join(lines)


def _nemesis_arc(protagonist_hero: str, events: list[NarrativeEvent]) -> tuple[int, str | None]:
    deaths_by_opponent: dict[str, int] = {}
    kills_by_opponent: dict[str, int] = {}
    for event in events:
        if event.kind == EventKind.KILL and event.protagonist_involved and event.target:
            kills_by_opponent[str(event.target)] = kills_by_opponent.get(str(event.target), 0) + 1
        elif event.kind == EventKind.DEATH and event.protagonist_involved and event.actor:
            deaths_by_opponent[str(event.actor)] = deaths_by_opponent.get(str(event.actor), 0) + 1

    best_points = 0
    best_hook: str | None = None
    for opponent, deaths_to_opponent in deaths_by_opponent.items():
        kills_of_opponent = kills_by_opponent.get(opponent, 0)
        if deaths_to_opponent < 2 or kills_of_opponent < 1:
            continue
        if kills_of_opponent >= deaths_to_opponent:
            points = WEIGHTS["nemesis_arc_full"]
            hook = (
                f"Nemesis arc settled: {protagonist_hero} fell to {opponent} {deaths_to_opponent} times "
                f"and answered with {kills_of_opponent} kills."
            )
        else:
            points = WEIGHTS["nemesis_arc_partial"]
            hook = (
                f"Nemesis arc unresolved: {protagonist_hero} fell to {opponent} {deaths_to_opponent} times "
                f"but only answered with {kills_of_opponent} kill."
            )
        if points > best_points:
            best_points = points
            best_hook = hook
    return best_points, best_hook


def _economy_reversal_events(events: list[NarrativeEvent]) -> list[NarrativeEvent]:
    return [
        event
        for event in events
        if event.kind == EventKind.ECONOMY and "turns toward" in event.summary
    ]


def _comeback_score(outcome: str, reversal_events: list[NarrativeEvent]) -> int:
    reversal_count = len(reversal_events)
    if outcome != "victory":
        return 0
    if reversal_count >= 2:
        return WEIGHTS["comeback_full"]
    if reversal_count == 1:
        return WEIGHTS["comeback_partial"]
    return 0


def _godlike_score(roster: list[dict[str, Any]]) -> tuple[int, str | None]:
    best = max(roster, key=lambda entry: int(entry.get("max_streak", 0) or 0), default=None)
    if not best:
        return 0, None
    max_streak = int(best.get("max_streak", 0) or 0)
    if max_streak >= 10:
        return WEIGHTS["godlike_full"], (
            f"Godlike heat: {best.get('name')} peaked at a {max_streak}-kill streak on {best.get('hero')}."
        )
    if max_streak >= 8:
        return WEIGHTS["godlike_partial"], (
            f"Hot hand: {best.get('name')} peaked at an {max_streak}-kill streak on {best.get('hero')}."
        )
    return 0, None


def _rampage_score(roster: list[dict[str, Any]]) -> tuple[int, str | None]:
    best = max(roster, key=lambda entry: int(entry.get("max_multi_kill", 0) or 0), default=None)
    if not best:
        return 0, None
    max_multi_kill = int(best.get("max_multi_kill", 0) or 0)
    if max_multi_kill >= 5:
        return WEIGHTS["rampage_full"], (
            f"Multi-kill spike: {best.get('name')} hit a {max_multi_kill}-kill burst on {best.get('hero')}."
        )
    if max_multi_kill == 4:
        return WEIGHTS["rampage_partial"], (
            f"Near-rampage pressure: {best.get('name')} hit a {max_multi_kill}-kill burst on {best.get('hero')}."
        )
    return 0, None


def _personal_arc(
    context: MatchContext,
    protagonist_hero: str,
    events: list[NarrativeEvent],
) -> tuple[int, str | None]:
    midpoint = float(context.duration or 0) / 2
    kill_events = _protagonist_kill_events(events)
    death_events = _protagonist_death_events(events)
    if len(kill_events) < 2 or len(death_events) < 2:
        return 0, None

    early_kills = sum(1 for event in kill_events if event.t <= midpoint)
    late_kills = len(kill_events) - early_kills
    early_deaths = sum(1 for event in death_events if event.t <= midpoint)
    late_deaths = len(death_events) - early_deaths
    kill_ratio = max(early_kills, late_kills) / len(kill_events)
    death_ratio = max(early_deaths, late_deaths) / len(death_events)
    if kill_ratio < 0.7 or death_ratio < 0.7:
        return 0, None
    if early_deaths > late_deaths and late_kills > early_kills:
        return WEIGHTS["personal_arc"], (
            f"Personal arc: {protagonist_hero} absorbs the pain early ({early_deaths} deaths) "
            f"and cashes out late ({late_kills} kills)."
        )
    if early_kills > late_kills and late_deaths > early_deaths:
        return WEIGHTS["personal_arc"], (
            f"Personal arc: {protagonist_hero} starts dominant ({early_kills} kills) and crashes late "
            f"({late_deaths} deaths)."
        )
    return 0, None


def _hubris_score(events: list[NarrativeEvent]) -> tuple[int, str | None]:
    hubris_events = [
        event
        for event in events
        if event.kind == EventKind.SOCIAL and event.data.get("hubris")
    ]
    points = min(len(hubris_events) * WEIGHTS["hubris_per_event"], WEIGHTS["hubris_cap"])
    if not points:
        return 0, None
    moments = ", ".join(str(int(event.t)) for event in hubris_events[:3])
    return points, f"Hubris beat: {len(hubris_events)} taunt-backed comeuppance moments at t={moments}s."


def _clutch_score(events: list[NarrativeEvent]) -> tuple[int, str | None]:
    buybacks = [
        event
        for event in events
        if event.kind == EventKind.ECONOMY
        and event.protagonist_involved
        and event.data.get("beat") == "buyback"
    ]
    heavy_teamfights = [
        event
        for event in events
        if event.kind == EventKind.PHASE and int(event.data.get("deaths", 0) or 0) >= 4
    ]
    triumphs = [
        event
        for event in events
        if event.kind == EventKind.TRIUMPH
        and any(abs(event.t - fight.t) <= 60 for fight in heavy_teamfights)
    ]
    beats = len(buybacks) + len(triumphs)
    points = min(beats * WEIGHTS["clutch_per_beat"], WEIGHTS["clutch_cap"])
    if not points:
        return 0, None
    return points, (
        f"Clutch leverage: {len(buybacks)} protagonist buybacks and {len(triumphs)} triumph beats land near major fights."
    )


def _streak_end_score(
    roster: list[dict[str, Any]],
    protagonist_hero: str,
    events: list[NarrativeEvent],
) -> tuple[int, str | None]:
    streaked_heroes = {
        str(entry.get("hero"))
        for entry in roster
        if int(entry.get("max_streak", 0) or 0) >= 8
    }
    fallen = [
        str(event.target)
        for event in events
        if event.kind == EventKind.KILL and event.protagonist_involved and str(event.target) in streaked_heroes
    ]
    if not fallen:
        return 0, None
    unique_targets = sorted(set(fallen))
    return WEIGHTS["streak_end"], (
        f"God-slaying beat: {protagonist_hero} ended the run of {', '.join(unique_targets)}."
    )


def _stomp_penalty(
    context: MatchContext,
    reversal_count: int,
    protagonist_kills: int,
    protagonist_deaths: int,
) -> tuple[int, str | None]:
    penalty = 0
    reasons: list[str] = []
    if reversal_count == 0 and (protagonist_deaths == 0 or protagonist_kills == 0):
        penalty += WEIGHTS["stomp_base_penalty"]
        reasons.append("no economy reversals and one side of the protagonist ledger is empty")
    if penalty and float(context.duration or 0) < 1500:
        penalty += WEIGHTS["stomp_short_penalty"]
        reasons.append(f"short duration ({int(context.duration)}s)")
    if not penalty:
        return 0, None
    return penalty, f"Stomp penalty: {'; '.join(reasons)}."


def _verdict(score: int) -> str:
    if score >= 60:
        return "WRITE"
    if score >= 35:
        return "MAYBE"
    return "SKIP"


def _recommend_pov(roster: list[dict[str, Any]], current_protagonist: str) -> list[POVRecommendation]:
    recommendations: list[POVRecommendation] = []
    for entry in roster:
        max_streak = int(entry.get("max_streak", 0) or 0)
        max_multi_kill = int(entry.get("max_multi_kill", 0) or 0)
        kills = int(entry.get("kills", 0) or 0)
        deaths = int(entry.get("deaths", 0) or 0)
        assists = int(entry.get("assists", 0) or 0)
        score = 0.0
        reasons: list[str] = []

        if max_streak >= 10:
            score += 40
            reasons.append(f"streak {max_streak}")
        elif max_streak >= 8:
            score += 25
            reasons.append(f"streak {max_streak}")

        if max_multi_kill >= 5:
            score += 20
            reasons.append(f"multi-kill {max_multi_kill}")
        elif max_multi_kill == 4:
            score += 10
            reasons.append("multi-kill 4")

        score += 2 * kills - deaths + 0.5 * assists
        reasons.append(f"K/D/A {kills}/{deaths}/{assists}")

        if str(entry.get("name")) == current_protagonist:
            score += 5
            reasons.append("incumbent bonus")

        recommendations.append(
            POVRecommendation(
                name=str(entry.get("name", "")),
                hero=str(entry.get("hero", "")),
                side=str(entry.get("side", "")),
                score=score,
                reason=", ".join(reasons),
                pov_value=str(entry.get("name", "")),
            )
        )

    return sorted(
        recommendations,
        key=lambda item: (item.score, item.name == current_protagonist, item.name),
        reverse=True,
    )


def _protagonist_kill_events(events: list[NarrativeEvent]) -> list[NarrativeEvent]:
    return [
        event
        for event in events
        if event.kind == EventKind.KILL and event.protagonist_involved
    ]


def _protagonist_death_events(events: list[NarrativeEvent]) -> list[NarrativeEvent]:
    return [
        event
        for event in events
        if event.kind == EventKind.DEATH and event.protagonist_involved
    ]
