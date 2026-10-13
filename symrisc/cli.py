"""Command-line interface: ``symrisc asm | dis | run``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .assembler import AssemblerError, Program, assemble, disassemble, fields_of
from .cpu import CPU, MachineError
from .isa import REGISTER_NAMES, to_signed


def _load_program(path: Path) -> Program:
    """Load assembly source (``.s``/``.asm``) or a machine-code hex image."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".s", ".asm"):
        return assemble(text, filename=str(path))
    return Program(text=_parse_hex(text))


def _parse_hex(text: str) -> list[int]:
    words = []
    for line in text.splitlines():
        line = line.split("//")[0].split("#")[0].strip()
        if not line or line == "v2.0 raw":
            continue
        for token in line.split():
            words.append(int(token, 16) & 0xFFFF_FFFF)
    return words


def _format_program(program: Program, fmt: str) -> str:
    if fmt == "hex":
        return "".join(f"{w:08x}\n" for w in program.text)
    if fmt == "bin":
        return "".join(f"{w:032b}\n" for w in program.text)
    if fmt == "logisim":
        return "v2.0 raw\n" + "".join(f"{w:x}\n" for w in program.text)
    lines = [f"{'addr':<6}{'word':<10}{'fields':<40}source"]
    for entry in program.listing:
        lines.append(f"{entry.address:04x}  {entry.word:08x}  {fields_of(entry.word):<38}  {entry.source.strip()}")
    return "\n".join(lines) + "\n"


def _cmd_asm(args: argparse.Namespace) -> int:
    program = assemble(Path(args.source).read_text(encoding="utf-8"), filename=args.source)
    output = _format_program(program, args.format)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"wrote {len(program.text)} instructions to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output)
    return 0


def _cmd_dis(args: argparse.Namespace) -> int:
    for i, word in enumerate(_parse_hex(Path(args.image).read_text(encoding="utf-8"))):
        print(f"{4 * i:04x}  {word:08x}  {disassemble(word)}")
    return 0


def _parse_range(spec: str) -> tuple[int, int]:
    start, _, count = spec.partition(":")
    return int(start, 0), int(count or "1", 0)


def _cmd_run(args: argparse.Namespace) -> int:
    program = _load_program(Path(args.program))
    cpu = CPU(program, dont_care=args.dont_care)
    if args.trace:
        print(f"{'cycle':>5}  {'pc':<6}  {'word':<8}  {'instruction':<24}  effect")
    for cycle in cpu.run(args.max_cycles):
        if args.trace:
            print(cycle.describe())
            if args.signals:
                print(f"{'':>34}{cycle.control.describe()}")

    print(f"\nhalted after {cpu.cycles} cycles, PC = 0x{cpu.pc:04x}\n")
    print("registers:")
    for number, name in enumerate(REGISTER_NAMES):
        value = cpu.registers[number]
        if value:
            print(f"  !{name:<4} 0x{value:08x}  {to_signed(value):>12}")

    if args.mem:
        start, count = _parse_range(args.mem)
        addresses = [start + 4 * i for i in range(count)]
    else:
        addresses = cpu.memory.addresses()
    if addresses:
        print("\ndata memory:")
        for address in addresses:
            word = cpu.memory.read(address)
            label = program.data_labels.get(address, "")
            print(f"  0x{address:04x}  0x{word:08x}  {to_signed(word):>12}  {label}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="symrisc", description="SymRISC-32 assembler, disassembler and simulator.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    asm = sub.add_parser("asm", help="assemble a source file")
    asm.add_argument("source")
    asm.add_argument("-o", "--output", help="output file (default: stdout)")
    asm.add_argument(
        "-f",
        "--format",
        choices=("listing", "hex", "bin", "logisim"),
        default="listing",
        help="listing (default), hex ($readmemh), bin, or logisim (v2.0 raw ROM image)",
    )
    asm.set_defaults(func=_cmd_asm)

    dis = sub.add_parser("dis", help="disassemble a hex image")
    dis.add_argument("image")
    dis.set_defaults(func=_cmd_dis)

    run = sub.add_parser("run", help="run a program on the single-cycle datapath model")
    run.add_argument("program", help=".s/.asm source or a hex image")
    run.add_argument("-t", "--trace", action="store_true", help="print every cycle")
    run.add_argument("-s", "--signals", action="store_true", help="with --trace, also print control signals")
    run.add_argument("-m", "--mem", metavar="ADDR:COUNT", help="dump COUNT data words starting at ADDR")
    run.add_argument("--max-cycles", type=int, default=1_000_000)
    run.add_argument("--dont-care", type=int, choices=(0, 1), default=0, help="value driven on X control signals")
    run.set_defaults(func=_cmd_run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (AssemblerError, MachineError, OSError, ValueError) as exc:
        print(f"symrisc: {exc}", file=sys.stderr)
        return 1
