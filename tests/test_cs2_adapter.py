"""Tests for the CS2 adapter using synthetic demoparser2 outputs."""

from __future__ import annotations

import importlib
import sys
import types

from retale.adapters.cs2_demo import CS2DemoAdapter
from retale.core.schema import EventKind


def _frame(rows: list[dict], columns: list[str] | None = None):
    import pandas as pd

    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=columns or [])


def _round_rows(winners: list[object]) -> list[dict]:
    return [
        {"round_num": index, "tick": float(index * 6400), "winner": winner}
        for index, winner in enumerate(winners, start=1)
    ]


def _install_fake_demoparser(monkeypatch, header: dict, kills_rows: list[dict], round_winners: list[object]):
    fake_module = types.ModuleType("demoparser2")
    events = {
        "player_death": _frame(kills_rows),
        "round_end": _frame(_round_rows(round_winners)),
        "bomb_planted": _frame([], columns=["tick", "user_name"]),
        "bomb_defused": _frame([], columns=["tick", "user_name"]),
    }

    class DemoParser:
        def __init__(self, source: str):
            self.source = source

        def parse_header(self) -> dict:
            return header

        def parse_event(self, name: str):
            return events[name]

    fake_module.DemoParser = DemoParser
    monkeypatch.setitem(sys.modules, "demoparser2", fake_module)


def test_cs2_module_imports_without_demoparser(monkeypatch):
    monkeypatch.delitem(sys.modules, "demoparser2", raising=False)
    module = importlib.reload(importlib.import_module("retale.adapters.cs2_demo"))
    assert module.CS2DemoAdapter.game_id == "cs2"


def test_cs2_adapter_victory_clutch_and_match_point(monkeypatch):
    round_winners = [2] * 6 + [3] * 6 + [3] * 7 + [2] * 5
    kills_rows = [
        {
            "round_num": 1,
            "tick": 640.0,
            "attacker_name": "Hero",
            "attacker_team_name": "T",
            "user_name": "Enemy1",
            "user_team_name": "CT",
            "headshot": False,
            "weapon": "ak47",
        },
        {
            "round_num": 13,
            "tick": 13 * 6400 + 640.0,
            "attacker_name": "Hero",
            "attacker_team_name": "CT",
            "user_name": "Enemy2",
            "user_team_name": "T",
            "headshot": False,
            "weapon": "m4a1_silencer",
        },
        {
            "round_num": 19,
            "tick": 19 * 6400 + 100.0,
            "attacker_name": "Enemy3",
            "attacker_team_name": "T",
            "user_name": "Ally1",
            "user_team_name": "CT",
            "headshot": False,
            "weapon": "ak47",
        },
        {
            "round_num": 19,
            "tick": 19 * 6400 + 200.0,
            "attacker_name": "Hero",
            "attacker_team_name": "CT",
            "user_name": "Enemy4",
            "user_team_name": "T",
            "headshot": True,
            "weapon": "m4a1_silencer",
        },
        {
            "round_num": 19,
            "tick": 19 * 6400 + 300.0,
            "attacker_name": "Hero",
            "attacker_team_name": "CT",
            "user_name": "Enemy5",
            "user_team_name": "T",
            "headshot": False,
            "weapon": "m4a1_silencer",
        },
        {
            "round_num": 19,
            "tick": 19 * 6400 + 400.0,
            "attacker_name": "Enemy6",
            "attacker_team_name": "T",
            "user_name": "Ally2",
            "user_team_name": "CT",
            "headshot": False,
            "weapon": "ak47",
        },
        {
            "round_num": 19,
            "tick": 19 * 6400 + 500.0,
            "attacker_name": "Hero",
            "attacker_team_name": "CT",
            "user_name": "Enemy7",
            "user_team_name": "T",
            "headshot": False,
            "weapon": "m4a1_silencer",
        },
    ]
    _install_fake_demoparser(
        monkeypatch,
        header={"map_name": "de_ancient"},
        kills_rows=kills_rows,
        round_winners=round_winners,
    )

    extraction = CS2DemoAdapter().extract("synthetic.dem", protagonist_hint="Hero")
    phase_summaries = [event.summary for event in extraction.events if event.kind == EventKind.PHASE]
    clutch_events = [event for event in extraction.events if event.summary == "Hero clutches the round."]

    assert extraction.context.outcome == "victory"
    assert any(summary == "Round 13 goes to the CTs (7-6)" for summary in phase_summaries)
    assert any("match point" in summary for summary in phase_summaries)
    assert len(clutch_events) == 1
    assert clutch_events[0].importance == 0.85


def test_cs2_adapter_defeat_case(monkeypatch):
    round_winners = ["CT"] * 5 + ["T"] * 7 + ["T"] * 6 + ["CT"] * 6
    kills_rows = [
        {
            "round_num": 1,
            "tick": 640.0,
            "attacker_name": "Enemy1",
            "attacker_team_name": "T",
            "user_name": "Hero",
            "user_team_name": "CT",
            "headshot": False,
            "weapon": "ak47",
        },
        {
            "round_num": 13,
            "tick": 13 * 6400 + 640.0,
            "attacker_name": "Hero",
            "attacker_team_name": "T",
            "user_name": "Enemy2",
            "user_team_name": "CT",
            "headshot": False,
            "weapon": "ak47",
        },
    ]
    _install_fake_demoparser(
        monkeypatch,
        header={"map_name": "de_nuke"},
        kills_rows=kills_rows,
        round_winners=round_winners,
    )

    extraction = CS2DemoAdapter().extract("synthetic.dem", protagonist_hint="Hero")

    assert extraction.context.outcome == "defeat"


def test_cs2_adapter_marks_overtime_start(monkeypatch):
    round_winners = [2, 3] * 12
    kills_rows = [
        {
            "round_num": 1,
            "tick": 640.0,
            "attacker_name": "Hero",
            "attacker_team_name": "T",
            "user_name": "Enemy1",
            "user_team_name": "CT",
            "headshot": False,
            "weapon": "ak47",
        }
    ]
    _install_fake_demoparser(
        monkeypatch,
        header={"map_name": "de_mirage"},
        kills_rows=kills_rows,
        round_winners=round_winners,
    )

    extraction = CS2DemoAdapter().extract("synthetic.dem", protagonist_hint="Hero")
    phase_summaries = [event.summary for event in extraction.events if event.kind == EventKind.PHASE]

    assert extraction.context.outcome == "draw"
    assert "Overtime begins at 12-12." in phase_summaries
