"""ImageStudioService — Neural synthesis engine, style presets, prompt enhancer, and Knowledge Vault exporter."""

from __future__ import annotations

import logging
import random
import urllib.parse
from typing import Any

from app.images.repository import ImageStudioRepository

logger = logging.getLogger(__name__)

# Aspect ratio to width x height mappings (standard diffusion resolutions)
ASPECT_RATIO_DIMENSIONS: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "2:3": (832, 1216),
    "3:2": (1216, 832),
    "4:5": (896, 1120),
}

# Curated artistic style presets
STYLE_PRESETS: dict[str, dict[str, str]] = {
    "photorealistic": {
        "name": "Photorealistic",
        "description": "Hyperrealistic photography with authentic lens depth of field",
        "prompt_suffix": "hyperrealistic photograph, shot on 35mm lens, f/1.8, natural lighting, intricate textures, 8k uhd, photorealistic",
    },
    "cinematic": {
        "name": "Cinematic",
        "description": "Dramatic Hollywood movie frame with anamorphic flares",
        "prompt_suffix": "cinematic movie still, dramatic composition, anamorphic lens flare, moody color grading, IMAX 70mm, atmospheric haze",
    },
    "anime": {
        "name": "Anime & Manga",
        "description": "Vibrant Japanese studio anime aesthetic with expressive line art",
        "prompt_suffix": "modern anime aesthetic, Makoto Shinkai style, vibrant colors, detailed sky, expressive line art, studio anime key visual",
    },
    "cyberpunk": {
        "name": "Cyberpunk",
        "description": "Futuristic neon-drenched sci-fi aesthetics with holographic glow",
        "prompt_suffix": "cyberpunk theme, neon lights, glowing cyan and magenta accents, rain reflections, futuristic high-tech dystopian cityscape",
    },
    "3d_render": {
        "name": "3D Animation",
        "description": "Pixar / Disney style raytraced character and environment render",
        "prompt_suffix": "Pixar Disney 3D animation style, raytraced subsurface scattering, soft ambient occlusion, cute expressive design, Octane Render",
    },
    "oil_painting": {
        "name": "Oil Painting",
        "description": "Textured impasto brushwork with classical museum lighting",
        "prompt_suffix": "classic oil painting, visible textured impasto brushstrokes, rich warm palette, dramatic chiaroscuro lighting, masterpiece on canvas",
    },
    "minimalist": {
        "name": "Minimalist",
        "description": "Clean vector geometry, subtle palettes, and elegant whitespace",
        "prompt_suffix": "minimalist vector line art, clean negative space, subtle pastel palette, elegant modern graphic design, Bauhaus aesthetics",
    },
    "watercolor": {
        "name": "Watercolor",
        "description": "Soft ethereal watercolor bleeds and organic pigment splashes",
        "prompt_suffix": "delicate watercolor illustration, wet-on-wet paint bleeds, organic splashes, textured cold-press cotton paper, soft ethereal lighting",
    },
}

SUPPORTED_MODELS: list[str] = [
    "flux",
    "flux-realism",
    "flux-anime",
    "flux-3d",
    "flux-cablyai",
    "turbo",
    "imagen-3.0",
]


