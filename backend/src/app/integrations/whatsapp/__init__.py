"""Universal WhatsApp Integration package for ROXY-AI."""

from app.integrations.whatsapp.base import WhatsAppBaseAdapter
from app.integrations.whatsapp.cloud_api_adapter import WhatsAppCloudApiAdapter
from app.integrations.whatsapp.desktop_adapter import WhatsAppDesktopAdapter
from app.integrations.whatsapp.models import (
    ConnectionState,
    WhatsAppCapability,
    WhatsAppConnectionReport,
    WhatsAppOperationResult,
    WhatsAppRoute,
    WhatsAppTaskStatus,
)
from app.integrations.whatsapp.service import WhatsAppService
from app.integrations.whatsapp.web_adapter import WhatsAppWebAdapter

__all__ = [
    "WhatsAppBaseAdapter",
    "WhatsAppCloudApiAdapter",
    "WhatsAppDesktopAdapter",
    "WhatsAppWebAdapter",
    "WhatsAppService",
    "WhatsAppRoute",
    "WhatsAppCapability",
    "ConnectionState",
    "WhatsAppTaskStatus",
    "WhatsAppConnectionReport",
    "WhatsAppOperationResult",
]
