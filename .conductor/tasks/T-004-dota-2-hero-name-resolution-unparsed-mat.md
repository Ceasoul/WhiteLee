---
id: T-004
title: 'Dota 2: hero name resolution + unparsed-match detection'
status: done
priority: 1
depends: []
---

## Context

First real-data run (match 7323799157) exposed two gaps in the Dota 2 adapter:

1. Real OpenDota match JSON gives players a numeric `hero_id` only - no
   `hero_name` / `localized_name` strings (our synthetic fixture had them,
   masking the gap). The protagonist rendered as "Hero 42", which is fatal
   for fiction.
2. Unparsed matches (replay expired or parse not requested) silently produce
   a 3-event skeleton. The user gets a hollow story with no explanation.

## Scope

You may touch: `retale/adapters/dota2_opendota.py`, `tests/test_pipeline.py`,
and you may add new fixture files under `tests/fixtures/`. Nothing else.
No new dependencies. Tests must remain fully offline (no network).

## Requirements

1. **Hero name resolution.** Add hero-name lookup to `Dota2OpenDotaAdapter`:
   - Resolution order per player: `hero_name`/`localized_name` field if
     present (keep current behavior) -> hero map fetched from
     `https://api.opendota.com/api/constants/heroes` (JSON dict keyed by
     hero id, each value has `localized_name`) -> fallback `"Hero {id}"`.
   - Fetch the constants at most ONCE per `extract()` call, via
     `self.session` (the adapter already accepts an injected
     `requests.Session` - tests must inject a fake session object with a
     `get()` method returning a stub response; do NOT monkeypatch the
     requests module globally).
   - If the constants fetch raises or returns bad data, degrade gracefully
     to the `"Hero {id}"` fallback - never crash extraction.
   - Apply resolved names everywhere heroes are named: protagonist persona,
     allies, opponents, kill/death summaries, big-item summaries.
   - Victim names in `kills_log` come as `npc_dota_hero_<slug>` strings -
     resolve them through the same map when possible (match by the
     constants' `name` field, which holds the npc slug), falling back to
     the current slug-prettifying behavior.

2. **Unparsed-match detection.** After loading the match JSON, detect the
   unparsed case: NO player has a non-empty `kills_log` AND the match has
   no `teamfights`. When detected:
   - Print a clear warning to stderr (English), stating the match has no
     parsed replay data, that stories will be skeletal, and suggesting:
     use a recent match (replays expire) and request parsing at
     https://www.opendota.com/matches/<match_id>.
   - Set `context.world["parsed"] = False` (True for parsed matches).
   - Still proceed and return the skeleton events (do not raise).

## Acceptance criteria

- [ ] New fixture `tests/fixtures/dota2_match_unparsed.json`: players with
      hero_id only (no hero_name), no kills_log, no teamfights, no chat.
- [ ] Existing parsed fixture: remove the `hero_name` fields from players
      so it matches real API shape, and update it (or the fake session in
      tests) so hero names now resolve through the constants map - proving
      the map path works end to end. Existing test assertions about names
      like "Juggernaut" must still pass.
- [ ] New tests: (a) hero names resolve via a fake-session constants map;
      (b) constants fetch failure degrades to "Hero {id}" without raising;
      (c) unparsed fixture sets world["parsed"] is False and emits the
      stderr warning (assert via capsys); (d) parsed fixture sets
      world["parsed"] is True.
- [ ] `python -m pytest tests/ -q` passes; `ruff check retale/` clean.

## Architect feedback (rework 1)

主角死亡检测不得用本地化名子串匹配 npc slug(Zeus/zuus、Nature's Prophet/furion、Wraith King/skeleton_king 等会漏检)。要求:(1) _hero_lookup 增加 by_id_slug 映射(hero_id -> 常量表 name 字段);(2) 死亡检测改为:取主角 hero_id 对应 slug,与 kills_log 的 key 精确等值比较;slug 未知时才回退子串逻辑;(3) 新增测试:slug 与本地化名不同的英雄(id -> {name: npc_dota_hero_zuus, localized_name: Zeus})作主角,对手击杀日志含 npc_dota_hero_zuus,断言 DEATH 事件生成且 summary 用 Zeus。其余不动。
