"""Universal Integration Resolution Engine (Phase 8).

Under the Zero Simulation doctrine:
Determines the optimal, most reliable integration pathway to fulfill an application
capability request across cloud APIs/Connectors, local MCP tools, CLI binaries,
native desktop UI automation, mobile bridge, and system process controllers.

Decision Hierarchy:
1. Cloud / SaaS Connector & API (Highest reliability, structured, robust OAuth)
2. Model Context Protocol (MCP) Tool (Standardized tool protocol)
3. CLI Subprocess / Local REST (Native high-speed deterministic binary execution)
4. Desktop UI Automation (Accessible Windows UIA, macOS Accessibility, Linux AT-SPI)
5. Mobile Bridge (Android ADB / iOS Instruments UI automation)
6. System Process Launcher (Application lifecycle start, stop, restart, focus)
7. Browser Web Subsystem (Web applications and browser sessions)
8. Honest Unsupported (Zero hallucination fallback with remediation guidance)
"""

from __future__ import annotations

import re
import shutil
import time
from typing import Any, cast

import structlog

from app.device.capability_engine import assess_action_risk
from app.device.schemas import (
    IntegrationCandidateModel,
    IntegrationResolutionRequest,
    IntegrationResolutionResult,
    IntegrationType,
    VerificationMethodType,
)

log = structlog.get_logger()


# -----------------------------------------------------------------------------
# Known Application & Connector Catalog
# -----------------------------------------------------------------------------

KNOWN_CONNECTOR_CATALOG: dict[str, dict[str, Any]] = {
    "spotify": {
        "title": "Spotify",
        "connector_type": "spotify",
        "capabilities": {
            "play_music": "spotify_play_track",
            "play": "spotify_play",
            "pause": "spotify_pause",
            "pause_music": "spotify_pause",
            "next_track": "spotify_next",
            "previous_track": "spotify_previous",
            "search_tracks": "spotify_search",
            "list_playlists": "spotify_get_playlists",
            "get_current_playback": "spotify_current_playback",
        },
        "auth_methods": ["oauth2"],
    },
    "slack": {
        "title": "Slack",
        "connector_type": "slack",
        "capabilities": {
            "send_message": "slack_post_message",
            "read_messages": "slack_list_messages",
            "list_channels": "slack_list_channels",
            "post_update": "slack_post_message",
        },
        "auth_methods": ["oauth2", "bot_token"],
    },
    "github": {
        "title": "GitHub",
        "connector_type": "github",
        "capabilities": {
            "create_issue": "github_create_issue",
            "search_repos": "github_search_repositories",
            "search_code": "github_search_code",
            "read_pull_request": "github_get_pull_request",
            "list_commits": "github_list_commits",
            "create_pull_request": "github_create_pull_request",
        },
        "auth_methods": ["oauth2", "pat"],
    },
    "google": {
        "title": "Google Workspace",
        "connector_type": "google",
        "capabilities": {
            "send_email": "google_send_email",
            "search_emails": "google_search_emails",
            "list_calendar_events": "google_list_calendar_events",
            "create_calendar_event": "google_create_calendar_event",
            "search_drive": "google_search_drive",
        },
        "auth_methods": ["oauth2"],
    },
    "notion": {
        "title": "Notion",
        "connector_type": "notion",
        "capabilities": {
            "search_pages": "notion_search_pages",
            "create_page": "notion_create_page",
            "query_database": "notion_query_database",
        },
        "auth_methods": ["oauth2", "internal_integration"],
    },
    "whatsapp": {
        "title": "WhatsApp",
        "connector_type": "whatsapp",
        "capabilities": {
            "send_message": "whatsapp_send_message",
            "send_text_message": "whatsapp_send_message",
            "draft_message": "whatsapp_send_message",
            "preview_message": "whatsapp_send_message",
            "check_session": "whatsapp_check_session",
            "check_status": "whatsapp_check_session",
            "get_status": "whatsapp_check_session",
        },
        "auth_methods": ["qr_session", "oauth2_meta_token"],
    },
}

