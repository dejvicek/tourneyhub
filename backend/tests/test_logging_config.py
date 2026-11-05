import io
import json
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
