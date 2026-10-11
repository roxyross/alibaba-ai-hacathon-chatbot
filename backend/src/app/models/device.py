"""Device Agent, App Discovery, and App Control ORM models.

Provides models for connected devices (desktop/laptop/mobile),
discovered applications, and device action audit logs.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DeviceRegistration(Base):
    """A registered device running the ROXY device operating bridge."""

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    device_name: Mapped[str] = mapped_column(String(128), nullable=False)
    device_type: Mapped[str] = mapped_column(
        String(32), default="desktop", nullable=False
    )  # desktop, laptop, mobile, server
    os_platform: Mapped[str] = mapped_column(
        String(32), default="windows", nullable=False
    )  # windows, darwin, linux, android, ios
    os_version: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    architecture: Mapped[str] = mapped_column(String(32), default="x86_64", nullable=False)
    hostname: Mapped[str] = mapped_column(String(128), default="localhost", nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), default="127.0.0.1", nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), default="online", nullable=False, index=True
    )  # online, offline, busy
    is_current_host: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    hardware_fingerprint: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    device_token_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    daemon_version: Mapped[str | None] = mapped_column(String(32), default="1.0.0", nullable=True)

    capabilities_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    telemetry_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    apps: Mapped[list[DiscoveredApp]] = relationship(
        "DiscoveredApp", back_populates="device", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_devices_user_status", "user_id", "status"),
    )

    def get_capabilities(self) -> list[str]:
        try:
            val = json.loads(self.capabilities_json)
            return [str(x) for x in val] if isinstance(val, list) else []
        except Exception:
            return []

    def set_capabilities(self, caps: list[str]) -> None:
        self.capabilities_json = json.dumps(caps)

    def get_telemetry(self) -> dict[str, Any]:
        try:
            val = json.loads(self.telemetry_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_telemetry(self, telemetry: dict[str, Any]) -> None:
        self.telemetry_json = json.dumps(telemetry)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "os_platform": self.os_platform,
            "os_version": self.os_version,
            "architecture": self.architecture,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "status": self.status,
            "is_current_host": self.is_current_host,
            "hardware_fingerprint": self.hardware_fingerprint,
            "daemon_version": self.daemon_version,
            "capabilities": self.get_capabilities(),
            "telemetry": self.get_telemetry(),
            "last_heartbeat_at": (
                self.last_heartbeat_at.isoformat()
                if self.last_heartbeat_at is not None
                else None
            ),
            "created_at": (
                self.created_at.isoformat()
                if self.created_at is not None
                else None
            ),
            "updated_at": (
                self.updated_at.isoformat()
                if self.updated_at is not None
                else None
            ),
        }


class DiscoveredApp(Base):
    """An installed or active desktop application discovered on a device."""

    __tablename__ = "discovered_apps"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False
    )

    app_name: Mapped[str] = mapped_column(String(128), nullable=False)
    executable_path: Mapped[str] = mapped_column(String(512), nullable=False)
    bundle_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str] = mapped_column(
        String(32), default="utilities", nullable=False, index=True
    )  # browser, development, productivity, media, communication, utilities, system, gaming, design, finance, security, other
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    supported_actions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    install_location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_system_app: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    icon_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_running: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    process_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    launch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    device: Mapped[DeviceRegistration] = relationship("DeviceRegistration", back_populates="apps")

    __table_args__ = (
        Index("idx_discovered_apps_device_name", "device_id", "app_name"),
    )

    def get_capabilities(self) -> list[str]:
        try:
            val = json.loads(self.capabilities_json)
            return [str(x) for x in val] if isinstance(val, list) else []
        except Exception:
            return []

    def set_capabilities(self, caps: list[str]) -> None:
        self.capabilities_json = json.dumps(caps)

    def get_supported_actions(self) -> list[str]:
        try:
            val = json.loads(self.supported_actions_json)
            return [str(x) for x in val] if isinstance(val, list) else []
        except Exception:
            return []

    def set_supported_actions(self, actions: list[str]) -> None:
        self.supported_actions_json = json.dumps(actions)

    def get_metadata(self) -> dict[str, Any]:
        try:
            val = json.loads(self.metadata_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_metadata(self, meta: dict[str, Any]) -> None:
        self.metadata_json = json.dumps(meta)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "app_name": self.app_name,
            "executable_path": self.executable_path,
            "bundle_id": self.bundle_id,
            "category": self.category,
            "version": self.version,
            "publisher": self.publisher,
            "description": self.description,
            "capabilities": self.get_capabilities(),
            "supported_actions": self.get_supported_actions(),
            "metadata": self.get_metadata(),
            "install_location": self.install_location,
            "is_system_app": self.is_system_app,
            "icon_url": self.icon_url,
            "is_running": self.is_running,
            "process_id": self.process_id,
            "launch_count": self.launch_count,
            "last_launched_at": (
                self.last_launched_at.isoformat()
                if self.last_launched_at is not None
                else None
            ),
            "created_at": (
                self.created_at.isoformat()
                if self.created_at is not None
                else None
            ),
            "updated_at": (
                self.updated_at.isoformat()
                if self.updated_at is not None
                else None
            ),
        }


class DeviceActionLog(Base):
    """Audit log of commands and control actions executed on a device."""

    __tablename__ = "device_action_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)

    action_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # launch_app, close_app, focus_app, screen_capture, system_command
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="success", nullable=False, index=True
    )  # success, failed, pending_approval
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    __table_args__ = (
        Index("idx_device_action_logs_user_device", "user_id", "device_id"),
    )

    def get_parameters(self) -> dict[str, Any]:
        try:
            val = json.loads(self.parameters_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_parameters(self, params: dict[str, Any]) -> None:
        self.parameters_json = json.dumps(params)

    def get_result(self) -> dict[str, Any]:
        try:
            val = json.loads(self.result_json)
            return val if isinstance(val, dict) else ({"result": val} if val is not None else {})
        except Exception:
            return {}

    def set_result(self, result: Any) -> None:
        self.result_json = json.dumps(result)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "action_type": self.action_type,
            "target": self.target,
            "parameters": self.get_parameters(),
            "status": self.status,
            "result": self.get_result(),
            "error_message": self.error_message,
            "executed_at": (
                self.executed_at.isoformat()
                if self.executed_at is not None
                else None
            ),
        }


# =============================================================================
# Phase 11: Cross-Device Continuity & Session Handover Model
# =============================================================================

class SessionHandover(Base):
    """Seamless session transfer token and context between user devices."""

    __tablename__ = "session_handovers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_device_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    target_device_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )  # pending, accepted, completed, expired, rejected
    state_payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    __table_args__ = (
        Index("idx_session_handovers_user_target", "user_id", "target_device_id", "status"),
    )

    def get_payload(self) -> dict[str, Any]:
        try:
            val = json.loads(self.state_payload_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_payload(self, payload: dict[str, Any]) -> None:
        self.state_payload_json = json.dumps(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "source_device_id": self.source_device_id,
            "target_device_id": self.target_device_id,
            "status": self.status,
            "state_payload": self.get_payload(),
            "expires_at": self.expires_at.isoformat() if self.expires_at is not None else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at is not None else None,
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
        }


# =============================================================================
# Phase 11: P2P WebRTC Peer Session Model
# =============================================================================

class WebRTCPeerSession(Base):
    """P2P WebRTC signaling channel session between paired user devices."""

    __tablename__ = "webrtc_peer_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    initiator_device_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    target_device_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)

    session_type: Mapped[str] = mapped_column(
        String(32), default="data_channel", nullable=False
    )  # data_channel, screen_stream, audio_call, file_sync
    status: Mapped[str] = mapped_column(
        String(32), default="negotiating", nullable=False, index=True
    )  # negotiating, connected, closed, failed

    sdp_offer: Mapped[str | None] = mapped_column(Text, nullable=True)
    sdp_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    ice_candidates_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_webrtc_user_peers", "user_id", "initiator_device_id", "target_device_id"),
    )

    def get_ice_candidates(self) -> list[dict[str, Any]]:
        try:
            val = json.loads(self.ice_candidates_json)
            return [x for x in val if isinstance(x, dict)] if isinstance(val, list) else []
        except Exception:
            return []

    def add_ice_candidate(self, candidate: dict[str, Any]) -> None:
        candidates = self.get_ice_candidates()
        candidates.append(candidate)
        self.ice_candidates_json = json.dumps(candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "initiator_device_id": self.initiator_device_id,
            "target_device_id": self.target_device_id,
            "session_type": self.session_type,
            "status": self.status,
            "sdp_offer": self.sdp_offer,
            "sdp_answer": self.sdp_answer,
            "ice_candidates": self.get_ice_candidates(),
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at is not None else None,
        }


# =============================================================================
# Phase 11: Matter & Zigbee IoT Smart Home Device Model
# =============================================================================

class IoTDevice(Base):
    """Connected Matter, Zigbee, or Thread smart home appliance/sensor."""

    __tablename__ = "iot_devices"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_name: Mapped[str] = mapped_column(String(128), nullable=False)
    device_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # light, plug, thermostat, lock, sensor
    protocol: Mapped[str] = mapped_column(
        String(32), default="matter", nullable=False, index=True
    )  # matter, zigbee, thread
    vendor: Mapped[str] = mapped_column(String(64), default="generic", nullable=False)
    model: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    node_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    endpoint: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    state_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_iot_devices_user_type", "user_id", "device_type"),
    )

    def get_state(self) -> dict[str, Any]:
        try:
            val = json.loads(self.state_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_state(self, state: dict[str, Any]) -> None:
        self.state_json = json.dumps(state)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "protocol": self.protocol,
            "vendor": self.vendor,
            "model": self.model,
            "node_id": self.node_id,
            "endpoint": self.endpoint,
            "is_online": self.is_online,
            "state": self.get_state(),
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at is not None else None,
        }


# =============================================================================
# Phase 3: Standalone Roxy Device Agent Enrollment & Command Queue Models
# =============================================================================

class DeviceEnrollmentToken(Base):
    """Temporary, time-bounded pairing token to enroll a standalone device."""

    __tablename__ = "device_enrollment_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(128), default="Device Enrollment Token", nullable=False)
    is_claimed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    claimed_by_device_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def is_valid(self) -> bool:
        if self.is_claimed:
            return False
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        return datetime.now(UTC) <= exp

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "token": self.token,
            "label": self.label,
            "is_claimed": self.is_claimed,
            "claimed_by_device_id": self.claimed_by_device_id,
            "expires_at": self.expires_at.isoformat() if self.expires_at is not None else None,
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at is not None else None,
            "is_valid": self.is_valid(),
        }


class DeviceCommand(Base):
    """An asynchronous command queued for execution by a standalone Roxy Device Agent."""

    __tablename__ = "device_commands"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    command_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # launch_app, close_app, focus_app, screen_capture, app_scan, system_telemetry, ping
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )  # pending, dispatched, completed, failed, expired, cancelled
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_device_commands_dev_status", "device_id", "status"),
    )

    def get_payload(self) -> dict[str, Any]:
        try:
            val = json.loads(self.payload_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_payload(self, data: dict[str, Any]) -> None:
        self.payload_json = json.dumps(data)

    def get_result(self) -> dict[str, Any]:
        try:
            val = json.loads(self.result_json)
            return val if isinstance(val, dict) else ({"result": val} if val is not None else {})
        except Exception:
            return {}

    def set_result(self, data: Any) -> None:
        self.result_json = json.dumps(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "user_id": self.user_id,
            "command_type": self.command_type,
            "payload": self.get_payload(),
            "status": self.status,
            "result": self.get_result(),
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
            "dispatched_at": self.dispatched_at.isoformat() if self.dispatched_at is not None else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at is not None else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at is not None else None,
        }


