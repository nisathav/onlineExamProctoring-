"""Account and login API (/auth/...): register a student, log in to get a JWT token,
read your own profile, and record the student's consent to camera monitoring.
Login attempts are rate-limited."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limit import RateLimiter
from app.core.security import (
    create_access_token,
    decode_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)
from app.db.session import get_db
from app.models import Role, Staff, Student, User
from app.schemas import ConsentOut, Token, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

_settings = get_settings()
login_limiter = RateLimiter(_settings.login_rate_limit, _settings.login_rate_window_seconds)
optional_token = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    body: UserCreate,
    db: Session = Depends(get_db),
    token: str | None = Depends(optional_token),
):
    """Open registration creates students. Creating a staff account needs a staff token."""
    if body.role == Role.staff:
        if not token or decode_token(token).get("role") != Role.staff.value:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only staff can create staff accounts")

    if db.query(User).filter((User.username == body.username) | (User.email == body.email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username or email already registered")

    user = User(
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.flush()
    if body.role == Role.student:
        number = body.student_number or f"S{user.id:06d}"
        if db.query(Student).filter(Student.student_number == number).first():
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Student number already registered")
        db.add(Student(user_id=user.id, student_number=number))
    else:
        db.add(Staff(user_id=user.id, department=body.department or ""))
    db.commit()
    db.refresh(user)
    return user


@router.post("/token", response_model=Token)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    client = request.client.host if request.client else "unknown"
    if not login_limiter.allow(f"{client}:{form.username}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts, try later")

    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password) or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user.username, user.role.value)
    return Token(access_token=token, role=user.role, username=user.username)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


def _consent_out(user: User) -> ConsentOut:
    s = get_settings()
    return ConsentOut(
        consent_given_at=user.consent_given_at,
        capture_interval_seconds=s.capture_interval_seconds,
        retention_days=s.evidence_retention_days,
    )


@router.get("/consent", response_model=ConsentOut)
def get_consent(user: User = Depends(require_role("student"))):
    return _consent_out(user)


@router.post("/consent", response_model=ConsentOut)
def give_consent(user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    user = db.merge(user)
    if user.consent_given_at is None:
        user.consent_given_at = datetime.now(timezone.utc)
        db.commit()
    return _consent_out(user)
