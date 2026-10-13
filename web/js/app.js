/*
 * SymRISC-32 Datapath Visualizer - UI layer.
 *
 * The simulation itself lives in symrisc.js. Every cycle returns the value on
 * each wire of the datapath, and the highlighting below is derived from the
 * control signals alone: a path lights up exactly when the hardware uses it.
 */
(function () {
  "use strict";

  const S = window.SymRISC;
  const EXAMPLES = window.SYMRISC_EXAMPLES || [];
  const $ = (id) => document.getElementById(id);
  const SVG_NS = "http://www.w3.org/2000/svg";
  const RUN_TO_END_LIMIT = 200000;
  const HISTORY_LIMIT = 200000;

  const state = {
    name: "",
    source: "",
    program: null,
    cpu: null,
    history: [],
    fault: null,
    radix: "dec",
    timer: null,
    breakpoints: new Set(),
  };

  // ------------------------------------------------------------------ formatting

  const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch]);
  const val = (v) => (state.radix === "hex" ? "0x" + S.hex(v) : String(S.toSigned(v)));
  const addr = (v) => "0x" + S.hex(v, 4);
  const reg = S.registerName;
  const sig = (v) => (v === null ? "X" : String(v));
  const aluName = (op) => (op === null ? "X" : S.ALU_OP_NAMES[op]);

  // ------------------------------------------------------------------ static setup

  function buildControlRows() {
    const group = $("ctrl-signals");
    S.SIGNAL_NAMES.forEach((name, i) => {
      const col = i < 6 ? 0 : 1;
      const row = i % 6;
      const x = col === 0 ? 396 : 516;
      const y = 76 + row * 21;
      const g = document.createElementNS(SVG_NS, "g");
      g.setAttribute("class", "ctrl-row");
      g.id = "c-" + name;
      const label = document.createElementNS(SVG_NS, "text");
      label.setAttribute("x", x);
      label.setAttribute("y", y);
      label.textContent = S.SIGNAL_LABELS[name];
      const value = document.createElementNS(SVG_NS, "text");
      value.setAttribute("x", x + (col === 0 ? 102 : 104));
      value.setAttribute("y", y);
      value.setAttribute("class", "val");
      g.append(label, value);
      group.append(g);
    });
  }

  function buildExampleMenu() {
    const select = $("example");
    EXAMPLES.forEach((ex, i) => select.add(new Option(ex.title, String(i))));
    select.add(new Option("Custom program", "custom"));
  }

  function buildRegisters() {
    const box = $("registers");
    box.innerHTML = S.REGISTER_NAMES.map(
      (name, i) => `<div class="reg" id="r-${i}"><span class="n">!${name}</span><span class="v"></span></div>`,
    ).join("");
  }

  // ------------------------------------------------------------------ program loading

  function load(source, name) {
    let program;
    try {
      program = S.assemble(source, name);
    } catch (err) {
      if (!(err instanceof S.AssemblerError)) throw err;
      showAsmError(String(err));
      return false;
    }
    showAsmError(null);
    stop();
    state.name = name;
    state.source = source;
    state.program = program;
    state.breakpoints.clear();
    buildListing();
    reset();
    return true;
  }

  function showAsmError(message) {
    const box = $("asm-error");
    box.hidden = !message;
    box.textContent = message || "";
  }

  function reset() {
    stop();
    state.cpu = new S.CPU(state.program);
    state.history = [];
    state.fault = null;
    render();
  }

  function buildListing() {
    const rows = state.program.listing.map((entry) => {
      const source = entry.source.replace(/\s+$/, "");
      return (
        `<div class="row" data-address="${entry.address}" title="Line ${entry.lineNo}">` +
        `<span class="bp"></span><span class="addr">${S.hex(entry.address, 4)}</span>` +
        `<span class="word">${S.hex(entry.word)}</span><span class="src">${esc(source.trim())}</span></div>`
      );
    });
    $("listing").innerHTML = rows.join("") || `<p class="hint" style="padding:8px">No instructions.</p>`;
  }

  // ------------------------------------------------------------------ execution

  function stepOnce() {
    const cpu = state.cpu;
    if (cpu.halted || state.fault) return null;
    try {
      const cycle = cpu.step();
      state.history.push(cycle);
      if (state.history.length > HISTORY_LIMIT) state.history.splice(0, HISTORY_LIMIT / 10);
      return cycle;
    } catch (err) {
      if (!(err instanceof S.MachineError)) throw err;
      state.fault = err.message;
      return null;
    }
  }

  function step() {
    stepOnce();
    render();
  }

  function back() {
    stop();
    if (state.fault) {
      state.fault = null;
    } else if (state.history.length) {
      state.cpu.undo(state.history.pop());
    }
    render();
  }

  function atBreakpoint() {
    return state.breakpoints.has(state.cpu.pc);
  }

  function runToEnd() {
    stop();
    let n = 0;
    while (!state.cpu.halted && !state.fault && n < RUN_TO_END_LIMIT) {
      stepOnce();
      n++;
      if (atBreakpoint()) break;
    }
    if (n >= RUN_TO_END_LIMIT && !state.cpu.halted) {
      state.fault = `stopped after ${RUN_TO_END_LIMIT.toLocaleString()} cycles (infinite loop?)`;
    }
    render();
  }

  function toggleRun() {
    if (state.timer) {
      stop();
      render();
      return;
    }
    if (state.cpu.halted || state.fault) return;
    const tick = () => {
      stepOnce();
      const done = state.cpu.halted || state.fault || atBreakpoint();
      if (done) state.timer = null;
      else state.timer = setTimeout(tick, 1000 / Number($("speed").value));
      render();
    };
    state.timer = setTimeout(tick, 0);
    render();
  }

  function stop() {
    if (state.timer) clearTimeout(state.timer);
    state.timer = null;
  }

  // ------------------------------------------------------------------ rendering

  function render() {
    const cycle = state.history.length ? state.history[state.history.length - 1] : null;
    const usage = cycle ? usageOf(cycle) : null;
    renderStatus(cycle);
    renderDatapath(cycle, usage);
    renderDecode(cycle);
    renderExplanation(cycle, usage);
    renderRegisters(cycle, usage);
    renderMemory(cycle);
    renderListing(cycle);
    renderButtons();
  }

  /** Which parts of the datapath this cycle uses, derived from the control signals. */
  function usageOf(c) {
    const s = c.signals;
    const aluUsed = s.aluOp !== null;
    const bShamt = aluUsed && s.shifting === 1;
    const bImm = aluUsed && !bShamt && s.aluSrc === 1;
    const bRd2 = aluUsed && !bShamt && s.aluSrc === 0;
    return {
      aluUsed,
      aluA: aluUsed && s.aluOp !== S.AluOp.NOT,
      bShamt,
      bImm,
      bRd2,
      mem: s.memRead === 1 || s.memWrite === 1,
      memRead: s.memRead === 1,
      memWrite: s.memWrite === 1,
      wb: s.regWrite === 1,
      br: s.branch === 1,
    };
  }

  function renderStatus(cycle) {
    const pill = $("status-pill");
    let label = "Ready", cls = "";
    if (state.fault) [label, cls] = ["Fault", "fault"];
    else if (state.cpu.halted) [label, cls] = ["Halted", "halted"];
    else if (state.timer) [label, cls] = ["Running", "running"];
    else if (cycle) label = "Paused";
    pill.textContent = label;
    pill.className = "pill " + cls;
    $("status-cycle").textContent = state.cpu.cycles;
    $("status-pc").textContent = addr(state.cpu.pc);
    $("status-ins").textContent = cycle ? S.disassemble(cycle.word) : "";
  }

  function setClass(id, cls, on) {
    const el = $(id);
    if (el) el.classList.toggle(cls, Boolean(on));
  }

  function setText(id, text, cls) {
    const el = $(id);
    el.textContent = text;
    if (cls !== undefined) el.setAttribute("class", cls);
  }

  function renderDatapath(c, u) {
    const on = Boolean(c);
    const s = c ? c.signals : {};
    const taken = c ? c.branchTaken : false;

    const wires = {
      "w-next": on, "w-pc": on, "w-pc-add": on, "w-four": on, "w-inst": on, "w-bus": on, "w-op": on,
      "w-pc4": on && !taken,
      "w-var1": u && u.aluA, "w-rd1": u && u.aluA,
      "w-var2": u && (u.bRd2 || u.memWrite), "w-rd2": u && u.bRd2, "w-rd2-mem": u && u.memWrite,
      "w-dest": u && (u.mem || u.br), "w-rd3-mem": u && u.mem, "w-rd3-pc": u && u.br && taken,
      "w-var2-dst": u && u.wb && s.regDst === 0, "w-dest-dst": u && u.wb && s.regDst === 1, "w-wr": u && u.wb,
      "w-imm": u && u.bImm, "w-se": u && u.bImm, "w-shamt": u && u.bShamt,
      "w-alusrc": u && (u.bRd2 || u.bImm), "w-aluB": u && u.aluUsed,
      "w-result": u && u.wb && s.memToReg === 0, "w-memout": u && u.wb && s.memToReg === 1, "w-wb": u && u.wb,
      "w-zero": u && u.br && s.branchSrc === 1, "w-less": u && u.br && s.branchSrc === 0,
      "w-less-n": u && u.br && s.branchSrc === 0, "w-bsrc": u && u.br, "w-negb": u && u.br,
      "w-xor": u && u.br, "w-br": u && u.br, "w-pcsrc": u && u.br,
    };
    for (const [id, active] of Object.entries(wires)) setClass(id, "active", active);
    setClass("d-pc", "active", on);
    setClass("d-var2", "active", wires["w-var2-dst"] && wires["w-var2"]);
    setClass("d-dest", "active", wires["w-dest-dst"] && wires["w-dest"]);
    setClass("d-rd2", "active", wires["w-rd2-mem"]);
    setClass("d-rd3", "active", wires["w-rd3-pc"] && wires["w-rd3-mem"]);

    const hot = {
      "u-pc": on, "u-im": on, "u-add": on, "u-ctrl": on, "u-rf": on, "m-pc": on,
      "m-regdst": u && u.wb, "u-se": u && u.bImm, "m-alusrc": u && (u.bRd2 || u.bImm), "m-shift": u && u.aluUsed,
      "u-alu": u && u.aluUsed, "u-dm": u && u.mem, "m-m2r": u && u.wb,
      "g-not": u && u.br && s.branchSrc === 0, "g-xor": u && u.br, "g-and": u && u.br,
    };
    for (const [id, active] of Object.entries(hot)) setClass(id, "hot", active);
    setClass("m-bsrc", "ctrl-hot", u && u.br);

    // control unit contents
    for (const name of S.SIGNAL_NAMES) {
      const row = $("c-" + name);
      const v = c ? s[name] : undefined;
      const text = v === undefined ? "–" : name === "aluOp" ? aluName(v) : sig(v);
      row.lastChild.textContent = text;
      row.setAttribute("class", "ctrl-row " + (v === null ? "x" : v === undefined ? "" : v ? "on" : "off"));
    }
    setText("alu-op", c && u.aluUsed ? aluName(s.aluOp) : "");

    // badges next to the multiplexers they drive
    const badge = (id, label, v, hotNow, ctl) =>
      setText(id, c ? `${label}=${sig(v)}` : label, hotNow ? (ctl ? "ctl" : "on") : "");
    badge("b-regDst", "RegDst", s.regDst, u && u.wb);
    badge("b-aluSrc", "ALUSrc", s.aluSrc, u && (u.bRd2 || u.bImm));
    badge("b-shifting", "Shifting", s.shifting, u && u.aluUsed);
    badge("b-memToReg", "MemtoReg", s.memToReg, u && u.wb);
    badge("b-branchSrc", "BranchSrc", s.branchSrc, u && u.br, true);
    badge("b-negBranch", "NegBranch", s.negBranch, u && u.br, true);
    badge("b-branch", "Branch", s.branch, u && u.br, true);
    badge("b-regWrite", "RegWrite", s.regWrite, u && u.wb);
    setText("b-pcsrc", c ? `PCSrc=${taken ? 1 : 0}` : "PCSrc", u && u.br ? "ctl" : "");
    setText("b-mem", c ? `MemRead=${sig(s.memRead)}  MemWrite=${sig(s.memWrite)}` : "MemRead  MemWrite", u && u.mem ? "on" : "");

    // wire values
    const show = (id, cond, text) => setText(id, cond ? text : "");
    show("v-pc", on, c && addr(c.pc));
    show("v-inst", on, c && "0x" + S.hex(c.word));
    show("v-pc4", on, c && addr(c.pcPlus4));
    show("v-wr", u && u.wb, c && reg(c.writeRegister));
    show("v-rd1", u && u.aluA, c && val(c.read1));
    show("v-rd2", u && (u.bRd2 || u.memWrite), c && val(c.read2));
    show("v-rd3", u && (u.mem || u.br), c && addr(c.read3));
    show("v-imm", u && u.bImm, c && val(c.immediate));
    show("v-shamt", u && u.bShamt, c && String(c.shamt));
    show("v-aluB", u && u.aluUsed, c && "B = " + val(c.operandB));
    show("v-zero", u && u.br, c && (c.zero ? "1" : "0"));
    show("v-less", u && u.br, c && (c.less ? "1" : "0"));
    show("v-result", u && u.aluUsed, c && val(c.aluResult));
    show("v-memout", u && u.memRead, c && val(c.memData));
    show("v-wd", u && u.wb, c && `${reg(c.writeRegister)} ← ${val(c.writeData)}`);
    show("v-target", u && u.br, c && "target " + addr(c.read3));
    show("v-next", on, c && addr(c.nextPc));
  }

  function renderDecode(c) {
    const cpu = state.cpu;
    let word = c ? c.word : null;
    let caption = "executed";
    if (word === null && !cpu.halted) {
      word = cpu.instructions[cpu.pc / 4];
      caption = "next";
    }
    const box = $("decode");
    if (word === null) {
      box.innerHTML = "";
      return;
    }
    const opcode = S.OPCODE.extract(word);
    const ins = S.BY_OPCODE.get(opcode);
    const fields = S.FIELDS[S.formatOf(opcode)];
    const meaning = (f, v) => {
      switch (f.name) {
        case "opcode": return ins ? `${ins.format}-format <b>${esc(ins.mnemonic)}</b>` : "<b>illegal</b>";
        case "var1": case "var2": case "dest": return `${f.name} <b>${reg(v)}</b>`;
        case "imm": return `imm <b>${S.toSigned(S.signExtend(v, 15))}</b>`;
        case "shamt": return `shamt <b>${v}</b>`;
        default: return "unused";
      }
    };
    box.innerHTML =
      fields
        .map((f) => {
          const v = f.extract(word);
          return (
            `<div class="field f-${f.name}" style="flex:${f.width} 1 0" title="bits [${f.hi}:${f.lo}]">` +
            `<span class="bits">${v.toString(2).padStart(f.width, "0")}</span>` +
            `<span class="meta">${meaning(f, v)}</span></div>`
          );
        })
        .join("") + `<span class="hint" style="align-self:center">${caption}</span>`;
  }

  function renderExplanation(c, u) {
    const box = $("explain");
    const cpu = state.cpu;
    if (state.fault) {
      box.innerHTML = `<h3>Fault</h3><p>${esc(state.fault)}</p><p class="muted">Press Back to return to the last good state, or Reset.</p>`;
      return;
    }
    if (!c) {
      box.innerHTML = cpu.halted
        ? `<p>This program has no instructions.</p>`
        : `<h3>Ready</h3><p>Press <b>Step</b> to execute the instruction at <code>${addr(cpu.pc)}</code>. ` +
          `The datapath then shows which wires, multiplexers and control signals that instruction uses.</p>`;
      return;
    }
    const ins = S.BY_OPCODE.get(c.opcode);
    const s = c.signals;
    const items = [];
    const pcStep = () =>
      items.push(`PC ← PC + 4 = <code>${addr(c.pcPlus4)}</code>`);

    if (ins.syntax === "BRANCH") {
      const reverse = s.aluOp === S.AluOp.RSUB;
      items.push(
        `ALU <b>${reverse ? "RSUB" : "SUB"}</b>: ${reverse ? "B − A" : "A − B"} with A = <code>${reg(c.var1)} = ${val(c.read1)}</code>, ` +
          `B = <code>${reg(c.var2)} = ${val(c.read2)}</code> → <code>${val(c.aluResult)}</code> (Zero = ${+c.zero}, Less = ${+c.less})`,
      );
      const cond = s.branchSrc ? c.zero : !c.less;
      items.push(`BranchSrc = ${s.branchSrc} selects ${s.branchSrc ? "Zero" : "¬Less"} = <b>${+cond}</b>`);
      items.push(`${+cond} ⊕ NegBranch (${s.negBranch}) = ${+(cond !== Boolean(s.negBranch))}, AND Branch (1) → PCSrc = <b>${+c.branchTaken}</b>`);
      items.push(
        c.branchTaken
          ? `<b>Taken:</b> PC ← ${reg(c.dest)} = <code>${addr(c.nextPc)}</code>`
          : `<b>Not taken:</b> PC ← PC + 4 = <code>${addr(c.pcPlus4)}</code>`,
      );
    } else if (ins.mnemonic === "LW") {
      items.push(`Address from Read data 3: <code>${reg(c.dest)} = ${addr(c.read3)}</code>`);
      items.push(`MemRead = 1: memory returns <code>${val(c.memData)}</code>`);
      items.push(`MemtoReg = 1, RegDst = 0 → <code>${reg(c.var2)} ← ${val(c.writeData)}</code>${c.var2 === 0 ? " (discarded: !Z is hard-wired)" : ""}`);
      pcStep();
    } else if (ins.mnemonic === "SW") {
      items.push(`Address from Read data 3: <code>${reg(c.dest)} = ${addr(c.read3)}</code>`);
      items.push(`MemWrite = 1: <code>M[${addr(c.read3)}] ← ${reg(c.var2)} = ${val(c.read2)}</code>; RegWrite = 0`);
      pcStep();
    } else {
      let b;
      if (u.bShamt) b = `shamt = ${c.shamt}`;
      else if (u.bImm) b = `imm = ${val(c.immediate)}`;
      else b = `${reg(c.var2)} = ${val(c.read2)}`;
      const a = u.aluA ? `A = <code>${reg(c.var1)} = ${val(c.read1)}</code>, ` : "";
      items.push(`ALU <b>${aluName(s.aluOp)}</b>: ${a}B = <code>${b}</code> → <code>${val(c.aluResult)}</code>`);
      const target = s.regDst ? "Dest" : "Var2";
      items.push(
        `RegDst = ${s.regDst} selects ${target} → <code>${reg(c.writeRegister)} ← ${val(c.writeData)}</code>` +
          (c.writeRegister === 0 ? " (discarded: !Z is hard-wired to zero)" : ""),
      );
      pcStep();
    }

    const finished = cpu.halted ? `<p class="muted">Program finished after ${cpu.cycles} cycles.</p>` : "";
    box.innerHTML =
      `<h3><code>${esc(S.disassemble(c.word))}</code> · ${esc(ins.name)}</h3>` +
      `<p class="muted"><code>${esc(ins.semantics)}</code></p>` +
      `<ol>${items.map((i) => `<li>${i}</li>`).join("")}</ol>` +
      finished;
  }

  function renderRegisters(c, u) {
    const cpu = state.cpu;
    const reads = new Set();
    if (c) {
      if (u.aluA) reads.add(c.var1);
      if (u.bRd2 || u.memWrite) reads.add(c.var2);
      if (u.mem || u.br) reads.add(c.dest);
    }
    const onlyNonZero = $("only-nonzero").checked;
    for (let i = 0; i < S.NUM_REGISTERS; i++) {
      const el = $("r-" + i);
      const v = cpu.registers[i];
      const written = c && c.regWritten === i;
      const read = reads.has(i);
      el.lastChild.textContent = val(v);
      el.className = "reg" + (v === 0 ? " zero" : "") + (read ? " rd" : "") + (written ? " wr" : "");
      el.hidden = onlyNonZero && v === 0 && !read && !written;
    }
  }

  function renderMemory(c) {
    const cpu = state.cpu;
    const addresses = new Set(cpu.memory.addresses());
    const readAt = c && c.signals.memRead === 1 ? c.read3 : null;
    if (readAt !== null) addresses.add(readAt);
    const sorted = [...addresses].sort((a, b) => a - b);
    const box = $("memory");
    if (!sorted.length) {
      box.innerHTML = `<p class="empty">No data. Add a <code>.data</code> section to your program.</p>`;
      return;
    }
    box.innerHTML = sorted
      .map((a) => {
        const cls = c && c.memWritten === a ? " wr" : a === readAt ? " rd" : "";
        const label = state.program.dataLabels.get(a) || "";
        return `<div class="mem${cls}"><span class="a">${addr(a)}</span><span class="v">${val(cpu.memory.read(a))}</span><span class="l">${esc(label)}</span></div>`;
      })
      .join("");
  }

  function renderListing(c) {
    const cpu = state.cpu;
    let nextRow = null;
    for (const row of $("listing").querySelectorAll(".row")) {
      const a = Number(row.dataset.address);
      row.classList.toggle("exec", Boolean(c) && c.pc === a);
      const isNext = !cpu.halted && !state.fault && cpu.pc === a;
      row.classList.toggle("next", isNext);
      row.classList.toggle("has-bp", state.breakpoints.has(a));
      if (isNext) nextRow = row;
    }
    if (nextRow && !$("listing").hidden) nextRow.scrollIntoView({ block: "nearest" });
  }

  function renderButtons() {
    const done = state.cpu.halted || Boolean(state.fault);
    $("btn-back").disabled = !state.history.length && !state.fault;
    $("btn-step").disabled = done || Boolean(state.timer);
    $("btn-end").disabled = done;
    $("btn-run").disabled = done && !state.timer;
    $("btn-run").textContent = state.timer ? "Pause" : "Run";
    $("btn-run").classList.toggle("active", Boolean(state.timer));
    $("btn-radix").textContent = state.radix === "hex" ? "Hex" : "Dec";
  }

  // ------------------------------------------------------------------ share links

  function encodeSource(text) {
    const bytes = new TextEncoder().encode(text);
    let binary = "";
    for (const b of bytes) binary += String.fromCharCode(b);
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function decodeSource(encoded) {
    const binary = atob(encoded.replace(/-/g, "+").replace(/_/g, "/"));
    return new TextDecoder().decode(Uint8Array.from(binary, (ch) => ch.charCodeAt(0)));
  }

  async function share() {
    const url = location.href.split("#")[0] + "#code=" + encodeSource(state.source);
    history.replaceState(null, "", url);
    const button = $("btn-share");
    try {
      await navigator.clipboard.writeText(url);
      button.textContent = "Link copied";
    } catch {
      button.textContent = "Link in address bar";
    }
    setTimeout(() => (button.textContent = "Share"), 1800);
  }

  // ------------------------------------------------------------------ tabs and wiring

  function showTab(edit) {
    $("tab-listing").setAttribute("aria-selected", String(!edit));
    $("tab-edit").setAttribute("aria-selected", String(edit));
    $("listing").hidden = edit;
    $("editor-pane").hidden = !edit;
    document.querySelector(".listing-hint").hidden = edit;
    if (edit) $("editor").value = state.source;
  }

  function assembleFromEditor() {
    if (load($("editor").value, "custom.s")) {
      $("example").value = "custom";
      showTab(false);
    }
  }

  function loadExample(index) {
    const ex = EXAMPLES[index];
    if (!ex) return;
    load(ex.source, ex.name);
    $("example").value = String(index);
    if (!$("editor-pane").hidden) $("editor").value = ex.source;
  }

  function wireEvents() {
    $("btn-reset").addEventListener("click", reset);
    $("btn-back").addEventListener("click", back);
    $("btn-step").addEventListener("click", step);
    $("btn-run").addEventListener("click", toggleRun);
    $("btn-end").addEventListener("click", runToEnd);
    $("btn-radix").addEventListener("click", () => {
      state.radix = state.radix === "dec" ? "hex" : "dec";
      render();
    });
    $("btn-share").addEventListener("click", share);
    $("speed").addEventListener("input", () => ($("speed-out").textContent = $("speed").value + "/s"));
    $("only-nonzero").addEventListener("change", render);
    $("tab-listing").addEventListener("click", () => showTab(false));
    $("tab-edit").addEventListener("click", () => showTab(true));
    $("btn-assemble").addEventListener("click", assembleFromEditor);
    $("example").addEventListener("change", (e) => {
      if (e.target.value === "custom") showTab(true);
      else loadExample(Number(e.target.value));
    });
    $("listing").addEventListener("click", (e) => {
      const row = e.target.closest(".row");
      if (!row) return;
      const a = Number(row.dataset.address);
      if (state.breakpoints.has(a)) state.breakpoints.delete(a);
      else state.breakpoints.add(a);
      renderListing(state.history[state.history.length - 1] || null);
    });
    $("editor").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        assembleFromEditor();
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.target.closest("textarea, input, select") || e.ctrlKey || e.metaKey || e.altKey) return;
      const actions = {
        ArrowRight: () => !$("btn-step").disabled && step(),
        ArrowLeft: () => !$("btn-back").disabled && back(),
        " ": () => !$("btn-run").disabled && toggleRun(),
        r: reset,
        R: reset,
      };
      if (actions[e.key]) {
        if (e.target.closest("button") && (e.key === " " || e.key === "Enter")) return;
        e.preventDefault();
        actions[e.key]();
      }
    });
  }

  // ------------------------------------------------------------------ start

  function start() {
    buildControlRows();
    buildExampleMenu();
    buildRegisters();
    wireEvents();
    loadExample(0);
    const match = /#code=([A-Za-z0-9_-]+)/.exec(location.hash);
    if (!match) return;
    let source;
    try {
      source = decodeSource(match[1]);
    } catch {
      return; // malformed link: keep the default example
    }
    $("example").value = "custom";
    if (!load(source, "shared.s")) {
      showTab(true);
      $("editor").value = source; // let the user fix the reported error
    }
  }

  start();
})();
