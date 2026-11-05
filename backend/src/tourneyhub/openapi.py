import json

from pydantic import SecretStr

from tourneyhub.app import create_app
from tourneyhub.settings import Settings


def main() -> None:
    """Print the OpenAPI schema; it does not depend on the placeholder settings."""
    settings = Settings(
        env="development",
        database_url=SecretStr("postgresql+psycopg://placeholder/placeholder"),
        jwt_secret=SecretStr("x" * 32),
    )
    print(json.dumps(create_app(settings).openapi(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
