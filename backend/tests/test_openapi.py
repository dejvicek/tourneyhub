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
        "generate_signup_code",
        "list_organizers",
        "read_signup_code",
        "reset_password",
        "set_signup_code",
        "change_password",
        "add_field",
        "add_player",
        "add_round",
        "back_to_setup",
        "create_league",
        "create_tournament",
        "delete_knockout",
        "delete_league",
        "delete_round",
        "delete_tournament",
        "draw_again",
        "draw_knockout_again",
        "draw_knockout_round",
        "start_knockout",
        "finish_tournament",
        "list_leagues",
        "list_players",
        "list_public_tournaments",
        "list_tournaments",
        "log_in",
        "log_out",
        "place_matches",
        "read_bracket",
        "read_knockout_preview",
        "read_league",
        "read_me",
        "read_places",
        "read_play",
        "read_public_bracket",
        "read_public_league",
        "read_public_places",
        "read_public_season_standings",
        "read_public_standings",
        "read_public_tournament",
        "read_schedule_preview",
        "read_season_effect",
        "read_season_standings",
        "read_tournament",
        "read_tournament_setup",
        "refresh",
        "remove_field",
        "rename_player",
        "rename_season",
        "set_doubles_pairs",
        "set_dyp_halves",
        "set_final_format",
        "set_match_result",
        "set_placement_points",
        "set_player_removed",
        "set_seed_order",
        "set_tiebreakers",
        "set_seeding_method",
        "set_tournament_format",
        "set_top_players",
        "set_tournament_players",
        "sign_up",
        "start_season",
        "start_tournament",
        "update_league",
        "update_me",
    }
