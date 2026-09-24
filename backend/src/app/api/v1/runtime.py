"""Runtime Router — Coordinator agent orchestration.

POST /api/v1/runtime/chat  — one-shot Coordinator routing with optional Critic pre-flight.
POST /api/v1/runtime/chat/stream  — streaming Coordinator with Critic pre-flight on final chunk.

The Coordinator classifies user intent, routes to the appropriate specialist agent,
and optionally runs a silent Critic pre-flight review on specialist responses.

Agent definitions live in .claude/agents/<slug>.md and are loaded at startup.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC
from pathlib import Path
from typing import Any

import httpx
import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.ai_gateway.models.schemas import AIRequest, AIResponse, Message, MessageRole
from app.ai_gateway.services.router import AIRouter
from app.auth.dependencies import get_current_user, get_optional_current_user
from app.auth.models import User
from app.skills.critic_review import get_executor as critic_review_executor
from app.skills.document_rag_query import DocumentRAGSkill
from app.skills.schemas import CriticReviewRequest

log = structlog.get_logger()

router = APIRouter(prefix="/runtime", tags=["runtime"])

# Path to agent definition files (relative to repo root)
_AGENTS_DIR = Path(__file__).resolve().parents[4] / ".claude" / "agents"


# ---------------------------------------------------------------------------
# Intent classification — keyword-based router
# ---------------------------------------------------------------------------

# Finance keywords (money, bank, budget, spending, expenses, income, savings)
_FINANCE_PATTERNS = [
    re.compile(r"\b(bank|balance|bank\s*account|financial\s*account|transactions?|transfer)\b", re.I),
    re.compile(r"\b(budget|budgeting|spending|expenses?|expense)\b", re.I),
    re.compile(r"\b(income|salary|wages|earnings|savings)\b", re.I),
    re.compile(r"\b(credit.debit|card|loan|mortgage)\b", re.I),
    re.compile(r"\b(net.worth|financial|finances?|money)\b", re.I),
    re.compile(r"\b(bill|bills|pay|payment|due)\b", re.I),
]

# Critic keywords
_CRITIC_PATTERNS = [
    re.compile(r"\b(critique|critic|review|evaluate|assess|analyze)\b", re.I),
    re.compile(r"\b(opinion|second.opinion|feedback)\b", re.I),
    re.compile(r"\b(pros.cons|pros and cons|strengths?.*weaknesses?)\b", re.I),
]

# Automation keywords
_AUTOMATION_PATTERNS = [
    re.compile(r"\b(remind|reminder|schedule|recurring|daily|weekly|monthly)\b", re.I),
    re.compile(r"\b(every.morning|every.week|every.day|alarm|alert)\b", re.I),
    re.compile(r"\b(cron|定时|自动)\b", re.I),
]

# Workspace keywords
_WORKSPACE_PATTERNS = [
    re.compile(r"\b(project|projects|workspace|workspaces|milestones?|kanban)\b", re.I),
    re.compile(r"\b(action\s*item|action\s*items|deliverables?|deliverable)\b", re.I),
]

# Email keywords
_EMAIL_PATTERNS = [
    re.compile(r"\b(email|emails|outbox|drafts?|compose\s*email|send\s*email|write\s*email)\b", re.I),
    re.compile(r"\b(mail\s*to|sent\s*mail|email\s*draft|email\s*message)\b", re.I),
]

# Voice & Audio keywords
_VOICE_PATTERNS = [
    re.compile(r"\b(voice\s*notes?|voice\s*recordings?|audio\s*recordings?|voice\s*transcripts?|audio\s*notes?)\b", re.I),
    re.compile(r"\b(transcribe|speech\s*to\s*text|text\s*to\s*speech|voice\s*session|audio\s*intelligence)\b", re.I),
]

# Research keywords
_RESEARCH_PATTERNS = [
    re.compile(r"\b(what.is|who.is|when.did|where.is|how.do)\b", re.I),
    re.compile(r"\b(search|look.up|find.information|research)\b", re.I),
    re.compile(r"\b(news|recent|latest|updated)\b", re.I),
]

# Coding keywords
_CODING_PATTERNS = [
    re.compile(r"\b(write.code|write.function|implement|debug|fix.bug)\b", re.I),
    re.compile(r"\b(code|python|javascript|typescript|java|rust|golang)\b", re.I),
    re.compile(r"\b(api|endpoint|function|class|module|import)\b", re.I),
    re.compile(r"\b(sql|query|database|table|schema)\b", re.I),
]

# Study keywords
_STUDY_PATTERNS = [
    re.compile(r"\b(flashcard|flashcards|study|quiz|quizzes|learn|memorize|revision|recall)\b", re.I),
    re.compile(r"\b(spaced.repetition|leitner|study.deck|study.guide|exam.prep|practice.quiz|test.me)\b", re.I),
    re.compile(r"\b(chapter|course|lecture|textbook)\b", re.I),
]

# Browser keywords
_BROWSER_PATTERNS = [
    re.compile(r"\b(browse|navigate|go.to|open.website|visit|browser)\b", re.I),
    re.compile(r"\b(fill.form|submit.form|login|download|extract.table|inspect.dom|web.automation|browser.task)\b", re.I),
]

# Semantic memory keywords
_MEMORY_PATTERNS = [
    re.compile(r"\b(remember|recall|memories|memory|memorized)\b", re.I),
    re.compile(r"\b(preference|preferences|prefer|preferred)\b", re.I),
    re.compile(r"\b(don't\s+forget|do\s+not\s+forget|forget\s+that|forget\s+my)\b", re.I),
    re.compile(r"\b(curator|curate|pruning|prune)\b", re.I),
]

# Audit and security activity keywords
_AUDIT_PATTERNS = [
    re.compile(r"\b(audit|audit\s*log|audit\s*trail|activity\s*log|security\s*log|history\s*of\s*actions)\b", re.I),
    re.compile(r"\b(what\s+did\s+(you|jarvis|roxy)\s+do\s+(today|recently))\b", re.I),
    re.compile(r"\b(what\s+actions\s+have\s+been\s+taken|what\s+actions\s+did\s+you\s+perform)\b", re.I),
    re.compile(r"\b(actions\s+today|events\s+today|security\s+review)\b", re.I),
]

# Billing, payments and subscription keywords
_BILLING_PATTERNS = [
    re.compile(r"\b(billing|subscription|subscribed|subscribing|invoice|invoices|ai\s*credits|credit\s*wallet|top-?up|upgrade\s*plan|pricing\s*plan|payment\s*method|payment\s*methods)\b", re.I),
    re.compile(r"\b(what\s+is\s+my\s+plan|what\s+plan\s+am\s+i\s+on|how\s+many\s+credits|check\s+my\s+credits|my\s+subscription|cancel\s+subscription)\b", re.I),
]

# Calendar, meetings and event scheduling keywords
_CALENDAR_PATTERNS = [
    re.compile(r"\b(calendar|appointment|appointments|event|events|meeting|meetings|agenda|reschedule|ics|icalendar)\b", re.I),
    re.compile(r"\b(what\s+is\s+on\s+my\s+calendar|what\s+do\s+i\s+have\s+(today|tomorrow|scheduled)|upcoming\s+meetings|upcoming\s+events|my\s+schedule|am\s+i\s+free)\b", re.I),
]


# Image generation keywords
_IMAGE_PATTERNS = [
    re.compile(r"\b(create|generate|make|draw|show|render)\s+(an?\s+)?image\s+(of|about|with)?\b", re.I),
    re.compile(r"\b(create|generate|make|draw|show)\s+(a\s+)?picture\s+(of|about|with)?\b", re.I),
    re.compile(r"\b(image\s+of|photo\s+of|painting\s+of|picture\s+of)\b", re.I),
    re.compile(r"^create\s+an?\s+image\s*:\s*", re.I),
]

# Image studio gallery keywords
_IMAGE_STUDIO_PATTERNS = [
    re.compile(r"\b(image\s*gallery|my\s*images|generated\s*images|artwork|saved\s*images|image\s*studio)\b", re.I),
]


def check_image_intent(message: str) -> tuple[bool, str]:
    """Check if message is requesting image generation and extract the subject."""
    msg = message.strip()
    for p in _IMAGE_PATTERNS:
        match = p.search(msg)
        if match:
            extracted = p.sub("", msg).strip().strip(":").strip()
            if not extracted or len(extracted) < 2:
                extracted = msg
            return True, extracted
    return False, ""


def generate_image_response(prompt: str) -> str:
    """Generate high-resolution image markdown using neural diffusion."""
    import urllib.parse
    cleaned = prompt.strip()
    encoded = urllib.parse.quote(cleaned)
    image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&enhance=true"
    return (
        f"Here is your generated image of **{cleaned}**:\n\n"
        f"![{cleaned}]({image_url})\n\n"
        f"*Generated using high-resolution neural diffusion synthesis.*"
    )


_SEARCH_PREFIXES = [
    re.compile(r"^(?:search\s+(?:the\s+)?web\s+for|web\s+search\s+for|google\s+search\s+for|look\s+up|search\s+for)\s*:\s*", re.I),
    re.compile(r"^(?:search\s+(?:the\s+)?web\s+for|web\s+search\s+for|google\s+search\s+for)\s+", re.I),
]

_WEATHER_KEYWORDS = re.compile(
    r"\b(weather|forecast|temperature|degrees|raining|rainy|sunny|snowing|humidity|wind\s+speed)\b",
    re.I,
)

_WEATHER_CODES: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Foggy", "🌫️"),
    48: ("Depositing rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Moderate drizzle", "🌦️"),
    55: ("Dense drizzle", "🌧️"),
    61: ("Slight rain", "🌧️"),
    63: ("Moderate rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    66: ("Freezing rain", "🌨️"),
    67: ("Heavy freezing rain", "🌨️"),
    71: ("Slight snowfall", "❄️"),
    73: ("Moderate snowfall", "❄️"),
    75: ("Heavy snowfall", "❄️"),
    77: ("Snow grains", "❄️"),
    80: ("Slight rain showers", "🌧️"),
    81: ("Moderate rain showers", "🌧️"),
    82: ("Violent rain showers", "⛈️"),
    85: ("Slight snow showers", "🌨️"),
    86: ("Heavy snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm with slight hail", "⛈️"),
    99: ("Thunderstorm with heavy hail", "⛈️"),
}


def extract_city_from_query(query: str) -> str:
    s = query
    for pat in [
        r"^(?:search\s+(?:the\s+)?web\s+for|web\s+search\s+for|google\s+search\s+for|look\s+up|search\s+for|search)\s*:\s*",
        r"\b(?:what\s+is|how\s+is|tell\s+me|show\s+me|check|give\s+me)\b",
        r"\b(?:the|current|today|tomorrow|this\s+week|right\s+now)\b",
        r"\b(?:weather|forecast|temperature|humidity|conditions?)\b",
        r"\b(?:in|at|for|around|near|of|like)\b",
    ]:
        s = re.sub(pat, " ", s, flags=re.I)
    cleaned = re.sub(r"[^\w\s\-,]", " ", s).strip()
    words = [w for w in cleaned.split() if len(w) > 1]
    return " ".join(words)


def check_search_or_weather_intent(message: str) -> tuple[bool, str, bool, str]:
    """Check if message is a web search or weather inquiry.
    Returns (is_search_or_weather, search_query, is_weather, city_name).
    """
    msg = message.strip()
    is_search_prefix = False
    clean_query = msg

    for p in _SEARCH_PREFIXES:
        if p.search(msg):
            clean_query = p.sub("", msg).strip().strip(":").strip()
            is_search_prefix = True
            break

    is_weather = bool(_WEATHER_KEYWORDS.search(msg))
    city = extract_city_from_query(clean_query if is_search_prefix else msg)

    is_search = is_search_prefix or is_weather
    return is_search, clean_query or msg, is_weather, city


async def fetch_live_weather(city_name: str) -> str | None:
    """Fetch live meteorological data from Open-Meteo (real-time, free, global)."""
    target_city = city_name.strip() or "Tokyo"
    headers = {
        "User-Agent": "ROXY-Agent/1.0",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(target_city)}&count=1"
            geo_res = await client.get(geo_url, headers=headers)
            if geo_res.status_code != 200:
                return None
            geo_data = geo_res.json()
            results = geo_data.get("results", [])
            if not results:
                return None

            loc = results[0]
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            place_name = loc.get("name", target_city)
            country = loc.get("country", "")
            admin = loc.get("admin1", "")
            full_place = f"{place_name}, {admin}, {country}".replace(", ,", ",").strip(", ")

            w_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
                f"&daily=temperature_2m_max,temperature_2m_min,weather_code&timezone=auto"
            )
            w_res = await client.get(w_url, headers=headers)
            if w_res.status_code != 200:
                return None
            w_data = w_res.json()
            curr = w_data.get("current", {})

            code = curr.get("weather_code", 0)
            desc, emoji = _WEATHER_CODES.get(code, ("Clear conditions", "🌤️"))
            temp_c = curr.get("temperature_2m", 0.0)
            temp_f = round(temp_c * 9 / 5 + 32, 1)
            feels_c = curr.get("apparent_temperature", temp_c)
            feels_f = round(feels_c * 9 / 5 + 32, 1)
            humidity = curr.get("relative_humidity_2m", 0)
            wind_kmh = curr.get("wind_speed_10m", 0)
            precip = curr.get("precipitation", 0)

            daily = w_data.get("daily", {})
            max_temps = daily.get("temperature_2m_max", [])
            min_temps = daily.get("temperature_2m_min", [])
            high_str = f"{max_temps[0]}°C" if max_temps else "N/A"
            low_str = f"{min_temps[0]}°C" if min_temps else "N/A"

            return (
                f"### {emoji} Live Weather for **{full_place}**\n\n"
                f"- **Condition:** {desc}\n"
                f"- **Current Temperature:** **{temp_c}°C** ({temp_f}°F)\n"
                f"- **Feels Like:** {feels_c}°C ({feels_f}°F)\n"
                f"- **Today's High / Low:** {high_str} / {low_str}\n"
                f"- **Relative Humidity:** {humidity}%\n"
                f"- **Wind Speed:** {wind_kmh} km/h\n"
                f"- **Precipitation:** {precip} mm\n\n"
                f"*Real-time meteorological observations retrieved live via Open-Meteo.*"
            )
    except Exception as exc:
        log.warning("fetch_live_weather.failed", city=city_name, error=str(exc))
        return None


async def fetch_live_search(query: str, num: int = 4) -> str | None:
    """Fetch live web search results via Tavily or DuckDuckGo."""
    try:
        from app.skills.schemas import WebSearchRequest
        from app.skills.web_search import WebSearchSkill

        skill = WebSearchSkill()
        res = await skill.execute(WebSearchRequest(query=query, num_results=num))
        if not res.results:
            return None

        lines = [f"### 🌐 Web Search Results for: *\"{query}\"*\n"]
        for idx, item in enumerate(res.results, 1):
            title = item.title or "Web Result"
            url = item.url or "#"
            snippet = item.snippet or ""
            lines.append(f"{idx}. [**{title}**]({url})\n   {snippet}\n")

        lines.append("*Live web search powered by Tavily & ROXY Runtime Engine.*")
        return "\n".join(lines)
    except Exception as exc:
        log.warning("fetch_live_search.failed", query=query, error=str(exc))
        return None


_MAPS_TRIGGERS = [
    re.compile(r"^(?:find\s+places\s+near|places\s+near|maps?\s+for|show\s+(?:me\s+)?map\s+of|map\s+of|view\s+on\s+map)\s*:\s*", re.I),
    re.compile(r"\b(?:find\s+places\s+near|places\s+near|restaurants?\s+near|cafes?\s+near|coffee\s+shops?\s+near|hotels?\s+near|food\s+near|attractions?\s+near|spots?\s+near|bars?\s+near)\b", re.I),
    re.compile(r"\b(?:show\s+(?:me\s+)?(?:the\s+)?map\s+(?:of|for)?|open\s+(?:the\s+)?map\s+(?:of|for)?|map\s+of)\b", re.I),
    re.compile(r"\b(?:google\s+maps?|openstreetmap|navigate\s+to|directions\s+to|view\s+on\s+map)\b", re.I),
    re.compile(r"\b(?:where\s+is\s+(?:the\s+)?|location\s+of\s+(?:the\s+)?)\b", re.I),
    re.compile(r"^(?:maps?|open\s+maps?|show\s+maps?|view\s+map)$", re.I),
]

_POPULAR_COORDINATES: dict[str, tuple[float, float, str]] = {
    "paris": (48.8566, 2.3522, "Paris, Île-de-France, France"),
    "eiffel tower": (48.8584, 2.2945, "Eiffel Tower, Paris, France"),
    "tokyo": (35.6762, 139.6503, "Tokyo, Japan"),
    "new york": (40.7128, -74.0060, "New York City, NY, USA"),
    "times square": (40.7580, -73.9855, "Times Square, New York, NY, USA"),
    "central park": (40.785091, -73.968285, "Central Park, New York, NY, USA"),
    "london": (51.5074, -0.1278, "London, United Kingdom"),
    "big ben": (51.5007, -0.1246, "Big Ben, London, United Kingdom"),
    "dubai": (25.2048, 55.2708, "Dubai, United Arab Emirates"),
    "burj khalifa": (25.1972, 55.2744, "Burj Khalifa, Dubai, United Arab Emirates"),
    "rome": (41.9028, 12.4964, "Rome, Lazio, Italy"),
    "colosseum": (41.8902, 12.4922, "Colosseum, Rome, Italy"),
    "san francisco": (37.7749, -122.4194, "San Francisco, CA, USA"),
    "sydney": (-33.8688, 151.2093, "Sydney, NSW, Australia"),
    "singapore": (1.3521, 103.8198, "Singapore"),
    "berlin": (52.5200, 13.4050, "Berlin, Germany"),
    "toronto": (43.6532, -79.3832, "Toronto, Ontario, Canada"),
    "mumbai": (19.0760, 72.8777, "Mumbai, Maharashtra, India"),
    "delhi": (28.6139, 77.2090, "New Delhi, Delhi, India"),
    "shanghai": (31.2304, 121.4737, "Shanghai, China"),
    "beijing": (39.9042, 116.4074, "Beijing, China"),
}


def extract_place_from_query(query: str) -> str:
    s = query.strip()
    s = re.sub(r"^(?:find\s+places\s+near|places\s+near|maps?\s+for|show\s+(?:me\s+)?(?:the\s+)?map\s+(?:of|for)?|map\s+of|view\s+on\s+map|navigate\s+to|directions\s+to|where\s+is\s+(?:the\s+)?|location\s+of\s+(?:the\s+)?)\s*:\s*", "", s, flags=re.I)
    s = re.sub(r"\b(?:show\s+(?:me\s+)?(?:the\s+)?map\s+(?:of|for)?|open\s+(?:the\s+)?map\s+(?:of|for)?|navigate\s+to|directions\s+to|where\s+is\s+(?:the\s+)?|location\s+of\s+(?:the\s+)?)\b", "", s, flags=re.I)
    s = re.sub(r"\b(?:find\s+places\s+near|places\s+near|restaurants?\s+near|cafes?\s+near|hotels?\s+near|food\s+near|attractions?\s+near)\b", "", s, flags=re.I)
    s = re.sub(r"\b(?:google\s+maps?|openstreetmap|in\s+maps?)\b", "", s, flags=re.I)
    cleaned = re.sub(r"[^\w\s\-,]", " ", s).strip()
    words = [w for w in cleaned.split() if len(w) > 0]
    return " ".join(words)


def check_maps_intent(message: str) -> tuple[bool, str]:
    """Check if message is asking for maps, navigation, or places nearby."""
    msg = message.strip()
    for p in _MAPS_TRIGGERS:
        if p.search(msg):
            place = extract_place_from_query(msg)
            return True, place
    return False, ""


async def fetch_live_maps(query: str) -> str | None:
    """Fetch live map coordinates, interactive embeds, navigation links, and nearby recommendations."""
    raw = query.strip()
    is_empty_or_generic = (not raw) or raw.lower() in ("maps", "map", "near me", "my location", "here")

    lat: float | None = None
    lon: float | None = None

    if is_empty_or_generic:
        clean_target = "Paris"
        place_name = "Paris, Île-de-France, France"
        lat, lon = 48.8566, 2.3522
    else:
        clean_target = raw
        place_name = clean_target

        target_lower = clean_target.lower()
        for key, (k_lat, k_lon, k_name) in _POPULAR_COORDINATES.items():
            if key == target_lower or key in target_lower:
                lat, lon, place_name = k_lat, k_lon, k_name
                break

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (ROXY/1.0)",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if not is_empty_or_generic and (lat is None or lon is None):
                # 1. Try Nominatim for landmarks and addresses
                nom_url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(clean_target)}&format=json&limit=1"
                try:
                    nom_res = await client.get(nom_url, headers=headers)
                    if nom_res.status_code == 200:
                        nom_data = nom_res.json()
                        if nom_data:
                            lat = float(nom_data[0]["lat"])
                            lon = float(nom_data[0]["lon"])
                            place_name = nom_data[0].get("display_name", clean_target)
                except Exception:
                    pass

                # 2. If not found by Nominatim, try Open-Meteo geocoding
                if lat is None or lon is None:
                    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(clean_target)}&count=1"
                    try:
                        geo_res = await client.get(geo_url, headers=headers)
                        if geo_res.status_code == 200:
                            geo_data = geo_res.json()
                            results = geo_data.get("results", [])
                            if results:
                                loc = results[0]
                                lat = float(loc["latitude"])
                                lon = float(loc["longitude"])
                                p_name = loc.get("name", clean_target)
                                country = loc.get("country", "")
                                admin = loc.get("admin1", "")
                                place_name = f"{p_name}, {admin}, {country}".replace(", ,", ",").strip(", ")
                    except Exception:
                        pass

            # Fallback if still unlocated
            if lat is None or lon is None:
                lat, lon = 48.8566, 2.3522
                place_name = f"{clean_target} (estimated)"

            # 3. Retrieve top places & reviews via Tavily
            tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
            places_summary = ""
            places_list: list[str] = []

            if tavily_key:
                try:
                    payload = {
                        "api_key": tavily_key,
                        "query": f"top popular places, attractions, restaurants near {clean_target} with address",
                        "max_results": 4,
                        "search_depth": "basic",
                        "include_answer": True,
                    }
                    tr = await client.post("https://api.tavily.com/search", json=payload)
                    if tr.status_code == 200:
                        tdata = tr.json()
                        if tdata.get("answer"):
                            places_summary = tdata["answer"]
                        for item in tdata.get("results", []):
                            title = item.get("title", "")
                            url = item.get("url", "#")
                            content = item.get("content", "")
                            if title and content:
                                places_list.append(f"- [**{title}**]({url})\n  {content[:160]}...")
                except Exception as t_exc:
                    log.warning("tavily.maps.failed", error=str(t_exc))

            lon_min = round(lon - 0.015, 5)
            lat_min = round(lat - 0.010, 5)
            lon_max = round(lon + 0.015, 5)
            lat_max = round(lat + 0.010, 5)

            embed_osm = f"https://www.openstreetmap.org/export/embed.html?bbox={lon_min}%2C{lat_min}%2C{lon_max}%2C{lat_max}&layer=mapnik&marker={lat}%2C{lon}"
            embed_google = f"https://maps.google.com/maps?q={lat},{lon}&hl=en&z=15&output=embed"
            encoded_q = urllib.parse.quote(clean_target)
            gmaps_search_url = f"https://www.google.com/maps/search/?api=1&query={encoded_q}"
            gmaps_dir_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
            osm_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}"

            map_data = {
                "place": place_name,
                "query": clean_target,
                "lat": lat,
                "lon": lon,
                "zoom": 15,
                "embed_osm": embed_osm,
                "embed_google": embed_google,
                "gmaps_search": gmaps_search_url,
                "directions": gmaps_dir_url,
                "osm_url": osm_url,
            }

            lines = []
            if is_empty_or_generic:
                lines.append("📍 **Interactive Maps & Places Explorer**: Enter any city, landmark, or neighborhood (for example: *Find places near: Tokyo* or *restaurants near Times Square*) to explore live navigation, coordinates, and local spots. Here is a featured map preview:\n")

            lines.append("```map")
            lines.append(json.dumps(map_data, indent=2))
            lines.append("```\n")

            lines.append(f"### 📍 Maps & Places Guide: **{place_name}**\n")
            lines.append(f"**Coordinates:** `{lat:.5f}°, {lon:.5f}°`\n")

            lines.append("#### 🗺️ Quick Navigation & Maps:\n")
            lines.append(f"- [📍 **Open in Google Maps**]({gmaps_search_url})")
            lines.append(f"- [🧭 **Turn-by-Turn Directions**]({gmaps_dir_url})")
            lines.append(f"- [🌐 **View on OpenStreetMap**]({osm_url})\n")

            if places_summary:
                lines.append(f"#### 🌟 Highlights & Overview:\n{places_summary}\n")

            if places_list:
                lines.append("#### 🏛️ Top Spots & Attractions Nearby:\n")
                lines.extend(places_list)
                lines.append("")

            lines.append("*Live interactive mapping & geographical telemetry powered by Google Maps, OpenStreetMap & ROXY Navigation Engine.*")
            return "\n".join(lines)
    except Exception as exc:
        log.warning("fetch_live_maps.failed", query=query, error=str(exc))
        return None


def classify_intent(message: str) -> str:
    """Classify user message into an agent slug using keyword matching.

    Returns one of: image_generator | finance | critic | automation | research | coding | study | browser | general
    """
    msg = message.strip()

    if check_image_intent(msg)[0]:
        return "image_generator"

    is_maps, _ = check_maps_intent(msg)
    if is_maps:
        return "research"

    is_search, _, is_weather, _ = check_search_or_weather_intent(msg)
    if is_search or is_weather:
        return "research"

    # Count matches per category
    scores: dict[str, int] = {
        "voice": sum(1 for p in _VOICE_PATTERNS if p.search(msg)),
        "email": sum(1 for p in _EMAIL_PATTERNS if p.search(msg)),
        "workspace": sum(1 for p in _WORKSPACE_PATTERNS if p.search(msg)),
        "finance": sum(1 for p in _FINANCE_PATTERNS if p.search(msg)),
        "critic": sum(1 for p in _CRITIC_PATTERNS if p.search(msg)),
        "automation": sum(1 for p in _AUTOMATION_PATTERNS if p.search(msg)),
        "research": sum(1 for p in _RESEARCH_PATTERNS if p.search(msg)),
        "coding": sum(1 for p in _CODING_PATTERNS if p.search(msg)),
        "study": sum(1 for p in _STUDY_PATTERNS if p.search(msg)),
        "browser": sum(1 for p in _BROWSER_PATTERNS if p.search(msg)),
        "memory": sum(1 for p in _MEMORY_PATTERNS if p.search(msg)),
        "audit": sum(1 for p in _AUDIT_PATTERNS if p.search(msg)),
        "billing": sum(1 for p in _BILLING_PATTERNS if p.search(msg)),
        "calendar": sum(1 for p in _CALENDAR_PATTERNS if p.search(msg)),
        "image-studio": sum(1 for p in _IMAGE_STUDIO_PATTERNS if p.search(msg)),
    }

    # Pick the highest-scoring non-zero category
    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0:
        return best
    return "general"


MULTILINGUAL_AGENT_HEADER = """# UNIVERSAL MULTILINGUAL MANDATE:
- You are a native-level, fully fluent multilingual AI assistant.
- You understand and speak English, Urdu (اردو), Roman Urdu, Hindi (हिंदी), Arabic (العربية), Spanish (Español), French (Français), German (Deutsch), Chinese (中文), Japanese (日本語), and all other languages.
- MANDATORY RULE: You MUST always respond in the EXACT SAME LANGUAGE and SCRIPT that the user writes or speaks in.
  - If the user writes or speaks in Urdu (اردو), you MUST respond in fluent Urdu script (اردو).
  - If the user writes or speaks in Roman Urdu (e.g. "aap kaise hain", "mujhe batao", "kya haal hai"), you MUST respond in fluent Roman Urdu.
  - If the user writes or speaks in English, respond in English.
  - If the user writes or speaks in Hindi, Arabic, Spanish, French, German, Chinese, etc., respond in that respective language.
