"""SQLAlchemy models (thesis section 4.2.4) plus ProctoringIncident and Consent."""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    student = "student"
    staff = "staff"


class IncidentType(str, enum.Enum):
    no_face = "no_face"
    multiple_faces = "multiple_faces"
    looking_away = "looking_away"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    reviewed_ok = "reviewed_ok"
    needs_follow_up = "needs_follow_up"


class AttemptStatus(str, enum.Enum):
    in_progress = "in_progress"
    paused = "paused"  # auto-paused after repeated looking-away; waiting for a staff decision
    submitted = "submitted"
    terminated = "terminated"  # staff decided the student may not continue


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    student: Mapped["Student | None"] = relationship(back_populates="user", uselist=False)
    staff: Mapped["Staff | None"] = relationship(back_populates="user", uselist=False)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    student_number: Mapped[str] = mapped_column(String(32), unique=True)

    user: Mapped[User] = relationship(back_populates="student")
    answers: Mapped[list["StudentAnswer"]] = relationship(back_populates="student")
    attempts: Mapped[list["ExamAttempt"]] = relationship(back_populates="student")


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    department: Mapped[str] = mapped_column(String(128), default="")

    user: Mapped[User] = relationship(back_populates="staff")
    examinations: Mapped[list["Examination"]] = relationship(back_populates="created_by")


class Examination(Base):
    __tablename__ = "examinations"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    created_by: Mapped[Staff] = relationship(back_populates="examinations")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="examination", order_by="Question.order", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    examination_id: Mapped[int] = mapped_column(ForeignKey("examinations.id", ondelete="CASCADE"))
    order: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON)
    correct_answer: Mapped[str] = mapped_column(String(255))
    marks: Mapped[float] = mapped_column(Float, default=1.0)

    examination: Mapped[Examination] = relationship(back_populates="questions")


class ExamAttempt(Base):
    __tablename__ = "exam_attempts"
    __table_args__ = (UniqueConstraint("student_id", "examination_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    examination_id: Mapped[int] = mapped_column(ForeignKey("examinations.id", ondelete="CASCADE"))
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, name="attempt_status"), default=AttemptStatus.in_progress
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Pause / staff-decision workflow
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_reason: Mapped[str] = mapped_column(String(255), default="")
    last_resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    help_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    help_message: Mapped[str] = mapped_column(Text, default="")
    decision_note: Mapped[str] = mapped_column(Text, default="")
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    student: Mapped[Student] = relationship(back_populates="attempts")


class StudentAnswer(Base):
    __tablename__ = "student_answers"
    __table_args__ = (UniqueConstraint("student_id", "question_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    examination_id: Mapped[int] = mapped_column(ForeignKey("examinations.id", ondelete="CASCADE"))
    answer: Mapped[str] = mapped_column(String(255))
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    marks_obtained: Mapped[float] = mapped_column(Float, default=0.0)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    student: Mapped[Student] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship()


class ProctoringIncident(Base):
    __tablename__ = "proctoring_incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    examination_id: Mapped[int] = mapped_column(
        ForeignKey("examinations.id", ondelete="CASCADE"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    incident_type: Mapped[IncidentType] = mapped_column(Enum(IncidentType, name="incident_type"))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status"), default=ReviewStatus.pending
    )
    reviewer_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    student: Mapped[Student] = relationship()
