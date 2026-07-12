# Report T-006: Styler hardening: reasoning-model budgets, output sanitizer, error context, --model flag

generated: 2026-07-12 02:47 UTC

## Implementer notes

recollect with v0.1.3 (UTF-8 fix); no code changes

## Test output

```
......................                                                   [100%]
22 passed in 1.01s
```

## Diff vs 357997f0db080795d16a55294b16c192c3367aee

```diff
...006-styler-hardening-reasoning-model-budgets.md |  84 +++++++++
 retale/cli.py                                      |   9 +-
 retale/narrative/styler.py                         |  89 ++++++++--
 tests/test_pipeline.py                             |   4 +-
 tests/test_styler_hardening.py                     | 188 +++++++++++++++++++++
 命令.txt                                           |   6 +
 6 files changed, 362 insertions(+), 18 deletions(-)
warning: in the working copy of '.conductor/tasks/T-006-styler-hardening-reasoning-model-budgets.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '命令.txt', CRLF will be replaced by LF the next time Git touches it


diff --git a/.conductor/tasks/T-006-styler-hardening-reasoning-model-budgets.md b/.conductor/tasks/T-006-styler-hardening-reasoning-model-budgets.md
new file mode 100644
index 0000000..e7fc82e
--- /dev/null
+++ b/.conductor/tasks/T-006-styler-hardening-reasoning-model-budgets.md
@@ -0,0 +1,84 @@
+---
+id: T-006
+title: 'Styler hardening: reasoning-model budgets, output sanitizer, error context,
+  --model flag'
+status: review
+priority: 1
+depends: []
+base: 357997f0db080795d16a55294b16c192c3367aee
+---
+
+## Context
+
+First real story generation (match 8879557061, gemini-3.5-flash via the
+openai_compatible provider) exposed three styler-layer defects:
+
+1. Chapters truncated mid-sentence: reasoning models spend "thinking" tokens
+   from the same max_tokens budget; our `words_per_chapter * 4` allowance
+   starves the visible prose. CJK also runs ~1-2 tokens per character.
+2. One chapter emitted raw English meta-commentary (the model's planning
+   notes) instead of prose. The "output '## title' then prose, nothing else"
+   contract must be ENFORCED in code, not trusted.
+3. HTTP errors surface only the status code; the response body (which names
+   the real cause, e.g. unknown model) is discarded. Also, switching models
+   requires editing env vars; a --model CLI flag is needed.
+
+## Scope
+
+You may touch: `retale/narrative/styler.py`, `retale/cli.py`, and add
+`tests/test_styler_hardening.py`. Nothing else. No new dependencies.
+Tests stay offline (mock clients only; never construct a real HTTP call).
+
+## Requirements
+
+1. **Token budget.** In `_write_chapter`, set
+   `max_tokens = max(words_per_chapter * 8, 4000)`.
+
+2. **Reasoning effort passthrough.** In `_openai_compatible`, if env
+   `RETALE_REASONING_EFFORT` is set (e.g. "low"), include
+   `"reasoning_effort": <value>` in the request JSON; omit the field
+   entirely when unset.
+
+3. **Structured completion result.** Change `LLMClient.complete` to return
+   a small dataclass `Completion(text: str, finish_reason: str)`.
+   - openai_compatible/openai: finish_reason from
+     `choices[0].finish_reason` (default "stop" if absent).
+   - anthropic: map `stop_reason` ("max_tokens" -> "length", else "stop").
+   Update `Styler` accordingly.
+
+4. **Truncation retry.** In `_write_chapter`, if `finish_reason == "length"`,
+   retry ONCE with `max_tokens * 2`; use whichever attempt has
+   finish_reason != "length", else the longer text.
+
+5. **Output sanitizer.** Add `_sanitize_chapter(raw: str, index: int) -> str`
+   applied to every chapter before it is returned:
+   - strip markdown code fences (``` lines);
+   - discard everything BEFORE the first line starting with `## `;
+   - if NO line starts with `## `, prepend `## 第{index}章` as the title and
+     keep the body;
+   - normalize the title line to exactly one `## ` prefix.
+
+6. **HTTP error context.** In both provider paths, on a non-2xx response
+   raise a RuntimeError whose message includes the status code AND the
+   first 500 characters of the response body. (Call `resp.raise_for_status()`
+   only after capturing the body, or replace it with an explicit check.)
+
+7. **--model flag.** `retale ... --model NAME` overrides `RETALE_MODEL`.
+   Plumb it: CLI arg -> `LLMClient(model_override=...)` (constructor param,
+   default None; env fallback preserved).
+
+## Acceptance criteria
+
+- [ ] Tests (all with mock clients / mock responses):
+      (a) sanitizer drops leading meta text before `## `;
+      (b) sanitizer synthesizes `## 第3章` when no header exists;
+      (c) a mock client returning finish_reason "length" then "stop" causes
+          exactly 2 calls, second with doubled max_tokens, final text from
+          the second call;
+      (d) mock 404 response with a JSON body -> raised error message
+          contains both "404" and a distinctive body substring;
+      (e) `--model` reaches the client (assert on a captured LLMClient or
+          via monkeypatched constructor).
+- [ ] Existing tests still pass (MockLLM in test_pipeline.py must be
+      updated to the new Completion return type).
+- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
diff --git a/retale/cli.py b/retale/cli.py
index dc369f5..6be75d6 100644
--- a/retale/cli.py
+++ b/retale/cli.py
@@ -16,7 +16,7 @@ from typing import Callable
 
 from retale.adapters.base import ExtractionResult, GameAdapter
 from retale.narrative.planner import Chapter, Planner
