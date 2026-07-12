"""ReTale command line.

Examples:
  retale dota2 8123456789 --style wuxia -o saga.md
  retale dota2 match.json --pov "MyNick" --style hardboiled
  retale cs2 demo.dem --pov s1mple --style adventure --dry-run
  retale dota2 8123456789 --style adventure --style-sample my_writing.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from retale.adapters.base import ExtractionResult, GameAdapter
from retale.narrative.planner import Chapter, Planner
from retale.narrative.styler import LLMClient, StyleProfile, Styler, export_json
from retale.output import write_epub


def _adapters() -> dict[str, type[GameAdapter]]:
    from retale.adapters.dota2_opendota import Dota2OpenDotaAdapter
    reg: dict[str, type[GameAdapter]] = {"dota2": Dota2OpenDotaAdapter}
    try:
        from retale.adapters.cs2_demo import CS2DemoAdapter
        reg["cs2"] = CS2DemoAdapter
    except ImportError:
        pass
    return reg


def main(argv: list[str] | None = None) -> int:
    reg = _adapters()
    p = argparse.ArgumentParser(
        prog="retale",
        description="Turn your gameplay into literature.")
    p.add_argument("game", choices=sorted(reg), help="game adapter")
    p.add_argument("source", help="match id / replay file / saved JSON")
    p.add_argument("--pov", default=None,
                   help="protagonist: player name, hero, or account id")
    p.add_argument("--style", default="adventure",
                   help="style profile name or path to a YAML")
    p.add_argument("--style-sample", default=None,
                   help="path to a text file whose voice the story imitates")
    p.add_argument("--codex", default=None,
                   help="load or save terminology codex JSON")
    p.add_argument("--model", default=None,
                   help="override the configured LLM model name")
    p.add_argument("--fresh", action="store_true",
                   help="discard any existing chapter checkpoint before generation")
    p.add_argument("--chapters", type=int, default=5,
                   help="target chapter count (auto-adjusted by density)")
    p.add_argument("-o", "--output", default=None, help="output .md path")
    p.add_argument("--format", choices=("md", "epub"), default="md",
                   help="output format")
    p.add_argument("--dry-run", action="store_true",
                   help="print the chapter plan as JSON, skip LLM generation")
    args = p.parse_args(argv)

    adapter = reg[args.game]()
    print(f"[retale] extracting events from {args.source} ...", file=sys.stderr)
    result = adapter.extract(args.source, protagonist_hint=args.pov)
    print(f"[retale] {len(result.events)} events | protagonist: "
          f"{result.context.protagonist.name} "
          f"({result.context.protagonist.persona}) | "
          f"outcome: {result.context.outcome}", file=sys.stderr)

    plan = Planner(target_chapters=args.chapters).plan(result.context, result.events)
    print(f"[retale] planned {len(plan.chapters)} chapters | {plan.logline}",
          file=sys.stderr)

    if args.dry_run:
        print(export_json(plan))
        return 0

    out = _output_path(args.game, result.context.world.get("match_id", "story"), args.output, args.format)
    progress_path = out.with_suffix(".progress.json")
    style = StyleProfile.load(args.style, sample_path=args.style_sample)
    if args.model:
        styler = Styler(style, client=LLMClient(model_override=args.model))
    else:
        styler = Styler(style)
    if args.fresh and progress_path.exists():
        progress_path.unlink()
    codex_path = _codex_path(out, args.codex)
    if codex_path.exists():
        codex = json.loads(codex_path.read_text(encoding="utf-8"))
    else:
        codex = styler.build_codex(plan)
        codex_path.write_text(
            json.dumps(codex, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def progress(ch: Chapter, _prose: str) -> None:
        print(f"[retale] chapter {ch.index}/{len(plan.chapters)} written "
              f"[{ch.arc_role}]", file=sys.stderr)

    chapter_exports: list[tuple[str, str]] = []

    def collect_chapter(_ch: Chapter, prose: str) -> None:
        chapter_exports.append(_chapter_export(prose))

    callback: Callable[[Chapter, str], None] | None = progress
    if args.format == "epub":
        def epub_callback(ch: Chapter, prose: str) -> None:
            progress(ch, prose)
            collect_chapter(ch, prose)

        callback = epub_callback

    story = styler.write_story(plan, on_chapter=callback, codex=codex, progress_path=progress_path)
    if args.format == "epub":
        write_epub(
            title=_story_title(result),
            author=result.context.protagonist.name,
            chapters=chapter_exports,
            out_path=out,
        )
    else:
        out.write_text(story, encoding="utf-8")
    print(f"[retale] story written to {out}", file=sys.stderr)
    return 0


def _story_title(result: ExtractionResult) -> str:
    return f"{result.context.protagonist.persona or result.context.protagonist.name} - a {result.context.game} tale"


def _output_path(game: str, match_id: object, output: str | None, format_name: str) -> Path:
    suffix = ".epub" if format_name == "epub" else ".md"
    if output:
        return Path(output).with_suffix(suffix)
    return Path(f"retale_{game}_{match_id or 'story'}{suffix}")


def _codex_path(output_path: Path, codex_arg: str | None) -> Path:
    if codex_arg:
        return Path(codex_arg)
    return output_path.with_suffix(".codex.json")


def _chapter_export(prose: str) -> tuple[str, str]:
    stripped = prose.strip()
    if not stripped:
        return "Untitled Chapter", ""
    lines = stripped.splitlines()
    first_line = lines[0].strip()
    if first_line.startswith("## "):
        title = first_line[3:].strip() or "Untitled Chapter"
        body = "\n".join(lines[1:]).strip()
        return title, body
    return "Untitled Chapter", stripped


if __name__ == "__main__":
    raise SystemExit(main())
