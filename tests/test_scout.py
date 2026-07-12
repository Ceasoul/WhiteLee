"""Tests for story scouting, POV recommendation, and scout CLI mode."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

from retale.adapters.dota2_opendota import Dota2OpenDotaAdapter
from retale.cli import main
from retale.core.schema import EventKind, MatchContext, NarrativeEvent, Protagonist
from retale.narrative.scout import render_report, scout

FIXTURE = Path(__file__).parent / "fixtures" / "dota2_match.json"

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

    def get(self, url, timeout=0):
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


def _fixture_report():
    adapter = Dota2OpenDotaAdapter(session=_constants_session())
    extraction = adapter.extract(str(FIXTURE), protagonist_hint="Ceaseless")
    return scout(extraction.context, extraction.events)


def _sample_context(
    *,
    outcome: str = "victory",
    duration: float = 2000,
    roster: list[dict[str, object]] | None = None,
) -> MatchContext:
    return MatchContext(
        game="dota2",
        protagonist=Protagonist(name="Hero", persona="Slark"),
        outcome=outcome,
        duration=duration,
        world={"roster": roster or []},
    )


def test_scout_scores_fixture_and_recommends_enemy_pov():
    report = _fixture_report()
    text = render_report(report)

    assert report.breakdown["godlike"] == 15
    assert report.breakdown["rampage"] == 10
    assert report.breakdown["nemesis_arc"] == 20
    assert report.breakdown["hubris"] == 5
    assert report.recommendations[0].name == "BangBang"
    assert "streak 10" in report.recommendations[0].reason
    assert '--pov "BangBang"' in text
    assert len(report.roster) == 10
    assert any(entry["name"] == "Ceaseless" and entry["is_protagonist"] is True for entry in report.roster)


def test_scout_verdict_thresholds_are_exact():
    write_roster = [
        {
            "name": "Hero",
            "hero": "Slark",
            "side": "Radiant",
            "is_protagonist": True,
            "kills": 3,
            "deaths": 1,
            "assists": 1,
            "max_streak": 0,
            "max_multi_kill": 0,
        },
        {
            "name": "Threat",
            "hero": "Sniper",
            "side": "Dire",
            "is_protagonist": False,
            "kills": 12,
            "deaths": 2,
            "assists": 4,
            "max_streak": 10,
            "max_multi_kill": 5,
        },
    ]
    write_events = [
        NarrativeEvent(t=300, kind=EventKind.ECONOMY, summary="The tide of gold turns toward the Dire."),
        NarrativeEvent(t=600, kind=EventKind.ECONOMY, summary="The tide of gold turns toward the Radiant."),
        NarrativeEvent(
            t=900,
            kind=EventKind.KILL,
            target="Sniper",
            summary="Slark struck down Sniper.",
            protagonist_involved=True,
        ),
        NarrativeEvent(t=1000, kind=EventKind.SOCIAL, data={"hubris": True, "taunt": True}),
        NarrativeEvent(t=1100, kind=EventKind.SOCIAL, data={"hubris": True, "taunt": True}),
    ]
    write_report = scout(_sample_context(roster=write_roster), write_events)

    maybe_roster = [
        {
            "name": "Hero",
            "hero": "Slark",
            "side": "Radiant",
            "is_protagonist": True,
            "kills": 2,
            "deaths": 2,
            "assists": 3,
            "max_streak": 0,
            "max_multi_kill": 0,
        },
        {
            "name": "Burst",
            "hero": "Lina",
            "side": "Dire",
            "is_protagonist": False,
            "kills": 5,
            "deaths": 4,
            "assists": 6,
            "max_streak": 0,
            "max_multi_kill": 4,
        },
    ]
    maybe_events = [
        NarrativeEvent(t=300, kind=EventKind.ECONOMY, summary="The tide of gold turns toward the Dire."),
        NarrativeEvent(t=600, kind=EventKind.ECONOMY, summary="The tide of gold turns toward the Radiant."),
        NarrativeEvent(
            t=800,
            kind=EventKind.KILL,
            target="Lina",
            summary="Slark struck down Lina.",
            protagonist_involved=True,
        ),
        NarrativeEvent(
            t=900,
            kind=EventKind.DEATH,
            actor="Lina",
            target="Slark",
            summary="Slark fell to Lina.",
            protagonist_involved=True,
        ),
        NarrativeEvent(t=1000, kind=EventKind.SOCIAL, data={"hubris": True, "taunt": True}),
        NarrativeEvent(t=1100, kind=EventKind.SOCIAL, data={"hubris": True, "taunt": True}),
    ]
    maybe_report = scout(_sample_context(roster=maybe_roster), maybe_events)

    assert write_report.score == 60
    assert write_report.verdict == "WRITE"
    assert maybe_report.score == 35
    assert maybe_report.verdict == "MAYBE"


def test_scout_applies_full_stomp_penalty():
    roster = [
        {
            "name": "Hero",
            "hero": "Slark",
            "side": "Radiant",
            "is_protagonist": True,
            "kills": 5,
            "deaths": 0,
            "assists": 1,
            "max_streak": 0,
            "max_multi_kill": 0,
        }
    ]
    events = [
        NarrativeEvent(
            t=500,
            kind=EventKind.KILL,
            target="Lion",
            summary="Slark struck down Lion.",
            protagonist_involved=True,
        )
    ]

    report = scout(_sample_context(duration=1400, roster=roster), events)

    assert report.breakdown["stomp_penalty"] == -30
    assert report.score == 0
    assert report.verdict == "SKIP"


def test_scout_clutch_uses_buyback_beat_tag():
    roster = [
        {
            "name": "Hero",
            "hero": "Slark",
            "side": "Radiant",
            "is_protagonist": True,
            "kills": 5,
            "deaths": 3,
            "assists": 2,
            "max_streak": 0,
            "max_multi_kill": 0,
        }
    ]
    events = [
        NarrativeEvent(
            t=1000,
            kind=EventKind.ECONOMY,
            summary="Any prose is fine here.",
            protagonist_involved=True,
            data={"beat": "buyback"},
        )
    ]

    report = scout(_sample_context(roster=roster), events)

    assert report.breakdown["clutch"] == 5


def test_scout_module_stays_adapter_free():
    scout_module = importlib.import_module("retale.narrative.scout")
    source_path = Path(inspect.getsourcefile(scout_module) or "")
    source = source_path.read_text(encoding="utf-8")

    assert "retale.adapters" not in source


def test_cli_scout_prints_report_without_llm(monkeypatch, capsys):
    class FakeAdapter:
        def extract(self, source: str, protagonist_hint: str | None = None):
            adapter = Dota2OpenDotaAdapter(session=_constants_session())
            return adapter.extract(str(FIXTURE), protagonist_hint=protagonist_hint)

    class RaisingClient:
        def complete(self, system: str, user: str, max_tokens: int = 0):
            raise AssertionError("LLM should not be called in --scout mode")

    class FakeStyler:
        def __init__(self, style, client=None):
            self.client = client or RaisingClient()

        def build_codex(self, plan):
            self.client.complete("", "", 0)
            return {}

        def write_story(self, plan, on_chapter=None, codex=None, progress_path=None):
            self.client.complete("", "", 0)
            return ""

    monkeypatch.setattr("retale.cli._adapters", lambda: {"dota2": FakeAdapter})
    monkeypatch.setattr("retale.cli.LLMClient", lambda model_override=None: RaisingClient())
    monkeypatch.setattr("retale.cli.Styler", FakeStyler)

    exit_code = main(["dota2", str(FIXTURE), "--scout"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "SCORE + VERDICT" in captured.out
    assert "ROSTER" in captured.out
    assert "BangBang" in captured.out
