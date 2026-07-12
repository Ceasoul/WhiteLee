# WhiteLee Roadmap

Guiding principle: every game falls into one of four **extraction tiers**.
The narrative engine is shared; only extraction differs.

| Tier | Method | Fidelity | Cost | Examples |
|---|---|---|---|---|
| A | structured replay / API | high | low | Dota 2, CS2, LoL, SC2, AoE4 |
| B | save-file / log diffing | medium-high | medium | Civilization, Total War, RimWorld |
| C | vision (VLM on screenshots) | medium | high | HoMM3, classic games, anything |
| D | live log tailing | high | medium | MMORPGs (combat logs), D&D VTTs |

## Phase 1 — Steam mainstream (Tier A) `v0.1 – v0.3`

- [x] Dota 2 via OpenDota API (match id → parsed JSON)
- [x] CS2 via demoparser2 (.dem)
- [x] Chapter planner with arc roles + turning points
- [x] Pluggable LLM providers (Anthropic / OpenAI / local via
      OpenAI-compatible endpoints)
- [x] Style profiles incl. personal-voice imitation from writing samples
- [ ] Dota 2: match-level chat + ward/rune events + lane phase detection
- [ ] CS2: round economy narrative (eco/force/full-buy as dramatic stakes),
      clutch detection (1vX), team outcome resolution
- [ ] League of Legends adapter (Riot Match-V5 API)
- [ ] StarCraft II adapter (sc2reader)
- [ ] EPUB export

## Phase 2 — strategy & turn-based (Tier B + C) `v0.4 – v0.6`

- [ ] Civilization VI: autosave diffing (turn-by-turn deltas → events:
      wars, wonders, city captures, diplomacy). Turn number is the time axis.
- [ ] **Heroes of Might & Magic III**: no replay format exists, so this is
      the pilot for the **vision adapter** — periodic screenshots → VLM
      event extraction ("hero X besieged castle Y") merged with savegame
      parsing (h3sed-style save readers) for ground-truth resources/armies.
- [ ] Battle Brothers / tactics games: log scraping
- [ ] Generic Tier-C toolkit: capture daemon + VLM prompt library +
      confidence scoring, so any game can be supported at reduced fidelity

## Phase 3 — live & multiplayer (Tier D) `v0.7+`

- [ ] MMORPG combat-log adapter (WoW-style log tailing); session events
      stream into a persistent character memory store
- [ ] **Cross-session sagas**: one protagonist, many sessions, one novel —
      requires the memory/summarization layer (chapter = session,
      book = character arc)
- [ ] Real-time mode: incremental "war correspondent" drafts during play,
      re-woven into proper retrospective chapters after the session
- [ ] D&D / tabletop: VTT logs (Foundry/Roll20) and voice-transcript
      ingestion — the session *is already a story*; WhiteLee becomes the
      chronicler
- [ ] Multi-protagonist braided narratives (same match, five POVs,
      Rashomon mode)

## Phase 4 — creator tooling

- [ ] Style marketplace (community YAML profiles)
- [ ] Outline-only export for writers who want the plot skeleton, not prose
- [ ] Illustration hooks (scene descriptions → image models)
- [ ] Web UI

## Non-goals (for now)

- Cheating/coaching analytics — plenty of tools do this
- Video generation
- Anything requiring game-client injection that violates anti-cheat ToS.
  Extraction must stay on the safe side: official APIs, replay files,
  save files, screenshots, and log files only.
