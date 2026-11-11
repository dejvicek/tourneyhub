import logging
import re
from contextvars import ContextVar
from typing import override

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

# A share token in a path: /public/<token>, as the API and the viewer pages have it.
_SHARE_TOKEN_IN_PATH = re.compile(r"(/public/)[^/?#\s\"']+")


def redact_share_tokens(text: str) -> str:
    """Replace every share token in a path with `***` (FR-071, ADR-008)."""
    return _SHARE_TOKEN_IN_PATH.sub(r"\1***", text)


class RequestIdFilter(logging.Filter):
    """Add the current request id to every record; `None` outside a request."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


class ShareTokenFilter(logging.Filter):
    """Redact share tokens in a record's message (FR-071, ADR-008).

    uvicorn's access log passes the path as an argument, so the message is
    formatted here, redacted, and kept without arguments.
    """

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_share_tokens(record.getMessage())
        record.args = None
        return True


LOGGING_CONFIG: dict[str, object] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": RequestIdFilter},
        "share_token": {"()": ShareTokenFilter},
    },
    "formatters": {"json": {"()": "pythonjsonlogger.json.JsonFormatter"}},
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_id", "share_token"],
            "stream": "ext://sys.stderr",
        },
    },
    "root": {"level": "INFO", "handlers": ["stderr"]},
    "loggers": {
        name: {"level": "INFO", "handlers": ["stderr"], "propagate": False}
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    },
}
