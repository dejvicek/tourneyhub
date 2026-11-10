import pytest

from tourneyhub.engine.leagues import DEFAULT_PLACEMENT_POINTS, first_increase


def test_fr011_the_default_table_gives_10_8_6_4_2() -> None:
    assert DEFAULT_PLACEMENT_POINTS == (10, 8, 6, 4, 2)


@pytest.mark.parametrize(
    "points",
    [
        pytest.param((10, 8, 6, 4, 2), id="FR-011-default"),
        pytest.param((5, 5, 0), id="FR-011-equal-places"),
        pytest.param((0,), id="FR-011-one-place"),
    ],
)
def test_fr011_a_non_increasing_table_has_no_increase(points: tuple[int, ...]) -> None:
    assert first_increase(points) is None


@pytest.mark.parametrize(
    ("points", "index"),
    [
        pytest.param((8, 10), 1, id="FR-011-second-above-first"),
        pytest.param((10, 8, 8, 9, 2), 3, id="FR-011-fourth-above-third"),
    ],
)
def test_fr011_reports_the_first_place_worth_more_than_the_one_above(
    points: tuple[int, ...], index: int
) -> None:
    assert first_increase(points) == index
