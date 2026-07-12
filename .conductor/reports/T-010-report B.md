# Report T-010: Chat wheel resolution, taunt tagging, hubris detection

generated: 2026-07-12 10:32 UTC

## Implementer notes

Addressed rework 1 within scope only. Replaced the three corrupted Chinese taunt entries in `_TAUNT_TEXTS` with the real UTF-8 strings `报警`, `菜`, and `?好`. Added an enemy typed-chat fixture line with content `菜` and updated pipeline coverage to assert the SOCIAL summary preserves `菜` and that `data["taunt"]` is true. While verifying this rework, the new UTF-8 fixture exposed a Windows locale issue in the adapter's local JSON loader, so `_load()` now reads saved `.json` files with `encoding="utf-8"`; this keeps offline fixtures working cross-locale without expanding scope. Verification passed with `python -m pytest tests/ -q` (36 passed) and `ruff check retale/ tests/` (clean). `_TAUNT_TEXTS` print evidence: command `python -X utf8 -c "from retale.adapters.dota2_opendota import _TAUNT_TEXTS; print([repr(item) for item in sorted(_TAUNT_TEXTS)])"` produced `["'?'", "'??'", "'???'", "'?好'", "'ez'", "'ez game'", "'gg ez'", "'noob'", "'report'", "'报警'", "'菜'"]`.

## Test output

```
....................................                                     [100%]
36 passed in 0.71s
```

## Diff vs d9c808f265b6437d9794bf6c020c4845a5d317bc

