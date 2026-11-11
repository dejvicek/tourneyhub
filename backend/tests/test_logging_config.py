import io
import json
import logging
from contextlib import redirect_stderr

from tourneyhub.api.errors import logger  # created when the module was imported
from tourneyhub.app import create_app
from tourneyhub.settings import Settings


def test_a_module_logger_emits_a_json_line(settings: Settings) -> None:
    with redirect_stderr(io.StringIO()) as stderr:
        create_app(settings)  # binds the log handler to this stream

    logger.error("probe", extra={"league_id": "L1"})  # tourneyhub.api.errors.logger

    line = json.loads(stderr.getvalue().splitlines()[-1])
    assert line["message"] == "probe"
    assert line["league_id"] == "L1"


def test_fr071_the_access_log_redacts_the_share_token(settings: Settings) -> None:
    with redirect_stderr(io.StringIO()) as stderr:
        create_app(settings)
        # The arguments uvicorn's access log passes (uvicorn/protocols/http).
        logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d',
            "203.0.113.7:51000",
            "GET",
            "/api/v1/public/s3cr3t-Token_x/tournaments/abc?x=1",
            "1.1",
            200,
        )

    line = json.loads(stderr.getvalue().splitlines()[-1])
    assert line["message"] == (
        '203.0.113.7:51000 - "GET /api/v1/public/***/tournaments/abc?x=1 HTTP/1.1" 200'
    )
    assert "s3cr3t" not in stderr.getvalue()


def test_fr071_a_message_with_a_share_link_is_redacted(settings: Settings) -> None:
    with redirect_stderr(io.StringIO()) as stderr:
        create_app(settings)
        logger.warning("seen https://example.org/public/s3cr3t")

    line = json.loads(stderr.getvalue().splitlines()[-1])
    assert line["message"] == "seen https://example.org/public/***"


def test_fr071_mapping_arguments_are_redacted_too(settings: Settings) -> None:
    with redirect_stderr(io.StringIO()) as stderr:
        create_app(settings)
        logger.warning("path %(path)s", {"path": "/public/s3cr3t/x"})

    line = json.loads(stderr.getvalue().splitlines()[-1])
    assert line["message"] == "path /public/***/x"


def test_other_paths_are_logged_as_they_are(settings: Settings) -> None:
    with redirect_stderr(io.StringIO()) as stderr:
        create_app(settings)
        logger.warning("%s", "/api/v1/leagues/abc/publications")

    line = json.loads(stderr.getvalue().splitlines()[-1])
    assert line["message"] == "/api/v1/leagues/abc/publications"