-from retale.narrative.styler import StyleProfile, Styler, export_json
+from retale.narrative.styler import LLMClient, StyleProfile, Styler, export_json
 from retale.output import write_epub
 
 
@@ -44,6 +44,8 @@ def main(argv: list[str] | None = None) -> int:
                    help="style profile name or path to a YAML")
     p.add_argument("--style-sample", default=None,
                    help="path to a text file whose voice the story imitates")
+    p.add_argument("--model", default=None,
+                   help="override the configured LLM model name")
     p.add_argument("--chapters", type=int, default=5,
                    help="target chapter count (auto-adjusted by density)")
     p.add_argument("-o", "--output", default=None, help="output .md path")
@@ -70,7 +72,10 @@ def main(argv: list[str] | None = None) -> int:
         return 0
 
     style = StyleProfile.load(args.style, sample_path=args.style_sample)
-    styler = Styler(style)
+    if args.model:
+        styler = Styler(style, client=LLMClient(model_override=args.model))
+    else:
+        styler = Styler(style)
 
     def progress(ch: Chapter, _prose: str) -> None:
         print(f"[retale] chapter {ch.index}/{len(plan.chapters)} written "
diff --git a/retale/narrative/styler.py b/retale/narrative/styler.py
index f9dd334..cbfa810 100644
--- a/retale/narrative/styler.py
+++ b/retale/narrative/styler.py
@@ -58,21 +58,27 @@ class StyleProfile:
                    words_per_chapter=int(data.get("words_per_chapter", 600)))
 
 
+@dataclass
+class Completion:
+    text: str
+    finish_reason: str = "stop"
+
+
 # ---------------------------------------------------------------------------
 # LLM providers
 # ---------------------------------------------------------------------------
 
 class LLMClient:
-    def __init__(self):
+    def __init__(self, model_override: str | None = None):
         self.provider = os.environ.get("RETALE_PROVIDER", "anthropic")
-        self.model = os.environ.get("RETALE_MODEL", "")
+        self.model = model_override or os.environ.get("RETALE_MODEL", "")
 
-    def complete(self, system: str, user: str, max_tokens: int = 2000) -> str:
+    def complete(self, system: str, user: str, max_tokens: int = 2000) -> Completion:
         if self.provider == "anthropic":
             return self._anthropic(system, user, max_tokens)
         return self._openai_compatible(system, user, max_tokens)
 
