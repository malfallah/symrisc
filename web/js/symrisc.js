/*
 * SymRISC-32 reference model for the browser.
 *
 * A direct port of the Python package (symrisc/isa.py, assembler.py,
 * control.py and cpu.py). tests/test_web_conformance.py runs both
 * implementations on the same programs and requires identical results,
 * cycle by cycle.
 *
 * Loads as a classic script (window.SymRISC) so the visualizer also works
 * from file://, and as a CommonJS module for Node.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.SymRISC = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ------------------------------------------------------------------------
  // Fields and word helpers
  // ------------------------------------------------------------------------

  const INSTRUCTION_BYTES = 4;
  const WORD_MAX = 0xffffffff;

  function makeField(name, hi, lo) {
    const width = hi - lo + 1;
    const mask = 2 ** width - 1;
    return {
      name, hi, lo, width, mask,
      extract: (word) => (word >>> lo) & mask,
      insert(value) {
        if (!(value >= 0 && value <= mask)) {
          throw new RangeError(`${value} does not fit in ${width}-bit field ${name}`);
        }
        return (value << lo) >>> 0;
      },
    };
  }

  const OPCODE = makeField("opcode", 31, 27);
  const VAR1 = makeField("var1", 26, 21);
  const VAR2 = makeField("var2", 20, 15);
  const DEST = makeField("dest", 14, 9);
  const SHAMT = makeField("shamt", 8, 4);
  const UNUSED = makeField("unused", 3, 0);
  const IMM = makeField("imm", 14, 0);

  const FIELDS = {
    B: [OPCODE, VAR1, VAR2, IMM],
    M: [OPCODE, VAR1, VAR2, DEST, SHAMT, UNUSED],
  };

  const IMM_MIN = -(2 ** (IMM.width - 1));
  const IMM_MAX = 2 ** (IMM.width - 1) - 1;
  const SHAMT_MAX = SHAMT.mask;

  const formatOf = (opcode) => (opcode & 0b10000 ? "M" : "B");
  const toUnsigned = (v) => v >>> 0;
  const toSigned = (v) => v | 0;

  function signExtend(value, bits) {
    const sign = 2 ** (bits - 1);
    value = value & (2 ** bits - 1);
    return toUnsigned((value ^ sign) - sign);
  }

  // ------------------------------------------------------------------------
  // Registers
  // ------------------------------------------------------------------------

  const REGISTER_NAMES = ["Z"];
  for (let i = 0; i < 21; i++) REGISTER_NAMES.push(`S${i}`);
  for (let i = 0; i < 21; i++) REGISTER_NAMES.push(`T${i}`);
  for (let i = 0; i < 17; i++) REGISTER_NAMES.push(`A${i}`);
  REGISTER_NAMES.push("GP", "SP", "FP", "RA");
  const NUM_REGISTERS = REGISTER_NAMES.length; // 64

  const REGISTER_INDEX = new Map(REGISTER_NAMES.map((name, i) => [name, i]));

  function registerNumber(token) {
    if (!token.startsWith("!")) throw new SyntaxError(`expected a register (e.g. !S0), got '${token}'`);
    const name = token.slice(1).toUpperCase();
    if (REGISTER_INDEX.has(name)) return REGISTER_INDEX.get(name);
    if (/^R[0-9]+$/.test(name)) {
      const number = parseInt(name.slice(1), 10);
      if (number < NUM_REGISTERS) return number;
    }
    throw new SyntaxError(`unknown register '${token}'`);
  }

  const registerName = (number) => "!" + REGISTER_NAMES[number];

  // ------------------------------------------------------------------------
  // ALU operations and instructions
  // ------------------------------------------------------------------------

  const AluOp = { ADD: 0, SUB: 1, AND: 2, OR: 3, DIV: 4, MUL: 5, SLL: 6, SRL: 7, NOT: 8, SLT: 9, RSUB: 10 };
  const ALU_OP_NAMES = Object.fromEntries(Object.entries(AluOp).map(([k, v]) => [v, k]));

  const Syntax = {
    ASSIGN: "rt, imm",
    IMMEDIATE: "rt, rs, imm",
    REGISTER: "rd, rs, rt",
    UNARY: "rd, rt",
    SHIFT: "rd, rs, shamt",
    MEMORY: "rt, (ra)",
    BRANCH: "rs, rt, ra",
  };

  const I = (mnemonic, opcode, name, syntax, aluOp, semantics) => ({
    mnemonic, opcode, name, syntax, aluOp, semantics, format: formatOf(opcode),
  });

  const INSTRUCTIONS = [
    I("ASi", 0b00000, "Assign Immediate", "ASSIGN", AluOp.ADD, "R[rt] = imm"),
    I("i++", 0b00001, "Add Immediate", "IMMEDIATE", AluOp.ADD, "R[rt] = R[rs] + imm"),
    I("i&", 0b00010, "And Immediate", "IMMEDIATE", AluOp.AND, "R[rt] = R[rs] & imm"),
    I("i||", 0b00011, "Or Immediate", "IMMEDIATE", AluOp.OR, "R[rt] = R[rs] | imm"),
    I("i~", 0b00100, "Not Immediate", "ASSIGN", AluOp.NOT, "R[rt] = ~imm"),
    I("i/", 0b00101, "Division Immediate", "IMMEDIATE", AluOp.DIV, "R[rt] = R[rs] / imm"),
    I("i*", 0b01011, "Multiplication Immediate", "IMMEDIATE", AluOp.MUL, "R[rt] = R[rs] * imm"),
    I("i--", 0b01100, "Subtract Immediate", "IMMEDIATE", AluOp.SUB, "R[rt] = R[rs] - imm"),
    I("LA", 0b01101, "Load Address", "IMMEDIATE", AluOp.ADD, "R[rt] = R[rs] + imm"),
    I("++", 0b10000, "Add", "REGISTER", AluOp.ADD, "R[rd] = R[rs] + R[rt]"),
    I("--", 0b10001, "Subtract", "REGISTER", AluOp.SUB, "R[rd] = R[rs] - R[rt]"),
    I("LW", 0b10010, "Load Word", "MEMORY", null, "R[rt] = M[R[ra]]"),
    I("SW", 0b10011, "Store Word", "MEMORY", null, "M[R[ra]] = R[rt]"),
    I("*", 0b10100, "Multiplication", "REGISTER", AluOp.MUL, "R[rd] = R[rs] * R[rt]"),
    I("/", 0b10101, "Division", "REGISTER", AluOp.DIV, "R[rd] = R[rs] / R[rt]"),
    I("&", 0b10110, "And", "REGISTER", AluOp.AND, "R[rd] = R[rs] & R[rt]"),
    I("||", 0b10111, "Or", "REGISTER", AluOp.OR, "R[rd] = R[rs] | R[rt]"),
    I("~", 0b11000, "Not", "UNARY", AluOp.NOT, "R[rd] = ~R[rt]"),
    I("SLT", 0b11001, "Set Less Than", "REGISTER", AluOp.SLT, "R[rd] = (R[rs] < R[rt]) ? 1 : 0"),
    I("<<", 0b11010, "Shift Left Logical", "SHIFT", AluOp.SLL, "R[rd] = R[rs] << shamt"),
    I(">>", 0b11011, "Shift Right Logical", "SHIFT", AluOp.SRL, "R[rd] = R[rs] >>> shamt"),
    I("B=", 0b11100, "Branch on Equal", "BRANCH", AluOp.SUB, "if (R[rs] == R[rt]) PC = R[ra]"),
    I("B!=", 0b11101, "Branch on Not Equal", "BRANCH", AluOp.SUB, "if (R[rs] != R[rt]) PC = R[ra]"),
    I("B<", 0b11110, "Branch Less Than", "BRANCH", AluOp.SUB, "if (R[rs] < R[rt]) PC = R[ra]"),
    I("B>", 0b11111, "Branch Greater Than", "BRANCH", AluOp.RSUB, "if (R[rs] > R[rt]) PC = R[ra]"),
  ];

  const BY_OPCODE = new Map(INSTRUCTIONS.map((ins) => [ins.opcode, ins]));
  const BY_MNEMONIC = new Map(INSTRUCTIONS.map((ins) => [ins.mnemonic.toUpperCase(), ins]));

  // ------------------------------------------------------------------------
  // Control unit (null = don't care)
  // ------------------------------------------------------------------------

  const SIGNAL_NAMES = [
    "regDst", "aluSrc", "shifting", "memRead", "memWrite", "memToReg",
    "regWrite", "branch", "branchSrc", "negBranch", "aluOp",
  ];
  const SIGNAL_LABELS = {
    regDst: "RegDst", aluSrc: "ALUSrc", shifting: "Shifting", memRead: "MemRead",
    memWrite: "MemWrite", memToReg: "MemtoReg", regWrite: "RegWrite", branch: "Branch",
    branchSrc: "BranchSrc", negBranch: "NegBranch", aluOp: "ALUOp",
  };

  const X = null;
  function signals(values) {
    const out = {};
    SIGNAL_NAMES.forEach((name, i) => (out[name] = values[i]));
    return Object.freeze(out);
  }

  function signalsFor(ins) {
    const s = ins.syntax, op = ins.aluOp;
    if (s === "REGISTER" || s === "UNARY") return signals([1, 0, 0, 0, 0, 0, 1, 0, X, X, op]);
    if (s === "ASSIGN" || s === "IMMEDIATE") return signals([0, 1, 0, 0, 0, 0, 1, 0, X, X, op]);
    if (s === "SHIFT") return signals([1, X, 1, 0, 0, 0, 1, 0, X, X, op]);
    if (ins.mnemonic === "LW") return signals([0, X, X, 1, 0, 1, 1, 0, X, X, X]);
    if (ins.mnemonic === "SW") return signals([X, X, X, 0, 1, X, 0, 0, X, X, X]);
    if (s === "BRANCH") {
      const branchSrc = ins.mnemonic === "B=" || ins.mnemonic === "B!=" ? 1 : 0;
      const negBranch = ins.mnemonic === "B=" ? 0 : 1;
      return signals([X, 0, 0, 0, 0, X, 0, 1, branchSrc, negBranch, op]);
    }
    throw new Error(`no control row for ${ins.mnemonic}`);
  }

  const CONTROL_TABLE = new Map(INSTRUCTIONS.map((ins) => [ins.opcode, signalsFor(ins)]));

  function resolveSignals(sig, dontCare) {
    const out = {};
    for (const name of SIGNAL_NAMES) out[name] = sig[name] === null ? dontCare : sig[name];
    return out;
  }

  // ------------------------------------------------------------------------
  // ALU
  // ------------------------------------------------------------------------

  function divide(a, b) {
    if (b === 0) return -1;
    if (a === -2147483648 && b === -1) return a;
    return Math.trunc(a / b);
  }

  /** a, b are unsigned 32-bit words. Returns {value, zero, less}. */
  function alu(op, a, b) {
    const sa = toSigned(a), sb = toSigned(b);
    let exact;
    switch (op) {
      case AluOp.ADD: exact = sa + sb; break;
      case AluOp.SUB: exact = sa - sb; break;
      case AluOp.RSUB: exact = sb - sa; break;
      case AluOp.AND: exact = a & b; break;
      case AluOp.OR: exact = a | b; break;
      case AluOp.NOT: exact = ~b; break;
      case AluOp.MUL: exact = Math.imul(sa, sb); break;
      case AluOp.DIV: exact = divide(sa, sb); break;
      case AluOp.SLL: exact = a << (b & 31); break;
      case AluOp.SRL: exact = a >>> (b & 31); break;
      case AluOp.SLT: exact = sa < sb ? 1 : 0; break;
      default: throw new Error(`unknown ALU operation ${op}`);
    }
    const value = toUnsigned(exact);
    const less = op === AluOp.SUB || op === AluOp.RSUB ? exact < 0 : value >>> 31 === 1;
    return { value, zero: value === 0, less };
  }

  // ------------------------------------------------------------------------
  // Assembler
  // ------------------------------------------------------------------------

  class AssemblerError extends Error {
    constructor(message, lineNo = 0, source = "", filename = "<input>") {
      super(message);
      this.name = "AssemblerError";
      this.detail = message;
      this.lineNo = lineNo;
      this.source = source;
      this.filename = filename;
    }
    toString() {
      const where = this.lineNo ? `${this.filename}:${this.lineNo}: ` : "";
      return `${where}error: ${this.detail}` + (this.source ? `\n    ${this.source.trim()}` : "");
    }
  }

  const COMMENT = /\/\/|#|;/;
  const LABEL = /^\s*([A-Za-z_][\w.]*)\s*:/;
  const SYMBOL = /^[A-Za-z_][\w.]*$/;
  const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const MNEMONIC = new RegExp(
    "^(" + INSTRUCTIONS.map((i) => i.mnemonic).sort((a, b) => b.length - a.length).map(escapeRe).join("|") + ")(?=\\s|!|$)",
    "i",
  );

  function stripComment(line) {
    const m = COMMENT.exec(line);
    return m ? line.slice(0, m.index) : line;
  }

  function splitOperands(text) {
    text = text.trim();
    if (!text) return [];
    const operands = text.split(",").map((op) => op.trim());
    if (operands.some((op) => !op)) throw new SyntaxError("empty operand (check for a stray comma)");
    return operands;
  }

  function parseNumber(term) {
    const t = term.replace(/_/g, "");
    let m;
    if ((m = /^0[xX]([0-9a-fA-F]+)$/.exec(t))) return parseInt(m[1], 16);
    if ((m = /^0[bB]([01]+)$/.exec(t))) return parseInt(m[1], 2);
    if ((m = /^0[oO]([0-7]+)$/.exec(t))) return parseInt(m[1], 8);
    if (/^(0+|[1-9][0-9]*)$/.test(t)) return parseInt(t, 10);
    throw new SyntaxError(`invalid number '${term}'`);
  }

  function evaluate(expr, symbols) {
    expr = expr.trim();
    if (!expr) throw new SyntaxError("missing value");
    const TERM = /\s*([+-]?)\s*([^+\-\s]+)\s*/y;
    let total = 0, pos = 0;
    while (pos < expr.length) {
      TERM.lastIndex = pos;
      const m = TERM.exec(expr);
      if (!m || TERM.lastIndex === pos) throw new SyntaxError(`cannot parse expression '${expr}'`);
      const [, sign, term] = m;
      if (pos > 0 && !sign) throw new SyntaxError(`cannot parse expression '${expr}'`);
      let value;
      if (SYMBOL.test(term)) {
        if (!symbols.has(term)) throw new SyntaxError(`undefined label '${term}'`);
        value = symbols.get(term);
      } else {
        value = parseNumber(term);
      }
      total += sign === "-" ? -value : value;
      pos = TERM.lastIndex;
    }
    return total;
  }

  function memoryOperand(token) {
    token = token.trim();
    if (token.startsWith("(") && token.endsWith(")")) token = token.slice(1, -1).trim();
    return registerNumber(token);
  }

  function encode(ins, operands, symbols = new Map()) {
    const expected = Syntax[ins.syntax].split(",").length;
    if (operands.length !== expected) {
      throw new SyntaxError(
        `${ins.mnemonic} expects ${expected} operands (${Syntax[ins.syntax]}), got ${operands.length}`,
      );
    }
    const imm = (token) => {
      const value = evaluate(token, symbols);
      if (!(value >= IMM_MIN && value <= IMM_MAX)) {
        throw new RangeError(`immediate ${value} out of range [${IMM_MIN}, ${IMM_MAX}]`);
      }
      return IMM.insert(value & IMM.mask);
    };
    const reg = registerNumber;
    let word = OPCODE.insert(ins.opcode);
    const [a, b, c] = operands;
    switch (ins.syntax) {
      case "ASSIGN": word |= VAR2.insert(reg(a)) | imm(b); break;
      case "IMMEDIATE": word |= VAR1.insert(reg(b)) | VAR2.insert(reg(a)) | imm(c); break;
      case "REGISTER": word |= VAR1.insert(reg(b)) | VAR2.insert(reg(c)) | DEST.insert(reg(a)); break;
      case "UNARY": word |= VAR2.insert(reg(b)) | DEST.insert(reg(a)); break;
      case "SHIFT": {
        const shamt = evaluate(c, symbols);
        if (!(shamt >= 0 && shamt <= SHAMT_MAX)) throw new RangeError(`shift amount ${shamt} out of range [0, ${SHAMT_MAX}]`);
        word |= VAR1.insert(reg(b)) | DEST.insert(reg(a)) | SHAMT.insert(shamt);
        break;
      }
      case "MEMORY": word |= VAR2.insert(reg(a)) | DEST.insert(memoryOperand(b)); break;
      case "BRANCH": word |= VAR1.insert(reg(a)) | VAR2.insert(reg(b)) | DEST.insert(reg(c)); break;
    }
    return word >>> 0;
  }

  function splitDirective(body) {
    const m = /^(\S+)\s*([\s\S]*)$/.exec(body);
    return [m[1].toLowerCase(), m[2]];
  }

  /** Assemble source text into {text, data: Map, symbols: Map, dataLabels: Map, listing}. */
  function assemble(source, filename = "<input>") {
    const statements = [];
    const symbols = new Map();
    const dataLabels = new Map();
    const counters = { text: 0, data: 0 };
    let section = "text";
    const lines = source.split(/\r\n|\r|\n/);

    lines.forEach((raw, index) => {
      const lineNo = index + 1;
      const fail = (message) => new AssemblerError(message, lineNo, raw, filename);
      let body = stripComment(raw);
      let m;
      while ((m = LABEL.exec(body))) {
        const label = m[1];
        if (symbols.has(label)) throw fail(`duplicate label '${label}'`);
        symbols.set(label, counters[section]);
        if (section === "data" && !dataLabels.has(counters.data)) dataLabels.set(counters.data, label);
        body = body.slice(m[0].length);
      }
      body = body.trim();
      if (!body) return;

      if (body.startsWith(".")) {
        const [directive, rest] = splitDirective(body);
        if (directive === ".text" || directive === ".data") {
          if (rest.trim()) throw fail(`${directive} takes no operands`);
          section = directive.slice(1);
          return;
        }
        if (section !== "data") throw fail(`${directive} is only allowed in the .data section`);
        let size;
        try {
          if (directive === ".word") {
            const count = splitOperands(rest).length;
            if (count === 0) throw new SyntaxError(".word needs at least one value");
            size = 4 * count;
          } else if (directive === ".space") {
            size = evaluate(rest, new Map());
            if (size < 0 || size % 4) throw new SyntaxError(".space size must be a non-negative multiple of 4");
          } else {
            throw new SyntaxError(`unknown directive '${directive}'`);
          }
        } catch (err) {
          throw fail(err.message);
        }
        statements.push({ lineNo, raw, section, body, address: counters[section] });
        counters[section] += size;
        return;
      }

      if (section !== "text") throw fail("instructions are only allowed in the .text section");
      statements.push({ lineNo, raw, section, body, address: counters.text });
      counters.text += INSTRUCTION_BYTES;
    });

    const program = { text: [], data: new Map(), symbols, dataLabels, listing: [] };
    for (const { lineNo, raw, section, body, address } of statements) {
      try {
        if (section === "data") {
          const [directive, rest] = splitDirective(body);
          if (directive === ".word") {
            splitOperands(rest).forEach((token, i) => {
              const value = evaluate(token, symbols);
              if (!(value >= -(2 ** 31) && value <= WORD_MAX)) {
                throw new RangeError(`.word value ${value} does not fit in 32 bits`);
              }
              program.data.set(address + 4 * i, toUnsigned(value));
            });
          } else {
            const size = evaluate(rest, new Map());
            for (let offset = 0; offset < size; offset += 4) program.data.set(address + offset, 0);
          }
          continue;
        }
        const m = MNEMONIC.exec(body);
        if (!m) throw new SyntaxError(`unknown instruction '${body.split(/\s+/)[0]}'`);
        const ins = BY_MNEMONIC.get(m[1].toUpperCase());
        const word = encode(ins, splitOperands(body.slice(m[0].length)), symbols);
        program.text.push(word);
        program.listing.push({ address, word, lineNo, source: raw });
      } catch (err) {
        if (err instanceof AssemblerError) throw err;
        throw new AssemblerError(err.message, lineNo, raw, filename);
      }
    }
    return program;
  }

  // ------------------------------------------------------------------------
  // Disassembler
  // ------------------------------------------------------------------------

  function disassemble(word) {
    const ins = BY_OPCODE.get(OPCODE.extract(word));
    if (!ins) return `.word 0x${hex(word)}`;
    const var1 = registerName(VAR1.extract(word));
    const var2 = registerName(VAR2.extract(word));
    const dest = registerName(DEST.extract(word));
    const imm = toSigned(signExtend(IMM.extract(word), IMM.width));
    let operands;
    switch (ins.syntax) {
      case "ASSIGN": operands = `${var2}, ${imm}`; break;
      case "IMMEDIATE": operands = `${var2}, ${var1}, ${imm}`; break;
      case "REGISTER": operands = `${dest}, ${var1}, ${var2}`; break;
      case "UNARY": operands = `${dest}, ${var2}`; break;
      case "SHIFT": operands = `${dest}, ${var1}, ${SHAMT.extract(word)}`; break;
      case "MEMORY": operands = `${var2}, (${dest})`; break;
      default: operands = `${var1}, ${var2}, ${dest}`;
    }
    return `${ins.mnemonic.padEnd(4)} ${operands}`;
  }

  const hex = (word, digits = 8) => (word >>> 0).toString(16).padStart(digits, "0");

  // ------------------------------------------------------------------------
  // Single-cycle datapath
  // ------------------------------------------------------------------------

  class MachineError extends Error {
    constructor(message) {
      super(message);
      this.name = "MachineError";
    }
  }

  class DataMemory {
    constructor(sizeBytes = 64 * 1024, image = new Map()) {
      this.size = sizeBytes;
      this.words = new Map();
      for (const [address, word] of image) this.write(address, word);
    }
    check(address) {
      if (address % 4) throw new MachineError(`misaligned data access at 0x${hex(address)}`);
      if (!(address >= 0 && address < this.size)) throw new MachineError(`data access out of range at 0x${hex(address)}`);
    }
    read(address) {
      this.check(address);
      return this.words.has(address) ? this.words.get(address) : 0;
    }
    write(address, word) {
      this.check(address);
      this.words.set(address, toUnsigned(word));
    }
    addresses() {
      return [...this.words.keys()].sort((a, b) => a - b);
    }
  }

  class CPU {
    constructor(program, { memorySize = 64 * 1024, dontCare = 0 } = {}) {
      this.instructions = program.text.slice();
      this.memory = new DataMemory(memorySize, program.data);
      this.registers = new Array(NUM_REGISTERS).fill(0);
      this.pc = 0;
      this.cycles = 0;
      this.dontCare = dontCare;
    }

    get halted() {
      return this.pc % INSTRUCTION_BYTES !== 0 || !(this.pc >= 0 && this.pc / INSTRUCTION_BYTES < this.instructions.length);
    }

    reg(number) {
      return toSigned(this.registers[number]);
    }

    /** Evaluate one clock cycle; returns every wire value of interest. */
    step() {
      if (this.halted) throw new MachineError(`no instruction at PC 0x${hex(this.pc)}`);
      const pc = this.pc;
      const word = this.instructions[pc / INSTRUCTION_BYTES];

      const opcode = OPCODE.extract(word);
      if (!CONTROL_TABLE.has(opcode)) {
        throw new MachineError(`illegal opcode ${opcode.toString(2).padStart(5, "0")} at PC 0x${hex(pc)}`);
      }
      const signals = CONTROL_TABLE.get(opcode);
      const ctl = resolveSignals(signals, this.dontCare);
      const var1 = VAR1.extract(word), var2 = VAR2.extract(word), dest = DEST.extract(word);
      const shamt = SHAMT.extract(word);

      const read1 = this.registers[var1], read2 = this.registers[var2], read3 = this.registers[dest];

      const immediate = signExtend(IMM.extract(word), IMM.width);
      const aluSrcOut = ctl.aluSrc === 0 ? read2 : immediate;
      const operandB = ctl.shifting ? shamt : aluSrcOut;
      const result = alu(ctl.aluOp, read1, operandB);

      const memData = ctl.memRead ? this.memory.read(read3) : 0;
      let memWritten = null, memValue = null, memPrevious;
      if (ctl.memWrite) {
        memPrevious = this.memory.words.get(read3);
        this.memory.write(read3, read2);
        memWritten = read3;
        memValue = read2;
      }

      let regWritten = null, regValue = null, regPrevious = null;
      const writeRegister = ctl.regDst ? dest : var2;
      const writeData = ctl.memToReg ? memData : result.value;
      if (ctl.regWrite && writeRegister !== 0) {
        regPrevious = this.registers[writeRegister];
        this.registers[writeRegister] = writeData;
        regWritten = writeRegister;
        regValue = writeData;
      }

      const condition = ctl.branchSrc ? result.zero : !result.less;
      const taken = Boolean(ctl.branch) && Boolean(condition) !== Boolean(ctl.negBranch);
      const pcPlus4 = toUnsigned(pc + INSTRUCTION_BYTES);
      this.pc = taken ? read3 : pcPlus4;
      this.cycles += 1;

      return {
        number: this.cycles, pc, word, opcode, signals, resolved: ctl,
        var1, var2, dest, shamt, read1, read2, read3, immediate, aluSrcOut, operandB,
        aluResult: result.value, zero: result.zero, less: result.less,
        memData, memWritten, memValue, memPrevious,
        writeRegister, writeData, regWritten, regValue, regPrevious,
        condition, branchTaken: taken, pcPlus4, nextPc: this.pc,
      };
    }

    /** Reverse the effects of the most recent cycle (as returned by step()). */
    undo(cycle) {
      if (cycle.regWritten !== null) this.registers[cycle.regWritten] = cycle.regPrevious;
      if (cycle.memWritten !== null) {
        if (cycle.memPrevious === undefined) this.memory.words.delete(cycle.memWritten);
        else this.memory.words.set(cycle.memWritten, cycle.memPrevious);
      }
      this.pc = cycle.pc;
      this.cycles -= 1;
    }
  }

  return {
    INSTRUCTION_BYTES, OPCODE, VAR1, VAR2, DEST, SHAMT, UNUSED, IMM, FIELDS, IMM_MIN, IMM_MAX, SHAMT_MAX,
    REGISTER_NAMES, NUM_REGISTERS, AluOp, ALU_OP_NAMES, Syntax, INSTRUCTIONS, BY_OPCODE, BY_MNEMONIC,
    SIGNAL_NAMES, SIGNAL_LABELS, CONTROL_TABLE,
    AssemblerError, MachineError, DataMemory, CPU,
    alu, assemble, disassemble, encode, formatOf, hex, registerName, registerNumber, signExtend, toSigned, toUnsigned,
  };
});
