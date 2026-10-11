"""FastAPI router for Plugin management and discovery."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.plugins.manager import PluginManager, PluginSecurityError
from app.plugins.schemas import (
    InstallPluginRequest,
    PluginActionRequest,
    PluginRecord,
)

router = APIRouter(prefix="/plugins", tags=["plugins"])
_manager = PluginManager.get_instance()


@router.get("", response_model=list[PluginRecord])
async def list_plugins(
    user: User = Depends(get_current_user),
) -> list[PluginRecord]:
    """List all installed plugins."""
    return _manager.list_plugins()


@router.post("/install", response_model=PluginRecord, status_code=status.HTTP_201_CREATED)
async def install_plugin(
    req: InstallPluginRequest,
    user: User = Depends(get_current_user),
) -> PluginRecord:
    """Install and validate a plugin from its manifest."""
    try:
        return _manager.install_plugin(req.manifest)
    except PluginSecurityError as sec_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(sec_err))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/{plugin_id}", response_model=PluginRecord)
async def get_plugin(
    plugin_id: str,
    user: User = Depends(get_current_user),
) -> PluginRecord:
    """Get plugin details."""
    record = _manager.get_plugin(plugin_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plugin '{plugin_id}' not found.")
    return record


@router.post("/{plugin_id}/enable", response_model=PluginRecord)
async def enable_plugin(
    plugin_id: str,
    user: User = Depends(get_current_user),
) -> PluginRecord:
    """Enable plugin and activate its tools."""
    try:
        return _manager.enable_plugin(plugin_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plugin '{plugin_id}' not found.")
    except PermissionError as p_err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(p_err))


@router.post("/{plugin_id}/disable", response_model=PluginRecord)
async def disable_plugin(
    plugin_id: str,
    user: User = Depends(get_current_user),
) -> PluginRecord:
    """Disable plugin and remove tools from registry."""
    try:
        return _manager.disable_plugin(plugin_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plugin '{plugin_id}' not found.")


@router.post("/{plugin_id}/revoke", response_model=PluginRecord)
async def revoke_plugin(
    plugin_id: str,
    req: PluginActionRequest | None = None,
    user: User = Depends(get_current_user),
) -> PluginRecord:
    """Revoke plugin permanently and de-register capabilities."""
    reason = req.reason if req and req.reason else "Administrative security revocation"
    try:
        return _manager.revoke_plugin(plugin_id, reason=reason)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plugin '{plugin_id}' not found.")


@router.delete("/{plugin_id}")
async def uninstall_plugin(
    plugin_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Uninstall plugin from system."""
    success = _manager.uninstall_plugin(plugin_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plugin '{plugin_id}' not found.")
    return {"status": "success", "message": f"Plugin '{plugin_id}' uninstalled."}
