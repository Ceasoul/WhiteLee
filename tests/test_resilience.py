"""Tests for retry backoff and chapter checkpoint resume."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from retale.cli import main
from retale.core.schema import EventKind, MatchContext, NarrativeEvent, Protagonist
from retale.narrative.planner import Chapter, StoryPlan
from retale.narrative.styler import Completion, LLMClient, StyleProfile, Styler


def _sample_plan(chapter_count: int = 3) -> StoryPlan:
    context = MatchContext(
        game="dota2",
        protagonist=Protagonist(name="Hero", persona="Slark"),
        outcome="victory",
        world={"match_id": 42},
    )
    chapters = []
    for index in range(1, chapter_count + 1):
        event = NarrativeEvent(
            t=float(index),
            kind=EventKind.KILL,
            summary=f"Event {index}",
            importance=0.7,
            protagonist_involved=True,
        )
        chapters.append(
            Chapter(
                index=index,
                title_hint=f"Hint {index}",
                arc_role="opening" if index == 1 else "resolution",
                t_start=float(index - 1),
                t_end=float(index),
                events=[event],
                turning_point=event,
            )
        )
    return StoryPlan(context=context, chapters=chapters, logline="Resilience test.")


class FakeHTTPResponse:
    def __init__(self, status_code: int, body: str, payload: dict | None = None, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.text = body
        self._payload = payload or {}
        self.headers = headers or {}

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def test_complete_retries_429_with_server_hint(monkeypatch):
    responses = [
        FakeHTTPResponse(429, '{"error":"retry in 10.3s"}'),
        FakeHTTPResponse(
            200,
            '{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}',
            payload={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        ),
    ]
    waits: list[float] = []

    monkeypatch.setattr("retale.narrative.styler.requests.post", lambda *args, **kwargs: responses.pop(0))
    client = LLMClient(model_override="test-model", sleep_fn=waits.append)
    client.provider = "openai_compatible"

    result = client.complete("system", "user", max_tokens=100)

    assert result.text == "ok"
    assert waits == [10.3]


def test_complete_retries_three_times_then_raises(monkeypatch):
    waits: list[float] = []
    responses = [FakeHTTPResponse(429, '{"error":"quota hit"}') for _ in range(4)]

    monkeypatch.setattr("retale.narrative.styler.requests.post", lambda *args, **kwargs: responses.pop(0))
    client = LLMClient(model_override="test-model", sleep_fn=waits.append)
    client.provider = "openai_compatible"

    with pytest.raises(RuntimeError) as exc_info:
        client.complete("system", "user", max_tokens=100)

    assert waits == [5.0, 15.0, 45.0]
    assert "429" in str(exc_info.value)


def test_complete_does_not_retry_non_transient_400(monkeypatch):
    waits: list[float] = []

    monkeypatch.setattr(
        "retale.narrative.styler.requests.post",
        lambda *args, **kwargs: FakeHTTPResponse(400, '{"error":"bad request"}'),
    )
    client = LLMClient(model_override="test-model", sleep_fn=waits.append)
    client.provider = "openai_compatible"

    with pytest.raises(RuntimeError) as exc_info:
        client.complete("system", "user", max_tokens=100)

    assert waits == []
    assert "400" in str(exc_info.value)


def test_write_story_resumes_from_checkpoint(tmp_path: Path):
    plan = _sample_plan(3)
    progress_path = tmp_path / "story.progress.json"
    calls: list[int] = []
    restored: list[int] = []

    class FailingClient:
        model = "model-a"

        def __init__(self):
            self.fail_on = 3

        def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
            chapter_no = int(user.split("Now write CHAPTER ", 1)[1].split(" ", 1)[0])
            calls.append(chapter_no)
            if chapter_no == self.fail_on:
                raise RuntimeError("chapter 3 exploded")
            return Completion(text=f"## Chapter {chapter_no}\n\nBody {chapter_no}", finish_reason="stop")

    styler = Styler(StyleProfile(name="adventure"), client=FailingClient())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        styler.write_story(
            plan,
            codex={"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}},
            progress_path=progress_path,
        )

    saved = json.loads(progress_path.read_text(encoding="utf-8"))
    assert sorted(saved["chapters"]) == ["1", "2"]

    calls.clear()
    styler.client.fail_on = 99  # type: ignore[attr-defined]
    story = styler.write_story(
        plan,
        codex={"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}},
        progress_path=progress_path,
        on_chapter=lambda chapter, prose: restored.append(chapter.index),
    )

    assert calls == [3]
    assert restored == [1, 2, 3]
    assert "Body 3" in story


def test_checkpoint_fingerprint_mismatch_ignores_restore(tmp_path: Path):
    plan = _sample_plan(2)
    progress_path = tmp_path / "story.progress.json"
    progress_path.write_text(
        json.dumps(
            {
                "fingerprint": "stale",
                "chapters": {"1": "## Old\n\nBody"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    calls: list[int] = []

    class RecordingClient:
        model = "different-model"

        def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
            chapter_no = int(user.split("Now write CHAPTER ", 1)[1].split(" ", 1)[0])
            calls.append(chapter_no)
            return Completion(text=f"## Chapter {chapter_no}\n\nBody {chapter_no}", finish_reason="stop")

    styler = Styler(StyleProfile(name="adventure"), client=RecordingClient())  # type: ignore[arg-type]
    styler.write_story(
        plan,
        codex={"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}},
        progress_path=progress_path,
    )

    assert calls == [1, 2]


def test_successful_completion_deletes_progress_file(tmp_path: Path):
    plan = _sample_plan(2)
    progress_path = tmp_path / "story.progress.json"

    class SuccessClient:
        model = "model-a"

        def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
            chapter_no = int(user.split("Now write CHAPTER ", 1)[1].split(" ", 1)[0])
            return Completion(text=f"## Chapter {chapter_no}\n\nBody {chapter_no}", finish_reason="stop")

    styler = Styler(StyleProfile(name="adventure"), client=SuccessClient())  # type: ignore[arg-type]
    styler.write_story(
        plan,
        codex={"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}},
        progress_path=progress_path,
    )

    assert not progress_path.exists()


def test_cli_fresh_removes_existing_checkpoint(monkeypatch, tmp_path: Path):
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

        def build_codex(self, plan):
            return {"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}}

        def write_story(self, plan, on_chapter=None, codex=None, progress_path=None):
            captured["progress_path"] = progress_path
            captured["progress_existed_at_call"] = progress_path.exists() if progress_path else None
            return "## Title\n\nBody"

    monkeypatch.setattr("retale.cli._adapters", lambda: {"dota2": FakeAdapter})
    monkeypatch.setattr("retale.cli.Planner", FakePlanner)
    monkeypatch.setattr("retale.cli.StyleProfile.load", lambda *args, **kwargs: StyleProfile(name="test"))
    monkeypatch.setattr("retale.cli.Styler", FakeStyler)

    out_path = tmp_path / "story.md"
    progress_path = out_path.with_suffix(".progress.json")
    progress_path.write_text("{}", encoding="utf-8")

    exit_code = main(["dota2", "fake.json", "--fresh", "-o", str(out_path)])

    assert exit_code == 0
    assert captured["progress_path"] == progress_path
    assert captured["progress_existed_at_call"] is False
