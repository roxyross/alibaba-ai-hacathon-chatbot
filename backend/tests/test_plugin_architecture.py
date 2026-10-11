"""Unit and Security Tests for ROXY 2.0 Plugin Architecture.

Verifies:
1. Valid plugin installation and dynamic ToolRegistry registration.
2. Sandboxed tool execution.
3. Security policy validation (banned imports & code injection prevention).
4. Lifecycle control (enable, disable, uninstall).
5. Immediate revocation and re-activation blocking.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from app.plugins.manager import PluginManager, PluginSecurityError
from app.plugins.schemas import (
    PluginManifest,
    PluginStatus,
    PluginToolDefinition,
)
from app.tools.registry import ToolRegistry


@pytest.fixture(autouse=True)
def cleanup_plugins() -> Generator[None, None, None]:
    yield
    reg = ToolRegistry.get_instance()
    for tid in list(reg._tools.keys()):
        if tid.startswith("plugin_"):
            reg.unregister(tid)


def test_plugin_installation_and_tool_registration() -> None:
    manager = PluginManager()
    registry = ToolRegistry.get_instance()

    manifest = PluginManifest(
        plugin_id="weather_plugin",
        name="Community Weather",
        description="Fetches weather forecasts",
        author="weather_dev",
        tools=[
            PluginToolDefinition(
                name="get_forecast",
                description="Get weather for a city",
                capabilities=["weather", "forecast"],
                handler_code="result = {'city': inputs.get('city', 'London'), 'temp': 22, 'condition': 'Sunny'}",
            )
        ],
    )

    record = manager.install_plugin(manifest, auto_enable=True)
    assert record.status == PluginStatus.ACTIVE
    assert manager.get_plugin("weather_plugin") is not None

    # Verify tool registered in ToolRegistry
    tool = registry.get("plugin_weather_plugin_get_forecast")
    assert tool is not None
    assert tool.name == "[Community Weather] get_forecast"

    # Disable plugin
    manager.disable_plugin("weather_plugin")
    p1 = manager.get_plugin("weather_plugin")
    assert p1 is not None
    assert p1.status == PluginStatus.DISABLED
    assert registry.get("plugin_weather_plugin_get_forecast") is None

    # Re-enable
    manager.enable_plugin("weather_plugin")
    p2 = manager.get_plugin("weather_plugin")
    assert p2 is not None
    assert p2.status == PluginStatus.ACTIVE
    assert registry.get("plugin_weather_plugin_get_forecast") is not None


@pytest.mark.asyncio
async def test_plugin_sandboxed_execution() -> None:
    manager = PluginManager()
    registry = ToolRegistry.get_instance()

    manifest = PluginManifest(
        plugin_id="math_extra",
        name="Math Extra",
        description="Extra math operations",
        tools=[
            PluginToolDefinition(
                name="double_val",
                description="Double input value",
                handler_code="result = {'doubled': inputs.get('val', 0) * 2}",
            )
        ],
    )
    manager.install_plugin(manifest, auto_enable=True)

    handler = registry.get_handler("plugin_math_extra_double_val")
    assert handler is not None

    output = await handler(val=21)
    assert output["doubled"] == 42


def test_plugin_security_rejection_banned_modules() -> None:
    manager = PluginManager()

    # Attempting to import subprocess is blocked
    malicious_manifest = PluginManifest(
        plugin_id="exploit_plugin",
        name="Exploit",
        description="Malicious plugin",
        tools=[
            PluginToolDefinition(
                name="run_cmd",
                description="Run shell",
                handler_code="import subprocess; subprocess.run(['calc.exe'])",
            )
        ],
    )

    with pytest.raises(PluginSecurityError) as exc_info:
        manager.install_plugin(malicious_manifest)
    assert "banned module 'subprocess'" in str(exc_info.value)


def test_plugin_revocation_lifecycle() -> None:
    manager = PluginManager()
    registry = ToolRegistry.get_instance()

    manifest = PluginManifest(
        plugin_id="revocation_test",
        name="Revoke Me",
        description="Plugin to test revocation",
        tools=[
            PluginToolDefinition(
                name="ping",
                description="Ping tool",
                handler_code="result = {'ping': 'pong'}",
            )
        ],
    )
    manager.install_plugin(manifest, auto_enable=True)
    assert registry.get("plugin_revocation_test_ping") is not None

    # Revoke
    revoked = manager.revoke_plugin("revocation_test", reason="Security audit failure")
    assert revoked.status == PluginStatus.REVOKED
    assert registry.get("plugin_revocation_test_ping") is None

    # Cannot be re-enabled
    with pytest.raises(PermissionError) as exc_info:
        manager.enable_plugin("revocation_test")
    assert "has been revoked and cannot be enabled" in str(exc_info.value)

    # Clean uninstall
    assert manager.uninstall_plugin("revocation_test") is True
    assert manager.get_plugin("revocation_test") is None


@pytest.mark.asyncio
async def test_plugin_infinite_loop_timeout_protection() -> None:
    """Verifies that an infinite loop in a plugin is forcefully terminated by timeout."""
    manager = PluginManager()
    registry = ToolRegistry.get_instance()

    manifest = PluginManifest(
        plugin_id="infinite_loop_test",
        name="Infinite Loop Test",
        description="Tests timeout protection",
        tools=[
            PluginToolDefinition(
                name="hang",
                description="Hangs indefinitely",
                handler_code="while True:\n    pass",
            )
        ],
    )
    manager.install_plugin(manifest, auto_enable=True)
    handler = registry.get_handler("plugin_infinite_loop_test_hang")
    assert handler is not None

    with pytest.raises(TimeoutError) as exc_info:
        await handler()
    assert "timed out" in str(exc_info.value)

