# Datapath Visualizer

An interactive, in-browser view of the SymRISC-32 single-cycle datapath. Step
through a program and watch every wire, multiplexer and control signal light up
as the hardware would use it.

**Live:** https://malfallah.github.io/symrisc/

## Run locally

No build step and no dependencies. Either open `index.html` directly, or serve
the folder:

```bash
python -m http.server 8000 --directory web
# then open http://localhost:8000
```

## Files

| File | Purpose |
|---|---|
| `index.html` | Page layout and the hand-drawn SVG datapath |
| `css/style.css` | Light/dark theme, wire animation, responsive layout |
| `js/symrisc.js` | JavaScript port of the reference model (assembler, control unit, ALU, datapath) |
| `js/app.js` | UI: stepping, undo, run, breakpoints, explanations, share links |
| `js/examples.js` | Generated from `examples/*.s` by `scripts/build_web_examples.py` |

## How the highlighting works

Each cycle, `CPU.step()` returns the value on every wire. The UI decides which
paths are *active* purely from the control signals (for example, `ALUSrc = 1`
lights the sign-extend path, and `Branch = 1` lights the branch unit), so the
picture always matches what the control unit actually selects.

## Correctness

`js/symrisc.js` must agree exactly with the Python package.
`tests/test_web_conformance.py` runs the example programs, assembler error
cases, faults and 300 randomly generated programs on both implementations and
compares every cycle. After editing an example, regenerate the bundle with
`python scripts/build_web_examples.py`.
