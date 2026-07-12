"""ReTale command line.

Examples:
  retale dota2 8123456789 --style wuxia -o saga.md
  retale dota2 match.json --pov "MyNick" --style hardboiled
  retale cs2 demo.dem --pov s1mple --style adventure --dry-run
  retale dota2 8123456789 --style adventure --style-sample my_writing.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from retale.adapters.base import GameAdapter
from retale.narrative.planner import Planner
from retale.narrative.styler import StyleProfile, Styler, export_json


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
    p.add_argument("--chapters", type=int, default=5,
                   help="target chapter count (auto-adjusted by density)")
    p.add_argument("-o", "--output", default=None, help="output .md path")
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

    style = StyleProfile.load(args.style, sample_path=args.style_sample)
    styler = Styler(style)

    def progress(ch, _prose):
        print(f"[retale] chapter {ch.index}/{len(plan.chapters)} written "
              f"[{ch.arc_role}]", file=sys.stderr)

    story = styler.write_story(plan, on_chapter=progress)
    out = Path(args.output) if args.output else Path(
        f"retale_{args.game}_{result.context.world.get('match_id', 'story')}.md")
    out.write_text(story, encoding="utf-8")
    print(f"[retale] story written to {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
