from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.session import create_session


def get_db_session() -> Iterator[Session]:
    with create_session() as session:
        yield session
