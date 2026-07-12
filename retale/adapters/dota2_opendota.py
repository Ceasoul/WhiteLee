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
OPENDOTA_CHAT_WHEEL_URL = "https://api.opendota.com/api/constants/chat_wheel"

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

_CLUTCH_ITEMS = {
    "black_king_bar",
    "blink",
    "glimmer_cape",
    "ghost",
    "sheepstick",
    "refresher",
    "satanic",
    "lotus_orb",
    "sphere",
    "cyclone",
}

_POWER_RUNES = {
    0: "Double Damage",
    1: "Haste",
    3: "Invisibility",
    4: "Regeneration",
    6: "Arcane",
    8: "Shield",
}

# Community additions are welcome as taunt idioms evolve across regions and patches.
_TAUNT_TEXTS = {
    "?",
    "??",
    "???",
    "ez",
    "ez game",
    "gg ez",
    "noob",
    "report",
    "报警",
    "菜",
    "?好",
}

_TAUNT_CHAT_WHEEL_SUBSTRINGS = {
    "well played",
    "gg",
    "ez",
    "haha",
    "thanks",
    "my bad",
    "fish bait",
    "?",
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
        chat_wheel_lookup = self._chat_wheel_lookup()
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
                "roster": self._roster(players, me, hero_lookup),
            },
            allies=[self._hero_name(p, hero_lookup) for p in players
                    if (p.get("player_slot", 0) < 128) == is_radiant and p is not me],
            opponents=[self._hero_name(p, hero_lookup) for p in players
                       if (p.get("player_slot", 0) < 128) != is_radiant],
        )

        events: list[NarrativeEvent] = []
        events += self._objective_events(match, me, hero, hero_lookup)
        events += self._player_events(players, me, hero, hero_lookup)
        events += self._chat_events(match, players, me, hero_lookup, chat_wheel_lookup)
        events += self._gold_swing_events(match)
        events += self._lane_phase_events(match)
        events += self._teamfight_events(match, me, hero, hero_lookup)
        events += self._buyback_events(players, me, hero, hero_lookup)
        events += self._rune_events(me, hero)
        signature_event = self._signature_event(me, hero, hero_lookup, context)
        if signature_event is not None:
            events.append(signature_event)
        self._apply_chat_drama_tags(events, hero)
        match_start_time = min(0.0, min((event.t for event in events), default=0.0)) - 1.0
        events.append(NarrativeEvent(
            t=match_start_time, kind=EventKind.MATCH_START, actor=handle,
            summary=f"{hero} takes the field for the "
                    f"{context.world['team']}.",
            importance=0.5, protagonist_involved=True))
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
            return json.loads(p.read_text(encoding="utf-8"))
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

    def _chat_wheel_lookup(self) -> dict[Any, str]:
        try:
            resp = self.session.get(OPENDOTA_CHAT_WHEEL_URL, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                return {}
        except Exception:
            return {}

        lookup: dict[Any, str] = {}
        for raw_id, raw_entry in payload.items():
            if isinstance(raw_entry, dict):
                message = raw_entry.get("message") or raw_entry.get("label")
            else:
                message = raw_entry
            if not message:
                continue
            lookup[str(raw_id)] = str(message)
            if str(raw_id).isdigit():
                lookup[int(raw_id)] = str(message)
        return lookup

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
    def _prettify_combat_name(name: str, protagonist_slug: str | None = None) -> str:
        pretty = str(name).strip()
        if pretty.startswith("item_"):
            pretty = pretty[5:]
        if protagonist_slug:
            hero_tail = protagonist_slug.replace("npc_dota_hero_", "")
            prefix = f"{hero_tail}_"
            if pretty.startswith(prefix):
                pretty = pretty[len(prefix):]
        return pretty.replace("_", " ").title()

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

    def _roster(
        self,
        players: list[dict[str, Any]],
        protagonist: dict[str, Any],
        hero_lookup: dict[str, dict[Any, str]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": str(player.get("personaname") or self._hero_name(player, hero_lookup)),
                "hero": self._hero_name(player, hero_lookup),
                "side": "Radiant" if int(player.get("player_slot", 0) or 0) < 128 else "Dire",
                "is_protagonist": player is protagonist,
                "kills": self._int_stat(player.get("kills")),
                "deaths": self._int_stat(player.get("deaths")),
                "assists": self._int_stat(player.get("assists")),
                "max_streak": self._max_counter_key(player.get("kill_streaks")),
                "max_multi_kill": self._max_counter_key(player.get("multi_kills")),
            }
            for player in players
        ]

    @staticmethod
    def _outcome(match: dict, is_radiant: bool) -> str:
        rw = match.get("radiant_win")
        if rw is None:
            return "unknown"
        return "victory" if rw == is_radiant else "defeat"

    @staticmethod
    def _int_stat(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _max_counter_key(counter: Any) -> int:
        if not isinstance(counter, dict):
            return 0
        values = [
            int(raw_key)
            for raw_key, count in counter.items()
            if Dota2OpenDotaAdapter._int_stat(count) > 0 and str(raw_key).isdigit()
        ]
        return max(values, default=0)

    def _objective_events(
        self,
        match: dict,
        me: dict[str, Any],
        hero: str,
        hero_lookup: dict[str, dict[Any, str]],
    ) -> list[NarrativeEvent]:
        out: list[NarrativeEvent] = []
        for obj in match.get("objectives", []) or []:
            building_event = self._building_objective_event(obj, me, hero, hero_lookup)
            if building_event is not None:
                out.append(building_event)
                continue

            kind, imp, phrase = _OBJECTIVE_MAP.get(
                obj.get("type", ""), (EventKind.OBJECTIVE, 0.4, "objective event"))
            out.append(NarrativeEvent(
                t=float(obj.get("time", 0)), kind=kind,
                actor=str(obj.get("unit", "") or obj.get("team", "")),
                target=str(obj.get("key", "")),
                summary=phrase, importance=imp, data=obj))
        return self._aggregate_building_events(out)

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
        chat_wheel_lookup: dict[Any, str],
    ) -> list[NarrativeEvent]:
        players_by_slot = {
            int(player.get("player_slot", -1)): player
            for player in players
            if player.get("player_slot") is not None
        }
        protagonist_slot = int(me.get("player_slot", -1))
        protagonist_is_radiant = protagonist_slot < 128
        out: list[NarrativeEvent] = []

        for line in match.get("chat", []) or []:
            raw_type = str(line.get("type", ""))
            raw_key = str(line.get("key", "")).strip()
            channel = "chatwheel" if raw_type == "chatwheel" or raw_key.isdigit() else "chat"
            if channel == "chatwheel":
                message = self._resolve_chat_wheel_message(raw_key, chat_wheel_lookup)
            else:
                message = raw_key
            if not message:
                continue

            actor, speaker_slot, speaker_hero = self._chat_actor(line, players_by_slot, hero_lookup)
            protagonist_spoke = speaker_slot == protagonist_slot
            truncated_message = message[:120]
            if channel == "chatwheel":
                summary = f'{actor}: "{truncated_message}" (chat wheel)' if actor else f'"{truncated_message}" (chat wheel)'
                base_importance = 0.15
            else:
                summary = f"{actor}: {truncated_message}" if actor else truncated_message
                base_importance = 0.35 if protagonist_spoke else 0.2
            data = {**line, "channel": channel}
            if speaker_slot is not None:
                data["enemy"] = (speaker_slot < 128) != protagonist_is_radiant
            if speaker_hero:
                data["speaker_hero"] = speaker_hero
            if self._is_taunt(truncated_message, channel):
                data["taunt"] = True

            out.append(NarrativeEvent(
                t=float(line.get("time", 0)),
                kind=EventKind.SOCIAL,
                actor=actor or None,
                summary=summary,
                importance=base_importance,
                protagonist_involved=protagonist_spoke,
                data=data,
            ))
        return out

    def _building_objective_event(
        self,
        obj: dict[str, Any],
        me: dict[str, Any],
        hero: str,
        hero_lookup: dict[str, dict[Any, str]],
    ) -> NarrativeEvent | None:
        objective_type = str(obj.get("type", ""))
        if objective_type not in {
            "building_kill",
            "CHAT_MESSAGE_TOWER_KILL",
            "CHAT_MESSAGE_BARRACKS_KILL",
        }:
            return None

        building = self._parse_building_key(str(obj.get("key", "")))
        if building is None:
            return None
        if building["kind"] == "fort":
            return None

        actor = None
        protagonist_involved = False
        unit = str(obj.get("unit", ""))
        if unit.startswith("npc_dota_hero_"):
            actor = self._resolve_hero_slug(unit, hero_lookup)
            protagonist_involved = unit == self._hero_slug(me, hero_lookup) or actor == hero

        if building["kind"] == "tower":
            descriptor = f"tier-{building['tier']} {building['lane']} tower" if building["lane"] else f"tier-{building['tier']} tower"
            importance = 0.45 + 0.05 * int(building["tier"])
        else:
            lane_text = f" in {building['lane']} lane" if building["lane"] else ""
            descriptor = f"{building['label']}{lane_text}"
            importance = 0.7

        return NarrativeEvent(
            t=float(obj.get("time", 0)),
            kind=EventKind.OBJECTIVE,
            actor=actor,
            target=str(obj.get("key", "")),
            summary=f"The {building['owner']}'s {descriptor} falls.",
            importance=importance,
            protagonist_involved=protagonist_involved,
            data={
                **obj,
                "building_owner": building["owner"],
                "building_kind": building["kind"],
                "building_lane": building["lane"],
                "building_key": str(obj.get("key", "")),
            },
        )

    @staticmethod
    def _parse_building_key(key: str) -> dict[str, Any] | None:
        if not key:
            return None
        tokens = key.split("_")
        owner = None
        if "goodguys" in tokens or key.startswith("radiant_"):
            owner = "Radiant"
        elif "badguys" in tokens or key.startswith("dire_"):
            owner = "Dire"
        elif key.startswith("goodguys_"):
            owner = "Radiant"
        elif key.startswith("badguys_"):
            owner = "Dire"
        elif key.startswith("dire_"):
            owner = "Dire"
        elif key.startswith("radiant_"):
            owner = "Radiant"
        if owner is None:
            return None

        lane = None
        if key.endswith("_top"):
            lane = "top"
        elif key.endswith("_mid"):
            lane = "mid"
        elif key.endswith("_bot"):
            lane = "bottom"

        compact_tokens = {"t1", "t2", "t3", "t4"}
        tier_token = next((token for token in tokens if token.startswith("tower")), None)
        if tier_token:
            tier_text = tier_token.replace("tower", "")
            if tier_text.isdigit():
                return {"owner": owner, "kind": "tower", "tier": int(tier_text), "lane": lane}

        compact_tier = next((token for token in tokens if token in compact_tokens), None)
        if compact_tier:
            return {"owner": owner, "kind": "tower", "tier": int(compact_tier[1]), "lane": lane}

        if "melee" in tokens and "rax" in tokens:
            return {"owner": owner, "kind": "barracks", "label": "melee barracks", "lane": lane}
        if "range" in tokens and "rax" in tokens:
            return {"owner": owner, "kind": "barracks", "label": "ranged barracks", "lane": lane}
        if "fort" in tokens:
            return {"owner": owner, "kind": "fort", "lane": lane}
        return None

    @staticmethod
    def _aggregate_building_events(events: list[NarrativeEvent]) -> list[NarrativeEvent]:
        aggregated: list[NarrativeEvent] = []
        building_buffer: list[NarrativeEvent] = []

        def flush_buffer() -> None:
            if not building_buffer:
                return
            if len(building_buffer) >= 3:
                first = building_buffer[0]
                owner = str(first.data.get("building_owner", "unknown"))
                winning_side = "Radiant" if owner == "Dire" else "Dire"
                aggregated.append(NarrativeEvent(
                    t=first.t,
                    kind=EventKind.OBJECTIVE,
                    actor=first.actor if all(event.actor == first.actor for event in building_buffer) else None,
                    summary=(
                        f"The {winning_side} tear through the {owner} base - "
                        f"{len(building_buffer)} structures fall."
                    ),
                    importance=0.75,
                    protagonist_involved=any(event.protagonist_involved for event in building_buffer),
                    data={
                        "building_owner": owner,
                        "merged_keys": [event.data.get("building_key", event.target) for event in building_buffer],
                    },
                ))
            else:
                aggregated.extend(building_buffer)
            building_buffer.clear()

        for event in sorted(events, key=lambda item: item.t):
            is_building = event.kind == EventKind.OBJECTIVE and "building_owner" in event.data
            if not is_building:
                flush_buffer()
                aggregated.append(event)
                continue

            if not building_buffer:
                building_buffer.append(event)
                continue

            same_owner = event.data.get("building_owner") == building_buffer[0].data.get("building_owner")
            within_window = event.t - building_buffer[0].t <= 60
            if same_owner and within_window:
                building_buffer.append(event)
            else:
                flush_buffer()
                building_buffer.append(event)

        flush_buffer()
        return aggregated

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

    def _teamfight_events(
        self,
        match: dict,
        me: dict,
        hero: str,
        hero_lookup: dict[str, dict[Any, str]],
    ) -> list[NarrativeEvent]:
        out = []
        my_slot = me.get("player_slot", 0)
        protagonist_slug = self._hero_slug(me, hero_lookup)
        for tf in match.get("teamfights", []) or []:
            deaths = tf.get("deaths", 0)
            involved = False
            tf_players = tf.get("players", []) or []
            misaligned = len(tf_players) != len(match.get("players", []))
            protagonist_fight_data = None
            for pslot, pdata in enumerate(tf_players):
                if pslot >= len(match.get("players", [])):
                    break
                if pdata.get("deaths", 0) or pdata.get("damage", 0):
                    # OpenDota teamfight players are index-aligned to match players
                    if match["players"][pslot].get("player_slot") == my_slot:
                        involved = involved or bool(pdata.get("damage", 0))
                        protagonist_fight_data = pdata

            summary = f"A team fight erupts - {deaths} heroes fall."
            importance = min(0.9, 0.4 + 0.08 * deaths)
            data = {"end": tf.get("end"), "deaths": deaths}
            if involved and protagonist_fight_data and not misaligned:
                abilities = self._top_ability_uses(
                    protagonist_fight_data.get("ability_uses", {}),
                    protagonist_slug,
                )
                clutch_items = self._clutch_items(protagonist_fight_data.get("item_uses", {}))
                damage = int(protagonist_fight_data.get("damage", 0) or 0)
                died = int(protagonist_fight_data.get("deaths", 0) or 0) > 0
                summary = self._teamfight_summary(hero, deaths, abilities, clutch_items, damage, died)
                importance = min(0.95, importance + (0.05 if clutch_items else 0.0))
                data = {
                    **data,
                    "abilities": abilities,
                    "clutch_items": clutch_items,
                    "damage": damage,
                    "died": died,
                }

            out.append(NarrativeEvent(
                t=float(tf.get("start", 0)), kind=EventKind.PHASE,
                summary=summary,
                importance=importance,
                protagonist_involved=involved,
                data=data))
        return out

    def _buyback_events(
        self,
        players: list[dict[str, Any]],
        me: dict[str, Any],
        hero: str,
        hero_lookup: dict[str, dict[Any, str]],
    ) -> list[NarrativeEvent]:
        out: list[NarrativeEvent] = []
        for player in players:
            actor = hero if player is me else self._hero_name(player, hero_lookup)
            for entry in player.get("buyback_log", []) or []:
                if player is me:
                    summary = f"{hero} pays the blood price and buys his life back."
                    importance = 0.7
                    protagonist_involved = True
                else:
                    summary = f"{actor} returns from death, gold spent for a second chance."
                    importance = 0.5
                    protagonist_involved = False
                out.append(NarrativeEvent(
                    t=float(entry.get("time", 0)),
                    kind=EventKind.ECONOMY,
                    actor=actor,
                    summary=summary,
                    importance=importance,
                    protagonist_involved=protagonist_involved,
                    data={**entry, "beat": "buyback"},
                ))
        return out

    @staticmethod
    def _rune_events(me: dict[str, Any], hero: str) -> list[NarrativeEvent]:
        out: list[NarrativeEvent] = []
        for entry in me.get("runes_log", []) or []:
            rune_name = _POWER_RUNES.get(entry.get("key"))
            if rune_name is None:
                continue
            out.append(NarrativeEvent(
                t=float(entry.get("time", 0)),
                kind=EventKind.AMBIENT,
                actor=hero,
                summary=f"{hero} seizes a {rune_name} rune.",
                importance=0.35,
                protagonist_involved=True,
                data=entry,
            ))
        return out

    def _signature_event(
        self,
        me: dict[str, Any],
        hero: str,
        hero_lookup: dict[str, dict[Any, str]],
        context: MatchContext,
    ) -> NarrativeEvent | None:
        damage_inflictor = me.get("damage_inflictor")
        if not isinstance(damage_inflictor, dict) or not damage_inflictor:
            return None
        top_entry = max(damage_inflictor.items(), key=lambda item: int(item[1] or 0))
        if int(top_entry[1] or 0) <= 0:
            return None
        pretty = self._prettify_combat_name(top_entry[0], self._hero_slug(me, hero_lookup))
        context.world["signature"] = {"name": pretty, "damage": int(top_entry[1])}
        return NarrativeEvent(
            t=max(float(context.duration) - 1.0, 0.0),
            kind=EventKind.AMBIENT,
            actor=hero,
            summary=f"Across the whole battle, no weapon of his drew more blood than {pretty}.",
            importance=0.3,
            protagonist_involved=True,
            data={"name": pretty, "damage": int(top_entry[1])},
        )

    def _top_ability_uses(
        self,
        ability_uses: Any,
        protagonist_slug: str | None,
    ) -> list[str]:
        if not isinstance(ability_uses, dict):
            return []
        ranked = sorted(
            (
                (name, int(count or 0))
                for name, count in ability_uses.items()
                if int(count or 0) > 0
            ),
            key=lambda item: (-item[1], item[0]),
        )
        return [
            self._prettify_combat_name(name, protagonist_slug)
            for name, _count in ranked[:2]
        ]

    def _clutch_items(self, item_uses: Any) -> list[str]:
        if not isinstance(item_uses, dict):
            return []
        ranked = sorted(
            (
                (name, int(count or 0))
                for name, count in item_uses.items()
                if name in _CLUTCH_ITEMS and int(count or 0) > 0
            ),
            key=lambda item: (-item[1], item[0]),
        )
        return [self._prettify_combat_name(name) for name, _count in ranked]

    @staticmethod
    def _teamfight_summary(
        hero: str,
        deaths: int,
        abilities: list[str],
        clutch_items: list[str],
        damage: int,
        died: bool,
    ) -> str:
        summary = f"A team fight erupts - {deaths} heroes fall."
        fragments: list[str] = []
        if clutch_items:
            item_text = " and ".join(clutch_items[:2])
            fragments.append(f"{hero} opens his {item_text}")
        if abilities:
            ability_text = " and ".join(abilities[:2])
            verb = "strikes with" if fragments else f"{hero} strikes with"
            fragments.append(f"{verb} {ability_text}")
        if damage > 0:
            if fragments:
                fragments[-1] = f"{fragments[-1]} ({damage} damage)"
            else:
                fragments.append(f"{hero} deals {damage} damage")
        if died:
            fragments.append("falls in the exchange")
        else:
            fragments.append("walking out untouched")
        return f"{summary} {' and '.join(fragments)}."

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
    ) -> tuple[str, int | None, str | None]:
        speaker_slot = line.get("player_slot", line.get("unit"))
        if isinstance(speaker_slot, str) and speaker_slot.isdigit():
            speaker_slot = int(speaker_slot)
        if isinstance(speaker_slot, int):
            player = players_by_slot.get(speaker_slot)
            if player:
                hero_name = Dota2OpenDotaAdapter._hero_name(player, hero_lookup)
                actor = str(
                    player.get("personaname") or hero_name
                )
                return actor, speaker_slot, hero_name
            return f"slot_{speaker_slot}", speaker_slot, None

        actor = str(line.get("unit", "")).strip()
        if actor.startswith("npc_dota_hero_"):
            actor = actor.replace("npc_dota_hero_", "").replace("_", " ").title()
        return actor, None, actor or None

    @staticmethod
    def _resolve_chat_wheel_message(raw_key: str, chat_wheel_lookup: dict[Any, str]) -> str | None:
        message = chat_wheel_lookup.get(raw_key)
        if message is None and raw_key.isdigit():
            message = chat_wheel_lookup.get(int(raw_key))
        return str(message).strip() if message else None

    @staticmethod
    def _is_taunt(message: str, channel: str) -> bool:
        lowered = message.strip().lower()
        if channel == "chat":
            return lowered in _TAUNT_TEXTS or (lowered and set(lowered) == {"?"})
        return any(fragment in lowered for fragment in _TAUNT_CHAT_WHEEL_SUBSTRINGS)

    @staticmethod
    def _apply_chat_drama_tags(events: list[NarrativeEvent], protagonist_hero: str) -> None:
        protagonist_windows = [
            event
            for event in events
            if event.kind in {EventKind.KILL, EventKind.DEATH} and event.protagonist_involved
        ]
        death_times_by_target: dict[str, list[float]] = {}
        for event in events:
            if event.kind == EventKind.DEATH and event.target:
                death_times_by_target.setdefault(str(event.target), []).append(float(event.t))
            if event.kind == EventKind.KILL and event.target:
                death_times_by_target.setdefault(str(event.target), []).append(float(event.t))

        for event in events:
            if event.kind != EventKind.SOCIAL or not event.data.get("taunt"):
                continue
            speaker_hero = event.data.get("speaker_hero")
            if speaker_hero:
                for death_time in death_times_by_target.get(str(speaker_hero), []):
                    if event.t < death_time <= event.t + 60:
                        event.importance = max(event.importance, 0.6)
                        event.data["hubris"] = True
                        break
            if any(abs(event.t - candidate.t) <= 30 for candidate in protagonist_windows):
                event.importance = max(event.importance, 0.45)

    @staticmethod
    def _advantage_sign(value: int | float) -> int:
        if value > 0:
            return 1
        if value < 0:
            return -1
        return 0
