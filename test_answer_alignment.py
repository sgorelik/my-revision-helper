"""
Tests for matching numbered answers to the questions they belong to.

Covers both places the questions can come from: earlier pages of the same scan,
and a library paper the hand-in is linked to.
"""

import os
from unittest.mock import patch

import pytest

from my_revision_helper.services.answer_alignment import (
    extract_numbered_answers,
    format_answer_map,
    partition_scan,
    prepare_work_for_marking,
    questions_text_for_library,
)


# Question pages, then a separate numbered answer sheet — the shape that used
# to come back as 0% or "could not read".
SEPARATE_SHEET_SCAN = """--- Page 1 ---
Mathematics — Fractions and percentages
1. Work out 3/4 of 60.
Answer: ......................... (2)
2. Increase £80 by 15%.
Answer: ......................... (2)
3. Write 0.375 as a fraction in its simplest form.
Answer: ......................... (3)

--- Page 2 ---
Answers
[written] 1. 45
[written] 2. 92
[written] 3. 3/8
"""

ANSWERS_ONLY = """Answers
[written] 1) 45
[written] 2) £92
[written] 3) 3/8
"""

SAME_PAGE = """1. Work out 3/4 of 60.
Answer: [written] 45  ......................... (2)
2. Increase £80 by 15%.
Answer: [written] 92  ......................... (2)
"""


@pytest.mark.unit
class TestExtractingNumberedAnswers:
    def test_handwritten_list(self):
        answers = extract_numbered_answers(ANSWERS_ONLY)
        assert [(a.number, a.text) for a in answers] == [
            ("1", "45"),
            ("2", "£92"),
            ("3", "3/8"),
        ]

    def test_typed_list_without_tags(self):
        answers = extract_numbered_answers("1. 45\n2. 92\n3. 3/8\n")
        assert [a.number for a in answers] == ["1", "2", "3"]

    def test_skips_empty_and_no_answer(self):
        text = "[written] 1. 45\n[written] 2. [no answer]\n[written] 3. ......\n"
        answers = extract_numbered_answers(text)
        assert [a.number for a in answers] == ["1"]


@pytest.mark.unit
class TestPartitioningAScan:
    def test_question_pages_come_apart_from_the_answer_sheet(self):
        parts = partition_scan(SEPARATE_SHEET_SCAN)

        assert "Work out 3/4 of 60." in parts.questions
        assert "3/8" not in parts.questions
        assert parts.has_separate_answers
        assert [a.number for a in parts.numbered] == ["1", "2", "3"]
        assert parts.numbered[0].text == "45"

    def test_an_answer_only_sheet_has_no_questions(self):
        parts = partition_scan(ANSWERS_ONLY)

        assert parts.questions == ""
        assert len(parts.numbered) == 3
        assert parts.has_separate_answers

    def test_a_same_page_worksheet_stays_together(self):
        parts = partition_scan(SAME_PAGE)

        assert "Work out 3/4 of 60." in parts.questions
        # Same-page work is not split into a separate answer sheet; the marker
        # still sees the answers next to their questions in the transcript.
        assert not parts.has_separate_answers or parts.questions == parts.answers

    def test_library_copy_uses_the_question_pages_alone(self):
        parts = partition_scan(SEPARATE_SHEET_SCAN)
        library = questions_text_for_library(parts, SEPARATE_SHEET_SCAN)

        assert "Work out 3/4 of 60." in library
        assert "[written] 1. 45" not in library


@pytest.mark.unit
class TestPreparingWorkForMarking:
    def test_puts_the_answer_map_first(self):
        text, parts = prepare_work_for_marking(SEPARATE_SHEET_SCAN)

        assert "=== ANSWERS BY NUMBER ===" in text
        assert "1. 45" in text
        assert "2. 92" in text
        assert parts.has_separate_answers

    def test_format_is_readable(self):
        answers = extract_numbered_answers(ANSWERS_ONLY)
        mapped = format_answer_map(answers)
        assert "Prefer this map" in mapped
        assert "3. 3/8" in mapped


# ---------------------------------------------------------------------------
# API: linking a library paper, and scanning question+answer pages together
# ---------------------------------------------------------------------------


def _requires_db():
    from my_revision_helper.database import engine

    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    if engine is None:
        pytest.skip("Database engine not configured")


@pytest.fixture
def client():
    _requires_db()
    from fastapi.testclient import TestClient
    from my_revision_helper.api import app
    from my_revision_helper.database import init_db

    init_db()
    return TestClient(app)


@pytest.fixture
def child(client):
    response = client.post("/api/children", json={"name": "Align Child", "yearGroup": "Year 8"})
    assert response.status_code == 201
    return response.json()["id"]


