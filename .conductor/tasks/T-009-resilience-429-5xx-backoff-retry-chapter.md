---
id: T-009
title: 'Resilience: 429/5xx backoff retry + chapter checkpoint/resume'
status: done
priority: 1
depends: []
base: 9402bf50a834e410cdd7ed14c18a810a441a2518
---

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
