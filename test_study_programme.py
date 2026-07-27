"""
Tests for the study programme: paper parsing, programme import, marking
aggregation, and the API flow from child through to marked work.

The unit tests need no database. The integration tests follow the existing
convention and skip unless DATABASE_URL is configured.
"""

from __future__ import annotations

import io
import json
import os
import re
import types
import zipfile
from datetime import datetime, timedelta
from typing import Any, List

import pytest

from my_revision_helper.file_processing import _docx_text_from_bytes, _xlsx_text_from_bytes
from my_revision_helper.services.marking_service import (
    QuestionMarkResult,
    _derive_strong_topics,
    _derive_weak_topics,
    _topic_totals,
    mark_per_question,
)
from my_revision_helper.services.paper_parser import (
    guess_title,
    parse_paper,
    split_answer_key,
    topic_from_session,
)
from my_revision_helper.services.plan_importer import (
    import_programme,
    parse_focus_topics,
    parse_score_log,
    parse_time_summary,
    parse_weekly_tracker,
)
from my_revision_helper.subjects import is_rotation_label, normalise_subject

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

WORKBOOK_TEXT = """Mathematics — Week 1 Workbook
Year 10 preparation • Number & Algebra foundations

How to use this workbook
Work each session in order. Mark your own work using the Answer Key at the back.

Session 1 — Indices (laws of powers)  · ~40 min
Key facts & formulae
aᵐ × aⁿ = aᵐ⁺ⁿ
Warm-up
1.  Simplify:  a³ × a⁴
2.  Simplify:  x⁷ ÷ x²
Standard
3.  Simplify:  3x² × 4x⁵
Exam-style
4.  Simplify fully:  (5x³y²)² ÷ (5x⁴y)  [3 marks]
Stretch
5.  Solve for n:  2ⁿ × 2³ = 2⁷

Session 2 — Expanding & factorising  · ~40 min
Warm-up
1.  Expand 3(x + 4)
Standard
2.  Factorise x² − 9

Answer Key — worked solutions
Mark in a different colour.
Session 1 — Indices
1.  a³⁺⁴ = a⁷
2.  x⁷⁻² = x⁵
3.  3 × 4 × x²⁺⁵ = 12x⁷
4.  25x⁶y⁴ ÷ 5x⁴y = 5x²y³
5.  2ⁿ⁺³ = 2⁷ → n = 4
Session 2 — Expanding & factorising
1.  3x + 12
2.  Difference of squares: (x − 3)(x + 3)
"""


