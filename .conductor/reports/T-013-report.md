# Report T-013: Release hardening: fort silence, Windows CI matrix, gitignore progress files

generated: 2026-07-12 12:24 UTC

## Implementer notes

Implemented the release-hardening leftovers within the exact scope. In `whitelee/adapters/dota2_opendota.py`, building objectives now silence fort/ancient keys before the generic objective fallback runs. The parser keeps treating these as deliberately skipped building keys, and `_objective_events()` now short-circuits any building objective whose key should be silenced, so `building_kill` entries like `npc_dota_badguys_fort` emit no event at all. Generic fallback remains available only for non-fort building objective keys that fail to parse into a specific building shape.

Fixture/test changes:
- Added one `building_kill` objective with key `npc_dota_badguys_fort` to `tests/fixtures/dota2_match.json`.
- Tightened `tests/test_pipeline.py` to assert:
  - objective event count remains 3,
  - no event targets `npc_dota_badguys_fort`,
  - aggregated base-push `merged_keys` stays at 4 and does not include the fort key,
  - existing tower and barracks assertions still pass.

CI / gitignore:
- Updated `.github/workflows/ci.yml` to a matrix over both OS and Python versions.
- Added `*.progress.json` to `.gitignore`.

YAML block verified manually as required:
```yaml
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ["3.10", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python-version }}" }
      - run: pip install -e ".[dev]"
      - run: ruff check whitelee/
      - run: pytest tests/ -q
```

Verification passed:
- `python -m pytest tests/ -q` -> `42 passed in 9.41s`
- `ruff check whitelee/` -> `All checks passed!`

## Test output

```
..........................................                               [100%]
42 passed in 0.73s
```

## Diff vs 7ee03702de80156d19e9e62f1daec33aef19f7df

```diff
...T-013-release-hardening-fort-silence-windows-c.md |  3 ++-
 .github/workflows/ci.yml                             |  6 ++++--
 .gitignore                                           |  1 +
 tests/fixtures/dota2_match.json                      |  6 ++++++
 tests/test_pipeline.py                               |  4 ++++
 whitelee/adapters/dota2_opendota.py                  | 20 +++++++++++++++++---
 6 files changed, 34 insertions(+), 6 deletions(-)
warning: in the working copy of '.conductor/tasks/T-001-dota-2-adapter-chat-gold-swing-momentum-.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-002-cs2-adapter-outcome-resolution-round-sta.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-003-epub-export-stdlib-only.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-004-dota-2-hero-name-resolution-unparsed-mat.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-005-dota-2-chat-filtering-building-enrichmen.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-006-styler-hardening-reasoning-model-budgets.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-007-terminology-codex-naming-conventions-tit.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-008-combat-texture-teamfight-ability-item-us.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-009-resilience-429-5xx-backoff-retry-chapter.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-010-chat-wheel-resolution-taunt-tagging-hubr.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-011-story-scout-worthiness-scoring-protagoni.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-012-rename-retale-to-whitelee-package-cli-en.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of '.conductor/tasks/T-013-release-hardening-fort-silence-windows-c.md', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of 'slark.codex.json', CRLF will be replaced by LF the next time Git touches it
warning: in the working copy of 'whitelee_dota2_8879557061.codex.json', CRLF will be replaced by LF the next time Git touches it


diff --git a/.conductor/tasks/T-013-release-hardening-fort-silence-windows-c.md b/.conductor/tasks/T-013-release-hardening-fort-silence-windows-c.md
index 3375fc6..1279c81 100644
--- a/.conductor/tasks/T-013-release-hardening-fort-silence-windows-c.md
+++ b/.conductor/tasks/T-013-release-hardening-fort-silence-windows-c.md
@@ -1,10 +1,11 @@
 ---
 id: T-013
 title: 'Release hardening: fort silence, Windows CI matrix, gitignore progress files'
-status: todo
+status: in_progress
 priority: 2
 depends:
 - T-012
+base: 7ee03702de80156d19e9e62f1daec33aef19f7df
 ---
 
 ## Context
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index dfa0b96..92ab742 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -4,9 +4,11 @@ on:
   pull_request:
 jobs:
   test:
-    runs-on: ubuntu-latest
+    runs-on: ${{ matrix.os }}
     strategy:
-      matrix: { python-version: ["3.10", "3.12"] }
+      matrix:
+        os: [ubuntu-latest, windows-latest]
+        python-version: ["3.10", "3.12"]
     steps:
       - uses: actions/checkout@v4
       - uses: actions/setup-python@v5
diff --git a/.gitignore b/.gitignore
index 175a188..e7ddd26 100644
--- a/.gitignore
+++ b/.gitignore
@@ -7,4 +7,5 @@ build/
 .pytest_cache/
 .ruff_cache/
 whitelee_*.md
+*.progress.json
 *.dem
diff --git a/tests/fixtures/dota2_match.json b/tests/fixtures/dota2_match.json
index dcb303e..15d4b45 100644
--- a/tests/fixtures/dota2_match.json
+++ b/tests/fixtures/dota2_match.json
@@ -336,6 +336,12 @@
    "type": "building_kill",
    "unit": "npc_dota_hero_juggernaut",
    "key": "npc_dota_badguys_tower4"
+  },
+  {
+   "time": 2065,
+   "type": "building_kill",
+   "unit": "npc_dota_hero_juggernaut",
+   "key": "npc_dota_badguys_fort"
   }
  ],
  "teamfights": [
diff --git a/tests/test_pipeline.py b/tests/test_pipeline.py
index dd1d930..688cdeb 100644
--- a/tests/test_pipeline.py
+++ b/tests/test_pipeline.py
@@ -173,6 +173,7 @@ def test_chat_and_economy_events(extraction):
         event for event in extraction.events
         if event.kind == EventKind.OBJECTIVE and "tier-1 mid tower" in event.summary
     ]
+    objective_events = [event for event in extraction.events if event.kind == EventKind.OBJECTIVE]
     barracks_events = [
         event for event in extraction.events
         if event.kind == EventKind.OBJECTIVE and "melee barracks" in event.summary
@@ -210,9 +211,12 @@ def test_chat_and_economy_events(extraction):
     assert tower_events[0].summary == "The Dire's tier-1 mid tower falls."
     assert tower_events[0].actor == "Slark"
     assert tower_events[0].protagonist_involved is True
+    assert len(objective_events) == 3
+    assert not any(event.target == "npc_dota_badguys_fort" for event in extraction.events)
     assert len(aggregate_events) == 1
     assert aggregate_events[0].importance == 0.75
     assert len(aggregate_events[0].data["merged_keys"]) == 4
+    assert "npc_dota_badguys_fort" not in aggregate_events[0].data["merged_keys"]
     assert len(barracks_events) == 1
     assert barracks_events[0].importance == 0.7
     assert len(lane_phase_events) == 1
diff --git a/whitelee/adapters/dota2_opendota.py b/whitelee/adapters/dota2_opendota.py
index dff4ce2..0d5c379 100644
--- a/whitelee/adapters/dota2_opendota.py
+++ b/whitelee/adapters/dota2_opendota.py
@@ -353,17 +353,24 @@ class Dota2OpenDotaAdapter(GameAdapter):
     ) -> list[NarrativeEvent]:
         out: list[NarrativeEvent] = []
         for obj in match.get("objectives", []) or []:
+            objective_type = str(obj.get("type", ""))
+            building_key = str(obj.get("key", ""))
             building_event = self._building_objective_event(obj, me, hero, hero_lookup)
             if building_event is not None:
                 out.append(building_event)
                 continue
+            if (
+                objective_type in {"building_kill", "CHAT_MESSAGE_TOWER_KILL", "CHAT_MESSAGE_BARRACKS_KILL"}
+                and self._is_silenced_building_key(building_key)
+            ):
+                continue
 
             kind, imp, phrase = _OBJECTIVE_MAP.get(
-                obj.get("type", ""), (EventKind.OBJECTIVE, 0.4, "objective event"))
+                objective_type, (EventKind.OBJECTIVE, 0.4, "objective event"))
             out.append(NarrativeEvent(
                 t=float(obj.get("time", 0)), kind=kind,
                 actor=str(obj.get("unit", "") or obj.get("team", "")),
-                target=str(obj.get("key", "")),
+                target=building_key,
                 summary=phrase, importance=imp, data=obj))
         return self._aggregate_building_events(out)
 
@@ -565,10 +572,17 @@ class Dota2OpenDotaAdapter(GameAdapter):
             return {"owner": owner, "kind": "barracks", "label": "melee barracks", "lane": lane}
         if "range" in tokens and "rax" in tokens:
             return {"owner": owner, "kind": "barracks", "label": "ranged barracks", "lane": lane}
-        if "fort" in tokens:
+        if Dota2OpenDotaAdapter._is_silenced_building_key(key):
             return {"owner": owner, "kind": "fort", "lane": lane}
         return None
 
+    @staticmethod
+    def _is_silenced_building_key(key: str) -> bool:
+        if not key:
+            return False
+        tokens = key.split("_")
+        return "fort" in tokens or "ancient" in tokens
+
     @staticmethod
     def _aggregate_building_events(events: list[NarrativeEvent]) -> list[NarrativeEvent]:
         aggregated: list[NarrativeEvent] = []
warning: in the working copy of '.conductor/tasks/T-013-release-hardening-fort-silence-windows-c.md', CRLF will be replaced by LF the next time Git touches it
```

