"""Pipeline tests: fixture JSON -> adapter -> planner -> (mock) styler."""

import json
from pathlib import Path

import pytest

from retale.adapters.dota2_opendota import Dota2OpenDotaAdapter
from retale.core.schema import EventKind
from retale.narrative.planner import Planner
from retale.narrative.styler import StyleProfile, Styler, export_json

FIXTURE = Path(__file__).parent / "fixtures" / "dota2_match.json"


@pytest.fixture()
def extraction():
    adapter = Dota2OpenDotaAdapter()
    return adapter.extract(str(FIXTURE), protagonist_hint="Ceaseless")


def test_adapter_resolves_protagonist(extraction):
    assert extraction.context.protagonist.name == "Ceaseless"
    assert extraction.context.protagonist.persona == "Juggernaut"
    assert extraction.context.outcome == "victory"


def test_adapter_event_stream(extraction):
    kinds = {e.kind for e in extraction.events}
    assert EventKind.MATCH_START in kinds
    assert EventKind.MATCH_END in kinds
    assert EventKind.KILL in kinds
    assert EventKind.DEATH in kinds
    # chronological
    ts = [e.t for e in extraction.events]
    assert ts == sorted(ts)
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

    assert len(social_events) >= 3
    assert any(event.actor == "Ceaseless" and event.importance == 0.35 for event in social_events)
    assert any(event.actor != "Ceaseless" and event.importance == 0.2 for event in social_events)
    assert len(economy_events) == 2
    assert [event.summary for event in economy_events] == [
        "The tide of gold turns toward the Dire.",
        "The tide of gold turns toward the Radiant.",
    ]
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
        return "## A Mock Chapter\n\nThe blade sang."


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
