# Errata: from the 2022 coursework to SymRISC-32 v1.0

SymRISC-32 began as a two-phase design project for *CSC320 Computer Organization* (spring 2022). The original reports are kept unchanged in [`reports/`](reports):

| File | Content |
|---|---|
| [`phase-1-isa-design.pdf`](reports/phase-1-isa-design.pdf) | RISC vs. CISC study, instruction formats, opcodes, registers, encoding examples, green sheet |
| [`phase-2-datapath-and-control.pdf`](reports/phase-2-datapath-and-control.pdf) | Sample C program and its assembly, single-cycle datapath per instruction class, control signals, ALU table |
| [`opcode-table.pdf`](reports/opcode-table.pdf) | Opcode reference table |

Building an executable reference model and checking it against exhaustive tests exposed a number of defects in the reports. This page lists every one and how v1.0 resolves it. The architecture's ideas are unchanged: the two formats, the 64-register file, the symbolic mnemonics, the opcode assignments, the three-read-port datapath, and the `Zero`/`MSB` → `XOR` → `AND` branch logic all carry over.

Each fix is pinned by a regression test, named in the **Test** column.

## Hardware defects

| # | Original | Problem | v1.0 resolution | Test |
|---|---|---|---|---|
| H1 | `ALUOp` is 3 bits. The ALU table assigns `010` to both **AND** and **NOT**. | Nine ALU operations cannot fit in 3 bits, so `&`, `i&`, `~` and `i~` were indistinguishable to the ALU. | `ALUOp` widened to 4 bits. The original codes `000`–`111` keep their values (with a leading 0). NOT is `1000`. | `test_isa.OpcodeTest.test_distinct_operations_get_distinct_alu_ops` |
| H2 | `B>` computes `Var1 − Var2` and branches on `~MSB`. | `~MSB` is also 1 when the operands are **equal**, so `B>` actually implemented `≥`. | `B>` uses the new `RSUB` operation (`Var2 − Var1`) with `NegBranch = 1`. It shares the `B<` logic with the operands swapped, and no new hardware path is needed. | `test_cpu.BranchTest.test_branch_greater_than_is_not_taken_on_equality` |
| H3 | `B<`/`B>` use the raw MSB of the subtraction. | The MSB is wrong when the subtraction overflows. For example, `INT_MAX − (−1)` is negative after wrap-around, so `INT_MAX < −1` would be taken. | The ALU exports `Less = N ⊕ V`, the overflow-corrected sign, in place of the raw MSB. | `test_alu.AluTest.test_less_flag_is_overflow_corrected`, `test_cpu.BranchTest.test_branch_conditions_exhaustively` |
| H4 | Branch control lists `RegWrite = 1`. The text lists `RegWrite` and `MemWrite` as don't-care. | Branches would write garbage into a register, or into memory. State-changing signals can never be don't-care. | Branches drive `RegWrite = 0` and `MemWrite = 0`. | `test_alu.ControlTableTest` |
| H5 | `Shamt` is 4 bits (`Instruction[8:5]`). | A 32-bit register needs shift amounts 0–31, but 4 bits only reach 15. | `Shamt` widened to 5 bits, `[8:4]`, taken from the unused field, which shrinks from 5 to 4 bits. | `test_isa.FieldLayoutTest`, `test_assembler.EncodingTest.test_shift_bounds` |
| H6 | `SLT` (`11001`) and `LA` (`01101`) are defined in Phase 1 §3. | Both are missing from the opcode table, the green sheet, and the ALU table, so the hardware could not execute them. | Both are fully specified. `SLT` uses ALUOp `1001`, and `LA` uses ADD. | `test_cpu.InstructionTest` |
| H7 | — | No control row existed for `SW`. | `SW`: `MemWrite = 1`, `RegWrite = 0`. The address comes from Read data 3 and the data from Read data 2. | `test_alu.ControlTableTest.test_store_and_load` |

## Specification inconsistencies

