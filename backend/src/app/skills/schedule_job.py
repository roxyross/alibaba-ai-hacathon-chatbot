"""schedule_job skill — create, list, update, cancel scheduled jobs.

Uses an in-memory job store with JSON persistence.
Fires jobs by calling the CronCreate/CronDelete/CronList tools at runtime.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import delete, select, update

from app.db import get_session_factory
from app.models.scheduled_job import ScheduledJob
from app.skills.base import SkillExecutor
from app.skills.schemas import (
    JobAction,
    JobEntry,
    ScheduleJobOp,
    ScheduleJobRequest,
    ScheduleJobResponse,
)

log = structlog.get_logger()

# Minimum interval: 1 minute
MIN_INTERVAL_SECONDS = 60

# Known agents and their valid skills (guardrail: reject unknown agents/skills)
VALID_AGENTS = {"research", "files", "coding", "planner", "browser", "study", "voice", "automation", "email", "web_search"}
VALID_SKILLS = {
    "web_search", "document_rag_query", "store_memory", "retrieve_memory",
    "email_draft", "browser_navigate", "flashcard_generate", "quiz_generate",
    "schedule_job", "calendar_read", "calculator", "speech_to_text", "text_to_speech",
}


GLOBAL_TIMEZONES: list[dict[str, Any]] = [
    # --- South Asia & Gulf ---
    {"value": "Asia/Karachi", "label": "🇵🇰 Asia/Karachi (PKT - UTC+5)", "region": "South Asia & Gulf", "offset": "UTC+5", "country": "Pakistan"},
    {"value": "Asia/Kolkata", "label": "🇮🇳 Asia/Kolkata (IST - UTC+5:30)", "region": "South Asia & Gulf", "offset": "UTC+5:30", "country": "India"},
    {"value": "Asia/Dhaka", "label": "🇧🇩 Asia/Dhaka (BST - UTC+6)", "region": "South Asia & Gulf", "offset": "UTC+6", "country": "Bangladesh"},
    {"value": "Asia/Colombo", "label": "🇱🇰 Asia/Colombo (SLST - UTC+5:30)", "region": "South Asia & Gulf", "offset": "UTC+5:30", "country": "Sri Lanka"},
    {"value": "Asia/Kathmandu", "label": "🇳🇵 Asia/Kathmandu (NPT - UTC+5:45)", "region": "South Asia & Gulf", "offset": "UTC+5:45", "country": "Nepal"},
    {"value": "Asia/Dubai", "label": "🇦🇪 Asia/Dubai (GST - UTC+4)", "region": "South Asia & Gulf", "offset": "UTC+4", "country": "United Arab Emirates"},
    {"value": "Asia/Riyadh", "label": "🇸🇦 Asia/Riyadh (AST - UTC+3)", "region": "South Asia & Gulf", "offset": "UTC+3", "country": "Saudi Arabia"},
    {"value": "Asia/Qatar", "label": "🇶🇦 Asia/Qatar (AST - UTC+3)", "region": "South Asia & Gulf", "offset": "UTC+3", "country": "Qatar"},
    {"value": "Asia/Kuwait", "label": "🇰🇼 Asia/Kuwait (AST - UTC+3)", "region": "South Asia & Gulf", "offset": "UTC+3", "country": "Kuwait"},
    {"value": "Asia/Muscat", "label": "🇴🇲 Asia/Muscat (GST - UTC+4)", "region": "South Asia & Gulf", "offset": "UTC+4", "country": "Oman"},
    {"value": "Asia/Bahrain", "label": "🇧🇭 Asia/Bahrain (AST - UTC+3)", "region": "South Asia & Gulf", "offset": "UTC+3", "country": "Bahrain"},

    # --- East & Southeast Asia ---
    {"value": "Asia/Singapore", "label": "🇸🇬 Asia/Singapore (SGT - UTC+8)", "region": "East & Southeast Asia", "offset": "UTC+8", "country": "Singapore"},
    {"value": "Asia/Kuala_Lumpur", "label": "🇲🇾 Asia/Kuala_Lumpur (MYT - UTC+8)", "region": "East & Southeast Asia", "offset": "UTC+8", "country": "Malaysia"},
    {"value": "Asia/Bangkok", "label": "🇹🇭 Asia/Bangkok (ICT - UTC+7)", "region": "East & Southeast Asia", "offset": "UTC+7", "country": "Thailand"},
    {"value": "Asia/Jakarta", "label": "🇮🇩 Asia/Jakarta (WIB - UTC+7)", "region": "East & Southeast Asia", "offset": "UTC+7", "country": "Indonesia"},
    {"value": "Asia/Makassar", "label": "🇮🇩 Asia/Makassar (WITA - UTC+8)", "region": "East & Southeast Asia", "offset": "UTC+8", "country": "Indonesia"},
    {"value": "Asia/Manila", "label": "🇵🇭 Asia/Manila (PST/PHT - UTC+8)", "region": "East & Southeast Asia", "offset": "UTC+8", "country": "Philippines"},
    {"value": "Asia/Ho_Chi_Minh", "label": "🇻🇳 Asia/Ho_Chi_Minh (ICT - UTC+7)", "region": "East & Southeast Asia", "offset": "UTC+7", "country": "Vietnam"},
    {"value": "Asia/Shanghai", "label": "🇨🇳 Asia/Shanghai (CST - UTC+8)", "region": "East & Southeast Asia", "offset": "UTC+8", "country": "China"},
    {"value": "Asia/Hong_Kong", "label": "🇭🇰 Asia/Hong_Kong (HKT - UTC+8)", "region": "East & Southeast Asia", "offset": "UTC+8", "country": "Hong Kong"},
    {"value": "Asia/Taipei", "label": "🇹🇼 Asia/Taipei (CST - UTC+8)", "region": "East & Southeast Asia", "offset": "UTC+8", "country": "Taiwan"},
    {"value": "Asia/Tokyo", "label": "🇯🇵 Asia/Tokyo (JST - UTC+9)", "region": "East & Southeast Asia", "offset": "UTC+9", "country": "Japan"},
    {"value": "Asia/Seoul", "label": "🇰🇷 Asia/Seoul (KST - UTC+9)", "region": "East & Southeast Asia", "offset": "UTC+9", "country": "South Korea"},

    # --- Central & West Asia ---
    {"value": "Asia/Baku", "label": "🇦🇿 Asia/Baku (AZT - UTC+4)", "region": "Central & West Asia", "offset": "UTC+4", "country": "Azerbaijan"},
    {"value": "Asia/Tashkent", "label": "🇺🇿 Asia/Tashkent (UZT - UTC+5)", "region": "Central & West Asia", "offset": "UTC+5", "country": "Uzbekistan"},
    {"value": "Asia/Almaty", "label": "🇰🇿 Asia/Almaty (ALMT - UTC+5)", "region": "Central & West Asia", "offset": "UTC+5", "country": "Kazakhstan"},
    {"value": "Europe/Istanbul", "label": "🇹🇷 Europe/Istanbul (TRT - UTC+3)", "region": "Central & West Asia", "offset": "UTC+3", "country": "Turkey"},
    {"value": "Asia/Jerusalem", "label": "🇮🇱 Asia/Jerusalem (IST/IDT - UTC+2/+3)", "region": "Central & West Asia", "offset": "UTC+2", "country": "Israel"},
    {"value": "Asia/Beirut", "label": "🇱🇧 Asia/Beirut (EET/EEST - UTC+2/+3)", "region": "Central & West Asia", "offset": "UTC+2", "country": "Lebanon"},

    # --- Europe & United Kingdom ---
    {"value": "Europe/London", "label": "🇬🇧 Europe/London (GMT/BST - UTC+0/+1)", "region": "Europe & UK", "offset": "UTC+0", "country": "United Kingdom"},
    {"value": "Europe/Dublin", "label": "🇮🇪 Europe/Dublin (IST/GMT - UTC+0/+1)", "region": "Europe & UK", "offset": "UTC+0", "country": "Ireland"},
    {"value": "Europe/Paris", "label": "🇫🇷 Europe/Paris (CET/CEST - UTC+1/+2)", "region": "Europe & UK", "offset": "UTC+1", "country": "France"},
    {"value": "Europe/Berlin", "label": "🇩🇪 Europe/Berlin (CET/CEST - UTC+1/+2)", "region": "Europe & UK", "offset": "UTC+1", "country": "Germany"},
    {"value": "Europe/Rome", "label": "🇮🇹 Europe/Rome (CET/CEST - UTC+1/+2)", "region": "Europe & UK", "offset": "UTC+1", "country": "Italy"},
    {"value": "Europe/Madrid", "label": "🇪🇸 Europe/Madrid (CET/CEST - UTC+1/+2)", "region": "Europe & UK", "offset": "UTC+1", "country": "Spain"},
    {"value": "Europe/Amsterdam", "label": "🇳🇱 Europe/Amsterdam (CET/CEST - UTC+1/+2)", "region": "Europe & UK", "offset": "UTC+1", "country": "Netherlands"},
    {"value": "Europe/Brussels", "label": "🇧🇪 Europe/Brussels (CET/CEST - UTC+1/+2)", "region": "Europe & UK", "offset": "UTC+1", "country": "Belgium"},
    {"value": "Europe/Zurich", "label": "🇨🇭 Europe/Zurich (CET/CEST - UTC+1/+2)", "region": "Europe & UK", "offset": "UTC+1", "country": "Switzerland"},
    {"value": "Europe/Vienna", "label": "🇦🇹 Europe/Vienna (CET/CEST - UTC+1/+2)", "region": "Europe & UK", "offset": "UTC+1", "country": "Austria"},
    {"value": "Europe/Stockholm", "label": "🇸🇪 Europe/Stockholm (CET/CEST - UTC+1/+2)", "region": "Europe & UK", "offset": "UTC+1", "country": "Sweden"},
    {"value": "Europe/Oslo", "label": "🇳🇴 Europe/Oslo (CET/CEST - UTC+1/+2)", "region": "Europe & UK", "offset": "UTC+1", "country": "Norway"},
    {"value": "Europe/Copenhagen", "label": "🇩🇰 Europe/Copenhagen (CET/CEST - UTC+1/+2)", "region": "Europe & UK", "offset": "UTC+1", "country": "Denmark"},
    {"value": "Europe/Helsinki", "label": "🇫🇮 Europe/Helsinki (EET/EEST - UTC+2/+3)", "region": "Europe & UK", "offset": "UTC+2", "country": "Finland"},
    {"value": "Europe/Warsaw", "label": "🇵🇱 Europe/Warsaw (CET/CEST - UTC+1/+2)", "region": "Europe & UK", "offset": "UTC+1", "country": "Poland"},
    {"value": "Europe/Athens", "label": "🇬🇷 Europe/Athens (EET/EEST - UTC+2/+3)", "region": "Europe & UK", "offset": "UTC+2", "country": "Greece"},
    {"value": "Europe/Lisbon", "label": "🇵🇹 Europe/Lisbon (WET/WEST - UTC+0/+1)", "region": "Europe & UK", "offset": "UTC+0", "country": "Portugal"},
    {"value": "Europe/Moscow", "label": "🇷🇺 Europe/Moscow (MSK - UTC+3)", "region": "Europe & UK", "offset": "UTC+3", "country": "Russia"},

    # --- Americas (North, Central & South) ---
    {"value": "America/New_York", "label": "🇺🇸 America/New_York (EST/EDT - UTC-5/-4)", "region": "Americas", "offset": "UTC-5", "country": "United States"},
    {"value": "America/Chicago", "label": "🇺🇸 America/Chicago (CST/CDT - UTC-6/-5)", "region": "Americas", "offset": "UTC-6", "country": "United States"},
    {"value": "America/Denver", "label": "🇺🇸 America/Denver (MST/MDT - UTC-7/-6)", "region": "Americas", "offset": "UTC-7", "country": "United States"},
    {"value": "America/Phoenix", "label": "🇺🇸 America/Phoenix (MST - UTC-7)", "region": "Americas", "offset": "UTC-7", "country": "United States"},
    {"value": "America/Los_Angeles", "label": "🇺🇸 America/Los_Angeles (PST/PDT - UTC-8/-7)", "region": "Americas", "offset": "UTC-8", "country": "United States"},
    {"value": "America/Anchorage", "label": "🇺🇸 America/Anchorage (AKST/AKDT - UTC-9/-8)", "region": "Americas", "offset": "UTC-9", "country": "United States"},
    {"value": "Pacific/Honolulu", "label": "🇺🇸 Pacific/Honolulu (HST - UTC-10)", "region": "Americas", "offset": "UTC-10", "country": "United States"},
    {"value": "America/Toronto", "label": "🇨🇦 America/Toronto (EST/EDT - UTC-5/-4)", "region": "Americas", "offset": "UTC-5", "country": "Canada"},
    {"value": "America/Vancouver", "label": "🇨🇦 America/Vancouver (PST/PDT - UTC-8/-7)", "region": "Americas", "offset": "UTC-8", "country": "Canada"},
    {"value": "America/Edmonton", "label": "🇨🇦 America/Edmonton (MST/MDT - UTC-7/-6)", "region": "Americas", "offset": "UTC-7", "country": "Canada"},
    {"value": "America/Halifax", "label": "🇨🇦 America/Halifax (AST/ADT - UTC-4/-3)", "region": "Americas", "offset": "UTC-4", "country": "Canada"},
    {"value": "America/Mexico_City", "label": "🇲🇽 America/Mexico_City (CST - UTC-6)", "region": "Americas", "offset": "UTC-6", "country": "Mexico"},
    {"value": "America/Bogota", "label": "🇨🇴 America/Bogota (COT - UTC-5)", "region": "Americas", "offset": "UTC-5", "country": "Colombia"},
    {"value": "America/Lima", "label": "🇵🇪 America/Lima (PET - UTC-5)", "region": "Americas", "offset": "UTC-5", "country": "Peru"},
    {"value": "America/Sao_Paulo", "label": "🇧🇷 America/Sao_Paulo (BRT - UTC-3)", "region": "Americas", "offset": "UTC-3", "country": "Brazil"},
    {"value": "America/Buenos_Aires", "label": "🇦🇷 America/Buenos_Aires (ART - UTC-3)", "region": "Americas", "offset": "UTC-3", "country": "Argentina"},
    {"value": "America/Santiago", "label": "🇨🇱 America/Santiago (CLT/CLST - UTC-4/-3)", "region": "Americas", "offset": "UTC-4", "country": "Chile"},

    # --- Africa ---
    {"value": "Africa/Cairo", "label": "🇪🇬 Africa/Cairo (EET/EEST - UTC+2/+3)", "region": "Africa", "offset": "UTC+2", "country": "Egypt"},
    {"value": "Africa/Johannesburg", "label": "🇿🇦 Africa/Johannesburg (SAST - UTC+2)", "region": "Africa", "offset": "UTC+2", "country": "South Africa"},
    {"value": "Africa/Lagos", "label": "🇳🇬 Africa/Lagos (WAT - UTC+1)", "region": "Africa", "offset": "UTC+1", "country": "Nigeria"},
    {"value": "Africa/Nairobi", "label": "🇰🇪 Africa/Nairobi (EAT - UTC+3)", "region": "Africa", "offset": "UTC+3", "country": "Kenya"},
    {"value": "Africa/Casablanca", "label": "🇲🇦 Africa/Casablanca (WET/WEST - UTC+1)", "region": "Africa", "offset": "UTC+1", "country": "Morocco"},
    {"value": "Africa/Accra", "label": "🇬🇭 Africa/Accra (GMT - UTC+0)", "region": "Africa", "offset": "UTC+0", "country": "Ghana"},
    {"value": "Africa/Addis_Ababa", "label": "🇪🇹 Africa/Addis_Ababa (EAT - UTC+3)", "region": "Africa", "offset": "UTC+3", "country": "Ethiopia"},

    # --- Australia, New Zealand & Pacific ---
    {"value": "Australia/Sydney", "label": "🇦🇺 Australia/Sydney (AEST/AEDT - UTC+10/+11)", "region": "Australia & Pacific", "offset": "UTC+10", "country": "Australia"},
    {"value": "Australia/Melbourne", "label": "🇦🇺 Australia/Melbourne (AEST/AEDT - UTC+10/+11)", "region": "Australia & Pacific", "offset": "UTC+10", "country": "Australia"},
    {"value": "Australia/Brisbane", "label": "🇦🇺 Australia/Brisbane (AEST - UTC+10)", "region": "Australia & Pacific", "offset": "UTC+10", "country": "Australia"},
    {"value": "Australia/Adelaide", "label": "🇦🇺 Australia/Adelaide (ACST/ACDT - UTC+9:30/+10:30)", "region": "Australia & Pacific", "offset": "UTC+9:30", "country": "Australia"},
    {"value": "Australia/Perth", "label": "🇦🇺 Australia/Perth (AWST - UTC+8)", "region": "Australia & Pacific", "offset": "UTC+8", "country": "Australia"},
    {"value": "Pacific/Auckland", "label": "🇳🇿 Pacific/Auckland (NZST/NZDT - UTC+12/+13)", "region": "Australia & Pacific", "offset": "UTC+12", "country": "New Zealand"},
    {"value": "Pacific/Fiji", "label": "🇫🇯 Pacific/Fiji (FJT - UTC+12)", "region": "Australia & Pacific", "offset": "UTC+12", "country": "Fiji"},

    # --- UTC & Global ---
    {"value": "UTC", "label": "🌐 UTC (Coordinated Universal Time - UTC+0)", "region": "UTC / Universal", "offset": "UTC+0", "country": "Global"},
]


def get_supported_timezones(
    query: str | None = None,
    region: str | None = None,
) -> list[dict[str, Any]]:
    """Return list of supported global timezones for scheduled jobs, with optional search & region filtering."""
    results = GLOBAL_TIMEZONES
    if region:
        reg_lower = region.strip().lower()
        results = [t for t in results if reg_lower in t.get("region", "").lower()]
    if query:
        q = query.strip().lower()
        results = [
            t for t in results
            if q in t["value"].lower()
            or q in t["label"].lower()
            or q in t.get("country", "").lower()
            or q in t.get("region", "").lower()
            or q in t.get("offset", "").lower()
        ]
    return results


def get_timezone_regions() -> list[dict[str, Any]]:
    """Return list of unique regions and count of timezones in each."""
    region_counts: dict[str, int] = {}
    for tz in GLOBAL_TIMEZONES:
        reg = tz.get("region", "Other")
        region_counts[reg] = region_counts.get(reg, 0) + 1
    return [{"name": reg, "count": count} for reg, count in region_counts.items()]


def validate_timezone(tz: str | None) -> dict[str, Any]:
    """Validate and resolve a user-supplied timezone string or alias."""
    import zoneinfo
    if not tz or not tz.strip():
        return {
            "input": tz,
            "normalized": "UTC",
            "valid": True,
            "is_alias": False,
            "metadata": next((t for t in GLOBAL_TIMEZONES if t["value"] == "UTC"), None),
        }
    raw = tz.strip()
    normalized = normalize_timezone(raw)
    is_valid = False
    try:
        zoneinfo.ZoneInfo(normalized)
        is_valid = True
    except Exception:
        try:
            zoneinfo.ZoneInfo(raw)
            normalized = raw
            is_valid = True
        except Exception:
            is_valid = False

    meta = next((t for t in GLOBAL_TIMEZONES if t["value"].lower() == normalized.lower()), None)
    return {
        "input": tz,
        "normalized": normalized,
        "valid": is_valid,
        "is_alias": normalized.lower() != raw.lower(),
        "metadata": meta,
    }


def normalize_timezone(tz: str | None) -> str:
    """Safely normalizes user-provided timezone strings to standard IANA identifiers."""
    if not tz or not tz.strip():
        return "UTC"
    raw = tz.strip()
    lower = raw.lower()
    mapping = {
        # Pakistan
        "karachi": "Asia/Karachi",
        "islamabad": "Asia/Karachi",
        "lahore": "Asia/Karachi",
        "rawalpindi": "Asia/Karachi",
        "faisalabad": "Asia/Karachi",
        "peshawar": "Asia/Karachi",
        "quetta": "Asia/Karachi",
        "multan": "Asia/Karachi",
        "pakistan": "Asia/Karachi",
        "pkt": "Asia/Karachi",
        "gmt+5": "Asia/Karachi",
        "utc+5": "Asia/Karachi",

        # India
        "india": "Asia/Kolkata",
        "delhi": "Asia/Kolkata",
        "new delhi": "Asia/Kolkata",
        "mumbai": "Asia/Kolkata",
        "kolkata": "Asia/Kolkata",
        "calcutta": "Asia/Kolkata",
        "bangalore": "Asia/Kolkata",
        "bengaluru": "Asia/Kolkata",
        "chennai": "Asia/Kolkata",
        "hyderabad": "Asia/Kolkata",
        "ist": "Asia/Kolkata",
        "gmt+5:30": "Asia/Kolkata",
        "utc+5:30": "Asia/Kolkata",

        # Bangladesh, Sri Lanka, Nepal
        "dhaka": "Asia/Dhaka",
        "bangladesh": "Asia/Dhaka",
        "bdst": "Asia/Dhaka",
        "colombo": "Asia/Colombo",
        "sri lanka": "Asia/Colombo",
        "kathmandu": "Asia/Kathmandu",
        "nepal": "Asia/Kathmandu",

        # Gulf & Middle East
        "dubai": "Asia/Dubai",
        "abu dhabi": "Asia/Dubai",
        "uae": "Asia/Dubai",
        "gst": "Asia/Dubai",
        "riyadh": "Asia/Riyadh",
        "jeddah": "Asia/Riyadh",
        "saudi": "Asia/Riyadh",
        "saudi arabia": "Asia/Riyadh",
        "ast": "Asia/Riyadh",
        "doha": "Asia/Qatar",
        "qatar": "Asia/Qatar",
        "kuwait": "Asia/Kuwait",
        "muscat": "Asia/Muscat",
        "oman": "Asia/Muscat",
        "bahrain": "Asia/Bahrain",
        "manama": "Asia/Bahrain",
        "baku": "Asia/Baku",
        "tashkent": "Asia/Tashkent",
        "almaty": "Asia/Almaty",
        "istanbul": "Europe/Istanbul",
        "turkey": "Europe/Istanbul",
        "ankara": "Europe/Istanbul",
        "jerusalem": "Asia/Jerusalem",
        "tel aviv": "Asia/Jerusalem",
        "israel": "Asia/Jerusalem",
        "beirut": "Asia/Beirut",
        "lebanon": "Asia/Beirut",

        # East & Southeast Asia
        "singapore": "Asia/Singapore",
        "sgt": "Asia/Singapore",
        "kuala lumpur": "Asia/Kuala_Lumpur",
        "malaysia": "Asia/Kuala_Lumpur",
        "myt": "Asia/Kuala_Lumpur",
        "bangkok": "Asia/Bangkok",
        "thailand": "Asia/Bangkok",
        "jakarta": "Asia/Jakarta",
        "indonesia": "Asia/Jakarta",
        "manila": "Asia/Manila",
        "philippines": "Asia/Manila",
        "vietnam": "Asia/Ho_Chi_Minh",
        "ho chi minh": "Asia/Ho_Chi_Minh",
        "hanoi": "Asia/Ho_Chi_Minh",
        "tokyo": "Asia/Tokyo",
        "japan": "Asia/Tokyo",
        "jst": "Asia/Tokyo",
        "seoul": "Asia/Seoul",
        "korea": "Asia/Seoul",
        "south korea": "Asia/Seoul",
        "kst": "Asia/Seoul",
        "shanghai": "Asia/Shanghai",
        "beijing": "Asia/Shanghai",
        "china": "Asia/Shanghai",
        "hong kong": "Asia/Hong_Kong",
        "taipei": "Asia/Taipei",
        "taiwan": "Asia/Taipei",

        # Europe & UK
        "london": "Europe/London",
        "uk": "Europe/London",
        "united kingdom": "Europe/London",
        "britain": "Europe/London",
        "gmt": "Europe/London",
        "bst": "Europe/London",
        "dublin": "Europe/Dublin",
        "ireland": "Europe/Dublin",
        "paris": "Europe/Paris",
        "france": "Europe/Paris",
        "berlin": "Europe/Berlin",
        "germany": "Europe/Berlin",
        "frankfurt": "Europe/Berlin",
        "munich": "Europe/Berlin",
        "rome": "Europe/Rome",
        "italy": "Europe/Rome",
        "milan": "Europe/Rome",
        "madrid": "Europe/Madrid",
        "spain": "Europe/Madrid",
        "barcelona": "Europe/Madrid",
        "amsterdam": "Europe/Amsterdam",
        "netherlands": "Europe/Amsterdam",
        "brussels": "Europe/Brussels",
        "belgium": "Europe/Brussels",
        "zurich": "Europe/Zurich",
        "switzerland": "Europe/Zurich",
        "geneva": "Europe/Zurich",
        "vienna": "Europe/Vienna",
        "austria": "Europe/Vienna",
        "stockholm": "Europe/Stockholm",
        "sweden": "Europe/Stockholm",
        "oslo": "Europe/Oslo",
        "norway": "Europe/Oslo",
        "copenhagen": "Europe/Copenhagen",
        "denmark": "Europe/Copenhagen",
        "helsinki": "Europe/Helsinki",
        "finland": "Europe/Helsinki",
        "warsaw": "Europe/Warsaw",
        "poland": "Europe/Warsaw",
        "athens": "Europe/Athens",
        "greece": "Europe/Athens",
        "lisbon": "Europe/Lisbon",
        "portugal": "Europe/Lisbon",
        "moscow": "Europe/Moscow",
        "russia": "Europe/Moscow",
        "cet": "Europe/Paris",
        "cest": "Europe/Paris",

        # Americas
        "new york": "America/New_York",
        "new_york": "America/New_York",
        "nyc": "America/New_York",
        "eastern": "America/New_York",
        "est": "America/New_York",
        "edt": "America/New_York",
        "chicago": "America/Chicago",
        "central": "America/Chicago",
        "cst": "America/Chicago",
        "cdt": "America/Chicago",
        "dallas": "America/Chicago",
        "houston": "America/Chicago",
        "denver": "America/Denver",
        "mountain": "America/Denver",
        "mst": "America/Denver",
        "mdt": "America/Denver",
        "phoenix": "America/Phoenix",
        "arizona": "America/Phoenix",
        "los angeles": "America/Los_Angeles",
        "pacific": "America/Los_Angeles",
        "pst": "America/Los_Angeles",
        "pdt": "America/Los_Angeles",
        "san francisco": "America/Los_Angeles",
        "seattle": "America/Los_Angeles",
        "anchorage": "America/Anchorage",
        "alaska": "America/Anchorage",
        "honolulu": "Pacific/Honolulu",
        "hawaii": "Pacific/Honolulu",
        "toronto": "America/Toronto",
        "canada": "America/Toronto",
        "montreal": "America/Toronto",
        "vancouver": "America/Vancouver",
        "edmonton": "America/Edmonton",
        "calgary": "America/Edmonton",
        "halifax": "America/Halifax",
        "mexico city": "America/Mexico_City",
        "mexico": "America/Mexico_City",
        "bogota": "America/Bogota",
        "colombia": "America/Bogota",
        "lima": "America/Lima",
        "peru": "America/Lima",
        "sao paulo": "America/Sao_Paulo",
        "brazil": "America/Sao_Paulo",
        "buenos aires": "America/Buenos_Aires",
        "argentina": "America/Buenos_Aires",
        "santiago": "America/Santiago",
        "chile": "America/Santiago",

        # Africa
        "cairo": "Africa/Cairo",
        "egypt": "Africa/Cairo",
        "johannesburg": "Africa/Johannesburg",
        "south africa": "Africa/Johannesburg",
        "cape town": "Africa/Johannesburg",
        "lagos": "Africa/Lagos",
        "nigeria": "Africa/Lagos",
        "nairobi": "Africa/Nairobi",
        "kenya": "Africa/Nairobi",
        "casablanca": "Africa/Casablanca",
        "morocco": "Africa/Casablanca",
        "accra": "Africa/Accra",
        "ghana": "Africa/Accra",
        "addis ababa": "Africa/Addis_Ababa",
        "ethiopia": "Africa/Addis_Ababa",

        # Australia & Pacific
        "sydney": "Australia/Sydney",
        "australia": "Australia/Sydney",
        "aest": "Australia/Sydney",
        "aedt": "Australia/Sydney",
        "melbourne": "Australia/Melbourne",
        "brisbane": "Australia/Brisbane",
        "adelaide": "Australia/Adelaide",
        "perth": "Australia/Perth",
        "auckland": "Pacific/Auckland",
        "new zealand": "Pacific/Auckland",
        "wellington": "Pacific/Auckland",
        "fiji": "Pacific/Fiji",

        # UTC
        "utc": "UTC",
    }
    if lower in mapping:
        return mapping[lower]
    try:
        import zoneinfo
        zoneinfo.ZoneInfo(raw)
        return raw
    except Exception:
        for candidate in (raw.title(), f"America/{raw.title()}", f"Europe/{raw.title()}", f"Asia/{raw.title()}", f"Africa/{raw.title()}", f"Australia/{raw.title()}"):
            try:
                import zoneinfo
                zoneinfo.ZoneInfo(candidate)
                return candidate
            except Exception:
                pass
        return "UTC"


class JobStore:
    """In-memory + JSON-persisted job store, partitioned by user_id."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, dict[str, Any]]] = {}  # user_id -> job_id -> job dict
        self._path = self._resolve_path()

    def _resolve_path(self) -> Path:
        import os
        raw = os.environ.get("JOB_STORE_PATH", "").strip()
        if raw:
            p = Path(raw)
        elif os.environ.get("VERCEL"):
            p = Path("/tmp") / "job_store.json"
        else:
            p = Path(__file__).resolve().parents[3] / "data" / "job_store.json"
        import contextlib
        with contextlib.suppress(Exception):
            p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                raw = json.load(f)
            for user_id, jobs in raw.items():
                self._jobs[user_id] = {}
                for job_id, job in jobs.items():
                    self._jobs[user_id][job_id] = job
        except Exception:
            pass

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._jobs, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            log.warning("job_store.save_failed", error=str(exc))

    def _ensure_user(self, user_id: str) -> None:
        if user_id not in self._jobs:
            self._jobs[user_id] = {}

    def _job_to_entry(self, job_id: str, job: dict[str, Any]) -> JobEntry:
        return JobEntry(
            job_id=job_id,
            name=job["name"],
            schedule=job["schedule"],
            timezone=job["timezone"],
            action=JobAction(**job["action"]),
            confirm_on_fire=job.get("confirm_on_fire", False),
            status=job.get("status", "active"),
            created_at=datetime.fromisoformat(job["created_at"]),
            next_fire_at=datetime.fromisoformat(job["next_fire_at"]) if job.get("next_fire_at") else None,
            tag=job.get("tag"),
        )

    def create(self, user_id: str, name: str, schedule: str, timezone: str, action: JobAction, confirm_on_fire: bool, tag: str | None = None) -> tuple[str, str | None]:
        """Create a job. Returns (job_id, error)."""
        self._load()
        self._ensure_user(user_id)

        norm_tz = normalize_timezone(timezone)
        # Validate cron / natural language / timestamp with normalized timezone
        parsed, resolved_schedule = self._parse_schedule(schedule, norm_tz)
        if parsed is None:
            return "", f"Invalid schedule: '{schedule}'. Try natural language like 'Every day at 9am' or a cron expression (e.g. '0 8 * * 1-5')."
        next_fire = parsed

        # Validate agent
        if action.agent_slug not in VALID_AGENTS:
            return "", f"Unknown agent: '{action.agent_slug}'. Valid agents: {', '.join(sorted(VALID_AGENTS))}."
        if action.skill_slug and action.skill_slug not in VALID_SKILLS:
            return "", f"Unknown skill: '{action.skill_slug}'. Valid skills: {', '.join(sorted(VALID_SKILLS))}."

        # Sensitive guardrail
        sensitive_skills = {"email_draft", "browser_fill_form", "bank_connect"}
        if action.skill_slug in sensitive_skills and not confirm_on_fire:
            return "", f"Job action uses a sensitive skill ('{action.skill_slug}'). Set confirm_on_fire: true to allow."

        job_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        job = {
            "name": name,
            "schedule": resolved_schedule,
            "timezone": norm_tz,
            "action": action.model_dump(),
            "confirm_on_fire": confirm_on_fire,
            "status": "active",
            "created_at": now.isoformat(),
            "next_fire_at": next_fire.isoformat() if next_fire else None,
            "tag": tag,
        }
        self._jobs[user_id][job_id] = job
        self._save()
        return job_id, None

    def list(self, user_id: str, tag: str | None = None) -> list[JobEntry]:
        self._load()
        self._ensure_user(user_id)
        entries = []
        for job_id, job in self._jobs[user_id].items():
            if tag and job.get("tag") != tag:
                continue
            entries.append(self._job_to_entry(job_id, job))
        return sorted(entries, key=lambda e: e.created_at, reverse=True)

    def cancel(self, user_id: str, job_id: str) -> tuple[bool, str | None]:
        self._load()
        if job_id in self._jobs.get(user_id, {}):
            del self._jobs[user_id][job_id]
            self._save()
            return True, None
        # Cross-partition fallback: locate in any user partition
        for uid, user_jobs in self._jobs.items():
            if job_id in user_jobs:
                del self._jobs[uid][job_id]
                self._save()
                return True, None
        return False, f"Job not found: {job_id}"

    def pause(self, user_id: str, job_id: str) -> tuple[bool, str | None]:
        self._load()
        job = self._jobs.get(user_id, {}).get(job_id)
        if job is None:
            # Cross-partition search
            for _uid, user_jobs in self._jobs.items():
                if job_id in user_jobs:
                    job = user_jobs[job_id]
                    break
        if job is None:
            return False, f"Job not found: {job_id}"
        job["status"] = "paused"
        self._save()
        return True, None

    def resume(self, user_id: str, job_id: str) -> tuple[bool, str | None]:
        self._load()
        job = self._jobs.get(user_id, {}).get(job_id)
        if job is None:
            # Cross-partition search
            for _uid, user_jobs in self._jobs.items():
                if job_id in user_jobs:
                    job = user_jobs[job_id]
                    break
        if job is None:
            return False, f"Job not found: {job_id}"
        job["status"] = "active"
        self._save()
        return True, None

    def update(self, user_id: str, job_id: str, name: str | None, schedule: str | None, timezone: str | None, action: JobAction | None, confirm_on_fire: bool | None, tag: str | None) -> tuple[bool, str | None]:
        self._load()
        job = self._jobs.get(user_id, {}).get(job_id)
        if job is None:
            return False, f"Job not found: {job_id}"
        if name is not None:
            job["name"] = name
        if schedule is not None:
            parsed, resolved_schedule = self._parse_schedule(schedule)
            if parsed is None:
                return False, f"Invalid schedule: '{schedule}'. Try e.g. 'Every day at 9am' or '0 8 * * 1-5'."
            job["schedule"] = resolved_schedule
            job["next_fire_at"] = parsed.isoformat()
        if timezone is not None:
            job["timezone"] = timezone
        if action is not None:
            if action.agent_slug not in VALID_AGENTS:
                return False, f"Unknown agent: '{action.agent_slug}'"
            if action.skill_slug and action.skill_slug not in VALID_SKILLS:
                return False, f"Unknown skill: '{action.skill_slug}'"
            job["action"] = action.model_dump()
        if confirm_on_fire is not None:
            job["confirm_on_fire"] = confirm_on_fire
        if tag is not None:
            job["tag"] = tag
        self._save()
        return True, None

    @staticmethod
    def _natural_to_cron(text: str) -> str | None:
        """Translates human-readable natural expressions into a 5-segment cron string."""
        t = text.strip().lower()
        # "every N minutes"
        m_min = re.match(r"^every\s+(\d+)\s*(?:min|minute)s?$", t)
        if m_min:
            mins = int(m_min.group(1))
            if 1 <= mins <= 59:
                return f"*/{mins} * * * *"
        if t == "every minute":
            return "* * * * *"
        if t in ("every hour", "hourly"):
            return "0 * * * *"
        m_hr = re.match(r"^every\s+(\d+)\s*(?:hour|hr)s?$", t)
        if m_hr:
            hrs = int(m_hr.group(1))
            if 1 <= hrs <= 23:
                return f"0 */{hrs} * * *"

        # Time extraction: e.g. "at 9am", "at 9:30 pm", "at 14:00"
        tm = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
        hour = 9
        minute = 0
        if tm:
            h = int(tm.group(1))
            mn = int(tm.group(2)) if tm.group(2) else 0
            mer = (tm.group(3) or "").lower()
            if mer == "pm" and h < 12:
                h += 12
            elif mer == "am" and h == 12:
                h = 0
            hour, minute = h, mn

        if any(k in t for k in ("weekday", "monday to friday", "mon-fri")):
            return f"{minute} {hour} * * 1-5"
        if "weekend" in t:
            return f"{minute} {hour} * * 0,6"

        days = {
            "sunday": 0, "sun": 0, "monday": 1, "mon": 1, "tuesday": 2, "tue": 2,
            "wednesday": 3, "wed": 3, "thursday": 4, "thu": 4, "friday": 5, "fri": 5,
            "saturday": 6, "sat": 6,
        }
        for day, num in days.items():
            if day in t:
                return f"{minute} {hour} * * {num}"

        if any(k in t for k in ("every day", "daily", "at ", "morning", "night", "evening")):
            return f"{minute} {hour} * * *"
        if any(k in t for k in ("monthly", "every month")):
            return f"{minute} {hour} 1 * *"

        return None

    @classmethod
    def _parse_schedule(cls, schedule: str, timezone_str: str = "UTC") -> tuple[datetime | None, str]:
        """Parse natural language, cron, or ISO-8601. Returns (next_fire, resolved_schedule)."""
        schedule = schedule.strip()
        import zoneinfo
        from datetime import timedelta

        tz: Any
        try:
            tz = zoneinfo.ZoneInfo(timezone_str)
        except Exception:
            tz = UTC

        # ISO-8601 datetime
        if re.match(r"^\d{4}-\d{2}-\d{2}", schedule):
            try:
                dt = datetime.fromisoformat(schedule.replace("Z", "+00:00"))
                return (dt.astimezone(UTC) if dt.tzinfo is None else dt, schedule)
            except Exception:
                return (None, schedule)

        # Standard 5-field Cron
        cron_pattern = re.compile(
            r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+(\S+))?$"
        )
        if cron_pattern.match(schedule):
            now_tz = datetime.now(tz)
            return ((now_tz + timedelta(days=1)).astimezone(UTC), schedule)

        # Natural Language Cron resolution
        resolved = cls._natural_to_cron(schedule)
        if resolved:
            now_tz = datetime.now(tz)
            return ((now_tz + timedelta(days=1)).astimezone(UTC), resolved)

        return (None, schedule)


