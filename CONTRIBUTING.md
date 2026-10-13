# Contributing to SymRISC-32

Thanks for your interest! Bug reports, documentation fixes, new example
programs and items from the [roadmap](README.md#roadmap) are all welcome.

## Development setup

```bash
git clone https://github.com/malfallah/symrisc.git
cd symrisc
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e . ruff
```

The package has no runtime dependencies; [ruff](https://docs.astral.sh/ruff/)
is only used for linting and formatting.

## Before opening a pull request

```bash
python -m unittest discover -s tests -t .   # all tests must pass
ruff check .                                # lint
ruff format .                               # format
```

## Guidelines

- **The spec is the contract.** Behavioural changes must update
  `docs/isa-spec.md` (and `docs/microarchitecture.md` for hardware changes) in
  the same pull request.
- **Single source of truth.** Instruction definitions live only in
  `symrisc/isa.py`; the assembler, disassembler and control unit derive from it.
- **Test what you change.** Bug fixes come with a regression test; new
  instructions need encoding, semantics and round-trip coverage.
- **Keep both models in sync.** The visualizer runs `web/js/symrisc.js`, a port
  of the Python package. Any behavioural change must be made in both;
  `tests/test_web_conformance.py` (needs Node.js) fails if they diverge. After
  editing an example, run `python scripts/build_web_examples.py`.
- **Keep the model faithful.** `symrisc/cpu.py` mirrors the datapath wire for
  wire. If you change how a signal is routed, change the diagram description too.

### Adding an instruction

1. Pick a reserved opcode (see the [opcode map](docs/isa-spec.md#4-opcode-map)).
2. Add an `Instruction` entry in `symrisc/isa.py` (and an `AluOp` if needed).
3. Add its control row in `symrisc/control.py` if it needs a new syntax class.
4. Add tests in `tests/` and document it in `docs/isa-spec.md`.

## Reporting bugs

Please include the assembly source, the command you ran, and the output of
`symrisc run --trace --signals` for the failing program.
