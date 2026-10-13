"""Main control unit and ALU for the single-cycle SymRISC-32 datapath.

The signal names match the Phase 2 datapath diagram. ``None`` marks a
don't-care (X) value: the simulator can resolve don't-cares to 0 or to 1,
and the test suite checks that the choice never changes program behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import NamedTuple

from .isa import BY_OPCODE, AluOp, Syntax, to_signed, to_unsigned

Signal = int | None


@dataclass(frozen=True)
class ControlSignals:
    reg_dst: Signal  # 0: write Var2 [20:15]          1: write Dest [14:9]
    alu_src: Signal  # 0: ALU B = Read data 2         1: ALU B = sign-extended imm
    shifting: Signal  # 0: ALU B = ALUSrc mux output   1: ALU B = shamt [8:4]
    mem_read: int
    mem_write: int
    mem_to_reg: Signal  # 0: write back ALU result    1: write back memory data
    reg_write: int
    branch: int
    branch_src: Signal  # 0: condition = ~Less          1: condition = Zero
    neg_branch: Signal  # XORed with the selected condition
    alu_op: AluOp | None

    def resolve(self, dont_care: int) -> ControlSignals:
        """Return a copy with every don't-care replaced by ``dont_care``."""
        values = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None:
                value = AluOp(dont_care) if f.name == "alu_op" else dont_care
            values[f.name] = value
        return ControlSignals(**values)

    def describe(self) -> str:
        def show(v: object) -> str:
            if v is None:
                return "X"
            return v.name if isinstance(v, AluOp) else str(v)

        parts = (
            ("RegDst", self.reg_dst),
            ("ALUSrc", self.alu_src),
            ("Shift", self.shifting),
            ("MemR", self.mem_read),
            ("MemW", self.mem_write),
            ("M2R", self.mem_to_reg),
            ("RegW", self.reg_write),
            ("Br", self.branch),
            ("BrSrc", self.branch_src),
            ("NegBr", self.neg_branch),
            ("ALUOp", self.alu_op),
        )
        return " ".join(f"{k}={show(v)}" for k, v in parts)


X = None


def _signals_for(syntax: Syntax, mnemonic: str, alu_op: AluOp | None) -> ControlSignals:
    if syntax in (Syntax.REGISTER, Syntax.UNARY):
        return ControlSignals(1, 0, 0, 0, 0, 0, 1, 0, X, X, alu_op)
    if syntax in (Syntax.ASSIGN, Syntax.IMMEDIATE):
        return ControlSignals(0, 1, 0, 0, 0, 0, 1, 0, X, X, alu_op)
    if syntax is Syntax.SHIFT:
        return ControlSignals(1, X, 1, 0, 0, 0, 1, 0, X, X, alu_op)
    if mnemonic == "LW":
        return ControlSignals(0, X, X, 1, 0, 1, 1, 0, X, X, X)
    if mnemonic == "SW":
        return ControlSignals(X, X, X, 0, 1, X, 0, 0, X, X, X)
    if syntax is Syntax.BRANCH:
        branch_src = 1 if mnemonic in ("B=", "B!=") else 0
        neg_branch = 0 if mnemonic == "B=" else 1
        return ControlSignals(X, 0, 0, 0, 0, X, 0, 1, branch_src, neg_branch, alu_op)
    raise AssertionError(f"no control row for {mnemonic}")


#: Truth table of the main control unit, indexed by opcode.
CONTROL_TABLE: dict[int, ControlSignals] = {
    op: _signals_for(ins.syntax, ins.mnemonic, ins.alu_op) for op, ins in BY_OPCODE.items()
}


# --------------------------------------------------------------------------- #
# ALU
# --------------------------------------------------------------------------- #


class AluResult(NamedTuple):
    value: int  # 32-bit unsigned result
    zero: bool  # result == 0
    less: bool  # sign of the result, overflow-corrected for SUB / RSUB (N xor V)


def _divide(a: int, b: int) -> int:
    """Signed division, truncating toward zero (C semantics), never trapping."""
    if b == 0:
        return -1
    if a == -(1 << 31) and b == -1:
        return a
    quotient = abs(a) // abs(b)
    return quotient if (a < 0) == (b < 0) else -quotient


def alu(op: AluOp, a: int, b: int) -> AluResult:
    sa, sb = to_signed(a), to_signed(b)
    if op is AluOp.ADD:
        exact = sa + sb
    elif op is AluOp.SUB:
        exact = sa - sb
    elif op is AluOp.RSUB:
        exact = sb - sa
    elif op is AluOp.AND:
        exact = a & b
    elif op is AluOp.OR:
        exact = a | b
    elif op is AluOp.NOT:
        exact = ~b
    elif op is AluOp.MUL:
        exact = sa * sb
    elif op is AluOp.DIV:
        exact = _divide(sa, sb)
    elif op is AluOp.SLL:
        exact = a << (b & 31)
    elif op is AluOp.SRL:
        exact = a >> (b & 31)
    elif op is AluOp.SLT:
        exact = 1 if sa < sb else 0
    else:  # pragma: no cover - AluOp is exhaustive
        raise ValueError(f"unknown ALU operation {op!r}")

    value = to_unsigned(exact)
    if op in (AluOp.SUB, AluOp.RSUB):
        less = exact < 0
    else:
        less = bool(value & 0x8000_0000)
    return AluResult(value, value == 0, less)


__all__ = ["ControlSignals", "CONTROL_TABLE", "AluResult", "alu"]