class ImageStudioService:
    """Service orchestrating neural synthesis, styling, prompt enhancement, and vault exports."""

    def __init__(self, repo: ImageStudioRepository | None = None) -> None:
        self._repo = repo or ImageStudioRepository()

    def get_style_presets(self) -> dict[str, dict[str, str]]:
        """Return available artistic style presets."""
        return STYLE_PRESETS

    def get_aspect_ratios(self) -> dict[str, tuple[int, int]]:
        """Return supported aspect ratios with pixel resolutions."""
        return ASPECT_RATIO_DIMENSIONS

    def enhance_prompt(self, base_prompt: str, style_preset: str = "photorealistic") -> str:
        """Enhance a user's prompt with rich atmospheric, lighting, and textural nuances."""
        cleaned = base_prompt.strip().rstrip(".")
        preset = STYLE_PRESETS.get(style_preset, STYLE_PRESETS["photorealistic"])
        suffix = preset["prompt_suffix"]

        # Ensure base prompt does not already duplicate modifiers
        enhancements = [cleaned]
        if "lighting" not in cleaned.lower() and "light" not in cleaned.lower():
            enhancements.append("volumetric dramatic lighting")
        if "detail" not in cleaned.lower():
            enhancements.append("masterpiece level fine detail")
        enhancements.append(suffix)

        return ", ".join(enhancements)

    def synthesize_image_url(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        style_preset: str = "photorealistic",
        model: str = "flux",
        seed: int | None = None,
    ) -> tuple[str, str, int, int, int]:
        """Generate high-resolution neural diffusion image URL and metadata.

        Returns: (media_url, revised_prompt, width, height, seed)
        """
        width, height = ASPECT_RATIO_DIMENSIONS.get(aspect_ratio, (1024, 1024))
        chosen_seed = seed if seed is not None else random.randint(100000, 99999999)

        revised_prompt = self.enhance_prompt(prompt, style_preset)
        encoded_prompt = urllib.parse.quote(revised_prompt)

        # Normalize model for Pollinations neural backend
        pollinations_model = model if model in ("flux", "flux-realism", "flux-anime", "flux-3d", "turbo") else "flux"

        media_url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={width}&height={height}"
            f"&model={pollinations_model}"
            f"&seed={chosen_seed}"
            f"&nologo=true&enhance=false"
        )

        return media_url, revised_prompt, width, height, chosen_seed

    async def export_to_knowledge_vault(
        self,
        user_id: str,
        image_id: str,
    ) -> dict[str, Any] | None:
        """Export generated artwork and its creative prompt into user's Knowledge Vault."""
        gen = await self._repo.get_generation(user_id, image_id)
        if not gen:
            return None

        # Check if already exported
        if gen.get("vault_document_id"):
            return gen

        doc_name = f"Artwork - {gen['prompt'][:40]}.md".replace("/", "-")
        content = (
            f"# Creative Studio Artwork: {gen['prompt']}\n\n"
            f"![{gen['prompt']}]({gen['media_url']})\n\n"
            f"### Generation Specifications\n"
            f"- **Base Prompt:** {gen['prompt']}\n"
            f"- **Revised Prompt:** {gen.get('revised_prompt') or gen['prompt']}\n"
            f"- **Style Preset:** {gen.get('style_preset', 'photorealistic').title()}\n"
            f"- **Model:** `{gen.get('model', 'flux')}`\n"
            f"- **Resolution:** {gen.get('width', 1024)}x{gen.get('height', 1024)} ({gen.get('aspect_ratio', '1:1')})\n"
            f"- **Seed:** {gen.get('seed') or 'N/A'}\n"
            f"- **Generated At:** {gen.get('created_at')}\n\n"
            f"*Ingested from ROXY-AI Image Studio into Personal Knowledge Vault.*"
        )

        vault_doc_id = f"doc_art_{gen['id']}"
        try:
            from app.documents.repository import DocumentRepository
            from app.skills.document_ingest import DocumentIngestRequest, DocumentIngestSkill

            skill = DocumentIngestSkill()
            req = DocumentIngestRequest(
                user_id=user_id,
                document_id=vault_doc_id,
                document_name=doc_name,
                filename=f"{doc_name}.md",
                file_bytes=content.encode("utf-8"),
                content_type="text/markdown",
            )
            await skill.execute(req)

            doc_repo = DocumentRepository()
            await doc_repo.create(
                user_id=user_id,
                filename=doc_name,
                document_id=vault_doc_id,
                folder="Artwork",
                file_size_bytes=len(content.encode("utf-8")),
                mime_type="text/markdown",
                extracted_text=content,
            )
        except Exception as exc:
            logger.warning(f"Failed to ingest image into Knowledge Vault: {exc}")

        # Update image record with vault document ID
        updated = await self._repo.attach_vault_document(user_id, image_id, vault_doc_id)
        return updated or gen
