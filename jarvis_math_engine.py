"""Local, bounded symbolic calculator worker. No eval/exec/string SymPy parser.
Run by jarvis_math.py with a fixed Python executable, JSON input and a timeout.
"""
import json
import math
import re
import sys

import sympy as S

from jarvis_math import number
from jarvis_time import ParseError

X = S.Symbol("x", real=True)
MAX_TEXT = 400
MAX_TOKENS = 80
MAX_DIGITS = 300
FUNCTIONS = {"sqrt", "cbrt", "sin", "cos", "tan", "ln", "log", "abs", "exp"}
NUMBER_WORDS = set(
    ("zero one two three four five six seven eight nine ten eleven twelve "
     "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty "
     "thirty forty fifty sixty seventy eighty ninety hundred thousand "
     "and point half a").split()
)


class MathError(ValueError):
    pass


def clean(text):
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise MathError("Please use a shorter expression")
    text = text.casefold().replace("\u2019", "'")
    text = text.replace("\u2212", "-").replace("\u00d7", "*").replace("\u00f7", "/")
    # Keep decimal dots and factorials. Only sentence-final dots are removed.
    text = text.strip().rstrip(" ?.")
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text)
    text = re.sub(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?![\d,])",
                  lambda m: m.group().replace(",", ""), text)
    # Whisper can put a pause comma between a numeric coefficient and x.
    # Accept "5, x" as "5 x", but NEVER turn "5,6" into 56 or a decimal.
    text = re.sub(r"(?<=\d),\s*(?=x\b)", " ", text)
    return " ".join(text.split())


def translate(text):
    text = clean(text)
    phrases = {
        "to the power of": "^", "raised to the power of": "^",
        "raised to": "^", "to the power": "^",
        "multiplied by": "*", "divided by": "/",
        "open parenthesis": "(", "close parenthesis": ")",
        "open parentheses": "(", "close parentheses": ")",
        "open bracket": "(", "close bracket": ")",
        "square root of": "sqrt", "the square root of": "sqrt",
        "cube root of": "cbrt", "the cube root of": "cbrt",
        "absolute value of": "abs", "the absolute value of": "abs",
        "natural logarithm of": "ln", "natural log of": "ln",
        "logarithm of": "log", "log base ten of": "log",
        "log base 10 of": "log", "log of": "log",
        "sine of": "sin", "cosine of": "cos", "tangent of": "tan",
        "sin of": "sin", "cos of": "cos", "tan of": "tan",
        "sine": "sin", "cosine": "cos", "tangent": "tan",
        "plus": "+", "minus": "-", "negative": "-",
        "times": "*", "over": "/", "squared": "^ 2", "cubed": "^ 3",
        "factorial": "!", "per cent of": "% *", "percent of": "% *",
        "per cent": "%", "percent": "%", "equals": "=", "equal to": "=",
        "is equal to": "=", "pi": "pi",
    }
    for phrase in sorted(phrases, key=len, reverse=True):
        text = re.sub(r"\b" + re.escape(phrase) + r"\b", phrases[phrase], text)
    text = re.sub(r"%\s*of\b", "% *", text)
    text = text.replace("**", "^")
    if re.search(r"\d(?:\.\d+)?e[+-]?\d", text):
        raise MathError("Say scientific notation as a number times ten to a power")
    raw = re.findall(r"\d+(?:\.\d+)?|\.\d+|[a-z]+|[^\s]", text)
    tokens = []
    i = 0
    while i < len(raw):
        token = raw[i]
        if token in NUMBER_WORDS:
            end = i + 1
            while end < len(raw) and raw[end] in NUMBER_WORDS:
                end += 1
            phrase = " ".join(raw[i:end])
            try:
                token = str(number(phrase))
            except (ParseError, ValueError):
                raise MathError("I could not read that number")
            i = end
        else:
            i += 1
        if (not re.fullmatch(r"\d+(?:\.\d+)?|\.\d+", token)
                and token not in FUNCTIONS | {"pi", "e", "x", "degrees", "degree",
                    "radians", "radian", "+", "-", "*", "/", "^", "(", ")", "!", "%", "="}):
            raise MathError("That expression contains an unsupported word or symbol")
        tokens.append(token)
    if not tokens or len(tokens) > MAX_TOKENS:
        raise MathError("Please use a shorter, complete expression")
    return tokens


