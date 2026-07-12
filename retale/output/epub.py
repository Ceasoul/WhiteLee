"""Minimal EPUB writer using only the Python standard library."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile
from xml.sax.saxutils import escape


def write_epub(
    title: str,
    author: str,
    chapters: list[tuple[str, str]],
    out_path: Path,
) -> None:
    """Write a minimal EPUB archive from chapter markdown."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(out_path, "w") as epub:
        epub.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        epub.writestr(
            "META-INF/container.xml",
            _container_xml(),
            compress_type=ZIP_DEFLATED,
        )
        epub.writestr(
            "OEBPS/content.opf",
            _content_opf(title, author, chapters),
            compress_type=ZIP_DEFLATED,
        )
        epub.writestr(
            "OEBPS/toc.ncx",
            _toc_ncx(title, chapters),
            compress_type=ZIP_DEFLATED,
        )
        for index, (chapter_title, chapter_md_text) in enumerate(chapters, start=1):
            epub.writestr(
                _chapter_href(index),
                _chapter_xhtml(chapter_title, chapter_md_text),
                compress_type=ZIP_DEFLATED,
            )


def _container_xml() -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _content_opf(title: str, author: str, chapters: list[tuple[str, str]]) -> str:
    manifest_items = [
        '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
    ]
    spine_items = []
    for index, _chapter in enumerate(chapters, start=1):
        manifest_items.append(
            f'    <item id="chap{index}" href="chapter{index}.xhtml" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'    <itemref idref="chap{index}"/>')

    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package version="2.0" xmlns="http://www.idpf.org/2007/opf" '
        'unique-identifier="bookid">\n'
        "  <metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">\n"
        f"    <dc:title>{escape(title)}</dc:title>\n"
        f"    <dc:creator>{escape(author)}</dc:creator>\n"
        "    <dc:language>en</dc:language>\n"
        "    <dc:identifier id=\"bookid\">retale-epub</dc:identifier>\n"
        "  </metadata>\n"
        "  <manifest>\n"
        + "\n".join(manifest_items)
        + "\n  </manifest>\n"
        "  <spine toc=\"ncx\">\n"
        + "\n".join(spine_items)
        + "\n  </spine>\n"
        "</package>\n"
    )


def _toc_ncx(title: str, chapters: list[tuple[str, str]]) -> str:
    nav_points = []
    for index, (chapter_title, _chapter_text) in enumerate(chapters, start=1):
        nav_points.append(
            "  <navPoint id=\"nav{idx}\" playOrder=\"{idx}\">\n"
            "    <navLabel><text>{label}</text></navLabel>\n"
            "    <content src=\"chapter{idx}.xhtml\"/>\n"
            "  </navPoint>".format(idx=index, label=escape(chapter_title))
        )

    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        "  <head>\n"
        "    <meta name=\"dtb:uid\" content=\"retale-epub\"/>\n"
        "    <meta name=\"dtb:depth\" content=\"1\"/>\n"
        "    <meta name=\"dtb:totalPageCount\" content=\"0\"/>\n"
        "    <meta name=\"dtb:maxPageNumber\" content=\"0\"/>\n"
        "  </head>\n"
        f"  <docTitle><text>{escape(title)}</text></docTitle>\n"
        "  <navMap>\n"
        + "\n".join(nav_points)
        + "\n  </navMap>\n"
        "</ncx>\n"
    )


def _chapter_xhtml(chapter_title: str, chapter_md_text: str) -> str:
    body_parts = [f"<h1>{escape(chapter_title)}</h1>"]
    for block in _paragraph_blocks(chapter_md_text):
        if block.startswith("## "):
            body_parts.append(f"<h2>{escape(block[3:].strip())}</h2>")
        else:
            body_parts.append(f"<p>{escape(block)}</p>")

    body = "\n    ".join(body_parts)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml">\n'
        "  <head>\n"
        f"    <title>{escape(chapter_title)}</title>\n"
        "  </head>\n"
        "  <body>\n"
        f"    {body}\n"
        "  </body>\n"
        "</html>\n"
    )


def _paragraph_blocks(markdown_text: str) -> list[str]:
    normalized = markdown_text.replace("\r\n", "\n").strip()
    if not normalized:
        return []

    blocks: list[str] = []
    current_lines: list[str] = []
    for line in normalized.split("\n"):
        stripped = line.strip()
        if not stripped:
            if current_lines:
                blocks.append(" ".join(current_lines))
                current_lines = []
            continue
        if stripped.startswith("## "):
            if current_lines:
                blocks.append(" ".join(current_lines))
                current_lines = []
            blocks.append(stripped)
            continue
        current_lines.append(stripped)

    if current_lines:
        blocks.append(" ".join(current_lines))
    return blocks


def _chapter_href(index: int) -> str:
    return f"OEBPS/chapter{index}.xhtml"
