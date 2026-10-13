import unittest
from pathlib import Path

from symrisc import CPU, assemble
from symrisc.isa import register_number

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def run_example(name, dont_care=0):
    program = assemble((EXAMPLES / name).read_text(encoding="utf-8"), filename=name)
    return program, CPU(program, dont_care=dont_care).run_to_completion()


def c_division(a, b):
    quotient = abs(a) // abs(b)
    return quotient if (a < 0) == (b < 0) else -quotient


class ExampleProgramsTest(unittest.TestCase):
    def test_course_demo_matches_c_reference(self):
        # Direct transliteration of examples/course_demo.c
        x, y, w, j = 10, 0, 0 << 2, 5
        array = [0, 0, 0, 0]
        i = 1
        while i < x:
            x += c_division((i + 2) - (i * 3), j)
            i += 1
        if x > w:
            w = x | 999
            y = x & w
            array[1] = y

        program, cpu = run_example("course_demo.s")
        registers = tuple(cpu.reg(register_number(n)) for n in ("!S0", "!S1", "!S2", "!S4"))
        self.assertEqual(registers, (x, y, w, i))
        self.assertEqual(cpu.memory.words(program.symbols["A"], 4), array)
        self.assertEqual((x, y, w), (6, 6, 999))

    def test_fibonacci(self):
        program, cpu = run_example("fibonacci.s")
        self.assertEqual(cpu.memory.words(program.symbols["fib"], 12), [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89])

    def test_bubble_sort(self):
        program, cpu = run_example("bubble_sort.s")
        values = cpu.memory.words(program.symbols["array"], 8, signed=True)
        self.assertEqual(values, sorted([42, -7, 19, 0, 1000, -300, 7, 7]))

    def test_dont_care_signals_never_change_behaviour(self):
        for path in sorted(EXAMPLES.glob("*.s")):
            _, low = run_example(path.name, dont_care=0)
            _, high = run_example(path.name, dont_care=1)
            self.assertEqual(low.registers, high.registers, path.name)
            self.assertEqual(low.memory.addresses(), high.memory.addresses(), path.name)
            self.assertEqual(low.memory.words(0, 64), high.memory.words(0, 64), path.name)
            self.assertEqual(low.cycles, high.cycles, path.name)


if __name__ == "__main__":
    unittest.main()