def bounded(value):
    if value.has(S.zoo, S.oo, -S.oo, S.nan):
        raise MathError("That expression is undefined or non-finite")
    if value.is_number and value.is_real is not True:
        raise MathError("This calculator uses real numbers; that result is not real")
    if S.count_ops(value) > 120:
        raise MathError("That expression is too complex for this voice calculator")
    if value.is_Rational:
        if abs(int(value.p)).bit_length() > 1000 or int(value.q).bit_length() > 1000:
            raise MathError("That number exceeds the calculator's size limit")
    return value


def power(base, exponent):
    bounded(base)
    bounded(exponent)
    if exponent.free_symbols:
        raise MathError("Variable exponents are not supported yet")
    if exponent.is_real is not True:
        raise MathError("Please use a real exponent")
    approximation = float(exponent.evalf(16))
    if not math.isfinite(approximation) or abs(approximation) > 10000:
        raise MathError("That exponent exceeds the calculator's limit")
    if base == 0 and exponent <= 0:
        raise MathError("Zero to a zero or negative power is undefined here")
    if base.free_symbols:
        if exponent.is_Integer is not True or not 0 <= exponent <= 10:
            raise MathError("Symbolic powers must be whole numbers from zero to ten")
    elif base != 0:
        magnitude = S.Abs(base).evalf(16)
        estimate = float(S.log(magnitude, 10).evalf(16)) * approximation
        if not math.isfinite(estimate) or abs(estimate) > MAX_DIGITS:
            raise MathError("That power exceeds the calculator's size limit")
    return bounded(S.Pow(base, exponent))


