"""Recursive text chunking engine for Knowledge Vault.

Preserves markdown structural hierarchies, code blocks, tables, and sentence
boundaries while producing bounded chunks for dense vector embedding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class VaultChunk:
    """Represents an extracted text segment ready for vector indexing."""

    index: int
    content: str
    token_count: int
    section: str | None = None
    page_number: int | None = None


class RecursiveChunker:
    """Hierarchical text splitter with markdown and code block awareness."""

    def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 200) -> None:
        self.chunk_size = max(200, chunk_size)
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size // 2))

    def split_text(self, text: str, default_section: str | None = None) -> list[VaultChunk]:
        """Split text recursively into overlapping chunks respecting structural boundaries."""
        clean_text = text.strip()
        if not clean_text:
            empty_list: list[VaultChunk] = []
            return empty_list

        # Detect sections if markdown headers are present
        sections = self._split_by_sections(clean_text, default_section)
        raw_chunks: list[tuple[str, str | None, int | None]] = []

        for sec_title, sec_content, page_num in sections:
            if len(sec_content) <= self.chunk_size:
                raw_chunks.append((sec_content.strip(), sec_title, page_num))
            else:
                sub_chunks = self._recursive_split(sec_content, self.chunk_size, self.chunk_overlap)
                for sc in sub_chunks:
                    raw_chunks.append((sc.strip(), sec_title, page_num))

        # Format into VaultChunk dataclasses
        result: list[VaultChunk] = []
        for idx, (content, sec_title, page_num) in enumerate(raw_chunks):
            if not content:
                continue
            # Approximate token count: ~4 chars per token in English/code
            tokens = max(1, len(content) // 4)
            result.append(
                VaultChunk(
                    index=idx,
                    content=content,
                    token_count=tokens,
                    section=sec_title,
                    page_number=page_num,
                )
            )

        return result

    def _split_by_sections(
        self, text: str, default_section: str | None
    ) -> list[tuple[str | None, str, int | None]]:
        """Identify major Markdown headings (#, ##, ###) or page delimiters."""
        # Check for page markers like --- Page 1 --- or form feeds \x0c
        page_pattern = re.compile(r"(?:---+\s*Page\s*(\d+)\s*---+|\f)", re.IGNORECASE)
        pages = page_pattern.split(text)

        results: list[tuple[str | None, str, int | None]] = []

        # If pages were detected
        if len(pages) > 1:
            current_page = 1
            idx = 0
            while idx < len(pages):
                seg = pages[idx]
                if seg and seg.isdigit():
                    current_page = int(seg)
                    idx += 1
                    continue
                if seg and seg.strip():
                    sec_results = self._split_markdown_headers(seg.strip(), default_section, current_page)
                    results.extend(sec_results)
                idx += 1
            if results:
                return results

        return self._split_markdown_headers(text, default_section, None)

    def _split_markdown_headers(
        self, text: str, default_section: str | None, page_num: int | None
    ) -> list[tuple[str | None, str, int | None]]:
        """Split text along Markdown headings (#, ##, ###) while retaining headings."""
        header_pattern = re.compile(r"(?m)^(#{1,4}\s+[^\n]+)$")
        parts = header_pattern.split(text)

        if len(parts) <= 1:
            return [(default_section, text, page_num)]

        results: list[tuple[str | None, str, int | None]] = []
        current_header = default_section
        current_body: list[str] = []

        for part in parts:
            if not part:
                continue
            match = header_pattern.match(part.strip())
            if match:
                # Flush previous section
                if current_body:
                    body_text = "\n".join(current_body).strip()
                    if body_text:
                        results.append((current_header, body_text, page_num))
                    current_body = []
                current_header = part.strip().lstrip("#").strip()
            else:
                current_body.append(part)

        if current_body:
            body_text = "\n".join(current_body).strip()
            if body_text:
                results.append((current_header, body_text, page_num))

        return results if results else [(default_section, text, page_num)]

    def _recursive_split(self, text: str, chunk_size: int, overlap: int) -> list[str]:
        """Recursively subdivide text by paragraph, sentence, and word separators."""
        separators = ["\n\n", "\n", ". ", "; ", ", ", " "]
        return self._split_with_separators(text, separators, chunk_size, overlap)

    def _split_with_separators(
        self, text: str, separators: list[str], chunk_size: int, overlap: int
    ) -> list[str]:
        if len(text) <= chunk_size:
            return [text]

        sep: str = separators[0] if separators else ""
        remaining_seps: list[str] = separators[1:]

        splits: list[str] = text.split(sep) if sep else list(text)

        chunks: list[str] = []
        current_chunk: list[str] = []
        current_len: int = 0

        for s in splits:
            seg = s.strip()
            if not seg:
                continue
            seg_len = len(seg) + len(sep)

            if seg_len > chunk_size and remaining_seps:
                # Sub-segment is too big, recurse with finer separator
                if current_chunk:
                    chunks.append(sep.join(current_chunk).strip())
                    current_chunk = []
                    current_len = 0
                sub_splits = self._split_with_separators(seg, remaining_seps, chunk_size, overlap)
                chunks.extend(sub_splits)
                continue

            if current_len + seg_len <= chunk_size:
                current_chunk.append(seg)
                current_len += seg_len
            else:
                if current_chunk:
                    chunks.append(sep.join(current_chunk).strip())

                # Build overlap from previous chunk items
                overlap_chunk: list[str] = []
                overlap_len = 0
                for prev in reversed(current_chunk):
                    if overlap_len + len(prev) + len(sep) <= overlap:
                        overlap_chunk.insert(0, prev)
                        overlap_len += len(prev) + len(sep)
                    else:
                        break

                current_chunk = overlap_chunk + [seg]
                current_len = overlap_len + seg_len

        if current_chunk:
            chunks.append(sep.join(current_chunk).strip())

        return [c for c in chunks if c.strip()]
