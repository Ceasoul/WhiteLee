# Report T-008: Combat texture: teamfight ability/item usage, buybacks, runes, damage signature

generated: 2026-07-12 03:55 UTC

## Implementer notes

Implemented the T-008 Dota 2 combat-texture enrichment entirely inside the allowed adapter/fixture/test scope. Added a combat-name prettifier that strips item_ prefixes, strips the protagonist hero-slug prefix from ability names when present, then converts underscores to title case, so slark_dark_pact -> Dark Pact and black_king_bar -> Black King Bar. Extended teamfight handling for protagonist-involved fights: when the teamfight players array is index-aligned to match players, the adapter now extracts the protagonist's top two ability_uses, filters item_uses through the curated clutch set, records fight damage and whether he died, and folds those details into the summary plus structured event data. Clutch-item usage increases teamfight importance by 0.05 with a 0.95 cap. If a teamfight players array is misaligned in length, the adapter now safely falls back to the original unenriched summary instead of raising or inventing details. Added buyback events from players[].buyback_log as ECONOMY events with protagonist/non-protagonist phrasing and the required importance levels. Added protagonist-only power-rune pickup events from runes_log as AMBIENT events while skipping non-power rune ids. Added a single late-match AMBIENT signature event from the protagonist's top damage_inflictor entry and persisted the same signature payload into context.world['signature']; both are skipped when the field is absent. Unparsed matches remain unaffected: no new texture events are emitted and world['signature'] stays absent. Updated the parsed fixture to provide full index-aligned teamfight player payloads for all 10 players across the sample fights, including a protagonist clutch fight with Black King Bar + Pounce + Dark Pact while surviving, a separate deaths>0 fight without a clutch item, protagonist and enemy buybacks, protagonist runes_log with one Haste and one skipped bounty rune, and a clear top damage_inflictor entry. For consistency with the Slark ability examples required by the task, the test constants/fixture protagonist hero mapping now resolve hero_id 8 to Slark and all related expected summaries were updated accordingly. Extended pipeline tests to assert the enriched fight summary text and structured data, the fallen phrasing on the deaths>0 fight, two buyback events with correct actors/importances, exactly one Haste rune event, one signature event plus context.world['signature'], misalignment fallback behavior, and that the unparsed fixture emits none of the new texture outputs. Verification: python -m pytest tests/ -q -> 29 passed; ruff check retale/ tests/ -> clean. No open questions.

## Test output

```
.............................                                            [100%]
29 passed in 0.85s
```

## Diff vs b92ce1881ff1aaa11ee9d5e3ce9e98d872d5b247

