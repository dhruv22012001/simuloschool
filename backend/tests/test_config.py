"""Settings normalisation and production preflight checks (no database needed)."""

from app.core.config import Settings

NEON_URL = (
    "postgresql+psycopg://user:pw@ep-damp-recipe-ayp4z0wy.c-5.us-east-2.aws.neon.tech"
    "/simuloschool?sslmode=require&channel_binding=require"
)

PROD_ENV = {
    "app_env": "production",
    "jwt_secret": "a-real-secret",
}


def test_database_url_trailing_whitespace_is_stripped():
    """A connection string pasted into a hosting dashboard picks up trailing
    spaces, which land inside `channel_binding=require` and make psycopg reject
    the connection outright."""
    assert Settings(database_url=NEON_URL + "   ").database_url == NEON_URL


def test_database_url_surrounding_whitespace_is_stripped():
    assert Settings(database_url="\n\t " + NEON_URL + " \n").database_url == NEON_URL


def test_database_url_without_whitespace_is_untouched():
    assert Settings(database_url=NEON_URL).database_url == NEON_URL


def test_database_host_is_the_neon_endpoint():
    settings = Settings(database_url=NEON_URL)
    assert settings.database_host == "ep-damp-recipe-ayp4z0wy.c-5.us-east-2.aws.neon.tech"


def test_production_config_with_a_real_database_has_no_problems():
    settings = Settings(database_url=NEON_URL, **PROD_ENV)
    assert settings.validate_for_production() == []


def test_production_flags_a_localhost_database():
    settings = Settings(database_url="postgresql+psycopg://u:p@localhost:5432/db", **PROD_ENV)
    problems = settings.validate_for_production()
    assert len(problems) == 1
    assert "DATABASE_URL" in problems[0]


def test_production_flags_the_default_jwt_secret():
    # Set explicitly: conftest puts a real JWT_SECRET in the environment, which
    # would otherwise mask the default this check exists to catch.
    settings = Settings(
        database_url=NEON_URL, app_env="production", jwt_secret="change-me-in-prod"
    )
    assert any("JWT_SECRET" in p for p in settings.validate_for_production())


def test_local_env_is_not_checked():
    """The localhost default is correct locally — flagging it would be noise."""
    settings = Settings(database_url="postgresql+psycopg://u:p@localhost:5432/db")
    assert settings.validate_for_production() == []
