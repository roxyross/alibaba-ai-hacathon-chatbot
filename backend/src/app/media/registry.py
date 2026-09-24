"""Unified CapabilityRegistry for creative image and video models."""

from __future__ import annotations

import os
from typing import Any

from app.media.schemas import MediaModelCapability


class CapabilityRegistry:
    """Registry maintaining truthful capabilities and dynamic availability of media models."""

    def __init__(self) -> None:
        self._models: list[dict[str, Any]] = [
            # ─────────────────────────────────────────────────────────────
            # Image Models
            # ─────────────────────────────────────────────────────────────
            {
                "id": "imagen-3.0-generate-002",
                "name": "Google Imagen 3",
                "provider": "google",
                "media_type": "image",
                "badge": "Official Google",
                "description": "High-fidelity photorealistic and artistic neural image synthesis from Google DeepMind.",
                "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"],
                "supported_resolutions": ["1024x1024", "1344x768", "768x1344", "1152x896", "896x1152"],
                "supported_inputs": ["text"],
                "supports_negative_prompt": True,
                "supports_guidance_scale": False,
                "supports_seed": True,
                "credit_cost": 1,
            },
            {
                "id": "imagen-4.0-generate-001",
                "name": "Google Imagen 4 Ultra",
                "provider": "google",
                "media_type": "image",
                "badge": "Flagship 4K",
                "description": "Ultra-detail generation with advanced typography and intricate surface physics.",
                "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"],
                "supported_resolutions": ["1024x1024", "1344x768", "768x1344", "1152x896", "896x1152"],
                "supported_inputs": ["text"],
                "supports_negative_prompt": True,
                "supports_guidance_scale": False,
                "supports_seed": True,
                "credit_cost": 2,
            },
            {
                "id": "flux-schnell",
                "name": "FLUX.1 Schnell",
                "provider": "pollinations",
                "media_type": "image",
                "badge": "Ultra Fast",
                "description": "Sub-second open-weights diffusion model with sharp prompt adherence.",
                "supported_aspect_ratios": ["1:1", "16:9", "9:16", "2:3", "3:2", "4:5"],
                "supported_resolutions": ["1024x1024", "1344x768", "768x1344", "832x1216", "1216x832", "896x1120"],
                "supported_inputs": ["text"],
                "supports_negative_prompt": False,
                "supports_guidance_scale": True,
                "supports_seed": True,
                "credit_cost": 1,
                "always_available": True,
            },
            {
                "id": "flux-dev",
                "name": "FLUX.1 Dev",
                "provider": "pollinations",
                "media_type": "image",
                "badge": "High Detail",
                "description": "Fine-tuned diffusion weights prioritizing aesthetic composition and lighting.",
                "supported_aspect_ratios": ["1:1", "16:9", "9:16", "2:3", "3:2", "4:5"],
                "supported_resolutions": ["1024x1024", "1344x768", "768x1344", "832x1216", "1216x832", "896x1120"],
                "supported_inputs": ["text"],
                "supports_negative_prompt": False,
                "supports_guidance_scale": True,
                "supports_seed": True,
                "credit_cost": 1,
                "always_available": True,
            },
            {
                "id": "flux-1.1-pro",
                "name": "FLUX 1.1 Pro",
                "provider": "replicate",
                "media_type": "image",
                "badge": "Studio Pro",
                "description": "Commercial studio-grade FLUX architecture with enhanced human anatomy.",
                "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"],
                "supported_resolutions": ["1024x1024", "1344x768", "768x1344", "1152x896", "896x1152"],
                "supported_inputs": ["text"],
                "supports_negative_prompt": True,
                "supports_guidance_scale": True,
                "supports_seed": True,
                "credit_cost": 2,
            },
            # ─────────────────────────────────────────────────────────────
            # Video Models
            # ─────────────────────────────────────────────────────────────
            {
                "id": "veo-3.1-generate-preview",
                "name": "Google Veo 3.1",
                "provider": "google",
                "media_type": "video",
                "badge": "Cinematic 1080p",
                "description": "Flagship generative video model from DeepMind with native camera controls and sound effects.",
                "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                "supported_resolutions": ["720p", "1080p", "4k"],
                "supported_durations": [5, 10],
                "supported_inputs": ["text", "image"],
                "supports_negative_prompt": True,
                "supports_guidance_scale": False,
                "supports_seed": True,
                "supports_audio": True,
                "supports_camera_motion": True,
                "supports_first_frame": True,
                "supports_last_frame": True,
                "credit_cost": 5,
            },
            {
                "id": "veo-2.0-generate-001",
                "name": "Google Veo 2.0",
                "provider": "google",
                "media_type": "video",
                "badge": "Stable Video",
                "description": "High-consistency generative video model for dynamic scene transitions.",
                "supported_aspect_ratios": ["16:9", "9:16"],
                "supported_resolutions": ["720p", "1080p"],
                "supported_durations": [5],
                "supported_inputs": ["text", "image"],
                "supports_negative_prompt": False,
                "supports_guidance_scale": False,
                "supports_seed": True,
                "supports_audio": False,
                "supports_camera_motion": True,
                "supports_first_frame": True,
                "supports_last_frame": False,
                "credit_cost": 3,
            },
            {
                "id": "gemini-omni-1.1-flash",
                "name": "Gemini Omni Flash 1.1",
                "provider": "google",
                "media_type": "video",
                "badge": "Multi-Turn Director",
                "description": "Native multimodal video generation, scene extension, and frame-by-frame interpolation.",
                "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                "supported_resolutions": ["720p", "1080p"],
                "supported_durations": [5, 10],
                "supported_inputs": ["text", "image", "video"],
                "supports_negative_prompt": True,
                "supports_guidance_scale": False,
                "supports_seed": True,
                "supports_audio": True,
                "supports_camera_motion": True,
                "supports_first_frame": True,
                "supports_last_frame": True,
                "credit_cost": 4,
            },
        ]

    def list_models(
        self,
        media_type: str | None = None,
        user_byok: dict[str, str] | None = None,
    ) -> list[MediaModelCapability]:
        """Return declared models with truthful, dynamically evaluated availability."""
        byok = user_byok or {}
        has_google_key = bool(
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or byok.get("byok_gemini")
        )
        has_replicate_key = bool(
            os.getenv("REPLICATE_API_TOKEN")
            or byok.get("byok_flux")
        )

        results: list[MediaModelCapability] = []
        for raw in self._models:
            if media_type and raw["media_type"] != media_type:
                continue

            # Determine availability
            provider = raw["provider"]
            if raw.get("always_available"):
                is_avail = True
                reason = "Free High-Speed Fallback (Active)"
            elif provider == "google":
                is_avail = has_google_key
                reason = (
                    "Google GenAI Engine connected"
                    if has_google_key
                    else "Requires GEMINI_API_KEY or BYOK key in Settings"
                )
            elif provider == "replicate":
                is_avail = has_replicate_key
                reason = (
                    "Replicate Engine connected"
                    if has_replicate_key
                    else "Requires REPLICATE_API_TOKEN or BYOK key in Settings"
                )
            else:
                is_avail = True
                reason = "Ready for synthesis"

            item = dict(raw)
            item.pop("always_available", None)
            item["is_available"] = is_avail
            item["availability_reason"] = reason

            results.append(MediaModelCapability(**item))

        return results

    def get_model(self, model_id: str) -> MediaModelCapability | None:
        """Find a model specification by ID."""
        for m in self.list_models():
            if m.id == model_id:
                return m
        return None