| # | Original | Problem | v1.0 resolution |
|---|---|---|---|
| S1 | The Phase 1 field list says the M-format is `opcode, Dest, Var1, Var2`, and the Phase 1 examples are encoded that way. | The Phase 1 diagram and the Phase 2 datapath both use `opcode, Var1, Var2, Dest`, wiring `Instruction[14:9]` to Read register 3 and to the `RegDst = 1` write port. | The datapath order `opcode · Var1 · Var2 · Dest · Shamt · unused` is normative, and all examples were re-encoded. |
| S2 | `~ Dest, var1, unused`. | The Phase 1 example encodes the source in `Var2`, and `i~` must invert ALU operand B, the constant. | `~` and `i~` both invert ALU operand B. The syntax is `~ rd, rt`, with the source in `Var2`. |
| S3 | `LW Dest, unused, var2` / `SW Dest, unused, var2`. | The Phase 2 datapath addresses memory with Read data 3 (`Dest` field) and writes back through `RegDst = 0` (`Var2` field). | `LW rt, (ra)` / `SW rt, (ra)`: the data register is in `Var2` and the address register in `Dest`. This keeps the original `LW !S2, !A1` spelling. |
| S4 | Branch syntax `B< Dest, var1, var2` ("branch to address in var2"). | In the Phase 2 datapath, the target comes from Read register 3 (`Dest`) and the compared values from Var1/Var2. | `B< rs, rt, ra`: compare `Var1` with `Var2` and jump to `R[Dest]`. This is the operand order the Phase 2 program already used. |
| S5 | Phase 1 note: "Target address = PC + (offset × 4)". | Branches are register-indirect and absolute, and there is no offset field. | `PC ← R[ra]`. |
| S6 | `!RA` = "Register Address". | — | `!RA` = **Return Address**. |
| S7 | Assignment text: "8 general purpose 32-bit registers: R0 … R63". | Contradictory. The design uses 6-bit register fields. | 64 registers, as designed. |
| S8 | — | The reports left several behaviours undefined: division by zero, `INT_MIN / −1`, sign- vs zero-extension of logical immediates, writes to `!Z`, misaligned accesses, and illegal opcodes. | All are now specified in [isa-spec.md §6](isa-spec.md#6-execution-semantics). |

## Encoding-example errors (Phase 1 §5)

All examples were regenerated by the assembler. See [isa-spec.md §8](isa-spec.md#8-encoding-examples).

| Example | Error in report |
|---|---|
| `i& !S2, !S3, 16` | The constant is encoded as 8 (`…0001000`) instead of 16. The destination is placed in `Var1` instead of `Var2`. |
| `i\|\| !S4, !S3, 20`, `i/ !S6, !S2, 17`, `i* !T20, !S2, 30` | The destination is placed in `Var1`. The datapath writes B-format results to `Var2` (`RegDst = 0`). |
| `i/ !S6, !S2, 17` | The binary string has 31 bits. |
| `B< !S2, !S1, !A2` | The binary string has 33 bits. |
| `LW !S2, !A1` | `!A1` is encoded as `000100` (4, which is `!S3`) instead of `101100` (44). |
| All M-format examples | They use the `opcode, Dest, Var1, Var2` order (see S1). |

## Phase 2 program (C → assembly)

The corrected program is [`examples/course_demo.s`](../examples/course_demo.s). Its result is checked against a direct transliteration of [`course_demo.c`](../examples/course_demo.c) in `test_examples.ExampleProgramsTest.test_course_demo_matches_c_reference`.

| # | Original | Problem | Fix |
|---|---|---|---|
| P1 | `B< !S4, !S0, Loop`, `B= !S1, !Z, Condition` | Branches take a target *register*, not a label. | Targets are loaded first (`ASi !A1, Loop`, …) and branches name `!A1`–`!A3`. |
| P2 | `if (x > w)` compiled as "skip if `x < w`". | When `x == w` the body would run, which is wrong. | Skip on `x < w` **or** `x == w` (two branches). |
| P3 | `i+ !S4, !S4, 1` and `i+ !T4, !A0, 4`. | `i+` is not an instruction. | `i++`. |
| P4 | "Assume the address of the array is in `!A0`". | The program is not self-contained. | `!A0` is initialised from the `.data` label `A`. |
| P5 | `B= !S1, !Z, Condition` relies on `y` still being 0. | It is fragile. | `B= !Z, !Z, !A2`, which is always taken. |

The final state matches C semantics: `x = 6`, `y = 6`, `w = 999`, `A[1] = 6`.
