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
    "8": {"name": "npc_dota_hero_juggernaut", "localized_name": "Juggernaut"},
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
    def __init__(self, payload=None, should_raise=False):
        self.payload = payload
        self.should_raise = should_raise
        self.calls = []

    def get(self, url, timeout=0):
        self.calls.append((url, timeout))
        if self.should_raise:
            raise RuntimeError("boom")
        return FakeResponse(self.payload, should_raise=False)


@pytest.fixture()
def extraction():
    adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
    return adapter.extract(str(FIXTURE), protagonist_hint="Ceaseless")


def test_adapter_resolves_protagonist(extraction):
    assert extraction.context.protagonist.name == "Ceaseless"
    assert extraction.context.protagonist.persona == "Juggernaut"
    assert extraction.context.outcome == "victory"
    assert extraction.context.world["parsed"] is True


def test_hero_names_resolve_via_constants_map():
    adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
    result = adapter.extract(str(FIXTURE), protagonist_hint="Ceaseless")

    assert result.context.protagonist.persona == "Juggernaut"
    assert "Crystal Maiden" in result.context.allies
    assert "Lion" in result.context.opponents
    assert any(event.summary == "Juggernaut struck down Lion." for event in result.events)
    assert any(event.summary == "Juggernaut completed Battle Fury." for event in result.events)


def test_constants_fetch_failure_degrades_to_hero_id():
    adapter = Dota2OpenDotaAdapter(session=FakeSession(should_raise=True))
    result = adapter.extract(str(FIXTURE), protagonist_hint="Ceaseless")

    assert result.context.protagonist.persona == "Hero 8"
    assert "Hero 9" in result.context.allies
    assert "Hero 20" in result.context.opponents


def test_unparsed_match_sets_flag_and_warns(capsys):
    adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
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

    adapter = Dota2OpenDotaAdapter(session=FakeSession(HERO_CONSTANTS))
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
    assert extraction.events[1].t == -40
    # protagonist involvement is marked
    assert any(e.protagonist_involved for e in extraction.events)


def test_chat_and_economy_events(extraction):
    social_events = [event for event in extraction.events if event.kind == EventKind.SOCIAL]
    economy_events = [event for event in extraction.events if event.kind == EventKind.ECONOMY]
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

    assert len(social_events) >= 4
    assert all(not event.summary.split(": ", 1)[-1].isdigit() for event in social_events)
    assert any(event.t == -40 for event in social_events)
    assert any(event.actor == "Ceaseless" and event.importance == 0.35 for event in social_events)
    assert any(event.actor != "Ceaseless" and event.importance == 0.2 for event in social_events)
    assert len(economy_events) == 2
    assert [event.summary for event in economy_events] == [
        "The tide of gold turns toward the Dire.",
        "The tide of gold turns toward the Radiant.",
    ]
    assert len(tower_events) == 1
    assert tower_events[0].summary == "The Dire's tier-1 mid tower falls."
    assert tower_events[0].actor == "Juggernaut"
    assert tower_events[0].protagonist_involved is True
    assert len(aggregate_events) == 1
    assert aggregate_events[0].importance == 0.75
    assert len(aggregate_events[0].data["merged_keys"]) == 4
    assert len(barracks_events) == 1
    assert barracks_events[0].importance == 0.7
    assert len(lane_phase_events) == 1


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
        assert "NEVER invent outcomes" in system
        assert "CHAPTER" in user
        return Completion(text="## A Mock Chapter\n\nThe blade sang.", finish_reason="stop")


def test_styler_assembles_story(extraction):
    plan = Planner().plan(extraction.context, extraction.events)
    style = StyleProfile.load("adventure")
    styler = Styler(style, client=MockLLM())
    story = styler.write_story(plan)
    assert story.count("## A Mock Chapter") == len(plan.chapters)
    assert story.startswith("# ")


def test_style_profiles_all_load():
    for name in ("adventure", "wuxia", "hardboiled", "chronicle_zh"):
        s = StyleProfile.load(name)
        assert s.prompt