def build_docx(paragraphs: List[str]) -> bytes:
    """Build a minimal .docx containing the given paragraphs."""
    body = "".join(
        f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def build_xlsx(sheets: dict[str, List[List[str]]]) -> bytes:
    """Build a minimal .xlsx with inline string cells."""
    shared: List[str] = []

    sheet_files = {}
    workbook_sheets = []
    rels = []

    for index, (name, rows) in enumerate(sheets.items(), start=1):
        row_xml = []
        for row in rows:
            cells = "".join(
                f'<c t="inlineStr"><is><t>{value}</t></is></c>' for value in row
            )
            row_xml.append(f"<row>{cells}</row>")
        sheet_files[f"xl/worksheets/sheet{index}.xml"] = (
            '<?xml version="1.0"?><worksheet><sheetData>'
            + "".join(row_xml)
            + "</sheetData></worksheet>"
        )
        workbook_sheets.append(
            f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>'
        )
        rels.append(
            f'<Relationship Id="rId{index}" Target="worksheets/sheet{index}.xml"/>'
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>" + "".join(workbook_sheets) + "</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships>' + "".join(rels) + "</Relationships>",
        )
        for path, content in sheet_files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Document extraction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_docx_extraction_reads_paragraphs():
    raw = build_docx(["Mathematics — Week 1", "Warm-up", "1. Simplify a³ × a⁴"])
    text = _docx_text_from_bytes(raw)

    assert "Mathematics — Week 1" in text
    assert "1. Simplify a³ × a⁴" in text


@pytest.mark.unit
def test_docx_extraction_returns_none_for_non_docx():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("something/else.xml", "<a/>")

    assert _docx_text_from_bytes(buffer.getvalue()) is None


@pytest.mark.unit
def test_xlsx_extraction_labels_each_sheet():
    raw = build_xlsx(
        {
            "Score Log": [["Subject", "Test", "Score %"], ["Maths", "Summer", "53"]],
            "Time Summary": [["Maths", "3", "150"]],
        }
    )
    text = _xlsx_text_from_bytes(raw)

    assert "--- Sheet: Score Log ---" in text
    assert "--- Sheet: Time Summary ---" in text
    assert "Maths | Summer | 53" in text


# ---------------------------------------------------------------------------
# Answer key splitting — the boundary that keeps solutions from students
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_split_answer_key_separates_solutions():
    questions, answers = split_answer_key(WORKBOOK_TEXT)

    assert answers is not None
    assert answers.startswith("Answer Key")
    # The last question stays on the student side.
    assert "2ⁿ × 2³ = 2⁷" in questions
    # No worked solution crosses over.
    assert "a³⁺⁴ = a⁷" not in questions
    assert "(x − 3)(x + 3)" not in questions


@pytest.mark.unit
def test_split_answer_key_ignores_passing_mentions():
    """
    "Mark your own work using the Answer Key at the back" appears in the
    instructions of every one of these workbooks. Splitting there would throw
    away the entire paper.
    """
    questions, answers = split_answer_key(WORKBOOK_TEXT)

    assert "Session 1 — Indices" in questions
    assert "Session 2 — Expanding" in questions
    assert answers.count("Session 1") == 1


@pytest.mark.unit
def test_split_answer_key_without_a_key():
    text = "Physics paper\n\n" + "1. Define velocity.\n" * 40
    questions, answers = split_answer_key(text)

    assert answers is None
    assert questions.startswith("Physics paper")


@pytest.mark.unit
@pytest.mark.parametrize(
    "heading",
    ["Answer Key", "Model Answers", "Mark scheme", "Worked solutions", "ANSWERS"],
)
def test_split_answer_key_recognises_common_headings(heading: str):
    text = "Paper title\n" + ("1. A question that is long enough to count.\n" * 20)
    text += f"\n{heading}\n1. The answer.\n"

    questions, answers = split_answer_key(text)

    assert answers is not None, f"failed to split on {heading!r}"
    assert "The answer." not in questions


# ---------------------------------------------------------------------------
# Question parsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_paper_extracts_questions_bands_and_answers():
    parsed = parse_paper(WORKBOOK_TEXT, subject="Mathematics")

    assert parsed.parse_status == "parsed"
    assert len(parsed.questions) == 7

    # Every question is paired with its answer, matched on session + number
    # even though numbering restarts in session 2.
    assert all(q.expected_answer for q in parsed.questions)

    first = parsed.questions[0]
    assert first.number == "1"
    assert first.band == "warm-up"
    assert "a⁷" in first.expected_answer

    # Session 2 question 1 must get session 2's answer, not session 1's.
    session_two = [q for q in parsed.questions if "Session 2" in (q.session_label or "")]
    assert len(session_two) == 2
    assert session_two[0].expected_answer == "3x + 12"


@pytest.mark.unit
def test_parse_paper_reads_printed_marks():
    parsed = parse_paper(WORKBOOK_TEXT, subject="Mathematics")
    exam_style = [q for q in parsed.questions if q.band == "exam-style"]

    assert exam_style[0].marks == 3


@pytest.mark.unit
def test_parse_paper_tags_every_question_with_a_topic():
    """Without topics there is nothing to build a retest from."""
    parsed = parse_paper(WORKBOOK_TEXT, subject="Mathematics")

    assert all(q.topic for q in parsed.questions)
    assert {q.topic for q in parsed.questions} == {"Indices", "Expanding & factorising"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "label,expected",
    [
        ("Session 1 — Indices (laws of powers)", "Indices"),
        ("Session 2 — Expanding & factorising  · ~40 min", "Expanding & factorising"),
        ("Session 3 — SPaG clinic: grammar", "SPaG clinic: grammar"),
        (None, None),
    ],
)
def test_topic_from_session(label, expected):
    assert topic_from_session(label) == expected


@pytest.mark.unit
def test_guess_title_uses_the_document_heading():
    assert guess_title(WORKBOOK_TEXT) == "Mathematics — Week 1 Workbook"


@pytest.mark.unit
def test_parse_paper_falls_back_when_ai_fails():
    """An AI error must degrade to the built-in parser, not lose the upload."""

    class ExplodingClient:
        def __init__(self):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("rate limited"))
                )
            )

    parsed = parse_paper(
        WORKBOOK_TEXT, subject="Mathematics", client=ExplodingClient(), model="gpt-4o"
    )

    assert parsed.parse_status == "parsed"
    assert len(parsed.questions) == 7


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Maths", "Mathematics"),
        ("maths", "Mathematics"),
        ("PRE", "PRE"),
        ("Religious Studies", "PRE"),
        ("Geog", "Geography"),
        ("Computing", "Computer Science"),
        ("Chemistry", "Chemistry"),
        ("Underwater Basketry", "Underwater Basketry"),
        ("", None),
        (None, None),
    ],
)
def test_normalise_subject(raw, expected):
    assert normalise_subject(raw) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "label,expected",
    [
        ("Humanities", True),
        ("Physics / Chem", True),
        ("History / Geography / PRE", True),
        ("Mathematics", False),
    ],
)
def test_is_rotation_label(label, expected):
    assert is_rotation_label(label) is expected


# ---------------------------------------------------------------------------
# Programme import from the tracker
# ---------------------------------------------------------------------------


TRACKER_TEXT = """--- Sheet: Weekly Tracker ---
Yuri — Weekly Study Tracker
Day | Block | Subject | Focus this session | Planned min
Mon | 1 | Maths | Index laws & expanding brackets | 50
Mon | 2 | Physics | Equations & definitions recall | 50
Tue | 1 | English | Language analysis | 50
Thu | 2 | Physics / Chem | Science catch-up | 50
Fri | 2 | Humanities | Rotate: History / Geog / PRE | 50

--- Sheet: Score Log ---
Subject | Test / date | Score % | Year avg % | Gap (pts) | Notes
Maths | Summer 2026 (non-calc) | 53 | 76 | -23 | Index laws, brackets, sequences
Maths | Summer 2026 (calc) | 55 | 70 | -15 | Volume & surface area, averages
English | Summer 2026 | 52 | 72 | -20 | Analysis depth, quotations, SPaG
Geography | Summer 2026 | 68 | n/a | 62

--- Sheet: Time Summary ---
Subject | Blocks / week | Minutes / week | Approx hours
Maths | 3 | 150 | 2.5
English | 2 | 100 | 1.67
History / Geography / PRE | 1 | 51 | 0.85
Total | 10 | 500 | 8.33
"""