```diff
...010-chat-wheel-resolution-taunt-tagging-hubr.md |  13 ++
 retale/adapters/dota2_opendota.py                  | 142 ++++++++++++++++++---
 tests/fixtures/dota2_match.json                    |  18 +++
 tests/test_pipeline.py                             |  54 ++++++--
 4 files changed, 203 insertions(+), 24 deletions(-)
warning: in the working copy of '.conductor/tasks/T-010-chat-wheel-resolution-taunt-tagging-hubr.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-010-chat-wheel-resolution-taunt-tagging-hubr.md', CRLF will be replaced by LF the next time Git touches it


diff --git a/T-010-spec.md b/.conductor/tasks/T-010-chat-wheel-resolution-taunt-tagging-hubr.md
similarity index 81%
rename from T-010-spec.md
rename to .conductor/tasks/T-010-chat-wheel-resolution-taunt-tagging-hubr.md
index 30b1572..dabedd2 100644
--- a/T-010-spec.md
+++ b/.conductor/tasks/T-010-chat-wheel-resolution-taunt-tagging-hubr.md
@@ -1,3 +1,12 @@
+---
+id: T-010
+title: Chat wheel resolution, taunt tagging, hubris detection
+status: in_progress
+priority: 1
+depends: []
+base: d9c808f265b6437d9794bf6c020c4845a5d317bc
+---
+
 ## Context
 
 Product-level feedback: Dota 2's dramatic beats correlate strongly with chat
@@ -71,3 +80,7 @@ appear" is superseded - update it to assert they appear RESOLVED.
       for an enemy speaker and an ally speaker; the T-005 "no digit-only
       SOCIAL" assertion still holds (resolved text is not digits).
 - [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
+
+## Architect feedback (rework 1)
+
+打回一处:_TAUNT_TEXTS 中的三个中文词条被写成了 Unicode 替换字符(\ufffd),中文嘲讽词表实际失效。要求:(1) 用真实中文重写这三个词条:报警、菜、?好,写文件时显式使用 UTF-8 编码;(2) 新增测试:fixture 中加一条敌方 typed chat 内容为'菜',断言其 taunt=True 且 summary 含'菜',防止编码损毁再次静默通过;(3) 修好后在报告 notes 中粘贴 python -c 打印 _TAUNT_TEXTS 的实际输出。另记一条纪律(无需改动):测试只为规格中的要求背书,'Fish bait! 应为嘲讽'是你的测试自创的需求而非规格回归,词条可保留,但 notes 中的'regression'表述不实。
diff --git a/retale/adapters/dota2_opendota.py b/retale/adapters/dota2_opendota.py
index 981fd53..1d7d848 100644
--- a/retale/adapters/dota2_opendota.py
+++ b/retale/adapters/dota2_opendota.py
@@ -28,6 +28,7 @@ from retale.core.schema import (
 
 OPENDOTA_MATCH_URL = "https://api.opendota.com/api/matches/{match_id}"
 OPENDOTA_HEROES_URL = "https://api.opendota.com/api/constants/heroes"
+OPENDOTA_CHAT_WHEEL_URL = "https://api.opendota.com/api/constants/chat_wheel"
 
 # Objective type -> (EventKind, base importance, human phrasing)
 _OBJECTIVE_MAP: dict[str, tuple[EventKind, float, str]] = {
@@ -70,6 +71,32 @@ _POWER_RUNES = {
     8: "Shield",
 }
 
+# Community additions are welcome as taunt idioms evolve across regions and patches.
+_TAUNT_TEXTS = {
+    "?",
+    "??",
+    "???",
+    "ez",
+    "ez game",
+    "gg ez",
+    "noob",
+    "report",
+    "报警",
+    "菜",
+    "?好",
+}
+
+_TAUNT_CHAT_WHEEL_SUBSTRINGS = {
+    "well played",
+    "gg",
+    "ez",
+    "haha",
+    "thanks",
+    "my bad",
+    "fish bait",
+    "?",
+}
+
 
 class Dota2OpenDotaAdapter(GameAdapter):
     game_id = "dota2"
@@ -85,6 +112,7 @@ class Dota2OpenDotaAdapter(GameAdapter):
             raise ValueError("Match JSON has no players; is the match parsed?")
 
         hero_lookup = self._hero_lookup()
+        chat_wheel_lookup = self._chat_wheel_lookup()
         parsed = self._is_parsed_match(match)
         if not parsed:
             match_id = match.get("match_id", "unknown")
@@ -122,7 +150,7 @@ class Dota2OpenDotaAdapter(GameAdapter):
         events: list[NarrativeEvent] = []
         events += self._objective_events(match, me, hero, hero_lookup)
         events += self._player_events(players, me, hero, hero_lookup)
-        events += self._chat_events(match, players, me, hero_lookup)
+        events += self._chat_events(match, players, me, hero_lookup, chat_wheel_lookup)
         events += self._gold_swing_events(match)
         events += self._lane_phase_events(match)
         events += self._teamfight_events(match, me, hero, hero_lookup)
@@ -131,6 +159,7 @@ class Dota2OpenDotaAdapter(GameAdapter):
         signature_event = self._signature_event(me, hero, hero_lookup, context)
         if signature_event is not None:
             events.append(signature_event)
+        self._apply_chat_drama_tags(events, hero)
         match_start_time = min(0.0, min((event.t for event in events), default=0.0)) - 1.0
         events.append(NarrativeEvent(
             t=match_start_time, kind=EventKind.MATCH_START, actor=handle,
@@ -150,7 +179,7 @@ class Dota2OpenDotaAdapter(GameAdapter):
         """source is a match id, an OpenDota URL, or a path to saved JSON."""
         p = Path(source)
         if p.suffix == ".json" and p.exists():
-            return json.loads(p.read_text())
+            return json.loads(p.read_text(encoding="utf-8"))
         match_id = source.rstrip("/").split("/")[-1]
         resp = self.session.get(OPENDOTA_MATCH_URL.format(match_id=match_id), timeout=30)
         resp.raise_for_status()
@@ -186,6 +215,29 @@ class Dota2OpenDotaAdapter(GameAdapter):
                     by_id_slug[int(raw_id)] = str(hero_slug)
         return {"by_id": by_id, "by_slug": by_slug, "by_id_slug": by_id_slug}
 
+    def _chat_wheel_lookup(self) -> dict[Any, str]:
+        try:
+            resp = self.session.get(OPENDOTA_CHAT_WHEEL_URL, timeout=30)
+            resp.raise_for_status()
+            payload = resp.json()
+            if not isinstance(payload, dict):
+                return {}
+        except Exception:
+            return {}
+
+        lookup: dict[Any, str] = {}
+        for raw_id, raw_entry in payload.items():
+            if isinstance(raw_entry, dict):
+                message = raw_entry.get("message") or raw_entry.get("label")
+            else:
+                message = raw_entry
+            if not message:
+                continue
+            lookup[str(raw_id)] = str(message)
+            if str(raw_id).isdigit():
+                lookup[int(raw_id)] = str(message)
+        return lookup
+
     @staticmethod
     def _hero_name(player: dict[str, Any], hero_lookup: dict[str, dict[Any, str]]) -> str:
         raw_name = player.get("hero_name") or player.get("localized_name")
@@ -326,6 +378,7 @@ class Dota2OpenDotaAdapter(GameAdapter):
         players: list[dict],
         me: dict[str, Any],
         hero_lookup: dict[str, dict[Any, str]],
+        chat_wheel_lookup: dict[Any, str],
     ) -> list[NarrativeEvent]:
         players_by_slot = {
             int(player.get("player_slot", -1)): player
@@ -333,28 +386,45 @@ class Dota2OpenDotaAdapter(GameAdapter):
             if player.get("player_slot") is not None
         }
         protagonist_slot = int(me.get("player_slot", -1))
+        protagonist_is_radiant = protagonist_slot < 128
         out: list[NarrativeEvent] = []
 
         for line in match.get("chat", []) or []:
-            if str(line.get("type", "")) != "chat":
-                continue
-            message = str(line.get("key", "")).strip()
-            if not message or message.isdigit():
+            raw_type = str(line.get("type", ""))
+            raw_key = str(line.get("key", "")).strip()
+            channel = "chatwheel" if raw_type == "chatwheel" or raw_key.isdigit() else "chat"
+            if channel == "chatwheel":
+                message = self._resolve_chat_wheel_message(raw_key, chat_wheel_lookup)
+            else:
+                message = raw_key
+            if not message:
                 continue
 
-            actor, speaker_slot = self._chat_actor(line, players_by_slot, hero_lookup)
+            actor, speaker_slot, speaker_hero = self._chat_actor(line, players_by_slot, hero_lookup)
             protagonist_spoke = speaker_slot == protagonist_slot
             truncated_message = message[:120]
-            summary = f"{actor}: {truncated_message}" if actor else truncated_message
+            if channel == "chatwheel":
+                summary = f'{actor}: "{truncated_message}" (chat wheel)' if actor else f'"{truncated_message}" (chat wheel)'
+                base_importance = 0.15
+            else:
+                summary = f"{actor}: {truncated_message}" if actor else truncated_message
+                base_importance = 0.35 if protagonist_spoke else 0.2
+            data = {**line, "channel": channel}
+            if speaker_slot is not None:
+                data["enemy"] = (speaker_slot < 128) != protagonist_is_radiant
+            if speaker_hero:
+                data["speaker_hero"] = speaker_hero
+            if self._is_taunt(truncated_message, channel):
+                data["taunt"] = True
 
             out.append(NarrativeEvent(
                 t=float(line.get("time", 0)),
                 kind=EventKind.SOCIAL,
                 actor=actor or None,
                 summary=summary,
-                importance=0.35 if protagonist_spoke else 0.2,
+                importance=base_importance,
                 protagonist_involved=protagonist_spoke,
-                data=line,
+                data=data,
             ))
         return out
 
@@ -763,23 +833,65 @@ class Dota2OpenDotaAdapter(GameAdapter):
         line: dict[str, Any],
         players_by_slot: dict[int, dict[str, Any]],
         hero_lookup: dict[str, dict[Any, str]],
-    ) -> tuple[str, int | None]:
+    ) -> tuple[str, int | None, str | None]:
         speaker_slot = line.get("player_slot", line.get("unit"))
         if isinstance(speaker_slot, str) and speaker_slot.isdigit():
             speaker_slot = int(speaker_slot)
         if isinstance(speaker_slot, int):
             player = players_by_slot.get(speaker_slot)
             if player:
+                hero_name = Dota2OpenDotaAdapter._hero_name(player, hero_lookup)
                 actor = str(
-                    player.get("personaname") or Dota2OpenDotaAdapter._hero_name(player, hero_lookup)
+                    player.get("personaname") or hero_name
                 )
-                return actor, speaker_slot
-            return f"slot_{speaker_slot}", speaker_slot
+                return actor, speaker_slot, hero_name
+            return f"slot_{speaker_slot}", speaker_slot, None
 
         actor = str(line.get("unit", "")).strip()
         if actor.startswith("npc_dota_hero_"):
             actor = actor.replace("npc_dota_hero_", "").replace("_", " ").title()
-        return actor, None
+        return actor, None, actor or None
+
+    @staticmethod
+    def _resolve_chat_wheel_message(raw_key: str, chat_wheel_lookup: dict[Any, str]) -> str | None:
+        message = chat_wheel_lookup.get(raw_key)
+        if message is None and raw_key.isdigit():
+            message = chat_wheel_lookup.get(int(raw_key))
+        return str(message).strip() if message else None
+
+    @staticmethod
+    def _is_taunt(message: str, channel: str) -> bool:
+        lowered = message.strip().lower()
+        if channel == "chat":
+            return lowered in _TAUNT_TEXTS or (lowered and set(lowered) == {"?"})
+        return any(fragment in lowered for fragment in _TAUNT_CHAT_WHEEL_SUBSTRINGS)
+
+    @staticmethod
+    def _apply_chat_drama_tags(events: list[NarrativeEvent], protagonist_hero: str) -> None:
+        protagonist_windows = [
+            event
+            for event in events
+            if event.kind in {EventKind.KILL, EventKind.DEATH} and event.protagonist_involved
+        ]
+        death_times_by_target: dict[str, list[float]] = {}
+        for event in events:
+            if event.kind == EventKind.DEATH and event.target:
+                death_times_by_target.setdefault(str(event.target), []).append(float(event.t))
+            if event.kind == EventKind.KILL and event.target:
+                death_times_by_target.setdefault(str(event.target), []).append(float(event.t))
+
+        for event in events:
+            if event.kind != EventKind.SOCIAL or not event.data.get("taunt"):
+                continue
+            speaker_hero = event.data.get("speaker_hero")
+            if speaker_hero:
+                for death_time in death_times_by_target.get(str(speaker_hero), []):
+                    if event.t < death_time <= event.t + 60:
+                        event.importance = max(event.importance, 0.6)
+                        event.data["hubris"] = True
+                        break
+            if any(abs(event.t - candidate.t) <= 30 for candidate in protagonist_windows):
+                event.importance = max(event.importance, 0.45)
 
     @staticmethod
     def _advantage_sign(value: int | float) -> int:
diff --git a/tests/fixtures/dota2_match.json b/tests/fixtures/dota2_match.json
index 0a90ed4..a2c48e4 100644
--- a/tests/fixtures/dota2_match.json
+++ b/tests/fixtures/dota2_match.json
@@ -234,11 +234,29 @@
    "type": "chat",
    "key": "One more clean fight and the map is ours. Keep lanes shoved, hold buyback, and do not overextend beyond vision."
   },
+  {
+   "time": 1330,
+   "player_slot": 128,
+   "type": "chat",
+   "key": "菜"
+  },
+  {
+   "time": 1870,
+   "player_slot": 128,
+   "type": "chat",
+   "key": "?"
+  },
   {
    "time": 1810,
    "player_slot": 128,
    "type": "chatwheel",
    "key": "93001"
+  },
+  {
+   "time": 1820,
+   "player_slot": 128,
+   "type": "chatwheel",
+   "key": "999999"
   }
  ],
  "radiant_gold_adv": [
diff --git a/tests/test_pipeline.py b/tests/test_pipeline.py
index b534c0d..184acbb 100644
--- a/tests/test_pipeline.py
+++ b/tests/test_pipeline.py
@@ -26,6 +26,11 @@ HERO_CONSTANTS = {
     "24": {"name": "npc_dota_hero_spirit_breaker", "localized_name": "Spirit Breaker"},
 }
 
+CHAT_WHEEL_CONSTANTS = {
+    "71": {"message": "Well played!"},
+    "93001": {"label": "Fish bait!"},
+}
+
 
 class FakeResponse:
     def __init__(self, payload=None, should_raise=False):
@@ -41,21 +46,32 @@ class FakeResponse:
 
 
 class FakeSession:
-    def __init__(self, payload=None, should_raise=False):
+    def __init__(self, payload=None, should_raise=False, url_map=None):
         self.payload = payload
         self.should_raise = should_raise
+        self.url_map = url_map or {}
         self.calls = []
 
     def get(self, url, timeout=0):
         self.calls.append((url, timeout))
         if self.should_raise:
             raise RuntimeError("boom")
-        return FakeResponse(self.payload, should_raise=False)
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
 
 
 @pytest.fixture()
 def extraction():
-    adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
+    adapter = Dota2OpenDotaAdapter(session=_constants_session())
     return adapter.extract(str(FIXTURE), protagonist_hint="Ceaseless")
 
 
@@ -67,7 +83,7 @@ def test_adapter_resolves_protagonist(extraction):
 
 
 def test_hero_names_resolve_via_constants_map():
-    adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
+    adapter = Dota2OpenDotaAdapter(session=_constants_session())
     result = adapter.extract(str(FIXTURE), protagonist_hint="Ceaseless")
 
     assert result.context.protagonist.persona == "Slark"
@@ -87,7 +103,7 @@ def test_constants_fetch_failure_degrades_to_hero_id():
 
 
 def test_unparsed_match_sets_flag_and_warns(capsys):
-    adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
+    adapter = Dota2OpenDotaAdapter(session=_constants_session())
     result = adapter.extract(str(UNPARSED_FIXTURE), protagonist_hint="Ceaseless")
     captured = capsys.readouterr()
 
@@ -107,7 +123,7 @@ def test_death_detection_uses_exact_slug_match_for_zeus(tmp_path: Path):
     zeus_fixture = tmp_path / "dota2_zeus_slug.json"
     zeus_fixture.write_text(json.dumps(match_data), encoding="utf-8")
 
-    adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
+    adapter = Dota2OpenDotaAdapter(session=_constants_session())
     result = adapter.extract(str(zeus_fixture), protagonist_hint="Ceaseless")
 
     death_events = [event for event in result.events if event.kind == EventKind.DEATH]
@@ -126,7 +142,7 @@ def test_adapter_event_stream(extraction):
     # MATCH_START must lead even with negative-time pre-game events.
     assert extraction.events[0].kind == EventKind.MATCH_START
     assert extraction.events[1].kind == EventKind.SOCIAL
-    assert extraction.events[1].t == -40
+    assert extraction.events[1].t == -83
     # protagonist involvement is marked
     assert any(e.protagonist_involved for e in extraction.events)
 
@@ -176,8 +192,15 @@ def test_chat_and_economy_events(extraction):
     assert len(social_events) >= 4
     assert all(not event.summary.split(": ", 1)[-1].isdigit() for event in social_events)
     assert any(event.t == -40 for event in social_events)
+    assert any(event.summary == 'ZapGod: "Well played!" (chat wheel)' for event in social_events)
+    assert any(event.summary == 'FingerOfDeath: "Fish bait!" (chat wheel)' for event in social_events)
+    assert not any("999999" in event.summary for event in social_events)
     assert any(event.actor == "Ceaseless" and event.importance == 0.35 for event in social_events)
     assert any(event.actor != "Ceaseless" and event.importance == 0.2 for event in social_events)
+    ally_chatwheel = next(event for event in social_events if event.summary == 'ZapGod: "Well played!" (chat wheel)')
+    enemy_chatwheel = next(event for event in social_events if event.summary == 'FingerOfDeath: "Fish bait!" (chat wheel)')
+    chinese_taunt = next(event for event in social_events if event.summary == "FingerOfDeath: 菜")
+    hubris_taunt = next(event for event in social_events if event.summary == "FingerOfDeath: ?")
     swing_events = [event for event in economy_events if "tide of gold" in event.summary]
     assert len(swing_events) == 2
     assert [event.summary for event in swing_events] == [
@@ -212,6 +235,19 @@ def test_chat_and_economy_events(extraction):
     assert len(signature_events) == 1
     assert "Essence Shift" in signature_events[0].summary
     assert extraction.context.world["signature"]["name"] == "Essence Shift"
+    assert ally_chatwheel.data["channel"] == "chatwheel"
+    assert ally_chatwheel.data["enemy"] is False
+    assert enemy_chatwheel.data["channel"] == "chatwheel"
+    assert enemy_chatwheel.data["enemy"] is True
+    assert "菜" in chinese_taunt.summary
+    assert chinese_taunt.data["channel"] == "chat"
+    assert chinese_taunt.data["enemy"] is True
+    assert chinese_taunt.data["taunt"] is True
+    assert hubris_taunt.data["channel"] == "chat"
+    assert hubris_taunt.data["enemy"] is True
+    assert hubris_taunt.data["taunt"] is True
+    assert hubris_taunt.data["hubris"] is True
+    assert hubris_taunt.importance == 0.6
 
 
 def test_teamfight_misalignment_falls_back_without_crashing(tmp_path: Path):
@@ -220,7 +256,7 @@ def test_teamfight_misalignment_falls_back_without_crashing(tmp_path: Path):
     misaligned_fixture = tmp_path / "dota2_misaligned.json"
     misaligned_fixture.write_text(json.dumps(match_data), encoding="utf-8")
 
-    adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
+    adapter = Dota2OpenDotaAdapter(session=_constants_session())
     result = adapter.extract(str(misaligned_fixture), protagonist_hint="Ceaseless")
 
     fallback_fight = next(
@@ -232,7 +268,7 @@ def test_teamfight_misalignment_falls_back_without_crashing(tmp_path: Path):
 
 
 def test_unparsed_match_does_not_emit_combat_texture_events():
-    adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
+    adapter = Dota2OpenDotaAdapter(session=_constants_session())
     result = adapter.extract(str(UNPARSED_FIXTURE), protagonist_hint="Ceaseless")
 
     assert "signature" not in result.context.world
warning: in the working copy of '.conductor/tasks/T-010-chat-wheel-resolution-taunt-tagging-hubr.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-010-chat-wheel-resolution-taunt-tagging-hubr.md', CRLF will be replaced by LF the next time Git touches it
```

