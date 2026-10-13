import unittest

from symrisc.assembler import AssemblerError, assemble, disassemble
from symrisc.isa import INSTRUCTIONS, Syntax


def word(source: str) -> int:
    program = assemble(source)
    assert len(program.text) == 1
    return program.text[0]


class EncodingTest(unittest.TestCase):
    """Golden encodings, worked out by hand from the field layout."""

    def test_b_format(self):
        self.assertEqual(word("i++ !S0, !S0, 9"), 0x0820_8009)  # matches the Phase 1 report
        self.assertEqual(word("ASi !S5, 8"), 0x0003_0008)  # matches the Phase 1 report
        self.assertEqual(word("i~ !S5, 7"), 0x2003_0007)  # matches the Phase 1 report
        self.assertEqual(word("i|| !S4, !S3, 20"), 0x1882_8014)  # report had Var1/Var2 swapped
        self.assertEqual(word("i++ !T0, !T0, -1"), 0x0ACB_7FFF)

    def test_m_format(self):
        self.assertEqual(word("++ !T1, !S0, !S1"), 0x8021_2E00)
        self.assertEqual(word("<< !S2, !T0, 2"), 0xD2C0_0620)
        self.assertEqual(word("B< !S2, !S1, !A2"), 0xF061_5A00)
        self.assertEqual(word("LW !S2, (!A1)"), 0x9001_D800)
        self.assertEqual(word("LW !S2, !A1"), 0x9001_D800)  # parentheses are optional

    def test_case_and_spacing_are_flexible(self):
        self.assertEqual(word("asi !s5, 8"), word("ASi !S5, 8"))
        self.assertEqual(word("<<!S2,!T0,2"), word("<< !S2, !T0, 2"))  # spelling used in the report

    def test_immediate_bounds(self):
        word("ASi !S0, 16383")
        word("ASi !S0, -16384")
        for value in ("16384", "-16385"):
            with self.assertRaises(AssemblerError):
                assemble(f"ASi !S0, {value}")

    def test_shift_bounds(self):
        word("<< !S0, !S1, 31")
        with self.assertRaises(AssemblerError):
            assemble("<< !S0, !S1, 32")


class RoundTripTest(unittest.TestCase):
    SAMPLE_OPERANDS = {
        Syntax.ASSIGN: "!S3, -42",
        Syntax.IMMEDIATE: "!T4, !A1, 1234",
        Syntax.REGISTER: "!RA, !GP, !SP",
        Syntax.UNARY: "!T20, !S20",
        Syntax.SHIFT: "!A16, !FP, 17",
        Syntax.MEMORY: "!S1, (!A3)",
        Syntax.BRANCH: "!S1, !S2, !A3",
    }

    def test_every_instruction_round_trips(self):
        for ins in INSTRUCTIONS:
            source = f"{ins.mnemonic} {self.SAMPLE_OPERANDS[ins.syntax]}"
            encoded = word(source)
            self.assertEqual(word(disassemble(encoded)), encoded, source)

    def test_unknown_opcode_disassembles_as_data(self):
        self.assertEqual(disassemble(0x3000_0000), ".word 0x30000000")


class ProgramTest(unittest.TestCase):
    def test_labels_sections_and_expressions(self):
        program = assemble(
            """
            start:  ASi !A0, table + 4   // data label plus offset
                    ASi !A1, end
            end:
                    .data
            pad:    .space 8
            table:  .word 1, -1, 0x10, end
            """
        )
        self.assertEqual(program.symbols, {"start": 0, "end": 8, "pad": 0, "table": 8})
        self.assertEqual(program.text[0] & 0x7FFF, 12)
        self.assertEqual(program.data, {0: 0, 4: 0, 8: 1, 12: 0xFFFF_FFFF, 16: 0x10, 20: 8})
        self.assertEqual(program.data_labels, {0: "pad", 8: "table"})

    def test_comment_styles(self):
        program = assemble("ASi !S0, 1 // c\nASi !S0, 2 # c\nASi !S0, 3 ; c\n// only a comment")
        self.assertEqual(len(program.text), 3)

    def test_listing_tracks_source_lines(self):
        program = assemble("\n\nloop: ASi !S0, 1\n")
        self.assertEqual(program.listing[0].line_no, 3)
        self.assertEqual(program.listing[0].address, 0)


class ErrorTest(unittest.TestCase):
    CASES = {
        "unknown instruction": "MOV !S0, !S1",
        "unknown register": "++ !S0, !S1, !Q2",
        "expects 3 operands": "++ !S0, !S1",
        "undefined label": "ASi !A0, nowhere",
        "duplicate label": "x: ASi !S0, 1\nx: ASi !S0, 2",
        "empty operand": "++ !S0, !S1, !S2,",
        "only allowed in the .text section": ".data\nASi !S0, 1",
        "only allowed in the .data section": ".word 5",
        "multiple of 4": ".data\n.space 3",
        "unknown directive": ".data\n.byte 1",
        "does not fit in 32 bits": ".data\n.word 0x100000000",
    }

    def test_errors_are_reported_with_line_numbers(self):
        for fragment, source in self.CASES.items():
            with self.assertRaises(AssemblerError, msg=fragment) as ctx:
                assemble(source, filename="t.s")
            self.assertIn(fragment, str(ctx.exception))
            self.assertRegex(str(ctx.exception), r"^t\.s:\d+: error: ")


if __name__ == "__main__":
    unittest.main()
