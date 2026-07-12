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

        me = self._pick_protagonist(players, protagonist_hint)
        my_slot = me.get("player_slot", 0)
        is_radiant = my_slot < 128
        hero = self._hero_name(me)
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
            },
            allies=[self._hero_name(p) for p in players
                    if (p.get("player_slot", 0) < 128) == is_radiant and p is not me],
            opponents=[self._hero_name(p) for p in players
                       if (p.get("player_slot", 0) < 128) != is_radiant],
        )

        events: list[NarrativeEvent] = [
            NarrativeEvent(t=0, kind=EventKind.MATCH_START, actor=handle,
                           summary=f"{hero} takes the field for the "
                                   f"{context.world['team']}.",
                           importance=0.5, protagonist_involved=True),
        ]
        events += self._objective_events(match)
        events += self._player_events(players, me, hero)
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

    @staticmethod
    def _hero_name(player: dict[str, Any]) -> str:
        # OpenDota includes hero_id; parsed matches often include localized name
        return (player.get("hero_name") or player.get("localized_name")
                or f"hero_{player.get('hero_id', '?')}").replace("npc_dota_hero_", "").replace("_", " ").title()

    @staticmethod
    def _pick_protagonist(players: list[dict], hint: str | None) -> dict:
        if hint:
            h = hint.lower()
            for p in players:
                if h in str(p.get("personaname", "")).lower() \
                        or h == str(p.get("account_id", "")) \
                        or h in Dota2OpenDotaAdapter._hero_name(p).lower():
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

    def _player_events(self, players: list[dict], me: dict, hero: str) -> list[NarrativeEvent]:
        out: list[NarrativeEvent] = []
        # protagonist's kills
        for k in me.get("kills_log", []) or []:
            victim = str(k.get("key", "")).replace("npc_dota_hero_", "").replace("_", " ").title()
            out.append(NarrativeEvent(
                t=float(k.get("time", 0)), kind=EventKind.KILL,
                actor=hero, target=victim,
                summary=f"{hero} struck down {victim}.",
                importance=0.6, protagonist_involved=True))
        # protagonist's deaths: reconstruct from everyone else's kill logs
        for p in players:
            if p is me:
                continue
            killer = self._hero_name(p)
            for k in p.get("kills_log", []) or []:
                victim_raw = str(k.get("key", ""))
                if hero.lower().replace(" ", "_") in victim_raw.lower():
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
        # chat (SOCIAL flavor)
        for c in (players[0].get("chat") if players else None) or match_chat(players):
            pass  # chat lives at match level; handled below if present
        return out

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


def match_chat(_players: list) -> list:
    """Placeholder: OpenDota exposes chat at match level, wired in v0.2."""
    return []