@pytest.mark.unit
def test_parse_score_log_reads_scores_and_averages():
    rows = TRACKER_TEXT.split("--- Sheet: Score Log ---")[1].split("--- Sheet:")[0]
    entries = parse_score_log(rows.strip().split("\n"))

    assert len(entries) == 4
    maths = [e for e in entries if e.subject == "Mathematics"]
    assert len(maths) == 2
    assert maths[0].score_pct == 53
    assert maths[0].year_average_pct == 76
    # The header row is not mistaken for data.
    assert all(e.subject != "Subject" for e in entries)


@pytest.mark.unit
def test_parse_score_log_handles_missing_year_average():
    rows = TRACKER_TEXT.split("--- Sheet: Score Log ---")[1].split("--- Sheet:")[0]
    entries = parse_score_log(rows.strip().split("\n"))

    geography = [e for e in entries if e.subject == "Geography"][0]
    assert geography.score_pct == 68
    assert geography.year_average_pct is None


@pytest.mark.unit
def test_parse_weekly_tracker_reads_the_timetable():
    rows = TRACKER_TEXT.split("--- Sheet: Weekly Tracker ---")[1].split("--- Sheet:")[0]
    blocks = parse_weekly_tracker(rows.strip().split("\n"))

    assert len(blocks) == 5
    monday = [b for b in blocks if b.day_of_week == 0]
    assert {b.block_index for b in monday} == {1, 2}
    assert monday[0].subject == "Mathematics"
    assert monday[0].planned_minutes == 50
    # Rotation slots keep their printed label.
    assert any(b.subject == "Physics / Chem" for b in blocks)


@pytest.mark.unit
def test_parse_time_summary_splits_rotation_allowance():
    rows = TRACKER_TEXT.split("--- Sheet: Time Summary ---")[1]
    minutes, total = parse_time_summary(rows.strip().split("\n"))

    assert minutes["Mathematics"] == 150
    assert total == 500
    # 51 minutes shared between three rotating subjects.
    assert minutes["History"] == 17
    assert minutes["Geography"] == 17
    assert minutes["PRE"] == 17


@pytest.mark.unit
def test_import_programme_end_to_end():
    programme = import_programme(TRACKER_TEXT, "The idea in one line.  Close the exam gap.")

    assert programme.warnings == []
    assert len(programme.scores) == 4
    assert len(programme.blocks) == 5
    assert programme.weekly_minutes_target == 500
    assert programme.days_per_week == 4  # Mon, Tue, Thu, Fri appear
    assert programme.plan_summary == "Close the exam gap."


@pytest.mark.unit
def test_import_programme_warns_without_a_tracker():
    programme = import_programme(None, None)

    assert programme.scores == []
    assert any("No tracker" in w for w in programme.warnings)


@pytest.mark.unit
def test_parse_focus_topics_splits_notes():
    assert parse_focus_topics("Index laws, brackets and sequences") == [
        "Index laws",
        "brackets",
        "sequences",
    ]
    assert parse_focus_topics(None) == []


# ---------------------------------------------------------------------------
# Marking aggregation
# ---------------------------------------------------------------------------


def _mark(topic: str, awarded: float, available: float, verdict: str) -> QuestionMarkResult:
    return QuestionMarkResult(
        paper_question_id=None,
        order_index=1,
        question_number="1",
        question_text="q",
        expected_answer=None,
        student_answer=None,
        marks_awarded=awarded,
        marks_available=available,
        verdict=verdict,
        feedback=None,
        topic=topic,
    )


@pytest.mark.unit
def test_topic_totals_aggregates_by_topic():
    marks = [
        _mark("Indices", 1, 1, "correct"),
        _mark("Indices", 0, 2, "incorrect"),
        _mark("Ratio", 3, 3, "correct"),
        _mark(None, 1, 1, "correct"),  # untagged questions are ignored
    ]

    totals = _topic_totals(marks)
    assert totals["Indices"] == (1.0, 3.0)
    assert totals["Ratio"] == (3.0, 3.0)
    assert None not in totals


@pytest.mark.unit
def test_weak_and_strong_topics_are_separated_by_threshold():
    marks = [
        _mark("Indices", 1, 4, "partial"),  # 25% -> weak
        _mark("Ratio", 9, 10, "correct"),  # 90% -> secure
        _mark("Graphs", 7, 10, "partial"),  # 70% -> neither
    ]

    assert _derive_weak_topics(marks) == ["Indices"]
    assert _derive_strong_topics(marks) == ["Ratio"]


@pytest.mark.unit
def test_weak_topics_are_ordered_worst_first():
    marks = [
        _mark("Ratio", 5, 10, "partial"),  # 50%
        _mark("Indices", 1, 10, "partial"),  # 10%
        _mark("Graphs", 4, 10, "partial"),  # 40%
    ]

    assert _derive_weak_topics(marks) == ["Indices", "Graphs", "Ratio"]


