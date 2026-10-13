"""Two-pass assembler and disassembler for SymRISC-32.

Source syntax::

    // comments start with //, # or ;
    label:  mnemonic operand, operand, ...
            .data                 // switch to data memory
    array:  .word 1, -2, 0x30     // 32-bit words
            .space 16             // zero-filled bytes (multiple of 4)
            .text                 // back to instruction memory

Registers are written ``!Z``, ``!S0``-``!S20``, ``!T0``-``!T20``,
``!A0``-``!A16``, ``!GP``, ``!SP``, ``!FP``, ``!RA``, or numerically as
``!R0``-``!R63``. Immediates accept decimal, ``0x``/``0b`` literals, labels,
and ``label+offset`` / ``label-offset`` expressions. Instruction memory and
data memory are separate address spaces (Harvard architecture), each
starting at byte address 0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import partial

from .isa import (
    BY_MNEMONIC,
    BY_OPCODE,
    DEST,
    FIELDS,
    IMM,
    IMM_MAX,
    IMM_MIN,
    INSTRUCTION_BYTES,
    INSTRUCTIONS,
    OPCODE,
    SHAMT,
    SHAMT_MAX,
    VAR1,
    VAR2,
    WORD_MASK,
    Instruction,
    Syntax,
    format_of,
    register_name,
    register_number,
    sign_extend,
    to_signed,
    to_unsigned,
)


class AssemblerError(Exception):
    def __init__(self, message: str, line_no: int = 0, source: str = "", filename: str = "<input>"):
        self.message = message
        self.line_no = line_no
        self.source = source
        self.filename = filename
        super().__init__(str(self))

    def __str__(self) -> str:
        where = f"{self.filename}:{self.line_no}: " if self.line_no else ""
        text = f"{where}error: {self.message}"
        if self.source:
            text += f"\n    {self.source.strip()}"
        return text


@dataclass
class ListingLine:
    address: int
    word: int
    line_no: int
    source: str


@dataclass
class Program:
    """An assembled program: instruction words plus an initial data image."""

    text: list[int] = field(default_factory=list)
    data: dict[int, int] = field(default_factory=dict)  # byte address -> word
    symbols: dict[str, int] = field(default_factory=dict)
    data_labels: dict[int, str] = field(default_factory=dict)  # data address -> label
    listing: list[ListingLine] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Lexing helpers
# --------------------------------------------------------------------------- #

_COMMENT = re.compile(r"//|#|;")
_LABEL = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*:")
_SYMBOL = re.compile(r"^[A-Za-z_][\w.]*$")
_MNEMONICS_LONGEST_FIRST = sorted((i.mnemonic for i in INSTRUCTIONS), key=len, reverse=True)
_MNEMONIC = re.compile(
    "^(" + "|".join(map(re.escape, _MNEMONICS_LONGEST_FIRST)) + r")(?=\s|!|$)",
    re.IGNORECASE,
)
_TERM = re.compile(r"\s*([+-]?)\s*([^+\-\s]+)\s*")


def _strip_comment(line: str) -> str:
    match = _COMMENT.search(line)
    return line[: match.start()] if match else line


def _split_operands(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    operands = [op.strip() for op in text.split(",")]
    if any(not op for op in operands):
        raise ValueError("empty operand (check for a stray comma)")
    return operands


def _evaluate(expr: str, symbols: dict[str, int]) -> int:
    """Evaluate ``number``, ``label`` or ``label±number`` style expressions."""
    expr = expr.strip()
    if not expr:
        raise ValueError("missing value")
    total, pos = 0, 0
    while pos < len(expr):
        match = _TERM.match(expr, pos)
        if not match or match.end() == pos:
            raise ValueError(f"cannot parse expression {expr!r}")
        sign, term = match.groups()
        if pos > 0 and not sign:
            raise ValueError(f"cannot parse expression {expr!r}")
        if _SYMBOL.match(term):
            if term not in symbols:
                raise ValueError(f"undefined label {term!r}")
            value = symbols[term]
        else:
            try:
                value = int(term, 0)
            except ValueError:
                raise ValueError(f"invalid number {term!r}") from None
        total += -value if sign == "-" else value
        pos = match.end()
    return total


def _split_directive(body: str) -> tuple[str, str]:
    parts = body.split(None, 1)
    return parts[0].lower(), parts[1] if len(parts) > 1 else ""


def _memory_operand(token: str) -> int:
    token = token.strip()
    if token.startswith("(") and token.endswith(")"):
        token = token[1:-1].strip()
    return register_number(token)


# --------------------------------------------------------------------------- #
# Encoding
# --------------------------------------------------------------------------- #


def encode(ins: Instruction, operands: list[str], symbols: dict[str, int] | None = None) -> int:
    """Encode a single instruction from its textual operands."""
    symbols = symbols or {}
    expected = len(ins.syntax.value.split(","))
    if len(operands) != expected:
        raise ValueError(f"{ins.mnemonic} expects {expected} operands ({ins.syntax.value}), got {len(operands)}")

    word = OPCODE.insert(ins.opcode)
    syntax = ins.syntax

    def imm(token: str) -> int:
        value = _evaluate(token, symbols)
        if not IMM_MIN <= value <= IMM_MAX:
            raise ValueError(f"immediate {value} out of range [{IMM_MIN}, {IMM_MAX}]")
        return IMM.insert(value & IMM.mask)

    if syntax is Syntax.ASSIGN:
        rt, value = operands
        word |= VAR2.insert(register_number(rt)) | imm(value)
    elif syntax is Syntax.IMMEDIATE:
        rt, rs, value = operands
        word |= VAR1.insert(register_number(rs)) | VAR2.insert(register_number(rt)) | imm(value)
    elif syntax is Syntax.REGISTER:
        rd, rs, rt = operands
        word |= VAR1.insert(register_number(rs)) | VAR2.insert(register_number(rt)) | DEST.insert(register_number(rd))
    elif syntax is Syntax.UNARY:
        rd, rt = operands
        word |= VAR2.insert(register_number(rt)) | DEST.insert(register_number(rd))
    elif syntax is Syntax.SHIFT:
        rd, rs, amount = operands
        shamt = _evaluate(amount, symbols)
        if not 0 <= shamt <= SHAMT_MAX:
            raise ValueError(f"shift amount {shamt} out of range [0, {SHAMT_MAX}]")
        word |= VAR1.insert(register_number(rs)) | DEST.insert(register_number(rd)) | SHAMT.insert(shamt)
    elif syntax is Syntax.MEMORY:
        rt, address = operands
        word |= VAR2.insert(register_number(rt)) | DEST.insert(_memory_operand(address))
    elif syntax is Syntax.BRANCH:
        rs, rt, target = operands
        word |= VAR1.insert(register_number(rs)) | VAR2.insert(register_number(rt))
        word |= DEST.insert(register_number(target))
    return word


def assemble(source: str, filename: str = "<input>") -> Program:
    """Assemble SymRISC-32 source text into a :class:`Program`."""
    # Pass 1: tokenise, assign addresses, collect labels.
    statements: list[tuple[int, str, str, str, int]] = []  # (line_no, raw, section, body, address)
    symbols: dict[str, int] = {}
    data_labels: dict[int, str] = {}
    counters = {"text": 0, "data": 0}
    section = "text"

    for line_no, raw in enumerate(source.splitlines(), start=1):
        body = _strip_comment(raw)

        fail = partial(AssemblerError, line_no=line_no, source=raw, filename=filename)

        while True:
            match = _LABEL.match(body)
            if not match:
                break
            label = match.group(1)
            if label in symbols:
                raise fail(f"duplicate label {label!r}")
            symbols[label] = counters[section]
            if section == "data":
                data_labels.setdefault(counters["data"], label)
            body = body[match.end() :]
        body = body.strip()
        if not body:
            continue

        if body.startswith("."):
            directive, rest = _split_directive(body)
            if directive in (".text", ".data"):
                if rest.strip():
                    raise fail(f"{directive} takes no operands")
                section = directive[1:]
                continue
            if section != "data":
                raise fail(f"{directive} is only allowed in the .data section")
            if directive == ".word":
                try:
                    count = len(_split_operands(rest))
                except ValueError as exc:
                    raise fail(str(exc)) from None
                if count == 0:
                    raise fail(".word needs at least one value")
                size = 4 * count
            elif directive == ".space":
                try:
                    size = _evaluate(rest, {})
                except ValueError as exc:
                    raise fail(str(exc)) from None
                if size < 0 or size % 4:
                    raise fail(".space size must be a non-negative multiple of 4")
            else:
                raise fail(f"unknown directive {directive!r}")
            statements.append((line_no, raw, section, body, counters[section]))
            counters[section] += size
            continue

        if section != "text":
            raise fail("instructions are only allowed in the .text section")
        statements.append((line_no, raw, section, body, counters["text"]))
        counters["text"] += INSTRUCTION_BYTES

    # Pass 2: encode instructions and data.
    program = Program(symbols=symbols, data_labels=data_labels)
    for line_no, raw, section, body, address in statements:
        try:
            if section == "data":
                directive, rest = _split_directive(body)
                if directive == ".word":
                    for i, token in enumerate(_split_operands(rest)):
                        value = _evaluate(token, symbols)
                        if not -(1 << 31) <= value <= WORD_MASK:
                            raise ValueError(f".word value {value} does not fit in 32 bits")
                        program.data[address + 4 * i] = to_unsigned(value)
                else:
                    for offset in range(0, _evaluate(rest, {}), 4):
                        program.data[address + offset] = 0
                continue

            match = _MNEMONIC.match(body)
            if not match:
                raise ValueError(f"unknown instruction {body.split()[0]!r}")
            ins = BY_MNEMONIC[match.group(1).upper()]
            word = encode(ins, _split_operands(body[match.end() :]), symbols)
        except ValueError as exc:
            raise AssemblerError(str(exc), line_no, raw, filename) from None
        program.text.append(word)
        program.listing.append(ListingLine(address, word, line_no, raw))
    return program


# --------------------------------------------------------------------------- #
# Disassembly
# --------------------------------------------------------------------------- #


def disassemble(word: int) -> str:
    """Render one instruction word as assembly text."""
    ins = BY_OPCODE.get(OPCODE.extract(word))
    if ins is None:
        return f".word 0x{word:08x}"
    var1 = register_name(VAR1.extract(word))
    var2 = register_name(VAR2.extract(word))
    dest = register_name(DEST.extract(word))
    imm = to_signed(sign_extend(IMM.extract(word), IMM.width))
    syntax = ins.syntax
    if syntax is Syntax.ASSIGN:
        operands = f"{var2}, {imm}"
    elif syntax is Syntax.IMMEDIATE:
        operands = f"{var2}, {var1}, {imm}"
    elif syntax is Syntax.REGISTER:
        operands = f"{dest}, {var1}, {var2}"
    elif syntax is Syntax.UNARY:
        operands = f"{dest}, {var2}"
    elif syntax is Syntax.SHIFT:
        operands = f"{dest}, {var1}, {SHAMT.extract(word)}"
    elif syntax is Syntax.MEMORY:
        operands = f"{var2}, ({dest})"
    else:
        operands = f"{var1}, {var2}, {dest}"
    return f"{ins.mnemonic:<4} {operands}"


def fields_of(word: int) -> str:
    """Show the instruction word split into its format's fields, in binary."""
    fmt = format_of(OPCODE.extract(word))
    return " ".join(format(f.extract(word), f"0{f.width}b") for f in FIELDS[fmt])
