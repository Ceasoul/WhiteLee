"""Narrative planner.

Turns a flat event stream into a chapter plan with a dramatic arc.

Why plan before writing: good fiction needs to know the ending to place
foreshadowing and tension. So WhiteLee is retrospective by design - we
segment the whole match into beats, find turning points (importance
spikes and momentum reversals), then hand the LLM one chapter at a time
WITH the global outline, so each chapter is written knowing its place
in the arc.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from whitelee.core.schema import EventKind, MatchContext, NarrativeEvent

# Arc roles assigned to chapters by position + content
ARC_ROLES = ["opening", "rising", "midpoint", "crisis", "climax", "resolution"]


@dataclass
class Chapter:
    index: int
    title_hint: str
    arc_role: str
    t_start: float
    t_end: float
    events: list[NarrativeEvent] = field(default_factory=list)
    turning_point: NarrativeEvent | None = None

    def protagonist_events(self) -> list[NarrativeEvent]:
        return [e for e in self.events if e.protagonist_involved]


@dataclass
class StoryPlan:
    context: MatchContext
    chapters: list[Chapter]
    logline: str  # one-sentence summary of the whole story


class Planner:
    def __init__(self, target_chapters: int = 5, min_chapters: int = 3,
                 max_chapters: int = 9):
        self.target = target_chapters
        self.min_ch = min_chapters
        self.max_ch = max_chapters

    # ------------------------------------------------------------------
    def plan(self, context: MatchContext, events: list[NarrativeEvent]) -> StoryPlan:
        if not events:
            raise ValueError("No events to plan a story from.")
        events = sorted(events, key=lambda e: e.t)
        n_chapters = self._chapter_count(events)
        boundaries = self._boundaries(events, n_chapters)
        chapters = self._build_chapters(events, boundaries)
        self._assign_arc_roles(chapters)
        logline = self._logline(context, events)
        return StoryPlan(context=context, chapters=chapters, logline=logline)

    # ------------------------------------------------------------------
    def _chapter_count(self, events: list[NarrativeEvent]) -> int:
        # scale with narrative density, not raw duration
        weighty = sum(1 for e in events if e.importance >= 0.5)
        n = max(self.min_ch, min(self.max_ch, round(weighty / 6) + 2))
        return n

    def _boundaries(self, events: list[NarrativeEvent], n: int) -> list[float]:
        """Chapter boundaries at high-importance events, roughly evenly spaced."""
        t0, t1 = events[0].t, events[-1].t
        span = max(t1 - t0, 1e-9)
        ideal = [t0 + span * i / n for i in range(1, n)]
        candidates = [e for e in events if e.importance >= 0.5]
        bounds = []
        for tgt in ideal:
            if candidates:
                best = min(candidates, key=lambda e: abs(e.t - tgt))
                bounds.append(best.t)
            else:
                bounds.append(tgt)
        # dedupe & keep order
        out: list[float] = []
        for b in sorted(bounds):
            if not out or b - out[-1] > span * 0.05:
                out.append(b)
        return out

    def _build_chapters(self, events: list[NarrativeEvent],
                        bounds: list[float]) -> list[Chapter]:
        edges = [events[0].t] + bounds + [events[-1].t + 1e-9]
        chapters = []
        for i in range(len(edges) - 1):
            chunk = [e for e in events if edges[i] <= e.t < edges[i + 1]]
            if not chunk:
                continue
            tp = max(chunk, key=lambda e: (e.importance, e.protagonist_involved))
            chapters.append(Chapter(
                index=len(chapters) + 1,
                title_hint=tp.summary[:80],
                arc_role="",
                t_start=chunk[0].t, t_end=chunk[-1].t,
                events=chunk, turning_point=tp))
        return chapters

    def _assign_arc_roles(self, chapters: list[Chapter]) -> None:
        n = len(chapters)
        for i, ch in enumerate(chapters):
            if i == 0:
                ch.arc_role = "opening"
            elif i == n - 1:
                ch.arc_role = "resolution"
            elif i == n - 2:
                ch.arc_role = "climax"
            else:
                # setbacks in the middle read as crisis, otherwise rising
                has_setback = any(e.kind in (EventKind.SETBACK, EventKind.DEATH)
                                  and e.protagonist_involved for e in ch.events)
                ch.arc_role = "crisis" if has_setback and i >= n // 2 else "rising"

    @staticmethod
    def _logline(context: MatchContext, events: list[NarrativeEvent]) -> str:
        hero = context.protagonist.persona or context.protagonist.name
        kills = sum(1 for e in events
                    if e.kind == EventKind.KILL and e.protagonist_involved)
        deaths = sum(1 for e in events
                     if e.kind == EventKind.DEATH and e.protagonist_involved)
        return (f"{hero} fights through {len(events)} recorded moments "
                f"({kills} triumphs, {deaths} falls) toward "
                f"{context.outcome} in {context.game}.")
