from collections.abc import Generator
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from .config import get_settings


settings = get_settings()
is_sqlite = settings.database_url.startswith("sqlite")


def _ensure_mysql_database() -> None:
    url = make_url(settings.database_url)
    if url.get_backend_name() != "mysql" or not url.database:
        return
    database = url.database
    escaped_database = database.replace("`", "``")
    server_engine = create_engine(
        url.set(database=""),
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    try:
        with server_engine.connect() as connection:
            connection.execute(text(f"CREATE DATABASE IF NOT EXISTS `{escaped_database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    finally:
        server_engine.dispose()


_ensure_mysql_database()
connect_args = {"check_same_thread": False} if is_sqlite else {}
engine_options = {"connect_args": connect_args, "pool_pre_ping": True}
if not is_sqlite:
    engine_options.update({"pool_size": 10, "max_overflow": 20, "pool_recycle": 1800})
engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

if is_sqlite:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
