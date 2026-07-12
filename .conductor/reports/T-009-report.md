# Report T-009: Resilience: 429/5xx backoff retry + chapter checkpoint/resume

generated: 2026-07-12 04:19 UTC

## Implementer notes

Implemented the T-009 resilience work within the allowed scope only. LLMClient.complete now wraps both provider paths with transient HTTP retry logic: HTTP 429 and all 5xx responses retry up to 3 times (4 total attempts) while non-transient 4xx responses fail immediately. Waits are derived from server hints when available (Retry-After header or a body fragment matching 'retry in <float>s'), otherwise defaulting to exponential 5/15/45 seconds, with each wait capped at 90 seconds. Waiting is routed through an injectable self._sleep (defaulting to time.sleep) so tests can capture retry delays without real sleeping. Each retry prints a stderr log line including retry attempt number, HTTP status, and wait seconds. After the final transient failure, the raised RuntimeError preserves the existing provider-specific message format (status code plus body excerpt). To support this cleanly, provider methods now raise an internal HTTPFailure carrier and complete converts it back into the existing RuntimeError only at the boundary. Styler.write_story now supports chapter checkpointing with progress_path. The progress file stores a fingerprint plus a chapters map and is written atomically via temp file + replace after each completed chapter. On startup, if a checkpoint exists and its fingerprint matches, stored chapters are restored in order, on_chapter is fired for each restored chapter so EPUB collection still works, a resume message is printed to stderr, and only missing chapters are generated. Fingerprints are sha256 over match id, style name, client model name, and the codex JSON dump; mismatches treat the checkpoint as stale and start fresh. On successful completion of all chapters, the progress file is deleted. CLI now wires a default progress path beside the output as <output stem>.progress.json and adds --fresh to remove any existing checkpoint before generation starts. Updated existing CLI-related fake styler signatures in tests to accept the new progress_path parameter. Added tests/test_resilience.py covering: 429 retry using a parsed 'retry in 10.3s' body hint, repeated 429 default backoff 5/15/45 and final failure, immediate non-retry on HTTP 400, chapter checkpoint persistence after a failure at chapter 3 and resume generating only the missing chapter while replaying on_chapter for restored chapters, fingerprint mismatch ignoring a stale checkpoint, automatic checkpoint deletion after success, and CLI --fresh removing a pre-existing checkpoint before calling the styler. Also updated one existing hardening test to assert HTTP error behavior through the complete() boundary, which is now where retries and RuntimeError conversion live. Verification: python -m pytest tests/ -q -> 36 passed; ruff check retale/ tests/ -> clean. No open questions.

## Test output

```
....................................                                     [100%]
36 passed in 1.24s
```

## Diff vs 9402bf50a834e410cdd7ed14c18a810a441a2518

