"""Pydantic request/response schemas (API contracts)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

# ---------- Auth ----------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: UUID
    email: str
    role: str

    model_config = {"from_attributes": True}


# ---------- Documents ----------


class DocumentOut(BaseModel):
    id: UUID
    title: str
    source_type: str
    status: str
    chunk_count: int
    knowledge_base_id: UUID | None = None
    error: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class IngestTextRequest(BaseModel):
    title: str = Field(max_length=512)
    content: str = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)
    knowledge_base_id: UUID | None = None


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class KnowledgeBaseMoveRequest(BaseModel):
    knowledge_base_id: UUID | None


class KnowledgeBaseOut(BaseModel):
    id: UUID
    name: str
    description: str
    document_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Search ----------


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    knowledge_base_id: UUID | None = None


class SearchHit(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    content: str
    score: float


class SearchResponse(BaseModel):
    hits: list[SearchHit]


# ---------- Chat ----------


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: UUID | None = None
    knowledge_base_id: UUID | None = None


class Citation(BaseModel):
    document_id: str
    document_title: str
    chunk_id: str
    snippet: str


class ChatResponse(BaseModel):
    conversation_id: UUID
    answer: str
    citations: list[Citation] = []
    usage: dict = {}
