"""Tests for terminology codex generation and title normalization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from retale.cli import main
from retale.core.schema import EventKind, MatchContext, NarrativeEvent, Protagonist
from retale.narrative.planner import Chapter, StoryPlan
from retale.narrative.styler import Completion, StyleProfile, Styler


def _two_chapter_plan() -> StoryPlan:
    context = MatchContext(
        game="dota2",
        protagonist=Protagonist(name="陆惊舟", persona="Slark"),
        outcome="victory",
        allies=["Invoker"],
        opponents=["Legion Commander"],
    )
    first = NarrativeEvent(
        t=1.0,
        kind=EventKind.KILL,
        summary="Slark strikes first.",
        importance=0.7,
        protagonist_involved=True,
    )
    second = NarrativeEvent(
        t=2.0,
        kind=EventKind.OBJECTIVE,
        summary="Radiant take the tower.",
        importance=0.6,
        protagonist_involved=True,
    )
    return StoryPlan(
        context=context,
        chapters=[
            Chapter(
                index=1,
                title_hint="First Blood",
                arc_role="opening",
                t_start=0.0,
                t_end=1.0,
                events=[first],
                turning_point=first,
            ),
            Chapter(
                index=2,
                title_hint="Tower Falls",
                arc_role="resolution",
                t_start=1.0,
                t_end=2.0,
                events=[second],
                turning_point=second,
            ),
        ],
        logline="A compact codex test.",
    )


def test_write_story_generates_codex_once_and_injects_terminology():
    plan = _two_chapter_plan()

    class RecordingClient:
        def __init__(self):
            self.calls: list[tuple[str, str]] = []

        def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
            self.calls.append((system, user))
            if len(self.calls) == 1:
                return Completion(
                    text=(
                        '{"heroes":{"Slark":"小鱼人","Legion Commander":"军团统帅"},'
                        '"protagonist_intro":"小鱼人“陆惊舟”","skills":{"Pounce":"追魂索命"},'
                        '"factions":{"Radiant":"天辉","Dire":"夜魇"}}'
                    ),
                    finish_reason="stop",
                )
            return Completion(text="## 旧标题\n\n正文。", finish_reason="stop")

    styler = Styler(
        StyleProfile(name="wuxia", language="zh", title_format="第{n}章 {title}", naming="Use Chinese nicknames."),
        client=RecordingClient(),  # type: ignore[arg-type]
    )
    story = styler.write_story(plan)
    calls = styler.client.calls  # type: ignore[attr-defined]

    assert len(calls) == 3
    assert "Return STRICT JSON only" in calls[0][0]
    assert "Use EXACTLY these names in every chapter" in calls[1][1]
    assert "heroes.Slark = 小鱼人" in calls[1][1]
    assert "factions.Radiant = 天辉" in calls[2][1]
    assert story.count("## 第") == 2


def test_invalid_codex_json_twice_falls_back_to_empty_codex(capsys):
    plan = _two_chapter_plan()

    class RecordingClient:
        def __init__(self):
            self.calls = 0

        def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
            self.calls += 1
            if self.calls <= 2:
                return Completion(text="not json", finish_reason="stop")
            return Completion(text="## Title\n\nStory body.", finish_reason="stop")

    styler = Styler(StyleProfile(name="test"), client=RecordingClient())  # type: ignore[arg-type]
    story = styler.write_story(plan)
    captured = capsys.readouterr()

    assert "warning" in captured.err
    assert "## Title" in story


def test_title_format_rewrites_without_double_prefix():
    styler = Styler(StyleProfile(name="zh", title_format="第{n}章 {title}"))

    sanitized = styler._sanitize_chapter("## 第四章 群雄并起\n\n正文。", 4)

    assert sanitized.startswith("## 第4章 群雄并起")
    assert sanitized.count("第4章") == 1


def test_cli_codex_existing_file_skips_generation_and_missing_file_writes(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    class FakeAdapter:
        def extract(self, source: str, protagonist_hint: str | None = None):
            return type(
                "Extraction",
                (),
                {
                    "context": MatchContext(
                        game="dota2",
                        protagonist=Protagonist(name="Hero", persona="Slark"),
                        outcome="victory",
                        world={"match_id": 7},
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

    class FakeStyler:
        def __init__(self, style, client=None):
            self.style = style
            captured["build_calls"] = 0

        def build_codex(self, plan):
            captured["build_calls"] = captured.get("build_calls", 0) + 1
            return {"heroes": {"Slark": "小鱼人"}, "protagonist_intro": "", "skills": {}, "factions": {}}

        def write_story(self, plan, on_chapter=None, codex=None):
            captured["codex"] = codex
            prose = "## Title\n\nBody"
            if on_chapter:
                on_chapter(plan.chapters[0], prose)
            return prose

    monkeypatch.setattr("retale.cli._adapters", lambda: {"dota2": FakeAdapter})
    monkeypatch.setattr("retale.cli.Planner", FakePlanner)
    monkeypatch.setattr("retale.cli.StyleProfile.load", lambda *args, **kwargs: StyleProfile(name="test"))
    monkeypatch.setattr("retale.cli.Styler", FakeStyler)

    existing_codex = tmp_path / "existing.codex.json"
    existing_codex.write_text(
        json.dumps({"heroes": {"Slark": "小鱼人"}, "protagonist_intro": "", "skills": {}, "factions": {}}),
        encoding="utf-8",
    )
    out_path = tmp_path / "story.md"
    exit_code = main(["dota2", "fake.json", "--codex", str(existing_codex), "-o", str(out_path)])

    assert exit_code == 0
    assert captured["build_calls"] == 0
    assert captured["codex"]["heroes"]["Slark"] == "小鱼人"  # type: ignore[index]

    missing_codex = tmp_path / "missing.codex.json"
    exit_code = main(["dota2", "fake.json", "--codex", str(missing_codex), "-o", str(out_path)])

    assert exit_code == 0
    assert missing_codex.exists()
    assert json.loads(missing_codex.read_text(encoding="utf-8"))["heroes"]["Slark"] == "小鱼人"


def test_sanitizer_fallback_preserves_blank_lines_and_indented_header():
    styler = Styler(StyleProfile(name="zh"))

    fallback = styler._sanitize_chapter("第一段。\n\n第二段。", 2)
    indented = styler._sanitize_chapter("  ## Title\n\nBody", 1)

    assert "第一段。\n\n第二段。" in fallback
    assert indented == "## Title\n\nBody"
