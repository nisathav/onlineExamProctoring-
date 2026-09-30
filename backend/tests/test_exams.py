"""Examination API: EXAM-1..EXAM-4 and role separation."""


def _all_questions(client, headers, exam_id):
    first = client.get(f"/exams/{exam_id}/questions/0", headers=headers).json()
    return [client.get(f"/exams/{exam_id}/questions/{i}", headers=headers).json()
            for i in range(first["total"])]


def test_exam_1_student_lists_only_active_exams(client, staff_headers, student_headers):
    """EXAM-1: students see active exams only; staff see all."""
    client.post("/exams", json={"title": "Draft", "is_active": False}, headers=staff_headers)
    staff_titles = {e["title"] for e in client.get("/exams", headers=staff_headers).json()}
    student_titles = {e["title"] for e in client.get("/exams", headers=student_headers).json()}
    assert {"Draft", "Sample Computing Quiz"} <= staff_titles
    assert student_titles == {"Sample Computing Quiz"}
    assert "correct_answer" not in str(client.get("/exams", headers=student_headers).json())


def test_exam_2_staff_creates_and_updates_exam(client, staff_headers):
    """EXAM-2: staff can create/update exams and questions."""
    r = client.post("/exams", headers=staff_headers, json={
        "title": "Maths", "duration_minutes": 30,
        "questions": [{"text": "1+1?", "options": ["1", "2"], "correct_answer": "2"}],
    })
    assert r.status_code == 201
    exam = r.json()
    assert exam["question_count"] == 1 and exam["questions"][0]["correct_answer"] == "2"

    r = client.put(f"/exams/{exam['id']}", json={"is_active": True, "title": "Maths 1"}, headers=staff_headers)
    assert r.json()["is_active"] is True and r.json()["title"] == "Maths 1"

    q = client.post(f"/exams/{exam['id']}/questions", headers=staff_headers,
                    json={"text": "2+2?", "options": ["3", "4"], "correct_answer": "4", "marks": 2})
    assert q.status_code == 201 and q.json()["order"] == 2
    qid = q.json()["id"]
    assert client.put(f"/questions/{qid}", json={"text": "2+2=?"}, headers=staff_headers).json()["text"] == "2+2=?"
    assert client.put(f"/questions/{qid}", json={"correct_answer": "9"}, headers=staff_headers).status_code == 422
    assert client.delete(f"/questions/{qid}", headers=staff_headers).status_code == 204
    assert client.delete(f"/questions/{qid}", headers=staff_headers).status_code == 404
    assert client.get(f"/exams/{exam['id']}", headers=staff_headers).json()["question_count"] == 1


def test_exam_2b_invalid_question_rejected(client, staff_headers, exam_id):
    """EXAM-2: correct answer must be one of the options."""
    r = client.post(f"/exams/{exam_id}/questions", headers=staff_headers,
                    json={"text": "?", "options": ["a", "b"], "correct_answer": "c"})
    assert r.status_code == 422


def test_exam_3_questions_never_expose_correct_answer(client, student_headers, started_exam):
    """EXAM-3: students fetch one question at a time, never with correct_answer."""
    pages = _all_questions(client, student_headers, started_exam)
    assert len(pages) == 10
    for page in pages:
        assert "correct_answer" not in page["question"]
    assert client.get(f"/exams/{started_exam}/questions/10", headers=student_headers).status_code == 404
    student_view = client.get(f"/exams/{started_exam}", headers=student_headers).json()
    assert "questions" not in student_view


def test_exam_3b_must_start_and_consent_first(client, student_headers, exam_id):
    """EXAM-3: questions need a started attempt; starting needs proctoring consent."""
    assert client.get(f"/exams/{exam_id}/questions/0", headers=student_headers).status_code == 409
    assert client.post(f"/exams/{exam_id}/start", headers=student_headers).status_code == 403
    client.post("/auth/consent", headers=student_headers)
    assert client.post(f"/exams/{exam_id}/start", headers=student_headers).status_code == 200
    # Starting again resumes the same attempt.
    assert client.post(f"/exams/{exam_id}/start", headers=student_headers).status_code == 200


def test_exam_4_answers_auto_marked_and_progress(client, student_headers, started_exam, db):
    """EXAM-4: answers are auto-marked; progress and score reported after submit."""
    from app.models import Question

    pages = _all_questions(client, student_headers, started_exam)
    correct = {q.id: q.correct_answer for q in db.query(Question).filter_by(examination_id=started_exam)}
    for i, page in enumerate(pages):
        qid = page["question"]["id"]
        answer = correct[qid] if i < 7 else next(o for o in page["question"]["options"] if o != correct[qid])
        r = client.post(f"/exams/{started_exam}/answers", json={"question_id": qid, "answer": answer},
                        headers=student_headers)
        assert r.status_code == 200 and "is_correct" not in r.json()

    # Changing an answer overwrites rather than duplicates.
    first_qid = pages[0]["question"]["id"]
    client.post(f"/exams/{started_exam}/answers", json={"question_id": first_qid, "answer": correct[first_qid]},
                headers=student_headers)
    assert client.get(f"/exams/{started_exam}/questions/0", headers=student_headers).json()["selected_answer"] == correct[first_qid]

    progress = client.get(f"/exams/{started_exam}/progress", headers=student_headers).json()
    assert progress["answered"] == 10 and progress["score"] is None

    final = client.post(f"/exams/{started_exam}/submit", headers=student_headers).json()
    assert final["status"] == "submitted" and final["score"] == 7 and final["max_score"] == 10

    # No more answers after submission.
    r = client.post(f"/exams/{started_exam}/answers", json={"question_id": first_qid, "answer": "x"},
                    headers=student_headers)
    assert r.status_code == 409
    assert client.post(f"/exams/{started_exam}/start", headers=student_headers).status_code == 409


def test_exam_4b_invalid_answers(client, student_headers, started_exam, staff_headers):
    """EXAM-4: answers must be an option and belong to this exam."""
    page = client.get(f"/exams/{started_exam}/questions/0", headers=student_headers).json()
    r = client.post(f"/exams/{started_exam}/answers", json={"question_id": page["question"]["id"], "answer": "zzz"},
                    headers=student_headers)
    assert r.status_code == 422
    other = client.post("/exams", headers=staff_headers, json={
        "title": "Other", "is_active": True,
        "questions": [{"text": "q", "options": ["a", "b"], "correct_answer": "a"}]}).json()
    r = client.post(f"/exams/{started_exam}/answers",
                    json={"question_id": other["questions"][0]["id"], "answer": "a"}, headers=student_headers)
    assert r.status_code == 404


def test_inactive_exam_hidden_from_students(client, staff_headers, student_headers):
    exam = client.post("/exams", json={"title": "Hidden"}, headers=staff_headers).json()
    assert client.get(f"/exams/{exam['id']}", headers=student_headers).status_code == 404
    assert client.get("/exams/9999", headers=staff_headers).status_code == 404
    assert client.get(f"/exams/{exam['id']}/progress", headers=student_headers).status_code == 404


def test_progress_before_start(client, student_headers, exam_id):
    r = client.get(f"/exams/{exam_id}/progress", headers=student_headers).json()
    assert r["status"] == "not_started" and r["answered"] == 0
