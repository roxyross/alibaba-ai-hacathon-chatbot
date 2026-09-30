"""Dense vector embeddings and hybrid search ranking engine for Knowledge Vault.

Provides deterministic multi-dimensional feature-hashed dense vectors,
cosine similarity computation, BM25-style lexical matching, and
Reciprocal Rank Fusion (RRF) hybrid scoring.
"""

from __future__ import annotations

import hashlib
import math
import re


class EmbeddingEngine:
    """Vector generation, cosine similarity, and hybrid ranking engine."""

    VECTOR_DIM = 128

    @classmethod
    def get_embedding(cls, text: str) -> list[float]:
        """Generate a normalized 128-dimensional dense vector for text.

        Uses signed feature hashing over words and character n-grams,
        weighted with logarithmic term frequencies and normalized to unit L2 norm.
        """
        clean = text.lower().strip()
        if not clean:
            return [0.0] * cls.VECTOR_DIM

        vec = [0.0] * cls.VECTOR_DIM

        # 1. Word tokens
        words = re.findall(r"\b\w{2,}\b", clean)
        word_counts: dict[str, int] = {}
        for w in words:
            word_counts[w] = word_counts.get(w, 0) + 1

        for w, count in word_counts.items():
            weight = 1.0 + math.log1p(count)
            # Hash to index and sign
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
            idx = h % cls.VECTOR_DIM
            sign = 1.0 if ((h >> 8) & 1) else -1.0
            vec[idx] += sign * weight

        # 2. Character tri-grams for sub-word semantic capture
        if len(clean) >= 3:
            for i in range(len(clean) - 2):
                tri = clean[i : i + 3]
                h = int(hashlib.md5(tri.encode("utf-8")).hexdigest(), 16)
                idx = h % cls.VECTOR_DIM
                sign = 1.0 if ((h >> 8) & 1) else -1.0
                vec[idx] += sign * 0.35

        # 3. L2 Normalization
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-9:
            return [round(x / norm, 6) for x in vec]
        return [0.0] * cls.VECTOR_DIM

    @classmethod
    def cosine_similarity(cls, vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two dense vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
        # Since vectors are unit-normalized, dot product is cosine similarity
        return max(0.0, min(1.0, dot))

    @classmethod
    def lexical_similarity(cls, query: str, content: str) -> float:
        """Calculate BM25-inspired lexical matching score between query and document text."""
        q_tokens = re.findall(r"\b\w{2,}\b", query.lower())
        if not q_tokens:
            return 0.0

        c_tokens = re.findall(r"\b\w{2,}\b", content.lower())
        if not c_tokens:
            return 0.0

        c_counts: dict[str, int] = {}
        for t in c_tokens:
            c_counts[t] = c_counts.get(t, 0) + 1

        doc_len = len(c_tokens)
        avg_len = 100.0
        k1 = 1.2
        b = 0.75
        k_val = k1 * (1.0 - b + b * (doc_len / avg_len))

        score = 0.0
        for qt in set(q_tokens):
            tf = c_counts.get(qt, 0)
            if tf > 0:
                tf_norm = (tf * (k1 + 1.0)) / (tf + k_val)
                score += tf_norm

        # Normalized query coverage
        coverage = len([qt for qt in set(q_tokens) if qt in c_counts]) / len(set(q_tokens))
        normalized_lexical = min(1.0, (score * 0.3) + (coverage * 0.7))
        return round(normalized_lexical, 4)

    @classmethod
    def hybrid_score(
        cls,
        query: str,
        content: str,
        query_vec: list[float],
        chunk_vec: list[float],
        hybrid: bool = True,
    ) -> tuple[float, float, float]:
        """Compute combined dense + lexical score with exact match bonus.

        Returns (combined_score, dense_score, lexical_score).
        """
        dense_score = cls.cosine_similarity(query_vec, chunk_vec)
        lexical_score = cls.lexical_similarity(query, content)

        if not hybrid:
            return (round(dense_score, 4), round(dense_score, 4), round(lexical_score, 4))

        # Weighting: 60% dense semantic, 40% lexical precision
        combined = (dense_score * 0.60) + (lexical_score * 0.40)

        # Exact query match boost
        if query.lower() in content.lower():
            combined = min(1.0, combined + 0.25)

        return (round(combined, 4), round(dense_score, 4), round(lexical_score, 4))

    @classmethod
    def rrf_rank(
        cls,
        dense_rankings: list[str],
        lexical_rankings: list[str],
        rrf_k: int = 60,
    ) -> dict[str, float]:
        """Compute Reciprocal Rank Fusion (RRF) scores across two ranked candidate lists."""
        rrf_scores: dict[str, float] = {}

        for rank, cid in enumerate(dense_rankings, 1):
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (rrf_k + rank))

        for rank, cid in enumerate(lexical_rankings, 1):
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (rrf_k + rank))

        return rrf_scores
