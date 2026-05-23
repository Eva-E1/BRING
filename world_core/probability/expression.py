"""Safe expression evaluator for probability formulas."""
import ast
import math
import operator
from typing import Dict, Any, Callable

# Safe math functions
ALLOWED_MATH_FUNCTIONS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "sqrt": math.sqrt,
    "pow": pow,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "radians": math.radians,
    "degrees": math.degrees,
    "factorial": math.factorial,
    "gcd": math.gcd,
    "isfinite": math.isfinite,
    "isinf": math.isinf,
    "isnan": math.isnan,
}

# Safe operators
ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
    ast.And: lambda a, b: a and b,
    ast.Or: lambda a, b: a or b,
}


def safe_eval(expr: str, context: Dict[str, float]) -> float:
    """
    Safely evaluate a mathematical expression with context variables.

    Args:
        expr: Mathematical expression string (e.g., "health * 0.5 + luck")
        context: Dictionary of variable names to values

    Returns:
        The result of the expression as a float

    Raises:
        ValueError: If the expression contains unsafe operations
        SyntaxError: If the expression has invalid syntax
    """
    if not expr or not expr.strip():
        return 0.0

    # Build the namespace with allowed functions and context variables
    namespace = ALLOWED_MATH_FUNCTIONS.copy()
    namespace.update(context)
    namespace["True"] = True
    namespace["False"] = False
    namespace["pi"] = math.pi
    namespace["e"] = math.e

    # Parse the expression to AST for safety checking
    try:
        parsed = ast.parse(expr.strip(), "<probability_expression>", "eval")
    except SyntaxError as e:
        raise SyntaxError(f"Invalid expression syntax: {e}") from e

    # Walk the AST to check for unsafe operations
    for node in ast.walk(parsed):
        # Check for function calls (only allowed math functions)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name not in ALLOWED_MATH_FUNCTIONS and func_name not in context:
                    raise ValueError(f"Unsafe function call: {func_name}")
            elif isinstance(node.func, ast.Attribute):
                # Disallow attribute access (e.g., obj.method)
                raise ValueError(f"Unsafe attribute access: {node.func.attr}")

        # Check for name references
        if isinstance(node, ast.Name):
            if node.id not in namespace:
                raise ValueError(f"Unknown variable: {node.id}")

        # Disallow subscript operations
        if isinstance(node, ast.Subscript):
            raise ValueError("Subscript operations are not allowed")

        # Disallow lambda functions
        if isinstance(node, ast.Lambda):
            raise ValueError("Lambda functions are not allowed")

        # Disallow comprehensions
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            raise ValueError("Comprehensions are not allowed")

        # Disallow await/async
        if isinstance(node, (ast.Await, ast.AsyncFor, ast.AsyncWith, ast.AsyncFunctionDef)):
            raise ValueError("Async operations are not allowed")

    # Safe to evaluate
    try:
        compiled = compile(parsed, "<probability_expression>", "eval")
        result = eval(compiled, {"__builtins__": {}}, namespace)
    except Exception as e:
        raise ValueError(f"Expression evaluation failed: {e}") from e

    # Convert to float
    try:
        return float(result)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Expression result is not numeric: {result}") from e


def create_evaluator(context: Dict[str, float]) -> Callable[[str], float]:
    """
    Create a partial evaluator function with pre-bound context.

    Args:
        context: Variable names to values

    Returns:
        Function that takes an expression string and returns a float
    """
    def evaluator(expr: str) -> float:
        return safe_eval(expr, context)
    return evaluator
