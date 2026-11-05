from collections.abc import Callable

from fastapi.testclient import TestClient

from tourneyhub.db.models.accounts import User


def test_login_returns_the_account(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    user = make_user(email="ana@example.test")

    response = client.post(
        "/api/v1/auth/login", json={"email": "Ana@Example.test", "password": "x" * 15}
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": str(user.id)}


def test_login_with_an_unknown_email_is_not_authenticated(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.test", "password": "x"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
