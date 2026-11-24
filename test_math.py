"""Math tests only. No microphone, GPU, voice, app, window or volume actions.
Includes a real worker subprocess test and a mocked timeout regression test.
"""
import subprocess
import unittest
from unittest.mock import patch

import sympy as S

from jarvis_math import calculator, is_math, number, symbolic_reply
from jarvis_math_engine import MathError, X, evaluate, expression, safe_evaluate


class ExpressionTests(unittest.TestCase):
    def test_arithmetic_and_screenshot(self):
        cases = {
            "3 to the power of 7": 2187,
            "three to the power of seven": 2187,
            "two plus three times four": 14,
            "open bracket two plus three close bracket times four": 20,
            "2^3^2": 512,
            "-2^2": -4,
            "(-2)^2": 4,
            "2^-3": S.Rational(1, 8),
            "0.1 + 0.2": S.Rational(3, 10),
            ".5 times eight": 4,
            "one hundred and twenty plus five": 125,
            "one point five times four": 6,
            "half plus a half": 1,
            "one and a half times four": 6,
            "1,000 + 25": 1025,
            "square root of eighty one": 9,
            "cube root of negative eight": -2,
            "absolute value of negative five": 5,
            "five factorial": 120,
            "5!": 120,
            "15 percent of 80": 12,
            "15% of 80": 12,
            "fifteen per cent of negative eighty": -12,
            "(25%) * 80": 20,
            "5 + 10%": S.Rational(51, 10),
            "log base ten of one thousand": 3,
            "natural log of e": 1,
            "sine of thirty degrees": S.Rational(1, 2),
            "cosine of sixty degrees": S.Rational(1, 2),
            "sine of (pi / 2) radians": 1,
            "2x + 3x": 5 * X,
            "(x+1)(x-1)": (X+1)*(X-1),
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                result, _ = expression(command)
                self.assertEqual(S.expand(result - expected), 0)

    def test_fail_closed(self):
        cases = [
            "1/0", "0^0", "0^-1", "square root of negative one",
            "natural log of zero", "tangent of ninety degrees",
            "101 factorial", "three point five factorial",
            "10^10001", "10^1000", "9^9^9", "x^100",
            "1/x", "x^-1", "2^x", "sqrt(x)",
            "__import__('os')", "open('file')", "x.__class__",
            "1e-5", "2 +", "(2+3", "2 + 3 garbage", "2 3",
            "(5%) 8", "1,2", "y+1",
        ]
        for command in cases:
            with self.subTest(command=command):
                with self.assertRaises(MathError):
                    expression(command)

    def test_limits(self):
        with self.assertRaises(MathError):
            expression("(" * 25 + "2" + ")" * 25)
        with self.assertRaises(MathError):
            expression("1+" * 100 + "1")
        with self.assertRaises(MathError):
            expression("1" * 31)

    def test_degrees_are_recorded(self):
        self.assertEqual(expression("sin 30 degrees")[1], {"degrees"})
        self.assertEqual(expression("sin 1")[1], {"radians"})

    def test_exact_screenshot_reply(self):
        self.assertEqual(evaluate("what's 3 to the power of 7?"),
                         "The answer is 2187, sir.")

    def test_numbers_do_not_round_small_values_to_zero(self):
        reply = evaluate("calculate 1/3")
        self.assertIn("approximately", reply)
        self.assertIn("0.333", reply)
        self.assertEqual(evaluate("calculate 0.1 + 0.2"), "The answer is 0.3, sir.")
        self.assertNotEqual(evaluate("calculate 10^-20"), "The answer is 0, sir.")


class AlgebraTests(unittest.TestCase):
    def test_linear(self):
        self.assertEqual(evaluate("solve two x plus three equals eleven"),
                         "x equals 4, sir.")

    def test_quadratic(self):
        self.assertEqual(evaluate("solve x squared minus five x plus six equals zero"),
                         "x equals 2; or 3, sir.")

    def test_whisper_coefficient_comma(self):
        for command in (
            "solve x squared minus 5, x plus 6 equals 0",
            "solve x squared minus 5,x plus 6 equals 0",
            "solve x squared minus five times x plus six equals zero",
        ):
            with self.subTest(command=command):
                self.assertEqual(evaluate(command), "x equals 2; or 3, sir.")
        # Unrelated numeric punctuation and misheard words still fail closed.
        for command in ("5,6 + 1", "salt x squared minus 5x plus 6 equals zero",
                        "integrate x squared from 0 plus 3"):
            with self.subTest(command=command):
                with self.assertRaises(MathError):
                    evaluate(command)

    def test_identity_and_no_solution(self):
        self.assertIn("Every real value", evaluate("solve x equals x"))
        self.assertIn("no real solutions", evaluate("solve x squared equals negative one"))
        self.assertIn("no real solutions", evaluate("solve x plus one equals x"))

    def test_polynomial_operations(self):
        self.assertIn("x to the power of 2", evaluate("expand (x+2)^2"))
        self.assertIn("(x - 3)", evaluate("factor x squared minus nine"))
        self.assertIn("5 times x", evaluate("simplify 2x + 3x"))

    def test_calculus(self):
        self.assertIn("3 times x to the power of 2 + 2",
                      evaluate("differentiate x cubed plus two x"))
        self.assertIn("x to the power of 3 divided by 3",
                      evaluate("integrate x squared"))
        self.assertIn("plus a constant", evaluate("integrate x squared"))
        self.assertEqual(evaluate("integrate x squared from zero to three"),
                         "The definite integral is 9, sir.")
        self.assertIn("cosine(x)", evaluate("differentiate sine of x"))

    def test_unsupported_calculus_and_equations(self):
        self.assertIn("polynomial", safe_evaluate("solve sin x equals zero"))
        self.assertIn("degree 4", safe_evaluate("solve x^5 equals 2"))
        self.assertIn("polynomial", safe_evaluate("integrate sin x from zero to pi"))


class IntegrationTests(unittest.TestCase):
    def test_routing_leaves_other_commands_alone(self):
        for command in ("open calculator", "open downloads", "close Notepad",
                        "what is the volume", "what is the date", "set a timer for ten seconds"):
            self.assertFalse(is_math(command), command)
            self.assertIsNone(calculator(command), command)
        for command in ("what's 3 to the power of 7", "solve 2x=8",
                        "differentiate x squared", "convert ten inches to centimetres"):
            self.assertTrue(is_math(command), command)

    def test_old_volume_number_parser_unchanged(self):
        self.assertEqual(number("thirty"), 30)
        self.assertEqual(number("five"), 5)
        self.assertEqual(number("one point five"), 1.5)

    def test_conversions_preserved(self):
        self.assertEqual(calculator("convert ten inches to centimetres"),
                         "10 inches is 25.4 centimetres, sir.")
        self.assertEqual(calculator("convert thirty two fahrenheit to celsius"),
                         "32 fahrenheit is 0 celsius, sir.")
        self.assertIn("different quantities", calculator("convert ten inches to kilograms"))
        self.assertIn("absolute zero", calculator("convert negative one kelvin to celsius"))

    def test_real_worker_and_dependency_import(self):
        self.assertEqual(calculator("what's 3 to the power of 7"),
                         "The answer is 2187, sir.")

    def test_timeout_reply(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 6)):
            self.assertIn("six second limit", symbolic_reply("calculate 3^7"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