## Original spec

## Context

Product-level feedback: Dota 2's dramatic beats correlate strongly with chat
wheel messages and all-chat taunts - which T-005 filtered out entirely
because they surfaced as numeric IDs. The IDs are resolvable: OpenDota
serves `constants/chat_wheel` (id -> message text). Reinstating them WITH
resolution and temporal context turns noise into the story's drama metadata:
an enemy spamming "?" thirty seconds before dying is a self-contained
hubris-and-comeuppance beat.

This task is the data layer for the upcoming story-scout feature (T-011).

## Scope

You may touch: `retale/adapters/dota2_opendota.py`,
`tests/fixtures/dota2_match.json`, `tests/test_pipeline.py`. Nothing else.
No new dependencies. Tests stay offline (fake session, same pattern as the
hero constants). NOTE: T-005's test asserting chatwheel entries "must NOT
appear" is superseded - update it to assert they appear RESOLVED.

## Requirements

1. **Chat wheel constants.** Fetch
   `https://api.opendota.com/api/constants/chat_wheel` at most once per
   `extract()` via `self.session` (mirror the hero-constants pattern:
   graceful failure -> empty map). Entries carry a message text field
   (accept `message` or `label`, whichever is present).

2. **Reinstate chatwheel entries.** For chat entries with `type ==
   "chatwheel"` or digit-only keys: resolve the id through the map and emit
   a SOCIAL event with summary `{actor}: "{message}" (chat wheel)`.
   Unresolvable ids stay skipped (current behavior). Resolved messages pass
   through the existing 120-char truncation.

