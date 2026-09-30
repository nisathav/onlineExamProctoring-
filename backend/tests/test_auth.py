"""Authentication and token security: AUTH-1..AUTH-7, SEC-1..SEC-3."""
from datetime import timedelta

from jose import jwt

from app.core.security import create_access_token, hash_password, verify_password
from tests.conftest import login


def test_auth_1_register_student(client):
    """AUTH-1: a new student can register; password is never returned."""
    r = client.post("/auth/register", json={
        "username": "alice", "email": "alice@example.com", "password": "password123", "full_name": "Alice",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "student"
    assert "password" not in body and "hashed_password" not in body


def test_auth_2_duplicate_registration_rejected(client):
    """AUTH-2: duplicate username/email is rejected."""
    payload = {"username": "student1", "email": "x@example.com", "password": "password123"}
    assert client.post("/auth/register", json=payload).status_code == 409


def test_auth_2b_weak_input_rejected(client):
    """AUTH-2: short password / bad email are validation errors."""
    assert client.post("/auth/register", json={"username": "bob", "email": "bob@example.com", "password": "short"}).status_code == 422
    assert client.post("/auth/register", json={"username": "bob", "email": "not-an-email", "password": "password123"}).status_code == 422


def test_auth_3_login_returns_jwt(client):
    """AUTH-3: valid credentials return a bearer JWT with role."""
    r = client.post("/auth/token", data={"username": "student1", "password": "studentpass123"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["role"] == "student"
    claims = jwt.get_unverified_claims(body["access_token"])
    assert claims["sub"] == "student1" and "exp" in claims


def test_auth_4_wrong_password_rejected(client):
    """AUTH-4: wrong password / unknown user gives 401 with no detail about which."""
    r1 = client.post("/auth/token", data={"username": "student1", "password": "nope"})
    r2 = client.post("/auth/token", data={"username": "ghost", "password": "nope"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"]


def test_auth_5_passwords_are_bcrypt_hashed(db):
    """AUTH-5: stored passwords are bcrypt hashes, not plaintext."""
    from app.models import User

    user = db.query(User).filter_by(username="student1").one()
    assert user.hashed_password.startswith("$2") and "studentpass123" not in user.hashed_password
    h = hash_password("abc12345")
    assert verify_password("abc12345", h) and not verify_password("wrong", h)


def test_auth_6_me_returns_current_user(client, student_headers):
    """AUTH-6: /auth/me identifies the token's user."""
    r = client.get("/auth/me", headers=student_headers)
    assert r.status_code == 200 and r.json()["username"] == "student1"


def test_auth_7_role_separation(client, student_headers, staff_headers, exam_id):
    """AUTH-7: students cannot use staff routes; staff cannot use student routes."""
    assert client.post("/exams", json={"title": "x"}, headers=student_headers).status_code == 403
    assert client.get(f"/reports/exams/{exam_id}", headers=student_headers).status_code == 403
    assert client.post(f"/exams/{exam_id}/start", headers=staff_headers).status_code == 403


def test_auth_7b_staff_registration_needs_staff_token(client, student_headers, staff_headers):
    """AUTH-7: public users and students cannot self-register as staff."""
    payload = {"username": "evil", "email": "evil@example.com", "password": "password123", "role": "staff"}
    assert client.post("/auth/register", json=payload).status_code == 403
    assert client.post("/auth/register", json=payload, headers=student_headers).status_code == 403
    assert client.post("/auth/register", json=payload, headers=staff_headers).status_code == 201


def test_sec_1_routes_require_token(client, exam_id):
    """SEC-1 / NFR2: every non-auth route rejects requests without a token."""
    for method, path in [
        ("get", "/exams"), ("get", "/auth/me"), ("post", f"/exams/{exam_id}/start"),
        ("post", "/proctoring/frame"), ("get", f"/reports/exams/{exam_id}"),
    ]:
        assert getattr(client, method)(path).status_code == 401, path
    assert client.get("/health").status_code == 200


def test_sec_2_tampered_token_rejected(client, student_headers):
    """SEC-2: a token signed with another key, or edited, is rejected."""
    forged = jwt.encode({"sub": "staff1", "role": "staff"}, "wrong-key", algorithm="HS256")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    token = student_headers["Authorization"].split()[1]
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_sec_3_expired_token_rejected(client):
    """SEC-3: an expired token is rejected."""
    token = create_access_token("student1", "student", expires_delta=timedelta(seconds=-5))
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_sec_3b_token_for_deleted_user_rejected(client, db):
    """SEC-3: a valid token for a user that no longer exists is rejected."""
    token = create_access_token("nobody", "student")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_sec_4_login_rate_limited(client):
    """SEC-4: repeated login attempts are rate limited."""
    codes = [client.post("/auth/token", data={"username": "student1", "password": "bad"}).status_code
             for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[-1] == 429


def test_login_helper_works_for_staff(client):
    assert "Authorization" in login(client, "staff1", "staffpass123")
