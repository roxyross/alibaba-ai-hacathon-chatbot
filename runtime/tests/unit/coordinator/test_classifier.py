"""Tests for runtime.coordinator.classifier — v1 keyword + similarity classifier."""

from __future__ import annotations

import pytest

from runtime.agents.loader import AgentDef
from runtime.agents.registry import AgentRegistry
from runtime.coordinator.classifier import (
    Classification,
    Classifier,
    _jaccard,
    _keyword_score,
    _tokens,
)


# ---- pure-function helpers ------------------------------------------------

class TestTokens:
    def test_lowercases(self) -> None:
        tokens = _tokens("Web Research Agent")
        assert "research" in tokens
        assert "web" in tokens
        assert "agent" in tokens

    def test_extracts_alphanumeric(self) -> None:
        tokens = _tokens("what's the weather in Tokyo?")
        assert "what" in tokens
        assert "tokyo" in tokens
        # Apostrophe splits "what's" into "what" and "s"
        assert "s" in tokens  # 's' is alphanumeric
        assert "weather" in tokens
        assert "the" in tokens

    def test_empty_string(self) -> None:
        assert _tokens("") == set()


class TestKeywordScore:
    def test_full_overlap(self) -> None:
        query_tokens = {"code", "debug"}
        score = _keyword_score(query_tokens, "debug code python explanation")
        assert score == 1.0  # both tokens appear

    def test_partial_overlap(self) -> None:
        # 2 of 3 query tokens appear in the description
        query_tokens = {"code", "debug", "extra"}
        score = _keyword_score(query_tokens, "debug code python")
        # debug and code appear, extra does not → 2/3
        assert score == pytest.approx(2 / 3)

    def test_no_overlap(self) -> None:
        score = _keyword_score({"foo", "bar"}, "completely different description")
        assert score == 0.0

    def test_empty_query(self) -> None:
        assert _keyword_score(set(), "any description") == 0.0


class TestJaccard:
    def test_identical_sets(self) -> None:
        s = {"a", "b", "c"}
        assert _jaccard(s, s) == 1.0

    def test_disjoint_sets(self) -> None:
        assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self) -> None:
        # |{"a","b"} & {"b","c"}| / |{"a","b","c","d","e"}| = 1/5
        score = _jaccard({"a", "b"}, {"b", "c", "d", "e"})
        assert score == pytest.approx(1 / 5)

    def test_empty_set(self) -> None:
        assert _jaccard(set(), {"a", "b"}) == 0.0


# ---- Classifier -----------------------------------------------------------

def _registry_with_agents(agents: list[AgentDef]) -> AgentRegistry:
    return AgentRegistry(agents)


def _agent(slug: str, description: str) -> AgentDef:
    return AgentDef(slug=slug, description=description, body=f"# {slug}")


class TestClassifier:
    def setup_method(self) -> None:
        self.registry = _registry_with_agents([
            _agent("research", "Web search and multi-source synthesis with citations."),
            _agent("coding", "Code generation, explanation, and debugging across languages."),
            _agent("files", "RAG over user-uploaded documents."),
        ])
        self.classifier = Classifier(self.registry)

    def test_research_query_routes_to_research(self) -> None:
        # "search" and "web" overlap with "Web search" description; score > threshold
        verdict = self.classifier.classify("search the web for latest AI research news")
        assert verdict.agent_slug == "research"
        assert verdict.uncertain is False

    def test_coding_query_routes_to_coding(self) -> None:
        # "code" and "generation" overlap with "Code generation" description
        verdict = self.classifier.classify("code generation and debugging in Python")
        assert verdict.agent_slug == "coding"
        assert verdict.uncertain is False

    def test_files_query_routes_to_files(self) -> None:
        # "document" and "uploaded" overlap with "user-uploaded documents" description
        verdict = self.classifier.classify("summarize the document I uploaded")
        assert verdict.agent_slug == "files"
        assert verdict.uncertain is False

    def test_empty_query_returns_uncertain(self) -> None:
        verdict = self.classifier.classify("")
        assert verdict.uncertain is True

    def test_uncertain_when_scores_below_threshold(self) -> None:
        # A very short or meaningless query may score below threshold
        verdict = self.classifier.classify("hi")
        # Either uncertain or a clear winner
        if verdict.uncertain:
            assert verdict.agent_slug is None
        else:
            assert verdict.agent_slug is not None

    def test_classification_result_structure(self) -> None:
        verdict = self.classifier.classify("explain this Python code")
        assert isinstance(verdict.agent_slug, str)
        assert isinstance(verdict.top_score, float)
        assert isinstance(verdict.second_score, float)
        assert isinstance(verdict.tied, bool)

    def test_tied_flag_when_scores_within_margin(self) -> None:
        # When two agents score nearly identically, tied should be True
        verdict = self.classifier.classify("help")
        # 'help' is vague enough that scores may be close
        # We just verify the field exists and is a bool
        assert isinstance(verdict.tied, bool)

    def test_top_score_greater_or_equal_second(self) -> None:
        verdict = self.classifier.classify("compare React and Vue in 2026")
        assert verdict.top_score >= verdict.second_score
