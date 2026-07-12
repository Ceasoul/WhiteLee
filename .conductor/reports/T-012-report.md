# Report T-012: Rename ReTale to WhiteLee (package, CLI, env vars, docs)

generated: 2026-07-12 12:08 UTC

## Implementer notes

Renamed the project from Retale to WhiteLee across the repository scope requested by the spec. Used `git mv retale whitelee` so the package directory rename is tracked, then updated all source and test imports from `retale.` to `whitelee.`. Updated `pyproject.toml` project metadata and console script to `whitelee = "whitelee.cli:main"`, kept version unchanged, and added the `whitelee` keyword. Renamed all `RETALE_` environment variable prefixes to `WHITELEE_` with no compatibility shim. Updated CLI surface details: argparse prog name is `whitelee`, stderr log prefixes are `[whitelee]`, and default output filenames now use `whitelee_<game>_<id>`. Updated README.md, ROADMAP.md, CONTRIBUTING.md, `.gitignore`, the tracked sample codex filename, and other repository references so the old brand does not leak outside archival task history.

Validation:
- `python -m pip install -e .` completed, `pip show whitelee` reports editable install at `D:\ProjectDAQ\project\retale`.
- `whitelee --help` works.
- `python -m pip uninstall -y retale` removed the old unpublished editable install, and `Get-Command retale` now reports: `retale command not found`.
- `python -m pytest tests/ -q` -> `42 passed in 8.57s`
- `ruff check whitelee/` -> `All checks passed!`
- `git grep -il retale -- ':!.conductor'` output verbatim: <empty>

History note:
- `git log --follow --oneline -- whitelee/cli.py` is empty in the current uncommitted rename worktree; Git does not follow the staged rename on the new path until a rename commit exists.
- Pre-rename history is present on the old path: `git log --follow --oneline -- retale/cli.py | Select-Object -First 10` returned:
  `e8db250 T-011: story scout - worthiness scoring, POV recommendation, roster`
  `54156cc T-009: transient-error backoff retry + chapter checkpoint/resume`
  `b92ce18 T-007: terminology codex, naming conventions, title scheme, sanitizer fixes`
  `e9675a1 T-006: styler hardening - reasoning budgets, sanitizer, error context, --model`
  `a2b4e88 T-003: stdlib-only EPUB export`
  `6f1bad8 v0.1.1 baseline`

No behavior changes were introduced beyond the requested rename.

## Test output

```
..........................................                               [100%]
42 passed in 1.41s
```

## Diff vs e8db250cac769541ebbb7555a300c82177dc2f2a

