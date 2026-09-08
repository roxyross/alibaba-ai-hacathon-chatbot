"""web_search skill — real search implementation using httpx + DuckDuckGo HTML."""

from __future__ import annotations

import os
import re
import urllib.parse
from typing import Annotated

import httpx
import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import SearchResult, WebSearchRequest, WebSearchResponse


log = structlog.get_logger()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class WebSearchSkill(SkillExecutor[WebSearchRequest, WebSearchResponse]):
    slug = "web_search"

    async def execute(self, input_data: WebSearchRequest) -> WebSearchResponse:
        query = input_data.query.strip()
        num = min(input_data.num_results, 20)
        source = (input_data.source or "tavily").lower()

        try:
            # 1. Try Tavily first if available
            tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
            if tavily_key and source in ("tavily", "duckduckgo", "google", ""):
                results = await self._tavily(query, num, tavily_key)
                if results:
                    return WebSearchResponse(
                        query=query,
                        results=results,
                        total_results=len(results),
                    )

            if source == "duckduckgo":
                results = await self._duckduckgo(query, num)
            elif source == "google":
                results = await self._google(query, num)
            elif source == "bing":
                results = await self._bing(query, num)
            else:
                results = await self._duckduckgo(query, num)

            return WebSearchResponse(
                query=query,
                results=results,
                total_results=len(results),
            )
        except Exception as exc:
            log.error("web_search.failed", query=query, source=source, error=str(exc))
            return WebSearchResponse(
                query=query,
                results=[],
                total_results=0,
            )

    async def _tavily(self, query: str, num: int, api_key: str) -> list[SearchResult]:
        """Query Tavily Search API for real-time web results."""
        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": num,
            "search_depth": "basic",
            "include_answer": True,
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            if resp.status_code != 200:
                log.warning("tavily.search.failed", status=resp.status_code, body=resp.text[:200])
                return []
            data = resp.json()

        results: list[SearchResult] = []
        # If Tavily synthesized a direct answer, include as top summary
        if data.get("answer"):
            results.append(
                SearchResult(
                    title="Quick Summary",
                    url="https://tavily.com",
                    snippet=data["answer"],
                    source="tavily",
                )
            )

        for item in data.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    source="tavily",
                )
            )
            if len(results) >= num:
                break

        return results

    async def _duckduckgo(self, query: str, num: int) -> list[SearchResult]:
        """Scrape DuckDuckGo HTML for search results (no API key required)."""
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()

        html = resp.text
        results: list[SearchResult] = []
        # DuckDuckGo HTML result pattern
        for match in re.finditer(
            r'<a class="result__a" href="([^"]+)"[^>]*>([^<]*)</a>',
            html,
        ):
            url_href = match.group(1)
            title = match.group(2).strip()
            if not url_href or not title or "duckduckgo" in url_href:
                continue
            # Snippet is in the next td
            snippet = ""
            snippet_match = re.search(
                re.escape(url_href) + r'[^<]*</a>\s*<a class="result__snippet"[^>]*>([^<]*)</a>',
                html,
            )
            if snippet_match:
                snippet = snippet_match.group(1).strip()
            results.append(
                SearchResult(
                    title=self._clean_html(title),
                    url=url_href,
                    snippet=self._clean_html(snippet),
                    source="duckduckgo",
                )
            )
            if len(results) >= num:
                break

        return results

    async def _google(self, query: str, num: int) -> list[SearchResult]:
        """Scrape Google search results (heuristic, may break with robots.txt)."""
        url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}&hl=en"
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()

        html = resp.text
        results: list[SearchResult] = []

        for match in re.finditer(
            r'<h3 class="zBAwLc[^"]*"[^>]*><a[^>]*href="([^"]+)"[^>]*>([^<]*)</a>',
            html,
        ):
            url_href = match.group(1)
            title = match.group(2).strip()
            if not url_href or not title:
                continue
            results.append(
                SearchResult(
                    title=self._clean_html(title),
                    url=url_href,
                    snippet="",
                    source="google",
                )
            )
            if len(results) >= num:
                break

        return results

    async def _bing(self, query: str, num: int) -> list[SearchResult]:
        """Scrape Bing search results."""
        url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}"
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()

        html = resp.text
        results: list[SearchResult] = []

        for match in re.finditer(
            r'<h2[^>]*><a href="([^"]+)"[^>]*>([^<]*)</a></h2>',
            html,
        ):
            url_href = match.group(1)
            title = match.group(2).strip()
            if not url_href or not title or "bing" in url_href.lower():
                continue
            results.append(
                SearchResult(
                    title=self._clean_html(title),
                    url=url_href,
                    snippet="",
                    source="bing",
                )
            )
            if len(results) >= num:
                break

        return results

    @staticmethod
    def _clean_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        return text.strip()


def get_executor() -> WebSearchSkill:
    return WebSearchSkill()
