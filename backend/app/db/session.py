"""
app/db/session.py

SQLAlchemy engine and session factory.
Use `get_db()` as a FastAPI dependency to get a database session per request.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

#create_engine creates an instance which acts as central interface between app and RDB
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # detect stale connections before using them
    pool_size=10,
    max_overflow=20,
)

# this is for creating sessions, which are used to interact with the database. 
# these sessions helps to manage transactions and queries. (acid properties)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    """Shared declarative base, all ORM models inherit from this."""
    pass


def get_db():
    """FastAPI dependency that yields a database session and closes it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
