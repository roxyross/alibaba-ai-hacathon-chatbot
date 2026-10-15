#!/usr/bin/env python3
"""Validate Alembic migration revisions integrity for ROXY-AI CI/CD.

Checks:
- Exactly one migration head exists (no dangling unmerged branches).
- The migration history chain is contiguous and acyclic.
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def validate_migrations(alembic_ini_path: Path | None = None) -> bool:
    if alembic_ini_path is None:
        alembic_ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"

    if not alembic_ini_path.exists():
        print(f"ERROR: Alembic config file not found at: {alembic_ini_path}", file=sys.stderr)
        return False

    config = Config(str(alembic_ini_path))
    script_dir = ScriptDirectory.from_config(config)

    heads = script_dir.get_heads()
    if len(heads) != 1:
        print(f"ERROR: Expected exactly 1 Alembic head, but found {len(heads)}: {heads}", file=sys.stderr)
        return False

    head_rev = heads[0]
    print(f"SUCCESS: Single Alembic migration head detected: {head_rev}")

    # Walk history back to base
    revisions = list(script_dir.walk_revisions("base", head_rev))
    print(f"SUCCESS: Migration chain verified with {len(revisions)} revisions:")
    for rev in reversed(revisions):
        if len(rev.revision) > 32:
            print(
                f"ERROR: Revision ID '{rev.revision}' ({len(rev.revision)} chars) exceeds the 32-character "
                f"limit for alembic_version.version_num!",
                file=sys.stderr,
            )
            return False
        print(f"  - [{rev.revision}] {rev.doc} (down: {rev.down_revision})")

    return True


if __name__ == "__main__":
    success = validate_migrations()
    sys.exit(0 if success else 1)
