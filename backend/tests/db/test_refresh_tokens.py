from sqlalchemy import text
from sqlalchemy.orm import Session


def test_adr006_a_partial_index_covers_the_live_family_check(session: Session) -> None:
    definition = session.scalar(
        text(
            "SELECT indexdef FROM pg_indexes"
            " WHERE indexname = 'ix_refresh_tokens_live_family_id'"
        )
    )

    assert definition is not None
    assert "(family_id)" in definition
    assert "WHERE (revoked_at IS NULL)" in definition
