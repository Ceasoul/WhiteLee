---
id: T-010
title: Chat wheel resolution, taunt tagging, hubris detection
status: done
priority: 1
depends: []
base: d9c808f265b6437d9794bf6c020c4845a5d317bc
---

## Context

Product-level feedback: Dota 2's dramatic beats correlate strongly with chat
wheel messages and all-chat taunts - which T-005 filtered out entirely
because they surfaced as numeric IDs. The IDs are resolvable: OpenDota
serves `constants/chat_wheel` (id -> message text). Reinstating them WITH
resolution and temporal context turns noise into the story's drama metadata:
an enemy spamming "?" thirty seconds before dying is a self-contained
hubris-and-comeuppance beat.

This task is the data layer for the upcoming story-scout feature (T-011).

## Scope

You may touch: `retale/adapters/dota2_opendota.py`,
`tests/fixtures/dota2_match.json`, `tests/test_pipeline.py`. Nothing else.
No new dependencies. Tests stay offline (fake session, same pattern as the
hero constants). NOTE: T-005's test asserting chatwheel entries "must NOT
appear" is superseded - update it to assert they appear RESOLVED.

## Requirements

1. **Chat wheel constants.** Fetch
   `https://api.opendota.com/api/constants/chat_wheel` at most once per
   `extract()` via `self.session` (mirror the hero-constants pattern:
   graceful failure -> empty map). Entries carry a message text field
   (accept `message` or `label`, whichever is present).

2. **Reinstate chatwheel entries.** For chat entries with `type ==
   "chatwheel"` or digit-only keys: resolve the id through the map and emit
   a SOCIAL event with summary `{actor}: "{message}" (chat wheel)`.
   Unresolvable ids stay skipped (current behavior). Resolved messages pass
   through the existing 120-char truncation.

3. **Channel + side tagging.** Every SOCIAL event's `data` gains:
   `channel`: "chat" | "chatwheel"; `enemy`: True when the speaker's
   player_slot is on the opposite side from the protagonist (False for
   allies/protagonist, absent when the speaker cannot be resolved).

4. **Taunt tagging.** `data["taunt"] = True` when:
   - typed chat text, lowercased and stripped, is in
     `{"?", "??", "???", "ez", "ez game", "gg ez", "noob", "report",
       "报警", "菜", "?好"}` or consists only of `?` characters; or
   - a resolved chat-wheel message, lowercased, contains one of
     `{"well played", "gg", "ez", "haha", "thanks", "my bad", "?"}`.
   Keep both sets as module-level constants with a comment inviting
   community PRs.

5. **Hubris detector.** After all events are collected: for every SOCIAL
   event tagged `taunt` whose speaker's hero is resolvable, if that same
   hero DIES (appears as DEATH target or as KILL victim in protagonist
   kill events) within the following 60 seconds, raise the taunt event's
   importance to 0.6 and set `data["hubris"] = True`. Independently, any
   taunt within ±30s of a KILL/DEATH event involving the protagonist gets
   importance 0.45 (from the 0.15 chatwheel / 0.2 chat baseline). Higher
   rule wins; never lower an importance.

6. **Unparsed matches** remain unaffected (no chat -> no new events).

## Acceptance criteria

- [ ] Fixture: fake-session responses now include a chat_wheel constants
      stub mapping id 71 -> "Well played!" and one hero-line id (e.g.
      93001 -> "Fish bait!"); chat array keeps the two previously-dropped
      chatwheel entries and adds: an enemy typed "?" at time T followed by
      that enemy hero's death at T+30 (hubris case), and one chatwheel id
      absent from the stub (must stay dropped).
- [ ] Tests assert: resolved chatwheel SOCIAL events exist with the mapped
      text and channel "chatwheel"; the unmapped id emits nothing; the "?"
      event has taunt=True, hubris=True, importance 0.6; enemy flag correct
      for an enemy speaker and an ally speaker; the T-005 "no digit-only
      SOCIAL" assertion still holds (resolved text is not digits).
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.

## Architect feedback (rework 1)

打回一处:_TAUNT_TEXTS 中的三个中文词条被写成了 Unicode 替换字符(\ufffd),中文嘲讽词表实际失效。要求:(1) 用真实中文重写这三个词条:报警、菜、?好,写文件时显式使用 UTF-8 编码;(2) 新增测试:fixture 中加一条敌方 typed chat 内容为'菜',断言其 taunt=True 且 summary 含'菜',防止编码损毁再次静默通过;(3) 修好后在报告 notes 中粘贴 python -c 打印 _TAUNT_TEXTS 的实际输出。另记一条纪律(无需改动):测试只为规格中的要求背书,'Fish bait! 应为嘲讽'是你的测试自创的需求而非规格回归,词条可保留,但 notes 中的'regression'表述不实。
