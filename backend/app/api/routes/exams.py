"""Examination API. Students never receive Question.correct_answer."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import (
    AttemptStatus,
    ExamAttempt,
    Examination,
    Question,
    Role,
    StudentAnswer,
    User,
)
from app.schemas import (
    AnswerResult,
    AnswerSubmit,
    AttemptOut,
    ExamCreate,
    ExamOut,
    ExamStaffOut,
    ExamUpdate,
    Progress,
    QuestionCreate,
    QuestionStaffOut,
    QuestionStudentOut,
    QuestionUpdate,
    StudentQuestionPage,
)

router = APIRouter(tags=["exams"])
staff_only = require_role("staff")
student_only = require_role("student")


def _exam_out(exam: Examination, cls=ExamOut):
    out = cls.model_validate(exam)
    out.question_count = len(exam.questions)
    return out


def _get_exam(db: Session, exam_id: int) -> Examination:
    exam = db.get(Examination, exam_id)
    if exam is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Examination not found")
    return exam


def _active_exam_for_student(db: Session, exam_id: int) -> Examination:
    exam = _get_exam(db, exam_id)
    if not exam.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Examination not found")
    return exam


def _attempt(db: Session, user: User, exam_id: int) -> ExamAttempt | None:
    return (
        db.query(ExamAttempt)
        .filter_by(student_id=user.student.id, examination_id=exam_id)
        .first()
    )


def _require_in_progress(db: Session, user: User, exam_id: int) -> ExamAttempt:
    attempt = _attempt(db, user, exam_id)
    if attempt is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Exam not started")
    if attempt.status != AttemptStatus.in_progress:
        raise HTTPException(status.HTTP_409_CONFLICT, "Exam already submitted")
    return attempt


# ---------------- Listing ----------------
@router.get("/exams", response_model=list[ExamOut])
def list_exams(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Examination)
    if user.role == Role.student:
        q = q.filter(Examination.is_active.is_(True))
    return [_exam_out(e) for e in q.order_by(Examination.id).all()]


@router.get("/exams/{exam_id}", response_model=ExamOut | ExamStaffOut)
def get_exam(exam_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == Role.staff:
        return _exam_out(_get_exam(db, exam_id), ExamStaffOut)
    return _exam_out(_active_exam_for_student(db, exam_id))


# ---------------- Staff: manage exams ----------------
@router.post("/exams", response_model=ExamStaffOut, status_code=status.HTTP_201_CREATED)
def create_exam(body: ExamCreate, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    exam = Examination(
        title=body.title,
        description=body.description,
        duration_minutes=body.duration_minutes,
        is_active=body.is_active,
        created_by_id=user.staff.id,
    )
    for i, q in enumerate(body.questions):
        exam.questions.append(Question(**q.model_dump(exclude={"order"}), order=q.order or i + 1))
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return _exam_out(exam, ExamStaffOut)


@router.put("/exams/{exam_id}", response_model=ExamStaffOut)
def update_exam(
    exam_id: int, body: ExamUpdate, _: User = Depends(staff_only), db: Session = Depends(get_db)
):
    exam = _get_exam(db, exam_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(exam, key, value)
    db.commit()
    db.refresh(exam)
    return _exam_out(exam, ExamStaffOut)


@router.post(
    "/exams/{exam_id}/questions", response_model=QuestionStaffOut, status_code=status.HTTP_201_CREATED
)
def add_question(
    exam_id: int, body: QuestionCreate, _: User = Depends(staff_only), db: Session = Depends(get_db)
):
    exam = _get_exam(db, exam_id)
    question = Question(**body.model_dump(exclude={"order"}), order=body.order or len(exam.questions) + 1)
    exam.questions.append(question)
    db.commit()
    db.refresh(question)
    return question


@router.put("/questions/{question_id}", response_model=QuestionStaffOut)
def update_question(
    question_id: int, body: QuestionUpdate, _: User = Depends(staff_only), db: Session = Depends(get_db)
):
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(question, key, value)
    if question.correct_answer not in question.options:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "correct_answer must be one of options")
    db.commit()
    db.refresh(question)
    return question


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(question_id: int, _: User = Depends(staff_only), db: Session = Depends(get_db)):
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    db.delete(question)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- Student: sit an exam ----------------
@router.post("/exams/{exam_id}/start", response_model=AttemptOut)
def start_exam(exam_id: int, user: User = Depends(student_only), db: Session = Depends(get_db)):
    _active_exam_for_student(db, exam_id)
    if user.consent_given_at is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Proctoring consent required before starting")
    attempt = _attempt(db, user, exam_id)
    if attempt is None:
        attempt = ExamAttempt(student_id=user.student.id, examination_id=exam_id)
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
    elif attempt.status != AttemptStatus.in_progress:
        raise HTTPException(status.HTTP_409_CONFLICT, "Exam already submitted")
    return AttemptOut(
        id=attempt.id,
        examination_id=attempt.examination_id,
        status=attempt.status.value,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
    )


@router.get("/exams/{exam_id}/questions/{index}", response_model=StudentQuestionPage)
def get_question(
    exam_id: int, index: int, user: User = Depends(student_only), db: Session = Depends(get_db)
):
    exam = _active_exam_for_student(db, exam_id)
    _require_in_progress(db, user, exam_id)
    total = len(exam.questions)
    if index < 0 or index >= total:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question index out of range")
    question = exam.questions[index]
    existing = (
        db.query(StudentAnswer)
        .filter_by(student_id=user.student.id, question_id=question.id)
        .first()
    )
    return StudentQuestionPage(
        index=index,
        total=total,
        question=QuestionStudentOut.model_validate(question),
        selected_answer=existing.answer if existing else None,
    )


@router.post("/exams/{exam_id}/answers", response_model=AnswerResult)
def submit_answer(
    exam_id: int, body: AnswerSubmit, user: User = Depends(student_only), db: Session = Depends(get_db)
):
    _active_exam_for_student(db, exam_id)
    _require_in_progress(db, user, exam_id)
    question = db.get(Question, body.question_id)
    if question is None or question.examination_id != exam_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found in this exam")
    if body.answer not in question.options:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Answer must be one of the options")

    is_correct = body.answer == question.correct_answer
    answer = (
        db.query(StudentAnswer)
        .filter_by(student_id=user.student.id, question_id=question.id)
        .first()
    )
    if answer is None:
        answer = StudentAnswer(
            student_id=user.student.id, question_id=question.id, examination_id=exam_id, answer=""
        )
        db.add(answer)
    answer.answer = body.answer
    answer.is_correct = is_correct
    answer.marks_obtained = question.marks if is_correct else 0.0
    answer.answered_at = datetime.now(timezone.utc)
    db.commit()
    return AnswerResult(question_id=question.id, answer=body.answer)


def _score(db: Session, student_id: int, exam: Examination) -> tuple[float, float]:
    score = (
        db.query(func.coalesce(func.sum(StudentAnswer.marks_obtained), 0.0))
        .filter_by(student_id=student_id, examination_id=exam.id)
        .scalar()
    )
    return float(score), float(sum(q.marks for q in exam.questions))


@router.post("/exams/{exam_id}/submit", response_model=Progress)
def submit_exam(exam_id: int, user: User = Depends(student_only), db: Session = Depends(get_db)):
    _active_exam_for_student(db, exam_id)
    attempt = _require_in_progress(db, user, exam_id)
    attempt.status = AttemptStatus.submitted
    attempt.submitted_at = datetime.now(timezone.utc)
    db.commit()
    return progress(exam_id, user, db)


@router.get("/exams/{exam_id}/progress", response_model=Progress)
def progress(exam_id: int, user: User = Depends(student_only), db: Session = Depends(get_db)):
    exam = _active_exam_for_student(db, exam_id)
    attempt = _attempt(db, user, exam_id)
    answered = (
        db.query(StudentAnswer).filter_by(student_id=user.student.id, examination_id=exam_id).count()
    )
    result = Progress(
        examination_id=exam_id,
        total_questions=len(exam.questions),
        answered=answered,
        status=attempt.status.value if attempt else "not_started",
    )
    if attempt and attempt.status == AttemptStatus.submitted:
        result.score, result.max_score = _score(db, user.student.id, exam)
    return result
