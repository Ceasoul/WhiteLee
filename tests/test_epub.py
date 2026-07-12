"""Tests for EPUB export."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from retale.adapters.base import ExtractionResult
from retale.cli import main
from retale.core.schema import EventKind, MatchContext, NarrativeEvent, Protagonist
from retale.output.epub import write_epub


def test_write_epub_builds_valid_archive(tmp_path: Path):
    out_path = tmp_path / "story.epub"
    chapters = [
        ("Arrival & Omen", "## Opening <Beat>\n\nFirst <line> & danger."),
        ("Second Turn", "A plain paragraph with > and &.\n\n## Pivot\n\nAnother bit."),
        ("Endgame", "Final <clash>."),
    ]

    write_epub("Story <Title>", "Author & Name", chapters, out_path)

    with zipfile.ZipFile(out_path) as epub:
        infos = epub.infolist()
        assert infos[0].filename == "mimetype"
        assert infos[0].compress_type == zipfile.ZIP_STORED
        assert epub.read("mimetype") == b"application/epub+zip"
        assert "META-INF/container.xml" in epub.namelist()
        assert "OEBPS/content.opf" in epub.namelist()
        assert "OEBPS/toc.ncx" in epub.namelist()

        chapter_one = epub.read("OEBPS/chapter1.xhtml").decode("utf-8")
        chapter_two = epub.read("OEBPS/chapter2.xhtml").decode("utf-8")
        chapter_three = epub.read("OEBPS/chapter3.xhtml").decode("utf-8")

    assert "Arrival &amp; Omen" in chapter_one
    assert "<h2>Opening &lt;Beat&gt;</h2>" in chapter_one
    assert "<p>First &lt;line&gt; &amp; danger.</p>" in chapter_one
    assert "Second Turn" in chapter_two
    assert "<h2>Pivot</h2>" in chapter_two
    assert "&gt;" in chapter_two
    assert "Endgame" in chapter_three
    assert "&lt;clash&gt;" in chapter_three


def test_cli_writes_epub_via_chapter_callback(monkeypatch, tmp_path: Path):
    chapter_prose = [
        "## Chapter One\n\nFirst paragraph.",
        "## Chapter Two\n\nSecond paragraph.",
        "## Chapter Three\n\nThird paragraph.",
    ]

    class FakeAdapter:
        def extract(self, source: str, protagonist_hint: str | None = None) -> ExtractionResult:
            return ExtractionResult(
                context=MatchContext(
                    game="dota2",
                    protagonist=Protagonist(name="Hero", persona="Knight"),
                    outcome="victory",
                    duration=120.0,
                    world={"match_id": 42, "time_unit": "seconds"},
                ),
                events=[NarrativeEvent(t=0.0, kind=EventKind.MATCH_START)],
            )

    @dataclass
    class FakeChapter:
        index: int
        arc_role: str

    @dataclass
    class FakePlan:
        chapters: list[FakeChapter]
        logline: str
        context: MatchContext

    class FakePlanner:
        def __init__(self, target_chapters: int = 5):
            self.target_chapters = target_chapters

        def plan(self, context: MatchContext, events: list[NarrativeEvent]) -> FakePlan:
            return FakePlan(
                chapters=[
                    FakeChapter(index=1, arc_role="opening"),
                    FakeChapter(index=2, arc_role="rising"),
                    FakeChapter(index=3, arc_role="resolution"),
                ],
                logline="A compact tale.",
                context=context,
            )

    class FakeStyle:
        pass

    class FakeStyler:
        def __init__(self, style):
            self.style = style

        def build_codex(self, plan: FakePlan) -> dict[str, object]:
            return {
                "heroes": {},
                "protagonist_intro": "",
                "skills": {},
                "factions": {},
            }

        def write_story(self, plan: FakePlan, on_chapter=None, codex=None, progress_path=None) -> str:
            parts = ["# Knight - a dota2 tale\n"]
            for chapter, prose in zip(plan.chapters, chapter_prose):
                parts.append(prose)
                if on_chapter:
                    on_chapter(chapter, prose)
            return "\n\n".join(parts)

    monkeypatch.setattr("retale.cli._adapters", lambda: {"dota2": FakeAdapter})
    monkeypatch.setattr("retale.cli.Planner", FakePlanner)
    monkeypatch.setattr("retale.cli.StyleProfile.load", lambda *args, **kwargs: FakeStyle())
    monkeypatch.setattr("retale.cli.Styler", FakeStyler)

    out_path = tmp_path / "story.md"
    exit_code = main(["dota2", "fake.json", "--format", "epub", "-o", str(out_path)])

    assert exit_code == 0
    epub_path = out_path.with_suffix(".epub")
    assert epub_path.exists()

    with zipfile.ZipFile(epub_path) as epub:
        assert "OEBPS/chapter1.xhtml" in epub.namelist()
        assert "Chapter One" in epub.read("OEBPS/chapter1.xhtml").decode("utf-8")
