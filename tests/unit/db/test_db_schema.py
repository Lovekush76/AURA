import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from aura_assistant.core.db.schema import (
    Base, User, Conversation, Message, Attachment, ToolCall, Feedback,
    Collection, Document, Chunk, Memory,
    ApiKey, PromptTemplate, ModelProfile, Task, TaskRun, AuditLog, UsageStat
)

@pytest.fixture
def db_session():
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    yield session
    session.close()

def test_chat_domain_schema(db_session):
    # 1. User
    user = User(username="alice", role="developer", preferences={"theme": "dark"})
    db_session.add(user)
    db_session.commit()
    assert user.id is not None

    # 2. Conversation
    conv = Conversation(user_id=user.id, title="Refactor Auth", model="qwen3-coder:30b")
    db_session.add(conv)
    db_session.commit()
    assert conv.user.username == "alice"

    # 3. Message
    msg = Message(conversation_id=conv.id, role="user", content="Add JWT tokens")
    db_session.add(msg)
    db_session.commit()

    # 4. Attachment
    att = Attachment(message_id=msg.id, kind="diff", sha256="abc123sha")
    db_session.add(att)

    # 5. Tool Call
    tc = ToolCall(message_id=msg.id, tool_name="run_code", arguments={"code": "print(1)"}, status="success")
    db_session.add(tc)

    # 6. Feedback
    fb = Feedback(message_id=msg.id, rating="thumbs_up", comment="Clean patch")
    db_session.add(fb)
    db_session.commit()

    assert len(msg.attachments) == 1
    assert len(msg.tool_calls) == 1
    assert len(msg.feedback) == 1

def test_knowledge_and_memory_schema(db_session):
    user = User(username="bob", role="user")
    db_session.add(user)
    db_session.commit()

    # Collection
    coll = Collection(user_id=user.id, name="Project Specs", embedding_model="nomic-embed-text")
    db_session.add(coll)
    db_session.commit()

    # Document
    doc = Document(collection_id=coll.id, filename="BRD.md", sha256="hash987")
    db_session.add(doc)
    db_session.commit()

    # Chunks
    c1 = Chunk(document_id=doc.id, ordinal=1, text="System Architecture Intro")
    c2 = Chunk(document_id=doc.id, ordinal=2, text="Database Schema Blueprint")
    db_session.add_all([c1, c2])

    # Memory
    mem = Memory(user_id=user.id, kind="preference", content="Prefers TypeScript over Python for UI", importance=0.9)
    db_session.add(mem)
    db_session.commit()

    assert len(doc.chunks) == 2
    assert len(user.memories) == 1

def test_platform_and_operations_schema(db_session):
    user = User(username="carol", role="admin")
    db_session.add(user)
    db_session.commit()

    # ApiKey
    key = ApiKey(user_id=user.id, key_hash="secret_key_hash", scopes=["admin"])
    # PromptTemplate
    pt = PromptTemplate(owner_id=user.id, name="code_review", version=1, content="Analyze diff for bugs")
    # ModelProfile
    mp = ModelProfile(owner_id=user.id, base_model="qwen3-coder:30b", parameters={"temp": 0.2})
    # Task & TaskRun
    task = Task(user_id=user.id, schedule="0 0 * * *", status="active")
    db_session.add_all([key, pt, mp, task])
    db_session.commit()

    tr = TaskRun(task_id=task.id, status="success", logs="Audit executed cleanly")
    # AuditLog
    al = AuditLog(user_id=user.id, action="CREATE_KEY", details={"key": "secret_key_hash"})
    # UsageStat
    us = UsageStat(user_id=user.id, model="qwen3-coder:30b", requests=42)
    db_session.add_all([tr, al, us])
    db_session.commit()

    assert len(task.runs) == 1
    assert len(user.audit_logs) == 1
    assert user.usage_stats[0].requests == 42
