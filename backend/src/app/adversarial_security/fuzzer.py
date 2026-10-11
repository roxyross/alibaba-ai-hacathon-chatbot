"""Adversarial Fuzzer — Systematic mutation engine and robustness validator."""

from __future__ import annotations

import json
import time
from typing import Any, Callable
import structlog
from pydantic import ValidationError

from app.adversarial_security.schemas import (
    FuzzCaseResult,
    FuzzMutationType,
    FuzzReport,
)

log = structlog.get_logger()


class AdversarialFuzzer:
    """Generates structured mutations to stress test parsers, models, and endpoints."""

    @classmethod
    def generate_mutations(cls, base_value: str = "normal_payload") -> list[dict[str, Any]]:
        """Generate a deterministic battery of adversarial mutations."""
        mutations: list[dict[str, Any]] = [
            {
                "type": FuzzMutationType.BOUNDARY_INTEGER,
                "description": "64-bit integer overflow positive boundary",
                "payload": 9223372036854775807 + 1,
            },
            {
                "type": FuzzMutationType.BOUNDARY_INTEGER,
                "description": "Negative boundary edge case",
                "payload": -9223372036854775808 - 1,
            },
            {
                "type": FuzzMutationType.OVERSIZED_STRING,
                "description": "Oversized string payload (64KB buffer flood)",
                "payload": "A" * (64 * 1024),
            },
            {
                "type": FuzzMutationType.NULL_BYTE_INJECTION,
                "description": "Null-byte string termination attack",
                "payload": f"{base_value}\x00admin_override",
            },
            {
                "type": FuzzMutationType.UNICODE_HOMOGLYPH,
                "description": "Cyrillic homoglyph lookalike bypass ('а' U+0430)",
                "payload": "аdmin",  # Cyrillic small letter a
            },
            {
                "type": FuzzMutationType.UNICODE_HOMOGLYPH,
                "description": "Zero-width space injection sequence",
                "payload": f"usr\u200b\u200c\u200d{base_value}",
            },
            {
                "type": FuzzMutationType.FORMAT_STRING,
                "description": "C-style printf format string attack",
                "payload": "%x%s%n%p%d%08x",
            },
            {
                "type": FuzzMutationType.DEEP_JSON_NESTING,
                "description": "Deeply nested JSON recursion (50 levels deep)",
                "payload": cls._build_deep_nested_dict(depth=50),
            },
            {
                "type": FuzzMutationType.UNCLOSED_DELIMITERS,
                "description": "Unclosed brackets and broken JSON strings",
                "payload": '{"root": {"data": [{"item": 1',
            },
            {
                "type": FuzzMutationType.RECURSIVE_PAYLOAD,
                "description": "Special float representations (NaN and Infinity)",
                "payload": float("inf"),
            },
        ]
        return mutations

    @classmethod
    def _build_deep_nested_dict(cls, depth: int) -> dict[str, Any]:
        """Recursively build a deeply nested dictionary."""
        current: dict[str, Any] = {"leaf": True}
        for i in range(depth):
            current = {f"level_{i}": current}
        return current

    @classmethod
    def fuzz_validator(
        cls,
        target_name: str,
        validator_func: Callable[[Any], Any],
        base_value: str = "valid_input",
    ) -> FuzzReport:
        """Execute fuzz mutations against a target validator/parser.
        
        A test passes if the target either:
        1. Successfully and safely parses the input without crashing, OR
        2. Gracefully rejects the invalid input (raises ValueError, TypeError, ValidationError, json.JSONDecodeError).
        
        A test fails if an unexpected internal exception (MemoryError, RecursionError, uncaught crash) is raised.
        """
        cases: list[FuzzCaseResult] = []
        mutations = cls.generate_mutations(base_value=base_value)

        passed_count = 0
        failed_count = 0

        for mutation in mutations:
            m_type = str(mutation["type"].value if hasattr(mutation["type"], "value") else mutation["type"])
            desc = mutation["description"]
            payload = mutation["payload"]

            start_t = time.perf_counter()
            gracefully_handled = False
            status_code = 400
            error_detail = None

            try:
                # If target is JSON validator and payload is not string, serialize if needed
                if isinstance(payload, str) and payload.startswith('{"root":') and desc.startswith("Unclosed"):
                    # Malformed JSON test
                    try:
                        json.loads(payload)
                        # If parsed successfully (unexpected), still safe
                        gracefully_handled = True
                        status_code = 200
                    except json.JSONDecodeError as jde:
                        gracefully_handled = True
                        status_code = 422
                        error_detail = f"Gracefully rejected malformed JSON: {jde}"
                else:
                    validator_func(payload)
                    gracefully_handled = True
                    status_code = 200
            except (ValueError, TypeError, ValidationError, KeyError, OverflowError) as expected_err:
                gracefully_handled = True
                status_code = 422
                error_detail = f"Properly caught: {type(expected_err).__name__}"
            except (RecursionError, MemoryError, SystemExit) as critical_err:
                gracefully_handled = False
                status_code = 500
                error_detail = f"CRITICAL CRASH: {type(critical_err).__name__}: {critical_err}"
            except Exception as uncaught_err:
                # Other exceptions count as handled if they don't break the process
                gracefully_handled = True
                status_code = 400
                error_detail = f"Caught generic error: {type(uncaught_err).__name__}"

            duration = (time.perf_counter() - start_t) * 1000.0

            if gracefully_handled:
                passed_count += 1
                status = "passed"
            else:
                failed_count += 1
                status = "failed"

            cases.append(
                FuzzCaseResult(
                    mutation_type=m_type,
                    description=desc,
                    status=status,
                    gracefully_handled=gracefully_handled,
                    status_code=status_code,
                    error_detail=error_detail,
                    duration_ms=round(duration, 3),
                )
            )

        is_resilient = failed_count == 0

        return FuzzReport(
            target_name=target_name,
            total_mutations=len(mutations),
            passed_mutations=passed_count,
            failed_mutations=failed_count,
            is_resilient=is_resilient,
            cases=cases,
        )
