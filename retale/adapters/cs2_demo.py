"""CS2 adapter: parses local .dem files with demoparser2.

demoparser2 is an optional dependency:  pip install retale[cs2]

Design: we query only the events that carry narrative weight
(round transitions, kills, bomb plants/defuses, clutch situations) and
map them onto the ReTale schema. Ticks are converted to seconds at
64 tick/s.
"""

from __future__ import annotations

from retale.adapters.base import ExtractionResult, GameAdapter
from retale.core.schema import (
    EventKind,
    MatchContext,
    NarrativeEvent,
    Protagonist,
)

TICK_RATE = 64.0


class CS2DemoAdapter(GameAdapter):
    game_id = "cs2"

    def extract(self, source: str, protagonist_hint: str | None = None) -> ExtractionResult:
        try:
            from demoparser2 import DemoParser  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "CS2 support requires demoparser2. Install with: pip install retale[cs2]"
            ) from exc

        parser = DemoParser(source)
        header = parser.parse_header()
        kills = parser.parse_event("player_death")
        rounds = parser.parse_event("round_end")
        plants = parser.parse_event("bomb_planted")
        defuses = parser.parse_event("bomb_defused")

        protagonist_name = self._resolve_protagonist(kills, protagonist_hint)

        events: list[NarrativeEvent] = [
            NarrativeEvent(t=0, kind=EventKind.MATCH_START,
                           actor=protagonist_name,
                           summary=f"{protagonist_name} loads in on "
                                   f"{header.get('map_name', 'an unknown map')}.",
                           importance=0.5, protagonist_involved=True)
        ]

        for _, row in kills.iterrows():
            t = float(row.get("tick", 0)) / TICK_RATE
            attacker = str(row.get("attacker_name", "?"))
            victim = str(row.get("user_name", "?"))
            hs = bool(row.get("headshot", False))
            weapon = str(row.get("weapon", ""))
            mine = protagonist_name in (attacker, victim)
            kind = (EventKind.DEATH if victim == protagonist_name else EventKind.KILL)
            events.append(NarrativeEvent(
                t=t, kind=kind, actor=attacker, target=victim,
                summary=f"{attacker} {'headshots' if hs else 'kills'} {victim}"
                        + (f" with the {weapon}" if weapon else "") + ".",
                importance=0.6 if mine else 0.35,
                protagonist_involved=mine,
                data={"headshot": hs, "weapon": weapon}))

        for _, row in rounds.iterrows():
            t = float(row.get("tick", 0)) / TICK_RATE
            winner = row.get("winner", "")
            events.append(NarrativeEvent(
                t=t, kind=EventKind.PHASE,
                summary=f"Round ends - side {winner} takes it.",
                importance=0.5, data={"winner": winner}))

        for df, phrase, kind in ((plants, "The bomb is planted.", EventKind.OBJECTIVE),
                                 (defuses, "The bomb is defused.", EventKind.TRIUMPH)):
            for _, row in df.iterrows():
                t = float(row.get("tick", 0)) / TICK_RATE
                actor = str(row.get("user_name", "?"))
                events.append(NarrativeEvent(
                    t=t, kind=kind, actor=actor, summary=f"{actor}: {phrase}",
                    importance=0.65,
                    protagonist_involved=(actor == protagonist_name)))

        duration = max((e.t for e in events), default=0.0)
        events.append(NarrativeEvent(
            t=duration, kind=EventKind.MATCH_END, actor=protagonist_name,
            summary="The match concludes.", importance=1.0,
            protagonist_involved=True))

        context = MatchContext(
            game="cs2",
            protagonist=Protagonist(name=protagonist_name, persona="operator"),
            outcome="unknown",  # refined in v0.2 from team round tallies
            duration=duration,
            world={"map": header.get("map_name", "unknown"),
                   "time_unit": "seconds"},
        )
        return ExtractionResult(context=context, events=self.sort_events(events))

    @staticmethod
    def _resolve_protagonist(kills_df, hint: str | None) -> str:
        names = list(kills_df.get("attacker_name", []))
        if hint:
            for n in names:
                if hint.lower() in str(n).lower():
                    return str(n)
        if names:
            # most frequent attacker = most active player
            return max(set(map(str, names)), key=names.count)
        return hint or "the operator"
