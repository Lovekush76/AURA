"""
Aura Assistant - Relational Database Schema Models (SQLAlchemy ORM)
Implements all entities defined in the System Architecture & Database Schema Blueprint:
- 1. Chat and tools: USERS, CONVERSATIONS, MESSAGES, ATTACHMENTS, TOOL_CALLS, FEEDBACK
- 2. Knowledge and memory: COLLECTIONS, DOCUMENTS, CHUNKS, MEMORIES
- 3. Platform and operations: API_KEYS, PROMPT_TEMPLATES, MODEL_PROFILES, TASKS, TASK_RUNS, AUDIT_LOGS, USAGE_STATS
"""

import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float, ForeignKey, DateTime, Date, JSON, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def generate_uuid() -> str:
    return str(uuid.uuid4())

# ==============================================================================
# 1. CORE USER & CHAT DOMAIN
# ==============================================================================

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(64), unique=True, nullable=False, index=True)
    role = Column(String(32), default="user", nullable=False)
    preferences = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    collections = relationship("Collection", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    prompt_templates = relationship("PromptTemplate", back_populates="owner", cascade="all, delete-orphan")
    model_profiles = relationship("ModelProfile", back_populates="owner", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")
    usage_stats = relationship("UsageStat", back_populates="user", cascade="all, delete-orphan")

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), default="New Conversation")
    model = Column(String(64), default="qwen3.5:4b")
    is_incognito = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    role = Column(String(32), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    status = Column(String(32), default="completed")  # 'pending', 'streaming', 'completed', 'error'
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")
    parent = relationship("Message", remote_side=[id])
    attachments = relationship("Attachment", back_populates="message", cascade="all, delete-orphan")
    tool_calls = relationship("ToolCall", back_populates="message", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="message", cascade="all, delete-orphan")

class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    message_id = Column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(64), nullable=False)  # 'image', 'audio', 'document', 'diff'
    sha256 = Column(String(64), nullable=False)
    file_path = Column(String(512), nullable=True)

    message = relationship("Message", back_populates="attachments")

class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    message_id = Column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = Column(String(64), nullable=False)
    arguments = Column(JSON, default=dict)
    status = Column(String(32), default="success")  # 'running', 'success', 'failed'
    output = Column(Text, nullable=True)

    message = relationship("Message", back_populates="tool_calls")

class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    message_id = Column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    rating = Column(String(16), nullable=False)  # 'thumbs_up', 'thumbs_down', '1-5'
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    message = relationship("Message", back_populates="feedback")

# ==============================================================================
# 2. KNOWLEDGE & MEMORY DOMAIN
# ==============================================================================

class Collection(Base):
    __tablename__ = "collections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    classification = Column(String(32), default="internal")  # 'public', 'internal', 'restricted'
    embedding_model = Column(String(64), default="nomic-embed-text")
    embedding_dim = Column(Integer, default=768)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="collections")
    documents = relationship("Document", back_populates="collection", cascade="all, delete-orphan")

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("collection_id", "sha256", name="uq_collection_document_hash"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    collection_id = Column(String(36), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    sha256 = Column(String(64), nullable=False)
    status = Column(String(32), default="indexed")
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    collection = relationship("Collection", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    ordinal = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    page = Column(Integer, default=1)

    document = relationship("Document", back_populates="chunks")

class Memory(Base):
    __tablename__ = "memories"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_message_id = Column(String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(64), default="preference")  # 'preference', 'fact', 'habit', 'identity'
    content = Column(Text, nullable=False)
    importance = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="memories")

# ==============================================================================
# 3. PLATFORM & OPERATIONS DOMAIN
# ==============================================================================

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key_hash = Column(String(128), unique=True, nullable=False, index=True)
    scopes = Column(JSON, default=list)  # e.g. ["chat", "code:exec", "workspace:patch"]
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="api_keys")

class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    version = Column(Integer, default=1)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="prompt_templates")

class ModelProfile(Base):
    __tablename__ = "model_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    base_model = Column(String(64), nullable=False)
    parameters = Column(JSON, default=dict)  # e.g. {"temperature": 0.4, "num_ctx": 4096}
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="model_profiles")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    schedule = Column(String(64), nullable=False)  # Cron or interval expression
    status = Column(String(32), default="active")  # 'active', 'paused', 'completed'
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="tasks")
    runs = relationship("TaskRun", back_populates="task", cascade="all, delete-orphan")

class TaskRun(Base):
    __tablename__ = "task_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), default="running")  # 'running', 'success', 'failed'
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    logs = Column(Text, nullable=True)

    task = relationship("Task", back_populates="runs")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(64), nullable=False)
    details = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_logs")

class UsageStat(Base):
    __tablename__ = "usage_stats"
    __table_args__ = (
        UniqueConstraint("user_id", "model", "day", name="uq_user_model_day"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    model = Column(String(64), nullable=False)
    day = Column(Date, default=date.today)
    requests = Column(Integer, default=1)

    user = relationship("User", back_populates="usage_stats")