class Parser:
    """Recursive descent: sums, products, unary signs, powers, postfix, atoms.
    Powers associate right; unary minus is below powers: -2^2 = -4.
    A spoken function without brackets takes one signed/powered argument.
    Explicit multiplication is required except 2x, 2(...), and adjacent brackets.
    """
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.depth = 0
        self.angles = set()

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self):
        value = self.peek()
        if value is None:
            raise MathError("The expression ends too early")
        self.pos += 1
        return value

    def accept(self, token):
        if self.peek() == token:
            self.pos += 1
            return True
        return False

    def parse(self):
        value = self.sum()
        if self.peek() is not None:
            raise MathError("I could not read the whole expression; use explicit operators")
        return bounded(value)

    def sum(self):
        left = self.product()
        while self.peek() in {"+", "-"}:
            op = self.take()
            right = self.product()
            left = bounded(left + right if op == "+" else left - right)
        return left

    def product(self):
        left = self.unary()
        while True:
            op = self.peek()
            if op in {"*", "/"}:
                self.take()
                right = self.unary()
                if op == "/":
                    if right == 0:
                        raise MathError("Division by zero is undefined")
                    if right.free_symbols:
                        raise MathError("Division by a variable expression is not supported yet")
                    left = bounded(left / right)
                else:
                    left = bounded(left * right)
            elif op in {"x", "pi", "e", "("}:
                left = bounded(left * self.unary())
            else:
                return left

    def unary(self):
        self.depth += 1
        if self.depth > 16:
            raise MathError("There are too many nested operations")
        try:
            if self.accept("+"):
                return self.unary()
            if self.accept("-"):
                return bounded(-self.unary())
            value = self.postfix()
            if self.accept("^"):
                value = power(value, self.unary())
            return value
        finally:
            self.depth -= 1

    def postfix(self):
        value = self.atom()
        while self.peek() in {"!", "%"}:
            op = self.take()
            if op == "%":
                value = bounded(value / 100)
            else:
                if value.is_Integer is not True or not 0 <= value <= 100:
                    raise MathError("Factorial accepts whole numbers from zero to one hundred")
                value = bounded(S.factorial(value))
        return value

    def atom(self):
        token = self.take()
        if re.fullmatch(r"\d+(?:\.\d+)?|\.\d+", token):
            if len(token) > 30:
                raise MathError("Please use numbers with at most thirty digits")
            # Convert numeric tokens ourselves, never send strings to SymPy parsers.
            if "." in token:
                whole, fraction = token.split(".")
                value = S.Rational(int((whole or "0") + fraction), 10 ** len(fraction))
            else:
                value = S.Integer(int(token))
            return bounded(value)
        if token in {"x", "pi", "e"}:
            return {"x": X, "pi": S.pi, "e": S.E}[token]
        if token == "(":
            value = self.sum()
            if not self.accept(")"):
                raise MathError("A closing bracket is missing")
            return value
        if token in FUNCTIONS:
            if self.accept("("):
                argument = self.sum()
                if not self.accept(")"):
                    raise MathError("A closing function bracket is missing")
            else:
                argument = self.unary()
            mode = None
            if self.peek() in {"degrees", "degree", "radians", "radian"}:
                mode = self.take()
            if token in {"sin", "cos", "tan"}:
                if mode in {"degree", "degrees"}:
                    argument = argument * S.pi / 180
                    self.angles.add("degrees")
                else:
                    self.angles.add("radians")
                return bounded({"sin": S.sin, "cos": S.cos, "tan": S.tan}[token](argument))
            if mode:
                raise MathError("Angle units belong to sine, cosine or tangent")
            if token == "sqrt":
                return power(argument, S.Rational(1, 2))
            if token == "cbrt":
                if argument.free_symbols:
                    raise MathError("Symbolic cube roots are not supported yet")
                return bounded(S.real_root(argument, 3))
            if token == "abs":
                return bounded(S.Abs(argument))
            if token in {"ln", "log"}:
                if argument.free_symbols or argument.is_positive is not True:
                    raise MathError("Logarithms currently require a positive numeric argument")
                return bounded(S.log(argument) if token == "ln" else S.log(argument, 10))
            if token == "exp":
                return power(S.E, argument)
        raise MathError("A number, x, or opening bracket was expected")


def expression(text):
    parser = Parser(translate(text))
    value = parser.parse()
    return value, parser.angles


def spoken(value):
    text = S.sstr(value)
    text = text.replace("**", " to the power of ").replace("*", " times ")
    text = text.replace("/", " divided by ")
    text = text.replace("sqrt(", "square root of (")
    text = text.replace("sin(", "sine(").replace("cos(", "cosine(").replace("tan(", "tangent(")
    return text


def describe(value):
    value = bounded(value)
    exact = spoken(value)
    if value.free_symbols:
        if len(exact) > 220:
            raise MathError("The symbolic answer is too long to read aloud")
        return exact
    if value.is_Integer:
        if len(str(value)) <= 36:
            return str(value)
        return "approximately " + str(value.evalf(10))
    approximation = str(value.evalf(12))
    if len(exact) > 100:
        return "approximately " + approximation
    if value.is_Rational:
        denominator = int(value.q)
        for factor in (2, 5):
            while denominator % factor == 0:
                denominator //= factor
        if denominator == 1:
            # Decimal arithmetic here is exact for terminating rational values.
            from decimal import Decimal, localcontext
            with localcontext() as context:
                context.prec = 650
                result = format(Decimal(int(value.p)) / Decimal(int(value.q)), "f")
            if len(result) <= 36:
                return result
    return exact + ", approximately " + approximation


def angle_note(angles):
    if angles == {"radians"}:
        return " Using radians."
    if angles == {"degrees"}:
        return " Using degrees."
    if angles:
        return " Using the specified angle units; unmarked angles use radians."
    return ""


def polynomial(value, limit):
    try:
        poly = S.Poly(value, X)
    except S.PolynomialError:
        raise MathError("That operation currently needs a polynomial in x")
    if poly.total_degree() > limit:
        raise MathError(f"That operation supports degree {limit} or lower")
    return poly


