import io
import json
from contextlib import redirect_stderr

import pytest

from tourneyhub.openapi import main


def test_main_prints_a_schema_with_function_names_as_operation_ids(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with redirect_stderr(io.StringIO()):  # not capsys's stream, which pytest closes
        main()

    schema = json.loads(capsys.readouterr().out)
    operation_ids = {
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
    }
    assert operation_ids == {
        "change_password",
        "create_league",
        "delete_league",
        "list_leagues",
        "log_in",
        "log_out",
        "read_league",
        "read_me",
        "refresh",
        "rename_season",
        "set_placement_points",
        "sign_up",
        "start_season",
        "update_league",
        "update_me",
    }