```diff
...009-resilience-429-5xx-backoff-retry-chapter.md |  74 ++++++
 retale/cli.py                                      |   7 +-
 retale/narrative/styler.py                         | 130 +++++++++-
 slark.codex.json                                   |  25 ++
 tests/test_epub.py                                 |   2 +-
 tests/test_resilience.py                           | 279 +++++++++++++++++++++
 tests/test_styler_codex.py                         |   3 +-
 tests/test_styler_hardening.py                     |   2 +-
 8 files changed, 508 insertions(+), 14 deletions(-)
warning: in the working copy of '.conductor/tasks/T-009-resilience-429-5xx-backoff-retry-chapter.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of 'slark.codex.json', CRLF will be replaced by LF the next time Git touches it


diff --git a/.conductor/tasks/T-009-resilience-429-5xx-backoff-retry-chapter.md b/.conductor/tasks/T-009-resilience-429-5xx-backoff-retry-chapter.md
new file mode 100644
index 0000000..134627f
--- /dev/null
+++ b/.conductor/tasks/T-009-resilience-429-5xx-backoff-retry-chapter.md
@@ -0,0 +1,74 @@
+---
+id: T-009
+title: 'Resilience: 429/5xx backoff retry + chapter checkpoint/resume'
+status: in_progress
+priority: 1
+depends: []
+base: 9402bf50a834e410cdd7ed14c18a810a441a2518
+---
+
+## Context
+
+A transient HTTP 429 (free-tier quota) killed a story run after chapter 2,
+discarding both completed chapters. Generation is the only step that costs
+real money; it must be resumable, and transient provider errors (429/5xx)
+must be retried with backoff instead of aborting the book.
+
+## Scope
+
+You may touch: `retale/narrative/styler.py`, `retale/cli.py`, add
+`tests/test_resilience.py`, and update existing tests if signatures change.
+No new dependencies. Tests stay offline; sleeping must be injectable/mocked
+(never actually sleep in tests).
+
+## Requirements
+
+1. **Transient-error retry with backoff.** In `LLMClient.complete` (wrapping
+   both provider paths):
+   - On HTTP 429 or any 5xx, retry up to 3 times.
+   - Wait time: parse a server hint if present - the JSON body pattern
+     `retry in <float>s` or a `Retry-After` header - else exponential
+     backoff 5s/15s/45s. Cap any single wait at 90s.
+   - Sleep via an injectable `self._sleep` (default `time.sleep`) so tests
+     can capture waits without real delays.
+   - Log each retry to stderr: attempt number, status, wait seconds.
+   - After the final attempt, raise the existing RuntimeError (status +
+     body excerpt) unchanged.
+   - Non-transient statuses (4xx other than 429) must NOT be retried.
+
+2. **Chapter checkpointing.** `Styler.write_story` gains
+   `progress_path: Path | None = None`:
+   - When set, after each chapter is sanitized, append/update a JSON
+     progress file: `{"fingerprint": <str>, "chapters": {"1": "<text>", ...}}`
+     written atomically (write temp file then replace).
+   - On start, if the file exists AND its fingerprint matches, restore the
+     stored chapters: fire `on_chapter` for each restored chapter in order
+     (so EPUB collection still works), print
+     "[retale] resuming: chapters 1-N restored from checkpoint" to stderr,
+     and generate only the missing chapters.
+   - Fingerprint = sha256 over: match id (context.world), style name, model
+     name (client.model), and the codex JSON dump - any mismatch means the
+     checkpoint is stale: ignore it and start fresh (overwrite).
+   - On successful completion of ALL chapters, delete the progress file.
+
+3. **CLI wiring.** Default `progress_path` =
+   `<output stem>.progress.json`. Add `--fresh` flag: delete any existing
+   checkpoint before starting.
+
+## Acceptance criteria
+
+- [ ] Tests with mock HTTP responses / mock clients:
+      (a) a 429 whose body contains "retry in 10.3s" causes one wait of
+          ~10.3s (captured, not slept) then success on retry;
+      (b) three consecutive 429s -> exactly 3 retries with default backoff
+          5/15/45 then RuntimeError containing the status;
+      (c) a 400 response raises immediately with zero retries;
+      (d) write_story with a client that fails at chapter 3 leaves a
+          checkpoint containing chapters 1-2; a second write_story call with
+          the same fingerprint generates ONLY chapter 3 (assert per-chapter
+          call count) and fires on_chapter for all 3 in order;
+      (e) fingerprint mismatch (different model) ignores the checkpoint;
+      (f) successful completion deletes the progress file;
+      (g) --fresh removes a pre-existing checkpoint (CLI-level test with a
+          fake styler).
+- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
diff --git a/retale/cli.py b/retale/cli.py
index a901013..8565e57 100644
--- a/retale/cli.py
+++ b/retale/cli.py
@@ -49,6 +49,8 @@ def main(argv: list[str] | None = None) -> int:
                    help="load or save terminology codex JSON")
     p.add_argument("--model", default=None,
                    help="override the configured LLM model name")
+    p.add_argument("--fresh", action="store_true",
+                   help="discard any existing chapter checkpoint before generation")
     p.add_argument("--chapters", type=int, default=5,
                    help="target chapter count (auto-adjusted by density)")
     p.add_argument("-o", "--output", default=None, help="output .md path")
@@ -75,11 +77,14 @@ def main(argv: list[str] | None = None) -> int:
         return 0
 
     out = _output_path(args.game, result.context.world.get("match_id", "story"), args.output, args.format)
+    progress_path = out.with_suffix(".progress.json")
     style = StyleProfile.load(args.style, sample_path=args.style_sample)
     if args.model:
         styler = Styler(style, client=LLMClient(model_override=args.model))
     else:
         styler = Styler(style)
+    if args.fresh and progress_path.exists():
+        progress_path.unlink()
     codex_path = _codex_path(out, args.codex)
     if codex_path.exists():
         codex = json.loads(codex_path.read_text(encoding="utf-8"))
@@ -107,7 +112,7 @@ def main(argv: list[str] | None = None) -> int:
 
         callback = epub_callback
 
-    story = styler.write_story(plan, on_chapter=callback, codex=codex)
+    story = styler.write_story(plan, on_chapter=callback, codex=codex, progress_path=progress_path)
     if args.format == "epub":
         write_epub(
             title=_story_title(result),
diff --git a/retale/narrative/styler.py b/retale/narrative/styler.py
index 917b7b1..f9098fa 100644
--- a/retale/narrative/styler.py
+++ b/retale/narrative/styler.py
@@ -19,6 +19,8 @@ import json
 import os
 import re
 import sys
+import time
+from hashlib import sha256
 from dataclasses import dataclass
 from pathlib import Path
 from typing import Any
@@ -71,19 +73,45 @@ class Completion:
     finish_reason: str = "stop"
 
 
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
 # ---------------------------------------------------------------------------
 # LLM providers
 # ---------------------------------------------------------------------------
 
 class LLMClient:
-    def __init__(self, model_override: str | None = None):
+    def __init__(self, model_override: str | None = None, sleep_fn=None):
         self.provider = os.environ.get("RETALE_PROVIDER", "anthropic")
         self.model = model_override or os.environ.get("RETALE_MODEL", "")
+        self._sleep = sleep_fn or time.sleep
 
     def complete(self, system: str, user: str, max_tokens: int = 2000) -> Completion:
-        if self.provider == "anthropic":
-            return self._anthropic(system, user, max_tokens)
-        return self._openai_compatible(system, user, max_tokens)
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
+                    f"[retale] retry {attempt + 1}/3 after HTTP {error.status_code}; waiting {wait_seconds}s",
+                    file=sys.stderr,
+                )
+                self._sleep(wait_seconds)
+        raise RuntimeError("unreachable")
 
     def _anthropic(self, system: str, user: str, max_tokens: int) -> Completion:
         key = os.environ.get("ANTHROPIC_API_KEY")
@@ -100,8 +128,11 @@ class LLMClient:
             timeout=120)
         body = resp.text[:500]
         if not resp.ok:
-            raise RuntimeError(
-                f"Anthropic HTTP {resp.status_code}: {body}"
+            raise HTTPFailure(
+                provider_label="Anthropic",
+                status_code=resp.status_code,
+                body_excerpt=body,
+                headers=dict(getattr(resp, "headers", {}) or {}),
             )
         payload = resp.json()
         finish_reason = "length" if payload.get("stop_reason") == "max_tokens" else "stop"
@@ -138,8 +169,11 @@ class LLMClient:
             timeout=120)
         body = resp.text[:500]
         if not resp.ok:
-            raise RuntimeError(
-                f"OpenAI-compatible HTTP {resp.status_code}: {body}"
+            raise HTTPFailure(
+                provider_label="OpenAI-compatible",
+                status_code=resp.status_code,
+                body_excerpt=body,
+                headers=dict(getattr(resp, "headers", {}) or {}),
             )
         data = resp.json()
         choice = data["choices"][0]
@@ -148,6 +182,19 @@ class LLMClient:
             finish_reason=choice.get("finish_reason", "stop"),
         )
 
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
 
 # ---------------------------------------------------------------------------
 # Prose generation
@@ -158,16 +205,39 @@ class Styler:
         self.style = style
         self.client = client or LLMClient()
 
-    def write_story(self, plan: StoryPlan, on_chapter=None, codex: dict[str, Any] | None = None) -> str:
+    def write_story(
+        self,
+        plan: StoryPlan,
+        on_chapter=None,
+        codex: dict[str, Any] | None = None,
+        progress_path: Path | None = None,
+    ) -> str:
         if codex is None:
             codex = self.build_codex(plan)
+        fingerprint = self._fingerprint(plan, codex)
+        restored = self._load_progress(progress_path, fingerprint)
         outline = self._outline_text(plan, codex)
         parts = [f"# {self._title(plan)}\n"]
+        checkpoint_chapters = {str(index): text for index, text in restored.items()}
+        if restored:
+            restored_indices = sorted(restored)
+            print(
+                f"[retale] resuming: chapters 1-{restored_indices[-1]} restored from checkpoint",
+                file=sys.stderr,
+            )
         for ch in plan.chapters:
-            prose = self._write_chapter(plan, ch, outline)
+            if ch.index in restored:
+                prose = restored[ch.index]
+            else:
+                prose = self._write_chapter(plan, ch, outline)
+                if progress_path is not None:
+                    checkpoint_chapters[str(ch.index)] = prose
+                    self._write_progress(progress_path, fingerprint, checkpoint_chapters)
             parts.append(prose.strip() + "\n")
             if on_chapter:
                 on_chapter(ch, prose)
+        if progress_path is not None and progress_path.exists():
+            progress_path.unlink()
         return "\n".join(parts)
 
     def build_codex(self, plan: StoryPlan) -> dict[str, Any]:
@@ -347,6 +417,46 @@ class Styler:
     def _empty_codex() -> dict[str, Any]:
         return {"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}}
 
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
     @staticmethod
     def _title(plan: StoryPlan) -> str:
         return (f"{plan.context.protagonist.persona or plan.context.protagonist.name}"
diff --git a/slark.codex.json b/slark.codex.json
new file mode 100644
index 0000000..8607c47
--- /dev/null
+++ b/slark.codex.json
@@ -0,0 +1,25 @@
+{
+  "heroes": {
+    "Slark": "小鱼人",
+    "Windranger": "风行",
+    "Dawnbreaker": "大锤",
+    "Rubick": "拉比克",
+    "Axe": "斧王",
+    "Legion Commander": "军团",
+    "Disruptor": "萨尔",
+    "Bane": "痛苦之源",
+    "Invoker": "卡尔",
+    "Morphling": "水人"
+  },
+  "protagonist_intro": "小鱼人“陆地神仙”",
+  "skills": {
+    "Dark Pact": "无垢玄契",
+    "Pounce": "飞蛟探海",
+    "Essence Shift": "北冥夺魄",
+    "Shadow Dance": "幻影神游"
+  },
+  "factions": {
+    "Radiant": "天辉",
+    "Dire": "夜魇"
+  }
+}
\ No newline at end of file
diff --git a/tests/test_epub.py b/tests/test_epub.py
index 12db7e2..bcbf489 100644
--- a/tests/test_epub.py
+++ b/tests/test_epub.py
@@ -106,7 +106,7 @@ def test_cli_writes_epub_via_chapter_callback(monkeypatch, tmp_path: Path):
                 "factions": {},
             }
 
-        def write_story(self, plan: FakePlan, on_chapter=None, codex=None) -> str:
+        def write_story(self, plan: FakePlan, on_chapter=None, codex=None, progress_path=None) -> str:
             parts = ["# Knight - a dota2 tale\n"]
             for chapter, prose in zip(plan.chapters, chapter_prose):
                 parts.append(prose)
diff --git a/tests/test_resilience.py b/tests/test_resilience.py
new file mode 100644
index 0000000..7a7c6d1
--- /dev/null
+++ b/tests/test_resilience.py
@@ -0,0 +1,279 @@
+"""Tests for retry backoff and chapter checkpoint resume."""
+
+from __future__ import annotations
+
+import json
+from dataclasses import dataclass
+from pathlib import Path
+
+import pytest
+
+from retale.cli import main
+from retale.core.schema import EventKind, MatchContext, NarrativeEvent, Protagonist
+from retale.narrative.planner import Chapter, StoryPlan
+from retale.narrative.styler import Completion, LLMClient, StyleProfile, Styler
+
+
+def _sample_plan(chapter_count: int = 3) -> StoryPlan:
+    context = MatchContext(
+        game="dota2",
+        protagonist=Protagonist(name="Hero", persona="Slark"),
+        outcome="victory",
+        world={"match_id": 42},
+    )
+    chapters = []
+    for index in range(1, chapter_count + 1):
+        event = NarrativeEvent(
+            t=float(index),
+            kind=EventKind.KILL,
+            summary=f"Event {index}",
+            importance=0.7,
+            protagonist_involved=True,
+        )
+        chapters.append(
+            Chapter(
+                index=index,
+                title_hint=f"Hint {index}",
+                arc_role="opening" if index == 1 else "resolution",
+                t_start=float(index - 1),
+                t_end=float(index),
+                events=[event],
+                turning_point=event,
+            )
+        )
+    return StoryPlan(context=context, chapters=chapters, logline="Resilience test.")
+
+
+class FakeHTTPResponse:
+    def __init__(self, status_code: int, body: str, payload: dict | None = None, headers: dict[str, str] | None = None):
+        self.status_code = status_code
+        self.text = body
+        self._payload = payload or {}
+        self.headers = headers or {}
+
+    @property
+    def ok(self) -> bool:
+        return 200 <= self.status_code < 300
+
+    def json(self):
+        return self._payload
+
+
+def test_complete_retries_429_with_server_hint(monkeypatch):
+    responses = [
+        FakeHTTPResponse(429, '{"error":"retry in 10.3s"}'),
+        FakeHTTPResponse(
+            200,
+            '{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}',
+            payload={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
+        ),
+    ]
+    waits: list[float] = []
+
+    monkeypatch.setattr("retale.narrative.styler.requests.post", lambda *args, **kwargs: responses.pop(0))
+    client = LLMClient(model_override="test-model", sleep_fn=waits.append)
+    client.provider = "openai_compatible"
+
+    result = client.complete("system", "user", max_tokens=100)
+
+    assert result.text == "ok"
+    assert waits == [10.3]
+
+
+def test_complete_retries_three_times_then_raises(monkeypatch):
+    waits: list[float] = []
+    responses = [FakeHTTPResponse(429, '{"error":"quota hit"}') for _ in range(4)]
+
+    monkeypatch.setattr("retale.narrative.styler.requests.post", lambda *args, **kwargs: responses.pop(0))
+    client = LLMClient(model_override="test-model", sleep_fn=waits.append)
+    client.provider = "openai_compatible"
+
+    with pytest.raises(RuntimeError) as exc_info:
+        client.complete("system", "user", max_tokens=100)
+
+    assert waits == [5.0, 15.0, 45.0]
+    assert "429" in str(exc_info.value)
+
+
+def test_complete_does_not_retry_non_transient_400(monkeypatch):
+    waits: list[float] = []
+
+    monkeypatch.setattr(
+        "retale.narrative.styler.requests.post",
+        lambda *args, **kwargs: FakeHTTPResponse(400, '{"error":"bad request"}'),
+    )
+    client = LLMClient(model_override="test-model", sleep_fn=waits.append)
+    client.provider = "openai_compatible"
+
+    with pytest.raises(RuntimeError) as exc_info:
+        client.complete("system", "user", max_tokens=100)
+
+    assert waits == []
+    assert "400" in str(exc_info.value)
+
+
+def test_write_story_resumes_from_checkpoint(tmp_path: Path):
+    plan = _sample_plan(3)
+    progress_path = tmp_path / "story.progress.json"
+    calls: list[int] = []
+    restored: list[int] = []
+
+    class FailingClient:
+        model = "model-a"
+
+        def __init__(self):
+            self.fail_on = 3
+
+        def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
+            chapter_no = int(user.split("Now write CHAPTER ", 1)[1].split(" ", 1)[0])
+            calls.append(chapter_no)
+            if chapter_no == self.fail_on:
+                raise RuntimeError("chapter 3 exploded")
+            return Completion(text=f"## Chapter {chapter_no}\n\nBody {chapter_no}", finish_reason="stop")
+
+    styler = Styler(StyleProfile(name="adventure"), client=FailingClient())  # type: ignore[arg-type]
+    with pytest.raises(RuntimeError):
+        styler.write_story(
+            plan,
+            codex={"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}},
+            progress_path=progress_path,
+        )
+
+    saved = json.loads(progress_path.read_text(encoding="utf-8"))
+    assert sorted(saved["chapters"]) == ["1", "2"]
+
+    calls.clear()
+    styler.client.fail_on = 99  # type: ignore[attr-defined]
+    story = styler.write_story(
+        plan,
+        codex={"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}},
+        progress_path=progress_path,
+        on_chapter=lambda chapter, prose: restored.append(chapter.index),
+    )
+
+    assert calls == [3]
+    assert restored == [1, 2, 3]
+    assert "Body 3" in story
+
+
+def test_checkpoint_fingerprint_mismatch_ignores_restore(tmp_path: Path):
+    plan = _sample_plan(2)
+    progress_path = tmp_path / "story.progress.json"
+    progress_path.write_text(
+        json.dumps(
+            {
+                "fingerprint": "stale",
+                "chapters": {"1": "## Old\n\nBody"},
+            },
+            ensure_ascii=False,
+        ),
+        encoding="utf-8",
+    )
+    calls: list[int] = []
+
+    class RecordingClient:
+        model = "different-model"
+
+        def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
+            chapter_no = int(user.split("Now write CHAPTER ", 1)[1].split(" ", 1)[0])
+            calls.append(chapter_no)
+            return Completion(text=f"## Chapter {chapter_no}\n\nBody {chapter_no}", finish_reason="stop")
+
+    styler = Styler(StyleProfile(name="adventure"), client=RecordingClient())  # type: ignore[arg-type]
+    styler.write_story(
+        plan,
+        codex={"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}},
+        progress_path=progress_path,
+    )
+
+    assert calls == [1, 2]
+
+
+def test_successful_completion_deletes_progress_file(tmp_path: Path):
+    plan = _sample_plan(2)
+    progress_path = tmp_path / "story.progress.json"
+
+    class SuccessClient:
+        model = "model-a"
+
+        def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
+            chapter_no = int(user.split("Now write CHAPTER ", 1)[1].split(" ", 1)[0])
+            return Completion(text=f"## Chapter {chapter_no}\n\nBody {chapter_no}", finish_reason="stop")
+
+    styler = Styler(StyleProfile(name="adventure"), client=SuccessClient())  # type: ignore[arg-type]
+    styler.write_story(
+        plan,
+        codex={"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}},
+        progress_path=progress_path,
+    )
+
+    assert not progress_path.exists()
+
+
+def test_cli_fresh_removes_existing_checkpoint(monkeypatch, tmp_path: Path):
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
+                        protagonist=Protagonist(name="Hero", persona="Slark"),
+                        outcome="victory",
+                        world={"match_id": 7},
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
+    class FakeStyler:
+        def __init__(self, style, client=None):
+            self.style = style
+
+        def build_codex(self, plan):
+            return {"heroes": {}, "protagonist_intro": "", "skills": {}, "factions": {}}
+
+        def write_story(self, plan, on_chapter=None, codex=None, progress_path=None):
+            captured["progress_path"] = progress_path
+            captured["progress_existed_at_call"] = progress_path.exists() if progress_path else None
+            return "## Title\n\nBody"
+
+    monkeypatch.setattr("retale.cli._adapters", lambda: {"dota2": FakeAdapter})
+    monkeypatch.setattr("retale.cli.Planner", FakePlanner)
+    monkeypatch.setattr("retale.cli.StyleProfile.load", lambda *args, **kwargs: StyleProfile(name="test"))
+    monkeypatch.setattr("retale.cli.Styler", FakeStyler)
+
+    out_path = tmp_path / "story.md"
+    progress_path = out_path.with_suffix(".progress.json")
+    progress_path.write_text("{}", encoding="utf-8")
+
+    exit_code = main(["dota2", "fake.json", "--fresh", "-o", str(out_path)])
+
+    assert exit_code == 0
+    assert captured["progress_path"] == progress_path
+    assert captured["progress_existed_at_call"] is False
diff --git a/tests/test_styler_codex.py b/tests/test_styler_codex.py
index c740e36..1bc58c0 100644
--- a/tests/test_styler_codex.py
+++ b/tests/test_styler_codex.py
@@ -175,8 +175,9 @@ def test_cli_codex_existing_file_skips_generation_and_missing_file_writes(monkey
             captured["build_calls"] = captured.get("build_calls", 0) + 1
             return {"heroes": {"Slark": "小鱼人"}, "protagonist_intro": "", "skills": {}, "factions": {}}
 
-        def write_story(self, plan, on_chapter=None, codex=None):
+        def write_story(self, plan, on_chapter=None, codex=None, progress_path=None):
             captured["codex"] = codex
+            captured["progress_path"] = progress_path
             prose = "## Title\n\nBody"
             if on_chapter:
                 on_chapter(plan.chapters[0], prose)
diff --git a/tests/test_styler_hardening.py b/tests/test_styler_hardening.py
index 376fb7d..5cb40b9 100644
--- a/tests/test_styler_hardening.py
+++ b/tests/test_styler_hardening.py
@@ -89,7 +89,7 @@ def test_openai_compatible_http_error_includes_body(monkeypatch):
     client.provider = "openai_compatible"
 
     with pytest.raises(RuntimeError) as exc_info:
-        client._openai_compatible("system", "user", 4000)
+        client.complete("system", "user", 4000)
 
     message = str(exc_info.value)
     assert "404" in message
warning: in the working copy of '.conductor/tasks/T-009-resilience-429-5xx-backoff-retry-chapter.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of 'slark.codex.json', CRLF will be replaced by LF the next time Git touches it
```

