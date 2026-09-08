"""web_search skill — Tavily + Google Search (SerpAPI) with stub fallback.

Provider priority (when source is not specified):
  1. Tavily  — set TAVILY_API_KEY
  2. Google  — set GOOGLE_SEARCH_API_KEY + GOOGLE_SEARCH_ENGINE_ID
  3. Stub    — clear placeholder when neither key is configured

Override with source="tavily" or source="google" in the skill call.
"""

from __future__ import annotations

import os
import structlog

import httpx

from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_TAVILY_URL = "https://api.tavily.com/search"
_GOOGLE_URL = "https://serpapi.com/search"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tavily_available() -> bool:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    return bool(key)


def _google_available() -> bool:
    key = os.environ.get("GOOGLE_SEARCH_API_KEY", "").strip()
    cx = os.environ.get("GOOGLE_SEARCH_ENGINE_ID", "").strip()
    return bool(key) and bool(cx)


def _stub_result(query: str) -> SkillResult:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return SkillResult(
        ok=True,
        data=[
            {
                "title": f"[STUB] No search provider configured — {query}",
                "url": "https://console.cloud.google.com/apis/credentials",
                "snippet": (
                    "Configure at least one search provider:\n"
                    "  • Tavily:        get a key at https://app.tavily.com\n"
                    "  • Google Search: get a key at https://serpapi.com (free tier)\n"
                    "Set TAVILY_API_KEY and/or GOOGLE_SEARCH_API_KEY + GOOGLE_SEARCH_ENGINE_ID "
                    "in your runtime .env file."
                ),
                "source": "stub",
                "published_date": now.isoformat(),
            }
        ],
        warning=(
            "web_search is running in stub mode. "
            "Set TAVILY_API_KEY (Tavily) or GOOGLE_SEARCH_API_KEY + GOOGLE_SEARCH_ENGINE_ID (Google) "
            "in the runtime .env file to enable real search results."
        ),
    )


# ---------------------------------------------------------------------------
# Tavily
# ---------------------------------------------------------------------------

async def _search_tavily(query: str, num_results: int, user_id: str) -> SkillResult:
    api_key = os.environ["TAVILY_API_KEY"].strip()
    params = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": num_results,
        "include_answer": False,
        "include_raw_content": False,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(_TAVILY_URL, json=params)
    except httpx.HTTPError as exc:
        log.error("web_search.tavily.network_error", user_id=user_id, error=str(exc))
        return SkillResult(ok=False, data=None, error=f"Failed to reach Tavily: {exc}")

    if resp.status_code == 401:
        return SkillResult(
            ok=False,
            data=None,
            error="Tavily API key is invalid or expired. Check TAVILY_API_KEY.",
        )
    if resp.status_code == 402:
        return SkillResult(
            ok=False,
            data=None,
            error="Tavily quota exceeded. Try again later or set GOOGLE_SEARCH_API_KEY as a fallback.",
        )
    if not resp.is_success:
        return SkillResult(ok=False, data=None, error=f"Tavily API error: {resp.status_code}")

    data = resp.json()
    results = []
    for item in data.get("results", [])[:num_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", "") or item.get("content", ""),
            "source": "tavily",
            "published_date": item.get("published_date"),
        })

    log.info(
        "web_search.tavily.done",
        user_id=user_id,
        query=query[:80],
        result_count=len(results),
    )
    return SkillResult(ok=True, data=results)


# ---------------------------------------------------------------------------
# Google Search via SerpAPI
# ---------------------------------------------------------------------------

async def _search_google(query: str, num_results: int, user_id: str) -> SkillResult:
    api_key = os.environ["GOOGLE_SEARCH_API_KEY"].strip()
    cx = os.environ["GOOGLE_SEARCH_ENGINE_ID"].strip()
    params = {
        "q": query,
        "num": min(num_results, 10),  # SerpAPI max 10 per page
        "start": 1,
        "api_key": api_key,
        "cx": cx,
        "hl": "en",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(_GOOGLE_URL, params=params)
    except httpx.HTTPError as exc:
        log.error("web_search.google.network_error", user_id=user_id, error=str(exc))
        return SkillResult(ok=False, data=None, error=f"Failed to reach Google Search: {exc}")

    if resp.status_code == 401:
        return SkillResult(
            ok=False,
            data=None,
            error="Google Search API key is invalid. Check GOOGLE_SEARCH_API_KEY.",
        )
    if resp.status_code == 429:
        return SkillResult(
            ok=False,
            data=None,
            error="Google Search rate limit exceeded. Try again later.",
        )
    if not resp.is_success:
        return SkillResult(ok=False, data=None, error=f"Google Search API error: {resp.status_code}")

    data = resp.json()
    results = []

    # SerpAPI returns organic results under "organic_results"
    for item in data.get("organic_results", [])[:num_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "source": "google",
            "published_date": item.get("date") if isinstance(item.get("date"), str) else None,
        })

    log.info(
        "web_search.google.done",
        user_id=user_id,
        query=query[:80],
        result_count=len(results),
    )
    return SkillResult(ok=True, data=results)


# ---------------------------------------------------------------------------
# Public skill function
# ---------------------------------------------------------------------------

async def web_search(
    query: str,
    num_results: int = 5,
    source: str | None = None,
    *,
    user_id: str,
) -> SkillResult:
    """Search the web using Tavily or Google Search.

    Args:
        query: The search query string.
        num_results: Number of results to return (default 5, max 20).
        source: Optional provider override — "tavily" or "google".
        user_id: for audit logging.

    Returns:
        SkillResult with a list of search results or a stub.
    """
    log.info(
        "web_search.invoked",
        user_id=user_id,
        query=query,
        num_results=num_results,
        source=source,
    )

    if not query or not query.strip():
        return SkillResult(ok=False, data=None, error="query cannot be empty")

    num_results = min(max(1, num_results), 20)

    # Explicit provider
    if source == "tavily":
        if not _tavily_available():
            return SkillResult(
                ok=False,
                data=None,
                error="source='tavily' requested but TAVILY_API_KEY is not set.",
            )
        return await _search_tavily(query, num_results, user_id)

    if source == "google":
        if not _google_available():
            return SkillResult(
                ok=False,
                data=None,
                error="source='google' requested but GOOGLE_SEARCH_API_KEY and/or GOOGLE_SEARCH_ENGINE_ID are not set.",
            )
        return await _search_google(query, num_results, user_id)

    # Auto-select: try Tavily first, then Google, then stub
    if _tavily_available():
        result = await _search_tavily(query, num_results, user_id)
        if result.ok:
            return result
        # Tavily failed — try Google as fallback
        log.warning("web_search.tavily.failed, trying google", user_id=user_id, error=result.error)

    if _google_available():
        result = await _search_google(query, num_results, user_id)
        if result.ok:
            return result
        log.warning("web_search.google.failed", user_id=user_id, error=result.error)

    # Nothing configured — return stub
    return _stub_result(query)
