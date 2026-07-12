"""Adapter contract.

To support a new game, subclass GameAdapter and implement extract().
That is the entire integration surface.

Adapter tiers (see ROADMAP.md):
  Tier A - structured replay/API   (Dota 2, CS2, LoL, StarCraft II)
  Tier B - save/log diffing        (Civilization, Total War, RimWorld)
  Tier C - vision (VLM screenshots) for games with no machine-readable
           trail (Heroes of Might & Magic III, older titles)
  Tier D - live log tailing        (MMORPG combat logs, streamed events)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from retale.core.schema import MatchContext, NarrativeEvent


@dataclass
class ExtractionResult:
    context: MatchContext
    events: list[NarrativeEvent]


class GameAdapter(ABC):
    """Turns one game session into (MatchContext, [NarrativeEvent])."""

    #: short id used on the CLI, e.g. "dota2"
    game_id: str = "base"

    @abstractmethod
    def extract(self, source: str, protagonist_hint: str | None = None) -> ExtractionResult:
        """Parse `source` (a match id, file path, or log path).

        protagonist_hint identifies whose POV the story takes:
        a player name, steam id, hero name, or civ name - adapter decides
        how to resolve it. If None, the adapter should pick the most
        active/likely player and record its choice in the context.
        """
        raise NotImplementedError

    # ---- shared helpers -------------------------------------------------

    @staticmethod
    def sort_events(events: list[NarrativeEvent]) -> list[NarrativeEvent]:
        return sorted(events, key=lambda e: e.t)
