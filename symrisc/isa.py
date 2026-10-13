"""SymRISC-32 instruction-set definition.

This module is the single source of truth for the architecture: instruction
formats, field layout, register file, opcodes, and ALU operation codes. The
assembler, disassembler, control unit, and simulator all derive from it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum

WORD_BITS = 32
WORD_MASK = 0xFFFF_FFFF
INSTRUCTION_BYTES = 4


# --------------------------------------------------------------------------- #
# Instruction formats and fields
# --------------------------------------------------------------------------- #


class Format(Enum):
    """Instruction format, selected by the most significant opcode bit."""

    B = "B"  # opcode | var1 | var2 | imm15                       (MSB = 0)
    M = "M"  # opcode | var1 | var2 | dest | shamt | unused        (MSB = 1)


@dataclass(frozen=True)
class Field:
    """A contiguous bit field ``[hi:lo]`` of a 32-bit instruction word."""

    name: str
    hi: int
    lo: int

    @property
    def width(self) -> int:
        return self.hi - self.lo + 1

    @property
    def mask(self) -> int:
        return (1 << self.width) - 1

    def extract(self, word: int) -> int:
        return (word >> self.lo) & self.mask

    def insert(self, value: int) -> int:
        if not 0 <= value <= self.mask:
            raise ValueError(f"{value} does not fit in {self.width}-bit field {self.name}")
        return value << self.lo


OPCODE = Field("opcode", 31, 27)
VAR1 = Field("var1", 26, 21)  # first source register   -> Read register 1
VAR2 = Field("var2", 20, 15)  # second source register  -> Read register 2 / B-format destination
DEST = Field("dest", 14, 9)  # M-format destination    -> Read register 3 (address / branch target)
SHAMT = Field("shamt", 8, 4)  # shift amount (5 bits: 0..31)
UNUSED = Field("unused", 3, 0)
IMM = Field("imm", 14, 0)  # 15-bit two's-complement constant

FIELDS: dict[Format, tuple[Field, ...]] = {
    Format.B: (OPCODE, VAR1, VAR2, IMM),
    Format.M: (OPCODE, VAR1, VAR2, DEST, SHAMT, UNUSED),
}

IMM_MIN = -(1 << (IMM.width - 1))  # -16384
IMM_MAX = (1 << (IMM.width - 1)) - 1  # +16383
SHAMT_MAX = SHAMT.mask  # 31


def format_of(opcode: int) -> Format:
    """Opcode bit 4 (instruction bit 31) selects the format: 0 -> B, 1 -> M."""
    return Format.M if opcode & 0b10000 else Format.B


# --------------------------------------------------------------------------- #
# Word arithmetic helpers
# --------------------------------------------------------------------------- #


def to_unsigned(value: int) -> int:
    return value & WORD_MASK


def to_signed(value: int) -> int:
    value &= WORD_MASK
    return value - (1 << WORD_BITS) if value & 0x8000_0000 else value


def sign_extend(value: int, bits: int) -> int:
    """Sign-extend a ``bits``-wide value to a 32-bit unsigned word."""
    sign = 1 << (bits - 1)
    value &= (1 << bits) - 1
    return to_unsigned((value ^ sign) - sign)


# --------------------------------------------------------------------------- #
# Register file
# --------------------------------------------------------------------------- #

NUM_REGISTERS = 64


def _build_register_names() -> tuple[str, ...]:
    names = ["Z"]
    names += [f"S{i}" for i in range(21)]  # 1..21   saved
    names += [f"T{i}" for i in range(21)]  # 22..42  temporary
    names += [f"A{i}" for i in range(17)]  # 43..59  address
    names += ["GP", "SP", "FP", "RA"]  # 60..63
    assert len(names) == NUM_REGISTERS
    return tuple(names)


REGISTER_NAMES: tuple[str, ...] = _build_register_names()

#: Register groups as ``(first, last, prefix/name, role)`` — used for documentation.
REGISTER_GROUPS = (
    (0, 0, "!Z", "Hard-wired constant zero (writes are ignored)"),
    (1, 21, "!S0 – !S20", "Saved registers"),
    (22, 42, "!T0 – !T20", "Temporary registers"),
    (43, 59, "!A0 – !A16", "Address registers (pointers, branch targets)"),
    (60, 60, "!GP", "Global pointer"),
    (61, 61, "!SP", "Stack pointer"),
    (62, 62, "!FP", "Frame pointer"),
    (63, 63, "!RA", "Return address"),
)


def register_number(token: str) -> int:
    """Parse a register token such as ``!S3``, ``!t0``, ``!RA`` or ``!R17``."""
    if not token.startswith("!"):
        raise ValueError(f"expected a register (e.g. !S0), got {token!r}")
    name = token[1:].upper()
    if name in _REGISTER_INDEX:
        return _REGISTER_INDEX[name]
    if name.startswith("R") and name[1:].isdigit():
        number = int(name[1:])
        if 0 <= number < NUM_REGISTERS:
            return number
    raise ValueError(f"unknown register {token!r}")


def register_name(number: int) -> str:
    return "!" + REGISTER_NAMES[number]


_REGISTER_INDEX = {name: i for i, name in enumerate(REGISTER_NAMES)}


# --------------------------------------------------------------------------- #
# ALU operations
# --------------------------------------------------------------------------- #


class AluOp(IntEnum):
    """4-bit ALU operation code driven by the control unit.

    Codes 0000-0111 keep the values of the original 3-bit design; NOT, SLT and
    RSUB are new (the original 3-bit field could not encode NOT separately
    from AND).
    """

    ADD = 0b0000
    SUB = 0b0001  # A - B
    AND = 0b0010
    OR = 0b0011
    DIV = 0b0100
    MUL = 0b0101
    SLL = 0b0110
    SRL = 0b0111
    NOT = 0b1000  # ~B
    SLT = 0b1001
    RSUB = 0b1010  # B - A  (used by B> so that equality is not taken)


# --------------------------------------------------------------------------- #
# Instructions
# --------------------------------------------------------------------------- #


class Syntax(Enum):
    """Assembly operand shape; also decides which fields each operand fills."""

    ASSIGN = "rt, imm"  # var2 <- imm             (var1 = !Z)
    IMMEDIATE = "rt, rs, imm"  # var2 <- var1 op imm
    REGISTER = "rd, rs, rt"  # dest <- var1 op var2
    UNARY = "rd, rt"  # dest <- op var2          (var1 = !Z)
    SHIFT = "rd, rs, shamt"  # dest <- var1 shift shamt
    MEMORY = "rt, (ra)"  # var2 <-> mem[dest]
    BRANCH = "rs, rt, ra"  # if var1 ? var2: PC <- dest


@dataclass(frozen=True)
class Instruction:
    mnemonic: str
    opcode: int
    name: str
    syntax: Syntax
    alu_op: AluOp | None
    semantics: str

    @property
    def format(self) -> Format:
        return format_of(self.opcode)


INSTRUCTIONS: tuple[Instruction, ...] = (
    # ---- B-format (opcode MSB = 0) ------------------------------------------
    Instruction("ASi", 0b00000, "Assign Immediate", Syntax.ASSIGN, AluOp.ADD, "R[rt] = imm"),
    Instruction("i++", 0b00001, "Add Immediate", Syntax.IMMEDIATE, AluOp.ADD, "R[rt] = R[rs] + imm"),
    Instruction("i&", 0b00010, "And Immediate", Syntax.IMMEDIATE, AluOp.AND, "R[rt] = R[rs] & imm"),
    Instruction("i||", 0b00011, "Or Immediate", Syntax.IMMEDIATE, AluOp.OR, "R[rt] = R[rs] | imm"),
    Instruction("i~", 0b00100, "Not Immediate", Syntax.ASSIGN, AluOp.NOT, "R[rt] = ~imm"),
    Instruction("i/", 0b00101, "Division Immediate", Syntax.IMMEDIATE, AluOp.DIV, "R[rt] = R[rs] / imm"),
    Instruction("i*", 0b01011, "Multiplication Immediate", Syntax.IMMEDIATE, AluOp.MUL, "R[rt] = R[rs] * imm"),
    Instruction("i--", 0b01100, "Subtract Immediate", Syntax.IMMEDIATE, AluOp.SUB, "R[rt] = R[rs] - imm"),
    Instruction("LA", 0b01101, "Load Address", Syntax.IMMEDIATE, AluOp.ADD, "R[rt] = R[rs] + imm"),
    # ---- M-format (opcode MSB = 1) ------------------------------------------
    Instruction("++", 0b10000, "Add", Syntax.REGISTER, AluOp.ADD, "R[rd] = R[rs] + R[rt]"),
    Instruction("--", 0b10001, "Subtract", Syntax.REGISTER, AluOp.SUB, "R[rd] = R[rs] - R[rt]"),
    Instruction("LW", 0b10010, "Load Word", Syntax.MEMORY, None, "R[rt] = M[R[ra]]"),
    Instruction("SW", 0b10011, "Store Word", Syntax.MEMORY, None, "M[R[ra]] = R[rt]"),
    Instruction("*", 0b10100, "Multiplication", Syntax.REGISTER, AluOp.MUL, "R[rd] = R[rs] * R[rt]"),
    Instruction("/", 0b10101, "Division", Syntax.REGISTER, AluOp.DIV, "R[rd] = R[rs] / R[rt]"),
    Instruction("&", 0b10110, "And", Syntax.REGISTER, AluOp.AND, "R[rd] = R[rs] & R[rt]"),
    Instruction("||", 0b10111, "Or", Syntax.REGISTER, AluOp.OR, "R[rd] = R[rs] | R[rt]"),
    Instruction("~", 0b11000, "Not", Syntax.UNARY, AluOp.NOT, "R[rd] = ~R[rt]"),
    Instruction("SLT", 0b11001, "Set Less Than", Syntax.REGISTER, AluOp.SLT, "R[rd] = (R[rs] < R[rt]) ? 1 : 0"),
    Instruction("<<", 0b11010, "Shift Left Logical", Syntax.SHIFT, AluOp.SLL, "R[rd] = R[rs] << shamt"),
    Instruction(">>", 0b11011, "Shift Right Logical", Syntax.SHIFT, AluOp.SRL, "R[rd] = R[rs] >>> shamt"),
    Instruction("B=", 0b11100, "Branch on Equal", Syntax.BRANCH, AluOp.SUB, "if (R[rs] == R[rt]) PC = R[ra]"),
    Instruction("B!=", 0b11101, "Branch on Not Equal", Syntax.BRANCH, AluOp.SUB, "if (R[rs] != R[rt]) PC = R[ra]"),
    Instruction("B<", 0b11110, "Branch Less Than", Syntax.BRANCH, AluOp.SUB, "if (R[rs] < R[rt]) PC = R[ra]"),
    Instruction("B>", 0b11111, "Branch Greater Than", Syntax.BRANCH, AluOp.RSUB, "if (R[rs] > R[rt]) PC = R[ra]"),
)

BY_OPCODE: dict[int, Instruction] = {ins.opcode: ins for ins in INSTRUCTIONS}
BY_MNEMONIC: dict[str, Instruction] = {ins.mnemonic.upper(): ins for ins in INSTRUCTIONS}

#: Opcodes not assigned to any instruction (all in the B-format half).
RESERVED_OPCODES = tuple(op for op in range(32) if op not in BY_OPCODE)
