"""
Aura Assistant - Database Engine & Session Management
Initializes SQLite database with WAL mode, foreign key enforcement,
and runtime persistence helpers for conversations, messages, memories, and audit logs.
"""

from datetime import date
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from aura_assistant.core.db.schema import (
    Base,
    User,
    ApiKey,
    Conversation,
    Message,
    Memory,
    AuditLog,
    UsageStat
)

logger = logging.getLogger("aura-db-session")

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

def persist_conversation_turn(
    session_id: str,
    user_prompt: str,
    assistant_response: str,
    model_name: str = "qwen3.5:4b"
) -> None:
    """Persists a completed user/assistant turn and updates usage stats in SQLite."""
    try:
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            user = db.query(User).filter_by(username="admin").first()
            if not user:
                user = User(username="admin", role="admin")
                db.add(user)
                db.commit()
                db.refresh(user)

            conv = db.query(Conversation).filter_by(id=session_id).first()
            if not conv:
                conv = Conversation(
                    id=session_id,
                    user_id=user.id,
                    title=user_prompt[:80] if user_prompt else "Session",
                    model=model_name
                )
                db.add(conv)
                db.commit()

            u_msg = Message(
                conversation_id=conv.id,
                role="user",
                content=user_prompt,
                status="completed"
            )
            db.add(u_msg)
            db.flush()

            a_msg = Message(
                conversation_id=conv.id,
                parent_id=u_msg.id,
                role="assistant",
                content=assistant_response,
                status="completed"
            )
            db.add(a_msg)

            # Update daily UsageStat
            today = date.today()
            stat = (
                db.query(UsageStat)
                .filter_by(user_id=user.id, model=model_name, day=today)
                .first()
            )
            if stat:
                stat.requests += 1
            else:
                db.add(UsageStat(user_id=user.id, model=model_name, day=today, requests=1))

            db.commit()
    except Exception as e:
        logger.debug(f"Non-fatal SQLite turn persistence warning: {e}")

def load_conversation_history(session_id: str, limit: int = 16) -> List[Dict[str, str]]:
    """Loads recent messages for a session_id from SQLite on startup/cache miss."""
    try:
        with SessionLocal() as db:
            msgs = (
                db.query(Message)
                .filter_by(conversation_id=session_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {"role": m.role, "content": m.content}
                for m in reversed(msgs)
            ]
    except Exception:
        return []

def persist_memory_orm(kind: str, content: str, importance: float = 1.0) -> None:
    """Persists an episodic memory entry into the SQLite memories table."""
    try:
        with SessionLocal() as db:
            user = db.query(User).filter_by(username="admin").first()
            if not user:
                return
            exists = db.query(Memory).filter_by(user_id=user.id, content=content).first()
            if not exists:
                db.add(Memory(user_id=user.id, kind=kind, content=content, importance=importance))
                db.commit()
    except Exception as e:
        logger.debug(f"SQLite memory persistence skipped: {e}")

def verify_api_key_in_db(token: str) -> bool:
    """Checks if a bearer token matches a registered ApiKey in SQLite."""
    try:
        with SessionLocal() as db:
            record = db.query(ApiKey).filter_by(key_hash=token).first()
            return record is not None
    except Exception:
        return False

def persist_audit_orm(action: str, details: Dict[str, Any]) -> None:
    """Writes an audit log entry to the SQLite audit_logs table."""
    try:
        with SessionLocal() as db:
            user = db.query(User).filter_by(username="admin").first()
            user_id = user.id if user else None
            db.add(AuditLog(user_id=user_id, action=action, details=details))
            db.commit()
    except Exception:
        pass