def evaluate(command):
    text = clean(command)
    text = re.sub(r"^(?:what is |what's |whats |calculate |compute |evaluate |work out )", "", text)
    if text.startswith("solve "):
        body = re.sub(r"^solve (?:for x[, ]+)?", "", text)
        body = re.sub(r"\s+for x$", "", body)
        tokens = translate(body)
        if tokens.count("=") != 1:
            raise MathError("Say solve, followed by one equation in x")
        index = tokens.index("=")
        left, right = Parser(tokens[:index]), Parser(tokens[index + 1:])
        difference = left.parse() - right.parse()
        polynomial(difference, 4)
        solutions = S.solveset(difference, X, domain=S.S.Reals)
        if solutions is S.S.Reals:
            return "Every real value of x satisfies that equation, sir."
        if solutions is S.S.EmptySet:
            return "There are no real solutions, sir."
        if not isinstance(solutions, S.FiniteSet):
            raise MathError("I could not produce a finite list of real solutions")
        answers = [describe(v) for v in sorted(solutions, key=S.default_sort_key)]
        result = "x equals " + "; or ".join(answers)
    elif text.startswith(("differentiate ", "derivative of ", "the derivative of ")):
        body = re.sub(r"^(?:differentiate |(?:the )?derivative of )", "", text)
        body = re.sub(r"\s+with respect to x$", "", body)
        value, angles = expression(body)
        result = "The derivative with respect to x is " + describe(S.diff(value, X))
        result += angle_note(angles)
    elif text.startswith(("integrate ", "integral of ", "the integral of ")):
        body = re.sub(r"^(?:integrate |(?:the )?integral of )", "", text)
        body = re.sub(r"\s+with respect to x$", "", body)
        definite = re.fullmatch(r"(.+?)\s+from\s+(.+?)\s+to\s+(.+)", body)
        if definite:
            value, angles = expression(definite.group(1))
            low, _ = expression(definite.group(2))
            high, _ = expression(definite.group(3))
            if low.free_symbols or high.free_symbols:
                raise MathError("Integration bounds must be real numbers")
            # Polynomial definite integrals avoid silently crossing singularities.
            polynomial(value, 10)
            answer = S.integrate(value, (X, low, high))
            result = "The definite integral is " + describe(answer)
        else:
            value, angles = expression(body)
            answer = S.integrate(value, X)
            if answer.has(S.Integral):
                raise MathError("I could not finish that integral")
            result = "An antiderivative with respect to x is " + describe(answer)
            result += ", plus a constant"
        result += angle_note(angles)
    elif text.startswith(("simplify ", "expand ", "factor ", "factorise ", "factorize ")):
        operation, body = text.split(" ", 1)
        value, angles = expression(body)
        if operation in {"expand", "factor", "factorise", "factorize"}:
            polynomial(value, 10)
        operation = {"factorise": "factor", "factorize": "factor"}.get(operation, operation)
        answer = {"simplify": S.simplify, "expand": S.expand, "factor": S.factor}[operation](value)
        result = "The result is " + describe(answer) + angle_note(angles)
    else:
        value, angles = expression(text)
        result = "The answer is " + describe(value) + angle_note(angles)
    if len(result) > 650:
        raise MathError("The answer is too long for a spoken reply")
    return result.rstrip(".") + ", sir."


def safe_evaluate(command):
    try:
        return evaluate(command)
    except (MathError, ParseError) as error:
        return str(error).rstrip(".") + ", sir."
    except Exception as error:
        print("Math worker error: " + type(error).__name__ + ": " + str(error), file=sys.stderr)
        return "I could not calculate that expression, sir."


if __name__ == "__main__":
    try:
        data = json.loads(sys.stdin.read(4096))
        reply = safe_evaluate(data["command"])
        print(json.dumps({"reply": reply}))
    except Exception as error:
        print(json.dumps({"reply": "The calculator received invalid input, sir."}))
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
