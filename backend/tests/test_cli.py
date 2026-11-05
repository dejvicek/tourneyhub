import io
from contextlib import redirect_stderr

import pytest

from tourneyhub.cli import main


def test_main_without_a_command_fails() -> None:
    # main() binds the log handler to stderr first (§9), so not capsys.
    with redirect_stderr(io.StringIO()) as stderr, pytest.raises(SystemExit) as raised:
        main([])

    assert raised.value.code == 2
    assert "usage: tourneyhub" in stderr.getvalue()
