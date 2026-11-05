from typing import Annotated

import pytest
from fastapi import Cookie, FastAPI, Response
from fastapi.testclient import TestClient

from tourneyhub.api.deps import SettingsDep
from tourneyhub.app import create_app
from tourneyhub.settings import Settings


def _set_cookie(response: Response, settings: SettingsDep) -> None:
    response.set_cookie(
        "refresh", "token", httponly=True, secure=settings.cookie_secure
    )


def _read_cookie(
    refresh: Annotated[str | None, Cookie()] = None,
) -> dict[str, str | None]:
    return {"refresh": refresh}


def _app(settings: Settings) -> FastAPI:
    app = create_app(settings)
    app.add_api_route("/cookie", _set_cookie, methods=["POST"])
    app.add_api_route("/cookie", _read_cookie, methods=["GET"])
    return app


def test_the_test_settings_let_a_cookie_come_back_over_http(
    settings: Settings,
) -> None:
    with TestClient(_app(settings)) as client:
        set_response = client.post("/cookie")
        response = client.get("/cookie")

    assert "secure" not in set_response.headers["set-cookie"].lower()
    assert response.json() == {"refresh": "token"}


@pytest.mark.parametrize(
    ("base_url", "sent_back"),
    [
        pytest.param("http://testserver", None, id="http-drops-it"),
        pytest.param("https://testserver", "token", id="https-sends-it"),
    ],
)
def test_a_secure_cookie_comes_back_only_over_https(
    settings: Settings, base_url: str, sent_back: str | None
) -> None:
    secure = settings.model_copy(update={"cookie_secure": True})

    with TestClient(_app(secure), base_url=base_url) as client:
        set_response = client.post("/cookie")
        response = client.get("/cookie")

    assert "secure" in set_response.headers["set-cookie"].lower()
    assert response.json() == {"refresh": sent_back}
