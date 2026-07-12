---
id: T-006
title: 'Styler hardening: reasoning-model budgets, output sanitizer, error context,
  --model flag'
status: done
priority: 1
depends: []
base: 357997f0db080795d16a55294b16c192c3367aee
---

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
