from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP("arith")


def _as_number(x):
    """
    Accept int, float or numeric string.
    Raise clean error otherwise.
    """
    if isinstance(x, bool):
       raise TypeError("Boolean values are not valid numbers.")
    
    if isinstance(x, (int, float)):
        return float(x)

    if isinstance(x, str):
        try:
            return float(x.strip())
        except ValueError:
            raise ValueError(f"'{x}' is not a valid number.")

    raise TypeError("Expected int, float or numeric string.")


@mcp.tool()
async def add(a: float, b: float) -> float:
    """Return a + b."""
    return _as_number(a) + _as_number(b)


@mcp.tool()
async def subtract(a: float, b: float) -> float:
    """Return a - b."""
    return _as_number(a) - _as_number(b)


@mcp.tool()
async def multiply(a: float, b: float) -> float:
    """Return a * b."""
    return _as_number(a) * _as_number(b)


@mcp.tool()
async def divide(a: float, b: float) -> float:
    """Return a / b."""
    a = _as_number(a)
    b = _as_number(b)

    if b == 0:
        raise ValueError("Division by zero is not allowed.")

    return a / b


@mcp.tool()
async def modulus(a: float, b: float) -> float:
    """Return a % b."""
    a = _as_number(a)
    b = _as_number(b)

    if b == 0:
        raise ValueError("Modulo by zero is not allowed.")

    return a % b


@mcp.tool()
async def power(a: float, b: float) -> float:
    """Return a raised to the power b."""

    a = _as_number(a)
    b = _as_number(b)

    result = a ** b

    if isinstance(result, complex):
        raise ValueError("The result must be a real number.")

    return result

@mcp.tool()
async def square_root(x: float) -> float:
    """Return square root of x."""
    x = _as_number(x)

    if x < 0:
        raise ValueError("Cannot take square root of a negative number.")

    return x ** 0.5


@mcp.tool()
async def absolute(x: float) -> float:
    """Return absolute value."""
    return abs(_as_number(x))


if __name__ == "__main__":
    mcp.run()