"""Parse `.claude/agents/<slug>.md` files into AgentDef.

Each file has YAML frontmatter (between `---` markers) with the
required keys `name` and `description`, and optional `tools`,
`sensitive`, and `internal`. The Markdown body is the agent's
system prompt.

A malformed file (missing frontmatter, missing `name`, unparseable
YAML) is a loader error: the loader logs the path and raises, so
the operator sees the failure in the runtime's startup log (per
spec §10.8). The agent is not registered; the runtime continues
to start and serves the other agents.
"""

from __future__ import annotations

import frontmatter
import structlog
import yaml
from pathlib import Path

from runtime.domain.agent import AgentDef

log = structlog.get_logger()


class AgentLoadError(Exception):
    """Raised when an agent's .md file cannot be parsed.

    The loader raises; the registry catches and logs; the runtime
    continues to start. Per spec §10.8.
    """

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


def load_agent(path: Path) -> AgentDef:
    """Parse a single agent .md file.

    Raises AgentLoadError on any failure.
    """
    try:
        post = frontmatter.load(path)
    except yaml.YAMLError as exc:
        raise AgentLoadError(path, f"unparseable YAML frontmatter: {exc}") from exc
    except Exception as exc:  # frontmatter raises on truly broken files
        raise AgentLoadError(path, f"could not read file: {exc}") from exc

    metadata = post.metadata or {}
    name = metadata.get("name")
    if not name:
        raise AgentLoadError(path, "missing required frontmatter key 'name'")
    description = metadata.get("description")
    if not description:
        raise AgentLoadError(path, "missing required frontmatter key 'description'")
    tools = metadata.get("tools", [])
    # Accept either YAML list (`[Read, Write]`) or comma-separated
    # string (`Read, Write`) — both are common in agent definitions.
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]
    elif not isinstance(tools, list):
        raise AgentLoadError(path, f"'tools' must be a list, got {type(tools).__name__}")
    sensitive = bool(metadata.get("sensitive", False))
    internal = bool(metadata.get("internal", False))

    body = post.content.strip()
    if not body:
        raise AgentLoadError(path, "empty body — agent needs a system prompt")

    return AgentDef(
        slug=name,
        description=description,
        body=body,
        tools=tools,
        sensitive=sensitive,
        internal=internal,
    )


def discover_agents(agents_dir: Path) -> list[AgentDef]:
    """Load every `<slug>.md` file in `agents_dir`.

    Per spec §10.8: a single bad file does not prevent startup. The
    bad file is logged with its path and parse error; the others are
    loaded normally.
    """
    if not agents_dir.exists():
        log.warning("agents.dir.missing", path=str(agents_dir))
        return []

    loaded: list[AgentDef] = []
    for path in sorted(agents_dir.glob("*.md")):
        try:
            agent = load_agent(path)
        except AgentLoadError as exc:
            log.error("agent.load.failed", path=str(exc.path), reason=exc.reason)
            continue
        loaded.append(agent)
        log.info("agent.loaded", slug=agent.slug, internal=agent.internal)
    return loaded