```diff
...008-combat-texture-teamfight-ability-item-us.md |   9 +
 retale/adapters/dota2_opendota.py                  | 221 ++++++++++++++++++++-
 tests/fixtures/dota2_match.json                    | 153 ++++++++++++--
 tests/test_pipeline.py                             |  81 +++++++-
 4 files changed, 428 insertions(+), 36 deletions(-)
warning: in the working copy of '.conductor/tasks/T-008-combat-texture-teamfight-ability-item-us.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-008-combat-texture-teamfight-ability-item-us.md', CRLF will be replaced by LF the next time Git touches it


diff --git a/T-008-spec.md b/.conductor/tasks/T-008-combat-texture-teamfight-ability-item-us.md
similarity index 95%
rename from T-008-spec.md
rename to .conductor/tasks/T-008-combat-texture-teamfight-ability-item-us.md
index e81fcad..d05a8ba 100644
--- a/T-008-spec.md
+++ b/.conductor/tasks/T-008-combat-texture-teamfight-ability-item-us.md
@@ -1,3 +1,12 @@
+---
+id: T-008
+title: 'Combat texture: teamfight ability/item usage, buybacks, runes, damage signature'
+status: in_progress
+priority: 2
+depends: []
+base: b92ce1881ff1aaa11ee9d5e3ce9e98d872d5b247
+---
+
 ## Context
 
 Reader feedback on the first full story: skill casts have no timing/effect
diff --git a/retale/adapters/dota2_opendota.py b/retale/adapters/dota2_opendota.py
index 3f5c1b5..981fd53 100644
--- a/retale/adapters/dota2_opendota.py
+++ b/retale/adapters/dota2_opendota.py
@@ -48,6 +48,28 @@ _BIG_ITEMS = {
     "manta", "daedalus", "bloodthorn", "sheepstick", "octarine_core",
 }
 
+_CLUTCH_ITEMS = {
+    "black_king_bar",
+    "blink",
+    "glimmer_cape",
+    "ghost",
+    "sheepstick",
+    "refresher",
+    "satanic",
+    "lotus_orb",
+    "sphere",
+    "cyclone",
+}
+
+_POWER_RUNES = {
+    0: "Double Damage",
+    1: "Haste",
+    3: "Invisibility",
+    4: "Regeneration",
+    6: "Arcane",
+    8: "Shield",
+}
+
 
 class Dota2OpenDotaAdapter(GameAdapter):
     game_id = "dota2"
@@ -103,7 +125,12 @@ class Dota2OpenDotaAdapter(GameAdapter):
         events += self._chat_events(match, players, me, hero_lookup)
         events += self._gold_swing_events(match)
         events += self._lane_phase_events(match)
-        events += self._teamfight_events(match, me, hero)
+        events += self._teamfight_events(match, me, hero, hero_lookup)
+        events += self._buyback_events(players, me, hero, hero_lookup)
+        events += self._rune_events(me, hero)
+        signature_event = self._signature_event(me, hero, hero_lookup, context)
+        if signature_event is not None:
+            events.append(signature_event)
         match_start_time = min(0.0, min((event.t for event in events), default=0.0)) - 1.0
         events.append(NarrativeEvent(
             t=match_start_time, kind=EventKind.MATCH_START, actor=handle,
@@ -177,6 +204,18 @@ class Dota2OpenDotaAdapter(GameAdapter):
             return str(hero_name)
         return hero_slug.replace("npc_dota_hero_", "").replace("_", " ").title()
 
+    @staticmethod
+    def _prettify_combat_name(name: str, protagonist_slug: str | None = None) -> str:
+        pretty = str(name).strip()
+        if pretty.startswith("item_"):
+            pretty = pretty[5:]
+        if protagonist_slug:
+            hero_tail = protagonist_slug.replace("npc_dota_hero_", "")
+            prefix = f"{hero_tail}_"
+            if pretty.startswith(prefix):
+                pretty = pretty[len(prefix):]
+        return pretty.replace("_", " ").title()
+
     @staticmethod
     def _hero_slug(player: dict[str, Any], hero_lookup: dict[str, dict[Any, str]]) -> str | None:
         raw_name = player.get("hero_name")
@@ -524,25 +563,195 @@ class Dota2OpenDotaAdapter(GameAdapter):
             )
         ]
 
-    def _teamfight_events(self, match: dict, me: dict, hero: str) -> list[NarrativeEvent]:
+    def _teamfight_events(
+        self,
+        match: dict,
+        me: dict,
+        hero: str,
+        hero_lookup: dict[str, dict[Any, str]],
+    ) -> list[NarrativeEvent]:
         out = []
         my_slot = me.get("player_slot", 0)
+        protagonist_slug = self._hero_slug(me, hero_lookup)
         for tf in match.get("teamfights", []) or []:
             deaths = tf.get("deaths", 0)
             involved = False
-            for pslot, pdata in enumerate(tf.get("players", []) or []):
+            tf_players = tf.get("players", []) or []
+            misaligned = len(tf_players) != len(match.get("players", []))
+            protagonist_fight_data = None
+            for pslot, pdata in enumerate(tf_players):
+                if pslot >= len(match.get("players", [])):
+                    break
                 if pdata.get("deaths", 0) or pdata.get("damage", 0):
                     # OpenDota teamfight players are index-aligned to match players
                     if match["players"][pslot].get("player_slot") == my_slot:
                         involved = involved or bool(pdata.get("damage", 0))
+                        protagonist_fight_data = pdata
+
+            summary = f"A team fight erupts - {deaths} heroes fall."
+            importance = min(0.9, 0.4 + 0.08 * deaths)
+            data = {"end": tf.get("end"), "deaths": deaths}
+            if involved and protagonist_fight_data and not misaligned:
+                abilities = self._top_ability_uses(
+                    protagonist_fight_data.get("ability_uses", {}),
+                    protagonist_slug,
+                )
+                clutch_items = self._clutch_items(protagonist_fight_data.get("item_uses", {}))
+                damage = int(protagonist_fight_data.get("damage", 0) or 0)
+                died = int(protagonist_fight_data.get("deaths", 0) or 0) > 0
+                summary = self._teamfight_summary(hero, deaths, abilities, clutch_items, damage, died)
+                importance = min(0.95, importance + (0.05 if clutch_items else 0.0))
+                data = {
+                    **data,
+                    "abilities": abilities,
+                    "clutch_items": clutch_items,
+                    "damage": damage,
+                    "died": died,
+                }
+
             out.append(NarrativeEvent(
                 t=float(tf.get("start", 0)), kind=EventKind.PHASE,
-                summary=f"A team fight erupts - {deaths} heroes fall.",
-                importance=min(0.9, 0.4 + 0.08 * deaths),
+                summary=summary,
+                importance=importance,
                 protagonist_involved=involved,
-                data={"end": tf.get("end"), "deaths": deaths}))
+                data=data))
         return out
 
+    def _buyback_events(
+        self,
+        players: list[dict[str, Any]],
+        me: dict[str, Any],
+        hero: str,
+        hero_lookup: dict[str, dict[Any, str]],
+    ) -> list[NarrativeEvent]:
+        out: list[NarrativeEvent] = []
+        for player in players:
+            actor = hero if player is me else self._hero_name(player, hero_lookup)
+            for entry in player.get("buyback_log", []) or []:
+                if player is me:
+                    summary = f"{hero} pays the blood price and buys his life back."
+                    importance = 0.7
+                    protagonist_involved = True
+                else:
+                    summary = f"{actor} returns from death, gold spent for a second chance."
+                    importance = 0.5
+                    protagonist_involved = False
+                out.append(NarrativeEvent(
+                    t=float(entry.get("time", 0)),
+                    kind=EventKind.ECONOMY,
+                    actor=actor,
+                    summary=summary,
+                    importance=importance,
+                    protagonist_involved=protagonist_involved,
+                    data=entry,
+                ))
+        return out
+
+    @staticmethod
+    def _rune_events(me: dict[str, Any], hero: str) -> list[NarrativeEvent]:
+        out: list[NarrativeEvent] = []
+        for entry in me.get("runes_log", []) or []:
+            rune_name = _POWER_RUNES.get(entry.get("key"))
+            if rune_name is None:
+                continue
+            out.append(NarrativeEvent(
+                t=float(entry.get("time", 0)),
+                kind=EventKind.AMBIENT,
+                actor=hero,
+                summary=f"{hero} seizes a {rune_name} rune.",
+                importance=0.35,
+                protagonist_involved=True,
+                data=entry,
+            ))
+        return out
+
+    def _signature_event(
+        self,
+        me: dict[str, Any],
+        hero: str,
+        hero_lookup: dict[str, dict[Any, str]],
+        context: MatchContext,
+    ) -> NarrativeEvent | None:
+        damage_inflictor = me.get("damage_inflictor")
+        if not isinstance(damage_inflictor, dict) or not damage_inflictor:
+            return None
+        top_entry = max(damage_inflictor.items(), key=lambda item: int(item[1] or 0))
+        if int(top_entry[1] or 0) <= 0:
+            return None
+        pretty = self._prettify_combat_name(top_entry[0], self._hero_slug(me, hero_lookup))
+        context.world["signature"] = {"name": pretty, "damage": int(top_entry[1])}
+        return NarrativeEvent(
+            t=max(float(context.duration) - 1.0, 0.0),
+            kind=EventKind.AMBIENT,
+            actor=hero,
+            summary=f"Across the whole battle, no weapon of his drew more blood than {pretty}.",
+            importance=0.3,
+            protagonist_involved=True,
+            data={"name": pretty, "damage": int(top_entry[1])},
+        )
+
+    def _top_ability_uses(
+        self,
+        ability_uses: Any,
+        protagonist_slug: str | None,
+    ) -> list[str]:
+        if not isinstance(ability_uses, dict):
+            return []
+        ranked = sorted(
+            (
+                (name, int(count or 0))
+                for name, count in ability_uses.items()
+                if int(count or 0) > 0
+            ),
+            key=lambda item: (-item[1], item[0]),
+        )
+        return [
+            self._prettify_combat_name(name, protagonist_slug)
+            for name, _count in ranked[:2]
+        ]
+
+    def _clutch_items(self, item_uses: Any) -> list[str]:
+        if not isinstance(item_uses, dict):
+            return []
+        ranked = sorted(
+            (
+                (name, int(count or 0))
+                for name, count in item_uses.items()
+                if name in _CLUTCH_ITEMS and int(count or 0) > 0
+            ),
+            key=lambda item: (-item[1], item[0]),
+        )
+        return [self._prettify_combat_name(name) for name, _count in ranked]
+
+    @staticmethod
+    def _teamfight_summary(
+        hero: str,
+        deaths: int,
+        abilities: list[str],
+        clutch_items: list[str],
+        damage: int,
+        died: bool,
+    ) -> str:
+        summary = f"A team fight erupts - {deaths} heroes fall."
+        fragments: list[str] = []
+        if clutch_items:
+            item_text = " and ".join(clutch_items[:2])
+            fragments.append(f"{hero} opens his {item_text}")
+        if abilities:
+            ability_text = " and ".join(abilities[:2])
+            verb = "strikes with" if fragments else f"{hero} strikes with"
+            fragments.append(f"{verb} {ability_text}")
+        if damage > 0:
+            if fragments:
+                fragments[-1] = f"{fragments[-1]} ({damage} damage)"
+            else:
+                fragments.append(f"{hero} deals {damage} damage")
+        if died:
+            fragments.append("falls in the exchange")
+        else:
+            fragments.append("walking out untouched")
+        return f"{summary} {' and '.join(fragments)}."
+
     @staticmethod
     def _is_parsed_match(match: dict[str, Any]) -> bool:
         has_kills = any(player.get("kills_log") for player in match.get("players", []))
diff --git a/tests/fixtures/dota2_match.json b/tests/fixtures/dota2_match.json
index babf292..0a90ed4 100644
--- a/tests/fixtures/dota2_match.json
+++ b/tests/fixtures/dota2_match.json
@@ -57,7 +57,27 @@
      "time": 100,
      "key": "tango"
     }
-   ]
+   ],
+   "buyback_log": [
+    {
+     "time": 1535
+    }
+   ],
+   "runes_log": [
+    {
+     "time": 445,
+     "key": 1
+    },
+    {
+     "time": 820,
+     "key": 5
+    }
+   ],
+   "damage_inflictor": {
+    "slark_essence_shift": 5400,
+    "slark_dark_pact": 2100,
+    "item_black_king_bar": 0
+   }
   },
   {
    "player_slot": 1,
@@ -67,7 +87,8 @@
    "kills": 0,
    "assists": 0,
    "kills_log": [],
-   "purchase_log": []
+   "purchase_log": [],
+   "buyback_log": []
   },
   {
    "player_slot": 2,
@@ -77,7 +98,8 @@
    "kills": 0,
    "assists": 0,
    "kills_log": [],
-   "purchase_log": []
+   "purchase_log": [],
+   "buyback_log": []
   },
   {
    "player_slot": 3,
@@ -87,7 +109,8 @@
    "kills": 0,
    "assists": 0,
    "kills_log": [],
-   "purchase_log": []
+   "purchase_log": [],
+   "buyback_log": []
   },
   {
    "player_slot": 4,
@@ -97,7 +120,8 @@
    "kills": 0,
    "assists": 0,
    "kills_log": [],
-   "purchase_log": []
+   "purchase_log": [],
+   "buyback_log": []
   },
   {
    "player_slot": 128,
@@ -109,10 +133,15 @@
    "kills_log": [
     {
      "time": 980,
-     "key": "npc_dota_hero_juggernaut"
+    "key": "npc_dota_hero_slark"
     }
    ],
-   "purchase_log": []
+   "purchase_log": [],
+   "buyback_log": [
+    {
+     "time": 1548
+    }
+   ]
   },
   {
    "player_slot": 129,
@@ -124,14 +153,15 @@
    "kills_log": [
     {
      "time": 700,
-     "key": "npc_dota_hero_juggernaut"
+    "key": "npc_dota_hero_slark"
     },
     {
      "time": 1520,
-     "key": "npc_dota_hero_juggernaut"
+    "key": "npc_dota_hero_slark"
     }
    ],
-   "purchase_log": []
+   "purchase_log": [],
+   "buyback_log": []
   },
   {
    "player_slot": 130,
@@ -141,7 +171,8 @@
    "kills": 0,
    "assists": 0,
    "kills_log": [],
-   "purchase_log": []
+   "purchase_log": [],
+   "buyback_log": []
   },
   {
    "player_slot": 131,
@@ -151,7 +182,8 @@
    "kills": 0,
    "assists": 0,
    "kills_log": [],
-   "purchase_log": []
+   "purchase_log": [],
+   "buyback_log": []
   },
   {
    "player_slot": 132,
@@ -161,7 +193,8 @@
    "kills": 0,
    "assists": 0,
    "kills_log": [],
-   "purchase_log": []
+   "purchase_log": [],
+   "buyback_log": []
   }
  ],
  "chat": [
@@ -229,7 +262,7 @@
   {
    "time": 900,
    "type": "CHAT_MESSAGE_TOWER_KILL",
-   "unit": "npc_dota_hero_juggernaut",
+   "unit": "npc_dota_hero_slark",
    "key": "npc_dota_badguys_tower1_mid"
   },
   {
@@ -241,25 +274,25 @@
   {
    "time": 1610,
    "type": "CHAT_MESSAGE_AEGIS",
-   "unit": "npc_dota_hero_juggernaut",
+   "unit": "npc_dota_hero_slark",
    "key": ""
   },
   {
    "time": 1700,
    "type": "CHAT_MESSAGE_BARRACKS_KILL",
-   "unit": "npc_dota_hero_juggernaut",
+   "unit": "npc_dota_hero_slark",
    "key": "npc_dota_badguys_melee_rax_bot"
   },
   {
    "time": 2010,
    "type": "building_kill",
-   "unit": "npc_dota_hero_juggernaut",
+   "unit": "npc_dota_hero_slark",
    "key": "npc_dota_badguys_tower3_mid"
   },
   {
    "time": 2030,
    "type": "building_kill",
-   "unit": "npc_dota_hero_juggernaut",
+   "unit": "npc_dota_hero_slark",
    "key": "npc_dota_badguys_melee_rax_mid"
   },
   {
@@ -282,42 +315,67 @@
    "deaths": 4,
    "players": [
     {
-     "deaths": 0,
-     "damage": 900
+    "ability_uses": {
+     "slark_dark_pact": 2,
+     "slark_pounce": 1
+    },
+    "item_uses": {
+     "manta": 1
+    },
+    "deaths": 0,
+    "damage": 3100
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 900
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 900
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 900
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 900
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 900
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 900
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 900
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 900
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 900
     }
@@ -329,42 +387,67 @@
    "deaths": 5,
    "players": [
     {
+    "ability_uses": {
+     "slark_dark_pact": 1,
+     "slark_pounce": 1
+    },
+    "item_uses": {
+     "manta": 1
+    },
      "deaths": 1,
-     "damage": 1200
+    "damage": 1700
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 1,
      "damage": 1200
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 1,
      "damage": 1200
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 1,
      "damage": 1200
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 1,
      "damage": 1200
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 1,
      "damage": 1200
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 1,
      "damage": 1200
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 1,
      "damage": 1200
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 1,
      "damage": 1200
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 1,
      "damage": 1200
     }
@@ -376,42 +459,68 @@
    "deaths": 6,
    "players": [
     {
+    "ability_uses": {
+     "slark_dark_pact": 3,
+     "slark_pounce": 2
+    },
+    "item_uses": {
+     "black_king_bar": 1,
+     "manta": 1
+    },
      "deaths": 0,
-     "damage": 2000
+    "damage": 3300
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 2000
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 2000
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 2000
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 2000
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 2000
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 2000
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 2000
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 2000
     },
     {
+    "ability_uses": {},
+    "item_uses": {},
      "deaths": 0,
      "damage": 2000
     }
diff --git a/tests/test_pipeline.py b/tests/test_pipeline.py
index 4353976..b534c0d 100644
--- a/tests/test_pipeline.py
+++ b/tests/test_pipeline.py
@@ -14,7 +14,7 @@ FIXTURE = Path(__file__).parent / "fixtures" / "dota2_match.json"
 UNPARSED_FIXTURE = Path(__file__).parent / "fixtures" / "dota2_match_unparsed.json"
 
 HERO_CONSTANTS = {
-    "8": {"name": "npc_dota_hero_juggernaut", "localized_name": "Juggernaut"},
+    "8": {"name": "npc_dota_hero_slark", "localized_name": "Slark"},
     "9": {"name": "npc_dota_hero_crystal_maiden", "localized_name": "Crystal Maiden"},
     "10": {"name": "npc_dota_hero_axe", "localized_name": "Axe"},
     "11": {"name": "npc_dota_hero_zuus", "localized_name": "Zeus"},
@@ -61,7 +61,7 @@ def extraction():
 
 def test_adapter_resolves_protagonist(extraction):
     assert extraction.context.protagonist.name == "Ceaseless"
-    assert extraction.context.protagonist.persona == "Juggernaut"
+    assert extraction.context.protagonist.persona == "Slark"
     assert extraction.context.outcome == "victory"
     assert extraction.context.world["parsed"] is True
 
@@ -70,11 +70,11 @@ def test_hero_names_resolve_via_constants_map():
     adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
     result = adapter.extract(str(FIXTURE), protagonist_hint="Ceaseless")
 
-    assert result.context.protagonist.persona == "Juggernaut"
+    assert result.context.protagonist.persona == "Slark"
     assert "Crystal Maiden" in result.context.allies
     assert "Lion" in result.context.opponents
-    assert any(event.summary == "Juggernaut struck down Lion." for event in result.events)
-    assert any(event.summary == "Juggernaut completed Battle Fury." for event in result.events)
+    assert any(event.summary == "Slark struck down Lion." for event in result.events)
+    assert any(event.summary == "Slark completed Battle Fury." for event in result.events)
 
 
 def test_constants_fetch_failure_degrades_to_hero_id():
@@ -134,6 +134,19 @@ def test_adapter_event_stream(extraction):
 def test_chat_and_economy_events(extraction):
     social_events = [event for event in extraction.events if event.kind == EventKind.SOCIAL]
     economy_events = [event for event in extraction.events if event.kind == EventKind.ECONOMY]
+    buyback_events = [
+        event for event in extraction.events
+        if event.kind == EventKind.ECONOMY and "second chance" in event.summary
+        or event.kind == EventKind.ECONOMY and "blood price" in event.summary
+    ]
+    rune_events = [
+        event for event in extraction.events
+        if event.kind == EventKind.AMBIENT and "rune" in event.summary
+    ]
+    signature_events = [
+        event for event in extraction.events
+        if event.kind == EventKind.AMBIENT and "no weapon of his drew more blood" in event.summary
+    ]
     lane_phase_events = [
         event
         for event in extraction.events
@@ -153,20 +166,27 @@ def test_chat_and_economy_events(extraction):
         event for event in extraction.events
         if event.summary == "The Radiant tear through the Dire base - 4 structures fall."
     ]
+    teamfight_events = [
+        event for event in extraction.events
+        if event.kind == EventKind.PHASE and event.summary.startswith("A team fight erupts")
+    ]
+    touched_fight = next(event for event in teamfight_events if "Black King Bar" in event.summary)
+    fallen_fight = next(event for event in teamfight_events if "falls in the exchange" in event.summary)
 
     assert len(social_events) >= 4
     assert all(not event.summary.split(": ", 1)[-1].isdigit() for event in social_events)
     assert any(event.t == -40 for event in social_events)
     assert any(event.actor == "Ceaseless" and event.importance == 0.35 for event in social_events)
     assert any(event.actor != "Ceaseless" and event.importance == 0.2 for event in social_events)
-    assert len(economy_events) == 2
-    assert [event.summary for event in economy_events] == [
+    swing_events = [event for event in economy_events if "tide of gold" in event.summary]
+    assert len(swing_events) == 2
+    assert [event.summary for event in swing_events] == [
         "The tide of gold turns toward the Dire.",
         "The tide of gold turns toward the Radiant.",
     ]
     assert len(tower_events) == 1
     assert tower_events[0].summary == "The Dire's tier-1 mid tower falls."
-    assert tower_events[0].actor == "Juggernaut"
+    assert tower_events[0].actor == "Slark"
     assert tower_events[0].protagonist_involved is True
     assert len(aggregate_events) == 1
     assert aggregate_events[0].importance == 0.75
@@ -174,6 +194,51 @@ def test_chat_and_economy_events(extraction):
     assert len(barracks_events) == 1
     assert barracks_events[0].importance == 0.7
     assert len(lane_phase_events) == 1
+    assert "Black King Bar" in touched_fight.summary
+    assert "Pounce" in touched_fight.summary
+    assert "Dark Pact" in touched_fight.summary
+    assert "3300 damage" in touched_fight.summary
+    assert "walking out untouched" in touched_fight.summary
+    assert touched_fight.importance == 0.93
+    assert touched_fight.data["abilities"] == ["Dark Pact", "Pounce"]
+    assert touched_fight.data["clutch_items"] == ["Black King Bar"]
+    assert touched_fight.data["died"] is False
+    assert "falls in the exchange" in fallen_fight.summary
+    assert len(buyback_events) == 2
+    assert {event.actor for event in buyback_events} == {"Slark", "Lion"}
+    assert sorted(event.importance for event in buyback_events) == [0.5, 0.7]
+    assert len(rune_events) == 1
+    assert rune_events[0].summary == "Slark seizes a Haste rune."
+    assert len(signature_events) == 1
+    assert "Essence Shift" in signature_events[0].summary
+    assert extraction.context.world["signature"]["name"] == "Essence Shift"
+
+
+def test_teamfight_misalignment_falls_back_without_crashing(tmp_path: Path):
+    match_data = json.loads(FIXTURE.read_text(encoding="utf-8"))
+    match_data["teamfights"][0]["players"] = match_data["teamfights"][0]["players"][:-1]
+    misaligned_fixture = tmp_path / "dota2_misaligned.json"
+    misaligned_fixture.write_text(json.dumps(match_data), encoding="utf-8")
+
+    adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
+    result = adapter.extract(str(misaligned_fixture), protagonist_hint="Ceaseless")
+
+    fallback_fight = next(
+        event
+        for event in result.events
+        if event.kind == EventKind.PHASE and event.t == 950
+    )
+    assert fallback_fight.summary == "A team fight erupts - 4 heroes fall."
+
+
+def test_unparsed_match_does_not_emit_combat_texture_events():
+    adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
+    result = adapter.extract(str(UNPARSED_FIXTURE), protagonist_hint="Ceaseless")
+
+    assert "signature" not in result.context.world
+    assert not any("rune" in event.summary for event in result.events)
+    assert not any("second chance" in event.summary or "blood price" in event.summary for event in result.events)
+    assert not any("no weapon of his drew more blood" in event.summary for event in result.events)
 
 
 def test_planner_builds_arc(extraction):
warning: in the working copy of '.conductor/tasks/T-008-combat-texture-teamfight-ability-item-us.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-008-combat-texture-teamfight-ability-item-us.md', CRLF will be replaced by LF the next time Git touches it
```