- Never switch back to English unless the user explicitly requests an English translation or answer.
- Maintain natural tone, correct grammar, and culturally appropriate phrasing in the chosen language.
"""


def detect_user_language_instruction(text: str) -> str:
    """Detect language of user message and return an explicit high-priority directive."""
    if not text:
        return ""

    # 1. Urdu / Arabic script
    if re.search(r"[\u0600-\u06FF]", text):
        return (
            "[CRITICAL MULTILINGUAL MANDATE]: The user is communicating in Urdu (اردو) / Arabic script. "
            "You MUST respond strictly and completely in Urdu (اردو) script. Do NOT respond in English."
        )

    # 2. Hindi / Devanagari script
    if re.search(r"[\u0900-\u097F]", text):
        return (
            "[CRITICAL MULTILINGUAL MANDATE]: The user is communicating in Hindi (हिंदी) script. "
            "You MUST respond strictly and completely in Hindi (हिंदी) script. Do NOT respond in English."
        )

    # 3. Chinese script
    if re.search(r"[\u4e00-\u9fff]", text):
        return (
            "[CRITICAL MULTILINGUAL MANDATE]: The user is communicating in Chinese (中文). "
            "You MUST respond strictly and completely in Chinese (中文). Do NOT respond in English."
        )

    # 4. Japanese script (Hiragana / Katakana)
    if re.search(r"[\u3040-\u30ff]", text):
        return (
            "[CRITICAL MULTILINGUAL MANDATE]: The user is communicating in Japanese (日本語). "
            "You MUST respond strictly and completely in Japanese (日本語). Do NOT respond in English."
        )

    # 5. Russian / Cyrillic script
    if re.search(r"[\u0400-\u04FF]", text):
        return (
            "[CRITICAL MULTILINGUAL MANDATE]: The user is communicating in Russian (Русский). "
            "You MUST respond strictly and completely in Russian (Русский). Do NOT respond in English."
        )

    # 6. Roman Urdu detection (high-frequency lexical markers)
    roman_urdu_words = {
        "kya", "kaise", "kaisay", "kese", "hai", "hain", "mujhe", "mujhko", "tum", "tumhe",
        "aap", "ap", "aapko", "apko", "batao", "bataiye", "chahiye", "karna", "karne",
        "raha", "rahe", "rahi", "shukriya", "theek", "thik", "nahi", "nahin", "acha",
        "achha", "bohot", "bahut", "kaun", "kon", "kab", "kaha", "kahan", "mera", "meri",
        "mere", "tera", "teri", "tere", "apka", "apki", "apke", "zada", "ziyada",
        "zaroorat", "zarurat", "hoga", "hogi", "hoge", "karte", "karti", "karta",
        "bhi", "yeh", "woh", "wo", "idhar", "udhar", "ab", "karo", "sakta", "sakti", "sakte",
        "bhai", "yaar", "lekin", "magar", "kyun", "kyu", "kuch", "sirf"
    }
    tokens = [w.strip(".,!?:;\"'()[]{}").lower() for w in text.split()]
    roman_matches = sum(1 for t in tokens if t in roman_urdu_words)
    if roman_matches >= 2 or (len(tokens) <= 4 and roman_matches >= 1):
        return (
            "[CRITICAL MULTILINGUAL MANDATE]: The user is communicating in Roman Urdu (Urdu written in Latin letters). "
            "You MUST formulate your response in natural, friendly, and fluent Roman Urdu (Latin script Urdu). "
            "For example: 'Jee zaroor, main aap ki madad kar sakta hoon...'. Do NOT switch to English."
        )

    # 7. Spanish detection
    spanish_markers = {"cómo", "como", "estás", "estas", "gracias", "por favor", "ayuda", "puedes", "hola", "buenos", "días", "noches", "quiero", "hacer", "para"}
    if sum(1 for t in tokens if t in spanish_markers) >= 2:
        return (
            "[CRITICAL MULTILINGUAL MANDATE]: The user is communicating in Spanish (Español). "
            "You MUST respond strictly and completely in Spanish (Español). Do NOT respond in English."
        )

    # 8. French detection
    french_markers = {"bonjour", "comment", "merci", "plaît", "pouvez", "faire", "aide", "salut", "pourquoi", "avec"}
    if sum(1 for t in tokens if t in french_markers) >= 2:
        return (
            "[CRITICAL MULTILINGUAL MANDATE]: The user is communicating in French (Français). "
            "You MUST respond strictly and completely in French (Français). Do NOT respond in English."
        )

    # 9. German detection
    german_markers = {"hallo", "wie", "geht's", "danke", "bitte", "kannst", "können", "hilfe", "guten", "morgen", "abend"}
    if sum(1 for t in tokens if t in german_markers) >= 2:
        return (
            "[CRITICAL MULTILINGUAL MANDATE]: The user is communicating in German (Deutsch). "
            "You MUST respond strictly and completely in German (Deutsch). Do NOT respond in English."
        )

    # Default fallback: strict preservation of user's chosen language
    return (
        "[CRITICAL MULTILINGUAL MANDATE]: Always detect the user's language and respond in the exact same language they used. "
        "If they speak or write in English, respond in English. If in Urdu, Roman Urdu, or any other language, respond in that same language."
    )


def load_agent_system_prompt(slug: str) -> str:
    """Load the system prompt from .claude/agents/<slug>.md.

    Strips YAML frontmatter and returns the markdown body with the universal multilingual mandate.
    Returns a comprehensive default prompt for general inquiries and fallback agents.
    """
    default_prompt = (
        "You are ROXY, an intelligent, helpful, and highly knowledgeable autonomous AI assistant. "
        "You provide comprehensive, detailed, clear, and well-structured responses to the user's questions. "
        "Never truncate or cut short your explanations. Provide thorough answers, detailed step-by-step guidance, "
        "and full runnable code examples when requested. Format your output with clear markdown headings, lists, and formatting."
    )
    if slug in ("general", "assistant", "default"):
        return f"{MULTILINGUAL_AGENT_HEADER}\n\n{default_prompt}"

    if not _AGENTS_DIR.exists():
        base = f"You are the {slug} agent. Handle the user's request thoroughly and provide complete answers."
        return f"{MULTILINGUAL_AGENT_HEADER}\n\n{base}"

    agent_file = _AGENTS_DIR / f"{slug}.md"
    if not agent_file.exists():
        base = f"You are the {slug} agent. Handle the user's request thoroughly and provide complete answers."
        return f"{MULTILINGUAL_AGENT_HEADER}\n\n{base}"

    content = agent_file.read_text(encoding="utf-8")
    # Strip YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].lstrip("\n")
    return f"{MULTILINGUAL_AGENT_HEADER}\n\n{content.strip()}"


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class RuntimeChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(default=None)
    stream: bool = Field(default=False)
    # If set, bypasses intent classification and forces a specific agent
    agent_override: str | None = Field(default=None)
    provider: str | None = Field(default=None)
    model: str | None = Field(default=None)


class RuntimeChatResponse(BaseModel):
    response: str
    agent_slug: str
    next_actions: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    critic_review: dict[str, Any] | None = Field(default=None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CACHED_PROMPTS: dict[str, str] = {}


def _get_agent_prompt(slug: str) -> str:
    if slug not in _CACHED_PROMPTS:
        _CACHED_PROMPTS[slug] = load_agent_system_prompt(slug)
    return _CACHED_PROMPTS[slug]


async def _persist_runtime_interaction(
    session_id: str | None,
    user_id: str,
    user_message: str,
    assistant_message: str,
    provider: str = "runtime",
    model: str = "coordinator",
) -> None:
    """Safely persist runtime interaction turns into chat_messages."""
    if not session_id:
        return
    try:
        from app.chat_history.repository import ChatMessageRepository
        from app.session.repository import ChatSessionRepository

        sessions = ChatSessionRepository()
        history = ChatMessageRepository()
        session = await sessions.get_by_id(session_id)
        if session is None:
            return
        if user_message:
            await history.append(
                session_id=session_id, role="user", content=user_message
            )
        if assistant_message:
            await history.append(
                session_id=session_id,
                role="assistant",
                content=assistant_message,
                provider=provider,
                model=model,
            )
        current_title = getattr(session, "title", None)
        default_titles = {"New chat", "New task", "New Conversation"}
        if (not current_title or current_title in default_titles) and user_message:
            from app.api.v1.greeting import generate_smart_title, is_greeting
            if is_greeting(user_message):
                if current_title != "New Conversation":
                    await sessions.rename(session.id, session.user_id, "New Conversation")
            else:
                smart_title = generate_smart_title(user_message)
                await sessions.rename(session.id, session.user_id, smart_title)
    except Exception as exc:
        log.warning("runtime.persist.failed", error=str(exc))


async def _call_ai_for_agent(
    agent_slug: str,
    user_message: str,
    stream: bool = False,
    user_id: str | None = None,
    session_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[str, str, str]:
    """Call the AI gateway with an agent-specific system prompt and history.

    Returns (response_text, provider, model).
    """
    is_img, img_prompt = check_image_intent(user_message)
    if is_img or agent_slug == "image_generator":
        prompt = img_prompt or user_message
        img_res = generate_image_response(prompt)
        if user_id:
            try:
                from app.images.repository import ImageStudioRepository
                img_repo = ImageStudioRepository()
                cleaned_p = prompt.strip()
                enc_p = urllib.parse.quote(cleaned_p)
                i_url = f"https://image.pollinations.ai/prompt/{enc_p}?width=1024&height=1024&nologo=true&enhance=true"
                await img_repo.create_generation(
                    user_id=user_id,
                    prompt=cleaned_p,
                    media_url=i_url,
                    style_preset="photorealistic",
                    aspect_ratio="1:1",
                    width=1024,
                    height=1024,
                    model="flux",
                )
            except Exception as exc:
                log.warning("runtime.image_persist_failed", error=str(exc))
        if session_id:
            await _persist_runtime_interaction(
                session_id, user_id or "", user_message, img_res, "roxy_vision", "flux-diffusion"
            )
        return img_res, "roxy_vision", "flux-diffusion"

    system_prompt = _get_agent_prompt(agent_slug)

    history_messages: list[Message] = [Message(role=MessageRole.SYSTEM, content=system_prompt)]
    if session_id and user_id:
        try:
            from app.chat_history.repository import ChatMessageRepository
            repo = ChatMessageRepository()
            rows = await repo.list_for_session(session_id, user_id, limit=8)
            for r in rows:
                role = MessageRole.USER if r.role == "user" else MessageRole.ASSISTANT
                history_messages.append(Message(role=role, content=r.content))
        except Exception:
            pass

    is_maps, maps_q = check_maps_intent(user_message)
    is_search, search_q, is_weather, city = check_search_or_weather_intent(user_message)
    live_context: str | None = None
    if is_maps:
        live_context = await fetch_live_maps(maps_q)
    elif is_weather:
        live_context = await fetch_live_weather(city)
        if not live_context:
            live_context = await fetch_live_search(f"current weather in {city or 'today'}")
    elif (is_search or agent_slug == "research") and not any(
        w in user_message.lower()
        for w in (
            "saved research",
            "saved report",
            "saved reports",
            "my research",
            "my reports",
            "in my library",
            "saved investigations",
            "have any saved",
        )
    ):
        live_context = await fetch_live_search(search_q)

    if live_context:
        history_messages.append(
            Message(
                role=MessageRole.SYSTEM,
                content=(
                    f"[LIVE REAL-TIME GROUND TRUTH DATA RETRIEVED AT RUNTIME]:\n"
                    f"{live_context}\n\n"
                    "Use this authoritative live data to directly answer the user's inquiry with exact numbers, conditions, and sources."
                ),
            )
        )

    # ── Knowledge Vault RAG Grounding ──────────────────────────────────────
    grounded_chunks: list[str] = []
    try:
        from app.skills.document_rag_query import DocumentRAGSkill
        from app.skills.schemas import DocumentRagQueryRequest
        rag_skill = DocumentRAGSkill()
        rag_res = await rag_skill.execute(
            DocumentRagQueryRequest(
                query=user_message,
                user_id=user_id or "guest_trial",
                top_k=3,
                min_score=0.20,
            )
        )
        if rag_res.chunks:
            grounded_chunks = [
                f"[Source: {c.document_name}]\n{c.content}"
                for c in rag_res.chunks
                if c.relevance_score >= 0.20
            ]
            if grounded_chunks:
                history_messages.append(
                    Message(
                        role=MessageRole.SYSTEM,
                        content=(
                            "[KNOWLEDGE VAULT CONTEXT — USER PRIVATE DOCUMENTS]:\n"
                            + "\n\n".join(grounded_chunks)
                            + "\n\nGround your answer using the excerpts above. Include citation [Source: <document_name>] when referencing document facts."
                        ),
                    )
                )
    except Exception as exc:
        log.warning("runtime.rag_grounding_failed", error=str(exc))

    # Phase 6: Financial Ledger Grounding for authenticated users
    is_finance = (agent_slug == "finance") or any(
        w in user_message.lower() for w in ("balance", "account", "bank", "raast", "plaid", "spending", "budget", "finance", "runway", "transaction")
    )
    if user_id and is_finance:
        try:
            from app.finance.repository import FinanceRepository
            fin_repo = FinanceRepository()
            fin_accs = await fin_repo.list_accounts(user_id)
            if fin_accs:
                tot_usd = sum(a.balance_usd for a in fin_accs)
                tot_pkr = sum(a.balance_pkr for a in fin_accs)
                acc_lines = [
                    f"- {a.institution_name} ({a.account_holder}, {a.account_type}): ${a.balance_usd:,.2f} / Rs {a.balance_pkr:,.0f} [{a.provider.upper()}]"
                    for a in fin_accs
                ]
                month_txs = await fin_repo.list_transactions(user_id, period="month", limit=5)
                tx_lines = [
                    f"  * {t.description}: ${abs(t.amount_usd):.2f} / Rs {abs(t.amount_pkr):.0f} ({t.category})"
                    for t in month_txs[:5]
                ]
                fin_context = (
                    "[FINANCIAL LEDGER CONTEXT — USER CONNECTED INSTITUTIONS & BALANCES]:\n"
                    f"Total Combined Balance: ${tot_usd:,.2f} USD (Rs {tot_pkr:,.0f} PKR)\n"
                    "Connected Accounts:\n" + "\n".join(acc_lines)
                )
                if tx_lines:
                    fin_context += "\nRecent Monthly Transactions:\n" + "\n".join(tx_lines)
                fin_context += "\n\nUse this live financial ledger data to accurately answer the user's inquiry regarding their balances, runway, transactions, and banking."
                history_messages.append(Message(role=MessageRole.SYSTEM, content=fin_context))
        except Exception as exc:
            log.warning("runtime.finance_grounding_failed", error=str(exc))

    # Phase 11: Calendar & Event Scheduling Grounding for authenticated users
    is_calendar = (agent_slug in ("calendar", "scheduler")) or (
        agent_slug != "automation"
        and any(
            w in user_message.lower()
            for w in (
                "calendar",
                "meeting",
                "appointment",
                "agenda",
                "events today",
                "am i free",
                "on my schedule",
                "on my calendar",
                "calendar schedule",
            )
        )
    )
    if user_id and is_calendar:
        try:
            from app.calendar.repository import CalendarRepository
            cal_repo = CalendarRepository()
            user_events = await cal_repo.list_events(user_id)
            if user_events:
                ev_lines = [
                    f"- **{e['title']}** (Time: `{e['start_time']}`, Category: {e.get('category', 'meeting')}, Location: {e.get('location') or 'Not specified'})"
                    for e in user_events[:10]
                ]
                cal_context = (
                    "[CALENDAR CONTEXT — UPCOMING USER EVENTS & SCHEDULE]:\n"
                    f"Total Scheduled Events: {len(user_events)}\n"
                    "Events:\n" + "\n".join(ev_lines)
                    + "\n\nUse this live schedule to answer the user's questions about their calendar, appointments, and availability."
                )
                history_messages.append(Message(role=MessageRole.SYSTEM, content=cal_context))
        except Exception as exc:
            log.warning("runtime.calendar_grounding_failed", error=str(exc))

    # Phase 12: Email & Communications Grounding for authenticated users
    is_email = (agent_slug in ("email", "communications")) or any(
        w in user_message.lower()
        for w in (
            "email",
            "emails",
            "outbox",
            "drafts",
            "draft an email",
            "sent email",
            "sent mail",
            "compose email",
            "write an email",
            "send an email",
            "email draft",
        )
    )
    if user_id and is_email:
        try:
            from app.emails.repository import EmailRepository
            email_repo = EmailRepository()
            user_emails = await email_repo.list_messages(user_id, limit=10)
            drafts = [m for m in user_emails if m.get("status") == "draft"]
            sent_msgs = [m for m in user_emails if m.get("status") == "sent"]
            email_lines = [
                f"- [{m.get('status', 'draft').upper()}] **{m.get('subject', 'No Subject')}** (To: `{m.get('to', '')}`, Date: `{m.get('created_at', '')}`)"
                for m in user_emails[:10]
            ]
            email_context = (
                "[EMAIL CONTEXT — RECENT OUTBOX & DRAFTS]:\n"
                f"Total Messages: {len(user_emails)} (Drafts: {len(drafts)}, Sent: {len(sent_msgs)})\n"
                "Recent Emails:\n" + ("\n".join(email_lines) if email_lines else "None")
                + "\n\nUse this authentic email history to assist the user with composing, reviewing drafts, or checking sent communications."
            )
            history_messages.append(Message(role=MessageRole.SYSTEM, content=email_context))
        except Exception as exc:
            log.warning("runtime.email_grounding_failed", error=str(exc))

    # Phase 10: Image Studio Gallery Grounding for authenticated users
    is_image_gallery = any(
        w in user_message.lower()
        for w in (
            "my image gallery",
            "image gallery",
            "my generated images",
            "generated artwork",
            "saved artwork",
            "my images",
            "artwork in my studio",
            "saved images",
            "image studio",
        )
    )
    if user_id and is_image_gallery:
        try:
            from app.images.repository import ImageStudioRepository
            img_repo = ImageStudioRepository()
            gens = await img_repo.list_generations(user_id, limit=10)
            gen_lines = [
                f"- **\"{g.get('prompt')}\"** (Style: `{g.get('style_preset', 'photorealistic')}`, Aspect: `{g.get('aspect_ratio', '1:1')}`, Favorited: {g.get('is_favorite', False)})"
                for g in gens[:10]
            ]
            img_context = (
                "[IMAGE STUDIO CONTEXT — USER SAVED GENERATIONS & ARTWORK]:\n"
                f"Total Saved Generations: {len(gens)}\n"
                "Recent Artwork:\n" + ("\n".join(gen_lines) if gen_lines else "None")
                + "\n\nUse this authentic image gallery history to assist the user with reviewing past creations, styles, and prompt details."
            )
            history_messages.append(Message(role=MessageRole.SYSTEM, content=img_context))
        except Exception as exc:
            log.warning("runtime.image_gallery_grounding_failed", error=str(exc))

    # Phase 13: Voice & Audio Transcripts Grounding for authenticated users
    is_voice = (agent_slug in ("voice", "audio")) or any(
        w in user_message.lower()
        for w in (
            "voice note",
            "voice notes",
            "voice recording",
            "voice recordings",
            "audio recording",
            "audio recordings",
            "audio transcript",
            "voice transcript",
            "transcribe",
            "audio note",
            "audio notes",
            "recordings",
        )
    )
    if user_id and is_voice:
        try:
            from app.voice.repository import VoiceRepository
            voice_repo = VoiceRepository()
            user_recs = await voice_repo.list_recordings(user_id, limit=10)
            rec_lines = [
                f"- **{r.get('title', 'Voice Note')}** (Date: `{r.get('created_at', '')}`, Duration: {r.get('duration_seconds') or 0}s, Summary: {r.get('summary') or r.get('transcript', '')[:100]}…)"
                for r in user_recs[:10]
            ]
            voice_context = (
                "[VOICE CONTEXT — RECENT AUDIO TRANSCRIPTS & RECORDINGS]:\n"
                f"Total Saved Voice Notes: {len(user_recs)}\n"
                "Recent Voice Recordings & Transcripts:\n" + ("\n".join(rec_lines) if rec_lines else "None")
                + "\n\nUse this authentic voice recordings and audio transcripts library to assist the user with reviewing past voice notes, summaries, or finding audio intelligence."
            )
            history_messages.append(Message(role=MessageRole.SYSTEM, content=voice_context))
        except Exception as exc:
            log.warning("runtime.voice_grounding_failed", error=str(exc))

    # Phase 14: Research & Saved Reports Grounding for authenticated users
    is_saved_research = (agent_slug == "research") or any(
        w in user_message.lower()
        for w in (
            "research report",
            "research reports",
            "saved research",
            "my research",
            "deep research",
            "investigation",
            "investigations",
        )
    )
    if user_id and is_saved_research:
        try:
            from app.research.repository import ResearchRepository
            research_repo = ResearchRepository()
            user_reports = await research_repo.list_reports(user_id, limit=10)
            rep_lines = [
                f"- **{r.get('title', 'Research Report')}** (Topic: *\"{r.get('query', '')}\"*, Confidence: `{r.get('confidence', 'medium')}`, Summary: {str(r.get('summary') or '')[:120]}…)"
                for r in user_reports[:10]
            ]
            research_context = (
                "[RESEARCH CONTEXT — SAVED RESEARCH REPORTS & INVESTIGATIONS]:\n"
                f"Total Saved Research Reports: {len(user_reports)}\n"
                "Recent Research Reports:\n" + ("\n".join(rep_lines) if rep_lines else "None")
                + "\n\nUse this authentic research reports library to assist the user with past findings, citations, and continuing investigations."
            )
            history_messages.append(Message(role=MessageRole.SYSTEM, content=research_context))
        except Exception as exc:
            log.warning("runtime.research_grounding_failed", error=str(exc))

    # Phase 15: Browser & Web Automation Grounding for authenticated users
    is_browser_task = (agent_slug == "browser") or any(
        w in user_message.lower()
        for w in (
            "browser task",
            "browser tasks",
            "web automation",
            "automation flow",
            "web extraction",
            "extract table",
            "inspect dom",
            "browse website",
            "navigate to",
            "fill form",
        )
    )
    if user_id and is_browser_task:
        try:
            from app.browser.repository import BrowserRepository
            browser_repo = BrowserRepository()
            user_tasks = await browser_repo.list_tasks(user_id, limit=10)
            task_lines = [
                f"- **{t.get('title', 'Browser Task')}** (URL: `{t.get('url', '')}`, Status: `{t.get('status', 'pending')}`, Type: `{t.get('action_type', 'navigate')}`)"
                for t in user_tasks[:10]
            ]
            browser_context = (
                "[BROWSER CONTEXT — RECENT WEB AUTOMATION TASKS & EXTRACTIONS]:\n"
                f"Total Saved Browser Tasks: {len(user_tasks)}\n"
                "Recent Browser Tasks:\n" + ("\n".join(task_lines) if task_lines else "None")
                + "\n\nUse this authentic browser automation library to assist the user with web tasks, DOM element inspection, data extraction, and form navigation."
            )
            history_messages.append(Message(role=MessageRole.SYSTEM, content=browser_context))
        except Exception as exc:
            log.warning("runtime.browser_grounding_failed", error=str(exc))

    # Phase 16: Study & Learning Studio Grounding for authenticated users
    is_study = (agent_slug == "study") or any(
        w in user_message.lower()
        for w in (
            "study deck",
            "study decks",
            "flashcard",
            "flashcards",
            "quiz",
            "quizzes",
            "spaced repetition",
            "practice quiz",
            "exam prep",
            "leitner",
            "test me",
            "study guide",
        )
    )
    if user_id and is_study:
        try:
            from app.study.repository import StudyRepository
            study_repo = StudyRepository()
            user_decks = await study_repo.list_decks(user_id, limit=10)
            deck_lines = [
                f"- **{d.get('title', 'Study Deck')}** (Subject: `{d.get('subject', 'General')}`, Cards: {d.get('card_count', 0)}, Mastery: {d.get('mastery_percentage', 0.0)}%)"
                for d in user_decks[:10]
            ]
            study_stats = await study_repo.get_study_stats(user_id)
            study_context = (
                "[STUDY CONTEXT — USER STUDY DECKS, FLASHCARDS & QUIZZES]:\n"
                f"Total Study Decks: {study_stats.get('total_decks', 0)}\n"
                f"Total Flashcards: {study_stats.get('total_cards', 0)}\n"
                f"Cards Due for Review: {study_stats.get('cards_due_for_review', 0)}\n"
                f"Average Mastery: {study_stats.get('average_mastery', 0.0)}%\n"
                f"Completed Quizzes: {study_stats.get('completed_quizzes', 0)}\n"
                "User Study Decks:\n" + ("\n".join(deck_lines) if deck_lines else "None")
                + "\n\nUse this authentic study and learning library to assist the user with their flashcards, active recall reviews, quiz prep, and spaced repetition scheduling."
            )
            history_messages.append(Message(role=MessageRole.SYSTEM, content=study_context))
        except Exception as exc:
            log.warning("runtime.study_grounding_failed", error=str(exc))

    # Phase 17: Coding & Developer Studio Grounding for authenticated users
    is_coding = (agent_slug == "coding") or any(
        w in user_message.lower()
        for w in (
            "write code",
            "write a function",
            "debug",
            "fix bug",
            "code snippet",
            "code snippets",
            "run code",
            "execute code",
            "coding playground",
            "coding studio",
            "python function",
            "javascript function",
            "code library",
        )
    )
    if user_id and is_coding:
        try:
            from app.coding.repository import CodeRepository
            coding_repo = CodeRepository()
            user_snippets, snip_total = await coding_repo.list_snippets(user_id, limit=10)
            user_executions, exec_total = await coding_repo.list_executions(user_id, limit=5)
            coding_stats = await coding_repo.get_user_stats(user_id)
            snip_lines = [
                f"- **{s.get('title', 'Snippet')}** (Language: `{s.get('language', 'python')}`, Favorite: {s.get('is_favorite', False)})\n  *Code preview:* `{s.get('code', '')[:80]}...`"
                for s in user_snippets[:5]
            ]
            coding_context = (
                "[CODING CONTEXT — USER SAVED SNIPPETS & RECENT CODE RUNS]:\n"
                f"Total Saved Snippets: {coding_stats.get('total_snippets', snip_total)}\n"
                f"Total Code Executions: {coding_stats.get('total_executions', exec_total)}\n"
                f"Execution Success Rate: {coding_stats.get('success_rate_percentage', 100.0)}%\n"
                "User Code Snippets:\n" + ("\n".join(snip_lines) if snip_lines else "None")
                + "\n\nUse this authentic developer library to assist the user with writing, debugging, explaining, and executing code."
            )
            history_messages.append(Message(role=MessageRole.SYSTEM, content=coding_context))
        except Exception as exc:
            log.warning("runtime.coding_grounding_failed", error=str(exc))

    # Phase 18: Semantic Memory Grounding for authenticated users
    is_memory = (agent_slug in ("memory", "curator", "memory-curator")) or any(
        p.search(user_message) for p in _MEMORY_PATTERNS
    )
    if user_id and is_memory:
        try:
            from app.memory.repository import MemoryRepository
            mem_repo = MemoryRepository()
            user_mems, mem_total = await mem_repo.list_memories(user_id=user_id, include_soft_deleted=False, limit=10)
            mem_stats = await mem_repo.get_stats(user_id)
            if user_mems:
                mem_lines = [
                    f"- [{m.get('importance', 'normal').upper()}] {m.get('content')} (Tags: {', '.join(m.get('tags', []))})"
                    for m in user_mems[:8]
                ]
                mem_context = (
                    "[SEMANTIC MEMORY CONTEXT — USER PREFERENCES & STORED FACTS]:\n"
                    f"Total Active Memories: {mem_stats.get('active_memories', len(user_mems))} (Forever Pinned: {mem_stats.get('forever_memories', 0)})\n"
                    "Active Long-Term Memories:\n" + "\n".join(mem_lines)
                    + "\n\nGround your answer in the user's stored memories and personal preferences."
                )
                history_messages.append(Message(role=MessageRole.SYSTEM, content=mem_context))
        except Exception as exc:
            log.warning("runtime.memory_grounding_failed", error=str(exc))

    # Phase 19: Audit & Security Activity Grounding for authenticated users
    is_audit = (agent_slug in ("audit", "security", "security-privacy")) or any(
        p.search(user_message) for p in _AUDIT_PATTERNS
    )
    if user_id and is_audit:
        try:
            from app.audit.repository import AuditRepository
            audit_repo = AuditRepository()
            today_events = await audit_repo.list_today_events(user_id, limit=10)
            audit_stats = await audit_repo.get_stats(user_id)
            event_lines = [
                f"- [{e.get('approval_tier', 'T1')}] **{e.get('agent_slug', 'coordinator').upper()}**: {e.get('action')} (Status: `{e.get('status_code', 'ok')}`, Latency: {e.get('latency_ms', 0)}ms)\n  *Summary:* {e.get('response_summary', '')[:100]}"
                for e in today_events[:8]
            ]
            audit_context = (
                "[AUDIT CONTEXT — ACTIONS PERFORMED TODAY & SECURITY LOG]:\n"
                f"Total Actions Logged: {audit_stats.get('total_events', len(today_events))} (Today: {audit_stats.get('today_events', len(today_events))})\n"
                f"Approval Tiers: {audit_stats.get('by_tier', {})}\n"
                f"Status Breakdown: {audit_stats.get('by_status', {})}\n"
                "Recent Today's Actions:\n" + ("\n".join(event_lines) if event_lines else "None recorded yet today.")
                + "\n\nUse this authentic audit log data to answer the user's questions about what ROXY/Jarvis did today, action history, and security reviews."
            )
            history_messages.append(Message(role=MessageRole.SYSTEM, content=audit_context))
        except Exception as exc:
            log.warning("runtime.audit_grounding_failed", error=str(exc))

    # Phase 7: Automation & Scheduled Jobs Grounding for authenticated users
    is_automation = not is_calendar and not is_email and (
        (agent_slug in ("automation", "planner")) or any(
            w in user_message.lower() for w in ("scheduled", "schedule", "reminder", "cron", "recurring task", "recurring job", "scheduled job", "scheduled task", "automation", "automate")
        )
    )
    if user_id and is_automation:
        try:
            from app.jobs.repository import JobRepository
            job_repo = JobRepository()
            user_jobs = await job_repo.list_jobs(user_id)
            if user_jobs:
                job_lines = [
                    f"- {j.name} (Schedule: {j.schedule}, Timezone: {j.timezone}, Status: {j.status}, Next Run: {j.next_run})"
                    for j in user_jobs
                ]
                job_context = (
                    "[SCHEDULED AUTOMATION CONTEXT — USER ACTIVE TASKS & JOBS]:\n"
                    f"Total Configured Tasks: {len(user_jobs)}\n"
                    "Active Tasks:\n" + "\n".join(job_lines)
                    + "\n\nUse this live scheduled automation data to accurately answer the user's inquiry regarding their scheduled tasks, reminders, and automation."
                )
                history_messages.append(Message(role=MessageRole.SYSTEM, content=job_context))
        except Exception as exc:
            log.warning("runtime.automation_grounding_failed", error=str(exc))

    # Phase 9: Workspace & Project Management Grounding for authenticated users
    is_workspace = (agent_slug in ("workspace", "project", "projects")) or any(
        w in user_message.lower() for w in ("project", "workspace", "milestone", "action item", "kanban")
    )
    if user_id and is_workspace:
        try:
            from app.projects.repository import ProjectRepository
            proj_repo = ProjectRepository()
            user_projects = await proj_repo.list_projects(user_id)
            if user_projects:
                proj_lines = []
                for p in user_projects:
                    tasks = await proj_repo.list_tasks(user_id, p["id"]) or []
                    t_summary = f"{sum(1 for t in tasks if t['status'] == 'done')}/{len(tasks)} tasks completed"
                    proj_lines.append(f"- **{p['name']}** (Status: {p['status']}, Progress: {t_summary})")
                proj_context = (
                    "[WORKSPACE HUB CONTEXT — USER PROJECTS & ACTION ITEMS]:\n"
                    f"Total Configured Projects: {len(user_projects)}\n"
                    "Active Projects:\n" + "\n".join(proj_lines)
                    + "\n\nUse this live workspace and project data to accurately answer the user's inquiry regarding their projects, deliverables, and tasks."
                )
                history_messages.append(Message(role=MessageRole.SYSTEM, content=proj_context))
        except Exception as exc:
            log.warning("runtime.workspace_grounding_failed", error=str(exc))

    # Phase 21: Billing, Subscription & Credit Wallet Grounding for authenticated users
    is_billing = (agent_slug in ("billing", "subscription", "payments", "invoicing")) or any(
        p.search(user_message) for p in _BILLING_PATTERNS
    )
    if user_id and is_billing:
        try:
            from app.billing.repository import BillingRepository
            billing_repo = BillingRepository()
            sub = await billing_repo.get_subscription(user_id)
            wallet = await billing_repo.get_credit_wallet(user_id)
            invoices = await billing_repo.list_invoices(user_id)
            plan_info = sub.get("plan", {})
            plan_name = plan_info.get("name", "Free (BYOK)")
            plan_status = plan_info.get("status", "active")
            remaining = wallet.get("remaining_credits", 100.0)
            used = wallet.get("used_this_month", 0.0)
            pm = sub.get("payment_method")
            pm_str = f"{pm.get('brand', 'Card').upper()} ending in {pm.get('last4')}" if pm else "None"
            billing_context = (
                "[BILLING & SUBSCRIPTION CONTEXT — USER PLAN, CREDITS & WALLET]:\n"
                f"Active Subscription Plan: {plan_name} (Status: {plan_status})\n"
                f"Remaining AI Credits: {remaining:,.0f}\n"
                f"Credits Used This Month: {used:,.0f}\n"
                f"Total Invoices on File: {len(invoices)}\n"
                f"Default Payment Method: {pm_str}\n\n"
                "Use this live subscription and credit wallet data to accurately answer the user's inquiry regarding their billing, plan, credits, invoices, or subscriptions."
            )
            history_messages.append(Message(role=MessageRole.SYSTEM, content=billing_context))
        except Exception as exc:
            log.warning("runtime.billing_grounding_failed", error=str(exc))

    lang_directive = detect_user_language_instruction(user_message)
    if lang_directive:
        history_messages.append(Message(role=MessageRole.SYSTEM, content=lang_directive))

    history_messages.append(Message(role=MessageRole.USER, content=user_message))

    router_ = AIRouter()
    provider_override = provider if (provider and provider not in ("runtime", "coordinator")) else None
    model_override = model if (model and model not in ("coordinator", "runtime", "auto", "default")) else None
    request = AIRequest(
        messages=history_messages,
        provider=provider_override,
        model=model_override,
        temperature=0.7,
        max_tokens=4096,
        stream=stream,
        user_id=user_id,
        session_id=session_id,
    )

    try:
        response: AIResponse = await router_.route(request)
        content = getattr(response, "content", None) or (response.choices[0].message.content if hasattr(response, "choices") else str(response))
        if is_maps and live_context and "```map" not in content:
            content = f"{live_context}\n\n{content}"
        return content, response.provider, response.model
    except Exception as exc:
        log.warning("router.route.failed_fallback", error=str(exc))
        if live_context:
            prov = "maps_service" if is_maps else ("weather_service" if is_weather else "web_search")
            mod = "google_maps" if is_maps else ("open-meteo" if is_weather else "tavily")
            if session_id:
                await _persist_runtime_interaction(
                    session_id, user_id or "", user_message, live_context, prov, mod
                )
            return live_context, prov, mod
        if grounded_chunks:
            rag_fallback = (
                "Based on your documents:\n\n"
                + "\n\n".join(grounded_chunks)
            )
            if session_id:
                await _persist_runtime_interaction(
                    session_id, user_id or "", user_message, rag_fallback, "vault", "knowledge-agent"
                )
            return rag_fallback, "vault", "knowledge-agent"
        if is_finance and user_id:
            try:
                from app.finance.repository import FinanceRepository
                fin_repo = FinanceRepository()
                fin_accs = await fin_repo.list_accounts(user_id)
                if fin_accs:
                    tot_usd = sum(a.balance_usd for a in fin_accs)
                    tot_pkr = sum(a.balance_pkr for a in fin_accs)
                    acc_names = ", ".join(f"{a.institution_name} ({a.account_holder})" for a in fin_accs)
                    fin_resp = (
                        f"Your total balance across connected accounts is ${tot_usd:,.2f} USD (Rs {tot_pkr:,.0f} PKR). "
                        f"Active connected accounts include: {acc_names}."
                    )
                else:
                    fin_resp = (
                        "You currently have no bank accounts or payment services connected. "
                        "You can connect an institution using Plaid or link a Raast account to track your balances and transactions."
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, fin_resp, "finance", "financial-agent"
                    )
                return fin_resp, "finance", "financial-agent"
            except Exception:
                pass
        if is_calendar and user_id:
            try:
                from app.calendar.repository import CalendarRepository
                cal_repo = CalendarRepository()
                user_events = await cal_repo.list_events(user_id)
                if user_events:
                    ev_lines = [
                        f"- **{e['title']}** (Time: `{e['start_time']}`, Category: {e.get('category', 'meeting')}, Location: {e.get('location') or 'Not specified'})"
                        for e in user_events
                    ]
                    cal_resp = (
                        f"You currently have {len(user_events)} event(s) on your calendar:\n\n"
                        + "\n".join(ev_lines)
                        + "\n\nYou can manage your appointments or export/import ICS files in your Calendar view."
                    )
                else:
                    cal_resp = (
                        "You currently have no events scheduled on your calendar. "
                        "You can schedule a new meeting, reminder, or appointment anytime!"
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, cal_resp, "calendar", "calendar-agent"
                    )
                return cal_resp, "calendar", "calendar-agent"
            except Exception:
                pass
        if is_email and user_id:
            try:
                from app.emails.repository import EmailRepository
                email_repo = EmailRepository()
                user_emails = await email_repo.list_messages(user_id, limit=10)
                drafts = [m for m in user_emails if m.get("status") == "draft"]
                sent_msgs = [m for m in user_emails if m.get("status") == "sent"]
                if user_emails:
                    msg_lines = [
                        f"- [{m.get('status', 'draft').upper()}] **{m.get('subject', 'No Subject')}** (To: `{m.get('to', '')}`)"
                        for m in user_emails[:5]
                    ]
                    email_resp = (
                        f"You currently have {len(user_emails)} message(s) in your communications hub "
                        f"({len(drafts)} draft(s), {len(sent_msgs)} sent):\n\n"
                        + "\n".join(msg_lines)
                        + "\n\nYou can manage your drafts, polish email copy, or dispatch messages in your Email panel."
                    )
                else:
                    email_resp = (
                        "You currently have no email drafts or sent messages in your communications hub. "
                        "You can compose a new draft, choose a template, or ask me to draft one for you anytime!"
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, email_resp, "email", "email-specialist"
                    )
                return email_resp, "email", "email-specialist"
            except Exception:
                pass
        if is_image_gallery and user_id:
            try:
                from app.images.repository import ImageStudioRepository
                img_repo = ImageStudioRepository()
                gens = await img_repo.list_generations(user_id, limit=10)
                if gens:
                    gen_lines = [
                        f"- **\"{g.get('prompt')}\"** (Style: `{g.get('style_preset', 'photorealistic')}`, Aspect: `{g.get('aspect_ratio', '1:1')}`, Favorited: {g.get('is_favorite', False)})"
                        for g in gens[:5]
                    ]
                    img_resp = (
                        f"You currently have {len(gens)} saved image generation(s) in your studio gallery:\n\n"
                        + "\n".join(gen_lines)
                        + "\n\nYou can view high-resolution versions, generate variations, or download them in your Image Studio."
                    )
                else:
                    img_resp = (
                        "You currently have no saved images in your studio gallery. "
                        "You can generate stunning artwork, concept designs, or photo variations anytime in your Image Studio!"
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, img_resp, "image-studio", "creative-director"
                    )
                return img_resp, "image-studio", "creative-director"
            except Exception:
                pass
        if is_voice and user_id:
            try:
                from app.voice.repository import VoiceRepository
                voice_repo = VoiceRepository()
                user_recs = await voice_repo.list_recordings(user_id, limit=10)
                if user_recs:
                    v_lines = [
                        f"- **{r.get('title', 'Voice Note')}** (Summary: {r.get('summary') or r.get('transcript', '')[:80]}…)"
                        for r in user_recs[:5]
                    ]
                    voice_resp = (
                        f"You currently have {len(user_recs)} saved voice recording(s) in your voice notes library:\n\n"
                        + "\n".join(v_lines)
                        + "\n\nYou can listen to recordings, review executive summaries, and search transcripts in your Voice Session view."
                    )
                else:
                    voice_resp = (
                        "You currently have no saved voice recordings or notes in your library. "
                        "You can record spoken notes or start a voice session anytime to save audio transcripts!"
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, voice_resp, "voice", "voice-agent"
                    )
                return voice_resp, "voice", "voice-agent"
            except Exception:
                pass
        if is_saved_research and user_id:
            try:
                from app.research.repository import ResearchRepository
                research_repo = ResearchRepository()
                user_reports = await research_repo.list_reports(user_id, limit=10)
                if user_reports:
                    r_lines = [
                        f"- **{r.get('title', 'Research Report')}** (Topic: *{r.get('query', '')}*, Confidence: `{r.get('confidence', 'medium')}`)\n  *Summary:* {str(r.get('summary') or '')[:100]}…"
                        for r in user_reports[:5]
                    ]
                    research_resp = (
                        f"You currently have {len(user_reports)} saved research report(s) in your research library:\n\n"
                        + "\n\n".join(r_lines)
                        + "\n\nYou can launch new autonomous deep research investigations, inspect source citations, and review findings in your Research Hub."
                    )
                else:
                    research_resp = (
                        "You currently have no saved research reports in your library. "
                        "You can launch an autonomous deep research investigation anytime in your Research Hub or ask me to research any topic!"
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, research_resp, "research", "research-specialist"
                    )
                return research_resp, "research", "research-specialist"
            except Exception:
                pass

        if is_browser_task and user_id:
            try:
                from app.browser.repository import BrowserRepository
                browser_repo = BrowserRepository()
                user_tasks = await browser_repo.list_tasks(user_id, limit=10)
                if user_tasks:
                    t_lines = [
                        f"- **{t.get('title', 'Browser Task')}** (Status: `{t.get('status', 'completed')}`, Type: `{t.get('action_type', 'navigate')}`)\n  *Target URL:* {t.get('url', '')}"
                        for t in user_tasks[:5]
                    ]
                    browser_resp = (
                        f"You currently have {len(user_tasks)} browser automation task(s) in your library:\n\n"
                        + "\n\n".join(t_lines)
                        + "\n\nYou can launch web flows, inspect live DOM elements, and extract structured data in your Browser Studio."
                    )
                else:
                    browser_resp = (
                        "You currently have no saved browser automation tasks in your library. "
                        "You can launch a new web flow or inspect any webpage anytime in your Browser Studio!"
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, browser_resp, "browser", "browser-agent"
                    )
                return browser_resp, "browser", "browser-agent"
            except Exception:
                pass

        if is_study and user_id:
            try:
                from app.study.repository import StudyRepository
                study_repo = StudyRepository()
                user_decks = await study_repo.list_decks(user_id, limit=10)
                study_stats = await study_repo.get_study_stats(user_id)
                if user_decks:
                    d_lines = [
                        f"- **{d.get('title', 'Study Deck')}** (Cards: {d.get('card_count', 0)}, Mastery: {d.get('mastery_percentage', 0.0)}%, Subject: `{d.get('subject', 'General')}`)"
                        for d in user_decks[:5]
                    ]
                    study_resp = (
                        f"You currently have {study_stats.get('total_decks', len(user_decks))} study deck(s) with {study_stats.get('total_cards', 0)} flashcards ({study_stats.get('cards_due_for_review', 0)} due for review):\n\n"
                        + "\n".join(d_lines)
                        + "\n\nYou can review flashcards with spaced repetition, generate quizzes, and track mastery in your Study Studio."
                    )
                else:
                    study_resp = (
                        "You currently have no study decks in your library. "
                        "You can create a study deck, generate flashcards from lecture notes, or take practice quizzes anytime in your Study Studio!"
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, study_resp, "study", "study-agent"
                    )
                return study_resp, "study", "study-agent"
            except Exception:
                pass

        if is_coding and user_id:
            try:
                from app.coding.repository import CodeRepository
                coding_repo = CodeRepository()
                user_snippets, snip_total = await coding_repo.list_snippets(user_id, limit=10)
                coding_stats = await coding_repo.get_user_stats(user_id)
                if user_snippets:
                    s_lines = [
                        f"- **{s.get('title', 'Snippet')}** (Language: `{s.get('language', 'python')}`, Favorite: {s.get('is_favorite', False)})"
                        for s in user_snippets[:5]
                    ]
                    coding_resp = (
                        f"You currently have {coding_stats.get('total_snippets', snip_total)} code snippet(s) in your library with {coding_stats.get('total_executions', 0)} sandbox execution(s) ({coding_stats.get('success_rate_percentage', 100.0)}% success rate):\n\n"
                        + "\n".join(s_lines)
                        + "\n\nYou can run code in the sandbox playground, generate solutions, or debug snippets in your Coding Studio."
                    )
                else:
                    coding_resp = (
                        "You currently have no saved code snippets in your library. "
                        "You can write and run code in the interactive playground, generate functions, or debug errors anytime in your Coding Studio!"
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, coding_resp, "coding", "coding-agent"
                    )
                return coding_resp, "coding", "coding-agent"
            except Exception:
                pass

        if is_memory and user_id:
            try:
                from app.memory.repository import MemoryRepository
                mem_repo = MemoryRepository()
                user_mems, mem_total = await mem_repo.list_memories(user_id=user_id, include_soft_deleted=False, limit=10)
                mem_stats = await mem_repo.get_stats(user_id)
                if user_mems:
                    m_lines = [
                        f"- [{m.get('importance', 'normal').upper()}] {m.get('content')} (Tags: {', '.join(m.get('tags', []))})"
                        for m in user_mems[:5]
                    ]
                    mem_resp = (
                        f"You currently have {mem_stats.get('active_memories', mem_total)} active long-term memories in your semantic vault "
                        f"({mem_stats.get('forever_memories', 0)} forever pinned, {mem_stats.get('curator_runs_count', 0)} curator passes executed):\n\n"
                        + "\n".join(m_lines)
                        + "\n\nYou can review, edit, or curate your memories anytime in your Memory Studio."
                    )
                else:
                    mem_resp = (
                        "You currently have no saved long-term memories in your semantic vault. "
                        "You can ask me to remember facts, preferences, or rules anytime, or manage them in your Memory Studio!"
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, mem_resp, "memory", "memory-curator"
                    )
                return mem_resp, "memory", "memory-curator"
            except Exception:
                pass

        if is_audit and user_id:
            try:
                from app.audit.repository import AuditRepository
                audit_repo = AuditRepository()
                today_events = await audit_repo.list_today_events(user_id, limit=10)
                audit_stats = await audit_repo.get_stats(user_id)
                if today_events:
                    ev_lines = [
                        f"- [{e.get('approval_tier', 'T1')}] **{e.get('agent_slug', 'coordinator').upper()}**: {e.get('action')} (Status: `{e.get('status_code', 'ok')}`, Latency: {e.get('latency_ms', 0)}ms)"
                        for e in today_events[:5]
                    ]
                    audit_resp = (
                        f"Here is your activity and audit summary for today:\n\n"
                        f"- **Total Events Recorded:** {audit_stats.get('total_events', len(today_events))}\n"
                        f"- **Events Today:** {audit_stats.get('today_events', len(today_events))}\n"
                        f"- **Retention Policy:** 1-Year Append-Only Log (§10.12)\n\n"
                        f"**Recent Actions Today:**\n" + "\n".join(ev_lines)
                        + "\n\nYou can inspect full details, filter by approval tier, and export your audit archive in the Audit & Security Studio."
                    )
                else:
                    audit_resp = (
                        f"Here is your activity and audit summary for today:\n\n"
                        f"- **Total Events Recorded:** {audit_stats.get('total_events', 0)}\n"
                        f"- **Events Today:** 0\n"
                        f"- **Retention Policy:** 1-Year Append-Only Log (§10.12)\n\n"
                        "No actions have been logged yet today. You can monitor your activity and security reviews in the Audit & Security Studio."
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, audit_resp, "audit", "security-auditor"
                    )
                return audit_resp, "audit", "security-auditor"
            except Exception:
                pass

        if is_automation and user_id:
            try:
                from app.jobs.repository import JobRepository
                job_repo = JobRepository()
                user_jobs = await job_repo.list_jobs(user_id)
                if user_jobs:
                    job_lines = [
                        f"- **{j.name}** (Schedule: `{j.schedule}`, Status: {j.status}, Next Run: {j.next_run})"
                        for j in user_jobs
                    ]
                    auto_resp = (
                        f"You currently have {len(user_jobs)} automated job(s) configured:\n\n"
                        + "\n".join(job_lines)
                        + "\n\nYou can trigger jobs manually via 'Run Now' or pause/resume them anytime in your Scheduled Jobs dashboard."
                    )
                else:
                    auto_resp = (
                        "You currently have no scheduled automated jobs. "
                        "You can create automated recurring jobs in your Scheduled Jobs dashboard or ask me to schedule tasks for you!"
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, auto_resp, "automation", "scheduler-engine"
                    )
                return auto_resp, "automation", "scheduler-engine"
            except Exception:
                pass
        if is_workspace and user_id:
            try:
                from app.projects.repository import ProjectRepository
                proj_repo = ProjectRepository()
                user_projects = await proj_repo.list_projects(user_id)
                if user_projects:
                    p_lines = []
                    for p in user_projects:
                        tasks = await proj_repo.list_tasks(user_id, p["id"]) or []
                        c_done = sum(1 for t in tasks if t["status"] == "done")
                        p_lines.append(f"- **{p['name']}** (Status: `{p['status']}`, Tasks: {c_done}/{len(tasks)} completed)")
                    ws_resp = (
                        f"You currently have {len(user_projects)} project(s) configured in your Workspace Hub:\n\n"
                        + "\n".join(p_lines)
                        + "\n\nYou can manage deliverables, track tasks, and link documents in your Workspace Hub dashboard."
                    )
                else:
                    ws_resp = (
                        "You currently have no active workspace projects. "
                        "You can create a project in your Workspace Hub to organize multi-turn workflows, tasks, and documents!"
                    )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, ws_resp, "workspace", "workspace-engine"
                    )
                return ws_resp, "workspace", "workspace-engine"
            except Exception:
                pass
        if is_billing and user_id:
            try:
                from app.billing.repository import BillingRepository
                billing_repo = BillingRepository()
                sub = await billing_repo.get_subscription(user_id)
                wallet = await billing_repo.get_credit_wallet(user_id)
                invoices = await billing_repo.list_invoices(user_id)
                plan_info = sub.get("plan", {})
                plan_name = plan_info.get("name", "Free (BYOK)")
                plan_status = plan_info.get("status", "active")
                remaining = wallet.get("remaining_credits", 100.0)
                used = wallet.get("used_this_month", 0.0)
                billing_resp = (
                    f"Here is your current billing & subscription overview:\n\n"
                    f"- **Active Plan:** {plan_name} (Status: `{plan_status}`)\n"
                    f"- **Remaining AI Credits:** {remaining:,.0f}\n"
                    f"- **Credits Used This Month:** {used:,.0f}\n"
                    f"- **Invoices on File:** {len(invoices)}\n\n"
                    f"You can upgrade your plan, purchase top-up credits, or manage payment methods in your Billing & Subscription settings."
                )
                if session_id:
                    await _persist_runtime_interaction(
                        session_id, user_id or "", user_message, billing_resp, "billing", "billing-agent"
                    )
                return billing_resp, "billing", "billing-agent"
            except Exception:
                pass
        lower = user_message.lower()
        if "python" in lower or "variable" in lower or "write code" in lower or "programming" in lower:
            fallback_code = (
                "Here is a complete Python guide and code example on variables:\n\n"
                "```python\n"
                "# 1. Variable Assignment & Data Types\n"
                "user_name = \"Alex\"             # str\n"
                "user_age = 25                  # int\n"
                "wallet_balance = 340.50        # float\n"
                "is_subscribed = True           # bool\n\n"
                "# 2. Structured Data\n"
                "hobbies = [\"Coding\", \"AI\", \"Design\"]\n"
                "profile = {\n"
                "    \"name\": user_name,\n"
                "    \"age\": user_age,\n"
                "    \"balance\": wallet_balance,\n"
                "    \"hobbies\": hobbies,\n"
                "}\n\n"
                "# 3. Displaying Variables\n"
                "print(f\"User: {profile['name']}, Age: {profile['age']}\")\n"
                "print(f\"Balance: ${profile['balance']:.2f}\")\n"
                "print(f\"Hobbies: {', '.join(profile['hobbies'])}\")\n"
                "```\n\n"
                "In Python, variables are dynamically typed and reference memory objects automatically."
            )
            if session_id:
                await _persist_runtime_interaction(
                    session_id, user_id or "", user_message, fallback_code, "coding", "python-interpreter"
                )
            return fallback_code, "coding", "python-interpreter"
        elif lower in ("i", "hi", "hello", "hey"):
            fallback_greeting = "Hello! I am ROXY, your autonomous AI assistant. How can I help you today?"
            if session_id:
                await _persist_runtime_interaction(
                    session_id, user_id or "", user_message, fallback_greeting, "general", "assistant"
                )
            return fallback_greeting, "general", "assistant"
        raise


async def _run_critic_preflight(
    agent_response: str,
    agent_slug: str,
    user_message: str,
) -> dict[str, Any] | None:
    """Run silent critic pre-flight on a specialist response.

    Returns the critic review dict, or None if it fails.
    """
    try:
        executor = critic_review_executor()
        req = CriticReviewRequest(
            content=(
                f"[User query]\n{user_message}\n\n"
                f"[{agent_slug} agent response]\n{agent_response}"
            ),
            type="text",
            depth="quick",
            criteria=["logic", "clarity", "helpfulness"],
        )
        result = await executor.execute(req)
        return {
            "verdict": result.verdict,
            "overall": result.overall,
            "strengths": result.strengths,
            "weaknesses": [
                {"name": w.name, "why_it_matters": w.why_it_matters}
                for w in result.weaknesses
            ],
            "summary": result.summary,
        }
    except Exception as exc:
        log.warning("critic_preflight.failed", agent=agent_slug, error=str(exc))
        return None


# ---------------------------------------------------------------------------
# POST /api/v1/runtime/chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=RuntimeChatResponse)
async def runtime_chat(
    body: RuntimeChatRequest,
    current_user: User | None = Depends(get_optional_current_user),
) -> RuntimeChatResponse:
    """One-shot Coordinator chat — classify intent, route to agent, return response."""
    effective_user_id = str(current_user.id) if current_user else "guest_trial"

    # Fast-path for pure greetings (<50ms) without invoking external LLMs
    from app.api.v1.greeting import get_warm_greeting, is_greeting
    if not body.agent_override and is_greeting(body.message):
        warm_reply, _ = get_warm_greeting(body.message)
        if body.session_id:
            await _persist_runtime_interaction(
                body.session_id,
                effective_user_id,
                body.message,
                warm_reply,
                "local_fast_greeting",
                "greeting_assistant",
            )
        return RuntimeChatResponse(
            response=warm_reply,
            agent_slug="greeting_assistant",
            critic_review=None,
        )

    agent_slug = body.agent_override or classify_intent(body.message)

    log.info(
        "runtime.chat",
        user_id=effective_user_id,
        message_preview=body.message[:80],
        agent=agent_slug,
        session_id=body.session_id,
        provider=body.provider,
        model=body.model,
    )

    try:
        response_text, resolved_agent_slug, _ = await _call_ai_for_agent(
            agent_slug,
            body.message,
            user_id=effective_user_id,
            session_id=body.session_id,
            provider=body.provider,
            model=body.model,
        )

        final_agent_slug = agent_slug if agent_slug != "general" else (resolved_agent_slug or "general")

        # Silent critic pre-flight — skip for very short responses or image generator
        critic_review: dict[str, Any] | None = None
        if len(response_text) > 200 and final_agent_slug != "image_generator":
            critic_review = await _run_critic_preflight(
                response_text, final_agent_slug, body.message
            )
            log.info(
                "runtime.critic_preflight",
                agent=final_agent_slug,
                verdict=critic_review.get("verdict") if critic_review else None,
            )

        return RuntimeChatResponse(
            response=response_text,
            agent_slug=final_agent_slug,
            critic_review=critic_review,
        )

    except Exception as exc:
        log.error("runtime.chat.error", agent=agent_slug, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Runtime error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# POST /api/v1/runtime/chat/stream
# ---------------------------------------------------------------------------

@router.post("/chat/stream")
async def runtime_chat_stream(
    body: RuntimeChatRequest,
    current_user: User | None = Depends(get_optional_current_user),
) -> StreamingResponse:
    """Streaming Coordinator chat — same as /chat but SSE with Critic pre-flight on final chunk."""
    effective_user_id = str(current_user.id) if current_user else "guest_trial"

    # Fast-path for pure greetings (<50ms) in streaming mode
    from app.api.v1.greeting import get_warm_greeting, is_greeting
    if not body.agent_override and is_greeting(body.message):
        warm_reply, _ = get_warm_greeting(body.message)

        async def greeting_stream() -> AsyncGenerator[bytes, None]:
            if body.session_id:
                await _persist_runtime_interaction(
                    body.session_id,
                    effective_user_id,
                    body.message,
                    warm_reply,
                    "local_fast_greeting",
                    "greeting_assistant",
                )
            words = warm_reply.split(" ")
            for idx, word in enumerate(words):
                chunk = word if idx == len(words) - 1 else word + " "
                data = json.dumps({
                    "delta": chunk,
                    "provider": "local_fast_greeting",
                    "model": "greeting_assistant",
                    "done": False,
                    "agent_slug": "greeting_assistant",
                })
                yield f"data: {data}\n\n".encode()
            done_data = json.dumps({
                "delta": "",
                "provider": "local_fast_greeting",
                "model": "greeting_assistant",
                "done": True,
                "agent_slug": "greeting_assistant",
            })
            yield f"data: {done_data}\n\n".encode()
            final_attr = json.dumps({
                "done": True,
                "provider": "local_fast_greeting",
                "model": "greeting_assistant",
                "agent_slug": "greeting_assistant",
            })
            yield f"event: attribution\ndata: {final_attr}\n\n".encode()

        return StreamingResponse(
            greeting_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    is_img, img_prompt = check_image_intent(body.message)
    if is_img or body.agent_override == "image_generator":
        prompt = img_prompt or body.message
        async def image_stream() -> AsyncGenerator[bytes, None]:
            img_res = generate_image_response(prompt)
            if current_user:
                try:
                    from app.images.repository import ImageStudioRepository
                    img_repo = ImageStudioRepository()
                    cleaned_p = prompt.strip()
                    enc_p = urllib.parse.quote(cleaned_p)
                    i_url = f"https://image.pollinations.ai/prompt/{enc_p}?width=1024&height=1024&nologo=true&enhance=true"
                    await img_repo.create_generation(
                        user_id=effective_user_id,
                        prompt=cleaned_p,
                        media_url=i_url,
                        style_preset="photorealistic",
                        aspect_ratio="1:1",
                        width=1024,
                        height=1024,
                        model="flux",
                    )
                except Exception as exc:
                    log.warning("runtime.stream_image_persist_failed", error=str(exc))
            if body.session_id:
                await _persist_runtime_interaction(
                    body.session_id, effective_user_id, body.message, img_res, "roxy_vision", "flux-diffusion"
                )
            data = json.dumps({
                "delta": img_res,
                "provider": "roxy_vision",
                "model": "flux-diffusion",
                "done": True,
                "agent_slug": "image_generator",
            })
            yield f"data: {data}\n\n".encode()
            final = json.dumps({
                "done": True,
                "provider": "roxy_vision",
                "model": "flux-diffusion",
                "agent_slug": "image_generator",
            })
            yield f"event: attribution\ndata: {final}\n\n".encode()

        return StreamingResponse(
            image_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    agent_slug = body.agent_override or classify_intent(body.message)

    log.info(
        "runtime.chat.stream",
        user_id=effective_user_id,
        message_preview=body.message[:80],
        agent=agent_slug,
        provider=body.provider,
        model=body.model,
    )

    async def event_generator() -> AsyncGenerator[bytes, None]:
        provider_name = body.provider or "unknown"
        model_name = body.model or "unknown"
        full_response: list[str] = []
        chunks_yielded = False

        try:
            system_prompt = _get_agent_prompt(agent_slug)
            history_messages: list[Message] = [Message(role=MessageRole.SYSTEM, content=system_prompt)]
            if body.session_id and current_user:
                try:
                    from app.chat_history.repository import ChatMessageRepository
                    repo = ChatMessageRepository()
                    rows = await repo.list_for_session(body.session_id, effective_user_id, limit=8)
                    for r in rows:
                        role = MessageRole.USER if r.role == "user" else MessageRole.ASSISTANT
                        history_messages.append(Message(role=role, content=r.content))
                except Exception:
                    pass
            is_maps, maps_q = check_maps_intent(body.message)
            is_search, search_q, is_weather, city = check_search_or_weather_intent(body.message)
            live_context: str | None = None
            if is_maps:
                live_context = await fetch_live_maps(maps_q)
            elif is_weather:
                live_context = await fetch_live_weather(city)
                if not live_context:
                    live_context = await fetch_live_search(f"current weather in {city or 'today'}")
            elif (is_search or agent_slug == "research") and not any(
                w in body.message.lower()
                for w in (
                    "saved research",
                    "saved report",
                    "saved reports",
                    "my research",
                    "my reports",
                    "in my library",
                    "saved investigations",
                    "have any saved",
                )
            ):
                live_context = await fetch_live_search(search_q)

            if live_context:
                history_messages.append(
                    Message(
                        role=MessageRole.SYSTEM,
                        content=(
                            f"[LIVE REAL-TIME GROUND TRUTH DATA RETRIEVED AT RUNTIME]:\n"
                            f"{live_context}\n\n"
                            "Use this authoritative live data to directly answer the user's inquiry with exact numbers, conditions, and sources."
                        ),
                    )
                )

            # ── Knowledge Vault RAG Grounding ──────────────────────────────
            try:
                from app.skills.document_rag_query import DocumentRAGSkill
                from app.skills.schemas import DocumentRagQueryRequest
                rag_skill = DocumentRAGSkill()
                rag_res = await rag_skill.execute(
                    DocumentRagQueryRequest(
                        query=body.message,
                        user_id=effective_user_id,
                        top_k=3,
                        min_score=0.20,
                    )
                )
                if rag_res.chunks:
                    grounded_chunks = [
                        f"[Source: {c.document_name}]\n{c.content}"
                        for c in rag_res.chunks
                        if c.relevance_score >= 0.20
                    ]
                    if grounded_chunks:
                        history_messages.append(
                            Message(
                                role=MessageRole.SYSTEM,
                                content=(
                                    "[KNOWLEDGE VAULT CONTEXT — USER PRIVATE DOCUMENTS]:\n"
                                    + "\n\n".join(grounded_chunks)
                                    + "\n\nGround your answer using the excerpts above. Include citation [Source: <document_name>] when referencing document facts."
                                ),
                            )
                        )
            except Exception as exc:
                log.warning("runtime.stream_rag_grounding_failed", error=str(exc))

            # Phase 9: Workspace & Project Management Grounding for stream
            is_workspace = (agent_slug in ("workspace", "project", "projects")) or any(
                w in body.message.lower() for w in ("project", "workspace", "milestone", "action item", "kanban")
            )
            if effective_user_id and is_workspace:
                try:
                    from app.projects.repository import ProjectRepository
                    proj_repo = ProjectRepository()
                    user_projects = await proj_repo.list_projects(effective_user_id)
                    if user_projects:
                        proj_lines = []
                        for p in user_projects:
                            tasks = await proj_repo.list_tasks(effective_user_id, p["id"]) or []
                            t_summary = f"{sum(1 for t in tasks if t['status'] == 'done')}/{len(tasks)} tasks completed"
                            proj_lines.append(f"- **{p['name']}** (Status: {p['status']}, Progress: {t_summary})")
                        proj_context = (
                            "[WORKSPACE HUB CONTEXT — USER PROJECTS & ACTION ITEMS]:\n"
                            f"Total Configured Projects: {len(user_projects)}\n"
                            "Active Projects:\n" + "\n".join(proj_lines)
                            + "\n\nUse this live workspace and project data to accurately answer the user's inquiry regarding their projects, deliverables, and tasks."
                        )
                        history_messages.append(Message(role=MessageRole.SYSTEM, content=proj_context))
                except Exception as exc:
                    log.warning("runtime.stream_workspace_grounding_failed", error=str(exc))

            # Phase 11: Calendar & Event Scheduling Grounding for stream
            is_calendar = (agent_slug in ("calendar", "scheduler")) or (
                agent_slug != "automation"
                and any(
                    w in body.message.lower()
                    for w in (
                        "calendar",
                        "meeting",
                        "appointment",
                        "agenda",
                        "events today",
                        "am i free",
                        "on my schedule",
                        "on my calendar",
                        "calendar schedule",
                    )
                )
            )
            if effective_user_id and is_calendar:
                try:
                    from app.calendar.repository import CalendarRepository
                    cal_repo = CalendarRepository()
                    user_events = await cal_repo.list_events(effective_user_id)
                    if user_events:
                        ev_lines = [
                            f"- **{e['title']}** (Time: `{e['start_time']}`, Category: {e.get('category', 'meeting')}, Location: {e.get('location') or 'Not specified'})"
                            for e in user_events[:10]
                        ]
                        cal_context = (
                            "[CALENDAR CONTEXT — UPCOMING USER EVENTS & SCHEDULE]:\n"
                            f"Total Scheduled Events: {len(user_events)}\n"
                            "Events:\n" + "\n".join(ev_lines)
                            + "\n\nUse this live schedule to answer the user's questions about their calendar, appointments, and availability."
                        )
                        history_messages.append(Message(role=MessageRole.SYSTEM, content=cal_context))
                except Exception as exc:
                    log.warning("runtime.stream_calendar_grounding_failed", error=str(exc))

            # Phase 12: Email & Communications Grounding for stream
            is_email = (agent_slug in ("email", "communications")) or any(
                w in body.message.lower()
                for w in (
                    "email",
                    "emails",
                    "outbox",
                    "drafts",
                    "draft an email",
                    "sent email",
                    "sent mail",
                    "compose email",
                    "write an email",
                    "send an email",
                    "email draft",
                )
            )
            if effective_user_id and is_email:
                try:
                    from app.emails.repository import EmailRepository
                    email_repo = EmailRepository()
                    user_emails = await email_repo.list_messages(effective_user_id, limit=10)
                    drafts = [m for m in user_emails if m.get("status") == "draft"]
                    sent_msgs = [m for m in user_emails if m.get("status") == "sent"]
                    email_lines = [
                        f"- [{m.get('status', 'draft').upper()}] **{m.get('subject', 'No Subject')}** (To: `{m.get('to', '')}`, Date: `{m.get('created_at', '')}`)"
                        for m in user_emails[:10]
                    ]
                    email_context = (
                        "[EMAIL CONTEXT — RECENT OUTBOX & DRAFTS]:\n"
                        f"Total Messages: {len(user_emails)} (Drafts: {len(drafts)}, Sent: {len(sent_msgs)})\n"
                        "Recent Emails:\n" + ("\n".join(email_lines) if email_lines else "None")
                        + "\n\nUse this authentic email history to assist the user with composing, reviewing drafts, or checking sent communications."
                    )
                    history_messages.append(Message(role=MessageRole.SYSTEM, content=email_context))
                except Exception as exc:
                    log.warning("runtime.stream_email_grounding_failed", error=str(exc))

            # Phase 10: Image Studio Gallery Grounding for stream
            is_image_gallery = any(
                w in body.message.lower()
                for w in (
                    "my image gallery",
                    "image gallery",
                    "my generated images",
                    "generated artwork",
                    "saved artwork",
                    "my images",
                    "artwork in my studio",
                    "saved images",
                    "image studio",
                )
            )
            if effective_user_id and is_image_gallery:
                try:
                    from app.images.repository import ImageStudioRepository
                    img_repo = ImageStudioRepository()
                    gens = await img_repo.list_generations(effective_user_id, limit=10)
                    gen_lines = [
                        f"- **\"{g.get('prompt')}\"** (Style: `{g.get('style_preset', 'photorealistic')}`, Aspect: `{g.get('aspect_ratio', '1:1')}`, Favorited: {g.get('is_favorite', False)})"
                        for g in gens[:10]
                    ]
                    img_context = (
                        "[IMAGE STUDIO CONTEXT — USER SAVED GENERATIONS & ARTWORK]:\n"
                        f"Total Saved Generations: {len(gens)}\n"
                        "Recent Artwork:\n" + ("\n".join(gen_lines) if gen_lines else "None")
                        + "\n\nUse this authentic image gallery history to assist the user with reviewing past creations, styles, and prompt details."
                    )
                    history_messages.append(Message(role=MessageRole.SYSTEM, content=img_context))
                except Exception as exc:
                    log.warning("runtime.stream_image_gallery_grounding_failed", error=str(exc))

            # Phase 13: Voice & Audio Transcripts Grounding for stream
            is_voice = (agent_slug in ("voice", "audio")) or any(
                w in body.message.lower()
                for w in (
                    "voice note",
                    "voice notes",
                    "voice recording",
                    "voice recordings",
                    "audio recording",
                    "audio recordings",
                    "audio transcript",
                    "voice transcript",
                    "transcribe",
                    "audio note",
                    "audio notes",
                    "recordings",
                )
            )
            if effective_user_id and is_voice:
                try:
                    from app.voice.repository import VoiceRepository
                    voice_repo = VoiceRepository()
                    user_recs = await voice_repo.list_recordings(effective_user_id, limit=10)
                    rec_lines = [
                        f"- **{r.get('title', 'Voice Note')}** (Date: `{r.get('created_at', '')}`, Summary: {r.get('summary') or r.get('transcript', '')[:100]}…)"
                        for r in user_recs[:10]
                    ]
                    voice_context = (
                        "[VOICE CONTEXT — RECENT AUDIO TRANSCRIPTS & RECORDINGS]:\n"
                        f"Total Saved Voice Notes: {len(user_recs)}\n"
                        "Recent Voice Recordings & Transcripts:\n" + ("\n".join(rec_lines) if rec_lines else "None")
                        + "\n\nUse this authentic voice recordings and audio transcripts library to assist the user with reviewing past voice notes, summaries, or finding audio intelligence."
                    )
                    history_messages.append(Message(role=MessageRole.SYSTEM, content=voice_context))
                except Exception as exc:
                    log.warning("runtime.stream_voice_grounding_failed", error=str(exc))

            # Phase 14: Research & Saved Reports Grounding for stream
            is_saved_research = (agent_slug == "research") or any(
                w in body.message.lower()
                for w in (
                    "research report",
                    "research reports",
                    "saved research",
                    "my research",
                    "deep research",
                    "investigation",
                    "investigations",
                )
            )
            if effective_user_id and is_saved_research:
                try:
                    from app.research.repository import ResearchRepository
                    research_repo = ResearchRepository()
                    user_reports = await research_repo.list_reports(effective_user_id, limit=10)
                    rep_lines = [
                        f"- **{r.get('title', 'Research Report')}** (Topic: *\"{r.get('query', '')}\"*, Confidence: `{r.get('confidence', 'medium')}`, Summary: {str(r.get('summary') or '')[:120]}…)"
                        for r in user_reports[:10]
                    ]
                    research_context = (
                        "[RESEARCH CONTEXT — SAVED RESEARCH REPORTS & INVESTIGATIONS]:\n"
                        f"Total Saved Research Reports: {len(user_reports)}\n"
                        "Recent Research Reports:\n" + ("\n".join(rep_lines) if rep_lines else "None")
                        + "\n\nUse this authentic research reports library to assist the user with past findings, citations, and continuing investigations."
                    )
                    history_messages.append(Message(role=MessageRole.SYSTEM, content=research_context))
                except Exception as exc:
                    log.warning("runtime.stream_research_grounding_failed", error=str(exc))

            # Phase 15: Browser & Web Automation Grounding for stream
            is_browser_task = (agent_slug == "browser") or any(
                w in body.message.lower()
                for w in (
                    "browser task",
                    "browser tasks",
                    "web automation",
                    "automation flow",
                    "web extraction",
                    "extract table",
                    "inspect dom",
                    "browse website",
                    "navigate to",
                    "fill form",
                )
            )
            if effective_user_id and is_browser_task:
                try:
                    from app.browser.repository import BrowserRepository
                    browser_repo = BrowserRepository()
                    user_tasks = await browser_repo.list_tasks(effective_user_id, limit=10)
                    task_lines = [
                        f"- **{t.get('title', 'Browser Task')}** (URL: `{t.get('url', '')}`, Status: `{t.get('status', 'pending')}`, Type: `{t.get('action_type', 'navigate')}`)"
                        for t in user_tasks[:10]
                    ]
                    browser_context = (
                        "[BROWSER CONTEXT — RECENT WEB AUTOMATION TASKS & EXTRACTIONS]:\n"
                        f"Total Saved Browser Tasks: {len(user_tasks)}\n"
                        "Recent Browser Tasks:\n" + ("\n".join(task_lines) if task_lines else "None")
                        + "\n\nUse this authentic browser automation library to assist the user with web tasks, DOM element inspection, data extraction, and form navigation."
                    )
                    history_messages.append(Message(role=MessageRole.SYSTEM, content=browser_context))
                except Exception as exc:
                    log.warning("runtime.stream_browser_grounding_failed", error=str(exc))

            # Phase 16: Study & Learning Studio Grounding for stream
            is_study = (agent_slug == "study") or any(
                w in body.message.lower()
                for w in (
                    "study deck",
                    "study decks",
                    "flashcard",
                    "flashcards",
                    "quiz",
                    "quizzes",
                    "spaced repetition",
                    "practice quiz",
                    "exam prep",
                    "leitner",
                    "test me",
                    "study guide",
                )
            )
            if effective_user_id and is_study:
                try:
                    from app.study.repository import StudyRepository
                    study_repo = StudyRepository()
                    user_decks = await study_repo.list_decks(effective_user_id, limit=10)
                    deck_lines = [
                        f"- **{d.get('title', 'Study Deck')}** (Subject: `{d.get('subject', 'General')}`, Cards: {d.get('card_count', 0)}, Mastery: {d.get('mastery_percentage', 0.0)}%)"
                        for d in user_decks[:10]
                    ]
                    study_stats = await study_repo.get_study_stats(effective_user_id)
                    study_context = (
                        "[STUDY CONTEXT — USER STUDY DECKS, FLASHCARDS & QUIZZES]:\n"
                        f"Total Study Decks: {study_stats.get('total_decks', 0)}\n"
                        f"Total Flashcards: {study_stats.get('total_cards', 0)}\n"
                        f"Cards Due for Review: {study_stats.get('cards_due_for_review', 0)}\n"
                        f"Average Mastery: {study_stats.get('average_mastery', 0.0)}%\n"
                        f"Completed Quizzes: {study_stats.get('completed_quizzes', 0)}\n"
                        "User Study Decks:\n" + ("\n".join(deck_lines) if deck_lines else "None")
                        + "\n\nUse this authentic study and learning library to assist the user with their flashcards, active recall reviews, quiz prep, and spaced repetition scheduling."
                    )
                    history_messages.append(Message(role=MessageRole.SYSTEM, content=study_context))
                except Exception as exc:
                    log.warning("runtime.stream_study_grounding_failed", error=str(exc))

            # Phase 17: Coding & Developer Studio Grounding for stream
            is_coding = (agent_slug == "coding") or any(
                w in body.message.lower()
                for w in (
                    "write code",
                    "write a function",
                    "debug",
                    "fix bug",
                    "code snippet",
                    "code snippets",
                    "run code",
                    "execute code",
                    "coding playground",
                    "coding studio",
                    "python function",
                    "javascript function",
                    "code library",
                )
            )
            if effective_user_id and is_coding:
                try:
                    from app.coding.repository import CodeRepository
                    coding_repo = CodeRepository()
                    user_snippets, snip_total = await coding_repo.list_snippets(effective_user_id, limit=10)
                    user_executions, exec_total = await coding_repo.list_executions(effective_user_id, limit=5)
                    coding_stats = await coding_repo.get_user_stats(effective_user_id)
                    snip_lines = [
                        f"- **{s.get('title', 'Snippet')}** (Language: `{s.get('language', 'python')}`, Favorite: {s.get('is_favorite', False)})\n  *Code preview:* `{s.get('code', '')[:80]}...`"
                        for s in user_snippets[:5]
                    ]
                    coding_context = (
                        "[CODING CONTEXT — USER SAVED SNIPPETS & RECENT CODE RUNS]:\n"
                        f"Total Saved Snippets: {coding_stats.get('total_snippets', snip_total)}\n"
                        f"Total Code Executions: {coding_stats.get('total_executions', exec_total)}\n"
                        f"Execution Success Rate: {coding_stats.get('success_rate_percentage', 100.0)}%\n"
                        "User Code Snippets:\n" + ("\n".join(snip_lines) if snip_lines else "None")
                        + "\n\nUse this authentic developer library to assist the user with writing, debugging, explaining, and executing code."
                    )
                    history_messages.append(Message(role=MessageRole.SYSTEM, content=coding_context))
                except Exception as exc:
                    log.warning("runtime.stream_coding_grounding_failed", error=str(exc))

            # Phase 18: Semantic Memory Grounding for stream
            is_memory = (agent_slug in ("memory", "curator", "memory-curator")) or any(
                p.search(body.message) for p in _MEMORY_PATTERNS
            )
            if effective_user_id and is_memory:
                try:
                    from app.memory.repository import MemoryRepository
                    mem_repo = MemoryRepository()
                    user_mems, mem_total = await mem_repo.list_memories(user_id=effective_user_id, include_soft_deleted=False, limit=10)
                    mem_stats = await mem_repo.get_stats(effective_user_id)
                    mem_lines = [
                        f"- [{m.get('importance', 'normal').upper()}] {m.get('content')} (Tags: {', '.join(m.get('tags', []))})"
                        for m in user_mems[:8]
                    ]
                    mem_context = (
                        "[SEMANTIC MEMORY CONTEXT — USER PREFERENCES & STORED FACTS]:\n"
                        f"Total Active Memories: {mem_stats.get('active_memories', len(user_mems))} (Forever Pinned: {mem_stats.get('forever_memories', 0)})\n"
                        "Active Long-Term Memories:\n" + ("\n".join(mem_lines) if mem_lines else "None")
                        + "\n\nGround your answer in the user's stored memories and personal preferences."
                    )
                    history_messages.append(Message(role=MessageRole.SYSTEM, content=mem_context))
                except Exception as exc:
                    log.warning("runtime.stream_memory_grounding_failed", error=str(exc))

            # Phase 19: Audit & Security Grounding for stream
            is_audit = (agent_slug in ("audit", "security", "security-privacy")) or any(
                p.search(body.message) for p in _AUDIT_PATTERNS
            )
            if effective_user_id and is_audit:
                try:
                    from app.audit.repository import AuditRepository
                    audit_repo = AuditRepository()
                    today_events = await audit_repo.list_today_events(effective_user_id, limit=10)
                    audit_stats = await audit_repo.get_stats(effective_user_id)
                    event_lines = [
                        f"- [{e.get('approval_tier', 'T1')}] **{e.get('agent_slug', 'coordinator').upper()}**: {e.get('action')} (Status: `{e.get('status_code', 'ok')}`, Latency: {e.get('latency_ms', 0)}ms)\n  *Summary:* {e.get('response_summary', '')[:100]}"
                        for e in today_events[:8]
                    ]
                    audit_context = (
                        "[AUDIT CONTEXT — ACTIONS PERFORMED TODAY & SECURITY LOG]:\n"
                        f"Total Actions Logged: {audit_stats.get('total_events', len(today_events))} (Today: {audit_stats.get('today_events', len(today_events))})\n"
                        f"Approval Tiers: {audit_stats.get('by_tier', {})}\n"
                        f"Status Breakdown: {audit_stats.get('by_status', {})}\n"
                        "Recent Today's Actions:\n" + ("\n".join(event_lines) if event_lines else "None recorded yet today.")
                        + "\n\nUse this authentic audit log data to answer the user's questions about what ROXY/Jarvis did today, action history, and security reviews."
                    )
                    history_messages.append(Message(role=MessageRole.SYSTEM, content=audit_context))
                except Exception as exc:
                    log.warning("runtime.stream_audit_grounding_failed", error=str(exc))

            # Phase 7: Automation & Scheduled Jobs Grounding for stream
            is_automation = not is_calendar and not is_email and (
                (agent_slug in ("automation", "planner")) or any(
                    w in body.message.lower() for w in ("scheduled", "schedule", "reminder", "cron", "recurring task", "recurring job", "scheduled job", "scheduled task", "automation", "automate")
                )
            )
            if effective_user_id and is_automation:
                try:
                    from app.jobs.repository import JobRepository
                    job_repo = JobRepository()
                    user_jobs = await job_repo.list_jobs(effective_user_id)
                    if user_jobs:
                        job_lines = [
                            f"- {j.name} (Schedule: {j.schedule}, Timezone: {j.timezone}, Status: {j.status}, Next Run: {j.next_run})"
                            for j in user_jobs
                        ]
                        job_context = (
                            "[SCHEDULED AUTOMATION CONTEXT — USER ACTIVE TASKS & JOBS]:\n"
                            f"Total Configured Tasks: {len(user_jobs)}\n"
                            "Active Tasks:\n" + "\n".join(job_lines)
                            + "\n\nUse this live scheduled automation data to accurately answer the user's inquiry regarding their scheduled tasks, reminders, and automation."
                        )
                        history_messages.append(Message(role=MessageRole.SYSTEM, content=job_context))
                except Exception as exc:
                    log.warning("runtime.stream_automation_grounding_failed", error=str(exc))

            # Phase 21: Billing, Subscription & Credit Wallet Grounding for stream
            is_billing = (agent_slug in ("billing", "subscription", "payments", "invoicing")) or any(
                p.search(body.message) for p in _BILLING_PATTERNS
            )
            if effective_user_id and is_billing:
                try:
                    from app.billing.repository import BillingRepository
                    billing_repo = BillingRepository()
                    sub = await billing_repo.get_subscription(effective_user_id)
                    wallet = await billing_repo.get_credit_wallet(effective_user_id)
                    invoices = await billing_repo.list_invoices(effective_user_id)
                    plan_info = sub.get("plan", {})
                    plan_name = plan_info.get("name", "Free (BYOK)")
                    plan_status = plan_info.get("status", "active")
                    remaining = wallet.get("remaining_credits", 100.0)
                    used = wallet.get("used_this_month", 0.0)
                    pm = sub.get("payment_method")
                    pm_str = f"{pm.get('brand', 'Card').upper()} ending in {pm.get('last4')}" if pm else "None"
                    billing_context = (
                        "[BILLING & SUBSCRIPTION CONTEXT — USER PLAN, CREDITS & WALLET]:\n"
                        f"Active Subscription Plan: {plan_name} (Status: {plan_status})\n"
                        f"Remaining AI Credits: {remaining:,.0f}\n"
                        f"Credits Used This Month: {used:,.0f}\n"
                        f"Total Invoices on File: {len(invoices)}\n"
                        f"Default Payment Method: {pm_str}\n\n"
                        "Use this live subscription and credit wallet data to accurately answer the user's inquiry regarding their billing, plan, credits, invoices, or subscriptions."
                    )
                    history_messages.append(Message(role=MessageRole.SYSTEM, content=billing_context))
                except Exception as exc:
                    log.warning("runtime.stream_billing_grounding_failed", error=str(exc))

            lang_directive = detect_user_language_instruction(body.message)
            if lang_directive:
                history_messages.append(Message(role=MessageRole.SYSTEM, content=lang_directive))

            history_messages.append(Message(role=MessageRole.USER, content=body.message))

            router_ = AIRouter()
            provider_override = body.provider if (body.provider and body.provider not in ("runtime", "coordinator")) else None
            model_override = body.model if (body.model and body.model not in ("coordinator", "runtime", "auto", "default")) else None
            request = AIRequest(
                messages=history_messages,
                provider=provider_override,
                model=model_override,
                temperature=0.7,
                max_tokens=4096,
                stream=True,
                user_id=effective_user_id,
                session_id=body.session_id,
            )

            if is_maps and live_context:
                chunks_yielded = True
                provider_name = "maps_service"
                model_name = "google_maps"
                data = json.dumps({
                    "delta": live_context + "\n\n",
                    "provider": provider_name,
                    "model": model_name,
                    "done": False,
                    "agent_slug": agent_slug,
                })
                yield f"data: {data}\n\n".encode()

            try:
                async for chunk in router_.route_stream(request):
                    chunks_yielded = True
                    if provider_name in ("unknown", None):
                        provider_name = chunk.provider
                        model_name = chunk.model
                        yield f": provider={provider_name} model={model_name}\n\n".encode()

                    delta = str(getattr(chunk, "delta", None) or getattr(chunk, "content", "") or "")
                    chunk_done = bool(getattr(chunk, "done", False))
                    full_response.append(delta)

                    data = json.dumps({
                        "delta": delta,
                        "provider": getattr(chunk, "provider", provider_name),
                        "model": getattr(chunk, "model", model_name),
                        "done": chunk_done,
                        "agent_slug": agent_slug,
                    })
                    yield f"data: {data}\n\n".encode()

                    if chunk_done:
                        break
            except Exception as stream_err:
                log.warning("router.stream.inner_failed", error=str(stream_err))
                if not chunks_yielded and live_context:
                    chunks_yielded = True
                    provider_name = "maps_service" if is_maps else "research"
                    model_name = "google_maps" if is_maps else "realtime"
                    full_response.append(live_context)
                    if body.session_id:
                        await _persist_runtime_interaction(
                            body.session_id, effective_user_id, body.message, live_context, provider_name, model_name
                        )
                    yield f"data: {json.dumps({'delta': live_context, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()

                if not chunks_yielded and is_workspace and effective_user_id:
                    try:
                        from app.projects.repository import ProjectRepository
                        proj_repo = ProjectRepository()
                        user_projects = await proj_repo.list_projects(effective_user_id)
                        if user_projects:
                            p_lines = []
                            for p in user_projects:
                                tasks = await proj_repo.list_tasks(effective_user_id, p["id"]) or []
                                c_done = sum(1 for t in tasks if t["status"] == "done")
                                p_lines.append(f"- **{p['name']}** (Status: `{p['status']}`, Tasks: {c_done}/{len(tasks)} completed)")
                            ws_resp = (
                                f"You currently have {len(user_projects)} project(s) configured in your Workspace Hub:\n\n"
                                + "\n".join(p_lines)
                                + "\n\nYou can manage deliverables, track tasks, and link documents in your Workspace Hub dashboard."
                            )
                        else:
                            ws_resp = (
                                "You currently have no active workspace projects. "
                                "You can create a project in your Workspace Hub to organize multi-turn workflows, tasks, and documents!"
                            )
                        chunks_yielded = True
                        provider_name = "workspace"
                        model_name = "project-coordinator"
                        full_response.append(ws_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, ws_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': ws_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_workspace_fallback_failed", error=str(err))

                if not chunks_yielded and is_calendar and effective_user_id:
                    try:
                        from app.calendar.repository import CalendarRepository
                        cal_repo = CalendarRepository()
                        user_events = await cal_repo.list_events(effective_user_id)
                        if user_events:
                            ev_lines = [
                                f"- **{e['title']}** (Time: `{e['start_time']}`, Category: {e.get('category', 'meeting')}, Location: {e.get('location') or 'Not specified'})"
                                for e in user_events
                            ]
                            cal_resp = (
                                f"You currently have {len(user_events)} event(s) on your calendar:\n\n"
                                + "\n".join(ev_lines)
                                + "\n\nYou can manage your appointments or export/import ICS files in your Calendar view."
                            )
                        else:
                            cal_resp = (
                                "You currently have no events scheduled on your calendar. "
                                "You can schedule a new meeting, reminder, or appointment anytime!"
                            )
                        chunks_yielded = True
                        provider_name = "calendar"
                        model_name = "calendar-coordinator"
                        full_response.append(cal_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, cal_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': cal_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_calendar_fallback_failed", error=str(err))

                if not chunks_yielded and is_email and effective_user_id:
                    try:
                        from app.emails.repository import EmailRepository
                        email_repo = EmailRepository()
                        user_emails = await email_repo.list_messages(effective_user_id, limit=10)
                        drafts = [m for m in user_emails if m.get("status") == "draft"]
                        sent_msgs = [m for m in user_emails if m.get("status") == "sent"]
                        if user_emails:
                            msg_lines = [
                                f"- [{m.get('status', 'draft').upper()}] **{m.get('subject', 'No Subject')}** (To: `{m.get('to', '')}`)"
                                for m in user_emails[:5]
                            ]
                            email_resp = (
                                f"You currently have {len(user_emails)} message(s) in your communications hub "
                                f"({len(drafts)} draft(s), {len(sent_msgs)} sent):\n\n"
                                + "\n".join(msg_lines)
                                + "\n\nYou can manage your drafts, polish email copy, or dispatch messages in your Email panel."
                            )
                        else:
                            email_resp = (
                                "You currently have no email drafts or sent messages in your communications hub. "
                                "You can compose a new draft, choose a template, or ask me to draft one for you anytime!"
                            )
                        chunks_yielded = True
                        provider_name = "email"
                        model_name = "email-specialist"
                        full_response.append(email_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, email_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': email_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_email_fallback_failed", error=str(err))

                if not chunks_yielded and is_image_gallery and effective_user_id:
                    try:
                        from app.images.repository import ImageStudioRepository
                        img_repo = ImageStudioRepository()
                        gens = await img_repo.list_generations(effective_user_id, limit=10)
                        if gens:
                            gen_lines = [
                                f"- **\"{g.get('prompt')}\"** (Style: `{g.get('style_preset', 'photorealistic')}`, Aspect: `{g.get('aspect_ratio', '1:1')}`, Favorited: {g.get('is_favorite', False)})"
                                for g in gens[:5]
                            ]
                            img_resp = (
                                f"You currently have {len(gens)} saved image generation(s) in your studio gallery:\n\n"
                                + "\n".join(gen_lines)
                                + "\n\nYou can view high-resolution versions, generate variations, or download them in your Image Studio."
                            )
                        else:
                            img_resp = (
                                "You currently have no saved images in your studio gallery. "
                                "You can generate stunning artwork, concept designs, or photo variations anytime in your Image Studio!"
                            )
                        chunks_yielded = True
                        provider_name = "image-studio"
                        model_name = "creative-director"
                        full_response.append(img_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, img_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': img_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_image_gallery_fallback_failed", error=str(err))

                if not chunks_yielded and is_voice and effective_user_id:
                    try:
                        from app.voice.repository import VoiceRepository
                        voice_repo = VoiceRepository()
                        user_recs = await voice_repo.list_recordings(effective_user_id, limit=10)
                        if user_recs:
                            v_lines = [
                                f"- **{r.get('title', 'Voice Note')}** (Summary: {r.get('summary') or r.get('transcript', '')[:80]}…)"
                                for r in user_recs[:5]
                            ]
                            voice_resp = (
                                f"You currently have {len(user_recs)} saved voice recording(s) in your voice notes library:\n\n"
                                + "\n".join(v_lines)
                                + "\n\nYou can listen to recordings, review executive summaries, and search transcripts in your Voice Session view."
                            )
                        else:
                            voice_resp = (
                                "You currently have no saved voice recordings or notes in your library. "
                                "You can record spoken notes or start a voice session anytime to save audio transcripts!"
                            )
                        chunks_yielded = True
                        provider_name = "voice"
                        model_name = "voice-agent"
                        full_response.append(voice_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, voice_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': voice_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_voice_fallback_failed", error=str(err))

                if not chunks_yielded and is_saved_research and effective_user_id:
                    try:
                        from app.research.repository import ResearchRepository
                        research_repo = ResearchRepository()
                        user_reports = await research_repo.list_reports(effective_user_id, limit=10)
                        if user_reports:
                            r_lines = [
                                f"- **{r.get('title', 'Research Report')}** (Topic: *{r.get('query', '')}*, Confidence: `{r.get('confidence', 'medium')}`)\n  *Summary:* {str(r.get('summary') or '')[:100]}…"
                                for r in user_reports[:5]
                            ]
                            research_resp = (
                                f"You currently have {len(user_reports)} saved research report(s) in your research library:\n\n"
                                + "\n\n".join(r_lines)
                                + "\n\nYou can launch new autonomous deep research investigations, inspect source citations, and review findings in your Research Hub."
                            )
                        else:
                            research_resp = (
                                "You currently have no saved research reports in your library. "
                                "You can launch an autonomous deep research investigation anytime in your Research Hub or ask me to research any topic!"
                            )
                        chunks_yielded = True
                        provider_name = "research"
                        model_name = "research-specialist"
                        full_response.append(research_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, research_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': research_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_research_fallback_failed", error=str(err))

                if not chunks_yielded and is_browser_task and effective_user_id:
                    try:
                        from app.browser.repository import BrowserRepository
                        browser_repo = BrowserRepository()
                        user_tasks = await browser_repo.list_tasks(effective_user_id, limit=10)
                        if user_tasks:
                            t_lines = [
                                f"- **{t.get('title', 'Browser Task')}** (Status: `{t.get('status', 'completed')}`, Type: `{t.get('action_type', 'navigate')}`)\n  *Target URL:* {t.get('url', '')}"
                                for t in user_tasks[:5]
                            ]
                            browser_resp = (
                                f"You currently have {len(user_tasks)} browser automation task(s) in your library:\n\n"
                                + "\n\n".join(t_lines)
                                + "\n\nYou can launch web flows, inspect live DOM elements, and extract structured data in your Browser Studio."
                            )
                        else:
                            browser_resp = (
                                "You currently have no saved browser automation tasks in your library. "
                                "You can launch a new web flow or inspect any webpage anytime in your Browser Studio!"
                            )
                        chunks_yielded = True
                        provider_name = "browser"
                        model_name = "browser-operator"
                        full_response.append(browser_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, browser_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': browser_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_browser_fallback_failed", error=str(err))

                if not chunks_yielded and is_study and effective_user_id:
                    try:
                        from app.study.repository import StudyRepository
                        study_repo = StudyRepository()
                        user_decks = await study_repo.list_decks(effective_user_id, limit=10)
                        study_stats = await study_repo.get_study_stats(effective_user_id)
                        if user_decks:
                            d_lines = [
                                f"- **{d.get('title', 'Study Deck')}** (Cards: {d.get('card_count', 0)}, Mastery: {d.get('mastery_percentage', 0.0)}%, Subject: `{d.get('subject', 'General')}`)"
                                for d in user_decks[:5]
                            ]
                            study_resp = (
                                f"You currently have {study_stats.get('total_decks', len(user_decks))} study deck(s) with {study_stats.get('total_cards', 0)} flashcards ({study_stats.get('cards_due_for_review', 0)} due for review):\n\n"
                                + "\n".join(d_lines)
                                + "\n\nYou can review flashcards with spaced repetition, generate quizzes, and track mastery in your Study Studio."
                            )
                        else:
                            study_resp = (
                                "You currently have no study decks in your library. "
                                "You can create a study deck, generate flashcards from lecture notes, or take practice quizzes anytime in your Study Studio!"
                            )
                        chunks_yielded = True
                        provider_name = "study"
                        model_name = "study-agent"
                        full_response.append(study_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, study_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': study_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_study_fallback_failed", error=str(err))

                if not chunks_yielded and is_coding and effective_user_id:
                    try:
                        from app.coding.repository import CodeRepository
                        coding_repo = CodeRepository()
                        user_snippets, snip_total = await coding_repo.list_snippets(effective_user_id, limit=10)
                        coding_stats = await coding_repo.get_user_stats(effective_user_id)
                        if user_snippets:
                            s_lines = [
                                f"- **{s.get('title', 'Snippet')}** (Language: `{s.get('language', 'python')}`, Favorite: {s.get('is_favorite', False)})"
                                for s in user_snippets[:5]
                            ]
                            coding_resp = (
                                f"You currently have {coding_stats.get('total_snippets', snip_total)} code snippet(s) in your library with {coding_stats.get('total_executions', 0)} sandbox execution(s) ({coding_stats.get('success_rate_percentage', 100.0)}% success rate):\n\n"
                                + "\n".join(s_lines)
                                + "\n\nYou can run code in the sandbox playground, generate solutions, or debug snippets in your Coding Studio."
                            )
                        else:
                            coding_resp = (
                                "You currently have no saved code snippets in your library. "
                                "You can write and run code in the interactive playground, generate functions, or debug errors anytime in your Coding Studio!"
                            )
                        chunks_yielded = True
                        provider_name = "coding"
                        model_name = "coding-agent"
                        full_response.append(coding_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, coding_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': coding_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_coding_fallback_failed", error=str(err))

                if not chunks_yielded and is_memory and effective_user_id:
                    try:
                        from app.memory.repository import MemoryRepository
                        mem_repo = MemoryRepository()
                        user_mems, mem_total = await mem_repo.list_memories(user_id=effective_user_id, include_soft_deleted=False, limit=10)
                        mem_stats = await mem_repo.get_stats(effective_user_id)
                        if user_mems:
                            m_lines = [
                                f"- [{m.get('importance', 'normal').upper()}] {m.get('content')} (Tags: {', '.join(m.get('tags', []))})"
                                for m in user_mems[:5]
                            ]
                            mem_resp = (
                                f"You currently have {mem_stats.get('active_memories', mem_total)} active long-term memories in your semantic vault "
                                f"({mem_stats.get('forever_memories', 0)} forever pinned, {mem_stats.get('curator_runs_count', 0)} curator passes executed):\n\n"
                                + "\n".join(m_lines)
                                + "\n\nYou can review, edit, or curate your memories anytime in your Memory Studio."
                            )
                        else:
                            mem_resp = (
                                "You currently have no saved long-term memories in your semantic vault. "
                                "You can ask me to remember facts, preferences, or rules anytime, or manage them in your Memory Studio!"
                            )
                        chunks_yielded = True
                        provider_name = "memory"
                        model_name = "memory-curator"
                        full_response.append(mem_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, mem_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': mem_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_memory_fallback_failed", error=str(err))

                if not chunks_yielded and is_audit and effective_user_id:
                    try:
                        from app.audit.repository import AuditRepository
                        audit_repo = AuditRepository()
                        today_events = await audit_repo.list_today_events(effective_user_id, limit=10)
                        audit_stats = await audit_repo.get_stats(effective_user_id)
                        if today_events:
                            ev_lines = [
                                f"- [{e.get('approval_tier', 'T1')}] **{e.get('agent_slug', 'coordinator').upper()}**: {e.get('action')} (Status: `{e.get('status_code', 'ok')}`, Latency: {e.get('latency_ms', 0)}ms)"
                                for e in today_events[:5]
                            ]
                            audit_resp = (
                                f"Here is your activity and audit summary for today:\n\n"
                                f"- **Total Events Recorded:** {audit_stats.get('total_events', len(today_events))}\n"
                                f"- **Events Today:** {audit_stats.get('today_events', len(today_events))}\n"
                                f"- **Retention Policy:** 1-Year Append-Only Log (§10.12)\n\n"
                                f"**Recent Actions Today:**\n" + "\n".join(ev_lines)
                                + "\n\nYou can inspect full details, filter by approval tier, and export your audit archive in the Audit & Security Studio."
                            )
                        else:
                            audit_resp = (
                                f"Here is your activity and audit summary for today:\n\n"
                                f"- **Total Events Recorded:** {audit_stats.get('total_events', 0)}\n"
                                f"- **Events Today:** 0\n"
                                f"- **Retention Policy:** 1-Year Append-Only Log (§10.12)\n\n"
                                "No actions have been logged yet today. You can monitor your activity and security reviews in the Audit & Security Studio."
                            )
                        chunks_yielded = True
                        provider_name = "audit"
                        model_name = "security-auditor"
                        full_response.append(audit_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, audit_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': audit_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_audit_fallback_failed", error=str(err))

                if not chunks_yielded and is_automation and effective_user_id:
                    try:
                        from app.jobs.repository import JobRepository
                        job_repo = JobRepository()
                        user_jobs = await job_repo.list_jobs(effective_user_id)
                        if user_jobs:
                            job_lines = [
                                f"- **{j.name}** (Schedule: `{j.schedule}`, Status: {j.status}, Next Run: {j.next_run})"
                                for j in user_jobs
                            ]
                            auto_resp = (
                                f"You currently have {len(user_jobs)} automated job(s) configured:\n\n"
                                + "\n".join(job_lines)
                                + "\n\nYou can trigger jobs manually via 'Run Now' or pause/resume them anytime in your Scheduled Jobs dashboard."
                            )
                        else:
                            auto_resp = (
                                "You currently have no scheduled automated jobs. "
                                "You can create automated recurring jobs in your Scheduled Jobs dashboard or ask me to schedule tasks for you!"
                            )
                        chunks_yielded = True
                        provider_name = "automation"
                        model_name = "scheduler-engine"
                        full_response.append(auto_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, auto_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': auto_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_automation_fallback_failed", error=str(err))

                if not chunks_yielded and is_billing and effective_user_id:
                    try:
                        from app.billing.repository import BillingRepository
                        billing_repo = BillingRepository()
                        sub = await billing_repo.get_subscription(effective_user_id)
                        wallet = await billing_repo.get_credit_wallet(effective_user_id)
                        invoices = await billing_repo.list_invoices(effective_user_id)
                        plan_info = sub.get("plan", {})
                        plan_name = plan_info.get("name", "Free (BYOK)")
                        plan_status = plan_info.get("status", "active")
                        remaining = wallet.get("remaining_credits", 100.0)
                        used = wallet.get("used_this_month", 0.0)
                        billing_resp = (
                            f"Here is your current billing & subscription overview:\n\n"
                            f"- **Active Plan:** {plan_name} (Status: `{plan_status}`)\n"
                            f"- **Remaining AI Credits:** {remaining:,.0f}\n"
                            f"- **Credits Used This Month:** {used:,.0f}\n"
                            f"- **Invoices on File:** {len(invoices)}\n\n"
                            f"You can upgrade your plan, purchase top-up credits, or manage payment methods in your Billing & Subscription settings."
                        )
                        chunks_yielded = True
                        provider_name = "billing"
                        model_name = "billing-agent"
                        full_response.append(billing_resp)
                        if body.session_id:
                            await _persist_runtime_interaction(
                                body.session_id, effective_user_id, body.message, billing_resp, provider_name, model_name
                            )
                        yield f"data: {json.dumps({'delta': billing_resp, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()
                    except Exception as err:
                        log.warning("runtime.stream_billing_fallback_failed", error=str(err))










            # Critic pre-flight on full response (only for non-trivial responses)
            if chunks_yielded and len("".join(full_response)) > 200:
                try:
                    critic_review = await _run_critic_preflight(
                        "".join(full_response), agent_slug, body.message
                    )
                    if critic_review:
                        review_data = json.dumps({
                            "type": "critic_review",
                            "review": critic_review,
                        })
                        yield f"data: {review_data}\n\n".encode()
                except Exception as exc:
                    log.warning("runtime.stream.critic_preflight.failed", error=str(exc))

            # Final attribution
            if chunks_yielded:
                final = json.dumps({
                    "done": True,
                    "provider": provider_name,
                    "model": model_name,
                    "agent_slug": agent_slug,
                })
                yield f"event: attribution\ndata: {final}\n\n".encode()

        except Exception as exc:
            import json as _json
            log.error("runtime.chat.stream.error", agent=agent_slug, error=str(exc))
            if is_maps and chunks_yielded:
                if body.session_id and live_context:
                    await _persist_runtime_interaction(
                        body.session_id,
                        effective_user_id,
                        body.message,
                        live_context,
                        "maps_service",
                        "google_maps",
                    )
                final = _json.dumps({
                    "done": True,
                    "provider": "maps_service",
                    "model": "google_maps",
                    "agent_slug": agent_slug,
                })
                yield f"data: {_json.dumps({'delta': '', 'done': True, 'agent_slug': agent_slug, 'provider': 'maps_service', 'model': 'google_maps'})}\n\n".encode()
                yield f"event: attribution\ndata: {final}\n\n".encode()
                return
            if live_context and not chunks_yielded:
                prov_lbl = "maps_service" if is_maps else ("weather_service" if is_weather else "weather_search")
                mod_lbl = "google_maps" if is_maps else ("open-meteo" if is_weather else "tavily")
                if body.session_id:
                    await _persist_runtime_interaction(
                        body.session_id,
                        effective_user_id,
                        body.message,
                        live_context,
                        prov_lbl,
                        mod_lbl,
                    )
                yield f"data: {_json.dumps({'delta': live_context, 'done': True, 'agent_slug': agent_slug, 'provider': prov_lbl, 'model': mod_lbl})}\n\n".encode()
                yield f"event: attribution\ndata: {_json.dumps({'done': True, 'provider': prov_lbl, 'model': mod_lbl, 'agent_slug': agent_slug})}\n\n".encode()
                return
            error_data = _json.dumps({
                "error": "runtime_error",
                "detail": str(exc),
                "done": True,
                "agent_slug": agent_slug,
            })
            yield f"data: {error_data}\n\n".encode()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Runtime document ingestion endpoints
# ---------------------------------------------------------------------------


class RuntimeUploadResponse(BaseModel):
    document_id: str
    document_name: str
    chunks_stored: int
    chunk_ids: list[str]
    doc_type: str
    metadata: dict[str, Any]


class RuntimeDocumentItem(BaseModel):
    document_id: str
    document_name: str
    chunk_count: int
    last_ingested: str | None


class RuntimeDocumentListResponse(BaseModel):
    documents: list[RuntimeDocumentItem]


class RuntimeDocumentDeleteResponse(BaseModel):
    document_id: str
    chunks_deleted: int


class RuntimeDocumentQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=8, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    document_ids: list[str] = Field(default_factory=list)


async def _ingest_document(
    file_bytes: bytes,
    document_name: str,
    filename: str,
    content_type: str,
    replace_existing: bool,
    user_id: str,
) -> RuntimeUploadResponse:
    """Shared ingest logic used by the upload endpoint."""
    from app.skills.document_ingest import (
        _chunk_store,
        _chunk_text,
        _document_meta,
        _make_embedding,
    )
    from app.skills.document_parser import parse_document

    if not document_name:
        document_name = filename or "unnamed"

    # Parse
    result = parse_document(file_bytes, content_type=content_type, filename=filename)
    if result.is_empty():
        raise ValueError("Document text is empty after parsing")

    document_id = str(uuid.uuid4())

    # Replace existing
    if replace_existing:
        user_docs = _document_meta.get(user_id, {})
        if document_id in user_docs:
            for cid in user_docs[document_id].get("chunk_ids", []):
                _chunk_store.pop(cid, None)
            del user_docs[document_id]

    # Chunk
    chunks = _chunk_text(result.content)
    if not chunks:
        raise ValueError("Could not chunk document text")

    # Embed
    embeddings = [_make_embedding(c) for c in chunks]

    # Store
    from datetime import datetime
    chunk_ids: list[str] = []
    now = datetime.now(UTC).isoformat()

    if user_id not in _document_meta:
        _document_meta[user_id] = {}
    user_docs = _document_meta[user_id]
    user_docs[document_id] = {
        "name": document_name,
        "doc_type": result.doc_type,
        "created_at": now,
        "chunk_ids": [],
    }

    for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
        chunk_id = str(uuid.uuid4())
        chunk_ids.append(chunk_id)
        _chunk_store[chunk_id] = {
            "user_id": user_id,
            "doc_id": document_id,
            "content": chunk_text,
            "embedding": embedding,
            "chunk_index": i,
            "page": None,
            "section": None,
        }
        user_docs[document_id]["chunk_ids"].append(chunk_id)

    log.info("runtime.upload.done", document_id=document_id, chunks=len(chunk_ids))

    return RuntimeUploadResponse(
        document_id=document_id,
        document_name=document_name,
        chunks_stored=len(chunk_ids),
        chunk_ids=chunk_ids,
        doc_type=result.doc_type,
        metadata=result.metadata,
    )


# Upload endpoint using multipart form data
@router.post(
    "/upload",
    response_model=RuntimeUploadResponse,
    responses={413: {"description": "File too large"}, 422: {"description": "Could not parse file"}},
)
async def runtime_upload(
    file: UploadFile = File(..., description="File to upload"),
    document_name: str | None = Form(default=None),
    content_type: str = Form(default=""),
    filename: str = Form(default=""),
    replace_existing: bool = Form(default=False),
    current_user: User = Depends(get_current_user),
) -> RuntimeUploadResponse:
    """Parse and ingest a file into the RAG vector store.

    Accepts multipart/form-data with the file and optional metadata fields.
    """
    user_id = str(current_user.id)

    # Read file bytes
    try:
        file_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to read file: {exc}") from exc

    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    if not file_bytes:
        raise HTTPException(status_code=422, detail="Empty file")

    # Determine content type and filename from UploadFile if not provided
    actual_content_type = content_type or (file.content_type or "")
    actual_filename = filename or (file.filename or "unnamed")
    doc_name = (document_name or actual_filename or "unnamed").strip()

    log.info("runtime.upload", user_id=user_id, filename=actual_filename, size=len(file_bytes))

    try:
        return await _ingest_document(
            file_bytes=file_bytes,
            document_name=doc_name,
            filename=actual_filename,
            content_type=actual_content_type,
            replace_existing=replace_existing,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("runtime.upload.failed", user_id=user_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Ingest failed: {exc}") from exc


# ---------------------------------------------------------------------------
# GET /api/v1/runtime/documents
# ---------------------------------------------------------------------------

@router.get("/documents", response_model=RuntimeDocumentListResponse)
async def runtime_list_documents(
    current_user: User = Depends(get_current_user),
) -> RuntimeDocumentListResponse:
    """List all documents ingested by the authenticated user."""
    user_id = str(current_user.id)
    from app.skills.document_ingest import _document_meta

    user_docs = _document_meta.get(user_id, {})

    docs = [
        RuntimeDocumentItem(
            document_id=doc_id,
            document_name=meta.get("name", doc_id),
            chunk_count=len(meta.get("chunk_ids", [])),
            last_ingested=meta.get("created_at"),
        )
        for doc_id, meta in user_docs.items()
    ]

    return RuntimeDocumentListResponse(documents=docs)


# ---------------------------------------------------------------------------
# DELETE /api/v1/runtime/documents/{document_id}
# ---------------------------------------------------------------------------

@router.delete("/documents/{document_id}", response_model=RuntimeDocumentDeleteResponse)
async def runtime_delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
) -> RuntimeDocumentDeleteResponse:
    """Delete a document and all its chunks from the RAG store."""
    user_id = str(current_user.id)
    from app.skills.document_ingest import _chunk_store, _document_meta

    user_docs = _document_meta.get(user_id, {})

    if document_id not in user_docs:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")

    chunk_ids = user_docs[document_id].get("chunk_ids", [])
    for chunk_id in chunk_ids:
        _chunk_store.pop(chunk_id, None)

    chunks_deleted = len(chunk_ids)
    del user_docs[document_id]

    log.info("runtime.delete_document", user_id=user_id, document_id=document_id, chunks_deleted=chunks_deleted)

    return RuntimeDocumentDeleteResponse(document_id=document_id, chunks_deleted=chunks_deleted)


# ---------------------------------------------------------------------------
# POST /api/v1/runtime/documents/query
# ---------------------------------------------------------------------------

@router.post("/documents/query")
async def runtime_documents_query(
    body: RuntimeDocumentQueryRequest,
    current_user: User = Depends(get_current_user),
) -> Any:
    """RAG query over the user's uploaded documents.

    Proxy to the document_rag_query skill with user context injected.
    """
    from app.skills.schemas import DocumentRagQueryRequest

    executor = DocumentRAGSkill()
    req = DocumentRagQueryRequest(
        query=body.query,
        top_k=body.top_k,
        document_ids=body.document_ids if body.document_ids else None,
        user_id=str(current_user.id),
    )
    return await executor.execute(req)

