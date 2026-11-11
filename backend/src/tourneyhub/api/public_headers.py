"""The headers of every answer under /api/v1/public (ADR-005, FR-071).

The path carries the share token: no cache may keep the answer, and no request
from the page names the address. The middleware adds them to answers that pass
through it; the 500 handlers add them too, because Starlette sends the
`Exception` handler's response from outside every user middleware.
"""

API_PREFIX = "/api/v1"
PUBLIC_PREFIX = "/public"
PUBLIC_PATH = API_PREFIX + PUBLIC_PREFIX

PUBLIC_HEADERS: dict[str, str] = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}


def is_public_path(path: str) -> bool:
    return path == PUBLIC_PATH or path.startswith(PUBLIC_PATH + "/")