3. **Channel + side tagging.** Every SOCIAL event's `data` gains:
   `channel`: "chat" | "chatwheel"; `enemy`: True when the speaker's
   player_slot is on the opposite side from the protagonist (False for
   allies/protagonist, absent when the speaker cannot be resolved).

4. **Taunt tagging.** `data["taunt"] = True` when:
   - typed chat text, lowercased and stripped, is in
     `{"?", "??", "???", "ez", "ez game", "gg ez", "noob", "report",
       "报警", "菜", "?好"}` or consists only of `?` characters; or
   - a resolved chat-wheel message, lowercased, contains one of
     `{"well played", "gg", "ez", "haha", "thanks", "my bad", "?"}`.
   Keep both sets as module-level constants with a comment inviting
   community PRs.

5. **Hubris detector.** After all events are collected: for every SOCIAL
   event tagged `taunt` whose speaker's hero is resolvable, if that same
   hero DIES (appears as DEATH target or as KILL victim in protagonist
   kill events) within the following 60 seconds, raise the taunt event's
   importance to 0.6 and set `data["hubris"] = True`. Independently, any
   taunt within ±30s of a KILL/DEATH event involving the protagonist gets
   importance 0.45 (from the 0.15 chatwheel / 0.2 chat baseline). Higher
   rule wins; never lower an importance.

