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
    )  # browser, development, productivity, media, system, utilities, other
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