-    def _anthropic(self, system: str, user: str, max_tokens: int) -> str:
+    def _anthropic(self, system: str, user: str, max_tokens: int) -> Completion:
         key = os.environ.get("ANTHROPIC_API_KEY")
         if not key:
             raise EnvironmentError("Set ANTHROPIC_API_KEY (or switch RETALE_PROVIDER).")
@@ -85,10 +91,19 @@ class LLMClient:
                   "system": system,
                   "messages": [{"role": "user", "content": user}]},
             timeout=120)
-        resp.raise_for_status()
-        return "".join(b.get("text", "") for b in resp.json().get("content", []))
+        body = resp.text[:500]
+        if not resp.ok:
+            raise RuntimeError(
+                f"Anthropic HTTP {resp.status_code}: {body}"
+            )
+        payload = resp.json()
+        finish_reason = "length" if payload.get("stop_reason") == "max_tokens" else "stop"
+        return Completion(
+            text="".join(block.get("text", "") for block in payload.get("content", [])),
+            finish_reason=finish_reason,
+        )
 
-    def _openai_compatible(self, system: str, user: str, max_tokens: int) -> str:
+    def _openai_compatible(self, system: str, user: str, max_tokens: int) -> Completion:
         if self.provider == "openai":
             base = "https://api.openai.com/v1"
             key = os.environ.get("OPENAI_API_KEY", "")
@@ -97,16 +112,34 @@ class LLMClient:
             base = os.environ.get("RETALE_BASE_URL", "http://localhost:11434/v1")
             key = os.environ.get("RETALE_API_KEY", "ollama")
             model = self.model or "llama3.1"
+        payload = {
+            "model": model,
+            "max_tokens": max_tokens,
+            "messages": [
+                {"role": "system", "content": system},
+                {"role": "user", "content": user},
+            ],
+        }
+        reasoning_effort = os.environ.get("RETALE_REASONING_EFFORT")
+        if reasoning_effort:
+            payload["reasoning_effort"] = reasoning_effort
         resp = requests.post(
             f"{base}/chat/completions",
             headers={"Authorization": f"Bearer {key}",
                      "content-type": "application/json"},
-            json={"model": model, "max_tokens": max_tokens,
-                  "messages": [{"role": "system", "content": system},
-                               {"role": "user", "content": user}]},
+            json=payload,
             timeout=120)
-        resp.raise_for_status()
-        return resp.json()["choices"][0]["message"]["content"]
+        body = resp.text[:500]
+        if not resp.ok:
+            raise RuntimeError(
+                f"OpenAI-compatible HTTP {resp.status_code}: {body}"
+            )
+        data = resp.json()
+        choice = data["choices"][0]
+        return Completion(
+            text=choice["message"]["content"],
+            finish_reason=choice.get("finish_reason", "stop"),
+        )
 
 
 # ---------------------------------------------------------------------------
@@ -183,8 +216,36 @@ class Styler:
             + "\n\nOutput: a chapter title line starting with '## ', then the prose. "
               "Nothing else."
         )
-        return self.client.complete(self._system_prompt(), user,
-                                    max_tokens=self.style.words_per_chapter * 4)
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
+    @staticmethod
+    def _sanitize_chapter(raw: str, index: int) -> str:
+        lines = [line for line in raw.splitlines() if not line.strip().startswith("```")]
+        title_index = next(
+            (line_index for line_index, line in enumerate(lines) if line.lstrip().startswith("## ")),
+            None,
+        )
+        if title_index is None:
+            body = "\n".join(line for line in lines if line.strip()).strip()
+            if body:
+                return f"## 第{index}章\n\n{body}"
+            return f"## 第{index}章"
+
+        kept_lines = lines[title_index:]
+        title = kept_lines[0].lstrip("#").strip()
+        kept_lines[0] = f"## {title}"
+        return "\n".join(kept_lines).strip()
 
     @staticmethod
     def _title(plan: StoryPlan) -> str:
