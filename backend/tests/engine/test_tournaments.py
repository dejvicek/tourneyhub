import pytest

from tourneyhub.engine.tournaments import (
    EntryKind,
    GroupPhase,
    MatchFormat,
    PhaseFormat,
    TournamentType,
    default_sit_out_points,
    entry_kind,
    group_phase_format,
    is_seeded,
)


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        pytest.param(GroupPhase.ROUND_ROBIN, PhaseFormat.ROUND_ROBIN, id="round-robin"),
        pytest.param(GroupPhase.SWISS, PhaseFormat.SWISS, id="swiss"),
        pytest.param(GroupPhase.MONSTER_DYP, PhaseFormat.MONSTER_DYP, id="monster"),
        pytest.param(GroupPhase.NONE, None, id="FR-031-no-group-phase"),
    ],
)
def test_fr031_a_group_phase_choice_names_its_format(
    choice: GroupPhase, expected: PhaseFormat | None
) -> None:
    assert group_phase_format(choice) is expected


@pytest.mark.parametrize(
    ("tournament_type", "kind"),
    [
        pytest.param(TournamentType.SINGLES, EntryKind.PLAYER, id="singles"),
        pytest.param(TournamentType.DOUBLES, EntryKind.PAIR, id="BR-030-doubles"),
        pytest.param(TournamentType.DYP, EntryKind.PAIR, id="BR-030-dyp"),
        pytest.param(TournamentType.MONSTER_DYP, EntryKind.PLAYER, id="D2-monster"),
    ],
)
def test_br030_doubles_and_dyp_enter_pairs(
    tournament_type: TournamentType, kind: EntryKind
) -> None:
    assert entry_kind(tournament_type) is kind


def test_fr034_every_type_but_monster_dyp_is_seeded() -> None:
    assert [is_seeded(t) for t in TournamentType] == [True, True, True, False]


@pytest.mark.parametrize(
    ("match_format", "expected"),
    [
        pytest.param(MatchFormat.BO1, 1, id="bo1-like-a-draw"),
        pytest.param(MatchFormat.BO2, 1, id="bo2-like-a-draw"),
        pytest.param(MatchFormat.BO3, 2, id="bo3-like-a-win"),
        pytest.param(MatchFormat.BO5, 2, id="bo5-like-a-win"),
    ],
)
def test_br071_the_default_sit_out_points_follow_the_match_format(
    match_format: MatchFormat, expected: int
) -> None:
    assert default_sit_out_points(match_format) == expected
