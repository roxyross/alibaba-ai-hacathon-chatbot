"""Natural Language Intent Parser and Conversational Grounding Engine for Device & Fleet Control.

Parses unstructured conversational chat prompts (e.g., "play Bohemian Rhapsody on my living room desktop",
"transfer this session to my laptop", "what devices are online?") into structured execution and handover
intents for FleetOrchestrator and UniversalAppController.
"""

from __future__ import annotations

from enum import StrEnum
import re
from typing import Any

from pydantic import BaseModel, Field
import structlog

log = structlog.get_logger()


class DeviceIntentType(StrEnum):
    """Categorized natural language device and fleet intent."""
    APP_CONTROL = "app_control"
    HANDOVER = "handover"
    FLEET_SUMMARY = "fleet_summary"
    FLEET_BROADCAST = "fleet_broadcast"
    CONFIRMATION = "confirmation"
    UNKNOWN = "unknown"


class ParsedDeviceIntent(BaseModel):
    """Structured representation of a parsed conversational device request."""
    intent_type: DeviceIntentType = DeviceIntentType.UNKNOWN
    application: str | None = None
    capability: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    target_device_hint: str | None = None
    source_device_hint: str | None = None
    confidence: float = 0.0
    raw_query: str = ""
    reason: str = ""


class DeviceIntentParser:
    """Parses natural language prompts into typed fleet and application control actions."""

    # -------------------------------------------------------------------------
    # Target Device Pattern Matchers
    # -------------------------------------------------------------------------
    _DEVICE_HINT_PATTERNS = [
        re.compile(r"\b(?:on|to|at)\s+(?:my\s+|the\s+)?((?:(?:living\s*room|bedroom|office|home|remote|local|cloud)\s+)?(?:desktop|laptop|workstation|pc|macbook|mac\s*mini|server|phone|tablet|rig))\b", re.I),
        re.compile(r"\b(?:device|machine|node)\s+([a-zA-Z0-9_\-]+)\b", re.I),
    ]

    # Handover specific target extraction
    _HANDOVER_TARGET_PATTERNS = [
        re.compile(r"\b(?:transfer|move|migrate|handover|switch|pass)\s+(?:this\s+)?(?:the\s+)?(?:my\s+)?(?:session|task|work|chat|app)?\s*(?:over\s*)?to\s+(?:my\s+|the\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+please|\.|$)", re.I),
        re.compile(r"\b(?:resume|continue)\s+(?:this|on)\s+(?:my\s+|the\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+please|\.|$)", re.I),
    ]

    # Handover source extraction
    _HANDOVER_SOURCE_PATTERNS = [
        re.compile(r"\bfrom\s+(?:my\s+|the\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+to|\s+over|\.|$)", re.I),
    ]

    # -------------------------------------------------------------------------
    # Fleet Summary & Status Query Patterns
    # -------------------------------------------------------------------------
    _FLEET_SUMMARY_PATTERNS = [
        re.compile(r"\b(what|which)\s+devices?\s+(are\s+)?(online|connected|enrolled|active|available|in\s+my\s+fleet)\b", re.I),
        re.compile(r"\b(show|list|get|check|display)\s+(my\s+)?(devices?|fleet|nodes?|machines?|rigs?)\b", re.I),
        re.compile(r"\bstatus\s+of\s+(my\s+)?(devices?|fleet)\b", re.I),
        re.compile(r"\bwhat\s+(hardware|computers|machines)\s+do\s+i\s+have\b", re.I),
        re.compile(r"\b(fleet|device)\s+summary\b", re.I),
    ]

    # -------------------------------------------------------------------------
    # Fleet Broadcast Query Patterns (e.g. "where is Spotify running?")
    # -------------------------------------------------------------------------
    _FLEET_BROADCAST_PATTERNS = [
        re.compile(r"\bwhere\s+is\s+([a-zA-Z0-9_\-\s]+?)\s+(running|installed|open)\b", re.I),
        re.compile(r"\bwhich\s+device\s+(has|is\s+running)\s+([a-zA-Z0-9_\-\s]+?)\b", re.I),
        re.compile(r"\bfind\s+(?:app|process)\s+([a-zA-Z0-9_\-\s]+?)\s+(?:across|in|on)\s+(?:my\s+)?(?:fleet|devices|machines)\b", re.I),
        re.compile(r"\bcheck\s+(cpu|memory|stats|system)\s+(?:across(?:\s+all)?|on\s+all)\s+(?:my\s+)?(?:devices|fleet)\b", re.I),
    ]

    # -------------------------------------------------------------------------
    # Application Control Patterns
    # -------------------------------------------------------------------------
    _MEDIA_PLAY_PATTERNS = [
        re.compile(r"\bplay\s+(.+?)(?:\s+on\s+([a-zA-Z0-9_\-]+))?(?:\s+(?:on|using|in)\s+([a-zA-Z0-9_\-]+))?$", re.I),
    ]

    _APP_LAUNCH_PATTERNS = [
        re.compile(r"\b(?:open|launch|start|run)\s+(?:the\s+)?(?:app|application|program)?\s*([a-zA-Z0-9_\-\.\+\s]+?)(?:\s+(?:on|to|at)\s+(?:my\s+|the\s+)?(?:desktop|laptop|workstation|pc|server|phone|tablet|rig)|$)", re.I),
    ]

    _APP_CLOSE_PATTERNS = [
        re.compile(r"\b(?:close|quit|exit|stop|terminate|kill)\s+(?:the\s+)?(?:app|application|process|program)?\s*([a-zA-Z0-9_\-\.\+\s]+?)(?:\s+(?:on|to|at)\s+(?:my\s+|the\s+)?(?:desktop|laptop|workstation|pc|server|phone|tablet|rig)|$)", re.I),
    ]

    _APP_RESTART_PATTERNS = [
        re.compile(r"\b(?:restart|relaunch|reboot)\s+(?:the\s+)?(?:app|application|process|program)?\s*([a-zA-Z0-9_\-\.\+\s]+?)(?:\s+(?:on|to|at)\s+(?:my\s+|the\s+)?(?:desktop|laptop|workstation|pc|server|phone|tablet|rig)|$)", re.I),
    ]

    _CLI_SCRIPT_PATTERNS = [
        re.compile(r"\b(?:run|execute)\s+(?:a\s+)?(?:python|bash|powershell|shell|cli)?\s*(?:script|code|command)\s*[:\-]?\s*(.+)$", re.I),
    ]

    # Known common applications
    _COMMON_APPS = {
        "spotify": "Spotify",
        "chrome": "Google Chrome",
        "google chrome": "Google Chrome",
        "firefox": "Firefox",
        "slack": "Slack",
        "discord": "Discord",
        "vs code": "Visual Studio Code",
        "vscode": "Visual Studio Code",
        "notepad": "Notepad",
        "calculator": "Calculator",
        "calc": "Calculator",
        "terminal": "Terminal",
        "powershell": "powershell",
        "cmd": "cmd",
        "docker": "Docker",
        "python": "python",
        "vlc": "VLC",
        "steam": "Steam",
        "youtube": "YouTube",
    }

    @classmethod
    def parse(cls, text: str, context: dict[str, Any] | None = None) -> ParsedDeviceIntent:
        """Parse natural language user text into a structured ParsedDeviceIntent."""
        raw = text.strip()
        lower = raw.lower()
        ctx = context or {}

        # ---------------------------------------------------------------------
        # 0. Confirmation / Cancellation Check
        # ---------------------------------------------------------------------
        if lower in ("confirm", "approve", "proceed", "yes", "confirm execution", "cancel", "deny", "abort"):
            is_approved = lower not in ("cancel", "deny", "abort")
            return ParsedDeviceIntent(
                intent_type=DeviceIntentType.CONFIRMATION,
                parameters={"approved": is_approved},
                confidence=1.0,
                raw_query=raw,
                reason=f"User confirmation response: {'approved' if is_approved else 'cancelled'}.",
            )

        # ---------------------------------------------------------------------
        # 1. Fleet Summary Check
        # ---------------------------------------------------------------------
        for pat in cls._FLEET_SUMMARY_PATTERNS:
            if pat.search(lower):
                return ParsedDeviceIntent(
                    intent_type=DeviceIntentType.FLEET_SUMMARY,
                    confidence=0.95,
                    raw_query=raw,
                    reason="User requested fleet device inventory or connection status.",
                )

        # ---------------------------------------------------------------------
        # 2. Handover Intent Check
        # ---------------------------------------------------------------------
        for pat in cls._HANDOVER_TARGET_PATTERNS:
            m = pat.search(lower)
            if m:
                target_hint = m.group(1).strip()
                # Clean trailing words & prefixes
                target_hint = re.sub(r"^(?:my|the)\s+", "", target_hint, flags=re.I).strip()
                target_hint = re.sub(r"\b(?:now|please|thanks|thank you)\b", "", target_hint).strip()

                source_hint = None
                for s_pat in cls._HANDOVER_SOURCE_PATTERNS:
                    sm = s_pat.search(lower)
                    if sm:
                        source_hint = re.sub(r"^(?:my|the)\s+", "", sm.group(1).strip(), flags=re.I).strip()

                return ParsedDeviceIntent(
                    intent_type=DeviceIntentType.HANDOVER,
                    target_device_hint=target_hint,
                    source_device_hint=source_hint or ctx.get("current_device_id"),
                    confidence=0.92,
                    raw_query=raw,
                    reason=f"Cross-device handover requested targeting '{target_hint}'.",
                )

        # ---------------------------------------------------------------------
        # 3. Fleet Broadcast Intent Check (e.g. "where is Spotify running?")
        # ---------------------------------------------------------------------
        for pat in cls._FLEET_BROADCAST_PATTERNS:
            m = pat.search(lower)
            if m:
                target_subject = m.group(1).strip()
                query_type = "find_app"
                if any(w in lower for w in ("cpu", "memory", "stats", "system")):
                    query_type = "system_stats"
                elif "process" in lower:
                    query_type = "find_process"

                norm_app = cls._COMMON_APPS.get(target_subject.lower(), target_subject.title())

                return ParsedDeviceIntent(
                    intent_type=DeviceIntentType.FLEET_BROADCAST,
                    application=norm_app if query_type != "system_stats" else None,
                    parameters={"query_type": query_type, "query_target": norm_app if query_type != "system_stats" else target_subject},
                    confidence=0.88,
                    raw_query=raw,
                    reason=f"Fleet broadcast query requested for {query_type} on '{norm_app}'.",
                )

        # ---------------------------------------------------------------------
        # 4. Extract Target Device Hint (if query targets a specific device)
        # ---------------------------------------------------------------------
        extracted_device_hint: str | None = None
        for d_pat in cls._DEVICE_HINT_PATTERNS:
            dm = d_pat.search(raw)
            if dm:
                extracted_device_hint = re.sub(r"^(?:my|the)\s+", "", dm.group(1).strip(), flags=re.I).strip()
                break

        # ---------------------------------------------------------------------
        # 5. Media Control Check (e.g. "play Bohemian Rhapsody on Spotify on desktop")
        # ---------------------------------------------------------------------
        if lower.startswith("play "):
            track_and_target = raw[5:].strip()
            app_name = "Spotify"
            track_name = track_and_target

            # Check if app is specified like "on Spotify", "on YouTube", etc.
            app_match = re.search(r"(?i)\s+(?:on|in|using)\s+(spotify|youtube|apple\s*music|vlc|media\s*player)\b", track_name)
            if app_match:
                matched_app_raw = app_match.group(1).lower()
                app_name = cls._COMMON_APPS.get(matched_app_raw, app_match.group(1).title())
                # Splice out the app mention
                track_name = track_name[:app_match.start()] + track_name[app_match.end():]
                track_name = track_name.strip()

            if extracted_device_hint:
                # Remove device mention from track name
                track_name = re.sub(
                    rf"(?i)\s*(?:on|to|at)\s*(?:my\s+|the\s+)?{re.escape(extracted_device_hint)}",
                    "",
                    track_name,
                ).strip()

            return ParsedDeviceIntent(
                intent_type=DeviceIntentType.APP_CONTROL,
                application=app_name,
                capability="play_media",
                parameters={"track": track_name, "query": track_name},
                target_device_hint=extracted_device_hint,
                confidence=0.90,
                raw_query=raw,
                reason=f"Media playback intent for '{track_name}' via {app_name}.",
            )

        # ---------------------------------------------------------------------
        # 6. Process Control Check (Terminate, Restart)
        # ---------------------------------------------------------------------
        for pat in cls._APP_CLOSE_PATTERNS:
            m = pat.search(raw)
            if m:
                app_candidate = m.group(1).strip().strip("'\"")
                norm_app = cls._COMMON_APPS.get(app_candidate.lower(), app_candidate)
                return ParsedDeviceIntent(
                    intent_type=DeviceIntentType.APP_CONTROL,
                    application=norm_app,
                    capability="terminate_process",
                    parameters={"app_name": norm_app, "force": "kill" in lower or "force" in lower},
                    target_device_hint=extracted_device_hint,
                    confidence=0.90,
                    raw_query=raw,
                    reason=f"Process termination requested for '{norm_app}'.",
                )

        for pat in cls._APP_RESTART_PATTERNS:
            m = pat.search(raw)
            if m:
                app_candidate = m.group(1).strip().strip("'\"")
                norm_app = cls._COMMON_APPS.get(app_candidate.lower(), app_candidate)
                return ParsedDeviceIntent(
                    intent_type=DeviceIntentType.APP_CONTROL,
                    application=norm_app,
                    capability="restart_process",
                    parameters={"app_name": norm_app},
                    target_device_hint=extracted_device_hint,
                    confidence=0.88,
                    raw_query=raw,
                    reason=f"Process restart requested for '{norm_app}'.",
                )

        # ---------------------------------------------------------------------
        # 7. Script Execution Check
        # ---------------------------------------------------------------------
        for pat in cls._CLI_SCRIPT_PATTERNS:
            m = pat.search(raw)
            if m:
                script_body = m.group(1).strip()
                if extracted_device_hint:
                    script_body = re.sub(
                        rf"(?i)\s+(?:on|to|at)\s+(?:my\s+|the\s+)?{re.escape(extracted_device_hint)}$",
                        "",
                        script_body,
                    ).strip()

                # Determine language/runtime
                runtime = "python"
                if "powershell" in lower:
                    runtime = "powershell"
                elif "bash" in lower or "shell" in lower:
                    runtime = "bash"

                return ParsedDeviceIntent(
                    intent_type=DeviceIntentType.APP_CONTROL,
                    application=runtime,
                    capability="execute_script",
                    parameters={"script": script_body},
                    target_device_hint=extracted_device_hint,
                    confidence=0.89,
                    raw_query=raw,
                    reason=f"Script execution intent for {runtime}.",
                )

        # ---------------------------------------------------------------------
        # 8. App Launch / Open Check
        # ---------------------------------------------------------------------
        for pat in cls._APP_LAUNCH_PATTERNS:
            m = pat.search(raw)
            if m:
                app_candidate = m.group(1).strip().strip("'\"")

                # Ignore non-app generic terms
                non_apps = {"file", "folder", "document", "tab", "window", "session", "link", "url", "meeting", "task"}
                if app_candidate.lower() in non_apps:
                    continue

                norm_app = cls._COMMON_APPS.get(app_candidate.lower(), app_candidate.title())

                params: dict[str, Any] = {"app_name": norm_app}

                return ParsedDeviceIntent(
                    intent_type=DeviceIntentType.APP_CONTROL,
                    application=norm_app,
                    capability="launch",
                    parameters=params,
                    target_device_hint=extracted_device_hint,
                    confidence=0.86,
                    raw_query=raw,
                    reason=f"Application launch requested for '{norm_app}'.",
                )

        # ---------------------------------------------------------------------
        # 9. Multilingual Semantic Normalization Fallback
        # ---------------------------------------------------------------------
        try:
            from app.multilingual.normalizer import UniversalIntentNormalizer
            from app.multilingual.schemas import IntentCategory

            uni_intent = UniversalIntentNormalizer.normalize(raw)
            if uni_intent.intent_category == IntentCategory.APP_CONTROL and uni_intent.target_app:
                capability = "launch" if uni_intent.action == "open" else "terminate_process"
                norm_app = cls._COMMON_APPS.get(uni_intent.target_app.lower(), uni_intent.target_app)
                return ParsedDeviceIntent(
                    intent_type=DeviceIntentType.APP_CONTROL,
                    application=norm_app,
                    capability=capability,
                    parameters={"app_name": norm_app},
                    target_device_hint=extracted_device_hint,
                    confidence=uni_intent.confidence,
                    raw_query=raw,
                    reason=f"Multilingual intent ({uni_intent.detected_language}) resolved target '{norm_app}'.",
                )
        except Exception:
            pass

        # ---------------------------------------------------------------------
        # Fallback: No device intent detected
        # ---------------------------------------------------------------------
        return ParsedDeviceIntent(
            intent_type=DeviceIntentType.UNKNOWN,
            confidence=0.0,
            raw_query=raw,
            reason="No device or fleet control intent recognized.",
        )
