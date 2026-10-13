import itertools
import unittest

from symrisc import CPU, MachineError, Program, assemble
from symrisc.isa import register_number, to_unsigned

INT_MIN, INT_MAX = -(1 << 31), (1 << 31) - 1


def execute(source, registers=None, dont_care=0):
    cpu = CPU(assemble(source), dont_care=dont_care)
    for name, value in (registers or {}).items():
        cpu.registers[register_number(name)] = to_unsigned(value)
    return cpu.run_to_completion(max_cycles=10_000)


def reg(cpu, name):
    return cpu.reg(register_number(name))


class BranchTest(unittest.TestCase):
    PREDICATES = {
        "B=": lambda a, b: a == b,
        "B!=": lambda a, b: a != b,
        "B<": lambda a, b: a < b,
        "B>": lambda a, b: a > b,
    }
    VALUES = (0, 1, 2, -1, -2, 1000, INT_MIN, INT_MAX)

    def test_branch_conditions_exhaustively(self):
        for mnemonic, predicate in self.PREDICATES.items():
            for a, b in itertools.product(self.VALUES, repeat=2):
                for dont_care in (0, 1):
                    cpu = execute(
                        f"{mnemonic} !S0, !S1, !A0\nASi !T0, 1\n",
                        {"!S0": a, "!S1": b, "!A0": 8},
                        dont_care,
                    )
                    taken = reg(cpu, "!T0") == 0
                    self.assertEqual(taken, predicate(a, b), f"{mnemonic} {a}, {b}")

    def test_branch_greater_than_is_not_taken_on_equality(self):
        # Regression: the original B> tested ~MSB(A - B), which is also 1 when A == B.
        cpu = execute("B> !S0, !S1, !A0\nASi !T0, 1\n", {"!S0": 5, "!S1": 5, "!A0": 8})
        self.assertEqual(reg(cpu, "!T0"), 1)

    def test_branch_target_comes_from_register(self):
        cpu = execute(
            """
                    ASi !A0, target
                    B=  !Z, !Z, !A0
                    ASi !S0, 1          // skipped
            target: ASi !S1, 1
            """
        )
        self.assertEqual((reg(cpu, "!S0"), reg(cpu, "!S1")), (0, 1))


class InstructionTest(unittest.TestCase):
    def test_immediate_instructions(self):
        cpu = execute(
            """
            ASi !S0, 100
            i++ !S1, !S0, -1
            i-- !S2, !S0, 1
            i&  !S3, !S0, 0x0F
            i|| !S4, !S0, 3
            i~  !S5, 5
            i/  !S6, !S0, -7
            i*  !S7, !S0, -3
            LA  !S8, !S0, 8
            """
        )
        expected = {
            "!S0": 100,
            "!S1": 99,
            "!S2": 99,
            "!S3": 4,
            "!S4": 103,
            "!S5": -6,
            "!S6": -14,
            "!S7": -300,
            "!S8": 108,
        }
        for name, value in expected.items():
            self.assertEqual(reg(cpu, name), value, name)

    def test_register_instructions(self):
        cpu = execute(
            """
            ++  !T0, !S0, !S1
            --  !T1, !S0, !S1
            *   !T2, !S0, !S1
            /   !T3, !S0, !S1
            &   !T4, !S0, !S1
            ||  !T5, !S0, !S1
            ~   !T6, !S0
            SLT !T7, !S1, !S0
            SLT !T8, !S0, !S1
            <<  !T9, !S0, 4
            >>  !T10, !S1, 28
            """,
            {"!S0": 12, "!S1": -5},
        )
        expected = {
            "!T0": 7,
            "!T1": 17,
            "!T2": -60,
            "!T3": -2,
            "!T4": 12 & -5,
            "!T5": 12 | -5,
            "!T6": ~12,
            "!T7": 1,
            "!T8": 0,
            "!T9": 192,
            "!T10": 0xF,
        }
        for name, value in expected.items():
            self.assertEqual(reg(cpu, name), value, name)

    def test_load_and_store(self):
        cpu = execute(
            """
                  ASi !A0, slot
                  LW  !S0, (!A0)
                  i++ !S0, !S0, 1
                  SW  !S0, (!A0)
                  .data
            slot: .word 41
            """
        )
        self.assertEqual(cpu.memory.read(0), 42)
        self.assertEqual(reg(cpu, "!S0"), 42)

    def test_zero_register_is_hard_wired(self):
        cpu = execute("ASi !Z, 7\n++ !S0, !Z, !Z")
        self.assertEqual(cpu.registers[0], 0)
        self.assertEqual(reg(cpu, "!S0"), 0)

    def test_misaligned_and_out_of_range_access(self):
        with self.assertRaisesRegex(MachineError, "misaligned"):
            execute("ASi !A0, 2\nLW !S0, (!A0)")
        with self.assertRaisesRegex(MachineError, "out of range"):
            execute("i~ !A0, 3\nSW !S0, (!A0)")  # address 0xFFFFFFFC

    def test_illegal_opcode(self):
        with self.assertRaisesRegex(MachineError, "illegal opcode"):
            CPU(Program(text=[0x3000_0000])).step()

    def test_runaway_program_is_stopped(self):
        with self.assertRaisesRegex(MachineError, "did not halt"):
            execute("B= !Z, !Z, !Z")  # jumps to address 0 forever


if __name__ == "__main__":
    unittest.main()
