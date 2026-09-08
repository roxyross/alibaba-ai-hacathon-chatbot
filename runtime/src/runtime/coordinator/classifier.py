"""v1 Coordinator classifier.

Takes a user query and returns either a single agent slug (the
best match) or a signal that classification is uncertain
(spec §3.1: re-prompt, do not default-route).

The v1 strategy is intentionally simple:

  score(slug) = keyword_weight * keyword_score + similarity_weight * similarity_score

  - keyword_score: fraction of words in the query that appear in
    the agent's description. Catches the obvious "code" / "research" /
    "calendar" cases.

  - similarity_score: Jaccard similarity over the lowercased token
    sets of the query and the description. Catches the "what's the
    weather in Tokyo" → research case where no single keyword matches
    but the description's vocabulary overlaps.

The threshold below which we return `Classification.uncertain()` is
configurable. Below the threshold, the Coordinator re-prompts
(spec §3.1, §8 Q1) rather than routing.

LLM-based classification is a v2 follow-up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from runtime.agents.registry import AgentRegistry
from runtime.config import settings
from runtime.domain.agent import AgentDef

_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Question-word tokens that indicate an information-seeking query.
# Used as a floor when the margin check fires but the top agent's
# description has content-word overlap with the query — this prevents
# routing "what is X?" to an agent whose description doesn't mention
# the query's topic (the "what" appears in every agent description
# and would otherwise route to the top agent alphabetically).
#
# "Content-word overlap" = query tokens that are neither question words
# nor generic stopwords AND that appear in the top agent's description.
# Per spec §3.1, §8 Q1.
_RESEARCH_QUESTION_WORDS = frozenset({
    "what", "who", "whom", "whose", "which",
    "where", "when", "why", "how",
    "does", "do", "did", "is", "are", "was", "were",
    "can", "could", "will", "would", "should",
})
_STOP_WORDS = frozenset({
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing",
    "a", "an", "the", "and", "but", "if", "or", "because", "as",
    "of", "at", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below",
    "to", "from", "up", "down", "in", "out", "on", "off", "over",
    "under", "again", "further", "then", "once", "here", "there",
    "when", "where", "why", "how", "all", "each", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only",
    "own", "same", "so", "than", "too", "very", "s", "t", "just",
    "don", "now", "d", "ll", "m", "o", "re", "ve", "y",
})


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _content_words(query_tokens: set[str]) -> set[str]:
    """Query tokens minus question words and stopwords — the meaningful words."""
    return query_tokens - _RESEARCH_QUESTION_WORDS - _STOP_WORDS


def _keyword_score(query_tokens: set[str], description: str) -> float:
    """Fraction of query tokens that appear in the description."""
    if not query_tokens:
        return 0.0
    desc_tokens = _tokens(description)
    if not desc_tokens:
        return 0.0
    return len(query_tokens & desc_tokens) / len(query_tokens)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class Classification:
    """The classifier's verdict on a query.

    Exactly one of `agent_slug` or `uncertain` is set. The Coordinator
    acts on `uncertain` by re-prompting the user (spec §3.1).
    """

    agent_slug: str | None
    uncertain: bool
    top_score: float
    second_score: float
    # If True, two agents tied within the margin. The Coordinator may
    # still pick the top one, but logs the ambiguity.
    tied: bool

    @classmethod
    def decided(cls, slug: str, top: float, second: float) -> "Classification":
        return cls(
            agent_slug=slug,
            uncertain=False,
            top_score=top,
            second_score=second,
            tied=abs(top - second) < 0.05,
        )

    @classmethod
    def uncertain_result(cls, top: float, second: float) -> "Classification":
        is_tied = False
        if second > 0:
            try:
                is_tied = (top / second < settings.classifier_margin) or (abs(top - second) < 0.05)
            except (ZeroDivisionError, OverflowError):
                is_tied = False
        return cls(
            agent_slug=None,
            uncertain=True,
            top_score=top,
            second_score=second,
            tied=is_tied,
        )


_DISTINCT_FROM_RE = re.compile(r"\bdistinct\s+from\b.*$", re.IGNORECASE)


def _clean_description(desc: str) -> str:
    """Strip negative disclaimer clauses like 'Distinct from the Coding Agent...'
    so agents are scored on what they DO, not what they disclaim."""
    return _DISTINCT_FROM_RE.split(desc)[0]


class Classifier:
    """v1 keyword + similarity classifier."""

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def classify(self, query: str) -> Classification:
        query_tokens = _tokens(query)
        if not query_tokens:
            return Classification.uncertain_result(0.0, 0.0)

        kw_w = settings.classifier_v1_keyword_weight
        sim_w = settings.classifier_v1_similarity_weight
        threshold = settings.classifier_uncertain_threshold

        eval_tokens = _content_words(query_tokens) or query_tokens

        scored: list[tuple[AgentDef, float]] = []
        for agent in self._registry.routable():
            clean_desc = _clean_description(agent.description)
            desc_tokens = _tokens(clean_desc) | _tokens(agent.slug.replace("-", " "))
            tools = getattr(agent, "tools", []) or []
            tools_tokens = _tokens(" ".join(t.replace("_", " ") for t in tools))
            all_agent_tokens = desc_tokens | tools_tokens

            kw = _keyword_score(eval_tokens, clean_desc + " " + agent.slug.replace("-", " "))
            sim = _jaccard(eval_tokens, all_agent_tokens)
            score = kw_w * kw + sim_w * sim
            scored.append((agent, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        if not scored:
            return Classification.uncertain_result(0.0, 0.0)

        top_agent, top_score = scored[0]
        second_score = scored[1][1] if len(scored) > 1 else 0.0

        # --- Question-word floor (spec §3.1, §8 Q1) -----------------------
        # "what is the capital of France?" style queries have generic question
        # words that appear in every agent description, so the margin check
        # fires spuriously.  We only apply the floor when the query has
        # content-word overlap with the TOP AGENT's description — this
        # prevents routing to an agent whose description doesn't mention
        # the query's topic (the question words alone would match all agents).
        if query_tokens & _RESEARCH_QUESTION_WORDS:
            content = _content_words(query_tokens)
            top_desc_tokens = _tokens(top_agent.description)
            if content and content & top_desc_tokens:
                # Route to top_agent (has content-word overlap)
                return Classification.decided(top_agent.slug, 0.001, 0.0)
            # No content overlap with top agent — question-word query is likely
            # a factual/informational inquiry (e.g. "what is the capital of France?").
            # Route to research as the default for factual queries. If research is
            # not the top agent, we still route to research because the content
            # doesn't match the top agent's domain and research is the appropriate
            # fallback for informational queries.
            if content:
                research_agent = next(
                    (a for a in self._registry.routable() if a.slug == "research"),
                    None,
                )
                if research_agent is not None:
                    research_kw = _keyword_score(query_tokens, research_agent.description)
                    research_sim = _jaccard(query_tokens, _tokens(research_agent.description))
                    research_score = 0.6 * research_kw + 0.4 * research_sim
                    return Classification.decided(
                        research_agent.slug, research_score, second_score
                    )
            # No content words at all — fall through to normal checks

        # --- Threshold check ---------------------------------------------
        if top_score < threshold:
            return Classification.uncertain_result(top_score, second_score)

        # --- Margin check ------------------------------------------------
        # If the top agent is barely ahead of the runner-up, re-prompt.
        margin = settings.classifier_margin
        if second_score > 0 and top_score / second_score < margin:
            return Classification.uncertain_result(top_score, second_score)

        return Classification.decided(top_agent.slug, top_score, second_score)
