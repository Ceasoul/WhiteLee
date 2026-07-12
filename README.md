# WhiteLee 白李

**Find the match worth writing. Then write it.**

WhiteLee turns real game sessions into literature — but unlike a mere
converter, it starts by telling you **whether a match deserves to be
written at all, and through whose eyes**. Emergent gameplay is a factory
for the most expensive raw material in fiction: causally coherent plots
nobody pre-authored. Most matches don't contain one. WhiteLee's scout
finds the ones that do.

> The name: White (白) + Lee (李), reversed — **李白**, the T'ang dynasty
> poet-swordsman who spent a lifetime turning battles and wanderings into
> verse. That is, literally, this program's job description.

## The scout says no before you spend a cent

```
$ whitelee dota2 8879557061 --pov 陆地神仙 --scout

SCORE + VERDICT
Score: 35/100
Verdict: MAYBE
Recommended re-run: --pov "myriamkemmerlbo"
HOOKS FOUND
- Nemesis arc settled: Slark fell to Legion Commander 3 times and answered with 3 kills.
- Hot hand: myriamkemmerlbo peaked at an 9-kill streak on Dawnbreaker.
RECOMMENDED POV
- 1. myriamkemmerlbo (Dawnbreaker, Radiant) | 66.0 | streak 9, K/D/A 17/2/18
- 2. 陆地神仙 (Slark, Radiant)              | 26.0 | K/D/A 9/5/16, incumbent bonus
...
```

Real output, real match. The scout scores nemesis arcs, comebacks,
god-streaks (超神), rampages (暴走), hubris beats (an enemy types "?" and
dies thirty seconds later — no novelist writes comeuppance that clean),
personal redemption/tragedy curves, and clutch buybacks. Stomps get
penalized: no adversity, no story. It also learned something we didn't
tell it: **the best player and the best protagonist are usually not the
same person.** A 17/2 godlike run is highlight-reel material; the 9/5
carry with a three-death blood feud against Legion Commander is the one
with a novel inside.

## What the prose looks like

From a real ranked match, wuxia style, protagonist Slark
(小鱼人"陆地神仙"), fifth chapter — the revenge kill on the Legion
Commander who had slain him three times:

> 陆地神仙伏在湿冷的河滩乱石之中,呼吸吐纳近乎于无。上一场在林间,他被那军团指挥官强行拉入"生死擂",重铠金戈之威至今震得他胸口隐隐作痛。那股屈辱与痛楚,如同附骨之疽,唯有以血洗之。……他身形如鬼魅般绕到她身后,鱼肠短刃带起一片幽绿的残影,噗嗤一声,已刺入她铠甲缝隙。

Every kill, death, objective and the final outcome are **facts from the
replay** — the model is only allowed to invent interiority: thoughts,
dialogue, atmosphere. Hard rules in the system prompt, enforced by an
output sanitizer, kept consistent across chapters by a generated
**terminology codex** (skill names and hero epithets fixed for the whole
book — editable JSON, reusable across a series).

## Quickstart

```bash
pip install -e .

# 1. Scout first (free, no LLM calls)
whitelee dota2 <match_id> --pov <your_nick> --scout

# 2. If the verdict says WRITE:
export WHITELEE_PROVIDER=openai_compatible          # or anthropic / openai
export WHITELEE_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
export WHITELEE_API_KEY=<key>
whitelee dota2 <match_id> --pov <your_nick> --style wuxia \
    --model gemini-3.5-flash --codex mybook.codex.json --format epub
```

Rate-limited? WhiteLee retries with the server's own backoff hints, and
checkpoints every finished chapter — rerun the same command tomorrow and
it resumes where it stopped. A free-tier API key can finish a book in
installments.

**Supported today:** Dota 2 (any parsed match on OpenDota, by match id)
and CS2 (local .dem via `pip install -e ".[cs2]"`).
**Styles:** `wuxia` 武侠 · `chronicle_zh` 史诗编年体 · `adventure` ·
`hardboiled` — plain YAML, add your own; `--style-sample your_essays.txt`
imitates your personal voice.

## Architecture

```
game source ──► Adapter ──► NarrativeEvent stream + MatchContext
                                   │
                     ┌─────────────┴─────────────┐
                  Scout (worth writing? whose POV?)
                     │
                  Planner (chapters, dramatic arc, turning points)
                     │
                  Styler (codex, style profile, checkpointed LLM calls)
                     │
                  novel.md / .epub
```

The narrative layer never sees game-specific data. **Adding a game =
writing one adapter** (`whitelee/adapters/base.py`, one method). The
scout consumes only generic events and a roster — a Civilization or
Crusader Kings adapter gets prospecting for free.

## Roadmap

Strategy & turn-based games (Civilization via save-diffing, Heroes of
Might & Magic III via a vision adapter), local .dem parsing for custom
lobbies and per-cast drama (the whiffed ult, the five-man Chronosphere),
MMORPG combat logs, cross-session sagas. See [ROADMAP.md](ROADMAP.md).

Built with an Architect/Implementer AI workflow —
the spec-and-review loop lives in the companion project **Conductor**.

## License

MIT. Player nicknames are part of the flavor; be kind when publishing
stories about real lobbies.