## Original spec

## Context

Release-hardening leftovers: (1) fort/ancient building kills leak a naked
"destroyed a building" event (the key parser correctly identifies `fort`
for skipping, but unparsable/skipped building keys fall through to the
generic objective branch and emit anyway) - seen in real match 8879557061,
final chapter. (2) CI tests only ubuntu-latest while all development
happens on Windows - tonight's encoding incident proved this gap is real.
(3) `*.progress.json` checkpoints are transient and must not enter git.

Depends on T-012 (run against the renamed package).

## Scope

You may touch: `whitelee/adapters/dota2_opendota.py`,
`tests/fixtures/dota2_match.json`, `tests/test_pipeline.py`,
`.github/workflows/ci.yml`, `.gitignore`. Nothing else.

## Requirements

1. **Fort silence.** Objectives of building-kill type whose key parses to
   the fort/ancient (or any key the parser deliberately skips) must emit
   NO event at all - the MATCH_END event already covers the throne. Keys
   that fail to parse as buildings but belong to building-kill objective
   types emit the generic fallback ONLY when they are not fort keys.
2. **CI matrix.** Extend the workflow to
   `os: [ubuntu-latest, windows-latest]` x `python: ["3.10", "3.12"]`,
   `runs-on: ${{ matrix.os }}`. Keep ruff + pytest steps unchanged.
3. **.gitignore** gains `*.progress.json`.

## Acceptance criteria

- [ ] Fixture gains one building_kill objective with key
      `npc_dota_badguys_fort`; tests assert it produces zero events, while
      existing tower/rax assertions still pass and the event count math is
      updated accordingly.
- [ ] Workflow YAML contains both OS entries under a matrix and uses
      matrix.os (assert by reading the YAML in a test OR verify manually
      and paste the yaml block in notes).
- [ ] `python -m pytest tests/ -q` passes; `ruff check whitelee/` clean.