class _StubMarker:
    """A model stub that awards a fixed verdict to every question."""

    def __init__(self, verdict: str, awarded: Any = None):
        self.verdict = verdict
        self.awarded = awarded
        self.calls = 0
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )

    def _create(self, model=None, messages=None, **kwargs):
        import re

        self.calls += 1
        numbers = re.findall(r"--- Question (\S+) ---", messages[-1]["content"])
        payload = {
            "marks": [
                {
                    "number": number,
                    "student_answer": "an answer",
                    "marks_awarded": self.awarded,
                    "verdict": self.verdict,
                    "feedback": "note",
                }
                for number in numbers
            ]
        }
        message = types.SimpleNamespace(content=json.dumps(payload))
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def _paper_questions(count: int, marks_each: int = 2):
    """Stand-ins for PaperQuestion rows."""
    return [
        types.SimpleNamespace(
            id=f"q{i}",
            order_index=i,
            number=str(i),
            question_text=f"Question {i}",
            marks=marks_each,
            topic="Indices",
            session_label="Session 1 — Indices",
            expected_answer="the answer",
            marking_notes=None,
        )
        for i in range(1, count + 1)
    ]


@pytest.mark.unit
def test_mark_per_question_totals_and_percentage():
    questions = _paper_questions(4, marks_each=2)
    stub = _StubMarker("correct", awarded=2)

    result = mark_per_question(
        questions, "my work", subject="Mathematics", client=stub, model="gpt-4o"
    )

    assert result.marks_available == 8
    assert result.marks_awarded == 8
    assert result.percentage == 100.0
    assert len(result.question_marks) == 4


@pytest.mark.unit
def test_mark_per_question_never_awards_more_than_available():
    questions = _paper_questions(2, marks_each=2)
    stub = _StubMarker("correct", awarded=99)

    result = mark_per_question(
        questions, "my work", subject="Mathematics", client=stub, model="gpt-4o"
    )

    assert result.marks_awarded == 4
    assert all(m.marks_awarded <= m.marks_available for m in result.question_marks)


@pytest.mark.unit
def test_mark_per_question_batches_large_papers():
    """A 60-question workbook must not be sent as a single request."""
    questions = _paper_questions(60)
    stub = _StubMarker("correct", awarded=2)

    result = mark_per_question(
        questions, "my work", subject="Mathematics", client=stub, model="gpt-4o"
    )

    assert stub.calls == 5  # 60 questions at 12 per batch
    assert len(result.question_marks) == 60


@pytest.mark.unit
def test_mark_per_question_survives_a_failed_batch():
    """
    One bad batch should cost only those questions, not the whole paper.
    """
    questions = _paper_questions(24)

    class FlakyMarker(_StubMarker):
        def _create(self, model=None, messages=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("500 from the API")
            return super()._create(model=model, messages=messages, **kwargs)

    stub = FlakyMarker("correct", awarded=2)
    result = mark_per_question(
        questions, "my work", subject="Mathematics", client=stub, model="gpt-4o"
    )

    assert len(result.question_marks) == 24
    not_attempted = [m for m in result.question_marks if m.verdict == "not_attempted"]
    assert len(not_attempted) == 12
    assert result.marks_awarded == 24  # the surviving batch still scored


@pytest.mark.unit
def test_not_attempted_questions_score_zero():
    questions = _paper_questions(3, marks_each=2)
    stub = _StubMarker("not_attempted", awarded=2)

    result = mark_per_question(
        questions, "blank page", subject="Mathematics", client=stub, model="gpt-4o"
    )

    assert result.marks_awarded == 0
    assert result.percentage == 0.0


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------


def _requires_db():
    from my_revision_helper.database import engine

    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - the study programme requires a database")
    if engine is None:
        pytest.skip("Database engine not configured")


@pytest.fixture
def client():
    """A test client with the schema created."""
    _requires_db()

    from fastapi.testclient import TestClient

    from my_revision_helper.api import app
    from my_revision_helper.database import init_db

    init_db()
    return TestClient(app)


@pytest.fixture
def child(client):
    """A child to hang test data off."""
    response = client.post(
        "/api/children", json={"name": "Test Child", "yearGroup": "Year 10"}
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.integration
def test_create_and_list_children(client):
    before = len(client.get("/api/children").json()["items"])

    created = client.post("/api/children", json={"name": "Alex", "colour": "cyan"})
    assert created.status_code == 201
    assert created.json()["name"] == "Alex"

    after = client.get("/api/children").json()["items"]
    assert len(after) == before + 1


@pytest.mark.integration
def test_child_requires_a_name(client):
    assert client.post("/api/children", json={"name": "   "}).status_code == 400


@pytest.mark.integration
def test_subject_baselines_report_the_gap(client, child):
    response = client.put(
        f"/api/children/{child}/subjects",
        json=[
            {"subject": "Mathematics", "baselineScore": 53, "yearAverage": 76, "priority": 5},
            {"subject": "Chemistry", "baselineScore": 65, "yearAverage": 77, "priority": 3},
        ],
    )
    assert response.status_code == 200

    subjects = response.json()
    # Worst gap first.
    assert [s["subject"] for s in subjects] == ["Mathematics", "Chemistry"]
    assert subjects[0]["gap"] == -23.0
    assert subjects[1]["gap"] == -12.0


@pytest.mark.integration
def test_replacing_subjects_deactivates_rather_than_deletes(client, child):
    client.put(
        f"/api/children/{child}/subjects",
        json=[{"subject": "Mathematics", "baselineScore": 53, "yearAverage": 76}],
    )
    client.put(
        f"/api/children/{child}/subjects",
        json=[{"subject": "Chemistry", "baselineScore": 65, "yearAverage": 77}],
    )

    subjects = client.get(f"/api/children/{child}/subjects").json()
    assert [s["subject"] for s in subjects] == ["Chemistry"]


@pytest.mark.integration
def test_upload_paper_hides_the_answer_key(client):
    """The single most important guarantee: students never receive answers."""
    response = client.post(
        "/api/papers",
        data={"subject": "Mathematics", "title": "Test Workbook", "weekLabel": "Week 1"},
        files={"files": ("wb.txt", WORKBOOK_TEXT.encode(), "text/plain")},
    )
    assert response.status_code == 201

    paper = response.json()
    assert paper["questionCount"] == 7
    assert paper["hasAnswerKey"] is True

    body = json.dumps(paper)
    assert "a³⁺⁴" not in body
    assert "expectedAnswer" not in body
    assert "answerKeyText" not in body

    detail = client.get(f"/api/papers/{paper['id']}?includeText=true").json()
    assert "a³⁺⁴" not in json.dumps(detail)
    assert "Answer Key — worked solutions" not in (detail["questionText"] or "")


@pytest.mark.integration
def test_upload_paper_requires_content(client):
    response = client.post("/api/papers", data={"subject": "Mathematics"})
    assert response.status_code == 400


@pytest.mark.integration
def test_assign_a_paper_and_read_the_todo_list(client, child):
    paper = client.post(
        "/api/papers",
        data={"subject": "Mathematics", "title": "Assignable"},
        files={"files": ("wb.txt", WORKBOOK_TEXT.encode(), "text/plain")},
    ).json()

    created = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Maths Week 1",
            "subject": "Mathematics",
            "assignmentType": "paper",
            "paperId": paper["id"],
            "dueDate": "2026-08-03",
        },
    )
    assert created.status_code == 201
    assert created.json()["questionCount"] == 7

    todo = client.get(f"/api/children/{child}/todo").json()
    assert any(item["id"] == created.json()["id"] for item in todo["items"])