def _upload_paper(client, *, title="Fractions worksheet"):
    """A blank library paper with three numbered questions."""
    content = (
        "Mathematics — Fractions and percentages\n"
        "1. Work out 3/4 of 60.\nAnswer: ......................... (2)\n"
        "2. Increase £80 by 15%.\nAnswer: ......................... (2)\n"
        "3. Write 0.375 as a fraction in its simplest form.\n"
        "Answer: ......................... (3)\n"
    )
    response = client.post(
        "/api/papers",
        data={"subject": "Mathematics", "title": title, "paperType": "worksheet"},
        files=[("files", ("fractions.txt", content, "text/plain"))],
    )
    assert response.status_code == 201, response.text
    return response.json()


def _fake_marking(questions, student_work, **kwargs):
    """Award full marks whenever the answer map is present — proves alignment ran."""
    from my_revision_helper.services.marking_service import MarkingResult, QuestionMarkResult

    assert "=== ANSWERS BY NUMBER ===" in student_work
    marks = []
    total = 0.0
    for q in questions:
        available = float(q.marks or 1)
        total += available
        marks.append(
            QuestionMarkResult(
                paper_question_id=q.id,
                order_index=q.order_index,
                question_number=q.number or str(q.order_index),
                question_text=q.question_text,
                expected_answer=q.expected_answer,
                student_answer="matched",
                marks_awarded=available,
                marks_available=available,
                verdict="correct",
                feedback="ok",
                topic=q.topic,
            )
        )
    return MarkingResult(
        marks_awarded=total,
        marks_available=total,
        percentage=100.0,
        overall_feedback="All matched.",
        question_marks=marks,
        model="test",
    )


@pytest.mark.integration
class TestLinkingAnAnswerSheetToALibraryPaper:
    def test_numbered_answers_are_marked_against_the_linked_paper(self, client, child):
        paper = _upload_paper(client)

        with patch(
            "my_revision_helper.routers.handins.mark_per_question",
            side_effect=_fake_marking,
        ), patch(
            "my_revision_helper.routers.handins.get_openai_client",
            return_value=object(),
        ):
            response = client.post(
                "/api/handins",
                data={
                    "childId": child,
                    "subject": "Mathematics",
                    "paperId": paper["id"],
                    "saveToLibrary": "false",
                },
                files=[("files", ("answers.txt", ANSWERS_ONLY, "text/plain"))],
            )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["paperId"] == paper["id"]
        assert body["savedToLibrary"] is False
        assert body["questionCount"] >= 1
        assert body["marking"]["percentage"] == 100.0
        assert body["marking"]["status"] == "marked"

    def test_an_unknown_paper_is_refused(self, client, child):
        response = client.post(
            "/api/handins",
            data={
                "childId": child,
                "subject": "Mathematics",
                "paperId": "does-not-exist",
                "marksAwarded": "2",
                "marksAvailable": "3",
            },
        )
        assert response.status_code == 404


@pytest.mark.integration
class TestQuestionsEarlierInTheSameScan:
    def test_question_pages_plus_answer_sheet_become_a_library_paper(self, client, child):
        """The library copy comes from the question pages, not the answer list."""
        response = client.post(
            "/api/handins",
            data={
                "childId": child,
                "subject": "Mathematics",
                "title": "Fractions (separate answers)",
                "marksAwarded": "6",
                "marksAvailable": "7",
                "saveToLibrary": "true",
            },
            files=[("files", ("workbook.txt", SEPARATE_SHEET_SCAN, "text/plain"))],
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["savedToLibrary"] is True
        assert body["questionCount"] >= 2

        paper = client.get(f"/api/papers/{body['paperId']}?includeText=true").json()
        text = (paper.get("questionText") or "") + (paper.get("fullText") or "")
        assert "Work out 3/4 of 60." in text
        assert "3/8" not in text  # child's answer must not sit in the library copy

    def test_an_answer_sheet_alone_is_not_forced_into_the_average(self, client, child):
        """
        Without a linked paper there is nowhere to match the numbers, so the
        work waits for a person rather than landing as a guessed zero.
        """
        with patch(
            "my_revision_helper.routers.handins.get_openai_client",
            return_value=object(),
        ):
            response = client.post(
                "/api/handins",
                data={
                    "childId": child,
                    "subject": "Mathematics",
                    "title": "Answers only",
                    "saveToLibrary": "true",
                },
                files=[("files", ("answers.txt", ANSWERS_ONLY, "text/plain"))],
            )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["savedToLibrary"] is False
        assert body["marking"]["status"] == "needs_review"
        assert body["marking"]["percentage"] is None
