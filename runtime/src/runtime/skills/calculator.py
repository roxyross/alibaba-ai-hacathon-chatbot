"""calculator skill — safe mathematical expression evaluator.

Uses Python's ast.parse for arithmetic expressions. This is safe because
ast.parse only parses into an AST; we then recursively evaluate only the
supported node types (literals, binary ops, unary ops, and a allowlist of
math functions). No exec() or eval() is ever called.

Supports: + - * / // % ** and parentheses, plus sqrt, log, sin, cos, tan.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
import math
import operator
import structlog

from runtime.skills.executor import SkillResult

log = structlog.get_logger()

# Map AST binary operator nodes to Python operators
_BINOPS: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# Allowlist of callable names in expressions
_ALLOWED_CALLS = frozenset({"sqrt", "log", "sin", "cos", "tan", "floor", "ceil", "round", "abs"})


def _eval_node(node: ast.AST) -> float:
    """Recursively evaluate an AST node as a numeric expression."""
    match node:
        case ast.Constant(value=value) if isinstance(value, (int, float)):
            return float(value)
        case ast.UnaryOp(op=op, operand=operand):
            val = _eval_node(operand)
            match op:
                case ast.UAdd:
                    return +val
                case ast.USub:
                    return -val
            raise ValueError(f"Unsupported unary operator: {type(op).__name__}")
        case ast.BinOp(left=left, op=op, right=right):
            left_val = _eval_node(left)
            right_val = _eval_node(right)
            fn = _BINOPS.get(type(op))
            if fn is None:
                raise ValueError(f"Unsupported binary operator: {type(op).__name__}")
            return fn(left_val, right_val)
        case ast.Call(func=ast.Name(id=id), args=[arg]) if id in _ALLOWED_CALLS:
            val = _eval_node(arg)
            match id:
                case "sqrt":
                    return math.sqrt(val)
                case "log":
                    return math.log(val)
                case "sin":
                    return math.sin(val)
                case "cos":
                    return math.cos(val)
                case "tan":
                    return math.tan(val)
                case "floor":
                    return math.floor(val)
                case "ceil":
                    return math.ceil(val)
                case "round":
                    return round(val)
                case "abs":
                    return abs(val)
            raise ValueError(f"Unsupported function: {id}")
        case ast.Name(id="pi"):
            return math.pi
        case ast.Name(id="e"):
            return math.e
        case _:
            raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def _validate_tree(tree: ast.Expression) -> None:
    """Walk the AST and raise ValueError on any disallowed construct."""
    for node in ast.walk(tree):
        match node:
            case ast.Name(id=id) if id not in _ALLOWED_CALLS and id not in ("pi", "e"):
                raise ValueError(f"Unknown name: '{id}'")
            case ast.Call(func=ast.Name(id=id)) if id not in _ALLOWED_CALLS:
                raise ValueError(f"Unknown function: '{id}'")
            case ast.Call(func=ast.Name(id=id), args=args) if len(args) != 1:
                raise ValueError(f"Function '{id}' takes exactly one argument")
            case ast.Subscript():
                raise ValueError("Subscript expressions are not allowed")
            case ast.Attribute():
                raise ValueError("Attribute access is not allowed")


async def calculator(
    expression: str,
    *,
    user_id: str,
) -> SkillResult:
    """Evaluate a mathematical expression safely.

    Args:
        expression: A mathematical expression, e.g. "(2 + 3) * 7" or "sqrt(16)".
        user_id: for audit logging.

    Returns:
        SkillResult with the numeric result.
    """
    log.info("calculator.invoked", user_id=user_id, expression=expression[:100])

    if not expression or not expression.strip():
        return SkillResult(ok=False, data=None, error="expression cannot be empty")

    expression = expression.strip()

    try:
        tree = ast.parse(expression, mode="eval")
        _validate_tree(tree.body)
        result = _eval_node(tree.body)

        if math.isnan(result) or math.isinf(result):
            return SkillResult(
                ok=False,
                data=None,
                error="Expression evaluates to an undefined value (NaN or Inf)",
            )

        # Return int when result is a whole number
        result_int = int(result) if result == int(result) else result

        return SkillResult(
            ok=True,
            data={
                "expression": expression,
                "result": result_int,
                "result_raw": result,
            },
        )
    except SyntaxError as exc:
        return SkillResult(
            ok=False,
            data=None,
            error=f"Syntax error: {exc.text}",
        )
    except ValueError as exc:
        return SkillResult(
            ok=False,
            data=None,
            error=f"Cannot evaluate: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        log.error("calculator.error", user_id=user_id, expression=expression[:100], error=str(exc))
        return SkillResult(ok=False, data=None, error=f"Calculation error: {exc}")
