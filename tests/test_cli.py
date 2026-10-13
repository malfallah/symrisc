import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from symrisc.cli import main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(a) for a in args])
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def test_assemble_then_disassemble_hex_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "fib.hex"
            code, _, _ = cli("asm", EXAMPLES / "fibonacci.s", "-f", "hex", "-o", image)
            self.assertEqual(code, 0)
            self.assertEqual(len(image.read_text().split()), 12)

            code, out, _ = cli("dis", image)
            self.assertEqual(code, 0)
            self.assertIn("B>   !T0, !Z, !A1", out)

    def test_logisim_image_has_header(self):
        code, out, _ = cli("asm", EXAMPLES / "fibonacci.s", "-f", "logisim")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("v2.0 raw\n"))

    def test_run_with_trace(self):
        code, out, _ = cli("run", EXAMPLES / "course_demo.s", "--trace", "--signals")
        self.assertEqual(code, 0)
        self.assertIn("halted after 60 cycles", out)
        self.assertIn("ALUOp=SUB", out)
        self.assertIn("M[0x0004] = 6", out)

    def test_errors_exit_non_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.s"
            bad.write_text("ASi !S0, nowhere\n")
            code, _, err = cli("asm", bad)
        self.assertEqual(code, 1)
        self.assertIn("undefined label", err)


if __name__ == "__main__":
    unittest.main()
