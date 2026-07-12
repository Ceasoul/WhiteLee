# Report T-003: EPUB export (stdlib-only)

generated: 2026-07-12 01:01 UTC

## Implementer notes

recollect with fixed tooling; no code changes

## Test output

```
............                                                             [100%]
12 passed in 0.70s
```

## Diff vs HEAD

```diff
.conductor/tasks/T-003-epub-export-stdlib-only.md |   2 +-
 retale/cli.py                                     |  62 ++++++++-
 retale/output/__init__.py                         |   5 +
 retale/output/epub.py                             | 162 ++++++++++++++++++++++
 tests/test_epub.py                                | 123 ++++++++++++++++
 5 files changed, 346 insertions(+), 8 deletions(-)
warning: in the working copy of '.conductor/tasks/T-003-epub-export-stdlib-only.md', CRLF will be replaced by LF the next time Git touches it


diff --git a/.conductor/tasks/T-003-epub-export-stdlib-only.md b/.conductor/tasks/T-003-epub-export-stdlib-only.md
index fcc3c3e..9f8976f 100644
--- a/.conductor/tasks/T-003-epub-export-stdlib-only.md
+++ b/.conductor/tasks/T-003-epub-export-stdlib-only.md
@@ -1,7 +1,7 @@
 ---
 id: T-003
 title: EPUB export (stdlib-only)
-status: todo
+status: review
 priority: 3
 depends: []
 ---
diff --git a/retale/cli.py b/retale/cli.py
index 2bc6e2e..dc369f5 100644
--- a/retale/cli.py
+++ b/retale/cli.py
@@ -12,10 +12,12 @@ from __future__ import annotations
 import argparse
 import sys
 from pathlib import Path
+from typing import Callable
 
-from retale.adapters.base import GameAdapter
-from retale.narrative.planner import Planner
+from retale.adapters.base import ExtractionResult, GameAdapter
+from retale.narrative.planner import Chapter, Planner
 from retale.narrative.styler import StyleProfile, Styler, export_json
+from retale.output import write_epub
 
 
 def _adapters() -> dict[str, type[GameAdapter]]:
@@ -45,6 +47,8 @@ def main(argv: list[str] | None = None) -> int:
     p.add_argument("--chapters", type=int, default=5,
                    help="target chapter count (auto-adjusted by density)")
     p.add_argument("-o", "--output", default=None, help="output .md path")
+    p.add_argument("--format", choices=("md", "epub"), default="md",
+                   help="output format")
     p.add_argument("--dry-run", action="store_true",
                    help="print the chapter plan as JSON, skip LLM generation")
     args = p.parse_args(argv)
@@ -68,17 +72,61 @@ def main(argv: list[str] | None = None) -> int:
     style = StyleProfile.load(args.style, sample_path=args.style_sample)
     styler = Styler(style)
 
-    def progress(ch, _prose):
+    def progress(ch: Chapter, _prose: str) -> None:
         print(f"[retale] chapter {ch.index}/{len(plan.chapters)} written "
               f"[{ch.arc_role}]", file=sys.stderr)
 
-    story = styler.write_story(plan, on_chapter=progress)
-    out = Path(args.output) if args.output else Path(
-        f"retale_{args.game}_{result.context.world.get('match_id', 'story')}.md")
-    out.write_text(story, encoding="utf-8")
+    chapter_exports: list[tuple[str, str]] = []
+
+    def collect_chapter(_ch: Chapter, prose: str) -> None:
+        chapter_exports.append(_chapter_export(prose))
+
+    callback: Callable[[Chapter, str], None] | None = progress
+    if args.format == "epub":
+        def epub_callback(ch: Chapter, prose: str) -> None:
+            progress(ch, prose)
+            collect_chapter(ch, prose)
+
+        callback = epub_callback
+
+    story = styler.write_story(plan, on_chapter=callback)
+    out = _output_path(args.game, result.context.world.get("match_id", "story"), args.output, args.format)
+    if args.format == "epub":
+        write_epub(
+            title=_story_title(result),
+            author=result.context.protagonist.name,
+            chapters=chapter_exports,
+            out_path=out,
+        )
+    else:
+        out.write_text(story, encoding="utf-8")
     print(f"[retale] story written to {out}", file=sys.stderr)
     return 0
 
 
+def _story_title(result: ExtractionResult) -> str:
+    return f"{result.context.protagonist.persona or result.context.protagonist.name} - a {result.context.game} tale"
+
+
+def _output_path(game: str, match_id: object, output: str | None, format_name: str) -> Path:
+    suffix = ".epub" if format_name == "epub" else ".md"
+    if output:
+        return Path(output).with_suffix(suffix)
+    return Path(f"retale_{game}_{match_id or 'story'}{suffix}")
+
+
+def _chapter_export(prose: str) -> tuple[str, str]:
+    stripped = prose.strip()
+    if not stripped:
+        return "Untitled Chapter", ""
+    lines = stripped.splitlines()
+    first_line = lines[0].strip()
+    if first_line.startswith("## "):
+        title = first_line[3:].strip() or "Untitled Chapter"
+        body = "\n".join(lines[1:]).strip()
+        return title, body
+    return "Untitled Chapter", stripped
+
+
 if __name__ == "__main__":
     raise SystemExit(main())
diff --git a/retale/output/__init__.py b/retale/output/__init__.py
new file mode 100644
index 0000000..eeb8954
--- /dev/null
+++ b/retale/output/__init__.py
@@ -0,0 +1,5 @@
+"""Output helpers for story export formats."""
+
+from retale.output.epub import write_epub
+
+__all__ = ["write_epub"]
diff --git a/retale/output/epub.py b/retale/output/epub.py
new file mode 100644
index 0000000..ea1ab9b
--- /dev/null
+++ b/retale/output/epub.py
@@ -0,0 +1,162 @@
+"""Minimal EPUB writer using only the Python standard library."""
+
+from __future__ import annotations
+
+from pathlib import Path
+from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile
+from xml.sax.saxutils import escape
+
+
+def write_epub(
+    title: str,
+    author: str,
+    chapters: list[tuple[str, str]],
+    out_path: Path,
+) -> None:
+    """Write a minimal EPUB archive from chapter markdown."""
+    out_path.parent.mkdir(parents=True, exist_ok=True)
+
+    with ZipFile(out_path, "w") as epub:
+        epub.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
+        epub.writestr(
+            "META-INF/container.xml",
+            _container_xml(),
+            compress_type=ZIP_DEFLATED,
+        )
+        epub.writestr(
+            "OEBPS/content.opf",
+            _content_opf(title, author, chapters),
+            compress_type=ZIP_DEFLATED,
+        )
+        epub.writestr(
+            "OEBPS/toc.ncx",
+            _toc_ncx(title, chapters),
+            compress_type=ZIP_DEFLATED,
+        )
+        for index, (chapter_title, chapter_md_text) in enumerate(chapters, start=1):
+            epub.writestr(
+                _chapter_href(index),
+                _chapter_xhtml(chapter_title, chapter_md_text),
+                compress_type=ZIP_DEFLATED,
+            )
+
+
+def _container_xml() -> str:
+    return """<?xml version="1.0" encoding="utf-8"?>
+<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
+  <rootfiles>
+    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
+  </rootfiles>
+</container>
+"""
+
+
+def _content_opf(title: str, author: str, chapters: list[tuple[str, str]]) -> str:
+    manifest_items = [
+        '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
+    ]
+    spine_items = []
+    for index, _chapter in enumerate(chapters, start=1):
+        manifest_items.append(
+            f'    <item id="chap{index}" href="chapter{index}.xhtml" media-type="application/xhtml+xml"/>'
+        )
+        spine_items.append(f'    <itemref idref="chap{index}"/>')
+
+    return (
+        '<?xml version="1.0" encoding="utf-8"?>\n'
+        '<package version="2.0" xmlns="http://www.idpf.org/2007/opf" '
+        'unique-identifier="bookid">\n'
+        "  <metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">\n"
+        f"    <dc:title>{escape(title)}</dc:title>\n"
+        f"    <dc:creator>{escape(author)}</dc:creator>\n"
+        "    <dc:language>en</dc:language>\n"
+        "    <dc:identifier id=\"bookid\">retale-epub</dc:identifier>\n"
+        "  </metadata>\n"
+        "  <manifest>\n"
+        + "\n".join(manifest_items)
+        + "\n  </manifest>\n"
+        "  <spine toc=\"ncx\">\n"
+        + "\n".join(spine_items)
+        + "\n  </spine>\n"
+        "</package>\n"
+    )
+
+
+def _toc_ncx(title: str, chapters: list[tuple[str, str]]) -> str:
+    nav_points = []
+    for index, (chapter_title, _chapter_text) in enumerate(chapters, start=1):
+        nav_points.append(
+            "  <navPoint id=\"nav{idx}\" playOrder=\"{idx}\">\n"
+            "    <navLabel><text>{label}</text></navLabel>\n"
+            "    <content src=\"chapter{idx}.xhtml\"/>\n"
+            "  </navPoint>".format(idx=index, label=escape(chapter_title))
+        )
+
+    return (
+        '<?xml version="1.0" encoding="utf-8"?>\n'
+        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
+        "  <head>\n"
+        "    <meta name=\"dtb:uid\" content=\"retale-epub\"/>\n"
+        "    <meta name=\"dtb:depth\" content=\"1\"/>\n"
+        "    <meta name=\"dtb:totalPageCount\" content=\"0\"/>\n"
+        "    <meta name=\"dtb:maxPageNumber\" content=\"0\"/>\n"
+        "  </head>\n"
+        f"  <docTitle><text>{escape(title)}</text></docTitle>\n"
+        "  <navMap>\n"
+        + "\n".join(nav_points)
+        + "\n  </navMap>\n"
+        "</ncx>\n"
+    )
+
+
+def _chapter_xhtml(chapter_title: str, chapter_md_text: str) -> str:
+    body_parts = [f"<h1>{escape(chapter_title)}</h1>"]
+    for block in _paragraph_blocks(chapter_md_text):
+        if block.startswith("## "):
+            body_parts.append(f"<h2>{escape(block[3:].strip())}</h2>")
+        else:
+            body_parts.append(f"<p>{escape(block)}</p>")
+
+    body = "\n    ".join(body_parts)
+    return (
+        '<?xml version="1.0" encoding="utf-8"?>\n'
+        '<html xmlns="http://www.w3.org/1999/xhtml">\n'
+        "  <head>\n"
+        f"    <title>{escape(chapter_title)}</title>\n"
+        "  </head>\n"
+        "  <body>\n"
+        f"    {body}\n"
+        "  </body>\n"
+        "</html>\n"
+    )
+
+
+def _paragraph_blocks(markdown_text: str) -> list[str]:
+    normalized = markdown_text.replace("\r\n", "\n").strip()
+    if not normalized:
+        return []
+
+    blocks: list[str] = []
+    current_lines: list[str] = []
+    for line in normalized.split("\n"):
+        stripped = line.strip()
+        if not stripped:
+            if current_lines:
+                blocks.append(" ".join(current_lines))
+                current_lines = []
+            continue
+        if stripped.startswith("## "):
+            if current_lines:
+                blocks.append(" ".join(current_lines))
+                current_lines = []
+            blocks.append(stripped)
+            continue
+        current_lines.append(stripped)
+
+    if current_lines:
+        blocks.append(" ".join(current_lines))
+    return blocks
+
+
+def _chapter_href(index: int) -> str:
+    return f"OEBPS/chapter{index}.xhtml"
diff --git a/tests/test_epub.py b/tests/test_epub.py
new file mode 100644
index 0000000..dc690bd
--- /dev/null
+++ b/tests/test_epub.py
@@ -0,0 +1,123 @@
+"""Tests for EPUB export."""
+
+from __future__ import annotations
+
+import zipfile
+from dataclasses import dataclass
+from pathlib import Path
+
+from retale.adapters.base import ExtractionResult
+from retale.cli import main
+from retale.core.schema import EventKind, MatchContext, NarrativeEvent, Protagonist
+from retale.output.epub import write_epub
+
+
+def test_write_epub_builds_valid_archive(tmp_path: Path):
+    out_path = tmp_path / "story.epub"
+    chapters = [
+        ("Arrival & Omen", "## Opening <Beat>\n\nFirst <line> & danger."),
+        ("Second Turn", "A plain paragraph with > and &.\n\n## Pivot\n\nAnother bit."),
+        ("Endgame", "Final <clash>."),
+    ]
+
+    write_epub("Story <Title>", "Author & Name", chapters, out_path)
+
+    with zipfile.ZipFile(out_path) as epub:
+        infos = epub.infolist()
+        assert infos[0].filename == "mimetype"
+        assert infos[0].compress_type == zipfile.ZIP_STORED
+        assert epub.read("mimetype") == b"application/epub+zip"
+        assert "META-INF/container.xml" in epub.namelist()
+        assert "OEBPS/content.opf" in epub.namelist()
+        assert "OEBPS/toc.ncx" in epub.namelist()
+
+        chapter_one = epub.read("OEBPS/chapter1.xhtml").decode("utf-8")
+        chapter_two = epub.read("OEBPS/chapter2.xhtml").decode("utf-8")
+        chapter_three = epub.read("OEBPS/chapter3.xhtml").decode("utf-8")
+
+    assert "Arrival &amp; Omen" in chapter_one
+    assert "<h2>Opening &lt;Beat&gt;</h2>" in chapter_one
+    assert "<p>First &lt;line&gt; &amp; danger.</p>" in chapter_one
+    assert "Second Turn" in chapter_two
+    assert "<h2>Pivot</h2>" in chapter_two
+    assert "&gt;" in chapter_two
+    assert "Endgame" in chapter_three
+    assert "&lt;clash&gt;" in chapter_three
+
+
+def test_cli_writes_epub_via_chapter_callback(monkeypatch, tmp_path: Path):
+    chapter_prose = [
+        "## Chapter One\n\nFirst paragraph.",
+        "## Chapter Two\n\nSecond paragraph.",
+        "## Chapter Three\n\nThird paragraph.",
+    ]
+
+    class FakeAdapter:
+        def extract(self, source: str, protagonist_hint: str | None = None) -> ExtractionResult:
+            return ExtractionResult(
+                context=MatchContext(
+                    game="dota2",
+                    protagonist=Protagonist(name="Hero", persona="Knight"),
+                    outcome="victory",
+                    duration=120.0,
+                    world={"match_id": 42, "time_unit": "seconds"},
+                ),
+                events=[NarrativeEvent(t=0.0, kind=EventKind.MATCH_START)],
+            )
+
+    @dataclass
+    class FakeChapter:
+        index: int
+        arc_role: str
+
+    @dataclass
+    class FakePlan:
+        chapters: list[FakeChapter]
+        logline: str
+        context: MatchContext
+
+    class FakePlanner:
+        def __init__(self, target_chapters: int = 5):
+            self.target_chapters = target_chapters
+
+        def plan(self, context: MatchContext, events: list[NarrativeEvent]) -> FakePlan:
+            return FakePlan(
+                chapters=[
+                    FakeChapter(index=1, arc_role="opening"),
+                    FakeChapter(index=2, arc_role="rising"),
+                    FakeChapter(index=3, arc_role="resolution"),
+                ],
+                logline="A compact tale.",
+                context=context,
+            )
+
+    class FakeStyle:
+        pass
+
+    class FakeStyler:
+        def __init__(self, style):
+            self.style = style
+
+        def write_story(self, plan: FakePlan, on_chapter=None) -> str:
+            parts = ["# Knight - a dota2 tale\n"]
+            for chapter, prose in zip(plan.chapters, chapter_prose):
+                parts.append(prose)
+                if on_chapter:
+                    on_chapter(chapter, prose)
+            return "\n\n".join(parts)
+
+    monkeypatch.setattr("retale.cli._adapters", lambda: {"dota2": FakeAdapter})
+    monkeypatch.setattr("retale.cli.Planner", FakePlanner)
+    monkeypatch.setattr("retale.cli.StyleProfile.load", lambda *args, **kwargs: FakeStyle())
+    monkeypatch.setattr("retale.cli.Styler", FakeStyler)
+
+    out_path = tmp_path / "story.md"
+    exit_code = main(["dota2", "fake.json", "--format", "epub", "-o", str(out_path)])
+
+    assert exit_code == 0
+    epub_path = out_path.with_suffix(".epub")
+    assert epub_path.exists()
+
+    with zipfile.ZipFile(epub_path) as epub:
+        assert "OEBPS/chapter1.xhtml" in epub.namelist()
+        assert "Chapter One" in epub.read("OEBPS/chapter1.xhtml").decode("utf-8")
warning: in the working copy of '.conductor/tasks/T-003-epub-export-stdlib-only.md', CRLF will be replaced by LF the next time Git touches it
```

