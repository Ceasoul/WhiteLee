"""Tests for styler hardening and CLI model plumbing."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from retale.cli import main
from retale.core.schema import EventKind, MatchContext, NarrativeEvent, Protagonist
from retale.narrative.planner import Chapter, StoryPlan
from retale.narrative.styler import Completion, LLMClient, StyleProfile, Styler


def _sample_plan() -> StoryPlan:
    context = MatchContext(
        game="dota2",
        protagonist=Protagonist(name="Hero", persona="Juggernaut"),
        outcome="victory",
    )
    event = NarrativeEvent(
        t=1.0,
        kind=EventKind.KILL,
        summary="Juggernaut struck down Lion.",
        importance=0.7,
        protagonist_involved=True,
    )
    chapter = Chapter(
        index=1,
        title_hint="Opening",
        arc_role="opening",
        t_start=0.0,
        t_end=10.0,
        events=[event],
        turning_point=event,
    )
    return StoryPlan(context=context, chapters=[chapter], logline="A compact tale.")


def test_sanitizer_drops_meta_text_before_header():
    sanitized = Styler(StyleProfile(name="test"))._sanitize_chapter(
        "Planning notes\nDo not show this\n## Actual Title\n\nStory text.",
        1,
    )

    assert sanitized.startswith("## Actual Title")
    assert "Planning notes" not in sanitized


def test_sanitizer_synthesizes_header_when_missing():
    sanitized = Styler(StyleProfile(name="test"))._sanitize_chapter("Plain body only.", 3)

    assert sanitized.startswith("## 第3章")
    assert "Plain body only." in sanitized


def test_write_chapter_retries_once_on_length():
    class MockClient:
        def __init__(self):
            self.calls: list[int] = []

        def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
            self.calls.append(max_tokens)
            if len(self.calls) == 1:
                return Completion(text="## First\n\nCut off", finish_reason="length")
            return Completion(text="## Second\n\nFull chapter.", finish_reason="stop")

    style = StyleProfile(name="test", words_per_chapter=100)
    client = MockClient()
    styler = Styler(style, client=client)  # type: ignore[arg-type]

    chapter_text = styler._write_chapter(_sample_plan(), _sample_plan().chapters[0], "Outline")

    assert client.calls == [4000, 8000]
    assert chapter_text == "## Second\n\nFull chapter."


def test_openai_compatible_http_error_includes_body(monkeypatch):
    class FakeResponse:
        ok = False
        status_code = 404
        text = '{"error":"unknown model"}'

        def json(self):
            return {}

    monkeypatch.setattr("retale.narrative.styler.requests.post", lambda *args, **kwargs: FakeResponse())
    client = LLMClient(model_override="missing-model")
    client.provider = "openai_compatible"

    with pytest.raises(RuntimeError) as exc_info:
        client.complete("system", "user", 4000)

    message = str(exc_info.value)
    assert "404" in message
    assert "unknown model" in message


def test_openai_compatible_passes_reasoning_effort(monkeypatch):
    captured_json = {}

    class FakeResponse:
        ok = True
        status_code = 200
        text = '{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}'

        def json(self):
            return {
                "choices": [
                    {
                        "message": {"content": "ok"},
                        "finish_reason": "stop",
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        captured_json.update(kwargs["json"])
        return FakeResponse()

    monkeypatch.setenv("RETALE_REASONING_EFFORT", "low")
    monkeypatch.setattr("retale.narrative.styler.requests.post", fake_post)
    client = LLMClient(model_override="test-model")
    client.provider = "openai_compatible"
    result = client._openai_compatible("system", "user", 4000)

    assert result.finish_reason == "stop"
    assert captured_json["reasoning_effort"] == "low"


def test_cli_model_flag_reaches_llm_client(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class FakeAdapter:
        def extract(self, source: str, protagonist_hint: str | None = None):
            return type(
                "Extraction",
                (),
                {
                    "context": MatchContext(
                        game="dota2",
                        protagonist=Protagonist(name="Hero", persona="Juggernaut"),
                        outcome="victory",
                        world={"match_id": 1},
                    ),
                    "events": [NarrativeEvent(t=0.0, kind=EventKind.MATCH_START, summary="start")],
                },
            )()

    @dataclass
    class FakePlan:
        chapters: list[Chapter]
        logline: str
        context: MatchContext

    class FakePlanner:
        def __init__(self, target_chapters: int = 5):
            self.target_chapters = target_chapters

        def plan(self, context: MatchContext, events: list[NarrativeEvent]) -> FakePlan:
            chapter = Chapter(
                index=1,
                title_hint="Hint",
                arc_role="opening",
                t_start=0.0,
                t_end=1.0,
                events=events,
                turning_point=events[0],
            )
            return FakePlan(chapters=[chapter], logline="Logline", context=context)

    class FakeClient:
        def __init__(self, model_override: str | None = None):
            captured["model_override"] = model_override

        def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
            return Completion(text="## Title\n\nBody", finish_reason="stop")

    monkeypatch.setattr("retale.cli._adapters", lambda: {"dota2": FakeAdapter})
    monkeypatch.setattr("retale.cli.Planner", FakePlanner)
    monkeypatch.setattr("retale.cli.StyleProfile.load", lambda *args, **kwargs: StyleProfile(name="test"))
    monkeypatch.setattr("retale.cli.LLMClient", FakeClient)

    out_path = tmp_path / "story.md"
    exit_code = main(["dota2", "fake.json", "--model", "gemini-test", "-o", str(out_path)])

    assert exit_code == 0
    assert captured["model_override"] == "gemini-test"
