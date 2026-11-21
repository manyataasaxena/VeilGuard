import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from pgvector.sqlalchemy import Vector
from app.core.database import Base


def utc_now():
    return datetime.now(timezone.utc)


def new_uuid():
    return str(uuid.uuid4())


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(120), unique=True, nullable=False)
    monthly_token_limit = Column(Integer, default=500000)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=new_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, default="INTERN")  # ADMIN, FINANCE, HR, INTERN
    created_at = Column(DateTime(timezone=True), default=utc_now)


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=new_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    allowed_roles = Column(ARRAY(String), nullable=False, default=lambda: ["ADMIN"])
    status = Column(String(30), default="PENDING")  # PENDING, PROCESSING, READY, FAILED
    total_pages = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, default=new_uuid)
    doc_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    allowed_roles = Column(ARRAY(String), nullable=False)
    page_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    search_vector = Column(TSVECTOR)      # Keyword (BM25/FTS) search ke liye
    embedding = Column(Vector(384))       # Vector semantic search ke liye (384 dimensions)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=new_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    user_role = Column(String(30), nullable=False)
    query_masked = Column(Text, nullable=False)
    pii_entities_found = Column(JSONB, default=list)
    injection_blocked = Column(Boolean, default=False)
    cache_hit = Column(Boolean, default=False)
    llm_provider = Column(String(50), default="none")
    latency_ms = Column(Float, default=0.0)
    tokens_used = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=utc_now)