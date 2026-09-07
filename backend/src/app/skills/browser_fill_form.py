"""browser_fill_form skill — fetch a URL, fill form fields, and optionally submit.

Uses httpx to fetch the HTML, parse form fields, and POST the filled values back.
For more complex JavaScript-heavy forms, a Playwright-based implementation is
recommended (can be swapped in via BROWSER_DRIVER env var = 'playwright').
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Annotated

import httpx
import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import (
    BrowserFillFormRequest,
    BrowserFillFormResponse,
    FormField,
)


log = structlog.get_logger()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class BrowserFillFormSkill(SkillExecutor[BrowserFillFormRequest, BrowserFillFormResponse]):
    slug = "browser_fill_form"

    async def execute(self, input_data: BrowserFillFormRequest) -> BrowserFillFormResponse:
        url = input_data.url.strip()

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(30.0, connect=10.0),
                headers=_HEADERS,
            ) as client:
                # 1. Fetch the page
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text

                # 2. Find the form and its action/method
                form_info = self._find_form(html, url)
                if form_info is None:
                    return BrowserFillFormResponse(
                        url=url,
                        filled_fields=[],
                        submitted=False,
                        success=False,
                        error="No form found on the page",
                    )

                action_url, method, field_names = form_info
                filled_fields: list[str] = []

                # 3. Build form data with the provided field values
                form_data: dict[str, str] = {}
                selectors_filled: list[str] = []

                # Match input_data.fields (selector → value) to form field names
                # If selector is a name= attribute, use it directly
                for field_def in input_data.fields:
                    selector = field_def.selector
                    value = field_def.value

                    # Try to match by name attribute
                    matched_name = self._match_selector_to_name(selector, field_names, html)
                    if matched_name:
                        form_data[matched_name] = value
                        selectors_filled.append(selector)
                    else:
                        # Fall back to selector as field name
                        form_data[selector] = value
                        selectors_filled.append(selector)

                filled_fields = selectors_filled

                # 4. Submit if requested
                submitted = False
                preview = None
                error = None

                if input_data.submit and method.upper() == "POST":
                    submitted, preview, error = await self._submit_form(
                        client, action_url, form_data
                    )
                else:
                    preview = self._strip_tags(html)[:2000]

                return BrowserFillFormResponse(
                    url=url,
                    filled_fields=filled_fields,
                    submitted=submitted,
                    success=not error,
                    error=error,
                    content_preview=preview,
                )

        except Exception as exc:
            log.error("browser_fill_form.failed", url=url, error=str(exc))
            return BrowserFillFormResponse(
                url=url,
                filled_fields=[],
                submitted=False,
                success=False,
                error=str(exc),
            )

    def _find_form(
        self, html: str, base_url: str
    ) -> tuple[str, str, list[str]] | None:
        """Extract form action, method, and field names from HTML."""
        form_match = re.search(r"<form[^>]*>", html, re.IGNORECASE)
        if not form_match:
            return None

        form_tag = form_match.group(0)

        # Get action
        action_match = re.search(r'action\s*=\s*["\']([^"\']*)["\']', form_tag, re.IGNORECASE)
        action = action_match.group(1) if action_match else base_url
        if action and not action.startswith(("http://", "https://")):
            action = urllib.parse.urljoin(base_url, action)

        # Get method
        method_match = re.search(r'method\s*=\s*["\'](\w+)["\']', form_tag, re.IGNORECASE)
        method = method_match.group(1).upper() if method_match else "GET"

        # Get field names
        field_names: list[str] = []
        for input_match in re.finditer(
            r'<input[^>]*name\s*=\s*["\']([^"\']*)["\'][^>]*>',
            html,
            re.IGNORECASE,
        ):
            name = input_match.group(1)
            if name and name not in field_names:
                field_names.append(name)

        return action, method, field_names

    def _match_selector_to_name(
        self, selector: str, field_names: list[str], html: str
    ) -> str | None:
        """Try to match a CSS selector (or bare name) to an actual field name."""
        # If selector looks like a bare name, try direct match
        if selector in field_names:
            return selector

        # Try matching by id= attribute
        id_match = re.search(
            rf'<input[^>]*id\s*=\s*["\']([^"\']*)["\'][^>]*name\s*=\s*["\']([^"\']*)["\']',
            html,
            re.IGNORECASE,
        )
        # Try the reverse: name then id
        for fm in re.finditer(
            r'<input[^>]*name\s*=\s*["\']([^"\']*)["\'][^>]*id\s*=\s*["\']([^"\']*)["\']',
            html,
            re.IGNORECASE,
        ):
            name, input_id = fm.group(1), fm.group(2)
            if selector == input_id or selector == f"#{input_id}":
                return name

        return None

    async def _submit_form(
        self,
        client: httpx.AsyncClient,
        action_url: str,
        form_data: dict[str, str],
    ) -> tuple[bool, str | None, str | None]:
        """POST the filled form data."""
        try:
            resp = await client.post(action_url, data=form_data)
            preview = self._strip_tags(resp.text)[:2000]
            return True, preview, None
        except Exception as exc:
            return False, None, str(exc)

    @staticmethod
    def _strip_tags(html: str) -> str:
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        return text.strip()


def get_executor() -> BrowserFillFormSkill:
    return BrowserFillFormSkill()