## Original spec

## Context

Reader feedback on the first full story: skill casts have no timing/effect
texture, and item usage is entirely absent - yet clutch item timing and
decisive (or disastrous) casts are what players remember. OpenDota cannot
give per-cast timestamps or ult target counts (that is .dem combat-log
territory, deferred to the replay-parsing spike), but it DOES expose four
unmined sources at teamfight granularity:

- `match.teamfights[].players[i]` (index-aligned with `match.players[i]`):
  per-fight `ability_uses`, `item_uses`, `deaths`, `damage`, `buybacks`
- `players[].buyback_log`: timestamped buybacks
- `players[].runes_log`: timestamped rune pickups (`key` = rune id)
- `players[].damage_inflictor`: match-total damage per ability/item

## Scope

You may touch: `retale/adapters/dota2_opendota.py`,
`tests/fixtures/dota2_match.json`, `tests/test_pipeline.py`. Nothing else -
explicitly DO NOT touch `retale/narrative/` (T-007 is editing styler.py in
parallel). No new dependencies. Tests stay offline.

## Requirements

1. **Name prettifier.** Add a helper that turns internal ability/item slugs
   into display names: strip a leading `item_` prefix; if an ability name
   starts with the protagonist's hero slug tail + `_` (e.g. `slark_pounce`),
   strip that prefix; then `_`->space, Title Case. `black_king_bar` ->
   "Black King Bar", `slark_dark_pact` -> "Dark Pact".