diff --git a/tests/test_pipeline.py b/tests/test_pipeline.py
index 7252d86..d353552 100644
--- a/tests/test_pipeline.py
+++ b/tests/test_pipeline.py
@@ -8,7 +8,7 @@ import pytest
 from retale.adapters.dota2_opendota import Dota2OpenDotaAdapter
 from retale.core.schema import EventKind
 from retale.narrative.planner import Planner
-from retale.narrative.styler import StyleProfile, Styler, export_json
+from retale.narrative.styler import Completion, StyleProfile, Styler, export_json
 
 FIXTURE = Path(__file__).parent / "fixtures" / "dota2_match.json"
 UNPARSED_FIXTURE = Path(__file__).parent / "fixtures" / "dota2_match_unparsed.json"
@@ -194,7 +194,7 @@ class MockLLM:
     def complete(self, system, user, max_tokens=0):
         assert "NEVER invent outcomes" in system
         assert "CHAPTER" in user
-        return "## A Mock Chapter\n\nThe blade sang."
+        return Completion(text="## A Mock Chapter\n\nThe blade sang.", finish_reason="stop")
 
 
 def test_styler_assembles_story(extraction):
diff --git a/tests/test_styler_hardening.py b/tests/test_styler_hardening.py
new file mode 100644
index 0000000..51ea63a
--- /dev/null
+++ b/tests/test_styler_hardening.py
@@ -0,0 +1,188 @@
+"""Tests for styler hardening and CLI model plumbing."""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+
+import pytest
+
+from retale.cli import main
+from retale.core.schema import EventKind, MatchContext, NarrativeEvent, Protagonist
+from retale.narrative.planner import Chapter, StoryPlan
+from retale.narrative.styler import Completion, LLMClient, StyleProfile, Styler
+
+
+def _sample_plan() -> StoryPlan:
+    context = MatchContext(
+        game="dota2",
+        protagonist=Protagonist(name="Hero", persona="Juggernaut"),
+        outcome="victory",
+    )
+    event = NarrativeEvent(
+        t=1.0,
+        kind=EventKind.KILL,
+        summary="Juggernaut struck down Lion.",
+        importance=0.7,
+        protagonist_involved=True,
+    )
+    chapter = Chapter(
+        index=1,
+        title_hint="Opening",
+        arc_role="opening",
+        t_start=0.0,
+        t_end=10.0,
+        events=[event],
+        turning_point=event,
+    )
+    return StoryPlan(context=context, chapters=[chapter], logline="A compact tale.")
+
+
+def test_sanitizer_drops_meta_text_before_header():
+    sanitized = Styler._sanitize_chapter(
+        "Planning notes\nDo not show this\n## Actual Title\n\nStory text.",
+        1,
+    )
+
+    assert sanitized.startswith("## Actual Title")
+    assert "Planning notes" not in sanitized
+
+
+def test_sanitizer_synthesizes_header_when_missing():
+    sanitized = Styler._sanitize_chapter("Plain body only.", 3)
+
+    assert sanitized.startswith("## 第3章")
+    assert "Plain body only." in sanitized
+
+
+def test_write_chapter_retries_once_on_length():
+    class MockClient:
+        def __init__(self):
+            self.calls: list[int] = []
+
+        def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
+            self.calls.append(max_tokens)
+            if len(self.calls) == 1:
+                return Completion(text="## First\n\nCut off", finish_reason="length")
+            return Completion(text="## Second\n\nFull chapter.", finish_reason="stop")
+
+    style = StyleProfile(name="test", words_per_chapter=100)
+    client = MockClient()
+    styler = Styler(style, client=client)  # type: ignore[arg-type]
+
+    chapter_text = styler._write_chapter(_sample_plan(), _sample_plan().chapters[0], "Outline")
+
+    assert client.calls == [4000, 8000]
+    assert chapter_text == "## Second\n\nFull chapter."
+
+
+def test_openai_compatible_http_error_includes_body(monkeypatch):
+    class FakeResponse:
+        ok = False
+        status_code = 404
+        text = '{"error":"unknown model"}'
+
+        def json(self):
+            return {}
+
+    monkeypatch.setattr("retale.narrative.styler.requests.post", lambda *args, **kwargs: FakeResponse())
+    client = LLMClient(model_override="missing-model")
+    client.provider = "openai_compatible"
+
+    with pytest.raises(RuntimeError) as exc_info:
+        client._openai_compatible("system", "user", 4000)
+
+    message = str(exc_info.value)
+    assert "404" in message
+    assert "unknown model" in message
+
+
+def test_openai_compatible_passes_reasoning_effort(monkeypatch):
+    captured_json = {}
+
+    class FakeResponse:
+        ok = True
+        status_code = 200
+        text = '{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}'
+
+        def json(self):
+            return {
+                "choices": [
+                    {
+                        "message": {"content": "ok"},
+                        "finish_reason": "stop",
+                    }
+                ]
+            }
+
+    def fake_post(*args, **kwargs):
+        captured_json.update(kwargs["json"])
+        return FakeResponse()
+
+    monkeypatch.setenv("RETALE_REASONING_EFFORT", "low")
+    monkeypatch.setattr("retale.narrative.styler.requests.post", fake_post)
+    client = LLMClient(model_override="test-model")
+    client.provider = "openai_compatible"
+    result = client._openai_compatible("system", "user", 4000)
+
+    assert result.finish_reason == "stop"
+    assert captured_json["reasoning_effort"] == "low"
+
+
+def test_cli_model_flag_reaches_llm_client(monkeypatch, tmp_path):
+    captured: dict[str, object] = {}
+
+    class FakeAdapter:
+        def extract(self, source: str, protagonist_hint: str | None = None):
+            return type(
+                "Extraction",
+                (),
+                {
+                    "context": MatchContext(
+                        game="dota2",
+                        protagonist=Protagonist(name="Hero", persona="Juggernaut"),
+                        outcome="victory",
+                        world={"match_id": 1},
+                    ),
+                    "events": [NarrativeEvent(t=0.0, kind=EventKind.MATCH_START, summary="start")],
+                },
+            )()
+
+    @dataclass
+    class FakePlan:
+        chapters: list[Chapter]
+        logline: str
+        context: MatchContext
+
+    class FakePlanner:
+        def __init__(self, target_chapters: int = 5):
+            self.target_chapters = target_chapters
+
+        def plan(self, context: MatchContext, events: list[NarrativeEvent]) -> FakePlan:
+            chapter = Chapter(
+                index=1,
+                title_hint="Hint",
+                arc_role="opening",
+                t_start=0.0,
+                t_end=1.0,
+                events=events,
+                turning_point=events[0],
+            )
+            return FakePlan(chapters=[chapter], logline="Logline", context=context)
+
+    class FakeClient:
+        def __init__(self, model_override: str | None = None):
+            captured["model_override"] = model_override
+
+        def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
+            return Completion(text="## Title\n\nBody", finish_reason="stop")
+
+    monkeypatch.setattr("retale.cli._adapters", lambda: {"dota2": FakeAdapter})
+    monkeypatch.setattr("retale.cli.Planner", FakePlanner)
+    monkeypatch.setattr("retale.cli.StyleProfile.load", lambda *args, **kwargs: StyleProfile(name="test"))
+    monkeypatch.setattr("retale.cli.LLMClient", FakeClient)
+
+    out_path = tmp_path / "story.md"
+    exit_code = main(["dota2", "fake.json", "--model", "gemini-test", "-o", str(out_path)])
+
+    assert exit_code == 0
+    assert captured["model_override"] == "gemini-test"
diff --git a/命令.txt b/命令.txt
new file mode 100644
index 0000000..7338f8d
--- /dev/null
+++ b/命令.txt
@@ -0,0 +1,6 @@
+cd D:\ProjectDAQ\project\Retale
+$env:RETALE_PROVIDER = "openai_compatible"
+$env:RETALE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
+$env:RETALE_API_KEY = "[REDACTED]"
+$env:RETALE_MODEL = "gemini-3.5-flash"
+retale dota2 8879557061 --pov 陆地神仙 --style wuxia
\ No newline at end of file
warning: in the working copy of '.conductor/tasks/T-006-styler-hardening-reasoning-model-budgets.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '命令.txt', CRLF will be replaced by LF the next time Git touches it
```

## Original spec

## Context

First real story generation (match 8879557061, gemini-3.5-flash via the
openai_compatible provider) exposed three styler-layer defects:

1. Chapters truncated mid-sentence: reasoning models spend "thinking" tokens
   from the same max_tokens budget; our `words_per_chapter * 4` allowance
   starves the visible prose. CJK also runs ~1-2 tokens per character.
2. One chapter emitted raw English meta-commentary (the model's planning
   notes) instead of prose. The "output '## title' then prose, nothing else"
   contract must be ENFORCED in code, not trusted.
3. HTTP errors surface only the status code; the response body (which names
   the real cause, e.g. unknown model) is discarded. Also, switching models
   requires editing env vars; a --model CLI flag is needed.

## Scope

You may touch: `retale/narrative/styler.py`, `retale/cli.py`, and add
`tests/test_styler_hardening.py`. Nothing else. No new dependencies.
Tests stay offline (mock clients only; never construct a real HTTP call).

## Requirements

1. **Token budget.** In `_write_chapter`, set
   `max_tokens = max(words_per_chapter * 8, 4000)`.

2. **Reasoning effort passthrough.** In `_openai_compatible`, if env
   `RETALE_REASONING_EFFORT` is set (e.g. "low"), include
   `"reasoning_effort": <value>` in the request JSON; omit the field
   entirely when unset.

3. **Structured completion result.** Change `LLMClient.complete` to return
   a small dataclass `Completion(text: str, finish_reason: str)`.
   - openai_compatible/openai: finish_reason from
     `choices[0].finish_reason` (default "stop" if absent).
   - anthropic: map `stop_reason` ("max_tokens" -> "length", else "stop").
   Update `Styler` accordingly.

4. **Truncation retry.** In `_write_chapter`, if `finish_reason == "length"`,
   retry ONCE with `max_tokens * 2`; use whichever attempt has
   finish_reason != "length", else the longer text.

5. **Output sanitizer.** Add `_sanitize_chapter(raw: str, index: int) -> str`
   applied to every chapter before it is returned:
   - strip markdown code fences (``` lines);
   - discard everything BEFORE the first line starting with `## `;
   - if NO line starts with `## `, prepend `## 第{index}章` as the title and
     keep the body;
   - normalize the title line to exactly one `## ` prefix.

6. **HTTP error context.** In both provider paths, on a non-2xx response
   raise a RuntimeError whose message includes the status code AND the
   first 500 characters of the response body. (Call `resp.raise_for_status()`
   only after capturing the body, or replace it with an explicit check.)

7. **--model flag.** `retale ... --model NAME` overrides `RETALE_MODEL`.
   Plumb it: CLI arg -> `LLMClient(model_override=...)` (constructor param,
   default None; env fallback preserved).

## Acceptance criteria

- [ ] Tests (all with mock clients / mock responses):
      (a) sanitizer drops leading meta text before `## `;
      (b) sanitizer synthesizes `## 第3章` when no header exists;
      (c) a mock client returning finish_reason "length" then "stop" causes
          exactly 2 calls, second with doubled max_tokens, final text from
          the second call;
      (d) mock 404 response with a JSON body -> raised error message
          contains both "404" and a distinctive body substring;
      (e) `--model` reaches the client (assert on a captured LLMClient or
          via monkeypatched constructor).
- [ ] Existing tests still pass (MockLLM in test_pipeline.py must be
      updated to the new Completion return type).
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
