"""FastAPI router for Connectors Integration Framework."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.connectors.schemas import (
    ConnectionTestResult,
    ConnectorCreateRequest,
    ConnectorResponse,
    ConnectorTypeInfo,
    ConnectorUpdateRequest,
    OpenAPIImportRequest,
    OpenAPIImportResponse,
)
from app.connectors.service import ConnectorService

router = APIRouter(prefix="/connectors", tags=["connectors"])
_service = ConnectorService()


def get_connector_service() -> ConnectorService:
    return _service


@router.get("/types", response_model=list[ConnectorTypeInfo])
async def list_connector_types(
    user: User = Depends(get_current_user),
) -> list[ConnectorTypeInfo]:
    """List all supported external connector types and metadata."""
    return _service.get_supported_types()


@router.get("", response_model=list[ConnectorResponse])
async def list_user_connectors(
    user: User = Depends(get_current_user),
) -> list[ConnectorResponse]:
    """List all configured connectors for the authenticated user."""
    return await _service.list_connectors(user_id=user.id)


@router.post("", response_model=ConnectorResponse, status_code=status.HTTP_201_CREATED)
async def create_connector(
    req: ConnectorCreateRequest,
    user: User = Depends(get_current_user),
) -> ConnectorResponse:
    """Create a new connector instance and register its tools."""
    try:
        return await _service.create_connector(user_id=user.id, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{connector_id}", response_model=ConnectorResponse)
async def get_connector(
    connector_id: str,
    user: User = Depends(get_current_user),
) -> ConnectorResponse:
    """Retrieve details of a specific connector instance."""
    conn = await _service.get_connector(user_id=user.id, connector_id=connector_id)
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connector '{connector_id}' not found.")
    return conn


@router.put("/{connector_id}", response_model=ConnectorResponse)
async def update_connector(
    connector_id: str,
    req: ConnectorUpdateRequest,
    user: User = Depends(get_current_user),
) -> ConnectorResponse:
    """Update configuration or credentials for a connector."""
    try:
        return await _service.update_connector(user_id=user.id, connector_id=connector_id, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(
    connector_id: str,
    user: User = Depends(get_current_user),
) -> None:
    """Delete a connector instance and unregister its tools."""
    deleted = await _service.delete_connector(user_id=user.id, connector_id=connector_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connector '{connector_id}' not found.")


@router.post("/{connector_id}/test", response_model=ConnectionTestResult)
async def test_connector(
    connector_id: str,
    user: User = Depends(get_current_user),
) -> ConnectionTestResult:
    """Run a health check and verify credentials for a connector."""
    try:
        return await _service.test_connector(user_id=user.id, connector_id=connector_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/openapi/import", response_model=OpenAPIImportResponse, status_code=status.HTTP_201_CREATED)
async def import_openapi(
    req: OpenAPIImportRequest,
    user: User = Depends(get_current_user),
) -> OpenAPIImportResponse:
    """Import an OpenAPI/Swagger spec and dynamically generate executable tools."""
    try:
        return await _service.import_openapi_spec(user_id=user.id, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
