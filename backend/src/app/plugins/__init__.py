"""Plugins package for ROXY 2.0."""

from app.plugins.manager import PluginManager, PluginSecurityError
from app.plugins.router import router as plugins_router
from app.plugins.schemas import (
    InstallPluginRequest,
    PluginActionRequest,
    PluginManifest,
    PluginRecord,
    PluginStatus,
    PluginToolDefinition,
)

__all__ = [
    "PluginManager",
    "PluginSecurityError",
    "plugins_router",
    "InstallPluginRequest",
    "PluginActionRequest",
    "PluginManifest",
    "PluginRecord",
    "PluginStatus",
    "PluginToolDefinition",
]
