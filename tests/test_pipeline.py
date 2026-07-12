"""Pipeline tests: fixture JSON -> adapter -> planner -> (mock) styler."""

import json
from pathlib import Path

import pytest

from retale.adapters.dota2_opendota import Dota2OpenDotaAdapter
from retale.core.schema import EventKind
from retale.narrative.planner import Planner
from retale.narrative.styler import Completion, StyleProfile, Styler, export_json

FIXTURE = Path(__file__).parent / "fixtures" / "dota2_match.json"
UNPARSED_FIXTURE = Path(__file__).parent / "fixtures" / "dota2_match_unparsed.json"

HERO_CONSTANTS = {
    "8": {"name": "npc_dota_hero_slark", "localized_name": "Slark"},
    "9": {"name": "npc_dota_hero_crystal_maiden", "localized_name": "Crystal Maiden"},
    "10": {"name": "npc_dota_hero_axe", "localized_name": "Axe"},
    "11": {"name": "npc_dota_hero_zuus", "localized_name": "Zeus"},
    "12": {"name": "npc_dota_hero_mirana", "localized_name": "Mirana"},
    "20": {"name": "npc_dota_hero_lion", "localized_name": "Lion"},
    "21": {"name": "npc_dota_hero_pudge", "localized_name": "Pudge"},
    "22": {"name": "npc_dota_hero_sniper", "localized_name": "Sniper"},
    "23": {"name": "npc_dota_hero_dazzle", "localized_name": "Dazzle"},
    "24": {"name": "npc_dota_hero_spirit_breaker", "localized_name": "Spirit Breaker"},
}

CHAT_WHEEL_CONSTANTS = {
    "71": {"message": "Well played!"},
    "93001": {"label": "Fish bait!"},
}


class FakeResponse:
    def __init__(self, payload=None, should_raise=False):
        self.payload = payload
        self.should_raise = should_raise

    def raise_for_status(self):
        if self.should_raise:
            raise RuntimeError("boom")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload=None, should_raise=False, url_map=None):
        self.payload = payload
        self.should_raise = should_raise
        self.url_map = url_map or {}
        self.calls = []

    def get(self, url, timeout=0):
        self.calls.append((url, timeout))
        if self.should_raise:
            raise RuntimeError("boom")
        payload = self.url_map.get(url, self.payload)
        return FakeResponse(payload, should_raise=False)


def _constants_session():
    return FakeSession(
        HERO_CONSTANTS,
        url_map={
            "https://api.opendota.com/api/constants/chat_wheel": CHAT_WHEEL_CONSTANTS,
        },
    )


@pytest.fixture()
def extraction():
    adapter = Dota2OpenDotaAdapter(session=_constants_session())
    return adapter.extract(str(FIXTURE), protagonist_hint="Ceaseless")


def test_adapter_resolves_protagonist(extraction):
    assert extraction.context.protagonist.name == "Ceaseless"
    assert extraction.context.protagonist.persona == "Slark"
    assert extraction.context.outcome == "victory"
    assert extraction.context.world["parsed"] is True


def test_hero_names_resolve_via_constants_map():
    adapter = Dota2OpenDotaAdapter(session=_constants_session())
    result = adapter.extract(str(FIXTURE), protagonist_hint="Ceaseless")

    assert result.context.protagonist.persona == "Slark"
    assert "Crystal Maiden" in result.context.allies
    assert "Lion" in result.context.opponents
    assert any(event.summary == "Slark struck down Lion." for event in result.events)
    assert any(event.summary == "Slark completed Battle Fury." for event in result.events)


def test_constants_fetch_failure_degrades_to_hero_id():
    adapter = Dota2OpenDotaAdapter(session=FakeSession(should_raise=True))
    result = adapter.extract(str(FIXTURE), protagonist_hint="Ceaseless")

    assert result.context.protagonist.persona == "Hero 8"
    assert "Hero 9" in result.context.allies
    assert "Hero 20" in result.context.opponents


def test_unparsed_match_sets_flag_and_warns(capsys):
    adapter = Dota2OpenDotaAdapter(session=_constants_session())
    result = adapter.extract(str(UNPARSED_FIXTURE), protagonist_hint="Ceaseless")
    captured = capsys.readouterr()

    assert result.context.world["parsed"] is False
    assert "no parsed replay data" in captured.err
    assert "stories will be skeletal" in captured.err


