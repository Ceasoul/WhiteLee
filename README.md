# ReTale — 把你的游戏过程变成文学作品

**Turn your gameplay into literature.**

ReTale is a game-session-to-novel engine. Point it at a match you played —
a Dota 2 match id, a CS2 demo file — and it produces an adventure novel
told from *your* point of view, in a literary style you choose (or your own
personal voice, distilled from your writing samples).

它不是流水账日志：ReTale 会先重建整场比赛的**叙事弧**（开端、危机、高潮、
结局），再让 LLM 在"知道结局"的前提下逐章写作——因为好故事需要伏笔和张力，
而伏笔只有回望时才存在。

## Why / 为什么

Emergent gameplay is a factory for the most expensive raw material in
fiction: **causally coherent plots nobody pre-authored.** ReTale mines that
material — for players who want their matches remembered, and for writers
who want to short-circuit plotting by *playing* their way to a story.

## Quickstart

```bash
pip install -e .
export ANTHROPIC_API_KEY=sk-...        # or see Providers below

# Dota 2: any parsed match on OpenDota, by match id
retale dota2 8123456789 --pov "YourNick" --style wuxia -o saga.md

# CS2: local demo file (pip install -e .[cs2])
retale cs2 mymatch.dem --pov YourName --style hardboiled

# Inspect the chapter plan without spending tokens
retale dota2 8123456789 --dry-run
```

### Styles

Built-in: `adventure` (English), `hardboiled` (noir, first person),
`wuxia` (武侠，中文), `chronicle_zh` (史诗编年体，中文).

Styles are plain YAML in `styles/` — copy one, edit the prompt, done.
To imitate **your own voice**, pass a sample of your writing:

```bash
retale dota2 8123456789 --style adventure --style-sample my_essays.txt
```

### Providers

| env | value |
|---|---|
| `RETALE_PROVIDER` | `anthropic` (default) / `openai` / `openai_compatible` |
| `RETALE_MODEL` | override model name |
| `RETALE_BASE_URL` | for local models: Ollama, vLLM, DeepSeek endpoints |

## Architecture

```
game source ──► Adapter ──► NarrativeEvent stream + MatchContext
                                    │
                              Planner (chapters, arc roles, turning points)
                                    │
                              Styler (LLM, style profile, POV)
                                    │
                              novel.md
```

The narrative layer never sees game-specific data. **Adding a game =
writing one adapter** (`retale/adapters/base.py` is the whole contract).

### Hard rules baked into generation

1. Facts are sacred: every kill, death, objective and the final outcome
   must match the event data. The model invents *interiority* (thoughts,
   dialogue, atmosphere), never *outcomes*.
2. No game-UI jargon in prose — mechanics are translated into fiction.
3. Retrospective by design: chapters are written with the full outline
   in context, so early chapters can foreshadow the ending.

## Roadmap

See [ROADMAP.md](ROADMAP.md). Short version:

- **Phase 1 (now):** Tier-A games with structured replays — Dota 2 ✅, CS2 ✅,
  next: League of Legends, StarCraft II, Age of Empires IV
- **Phase 2:** strategy & tactics — Civilization VI (save diffing),
  Battle Brothers, and vision-based extraction (VLM screenshots) for games
  with no machine-readable trail: **Heroes of Might & Magic III**, classic
  titles
- **Phase 3:** live & multiplayer — MMORPG combat-log tailing (WoW-style
  logs), session-spanning sagas with persistent character memory,
  D&D / tabletop session transcripts
- **Phase 4:** EPUB/PDF export, illustrations, multi-protagonist braided
  narratives, community style marketplace

## Contributing

The most valuable contribution is a new adapter. Read
`retale/adapters/base.py` (the contract is one method), copy
`dota2_opendota.py` as a template, and open a PR with a fixture JSON +
test. Style profiles (any language, any genre) are equally welcome.

## License

MIT
