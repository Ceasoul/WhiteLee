"""ReTale core schema.

Every game adapter must emit a stream of NarrativeEvent objects plus a
MatchContext. The narrative engine only ever sees these two types, which
is what makes ReTale game-agnostic: adding a new game means writing one
adapter, never touching the narrative layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EventKind(str, Enum):
    """Game-agnostic event vocabulary.

    Deliberately small. Adapters map hundreds of game-specific event
    types onto this vocabulary; nuance goes into `data` and `summary`.
    """

    MATCH_START = "match_start"
    MATCH_END = "match_end"
    PHASE = "phase"              # round start/end, new turn, new day, boss phase
    KILL = "kill"                # actor eliminated target
    DEATH = "death"              # protagonist (or ally) died
    OBJECTIVE = "objective"      # tower/bomb plant/city captured/quest done
    ACQUISITION = "acquisition"  # item purchase, loot, tech researched, level up
    MOVEMENT = "movement"        # rotation, retreat, exploration
    ECONOMY = "economy"          # gold swing, resource crisis
    SOCIAL = "social"            # chat, ping, trade, diplomacy, guild event
    SETBACK = "setback"          # lost fight, lost city, wipe
    TRIUMPH = "triumph"          # won fight, ace, wonder built
    AMBIENT = "ambient"          # flavor: weather, map events, background


@dataclass
class NarrativeEvent:
    """One thing that happened, from the game's point of view."""

    t: float                     # seconds (or turn number) from match start
    kind: EventKind
    actor: Optional[str] = None      # canonical entity name ("protagonist" allowed)
    target: Optional[str] = None
    summary: str = ""                # short factual sentence, e.g. "Juggernaut killed Lion mid lane"
    importance: float = 0.3          # 0..1, adapter's estimate of narrative weight
    protagonist_involved: bool = False
    data: dict[str, Any] = field(default_factory=dict)  # raw game-specific payload

    def __post_init__(self) -> None:
        self.importance = max(0.0, min(1.0, self.importance))


@dataclass
class Protagonist:
    """Who the story is about."""

    name: str                        # in-game handle
    persona: str = ""                # role/class/civ, e.g. "Juggernaut, carry"
    traits: list[str] = field(default_factory=list)  # optional player-supplied traits


@dataclass
class MatchContext:
    """Everything the narrative engine needs beyond the event stream."""

    game: str                        # "dota2", "cs2", "civ6", ...
    protagonist: Protagonist
    outcome: str = "unknown"         # "victory" | "defeat" | "draw" | "unknown"
    duration: float = 0.0            # seconds or turns
    world: dict[str, Any] = field(default_factory=dict)   # map name, factions, teams
    allies: list[str] = field(default_factory=list)
    opponents: list[str] = field(default_factory=list)

    def time_unit(self) -> str:
        return self.world.get("time_unit", "seconds")