2. **Teamfight combat texture.** In `_teamfight_events`, when the
   protagonist participated (existing detection), enrich the event:
   - collect his `ability_uses` for that fight, take the top 2 by count;
   - intersect his `item_uses` with a curated clutch set
     `{black_king_bar, blink, glimmer_cape, ghost, sheepstick, refresher,
       satanic, lotus_orb, sphere (Linken's Sphere), cyclone (Eul's)}`;
   - note his `damage` and whether his `deaths` for the fight is 0.
   Extend the summary, e.g.:
   "A team fight erupts - 4 heroes fall. Slark opens his Black King Bar and
   strikes with Pounce and Dark Pact (3100 damage), walking out untouched."
   Vary the tail: "...falls in the exchange." when his fight deaths > 0.
   Put the structured details into `data` (abilities, clutch_items, damage,
   died). Importance: +0.05 when a clutch item was used (cap 0.95).
   Guard index misalignment: if `teamfights[].players` length differs from
   `match['players']`, fall back to the current unenriched summary.

3. **Buyback events.** From every player's `buyback_log`, emit
   `EventKind.ECONOMY` events: protagonist buybacks importance 0.7,
   `protagonist_involved=True`, summary
   "Slark pays the blood price and buys his life back."; other players'
   buybacks importance 0.5 with the hero's name, phrased from the outside
   ("Invoker returns from death, gold spent for a second chance.").

