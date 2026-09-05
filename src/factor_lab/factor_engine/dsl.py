"""Safe Formulaic Alpha DSL for REQ-001 standard factors."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from factor_lab.core.errors import ValidationError
from factor_lab.core.source_universe import (
    PRICE_VOLUME_SOURCE_FAMILY,
    validate_source_family,
)
from factor_lab.factor_engine.models.factor_spec import FactorSpec

DSL_AST_VERSION: Final[str] = "formulaic_alpha_dsl_ast@1.0"
OPERATOR_SET_VERSION: Final[str] = "formulaic_alpha_operator_set@1.0"
DEFAULT_NAN_POLICY: Final[str] = "zero_fill"

_ARITHMETIC_OPERATORS: Final[frozenset[str]] = frozenset(
    {"+", "-", "*", "/", "unary-"}
)
_FUNCTION_OPERATORS: Final[frozenset[str]] = frozenset(
    {
        "abs",
        "corr",
        "cov",
        "decay",
        "decay_linear",
        "delay",
        "delta",
        "log",
        "mean",
        "neutralize",
        "product",
        "rank",
        "scale",
        "sign",
        "signed_power",
        "sqrt",
        "std",
        "sum",
        "ts_rank",
        "ts_zscore",
        "winsorized_rank",
        "winsorize",
        "zscore",
    }
)
_ALLOWED_OPERATORS: Final[frozenset[str]] = frozenset(
    _ARITHMETIC_OPERATORS | _FUNCTION_OPERATORS
)
_WINDOW_ARGUMENT_INDEX: Final[dict[str, int]] = {
    "corr": 2,
    "cov": 2,
    "decay": 1,
    "decay_linear": 1,
    "delay": 1,
    "delta": 1,
    "mean": 1,
    "product": 1,
    "std": 1,
    "sum": 1,
    "ts_rank": 1,
    "ts_zscore": 1,
}
_CROSS_SECTIONAL_OPERATORS: Final[frozenset[str]] = frozenset(
    {"rank", "zscore", "neutralize", "scale", "winsorize", "winsorized_rank"}
)
_TIME_SERIES_OPERATORS: Final[frozenset[str]] = frozenset(
    {
        "corr",
        "cov",
        "decay",
        "decay_linear",
        "delay",
        "delta",
        "mean",
        "product",
        "std",
        "sum",
        "ts_rank",
        "ts_zscore",
    }
)
_ELEMENTWISE_OPERATORS: Final[frozenset[str]] = frozenset(
    {"abs", "log", "sign", "signed_power", "sqrt"}
)


@dataclass(frozen=True, slots=True)
class DSLAnalysis:
    """Normalized Formulaic DSL metadata used by specs, mining, and review."""

    normalized_ast: dict[str, object]
    operator_list: list[str]
    field_refs: list[str]
    window_refs: list[int]
    node_count: int
    max_depth: int
    complexity_score: float
    expression_hash: str

    def to_metadata(self) -> dict[str, object]:
        return {
            "dsl_ast_version": DSL_AST_VERSION,
            "operator_set_version": OPERATOR_SET_VERSION,
            "expression_hash": self.expression_hash,
            "complexity_score": self.complexity_score,
            "field_refs": self.field_refs,
            "window_refs": self.window_refs,
            "nan_policy": DEFAULT_NAN_POLICY,
            "normalized_ast": self.normalized_ast,
            "operator_list": self.operator_list,
            "node_count": self.node_count,
            "max_depth": self.max_depth,
        }


def allowed_operator_names() -> list[str]:
    """Return the versioned safe Formulaic DSL operator set."""

    return sorted(_ALLOWED_OPERATORS)


def safe_symbolic_operator_names() -> list[str]:
    """Return the L4-safe generation subset of Formulaic DSL operators."""

    return [
        "rank",
        "ts_rank",
        "delay",
        "delta",
        "corr",
        "cov",
        "decay",
        "decay_linear",
        "zscore",
        "ts_zscore",
        "abs",
        "sign",
        "signed_power",
        "log",
        "sqrt",
        "mean",
        "std",
        "sum",
        "product",
        "scale",
        "winsorize",
        "winsorized_rank",
        "+",
        "-",
        "*",
        "/",
    ]


def _float_series(rows: Sequence[Mapping[str, object]], field_name: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(field_name)
        if value is None:
            raise ValidationError(f"DSL field not found: {field_name}")
        values.append(float(str(value)))
    return values


def _clean_float(value: float) -> float:
    return value if math.isfinite(value) else 0.0


def _contains_nonfinite(values: Sequence[float]) -> bool:
    return any(not math.isfinite(float(value)) for value in values)


def _safe_divide(numerator: float, denominator: float) -> float:
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return 0.0
    if abs(denominator) <= 1e-12:
        return 0.0
    return numerator / denominator


def _rank(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    if len(values) == 1:
        return [0.5]
    ordered = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    for rank, index in enumerate(ordered):
        ranks[index] = rank / (len(values) - 1)
    return ranks


def _delay(values: Sequence[float], periods: int) -> list[float]:
    shift = max(0, periods)
    if shift == 0:
        return [float(value) for value in values]
    return [math.nan] * shift + [float(value) for value in values[:-shift]]


def _delta(values: Sequence[float], periods: int) -> list[float]:
    delayed = _delay(values, periods)
    return [
        0.0 if math.isnan(lag) else float(value) - lag
        for value, lag in zip(values, delayed, strict=False)
    ]


def _window_slice(values: Sequence[float], index: int, window: int) -> list[float]:
    span = max(1, window)
    start = max(0, index - span + 1)
    return [float(value) for value in values[start : index + 1]]


def _ts_rank(values: Sequence[float], window: int) -> list[float]:
    output: list[float] = []
    for index, value in enumerate(values):
        ranked = _rank(_window_slice(values, index, window))
        output.append(ranked[-1] if ranked else float(value))
    return output


def _rolling_stat(
    values: Sequence[float],
    window: int | None,
    reducer: str,
) -> list[float]:
    output: list[float] = []
    for index in range(len(values)):
        current_window = (
            [float(value) for value in values]
            if window is None
            else _window_slice(values, index, window)
        )
        if not current_window:
            output.append(0.0)
        elif _contains_nonfinite(current_window):
            # Keep rolling operators aligned with the DSL's output-level
            # zero-fill policy.  In particular, statistics.pstdev cannot
            # consume NaN values, while mean/sum/product propagate one to
            # _clean_float at evaluate time.  Propagating NaN here preserves
            # the causal window and avoids treating a missing observation as
            # a numeric signal inside the rolling calculation.
            output.append(math.nan)
        elif reducer == "mean":
            output.append(statistics.mean(current_window))
        elif reducer == "std":
            output.append(
                statistics.pstdev(current_window)
                if len(current_window) >= 2
                else 0.0
            )
        elif reducer == "sum":
            output.append(sum(current_window))
        elif reducer == "product":
            product = 1.0
            for item in current_window:
                product *= item
            output.append(product)
        else:
            raise ValidationError(f"Unsupported rolling reducer: {reducer}")
    return output


def _corr_or_cov(
    left: Sequence[float],
    right: Sequence[float],
    window: int,
    *,
    correlation: bool,
) -> list[float]:
    output: list[float] = []
    span = max(2, window)
    for index in range(len(left)):
        start = max(0, index - span + 1)
        left_window = [float(value) for value in left[start : index + 1]]
        right_window = [float(value) for value in right[start : index + 1]]
        if len(left_window) < 2:
            output.append(0.0)
            continue
        mean_left = statistics.mean(left_window)
        mean_right = statistics.mean(right_window)
        covariance = sum(
            (left_value - mean_left) * (right_value - mean_right)
            for left_value, right_value in zip(left_window, right_window, strict=False)
        ) / len(left_window)
        if not correlation:
            output.append(covariance)
            continue
        denominator_left = sum((value - mean_left) ** 2 for value in left_window)
        denominator_right = sum((value - mean_right) ** 2 for value in right_window)
        denominator = denominator_left * denominator_right
        if denominator <= 0.0:
            output.append(0.0)
        else:
            adjusted_denominator = math.sqrt(denominator / (len(left_window) ** 2))
            output.append(covariance / adjusted_denominator)
    return output


def _corr(left: Sequence[float], right: Sequence[float], window: int) -> list[float]:
    return _corr_or_cov(left, right, window, correlation=True)


def _cov(left: Sequence[float], right: Sequence[float], window: int) -> list[float]:
    return _corr_or_cov(left, right, window, correlation=False)


def _decay(values: Sequence[float], window: int) -> list[float]:
    output: list[float] = []
    span = max(1, window)
    for index in range(len(values)):
        start = max(0, index - span + 1)
        window_values = [float(value) for value in values[start : index + 1]]
        weights = list(range(1, len(window_values) + 1))
        denominator = sum(weights) or 1
        output.append(
            sum(
                value * weight
                for value, weight in zip(window_values, weights, strict=False)
            )
            / denominator
        )
    return output


def _zscore(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    if _contains_nonfinite(values):
        return [math.nan for _ in values]
    mean_value = statistics.mean(values)
    std_value = statistics.pstdev(values) if len(values) >= 2 else 0.0
    if std_value == 0.0:
        return [0.0 for _ in values]
    return [(float(value) - mean_value) / std_value for value in values]


def _ts_zscore(values: Sequence[float], window: int) -> list[float]:
    output: list[float] = []
    for index, value in enumerate(values):
        window_values = _window_slice(values, index, window)
        if _contains_nonfinite(window_values):
            output.append(math.nan)
            continue
        mean_value = statistics.mean(window_values) if window_values else 0.0
        std_value = (
            statistics.pstdev(window_values) if len(window_values) >= 2 else 0.0
        )
        if std_value <= 1e-12:
            output.append(0.0)
        else:
            output.append((float(value) - mean_value) / std_value)
    return output


def _neutralize(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    mean_value = statistics.mean(values)
    return [float(value) - mean_value for value in values]


def _scale(values: Sequence[float], scale_to: float = 1.0) -> list[float]:
    denominator = sum(abs(float(value)) for value in values)
    if denominator <= 1e-12:
        return [0.0 for _ in values]
    return [float(value) * scale_to / denominator for value in values]


def _quantile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    clipped = min(max(quantile, 0.0), 1.0)
    position = clipped * (len(ordered) - 1)
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return ordered[lower_index]
    weight = position - lower_index
    return (ordered[lower_index] * (1.0 - weight)) + (ordered[upper_index] * weight)


def _winsorize(
    values: Sequence[float],
    lower_quantile: float = 0.05,
    upper_quantile: float = 0.95,
) -> list[float]:
    lower = _quantile(values, lower_quantile)
    upper = _quantile(values, upper_quantile)
    if lower > upper:
        lower, upper = upper, lower
    return [min(max(float(value), lower), upper) for value in values]


def _winsorized_rank(
    values: Sequence[float],
    lower_quantile: float = 0.05,
    upper_quantile: float = 0.95,
) -> list[float]:
    return _rank(_winsorize(values, lower_quantile, upper_quantile))


def _signed_power(values: Sequence[float], exponent: float = 2.0) -> list[float]:
    bounded_exponent: float = min(max(abs(float(exponent)), 0.0), 8.0)
    output: list[float] = []
    for value in values:
        clean_value = float(value)
        if not math.isfinite(clean_value):
            clean_value = 0.0
        sign = -1.0 if clean_value < 0.0 else 1.0
        powered_value = sign * math.pow(abs(clean_value), bounded_exponent)
        output.append(powered_value)
    return output


def _sign(values: Sequence[float]) -> list[float]:
    output: list[float] = []
    for value in values:
        if value > 0:
            output.append(1.0)
        elif value < 0:
            output.append(-1.0)
        else:
            output.append(0.0)
    return output


def _log(values: Sequence[float]) -> list[float]:
    return [
        math.log(value) if value > 0 and math.isfinite(value) else 0.0
        for value in values
    ]


def _sqrt(values: Sequence[float]) -> list[float]:
    return [
        math.sqrt(value) if value >= 0 and math.isfinite(value) else 0.0
        for value in values
    ]


def _abs(values: Sequence[float]) -> list[float]:
    return [abs(float(value)) for value in values]


def _binary_operator_symbol(node: ast.operator) -> str:
    if isinstance(node, ast.Add):
        return "+"
    if isinstance(node, ast.Sub):
        return "-"
    if isinstance(node, ast.Mult):
        return "*"
    if isinstance(node, ast.Div):
        return "/"
    raise ValidationError(
        f"Unsupported DSL arithmetic operator: {node.__class__.__name__}"
    )


def _numeric_constant(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValidationError("DSL constants must be numeric")
    return float(value)


def _normalize_constant(value: object) -> int | float:
    number = _numeric_constant(value)
    return int(number) if number.is_integer() else number


def _node_depth(normalized: Mapping[str, object]) -> int:
    node_type = str(normalized.get("type", ""))
    if node_type in {"field", "constant"}:
        return 1
    if node_type == "unary":
        operand = cast(Mapping[str, object], normalized.get("operand", {}))
        return 1 + _node_depth(operand)
    if node_type == "binary":
        left = cast(Mapping[str, object], normalized.get("left", {}))
        right = cast(Mapping[str, object], normalized.get("right", {}))
        return 1 + max(_node_depth(left), _node_depth(right))
    if node_type == "call":
        args = cast(list[object], normalized.get("args", []))
        if not args:
            return 1
        return 1 + max(_node_depth(cast(Mapping[str, object], arg)) for arg in args)
    return 1


def _node_count(normalized: Mapping[str, object]) -> int:
    node_type = str(normalized.get("type", ""))
    if node_type in {"field", "constant"}:
        return 1
    if node_type == "unary":
        operand = cast(Mapping[str, object], normalized.get("operand", {}))
        return 1 + _node_count(operand)
    if node_type == "binary":
        left = cast(Mapping[str, object], normalized.get("left", {}))
        right = cast(Mapping[str, object], normalized.get("right", {}))
        return 1 + _node_count(left) + _node_count(right)
    if node_type == "call":
        return 1 + sum(
            _node_count(cast(Mapping[str, object], arg))
            for arg in cast(list[object], normalized.get("args", []))
        )
    return 1


def _extract_window_ref(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant):
        return max(1, int(_numeric_constant(node.value)))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        if isinstance(node.operand, ast.Constant):
            return max(1, abs(int(_numeric_constant(node.operand.value))))
    return None


class _DSLNormalizer:
    def __init__(self):
        self.operators: set[str] = set()
        self.fields: set[str] = set()
        self.windows: set[int] = set()

    def normalize(self, node: ast.AST) -> dict[str, object]:
        if isinstance(node, ast.Expression):
            return self.normalize(node.body)
        if isinstance(node, ast.Name):
            self.fields.add(node.id)
            return {"type": "field", "name": node.id}
        if isinstance(node, ast.Constant):
            return {"type": "constant", "value": _normalize_constant(node.value)}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            self.operators.add("unary-")
            return {"type": "unary", "op": "-", "operand": self.normalize(node.operand)}
        if isinstance(node, ast.BinOp):
            operator = _binary_operator_symbol(node.op)
            self.operators.add(operator)
            return {
                "type": "binary",
                "op": operator,
                "left": self.normalize(node.left),
                "right": self.normalize(node.right),
            }
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            operator = node.func.id
            self.operators.add(operator)
            window_arg_index = _WINDOW_ARGUMENT_INDEX.get(operator)
            if window_arg_index is not None and len(node.args) > window_arg_index:
                window_ref = _extract_window_ref(node.args[window_arg_index])
                if window_ref is not None:
                    self.windows.add(window_ref)
            return {
                "type": "call",
                "operator": operator,
                "args": [self.normalize(argument) for argument in node.args],
            }
        raise ValidationError(f"Unsafe DSL node: {node.__class__.__name__}")


def analyze_expression(expression: str) -> DSLAnalysis:
    """Parse, validate, normalize, and score a Formulaic DSL expression."""

    dsl = FormulaicAlphaDSL(expression)
    return dsl.analysis


class FormulaicAlphaDSL:
    """Parse and evaluate a safe Alpha101-style expression grammar."""

    def __init__(self, expression: str):
        self.expression: str = expression.strip()
        if not self.expression:
            raise ValidationError("DSL expression is required")
        try:
            self._tree: ast.Expression = ast.parse(self.expression, mode="eval")
        except SyntaxError as exc:
            raise ValidationError(f"Invalid DSL expression: {self.expression}") from exc
        self._validate(self._tree)
        normalizer = _DSLNormalizer()
        normalized_ast = normalizer.normalize(self._tree)
        normalized_json = json.dumps(
            normalized_ast,
            sort_keys=True,
            separators=(",", ":"),
        )
        node_count = _node_count(normalized_ast)
        max_depth = _node_depth(normalized_ast)
        complexity_score = round(
            node_count + (0.5 * len(normalizer.windows)) + (0.25 * max_depth),
            6,
        )
        self.analysis: DSLAnalysis = DSLAnalysis(
            normalized_ast=normalized_ast,
            operator_list=sorted(normalizer.operators),
            field_refs=sorted(normalizer.fields),
            window_refs=sorted(normalizer.windows),
            node_count=node_count,
            max_depth=max_depth,
            complexity_score=complexity_score,
            expression_hash=hashlib.sha256(normalized_json.encode()).hexdigest()[:16],
        )

    def _validate(self, node: ast.AST) -> None:
        if isinstance(node, ast.Expression):
            self._validate(node.body)
            return
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValidationError("DSL only allows direct function calls")
            if node.func.id not in _FUNCTION_OPERATORS:
                raise ValidationError(f"Unsupported DSL operator: {node.func.id}")
            for argument in node.args:
                self._validate(argument)
            if node.keywords:
                raise ValidationError("DSL keyword arguments are not supported")
            return
        if isinstance(node, ast.BinOp):
            _ = _binary_operator_symbol(node.op)
            self._validate(node.left)
            self._validate(node.right)
            return
        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, ast.USub):
                raise ValidationError("DSL only supports unary minus")
            self._validate(node.operand)
            return
        if isinstance(node, ast.Name):
            if node.id.startswith("__"):
                raise ValidationError(f"Unsafe DSL field reference: {node.id}")
            return
        if isinstance(node, ast.Constant):
            _ = _numeric_constant(node.value)
            return
        raise ValidationError(f"Unsafe DSL node: {node.__class__.__name__}")

    def _eval_node(self, node: ast.AST, rows: Sequence[Mapping[str, object]]) -> object:
        if isinstance(node, ast.Expression):
            return self._eval_node(node.body, rows)
        if isinstance(node, ast.Name):
            return _float_series(rows, node.id)
        if isinstance(node, ast.Constant):
            return _numeric_constant(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            value = self._eval_node(node.operand, rows)
            if isinstance(value, list):
                return [-float(item) for item in cast(list[float], value)]
            return -self._as_float(value)
        if isinstance(node, ast.BinOp):
            return self._apply_binary_operator(
                _binary_operator_symbol(node.op),
                self._eval_node(node.left, rows),
                self._eval_node(node.right, rows),
                len(rows),
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            operator = node.func.id
            args = [self._eval_node(argument, rows) for argument in node.args]
            return self._apply_operator(operator, args)
        raise ValidationError("Invalid DSL expression node")

    @staticmethod
    def _as_series(value: object) -> list[float]:
        if isinstance(value, list):
            return [float(str(item)) for item in cast(list[object], value)]
        raise ValidationError("DSL operator expected a series argument")

    @staticmethod
    def _as_float(value: object) -> float:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        raise ValidationError("DSL operator expected a numeric argument")

    @staticmethod
    def _as_int(value: object) -> int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float):
            return int(value)
        raise ValidationError("DSL operator expected an integer argument")

    @classmethod
    def _broadcast(cls, value: object, row_count: int) -> list[float]:
        if isinstance(value, list):
            return [float(str(item)) for item in cast(list[object], value)]
        return [cls._as_float(value)] * row_count

    @classmethod
    def _apply_binary_operator(
        cls,
        operator: str,
        left: object,
        right: object,
        row_count: int,
    ) -> object:
        left_is_series = isinstance(left, list)
        right_is_series = isinstance(right, list)
        if not left_is_series and not right_is_series:
            left_float = cls._as_float(left)
            right_float = cls._as_float(right)
            if operator == "+":
                return left_float + right_float
            if operator == "-":
                return left_float - right_float
            if operator == "*":
                return left_float * right_float
            if operator == "/":
                return _safe_divide(left_float, right_float)
        left_values = cls._broadcast(left, row_count)
        right_values = cls._broadcast(right, row_count)
        if len(left_values) != len(right_values):
            raise ValidationError("DSL arithmetic operands have incompatible lengths")
        output: list[float] = []
        for left_value, right_value in zip(left_values, right_values, strict=False):
            if operator == "+":
                output.append(left_value + right_value)
            elif operator == "-":
                output.append(left_value - right_value)
            elif operator == "*":
                output.append(left_value * right_value)
            elif operator == "/":
                output.append(_safe_divide(left_value, right_value))
            else:
                raise ValidationError(
                    f"Unsupported DSL arithmetic operator: {operator}"
                )
        return output

    def _apply_operator(self, operator: str, args: list[object]) -> list[float]:
        if operator == "rank" and len(args) == 1:
            return _rank(self._as_series(args[0]))
        if operator == "ts_rank" and len(args) == 2:
            return _ts_rank(self._as_series(args[0]), self._as_int(args[1]))
        if operator == "delay" and len(args) == 2:
            return _delay(self._as_series(args[0]), self._as_int(args[1]))
        if operator == "delta" and len(args) == 2:
            return _delta(self._as_series(args[0]), self._as_int(args[1]))
        if operator == "corr" and len(args) == 3:
            return _corr(
                self._as_series(args[0]),
                self._as_series(args[1]),
                self._as_int(args[2]),
            )
        if operator == "cov" and len(args) == 3:
            return _cov(
                self._as_series(args[0]),
                self._as_series(args[1]),
                self._as_int(args[2]),
            )
        if operator == "decay" and len(args) == 2:
            return _decay(self._as_series(args[0]), self._as_int(args[1]))
        if operator == "decay_linear" and len(args) == 2:
            return _decay(self._as_series(args[0]), self._as_int(args[1]))
        if operator == "zscore" and len(args) == 1:
            return _zscore(self._as_series(args[0]))
        if operator == "ts_zscore" and len(args) == 2:
            return _ts_zscore(self._as_series(args[0]), self._as_int(args[1]))
        if operator == "neutralize" and len(args) == 1:
            return _neutralize(self._as_series(args[0]))
        if operator == "scale" and len(args) in {1, 2}:
            scale_to = self._as_float(args[1]) if len(args) == 2 else 1.0
            return _scale(self._as_series(args[0]), scale_to)
        if operator == "winsorize" and len(args) in {1, 3}:
            if len(args) == 3:
                return _winsorize(
                    self._as_series(args[0]),
                    self._as_float(args[1]),
                    self._as_float(args[2]),
                )
            return _winsorize(self._as_series(args[0]))
        if operator == "winsorized_rank" and len(args) in {1, 3}:
            if len(args) == 3:
                return _winsorized_rank(
                    self._as_series(args[0]),
                    self._as_float(args[1]),
                    self._as_float(args[2]),
                )
            return _winsorized_rank(self._as_series(args[0]))
        if operator == "signed_power" and len(args) in {1, 2}:
            exponent = self._as_float(args[1]) if len(args) == 2 else 2.0
            return _signed_power(self._as_series(args[0]), exponent)
        if operator == "abs" and len(args) == 1:
            return _abs(self._as_series(args[0]))
        if operator == "sign" and len(args) == 1:
            return _sign(self._as_series(args[0]))
        if operator == "log" and len(args) == 1:
            return _log(self._as_series(args[0]))
        if operator == "sqrt" and len(args) == 1:
            return _sqrt(self._as_series(args[0]))
        if operator in {"mean", "std", "sum", "product"} and len(args) in {1, 2}:
            window = self._as_int(args[1]) if len(args) == 2 else None
            return _rolling_stat(self._as_series(args[0]), window, operator)
        raise ValidationError(f"Invalid argument count for DSL operator: {operator}")

    def evaluate(self, rows: Sequence[Mapping[str, object]]) -> list[float]:
        """Evaluate expression against ordered row mappings."""

        raw = self._eval_node(self._tree, rows)
        values = self._broadcast(raw, len(rows))
        return [round(_clean_float(float(value)), 6) for value in values]

    def evaluate_panel(self, rows: Sequence[Mapping[str, object]]) -> list[float]:
        """Evaluate expression on a symbol/date panel.

        Time-series operators are applied within each symbol. Cross-sectional
        operators such as ``rank`` and ``zscore`` are applied within each
        timestamp. The returned values are aligned to the input row order.
        """

        raw = self._eval_panel_node(self._tree, rows)
        values = self._broadcast(raw, len(rows))
        return [round(_clean_float(float(value)), 6) for value in values]

    def _eval_panel_node(
        self,
        node: ast.AST,
        rows: Sequence[Mapping[str, object]],
    ) -> object:
        if isinstance(node, ast.Expression):
            return self._eval_panel_node(node.body, rows)
        if isinstance(node, ast.Name):
            return _float_series(rows, node.id)
        if isinstance(node, ast.Constant):
            return _numeric_constant(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            value = self._eval_panel_node(node.operand, rows)
            if isinstance(value, list):
                return [-float(item) for item in cast(list[float], value)]
            return -self._as_float(value)
        if isinstance(node, ast.BinOp):
            return self._apply_binary_operator(
                _binary_operator_symbol(node.op),
                self._eval_panel_node(node.left, rows),
                self._eval_panel_node(node.right, rows),
                len(rows),
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            operator = node.func.id
            args = [self._eval_panel_node(argument, rows) for argument in node.args]
            if operator in _CROSS_SECTIONAL_OPERATORS:
                return self._apply_cross_sectional_operator(operator, args, rows)
            if operator in _TIME_SERIES_OPERATORS:
                return self._apply_time_series_operator(operator, args, rows)
            if operator in _ELEMENTWISE_OPERATORS:
                return self._apply_operator(operator, args)
            return self._apply_operator(operator, args)
        raise ValidationError("Invalid DSL expression node")

    @staticmethod
    def _group_indices(
        rows: Sequence[Mapping[str, object]],
        key_name: str,
    ) -> dict[str, list[int]]:
        groups: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(rows):
            if key_name == "symbol":
                key = str(row.get("symbol") or row.get("asset_id") or "")
            else:
                key = str(row.get("timestamp") or row.get("asof_date") or "")
            if not key:
                raise ValidationError(f"DSL panel row is missing {key_name}")
            groups[key].append(index)
        return groups

    @classmethod
    def _cross_sectional_apply(
        cls,
        values: Sequence[float],
        rows: Sequence[Mapping[str, object]],
        reducer: str,
        extra_args: Sequence[object],
    ) -> list[float]:
        output = [0.0] * len(rows)
        for indices in cls._group_indices(rows, "timestamp").values():
            group_values = [float(values[index]) for index in indices]
            if reducer == "rank":
                group_output = _rank(group_values)
            elif reducer == "zscore":
                group_output = _zscore(group_values)
            elif reducer == "neutralize":
                group_output = _neutralize(group_values)
            elif reducer == "scale":
                scale_to = cls._as_float(extra_args[0]) if extra_args else 1.0
                group_output = _scale(group_values, scale_to)
            elif reducer == "winsorize":
                lower = cls._as_float(extra_args[0]) if len(extra_args) == 2 else 0.05
                upper = cls._as_float(extra_args[1]) if len(extra_args) == 2 else 0.95
                group_output = _winsorize(group_values, lower, upper)
            elif reducer == "winsorized_rank":
                lower = cls._as_float(extra_args[0]) if len(extra_args) == 2 else 0.05
                upper = cls._as_float(extra_args[1]) if len(extra_args) == 2 else 0.95
                group_output = _winsorized_rank(group_values, lower, upper)
            else:
                raise ValidationError(f"Unsupported cross-sectional reducer: {reducer}")
            for index, value in zip(indices, group_output, strict=False):
                output[index] = value
        return output

    def _apply_cross_sectional_operator(
        self,
        operator: str,
        args: list[object],
        rows: Sequence[Mapping[str, object]],
    ) -> list[float]:
        if operator in {"rank", "zscore", "neutralize"} and len(args) == 1:
            return self._cross_sectional_apply(
                self._as_series(args[0]),
                rows,
                operator,
                [],
            )
        if operator == "scale" and len(args) in {1, 2}:
            return self._cross_sectional_apply(
                self._as_series(args[0]),
                rows,
                operator,
                args[1:],
            )
        if operator in {"winsorize", "winsorized_rank"} and len(args) in {1, 3}:
            return self._cross_sectional_apply(
                self._as_series(args[0]),
                rows,
                operator,
                args[1:],
            )
        raise ValidationError(f"Invalid argument count for DSL operator: {operator}")

    @classmethod
    def _time_series_apply(
        cls,
        rows: Sequence[Mapping[str, object]],
        values: Sequence[float],
        reducer: str,
        extra_args: Sequence[object],
        right_values: Sequence[float] | None = None,
    ) -> list[float]:
        output = [0.0] * len(rows)
        for indices in cls._group_indices(rows, "symbol").values():
            ordered_indices = sorted(
                indices,
                key=lambda index: str(
                    rows[index].get("timestamp") or rows[index].get("asof_date") or ""
                ),
            )
            left_series = [float(values[index]) for index in ordered_indices]
            if reducer in {"delay", "delta", "mean", "std", "sum", "product"}:
                window = cls._as_int(extra_args[0]) if extra_args else None
                if reducer == "delay":
                    group_output = _delay(left_series, int(window or 0))
                elif reducer == "delta":
                    group_output = _delta(left_series, int(window or 0))
                else:
                    group_output = _rolling_stat(left_series, window, reducer)
            elif reducer in {"ts_rank", "ts_zscore", "decay", "decay_linear"}:
                window = cls._as_int(extra_args[0])
                if reducer == "ts_rank":
                    group_output = _ts_rank(left_series, window)
                elif reducer == "ts_zscore":
                    group_output = _ts_zscore(left_series, window)
                else:
                    group_output = _decay(left_series, window)
            elif reducer in {"corr", "cov"}:
                if right_values is None:
                    raise ValidationError(f"{reducer} requires two series arguments")
                right_series = [float(right_values[index]) for index in ordered_indices]
                window = cls._as_int(extra_args[0])
                group_output = (
                    _corr(left_series, right_series, window)
                    if reducer == "corr"
                    else _cov(left_series, right_series, window)
                )
            else:
                raise ValidationError(f"Unsupported time-series reducer: {reducer}")
            for index, value in zip(ordered_indices, group_output, strict=False):
                output[index] = value
        return output

    def _apply_time_series_operator(
        self,
        operator: str,
        args: list[object],
        rows: Sequence[Mapping[str, object]],
    ) -> list[float]:
        if operator in {"delay", "delta", "mean", "std", "sum", "product"} and len(
            args
        ) in {1, 2}:
            return self._time_series_apply(
                rows,
                self._as_series(args[0]),
                operator,
                args[1:],
            )
        if operator in {"ts_rank", "ts_zscore", "decay", "decay_linear"} and len(
            args
        ) == 2:
            return self._time_series_apply(
                rows,
                self._as_series(args[0]),
                operator,
                args[1:],
            )
        if operator in {"corr", "cov"} and len(args) == 3:
            return self._time_series_apply(
                rows,
                self._as_series(args[0]),
                operator,
                args[2:],
                right_values=self._as_series(args[1]),
            )
        raise ValidationError(f"Invalid argument count for DSL operator: {operator}")


def factor_spec_from_dsl(
    *,
    expression: str,
    name: str,
    spec_version: str | None = None,
    source_family: str = PRICE_VOLUME_SOURCE_FAMILY,
) -> FactorSpec:
    """Generate a versioned FactorSpec from a validated DSL expression."""

    dsl = FormulaicAlphaDSL(expression)
    resolved_source_family = validate_source_family(
        source_family, context="dsl_factor_spec"
    )
    version = spec_version or f"fac_dsl_{dsl.analysis.expression_hash}@1.0"
    input_field_lineage = {
        field: f"dataset.rows[].{field}" for field in dsl.analysis.field_refs
    }
    input_field_lineage["expression"] = expression
    return FactorSpec(
        spec_id=version,
        spec_version=version,
        name=name,
        description=f"Formulaic Alpha DSL factor: {expression}",
        factor_type="formulaic_dsl",
        callable_ref="factor_lab.factor_engine.dsl:FormulaicAlphaDSL",
        dsl_expression=dsl.expression,
        input_schema={
            "expression": expression,
            "pit_required": True,
            "field_refs": dsl.analysis.field_refs,
            "window_refs": dsl.analysis.window_refs,
            "nan_policy": DEFAULT_NAN_POLICY,
        },
        output_schema={"factor_name": name, "factor_type": "float"},
        parameters={
            "operators": dsl.analysis.operator_list,
            "allowed_operators": allowed_operator_names(),
            "operator_set_version": OPERATOR_SET_VERSION,
        },
        source_family=resolved_source_family,
        input_field_lineage=input_field_lineage,
        tags={"library": "formulaic_alpha_dsl", "req": "REQ-001"},
        dsl_ast_version=DSL_AST_VERSION,
        operator_set_version=OPERATOR_SET_VERSION,
        expression_hash=dsl.analysis.expression_hash,
        complexity_score=dsl.analysis.complexity_score,
        field_refs=dsl.analysis.field_refs,
        window_refs=dsl.analysis.window_refs,
        nan_policy=DEFAULT_NAN_POLICY,
        normalized_ast=dsl.analysis.normalized_ast,
        operator_list=dsl.analysis.operator_list,
    )


def build_dsl_factor_frame(
    rows: Sequence[Mapping[str, object]],
    *,
    factor_spec: FactorSpec,
    source_refs: Sequence[str],
) -> list[dict[str, object]]:
    """Build a factor frame for a registered DSL FactorSpec."""

    if factor_spec.dsl_expression is None:
        raise ValidationError("DSL factor spec is missing dsl_expression")
    expression = FormulaicAlphaDSL(factor_spec.dsl_expression)
    source_ref_list = list(dict.fromkeys(str(ref) for ref in source_refs))
    factor_name = str(factor_spec.output_schema.get("factor_name") or factor_spec.name)
    ordered_rows: list[Mapping[str, object]] = []
    for row in rows:
        symbol = str(row.get("symbol") or row.get("asset_id") or "")
        if not symbol:
            raise ValidationError("DSL source row is missing symbol/asset_id")
        ordered_rows.append(row)
    ordered_rows = sorted(
        ordered_rows,
        key=lambda row: (
            str(row.get("symbol") or row.get("asset_id") or ""),
            str(row.get("timestamp") or row.get("asof_date") or ""),
        ),
    )
    values = expression.evaluate_panel(ordered_rows)
    factor_rows: list[dict[str, object]] = []
    for row, value in zip(ordered_rows, values, strict=False):
        symbol = str(row.get("symbol") or row.get("asset_id") or "")
        factor_rows.append(
            {
                "symbol": symbol,
                "timestamp": str(row["timestamp"]),
                "asof_date": str(row.get("asof_date", row["timestamp"])),
                "available_at": str(row.get("available_at", row["timestamp"])),
                "factor_value": round(float(value), 6),
                "factor_name": factor_name,
                "factor_spec_version": factor_spec.spec_version,
                "source_family": factor_spec.source_family,
                "source_refs": source_ref_list,
                "input_field_lineage": {
                    **factor_spec.input_field_lineage,
                    "source_refs": ",".join(source_ref_list),
                },
                "asset_kind": str(
                    row.get("asset_kind")
                    or row.get("instrument_type")
                    or "tradable_instrument"
                ),
                "is_self_built_asset": bool(
                    row.get("is_self_built_asset", False)
                ),
                "dsl_expression_snapshot": factor_spec.dsl_expression,
                "normalized_ast": factor_spec.normalized_ast,
                "operator_list": factor_spec.operator_list,
                "field_refs": factor_spec.field_refs,
                "window_refs": factor_spec.window_refs,
                "complexity_score": factor_spec.complexity_score,
                "nan_policy": factor_spec.nan_policy,
                "expression_hash": factor_spec.expression_hash,
            }
        )
    return factor_rows
