"""Comprehensive tests for Alembic migration history, single-head determinism, and revision schema limits."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_chain_integrity_and_revision_id_lengths() -> None:
    """Audit that every revision ID is <= 32 characters and exactly 1 head exists."""
    alembic_ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(alembic_ini_path))
    config.set_main_option("script_location", str(alembic_ini_path.parent / "alembic"))
    script_dir = ScriptDirectory.from_config(config)

    heads = script_dir.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 Alembic head, got {heads}"
    head_rev = heads[0]
    assert head_rev == "012_billing_connectors"

    revisions = list(script_dir.walk_revisions("base", head_rev))
    assert len(revisions) == 12

    # Verify that NO revision ID exceeds the 32-character limit of alembic_version.version_num
    for rev in revisions:
        assert len(rev.revision) <= 32, (
            f"Revision ID '{rev.revision}' length {len(rev.revision)} exceeds 32 characters, "
            f"which will cause overflow in alembic_version.version_num!"
        )

    # Verify specific revisions
    rev_map = {r.revision: r for r in revisions}
    assert "010_cowork_artifacts_open_work" in rev_map
    assert rev_map["010_cowork_artifacts_open_work"].down_revision == "009_deep_app_catalog"
    assert rev_map["011_trust_reliability_hardening"].down_revision == "010_cowork_artifacts_open_work"
    assert rev_map["012_billing_connectors"].down_revision == "011_trust_reliability_hardening"


def test_migration_fresh_and_incremental_upgrade_paths() -> None:
    """Verify that Alembic can traverse upgrade paths for both fresh and incremental migrations."""
    alembic_ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(alembic_ini_path))
    config.set_main_option("script_location", str(alembic_ini_path.parent / "alembic"))
    script_dir = ScriptDirectory.from_config(config)

    # 1. Fresh path: base -> 012_billing_connectors
    path_fresh = list(script_dir.walk_revisions("base", "012_billing_connectors"))
    assert len(path_fresh) == 12

    # 2. Upgrade path from existing 011 -> 012
    path_from_011 = list(script_dir.walk_revisions("011_trust_reliability_hardening", "012_billing_connectors"))
    assert len(path_from_011) == 2
    assert [r.revision for r in path_from_011] == [
        "012_billing_connectors",
        "011_trust_reliability_hardening",
    ]

    # 3. Upgrade path from existing 009: 009 -> 012 (walk_revisions is inclusive)
    path_incremental = list(script_dir.walk_revisions("009_deep_app_catalog", "012_billing_connectors"))
    assert len(path_incremental) == 4
    assert [r.revision for r in path_incremental] == [
        "012_billing_connectors",
        "011_trust_reliability_hardening",
        "010_cowork_artifacts_open_work",
        "009_deep_app_catalog",
    ]
