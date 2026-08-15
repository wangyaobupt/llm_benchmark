from __future__ import annotations

import contextlib
import io
import unittest
from unittest.mock import patch

from data_pipeline.text_ner import __main__ as text_ner_main


class TextNerCliTests(unittest.TestCase):
    def test_keyboard_interrupt_exits_cleanly_without_traceback(self) -> None:
        standard_error = io.StringIO()
        with (
            patch.object(text_ner_main, "main", side_effect=KeyboardInterrupt),
            contextlib.redirect_stderr(standard_error),
            self.assertRaises(SystemExit) as raised,
        ):
            text_ner_main.cli()

        self.assertEqual(raised.exception.code, 130)
        message = standard_error.getvalue()
        self.assertIn("TEXT_NER_INTERRUPTED_BY_USER", message)
        self.assertIn("已落盘", message)
        self.assertNotIn("Traceback", message)


if __name__ == "__main__":
    unittest.main()
