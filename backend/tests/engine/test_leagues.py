import pytest

from tourneyhub.engine.leagues import LeagueStatus, can_transition


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        pytest.param(
            LeagueStatus.ACTIVE, LeagueStatus.ARCHIVED, True, id="archive-an-active"
        ),
        pytest.param(
            LeagueStatus.ARCHIVED, LeagueStatus.ACTIVE, True, id="restore-an-archived"
        ),
        pytest.param(LeagueStatus.ACTIVE, LeagueStatus.ACTIVE, False, id="stay-active"),
        pytest.param(
            LeagueStatus.ARCHIVED, LeagueStatus.ARCHIVED, False, id="stay-archived"
        ),
    ],
)
def test_can_transition_between_distinct_statuses_only(
    current: LeagueStatus, target: LeagueStatus, allowed: bool
) -> None:
    assert can_transition(current, target) is allowed
