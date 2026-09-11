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
from pathlib import Path
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request as StarletteRequest, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user, get_optional_current_user
from app.auth.models import User
from app.ai_gateway.models.schemas import AIRequest, AIResponse, Message, MessageRole
from app.ai_gateway.services.router import AIRouter
from app.skills.critic_review import get_executor as critic_review_executor
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
    re.compile(r"\b(flashcard|study|quiz|learn| memorize|revision)\b", re.I),
    re.compile(r"\b(chapter|course|lecture|textbook)\b", re.I),
]

# Browser keywords
_BROWSER_PATTERNS = [
    re.compile(r"\b(browse|navigate|go.to|open.website|visit)\b", re.I),
    re.compile(r"\b(fill.form|submit.form|login|download)\b", re.I),
]


# Image generation keywords
_IMAGE_PATTERNS = [
    re.compile(r"\b(create|generate|make|draw|show|render)\s+(an?\s+)?image\s+(of|about|with)?\b", re.I),
    re.compile(r"\b(create|generate|make|draw|show)\s+(a\s+)?picture\s+(of|about|with)?\b", re.I),
    re.compile(r"\b(image\s+of|photo\s+of|painting\s+of|picture\s+of)\b", re.I),
    re.compile(r"^create\s+an?\s+image\s*:\s*", re.I),
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

    if is_empty_or_generic:
        clean_target = "Paris"
        place_name = "Paris, Île-de-France, France"
        lat, lon = 48.8566, 2.3522
    else:
        clean_target = raw
        place_name = clean_target
        lat: float | None = None
        lon: float | None = None

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
        "finance": sum(1 for p in _FINANCE_PATTERNS if p.search(msg)),
        "critic": sum(1 for p in _CRITIC_PATTERNS if p.search(msg)),
        "automation": sum(1 for p in _AUTOMATION_PATTERNS if p.search(msg)),
        "research": sum(1 for p in _RESEARCH_PATTERNS if p.search(msg)),
        "coding": sum(1 for p in _CODING_PATTERNS if p.search(msg)),
        "study": sum(1 for p in _STUDY_PATTERNS if p.search(msg)),
        "browser": sum(1 for p in _BROWSER_PATTERNS if p.search(msg)),
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
        return generate_image_response(prompt), "roxy_vision", "flux-diffusion"

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
    elif is_search or agent_slug == "research":
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
            return live_context, prov, mod
        lower = user_message.lower()
        if "python" in lower or "variable" in lower or "code" in lower:
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
            return fallback_code, "coding", "python-interpreter"
        elif lower in ("i", "hi", "hello", "hey"):
            return "Hello! I am ROXY, your autonomous AI assistant. How can I help you today?", "general", "assistant"
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
    agent_slug = body.agent_override or classify_intent(body.message)
    effective_user_id = str(current_user.id) if current_user else "guest_trial"

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
        response_text, _, _ = await _call_ai_for_agent(
            agent_slug,
            body.message,
            user_id=effective_user_id,
            session_id=body.session_id,
            provider=body.provider,
            model=body.model,
        )

        # Silent critic pre-flight — skip for very short responses or image generator
        critic_review: dict[str, Any] | None = None
        if len(response_text) > 200 and agent_slug != "image_generator":
            critic_review = await _run_critic_preflight(
                response_text, agent_slug, body.message
            )
            log.info(
                "runtime.critic_preflight",
                agent=agent_slug,
                verdict=critic_review.get("verdict") if critic_review else None,
            )

        return RuntimeChatResponse(
            response=response_text,
            agent_slug=agent_slug,
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
):
    """Streaming Coordinator chat — same as /chat but SSE with Critic pre-flight on final chunk."""
    effective_user_id = str(current_user.id) if current_user else "guest_trial"
    is_img, img_prompt = check_image_intent(body.message)
    if is_img or body.agent_override == "image_generator":
        prompt = img_prompt or body.message
        async def image_stream():
            img_res = generate_image_response(prompt)
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

    async def event_generator():
        provider_name = body.provider or "unknown"
        model_name = body.model or "unknown"
        full_response = []
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
            elif is_search or agent_slug == "research":
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

                    delta = getattr(chunk, "delta", None) or getattr(chunk, "content", "")
                    chunk_done = getattr(chunk, "done", False)
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
                    yield f"data: {json.dumps({'delta': live_context, 'done': True, 'agent_slug': agent_slug, 'provider': provider_name, 'model': model_name})}\n\n".encode()

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

import uuid

from fastapi import File, Form, UploadFile

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
    from app.skills.document_parser import parse_document
    from app.skills.document_ingest import (
        _chunk_store,
        _chunk_text,
        _document_meta,
        _make_embedding,
    )

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
    from datetime import datetime, timezone
    chunk_ids: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    if user_id not in _document_meta:
        _document_meta[user_id] = {}
    user_docs = _document_meta[user_id]
    user_docs[document_id] = {
        "name": document_name,
        "doc_type": result.doc_type,
        "created_at": now,
        "chunk_ids": [],
    }

    for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
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
):
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
):
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
):
    """Delete a document and all its chunks from the RAG store."""
    user_id = str(current_user.id)
    from app.skills.document_ingest import _document_meta, _chunk_store

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
):
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


from app.skills.document_rag_query import DocumentRAGSkill
