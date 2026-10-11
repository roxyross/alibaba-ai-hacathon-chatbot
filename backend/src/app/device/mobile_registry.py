"""Phase 13: Mobile App Discovery + Capability Resolution Engine.

Implements:
1. MobileAppRegistry:
   - Deep discovery and authoritative cataloging of installed and known applications for Android and iOS.
   - Comprehensive app metadata: package/bundle identifier, title, version, category,
     supported intents, deep links/URL schemes, share targets, app intents, known integrations,
     permissions, and automation capabilities.
   - Dual-source discovery via native ADB subprocess inspection, enrolled Companion protocols,
     and authoritative mobile knowledge bases.
2. MobileCapabilityRegistry:
   - Dynamic and deterministic synthesis of mobile automation capabilities.
   - Generation of JSONSchema inputs/outputs, risk classifications (LOW, MEDIUM, HIGH, CRITICAL),
     permission scopes, and verification strategies.
3. MobileIntegrationResolver:
   - Resolves optimal mobile execution pathways according to the Universal Integration Priority:
     Connector/Cloud API -> App Intent / Shortcut -> Universal Link / Custom Scheme -> Explicit Intent -> Share Sheet -> UI Automation.
   - Strictly enforces the Zero Simulation Doctrine on iOS: declares arbitrary UI inspection/touch injection as
     unsupported_on_this_platform while offering legitimate platform-supported alternatives.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime
from typing import Any

import structlog

from app.device.capability_engine import assess_action_risk
from app.device.schemas import (
    MobileAppDiscoveryRequest,
    MobileAppDiscoveryResponse,
    MobileAppModel,
    MobileCapabilityModel,
    MobileCapabilityResolutionRequest,
    MobileCapabilityResolutionResponse,
)

log = structlog.get_logger()


# -----------------------------------------------------------------------------
# Authoritative Mobile Knowledge Bases (Android & iOS)
# -----------------------------------------------------------------------------

ANDROID_KNOWN_APPS: dict[str, dict[str, Any]] = {
    "com.spotify.music": {
        "name": "Spotify",
        "category": "media",
        "version": "8.9.22",
        "is_system_app": False,
        "supported_intents": [
            "android.media.action.MEDIA_PLAY_FROM_SEARCH",
            "android.intent.action.VIEW",
        ],
        "deep_links": [
            "spotify:",
            "https://open.spotify.com",
        ],
        "share_targets": [
            "text/plain",
        ],
        "app_intents": [
            "actions.intent.PLAY_MUSIC",
        ],
        "known_integrations": ["connector", "intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.WAKE_LOCK",
            "android.permission.ACCESS_NETWORK_STATE",
        ],
    },
    "com.whatsapp": {
        "name": "WhatsApp",
        "category": "communication",
        "version": "2.24.8",
        "is_system_app": False,
        "supported_intents": [
            "android.intent.action.SEND",
            "android.intent.action.SENDTO",
            "android.intent.action.VIEW",
        ],
        "deep_links": [
            "whatsapp:",
            "https://wa.me",
            "https://api.whatsapp.com",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
            "video/*",
            "audio/*",
            "application/*",
        ],
        "app_intents": [
            "actions.intent.SEND_MESSAGE",
            "actions.intent.START_CALL",
        ],
        "known_integrations": ["intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.READ_CONTACTS",
            "android.permission.RECORD_AUDIO",
            "android.permission.CAMERA",
        ],
    },
    "com.Slack": {
        "name": "Slack",
        "category": "communication",
        "version": "24.03.10",
        "is_system_app": False,
        "supported_intents": [
            "android.intent.action.VIEW",
            "android.intent.action.SEND",
        ],
        "deep_links": [
            "slack:",
            "https://app.slack.com",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
            "application/*",
        ],
        "app_intents": [
            "actions.intent.SEND_MESSAGE",
        ],
        "known_integrations": ["connector", "intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.POST_NOTIFICATIONS",
        ],
    },
    "com.google.android.youtube": {
        "name": "YouTube",
        "category": "media",
        "version": "19.12.34",
        "is_system_app": False,
        "supported_intents": [
            "android.intent.action.VIEW",
            "android.intent.action.SEARCH",
        ],
        "deep_links": [
            "vnd.youtube:",
            "https://www.youtube.com",
            "https://youtu.be",
        ],
        "share_targets": [
            "text/plain",
        ],
        "app_intents": [
            "actions.intent.PLAY_VIDEO",
        ],
        "known_integrations": ["intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
        ],
    },
    "com.google.android.apps.maps": {
        "name": "Google Maps",
        "category": "utilities",
        "version": "11.120.0",
        "is_system_app": False,
        "supported_intents": [
            "android.intent.action.VIEW",
        ],
        "deep_links": [
            "geo:",
            "google.navigation:",
            "https://maps.google.com",
        ],
        "share_targets": [
            "text/plain",
        ],
        "app_intents": [
            "actions.intent.GET_DIRECTIONS",
        ],
        "known_integrations": ["intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.ACCESS_COARSE_LOCATION",
            "android.permission.INTERNET",
        ],
    },
    "com.google.android.gm": {
        "name": "Gmail",
        "category": "communication",
        "version": "2024.03.03",
        "is_system_app": True,
        "supported_intents": [
            "android.intent.action.SEND",
            "android.intent.action.SENDTO",
            "android.intent.action.VIEW",
        ],
        "deep_links": [
            "mailto:",
            "https://mail.google.com",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
            "application/*",
        ],
        "app_intents": [
            "actions.intent.SEND_EMAIL",
        ],
        "known_integrations": ["connector", "intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.GET_ACCOUNTS",
            "android.permission.READ_CONTACTS",
            "android.permission.INTERNET",
        ],
    },
    "com.twitter.android": {
        "name": "X",
        "category": "communication",
        "version": "10.32.0",
        "is_system_app": False,
        "supported_intents": [
            "android.intent.action.VIEW",
            "android.intent.action.SEND",
        ],
        "deep_links": [
            "twitter:",
            "https://x.com",
            "https://twitter.com",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
        ],
        "app_intents": [
            "actions.intent.POST_STATUS",
        ],
        "known_integrations": ["intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.INTERNET",
        ],
    },
    "notion.id": {
        "name": "Notion",
        "category": "productivity",
        "version": "0.6.142",
        "is_system_app": False,
        "supported_intents": [
            "android.intent.action.VIEW",
            "android.intent.action.SEND",
        ],
        "deep_links": [
            "notion:",
            "https://www.notion.so",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
        ],
        "app_intents": [
            "actions.intent.CREATE_NOTE",
        ],
        "known_integrations": ["connector", "intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.INTERNET",
        ],
    },
    "com.android.chrome": {
        "name": "Google Chrome",
        "category": "browser",
        "version": "123.0.6312.80",
        "is_system_app": True,
        "supported_intents": [
            "android.intent.action.VIEW",
            "android.intent.action.WEB_SEARCH",
        ],
        "deep_links": [
            "http:",
            "https:",
            "googlechrome:",
        ],
        "share_targets": [
            "text/plain",
        ],
        "app_intents": [
            "actions.intent.OPEN_URL",
        ],
        "known_integrations": ["intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
        ],
    },
    "org.telegram.messenger": {
        "name": "Telegram",
        "category": "communication",
        "version": "10.9.1",
        "is_system_app": False,
        "supported_intents": [
            "android.intent.action.SEND",
            "android.intent.action.VIEW",
        ],
        "deep_links": [
            "tg:",
            "https://t.me",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
            "video/*",
            "application/*",
        ],
        "app_intents": [
            "actions.intent.SEND_MESSAGE",
        ],
        "known_integrations": ["intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.READ_CONTACTS",
        ],
    },
    "com.google.android.dialer": {
        "name": "Phone",
        "category": "system",
        "version": "125.0",
        "is_system_app": True,
        "supported_intents": [
            "android.intent.action.DIAL",
            "android.intent.action.CALL",
        ],
        "deep_links": [
            "tel:",
        ],
        "share_targets": [],
        "app_intents": [
            "actions.intent.CALL_NUMBER",
        ],
        "known_integrations": ["intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.CALL_PHONE",
            "android.permission.READ_CONTACTS",
        ],
    },
    "com.google.android.apps.messaging": {
        "name": "Messages",
        "category": "communication",
        "version": "2024.03.12",
        "is_system_app": True,
        "supported_intents": [
            "android.intent.action.SENDTO",
            "android.intent.action.VIEW",
        ],
        "deep_links": [
            "sms:",
            "smsto:",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
        ],
        "app_intents": [
            "actions.intent.SEND_MESSAGE",
        ],
        "known_integrations": ["intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.SEND_SMS",
            "android.permission.READ_SMS",
        ],
    },
    "com.google.android.calendar": {
        "name": "Google Calendar",
        "category": "productivity",
        "version": "2024.10.0",
        "is_system_app": True,
        "supported_intents": [
            "android.intent.action.INSERT",
            "android.intent.action.VIEW",
        ],
        "deep_links": [
            "https://calendar.google.com",
        ],
        "share_targets": [],
        "app_intents": [
            "actions.intent.CREATE_CALENDAR_EVENT",
        ],
        "known_integrations": ["connector", "intent", "deep_link", "ui_automation"],
        "permissions": [
            "android.permission.READ_CALENDAR",
            "android.permission.WRITE_CALENDAR",
        ],
    },
    "com.google.android.calculator": {
        "name": "Calculator",
        "category": "utilities",
        "version": "8.4",
        "is_system_app": True,
        "supported_intents": [
            "android.intent.action.VIEW",
        ],
        "deep_links": [],
        "share_targets": [],
        "app_intents": [],
        "known_integrations": ["ui_automation"],
        "permissions": [],
    },
}

IOS_KNOWN_APPS_CATALOG: dict[str, dict[str, Any]] = {
    "com.apple.shortcuts": {
        "name": "Apple Shortcuts",
        "category": "utilities",
        "version": "7.0",
        "is_system_app": True,
        "supported_intents": [],
        "deep_links": [
            "shortcuts:",
            "shortcuts://run-shortcut",
        ],
        "share_targets": [
            "*/*",
        ],
        "app_intents": [
            "RunShortcutIntent",
        ],
        "known_integrations": ["shortcut", "url_scheme"],
        "permissions": [],
    },
    "com.spotify.client": {
        "name": "Spotify",
        "category": "media",
        "version": "8.9.22",
        "is_system_app": False,
        "supported_intents": [],
        "deep_links": [
            "spotify:",
            "https://open.spotify.com",
        ],
        "share_targets": [
            "text/plain",
        ],
        "app_intents": [
            "PlayMusicIntent",
            "INPlayMediaIntent",
        ],
        "known_integrations": ["connector", "universal_link", "url_scheme", "app_intent"],
        "permissions": [
            "NSAppleMusicUsageDescription",
        ],
    },
    "com.apple.Maps": {
        "name": "Apple Maps",
        "category": "utilities",
        "version": "3.0",
        "is_system_app": True,
        "supported_intents": [],
        "deep_links": [
            "maps:",
            "http://maps.apple.com",
            "https://maps.apple.com",
        ],
        "share_targets": [
            "text/plain",
        ],
        "app_intents": [
            "INRequestRideIntent",
        ],
        "known_integrations": ["universal_link", "url_scheme", "app_intent"],
        "permissions": [
            "NSLocationWhenInUseUsageDescription",
        ],
    },
    "com.google.ios.youtube": {
        "name": "YouTube",
        "category": "media",
        "version": "19.12",
        "is_system_app": False,
        "supported_intents": [],
        "deep_links": [
            "youtube:",
            "vnd.youtube:",
            "https://www.youtube.com",
            "https://youtu.be",
        ],
        "share_targets": [
            "text/plain",
        ],
        "app_intents": [],
        "known_integrations": ["universal_link", "url_scheme"],
        "permissions": [],
    },
    "com.tinyspeck.chatlyio": {
        "name": "Slack",
        "category": "communication",
        "version": "24.03",
        "is_system_app": False,
        "supported_intents": [],
        "deep_links": [
            "slack:",
            "https://slack.com",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
        ],
        "app_intents": [
            "INSendMessageIntent",
        ],
        "known_integrations": ["connector", "universal_link", "url_scheme", "app_intent"],
        "permissions": [
            "NSPhotoLibraryUsageDescription",
        ],
    },
    "net.whatsapp.WhatsApp": {
        "name": "WhatsApp",
        "category": "communication",
        "version": "24.6.77",
        "is_system_app": False,
        "supported_intents": [],
        "deep_links": [
            "whatsapp:",
            "https://wa.me",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
            "video/*",
        ],
        "app_intents": [
            "INSendMessageIntent",
            "INStartAudioCallIntent",
        ],
        "known_integrations": ["universal_link", "url_scheme", "app_intent", "share_sheet"],
        "permissions": [
            "NSContactsUsageDescription",
            "NSMicrophoneUsageDescription",
            "NSCameraUsageDescription",
        ],
    },
    "com.atebits.Tweetie2": {
        "name": "X",
        "category": "communication",
        "version": "10.32",
        "is_system_app": False,
        "supported_intents": [],
        "deep_links": [
            "twitter:",
            "https://x.com",
            "https://twitter.com",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
        ],
        "app_intents": [],
        "known_integrations": ["universal_link", "url_scheme", "share_sheet"],
        "permissions": [],
    },
    "notion.id": {
        "name": "Notion",
        "category": "productivity",
        "version": "0.6.142",
        "is_system_app": False,
        "supported_intents": [],
        "deep_links": [
            "notion:",
            "https://www.notion.so",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
        ],
        "app_intents": [],
        "known_integrations": ["connector", "universal_link", "url_scheme", "share_sheet"],
        "permissions": [],
    },
    "com.apple.facetime": {
        "name": "FaceTime",
        "category": "communication",
        "version": "1.0",
        "is_system_app": True,
        "supported_intents": [],
        "deep_links": [
            "facetime:",
            "facetime-audio:",
        ],
        "share_targets": [],
        "app_intents": [
            "INStartVideoCallIntent",
            "INStartAudioCallIntent",
        ],
        "known_integrations": ["url_scheme", "app_intent"],
        "permissions": [
            "NSCameraUsageDescription",
            "NSMicrophoneUsageDescription",
        ],
    },
    "com.apple.mobilephone": {
        "name": "Phone",
        "category": "system",
        "version": "1.0",
        "is_system_app": True,
        "supported_intents": [],
        "deep_links": [
            "tel:",
        ],
        "share_targets": [],
        "app_intents": [
            "INStartAudioCallIntent",
        ],
        "known_integrations": ["url_scheme", "app_intent"],
        "permissions": [],
    },
    "com.apple.mobilemail": {
        "name": "Apple Mail",
        "category": "communication",
        "version": "1.0",
        "is_system_app": True,
        "supported_intents": [],
        "deep_links": [
            "mailto:",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
            "application/*",
        ],
        "app_intents": [
            "INSearchForMessagesIntent",
        ],
        "known_integrations": ["url_scheme", "app_intent", "share_sheet"],
        "permissions": [],
    },
    "com.apple.MobileSMS": {
        "name": "Messages",
        "category": "communication",
        "version": "1.0",
        "is_system_app": True,
        "supported_intents": [],
        "deep_links": [
            "sms:",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
        ],
        "app_intents": [
            "INSendMessageIntent",
        ],
        "known_integrations": ["url_scheme", "app_intent", "share_sheet"],
        "permissions": [],
    },
    "com.apple.mobilenotes": {
        "name": "Notes",
        "category": "productivity",
        "version": "1.0",
        "is_system_app": True,
        "supported_intents": [],
        "deep_links": [
            "mobilenotes:",
        ],
        "share_targets": [
            "text/plain",
            "image/*",
        ],
        "app_intents": [
            "INCreateNoteIntent",
        ],
        "known_integrations": ["url_scheme", "app_intent", "share_sheet"],
        "permissions": [],
    },
    "com.apple.mobilecal": {
        "name": "Calendar",
        "category": "productivity",
        "version": "1.0",
        "is_system_app": True,
        "supported_intents": [],
        "deep_links": [
            "calshow:",
        ],
        "share_targets": [],
        "app_intents": [
            "INCreateEventIntent",
        ],
        "known_integrations": ["url_scheme", "app_intent"],
        "permissions": [
            "NSCalendarsUsageDescription",
        ],
    },
    "com.apple.Music": {
        "name": "Apple Music",
        "category": "media",
        "version": "1.0",
        "is_system_app": True,
        "supported_intents": [],
        "deep_links": [
            "music:",
            "musics:",
            "https://music.apple.com",
        ],
        "share_targets": [
            "text/plain",
        ],
        "app_intents": [
            "INPlayMediaIntent",
        ],
        "known_integrations": ["universal_link", "url_scheme", "app_intent"],
        "permissions": [
            "NSAppleMusicUsageDescription",
        ],
    },
    "com.apple.mobilesafari": {
        "name": "Safari",
        "category": "browser",
        "version": "17.0",
        "is_system_app": True,
        "supported_intents": [],
        "deep_links": [
            "http:",
            "https:",
        ],
        "share_targets": [
            "text/plain",
        ],
        "app_intents": [],
        "known_integrations": ["universal_link", "url_scheme"],
        "permissions": [],
    },
    "com.apple.reminders": {
        "name": "Reminders",
        "category": "productivity",
        "version": "1.0",
        "is_system_app": True,
        "supported_intents": [],
        "deep_links": [
            "x-apple-reminderkit:",
        ],
        "share_targets": [
            "text/plain",
        ],
        "app_intents": [
            "INAddTasksIntent",
        ],
        "known_integrations": ["url_scheme", "app_intent", "share_sheet"],
        "permissions": [
            "NSRemindersUsageDescription",
        ],
    },
}


# -----------------------------------------------------------------------------
# Mobile Capability Registry
# -----------------------------------------------------------------------------

class MobileCapabilityRegistry:
    """Discovers, synthesizes, and registers capability models for mobile apps."""

    def __init__(self) -> None:
        self._capabilities: dict[str, list[MobileCapabilityModel]] = {}
        self._lock = threading.Lock()

    def register_capability(self, app_id: str, capability: MobileCapabilityModel) -> None:
        with self._lock:
            if app_id not in self._capabilities:
                self._capabilities[app_id] = []
            # Replace existing if duplicate ID
            self._capabilities[app_id] = [
                c for c in self._capabilities[app_id] if c.capability_id != capability.capability_id
            ]
            self._capabilities[app_id].append(capability)

    def get_capabilities_for_app(self, app_id: str) -> list[MobileCapabilityModel]:
        with self._lock:
            return list(self._capabilities.get(app_id, []))

    def find_capability(self, app_id: str, capability_name: str) -> MobileCapabilityModel | None:
        with self._lock:
            caps = self._capabilities.get(app_id, [])
            norm = capability_name.lower().replace(" ", "_")
            for c in caps:
                if c.capability_id == norm or norm in c.capability_id:
                    return c
            return None

    def synthesize_capabilities(self, app: MobileAppModel) -> list[MobileCapabilityModel]:
        """Synthesize authoritative capabilities for a mobile app based on its metadata."""
        synthesized: list[MobileCapabilityModel] = []
        app_slug = app.name.lower().replace(" ", "_")

        # 1. Cloud Connector capabilities (Tier 1 Priority)
        from app.device.integration_resolver import KNOWN_CONNECTOR_CATALOG

        if app_slug in KNOWN_CONNECTOR_CATALOG:
            connector_info = KNOWN_CONNECTOR_CATALOG[app_slug]
            for cap_name, tool_name in connector_info.get("capabilities", {}).items():
                synthesized.append(
                    MobileCapabilityModel(
                        capability_id=f"{app_slug}_{cap_name}",
                        name=f"{app.name} {cap_name.replace('_', ' ').title()}",
                        description=f"Official Cloud Connector action for {app.name}.",
                        capability_type="connector",
                        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                        output_schema={"type": "object"},
                        risk_level=assess_action_risk(cap_name).value.upper(),  # type: ignore[arg-type]
                        required_permission=f"connector:{app_slug}:{cap_name}",
                        execution_adapter="cloud_connector",
                        verification_strategy="api_status_check",
                        confidence=0.98,
                        source="known_catalog",
                        parameters={"tool_name": tool_name, "connector_type": app_slug},
                    )
                )

        # 2. Deep links & URL Schemes
        for scheme in app.deep_links:
            synthesized.append(
                MobileCapabilityModel(
                    capability_id=f"{app_slug}_open_link",
                    name=f"Open {app.name} via Scheme/Link",
                    description=f"Direct URI navigation via scheme '{scheme}'.",
                    capability_type="universal_link" if scheme.startswith("https") else "url_scheme",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "parameters": {"type": "object"},
                        },
                    },
                    output_schema={"type": "object"},
                    risk_level="LOW",
                    required_permission=f"app:{app.package_or_bundle_id}:open",
                    execution_adapter="ios_universal_link" if app.platform == "ios" and scheme.startswith("https") else (
                        "ios_url_scheme" if app.platform == "ios" else "android_deep_link"
                    ),
                    verification_strategy="ios_link_or_scheme_probe" if app.platform == "ios" else "mobile_ui_dump_match",
                    confidence=0.92,
                    source="known_catalog",
                    parameters={"scheme": scheme, "target_package": app.package_or_bundle_id},
                )
            )

        # 3. Android Intent Actions
        if app.platform == "android":
            for intent_action in app.supported_intents:
                action_slug = intent_action.split(".")[-1].lower()
                synthesized.append(
                    MobileCapabilityModel(
                        capability_id=f"{app_slug}_intent_{action_slug}",
                        name=f"{app.name} Intent {action_slug.title()}",
                        description=f"Android Intent invocation for action '{intent_action}'.",
                        capability_type="intent",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "uri": {"type": "string"},
                                "extras": {"type": "object"},
                            },
                        },
                        output_schema={"type": "object"},
                        risk_level=assess_action_risk(action_slug).value.upper(),  # type: ignore[arg-type]
                        required_permission=f"app:{app.package_or_bundle_id}:intent_{action_slug}",
                        execution_adapter="android_intent",
                        verification_strategy="mobile_intent_and_ui_hierarchy",
                        confidence=0.90,
                        source="package_manifest",
                        parameters={"action": intent_action, "package": app.package_or_bundle_id},
                    )
                )

        # 4. iOS App Intents & Apple Shortcuts
        if app.platform == "ios":
            for intent_name in app.app_intents:
                synthesized.append(
                    MobileCapabilityModel(
                        capability_id=f"{app_slug}_app_intent_{intent_name.lower()}",
                        name=f"{app.name} App Intent {intent_name}",
                        description=f"iOS 16+ App Intent dispatch for '{intent_name}'.",
                        capability_type="app_intent",
                        input_schema={"type": "object", "properties": {"parameters": {"type": "object"}}},
                        output_schema={"type": "object"},
                        risk_level=assess_action_risk(intent_name).value.upper(),  # type: ignore[arg-type]
                        required_permission=f"app:{app.package_or_bundle_id}:app_intent",
                        execution_adapter="ios_app_intent",
                        verification_strategy="ios_app_intent_probe",
                        confidence=0.94,
                        source="known_catalog",
                        parameters={"intent_name": intent_name, "bundle_id": app.package_or_bundle_id},
                    )
                )
            # Default shortcut run capability
            synthesized.append(
                MobileCapabilityModel(
                    capability_id=f"{app_slug}_run_shortcut",
                    name=f"Run {app.name} Shortcut",
                    description=f"Executes an Apple Shortcut interacting with {app.name}.",
                    capability_type="shortcut",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "shortcut_name": {"type": "string"},
                            "input_value": {"type": "string"},
                        },
                    },
                    output_schema={"type": "object"},
                    risk_level="MEDIUM",
                    required_permission="device:ios:run_shortcut",
                    execution_adapter="ios_shortcut",
                    verification_strategy="ios_shortcut_probe",
                    confidence=0.95,
                    source="shortcut_registry",
                    parameters={"bundle_id": app.package_or_bundle_id},
                )
            )

        # 5. Share Targets / Share Sheet
        if app.share_targets:
            synthesized.append(
                MobileCapabilityModel(
                    capability_id=f"{app_slug}_share",
                    name=f"Share Content with {app.name}",
                    description=f"Dispatches content to {app.name} via system Share Sheet.",
                    capability_type="share_sheet",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "url": {"type": "string"},
                            "file_path": {"type": "string"},
                        },
                    },
                    output_schema={"type": "object"},
                    risk_level="LOW",
                    required_permission=f"app:{app.package_or_bundle_id}:share",
                    execution_adapter="ios_share_sheet" if app.platform == "ios" else "android_intent",
                    verification_strategy="ios_share_sheet_probe" if app.platform == "ios" else "mobile_ui_dump_match",
                    confidence=0.88,
                    source="known_catalog",
                    parameters={"target_package": app.package_or_bundle_id, "share_targets": app.share_targets},
                )
            )

        # 6. UI Automation
        if app.platform == "android":
            # Real accessibility-based automation
            synthesized.append(
                MobileCapabilityModel(
                    capability_id=f"{app_slug}_ui_automation",
                    name=f"{app.name} Interactive UI Automation",
                    description=f"Inspects and automates {app.name} via Android AccessibilityService.",
                    capability_type="ui_automation",
                    input_schema={"type": "object", "properties": {"action": {"type": "string"}}},
                    output_schema={"type": "object"},
                    risk_level="MEDIUM",
                    required_permission="device:android:mobile_automation",
                    execution_adapter="android_ui",
                    verification_strategy="mobile_ui_dump_match",
                    confidence=0.85,
                    source="os_query",
                    parameters={"package": app.package_or_bundle_id},
                )
            )
        else:
            # iOS Zero Simulation boundary
            synthesized.append(
                MobileCapabilityModel(
                    capability_id=f"{app_slug}_ui_automation",
                    name=f"{app.name} UI Automation (Platform Restricted)",
                    description=(
                        "Direct third-party UI touch automation is restricted by iOS security sandbox. "
                        "Use supported alternatives: Universal Links, Custom URL Schemes, Apple Shortcuts, or App Intents."
                    ),
                    capability_type="ui_automation",
                    input_schema={"type": "object"},
                    output_schema={"type": "object"},
                    risk_level="LOW",
                    required_permission="none",
                    execution_adapter="unsupported",
                    verification_strategy="none",
                    confidence=0.0,
                    source="os_query",
                    parameters={"status": "unsupported_on_this_platform"},
                )
            )

        # Cache synthesized capabilities
        with self._lock:
            self._capabilities[app.app_id] = synthesized

        return synthesized


# -----------------------------------------------------------------------------
# Mobile App Registry
# -----------------------------------------------------------------------------

class MobileAppRegistry:
    """Authoritative registry and deep discovery coordinator for mobile apps."""

    def __init__(self, capability_registry: MobileCapabilityRegistry | None = None) -> None:
        self._capability_registry = capability_registry or MobileCapabilityRegistry()
        self._apps: dict[str, MobileAppModel] = {}  # keyed by app_id
        self._device_apps: dict[str, list[str]] = {}  # device_id -> list of app_ids
        self._lock = threading.Lock()
        self._initialize_builtins()

    def _initialize_builtins(self) -> None:
        """Pre-populate the global catalog with verified Android and iOS applications."""
        now = datetime.now(UTC).isoformat()

        # Load Android built-ins
        for pkg, meta in ANDROID_KNOWN_APPS.items():
            app_id = f"mobile:android:{pkg}"
            app = MobileAppModel(
                app_id=app_id,
                package_or_bundle_id=pkg,
                name=meta["name"],
                version=meta.get("version", "1.0.0"),
                platform="android",
                category=meta.get("category", "general"),
                installed=True,
                is_system_app=meta.get("is_system_app", False),
                supported_intents=meta.get("supported_intents", []),
                deep_links=meta.get("deep_links", []),
                share_targets=meta.get("share_targets", []),
                app_intents=meta.get("app_intents", []),
                known_integrations=meta.get("known_integrations", []),
                permissions=meta.get("permissions", []),
                discovered_at=now,
            )
            app.automation_capabilities = self._capability_registry.synthesize_capabilities(app)
            self._apps[app_id] = app

        # Load iOS built-ins
        for bundle, meta in IOS_KNOWN_APPS_CATALOG.items():
            app_id = f"mobile:ios:{bundle}"
            app = MobileAppModel(
                app_id=app_id,
                package_or_bundle_id=bundle,
                name=meta["name"],
                version=meta.get("version", "1.0.0"),
                platform="ios",
                category=meta.get("category", "general"),
                installed=True,
                is_system_app=meta.get("is_system_app", False),
                supported_intents=meta.get("supported_intents", []),
                deep_links=meta.get("deep_links", []),
                share_targets=meta.get("share_targets", []),
                app_intents=meta.get("app_intents", []),
                known_integrations=meta.get("known_integrations", []),
                permissions=meta.get("permissions", []),
                discovered_at=now,
            )
            app.automation_capabilities = self._capability_registry.synthesize_capabilities(app)
            self._apps[app_id] = app

    def register_app(self, app: MobileAppModel, device_id: str | None = None) -> MobileAppModel:
        """Register or update an application in the registry."""
        with self._lock:
            # Synthesize capabilities if missing
            if not app.automation_capabilities:
                app.automation_capabilities = self._capability_registry.synthesize_capabilities(app)

            self._apps[app.app_id] = app

            target_device = device_id or app.device_id
            if target_device:
                if target_device not in self._device_apps:
                    self._device_apps[target_device] = []
                if app.app_id not in self._device_apps[target_device]:
                    self._device_apps[target_device].append(app.app_id)

            return app

    def get_app(
        self, package_or_bundle: str, platform: str | None = None, device_id: str | None = None
    ) -> MobileAppModel | None:
        """Retrieve app by package or bundle ID, optionally scoped by platform and device."""
        with self._lock:
            # Direct app_id check
            if package_or_bundle in self._apps:
                return self._apps[package_or_bundle]

            target_apps = list(self._apps.values())
            if device_id and device_id in self._device_apps:
                dev_ids = set(self._device_apps[device_id])
                target_apps = [a for a in target_apps if a.app_id in dev_ids]

            for a in target_apps:
                if platform and a.platform != platform:
                    continue
                if a.package_or_bundle_id.lower() == package_or_bundle.lower():
                    return a

            return None

    def find_app_by_name(
        self, name: str, platform: str | None = None, device_id: str | None = None
    ) -> MobileAppModel | None:
        """Search app by human-readable title, slug, or synonym."""
        clean = name.strip().lower().replace(" ", "")
        with self._lock:
            target_apps = list(self._apps.values())
            if device_id and device_id in self._device_apps:
                dev_ids = set(self._device_apps[device_id])
                target_apps = [a for a in target_apps if a.app_id in dev_ids]

            # 1. Exact match on name or package
            for a in target_apps:
                if platform and a.platform != platform:
                    continue
                if a.name.lower().replace(" ", "") == clean:
                    return a
                if a.package_or_bundle_id.lower() == clean:
                    return a

            # 2. Substring or token match (require minimum 3 characters to avoid false-positive token matches)
            for a in target_apps:
                if platform and a.platform != platform:
                    continue
                app_clean = a.name.lower().replace(" ", "")
                if (len(clean) >= 3 and clean in app_clean) or (len(app_clean) >= 3 and app_clean in clean):
                    return a

            return None

    def list_apps(
        self,
        device_id: str | None = None,
        platform: str | None = None,
        include_system: bool = True,
    ) -> list[MobileAppModel]:
        """List registered mobile applications matching criteria."""
        with self._lock:
            target_apps = list(self._apps.values())
            if device_id and device_id in self._device_apps:
                dev_ids = set(self._device_apps[device_id])
                target_apps = [a for a in target_apps if a.app_id in dev_ids]

            filtered: list[MobileAppModel] = []
            for a in target_apps:
                if platform and a.platform != platform:
                    continue
                if not include_system and a.is_system_app:
                    continue
                filtered.append(a)

            return sorted(filtered, key=lambda x: x.name.lower())

    def discover_device_apps(self, request: MobileAppDiscoveryRequest) -> MobileAppDiscoveryResponse:
        """Execute comprehensive app discovery on physical device, simulator, or companion."""
        start_time = time.perf_counter()
        discovered: list[MobileAppModel] = []
        scan_source: Any = "known_catalog"
        now = datetime.now(UTC).isoformat()

        # 1. Check if companion provided catalog directly in request
        if request.companion_catalog:
            scan_source = "companion_protocol"
            for raw in request.companion_catalog:
                pkg_or_bundle = raw.get("package_name") or raw.get("bundle_id") or raw.get("id", "")
                if not pkg_or_bundle:
                    continue
                title = raw.get("name") or raw.get("title") or pkg_or_bundle.split(".")[-1].title()
                app_id = f"mobile:{request.platform}:{pkg_or_bundle}"

                # Merge with known knowledge base if available
                known = (
                    ANDROID_KNOWN_APPS.get(pkg_or_bundle)
                    if request.platform == "android"
                    else IOS_KNOWN_APPS_CATALOG.get(pkg_or_bundle)
                ) or {}

                app = MobileAppModel(
                    app_id=app_id,
                    package_or_bundle_id=pkg_or_bundle,
                    name=title,
                    version=raw.get("version") or known.get("version", "1.0.0"),
                    platform=request.platform,
                    device_id=request.device_id,
                    installed=True,
                    is_system_app=raw.get("is_system_app", known.get("is_system_app", False)),
                    category=raw.get("category", known.get("category", "general")),
                    supported_intents=raw.get("supported_intents", known.get("supported_intents", [])),
                    deep_links=raw.get("deep_links", known.get("deep_links", [])),
                    share_targets=raw.get("share_targets", known.get("share_targets", [])),
                    app_intents=raw.get("app_intents", known.get("app_intents", [])),
                    known_integrations=known.get("known_integrations", []),
                    permissions=raw.get("permissions", known.get("permissions", [])),
                    discovered_at=now,
                    last_verified_at=now,
                )
                app.automation_capabilities = self._capability_registry.synthesize_capabilities(app)
                self.register_app(app, request.device_id)
                discovered.append(app)

        # 2. If Android, attempt physical/emulator ADB query
        elif request.platform == "android" and shutil.which("adb"):
            try:
                cmd = ["adb", "-s", request.device_id, "shell", "pm", "list", "packages", "-3"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    scan_source = "adb_subsystem"
                    for line in res.stdout.splitlines():
                        if not line.startswith("package:"):
                            continue
                        pkg = line.replace("package:", "").strip()
                        known = ANDROID_KNOWN_APPS.get(pkg, {})
                        title = known.get("name") or pkg.split(".")[-1].title()
                        app_id = f"mobile:android:{pkg}"

                        app = MobileAppModel(
                            app_id=app_id,
                            package_or_bundle_id=pkg,
                            name=title,
                            version=known.get("version", "1.0.0"),
                            platform="android",
                            device_id=request.device_id,
                            installed=True,
                            is_system_app=False,
                            category=known.get("category", "general"),
                            supported_intents=known.get("supported_intents", []),
                            deep_links=known.get("deep_links", []),
                            share_targets=known.get("share_targets", []),
                            app_intents=known.get("app_intents", []),
                            known_integrations=known.get("known_integrations", ["intent", "ui_automation"]),
                            permissions=known.get("permissions", []),
                            discovered_at=now,
                            last_verified_at=now,
                        )
                        app.automation_capabilities = self._capability_registry.synthesize_capabilities(app)
                        self.register_app(app, request.device_id)
                        discovered.append(app)
            except Exception as e:
                log.debug("adb_scan_failed", error=str(e), device_id=request.device_id)

        # 3. Fallback / Hybrid: populate from authoritative known catalog
        if not discovered:
            scan_source = "known_catalog"
            catalog = ANDROID_KNOWN_APPS if request.platform == "android" else IOS_KNOWN_APPS_CATALOG
            for identifier, meta in catalog.items():
                if not request.include_system_apps and meta.get("is_system_app", False):
                    continue
                app_id = f"mobile:{request.platform}:{identifier}"
                app = MobileAppModel(
                    app_id=app_id,
                    package_or_bundle_id=identifier,
                    name=meta["name"],
                    version=meta.get("version", "1.0.0"),
                    platform=request.platform,
                    device_id=request.device_id,
                    installed=True,
                    is_system_app=meta.get("is_system_app", False),
                    category=meta.get("category", "general"),
                    supported_intents=meta.get("supported_intents", []),
                    deep_links=meta.get("deep_links", []),
                    share_targets=meta.get("share_targets", []),
                    app_intents=meta.get("app_intents", []),
                    known_integrations=meta.get("known_integrations", []),
                    permissions=meta.get("permissions", []),
                    discovered_at=now,
                    last_verified_at=now,
                )
                app.automation_capabilities = self._capability_registry.synthesize_capabilities(app)
                self.register_app(app, request.device_id)
                discovered.append(app)

        elapsed = (time.perf_counter() - start_time) * 1000
        return MobileAppDiscoveryResponse(
            device_id=request.device_id,
            platform=request.platform,
            total_apps=len(discovered),
            apps=discovered,
            scan_source=scan_source,
            duration_ms=round(elapsed, 2),
            discovered_at=now,
        )


# -----------------------------------------------------------------------------
# Mobile Integration Resolver
# -----------------------------------------------------------------------------

class MobileIntegrationResolver:
    """Evaluates the optimal mobile integration pathway according to the Universal Integration Priority."""

    def __init__(
        self,
        app_registry: MobileAppRegistry | None = None,
        capability_registry: MobileCapabilityRegistry | None = None,
    ) -> None:
        self._capability_registry = capability_registry or MobileCapabilityRegistry()
        self._app_registry = app_registry or MobileAppRegistry(self._capability_registry)

    def resolve_capability(
        self, request: MobileCapabilityResolutionRequest
    ) -> MobileCapabilityResolutionResponse:
        """Resolve optimal execution adapter, permissions, and verification strategy."""
        target_raw = request.package_or_bundle_id.strip()
        cap_raw = request.requested_capability.strip()
        platform = request.platform

        # 1. Lookup app in registry
        app = self._app_registry.get_app(target_raw, platform, request.device_id)
        if not app:
            app = self._app_registry.find_app_by_name(target_raw, platform, request.device_id)

        if not app and not platform:
            # Check if target is a known app in another platform if not specified
            app = self._app_registry.find_app_by_name(target_raw, "android", request.device_id) or (
                self._app_registry.find_app_by_name(target_raw, "ios", request.device_id)
            )

        if not app:
            return MobileCapabilityResolutionResponse(
                success=False,
                remediation_guidance=(
                    f"Application '{target_raw}' was not discovered on the device or recognized in authoritative catalogs. "
                    f"Please verify installation or run mobile app discovery."
                ),
            )

        app_platform = app.platform
        norm_cap = cap_raw.lower().replace(" ", "_")

        # 2. Check caller's preferred integration override
        if request.preferred_integration:
            for cap in app.automation_capabilities:
                if cap.capability_type == request.preferred_integration or cap.execution_adapter == request.preferred_integration:
                    return MobileCapabilityResolutionResponse(
                        success=True,
                        app=app,
                        capability=cap,
                        integration_type=cap.capability_type,
                        confidence=0.96,
                        execution_adapter=cap.execution_adapter,
                        verification_strategy=cap.verification_strategy,
                        required_permission=cap.required_permission,
                        risk_level=cap.risk_level,
                        requires_confirmation=cap.risk_level in ("HIGH", "CRITICAL"),
                        resolved_parameters={**cap.parameters, **request.parameters},
                    )

        # 3. Universal Integration Priority Evaluation

        # --- Priority 1: Cloud Connector / API ---
        for cap in app.automation_capabilities:
            if cap.capability_type == "connector" and (norm_cap in cap.capability_id or cap.capability_id in norm_cap):
                return MobileCapabilityResolutionResponse(
                    success=True,
                    app=app,
                    capability=cap,
                    integration_type="connector",
                    confidence=0.98,
                    execution_adapter=cap.execution_adapter,
                    verification_strategy=cap.verification_strategy,
                    required_permission=cap.required_permission,
                    risk_level=cap.risk_level,
                    requires_confirmation=cap.risk_level in ("HIGH", "CRITICAL"),
                    resolved_parameters={**cap.parameters, **request.parameters},
                )

        # --- Priority 2: Platform App Intent / Apple Shortcut ---
        if app_platform == "ios":
            # App Intents
            for cap in app.automation_capabilities:
                if cap.capability_type == "app_intent" and (norm_cap in cap.capability_id or any(k in norm_cap for k in ("intent", "action"))):
                    return MobileCapabilityResolutionResponse(
                        success=True,
                        app=app,
                        capability=cap,
                        integration_type="app_intent",
                        confidence=0.95,
                        execution_adapter=cap.execution_adapter,
                        verification_strategy=cap.verification_strategy,
                        required_permission=cap.required_permission,
                        risk_level=cap.risk_level,
                        requires_confirmation=cap.risk_level in ("HIGH", "CRITICAL"),
                        resolved_parameters={**cap.parameters, **request.parameters},
                    )
            # Shortcuts
            if any(k in norm_cap for k in ("shortcut", "run", "flow")):
                for cap in app.automation_capabilities:
                    if cap.capability_type == "shortcut":
                        return MobileCapabilityResolutionResponse(
                            success=True,
                            app=app,
                            capability=cap,
                            integration_type="shortcut",
                            confidence=0.94,
                            execution_adapter=cap.execution_adapter,
                            verification_strategy=cap.verification_strategy,
                            required_permission=cap.required_permission,
                            risk_level=cap.risk_level,
                            requires_confirmation=cap.risk_level in ("HIGH", "CRITICAL"),
                            resolved_parameters={**cap.parameters, **request.parameters},
                        )

        # --- Priority 3: Deep Link / Universal Link / URL Scheme ---
        if any(k in norm_cap for k in ("open", "launch", "link", "url", "play", "view", "track", "channel", "page")):
            for cap in app.automation_capabilities:
                if cap.capability_type in ("universal_link", "url_scheme", "deep_link"):
                    return MobileCapabilityResolutionResponse(
                        success=True,
                        app=app,
                        capability=cap,
                        integration_type=cap.capability_type,
                        confidence=0.92,
                        execution_adapter=cap.execution_adapter,
                        verification_strategy=cap.verification_strategy,
                        required_permission=cap.required_permission,
                        risk_level=cap.risk_level,
                        requires_confirmation=cap.risk_level in ("HIGH", "CRITICAL"),
                        resolved_parameters={**cap.parameters, **request.parameters},
                    )

        # --- Priority 4: Explicit Android Intent ---
        if app_platform == "android":
            for cap in app.automation_capabilities:
                if cap.capability_type == "intent" and (norm_cap in cap.capability_id or any(k in norm_cap for k in ("intent", "send", "view", "dial"))):
                    return MobileCapabilityResolutionResponse(
                        success=True,
                        app=app,
                        capability=cap,
                        integration_type="intent",
                        confidence=0.90,
                        execution_adapter=cap.execution_adapter,
                        verification_strategy=cap.verification_strategy,
                        required_permission=cap.required_permission,
                        risk_level=cap.risk_level,
                        requires_confirmation=cap.risk_level in ("HIGH", "CRITICAL"),
                        resolved_parameters={**cap.parameters, **request.parameters},
                    )

        # --- Priority 5: System Share Sheet ---
        if any(k in norm_cap for k in ("share", "post", "send_file", "send_link")):
            for cap in app.automation_capabilities:
                if cap.capability_type == "share_sheet":
                    return MobileCapabilityResolutionResponse(
                        success=True,
                        app=app,
                        capability=cap,
                        integration_type="share_sheet",
                        confidence=0.89,
                        execution_adapter=cap.execution_adapter,
                        verification_strategy=cap.verification_strategy,
                        required_permission=cap.required_permission,
                        risk_level=cap.risk_level,
                        requires_confirmation=cap.risk_level in ("HIGH", "CRITICAL"),
                        resolved_parameters={**cap.parameters, **request.parameters},
                    )

        # --- Priority 6: UI Automation vs Zero Simulation Platform Boundary ---
        if any(k in norm_cap for k in ("click", "tap", "type", "scroll", "inspect", "ui")):
            if app_platform == "android":
                for cap in app.automation_capabilities:
                    if cap.capability_type == "ui_automation":
                        return MobileCapabilityResolutionResponse(
                            success=True,
                            app=app,
                            capability=cap,
                            integration_type="ui_automation",
                            confidence=0.85,
                            execution_adapter=cap.execution_adapter,
                            verification_strategy=cap.verification_strategy,
                            required_permission=cap.required_permission,
                            risk_level=cap.risk_level,
                            requires_confirmation=cap.risk_level in ("HIGH", "CRITICAL"),
                            resolved_parameters={**cap.parameters, **request.parameters},
                        )
            else:
                # iOS: Zero Simulation Doctrine honesty
                return MobileCapabilityResolutionResponse(
                    success=False,
                    app=app,
                    integration_type="unsupported_on_this_platform",
                    confidence=0.0,
                    execution_adapter="unsupported",
                    verification_strategy="none",
                    remediation_guidance=(
                        f"Arbitrary UI touch/type automation is forbidden by iOS platform sandbox security. "
                        f"Please use one of the supported alternatives available for {app.name}: "
                        f"Universal Links ({app.deep_links}), Apple Shortcuts, or App Intents ({app.app_intents})."
                    ),
                    alternatives=["universal_link", "url_scheme", "shortcut", "app_intent", "share_sheet"],
                )

        # Default fallback: pick the most capable supported action or open_link
        if app.automation_capabilities:
            best_cap = app.automation_capabilities[0]
            return MobileCapabilityResolutionResponse(
                success=True,
                app=app,
                capability=best_cap,
                integration_type=best_cap.capability_type,
                confidence=0.80,
                execution_adapter=best_cap.execution_adapter,
                verification_strategy=best_cap.verification_strategy,
                required_permission=best_cap.required_permission,
                risk_level=best_cap.risk_level,
                requires_confirmation=best_cap.risk_level in ("HIGH", "CRITICAL"),
                resolved_parameters={**best_cap.parameters, **request.parameters},
            )

        return MobileCapabilityResolutionResponse(
            success=False,
            app=app,
            remediation_guidance=f"No supported mobile capability resolved for action '{cap_raw}' on {app.name}.",
        )


# Global Singleton instances
_global_capability_registry = MobileCapabilityRegistry()
_global_app_registry = MobileAppRegistry(_global_capability_registry)
_global_integration_resolver = MobileIntegrationResolver(_global_app_registry, _global_capability_registry)


def get_mobile_app_registry() -> MobileAppRegistry:
    return _global_app_registry


def get_mobile_capability_registry() -> MobileCapabilityRegistry:
    return _global_capability_registry


def get_mobile_integration_resolver() -> MobileIntegrationResolver:
    return _global_integration_resolver