@pytest.mark.integration
def test_paper_assignment_requires_a_paper_id(client, child):
    response = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Nothing attached",
            "subject": "Mathematics",
            "assignmentType": "paper",
        },
    )
    assert response.status_code == 400


@pytest.mark.integration
def test_task_can_be_self_reported_but_paper_cannot(client, child):
    task = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Read for two hours",
            "subject": "English",
            "assignmentType": "task",
            "verification": "self_report",
        },
    ).json()

    done = client.post(
        f"/api/assignments/{task['id']}/complete",
        json={"minutesSpent": 120, "note": "Finished chapter 3"},
    )
    assert done.status_code == 200
    assert done.json()["status"] == "done"

    paper = client.post(
        "/api/papers",
        data={"subject": "Mathematics", "title": "Not tickable"},
        files={"files": ("wb.txt", WORKBOOK_TEXT.encode(), "text/plain")},
    ).json()
    paper_assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Maths paper",
            "subject": "Mathematics",
            "assignmentType": "paper",
            "paperId": paper["id"],
        },
    ).json()

    # A paper must be handed in, not ticked off, or it would appear complete
    # with no score behind it.
    refused = client.post(
        f"/api/assignments/{paper_assignment['id']}/complete", json={"minutesSpent": 40}
    )
    assert refused.status_code == 400


@pytest.mark.integration
def test_bulk_assign_covers_every_child(client):
    first = client.post("/api/children", json={"name": "Bulk One"}).json()["id"]
    second = client.post("/api/children", json={"name": "Bulk Two"}).json()["id"]

    response = client.post(
        "/api/assignments/bulk",
        json={
            "childIds": [first, second],
            "assignments": [
                {
                    "childId": first,
                    "title": "Shared reading",
                    "subject": "English",
                    "assignmentType": "task",
                    "verification": "self_report",
                }
            ],
        },
    )
    assert response.status_code == 201
    assert response.json()["total"] == 2
    assert {item["childId"] for item in response.json()["items"]} == {first, second}


@pytest.mark.integration
def test_another_session_cannot_see_or_reach_the_data(client, child):
    """Ownership scoping is what keeps one family's data private."""
    from fastapi.testclient import TestClient

    from my_revision_helper.api import app

    other = TestClient(app)  # a fresh session cookie is a different owner

    assert other.get("/api/children").json()["items"] == []
    assert other.get(f"/api/children/{child}").status_code == 404
    assert other.get(f"/api/children/{child}/progress").status_code == 404
    assert other.get(f"/api/children/{child}/todo").status_code == 404
    assert (
        other.post(
            "/api/assignments",
            json={
                "childId": child,
                "title": "Sneaky",
                "subject": "Mathematics",
                "assignmentType": "task",
            },
        ).status_code
        == 404
    )


