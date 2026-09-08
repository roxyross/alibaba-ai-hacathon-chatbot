"""ROXY JARVIS multi-agent runtime.

Loads `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` at startup,
classifies user queries through a Coordinator, and dispatches them to
the right specialist. Calls the existing AI gateway at
`/api/v1/ai/chat` for LLM inference.

See `specs/001-runtime-orchestrator/spec.md` for the full design and
`specs/001-runtime-orchestrator/plan.md` for the implementation plan.
"""

__version__ = "0.1.0"
