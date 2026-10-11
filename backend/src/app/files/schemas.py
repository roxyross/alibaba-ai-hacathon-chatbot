"""Schemas and types for Sandboxed File & Folder Intelligence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FileItem(BaseModel):
    name: str
    relative_path: str
    absolute_path: str
    is_directory: bool
    size_bytes: int
    modified_at: str
    extension: str = ""


class FileListResponse(BaseModel):
    directory: str
    total_items: int
    items: list[FileItem] = Field(default_factory=list)


class FileReadResponse(BaseModel):
    path: str
    file_type: str
    size_bytes: int
    content: str
    truncated: bool = False
    lines_count: int = 0


class FileWriteResponse(BaseModel):
    path: str
    size_bytes: int
    created: bool
    success: bool
    message: str


class FileSearchResultItem(BaseModel):
    file_path: str
    line_number: int | None = None
    snippet: str


class FileSearchResponse(BaseModel):
    query: str
    total_matches: int
    matches: list[FileSearchResultItem] = Field(default_factory=list)


class FolderAnalysisReport(BaseModel):
    folder_path: str
    total_files: int
    total_directories: int
    primary_languages: list[str] = Field(default_factory=list)
    project_type: str = "general"
    entrypoints: list[str] = Field(default_factory=list)
    summary: str
    key_structure: list[str] = Field(default_factory=list)
