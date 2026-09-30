"""Generators and diff computation engine for Cowork Workspace artifacts.

Supports:
- Unified Diff calculation with additions/deletions tracking
- Markdown document generator
- Mermaid diagram synthesizer
- Scalable Vector Graphics (SVG) architecture diagram generator
"""

from __future__ import annotations

import difflib
from typing import Any


def compute_unified_diff(old_text: str, new_text: str, filename: str = "artifact") -> tuple[str, int, int]:
    """Compute unified diff and count additions and deletions.

    Returns (unified_diff_str, additions_count, deletions_count).
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
        )
    )

    additions = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    diff_str = "\n".join(diff_lines)

    return diff_str, additions, deletions


def generate_markdown_doc(
    title: str,
    sections: list[dict[str, str]] | None = None,
    summary: str = "",
) -> str:
    """Generate structured Markdown document with standard formatting."""
    lines: list[str] = [f"# {title.strip()}"]
    if summary:
        lines.append(f"\n> **Executive Summary**: {summary.strip()}\n")

    default_sections = sections or [
        {"title": "Overview", "content": "This document outlines the scope, objectives, and deliverables."},
        {"title": "Architecture & Flow", "content": "Detailed breakdown of system mechanics and responsibilities."},
        {"title": "Action Items & Milestones", "content": "- [ ] Implement core interfaces\n- [ ] Run automated test validation\n- [ ] Deploy to staging"},
    ]

    for sec in default_sections:
        s_title = sec.get("title", "Section")
        s_content = sec.get("content", "")
        lines.append(f"## {s_title}\n\n{s_content}\n")

    return "\n".join(lines).strip() + "\n"


def generate_mermaid_diagram(
    title: str,
    diagram_type: str = "flowchart",
    nodes: list[dict[str, str]] | None = None,
    relationships: list[dict[str, str]] | None = None,
) -> str:
    """Generate syntactically clean Mermaid.js diagram markup."""
    d_type = diagram_type.lower().strip()

    if "seq" in d_type:
        lines = [
            f"%% Diagram: {title}",
            "sequenceDiagram",
            "    autonumber",
            "    actor User",
            "    participant Cowork as Open Work Agent",
            "    participant Canvas as Cowork Canvas",
            "    participant Tools as Tool Registry",
            "    User->>Cowork: Submit task & requirements",
            "    Cowork->>Tools: Discover & execute tools",
            "    Tools-->>Cowork: Tool execution result",
            "    Cowork->>Canvas: Stream updated artifact",
            "    Canvas-->>User: Live visual preview & diff",
        ]
        return "\n".join(lines) + "\n"

    # Default to flowchart TD
    lines = [
        f"%% Diagram: {title}",
        "flowchart TD",
    ]

    if nodes:
        for node in nodes:
            nid = node.get("id", "N1")
            label = node.get("label", nid)
            lines.append(f"    {nid}[\"{label}\"]")
    else:
        lines.extend([
            "    Client[\"User Client (Web/Desktop)\"]",
            "    Gateway[\"ROXY Runtime Gateway\"]",
            "    Agent[\"Open Work Agent / Cowork\"]",
            "    Artifacts[\"Multi-Artifact Canvas\"]",
            "    Registry[\"Central Tool Registry\"]",
        ])

    if relationships:
        for rel in relationships:
            src = rel.get("from", "Client")
            dst = rel.get("to", "Gateway")
            arrow = rel.get("label", "")
            if arrow:
                lines.append(f"    {src} -->|\"{arrow}\"| {dst}")
            else:
                lines.append(f"    {src} --> {dst}")
    else:
        lines.extend([
            "    Client -->|\"Input prompt / Task\"| Gateway",
            "    Gateway --> Agent",
            "    Agent --> Registry",
            "    Agent -->|\"Synthesize output\"| Artifacts",
            "    Artifacts -->|\"Live visual preview\"| Client",
        ])

    return "\n".join(lines) + "\n"


def generate_svg_diagram(title: str, components: list[dict[str, Any]] | None = None) -> str:
    """Generate clean, scalable vector graphics SVG architecture preview."""
    boxes = components or [
        {"x": 50, "y": 60, "w": 180, "h": 80, "title": "Cowork Agent", "subtitle": "Autonomous Orchestrator"},
        {"x": 280, "y": 60, "w": 180, "h": 80, "title": "Artifact Engine", "subtitle": "Diff & Version Tracking"},
        {"x": 510, "y": 60, "w": 180, "h": 80, "title": "Tool Registry", "subtitle": "Execution Layer"},
    ]

    svg_lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 740 220" width="100%" height="100%">',
        '  <defs>',
        '    <linearGradient id="cardGrad" x1="0%" y1="0%" x2="100%" y2="100%">',
        '      <stop offset="0%" stop-color="#1e293b" />',
        '      <stop offset="100%" stop-color="#0f172a" />',
        '    </linearGradient>',
        '    <filter id="shadow" x="-5%" y="-5%" width="110%" height="115%">',
        '      <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000000" flood-opacity="0.3"/>',
        '    </filter>',
        '  </defs>',
        '  <rect width="740" height="220" rx="12" fill="#0b1120" />',
        f'  <text x="24" y="34" font-family="Inter, system-ui, sans-serif" font-size="16" font-weight="700" fill="#f8fafc">{title}</text>',
    ]

    for i, box in enumerate(boxes):
        x, y, w, h = box["x"], box["y"], box["w"], box["h"]
        t, sub = box["title"], box["subtitle"]
        svg_lines.append(
            f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="url(#cardGrad)" stroke="#334155" stroke-width="1.5" filter="url(#shadow)"/>'
        )
        svg_lines.append(
            f'  <text x="{x + 16}" y="{y + 32}" font-family="Inter, sans-serif" font-size="14" font-weight="600" fill="#38bdf8">{t}</text>'
        )
        svg_lines.append(
            f'  <text x="{x + 16}" y="{y + 56}" font-family="Inter, sans-serif" font-size="11" fill="#94a3b8">{sub}</text>'
        )

        # Draw connector arrow between cards
        if i < len(boxes) - 1:
            arrow_start_x = x + w
            arrow_end_x = boxes[i + 1]["x"]
            mid_y = y + h // 2
            svg_lines.append(
                f'  <line x1="{arrow_start_x}" y1="{mid_y}" x2="{arrow_end_x - 6}" y2="{mid_y}" stroke="#0ea5e9" stroke-width="2" stroke-dasharray="4"/>'
            )
            svg_lines.append(
                f'  <polygon points="{arrow_end_x},{mid_y} {arrow_end_x - 6},{mid_y - 4} {arrow_end_x - 6},{mid_y + 4}" fill="#0ea5e9" />'
            )

    svg_lines.append('</svg>')
    return "\n".join(svg_lines)
