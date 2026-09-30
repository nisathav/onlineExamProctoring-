"""Seed one staff user, one student and a 10-question MCQ exam.

Usage: python -m app.seed   (credentials from SEED_* env vars, with dev defaults)
"""
import os

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Examination, Question, Role, Staff, Student, User

SAMPLE_QUESTIONS = [
    ("What does CPU stand for?", ["Central Processing Unit", "Computer Personal Unit", "Central Program Utility", "Core Processing Utility"], "Central Processing Unit"),
    ("Which data structure uses FIFO order?", ["Stack", "Queue", "Tree", "Graph"], "Queue"),
    ("What is 2^10?", ["512", "1000", "1024", "2048"], "1024"),
    ("Which HTTP status code means 'Not Found'?", ["200", "301", "404", "500"], "404"),
    ("Which language runs natively in web browsers?", ["Python", "JavaScript", "C++", "Java"], "JavaScript"),
    ("What does SQL stand for?", ["Structured Query Language", "Simple Question Language", "Sequential Query Logic", "Standard Query List"], "Structured Query Language"),
    ("Binary search on a sorted array runs in:", ["O(n)", "O(log n)", "O(n log n)", "O(1)"], "O(log n)"),
    ("Which port does HTTPS use by default?", ["21", "80", "443", "8080"], "443"),
    ("Which of these is a version control system?", ["Docker", "Git", "Nginx", "Redis"], "Git"),
    ("What does RAM stand for?", ["Random Access Memory", "Read Access Memory", "Rapid Action Module", "Runtime Allocation Map"], "Random Access Memory"),
]


def _user(db: Session, username: str, email: str, password: str, role: Role, full_name: str) -> User:
    user = db.query(User).filter_by(username=username).first()
    if user:
        return user
    user = User(username=username, email=email, full_name=full_name,
                hashed_password=hash_password(password), role=role)
    db.add(user)
    db.flush()
    if role == Role.staff:
        db.add(Staff(user_id=user.id, department="Computing"))
    else:
        db.add(Student(user_id=user.id, student_number=f"S{user.id:06d}"))
    db.flush()
    return user


def seed(db: Session) -> None:
    staff = _user(db, os.getenv("SEED_STAFF_USER", "staff1"), "staff1@example.com",
                  os.getenv("SEED_STAFF_PASSWORD", "staffpass123"), Role.staff, "Dr. Staff")
    _user(db, os.getenv("SEED_STUDENT_USER", "student1"), "student1@example.com",
          os.getenv("SEED_STUDENT_PASSWORD", "studentpass123"), Role.student, "Sam Student")
    db.refresh(staff)

    if not db.query(Examination).filter_by(title="Sample Computing Quiz").first():
        exam = Examination(title="Sample Computing Quiz",
                           description="10 multiple-choice questions. Webcam and screen sharing required.",
                           duration_minutes=20, is_active=True, created_by_id=staff.staff.id)
        for i, (text, options, answer) in enumerate(SAMPLE_QUESTIONS, start=1):
            exam.questions.append(Question(order=i, text=text, options=options, correct_answer=answer))
        db.add(exam)
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session)
    print("Seed complete")
