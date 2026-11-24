"""JARVIS maths v7. Fixed unit conversions plus an isolated symbolic worker.
number() remains compatible with existing volume controls. No eval or LLM.
"""
from decimal import Decimal, InvalidOperation, localcontext
import re

from jarvis_time import integer, ParseError

D = Decimal


def normal(text):
    text = text.casefold().replace("\u2019", "'")
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text)
    return " ".join(text.strip(" ,?!").split()).rstrip(".")


def number(text):
    text = normal(text)
    sign = 1
    if text.startswith(("minus ", "negative ")):
        text = text.split(" ", 1)[1]
        sign = -1
    elif text.startswith("-"):
        text = text[1:].strip()
        sign = -1
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        value = D(text)
    elif text in {"half", "a half"}:
        value = D("0.5")
    elif text.endswith(" and a half"):
        value = D(integer(text[:-11])) + D("0.5")
    elif " point " in text or text.startswith("point "):
        whole, fraction = ("zero " + text if text.startswith("point ") else text).split(" point ", 1)
        tokens = fraction.split()
        if len(tokens) == 1 and tokens[0].isdigit():
            digits = tokens[0]
        else:
            digits = ""
            for token in tokens:
                value = integer(token)
                if not 0 <= value <= 9:
                    raise ParseError("Say decimal digits individually after point")
                digits += str(value)
        if not digits or len(digits) > 12:
            raise ParseError("Please use at most twelve decimal places")
        value = D(integer(whole)) + D("0." + digits)
    else:
        value = D(integer(text))
    value *= sign
    if abs(value) > D("1e12") or (value and abs(value) < D("1e-12")):
        raise ParseError("That number is outside this basic calculator's range")
    return value


def formatted(value):
    with localcontext() as context:
        context.prec = 60
        rounded = value.quantize(D("0.00000001"))
    if not rounded:
        rounded = D(0)
    text = format(rounded, "f").rstrip("0").rstrip(".")
    return text or "0"


# Factors convert to metres, kilograms or litres within each dimension.
UNITS = {
    "millimetres": ("length", D("0.001")),
    "centimetres": ("length", D("0.01")),
    "metres": ("length", D("1")),
    "kilometres": ("length", D("1000")),
    "inches": ("length", D("0.0254")),
    "feet": ("length", D("0.3048")),
    "yards": ("length", D("0.9144")),
    "miles": ("length", D("1609.344")),
    "milligrams": ("mass", D("0.000001")),
    "grams": ("mass", D("0.001")),
    "kilograms": ("mass", D("1")),
    "ounces": ("mass", D("0.028349523125")),
    "pounds": ("mass", D("0.45359237")),
    "tonnes": ("mass", D("1000")),
    "millilitres": ("volume", D("0.001")),
    "litres": ("volume", D("1")),
    "celsius": ("temperature", None),
    "fahrenheit": ("temperature", None),
    "kelvin": ("temperature", None),
}
ALIASES = {
    "millimeter": "millimetres", "millimeters": "millimetres", "millimetre": "millimetres", "mm": "millimetres",
    "centimeter": "centimetres", "centimeters": "centimetres", "centimetre": "centimetres", "cm": "centimetres",
    "meter": "metres", "meters": "metres", "metre": "metres",
    "kilometer": "kilometres", "kilometers": "kilometres", "kilometre": "kilometres", "km": "kilometres",
    "inch": "inches", "foot": "feet", "yard": "yards", "mile": "miles",
    "milligram": "milligrams", "mg": "milligrams", "gram": "grams",
    "kilogram": "kilograms", "kg": "kilograms", "kilo": "kilograms", "kilos": "kilograms",
    "ounce": "ounces", "pound": "pounds", "lb": "pounds", "lbs": "pounds", "tonne": "tonnes",
    "millilitre": "millilitres", "milliliter": "millilitres", "milliliters": "millilitres", "ml": "millilitres",
    "litre": "litres", "liter": "litres", "liters": "litres",
}
for unit in UNITS:
    ALIASES[unit] = unit
for unit in ("celsius", "fahrenheit", "kelvin"):
    ALIASES["degrees " + unit] = unit
    ALIASES["degree " + unit] = unit

UNIT_PATTERN = "(?:" + "|".join(
    re.escape(unit) for unit in sorted(ALIASES, key=len, reverse=True)
) + ")"