@pytest.mark.integration
def test_progress_endpoint_summarises_the_child(client, child):
    client.put(
        f"/api/children/{child}/subjects",
        json=[{"subject": "Mathematics", "baselineScore": 53, "yearAverage": 76}],
    )
    client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "A task",
            "subject": "Mathematics",
            "assignmentType": "task",
            "verification": "self_report",
        },
    )

    progress = client.get(f"/api/children/{child}/progress").json()

    assert progress["child"]["id"] == child
    assert progress["assignmentsTotal"] == 1
    assert progress["assignmentsDone"] == 0
    assert len(progress["subjects"]) == 1
    assert progress["subjects"][0]["baselineGap"] == -23.0


@pytest.mark.integration
def test_retest_refuses_when_nothing_is_known_to_be_weak(client, child):
    response = client.post(
        f"/api/children/{child}/retest", json={"subject": "Mathematics", "questionCount": 5}
    )
    assert response.status_code == 400


@pytest.mark.integration
def test_retest_falls_back_to_report_focus_topics(client, child):
    """
    On day one there are no markings yet, so the retest button should still
    work from the topics the school report flagged.
    """
    client.put(
        f"/api/children/{child}/subjects",
        json=[
            {
                "subject": "Mathematics",
                "baselineScore": 53,
                "yearAverage": 76,
                "focusTopics": ["index laws", "expanding brackets"],
            }
        ],
    )

    response = client.post(
        f"/api/children/{child}/retest", json={"subject": "Mathematics", "questionCount": 6}
    )
    assert response.status_code == 201
    assert response.json()["topics"] == ["index laws", "expanding brackets"]
    assert response.json()["revisionId"]


@pytest.mark.integration
def test_score_log_computes_the_gap(client, child):
    client.put(
        f"/api/children/{child}/subjects",
        json=[{"subject": "Mathematics", "baselineScore": 53, "yearAverage": 76}],
    )

    created = client.post(
        f"/api/children/{child}/score-log",
        json={"subject": "Mathematics", "label": "Mock 1", "scorePct": 61},
    )
    assert created.status_code == 201
    # Year average is filled in from the subject baseline.
    assert created.json()["yearAveragePct"] == 76.0
    assert created.json()["gap"] == -15.0


# ---------------------------------------------------------------------------
# The full loop: assign -> hand in -> mark -> mastery -> retest
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_marking(monkeypatch):
    """
    Route the marking endpoint at a stub model.

    Returns the stub so a test can vary the verdict, which is what decides
    whether a topic is recorded as weak.
    """
    holder = {}

    def install(verdict: str, awarded: Any):
        stub = _StubMarker(verdict, awarded=awarded)
        monkeypatch.setattr(
            "my_revision_helper.routers.submissions.get_openai_client", lambda: stub
        )
        monkeypatch.setattr(
            "my_revision_helper.routers.submissions.get_reasoning_model", lambda: "gpt-4o"
        )
        holder["stub"] = stub
        return stub

    return install


def _assign_workbook(client, child):
    """Upload the sample workbook and give it to the child."""
    paper = client.post(
        "/api/papers",
        data={"subject": "Mathematics", "title": "Week 1", "weekLabel": "Week 1"},
        files={"files": ("wb.txt", WORKBOOK_TEXT.encode(), "text/plain")},
    ).json()

    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Week 1 workbook",
            "subject": "Mathematics",
            "assignmentType": "paper",
            "paperId": paper["id"],
            "verification": "upload",
        },
    ).json()

    return paper, assignment


@pytest.mark.integration
def test_handing_in_work_produces_a_marking(client, child, stub_marking):
    stub_marking("correct", awarded=None)  # None => full marks for a correct verdict
    _, assignment = _assign_workbook(client, child)

    response = client.post(
        f"/api/assignments/{assignment['id']}/submit",
        data={"pastedText": "1. a^7\n2. 5x + 15\n"},
    )
    assert response.status_code == 201

    marking = response.json()
    assert marking["percentage"] == 100.0
    assert len(marking["questionMarks"]) == 7
    assert marking["marksAwarded"] == marking["marksAvailable"]

    # The assignment moves on by itself once it has been marked.
    after = client.get(f"/api/assignments/{assignment['id']}").json()
    assert after["status"] == "marked"


@pytest.mark.integration
def test_a_wrong_paper_feeds_mastery_and_then_a_retest(client, child, stub_marking):
    """
    The loop the whole app exists for: get it wrong, have that recorded as a
    weak topic, and be able to press the retest button on the strength of it.
    """
    stub_marking("incorrect", awarded=0)
    _, assignment = _assign_workbook(client, child)

    marking = client.post(
        f"/api/assignments/{assignment['id']}/submit",
        data={"pastedText": "no idea"},
    ).json()

    assert marking["percentage"] == 0.0
    assert marking["weakTopics"], "a paper scored at zero must yield weak topics"

    mastery = client.get(f"/api/children/{child}/mastery").json()
    assert mastery, "marking should have created topic mastery rows"
    assert all(row["masteryPct"] == 0.0 for row in mastery)
    assert all(row["status"] == "weak" for row in mastery)

    # The score log picks the result up, so it charts on the dashboard.
    scores = client.get(f"/api/children/{child}/score-log").json()
    assert any(entry["source"] == "marking" for entry in scores)

    retest = client.post(
        f"/api/children/{child}/retest",
        json={"markingId": marking["id"], "questionCount": 5},
    )
    assert retest.status_code == 201
    assert retest.json()["revisionId"]
    assert set(retest.json()["topics"]) & set(marking["weakTopics"])