def test_death_detection_uses_exact_slug_match_for_zeus(tmp_path: Path):
    match_data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # Keep the fixture structure realistic while forcing the protagonist to use
    # a slug that differs from the localized name.
    match_data["players"][0]["hero_id"] = 11
    match_data["players"][0]["kills_log"] = []
    match_data["players"][5]["kills_log"] = [{"time": 980, "key": "npc_dota_hero_zuus"}]

    zeus_fixture = tmp_path / "dota2_zeus_slug.json"
    zeus_fixture.write_text(json.dumps(match_data), encoding="utf-8")

    adapter = Dota2OpenDotaAdapter(session=_constants_session())
    result = adapter.extract(str(zeus_fixture), protagonist_hint="Ceaseless")

    death_events = [event for event in result.events if event.kind == EventKind.DEATH]
    assert any(event.summary == "Zeus fell to Lion." for event in death_events)


def test_adapter_event_stream(extraction):
    kinds = {e.kind for e in extraction.events}
    assert EventKind.MATCH_START in kinds
    assert EventKind.MATCH_END in kinds
    assert EventKind.KILL in kinds
    assert EventKind.DEATH in kinds
    # chronological
    ts = [e.t for e in extraction.events]
    assert ts == sorted(ts)
    # MATCH_START must lead even with negative-time pre-game events.
    assert extraction.events[0].kind == EventKind.MATCH_START
    assert extraction.events[1].kind == EventKind.SOCIAL
    assert extraction.events[1].t == -83
    # protagonist involvement is marked
    assert any(e.protagonist_involved for e in extraction.events)


def test_chat_and_economy_events(extraction):
    social_events = [event for event in extraction.events if event.kind == EventKind.SOCIAL]
    economy_events = [event for event in extraction.events if event.kind == EventKind.ECONOMY]
    buyback_events = [
        event for event in extraction.events
        if event.kind == EventKind.ECONOMY and "second chance" in event.summary
        or event.kind == EventKind.ECONOMY and "blood price" in event.summary
    ]
    rune_events = [
        event for event in extraction.events
        if event.kind == EventKind.AMBIENT and "rune" in event.summary
    ]
    signature_events = [
        event for event in extraction.events
        if event.kind == EventKind.AMBIENT and "no weapon of his drew more blood" in event.summary
    ]
    lane_phase_events = [
        event
        for event in extraction.events
        if event.kind == EventKind.PHASE
        and event.t == 600
        and event.summary == "The laning stage draws to a close."
    ]
    tower_events = [
        event for event in extraction.events
        if event.kind == EventKind.OBJECTIVE and "tier-1 mid tower" in event.summary
    ]
    barracks_events = [
        event for event in extraction.events
        if event.kind == EventKind.OBJECTIVE and "melee barracks" in event.summary
    ]
    aggregate_events = [
        event for event in extraction.events
        if event.summary == "The Radiant tear through the Dire base - 4 structures fall."
    ]
    teamfight_events = [
        event for event in extraction.events
        if event.kind == EventKind.PHASE and event.summary.startswith("A team fight erupts")
    ]
    touched_fight = next(event for event in teamfight_events if "Black King Bar" in event.summary)
    fallen_fight = next(event for event in teamfight_events if "falls in the exchange" in event.summary)

    assert len(social_events) >= 4
    assert all(not event.summary.split(": ", 1)[-1].isdigit() for event in social_events)
    assert any(event.t == -40 for event in social_events)
    assert any(event.summary == 'ZapGod: "Well played!" (chat wheel)' for event in social_events)
    assert any(event.summary == 'FingerOfDeath: "Fish bait!" (chat wheel)' for event in social_events)
    assert not any("999999" in event.summary for event in social_events)
    assert any(event.actor == "Ceaseless" and event.importance == 0.35 for event in social_events)
    assert any(event.actor != "Ceaseless" and event.importance == 0.2 for event in social_events)
    ally_chatwheel = next(event for event in social_events if event.summary == 'ZapGod: "Well played!" (chat wheel)')
    enemy_chatwheel = next(event for event in social_events if event.summary == 'FingerOfDeath: "Fish bait!" (chat wheel)')
    chinese_taunt = next(event for event in social_events if event.summary == "FingerOfDeath: 菜")
    hubris_taunt = next(event for event in social_events if event.summary == "FingerOfDeath: ?")
    swing_events = [event for event in economy_events if "tide of gold" in event.summary]
    assert len(swing_events) == 2
    assert [event.summary for event in swing_events] == [
        "The tide of gold turns toward the Dire.",
        "The tide of gold turns toward the Radiant.",
    ]
    assert len(tower_events) == 1
    assert tower_events[0].summary == "The Dire's tier-1 mid tower falls."
    assert tower_events[0].actor == "Slark"
    assert tower_events[0].protagonist_involved is True
    assert len(aggregate_events) == 1
    assert aggregate_events[0].importance == 0.75
    assert len(aggregate_events[0].data["merged_keys"]) == 4
    assert len(barracks_events) == 1
    assert barracks_events[0].importance == 0.7
    assert len(lane_phase_events) == 1
    assert "Black King Bar" in touched_fight.summary
    assert "Pounce" in touched_fight.summary
    assert "Dark Pact" in touched_fight.summary
    assert "3300 damage" in touched_fight.summary
    assert "walking out untouched" in touched_fight.summary
    assert touched_fight.importance == 0.93
    assert touched_fight.data["abilities"] == ["Dark Pact", "Pounce"]
    assert touched_fight.data["clutch_items"] == ["Black King Bar"]
    assert touched_fight.data["died"] is False
    assert "falls in the exchange" in fallen_fight.summary
    assert len(buyback_events) == 2
    assert {event.actor for event in buyback_events} == {"Slark", "Lion"}
    assert sorted(event.importance for event in buyback_events) == [0.5, 0.7]
    assert len(rune_events) == 1
    assert rune_events[0].summary == "Slark seizes a Haste rune."
    assert len(signature_events) == 1
    assert "Essence Shift" in signature_events[0].summary
    assert extraction.context.world["signature"]["name"] == "Essence Shift"
    assert ally_chatwheel.data["channel"] == "chatwheel"
    assert ally_chatwheel.data["enemy"] is False
    assert enemy_chatwheel.data["channel"] == "chatwheel"
    assert enemy_chatwheel.data["enemy"] is True
    assert "菜" in chinese_taunt.summary
    assert chinese_taunt.data["channel"] == "chat"
    assert chinese_taunt.data["enemy"] is True
    assert chinese_taunt.data["taunt"] is True
    assert hubris_taunt.data["channel"] == "chat"
    assert hubris_taunt.data["enemy"] is True
    assert hubris_taunt.data["taunt"] is True
    assert hubris_taunt.data["hubris"] is True
    assert hubris_taunt.importance == 0.6


