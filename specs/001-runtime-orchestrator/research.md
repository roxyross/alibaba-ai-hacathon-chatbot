# Research: Web Search Provider for `web_search` Skill

**PR:** 3 | **Status:** Research (not implemented in PR 2)
**Agent:** Research Agent | **Skill:** `web_search`

---

## Providers Considered

### 1. Brave Search API

- **Free tier:** 2,000 queries/month
- **Privacy:** No user tracking; queries are not logged
- **Latency:** p50 < 200ms
- **Integration:** REST API, API key auth
- **Result shape:** `{ title, url, snippet, published_date }`
- **Pros:** Generous free tier, privacy-friendly, no Google dependency
- **Cons:** Requires API key (free); less comprehensive than Google

**Recommended for PR 3.**

### 2. SerpAPI (Google, Bing, etc.)

- **Free tier:** 100 searches/month
- **Privacy:** Queries logged; paid plans available
- **Latency:** p50 < 800ms
- **Integration:** API wrapper library; API key auth
- **Result shape:** Provider-specific
- **Pros:** Google/Bing/DuckDuckGo; feature-rich
- **Cons:** Expensive for higher volume; aggressive rate limits

### 3. Google Programmable Search

- **Free tier:** 100 queries/day
- **Privacy:** Google's standard privacy policy
- **Latency:** Variable
- **Integration:** Custom Search Engine; API key required
- **Pros:** Google's index
- **Cons:** Requires CSE setup; low free tier; Google branding

---

## Recommendation

**Brave Search API** — free, privacy-respecting, sufficient for the hackathon demo, and the Research Agent's needs (factual queries, news) are well-served by Brave's index.

**Decision to be formalized in ADR-003 (PR 3):** `ADR-003-web-search-provider.md` capturing the choice, tradeoffs, and provider key configuration.

---

## Implementation Notes

The `web_search` skill implementation will:

1. Accept the Brave Search API key from `BRAVE_SEARCH_API_KEY` env var
2. Call `https://api.search.brave.com/res/v1/web/search?q=...`
3. Transform Brave's `web.results[].title|url|description|page_age` to `SkillResult`
4. Handle 429 (rate limited) with exponential backoff (3 retries)
5. Handle 401/403 by surfacing "Brave API key invalid or revoked"
6. Log each search with query, result count, and latency in structlog

---

## Skill Contract (unchanged from SKILL.md)

```python
async def web_search(
    query: str,
    num_results: int = 10,
    recency: Literal["day", "week", "month", "year", "any"] = "any",
    site: str | None = None,
    *,
    user_id: str,
) -> SkillResult:
    ...
```

Returns `SkillResult(ok=True, data=[SearchResult(...)])` on success.

---

## Out of Scope for Provider Decision

- **Image search:** Not part of the Research Agent's v1 use case
- **News search:** Brave's web search already covers news results
- **Custom ranking:** Brave's ranking is applied; no custom re-ranking in PR 3
