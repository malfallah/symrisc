# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-14

### Added
- Normative ISA specification (`docs/isa-spec.md`) and microarchitecture
  document (`docs/microarchitecture.md`).
- `symrisc` Python package: two-pass assembler with labels, expressions and
  `.text`/`.data` sections; disassembler; signal-level single-cycle datapath
  simulator with cycle traces; `symrisc asm | dis | run` command line.
- Output formats: listing, hex (`$readmemh`), binary and Logisim ROM images.
- Example programs: the course demo (with its C source), Fibonacci and
  bubble sort.
- Test suite covering encodings, ISA invariants, ALU semantics, exhaustive
  branch conditions, example programs and don't-care safety; CI on Linux,
  Windows and macOS.
- `docs/errata.md` documenting every change from the 2022 reports.

### Fixed
- `ALUOp` widened from 3 to 4 bits: AND and NOT no longer share a code.
- `B>` no longer branches when its operands are equal.
- Signed comparisons are correct when the subtraction overflows.
- Branch control no longer asserts `RegWrite`.
- Shift amount widened to 5 bits so shifts of 16-31 are encodable.
- `SLT` and `LA` added to the opcode table, control unit and ALU table.
- M-format field order, `LW`/`SW`/`~` operand placement and all encoding
  examples made consistent with the datapath.
- Phase 2 assembly program: label branch targets, `x == w` case, typos.

### Changed
- Repository renamed from `ComputerOrganizationProject` to `symrisc`;
  reports moved to `docs/reports/` with descriptive file names.
- License changed from MIT to Apache-2.0.

## [0.1.0] - 2022-04-28

### Added
- Original coursework: Phase 1 ISA design report, Phase 2 datapath and
  control report, opcode table.

[1.0.0]: https://github.com/malfallah/symrisc/releases/tag/v1.0.0
[0.1.0]: https://github.com/malfallah/symrisc/releases/tag/v0.1.0
