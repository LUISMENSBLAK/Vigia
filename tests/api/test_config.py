from services.api.vigia_api.config import Settings


def test_cors_origin_accepts_documented_env_format() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        CORS_ALLOWED_ORIGINS="http://localhost:3000,https://vigia.example",
    )
    assert settings.CORS_ALLOWED_ORIGINS == [
        "http://localhost:3000",
        "https://vigia.example",
    ]
