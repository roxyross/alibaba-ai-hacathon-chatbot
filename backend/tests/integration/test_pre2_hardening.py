from __future__ import annotations

import sys
from typing import Any

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

from app.api.v1.runtime import (
    PRE_2_0_CONTEXT_MANDATE,
    check_search_or_weather_intent,
    load_agent_system_prompt,
)
from app.research.schemas import (
    DeepResearchResponse,
    ResearchFinding,
)


def test_deep_research_response_schema_structured_and_string_findings() -> None:
    """Verify that DeepResearchResponse supports both string and dictionary findings."""
    finding_obj = ResearchFinding(
        theme="Background",
        claim="Mir Raza's investigation background",
        confidence="high",
        source_indices=[0],
    )
    finding_dict: dict[str, Any] = {
        "theme": "Historical context",
        "claim": "Case details and records",
        "confidence": "high",
        "source_indices": [],
    }

    resp = DeepResearchResponse(
        topic="Mir Raza story",
        title="Investigation: Mir Raza story",
        summary="Executive summary of the case.",
        query="Mir Raza story",
        findings=[finding_obj.model_dump(), finding_dict, "Simple text finding"],
        sources=[{"title": "Archive", "url": "https://example.com"}],
        citations=["[1] Archive"],
        confidence="high",
        depth="deep",
        sub_queries=["mir raza background", "mir raza case overview"],
        next_actions=["Explore related archives"],
        report_id="rep-12345",
    )

    assert resp.query == "Mir Raza story"
    assert len(resp.findings) == 3
    first_finding: Any = resp.findings[0]
    assert isinstance(first_finding, dict)
    assert first_finding.get("theme") == "Background"
    second_finding: Any = resp.findings[1]
    assert isinstance(second_finding, dict)
    assert second_finding.get("theme") == "Historical context"
    assert resp.findings[2] == "Simple text finding"
    assert resp.confidence == "high"


def test_freshness_queries_trigger_search_intent() -> None:
    """Verify that freshness queries automatically trigger search intent without requiring manual prefix."""
    freshness_queries: list[str] = [
        "Latest AI news",
        "What's happening today?",
        "Current price of Bitcoin",
        "Who is currently the CEO of Twitter?",
        "Latest information about quantum computing",
    ]

    for q in freshness_queries:
        is_search, search_q, is_weather, _ = check_search_or_weather_intent(q)
        assert is_search, f"Query '{q}' should trigger search intent"
        assert search_q, f"Query '{q}' should have non-empty search query"


def test_conversational_follow_ups_do_not_trigger_search() -> None:
    """Verify that conversational follow-ups are preserved for context resolution rather than triggering external search."""
    follow_up_queries: list[str] = [
        "What happened after that?",
        "Make it shorter",
        "Explain that",
        "What about the second one?",
        "What did we discuss earlier?",
        "Tell me more about it",
    ]

    for q in follow_up_queries:
        is_search, _, _, _ = check_search_or_weather_intent(q)
        assert not is_search, f"Follow-up '{q}' should resolve from conversation context, not trigger external search"


def test_system_prompt_contains_pre2_mandates() -> None:
    """Verify that agent system prompt loads the Pre-2.0 contextual and factual integrity mandates."""
    prompt = load_agent_system_prompt("general")
    assert PRE_2_0_CONTEXT_MANDATE in prompt
    assert "CONVERSATIONAL CONTINUITY & CONTEXT RESOLUTION" in prompt
    assert "Resolve contextual references and pronouns" in prompt
    assert "FACTUAL INTEGRITY: CURRENT, HISTORICAL & FUTURE KNOWLEDGE" in prompt
    assert "DOCUMENTED, SCHEDULED, FORECAST, PREDICTION, or UNKNOWN" in prompt
    assert "Never claim supernatural powers or mind-reading" in prompt
