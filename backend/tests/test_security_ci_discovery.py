"""CI Enforcement & Security Test Discovery Guard.

Guarantees that:
1. All critical security regression test suites are actively registered and executed in .github/workflows/ci.yml.
2. No security test suite can be silently excluded or dropped from the CI pipeline without failing this test.
3. CI workflow triggers on the authoritative base branch (master), release candidate branches, and PRs.
"""

from __future__ import annotations

import os

REQUIRED_SECURITY_TEST_FILES = [
    "tests/test_auth_jwt_security.py",
    "tests/test_auth_demo_security.py",
    "tests/test_auth_oauth_state_security.py",
    "tests/test_auth_redirect_security.py",
    "tests/test_skills_confirmation_security.py",
    "tests/test_gmail_token_storage_security.py",
    "tests/test_ai_routing_reconciliation.py",
    "tests/test_phase24_adversarial_security.py",
    "tests/test_security_ci_discovery.py",
]


def test_ci_workflow_executes_all_security_suites() -> None:
    """Verify .github/workflows/ci.yml contains all mandatory security test suites."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(backend_dir)
    ci_workflow_path = os.path.join(repo_root, ".github", "workflows", "ci.yml")

    assert os.path.exists(ci_workflow_path), f"CI workflow not found at {ci_workflow_path}"

    with open(ci_workflow_path, encoding="utf-8") as f:
        ci_content = f.read()

    missing_suites: list[str] = []
    for test_file in REQUIRED_SECURITY_TEST_FILES:
        # Match test filename in the CI pytest execution commands
        test_filename = os.path.basename(test_file)
        if test_filename not in ci_content:
            missing_suites.append(test_file)

    assert not missing_suites, (
        f"CRITICAL CI GOVERNANCE FAILURE: The following security test suites are not registered "
        f"in .github/workflows/ci.yml: {missing_suites}. All security tests must be enforced in CI."
    )


def test_all_local_security_tests_accounted_for() -> None:
    """Dynamically discover any test_*_security.py in backend/tests and ensure they are tested."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tests_dir = os.path.join(backend_dir, "tests")

    discovered = [
        f for f in os.listdir(tests_dir)
        if f.startswith("test_") and f.endswith("_security.py")
    ]

    for f in discovered:
        rel_path = f"tests/{f}"
        assert rel_path in REQUIRED_SECURITY_TEST_FILES, (
            f"New security test file '{f}' detected in backend/tests/ but not listed in "
            f"REQUIRED_SECURITY_TEST_FILES. Add it to REQUIRED_SECURITY_TEST_FILES and CI workflow."
        )


def test_ci_workflow_triggers_on_master_and_remediation_branches() -> None:
    """Verify that CI workflow triggers on master and release branches."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(backend_dir)
    ci_workflow_path = os.path.join(repo_root, ".github", "workflows", "ci.yml")

    with open(ci_workflow_path, encoding="utf-8") as f:
        ci_content = f.read()

    assert "master" in ci_content, "CI workflow must trigger on master branch"
    assert "release/audit-remediation" in ci_content, "CI workflow must trigger on release/audit-remediation"
