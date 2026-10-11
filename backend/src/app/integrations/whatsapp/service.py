"""Central WhatsApp Integration Service orchestrating route negotiation and security gates."""

from __future__ import annotations

import contextlib
import hashlib
import os
import uuid
from typing import Any

import structlog

from app.integrations.whatsapp.base import WhatsAppBaseAdapter
from app.integrations.whatsapp.cloud_api_adapter import WhatsAppCloudApiAdapter
from app.integrations.whatsapp.desktop_adapter import WhatsAppDesktopAdapter
from app.integrations.whatsapp.models import (
    WhatsAppConnectionReport,
    WhatsAppOperationResult,
    WhatsAppRoute,
    WhatsAppTaskStatus,
)
from app.integrations.whatsapp.web_adapter import WhatsAppWebAdapter
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource
from app.trust.confirmation_gate import ConfirmationGate
from app.trust.schemas import ConfirmationChallengeResponse, ConfirmationStatus, RiskTier

log = structlog.get_logger()


class WhatsAppService:
    """Universal WhatsApp capability service managing adapters, permissions, and negotiation."""

    _instance: WhatsAppService | None = None

    def __init__(self) -> None:
        self.desktop_adapter = WhatsAppDesktopAdapter()
        self.web_adapter = WhatsAppWebAdapter()
        self.cloud_api_adapter = WhatsAppCloudApiAdapter()
        self._consumed_challenge_tokens: set[str] = set()

    @classmethod
    def get_instance(cls) -> WhatsAppService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_adapter(self, route: WhatsAppRoute) -> WhatsAppBaseAdapter:
        """Retrieve concrete adapter by route."""
        if route == WhatsAppRoute.DESKTOP:
            return self.desktop_adapter
        elif route == WhatsAppRoute.WEB:
            return self.web_adapter
        elif route == WhatsAppRoute.CLOUD_API:
            return self.cloud_api_adapter
        raise ValueError(f"Unknown WhatsApp route: {route}")

    # -------------------------------------------------------------------------
    # Recipient Normalization & Allowlist Enforcement
    # -------------------------------------------------------------------------

    @classmethod
    def get_configured_test_recipients(cls) -> list[str]:
        """Fetch list of approved test recipients from environment allowlists."""
        recipients = []
        # Check single primary test recipient
        r1 = os.environ.get("ROXY_WHATSAPP_TEST_RECIPIENT", "").strip()
        if r1:
            with contextlib.suppress(ValueError):
                recipients.append(WhatsAppBaseAdapter.normalize_phone_number(r1))

        # Check comma-separated allowlist
        r_list = os.environ.get("WHATSAPP_TEST_RECIPIENT_ALLOWLIST", "").strip()
        if r_list:
            for item in r_list.split(","):
                clean = item.strip()
                if clean:
                    with contextlib.suppress(ValueError):
                        recipients.append(WhatsAppBaseAdapter.normalize_phone_number(clean))
        return list(dict.fromkeys(recipients))

    @classmethod
    def validate_recipient_allowlist(cls, target_number: str) -> tuple[bool, str, str]:
        """Validate recipient format and enforce strict test allowlist."""
        try:
            norm = WhatsAppBaseAdapter.normalize_phone_number(target_number)
        except ValueError as err:
            return False, "", str(err)

        allowed = cls.get_configured_test_recipients()
        if not allowed:
            return (
                False,
                norm,
                "BLOCKED: No test recipient allowlist configured. Set ROXY_WHATSAPP_TEST_RECIPIENT or WHATSAPP_TEST_RECIPIENT_ALLOWLIST in environment.",
            )

        if norm not in allowed:
            redacted = WhatsAppBaseAdapter.redact_phone_number(norm)
            return (
                False,
                norm,
                f"REJECTED: Recipient {redacted} is not in the approved test allowlist. Disallowed under Zero Simulation Doctrine.",
            )

        return True, norm, "OK"

    # -------------------------------------------------------------------------
    # Route & Capability Negotiation
    # -------------------------------------------------------------------------

    async def probe_all_routes(self) -> dict[WhatsAppRoute, WhatsAppConnectionReport]:
        """Probe connection status across all three integration routes."""
        reports = {}
        reports[WhatsAppRoute.DESKTOP] = await self.desktop_adapter.get_connection_status()
        reports[WhatsAppRoute.WEB] = await self.web_adapter.get_connection_status()
        reports[WhatsAppRoute.CLOUD_API] = await self.cloud_api_adapter.get_connection_status()
        return reports

    async def negotiate_route(self, requested_route: WhatsAppRoute = WhatsAppRoute.AUTO) -> tuple[WhatsAppRoute | None, str]:
        """Determine the appropriate route based on user preference, configuration, and session availability.

        Returns (selected_route, explanation)
        """
        if requested_route != WhatsAppRoute.AUTO:
            adapter = self.get_adapter(requested_route)
            st = await adapter.get_connection_status()
            if st.is_ready:
                return requested_route, f"Explicit route {requested_route.value} verified and ready."
            else:
                return None, f"Requested route '{requested_route.value}' is not ready: {st.details}"

        # Automatic negotiation
        reports = await self.probe_all_routes()

        # Preference 1: Official Cloud API if configured and authenticated
        if reports[WhatsAppRoute.CLOUD_API].is_ready:
            return WhatsAppRoute.CLOUD_API, "Selected Official Cloud API (configured and verified)."

        # Preference 2: WhatsApp Desktop if installed and authenticated
        if reports[WhatsAppRoute.DESKTOP].is_ready:
            return WhatsAppRoute.DESKTOP, "Selected WhatsApp Desktop (authenticated session active)."

        # Preference 3: WhatsApp Web if persistent profile is authenticated
        if reports[WhatsAppRoute.WEB].is_ready:
            return WhatsAppRoute.WEB, "Selected WhatsApp Web (persistent browser session active)."

        # None ready: construct clear diagnostic summary
        details = [
            f"Desktop: {reports[WhatsAppRoute.DESKTOP].state.value} ({reports[WhatsAppRoute.DESKTOP].details})",
            f"Web: {reports[WhatsAppRoute.WEB].state.value} ({reports[WhatsAppRoute.WEB].details})",
            f"Cloud API: {reports[WhatsAppRoute.CLOUD_API].state.value} ({reports[WhatsAppRoute.CLOUD_API].details})",
        ]
        return None, "No authenticated WhatsApp route is available. " + "; ".join(details)

    # -------------------------------------------------------------------------
    # Confirmation Gate & Tamper-Resistant Approval
    # -------------------------------------------------------------------------

    def create_send_challenge(
        self,
        user_id: str,
        recipient: str,
        message: str,
        route: WhatsAppRoute,
        run_id: str,
        ttl_seconds: int = 180,
    ) -> ConfirmationChallengeResponse:
        """Create a cryptographic ConfirmationGate challenge bound to recipient, message hash, and route."""
        is_valid, norm_recipient, err = self.validate_recipient_allowlist(recipient)
        if not is_valid:
            raise ValueError(f"Cannot create send challenge: {err}")

        msg_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
        redacted = WhatsAppBaseAdapter.redact_phone_number(norm_recipient)

        details = {
            "app": "WhatsApp",
            "action": "send_text_message",
            "route": route.value,
            "recipient_normalized": norm_recipient,
            "recipient_redacted": redacted,
            "message_text": message,
            "message_hash": msg_hash,
            "run_id": run_id,
        }

        challenge = ConfirmationGate.create_challenge(
            user_id=user_id,
            action_type="whatsapp_send_message",
            title=f"Approve Outbound WhatsApp Message ({route.value.upper()})",
            summary=f"Send 1 verified WhatsApp text message to {redacted} via {route.value}",
            details=details,
            risk_tier=RiskTier.HIGH,
            risk_score=80,
            requires_2fa=False,
            ttl_seconds=ttl_seconds,
        )

        log.info(
            "whatsapp_service.challenge_created",
            challenge_id=challenge.challenge_id,
            recipient=redacted,
            route=route.value,
            run_id=run_id,
        )
        return challenge

    def validate_send_approval(
        self,
        challenge_id: str,
        user_id: str,
        expected_recipient: str,
        expected_message: str,
        expected_route: WhatsAppRoute,
        expected_run_id: str,
    ) -> tuple[bool, str]:
        """Revalidate server-side approval and enforce single-use execution token."""
        if challenge_id in self._consumed_challenge_tokens:
            return False, "REJECTED: Send challenge token has already been consumed (replay / duplicate send prevented)."

        challenge = ConfirmationGate.get_challenge(challenge_id, user_id=user_id)
        if not challenge:
            return False, f"REJECTED: Confirmation challenge {challenge_id} not found."

        if challenge.get("status") != ConfirmationStatus.APPROVED:
            return False, f"REJECTED: Challenge status is '{challenge.get('status')}', expected 'approved'."

        details = challenge.get("details", {})
        if details.get("run_id") != expected_run_id:
            return False, "REJECTED: Action run_id does not match approved challenge."

        if details.get("recipient_normalized") != expected_recipient:
            return False, "REJECTED: Target recipient does not match approved challenge."

        if details.get("route") != expected_route.value:
            return False, f"REJECTED: Sending route was switched after approval ({details.get('route')} != {expected_route.value})."

        expected_hash = hashlib.sha256(expected_message.encode("utf-8")).hexdigest()
        if details.get("message_hash") != expected_hash:
            return False, "REJECTED: Outbound message text was altered after user approval."

        # Mark token as consumed
        self._consumed_challenge_tokens.add(challenge_id)
        log.info("whatsapp_service.approval_validated", challenge_id=challenge_id, run_id=expected_run_id)
        return True, "APPROVED"

    # -------------------------------------------------------------------------
    # Unified Send Execution
    # -------------------------------------------------------------------------

    async def send_message(
        self,
        user_id: str,
        recipient: str,
        message: str,
        route: WhatsAppRoute = WhatsAppRoute.AUTO,
        challenge_id: str | None = None,
        run_id: str | None = None,
    ) -> WhatsAppOperationResult:
        """Unified send workflow with preflight allowlist check, route negotiation, and approval gating."""
        active_run_id = run_id or f"wa_{uuid.uuid4().hex[:10]}"
        redacted = WhatsAppBaseAdapter.redact_phone_number(recipient)

        # 1. Allowlist preflight check
        is_valid, norm_recipient, allow_err = self.validate_recipient_allowlist(recipient)
        if not is_valid:
            return WhatsAppOperationResult(
                operation_id=active_run_id,
                route=route,
                status=WhatsAppTaskStatus.BLOCKED,
                recipient_redacted=redacted,
                message_snippet=message[:40],
                error_code="ALLOWLIST_REJECTED",
                user_facing_error=allow_err,
            )

        # 2. Negotiate route
        selected_route, nego_explanation = await self.negotiate_route(route)
        if not selected_route:
            is_cred_err = (
                route == WhatsAppRoute.CLOUD_API
                and any(k in nego_explanation.lower() for k in ("credential", "token", "phone_number_id", "not_configured"))
            )
            err_code = "BLOCKED_CREDENTIALS" if is_cred_err else "NO_AUTHENTICATED_ROUTE"
            return WhatsAppOperationResult(
                operation_id=active_run_id,
                route=route,
                status=WhatsAppTaskStatus.BLOCKED,
                recipient_redacted=redacted,
                recipient_normalized=norm_recipient,
                message_snippet=message[:40],
                error_code=err_code,
                user_facing_error=f"BLOCKED: {nego_explanation}",
            )

        # 3. Check for approval token
        if not challenge_id:
            chal = self.create_send_challenge(
                user_id=user_id,
                recipient=norm_recipient,
                message=message,
                route=selected_route,
                run_id=active_run_id,
            )
            return WhatsAppOperationResult(
                operation_id=active_run_id,
                route=selected_route,
                status=WhatsAppTaskStatus.WAITING_FOR_APPROVAL,
                requires_approval=True,
                recipient_redacted=redacted,
                recipient_normalized=norm_recipient,
                message_snippet=message[:40],
                challenge_id=chal.challenge_id,
                verification_evidence={"challenge": chal.model_dump()},
                user_facing_error="Message draft prepared. Explicit user approval is required before sending.",
            )

        # 4. Revalidate approval challenge
        is_approved, apprv_reason = self.validate_send_approval(
            challenge_id=challenge_id,
            user_id=user_id,
            expected_recipient=norm_recipient,
            expected_message=message,
            expected_route=selected_route,
            expected_run_id=active_run_id,
        )
        if not is_approved:
            return WhatsAppOperationResult(
                operation_id=active_run_id,
                route=selected_route,
                status=WhatsAppTaskStatus.BLOCKED,
                recipient_redacted=redacted,
                recipient_normalized=norm_recipient,
                message_snippet=message[:40],
                challenge_id=challenge_id,
                error_code="APPROVAL_REJECTED",
                user_facing_error=f"Approval validation failed: {apprv_reason}",
            )

        # 5. Dispatch via concrete adapter
        adapter = self.get_adapter(selected_route)
        return await adapter.send_message(
            user_id=user_id,
            recipient=norm_recipient,
            message=message,
            challenge_id=challenge_id,
            run_id=active_run_id,
        )

    # -------------------------------------------------------------------------
    # Tool Registry Integration
    # -------------------------------------------------------------------------

    def register_tools(self) -> None:
        """Register universal WhatsApp tools in the central Roxy ToolRegistry."""
        reg = ToolRegistry.get_instance()

        async def _tool_send_whatsapp(
            recipient: str,
            message: str,
            route: str = "auto",
            challenge_id: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            try:
                selected_route = WhatsAppRoute(route.lower())
            except ValueError:
                selected_route = WhatsAppRoute.AUTO

            res = await self.send_message(
                user_id=uid,
                recipient=recipient,
                message=message,
                route=selected_route,
                challenge_id=challenge_id,
            )
            return res.to_dict()

        async def _tool_check_whatsapp_status(route: str = "auto") -> dict[str, Any]:
            try:
                r_enum = WhatsAppRoute(route.lower())
            except ValueError:
                r_enum = WhatsAppRoute.AUTO

            if r_enum == WhatsAppRoute.AUTO:
                all_reports = await self.probe_all_routes()
                return {r.value: rep.__dict__ for r, rep in all_reports.items()}
            else:
                rep = await self.get_adapter(r_enum).get_connection_status()
                return {r_enum.value: rep.__dict__}

        reg.register(
            AgentTool(
                id="whatsapp_send_message",
                name="whatsapp_send_message",
                description="Send a single strictly approved WhatsApp message via Desktop, Web, or Official Cloud API.",
                source=ToolSource.CONNECTOR,
                capabilities=["messaging", "whatsapp", "communication"],
                permissions=["messaging:whatsapp:send"],
                risk_level=RiskLevel.HIGH,
                requires_confirmation=True,
                input_schema={
                    "type": "object",
                    "properties": {
                        "recipient": {
                            "type": "string",
                            "description": "Recipient phone number in E.164 format (+country_code digits)",
                        },
                        "message": {
                            "type": "string",
                            "description": "Text message content to send",
                        },
                        "route": {
                            "type": "string",
                            "enum": ["auto", "desktop", "web", "cloud_api"],
                            "default": "auto",
                            "description": "Target integration route (auto, desktop, web, or cloud_api)",
                        },
                        "challenge_id": {
                            "type": "string",
                            "description": "Cryptographic confirmation challenge token obtained from user approval",
                        },
                    },
                    "required": ["recipient", "message"],
                },
            ),
            _tool_send_whatsapp,
        )

        reg.register(
            AgentTool(
                id="whatsapp_check_session",
                name="whatsapp_check_session",
                description="Check session and connection availability across WhatsApp Desktop, Web, and Cloud API.",
                source=ToolSource.CONNECTOR,
                capabilities=["messaging", "whatsapp", "telemetry"],
                permissions=["messaging:whatsapp:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
                input_schema={
                    "type": "object",
                    "properties": {
                        "route": {
                            "type": "string",
                            "enum": ["auto", "desktop", "web", "cloud_api"],
                            "default": "auto",
                            "description": "Route to inspect",
                        },
                    },
                },
            ),
            _tool_check_whatsapp_status,
        )
        log.info("whatsapp_service.tools_registered")