@pytest.mark.integration
def test_marking_is_not_reachable_from_another_account(client, child, stub_marking):
    stub_marking("correct", awarded=None)
    _, assignment = _assign_workbook(client, child)

    marking = client.post(
        f"/api/assignments/{assignment['id']}/submit",
        data={"pastedText": "some work"},
    ).json()

    from fastapi.testclient import TestClient

    from my_revision_helper.api import app

    other = TestClient(app)
    other.cookies.set("session_id", "a-different-browser")

    assert other.get(f"/api/markings/{marking['id']}").status_code == 404
    assert len(other.get("/api/markings").json()["items"]) == 0


# ---------------------------------------------------------------------------
# The printable worksheet
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_normalise_resources_accepts_strings_and_dicts():
    from my_revision_helper.services.worksheet import normalise_resources

    links = normalise_resources(
        [
            "https://example.com/one",
            {"url": "https://example.com/two", "label": "Watch me", "kind": "watch"},
        ]
    )

    assert [l["url"] for l in links] == ["https://example.com/one", "https://example.com/two"]
    # A bare string still gets a usable label rather than an empty heading.
    assert links[0]["label"]
    assert links[1]["label"] == "Watch me"


@pytest.mark.unit
def test_normalise_resources_rejects_non_http_urls():
    """A link is rendered into a page, so javascript: and data: must not survive."""
    from my_revision_helper.services.worksheet import normalise_resources

    links = normalise_resources(
        [
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "  https://example.com/ok  ",
        ]
    )

    assert [l["url"] for l in links] == ["https://example.com/ok"]


@pytest.mark.unit
def test_merge_resources_puts_the_papers_links_first_and_dedupes():
    from my_revision_helper.services.worksheet import merge_resources

    merged = merge_resources(
        [{"url": "https://example.com/video", "label": "Paper link"}],
        [{"url": "https://example.com/extra", "label": "Assignment link"}],
        "https://example.com/video",  # legacy field repeating the paper's link
    )

    assert [l["url"] for l in merged] == [
        "https://example.com/video",
        "https://example.com/extra",
    ]
    assert merged[0]["label"] == "Paper link"


@pytest.mark.unit
def test_worksheet_escapes_question_text():
    from my_revision_helper.services.worksheet import render_worksheet

    question = types.SimpleNamespace(
        number="1",
        order_index=0,
        question_text="Solve <script>alert(1)</script> for x",
        marks=2,
        session_label=None,
    )

    html_doc = render_worksheet(
        title="Sheet", subject="Mathematics", questions=[question]
    )

    assert "<script>alert(1)</script>" not in html_doc
    assert "&lt;script&gt;" in html_doc


@pytest.mark.unit
def test_worksheet_gives_more_answer_space_to_bigger_questions():
    """A four-mark question needs room to work in; a one-mark question does not."""
    from my_revision_helper.services.worksheet import render_worksheet

    def height(marks):
        question = types.SimpleNamespace(
            number="1", order_index=0, question_text="Q", marks=marks, session_label=None
        )
        doc = render_worksheet(title="S", subject="Mathematics", questions=[question])
        return int(re.search(r"min-height:(\d+)mm", doc).group(1))

    assert height(1) < height(5)


@pytest.mark.integration
def test_worksheet_never_contains_the_answer_key(client, child):
    """
    The whole reason this endpoint exists. The uploaded document carries its
    answer key, so the worksheet is generated from the parsed questions instead.
    """
    paper, assignment = _assign_workbook(client, child)

    response = client.get(f"/api/assignments/{assignment['id']}/worksheet")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    body = response.text

    # Every stored expected answer must be absent.
    from my_revision_helper.database import SessionLocal
    from my_revision_helper.models_db import PaperQuestion

    db = SessionLocal()
    answers = [
        q.expected_answer
        for q in db.query(PaperQuestion).filter(PaperQuestion.paper_id == paper["id"]).all()
        if q.expected_answer and len(q.expected_answer.strip()) > 6
    ]
    db.close()

    assert answers, "the fixture workbook should have parsed answers to check against"
    for answer in answers:
        assert answer.strip() not in body

    assert "Answer Key" not in body
    # The questions themselves are present, so this is not passing by being empty.
    assert "Simplify" in body or "question" in body.lower()


