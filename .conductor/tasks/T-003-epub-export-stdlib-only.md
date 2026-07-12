---
id: T-003
title: EPUB export (stdlib-only)
status: done
priority: 3
depends: []
---

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
