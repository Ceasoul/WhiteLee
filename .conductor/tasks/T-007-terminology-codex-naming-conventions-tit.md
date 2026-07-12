---
id: T-007
title: 'Terminology codex: naming conventions, title scheme, sanitizer fixes'
status: done
priority: 1
depends: []
base: e9675a1d68f96027ca2ca59b93adb08733fed0f5
---

## Context

Full-story generation exposed cross-chapter consistency defects, because each
chapter is generated independently:

1. The protagonist's signature skill was named "移星易宿" in chapter 5 and
   "玄阴盗气法" in chapter 9; Legion Commander drifts between 铁血女帅 /
   军团统领 / 特雷斯汀.
2. Chinese literary convention requires heroes to be introduced by their
   community/unit nickname + player handle - 小鱼人"陆地神仙" - NOT the
   transliterated official name 斯拉克. This is a language-culture concern
   and must NOT leak into the adapter layer.
3. Chapter titles drift in numbering scheme (第一章 / 决斗场中英豪陨 /
   第五章 mixed). Title schemes must be a style-profile rule, extensible to
   other languages.
4. Ledger items from T-006 review: the sanitizer's no-header fallback
   collapses blank lines (destroying paragraph structure), and an indented
   header ("  ## X") normalizes incorrectly to "## ## X".

## Scope

You may touch: `retale/narrative/styler.py`, `retale/cli.py`, all files under
`styles/`, and add `tests/test_styler_codex.py`. You may update MockLLM in
`tests/test_pipeline.py` if the new call sequence requires it. Nothing else.
No new dependencies. Tests stay offline (mock clients only).

## Requirements

1. **StyleProfile fields.** Add optional fields, loaded from YAML:
   - `title_format`: e.g. `"第{n}章 {title}"` (zh) or `"Chapter {n}: {title}"`
     (en). Empty/absent = no enforcement.
   - `naming`: free-text naming conventions injected into the codex prompt.
   Update the four bundled styles: wuxia gets
   `title_format: "第{n}章 {title}"` and a `naming` block stating: heroes are
   referred to by their Chinese community/unit nickname (e.g. Slark -> 小鱼人,
   Invoker -> 卡尔, Morphling -> 水人); the protagonist is INTRODUCED as
   <nickname>"<player handle>" (e.g. 小鱼人"陆地神仙"); the protagonist's
   skills receive wuxia-style names fixed for the whole book. chronicle_zh
   gets the same title_format and a naming block in chronicle register.
   adventure/hardboiled get `title_format: "Chapter {n}: {title}"`.

2. **Codex generation.** Before writing chapters, `Styler.write_story` makes
   ONE extra client call: given protagonist (persona + handle), allies,
   opponents, style language and `naming`, request STRICT JSON only (no
   fences, no prose):
   `{"heroes": {"<canonical name>": "<name to use in prose>"...},
     "protagonist_intro": "<exact introduction phrase>",
     "skills": {"<mechanic>": "<fixed literary name>"...},
     "factions": {"Radiant": "...", "Dire": "..."}}`
   Parse defensively: strip code fences if present; on JSON failure retry
   ONCE; on second failure proceed with an empty codex and print a stderr
   warning. Do not crash.

3. **Codex injection.** Append a TERMINOLOGY section to the outline text that
   lists every codex mapping verbatim, with the hard rule: "Use EXACTLY these
   names in every chapter. Never invent alternative names for the same
   entity." (The outline is already included in every chapter prompt.)

4. **`--codex PATH` CLI flag.** If PATH exists: load it as the codex JSON and
   SKIP the generation call. If PATH does not exist: generate, then write the
   codex JSON to PATH (UTF-8, ensure_ascii=False). When the flag is absent,
   behave as today plus save the codex beside the story output as
   `<output stem>.codex.json`.

5. **Title enforcement.** When `title_format` is set, extend the sanitizer:
   after existing normalization, strip any leading `第[一二三四五六七八九十百\d]+[章回][ :：]?`
   or `Chapter \d+[:. ]?` from the model's title, then rewrite the title line
   as `## ` + title_format with `{n}` = chapter index and `{title}` = the
   stripped title. Never double-prefix.

6. **Ledger fixes.**
   - No-header fallback must preserve blank lines (paragraph structure).
   - `"  ## Title"` (indented header) must normalize to `## Title`, not
     `## ## Title`.

## Acceptance criteria

- [ ] Tests with a call-capturing mock client:
      (a) write_story with 2+ chapters issues exactly 1 codex call first,
          and every subsequent chapter prompt contains a codex mapping string
          (e.g. 小鱼人) and the TERMINOLOGY hard rule;
      (b) codex call returning invalid JSON twice -> empty codex, story still
          generated, warning on stderr (capsys);
      (c) title_format "第{n}章 {title}": model title "## 决斗场中英豪陨" for
          chapter 4 becomes "## 第4章 决斗场中英豪陨"; model title already
          "## 第四章 XX" does NOT double-prefix;
      (d) --codex with an existing file skips the codex generation call
          (assert call count) and its mappings appear in chapter prompts;
          --codex with a missing path writes the file after generation;
      (e) sanitizer fallback preserves an empty line between two paragraphs;
          "  ## Title" normalizes to exactly "## Title".
- [ ] All bundled style YAMLs load with the new fields
      (extend test_style_profiles_all_load).
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.

## Architect feedback (rework 1)

cli.py 中的 getattr(styler,'build_codex',...) 垫片和 try/except TypeError 回退必须删除:except TypeError 会吞掉 write_story 内部的真实错误并静默整本重新生成(双倍费用,on_chapter 回调二次触发污染 EPUB 章节列表)。改为直接调用 styler.write_story(plan, on_chapter=callback, codex=codex) 与 styler.build_codex(plan)。Scope 扩展:允许修改 tests/test_epub.py,将其 FakeStyler 的 write_story 签名更新为 (self, plan, on_chapter=None, codex=None)。这是本次唯一修改项,其余实现保持不动。另:遇到 Scope 不够用时,正确动作是停下提问,不是用生产代码绕过——规则第 2 条。
