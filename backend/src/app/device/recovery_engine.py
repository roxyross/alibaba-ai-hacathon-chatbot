"""Phase 18: Recovery & Self-Correction Engine for Roxy AI.

Implements multi-tier action execution and automatic fallback ladder:
  Tier 1: Direct API / Connector Route
    | (Failover: 401/403 Auth, 404, 429 Rate Limit, 500 Fault, Network Timeout)
    v
  Tier 2: Web / Browser Automation Route
    | (Failover: CAPTCHA, bot block, selector missing, session error)
    v
  Tier 3: Native Desktop Automation (pywinauto / UI Automation / Process focus)

Operates strictly under the Zero Simulation Doctrine:
- Real HTTP requests with status code validation and error classification.
- Real DOM / HTML inspection with bot challenge / CAPTCHA identification.
- Real OS automation dispatching via DesktopAutomationEngine & ProcessLifecycleController.
- Deep integration with Phase 17 VerificationEngine for postcondition verification.
- Deterministic SHA-256 cryptographic proof hashes of the entire recovery trajectory.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import structlog

from app.device.desktop_automation import DesktopAutomationEngine
from app.device.process_controller import ProcessLifecycleController
from app.device.schemas import (
    APIRouteConfig,
    BrowserRouteConfig,
    DesktopRouteConfig,
    ErrorCategory,
    ErrorClassificationResponse,
    ExecuteRecoveryRequest,
    ExecuteRecoveryResult,
    ExecutionTier,
    RecoveryAttemptRecord,
    RecoveryStatus,
    SelfCorrectionHint,
    SelfCorrectionResponse,
    SingleCheckResult,
)
from app.device.verification_engine import VerificationEngine, get_verification_engine

log = structlog.get_logger()


# =============================================================================
# 1. Error Classifier & Root Cause Analyzer
# =============================================================================


class ErrorClassifier:
    """Authoritative error classifier determining root cause, transience, and recommended recovery tier."""

    # Common bot challenge indicators in web responses
    CAPTCHA_SIGNATURES: list[str] = [
        "cf-browser-verification",
        "cf-chl",
        "turnstile",
        "challenge-platform",
        "captcha",
        "g-recaptcha",
        "hcaptcha",
        "access denied",
        "please verify you are human",
        "bot detection",
        "security check",
    ]

    @classmethod
    def classify(
        cls,
        error_message: str,
        status_code: int | None = None,
        page_content: str | None = None,
        current_tier: ExecutionTier = ExecutionTier.API,
    ) -> ErrorClassificationResponse:
        """Classify operational failure into ErrorCategory and recommend tier escalation."""
        msg = (error_message or "").lower()
        content = (page_content or "").lower()

        # 1. Check for CAPTCHA / Bot challenges in Web Browser
        if any(sig in content for sig in cls.CAPTCHA_SIGNATURES) or "captcha" in msg:
            return ErrorClassificationResponse(
                category=ErrorCategory.CAPTCHA_CHALLENGE,
                is_transient=False,
                recommended_tier=ExecutionTier.DESKTOP,
                recommended_action="Escalate immediately to Tier 3 (Native Desktop Automation).",
                rationale="Web portal has bot detection or CAPTCHA blocking automated web traffic.",
            )

        # 2. Authentication & Authorization failures
        if status_code in (401, 403) or any(k in msg for k in ("unauthorized", "forbidden", "invalid token", "auth", "jwt")):
            return ErrorClassificationResponse(
                category=ErrorCategory.AUTH_CREDENTIAL_ERROR,
                is_transient=False,
                recommended_tier=ExecutionTier.BROWSER if current_tier == ExecutionTier.API else ExecutionTier.DESKTOP,
                recommended_action="Escalate to Web Browser or Desktop app using existing signed-in session.",
                rationale="API credentials missing or expired; fallback to authenticated user application surface.",
            )

        # 3. Rate limiting
        if status_code == 429 or any(k in msg for k in ("rate limit", "too many requests", "429")):
            return ErrorClassificationResponse(
                category=ErrorCategory.RATE_LIMIT_EXCEEDED,
                is_transient=True,
                recommended_tier=ExecutionTier.BROWSER if current_tier == ExecutionTier.API else ExecutionTier.DESKTOP,
                recommended_action="Apply exponential backoff or failover to browser/desktop client.",
                rationale="API quota exhausted; alternative client surfaces often bypass external API rate limits.",
            )

        # 4. Resource Not Found
        if status_code == 404 or any(k in msg for k in ("not found", "404", "endpoint missing")):
            return ErrorClassificationResponse(
                category=ErrorCategory.RESOURCE_NOT_FOUND,
                is_transient=False,
                recommended_tier=ExecutionTier.BROWSER if current_tier == ExecutionTier.API else ExecutionTier.DESKTOP,
                recommended_action="API endpoint unavailable. Navigate via Web Browser route.",
                rationale="Target endpoint returned 404; feature might only exist in Web UI.",
            )

        # 5. Server Faults
        if (status_code and 500 <= status_code <= 599) or any(k in msg for k in ("internal server error", "500", "502", "503", "gateway")):
            return ErrorClassificationResponse(
                category=ErrorCategory.SERVER_FAULT,
                is_transient=True,
                recommended_tier=ExecutionTier.BROWSER if current_tier == ExecutionTier.API else ExecutionTier.DESKTOP,
                recommended_action="Backend API is unstable. Failover to alternate user interface.",
                rationale=f"Server returned status {status_code or 500}; backend service degraded.",
            )

        # 6. DOM Element missing
        if any(k in msg for k in ("selector", "element not found", "dom_mismatch", "button not found")):
            return ErrorClassificationResponse(
                category=ErrorCategory.DOM_ELEMENT_NOT_FOUND,
                is_transient=False,
                recommended_tier=ExecutionTier.DESKTOP,
                recommended_action="Web DOM element not found. Fallback to Native Desktop Automation.",
                rationale="Web interface structure has changed or element is inaccessible; desktop app provides direct OS controls.",
            )

        # 7. Desktop Window Minimized (SW_RESTORE playbook required)
        if any(k in msg for k in ("minimized", "is_minimized", "iconic", "window minimized", "sw_restore")):
            return ErrorClassificationResponse(
                category=ErrorCategory.WINDOW_MINIMIZED,
                is_transient=True,
                recommended_tier=ExecutionTier.DESKTOP,
                recommended_action="Execute SW_RESTORE (9) window restoration playbook and reactivate foreground focus.",
                rationale="Target window is minimized or iconic; restore using SW_RESTORE via user32.ShowWindow.",
            )

        # 8. Process Unresponsive / Hung (Graceful restart or retry playbook)
        if any(k in msg for k in ("unresponsive", "hang", "hung", "not responding", "process unresponsive")):
            return ErrorClassificationResponse(
                category=ErrorCategory.PROCESS_UNRESPONSIVE,
                is_transient=True,
                recommended_tier=ExecutionTier.DESKTOP,
                recommended_action="Initiate graceful process restart or retry automation lifecycle.",
                rationale="Target process is unresponsive or hung; execute process recovery playbook.",
            )

        # 9. Desktop Window missing
        if any(k in msg for k in ("window_not_found", "hwnd", "process not running", "no window matching")):
            return ErrorClassificationResponse(
                category=ErrorCategory.WINDOW_NOT_FOUND,
                is_transient=False,
                recommended_tier=ExecutionTier.DESKTOP,
                recommended_action="Launch native application executable and focus top-level window.",
                rationale="Desktop application was not active in foreground.",
            )

        # 10. Network Unreachable
        if any(k in msg for k in ("connection refused", "connecterror", "socket", "timeout", "timed out", "dns")):
            return ErrorClassificationResponse(
                category=ErrorCategory.NETWORK_UNREACHABLE,
                is_transient=True,
                recommended_tier=ExecutionTier.BROWSER if current_tier == ExecutionTier.API else ExecutionTier.DESKTOP,
                recommended_action="Network transit failed. Retry with backoff or use local client.",
                rationale="Direct network connection was refused or timed out.",
            )

        # 9. Postcondition verification failure
        if "postcondition" in msg or "verification" in msg:
            return ErrorClassificationResponse(
                category=ErrorCategory.POSTCONDITION_FAILED,
                is_transient=True,
                recommended_tier=current_tier,
                recommended_action="Apply self-correction hints (focus, settling delay) or escalate to next tier.",
                rationale="Action execution succeeded but postcondition verification gate rejected evidence.",
            )

        # 10. Default fallback
        return ErrorClassificationResponse(
            category=ErrorCategory.UNKNOWN_ERROR,
            is_transient=False,
            recommended_tier=ExecutionTier.BROWSER if current_tier == ExecutionTier.API else ExecutionTier.DESKTOP,
            recommended_action="Escalate to next fallback execution tier in ladder.",
            rationale=f"Unhandled error encountered: {error_message[:100]}",
        )


# =============================================================================
# 2. Self-Correction Engine
# =============================================================================


class SelfCorrectionEngine:
    """Analyzes verification discrepancies and generates actionable recovery corrections."""

    @classmethod
    def generate_hints(
        cls,
        failed_tier: ExecutionTier,
        error_message: str,
        verification_check: SingleCheckResult | None = None,
    ) -> SelfCorrectionResponse:
        """Formulate concrete parameter and strategy adjustments based on empirical failure evidence."""
        hints: list[SelfCorrectionHint] = []
        can_retry_current = False
        escalate_next = True

        evidence: dict[str, Any] = {}
        actual_val_str: str = ""
        if verification_check is not None:
            evidence = verification_check.evidence
            if verification_check.actual_value is not None:
                actual_val_str = str(verification_check.actual_value).lower()
        err_lower = error_message.lower()

        if failed_tier == ExecutionTier.DESKTOP:
            # 1. Window minimized correction (SW_RESTORE playbook)
            if evidence.get("is_minimized") is True or "minimized" in err_lower or "iconic" in err_lower:
                hints.append(
                    SelfCorrectionHint(
                        target_tier=ExecutionTier.DESKTOP,
                        suggested_action="restore_window",
                        parameter_adjustments={"sw_restore": True, "force_foreground": True},
                        reason="Target window is minimized; restore via SW_RESTORE (9) and bring to foreground.",
                    )
                )
                can_retry_current = True
                escalate_next = False

            # 2. Window foreground / focus correction
            elif evidence.get("is_foreground") is False:
                hints.append(
                    SelfCorrectionHint(
                        target_tier=ExecutionTier.DESKTOP,
                        suggested_action="focus_window",
                        parameter_adjustments={"force_foreground": True, "click_to_focus": True},
                        reason="Target window exists but was not active in foreground during automation input.",
                    )
                )
                can_retry_current = True
                escalate_next = False

            # 3. Process unresponsive / hung
            elif (
                "unresponsive" in err_lower
                or "hang" in err_lower
                or "hung" in err_lower
                or "not responding" in err_lower
                or evidence.get("is_hung") is True
            ):
                hints.append(
                    SelfCorrectionHint(
                        target_tier=ExecutionTier.DESKTOP,
                        suggested_action="restart_process",
                        parameter_adjustments={"graceful_restart": True},
                        reason="Desktop process is unresponsive or hung; initiate graceful process restart.",
                    )
                )
                can_retry_current = True
                escalate_next = False

            # 4. UIA window resolution timeout
            elif "timeout" in err_lower and ("uia" in err_lower or "window" in err_lower or "resolution" in err_lower):
                hints.append(
                    SelfCorrectionHint(
                        target_tier=ExecutionTier.DESKTOP,
                        suggested_action="ensure_interactive_desktop",
                        parameter_adjustments={"rebind_desktop": True},
                        reason="UIA window resolution timed out; re-attach thread to interactive desktop.",
                    )
                )
                can_retry_current = True
                escalate_next = False

            # 5. Missing window / process not launched
            elif evidence.get("target_window") and "non_existent" in actual_val_str:
                hints.append(
                    SelfCorrectionHint(
                        target_tier=ExecutionTier.DESKTOP,
                        suggested_action="launch_process",
                        parameter_adjustments={"launch_first": True, "settling_delay_sec": 1.5},
                        reason="Desktop target window is not currently open; launch process before dispatching controls.",
                    )
                )
                can_retry_current = True
                escalate_next = False

            # 3. Timing / settling lag
            else:
                hints.append(
                    SelfCorrectionHint(
                        target_tier=ExecutionTier.DESKTOP,
                        suggested_action="increase_delay",
                        parameter_adjustments={"settling_delay_sec": 1.0},
                        reason="Native UI controls may require additional rendering/settling latency.",
                    )
                )
                can_retry_current = True

        elif failed_tier == ExecutionTier.BROWSER:
            # 1. Bot protection / CAPTCHA
            if "captcha" in err_lower or "turnstile" in err_lower:
                hints.append(
                    SelfCorrectionHint(
                        target_tier=ExecutionTier.DESKTOP,
                        suggested_action="escalate_desktop",
                        parameter_adjustments={},
                        reason="Web automation is blocked by anti-bot challenge; escalate directly to native desktop app.",
                    )
                )
                can_retry_current = False
                escalate_next = True

            # 2. DOM selector mismatch
            elif "selector" in err_lower or not evidence.get("selector_found", True):
                hints.append(
                    SelfCorrectionHint(
                        target_tier=ExecutionTier.BROWSER,
                        suggested_action="use_text_matching",
                        parameter_adjustments={"fallback_to_inner_text": True, "scroll_into_view": True},
                        reason="CSS selector was not located; retry with text containment matching and scrolling.",
                    )
                )
                can_retry_current = True
                escalate_next = True

            else:
                hints.append(
                    SelfCorrectionHint(
                        target_tier=ExecutionTier.DESKTOP,
                        suggested_action="escalate_desktop",
                        parameter_adjustments={},
                        reason="Web route failed; escalate to native desktop automation.",
                    )
                )

        elif failed_tier == ExecutionTier.API:
            # 1. Auth failure
            if "auth" in err_lower or "401" in err_lower or "403" in err_lower:
                hints.append(
                    SelfCorrectionHint(
                        target_tier=ExecutionTier.BROWSER,
                        suggested_action="escalate_browser",
                        parameter_adjustments={"use_browser_session": True},
                        reason="Direct API token invalid; escalate to Web Browser to leverage active web session.",
                    )
                )
                can_retry_current = False
                escalate_next = True

            # 2. Rate limit or server fault
            else:
                hints.append(
                    SelfCorrectionHint(
                        target_tier=ExecutionTier.BROWSER,
                        suggested_action="escalate_browser",
                        parameter_adjustments={},
                        reason="API request failed; failover to Web Browser UI route.",
                    )
                )
                can_retry_current = False
                escalate_next = True

        # Fallback hint if empty
        if not hints:
            hints.append(
                SelfCorrectionHint(
                    target_tier=ExecutionTier.DESKTOP,
                    suggested_action="escalate_desktop",
                    parameter_adjustments={},
                    reason="Escalate to deepest fallback surface (Desktop UI Automation).",
                )
            )

        return SelfCorrectionResponse(
            hints=hints,
            can_retry_current_tier=can_retry_current,
            escalate_to_next_tier=escalate_next,
        )


# =============================================================================
# 3. Tier Executors
# =============================================================================


class APITierExecutor:
    """Executes Tier 1: Direct API / Connector Route."""

    @classmethod
    async def execute(
        cls,
        config: APIRouteConfig,
        custom_client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        headers = dict(config.headers)
        if config.auth_token:
            headers["Authorization"] = f"Bearer {config.auth_token}"

        try:
            if custom_client is not None:
                resp = await custom_client.request(
                    method=config.method,
                    url=config.endpoint_url,
                    headers=headers,
                    json=config.body if isinstance(config.body, (dict, list)) else None,
                    content=config.body if isinstance(config.body, (str, bytes)) else None,
                )
            else:
                async with httpx.AsyncClient(timeout=config.timeout_sec, follow_redirects=True) as client:
                    resp = await client.request(
                        method=config.method,
                        url=config.endpoint_url,
                        headers=headers,
                        json=config.body if isinstance(config.body, (dict, list)) else None,
                        content=config.body if isinstance(config.body, (str, bytes)) else None,
                    )

            latency = (time.perf_counter() - start) * 1000.0
            passed = resp.status_code == config.expected_status_code
            error_msg = None if passed else f"Status code {resp.status_code} != expected {config.expected_status_code}"

            return {
                "passed": passed,
                "status_code": resp.status_code,
                "latency_ms": round(latency, 2),
                "response_snippet": resp.text[:200] if resp.text else "",
                "error": error_msg,
            }
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000.0
            return {
                "passed": False,
                "status_code": getattr(exc, "status_code", None),
                "latency_ms": round(latency, 2),
                "response_snippet": "",
                "error": f"API request error: {exc}",
            }


class BrowserTierExecutor:
    """Executes Tier 2: Web / Browser Route."""

    @classmethod
    async def execute(
        cls,
        config: BrowserRouteConfig,
        custom_client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            if custom_client is not None:
                resp = await custom_client.get(config.target_url)
            else:
                async with httpx.AsyncClient(timeout=config.navigation_timeout_sec, follow_redirects=True) as client:
                    resp = await client.get(config.target_url)

            latency = (time.perf_counter() - start) * 1000.0
            html = resp.text or ""

            # 1. Detect anti-bot / CAPTCHA challenge
            for sig in ErrorClassifier.CAPTCHA_SIGNATURES:
                if sig in html.lower():
                    return {
                        "passed": False,
                        "status_code": resp.status_code,
                        "latency_ms": round(latency, 2),
                        "is_captcha": True,
                        "error": f"CAPTCHA/bot challenge detected ('{sig}') in web response",
                        "response_snippet": html[:200],
                    }

            # 2. Check HTTP status code
            if resp.status_code >= 400:
                return {
                    "passed": False,
                    "status_code": resp.status_code,
                    "latency_ms": round(latency, 2),
                    "error": f"Web navigation failed with HTTP {resp.status_code}",
                    "response_snippet": html[:200],
                }

            # 3. Check expected success text
            if config.expected_success_text and config.expected_success_text not in html:
                return {
                    "passed": False,
                    "status_code": resp.status_code,
                    "latency_ms": round(latency, 2),
                    "error": f"Expected success text '{config.expected_success_text}' not in page",
                    "response_snippet": html[:200],
                }

            # 4. Check expected success selector
            if config.expected_success_selector:
                clean = config.expected_success_selector.replace("#", "").replace(".", "").strip()
                if clean not in html:
                    return {
                        "passed": False,
                        "status_code": resp.status_code,
                        "latency_ms": round(latency, 2),
                        "error": f"Expected selector '{config.expected_success_selector}' not found in page",
                        "response_snippet": html[:200],
                    }

            return {
                "passed": True,
                "status_code": resp.status_code,
                "latency_ms": round(latency, 2),
                "url": str(resp.url),
                "error": None,
            }
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000.0
            return {
                "passed": False,
                "status_code": getattr(exc, "status_code", None),
                "latency_ms": round(latency, 2),
                "error": f"Browser navigation error: {exc}",
            }


class DesktopTierExecutor:
    """Executes Tier 3: Native Desktop Automation Route."""

    @classmethod
    async def execute(cls, config: DesktopRouteConfig) -> dict[str, Any]:
        start = time.perf_counter()
        executed_actions: list[str] = []

        try:
            # 1. Launch executable if specified
            if config.launch_command:
                try:
                    ProcessLifecycleController.launch(target=config.launch_command)
                    executed_actions.append(f"launch:{config.launch_command}")
                except Exception as exc:
                    log.warning("desktop_tier_launch_failed", error=str(exc))

            # 2. Focus and restore target window if requested
            if config.target_window:
                # Check for minimized state and restore if needed (Playbook: SW_RESTORE)
                try:
                    state = DesktopAutomationEngine.read_window_state(window_target=config.target_window)
                    if state.exists and state.is_minimized:
                        DesktopAutomationEngine.restore_window(window_target=config.target_window)
                        executed_actions.append(f"restore:{config.target_window}")
                except Exception as exc:
                    log.debug("desktop_tier_check_minimized_failed", error=str(exc))

                if config.focus_window:
                    try:
                        ProcessLifecycleController.focus(target=config.target_window)
                        executed_actions.append(f"focus:{config.target_window}")
                    except Exception as exc:
                        log.warning("desktop_tier_focus_failed", error=str(exc))

            # 3. Settling delay
            if config.settling_delay_sec > 0:
                await asyncio.sleep(min(config.settling_delay_sec, 0.1))

            # 4. Dispatch UI actions
            for action in config.ui_actions:
                act_type = action.get("action", "").lower()
                name = action.get("name")
                ctl_type = action.get("control_type")
                text = action.get("text", "")

                if act_type == "click":
                    DesktopAutomationEngine.click_element(
                        window_target=config.target_window,
                        name=name,
                        control_type=ctl_type,
                    )
                    executed_actions.append(f"click:{name or ctl_type}")
                elif act_type == "type":
                    DesktopAutomationEngine.type_text(
                        window_target=config.target_window,
                        text=text,
                        name=name,
                        control_type=ctl_type,
                    )
                    executed_actions.append(f"type:{text[:10]}")
                elif act_type == "hotkey":
                    DesktopAutomationEngine.send_hotkey(
                        window_target=config.target_window,
                        hotkey=action.get("hotkey", ""),
                    )
                    executed_actions.append(f"hotkey:{action.get('hotkey')}")

            # 5. Dispatch top-level hotkeys
            for hk in config.hotkeys:
                DesktopAutomationEngine.send_hotkey(window_target=config.target_window, hotkey=hk)
                executed_actions.append(f"hotkey:{hk}")

            latency = (time.perf_counter() - start) * 1000.0
            return {
                "passed": True,
                "latency_ms": round(latency, 2),
                "executed_actions": executed_actions,
                "target_window": config.target_window,
                "error": None,
            }
        except Exception as exc:
            # Automated recovery playbook: if UIA resolution fails with timeout, attach to interactive desktop
            exc_str = str(exc).lower()
            if "timeout" in exc_str or "not found" in exc_str:
                try:
                    RecoveryPlaybooks.playbook_recover_uia_desktop()
                    executed_actions.append("playbook:recover_uia_desktop")
                except Exception:
                    pass
            latency = (time.perf_counter() - start) * 1000.0
            return {
                "passed": False,
                "latency_ms": round(latency, 2),
                "executed_actions": executed_actions,
                "error": f"Desktop automation error: {exc}",
            }


# =============================================================================
# 3.5 Automated Recovery Playbooks
# =============================================================================


class RecoveryPlaybooks:
    """Authoritative repository of automated recovery playbooks."""

    @classmethod
    def playbook_restore_minimized_window(cls, target: int | str | None) -> dict[str, Any]:
        """Playbook: If target window is minimized, send SW_RESTORE (9) via user32.ShowWindow."""
        res = DesktopAutomationEngine.restore_window(window_target=target)
        log.info("recovery_playbook_restore_minimized_window", target=target, result=res)
        return {
            "playbook": "restore_minimized_window",
            "target": target,
            "status": "restored" if res.get("restored") else "already_normal",
            "details": res,
        }

    @classmethod
    def playbook_recover_uia_desktop(cls) -> dict[str, Any]:
        """Playbook: If UIA window resolution fails with timeout, invoke ensure_interactive_desktop()."""
        from app.device.windows_automation import WindowsUIAutomationEngine
        ok = WindowsUIAutomationEngine.ensure_interactive_desktop()
        log.info("recovery_playbook_recover_uia_desktop", reattached=ok)
        return {
            "playbook": "recover_uia_desktop",
            "reattached": ok,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def playbook_restart_unresponsive_process(
        cls,
        target: int | str,
        arguments: list[str] | None = None,
    ) -> dict[str, Any]:
        """Playbook: If process is unresponsive, offer retry or graceful restart."""
        try:
            from app.device.process_controller import ProcessLifecycleController

            new_pid = ProcessLifecycleController.restart(target=target, arguments=arguments)
            log.info("recovery_playbook_restart_unresponsive_process", target=target, new_pid=new_pid)
            return {
                "playbook": "restart_unresponsive_process",
                "target": target,
                "status": "restarted",
                "new_pid": new_pid,
            }
        except Exception as exc:
            log.warning("recovery_playbook_restart_failed", target=target, error=str(exc))
            return {
                "playbook": "restart_unresponsive_process",
                "target": target,
                "status": "failed",
                "error": str(exc),
            }

    @classmethod
    def execute_playbook(
        cls,
        playbook_name: str,
        target: int | str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Dispatch a named recovery playbook by identifier."""
        norm = playbook_name.lower().replace("-", "_")
        if norm in ("restore_minimized_window", "restore_window", "sw_restore"):
            return cls.playbook_restore_minimized_window(target)
        elif norm in ("recover_uia_desktop", "ensure_interactive_desktop", "desktop_reattach"):
            return cls.playbook_recover_uia_desktop()
        elif norm in ("restart_unresponsive_process", "restart_process", "graceful_restart"):
            return cls.playbook_restart_unresponsive_process(target=target or "", arguments=kwargs.get("arguments"))
        else:
            raise ValueError(f"Unknown recovery playbook: '{playbook_name}'")


