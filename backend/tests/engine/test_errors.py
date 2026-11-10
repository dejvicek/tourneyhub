from tourneyhub.engine.errors import EngineError


def test_engine_errors_are_exceptions() -> None:
    # A service that forgets to translate one still gets internal_error from the
    # API's Exception handler (§4.4), not a dropped connection.
    assert issubclass(EngineError, Exception)
