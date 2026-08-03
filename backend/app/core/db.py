"""SQLAlchemy engine + session dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# connect_timeout bounds how long a wrong or unreachable host can stall us.
# Without it a bad DATABASE_URL makes the process hang at startup, which the
# hosting platform can only report as "service unresponsive".
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 10},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