## Original spec

## Context

Stories currently export as a single .md. Readers want EPUB for e-readers/phones.

## Scope

Create `retale/output/epub.py` (+ `retale/output/__init__.py`). Touch
`retale/cli.py` only to add `--format md|epub` (default md). Add
`tests/test_epub.py`. Allowed new dependency: NONE - build the EPUB by hand
(it's a zip: mimetype + META-INF/container.xml + OEBPS content). Use stdlib
`zipfile` and `xml.sax.saxutils.escape`.

## Requirements

1. `write_epub(title: str, author: str, chapters: list[tuple[str, str]], out_path: Path)`
   where chapters = [(chapter_title, chapter_md_text)]. Convert the
   chapter markdown minimally: `## X` -> `<h2>`, blank-line-separated paragraphs
   -> `<p>`. Escape all user text.
2. EPUB must validate structurally: `mimetype` stored FIRST and UNCOMPRESSED
   (zipfile: use ZIP_STORED for that entry), valid container.xml, content.opf
   with spine, one xhtml per chapter, toc.ncx.
3. CLI: `retale dota2 <src> --format epub` writes `.epub` beside the default
   output path. The Styler's per-chapter callback should feed chapters to the
   writer - do not re-parse the final markdown blob.

## Acceptance criteria

- [ ] `tests/test_epub.py`: builds an epub from 3 fake chapters, then re-opens
      with zipfile and asserts: first entry is `mimetype`, uncompressed,
      content == "application/epub+zip"; container.xml present; every chapter
      title appears in its xhtml; XML special chars in input are escaped.
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