6. **Unparsed matches** remain unaffected (no chat -> no new events).

## Acceptance criteria

- [ ] Fixture: fake-session responses now include a chat_wheel constants
      stub mapping id 71 -> "Well played!" and one hero-line id (e.g.
      93001 -> "Fish bait!"); chat array keeps the two previously-dropped
      chatwheel entries and adds: an enemy typed "?" at time T followed by
      that enemy hero's death at T+30 (hubris case), and one chatwheel id
      absent from the stub (must stay dropped).
- [ ] Tests assert: resolved chatwheel SOCIAL events exist with the mapped
      text and channel "chatwheel"; the unmapped id emits nothing; the "?"
      event has taunt=True, hubris=True, importance 0.6; enemy flag correct
      for an enemy speaker and an ally speaker; the T-005 "no digit-only
      SOCIAL" assertion still holds (resolved text is not digits).
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.

## Architect feedback (rework 1)

打回一处:_TAUNT_TEXTS 中的三个中文词条被写成了 Unicode 替换字符(\ufffd),中文嘲讽词表实际失效。要求:(1) 用真实中文重写这三个词条:报警、菜、?好,写文件时显式使用 UTF-8 编码;(2) 新增测试:fixture 中加一条敌方 typed chat 内容为'菜',断言其 taunt=True 且 summary 含'菜',防止编码损毁再次静默通过;(3) 修好后在报告 notes 中粘贴 python -c 打印 _TAUNT_TEXTS 的实际输出。另记一条纪律(无需改动):测试只为规格中的要求背书,'Fish bait! 应为嘲讽'是你的测试自创的需求而非规格回归,词条可保留,但 notes 中的'regression'表述不实。
