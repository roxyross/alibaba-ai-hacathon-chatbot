"""calculator skill — safely evaluate math expressions and return a numeric result."""

from __future__ import annotations

import ast
import operator
import re
from typing import Callable

from app.skills.base import SkillExecutor
from app.skills.schemas import CalculatorRequest, CalculatorResponse


# Safe operators — no getattr, no builtins, no power with negative exponent
SAFE_OPS: dict[str, Callable[[object, object], object]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


class CalculatorSkill(SkillExecutor[CalculatorRequest, CalculatorResponse]):
    slug = "calculator"

    async def execute(self, input_data: CalculatorRequest) -> CalculatorResponse:
        expr = input_data.expression.strip()

        try:
            result = self._eval_expr(expr)
            return CalculatorResponse(
                expression=expr,
                result=result,
                error=None,
            )
        except Exception as exc:
            return CalculatorResponse(
                expression=expr,
                result=None,
                error=str(exc),
            )

    def _eval_expr(self, expr: str) -> float:
        """Evaluate a numeric expression safely using Python's AST parser.

        Supports: + - * / // % and parenthesised sub-expressions.
        """
        # Remove whitespace
        expr = re.sub(r"\s+", "", expr)
        if not expr:
            raise ValueError("Empty expression")

        # Only allow numbers, operators, parentheses, decimal points
        if not re.match(r"^[0-9+\-*/().eE]+$", expr):
            raise ValueError(f"Invalid characters in expression: {expr!r}")

        node = ast.parse(expr, mode="eval")
        return self._eval_node(node.body)  # type: ignore[arg-type]

    def _eval_node(self, node: ast.AST) -> float:
        match node:
            case ast.Constant(value=v) if isinstance(v, (int, float)):
                return float(v)
            case ast.BinOp(left=l, op=op, right=r):
                left = self._eval_node(l)
                right = self._eval_node(r)
                fn = SAFE_OPS.get(type(op))
                if fn is None:
                    raise ValueError(f"Unsupported binary operator: {type(op).__name__}")
                return fn(left, right)  # type: ignore[arg-type]
            case ast.UnaryOp(op=op, operand=operand):
                fn = SAFE_OPS.get(type(op))
                if fn is None:
                    raise ValueError(f"Unsupported unary operator: {type(op).__name__}")
                val = self._eval_node(operand)
                return fn(val)  # type: ignore[arg-type]
            case _:
                raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def get_executor() -> CalculatorSkill:
    return CalculatorSkill()