## Original spec

## Context

A transient HTTP 429 (free-tier quota) killed a story run after chapter 2,
discarding both completed chapters. Generation is the only step that costs
real money; it must be resumable, and transient provider errors (429/5xx)
must be retried with backoff instead of aborting the book.

## Scope

You may touch: `retale/narrative/styler.py`, `retale/cli.py`, add
`tests/test_resilience.py`, and update existing tests if signatures change.
No new dependencies. Tests stay offline; sleeping must be injectable/mocked
(never actually sleep in tests).

## Requirements

1. **Transient-error retry with backoff.** In `LLMClient.complete` (wrapping
   both provider paths):
   - On HTTP 429 or any 5xx, retry up to 3 times.
   - Wait time: parse a server hint if present - the JSON body pattern
     `retry in <float>s` or a `Retry-After` header - else exponential
     backoff 5s/15s/45s. Cap any single wait at 90s.
   - Sleep via an injectable `self._sleep` (default `time.sleep`) so tests
     can capture waits without real delays.
   - Log each retry to stderr: attempt number, status, wait seconds.
   - After the final attempt, raise the existing RuntimeError (status +
     body excerpt) unchanged.
   - Non-transient statuses (4xx other than 429) must NOT be retried.

2. **Chapter checkpointing.** `Styler.write_story` gains
   `progress_path: Path | None = None`:
   - When set, after each chapter is sanitized, append/update a JSON
     progress file: `{"fingerprint": <str>, "chapters": {"1": "<text>", ...}}`
     written atomically (write temp file then replace).
   - On start, if the file exists AND its fingerprint matches, restore the
     stored chapters: fire `on_chapter` for each restored chapter in order
     (so EPUB collection still works), print
     "[retale] resuming: chapters 1-N restored from checkpoint" to stderr,
     and generate only the missing chapters.
   - Fingerprint = sha256 over: match id (context.world), style name, model
     name (client.model), and the codex JSON dump - any mismatch means the
     checkpoint is stale: ignore it and start fresh (overwrite).
   - On successful completion of ALL chapters, delete the progress file.

3. **CLI wiring.** Default `progress_path` =
   `<output stem>.progress.json`. Add `--fresh` flag: delete any existing
   checkpoint before starting.

## Acceptance criteria

- [ ] Tests with mock HTTP responses / mock clients:
      (a) a 429 whose body contains "retry in 10.3s" causes one wait of
          ~10.3s (captured, not slept) then success on retry;
      (b) three consecutive 429s -> exactly 3 retries with default backoff
          5/15/45 then RuntimeError containing the status;
      (c) a 400 response raises immediately with zero retries;
      (d) write_story with a client that fails at chapter 3 leaves a
          checkpoint containing chapters 1-2; a second write_story call with
          the same fingerprint generates ONLY chapter 3 (assert per-chapter
          call count) and fires on_chapter for all 3 in order;
      (e) fingerprint mismatch (different model) ignores the checkpoint;
      (f) successful completion deletes the progress file;
      (g) --fresh removes a pre-existing checkpoint (CLI-level test with a
          fake styler).
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.
