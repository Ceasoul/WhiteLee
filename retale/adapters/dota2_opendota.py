"""Dota 2 adapter backed by the OpenDota API.

Zero local parsing: give it a match id, it fetches the fully parsed
match JSON from https://api.opendota.com and maps it onto the ReTale
event schema.

Note: a match must have been parsed by OpenDota for rich fields
(kills_log, teamfights, chat). For unparsed matches, request parsing at
POST /request/{match_id} or use the web UI, then retry.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import requests

from retale.adapters.base import ExtractionResult, GameAdapter
from retale.core.schema import (
    EventKind,
    MatchContext,
    NarrativeEvent,
    Protagonist,
)

OPENDOTA_MATCH_URL = "https://api.opendota.com/api/matches/{match_id}"
OPENDOTA_HEROES_URL = "https://api.opendota.com/api/constants/heroes"

# Objective type -> (EventKind, base importance, human phrasing)
_OBJECTIVE_MAP: dict[str, tuple[EventKind, float, str]] = {
    "building_kill": (EventKind.OBJECTIVE, 0.55, "destroyed a building"),
    "CHAT_MESSAGE_TOWER_KILL": (EventKind.OBJECTIVE, 0.5, "took a tower"),
    "CHAT_MESSAGE_TOWER_DENY": (EventKind.OBJECTIVE, 0.45, "denied a tower"),
    "CHAT_MESSAGE_BARRACKS_KILL": (EventKind.OBJECTIVE, 0.7, "razed barracks"),
    "CHAT_MESSAGE_FIRSTBLOOD": (EventKind.KILL, 0.8, "drew first blood"),
    "CHAT_MESSAGE_ROSHAN_KILL": (EventKind.TRIUMPH, 0.75, "slew Roshan"),
    "CHAT_MESSAGE_AEGIS": (EventKind.ACQUISITION, 0.6, "claimed the Aegis"),
    "CHAT_MESSAGE_COURIER_LOST": (EventKind.SETBACK, 0.35, "lost a courier"),
}

_BIG_ITEMS = {
    "black_king_bar", "blink", "radiance", "battle_fury", "desolator",
    "monkey_king_bar", "butterfly", "satanic", "abyssal_blade", "rapier",
    "aghanims_scepter", "refresher", "assault", "heart", "skadi",
    "manta", "daedalus", "bloodthorn", "sheepstick", "octarine_core",
}


class Dota2OpenDotaAdapter(GameAdapter):
    game_id = "dota2"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    # ------------------------------------------------------------------
    def extract(self, source: str, protagonist_hint: str | None = None) -> ExtractionResult:
        match = self._load(source)
        players = match.get("players", [])
        if not players:
            raise ValueError("Match JSON has no players; is the match parsed?")

        hero_lookup = self._hero_lookup()
        parsed = self._is_parsed_match(match)
        if not parsed:
            match_id = match.get("match_id", "unknown")
            print(
                "[retale] warning: this match has no parsed replay data; stories will be skeletal. "
                "Use a recent match (replays expire) and request parsing at "
                f"https://www.opendota.com/matches/{match_id}.",
                file=sys.stderr,
            )

        me = self._pick_protagonist(players, protagonist_hint, hero_lookup)
        my_slot = me.get("player_slot", 0)
        is_radiant = my_slot < 128
        hero = self._hero_name(me, hero_lookup)
        handle = me.get("personaname") or hero

        context = MatchContext(
            game="dota2",
            protagonist=Protagonist(name=handle, persona=hero),
            outcome=self._outcome(match, is_radiant),
            duration=float(match.get("duration", 0)),
            world={
                "map": "Dota 2 - the two Ancients",
                "team": "Radiant" if is_radiant else "Dire",
                "time_unit": "seconds",
                "match_id": match.get("match_id"),
                "parsed": parsed,
            },
            allies=[self._hero_name(p, hero_lookup) for p in players
                    if (p.get("player_slot", 0) < 128) == is_radiant and p is not me],
            opponents=[self._hero_name(p, hero_lookup) for p in players
                       if (p.get("player_slot", 0) < 128) != is_radiant],
        )

        events: list[NarrativeEvent] = [
            NarrativeEvent(t=0, kind=EventKind.MATCH_START, actor=handle,
                           summary=f"{hero} takes the field for the "
                                   f"{context.world['team']}.",
                           importance=0.5, protagonist_involved=True),
        ]
        events += self._objective_events(match)
        events += self._player_events(players, me, hero, hero_lookup)
        events += self._chat_events(match, players, me, hero_lookup)
        events += self._gold_swing_events(match)
        events += self._lane_phase_events(match)
        events += self._teamfight_events(match, me, hero)
        events.append(NarrativeEvent(
            t=context.duration, kind=EventKind.MATCH_END, actor=handle,
            summary=f"The Ancient falls. {context.outcome.capitalize()} "
                    f"for the {context.world['team']}.",
            importance=1.0, protagonist_involved=True))

        return ExtractionResult(context=context, events=self.sort_events(events))

    # ------------------------------------------------------------------
    def _load(self, source: str) -> dict[str, Any]:
        """source is a match id, an OpenDota URL, or a path to saved JSON."""
        p = Path(source)
        if p.suffix == ".json" and p.exists():
            return json.loads(p.read_text())
        match_id = source.rstrip("/").split("/")[-1]
        resp = self.session.get(OPENDOTA_MATCH_URL.format(match_id=match_id), timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _hero_lookup(self) -> dict[str, dict[Any, str]]:
        try:
            resp = self.session.get(OPENDOTA_HEROES_URL, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                return {"by_id": {}, "by_slug": {}, "by_id_slug": {}}
        except Exception:
            return {"by_id": {}, "by_slug": {}, "by_id_slug": {}}

        by_id: dict[Any, str] = {}
        by_slug: dict[Any, str] = {}
        by_id_slug: dict[Any, str] = {}
        for raw_id, raw_hero in payload.items():
            if not isinstance(raw_hero, dict):
                continue
            localized_name = raw_hero.get("localized_name")
            hero_slug = raw_hero.get("name")
            if localized_name:
                by_id[str(raw_id)] = str(localized_name)
                if str(raw_id).isdigit():
                    by_id[int(raw_id)] = str(localized_name)
            if hero_slug and localized_name:
                by_slug[str(hero_slug)] = str(localized_name)
            if hero_slug:
                by_id_slug[str(raw_id)] = str(hero_slug)
                if str(raw_id).isdigit():
                    by_id_slug[int(raw_id)] = str(hero_slug)
        return {"by_id": by_id, "by_slug": by_slug, "by_id_slug": by_id_slug}

    @staticmethod
    def _hero_name(player: dict[str, Any], hero_lookup: dict[str, dict[Any, str]]) -> str:
        raw_name = player.get("hero_name") or player.get("localized_name")
        if raw_name:
            return str(raw_name).replace("npc_dota_hero_", "").replace("_", " ").title()

        hero_id = player.get("hero_id", "?")
        hero_name = hero_lookup.get("by_id", {}).get(hero_id) or hero_lookup.get("by_id", {}).get(str(hero_id))
        if hero_name:
            return str(hero_name)
        return f"Hero {hero_id}"

    def _resolve_hero_slug(self, hero_slug: str, hero_lookup: dict[str, dict[Any, str]]) -> str:
        hero_name = hero_lookup.get("by_slug", {}).get(hero_slug)
        if hero_name:
            return str(hero_name)
        return hero_slug.replace("npc_dota_hero_", "").replace("_", " ").title()

    @staticmethod
    def _hero_slug(player: dict[str, Any], hero_lookup: dict[str, dict[Any, str]]) -> str | None:
        raw_name = player.get("hero_name")
        if raw_name:
            return str(raw_name)

        hero_id = player.get("hero_id")
        hero_slug = (
            hero_lookup.get("by_id_slug", {}).get(hero_id)
            or hero_lookup.get("by_id_slug", {}).get(str(hero_id))
        )
        return str(hero_slug) if hero_slug else None

    def _pick_protagonist(
        self,
        players: list[dict],
        hint: str | None,
        hero_lookup: dict[str, dict[Any, str]],
    ) -> dict:
        if hint:
            h = hint.lower()
            for p in players:
                if h in str(p.get("personaname", "")).lower() \
                        or h == str(p.get("account_id", "")) \
                        or h in self._hero_name(p, hero_lookup).lower():
                    return p
        # default: highest kill participation
        return max(players, key=lambda p: (p.get("kills", 0) + p.get("assists", 0)))

    @staticmethod
    def _outcome(match: dict, is_radiant: bool) -> str:
        rw = match.get("radiant_win")
        if rw is None:
            return "unknown"
        return "victory" if rw == is_radiant else "defeat"

    def _objective_events(self, match: dict) -> list[NarrativeEvent]:
        out = []
        for obj in match.get("objectives", []) or []:
            kind, imp, phrase = _OBJECTIVE_MAP.get(
                obj.get("type", ""), (EventKind.OBJECTIVE, 0.4, "objective event"))
            out.append(NarrativeEvent(
                t=float(obj.get("time", 0)), kind=kind,
                actor=str(obj.get("unit", "") or obj.get("team", "")),
                target=str(obj.get("key", "")),
                summary=phrase, importance=imp, data=obj))
        return out

    def _player_events(
        self,
        players: list[dict],
        me: dict,
        hero: str,
        hero_lookup: dict[str, dict[Any, str]],
    ) -> list[NarrativeEvent]:
        out: list[NarrativeEvent] = []
        # protagonist's kills
        for k in me.get("kills_log", []) or []:
            victim = self._resolve_hero_slug(str(k.get("key", "")), hero_lookup)
            out.append(NarrativeEvent(
                t=float(k.get("time", 0)), kind=EventKind.KILL,
                actor=hero, target=victim,
                summary=f"{hero} struck down {victim}.",
                importance=0.6, protagonist_involved=True))
        # protagonist's deaths: reconstruct from everyone else's kill logs
        protagonist_slug = self._hero_slug(me, hero_lookup)
        for p in players:
            if p is me:
                continue
            killer = self._hero_name(p, hero_lookup)
            for k in p.get("kills_log", []) or []:
                victim_raw = str(k.get("key", ""))
                if protagonist_slug:
                    victim_matches = victim_raw == protagonist_slug
                else:
                    victim_matches = hero.lower().replace(" ", "_") in victim_raw.lower()
                if victim_matches:
                    out.append(NarrativeEvent(
                        t=float(k.get("time", 0)), kind=EventKind.DEATH,
                        actor=killer, target=hero,
                        summary=f"{hero} fell to {killer}.",
                        importance=0.65, protagonist_involved=True))
        # big item purchases
        for buy in me.get("purchase_log", []) or []:
            item = str(buy.get("key", ""))
            if item in _BIG_ITEMS:
                out.append(NarrativeEvent(
                    t=float(buy.get("time", 0)), kind=EventKind.ACQUISITION,
                    actor=hero, target=item,
                    summary=f"{hero} completed {item.replace('_', ' ').title()}.",
                    importance=0.45, protagonist_involved=True))
        return out

    def _chat_events(
        self,
        match: dict[str, Any],
        players: list[dict],
        me: dict[str, Any],
        hero_lookup: dict[str, dict[Any, str]],
    ) -> list[NarrativeEvent]:
        players_by_slot = {
            int(player.get("player_slot", -1)): player
            for player in players
            if player.get("player_slot") is not None
        }
        protagonist_slot = int(me.get("player_slot", -1))
        out: list[NarrativeEvent] = []

        for line in match.get("chat", []) or []:
            message = str(line.get("key", "")).strip()
            if not message:
                continue

            actor, speaker_slot = self._chat_actor(line, players_by_slot, hero_lookup)
            protagonist_spoke = speaker_slot == protagonist_slot
            truncated_message = message[:120]
            summary = f"{actor}: {truncated_message}" if actor else truncated_message

            out.append(NarrativeEvent(
                t=float(line.get("time", 0)),
                kind=EventKind.SOCIAL,
                actor=actor or None,
                summary=summary,
                importance=0.35 if protagonist_spoke else 0.2,
                protagonist_involved=protagonist_spoke,
                data=line,
            ))
        return out

    def _gold_swing_events(self, match: dict[str, Any]) -> list[NarrativeEvent]:
        gold_advantage = match.get("radiant_gold_adv", []) or []
        out: list[NarrativeEvent] = []

        for minute in range(1, len(gold_advantage)):
            current_advantage = gold_advantage[minute]
            previous_advantage = gold_advantage[minute - 1]
            if current_advantage is None or previous_advantage is None or minute < 3:
                continue

            current_sign = self._advantage_sign(current_advantage)
            previous_sign = self._advantage_sign(previous_advantage)
            if current_sign == 0 or previous_sign == 0 or current_sign == previous_sign:
                continue

            earlier_advantage = gold_advantage[minute - 3]
            if earlier_advantage is None:
                continue

            swing = float(current_advantage) - float(earlier_advantage)
            if abs(swing) <= 2000:
                continue

            favored_team = "Radiant" if current_sign > 0 else "Dire"
            out.append(NarrativeEvent(
                t=float(minute * 60),
                kind=EventKind.ECONOMY,
                summary=f"The tide of gold turns toward the {favored_team}.",
                importance=0.55,
                protagonist_involved=False,
                data={
                    "minute": minute,
                    "radiant_gold_adv": current_advantage,
                    "three_min_delta": swing,
                },
            ))
        return out

    def _lane_phase_events(self, match: dict[str, Any]) -> list[NarrativeEvent]:
        if float(match.get("duration", 0)) <= 720:
            return []
        return [
            NarrativeEvent(
                t=600.0,
                kind=EventKind.PHASE,
                summary="The laning stage draws to a close.",
                importance=0.35,
                protagonist_involved=False,
            )
        ]

    def _teamfight_events(self, match: dict, me: dict, hero: str) -> list[NarrativeEvent]:
        out = []
        my_slot = me.get("player_slot", 0)
        for tf in match.get("teamfights", []) or []:
            deaths = tf.get("deaths", 0)
            involved = False
            for pslot, pdata in enumerate(tf.get("players", []) or []):
                if pdata.get("deaths", 0) or pdata.get("damage", 0):
                    # OpenDota teamfight players are index-aligned to match players
                    if match["players"][pslot].get("player_slot") == my_slot:
                        involved = involved or bool(pdata.get("damage", 0))
            out.append(NarrativeEvent(
                t=float(tf.get("start", 0)), kind=EventKind.PHASE,
                summary=f"A team fight erupts - {deaths} heroes fall.",
                importance=min(0.9, 0.4 + 0.08 * deaths),
                protagonist_involved=involved,
                data={"end": tf.get("end"), "deaths": deaths}))
        return out

    @staticmethod
    def _is_parsed_match(match: dict[str, Any]) -> bool:
        has_kills = any(player.get("kills_log") for player in match.get("players", []))
        has_teamfights = bool(match.get("teamfights"))
        return has_kills or has_teamfights

    @staticmethod
    def _chat_actor(
        line: dict[str, Any],
        players_by_slot: dict[int, dict[str, Any]],
        hero_lookup: dict[str, dict[Any, str]],
    ) -> tuple[str, int | None]:
        speaker_slot = line.get("player_slot", line.get("unit"))
        if isinstance(speaker_slot, str) and speaker_slot.isdigit():
            speaker_slot = int(speaker_slot)
        if isinstance(speaker_slot, int):
            player = players_by_slot.get(speaker_slot)
            if player:
                actor = str(
                    player.get("personaname") or Dota2OpenDotaAdapter._hero_name(player, hero_lookup)
                )
                return actor, speaker_slot
            return f"slot_{speaker_slot}", speaker_slot

        actor = str(line.get("unit", "")).strip()
        if actor.startswith("npc_dota_hero_"):
            actor = actor.replace("npc_dota_hero_", "").replace("_", " ").title()
        return actor, None

    @staticmethod
    def _advantage_sign(value: int | float) -> int:
        if value > 0:
            return 1
        if value < 0:
            return -1
        return 0
