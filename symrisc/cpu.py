"""Signal-level model of the SymRISC-32 single-cycle datapath.

Each call to :meth:`CPU.step` evaluates one clock cycle by driving the same
wires and multiplexers as the Phase 2 datapath diagram:

* Read register 1/2/3 are fed from Var1 [26:21], Var2 [20:15] and Dest [14:9].
* ``RegDst`` selects the write register (Var2 or Dest).
* ``ALUSrc`` and ``Shifting`` select ALU operand B (Read data 2, the
  sign-extended immediate, or the shift amount).
* Data memory is addressed by Read data 3 and written with Read data 2.
* The branch unit selects ``Zero`` or ``~Less`` (``BranchSrc``), XORs it with
  ``NegBranch`` and ANDs it with ``Branch``; when taken, the PC loads
  Read data 3, otherwise PC + 4.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .assembler import Program, disassemble
from .control import CONTROL_TABLE, ControlSignals, alu
from .isa import (
    DEST,
    IMM,
    INSTRUCTION_BYTES,
    NUM_REGISTERS,
    OPCODE,
    SHAMT,
    VAR1,
    VAR2,
    register_name,
    sign_extend,
    to_signed,
    to_unsigned,
)


class MachineError(Exception):
    """Raised for architectural faults (illegal opcode, bad memory access)."""


class DataMemory:
    """Word-addressable data memory with byte addresses and alignment checks."""

    def __init__(self, size_bytes: int = 64 * 1024, image: dict[int, int] | None = None):
        self.size = size_bytes
        self._words: dict[int, int] = {}
        for address, word in (image or {}).items():
            self.write(address, word)

    def _check(self, address: int) -> None:
        if address % 4:
            raise MachineError(f"misaligned data access at 0x{address:08x}")
        if not 0 <= address < self.size:
            raise MachineError(f"data access out of range at 0x{address:08x}")

    def read(self, address: int) -> int:
        self._check(address)
        return self._words.get(address, 0)

    def write(self, address: int, word: int) -> None:
        self._check(address)
        self._words[address] = to_unsigned(word)

    def addresses(self) -> list[int]:
        """Byte addresses that have ever been initialised or written."""
        return sorted(self._words)

    def words(self, start: int, count: int, signed: bool = False) -> list[int]:
        """Read ``count`` consecutive words starting at byte address ``start``."""
        words = [self.read(start + 4 * i) for i in range(count)]
        return [to_signed(w) for w in words] if signed else words


@dataclass
class Cycle:
    """Everything observable about one executed clock cycle."""

    number: int
    pc: int
    word: int
    control: ControlSignals  # as specified by the control table (None = X)
    alu_result: int
    branch_taken: bool
    next_pc: int
    reg_written: int | None
    reg_value: int | None
    mem_written: int | None
    mem_value: int | None

    def describe(self) -> str:
        effects = []
        if self.reg_written is not None:
            effects.append(f"{register_name(self.reg_written)} = {to_signed(self.reg_value or 0)}")
        if self.mem_written is not None:
            effects.append(f"M[0x{self.mem_written:04x}] = {to_signed(self.mem_value or 0)}")
        if self.branch_taken:
            effects.append(f"PC -> 0x{self.next_pc:04x}")
        text = f"{self.number:>5}  0x{self.pc:04x}  {self.word:08x}  {disassemble(self.word):<24}"
        return f"{text}  {', '.join(effects) or '-'}"


class CPU:
    def __init__(self, program: Program, memory_size: int = 64 * 1024, dont_care: int = 0):
        if dont_care not in (0, 1):
            raise ValueError("dont_care must be 0 or 1")
        self.instructions = list(program.text)
        self.memory = DataMemory(memory_size, program.data)
        self.registers = [0] * NUM_REGISTERS
        self.pc = 0
        self.cycles = 0
        self.dont_care = dont_care

    @property
    def halted(self) -> bool:
        """The machine stops when the PC leaves the loaded program."""
        index, offset = divmod(self.pc, INSTRUCTION_BYTES)
        return offset != 0 or not 0 <= index < len(self.instructions)

    def reg(self, number: int) -> int:
        """Signed value of a register."""
        return to_signed(self.registers[number])

    def step(self) -> Cycle:
        if self.halted:
            raise MachineError(f"no instruction at PC 0x{self.pc:08x}")
        pc = self.pc
        word = self.instructions[pc // INSTRUCTION_BYTES]

        # Decode
        opcode = OPCODE.extract(word)
        if opcode not in CONTROL_TABLE:
            raise MachineError(f"illegal opcode {opcode:05b} at PC 0x{pc:08x}")
        signals = CONTROL_TABLE[opcode]
        ctl = signals.resolve(self.dont_care)
        var1, var2, dest = VAR1.extract(word), VAR2.extract(word), DEST.extract(word)

        # Register file read
        read1, read2, read3 = self.registers[var1], self.registers[var2], self.registers[dest]

        # Execute
        immediate = sign_extend(IMM.extract(word), IMM.width)
        operand_b = read2 if ctl.alu_src == 0 else immediate
        if ctl.shifting:
            operand_b = SHAMT.extract(word)
        result = alu(ctl.alu_op, read1, operand_b)  # type: ignore[arg-type]

        # Memory
        mem_data = self.memory.read(read3) if ctl.mem_read else 0
        mem_written = mem_value = None
        if ctl.mem_write:
            self.memory.write(read3, read2)
            mem_written, mem_value = read3, read2

        # Write back
        reg_written = reg_value = None
        if ctl.reg_write:
            target = dest if ctl.reg_dst else var2
            value = mem_data if ctl.mem_to_reg else result.value
            if target != 0:  # !Z is hard-wired to zero
                self.registers[target] = value
                reg_written, reg_value = target, value

        # Next PC
        condition = result.zero if ctl.branch_src else not result.less
        taken = bool(ctl.branch) and (bool(condition) != bool(ctl.neg_branch))
        self.pc = read3 if taken else to_unsigned(pc + INSTRUCTION_BYTES)

        self.cycles += 1
        return Cycle(
            self.cycles,
            pc,
            word,
            signals,
            result.value,
            taken,
            self.pc,
            reg_written,
            reg_value,
            mem_written,
            mem_value,
        )

    def run(self, max_cycles: int = 1_000_000) -> Iterable[Cycle]:
        """Execute until the program ends, yielding every cycle."""
        while not self.halted:
            if self.cycles >= max_cycles:
                raise MachineError(f"did not halt within {max_cycles} cycles")
            yield self.step()

    def run_to_completion(self, max_cycles: int = 1_000_000) -> CPU:
        for _ in self.run(max_cycles):
            pass
        return self
