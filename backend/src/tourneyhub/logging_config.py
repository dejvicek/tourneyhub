import logging
from contextvars import ContextVar
from typing import override

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Add the current request id to every record; `None` outside a request."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


LOGGING_CONFIG: dict[str, object] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": RequestIdFilter}},
    "formatters": {"json": {"()": "pythonjsonlogger.json.JsonFormatter"}},
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_id"],
            "stream": "ext://sys.stderr",
        },
    },
    "root": {"level": "INFO", "handlers": ["stderr"]},
    "loggers": {
        name: {"level": "INFO", "handlers": ["stderr"], "propagate": False}
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    },
}
