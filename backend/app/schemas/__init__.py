"""Pydantic schemas for every API input and output."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import IncidentType, ReviewStatus, Role


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    full_name: str = ""
    password: str = Field(min_length=8, max_length=128)
    role: Role = Role.student
    student_number: str | None = None
    department: str | None = None


class UserOut(ORM):
    id: int
    username: str
    email: str
    full_name: str
    role: Role
    consent_given_at: datetime | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    username: str


# ---------- Exams ----------
class QuestionCreate(BaseModel):
    text: str = Field(min_length=1)
    options: list[str] = Field(min_length=2)
    correct_answer: str
    marks: float = Field(default=1.0, gt=0)
    order: int = 0

    @model_validator(mode="after")
    def answer_in_options(self):
        if self.correct_answer not in self.options:
            raise ValueError("correct_answer must be one of options")
        return self


class QuestionUpdate(BaseModel):
    text: str | None = None
    options: list[str] | None = None
    correct_answer: str | None = None
    marks: float | None = Field(default=None, gt=0)
    order: int | None = None


class QuestionStaffOut(ORM):
    id: int
    order: int
    text: str
    options: list[str]
    correct_answer: str
    marks: float


class QuestionStudentOut(ORM):
    """What a student sees. Deliberately has no correct_answer field."""

    id: int
    order: int
    text: str
    options: list[str]
    marks: float


class StudentQuestionPage(BaseModel):
    index: int
    total: int
    question: QuestionStudentOut
    selected_answer: str | None = None


class ExamCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    duration_minutes: int = Field(default=60, gt=0, le=600)
    is_active: bool = False
    questions: list[QuestionCreate] = []


class ExamUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    duration_minutes: int | None = Field(default=None, gt=0, le=600)
    is_active: bool | None = None


class ExamOut(ORM):
    id: int
    title: str
    description: str
    duration_minutes: int
    is_active: bool
    question_count: int = 0


class ExamStaffOut(ExamOut):
    questions: list[QuestionStaffOut] = []


class AttemptOut(ORM):
    id: int
    examination_id: int
    status: str
    started_at: datetime
    submitted_at: datetime | None = None


class AnswerSubmit(BaseModel):
    question_id: int
    answer: str


class AnswerResult(BaseModel):
    question_id: int
    answer: str
    saved: bool = True


class Progress(BaseModel):
    examination_id: int
    total_questions: int
    answered: int
    status: str
    score: float | None = None
    max_score: float | None = None


# ---------- Proctoring ----------
class FrameIn(BaseModel):
    exam_id: int
    image: str = Field(description="Base64-encoded JPEG, optionally a data: URL")

    @field_validator("image")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("image is empty")
        return v


class FrameResult(BaseModel):
    face_detected: bool
    face_count: int
    gaze: Literal["at", "away"] | None
    confidence: float
    warning: str | None
    incident_id: int | None = None
    processing_ms: float


class IncidentOut(ORM):
    id: int
    student_id: int
    examination_id: int
    timestamp: datetime
    incident_type: IncidentType
    confidence: float
    review_status: ReviewStatus
    reviewer_note: str = ""
    evidence_url: str | None = None


class IncidentReview(BaseModel):
    review_status: Literal["reviewed_ok", "needs_follow_up"]
    note: str = ""


class ConsentOut(BaseModel):
    consent_given_at: datetime | None
    capture_interval_seconds: int
    retention_days: int


# ---------- Reports ----------
class StudentSummary(BaseModel):
    student_id: int
    username: str
    full_name: str
    attempt_status: str | None
    incident_count: int
    incidents_by_type: dict[str, int]
    first_incident: datetime | None
    last_incident: datetime | None
    score: float
    max_score: float
    flagged: bool
    flag_reasons: list[str]
    pending_reviews: int


class ExamReport(BaseModel):
    examination_id: int
    title: str
    students: list[StudentSummary]


class StudentTimeline(BaseModel):
    examination_id: int
    student_id: int
    username: str
    flagged: bool
    flag_reasons: list[str]
    incidents: list[IncidentOut]