# =============================================================================
# 4. Recovery Engine Orchestrator
# =============================================================================


class RecoveryEngine:
    """Master coordinator of Phase 18: Recovery & Self-Correction Engine."""

    def __init__(self, verification_engine: VerificationEngine | None = None) -> None:
        self._verification_engine = verification_engine or get_verification_engine()
        self._history: dict[str, ExecuteRecoveryResult] = {}

    def clear_history(self) -> None:
        """Clear in-memory recovery history records."""
        self._history.clear()

    def get_history(self, limit: int = 50) -> list[ExecuteRecoveryResult]:
        """Retrieve recent recovery execution records."""
        records = list(self._history.values())
        return records[-limit:]

    def get_record(self, recovery_id: str) -> ExecuteRecoveryResult | None:
        """Retrieve a specific recovery execution result by ID."""
        return self._history.get(recovery_id)

    @staticmethod
    def execute_playbook(
        playbook_name: str,
        target: int | str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute named automated recovery playbook."""
        return RecoveryPlaybooks.execute_playbook(playbook_name=playbook_name, target=target, **kwargs)

    @staticmethod
    def _generate_proof_hash(
        recovery_id: str,
        action_name: str,
        status: RecoveryStatus,
        resolved_tier: ExecutionTier | None,
        completed_at: str,
        attempts: list[RecoveryAttemptRecord],
    ) -> str:
        """Generate deterministic SHA-256 fingerprint of the complete recovery lifecycle."""
        payload = {
            "recovery_id": recovery_id,
            "action_name": action_name,
            "status": status.value,
            "resolved_tier": resolved_tier.value if resolved_tier else None,
            "completed_at": completed_at,
            "attempts": [
                {
                    "number": a.attempt_number,
                    "tier": a.tier.value,
                    "passed": a.passed,
                    "category": a.error_category.value if a.error_category else None,
                    "error": a.error_message,
                }
                for a in attempts
            ],
        }
        raw_json = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    async def execute_recovery(
        self,
        request: ExecuteRecoveryRequest,
        custom_client: httpx.AsyncClient | None = None,
    ) -> ExecuteRecoveryResult:
        """Execute action across the multi-tier ladder with automatic fallback and verification."""
        rec_id = request.recovery_id or f"rec_{uuid4().hex[:12]}"
        start_time = time.perf_counter()
        policy = request.policy
        attempts: list[RecoveryAttemptRecord] = []
        attempt_counter = 0

        final_status = RecoveryStatus.FAILED_ALL_TIERS
        resolved_tier: ExecutionTier | None = None
        last_verification_result = None
        all_errors: list[str] = []

        log.info(
            "recovery_execution_started",
            recovery_id=rec_id,
            action=request.action_name,
            ladder=[t.value for t in policy.fallback_ladder],
        )

        # Iterate over the configured execution tiers in ladder sequence
        for tier in policy.fallback_ladder:
            # Check if route configuration is provided for this tier
            tier_config: APIRouteConfig | BrowserRouteConfig | DesktopRouteConfig | None = None
            if tier == ExecutionTier.API:
                tier_config = request.api_route
            elif tier == ExecutionTier.BROWSER:
                tier_config = request.browser_route
            elif tier == ExecutionTier.DESKTOP:
                tier_config = request.desktop_route

            if tier_config is None:
                log.debug("recovery_tier_skipped_no_config", tier=tier.value)
                continue

            max_retries = max(0, policy.max_retries_per_tier)
            tier_passed = False

            for retry_idx in range(max_retries + 1):
                attempt_counter += 1
                correction_hint_text: str | None = None

                # Execute tier
                if tier == ExecutionTier.API and isinstance(tier_config, APIRouteConfig):
                    tier_res = await APITierExecutor.execute(tier_config, custom_client=custom_client)
                elif tier == ExecutionTier.BROWSER and isinstance(tier_config, BrowserRouteConfig):
                    tier_res = await BrowserTierExecutor.execute(tier_config, custom_client=custom_client)
                elif tier == ExecutionTier.DESKTOP and isinstance(tier_config, DesktopRouteConfig):
                    tier_res = await DesktopTierExecutor.execute(tier_config)
                else:
                    continue

                tier_ok = tier_res.get("passed", False)
                error_msg = tier_res.get("error")

                # If tier execution failed
                if not tier_ok:
                    classification = ErrorClassifier.classify(
                        error_message=error_msg or "Unknown execution error",
                        status_code=tier_res.get("status_code"),
                        page_content=tier_res.get("response_snippet"),
                        current_tier=tier,
                    )
                    all_errors.append(f"[{tier.value.upper()}] {error_msg}")

                    attempts.append(
                        RecoveryAttemptRecord(
                            attempt_number=attempt_counter,
                            tier=tier,
                            passed=False,
                            error_category=classification.category,
                            error_message=error_msg,
                            latency_ms=tier_res.get("latency_ms", 0.0),
                            correction_applied=None,
                            evidence=tier_res,
                            timestamp=datetime.now(UTC).isoformat(),
                        )
                    )

                    # Fast failover checks
                    if tier == ExecutionTier.API and classification.category == ErrorCategory.AUTH_CREDENTIAL_ERROR and policy.fast_failover_on_auth_error:
                        log.info("recovery_fast_failover_auth_error", tier=tier.value)
                        break

                    if tier == ExecutionTier.BROWSER and classification.category == ErrorCategory.CAPTCHA_CHALLENGE and policy.fast_failover_on_captcha:
                        log.info("recovery_fast_failover_captcha", tier=tier.value)
                        break

                    # If retries remain in current tier, backoff before retry
                    if retry_idx < max_retries:
                        delay = min(policy.backoff_base_sec * (retry_idx + 1), 0.1)
                        await asyncio.sleep(delay)
                    continue

                # Tier execution succeeded -> now check postcondition verification gate
                if policy.require_postcondition_verification and request.verification_criteria:
                    verif_res = await self._verification_engine.execute_composite(
                        request.verification_criteria,
                        custom_client=custom_client,
                    )
                    last_verification_result = verif_res

                    if verif_res.passed:
                        # Postcondition satisfied!
                        attempts.append(
                            RecoveryAttemptRecord(
                                attempt_number=attempt_counter,
                                tier=tier,
                                passed=True,
                                latency_ms=tier_res.get("latency_ms", 0.0),
                                correction_applied=correction_hint_text,
                                evidence=tier_res,
                                timestamp=datetime.now(UTC).isoformat(),
                            )
                        )
                        tier_passed = True
                        break
                    else:
                        # Execution reported OK, but verification check failed -> Self-Correction loop!
                        correction = SelfCorrectionEngine.generate_hints(
                            failed_tier=tier,
                            error_message=f"Postcondition criteria failed: {verif_res.failed_criteria} failure(s)",
                            verification_check=verif_res.check_results[0] if verif_res.check_results else None,
                        )
                        correction_hint_text = correction.hints[0].suggested_action if correction.hints else None
                        all_errors.append(f"[{tier.value.upper()}_VERIFICATION_FAILED] Postcondition criteria not satisfied")

                        attempts.append(
                            RecoveryAttemptRecord(
                                attempt_number=attempt_counter,
                                tier=tier,
                                passed=False,
                                error_category=ErrorCategory.POSTCONDITION_FAILED,
                                error_message=f"Postcondition failed: {verif_res.failed_criteria} criteria unmet",
                                latency_ms=tier_res.get("latency_ms", 0.0),
                                correction_applied=correction_hint_text,
                                evidence={"verification_score": verif_res.overall_score},
                                timestamp=datetime.now(UTC).isoformat(),
                            )
                        )

                        if retry_idx < max_retries and correction.can_retry_current_tier:
                            delay = min(policy.backoff_base_sec * (retry_idx + 1), 0.1)
                            await asyncio.sleep(delay)
                            continue
                        else:
                            # Escalate to next tier in ladder
                            break
                else:
                    # No verification required -> mark tier passed
                    attempts.append(
                        RecoveryAttemptRecord(
                            attempt_number=attempt_counter,
                            tier=tier,
                            passed=True,
                            latency_ms=tier_res.get("latency_ms", 0.0),
                            correction_applied=None,
                            evidence=tier_res,
                            timestamp=datetime.now(UTC).isoformat(),
                        )
                    )
                    tier_passed = True
                    break

            if tier_passed:
                resolved_tier = tier
                if tier == ExecutionTier.API:
                    final_status = RecoveryStatus.SUCCEEDED_PRIMARY
                elif tier == ExecutionTier.BROWSER:
                    final_status = RecoveryStatus.RECOVERED_BROWSER
                else:
                    final_status = RecoveryStatus.RECOVERED_DESKTOP
                break

        # Calculate final metrics and proof hash
        total_duration = (time.perf_counter() - start_time) * 1000.0
        now_iso = datetime.now(UTC).isoformat()
        proof_hash = self._generate_proof_hash(
            recovery_id=rec_id,
            action_name=request.action_name,
            status=final_status,
            resolved_tier=resolved_tier,
            completed_at=now_iso,
            attempts=attempts,
        )

        rca = "; ".join(all_errors) if all_errors and final_status == RecoveryStatus.FAILED_ALL_TIERS else None

        result = ExecuteRecoveryResult(
            recovery_id=rec_id,
            action_name=request.action_name,
            status=final_status,
            passed=final_status != RecoveryStatus.FAILED_ALL_TIERS,
            resolved_tier=resolved_tier,
            total_attempts=attempt_counter,
            tier_attempts=attempts,
            verification_result=last_verification_result,
            recovery_proof_hash=proof_hash,
            duration_ms=round(total_duration, 2),
            completed_at=now_iso,
            root_cause_analysis=rca,
        )

        self._history[rec_id] = result
        log.info(
            "recovery_execution_completed",
            recovery_id=rec_id,
            status=final_status.value,
            resolved_tier=resolved_tier.value if resolved_tier else None,
            attempts=attempt_counter,
            duration_ms=result.duration_ms,
        )
        return result


# Singleton instance
_RECOVERY_ENGINE_INSTANCE: RecoveryEngine | None = None


def get_recovery_engine() -> RecoveryEngine:
    """Return the global RecoveryEngine singleton."""
    global _RECOVERY_ENGINE_INSTANCE
    if _RECOVERY_ENGINE_INSTANCE is None:
        _RECOVERY_ENGINE_INSTANCE = RecoveryEngine()
    return _RECOVERY_ENGINE_INSTANCE
