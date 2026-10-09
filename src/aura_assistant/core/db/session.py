"""
Aura Assistant - Database Engine & Session Management
Initializes SQLite database with WAL mode and foreign key enforcement.
"""

from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from aura_assistant.core.db.schema import Base, User, ApiKey

DB_DIR = Path("data")
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "aura.db"

DATABASE_URL = f"sqlite:///{DB_PATH.resolve()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

# Enable foreign keys and WAL mode on SQLite connections
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initializes tables and seeds default user if none exists."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        default_user = session.query(User).filter_by(username="admin").first()
        if not default_user:
            user = User(
                username="admin",
                role="admin",
                preferences={"theme": "dark", "voice_rate": 1.0}
            )
            session.add(user)
            session.commit()
            session.refresh(user)

            # Seed default API key
            key = ApiKey(
                user_id=user.id,
                key_hash="aura_sec_default_change_me",
                scopes=["chat", "code:exec", "workspace:patch", "admin"]
            )
            session.add(key)
            session.commit()
