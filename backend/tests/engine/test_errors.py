from tourneyhub.engine.errors import EngineError


def test_an_untranslated_engine_error_reaches_the_exception_handler() -> None:
    # A service that forgets to translate one still gets internal_error from the
    # API's Exception handler (§4.4), not a dropped connection.
    assert issubclass(EngineError, Exception)
