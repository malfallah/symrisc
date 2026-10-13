import unittest

from symrisc.control import CONTROL_TABLE
from symrisc.isa import (
    BY_OPCODE,
    FIELDS,
    INSTRUCTIONS,
    NUM_REGISTERS,
    REGISTER_GROUPS,
    REGISTER_NAMES,
    Format,
    Syntax,
    register_name,
    register_number,
)


class FieldLayoutTest(unittest.TestCase):
    def test_formats_cover_all_32_bits_without_overlap(self):
        for fmt, fields in FIELDS.items():
            covered = 0
            for f in fields:
                bits = f.mask << f.lo
                self.assertEqual(covered & bits, 0, f"{fmt}: {f.name} overlaps another field")
                covered |= bits
            self.assertEqual(covered, 0xFFFF_FFFF, f"{fmt} does not cover all 32 bits")

    def test_field_widths(self):
        widths = {f.name: f.width for fmt in FIELDS.values() for f in fmt}
        self.assertEqual(widths, {"opcode": 5, "var1": 6, "var2": 6, "imm": 15, "dest": 6, "shamt": 5, "unused": 4})


class OpcodeTest(unittest.TestCase):
    def test_opcodes_and_mnemonics_are_unique(self):
        self.assertEqual(len({i.opcode for i in INSTRUCTIONS}), len(INSTRUCTIONS))
        self.assertEqual(len({i.mnemonic.upper() for i in INSTRUCTIONS}), len(INSTRUCTIONS))

    def test_opcode_msb_selects_format(self):
        for ins in INSTRUCTIONS:
            expected = Format.M if ins.opcode >> 4 else Format.B
            self.assertIs(ins.format, expected, ins.mnemonic)

    def test_immediate_syntax_only_in_b_format(self):
        for ins in INSTRUCTIONS:
            uses_imm = ins.syntax in (Syntax.ASSIGN, Syntax.IMMEDIATE)
            self.assertEqual(uses_imm, ins.format is Format.B, ins.mnemonic)

    def test_instruction_count(self):
        self.assertEqual(len(INSTRUCTIONS), 25)
        self.assertEqual(sum(i.format is Format.B for i in INSTRUCTIONS), 9)

    def test_every_opcode_has_a_control_row(self):
        self.assertEqual(set(CONTROL_TABLE), set(BY_OPCODE))

    def test_distinct_operations_get_distinct_alu_ops(self):
        # Regression: the original 3-bit ALUOp encoded both AND and NOT as 010.
        adders = {"Assign", "Add", "Load Address"}
        operation_of = {}
        for ins in INSTRUCTIONS:
            if ins.alu_op is None or ins.syntax is Syntax.BRANCH:
                continue
            base = ins.name.replace(" Immediate", "")
            operation = "Add" if base in adders else base
            self.assertEqual(
                operation_of.setdefault(ins.alu_op, operation),
                operation,
                f"{ins.mnemonic} shares ALUOp {ins.alu_op.name} with a different operation",
            )


class RegisterTest(unittest.TestCase):
    def test_sixty_four_unique_registers(self):
        self.assertEqual(len(REGISTER_NAMES), NUM_REGISTERS)
        self.assertEqual(len(set(REGISTER_NAMES)), NUM_REGISTERS)

    def test_groups_tile_the_register_file(self):
        expected = 0
        for first, last, _, _ in REGISTER_GROUPS:
            self.assertEqual(first, expected)
            expected = last + 1
        self.assertEqual(expected, NUM_REGISTERS)

    def test_register_numbers(self):
        cases = {
            "!Z": 0,
            "!S0": 1,
            "!S20": 21,
            "!T0": 22,
            "!T20": 42,
            "!A0": 43,
            "!A16": 59,
            "!GP": 60,
            "!SP": 61,
            "!FP": 62,
            "!RA": 63,
            "!r17": 17,
            "!s3": 4,
        }
        for token, number in cases.items():
            self.assertEqual(register_number(token), number, token)

    def test_register_names_round_trip(self):
        for number in range(NUM_REGISTERS):
            self.assertEqual(register_number(register_name(number)), number)

    def test_invalid_registers(self):
        for token in ("S0", "!S21", "!T21", "!A17", "!R64", "!X1", "!"):
            with self.assertRaises(ValueError, msg=token):
                register_number(token)


if __name__ == "__main__":
    unittest.main()