# Synonyms for matching application names
APP_SYNONYMS: dict[str, str] = {
    "gmail": "google",
    "google_mail": "google",
    "gcalendar": "google",
    "google_calendar": "google",
    "gdrive": "google",
    "google_drive": "google",
    "spotify_music": "spotify",
    "slack_messenger": "slack",
    "gh": "github",
    "wa": "whatsapp",
    "whatsapp_web": "whatsapp",
    "whatsapp_desktop": "whatsapp",
    "whatsapp_messenger": "whatsapp",
}

# Known CLI tools and their primary capabilities
KNOWN_CLI_TOOLS: dict[str, list[str]] = {
    "git": ["commit", "push", "pull", "status", "diff", "branch", "clone", "checkout", "log"],
    "docker": ["run", "ps", "stop", "build", "images", "exec", "logs", "compose"],
    "ollama": ["run", "serve", "list", "pull", "show", "ps", "create"],
    "curl": ["get", "post", "fetch", "request", "download"],
    "ffmpeg": ["convert", "compress", "extract_audio", "trim", "record"],
    "code": ["open", "launch", "edit", "new_window"],
    "python": ["run", "execute", "eval", "script", "run_script", "c"],
}


class IntegrationResolver:
    """Production-grade Integration Resolution Engine.

    Evaluates application capabilities against all available integration surfaces
    and produces deterministic, verified resolution plans.
    """

    @classmethod
    def normalize_app_name(cls, app: str) -> str:
        """Normalize application identifier to canonical slug."""
        clean = re.sub(r"[\s-]+", "_", app.strip().lower())
        clean = re.sub(r"[^a-zA-Z0-9_]", "", clean)
        return APP_SYNONYMS.get(clean, clean)

    @classmethod
    def normalize_capability(cls, capability: str) -> str:
        """Normalize requested capability to canonical verb_noun form."""
        clean = re.sub(r"[\s-]+", "_", capability.strip().lower())
        return re.sub(r"[^a-zA-Z0-9_]", "", clean)

    @classmethod
    def _evaluate_risk(cls, action_name: str, description: str = "") -> tuple[str, bool]:
        """Assess semantic action risk and confirmation requirement."""
        from app.tools.schemas import RiskLevel

        rl = assess_action_risk(action_name, description)
        risk_str = rl.value.upper()
        conf_req = rl in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        return risk_str, conf_req

    @classmethod
    def resolve(
        cls,
        request: IntegrationResolutionRequest,
    ) -> IntegrationResolutionResult:
        """Execute full resolution evaluation across the 8-tier hierarchy."""
        start_time = time.perf_counter()
        app_raw = request.application
        app_norm = cls.normalize_app_name(app_raw)
        cap_norm = cls.normalize_capability(request.requested_capability)
        device = request.device or {}
        user_ctx = request.user_context or {}
        preferred = request.preferred_integration

        candidates: list[IntegrationCandidateModel] = []
        diagnostics: dict[str, Any] = {
            "normalized_app": app_norm,
            "normalized_capability": cap_norm,
            "device_platform": device.get("os_platform") or device.get("platform"),
            "evaluated_surfaces": [],
        }

        # ---------------------------------------------------------------------
        # Tier 1: Cloud / SaaS Connector & API Evaluation
        # ---------------------------------------------------------------------
        connector_candidate = cls._evaluate_cloud_connector(app_norm, cap_norm, user_ctx)
        if connector_candidate:
            candidates.append(connector_candidate)
            diagnostics["evaluated_surfaces"].append("cloud_connector")

        # ---------------------------------------------------------------------
        # Tier 2: MCP (Model Context Protocol) Tool Evaluation
        # ---------------------------------------------------------------------
        mcp_candidate = cls._evaluate_mcp_tool(app_norm, cap_norm, user_ctx)
        if mcp_candidate:
            candidates.append(mcp_candidate)
            diagnostics["evaluated_surfaces"].append("mcp_tool")

        # ---------------------------------------------------------------------
        # Tier 3: CLI Subprocess / Local REST Evaluation
        # ---------------------------------------------------------------------
        cli_candidate = cls._evaluate_cli_process(app_norm, cap_norm, device)
        if cli_candidate:
            candidates.append(cli_candidate)
            diagnostics["evaluated_surfaces"].append("cli_process")

        # ---------------------------------------------------------------------
        # Tier 4: System Process Lifecycle (Launch, Close, Focus) Evaluation
        # ---------------------------------------------------------------------
        process_candidate = cls._evaluate_system_launcher(app_raw, app_norm, cap_norm, device)
        if process_candidate:
            candidates.append(process_candidate)
            diagnostics["evaluated_surfaces"].append("system_launcher")

        # ---------------------------------------------------------------------
        # Tier 5: Native Desktop UI Automation Evaluation
        # ---------------------------------------------------------------------
        desktop_candidate = cls._evaluate_desktop_ui(app_raw, app_norm, cap_norm, device)
        if desktop_candidate:
            candidates.append(desktop_candidate)
            diagnostics["evaluated_surfaces"].append("desktop_ui_automation")

        # ---------------------------------------------------------------------
        # Tier 6: Mobile Device Bridge Evaluation
        # ---------------------------------------------------------------------
        mobile_candidate = cls._evaluate_mobile_bridge(app_raw, app_norm, cap_norm, device, preferred)
        if mobile_candidate:
            candidates.append(mobile_candidate)
            diagnostics["evaluated_surfaces"].append("mobile_bridge")

        # ---------------------------------------------------------------------
        # Tier 7: Browser Web Subsystem Evaluation
        # ---------------------------------------------------------------------
        browser_candidate = cls._evaluate_browser_automation(app_raw, app_norm, cap_norm)
        if browser_candidate:
            candidates.append(browser_candidate)
            diagnostics["evaluated_surfaces"].append("browser_automation")

        # ---------------------------------------------------------------------
        # Selection & Ranking Logic
        # ---------------------------------------------------------------------
        chosen: IntegrationCandidateModel | None = None

        # 1. Apply caller preference if specified and valid
        if preferred:
            for c in candidates:
                if c.integration == preferred:
                    chosen = c
                    diagnostics["override_applied"] = preferred
                    break

        # 2. Priority sort: Confidence descending, then tier hierarchy
        tier_priority: dict[IntegrationType, int] = {
            "cloud_connector": 10,
            "mcp_tool": 9,
            "cli_process": 8,
            "system_launcher": 7,
            "desktop_ui_automation": 6,
            "mobile_bridge": 5,
            "browser_automation": 4,
            "unsupported": 0,
        }

        candidates.sort(
            key=lambda c: (c.confidence, tier_priority.get(c.integration, 0)),
            reverse=True,
        )

        if not chosen and candidates:
            # Pick candidate with highest confidence
            top = candidates[0]
            if top.confidence >= 0.5:
                chosen = top

        duration = round((time.perf_counter() - start_time) * 1000, 2)

        # ---------------------------------------------------------------------
        # Outcome Generation (Zero Simulation)
        # ---------------------------------------------------------------------
        if chosen:
            log.info(
                "integration_resolver.resolved",
                application=app_raw,
                capability=cap_norm,
                chosen_integration=chosen.integration,
                confidence=chosen.confidence,
                execution_method=chosen.execution_method,
            )
            return IntegrationResolutionResult(
                success=True,
                application=app_raw,
                requested_capability=cap_norm,
                chosen_integration=chosen.integration,
                confidence=chosen.confidence,
                required_permission=chosen.required_permission,
                risk=chosen.risk,
                requires_confirmation=chosen.requires_confirmation,
                execution_method=chosen.execution_method,
                verification_method=chosen.verification_method,
                handler_target=chosen.handler_target,
                candidates=candidates,
                diagnostics=diagnostics,
                recommended_action=f"Execute via {chosen.execution_method} ({chosen.description})",
                duration_ms=duration,
            )

        # Fallback: Honest Unsupported
        remediation = (
            f"No integration route found for application '{app_raw}' with capability '{cap_norm}'. "
            "To enable: connect a cloud account in Connectors, install an MCP server, "
            "ensure the desktop app is installed, or verify local CLI tools."
        )
        log.warning(
            "integration_resolver.unsupported",
            application=app_raw,
            capability=cap_norm,
        )
        return IntegrationResolutionResult(
            success=False,
            application=app_raw,
            requested_capability=cap_norm,
            chosen_integration="unsupported",
            confidence=0.0,
            required_permission=f"app:{app_norm}:{cap_norm}",
            risk="LOW",
            requires_confirmation=False,
            execution_method="none",
            verification_method="none",
            handler_target=None,
            candidates=candidates,
            diagnostics=diagnostics,
            recommended_action=remediation,
            duration_ms=duration,
        )

    # -------------------------------------------------------------------------
    # Evaluation Sub-methods
    # -------------------------------------------------------------------------

    @classmethod
    def _evaluate_cloud_connector(
        cls, app_norm: str, cap_norm: str, user_ctx: dict[str, Any]
    ) -> IntegrationCandidateModel | None:
        """Evaluate Tier 1: Cloud Connector & API availability."""
        catalog_entry = KNOWN_CONNECTOR_CATALOG.get(app_norm)
        if not catalog_entry:
            return None

        # Check if requested capability maps to a connector action
        capabilities = catalog_entry["capabilities"]
        matched_action = None
        for cap_key, action_name in capabilities.items():
            if cap_key == cap_norm or cap_key in cap_norm or cap_norm in cap_key:
                matched_action = action_name
                break

        if not matched_action:
            return None

        # Check active user connectors / OAuth tokens in user_ctx
        active_connectors: list[str] = user_ctx.get("active_connectors", [])
        oauth_tokens: dict[str, Any] = user_ctx.get("oauth_tokens", {})
        has_auth = (
            app_norm in active_connectors
            or catalog_entry["connector_type"] in active_connectors
            or app_norm in oauth_tokens
        )

        # Check active environment credentials dynamically (Phase 15)
        if not has_auth:
            try:
                from app.device.mcp_connector_discovery import ConnectorDiscoveryEngine
                env_creds = ConnectorDiscoveryEngine.discover_environment_credentials()
                for ec in env_creds:
                    if ec.connector_type == catalog_entry["connector_type"] or ec.connector_type == app_norm:
                        has_auth = True
                        break
            except Exception:
                pass

        if app_norm == "whatsapp":
            # WhatsApp specific route and session readiness check under Zero Simulation
            try:
                from app.integrations.whatsapp.cloud_api_adapter import WhatsAppCloudApiAdapter
                cfg = WhatsAppCloudApiAdapter.get_config()
                if cfg.get("enabled") and cfg.get("access_token") and cfg.get("phone_number_id"):
                    has_auth = True
            except Exception:
                pass

            if user_ctx.get("whatsapp_authenticated"):
                has_auth = True

            confidence = 0.98 if has_auth else 0.60
            desc = (
                "Official WhatsApp Business Cloud API connector or active session verified."
                if has_auth
                else "WhatsApp connector catalog entry evaluated (Desktop/Web session unauthenticated or Cloud API credentials missing; requires authentication)."
            )
            verif_method: VerificationMethodType = "whatsapp_status_check"
            perm = "messaging:whatsapp:send" if "send" in cap_norm else f"app:whatsapp:{cap_norm}"
            risk, conf_req = cls._evaluate_risk(cap_norm)
            if "send" in cap_norm:
                risk = "HIGH"
                conf_req = True

            return IntegrationCandidateModel(
                integration="cloud_connector",
                confidence=confidence,
                execution_method="connector_api",
                verification_method=verif_method,
                required_permission=perm,
                risk=risk,
                requires_confirmation=conf_req,
                source="active_connector" if has_auth else "catalog_connector",
                description=desc,
                handler_target=matched_action,
                parameters={"connector_type": "whatsapp", "action": matched_action},
            )

        confidence = 0.98 if has_auth else 0.55
        desc = (
            f"Official {catalog_entry['title']} API connector available with active credentials."
            if has_auth
            else f"Official {catalog_entry['title']} connector available in catalog (requires authentication)."
        )

        perm = f"app:{app_norm}:{cap_norm}"
        risk, conf_req = cls._evaluate_risk(cap_norm)

        return IntegrationCandidateModel(
            integration="cloud_connector",
            confidence=confidence,
            execution_method="connector_api",
            verification_method="api_status_check",
            required_permission=perm,
            risk=risk,
            requires_confirmation=conf_req,
            source="active_connector" if has_auth else "catalog_connector",
            description=desc,
            handler_target=matched_action,
            parameters={"connector_type": catalog_entry["connector_type"], "action": matched_action},
        )

    @classmethod
    def _evaluate_mcp_tool(
        cls, app_norm: str, cap_norm: str, user_ctx: dict[str, Any]
    ) -> IntegrationCandidateModel | None:
        """Evaluate Tier 2: Model Context Protocol (MCP) tool availability."""
        registered_mcp_tools: list[dict[str, Any]] = user_ctx.get("mcp_tools", [])
        mcp_servers: list[str] = user_ctx.get("mcp_servers", [])

        # 1. Search in explicitly registered MCP tools
        for tool in registered_mcp_tools:
            name = str(tool.get("name", "")).lower()
            if app_norm in name and (cap_norm in name or not cap_norm):
                perm = f"mcp:{app_norm}:{name}"
                risk, conf_req = cls._evaluate_risk(name)
                return IntegrationCandidateModel(
                    integration="mcp_tool",
                    confidence=0.92,
                    execution_method="mcp_call",
                    verification_method="mcp_result_schema_validation",
                    required_permission=perm,
                    risk=risk,
                    requires_confirmation=conf_req,
                    source="mcp_tool_registry",
                    description=f"Active MCP tool '{name}' matches target application and capability.",
                    handler_target=tool.get("name"),
                    parameters={"tool_name": tool.get("name")},
                )

        # 2. Check if a dedicated MCP server is registered for this domain
        for srv in mcp_servers:
            srv_norm = srv.lower().replace("-", "_")
            if app_norm in srv_norm:
                perm = f"mcp:{app_norm}:{cap_norm}"
                risk, conf_req = cls._evaluate_risk(cap_norm)
                return IntegrationCandidateModel(
                    integration="mcp_tool",
                    confidence=0.88,
                    execution_method="mcp_call",
                    verification_method="mcp_result_schema_validation",
                    required_permission=perm,
                    risk=risk,
                    requires_confirmation=conf_req,
                    source="mcp_server",
                    description=f"Active MCP server '{srv}' is registered for application '{app_norm}'.",
                    handler_target=f"{srv}:{cap_norm}",
                    parameters={"server_name": srv, "capability": cap_norm},
                )

        # 3. Check dynamically bound discovery tools from Phase 15
        try:
            from app.device.mcp_connector_discovery import get_discovery_binding_registry

            for binding in get_discovery_binding_registry().list_bindings():
                if binding.get("source_type") == "mcp":
                    b_name = binding.get("name", "").lower()
                    if app_norm in b_name or b_name in app_norm:
                        for tool_id in binding.get("bound_tools", []):
                            t_lower = tool_id.lower()
                            if cap_norm in t_lower or not cap_norm:
                                risk, conf_req = cls._evaluate_risk(cap_norm or tool_id)
                                return IntegrationCandidateModel(
                                    integration="mcp_tool",
                                    confidence=0.94,
                                    execution_method="mcp_call",
                                    verification_method="mcp_result_schema_validation",
                                    required_permission=f"mcp:{app_norm}:{tool_id}",
                                    risk=risk,
                                    requires_confirmation=conf_req,
                                    source="dynamic_discovery_binding",
                                    description=f"Dynamically bound MCP tool '{tool_id}' available from {binding.get('name')}.",
                                    handler_target=tool_id,
                                    parameters={"tool_name": tool_id},
                                )
        except Exception:
            pass

        return None

    @classmethod
    def _evaluate_cli_process(
        cls, app_norm: str, cap_norm: str, device: dict[str, Any]
    ) -> IntegrationCandidateModel | None:
        """Evaluate Tier 3: CLI Subprocess / Local Binary Execution."""
        # 1. Check known CLI tools
        is_known = app_norm in KNOWN_CLI_TOOLS
        supported_subcmds = KNOWN_CLI_TOOLS.get(app_norm, [])

        # 2. Check executable in PATH
        resolved_bin = shutil.which(app_norm)
        if not resolved_bin and not is_known:
            return None

        # Match capability to subcommand
        matched_sub = None
        for sub in supported_subcmds:
            if sub in cap_norm or cap_norm in sub:
                matched_sub = sub
                break

        if not matched_sub and not resolved_bin:
            return None

        confidence = 0.88 if (resolved_bin and matched_sub) else (0.75 if resolved_bin else 0.60)
        perm = f"cli:{app_norm}:{matched_sub or cap_norm}"
        risk, conf_req = cls._evaluate_risk(matched_sub or cap_norm)

        return IntegrationCandidateModel(
            integration="cli_process",
            confidence=confidence,
            execution_method="cli_exec",
            verification_method="process_exit_code_and_output",
            required_permission=perm,
            risk=risk,
            requires_confirmation=conf_req,
            source="cli_binary",
            description=f"Local CLI binary '{app_norm}' found in PATH ({resolved_bin or 'PATH binary'}).",
            handler_target=resolved_bin or app_norm,
            parameters={"binary": app_norm, "subcommand": matched_sub, "executable_path": resolved_bin},
        )

    @classmethod
    def _evaluate_system_launcher(
        cls, app_raw: str, app_norm: str, cap_norm: str, device: dict[str, Any]
    ) -> IntegrationCandidateModel | None:
        """Evaluate Tier 5: System Process Controller (launch, terminate, focus)."""
        platform_name = str(device.get("os_platform") or device.get("platform") or "").lower()
        device_type = str(device.get("device_type", "")).lower()
        if platform_name in ("android", "ios") or device_type == "mobile":
            return None

        launch_verbs = {"launch", "open", "start", "run"}
        terminate_verbs = {"close", "terminate", "kill", "stop", "exit"}
        focus_verbs = {"focus", "bring_to_front", "activate"}

        matched_method = None
        if any(v in cap_norm for v in launch_verbs):
            matched_method = "launch"
        elif any(v in cap_norm for v in terminate_verbs):
            matched_method = "terminate"
        elif any(v in cap_norm for v in focus_verbs):
            matched_method = "focus"

        if not matched_method:
            return None

        # Check installed applications list if provided in device
        installed_apps: list[str] = [str(a).lower() for a in device.get("installed_apps", [])]
        is_installed = any(app_norm in a or a in app_norm for a in installed_apps) if installed_apps else True

        confidence = 0.92 if is_installed else 0.70
        risk, conf_req = cls._evaluate_risk(matched_method)
        perm = f"app:{app_norm}:{matched_method}"

        return IntegrationCandidateModel(
            integration="system_launcher",
            confidence=confidence,
            execution_method="process_launch",
            verification_method="process_pid_and_window_presence",
            required_permission=perm,
            risk=risk,
            requires_confirmation=conf_req,
            source="process_controller",
            description=f"Native OS process controller '{matched_method}' operation for application '{app_raw}'.",
            handler_target=app_raw,
            parameters={"target": app_raw, "action": matched_method},
        )

    @classmethod
    def _evaluate_desktop_ui(
        cls, app_raw: str, app_norm: str, cap_norm: str, device: dict[str, Any]
    ) -> IntegrationCandidateModel | None:
        """Evaluate Tier 4: Native Desktop UI Automation."""
        platform_name = str(device.get("os_platform") or device.get("platform") or "").lower()
        # Only applicable on desktop OS
        if platform_name in ("android", "ios"):
            return None

        # Check if window is currently reported running or active in device telemetry
        active_windows: list[str] = [str(w).lower() for w in device.get("open_windows", [])]
        foreground_window = str(device.get("foreground_window", "")).lower()

        window_found = any(app_norm in w for w in active_windows) or (app_norm in foreground_window)

        # UI actions (click, type, read, inspect, hotkey, scroll, screenshot)
        ui_verbs = {"click", "type", "input", "press", "hotkey", "scroll", "read", "inspect", "select", "screenshot"}
        is_ui_action = any(v in cap_norm for v in ui_verbs)

        if not is_ui_action and not window_found:
            return None

        confidence = 0.85 if window_found else 0.65
        perm = "device:local:desktop_automation"
        risk, conf_req = cls._evaluate_risk(cap_norm)

        return IntegrationCandidateModel(
            integration="desktop_ui_automation",
            confidence=confidence,
            execution_method="desktop_ui",
            verification_method="accessibility_tree_match" if is_ui_action else "window_state_probe",
            required_permission=perm,
            risk=risk,
            requires_confirmation=conf_req,
            source="desktop_window_state" if window_found else "desktop_automation_engine",
            description=f"Native desktop UI automation via accessibility hierarchy for '{app_raw}'.",
            handler_target=app_raw,
            parameters={"window_target": app_raw, "capability": cap_norm},
        )

    @classmethod
    def _evaluate_mobile_bridge(
        cls,
        app_raw: str,
        app_norm: str,
        cap_norm: str,
        device: dict[str, Any],
        preferred: str | None = None,
    ) -> IntegrationCandidateModel | None:
        """Evaluate Tier 6: Mobile Device Bridge (Android & iOS)."""
        platform_name = str(device.get("os_platform") or device.get("platform") or "").lower()
        device_type = str(device.get("device_type", "")).lower()

        is_mobile_env = platform_name in ("android", "ios") or device_type == "mobile"
        is_mobile_preferred = preferred == "mobile_bridge"
        is_package_or_bundle = bool(re.match(r"^[a-zA-Z][a-zA-Z0-9_\-]*(\.[a-zA-Z0-9_\-]+)+$", app_raw))
        is_mobile_cap = any(
            c in cap_norm
            for c in (
                "intent",
                "deep_link",
                "deeplink",
                "swipe",
                "companion",
                "inspect",
                "universal_link",
                "url_scheme",
                "shortcut",
                "app_intent",
                "share_sheet",
                "share",
            )
        )

        if not (is_mobile_env or is_mobile_preferred or (is_package_or_bundle and is_mobile_cap)):
            return None

        perm = f"device:{device.get('device_id', 'mobile')}:mobile_automation"
        risk, conf_req = cls._evaluate_risk(cap_norm)
        is_ios = platform_name == "ios" or any(k in cap_norm for k in ("shortcut", "universal_link", "url_scheme", "share_sheet"))
        display_platform = "iOS" if is_ios else (platform_name.capitalize() if platform_name else "Android")

        # Select canonical verification method
        verif_method: VerificationMethodType
        if is_ios:
            if "shortcut" in cap_norm:
                verif_method = "ios_shortcut_probe"
            elif "universal_link" in cap_norm or "url_scheme" in cap_norm or "scheme" in cap_norm or "link" in cap_norm:
                verif_method = "ios_link_or_scheme_probe"
            elif "app_intent" in cap_norm or "intent" in cap_norm:
                verif_method = "ios_app_intent_probe"
            elif "share" in cap_norm:
                verif_method = "ios_share_sheet_probe"
            else:
                verif_method = "ios_companion_telemetry_probe"
        else:
            verif_method = "mobile_ui_dump_match"

        confidence = 0.85
        resolved_params: dict[str, Any] = {
            "package_name": app_raw,
            "action": cap_norm,
            "platform": "ios" if is_ios else "android",
        }

        # Query MobileIntegrationResolver for rich app and capability metadata
        try:
            from app.device.mobile_registry import get_mobile_integration_resolver
            from app.device.schemas import MobileCapabilityResolutionRequest

            mobile_req = MobileCapabilityResolutionRequest(
                package_or_bundle_id=app_raw,
                requested_capability=cap_norm,
                platform="ios" if is_ios else ("android" if platform_name == "android" else None),
                device_id=device.get("device_id"),
                parameters={"target": app_raw, "action": cap_norm},
                preferred_integration=preferred,
            )
            mobile_res = get_mobile_integration_resolver().resolve_capability(mobile_req)
            if mobile_res.success and mobile_res.confidence > 0:
                confidence = mobile_res.confidence
                if mobile_res.verification_strategy and mobile_res.verification_strategy != "none":
                    verif_method = cast(VerificationMethodType, mobile_res.verification_strategy)
                if mobile_res.required_permission:
                    resolved_params["app_permission"] = mobile_res.required_permission
                if mobile_res.risk_level:
                    risk = mobile_res.risk_level
                conf_req = mobile_res.requires_confirmation
                resolved_params = {**resolved_params, **mobile_res.resolved_parameters}
                if mobile_res.app:
                    resolved_params["package_or_bundle_id"] = mobile_res.app.package_or_bundle_id
                    resolved_params["app_name"] = mobile_res.app.name
        except Exception as e:
            log.debug("mobile_integration_resolver_query_failed", error=str(e))

        return IntegrationCandidateModel(
            integration="mobile_bridge",
            confidence=confidence,
            execution_method="mobile_ui",
            verification_method=verif_method,
            required_permission=perm,
            risk=risk,
            requires_confirmation=conf_req,
            source="mobile_device_bridge",
            description=f"Mobile device automation bridge for {display_platform} target '{app_raw}'.",
            handler_target=app_raw,
            parameters=resolved_params,
        )

    @classmethod
    def _evaluate_browser_automation(
        cls, app_raw: str, app_norm: str, cap_norm: str
    ) -> IntegrationCandidateModel | None:
        """Evaluate Tier 7: Web Browser Automation."""
        # Detect web domains or explicitly web-based targets
        is_web = (
            "http://" in app_raw
            or "https://" in app_raw
            or ".com" in app_raw
            or ".io" in app_raw
            or ".app" in app_raw
            or app_norm in ("web_browser", "chrome", "firefox", "edge", "safari")
        )

        if not is_web:
            return None

        if cap_norm in ("inspect_dom", "inspect", "navigate", "read", "view", "screenshot"):
            perm = "browser:read"
            risk = "LOW"
            conf_req = False
        else:
            perm = "browser:web_session:execute"
            risk, conf_req = cls._evaluate_risk(cap_norm)

        return IntegrationCandidateModel(
            integration="browser_automation",
            confidence=0.75,
            execution_method="browser_session",
            verification_method="dom_element_state_probe",
            required_permission=perm,
            risk=risk,
            requires_confirmation=conf_req,
            source="browser_subsystem",
            description=f"Web browser automation subsystem for target '{app_raw}'.",
            handler_target=app_raw,
            parameters={"target_url": app_raw, "action": cap_norm},
        )
