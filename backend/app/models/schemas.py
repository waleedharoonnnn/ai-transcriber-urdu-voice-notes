from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NoteResponse(BaseModel):
    id: str
    urdu_text: str
    urdu_text_corrected: Optional[str]
    english_text: str
    title: Optional[str]
    tags: Optional[list[str]]
    audio_url: Optional[str]
    duration_seconds: Optional[int]
    created_at: datetime


class SearchResult(BaseModel):
    id: str
    english_text: str
    urdu_text: str
    urdu_text_corrected: Optional[str]
    title: Optional[str]
    tags: Optional[list[str]]
    similarity: float
    created_at: datetime


class AuthRequest(BaseModel):
    email: str
    password: str


class SummaryPreferenceRequest(BaseModel):
    user_id: str
    days: int


class NoteUpdateRequest(BaseModel):
    title: Optional[str] = None
    tags: Optional[list[str]] = None
    english_text: Optional[str] = None
    urdu_text: Optional[str] = None
    urdu_text_corrected: Optional[str] = None


class SemanticSearchRequest(BaseModel):
    query: str
    top_k: int = 10
