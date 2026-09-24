"""Google GenAI media synthesis engine (Imagen 3/4, Veo 2/3.1, Gemini Omni Flash)."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class GoogleGenAIMediaEngine:
    """Wrapper around official google.genai SDK for truthful image and video synthesis."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (
            api_key
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )

    def _get_client(self, override_key: str | None = None) -> Any:
        key = override_key or self.api_key
        if not key:
            raise ValueError(
                "Google GenAI API key is missing. Please configure GEMINI_API_KEY or BYOK in Settings."
            )
        from google import genai
        return genai.Client(api_key=key)

    async def generate_image(
        self,
        prompt: str,
        model: str = "imagen-3.0-generate-002",
        aspect_ratio: str = "1:1",
        number_of_images: int = 1,
        override_key: str | None = None,
    ) -> list[bytes]:
        """Generate high-resolution images via client.models.generate_images."""
        from google.genai import types

        client = self._get_client(override_key)

        def _call_imagen() -> list[bytes]:
            # Normalise aspect ratio to Imagen format
            valid_ratios = {"1:1", "16:9", "9:16", "4:3", "3:4"}
            ratio = aspect_ratio if aspect_ratio in valid_ratios else "1:1"

            config = types.GenerateImagesConfig(
                number_of_images=number_of_images,
                aspect_ratio=ratio,
            )
            response = client.models.generate_images(
                model=model,
                prompt=prompt,
                config=config,
            )
            images: list[bytes] = []
            if hasattr(response, "generated_images") and response.generated_images:
                for item in response.generated_images:
                    if hasattr(item, "image") and hasattr(item.image, "image_bytes"):
                        images.append(item.image.image_bytes)
            return images

        return await asyncio.to_thread(_call_imagen)

    async def generate_video_operation(
        self,
        prompt: str,
        model: str = "veo-3.1-generate-preview",
        duration_seconds: int = 5,
        first_frame_bytes: bytes | None = None,
        override_key: str | None = None,
    ) -> Any:
        """Start long-running video generation operation via client.models.generate_videos."""
        from google.genai import types

        client = self._get_client(override_key)

        def _call_veo() -> Any:
            source_args: dict[str, Any] = {"prompt": prompt}
            if first_frame_bytes:
                source_args["image"] = types.Image.from_bytes(data=first_frame_bytes)

            source = types.GenerateVideosSource(**source_args)
            config = types.GenerateVideosConfig(
                number_of_videos=1,
                duration_seconds=duration_seconds,
                enhance_prompt=True,
            )
            operation = client.models.generate_videos(
                model=model,
                source=source,
                config=config,
            )
            return operation

        return await asyncio.to_thread(_call_veo)

    async def poll_video_operation(self, operation: Any, override_key: str | None = None) -> Any:
        """Poll status of a Veo long-running operation."""
        client = self._get_client(override_key)
        return await asyncio.to_thread(client.operations.get, operation)
