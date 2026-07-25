"""
Calculator Plugin (Phase 10, built-in).

A pure, dependency-free, side-effect-free plugin.  Evaluates arithmetic
expressions safely by walking a restricted AST -- never uses ``eval`` on raw
input, so it is safe to run with no permissions at all.
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any

from ..base import Capability, HealthState, PluginHealth, PluginManifest, Permission
from ..sdk import SimplePlugin, action


_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS: dict[str, Any] = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log2": math.log2, "log10": math.log10, "exp": math.exp,
    "abs": abs, "round": round, "floor": math.floor, "ceil": math.ceil,
    "min": min, "max": max, "pow": pow,
}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


class SafeEval(ast.NodeVisitor):
    """Evaluate a restricted arithmetic AST."""

    def visit(self, node: ast.AST) -> Any:  # noqa: C901
        if isinstance(node, ast.Expression):
            return self.visit(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("only numeric constants allowed")
        if isinstance(node, ast.BinOp):
            op = _BIN_OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"operator {type(node.op).__name__} not allowed")
            return op(self.visit(node.left), self.visit(node.right))
        if isinstance(node, ast.UnaryOp):
            op = _UNARY_OPS.get(type(node.op))
            if op is None:
                raise ValueError("unary operator not allowed")
            return op(self.visit(node.operand))
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
                raise ValueError("function not allowed")
            args = [self.visit(a) for a in node.args]
            return _FUNCS[node.func.id](*args)
        if isinstance(node, ast.Name):
            if node.id in _CONSTS:
                return _CONSTS[node.id]
            raise ValueError(f"name {node.id!r} not allowed")
        raise ValueError(f"syntax element {type(node).__name__} not allowed")


class CalculatorPlugin(SimplePlugin):
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="calculator",
            version="1.0.0",
            capabilities=[Capability.CALCULATOR],
            permissions=[],  # pure, needs nothing
            description="Safe arithmetic and math-function evaluation.",
            documentation="actions: evaluate(expression) -> number",
            tags=["math", "utility", "offline"],
        )

    @action
    def evaluate(self, expression: str) -> float:
        tree = ast.parse(str(expression), mode="eval")
        return SafeEval().visit(tree)

    @action
    def constants(self) -> dict[str, float]:
        return dict(_CONSTS)

    def health(self) -> PluginHealth:
        # self-test 2+2 to prove the evaluator works
        try:
            ok = SafeEval().visit(ast.parse("2+2", mode="eval")) == 4
            return self.health_of(HealthState.HEALTHY if ok else HealthState.DEGRADED, "self-test")
        except Exception as exc:  # noqa: BLE001
            return self.health_of(HealthState.DEGRADED, str(exc))
