
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from fastmcp import FastMCP

mcp = FastMCP("MultiMind Tools")



@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


@mcp.tool()
def subtract(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


@mcp.tool()
def divide(a: float, b: float) -> float:
    """Divide a by b."""
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b


@mcp.tool()
def modulus(a: float, b: float) -> float:
    """Return the remainder when a is divided by b."""
    if b == 0:
        raise ValueError("Cannot calculate modulus with zero.")
    return a % b


@mcp.tool()
def power(a: float, b: float) -> float:
    """Raise a to the power b."""
    result = a ** b
    if isinstance(result, complex):
        raise ValueError("Complex results are not supported.")
    return result


@mcp.tool()
def square_root(number: float) -> float:
    """Calculate the square root of a non-negative number."""
    if number < 0:
        raise ValueError("Cannot calculate the real square root of a negative number.")
    return math.sqrt(number)


@mcp.tool()
def absolute(number: float) -> float:
    """Return the absolute value of a number."""
    return abs(number)



@mcp.tool()
def get_current_datetime(timezone: str = "Asia/Kolkata") -> str:
    """Get the current date and time in a specified IANA timezone."""
    try:
        now = datetime.now(ZoneInfo(timezone))
        return now.strftime("%A, %d %B %Y, %I:%M:%S %p %Z")
    except Exception as exc:
        raise ValueError(
            f"Invalid or unavailable timezone: {timezone}"
        ) from exc


@mcp.tool()
def calculate_date_difference(
    start_date: str,
    end_date: str
) -> int:
    """Calculate the number of days between two dates in YYYY-MM-DD format."""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        return (end - start).days
    except ValueError as exc:
        raise ValueError(
            "Dates must use the YYYY-MM-DD format."
        ) from exc


# ---------------- TEXT UTILITY TOOLS ----------------

@mcp.tool()
def count_words(text: str) -> int:
    """Count the words in a text."""
    return len(text.split())


@mcp.tool()
def count_characters(text: str) -> int:
    """Count characters, including spaces and punctuation."""
    return len(text)


@mcp.tool()
def reverse_text(text: str) -> str:
    """Reverse a string."""
    return text[::-1]


@mcp.tool()
def convert_text_case(
    text: str,
    case: str
) -> str:
    """Convert text to uppercase, lowercase, title case, or sentence case."""
    case = case.strip().lower()

    conversions = {
        "upper": str.upper,
        "uppercase": str.upper,
        "lower": str.lower,
        "lowercase": str.lower,
        "title": str.title,
        "sentence": str.capitalize,
    }

    converter = conversions.get(case)
    if converter is None:
        raise ValueError(
            "Supported cases: upper, lower, title, sentence."
        )

    return converter(text)


# ---------------- UNIT CONVERSION TOOLS ----------------

@mcp.tool()
def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert a temperature from Celsius to Fahrenheit."""
    return (celsius * 9 / 5) + 32


@mcp.tool()
def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert a temperature from Fahrenheit to Celsius."""
    return (fahrenheit - 32) * 5 / 9


@mcp.tool()
def kilometers_to_miles(kilometers: float) -> float:
    """Convert kilometers to miles."""
    return kilometers * 0.621371


@mcp.tool()
def miles_to_kilometers(miles: float) -> float:
    """Convert miles to kilometers."""
    return miles / 0.621371


@mcp.tool()
def kilograms_to_pounds(kilograms: float) -> float:
    """Convert kilograms to pounds."""
    return kilograms * 2.2046226218


@mcp.tool()
def pounds_to_kilograms(pounds: float) -> float:
    """Convert pounds to kilograms."""
    return pounds / 2.2046226218


# ---------------- SERVER ENTRY POINT ----------------

if __name__ == "__main__":
    mcp.run()