def convert(value, source, target):
    source, target = ALIASES[source], ALIASES[target]
    dimension, factor = UNITS[source]
    target_dimension, target_factor = UNITS[target]
    if dimension != target_dimension:
        raise ParseError("Those units measure different quantities")
    if dimension == "temperature":
        if source == "fahrenheit":
            celsius = (value - 32) * 5 / 9
        elif source == "kelvin":
            celsius = value - D("273.15")
        else:
            celsius = value
        if celsius < D("-273.15"):
            raise ParseError("That temperature is below absolute zero")
        if target == "fahrenheit":
            return celsius * 9 / 5 + 32, target
        if target == "kelvin":
            return celsius + D("273.15"), target
        return celsius, target
    return value * factor / target_factor, target



def is_math(command):
    text = command.casefold().replace("\u2019", "'").strip(" ?.")
    if text.startswith(("calculate ", "compute ", "evaluate ", "work out ", "convert ",
                        "solve ", "simplify ", "expand ", "factor ", "factorise ",
                        "factorize ", "differentiate ", "integrate ")):
        return True
    text = re.sub(r"^(?:what is |what's |whats )", "", text)
    return bool(re.match(
        r"^(?:[-+(\d.]|zero\b|one\b|two\b|three\b|four\b|five\b|six\b|seven\b|eight\b|nine\b"
        r"|ten\b|eleven\b|twelve\b|thirteen\b|fourteen\b|fifteen\b|sixteen\b|seventeen\b"
        r"|eighteen\b|nineteen\b|twenty\b|thirty\b|forty\b|fifty\b|sixty\b|seventy\b"
        r"|eighty\b|ninety\b|half\b|a half\b|point\b|negative\b|minus\b"
        r"|pi\b|e\b|x\b|sqrt\b|cbrt\b|sin\b|cos\b|tan\b|sine\b|cosine\b|tangent\b"
        r"|ln\b|log\b|abs\b|exp\b|natural log\b|natural logarithm\b|logarithm\b"
        r"|(?:the )?(?:square root|cube root|absolute value|derivative|integral)\b)",
        text,
    ))


def symbolic_reply(command):
    import json
    from pathlib import Path
    import subprocess
    import sys

    worker = Path(__file__).resolve().with_name("jarvis_math_engine.py")
    if not worker.is_file():
        return "The new calculator file is missing. Check jarvis_math_engine.py, sir."
    try:
        completed = subprocess.run(
            [sys.executable, str(worker)],
            input=json.dumps({"command": command}),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=6, check=False, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.stderr:
            print(completed.stderr.strip(), flush=True)
        if completed.returncode:
            return "The calculator could not start. Check its terminal error and SymPy installation, sir."
        reply = json.loads(completed.stdout).get("reply")
        if not isinstance(reply, str) or not reply or len(reply) > 900:
            raise ValueError("Invalid calculator response")
        return reply
    except subprocess.TimeoutExpired:
        return "That calculation exceeded my six second limit, sir. Please use a smaller expression."
    except (OSError, ValueError):
        return "The calculator could not return an answer. Check the terminal, sir."


def calculator(command):
    if not is_math(command):
        return None
    if len(command) > 400:
        return "Please use a shorter expression, sir."
    text = normal(command)
    text = re.sub(r"^(?:what is |what's |whats |calculate |compute |evaluate |work out )", "", text)
    try:
        conversion = re.fullmatch(
            r"(?:convert )?(.+?)\s+(" + UNIT_PATTERN + r")\s+(?:to|in|into)\s+(" + UNIT_PATTERN + r")",
            text,
        )
        if conversion:
            with localcontext() as context:
                context.prec = 60
                value = number(conversion.group(1))
                source = conversion.group(2)
                result, target = convert(value, source, conversion.group(3))
                qualifier = "approximately " if D(formatted(result)) != result else ""
                return (
                    f"{formatted(value)} {ALIASES[source]} is {qualifier}"
                    f"{formatted(result)} {target}, sir."
                )
        if text.startswith("convert "):
            return "Try convert ten inches to centimetres, or thirty two Fahrenheit to Celsius, sir."
    except (ParseError, InvalidOperation, ValueError, OverflowError) as error:
        return f"{error}, sir."
    return symbolic_reply(command)


if __name__ == "__main__":
    print("Typed maths test. No microphone, GPU, speech, volume or app controls.")
    print("Type a maths command without Jarvis. Type quit to stop.")
    while True:
        try:
            command = input("Math> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if command.casefold() in {"quit", "exit"}:
            break
        print(calculator(command) or "Not a recognized maths command.")
