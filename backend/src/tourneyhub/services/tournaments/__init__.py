"""Tournaments: setup, start, results, fields, standings and finishing (FR-030 to FR-094).

Every write locks the league row, then the tournament row (ADR-008), and loads
every id it is given through them. A change to the entries discards the seeding
and draws again where the inputs are complete, incrementing the draw counter
(ADR-010). Starting creates the schedule with the engine and puts the first
matches on the fields (FR-035, BR-130); going back to setup deletes it while no
match has a result (FR-036). Results and placements by hand are whole target
states (ADR-008); the standings and places are computed on read (ADR-009).
"""

from tourneyhub.services.tournaments.entries import (
    DrawTarget,
    draw_again,
    set_doubles_pairs,
    set_dyp_halves,
    set_seed_order,
    set_seeding_method,
    set_tournament_players,
)
from tourneyhub.services.tournaments.fields import (
    FieldPlacement,
    add_field,
    place_matches,
    remove_field,
)
from tourneyhub.services.tournaments.monster_dyp import set_top_players
from tourneyhub.services.tournaments.places import (
    PlacesView,
    finished_season_points,
    read_places,
    view_places,
)
from tourneyhub.services.tournaments.play import (
    GroupStandingRow,
    group_standings,
    read_play,
    tie_groups,
    view_group_standings,
)
from tourneyhub.services.tournaments.results import MatchResult, set_match_result
from tourneyhub.services.tournaments.rounds import (
    add_round,
    delete_round,
    finish_tournament,
    set_tiebreakers,
)
from tourneyhub.services.tournaments.setup import (
    FormatRequest,
    create_tournament,
    delete_tournament,
    set_tournament_format,
)
from tourneyhub.services.tournaments.shared import (
    PLAYED_GROUP_FORMATS,
    Clock,
    KnockoutBracket,
    knockout_bracket,
)
from tourneyhub.services.tournaments.start import (
    back_to_setup,
    preview_schedule,
    start_tournament,
)
from tourneyhub.services.tournaments.views import (
    SideView,
    TournamentSummary,
    TournamentView,
    list_season_tournaments,
    list_tournaments,
    load_summaries,
    read_tournament,
    read_tournament_setup,
    view_tournament,
)

__all__ = [
    "PLAYED_GROUP_FORMATS",
    "Clock",
    "DrawTarget",
    "FieldPlacement",
    "FormatRequest",
    "GroupStandingRow",
    "KnockoutBracket",
    "MatchResult",
    "PlacesView",
    "SideView",
    "TournamentSummary",
    "TournamentView",
    "add_field",
    "add_round",
    "back_to_setup",
    "create_tournament",
    "delete_round",
    "delete_tournament",
    "draw_again",
    "finish_tournament",
    "finished_season_points",
    "group_standings",
    "knockout_bracket",
    "list_season_tournaments",
    "list_tournaments",
    "load_summaries",
    "place_matches",
    "preview_schedule",
    "read_places",
    "read_play",
    "read_tournament",
    "read_tournament_setup",
    "remove_field",
    "set_doubles_pairs",
    "set_dyp_halves",
    "set_match_result",
    "set_seed_order",
    "set_seeding_method",
    "set_tiebreakers",
    "set_top_players",
    "set_tournament_format",
    "set_tournament_players",
    "start_tournament",
    "tie_groups",
    "view_group_standings",
    "view_places",
    "view_tournament",
]