@pytest.mark.integration
def test_worksheet_prints_the_papers_prerequisite_link(client, child):
    """A printed worksheet has to carry the link, or it is lost off-screen."""
    paper = client.post(
        "/api/papers",
        data={
            "subject": "Mathematics",
            "title": "With a video",
            "resourceUrl": "https://www.khanacademy.org/math/indices",
            "resourceLabel": "Watch this first",
        },
        files={"files": ("wb.txt", WORKBOOK_TEXT.encode(), "text/plain")},
    ).json()

    assert [l["url"] for l in paper["resources"]] == [
        "https://www.khanacademy.org/math/indices"
    ]

    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Indices",
            "subject": "Mathematics",
            "assignmentType": "paper",
            "paperId": paper["id"],
        },
    ).json()

    # The link is inherited by the assignment without being restated.
    assert [l["url"] for l in assignment["resources"]] == [
        "https://www.khanacademy.org/math/indices"
    ]

    body = client.get(f"/api/assignments/{assignment['id']}/worksheet").text

    # Readable URL for typing, and a QR code for scanning off paper.
    assert "khanacademy.org/math/indices" in body
    assert "Watch this first" in body
    assert "<svg" in body


@pytest.mark.integration
def test_worksheet_is_not_reachable_from_another_account(client, child):
    _, assignment = _assign_workbook(client, child)

    from fastapi.testclient import TestClient

    from my_revision_helper.api import app

    other = TestClient(app)
    other.cookies.set("session_id", "someone-else")

    assert other.get(f"/api/assignments/{assignment['id']}/worksheet").status_code == 404


@pytest.mark.integration
def test_paper_flags_whether_the_original_may_be_handed_over(client):
    """
    A workbook with a key inside it cannot be given to a student as-is; the
    library needs to say so rather than leaving the parent to guess.
    """
    with_key = client.post(
        "/api/papers",
        data={"subject": "Mathematics", "title": "Has a key"},
        files={"files": ("wb.txt", WORKBOOK_TEXT.encode(), "text/plain")},
    ).json()
    assert with_key["hasAnswerKey"] is True
    assert with_key["originalIsStudentSafe"] is False

    without_key = client.post(
        "/api/papers",
        data={"subject": "Mathematics", "title": "No key"},
        files={"files": ("plain.txt", b"1. What is 2 + 2?\n2. What is 3 + 3?", "text/plain")},
    ).json()
    assert without_key["hasAnswerKey"] is False
    assert without_key["originalIsStudentSafe"] is True


@pytest.mark.integration
def test_overdue_work_is_counted_separately(client, child):
    client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Late one",
            "subject": "Mathematics",
            "assignmentType": "task",
            "verification": "self_report",
            "dueDate": (datetime.now() - timedelta(days=3)).date().isoformat(),
        },
    )
    client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Due today, not late yet",
            "subject": "Mathematics",
            "assignmentType": "task",
            "verification": "self_report",
            "dueDate": datetime.now().date().isoformat(),
        },
    )

    progress = client.get(f"/api/children/{child}/progress").json()
    assert progress["assignmentsOverdue"] == 1


@pytest.mark.integration
def test_deleting_a_child_takes_their_whole_history_with_them(
    client, child, stub_marking, monkeypatch
):
    """
    A child who has been marked has score log and mastery rows pointing at
    them, and those are held by foreign keys the ORM cascade does not cover.
    Deleting has to clear them or the database refuses.
    """
    stub_marking("incorrect", awarded=0)
    _, assignment = _assign_workbook(client, child)
    client.post(f"/api/assignments/{assignment['id']}/submit", data={"pastedText": "no idea"})

    assert client.get(f"/api/children/{child}/score-log").json()
    assert client.get(f"/api/children/{child}/mastery").json()

    # Deletion is refused for anonymous callers, so sign in for this one.
    from my_revision_helper.auth import get_current_user_optional
    from my_revision_helper.api import app

    app.dependency_overrides[get_current_user_optional] = lambda: {
        "user_id": "auth0|deleter",
        "email": "deleter@example.com",
        "name": "Deleter",
    }
    try:
        owned = client.post("/api/children", json={"name": "Doomed"}).json()["id"]
        paper = client.post(
            "/api/papers",
            data={"subject": "Mathematics", "title": "Doomed paper"},
            files={"files": ("wb.txt", WORKBOOK_TEXT.encode(), "text/plain")},
        ).json()
        doomed_assignment = client.post(
            "/api/assignments",
            json={
                "childId": owned,
                "title": "Doomed work",
                "subject": "Mathematics",
                "assignmentType": "paper",
                "paperId": paper["id"],
            },
        ).json()
        client.post(
            f"/api/assignments/{doomed_assignment['id']}/submit",
            data={"pastedText": "no idea"},
        )
        assert client.get(f"/api/children/{owned}/score-log").json()

        assert client.delete(f"/api/children/{owned}").status_code == 200
        assert client.get(f"/api/children/{owned}").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user_optional, None)


@pytest.mark.integration
def test_parent_can_override_a_question_mark(client, child, stub_marking):
    """Marking is AI-assisted, not AI-decided — the parent has the last word."""
    stub_marking("incorrect", awarded=0)
    _, assignment = _assign_workbook(client, child)

    marking = client.post(
        f"/api/assignments/{assignment['id']}/submit",
        data={"pastedText": "borderline working"},
    ).json()

    first = marking["questionMarks"][0]
    available = first["marksAvailable"]

    response = client.patch(
        f"/api/markings/{marking['id']}/questions/{first['id']}",
        json={"marksAwarded": available, "verdict": "correct", "feedback": "Accepted on appeal"},
    )
    assert response.status_code == 200

    updated = response.json()
    assert updated["marksAwarded"] > 0
    # The overall total is recomputed, not left stale.
    assert updated["percentage"] > 0
