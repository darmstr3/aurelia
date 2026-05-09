"""Tests for prompt builders.

We don't try to assert the LLM behaves a certain way — that's a regression
test for another day. We just check that the builders include the load-bearing
substrings we'd be unhappy to find missing in production.
"""

from __future__ import annotations

import pytest

from aurelia.intake import Urgency
from aurelia.prompts import greeting, system_prompt


@pytest.fixture
def prompt_text() -> str:
    return system_prompt(
        company_name="Northwind HVAC",
        business_hours="weekdays 7am-6pm",
        agent_name="Aurelia",
    )


def test_system_prompt_has_persona(prompt_text: str) -> None:
    assert "Aurelia" in prompt_text
    assert "Northwind HVAC" in prompt_text
    assert "weekdays 7am-6pm" in prompt_text


def test_system_prompt_lists_all_urgency_levels(prompt_text: str) -> None:
    for level in Urgency:
        assert level.value in prompt_text


def test_system_prompt_emergency_triage_keywords(prompt_text: str) -> None:
    # The emergency triggers we explicitly call out.
    for keyword in ("gas leak", "Carbon monoxide", "No heat in winter", "smoke"):
        assert keyword.lower() in prompt_text.lower()


def test_system_prompt_tool_discipline(prompt_text: str) -> None:
    assert "submit_intake" in prompt_text
    assert "exactly once" in prompt_text


def test_greeting_mentions_company_and_agent() -> None:
    line = greeting(company_name="Northwind HVAC", agent_name="Aurelia")
    assert "Northwind HVAC" in line
    assert "Aurelia" in line
    # Should end with a question to invite the caller to start.
    assert line.rstrip().endswith("?")
