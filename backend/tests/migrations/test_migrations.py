from pytest_alembic.tests import (  # noqa: F401  (pytest collects the imported tests)
    test_model_definitions_match_ddl,
    test_single_head_revision,
    test_up_down_consistency,
    test_upgrade,
)
