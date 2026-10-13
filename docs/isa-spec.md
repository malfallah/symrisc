# SymRISC-32 Instruction Set Architecture

**Version 1.0**

This document is the normative specification of SymRISC-32. The reference implementation in [`symrisc/`](../symrisc) implements it, and the test suite in [`tests/`](../tests) exercises its rules. For the hardware that implements the ISA, see [microarchitecture.md](microarchitecture.md). For what changed relative to the original 2022 coursework reports, see [errata.md](errata.md).

## Contents

1. [Design principles](#1-design-principles)
2. [Programmer's model](#2-programmers-model)
3. [Instruction formats](#3-instruction-formats)
4. [Opcode map](#4-opcode-map)
5. [Instruction reference](#5-instruction-reference)
6. [Execution semantics](#6-execution-semantics)
7. [Assembly language](#7-assembly-language)
8. [Encoding examples](#8-encoding-examples)

---

## 1. Design principles

SymRISC-32 is a load/store RISC architecture. The design follows these rules:

| Principle | How SymRISC-32 applies it |
|---|---|
| **Fixed-length instructions** | Every instruction is one 32-bit word, so the PC always advances by 4. |
| **Few, regular formats** | There are two formats. Opcode bit 31 alone selects between them. |
| **Load/store** | Only `LW` and `SW` touch data memory. Every other instruction operates on registers. |
| **Large register file** | 64 general-purpose registers, addressed by 6-bit fields. This reduces how often values must be spilled to memory. |
| **Harvard memory** | Instruction memory and data memory are separate, so one instruction can be fetched and one data access made in the same cycle. |
| **Symbolic mnemonics** | Operations are written as the operator they perform (`++`, `--`, `*`, `/`, `&`, `\|\|`, `~`, `<<`, `>>`, `B<` …). An `i` prefix marks the immediate form, and registers carry a `!` sigil. |
| **Single-cycle implementable** | Every instruction completes in one pass through a datapath: fetch → decode/read → ALU → memory → write-back. |

> **RISC vs. CISC in brief.** A CISC machine (such as x86) offers complex, variable-length instructions that may read memory, compute, and write memory in a single instruction. That shrinks code size, but it needs multi-cycle or microcoded control. A RISC machine (such as MIPS or RISC-V) restricts memory access to loads and stores and keeps instructions simple and uniform. Programs need more instructions, but each one is cheap to decode and easy to pipeline: performance = instructions × CPI × cycle time, and RISC trades a higher instruction count for a lower CPI and a shorter cycle. SymRISC-32 sits firmly on the RISC side.

## 2. Programmer's model

### 2.1 Registers

There are 64 registers, each 32 bits wide, identified by a 6-bit number. In assembly they are written with a `!` sigil, either by role name or numerically as `!R0`–`!R63`.

| Register | Number | Binary | Role |
|---|---|---|---|
| `!Z` | 0 | `000000` | Hard-wired zero. Reads return 0 and writes are ignored. |
| `!S0` – `!S20` | 1 – 21 | `000001` – `010101` | Saved registers (long-lived values) |
| `!T0` – `!T20` | 22 – 42 | `010110` – `101010` | Temporary registers (scratch values) |
| `!A0` – `!A16` | 43 – 59 | `101011` – `111011` | Address registers (pointers, branch targets) |
| `!GP` | 60 | `111100` | Global pointer |
| `!SP` | 61 | `111101` | Stack pointer |
| `!FP` | 62 | `111110` | Frame pointer |
| `!RA` | 63 | `111111` | Return address |

The saved, temporary, and address roles are software conventions. The hardware treats registers 1–63 identically.

### 2.2 Program counter

`PC` is a 32-bit byte address into instruction memory. Execution begins at address `0`. Instructions are word-aligned, and after a non-branching instruction the PC increments by **4 bytes**.

### 2.3 Memory

* **Instruction memory** and **data memory** are separate, byte-addressed spaces, and each starts at address `0`.
* Data memory is accessed only as aligned 32-bit words. An address that is not a multiple of 4 is an alignment fault.
* The reference simulator provides 64 KiB of data memory by default.

### 2.4 Data types

Registers hold 32-bit words. Arithmetic is two's-complement, and every comparison (`SLT`, `B<`, `B>`) is **signed**.

## 3. Instruction formats

The most significant opcode bit (instruction bit 31) selects the format: **0 → B-format**, **1 → M-format**.

```
B-format (immediate)
 31      27 26        21 20        15 14                            0
┌──────────┬────────────┬────────────┬───────────────────────────────┐
│  opcode  │    Var1    │    Var2    │        Constant / Address     │
│    5     │     6      │     6      │               15              │
└──────────┴────────────┴────────────┴───────────────────────────────┘

M-format (register)
 31      27 26        21 20        15 14         9 8        4 3      0
┌──────────┬────────────┬────────────┬────────────┬──────────┬────────┐
│  opcode  │    Var1    │    Var2    │    Dest    │  Shamt   │ unused │
│    5     │     6      │     6      │     6      │    5     │   4    │
└──────────┴────────────┴────────────┴────────────┴──────────┴────────┘
```

| Field | Bits | Width | Meaning |
|---|---|---|---|
| opcode | 31:27 | 5 | Operation. Bit 31 selects the format. |
| Var1 | 26:21 | 6 | First source register (`rs`), which drives ALU operand A |
| Var2 | 20:15 | 6 | Second source register (`rt`). In the B-format it is the **destination**. |
| Dest | 14:9 | 6 | M-format destination (`rd`), memory-address register, or branch-target register (`ra`) |
| Shamt | 8:4 | 5 | Shift amount, 0 – 31 |
| unused | 3:0 | 4 | Must be zero |
| Constant | 14:0 | 15 | Two's-complement immediate, sign-extended to 32 bits. Range −16384 … +16383. |

Register fields sit in the same bit positions in both formats. This lets the register file start reading before the instruction has been fully decoded.

## 4. Opcode map

Rows are `opcode[4:3]` and columns are `opcode[2:0]`. A cell marked — is reserved, and executing a reserved opcode is an illegal-instruction fault.

| `[4:3]` \ `[2:0]` | `000` | `001` | `010` | `011` | `100` | `101` | `110` | `111` |
|---|---|---|---|---|---|---|---|---|
| **`00`** (B) | `ASi` | `i++` | `i&` | `i\|\|` | `i~` | `i/` | — | — |
| **`01`** (B) | — | — | — | `i*` | `i--` | `LA` | — | — |
| **`10`** (M) | `++` | `--` | `LW` | `SW` | `*` | `/` | `&` | `\|\|` |
| **`11`** (M) | `~` | `SLT` | `<<` | `>>` | `B=` | `B!=` | `B<` | `B>` |

There are 25 instructions: 9 in the B-format and 16 in the M-format. Seven B-format opcodes (`00110`, `00111`, `01000`, `01001`, `01010`, `01110`, `01111`) are free for future extensions.

## 5. Instruction reference

`rs` = Var1, `rt` = Var2, `rd` = Dest (M-format destination), `ra` = Dest used as an address/target register, `imm` = sign-extended constant.

| Opcode | Hex | Fmt | Mnemonic | Name | Syntax | Operation |
|---|---|---|---|---|---|---|
| `00000` | `00` | B | `ASi` | Assign Immediate | `ASi rt, imm` | `R[rt] = imm` |
| `00001` | `01` | B | `i++` | Add Immediate | `i++ rt, rs, imm` | `R[rt] = R[rs] + imm` |
| `00010` | `02` | B | `i&` | And Immediate | `i& rt, rs, imm` | `R[rt] = R[rs] & imm` |
| `00011` | `03` | B | `i\|\|` | Or Immediate | `i\|\| rt, rs, imm` | `R[rt] = R[rs] \| imm` |
| `00100` | `04` | B | `i~` | Not Immediate | `i~ rt, imm` | `R[rt] = ~imm` |
| `00101` | `05` | B | `i/` | Division Immediate | `i/ rt, rs, imm` | `R[rt] = R[rs] / imm` |
| `01011` | `0B` | B | `i*` | Multiplication Immediate | `i* rt, rs, imm` | `R[rt] = R[rs] * imm` |
| `01100` | `0C` | B | `i--` | Subtract Immediate | `i-- rt, rs, imm` | `R[rt] = R[rs] - imm` |
| `01101` | `0D` | B | `LA` | Load Address | `LA rt, rs, imm` | `R[rt] = R[rs] + imm` |
| `10000` | `10` | M | `++` | Add | `++ rd, rs, rt` | `R[rd] = R[rs] + R[rt]` |
| `10001` | `11` | M | `--` | Subtract | `-- rd, rs, rt` | `R[rd] = R[rs] - R[rt]` |
| `10010` | `12` | M | `LW` | Load Word | `LW rt, (ra)` | `R[rt] = M[R[ra]]` |
| `10011` | `13` | M | `SW` | Store Word | `SW rt, (ra)` | `M[R[ra]] = R[rt]` |
| `10100` | `14` | M | `*` | Multiplication | `* rd, rs, rt` | `R[rd] = R[rs] * R[rt]` |
| `10101` | `15` | M | `/` | Division | `/ rd, rs, rt` | `R[rd] = R[rs] / R[rt]` |
| `10110` | `16` | M | `&` | And | `& rd, rs, rt` | `R[rd] = R[rs] & R[rt]` |
| `10111` | `17` | M | `\|\|` | Or | `\|\| rd, rs, rt` | `R[rd] = R[rs] \| R[rt]` |
| `11000` | `18` | M | `~` | Not | `~ rd, rt` | `R[rd] = ~R[rt]` |
| `11001` | `19` | M | `SLT` | Set Less Than | `SLT rd, rs, rt` | `R[rd] = (R[rs] < R[rt]) ? 1 : 0` |
| `11010` | `1A` | M | `<<` | Shift Left Logical | `<< rd, rs, shamt` | `R[rd] = R[rs] << shamt` |
| `11011` | `1B` | M | `>>` | Shift Right Logical | `>> rd, rs, shamt` | `R[rd] = R[rs] >>> shamt` |
| `11100` | `1C` | M | `B=` | Branch on Equal | `B= rs, rt, ra` | `if (R[rs] == R[rt]) PC = R[ra]` |
| `11101` | `1D` | M | `B!=` | Branch on Not Equal | `B!= rs, rt, ra` | `if (R[rs] != R[rt]) PC = R[ra]` |
| `11110` | `1E` | M | `B<` | Branch Less Than | `B< rs, rt, ra` | `if (R[rs] < R[rt]) PC = R[ra]` |
| `11111` | `1F` | M | `B>` | Branch Greater Than | `B> rs, rt, ra` | `if (R[rs] > R[rt]) PC = R[ra]` |

Fields an instruction does not use are encoded as zero. `ASi` and `i~` encode `Var1 = !Z`, `~` encodes `Var1 = !Z`, and `LW`/`SW` encode `Var1 = !Z`.

## 6. Execution semantics

**Arithmetic.** `+`, `-` and `*` wrap modulo 2³². `*` keeps the low 32 bits of the product. No instruction traps on overflow.

**Division.** `/` and `i/` perform signed division that **truncates toward zero**, matching C99 and later. Division never traps:

| Case | Result |
|---|---|
| `x / 0` | `-1` (`0xFFFFFFFF`) |
| `-2³¹ / -1` | `-2³¹` (overflow wraps) |

**Immediates.** The 15-bit constant is always sign-extended, including for the logical operations `i&`, `i||` and `i~`. To build a wider constant, combine `ASi`, `<<` and `i||` using non-negative 14-bit chunks.

**Shifts.** `<<` and `>>` are logical shifts by `shamt` ∈ [0, 31]. `>>` fills with zeros.

**NOT.** `~` and `i~` invert ALU operand B (the `Var2` register or the immediate respectively). The ALU's A input is unused.

**Comparisons.** `SLT`, `B<` and `B>` compare signed values exactly, including when `R[rs] − R[rt]` would overflow 32 bits (e.g. `B< INT_MAX, -1` is not taken).

**Branches.** Branches are register-indirect and absolute: if the condition holds, `PC ← R[ra]`, otherwise `PC ← PC + 4`. To branch to a label, first load its address, e.g. `ASi !A1, Loop`. An unconditional jump is `B= !Z, !Z, ra`.

**Register zero.** Writes to `!Z` are discarded, so `!Z` always reads 0.

**Memory.** `LW`/`SW` addresses must be multiples of 4 and inside data memory, otherwise a fault is raised.

**Reserved encodings.** Executing an unassigned opcode raises an illegal-instruction fault. Non-zero `unused` bits, or non-zero register fields that an instruction does not use, are reserved. Software must not rely on them.

**Program termination** (reference simulator convention). Execution stops when the PC leaves the loaded program, i.e. runs past the last instruction or jumps outside it. A program therefore ends by falling off its final instruction, typically at an `Exit:` label placed after the last instruction.

## 7. Assembly language

```asm
// Comments start with //, # or ;
        .text                   // instruction memory (default section)
start:  ASi  !A0, table         // labels end with ':'; immediates may be labels
        LW   !S0, (!A0)         // parentheses around address registers are optional
        i++  !S0, !S0, 0x10     // decimal, 0x hex and 0b binary literals
        SW   !S0, (!A0)
        ASi  !A1, table+4       // label ± constant expressions
        .data                   // data memory
table:  .word 1, -2, 0x30       // 32-bit words
buffer: .space 16               // zero-filled bytes (multiple of 4)
```

* Mnemonics and register names are case-insensitive (`asi !s0, 1` is valid).
* Operands are separated by commas, and whitespace is optional (`<<!S2,!T0,2` is valid).
* Each label resolves to an address in its own section: text labels are instruction addresses, data labels are data addresses.
* Errors are reported as `file:line: error: message`, followed by the offending source line.

## 8. Encoding examples

Every encoding below was produced by the reference assembler and cross-checked by hand in [`tests/test_assembler.py`](../tests/test_assembler.py). Fields are shown in format order.

### B-format

| Assembly | Fields (opcode · Var1 · Var2 · Constant) | Hex |
|---|---|---|
| `ASi !S5, 8` | `00000 000000 000110 000000000001000` | `0x00030008` |
| `i++ !S0, !S0, 9` | `00001 000001 000001 000000000001001` | `0x08208009` |
| `i& !S2, !S3, 16` | `00010 000100 000011 000000000010000` | `0x10818010` |
| `i\|\| !S4, !S3, 20` | `00011 000100 000101 000000000010100` | `0x18828014` |
| `i~ !S5, 7` | `00100 000000 000110 000000000000111` | `0x20030007` |
| `i/ !S6, !S2, 17` | `00101 000011 000111 000000000010001` | `0x28638011` |
| `i* !T20, !S2, 30` | `01011 000011 101010 000000000011110` | `0x5875001E` |
| `i++ !T0, !T0, -1` | `00001 010110 010110 111111111111111` | `0x0ACB7FFF` |
| `LA !A1, !A0, 8` | `01101 101011 101100 000000000001000` | `0x6D760008` |

### M-format

| Assembly | Fields (opcode · Var1 · Var2 · Dest · Shamt · unused) | Hex |
|---|---|---|
| `++ !T1, !S0, !S1` | `10000 000001 000010 010111 00000 0000` | `0x80212E00` |
| `-- !S6, !S0, !S1` | `10001 000001 000010 000111 00000 0000` | `0x88210E00` |
| `* !S20, !S11, !S12` | `10100 001100 001101 010101 00000 0000` | `0xA186AA00` |
| `& !S3, !S0, !Z` | `10110 000001 000000 000100 00000 0000` | `0xB0200800` |
| `\|\| !S10, !S0, !S1` | `10111 000001 000010 001011 00000 0000` | `0xB8211600` |
| `~ !T1, !S0` | `11000 000000 000001 010111 00000 0000` | `0xC000AE00` |
| `SLT !T0, !S1, !S2` | `11001 000010 000011 010110 00000 0000` | `0xC841AC00` |
| `<< !S2, !T0, 2` | `11010 010110 000000 000011 00010 0000` | `0xD2C00620` |
| `LW !S2, (!A1)` | `10010 000000 000011 101100 00000 0000` | `0x9001D800` |
| `SW !S1, (!T4)` | `10011 000000 000010 011010 00000 0000` | `0x98013400` |
| `B< !S2, !S1, !A2` | `11110 000011 000010 101101 00000 0000` | `0xF0615A00` |
