"""Google GenAI media synthesis engine (Imagen 3/4, Veo 2/3.1, Gemini Omni Flash)."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

try:
    from google import genai
    from google.genai import types
except (ImportError, ModuleNotFoundError):
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]

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
        key = (override_key or self.api_key or "").strip()
        if not key:
            raise ValueError(
                "Google GenAI API key is missing. Please configure GEMINI_API_KEY or BYOK in Settings."
            )
        if genai is None:
            raise ImportError(
                "The 'google-genai' package is not installed. Please run: pip install google-genai>=1.0.0"
            )
        return genai.Client(api_key=key)

    async def generate_image(
        self,
        prompt: str,
        model: str = "imagen-3.0-generate-002",
        aspect_ratio: str = "1:1",
        number_of_images: int = 1,
        negative_prompt: str | None = None,
        seed: int | None = None,
        override_key: str | None = None,
    ) -> list[bytes]:
        """Generate high-resolution images via client.models.generate_images with generate_content fallback."""
        if types is None:
            raise ImportError("The 'google-genai' package is not installed.")

        client = self._get_client(override_key)

        def _call_imagen() -> list[bytes]:
            # Normalise aspect ratio to Imagen format
            valid_ratios = {"1:1", "16:9", "9:16", "4:3", "3:4"}
            ratio = aspect_ratio if aspect_ratio in valid_ratios else "1:1"

            # 1. Try Imagen generate_images (supported in Enterprise mode)
            try:
                config_kwargs: dict[str, Any] = {
                    "number_of_images": number_of_images,
                    "aspect_ratio": ratio,
                }
                if negative_prompt:
                    config_kwargs["negative_prompt"] = negative_prompt
                if seed is not None:
                    config_kwargs["seed"] = seed

                config = types.GenerateImagesConfig(**config_kwargs)
                response = client.models.generate_images(
                    model=model,
                    prompt=prompt,
                    config=config,
                )
                images: list[bytes] = []
                if hasattr(response, "generated_images") and response.generated_images:
                    for item in response.generated_images:
                        if getattr(item, "rai_filtered_reason", None):
                            logger.warning(f"Imagen content filtered by safety: {item.rai_filtered_reason}")
                        img_obj = getattr(item, "image", None)
                        if img_obj and getattr(img_obj, "image_bytes", None):
                            images.append(img_obj.image_bytes)
                if images:
                    return images
            except ValueError as ve:
                # Catch "This method is only supported in Gemini Enterprise Agent Platform mode"
                logger.info(f"generate_images not supported in developer mode ({ve}), trying generate_content")
            except Exception as exc:
                logger.info(f"generate_images call failed ({exc}), trying generate_content")

            # 2. Try Gemini 2.5/3 image multimodal generate_content (Developer API mode)
            fallback_models = ["gemini-2.5-flash-image", "gemini-3.1-flash-image", "gemini-3-pro-image"]
            for img_model in fallback_models:
                try:
                    content_config = types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=types.ImageConfig(aspect_ratio=ratio),
                    )
                    resp = client.models.generate_content(
                        model=img_model,
                        contents=prompt,
                        config=content_config,
                    )
                    content_images: list[bytes] = []
                    if hasattr(resp, "candidates") and resp.candidates:
                        for cand in resp.candidates:
                            content = getattr(cand, "content", None)
                            parts = getattr(content, "parts", []) if content else []
                            for part in parts:
                                inline = getattr(part, "inline_data", None)
                                if inline and getattr(inline, "data", None):
                                    content_images.append(inline.data)
                    if content_images:
                        return content_images
                except Exception as cand_err:
                    logger.debug(f"Model {img_model} generate_content attempt failed: {cand_err}")

            return []

        return await asyncio.to_thread(_call_imagen)

    async def generate_video_operation(
        self,
        prompt: str,
        model: str = "veo-3.1-generate-preview",
        duration_seconds: int = 5,
        first_frame_bytes: bytes | None = None,
        last_frame_bytes: bytes | None = None,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        fps: int = 24,
        audio: bool = True,
        negative_prompt: str | None = None,
        seed: int | None = None,
        override_key: str | None = None,
    ) -> Any:
        """Start long-running video generation operation via client.models.generate_videos."""
        if types is None:
            raise ImportError("The 'google-genai' package is not installed.")

        client = self._get_client(override_key)

        def _call_veo() -> Any:
            first_frame_img = types.Image(image_bytes=first_frame_bytes) if first_frame_bytes else None
            last_frame_img = types.Image(image_bytes=last_frame_bytes) if last_frame_bytes else None

            config_kwargs: dict[str, Any] = {
                "number_of_videos": 1,
                "duration_seconds": duration_seconds,
                "enhance_prompt": True,
            }
            if aspect_ratio:
                config_kwargs["aspect_ratio"] = aspect_ratio
            if resolution:
                config_kwargs["resolution"] = resolution
            if fps:
                config_kwargs["fps"] = fps
            if audio is not None:
                config_kwargs["generate_audio"] = audio
            if negative_prompt:
                config_kwargs["negative_prompt"] = negative_prompt
            if seed is not None:
                config_kwargs["seed"] = seed
            if last_frame_img:
                config_kwargs["last_frame"] = last_frame_img

            source_args: dict[str, Any] = {"prompt": prompt}
            if first_frame_img:
                source_args["image"] = first_frame_img
            source = types.GenerateVideosSource(**source_args)

            config = types.GenerateVideosConfig(**config_kwargs)
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
