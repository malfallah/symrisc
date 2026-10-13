import unittest

from symrisc.control import CONTROL_TABLE, alu
from symrisc.isa import BY_MNEMONIC, AluOp, to_signed, to_unsigned

INT_MIN, INT_MAX = -(1 << 31), (1 << 31) - 1


def run(op, a, b):
    return to_signed(alu(op, to_unsigned(a), to_unsigned(b)).value)


class AluTest(unittest.TestCase):
    def test_arithmetic_wraps_modulo_2_32(self):
        self.assertEqual(run(AluOp.ADD, INT_MAX, 1), INT_MIN)
        self.assertEqual(run(AluOp.SUB, INT_MIN, 1), INT_MAX)
        self.assertEqual(run(AluOp.RSUB, 3, 10), 7)
        self.assertEqual(run(AluOp.MUL, 1 << 20, 1 << 12), 0)
        self.assertEqual(run(AluOp.MUL, -6, 7), -42)

    def test_division_truncates_toward_zero(self):
        self.assertEqual(run(AluOp.DIV, 7, 2), 3)
        self.assertEqual(run(AluOp.DIV, -7, 2), -3)
        self.assertEqual(run(AluOp.DIV, 7, -2), -3)
        self.assertEqual(run(AluOp.DIV, -7, -2), 3)

    def test_division_corner_cases_do_not_trap(self):
        self.assertEqual(run(AluOp.DIV, 5, 0), -1)
        self.assertEqual(run(AluOp.DIV, INT_MIN, -1), INT_MIN)

    def test_logic_and_shifts(self):
        self.assertEqual(run(AluOp.AND, 0b1100, 0b1010), 0b1000)
        self.assertEqual(run(AluOp.OR, 0b1100, 0b1010), 0b1110)
        self.assertEqual(run(AluOp.NOT, 12345, 0), -1)  # NOT acts on operand B only
        self.assertEqual(run(AluOp.NOT, 0, 5), -6)
        self.assertEqual(run(AluOp.SLL, 1, 31), INT_MIN)
        self.assertEqual(to_unsigned(run(AluOp.SRL, -1, 28)), 0xF)  # logical, not arithmetic

    def test_set_less_than_is_signed(self):
        self.assertEqual(run(AluOp.SLT, -1, 1), 1)
        self.assertEqual(run(AluOp.SLT, 1, -1), 0)
        self.assertEqual(run(AluOp.SLT, 3, 3), 0)

    def test_less_flag_is_overflow_corrected(self):
        # INT_MAX - (-1) overflows; a raw MSB tap would claim INT_MAX < -1.
        self.assertFalse(alu(AluOp.SUB, to_unsigned(INT_MAX), to_unsigned(-1)).less)
        self.assertTrue(alu(AluOp.SUB, to_unsigned(INT_MIN), 1).less)
        self.assertTrue(alu(AluOp.SUB, 0, 0).zero)


class ControlTableTest(unittest.TestCase):
    def test_state_changing_signals_are_never_dont_care(self):
        for opcode, signals in CONTROL_TABLE.items():
            for name in ("mem_read", "mem_write", "reg_write", "branch"):
                self.assertIn(getattr(signals, name), (0, 1), f"{opcode:05b}.{name}")

    def test_branches_do_not_write_registers_or_memory(self):
        # Regression: the Phase 2 report listed RegWrite = 1 for branches.
        for mnemonic in ("B=", "B!=", "B<", "B>"):
            signals = CONTROL_TABLE[BY_MNEMONIC[mnemonic].opcode]
            self.assertEqual((signals.branch, signals.reg_write, signals.mem_write), (1, 0, 0), mnemonic)

    def test_load_and_store(self):
        sw = CONTROL_TABLE[BY_MNEMONIC["SW"].opcode]
        lw = CONTROL_TABLE[BY_MNEMONIC["LW"].opcode]
        self.assertEqual((sw.mem_write, sw.reg_write), (1, 0))
        self.assertEqual((lw.mem_read, lw.mem_to_reg, lw.reg_write, lw.reg_dst), (1, 1, 1, 0))


if __name__ == "__main__":
    unittest.main()
