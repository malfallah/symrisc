// Runs programs on the browser model (web/js/symrisc.js) and prints the
// results as JSON. Driven by tests/test_web_conformance.py, which runs the
// same programs on the Python model and compares the two.
//
// stdin:  [{"source": str, "registers": {number: value}, "dontCare": 0|1}, ...]
// stdout: [{"error": str|null, "text": [...], "data": [[addr, word], ...],
//           "cycles": [[pc, word, regWritten, regValue, memWritten, memValue, taken, nextPc], ...],
//           "registers": [...], "memory": [[addr, word], ...]}, ...]
"use strict";

const path = require("path");
const SymRISC = require(path.join(__dirname, "..", "web", "js", "symrisc.js"));

function run(job) {
  const out = { error: null, text: [], data: [], cycles: [], registers: [], memory: [] };
  let program;
  try {
    program = SymRISC.assemble(job.source, "t.s");
  } catch (err) {
    out.error = String(err);
    return out;
  }
  out.text = program.text;
  out.data = [...program.data.entries()].sort((a, b) => a[0] - b[0]);

  const cpu = new SymRISC.CPU(program, { dontCare: job.dontCare || 0 });
  for (const [number, value] of Object.entries(job.registers || {})) {
    cpu.registers[Number(number)] = value >>> 0;
  }
  try {
    while (!cpu.halted) {
      if (cpu.cycles >= 10000) throw new SymRISC.MachineError("did not halt within 10000 cycles");
      const c = cpu.step();
      out.cycles.push([c.pc, c.word, c.regWritten, c.regValue, c.memWritten, c.memValue, c.branchTaken, c.nextPc]);
    }
  } catch (err) {
    if (!(err instanceof SymRISC.MachineError)) throw err;
    out.error = err.message;
  }
  out.registers = cpu.registers;
  out.memory = cpu.memory.addresses().map((a) => [a, cpu.memory.read(a)]);
  return out;
}

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  process.stdout.write(JSON.stringify(JSON.parse(input).map(run)));
});
