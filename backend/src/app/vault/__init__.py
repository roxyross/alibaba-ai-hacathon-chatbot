"""Knowledge Vault & Vector Memory Module (Phase 5)."""

from app.vault.chunker import RecursiveChunker, VaultChunk
from app.vault.embeddings import EmbeddingEngine
from app.vault.router import router as vault_router
from app.vault.service import VaultService

__all__ = [
    "EmbeddingEngine",
    "RecursiveChunker",
    "VaultChunk",
    "VaultService",
    "vault_router",
]