_job_store: JobStore | None = None


def get_job_store() -> JobStore:
    global _job_store
    if _job_store is None:
        _job_store = JobStore()
    return _job_store


class ScheduleJobSkill(SkillExecutor[ScheduleJobRequest, ScheduleJobResponse]):
    slug = "schedule_job"

    async def execute(self, input_data: ScheduleJobRequest) -> ScheduleJobResponse:
        user_id = input_data.user_id or "anonymous"
        store = get_job_store()
        op = input_data.op
        session_factory = get_session_factory()

        if op == ScheduleJobOp.CREATE:
            if not input_data.name or not input_data.schedule or not input_data.timezone or not input_data.action:
                return ScheduleJobResponse(
                    op="create", success=False, error="name, schedule, timezone, and action are required for create"
                )
            job_id, err = store.create(
                user_id=user_id,
                name=input_data.name,
                schedule=input_data.schedule,
                timezone=input_data.timezone,
                action=input_data.action,
                confirm_on_fire=input_data.confirm_on_fire,
                tag=input_data.tag,
            )
            if err:
                return ScheduleJobResponse(op="create", success=False, error=err)

            job_record = store._jobs.get(user_id, {}).get(job_id)
            effective_schedule = str(job_record.get("schedule")) if job_record and job_record.get("schedule") else str(input_data.schedule)
            effective_tz = str(job_record.get("timezone")) if job_record and job_record.get("timezone") else input_data.timezone

            # Persist to PostgreSQL if database is configured
            if session_factory:
                try:
                    async with session_factory() as session:
                        now = datetime.now(UTC)
                        next_fire = (
                            datetime.fromisoformat(job_record["next_fire_at"])
                            if job_record and job_record.get("next_fire_at")
                            else None
                        )
                        new_db_job = ScheduledJob(
                            id=job_id,
                            user_id=user_id,
                            name=input_data.name,
                            schedule=effective_schedule,
                            timezone=effective_tz,
                            action=input_data.action.model_dump(),
                            confirm_on_fire=input_data.confirm_on_fire or False,
                            status="active",
                            created_at=now,
                            next_fire_at=next_fire,
                            tag=input_data.tag,
                        )
                        session.add(new_db_job)
                        await session.commit()
                except Exception as exc:
                    log.warning("schedule_job.db_create_failed", error=str(exc))

            _reschedule_if_running(
                job_id=job_id,
                user_id=user_id,
                schedule=effective_schedule,
                timezone=effective_tz,
                action=input_data.action,
                confirm_on_fire=input_data.confirm_on_fire or False,
            )
            return ScheduleJobResponse(op="create", success=True, job_id=job_id)

        elif op == ScheduleJobOp.LIST:
            # Query from PostgreSQL if available
            if session_factory:
                try:
                    async with session_factory() as session:
                        stmt = select(ScheduledJob).where(ScheduledJob.user_id == user_id)
                        if input_data.tag:
                            stmt = stmt.where(ScheduledJob.tag == input_data.tag)
                        stmt = stmt.order_by(ScheduledJob.created_at.desc())
                        res = await session.execute(stmt)
                        rows = res.scalars().all()
                        jobs = [
                            JobEntry(
                                job_id=r.id,
                                name=r.name,
                                schedule=r.schedule,
                                timezone=r.timezone,
                                action=JobAction(**r.action),
                                confirm_on_fire=r.confirm_on_fire,
                                status=r.status,
                                created_at=r.created_at,
                                next_fire_at=r.next_fire_at,
                                tag=r.tag,
                            )
                            for r in rows
                        ]
                        return ScheduleJobResponse(op="list", success=True, jobs=jobs)
                except Exception as exc:
                    log.warning("schedule_job.db_list_failed", error=str(exc))

            jobs = store.list(user_id=user_id, tag=input_data.tag)
            return ScheduleJobResponse(op="list", success=True, jobs=jobs)

        elif op == ScheduleJobOp.CANCEL:
            if not input_data.job_id:
                return ScheduleJobResponse(op="cancel", success=False, error="job_id is required")

            db_deleted = False
            if session_factory:
                try:
                    async with session_factory() as session:
                        del_stmt = delete(ScheduledJob).where(ScheduledJob.id == input_data.job_id)
                        del_res: Any = await session.execute(del_stmt)
                        await session.commit()
                        rowcount = getattr(del_res, "rowcount", 0) or 0
                        if rowcount > 0:
                            db_deleted = True
                except Exception as exc:
                    log.warning("schedule_job.db_cancel_failed", error=str(exc))

            ok, err = store.cancel(user_id=user_id, job_id=input_data.job_id)
            if ok or db_deleted:
                _cancel_if_running(input_data.job_id)
                return ScheduleJobResponse(op="cancel", success=True, job_id=input_data.job_id)
            return ScheduleJobResponse(op="cancel", success=False, error=err or "Job not found", job_id=input_data.job_id)

        elif op == ScheduleJobOp.PAUSE:
            if not input_data.job_id:
                return ScheduleJobResponse(op="pause", success=False, error="job_id is required")

            db_paused = False
            if session_factory:
                try:
                    async with session_factory() as session:
                        pause_stmt = (
                            update(ScheduledJob)
                            .where(ScheduledJob.id == input_data.job_id)
                            .values(status="paused")
                        )
                        pause_res: Any = await session.execute(pause_stmt)
                        await session.commit()
                        rowcount = getattr(pause_res, "rowcount", 0) or 0
                        if rowcount > 0:
                            db_paused = True
                except Exception as exc:
                    log.warning("schedule_job.db_pause_failed", error=str(exc))

            ok, err = store.pause(user_id=user_id, job_id=input_data.job_id)
            if ok or db_paused:
                _cancel_if_running(input_data.job_id)
                return ScheduleJobResponse(op="pause", success=True, job_id=input_data.job_id)
            return ScheduleJobResponse(op="pause", success=False, error=err or "Job not found", job_id=input_data.job_id)

        elif op == ScheduleJobOp.RESUME:
            if not input_data.job_id:
                return ScheduleJobResponse(op="resume", success=False, error="job_id is required")

            db_resumed = False
            db_job = None
            if session_factory:
                try:
                    async with session_factory() as session:
                        resume_stmt = (
                            update(ScheduledJob)
                            .where(ScheduledJob.id == input_data.job_id)
                            .values(status="active")
                        )
                        resume_res: Any = await session.execute(resume_stmt)
                        await session.commit()
                        rowcount = getattr(resume_res, "rowcount", 0) or 0
                        if rowcount > 0:
                            db_resumed = True
                            q_find = select(ScheduledJob).where(ScheduledJob.id == input_data.job_id)
                            res_job = await session.execute(q_find)
                            db_job = res_job.scalar_one_or_none()
                except Exception as exc:
                    log.warning("schedule_job.db_resume_failed", error=str(exc))

            ok, err = store.resume(user_id=user_id, job_id=input_data.job_id)
            if ok or db_resumed:
                job = None
                for _uid, user_jobs in store._jobs.items():
                    if input_data.job_id in user_jobs:
                        job = user_jobs[input_data.job_id]
                        break
                if job:
                    _reschedule_if_running(
                        job_id=input_data.job_id,
                        user_id=user_id,
                        schedule=str(job["schedule"]),
                        timezone=job.get("timezone"),
                        action=JobAction(**job["action"]),
                        confirm_on_fire=job.get("confirm_on_fire", False),
                    )
                elif db_job:
                    _reschedule_if_running(
                        job_id=db_job.id,
                        user_id=user_id,
                        schedule=str(db_job.schedule),
                        timezone=db_job.timezone,
                        action=JobAction(**db_job.action),
                        confirm_on_fire=db_job.confirm_on_fire,
                    )
                return ScheduleJobResponse(op="resume", success=True, job_id=input_data.job_id)
            return ScheduleJobResponse(op="resume", success=False, error=err or "Job not found", job_id=input_data.job_id)

        elif op == ScheduleJobOp.UPDATE:
            if not input_data.job_id:
                return ScheduleJobResponse(op="update", success=False, error="job_id is required")

            db_updated = False
            if session_factory:
                try:
                    async with session_factory() as session:
                        values_to_update: dict[str, Any] = {}
                        if input_data.name is not None:
                            values_to_update["name"] = input_data.name
                        if input_data.schedule is not None:
                            values_to_update["schedule"] = input_data.schedule
                        if input_data.timezone is not None:
                            values_to_update["timezone"] = normalize_timezone(input_data.timezone)
                        if input_data.action is not None:
                            values_to_update["action"] = input_data.action.model_dump()
                        if input_data.confirm_on_fire is not None:
                            values_to_update["confirm_on_fire"] = input_data.confirm_on_fire
                        if input_data.tag is not None:
                            values_to_update["tag"] = input_data.tag

                        if values_to_update:
                            upd_stmt = (
                                update(ScheduledJob)
                                .where(ScheduledJob.id == input_data.job_id)
                                .values(**values_to_update)
                            )
                            upd_res: Any = await session.execute(upd_stmt)
                            await session.commit()
                            rowcount = getattr(upd_res, "rowcount", 0) or 0
                            if rowcount > 0:
                                db_updated = True
                except Exception as exc:
                    log.warning("schedule_job.db_update_failed", error=str(exc))

            ok, err = store.update(
                user_id=user_id,
                job_id=input_data.job_id,
                name=input_data.name,
                schedule=input_data.schedule,
                timezone=input_data.timezone,
                action=input_data.action,
                confirm_on_fire=input_data.confirm_on_fire,
                tag=input_data.tag,
            )
            if ok or db_updated:
                if input_data.action and input_data.schedule:
                    _reschedule_if_running(
                        job_id=input_data.job_id,
                        user_id=user_id,
                        schedule=input_data.schedule or "",
                        timezone=input_data.timezone,
                        action=input_data.action,
                        confirm_on_fire=input_data.confirm_on_fire or False,
                    )
                return ScheduleJobResponse(op="update", success=True, job_id=input_data.job_id)
            return ScheduleJobResponse(op="update", success=False, error=err or "Job not found", job_id=input_data.job_id)
        elif op == ScheduleJobOp.TIMEZONES:
            return ScheduleJobResponse(
                op="timezones",
                success=True,
                timezones=get_supported_timezones(),
            )

        return ScheduleJobResponse(op=op.value, success=False, error=f"Unknown op: {op}")


def _cancel_if_running(job_id: str) -> None:
    """Remove a job from APScheduler if it is running."""
    try:
        from app.job_scheduler import cancel_scheduled_job
        cancel_scheduled_job(job_id)
    except Exception:
        pass  # Scheduler may not be running


def _reschedule_if_running(
    job_id: str,
    user_id: str,
    schedule: str,
    timezone: str | None,
    action: JobAction,
    confirm_on_fire: bool,
) -> None:
    """If APScheduler is running, update the scheduled firing."""
    try:
        from app.job_scheduler import cancel_scheduled_job, reschedule_job
        cancel_scheduled_job(job_id)
        reschedule_job(
            job_id=job_id,
            user_id=user_id,
            schedule=schedule,
            timezone=timezone,
            agent_slug=action.agent_slug,
            skill_slug=action.skill_slug,
            inputs=action.inputs,
            confirm_on_fire=confirm_on_fire,
        )
    except Exception:
        pass  # Scheduler may not be running (e.g., in test env)


def get_executor() -> ScheduleJobSkill:
    return ScheduleJobSkill()
