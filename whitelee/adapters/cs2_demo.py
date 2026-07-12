"""CS2 adapter: parses local .dem files with demoparser2.

demoparser2 is an optional dependency:  pip install whitelee[cs2]

Design: we query only the events that carry narrative weight
(round transitions, kills, bomb plants/defuses, clutch situations) and
map them onto the WhiteLee schema. Ticks are converted to seconds at
64 tick/s.
"""

from __future__ import annotations

from collections.abc import Iterable

from whitelee.adapters.base import ExtractionResult, GameAdapter
from whitelee.core.schema import (
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
                "CS2 support requires demoparser2. Install with: pip install whitelee[cs2]"
            ) from exc

        parser = DemoParser(source)
        header = parser.parse_header()
        kills = parser.parse_event("player_death")
        rounds = parser.parse_event("round_end")
        plants = parser.parse_event("bomb_planted")
        defuses = parser.parse_event("bomb_defused")

        protagonist_name = self._resolve_protagonist(kills, protagonist_hint)
        protagonist_round_sides = self._resolve_protagonist_round_sides(kills, protagonist_name)
        starting_side = protagonist_round_sides.get(1) or self._first_known_side(protagonist_round_sides)

        events: list[NarrativeEvent] = [
            NarrativeEvent(t=0, kind=EventKind.MATCH_START,
                           actor=protagonist_name,
                           summary=f"{protagonist_name} loads in on "
                                   f"{header.get('map_name', 'an unknown map')}.",
                           importance=0.5, protagonist_involved=True)
        ]

        events += self._round_phase_events(rounds, protagonist_round_sides, starting_side)
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

        events += self._clutch_events(
            kills, protagonist_name, protagonist_round_sides, starting_side
        )

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
            outcome=self._resolve_outcome(rounds, protagonist_round_sides, starting_side),
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

    @staticmethod
    def _round_phase_events(rounds_df, protagonist_round_sides: dict[int, str], starting_side: str | None) -> list[NarrativeEvent]:
        events: list[NarrativeEvent] = []
        score = {"T": 0, "CT": 0}
        match_point_markers: set[str] = set()
        overtime_emitted = False

        for fallback_round, row in enumerate(CS2DemoAdapter._rows(rounds_df), start=1):
            round_number = CS2DemoAdapter._round_number(row, fallback_round)
            winner = CS2DemoAdapter._normalize_side(row.get("winner"))
            if winner is None:
                continue

            score[winner] += 1
            t = float(row.get("tick", 0)) / TICK_RATE
            events.append(NarrativeEvent(
                t=t,
                kind=EventKind.PHASE,
                summary=(
                    f"Round {round_number} goes to the {CS2DemoAdapter._side_label(winner)} "
                    f"({score['CT']}-{score['T']})"
                ),
                importance=0.5,
                protagonist_involved=(
                    CS2DemoAdapter._protagonist_side_for_round(
                        round_number, protagonist_round_sides, starting_side
                    ) == winner
                ),
                data={"winner": winner, "round": round_number, "score": dict(score)},
            ))

            if score["T"] == 12 and score["CT"] == 12 and not overtime_emitted:
                overtime_emitted = True
                events.append(NarrativeEvent(
                    t=t,
                    kind=EventKind.PHASE,
                    summary="Overtime begins at 12-12.",
                    importance=0.6,
                    data={"round": round_number, "score": dict(score)},
                ))

            for side in ("T", "CT"):
                if score[side] == 12 and side not in match_point_markers:
                    match_point_markers.add(side)
                    events.append(NarrativeEvent(
                        t=t,
                        kind=EventKind.PHASE,
                        summary=f"The {CS2DemoAdapter._side_label(side)} reach match point.",
                        importance=0.6,
                        data={"side": side, "round": round_number, "score": dict(score)},
                    ))

        return events

    @staticmethod
    def _clutch_events(kills_df, protagonist_name: str, protagonist_round_sides: dict[int, str], starting_side: str | None) -> list[NarrativeEvent]:
        events: list[NarrativeEvent] = []
        rows_by_round: dict[int, list[dict]] = {}

        for fallback_round, row in enumerate(CS2DemoAdapter._rows(kills_df), start=1):
            round_number = CS2DemoAdapter._round_number(row, fallback_round)
            rows_by_round.setdefault(round_number, []).append(row)

        for round_number, rows in rows_by_round.items():
            protagonist_side = CS2DemoAdapter._protagonist_side_for_round(
                round_number, protagonist_round_sides, starting_side
            )
            enemy_side = CS2DemoAdapter._opposite_side(protagonist_side)
            if protagonist_side is None or enemy_side is None:
                continue

            alive = {"T": 5, "CT": 5}
            clutch_window_open = False
            clutch_kills = 0
            clutch_tick: float | None = None

            for row in sorted(rows, key=lambda item: float(item.get("tick", 0))):
                attacker = str(row.get("attacker_name", ""))
                victim_side = CS2DemoAdapter._normalize_side(row.get("user_team_name"))

                if clutch_window_open and attacker == protagonist_name:
                    clutch_kills += 1
                    clutch_tick = float(row.get("tick", 0)) / TICK_RATE

                if victim_side in alive and alive[victim_side] > 0:
                    alive[victim_side] -= 1

                if alive[protagonist_side] < alive[enemy_side]:
                    clutch_window_open = True

            if clutch_kills >= 3 and clutch_tick is not None:
                events.append(NarrativeEvent(
                    t=clutch_tick,
                    kind=EventKind.TRIUMPH,
                    actor=protagonist_name,
                    summary=f"{protagonist_name} clutches the round.",
                    importance=0.85,
                    protagonist_involved=True,
                    data={"round": round_number, "kills_after_disadvantage": clutch_kills},
                ))

        return events

    @staticmethod
    def _resolve_outcome(rounds_df, protagonist_round_sides: dict[int, str], starting_side: str | None) -> str:
        if starting_side is None:
            return "unknown"

        protagonist_wins = 0
        opponent_wins = 0
        for fallback_round, row in enumerate(CS2DemoAdapter._rows(rounds_df), start=1):
            round_number = CS2DemoAdapter._round_number(row, fallback_round)
            winner = CS2DemoAdapter._normalize_side(row.get("winner"))
            protagonist_side = CS2DemoAdapter._protagonist_side_for_round(
                round_number, protagonist_round_sides, starting_side
            )
            if winner is None or protagonist_side is None:
                continue
            if winner == protagonist_side:
                protagonist_wins += 1
            else:
                opponent_wins += 1

        if protagonist_wins > opponent_wins:
            return "victory"
        if protagonist_wins < opponent_wins:
            return "defeat"
        if protagonist_wins or opponent_wins:
            return "draw"
        return "unknown"

    @staticmethod
    def _resolve_protagonist_round_sides(kills_df, protagonist_name: str) -> dict[int, str]:
        sides: dict[int, str] = {}
        for fallback_round, row in enumerate(CS2DemoAdapter._rows(kills_df), start=1):
            round_number = CS2DemoAdapter._round_number(row, fallback_round)
            side: str | None = None
            if str(row.get("attacker_name", "")) == protagonist_name:
                side = CS2DemoAdapter._normalize_side(row.get("attacker_team_name"))
            elif str(row.get("user_name", "")) == protagonist_name:
                side = CS2DemoAdapter._normalize_side(row.get("user_team_name"))
            if side and round_number not in sides:
                sides[round_number] = side
        return sides

    @staticmethod
    def _protagonist_side_for_round(round_number: int, round_sides: dict[int, str], starting_side: str | None) -> str | None:
        if round_number in round_sides:
            return round_sides[round_number]
        if starting_side is None:
            return None
        if round_number <= 12:
            return starting_side
        return CS2DemoAdapter._opposite_side(starting_side)

    @staticmethod
    def _first_known_side(round_sides: dict[int, str]) -> str | None:
        if not round_sides:
            return None
        first_round = min(round_sides)
        return round_sides[first_round]

    @staticmethod
    def _round_number(row: dict, fallback_round: int) -> int:
        value = row.get("round_num", row.get("round", fallback_round))
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback_round

    @staticmethod
    def _rows(frame) -> Iterable[dict]:
        for _, row in frame.iterrows():
            yield row

    @staticmethod
    def _normalize_side(value: object) -> str | None:
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in {"T", "TERRORIST", "TERRORISTS", "2"}:
                return "T"
            if normalized in {"CT", "COUNTER-TERRORIST", "COUNTER_TERRORIST", "COUNTERTERRORIST", "3"}:
                return "CT"
        elif isinstance(value, (int, float)):
            if int(value) == 2:
                return "T"
            if int(value) == 3:
                return "CT"
        return None

    @staticmethod
    def _opposite_side(side: str | None) -> str | None:
        if side == "T":
            return "CT"
        if side == "CT":
            return "T"
        return None

    @staticmethod
    def _side_label(side: str) -> str:
        return "CTs" if side == "CT" else "Ts"