def test_teamfight_misalignment_falls_back_without_crashing(tmp_path: Path):
    match_data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    match_data["teamfights"][0]["players"] = match_data["teamfights"][0]["players"][:-1]
    misaligned_fixture = tmp_path / "dota2_misaligned.json"
    misaligned_fixture.write_text(json.dumps(match_data), encoding="utf-8")

    adapter = Dota2OpenDotaAdapter(session=_constants_session())
    result = adapter.extract(str(misaligned_fixture), protagonist_hint="Ceaseless")

    fallback_fight = next(
        event
        for event in result.events
        if event.kind == EventKind.PHASE and event.t == 950
    )
    assert fallback_fight.summary == "A team fight erupts - 4 heroes fall."


def test_unparsed_match_does_not_emit_combat_texture_events():
    adapter = Dota2OpenDotaAdapter(session=_constants_session())
    result = adapter.extract(str(UNPARSED_FIXTURE), protagonist_hint="Ceaseless")

    assert "signature" not in result.context.world
    assert not any("rune" in event.summary for event in result.events)
    assert not any("second chance" in event.summary or "blood price" in event.summary for event in result.events)
    assert not any("no weapon of his drew more blood" in event.summary for event in result.events)


def test_planner_builds_arc(extraction):
    plan = Planner().plan(extraction.context, extraction.events)
    assert 3 <= len(plan.chapters) <= 9
    assert plan.chapters[0].arc_role == "opening"
    assert plan.chapters[-1].arc_role == "resolution"
    if len(plan.chapters) >= 3:
        assert plan.chapters[-2].arc_role == "climax"
    # every event lands in exactly one chapter
    total = sum(len(c.events) for c in plan.chapters)
    assert total == len(extraction.events)
    # export is valid JSON
    json.loads(export_json(plan))


class MockLLM:
    def complete(self, system, user, max_tokens=0):
        if "Return STRICT JSON only" in system:
            return Completion(
                text='{"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}}',
                finish_reason="stop",
            )
        assert "NEVER invent outcomes" in system
        assert "CHAPTER" in user
        return Completion(text="## A Mock Chapter\n\nThe blade sang.", finish_reason="stop")


def test_styler_assembles_story(extraction):
    plan = Planner().plan(extraction.context, extraction.events)
    style = StyleProfile.load("adventure")
    styler = Styler(style, client=MockLLM())
    story = styler.write_story(plan)
    assert story.count("A Mock Chapter") == len(plan.chapters)
    assert story.startswith("# ")


def test_style_profiles_all_load():
    for name in ("adventure", "wuxia", "hardboiled", "chronicle_zh"):
        s = StyleProfile.load(name)
        assert s.prompt
        assert hasattr(s, "title_format")
        assert hasattr(s, "naming")