```diff
rom whitelee.adapters.base import ExtractionResult, GameAdapter
+from whitelee.core.schema import (
     EventKind,
     MatchContext,
     NarrativeEvent,
@@ -31,7 +31,7 @@ class CS2DemoAdapter(GameAdapter):
             from demoparser2 import DemoParser  # type: ignore
         except ImportError as exc:  # pragma: no cover
             raise ImportError(
-                "CS2 support requires demoparser2. Install with: pip install retale[cs2]"
+                "CS2 support requires demoparser2. Install with: pip install whitelee[cs2]"
             ) from exc
 
         parser = DemoParser(source)
diff --git a/retale/adapters/dota2_opendota.py b/whitelee/adapters/dota2_opendota.py
similarity index 99%
rename from retale/adapters/dota2_opendota.py
rename to whitelee/adapters/dota2_opendota.py
index ec391e1..dff4ce2 100644
--- a/retale/adapters/dota2_opendota.py
+++ b/whitelee/adapters/dota2_opendota.py
@@ -1,7 +1,7 @@
 """Dota 2 adapter backed by the OpenDota API.
 
 Zero local parsing: give it a match id, it fetches the fully parsed
-match JSON from https://api.opendota.com and maps it onto the ReTale
+match JSON from https://api.opendota.com and maps it onto the WhiteLee
 event schema.
 
 Note: a match must have been parsed by OpenDota for rich fields
@@ -18,8 +18,8 @@ from typing import Any
 
 import requests
 
-from retale.adapters.base import ExtractionResult, GameAdapter
-from retale.core.schema import (
+from whitelee.adapters.base import ExtractionResult, GameAdapter
+from whitelee.core.schema import (
     EventKind,
     MatchContext,
     NarrativeEvent,
@@ -117,7 +117,7 @@ class Dota2OpenDotaAdapter(GameAdapter):
         if not parsed:
             match_id = match.get("match_id", "unknown")
             print(
-                "[retale] warning: this match has no parsed replay data; stories will be skeletal. "
+                "[whitelee] warning: this match has no parsed replay data; stories will be skeletal. "
                 "Use a recent match (replays expire) and request parsing at "
                 f"https://www.opendota.com/matches/{match_id}.",
                 file=sys.stderr,
diff --git a/retale/cli.py b/whitelee/cli.py
similarity index 81%
rename from retale/cli.py
rename to whitelee/cli.py
index 1bbf8ce..575affe 100644
--- a/retale/cli.py
+++ b/whitelee/cli.py
@@ -1,10 +1,10 @@
-"""ReTale command line.
+"""WhiteLee command line.
 
 Examples:
-  retale dota2 8123456789 --style wuxia -o saga.md
-  retale dota2 match.json --pov "MyNick" --style hardboiled
-  retale cs2 demo.dem --pov s1mple --style adventure --dry-run
-  retale dota2 8123456789 --style adventure --style-sample my_writing.txt
+  whitelee dota2 8123456789 --style wuxia -o saga.md
+  whitelee dota2 match.json --pov "MyNick" --style hardboiled
+  whitelee cs2 demo.dem --pov s1mple --style adventure --dry-run
+  whitelee dota2 8123456789 --style adventure --style-sample my_writing.txt
 """
 
 from __future__ import annotations
@@ -15,18 +15,18 @@ import sys
 from pathlib import Path
 from typing import Callable
 
-from retale.adapters.base import ExtractionResult, GameAdapter
-from retale.narrative.scout import render_report, scout
-from retale.narrative.planner import Chapter, Planner
-from retale.narrative.styler import LLMClient, StyleProfile, Styler, export_json
-from retale.output import write_epub
+from whitelee.adapters.base import ExtractionResult, GameAdapter
+from whitelee.narrative.scout import render_report, scout
+from whitelee.narrative.planner import Chapter, Planner
+from whitelee.narrative.styler import LLMClient, StyleProfile, Styler, export_json
+from whitelee.output import write_epub
 
 
 def _adapters() -> dict[str, type[GameAdapter]]:
-    from retale.adapters.dota2_opendota import Dota2OpenDotaAdapter
+    from whitelee.adapters.dota2_opendota import Dota2OpenDotaAdapter
     reg: dict[str, type[GameAdapter]] = {"dota2": Dota2OpenDotaAdapter}
     try:
-        from retale.adapters.cs2_demo import CS2DemoAdapter
+        from whitelee.adapters.cs2_demo import CS2DemoAdapter
         reg["cs2"] = CS2DemoAdapter
     except ImportError:
         pass
@@ -36,7 +36,7 @@ def _adapters() -> dict[str, type[GameAdapter]]:
 def main(argv: list[str] | None = None) -> int:
     reg = _adapters()
     p = argparse.ArgumentParser(
-        prog="retale",
+        prog="whitelee",
         description="Turn your gameplay into literature.")
     p.add_argument("game", choices=sorted(reg), help="game adapter")
     p.add_argument("source", help="match id / replay file / saved JSON")
@@ -64,9 +64,9 @@ def main(argv: list[str] | None = None) -> int:
     args = p.parse_args(argv)
 
     adapter = reg[args.game]()
-    print(f"[retale] extracting events from {args.source} ...", file=sys.stderr)
+    print(f"[whitelee] extracting events from {args.source} ...", file=sys.stderr)
     result = adapter.extract(args.source, protagonist_hint=args.pov)
-    print(f"[retale] {len(result.events)} events | protagonist: "
+    print(f"[whitelee] {len(result.events)} events | protagonist: "
           f"{result.context.protagonist.name} "
           f"({result.context.protagonist.persona}) | "
           f"outcome: {result.context.outcome}", file=sys.stderr)
@@ -76,7 +76,7 @@ def main(argv: list[str] | None = None) -> int:
         return 0
 
     plan = Planner(target_chapters=args.chapters).plan(result.context, result.events)
-    print(f"[retale] planned {len(plan.chapters)} chapters | {plan.logline}",
+    print(f"[whitelee] planned {len(plan.chapters)} chapters | {plan.logline}",
           file=sys.stderr)
 
     if args.dry_run:
@@ -103,7 +103,7 @@ def main(argv: list[str] | None = None) -> int:
         )
 
     def progress(ch: Chapter, _prose: str) -> None:
-        print(f"[retale] chapter {ch.index}/{len(plan.chapters)} written "
+        print(f"[whitelee] chapter {ch.index}/{len(plan.chapters)} written "
               f"[{ch.arc_role}]", file=sys.stderr)
 
     chapter_exports: list[tuple[str, str]] = []
@@ -129,7 +129,7 @@ def main(argv: list[str] | None = None) -> int:
         )
     else:
         out.write_text(story, encoding="utf-8")
-    print(f"[retale] story written to {out}", file=sys.stderr)
+    print(f"[whitelee] story written to {out}", file=sys.stderr)
     return 0
 
 
@@ -141,7 +141,7 @@ def _output_path(game: str, match_id: object, output: str | None, format_name: s
     suffix = ".epub" if format_name == "epub" else ".md"
     if output:
         return Path(output).with_suffix(suffix)
-    return Path(f"retale_{game}_{match_id or 'story'}{suffix}")
+    return Path(f"whitelee_{game}_{match_id or 'story'}{suffix}")
 
 
 def _codex_path(output_path: Path, codex_arg: str | None) -> Path:
diff --git a/whitelee/core/__init__.py b/whitelee/core/__init__.py
new file mode 100644
index 0000000..aba55bf
--- /dev/null
+++ b/whitelee/core/__init__.py
@@ -0,0 +1,77 @@
+"""WhiteLee core schema.
+
+Every game adapter must emit a stream of NarrativeEvent objects plus a
+MatchContext. The narrative engine only ever sees these two types, which
+is what makes WhiteLee game-agnostic: adding a new game means writing one
+adapter, never touching the narrative layer.
+"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass, field
+from enum import Enum
+from typing import Any, Optional
+
+
+class EventKind(str, Enum):
+    """Game-agnostic event vocabulary.
+
+    Deliberately small. Adapters map hundreds of game-specific event
+    types onto this vocabulary; nuance goes into `data` and `summary`.
+    """
+
+    MATCH_START = "match_start"
+    MATCH_END = "match_end"
+    PHASE = "phase"              # round start/end, new turn, new day, boss phase
+    KILL = "kill"                # actor eliminated target
+    DEATH = "death"              # protagonist (or ally) died
+    OBJECTIVE = "objective"      # tower/bomb plant/city captured/quest done
+    ACQUISITION = "acquisition"  # item purchase, loot, tech researched, level up
+    MOVEMENT = "movement"        # rotation, retreat, exploration
+    ECONOMY = "economy"          # gold swing, resource crisis
+    SOCIAL = "social"            # chat, ping, trade, diplomacy, guild event
+    SETBACK = "setback"          # lost fight, lost city, wipe
+    TRIUMPH = "triumph"          # won fight, ace, wonder built
+    AMBIENT = "ambient"          # flavor: weather, map events, background
+
+
+@dataclass
+class NarrativeEvent:
+    """One thing that happened, from the game's point of view."""
+
+    t: float                     # seconds (or turn number) from match start
+    kind: EventKind
+    actor: Optional[str] = None      # canonical entity name ("protagonist" allowed)
+    target: Optional[str] = None
+    summary: str = ""                # short factual sentence, e.g. "Juggernaut killed Lion mid lane"
+    importance: float = 0.3          # 0..1, adapter's estimate of narrative weight
+    protagonist_involved: bool = False
+    data: dict[str, Any] = field(default_factory=dict)  # raw game-specific payload
+
+    def __post_init__(self) -> None:
+        self.importance = max(0.0, min(1.0, self.importance))
+
+
+@dataclass
+class Protagonist:
+    """Who the story is about."""
+
+    name: str                        # in-game handle
+    persona: str = ""                # role/class/civ, e.g. "Juggernaut, carry"
+    traits: list[str] = field(default_factory=list)  # optional player-supplied traits
+
+
+@dataclass
+class MatchContext:
+    """Everything the narrative engine needs beyond the event stream."""
+
+    game: str                        # "dota2", "cs2", "civ6", ...
+    protagonist: Protagonist
+    outcome: str = "unknown"         # "victory" | "defeat" | "draw" | "unknown"
+    duration: float = 0.0            # seconds or turns
+    world: dict[str, Any] = field(default_factory=dict)   # map name, factions, teams
+    allies: list[str] = field(default_factory=list)
+    opponents: list[str] = field(default_factory=list)
+
+    def time_unit(self) -> str:
+        return self.world.get("time_unit", "seconds")
diff --git a/retale/core/schema.py b/whitelee/core/schema.py
similarity index 96%
rename from retale/core/schema.py
rename to whitelee/core/schema.py
index 89ea6c1..aba55bf 100644
--- a/retale/core/schema.py
+++ b/whitelee/core/schema.py
@@ -1,8 +1,8 @@
-"""ReTale core schema.
+"""WhiteLee core schema.
 
 Every game adapter must emit a stream of NarrativeEvent objects plus a
 MatchContext. The narrative engine only ever sees these two types, which
-is what makes ReTale game-agnostic: adding a new game means writing one
+is what makes WhiteLee game-agnostic: adding a new game means writing one
 adapter, never touching the narrative layer.
 """
 
diff --git a/whitelee/narrative/__init__.py b/whitelee/narrative/__init__.py
new file mode 100644
index 0000000..953b6f6
--- /dev/null
+++ b/whitelee/narrative/__init__.py
@@ -0,0 +1,477 @@
+"""Styler: chapter plan -> prose, in a configurable literary style.
+
+Providers are pluggable via env vars (no SDK dependencies, plain HTTPS):
+
+  WHITELEE_PROVIDER=anthropic   (default)  needs ANTHROPIC_API_KEY
+  WHITELEE_PROVIDER=openai                 needs OPENAI_API_KEY
+  WHITELEE_PROVIDER=openai_compatible      needs WHITELEE_BASE_URL + WHITELEE_API_KEY
+                                         (works with Ollama, vLLM, DeepSeek...)
+
+Style profiles are YAML files in styles/. A profile controls voice,
+diction, pacing and language; users can also point --style at their own
+YAML, or supply --style-sample <file> with their own writing so the
+model imitates their personal voice.
+"""
+
+from __future__ import annotations
+
+import json
+import os
+import re
+import sys
+import time
+from hashlib import sha256
+from dataclasses import dataclass
+from pathlib import Path
+from typing import Any
+
+import requests
+import yaml
+
+from whitelee.narrative.planner import Chapter, StoryPlan
+
+STYLES_DIR = Path(__file__).resolve().parent.parent.parent / "styles"
+
+
+@dataclass
+class StyleProfile:
+    name: str
+    language: str = "en"
+    voice: str = "third_person_limited"   # or first_person
+    prompt: str = ""                       # free-form style instructions
+    sample: str = ""                       # optional writing sample to imitate
+    words_per_chapter: int = 600
+    title_format: str = ""
+    naming: str = ""
+
+    @classmethod
+    def load(cls, name_or_path: str, sample_path: str | None = None) -> "StyleProfile":
+        p = Path(name_or_path)
+        if not p.exists():
+            p = STYLES_DIR / f"{name_or_path}.yaml"
+        if not p.exists():
+            raise FileNotFoundError(
+                f"Style '{name_or_path}' not found. Available: "
+                + ", ".join(sorted(f.stem for f in STYLES_DIR.glob("*.yaml"))))
+        data = yaml.safe_load(p.read_text(encoding="utf-8"))
+        sample = ""
+        if sample_path:
+            sample = Path(sample_path).read_text(encoding="utf-8")[:6000]
+        return cls(name=data.get("name", p.stem),
+                   language=data.get("language", "en"),
+                   voice=data.get("voice", "third_person_limited"),
+                   prompt=data.get("prompt", ""),
+                   sample=sample,
+                   words_per_chapter=int(data.get("words_per_chapter", 600)),
+                   title_format=data.get("title_format", "") or "",
+                   naming=data.get("naming", "") or "")
+
+
+@dataclass
+class Completion:
+    text: str
+    finish_reason: str = "stop"
+
+
+@dataclass
+class HTTPFailure(Exception):
+    provider_label: str
+    status_code: int
+    body_excerpt: str
+    headers: dict[str, str]
+
+    def as_runtime_error(self) -> RuntimeError:
+        return RuntimeError(f"{self.provider_label} HTTP {self.status_code}: {self.body_excerpt}")
+
+
+# ---------------------------------------------------------------------------
+# LLM providers
+# ---------------------------------------------------------------------------
+
+class LLMClient:
+    def __init__(self, model_override: str | None = None, sleep_fn=None):
+        self.provider = os.environ.get("WHITELEE_PROVIDER", "anthropic")
+        self.model = model_override or os.environ.get("WHITELEE_MODEL", "")
+        self._sleep = sleep_fn or time.sleep
+
+    def complete(self, system: str, user: str, max_tokens: int = 2000) -> Completion:
+        default_waits = [5.0, 15.0, 45.0]
+        for attempt in range(4):
+            try:
+                if self.provider == "anthropic":
+                    return self._anthropic(system, user, max_tokens)
+                return self._openai_compatible(system, user, max_tokens)
+            except HTTPFailure as error:
+                is_transient = error.status_code == 429 or error.status_code >= 500
+                if not is_transient or attempt == 3:
+                    raise error.as_runtime_error()
+                wait_seconds = self._retry_wait_seconds(error, default_waits[attempt])
+                print(
+                    f"[whitelee] retry {attempt + 1}/3 after HTTP {error.status_code}; waiting {wait_seconds}s",
+                    file=sys.stderr,
+                )
+                self._sleep(wait_seconds)
+        raise RuntimeError("unreachable")
+
+    def _anthropic(self, system: str, user: str, max_tokens: int) -> Completion:
+        key = os.environ.get("ANTHROPIC_API_KEY")
+        if not key:
+            raise EnvironmentError("Set ANTHROPIC_API_KEY (or switch WHITELEE_PROVIDER).")
+        resp = requests.post(
+            "https://api.anthropic.com/v1/messages",
+            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
+                     "content-type": "application/json"},
+            json={"model": self.model or "claude-sonnet-4-5",
+                  "max_tokens": max_tokens,
+                  "system": system,
+                  "messages": [{"role": "user", "content": user}]},
+            timeout=120)
+        body = resp.text[:500]
+        if not resp.ok:
+            raise HTTPFailure(
+                provider_label="Anthropic",
+                status_code=resp.status_code,
+                body_excerpt=body,
+                headers=dict(getattr(resp, "headers", {}) or {}),
+            )
+        payload = resp.json()
+        finish_reason = "length" if payload.get("stop_reason") == "max_tokens" else "stop"
+        return Completion(
+            text="".join(block.get("text", "") for block in payload.get("content", [])),
+            finish_reason=finish_reason,
+        )
+
+    def _openai_compatible(self, system: str, user: str, max_tokens: int) -> Completion:
+        if self.provider == "openai":
+            base = "https://api.openai.com/v1"
+            key = os.environ.get("OPENAI_API_KEY", "")
+            model = self.model or "gpt-4o"
+        else:
+            base = os.environ.get("WHITELEE_BASE_URL", "http://localhost:11434/v1")
+            key = os.environ.get("WHITELEE_API_KEY", "ollama")
+            model = self.model or "llama3.1"
+        payload = {
+            "model": model,
+            "max_tokens": max_tokens,
+            "messages": [
+                {"role": "system", "content": system},
+                {"role": "user", "content": user},
+            ],
+        }
+        reasoning_effort = os.environ.get("WHITELEE_REASONING_EFFORT")
+        if reasoning_effort:
+            payload["reasoning_effort"] = reasoning_effort
+        resp = requests.post(
+            f"{base}/chat/completions",
+            headers={"Authorization": f"Bearer {key}",
+                     "content-type": "application/json"},
+            json=payload,
+            timeout=120)
+        body = resp.text[:500]
+        if not resp.ok:
+            raise HTTPFailure(
+                provider_label="OpenAI-compatible",
+                status_code=resp.status_code,
+                body_excerpt=body,
+                headers=dict(getattr(resp, "headers", {}) or {}),
+            )
+        data = resp.json()
+        choice = data["choices"][0]
+        return Completion(
+            text=choice["message"]["content"],
+            finish_reason=choice.get("finish_reason", "stop"),
+        )
+
+    @staticmethod
+    def _retry_wait_seconds(error: HTTPFailure, default_wait: float) -> float:
+        retry_after = error.headers.get("Retry-After")
+        if retry_after:
+            try:
+                return min(float(retry_after), 90.0)
+            except ValueError:
+                pass
+        match = re.search(r"retry in (\d+(?:\.\d+)?)s", error.body_excerpt, flags=re.IGNORECASE)
+        if match:
+            return min(float(match.group(1)), 90.0)
+        return min(default_wait, 90.0)
+
+
+# ---------------------------------------------------------------------------
+# Prose generation
+# ---------------------------------------------------------------------------
+
+class Styler:
+    def __init__(self, style: StyleProfile, client: LLMClient | None = None):
+        self.style = style
+        self.client = client or LLMClient()
+
+    def write_story(
+        self,
+        plan: StoryPlan,
+        on_chapter=None,
+        codex: dict[str, Any] | None = None,
+        progress_path: Path | None = None,
+    ) -> str:
+        if codex is None:
+            codex = self.build_codex(plan)
+        fingerprint = self._fingerprint(plan, codex)
+        restored = self._load_progress(progress_path, fingerprint)
+        outline = self._outline_text(plan, codex)
+        parts = [f"# {self._title(plan)}\n"]
+        checkpoint_chapters = {str(index): text for index, text in restored.items()}
+        if restored:
+            restored_indices = sorted(restored)
+            print(
+                f"[whitelee] resuming: chapters 1-{restored_indices[-1]} restored from checkpoint",
+                file=sys.stderr,
+            )
+        for ch in plan.chapters:
+            if ch.index in restored:
+                prose = restored[ch.index]
+            else:
+                prose = self._write_chapter(plan, ch, outline)
+                if progress_path is not None:
+                    checkpoint_chapters[str(ch.index)] = prose
+                    self._write_progress(progress_path, fingerprint, checkpoint_chapters)
+            parts.append(prose.strip() + "\n")
+            if on_chapter:
+                on_chapter(ch, prose)
+        if progress_path is not None and progress_path.exists():
+            progress_path.unlink()
+        return "\n".join(parts)
+
+    def build_codex(self, plan: StoryPlan) -> dict[str, Any]:
+        system = (
+            "Return STRICT JSON only. No markdown fences. No explanations. "
+            "Provide a terminology codex for a serialized novel adaptation."
+        )
+        user = self._codex_request(plan)
+        for _attempt in range(2):
+            completion = self.client.complete(system, user, max_tokens=4000)
+            parsed = self._parse_codex_json(completion.text)
+            if parsed is not None:
+                return parsed
+        print(
+            "[whitelee] warning: failed to parse terminology codex JSON; continuing with an empty codex.",
+            file=sys.stderr,
+        )
+        return self._empty_codex()
+
+    # -- prompt assembly ------------------------------------------------
+    def _system_prompt(self) -> str:
+        base = (
+            "You are a novelist adapting a real recorded game session into "
+            "fiction. Hard rules:\n"
+            "1. NEVER invent outcomes: every kill, death, objective and the "
+            "final result must match the provided event data exactly.\n"
+            "2. You MAY invent interiority: thoughts, sensations, dialogue, "
+            "atmosphere - as long as they are consistent with the facts.\n"
+            "3. Write in the requested language and style. No game-UI jargon "
+            "(no 'HP', 'respawn timer', 'creep score') - translate mechanics "
+            "into fictional equivalents.\n"
+            f"4. Narrative voice: {self.style.voice}. Target about "
+            f"{self.style.words_per_chapter} words per chapter.\n"
+            f"5. Language: {self.style.language}.\n"
+        )
+        if self.style.prompt:
+            base += f"\nSTYLE DIRECTIVES:\n{self.style.prompt}\n"
+        if self.style.sample:
+            base += ("\nIMITATE THE VOICE OF THIS WRITING SAMPLE "
+                     "(rhythm, diction, sentence length - not its content):\n"
+                     f"---\n{self.style.sample}\n---\n")
+        return base
+
+    def _outline_text(self, plan: StoryPlan, codex: dict[str, Any]) -> str:
+        ctx = plan.context
+        lines = [
+            f"GAME: {ctx.game} | OUTCOME: {ctx.outcome} | "
+            f"PROTAGONIST: {ctx.protagonist.name} ({ctx.protagonist.persona})",
+            f"ALLIES: {', '.join(ctx.allies) or '-'}",
+            f"OPPONENTS: {', '.join(ctx.opponents) or '-'}",
+            f"LOGLINE: {plan.logline}",
+            "CHAPTER OUTLINE:",
+        ]
+        for ch in plan.chapters:
+            lines.append(f"  Ch{ch.index} [{ch.arc_role}] ~ {ch.title_hint}")
+        lines += self._terminology_lines(codex)
+        return "\n".join(lines)
+
+    def _write_chapter(self, plan: StoryPlan, ch: Chapter, outline: str) -> str:
+        ev_lines = [
+            f"- t={e.t:.0f}: [{e.kind.value}]"
+            + (" (PROTAGONIST)" if e.protagonist_involved else "")
+            + f" {e.summary}"
+            for e in ch.events if e.importance >= 0.3 or e.protagonist_involved
+        ][:60]
+        user = (
+            f"{outline}\n\n"
+            f"Now write CHAPTER {ch.index} of {len(plan.chapters)} "
+            f"(arc role: {ch.arc_role}).\n"
+            f"Chapter turning point: {ch.turning_point.summary if ch.turning_point else '-'}\n"
+            f"Verified events in this chapter (chronological):\n"
+            + "\n".join(ev_lines)
+            + "\n\nOutput: a chapter title line starting with '## ', then the prose. "
+              "Nothing else."
+        )
+        max_tokens = max(self.style.words_per_chapter * 8, 4000)
+        first = self.client.complete(self._system_prompt(), user, max_tokens=max_tokens)
+        best = first
+        if first.finish_reason == "length":
+            second = self.client.complete(
+                self._system_prompt(), user, max_tokens=max_tokens * 2
+            )
+            if second.finish_reason != "length":
+                best = second
+            elif len(second.text) > len(first.text):
+                best = second
+        return self._sanitize_chapter(best.text, ch.index)
+
+    def _sanitize_chapter(self, raw: str, index: int) -> str:
+        lines = [line for line in raw.splitlines() if not line.strip().startswith("```")]
+        title_index = next(
+            (line_index for line_index, line in enumerate(lines) if line.lstrip().startswith("## ")),
+            None,
+        )
+        if title_index is None:
+            body = "\n".join(lines).strip("\n")
+            if body:
+                return f"{self._title_line(index, '')}\n\n{body}"
+            return self._title_line(index, "")
+
+        kept_lines = lines[title_index:]
+        header = kept_lines[0].lstrip()
+        title = header[3:].strip() if header.startswith("## ") else header.lstrip("#").strip()
+        kept_lines[0] = self._title_line(index, title)
+        return "\n".join(kept_lines).strip()
+
+    def _title_line(self, index: int, title: str) -> str:
+        cleaned = self._strip_title_prefix(title).strip()
+        if self.style.title_format:
+            rendered = self.style.title_format.format(n=index, title=cleaned).strip()
+            return f"## {rendered}"
+        if cleaned:
+            return f"## {cleaned}"
+        return f"## 第{index}章"
+
+    @staticmethod
+    def _parse_codex_json(raw: str) -> dict[str, Any] | None:
+        cleaned = "\n".join(
+            line for line in raw.splitlines() if not line.strip().startswith("```")
+        ).strip()
+        if not cleaned:
+            return None
+        try:
+            data = json.loads(cleaned)
+        except json.JSONDecodeError:
+            return None
+        if not isinstance(data, dict):
+            return None
+        empty = Styler._empty_codex()
+        for key in empty:
+            value = data.get(key, {})
+            empty[key] = value if isinstance(value, dict) else empty[key]
+        protagonist_intro = data.get("protagonist_intro", "")
+        empty["protagonist_intro"] = protagonist_intro if isinstance(protagonist_intro, str) else ""
+        return empty
+
+    def _codex_request(self, plan: StoryPlan) -> str:
+        ctx = plan.context
+        return (
+            "Create a strict terminology codex JSON for this story.\n"
+            f"Language: {self.style.language}\n"
+            f"Naming conventions:\n{self.style.naming or '-'}\n"
+            f"Protagonist handle: {ctx.protagonist.name}\n"
+            f"Protagonist persona: {ctx.protagonist.persona}\n"
+            f"Allies: {', '.join(ctx.allies) or '-'}\n"
+            f"Opponents: {', '.join(ctx.opponents) or '-'}\n"
+            "Return exactly this schema:\n"
+            '{"heroes": {"<canonical name>": "<name to use in prose>"}, '
+            '"protagonist_intro": "<exact introduction phrase>", '
+            '"skills": {"<mechanic>": "<fixed literary name>"}, '
+            '"factions": {"Radiant": "...", "Dire": "..."}}'
+        )
+
+    def _terminology_lines(self, codex: dict[str, Any]) -> list[str]:
+        lines = [
+            "TERMINOLOGY:",
+            "Use EXACTLY these names in every chapter. Never invent alternative names for the same entity.",
+        ]
+        if codex.get("protagonist_intro"):
+            lines.append(f"protagonist_intro: {codex['protagonist_intro']}")
+        for section in ("heroes", "skills", "factions"):
+            entries = codex.get(section, {})
+            for canonical, preferred in entries.items():
+                lines.append(f"{section}.{canonical} = {preferred}")
+        return lines
+
+    @staticmethod
+    def _strip_title_prefix(title: str) -> str:
+        return re.sub(
+            r"^(?:第[一二三四五六七八九十百千\d]+[章节回卷篇部][ :：.-]?|Chapter \d+[:. ]?)\s*",
+            "",
+            title,
+            flags=re.IGNORECASE,
+        )
+
+    @staticmethod
+    def _empty_codex() -> dict[str, Any]:
+        return {"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}}
+
+    def _fingerprint(self, plan: StoryPlan, codex: dict[str, Any]) -> str:
+        payload = {
+            "match_id": plan.context.world.get("match_id"),
+            "style": self.style.name,
+            "model": getattr(self.client, "model", ""),
+            "codex": codex,
+        }
+        return sha256(
+            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
+        ).hexdigest()
+
+    @staticmethod
+    def _load_progress(progress_path: Path | None, fingerprint: str) -> dict[int, str]:
+        if progress_path is None or not progress_path.exists():
+            return {}
+        try:
+            payload = json.loads(progress_path.read_text(encoding="utf-8"))
+        except (OSError, json.JSONDecodeError):
+            return {}
+        if payload.get("fingerprint") != fingerprint:
+            return {}
+        chapters = payload.get("chapters", {})
+        if not isinstance(chapters, dict):
+            return {}
+        restored: dict[int, str] = {}
+        for index, text in chapters.items():
+            if str(index).isdigit() and isinstance(text, str):
+                restored[int(index)] = text
+        return restored
+
+    @staticmethod
+    def _write_progress(progress_path: Path, fingerprint: str, chapters: dict[str, str]) -> None:
+        progress_path.parent.mkdir(parents=True, exist_ok=True)
+        temp_path = progress_path.with_name(progress_path.name + ".tmp")
+        temp_path.write_text(
+            json.dumps({"fingerprint": fingerprint, "chapters": chapters}, ensure_ascii=False, indent=2),
+            encoding="utf-8",
+        )
+        temp_path.replace(progress_path)
+
+    @staticmethod
+    def _title(plan: StoryPlan) -> str:
+        return (f"{plan.context.protagonist.persona or plan.context.protagonist.name}"
+                f" - a {plan.context.game} tale")
+
+
+def export_json(plan: StoryPlan) -> str:
+    """Machine-readable dump of the plan, for debugging and other frontends."""
+    return json.dumps({
+        "logline": plan.logline,
+        "outcome": plan.context.outcome,
+        "chapters": [{
+            "index": c.index, "arc_role": c.arc_role,
+            "t": [c.t_start, c.t_end],
+            "turning_point": c.turning_point.summary if c.turning_point else None,
+            "events": [e.summary for e in c.events],
+        } for c in plan.chapters],
+    }, ensure_ascii=False, indent=2)
diff --git a/retale/narrative/planner.py b/whitelee/narrative/planner.py
similarity index 97%
rename from retale/narrative/planner.py
rename to whitelee/narrative/planner.py
index 7113ea5..abf9612 100644
--- a/retale/narrative/planner.py
+++ b/whitelee/narrative/planner.py
@@ -3,7 +3,7 @@
 Turns a flat event stream into a chapter plan with a dramatic arc.
 
 Why plan before writing: good fiction needs to know the ending to place
-foreshadowing and tension. So ReTale is retrospective by design - we
+foreshadowing and tension. So WhiteLee is retrospective by design - we
 segment the whole match into beats, find turning points (importance
 spikes and momentum reversals), then hand the LLM one chapter at a time
 WITH the global outline, so each chapter is written knowing its place
@@ -14,7 +14,7 @@ from __future__ import annotations
 
 from dataclasses import dataclass, field
 
-from retale.core.schema import EventKind, MatchContext, NarrativeEvent
+from whitelee.core.schema import EventKind, MatchContext, NarrativeEvent
 
 # Arc roles assigned to chapters by position + content
 ARC_ROLES = ["opening", "rising", "midpoint", "crisis", "climax", "resolution"]
diff --git a/retale/narrative/scout.py b/whitelee/narrative/scout.py
similarity index 99%
rename from retale/narrative/scout.py
rename to whitelee/narrative/scout.py
index 738e27f..0370249 100644
--- a/retale/narrative/scout.py
+++ b/whitelee/narrative/scout.py
@@ -5,7 +5,7 @@ from __future__ import annotations
 from dataclasses import dataclass, field
 from typing import Any
 
-from retale.core.schema import EventKind, MatchContext, NarrativeEvent
+from whitelee.core.schema import EventKind, MatchContext, NarrativeEvent
 
 WEIGHTS = {
     "nemesis_arc_full": 20,
diff --git a/retale/narrative/styler.py b/whitelee/narrative/styler.py
similarity index 94%
rename from retale/narrative/styler.py
rename to whitelee/narrative/styler.py
index f9098fa..953b6f6 100644
--- a/retale/narrative/styler.py
+++ b/whitelee/narrative/styler.py
@@ -2,9 +2,9 @@
 
 Providers are pluggable via env vars (no SDK dependencies, plain HTTPS):
 
-  RETALE_PROVIDER=anthropic   (default)  needs ANTHROPIC_API_KEY
-  RETALE_PROVIDER=openai                 needs OPENAI_API_KEY
-  RETALE_PROVIDER=openai_compatible      needs RETALE_BASE_URL + RETALE_API_KEY
+  WHITELEE_PROVIDER=anthropic   (default)  needs ANTHROPIC_API_KEY
+  WHITELEE_PROVIDER=openai                 needs OPENAI_API_KEY
+  WHITELEE_PROVIDER=openai_compatible      needs WHITELEE_BASE_URL + WHITELEE_API_KEY
                                          (works with Ollama, vLLM, DeepSeek...)
 
 Style profiles are YAML files in styles/. A profile controls voice,
@@ -28,7 +28,7 @@ from typing import Any
 import requests
 import yaml
 
-from retale.narrative.planner import Chapter, StoryPlan
+from whitelee.narrative.planner import Chapter, StoryPlan
 
 STYLES_DIR = Path(__file__).resolve().parent.parent.parent / "styles"
 
@@ -90,8 +90,8 @@ class HTTPFailure(Exception):
 
 class LLMClient:
     def __init__(self, model_override: str | None = None, sleep_fn=None):
-        self.provider = os.environ.get("RETALE_PROVIDER", "anthropic")
-        self.model = model_override or os.environ.get("RETALE_MODEL", "")
+        self.provider = os.environ.get("WHITELEE_PROVIDER", "anthropic")
+        self.model = model_override or os.environ.get("WHITELEE_MODEL", "")
         self._sleep = sleep_fn or time.sleep
 
     def complete(self, system: str, user: str, max_tokens: int = 2000) -> Completion:
@@ -107,7 +107,7 @@ class LLMClient:
                     raise error.as_runtime_error()
                 wait_seconds = self._retry_wait_seconds(error, default_waits[attempt])
                 print(
-                    f"[retale] retry {attempt + 1}/3 after HTTP {error.status_code}; waiting {wait_seconds}s",
+                    f"[whitelee] retry {attempt + 1}/3 after HTTP {error.status_code}; waiting {wait_seconds}s",
                     file=sys.stderr,
                 )
                 self._sleep(wait_seconds)
@@ -116,7 +116,7 @@ class LLMClient:
     def _anthropic(self, system: str, user: str, max_tokens: int) -> Completion:
         key = os.environ.get("ANTHROPIC_API_KEY")
         if not key:
-            raise EnvironmentError("Set ANTHROPIC_API_KEY (or switch RETALE_PROVIDER).")
+            raise EnvironmentError("Set ANTHROPIC_API_KEY (or switch WHITELEE_PROVIDER).")
         resp = requests.post(
             "https://api.anthropic.com/v1/messages",
             headers={"x-api-key": key, "anthropic-version": "2023-06-01",
@@ -147,8 +147,8 @@ class LLMClient:
             key = os.environ.get("OPENAI_API_KEY", "")
             model = self.model or "gpt-4o"
         else:
-            base = os.environ.get("RETALE_BASE_URL", "http://localhost:11434/v1")
-            key = os.environ.get("RETALE_API_KEY", "ollama")
+            base = os.environ.get("WHITELEE_BASE_URL", "http://localhost:11434/v1")
+            key = os.environ.get("WHITELEE_API_KEY", "ollama")
             model = self.model or "llama3.1"
         payload = {
             "model": model,
@@ -158,7 +158,7 @@ class LLMClient:
                 {"role": "user", "content": user},
             ],
         }
-        reasoning_effort = os.environ.get("RETALE_REASONING_EFFORT")
+        reasoning_effort = os.environ.get("WHITELEE_REASONING_EFFORT")
         if reasoning_effort:
             payload["reasoning_effort"] = reasoning_effort
         resp = requests.post(
@@ -222,7 +222,7 @@ class Styler:
         if restored:
             restored_indices = sorted(restored)
             print(
-                f"[retale] resuming: chapters 1-{restored_indices[-1]} restored from checkpoint",
+                f"[whitelee] resuming: chapters 1-{restored_indices[-1]} restored from checkpoint",
                 file=sys.stderr,
             )
         for ch in plan.chapters:
@@ -252,7 +252,7 @@ class Styler:
             if parsed is not None:
                 return parsed
         print(
-            "[retale] warning: failed to parse terminology codex JSON; continuing with an empty codex.",
+            "[whitelee] warning: failed to parse terminology codex JSON; continuing with an empty codex.",
             file=sys.stderr,
         )
         return self._empty_codex()
diff --git a/retale/output/__init__.py b/whitelee/output/__init__.py
similarity index 62%
rename from retale/output/__init__.py
rename to whitelee/output/__init__.py
index eeb8954..26eda94 100644
--- a/retale/output/__init__.py
+++ b/whitelee/output/__init__.py
@@ -1,5 +1,5 @@
 """Output helpers for story export formats."""
 
-from retale.output.epub import write_epub
+from whitelee.output.epub import write_epub
 
 __all__ = ["write_epub"]
diff --git a/retale/output/epub.py b/whitelee/output/epub.py
similarity index 97%
rename from retale/output/epub.py
rename to whitelee/output/epub.py
index ea1ab9b..973eaec 100644
--- a/retale/output/epub.py
+++ b/whitelee/output/epub.py
@@ -70,7 +70,7 @@ def _content_opf(title: str, author: str, chapters: list[tuple[str, str]]) -> st
         f"    <dc:title>{escape(title)}</dc:title>\n"
         f"    <dc:creator>{escape(author)}</dc:creator>\n"
         "    <dc:language>en</dc:language>\n"
-        "    <dc:identifier id=\"bookid\">retale-epub</dc:identifier>\n"
+        "    <dc:identifier id=\"bookid\">whitelee-epub</dc:identifier>\n"
         "  </metadata>\n"
         "  <manifest>\n"
         + "\n".join(manifest_items)
@@ -96,7 +96,7 @@ def _toc_ncx(title: str, chapters: list[tuple[str, str]]) -> str:
         '<?xml version="1.0" encoding="utf-8"?>\n'
         '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
         "  <head>\n"
-        "    <meta name=\"dtb:uid\" content=\"retale-epub\"/>\n"
+        "    <meta name=\"dtb:uid\" content=\"whitelee-epub\"/>\n"
         "    <meta name=\"dtb:depth\" content=\"1\"/>\n"
         "    <meta name=\"dtb:totalPageCount\" content=\"0\"/>\n"
         "    <meta name=\"dtb:maxPageNumber\" content=\"0\"/>\n"
diff --git a/retale_dota2_8879557061.codex.json b/whitelee_dota2_8879557061.codex.json
similarity index 100%
rename from retale_dota2_8879557061.codex.json
rename to whitelee_dota2_8879557061.codex.json
warning: in the working copy of '.conductor/tasks/T-012-rename-retale-to-whitelee-package-cli-en.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-013-release-hardening-fort-silence-windows-c.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-012-rename-retale-to-whitelee-package-cli-en.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-013-release-hardening-fort-silence-windows-c.md', CRLF will be replaced by LF the next time Git touches it
```

## Original spec

## Context

The project is being renamed from ReTale to **WhiteLee** (白+李 -> 李白, the
poet-swordsman; fitting for an engine that turns battles into literature)
before its first public release. Renames after publication break links and
installs; now is the only cheap moment. This is a mechanical but total
rename - anything the old name leaks through (imports, CLI, env vars,
output filenames) becomes permanent debt once published.

## Scope

You may touch every file in the repository. Use `git mv` for the package
directory so history is preserved. No new dependencies. No behavior changes
other than names.

## Requirements

1. **Package**: `git mv retale whitelee`; update ALL imports
   (`retale.` -> `whitelee.`) across source and tests.
2. **pyproject.toml**: project name `whitelee`; console script
   `whitelee = "whitelee.cli:main"`; keep version; keywords gain "whitelee".
3. **Environment variables**: rename the prefix `RETALE_` -> `WHITELEE_`
   everywhere (PROVIDER, MODEL, BASE_URL, API_KEY, REASONING_EFFORT).
   No backward-compat shim - the project is unpublished.
4. **CLI surface**: argparse prog name "whitelee"; all stderr log prefixes
   `[retale]` -> `[whitelee]`; default output filenames
   `retale_<game>_<id>` -> `whitelee_<game>_<id>`.
5. **Docs**: README.md / ROADMAP.md / CONTRIBUTING.md: replace the name in
   titles, commands, and paths only (a full README rewrite happens
   separately - do NOT restructure content).
6. **.gitignore**: update `retale_*.md` pattern to `whitelee_*.md`.
7. Repository-wide check: after the rename,
   `git grep -i retale` must return ZERO hits outside `.conductor/`
   (task/report history is archival and must NOT be rewritten).

## Acceptance criteria

- [ ] `pip install -e .` then `whitelee --help` works; `retale` command no
      longer exists.
- [ ] `python -m pytest tests/ -q` passes; `ruff check whitelee/` clean.
- [ ] `git grep -il retale -- ':!.conductor'` output is empty; report this
      command's output verbatim in the notes.
- [ ] `git log --follow whitelee/cli.py` shows pre-rename history
      (confirm in notes).
