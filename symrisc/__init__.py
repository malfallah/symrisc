"""SymRISC-32: a 32-bit RISC instruction set with symbolic mnemonics.

The package provides a reference toolchain for the architecture:

* :mod:`symrisc.isa`       - formats, fields, registers and opcodes
* :mod:`symrisc.assembler` - two-pass assembler and disassembler
* :mod:`symrisc.control`   - main control unit truth table and ALU
* :mod:`symrisc.cpu`       - signal-level single-cycle datapath model
"""

__version__ = "1.0.0"

from .assembler import AssemblerError, Program, assemble, disassemble
from .cpu import CPU, MachineError

__all__ = ["AssemblerError", "CPU", "MachineError", "Program", "assemble", "disassemble", "__version__"]
