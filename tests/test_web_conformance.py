"""The browser model (web/js/symrisc.js) must behave exactly like the Python one.

Every program below runs on both implementations; assembled words, data
images, every cycle's effects, final registers, final memory and error
messages must all match. Skipped when Node.js is not installed.
"""

import json
import random
import shutil
import subprocess
import unittest
from pathlib import Path

from symrisc import CPU, AssemblerError, MachineError, assemble
from symrisc.isa import INSTRUCTIONS, NUM_REGISTERS, Syntax

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


def run_python(job):
    out = {"error": None, "text": [], "data": [], "cycles": [], "registers": [], "memory": []}
    try:
        program = assemble(job["source"], filename="t.s")
    except AssemblerError as exc:
        out["error"] = str(exc)
        return out
    out["text"] = program.text
    out["data"] = sorted([a, w] for a, w in program.data.items())

    cpu = CPU(program, dont_care=job.get("dontCare", 0))
    for number, value in job.get("registers", {}).items():
        cpu.registers[int(number)] = value & 0xFFFF_FFFF
    try:
        for c in cpu.run(max_cycles=10_000):
            out["cycles"].append(
                [c.pc, c.word, c.reg_written, c.reg_value, c.mem_written, c.mem_value, c.branch_taken, c.next_pc]
            )
    except MachineError as exc:
        out["error"] = str(exc)
    out["registers"] = cpu.registers
    out["memory"] = [[a, cpu.memory.read(a)] for a in cpu.memory.addresses()]
    return out


def run_node(jobs):
    result = subprocess.run(
        [NODE, str(ROOT / "tests" / "web_conformance.js")],
        input=json.dumps(jobs),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


BOUNDARY = [0, 1, -1, 2, -2, 7, 31, 32, 1000, -1000, 16383, -16384, 2**31 - 1, -(2**31), 0x7FFF, 0xFFFF]


def random_operand(rng, kind):
    if kind == "imm":
        return str(rng.choice([rng.randint(-16384, 16383), rng.choice([-16384, -1, 0, 1, 16383])]))
    if kind == "shamt":
        return str(rng.randint(0, 31))
    return f"!R{rng.randrange(NUM_REGISTERS)}"


def random_program(rng, length):
    """Straight-line arithmetic, plus guarded memory accesses and forward branches."""
    alu_instructions = [i for i in INSTRUCTIONS if i.syntax not in (Syntax.MEMORY, Syntax.BRANCH)]
    lines = []
    for _ in range(length):
        roll = rng.random()
        if roll < 0.15:
            # Memory access through !A0, which only ever holds a valid, aligned address.
            lines.append(f"ASi !A0, {4 * rng.randrange(16)}")
            op = rng.choice(["LW", "SW"])
            lines.append(f"{op} !R{rng.randrange(1, 43)}, (!A0)")
        elif roll < 0.25:
            # Forward branch over the next line; the target is loaded into !A1.
            label = f"L{len(lines)}"
            op = rng.choice(["B=", "B!=", "B<", "B>"])
            lines += [f"ASi !A1, {label}", f"{op} !R{rng.randrange(43)}, !R{rng.randrange(43)}, !A1", "ASi !S0, 1"]
            lines.append(f"{label}:")
        else:
            ins = rng.choice(alu_instructions)
            kinds = [k.strip() for k in ins.syntax.value.split(",")]
            operands = [random_operand(rng, "imm" if k == "imm" else "shamt" if k == "shamt" else "reg") for k in kinds]
            # Keep !A0 / !A1 (registers 43, 44) reserved for the generator above.
            operands[0] = f"!R{rng.choice([r for r in range(NUM_REGISTERS) if r not in (43, 44)])}"
            lines.append(f"{ins.mnemonic} {', '.join(operands)}")
    return "\n".join(lines)


def random_registers(rng):
    return {str(r): rng.choice(BOUNDARY + [rng.getrandbits(32)]) for r in range(1, 43)}


ASSEMBLER_ERRORS = [
    "MOV !S0, !S1",
    "++ !S0, !S1, !Q2",
    "++ !S0, !S1",
    "ASi !A0, nowhere",
    "x: ASi !S0, 1\nx: ASi !S0, 2",
    "++ !S0, !S1, !S2,",
    ".data\nASi !S0, 1",
    ".word 5",
    ".data\n.space 3",
    ".data\n.byte 1",
    ".data\n.word 0x100000000",
    "ASi !S0, 16384",
    "<< !S0, !S1, 32",
    "ASi !S0, 08",
    "ASi !S0, 1 2",
    "LW !S0, S1",
]

FAULTS = [
    "ASi !A0, 2\nLW !S0, (!A0)",
    "i~ !A0, 3\nSW !S0, (!A0)",
    "B= !Z, !Z, !Z",
]


class WebExamplesBundleTest(unittest.TestCase):
    def test_bundle_is_up_to_date(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("build", ROOT / "scripts" / "build_web_examples.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        bundle = (ROOT / "web" / "js" / "examples.js").read_text(encoding="utf-8")
        self.assertEqual(bundle, build.render(), "run: python scripts/build_web_examples.py")


@unittest.skipUnless(NODE, "Node.js is not installed")
class WebConformanceTest(unittest.TestCase):
    def check(self, jobs):
        for job, js in zip(jobs, run_node(jobs), strict=True):
            py = run_python(job)
            for key in py:
                self.assertEqual(js[key], py[key], f"{key} differs for:\n{job['source']}")

    def test_example_programs(self):
        jobs = [
            {"source": p.read_text(encoding="utf-8"), "dontCare": dc}
            for p in sorted((ROOT / "examples").glob("*.s"))
            for dc in (0, 1)
        ]
        self.check(jobs)

    def test_assembler_errors_and_faults(self):
        self.check([{"source": s} for s in ASSEMBLER_ERRORS + FAULTS])

    def test_random_programs(self):
        rng = random.Random(320)
        jobs = [
            {"source": random_program(rng, rng.randint(5, 40)), "registers": random_registers(rng), "dontCare": i % 2}
            for i in range(300)
        ]
        self.check(jobs)


if __name__ == "__main__":
    unittest.main()
