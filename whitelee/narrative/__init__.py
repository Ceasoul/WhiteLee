"""Styler: chapter plan -> prose, in a configurable literary style.

Providers are pluggable via env vars (no SDK dependencies, plain HTTPS):

  WHITELEE_PROVIDER=anthropic   (default)  needs ANTHROPIC_API_KEY
  WHITELEE_PROVIDER=openai                 needs OPENAI_API_KEY
  WHITELEE_PROVIDER=openai_compatible      needs WHITELEE_BASE_URL + WHITELEE_API_KEY
                                         (works with Ollama, vLLM, DeepSeek...)

Style profiles are YAML files in styles/. A profile controls voice,
diction, pacing and language; users can also point --style at their own
YAML, or supply --style-sample <file> with their own writing so the
model imitates their personal voice.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from hashlib import sha256
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import yaml

from whitelee.narrative.planner import Chapter, StoryPlan

STYLES_DIR = Path(__file__).resolve().parent.parent.parent / "styles"


@dataclass
class StyleProfile:
    name: str
    language: str = "en"
    voice: str = "third_person_limited"   # or first_person
    prompt: str = ""                       # free-form style instructions
    sample: str = ""                       # optional writing sample to imitate
    words_per_chapter: int = 600
    title_format: str = ""
    naming: str = ""

    @classmethod
    def load(cls, name_or_path: str, sample_path: str | None = None) -> "StyleProfile":
        p = Path(name_or_path)
        if not p.exists():
            p = STYLES_DIR / f"{name_or_path}.yaml"
        if not p.exists():
            raise FileNotFoundError(
                f"Style '{name_or_path}' not found. Available: "
                + ", ".join(sorted(f.stem for f in STYLES_DIR.glob("*.yaml"))))
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        sample = ""
        if sample_path:
            sample = Path(sample_path).read_text(encoding="utf-8")[:6000]
        return cls(name=data.get("name", p.stem),
                   language=data.get("language", "en"),
                   voice=data.get("voice", "third_person_limited"),
                   prompt=data.get("prompt", ""),
                   sample=sample,
                   words_per_chapter=int(data.get("words_per_chapter", 600)),
                   title_format=data.get("title_format", "") or "",
                   naming=data.get("naming", "") or "")


@dataclass
class Completion:
    text: str
    finish_reason: str = "stop"


@dataclass
class HTTPFailure(Exception):
    provider_label: str
    status_code: int
    body_excerpt: str
    headers: dict[str, str]

    def as_runtime_error(self) -> RuntimeError:
        return RuntimeError(f"{self.provider_label} HTTP {self.status_code}: {self.body_excerpt}")


# ---------------------------------------------------------------------------
# LLM providers
# ---------------------------------------------------------------------------

class LLMClient:
    def __init__(self, model_override: str | None = None, sleep_fn=None):
        self.provider = os.environ.get("WHITELEE_PROVIDER", "anthropic")
        self.model = model_override or os.environ.get("WHITELEE_MODEL", "")
        self._sleep = sleep_fn or time.sleep

    def complete(self, system: str, user: str, max_tokens: int = 2000) -> Completion:
        default_waits = [5.0, 15.0, 45.0]
        for attempt in range(4):
            try:
                if self.provider == "anthropic":
                    return self._anthropic(system, user, max_tokens)
                return self._openai_compatible(system, user, max_tokens)
            except HTTPFailure as error:
                is_transient = error.status_code == 429 or error.status_code >= 500
                if not is_transient or attempt == 3:
                    raise error.as_runtime_error()
                wait_seconds = self._retry_wait_seconds(error, default_waits[attempt])
                print(
                    f"[whitelee] retry {attempt + 1}/3 after HTTP {error.status_code}; waiting {wait_seconds}s",
                    file=sys.stderr,
                )
                self._sleep(wait_seconds)
        raise RuntimeError("unreachable")

    def _anthropic(self, system: str, user: str, max_tokens: int) -> Completion:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise EnvironmentError("Set ANTHROPIC_API_KEY (or switch WHITELEE_PROVIDER).")
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": self.model or "claude-sonnet-4-5",
                  "max_tokens": max_tokens,
                  "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=120)
        body = resp.text[:500]
        if not resp.ok:
            raise HTTPFailure(
                provider_label="Anthropic",
                status_code=resp.status_code,
                body_excerpt=body,
                headers=dict(getattr(resp, "headers", {}) or {}),
            )
        payload = resp.json()
        finish_reason = "length" if payload.get("stop_reason") == "max_tokens" else "stop"
        return Completion(
            text="".join(block.get("text", "") for block in payload.get("content", [])),
            finish_reason=finish_reason,
        )

    def _openai_compatible(self, system: str, user: str, max_tokens: int) -> Completion:
        if self.provider == "openai":
            base = "https://api.openai.com/v1"
            key = os.environ.get("OPENAI_API_KEY", "")
            model = self.model or "gpt-4o"
        else:
            base = os.environ.get("WHITELEE_BASE_URL", "http://localhost:11434/v1")
            key = os.environ.get("WHITELEE_API_KEY", "ollama")
            model = self.model or "llama3.1"
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        reasoning_effort = os.environ.get("WHITELEE_REASONING_EFFORT")
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        resp = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "content-type": "application/json"},
            json=payload,
            timeout=120)
        body = resp.text[:500]
        if not resp.ok:
            raise HTTPFailure(
                provider_label="OpenAI-compatible",
                status_code=resp.status_code,
                body_excerpt=body,
                headers=dict(getattr(resp, "headers", {}) or {}),
            )
        data = resp.json()
        choice = data["choices"][0]
        return Completion(
            text=choice["message"]["content"],
            finish_reason=choice.get("finish_reason", "stop"),
        )

    @staticmethod
    def _retry_wait_seconds(error: HTTPFailure, default_wait: float) -> float:
        retry_after = error.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 90.0)
            except ValueError:
                pass
        match = re.search(r"retry in (\d+(?:\.\d+)?)s", error.body_excerpt, flags=re.IGNORECASE)
        if match:
            return min(float(match.group(1)), 90.0)
        return min(default_wait, 90.0)


# ---------------------------------------------------------------------------
# Prose generation
# ---------------------------------------------------------------------------

class Styler:
    def __init__(self, style: StyleProfile, client: LLMClient | None = None):
        self.style = style
        self.client = client or LLMClient()

    def write_story(
        self,
        plan: StoryPlan,
        on_chapter=None,
        codex: dict[str, Any] | None = None,
        progress_path: Path | None = None,
    ) -> str:
        if codex is None:
            codex = self.build_codex(plan)
        fingerprint = self._fingerprint(plan, codex)
        restored = self._load_progress(progress_path, fingerprint)
        outline = self._outline_text(plan, codex)
        parts = [f"# {self._title(plan)}\n"]
        checkpoint_chapters = {str(index): text for index, text in restored.items()}
        if restored:
            restored_indices = sorted(restored)
            print(
                f"[whitelee] resuming: chapters 1-{restored_indices[-1]} restored from checkpoint",
                file=sys.stderr,
            )
        for ch in plan.chapters:
            if ch.index in restored:
                prose = restored[ch.index]
            else:
                prose = self._write_chapter(plan, ch, outline)
                if progress_path is not None:
                    checkpoint_chapters[str(ch.index)] = prose
                    self._write_progress(progress_path, fingerprint, checkpoint_chapters)
            parts.append(prose.strip() + "\n")
            if on_chapter:
                on_chapter(ch, prose)
        if progress_path is not None and progress_path.exists():
            progress_path.unlink()
        return "\n".join(parts)

    def build_codex(self, plan: StoryPlan) -> dict[str, Any]:
        system = (
            "Return STRICT JSON only. No markdown fences. No explanations. "
            "Provide a terminology codex for a serialized novel adaptation."
        )
        user = self._codex_request(plan)
        for _attempt in range(2):
            completion = self.client.complete(system, user, max_tokens=4000)
            parsed = self._parse_codex_json(completion.text)
            if parsed is not None:
                return parsed
        print(
            "[whitelee] warning: failed to parse terminology codex JSON; continuing with an empty codex.",
            file=sys.stderr,
        )
        return self._empty_codex()

    # -- prompt assembly ------------------------------------------------
    def _system_prompt(self) -> str:
        base = (
            "You are a novelist adapting a real recorded game session into "
            "fiction. Hard rules:\n"
            "1. NEVER invent outcomes: every kill, death, objective and the "
            "final result must match the provided event data exactly.\n"
            "2. You MAY invent interiority: thoughts, sensations, dialogue, "
            "atmosphere - as long as they are consistent with the facts.\n"
            "3. Write in the requested language and style. No game-UI jargon "
            "(no 'HP', 'respawn timer', 'creep score') - translate mechanics "
            "into fictional equivalents.\n"
            f"4. Narrative voice: {self.style.voice}. Target about "
            f"{self.style.words_per_chapter} words per chapter.\n"
            f"5. Language: {self.style.language}.\n"
        )
        if self.style.prompt:
            base += f"\nSTYLE DIRECTIVES:\n{self.style.prompt}\n"
        if self.style.sample:
            base += ("\nIMITATE THE VOICE OF THIS WRITING SAMPLE "
                     "(rhythm, diction, sentence length - not its content):\n"
                     f"---\n{self.style.sample}\n---\n")
        return base

    def _outline_text(self, plan: StoryPlan, codex: dict[str, Any]) -> str:
        ctx = plan.context
        lines = [
            f"GAME: {ctx.game} | OUTCOME: {ctx.outcome} | "
            f"PROTAGONIST: {ctx.protagonist.name} ({ctx.protagonist.persona})",
            f"ALLIES: {', '.join(ctx.allies) or '-'}",
            f"OPPONENTS: {', '.join(ctx.opponents) or '-'}",
            f"LOGLINE: {plan.logline}",
            "CHAPTER OUTLINE:",
        ]
        for ch in plan.chapters:
            lines.append(f"  Ch{ch.index} [{ch.arc_role}] ~ {ch.title_hint}")
        lines += self._terminology_lines(codex)
        return "\n".join(lines)

    def _write_chapter(self, plan: StoryPlan, ch: Chapter, outline: str) -> str:
        ev_lines = [
            f"- t={e.t:.0f}: [{e.kind.value}]"
            + (" (PROTAGONIST)" if e.protagonist_involved else "")
            + f" {e.summary}"
            for e in ch.events if e.importance >= 0.3 or e.protagonist_involved
        ][:60]
        user = (
            f"{outline}\n\n"
            f"Now write CHAPTER {ch.index} of {len(plan.chapters)} "
            f"(arc role: {ch.arc_role}).\n"
            f"Chapter turning point: {ch.turning_point.summary if ch.turning_point else '-'}\n"
            f"Verified events in this chapter (chronological):\n"
            + "\n".join(ev_lines)
            + "\n\nOutput: a chapter title line starting with '## ', then the prose. "
              "Nothing else."
        )
        max_tokens = max(self.style.words_per_chapter * 8, 4000)
        first = self.client.complete(self._system_prompt(), user, max_tokens=max_tokens)
        best = first
        if first.finish_reason == "length":
            second = self.client.complete(
                self._system_prompt(), user, max_tokens=max_tokens * 2
            )
            if second.finish_reason != "length":
                best = second
            elif len(second.text) > len(first.text):
                best = second
        return self._sanitize_chapter(best.text, ch.index)

    def _sanitize_chapter(self, raw: str, index: int) -> str:
        lines = [line for line in raw.splitlines() if not line.strip().startswith("```")]
        title_index = next(
            (line_index for line_index, line in enumerate(lines) if line.lstrip().startswith("## ")),
            None,
        )
        if title_index is None:
            body = "\n".join(lines).strip("\n")
            if body:
                return f"{self._title_line(index, '')}\n\n{body}"
            return self._title_line(index, "")

        kept_lines = lines[title_index:]
        header = kept_lines[0].lstrip()
        title = header[3:].strip() if header.startswith("## ") else header.lstrip("#").strip()
        kept_lines[0] = self._title_line(index, title)
        return "\n".join(kept_lines).strip()

    def _title_line(self, index: int, title: str) -> str:
        cleaned = self._strip_title_prefix(title).strip()
        if self.style.title_format:
            rendered = self.style.title_format.format(n=index, title=cleaned).strip()
            return f"## {rendered}"
        if cleaned:
            return f"## {cleaned}"
        return f"## 第{index}章"

    @staticmethod
    def _parse_codex_json(raw: str) -> dict[str, Any] | None:
        cleaned = "\n".join(
            line for line in raw.splitlines() if not line.strip().startswith("```")
        ).strip()
        if not cleaned:
            return None
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        empty = Styler._empty_codex()
        for key in empty:
            value = data.get(key, {})
            empty[key] = value if isinstance(value, dict) else empty[key]
        protagonist_intro = data.get("protagonist_intro", "")
        empty["protagonist_intro"] = protagonist_intro if isinstance(protagonist_intro, str) else ""
        return empty

    def _codex_request(self, plan: StoryPlan) -> str:
        ctx = plan.context
        return (
            "Create a strict terminology codex JSON for this story.\n"
            f"Language: {self.style.language}\n"
            f"Naming conventions:\n{self.style.naming or '-'}\n"
            f"Protagonist handle: {ctx.protagonist.name}\n"
            f"Protagonist persona: {ctx.protagonist.persona}\n"
            f"Allies: {', '.join(ctx.allies) or '-'}\n"
            f"Opponents: {', '.join(ctx.opponents) or '-'}\n"
            "Return exactly this schema:\n"
            '{"heroes": {"<canonical name>": "<name to use in prose>"}, '
            '"protagonist_intro": "<exact introduction phrase>", '
            '"skills": {"<mechanic>": "<fixed literary name>"}, '
            '"factions": {"Radiant": "...", "Dire": "..."}}'
        )

    def _terminology_lines(self, codex: dict[str, Any]) -> list[str]:
        lines = [
            "TERMINOLOGY:",
            "Use EXACTLY these names in every chapter. Never invent alternative names for the same entity.",
        ]
        if codex.get("protagonist_intro"):
            lines.append(f"protagonist_intro: {codex['protagonist_intro']}")
        for section in ("heroes", "skills", "factions"):
            entries = codex.get(section, {})
            for canonical, preferred in entries.items():
                lines.append(f"{section}.{canonical} = {preferred}")
        return lines

    @staticmethod
    def _strip_title_prefix(title: str) -> str:
        return re.sub(
            r"^(?:第[一二三四五六七八九十百千\d]+[章节回卷篇部][ :：.-]?|Chapter \d+[:. ]?)\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _empty_codex() -> dict[str, Any]:
        return {"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}}

    def _fingerprint(self, plan: StoryPlan, codex: dict[str, Any]) -> str:
        payload = {
            "match_id": plan.context.world.get("match_id"),
            "style": self.style.name,
            "model": getattr(self.client, "model", ""),
            "codex": codex,
        }
        return sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _load_progress(progress_path: Path | None, fingerprint: str) -> dict[int, str]:
        if progress_path is None or not progress_path.exists():
            return {}
        try:
            payload = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if payload.get("fingerprint") != fingerprint:
            return {}
        chapters = payload.get("chapters", {})
        if not isinstance(chapters, dict):
            return {}
        restored: dict[int, str] = {}
        for index, text in chapters.items():
            if str(index).isdigit() and isinstance(text, str):
                restored[int(index)] = text
        return restored

    @staticmethod
    def _write_progress(progress_path: Path, fingerprint: str, chapters: dict[str, str]) -> None:
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = progress_path.with_name(progress_path.name + ".tmp")
        temp_path.write_text(
            json.dumps({"fingerprint": fingerprint, "chapters": chapters}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(progress_path)

    @staticmethod
    def _title(plan: StoryPlan) -> str:
        return (f"{plan.context.protagonist.persona or plan.context.protagonist.name}"
                f" - a {plan.context.game} tale")


def export_json(plan: StoryPlan) -> str:
    """Machine-readable dump of the plan, for debugging and other frontends."""
    return json.dumps({
        "logline": plan.logline,
        "outcome": plan.context.outcome,
        "chapters": [{
            "index": c.index, "arc_role": c.arc_role,
            "t": [c.t_start, c.t_end],
            "turning_point": c.turning_point.summary if c.turning_point else None,
            "events": [e.summary for e in c.events],
        } for c in plan.chapters],
    }, ensure_ascii=False, indent=2)