4. **Rune events.** From the protagonist's `runes_log`, emit importance-0.35
   AMBIENT events for power runes only, mapping key ids:
   0 Double Damage, 1 Haste, 3 Invisibility, 4 Regeneration, 6 Arcane,
   8 Shield (other ids: skip). Summary: "Slark seizes a Haste rune."

5. **Damage signature.** Compute the protagonist's top entry in
   `damage_inflictor` (prettified, ability or item). Emit ONE AMBIENT event
   at t = duration - 1, importance 0.3, summary like
   "Across the whole battle, no weapon of his drew more blood than
   Essence Shift." Also store `context.world["signature"]` =
   {"name": <pretty>, "damage": <int>}. Skip both when the field is absent.

6. **Unparsed matches** (no teamfights/kills) must be unaffected: no new
   events, no crashes, `world["signature"]` absent.

## Acceptance criteria

- [ ] Fixture: extend teamfights[].players with index-aligned ability_uses /
      item_uses / deaths / damage for all 10 players (protagonist uses
      black_king_bar + slark_pounce x2 + slark_dark_pact x3 in one fight with
      deaths 0, and in another fight has deaths 1 and no clutch item);
      add protagonist buyback_log (1 entry), one enemy buyback,
      runes_log with one Haste (key 1) and one bounty (key 5, must be
      skipped), and damage_inflictor with a clear top ability.
- [ ] Tests assert: enriched fight summary contains "Black King Bar",
      "Pounce", "Dark Pact", the damage number, and the untouched phrasing;
      the deaths>0 fight uses the fallen phrasing; exactly 2 buyback events
      with correct importances and actors; exactly 1 rune event (Haste);
      signature event exists once and world["signature"]["name"] matches;
      misaligned teamfights players array falls back without raising;
      unparsed fixture emits none of the new event types.
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
