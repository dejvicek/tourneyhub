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
        "add_player",
        "create_league",
        "create_tournament",
        "delete_league",
        "delete_tournament",
        "draw_again",
        "list_leagues",
        "list_players",
        "list_tournaments",
        "log_in",
        "log_out",
        "read_league",
        "read_me",
        "read_tournament_setup",
        "refresh",
        "rename_player",
        "rename_season",
        "set_doubles_pairs",
        "set_dyp_halves",
        "set_placement_points",
        "set_player_removed",
        "set_seed_order",
        "set_seeding_method",
        "set_tournament_format",
        "set_tournament_players",
        "sign_up",
        "start_season",
        "update_league",
        "update_me",
    }
