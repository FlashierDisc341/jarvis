# JARVIS maths upgrade v7

The screenshot's transcription was correct. The previous v5 calculator accepted
one basic operation but did not implement "to the power of".
This upgrade extends the command layer; it does not change Whisper or the voice.

## Install into the current Jarvis folder

1. Stop JARVIS with Ctrl+C.
2. Replace these three files with the new attachments:
   - jarvis_math.py
   - jarvis_actions.py
   - jarvis_help.py
3. Add these two new Python files beside them:
   - jarvis_math_engine.py
   - test_math.py
4. Keep jarvis_whisper.py, jarvis_whisper_audio.py, jarvis_time.py,
   jarvis_desktop.py, jarvis_processes.py and the other existing files.
5. From PowerShell in the Jarvis folder, install the maths dependency:

       .\.venv-whisper\Scripts\python.exe -m pip install --only-binary=:all: sympy==1.14.0

6. Run the tests BEFORE restarting the voice assistant:

       .\.venv-whisper\Scripts\python.exe test_math.py

   They check parsing, calculations, bounds, unit conversions and the worker.
   They do not use the microphone/GPU or change apps, windows or volume.
   They include a real calculator subprocess and a mocked timeout response.
   This generated build has been reviewed but NOT executed in the author's environment.
   A test failure is a blocker: keep the complete output rather than proceeding.

7. When the tests report OK:

       .\.venv-whisper\Scripts\python.exe jarvis_whisper.py

   Do not add --dry-run if you want spoken calculation results.
   The frontend's dry-run mode only prints commands; it does not call the calculator.

This installs SymPy only into .venv-whisper. The original .venv environment is not
changed. If you later use the Vosk entry point with these new shared command files,
install the same SymPy dependency into that environment too.

## Start with these voice tests

- "Jarvis, what's three to the power of seven?" -> 2187
- "Jarvis, what's two plus three times four?" -> 14
- "Jarvis, what's the square root of eighty one?" -> 9
- "Jarvis, what's fifteen percent of eighty?" -> 12
- "Jarvis, solve two x plus three equals eleven." -> x = 4

Say Jarvis at the start OR end as before, and wait for LISTENING.
The transcript in the terminal is the evidence of what the recognizer heard.

## Supported maths

Arithmetic:
- +, -, multiplication, division, negatives and decimals
- Multiple operations with standard precedence
- Right-associative powers: 2^3^2 means 2^(3^2)
- Unary minus below powers: -2^2 = -4; (-2)^2 = 4
- Percentages: "fifteen percent of eighty", "15% of 80"
- "five factorial" -> 120
- "square root of eighty one", "cube root of negative eight"
- Constants pi and e
- Existing length, mass, volume and temperature conversions

Grouping:
- "open bracket two plus three close bracket times four" -> 20
- Parentheses may also be typed.
- A spoken function without brackets consumes its next signed/powered argument.
  "square root of nine plus sixteen" means sqrt(9) + 16.
  To take the root of the sum, include open/close brackets.
- Use "times" for multiplication. Limited implicit multiplication supports
  2x, 2(x+1) and (x+1)(x-1).
- Say "factorial" rather than relying on Whisper to emit an exclamation mark.

Trigonometry and logs:
- "sine of thirty degrees" -> 0.5
- "cosine of sixty degrees" -> 0.5
- "tangent of forty five degrees" -> 1
- Without explicit degrees, trig uses radians and says so in the reply.
- "natural log of e" -> 1
- "log base ten of one thousand" -> 3
- Bare log is base 10; ln is natural logarithm.
- This version uses REAL numbers. Non-real or undefined results are refused.

Algebra:
- "solve two x plus three equals eleven"
- "solve x squared minus five x plus six equals zero" -> x = 2 or 3
- Real roots of one polynomial equation in x, up to degree four
- "simplify two x plus three x"
- "expand open bracket x plus two close bracket squared"
- "factor x squared minus nine"
- Expand/factor support polynomials up to degree ten.
- Some exact symbolic answers are spoken with a decimal approximation.

Basic calculus:
- "differentiate x cubed plus two x"
- "differentiate sine of x"
- "integrate x squared" -> x^3/3 plus a constant
- "integrate x squared from zero to three" -> 9
- x is the only variable and is treated as real.
- Definite integrals are limited to polynomials, up to degree ten.
- Indefinite integrals must finish within the same worker time limit.
- An unevaluated integral is reported as unfinished, not claimed as an answer.

## Deliberate limits

This is a calculator, not an all-purpose mathematical reasoning agent.
It does NOT interpret arbitrary word problems, prove theorems, solve systems of
equations, work with matrices, graph, or explain derivations step by step.
Only x is supported. Variable exponents, symbolic division, symbolic roots,
inverse trig and complex arithmetic are not implemented in this version.
Unsupported syntax is rejected rather than guessed.

Inputs have a 400-character, 80-token and nesting limit. Numeric literals have
at most 30 characters. Spoken number words reuse the existing limited number
parser; digit-form large numbers have broader coverage.
Symbolic powers accept integer exponents from 0 to 10. Numeric exponents are
bounded, as are intermediate sizes. Factorial is capped at 100.
Results that are too large/long for useful spoken output are refused or shortened
to an explicitly approximate value.

Long numerical approximations use twelve significant digits; very large integer
readbacks use a shorter approximation. Exact rational arithmetic is used internally.
No claim of arbitrary precision or correctness for any possible phrase is intended.

## How it connects

jarvis_actions.py still calls calculator(command). The only dispatcher change adds
the new maths verbs as new requests, so "solve ..." can leave a pending app choice
or confirmation instead of being mistaken for a choice answer.
Number-only answers still select existing choices. Existing app/window/volume
protections are unchanged. The number() helper used by volume commands is retained.

Conversions still run through the existing Decimal-based converter.
Other maths runs in a short-lived local Python subprocess, using this environment's
Python executable and a fixed worker path. Spoken text goes through JSON stdin,
not a shell command. No eval, exec, parse_expr or sympify string parsing is used:
a restricted tokenizer/parser constructs numbers and approved SymPy operations.

The worker has a six-second timeout and expression-size limits. These are practical
bounds, not an OS-enforced memory sandbox. A timed-out worker is terminated by
subprocess.run; JARVIS returns a spoken timeout message instead of waiting indefinitely.
SymPy is imported only in the worker. No speech/GPU model is loaded by that worker.

The existing voice loop pauses microphone capture while an action runs. Maths can
therefore pause listening and delay a timer announcement until the action finishes,
up to the worker timeout plus startup/cleanup and spoken output. No barge-in is added.

Calculations remain local. The dependency installation needs internet access;
the calculator itself does not query an online maths service.
No new recording, transcript storage or in-app controls are added.

## Optional typed calculator

To distinguish speech recognition from calculation problems:

    .\.venv-whisper\Scripts\python.exe jarvis_math.py

Type commands without Jarvis, such as:
    what's 3 to the power of 7
    solve x^2 - 5x + 6 = 0
    integrate x^2 from 0 to 3

This mode does not load the microphone, voice or GPU and cannot control apps.
Type quit to finish.

## Primary references

SymPy package:
https://pypi.org/project/sympy/1.14.0/

Symbolic equation solving:
https://docs.sympy.org/latest/guides/solving/solve-equation-algebraically.html

Calculus:
https://docs.sympy.org/latest/tutorials/intro-tutorial/calculus.html

Why user speech is NOT passed to SymPy's string expression parser:
https://docs.sympy.org/latest/modules/parsing.html
