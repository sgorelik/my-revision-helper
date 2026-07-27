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


def _one_page_jpeg() -> bytes:
    """A tiny real JPEG, so page handling is exercised on actual image bytes."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (60, 80), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def _stub_async(result):
    """Replace an awaited call with a fixed result."""

    async def _stub(*args, **kwargs):
        return result

    return _stub


def _simple_marking_result():
    """A marking outcome with no per-question detail, for submission plumbing."""
    from my_revision_helper.services.marking_service import MarkingResult

    return MarkingResult(
        marks_awarded=3.0,
        marks_available=3.0,
        percentage=100.0,
        overall_feedback="Good work.",
        strengths=[],
        weaknesses=[],
        weak_topics=[],
        question_marks=[],
        model="test",
    )


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
# Keeping the pages, not just the words
# ---------------------------------------------------------------------------


class _FakeQuestion:
    def __init__(self, number, text, expected=None, marks=1):
        self.number = number
        self.question_text = text
        self.expected_answer = expected
        self.marks = marks
        self.session_label = None
        self.marking_notes = None


@pytest.mark.unit
def test_a_question_answered_by_drawing_is_recognised():
    """
    "Draw a fully-labelled pie chart" is three marks for a drawing. No
    transcription of it is good enough to mark, so it has to be spotted.
    """
    from my_revision_helper.services.marking_service import needs_the_page

    assert needs_the_page(_FakeQuestion("7b", "Draw a fully-labelled pie chart below."))
    assert needs_the_page(_FakeQuestion("3", "Plot the points on the grid."))
    assert needs_the_page(_FakeQuestion("5", "Sketch the graph of y = 2x + 1."))
    assert needs_the_page(_FakeQuestion("9", "Complete the table of values."))

    assert not needs_the_page(_FakeQuestion("1", "Work out 32 ÷ 4."))
    assert not needs_the_page(_FakeQuestion("2", "Explain why the answer is 15."))


@pytest.mark.unit
def test_pages_are_attached_only_for_drawing_questions():
    """Each attached page costs a Vision input, so they are not sent every time."""
    from unittest.mock import MagicMock

    from my_revision_helper.services.marking_service import _mark_batch

    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content='{"marks": [{"number": "1", "marks_awarded": 1, '
                    '"verdict": "correct", "feedback": "Yes"}]}'
                )
            )
        ]
    )
    pages = [b"\xff\xd8fake jpeg one", b"\xff\xd8fake jpeg two"]

    # Arithmetic only: the transcript is enough.
    _mark_batch(client, "gpt-4o", [_FakeQuestion("1", "Work out 6 × 7.")], "6 × 7 = 42", "Maths", pages)
    content = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert isinstance(content, str)

    # A drawing: the pages go with it.
    _mark_batch(
        client,
        "gpt-4o",
        [_FakeQuestion("7b", "Draw a fully-labelled pie chart.", marks=3)],
        "[FIGURE: drawn by student — pie chart]",
        "Maths",
        pages,
    )
    content = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert isinstance(content, list)
    assert sum(1 for part in content if part["type"] == "image_url") == 2
    assert "7b" in content[0]["text"]


@pytest.mark.unit
def test_marking_still_works_when_there_are_no_pages():
    """Typed answers have no pages, and a drawing question must not break."""
    from unittest.mock import MagicMock

    from my_revision_helper.services.marking_service import _mark_batch

    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"marks": []}'))]
    )

    _mark_batch(client, "gpt-4o", [_FakeQuestion("7b", "Draw a pie chart.")], "work", "Maths", None)

    content = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert isinstance(content, str)


@pytest.mark.unit
def test_only_a_handful_of_pages_go_in_one_call():
    from unittest.mock import MagicMock

    from my_revision_helper.services.marking_service import MAX_PAGES_PER_BATCH, _mark_batch

    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"marks": []}'))]
    )

    _mark_batch(
        client,
        "gpt-4o",
        [_FakeQuestion("7b", "Draw a pie chart.")],
        "work",
        "Maths",
        [b"page"] * 20,
    )

    content = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    images = [part for part in content if part["type"] == "image_url"]
    assert len(images) == MAX_PAGES_PER_BATCH


@pytest.mark.unit
def test_a_photo_is_already_a_page():
    from my_revision_helper.services.page_images import render_pages

    assert render_pages(b"jpeg bytes", "work.jpg") == [b"jpeg bytes"]
    # Nothing to show for a document with no pages to render.
    assert render_pages(b"whatever", "notes.txt") == []


@pytest.mark.integration
def test_pages_of_handed_in_work_can_be_fetched_back(client, child, monkeypatch):
    """The child has to be able to see the chart they drew, not a description."""
    import my_revision_helper.routers.submissions as subs

    paper = client.post(
        "/api/papers",
        data={"subject": "Mathematics", "title": "Pie charts"},
        files={"files": ("wb.txt", WORKBOOK_TEXT.encode(), "text/plain")},
    ).json()
    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Pie charts",
            "subject": "Mathematics",
            "assignmentType": "paper",
            "paperId": paper["id"],
        },
    ).json()

    page_one = _one_page_jpeg()

    monkeypatch.setattr(subs, "get_openai_client", lambda: object())
    monkeypatch.setattr(subs, "get_reasoning_model", lambda: "gpt-4o")
    monkeypatch.setattr(
        subs, "process_uploaded_files", _stub_async({"work.jpg": "[FIGURE: pie chart]"})
    )
    monkeypatch.setattr(
        subs,
        "mark_per_question",
        lambda *a, **k: _simple_marking_result(),
    )

    marking = client.post(
        f"/api/assignments/{assignment['id']}/submit",
        files={"files": ("work.jpg", page_one, "image/jpeg")},
    ).json()

    assert len(marking["pageImageIds"]) == 1

    page_id = marking["pageImageIds"][0]
    got = client.get(f"/api/submissions/{marking['submissionId']}/files/{page_id}")
    assert got.status_code == 200
    assert got.content == page_one


@pytest.mark.integration
def test_pages_of_work_are_not_readable_by_another_account(client, child, monkeypatch):
    import my_revision_helper.routers.submissions as subs

    paper = client.post(
        "/api/papers",
        data={"subject": "Mathematics"},
        files={"files": ("wb.txt", WORKBOOK_TEXT.encode(), "text/plain")},
    ).json()
    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Pie charts",
            "subject": "Mathematics",
            "assignmentType": "paper",
            "paperId": paper["id"],
        },
    ).json()

    monkeypatch.setattr(subs, "get_openai_client", lambda: object())
    monkeypatch.setattr(subs, "get_reasoning_model", lambda: "gpt-4o")
    monkeypatch.setattr(subs, "process_uploaded_files", _stub_async({"work.jpg": "answers"}))
    monkeypatch.setattr(subs, "mark_per_question", lambda *a, **k: _simple_marking_result())

    marking = client.post(
        f"/api/assignments/{assignment['id']}/submit",
        files={"files": ("work.jpg", _one_page_jpeg(), "image/jpeg")},
    ).json()

    from fastapi.testclient import TestClient

    from my_revision_helper.api import app

    other = TestClient(app)
    other.cookies.set("session_id", "not-mine")

    page_id = marking["pageImageIds"][0]
    assert (
        other.get(f"/api/submissions/{marking['submissionId']}/files/{page_id}").status_code == 404
    )


# ---------------------------------------------------------------------------
# Timing a sitting
# ---------------------------------------------------------------------------


class _FakeAssignment:
    """Just the timer fields, to test the arithmetic without a database."""

    def __init__(self):
        self.id = "fake"
        self.status = "todo"
        self.timer_state = "idle"
        self.timer_started_at = None
        self.timer_accumulated_seconds = 0
        self.timer_pause_count = 0
        self.timer_first_started_at = None
        self.timer_stopped_at = None


@pytest.mark.unit
def test_paused_time_does_not_count_towards_the_total():
    from my_revision_helper.services import timing

    a = _FakeAssignment()
    t0 = datetime(2026, 7, 27, 10, 0, 0)

    timing.start(a, now=t0)
    # Ten minutes of work.
    timing.pause(a, now=t0 + timedelta(minutes=10))
    # An hour away from the desk, which must not be counted.
    timing.resume(a, now=t0 + timedelta(minutes=70))
    # Five more minutes of work.
    timing.stop(a, now=t0 + timedelta(minutes=75))

    assert timing.elapsed_seconds(a) == 15 * 60
    assert timing.logged_minutes(a) == 15
    assert a.timer_pause_count == 1


@pytest.mark.unit
def test_elapsed_time_keeps_growing_while_running():
    """
    The total is derived, not stored, so a client that was closed mid-paper sees
    the right time when it comes back rather than a frozen number.
    """
    from my_revision_helper.services import timing

    a = _FakeAssignment()
    t0 = datetime(2026, 7, 27, 10, 0, 0)

    timing.start(a, now=t0)

    assert timing.elapsed_seconds(a, now=t0 + timedelta(minutes=3)) == 180
    assert timing.elapsed_seconds(a, now=t0 + timedelta(minutes=25)) == 1500
    # Nothing was written down in the meantime.
    assert a.timer_accumulated_seconds == 0


@pytest.mark.unit
def test_each_pause_is_counted_but_double_tapping_is_not():
    from my_revision_helper.services import timing

    a = _FakeAssignment()
    t0 = datetime(2026, 7, 27, 10, 0, 0)
    timing.start(a, now=t0)

    for i in range(3):
        timing.pause(a, now=t0 + timedelta(minutes=10 * i + 5))
        # A second tap on pause, or another tab doing the same, is not a pause.
        timing.pause(a, now=t0 + timedelta(minutes=10 * i + 6))
        timing.resume(a, now=t0 + timedelta(minutes=10 * i + 10))

    assert a.timer_pause_count == 3


@pytest.mark.unit
def test_restarting_a_running_timer_does_not_lose_time():
    """A double tap on start must not reset the clock back to zero."""
    from my_revision_helper.services import timing

    a = _FakeAssignment()
    t0 = datetime(2026, 7, 27, 10, 0, 0)

    timing.start(a, now=t0)
    timing.start(a, now=t0 + timedelta(minutes=5))

    assert timing.elapsed_seconds(a, now=t0 + timedelta(minutes=6)) == 6 * 60


@pytest.mark.unit
def test_finishing_while_paused_is_allowed():
    from my_revision_helper.services import timing

    a = _FakeAssignment()
    t0 = datetime(2026, 7, 27, 10, 0, 0)

    timing.start(a, now=t0)
    timing.pause(a, now=t0 + timedelta(minutes=8))
    timing.stop(a, now=t0 + timedelta(minutes=30))

    # Only the eight worked minutes count, not the wait before finishing.
    assert timing.logged_minutes(a) == 8


@pytest.mark.unit
def test_a_forgotten_timer_cannot_distort_the_weekly_total():
    from my_revision_helper.services import timing

    a = _FakeAssignment()
    t0 = datetime(2026, 7, 27, 10, 0, 0)

    timing.start(a, now=t0)
    # Left running overnight.
    timing.stop(a, now=t0 + timedelta(hours=20))

    assert timing.logged_minutes(a) == timing.MAX_LOGGED_MINUTES
    # The raw measurement is still there to be looked at.
    assert timing.elapsed_seconds(a) == 20 * 3600


@pytest.mark.unit
def test_untimed_work_reports_no_minutes():
    from my_revision_helper.services import timing

    assert timing.logged_minutes(_FakeAssignment()) is None


@pytest.mark.unit
def test_a_few_seconds_of_work_rounds_to_a_minute_not_zero():
    from my_revision_helper.services import timing

    a = _FakeAssignment()
    t0 = datetime(2026, 7, 27, 10, 0, 0)
    timing.start(a, now=t0)
    timing.stop(a, now=t0 + timedelta(seconds=20))

    assert timing.logged_minutes(a) == 1


@pytest.mark.unit
def test_actions_that_do_not_apply_are_refused():
    from my_revision_helper.services import timing

    a = _FakeAssignment()

    with pytest.raises(timing.TimerError):
        timing.pause(a)  # Never started
    with pytest.raises(timing.TimerError):
        timing.resume(a)  # Not paused
    with pytest.raises(timing.TimerError):
        timing.stop(a)  # Never started

    t0 = datetime(2026, 7, 27, 10, 0, 0)
    timing.start(a, now=t0)
    timing.stop(a, now=t0 + timedelta(minutes=5))

    with pytest.raises(timing.TimerError):
        timing.start(a)  # Already finished

    # Resetting clears the way for another attempt.
    timing.reset(a)
    timing.start(a, now=t0 + timedelta(hours=1))
    assert a.timer_state == "running"
    assert a.timer_pause_count == 0


@pytest.mark.integration
def test_starting_the_clock_marks_the_work_as_in_progress(client, child):
    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Read chapter 3",
            "subject": "English",
            "assignmentType": "task",
        },
    ).json()
    assert assignment["timer"]["state"] == "idle"
    assert assignment["status"] == "todo"

    started = client.post(f"/api/assignments/{assignment['id']}/timer/start").json()

    assert started["timer"]["state"] == "running"
    assert started["timer"]["startedAt"]
    assert started["status"] == "in_progress"


@pytest.mark.integration
def test_the_clock_survives_being_reloaded(client, child):
    """
    The point of keeping time on the server: a child reloads the page, locks the
    iPad, or moves device mid-paper, and the elapsed time is still right.
    """
    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Maths",
            "subject": "Mathematics",
            "assignmentType": "task",
        },
    ).json()

    client.post(f"/api/assignments/{assignment['id']}/timer/start")

    # Pretend four minutes passed, by moving the stored start back.
    from my_revision_helper.database import SessionLocal
    from my_revision_helper.models_db import Assignment as AssignmentRow

    db = SessionLocal()
    row = db.query(AssignmentRow).filter(AssignmentRow.id == assignment["id"]).first()
    row.timer_started_at = row.timer_started_at - timedelta(minutes=4)
    db.commit()
    db.close()

    # A completely fresh read, as a reloaded page would do.
    reloaded = client.get(f"/api/assignments/{assignment['id']}").json()

    assert reloaded["timer"]["state"] == "running"
    assert 235 <= reloaded["timer"]["elapsedSeconds"] <= 245
    assert reloaded["timer"]["loggedMinutes"] == 4


@pytest.mark.integration
def test_pausing_and_resuming_over_the_api_counts_the_pause(client, child):
    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Maths",
            "subject": "Mathematics",
            "assignmentType": "task",
        },
    ).json()

    client.post(f"/api/assignments/{assignment['id']}/timer/start")
    paused = client.post(f"/api/assignments/{assignment['id']}/timer/pause").json()

    assert paused["timer"]["state"] == "paused"
    assert paused["timer"]["pauseCount"] == 1

    # While paused the clock does not move.
    first = client.get(f"/api/assignments/{assignment['id']}").json()["timer"]["elapsedSeconds"]
    second = client.get(f"/api/assignments/{assignment['id']}").json()["timer"]["elapsedSeconds"]
    assert first == second

    resumed = client.post(f"/api/assignments/{assignment['id']}/timer/resume").json()
    assert resumed["timer"]["state"] == "running"
    # Resuming is not another pause.
    assert resumed["timer"]["pauseCount"] == 1

    finished = client.post(f"/api/assignments/{assignment['id']}/timer/stop").json()
    assert finished["timer"]["state"] == "stopped"
    assert finished["timer"]["stoppedAt"]


@pytest.mark.integration
def test_an_action_that_no_longer_applies_gets_a_clear_refusal(client, child):
    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Maths",
            "subject": "Mathematics",
            "assignmentType": "task",
        },
    ).json()

    response = client.post(f"/api/assignments/{assignment['id']}/timer/pause")
    assert response.status_code == 409
    assert "not running" in response.json()["detail"].lower()

    assert client.post(f"/api/assignments/{assignment['id']}/timer/sprint").status_code == 400


@pytest.mark.integration
def test_completing_a_task_records_the_measured_time_not_the_typed_one(client, child):
    """The whole point: nobody has to estimate how long it took."""
    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Read for an hour",
            "subject": "English",
            "assignmentType": "task",
        },
    ).json()

    client.post(f"/api/assignments/{assignment['id']}/timer/start")
    client.post(f"/api/assignments/{assignment['id']}/timer/pause")
    client.post(f"/api/assignments/{assignment['id']}/timer/resume")

    from my_revision_helper.database import SessionLocal
    from my_revision_helper.models_db import Assignment as AssignmentRow
    from my_revision_helper.models_db import Submission as SubmissionRow

    db = SessionLocal()
    row = db.query(AssignmentRow).filter(AssignmentRow.id == assignment["id"]).first()
    row.timer_accumulated_seconds = 22 * 60
    db.commit()
    db.close()

    # A wildly wrong self-report, which should be ignored in favour of the clock.
    done = client.post(
        f"/api/assignments/{assignment['id']}/complete", json={"minutesSpent": 300}
    ).json()

    assert done["status"] == "done"
    # Finishing the work also finishes the clock.
    assert done["timer"]["state"] == "stopped"

    db = SessionLocal()
    submission = (
        db.query(SubmissionRow).filter(SubmissionRow.assignment_id == assignment["id"]).first()
    )
    assert submission.minutes_spent == 22
    assert submission.timed is True
    assert submission.pause_count == 1
    db.close()


@pytest.mark.integration
def test_a_typed_time_is_still_accepted_when_the_clock_was_never_used(client, child):
    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Read for an hour",
            "subject": "English",
            "assignmentType": "task",
        },
    ).json()

    client.post(f"/api/assignments/{assignment['id']}/complete", json={"minutesSpent": 45})

    from my_revision_helper.database import SessionLocal
    from my_revision_helper.models_db import Submission as SubmissionRow

    db = SessionLocal()
    submission = (
        db.query(SubmissionRow).filter(SubmissionRow.assignment_id == assignment["id"]).first()
    )
    assert submission.minutes_spent == 45
    assert submission.timed is False
    db.close()


@pytest.mark.integration
def test_timed_minutes_reach_the_weekly_totals(client, child):
    """Measured time has to land where self-reported time used to."""
    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Read for an hour",
            "subject": "English",
            "assignmentType": "task",
        },
    ).json()

    client.post(f"/api/assignments/{assignment['id']}/timer/start")

    from my_revision_helper.database import SessionLocal
    from my_revision_helper.models_db import Assignment as AssignmentRow

    db = SessionLocal()
    row = db.query(AssignmentRow).filter(AssignmentRow.id == assignment["id"]).first()
    row.timer_accumulated_seconds = 35 * 60
    row.timer_state = "paused"
    row.timer_started_at = None
    db.commit()
    db.close()

    client.post(f"/api/assignments/{assignment['id']}/complete", json={})

    progress = client.get(f"/api/children/{child}/progress").json()
    assert progress["minutesLoggedThisWeek"] == 35


@pytest.mark.integration
def test_someone_elses_timer_cannot_be_touched(client, child):
    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Maths",
            "subject": "Mathematics",
            "assignmentType": "task",
        },
    ).json()

    from fastapi.testclient import TestClient

    from my_revision_helper.api import app

    other = TestClient(app)
    other.cookies.set("session_id", "not-mine")

    assert other.post(f"/api/assignments/{assignment['id']}/timer/start").status_code == 404


# ---------------------------------------------------------------------------
# Links the documents already contain
# ---------------------------------------------------------------------------


def _docx_with_hyperlinks(links, body_text="Session 1 — Indices"):
    """
    Build a minimal .docx whose links are stored the way Word really stores them.

    Deliberately puts the URLs *only* in the relationship file, never in the
    document text, because that is what a real workbook does and it is what makes
    text-scraping useless.
    """
    rels = ['<?xml version="1.0" encoding="UTF-8"?>', "<Relationships>"]
    body = [f"<w:p><w:r><w:t>{body_text}</w:t></w:r></w:p>"]

    for index, (url, anchor) in enumerate(links, start=1):
        rel_id = f"rId{index}"
        rels.append(
            f'<Relationship Id="{rel_id}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            f'Target="{url}" TargetMode="External"/>'
        )
        body.append(f'<w:hyperlink r:id="{rel_id}"><w:r><w:t>{anchor}</w:t></w:r></w:hyperlink>')

    rels.append("</Relationships>")

    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<w:body>{"".join(body)}</w:body></w:document>'
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", "".join(rels))
    return buffer.getvalue()


@pytest.mark.unit
def test_docx_links_come_from_the_relationship_file_not_the_text():
    """
    The whole reason this exists: a Word hyperlink's address is not in the
    visible text, so scanning extracted text finds nothing in a real workbook.
    """
    from my_revision_helper.file_processing import _docx_text_from_bytes
    from my_revision_helper.services.link_extraction import extract_links, links_from_text

    content = _docx_with_hyperlinks(
        [
            (
                "https://www.khanacademy.org/math/algebra/exponents",
                "Khan Academy: Exponent properties",
            )
        ]
    )

    # Confirm the premise before relying on it.
    assert "khanacademy" not in _docx_text_from_bytes(content)
    assert links_from_text(_docx_text_from_bytes(content)) == []

    links = extract_links({"Maths_Week1_Workbook.docx": content})
    assert [l["url"] for l in links] == ["https://www.khanacademy.org/math/algebra/exponents"]
    # The anchor text becomes the label, which is why it is worth the trouble.
    assert links[0]["label"] == "Khan Academy: Exponent properties"


@pytest.mark.unit
def test_repeated_and_unlabelled_links_are_tidied_up():
    from my_revision_helper.services.link_extraction import extract_links

    content = _docx_with_hyperlinks(
        [
            ("https://www.bbc.co.uk/bitesize/subjects/z3kw2hv", "BBC Bitesize: English"),
            # The same link again, as in the real English workbook.
            ("https://www.bbc.co.uk/bitesize/subjects/z3kw2hv", "BBC Bitesize"),
            # Anchor text that is just the URL is no more useful than the URL.
            ("https://www.khanacademy.org/humanities/grammar", "https://www.khanacademy.org/humanities/grammar"),
        ]
    )

    links = extract_links({"English_Week1_Workbook.docx": content})

    assert len(links) == 2
    assert links[0]["label"] == "BBC Bitesize: English"
    assert links[1]["label"] == "Khan Academy"


@pytest.mark.unit
def test_link_kind_is_guessed_from_the_destination():
    from my_revision_helper.services.link_extraction import kind_for_url

    assert kind_for_url("https://www.youtube.com/watch?v=abc") == "watch"
    assert kind_for_url("https://www.bbc.co.uk/bitesize/guides/z1/revision/1") == "read"
    assert kind_for_url("https://quizlet.com/set/123") == "practise"


@pytest.mark.unit
def test_plain_text_urls_are_found_and_trimmed():
    from my_revision_helper.services.link_extraction import extract_links

    links = extract_links(
        text="Watch https://www.khanacademy.org/math/algebra. Then read (https://example.com/notes)."
    )

    assert [l["url"] for l in links] == [
        "https://www.khanacademy.org/math/algebra",
        "https://example.com/notes",
    ]


@pytest.mark.unit
def test_non_hyperlink_relationships_are_ignored():
    """An externally referenced image is not reading material."""
    from my_revision_helper.services.link_extraction import links_from_docx

    document = (
        '<?xml version="1.0"?><w:document '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Nothing here</w:t></w:r></w:p></w:body></w:document>"
    )
    rels = (
        '<?xml version="1.0"?><Relationships>'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="https://example.com/logo.png" TargetMode="External"/>'
        "</Relationships>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", rels)

    assert links_from_docx(buffer.getvalue()) == []


@pytest.mark.unit
def test_a_document_that_is_not_a_docx_is_not_an_error():
    from my_revision_helper.services.link_extraction import links_from_docx

    assert links_from_docx(b"just some bytes") == []


# ---------------------------------------------------------------------------
# Reading metadata off filenames
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_subject_is_read_from_the_real_workbook_filenames():
    """The files actually being uploaded are named after their subject."""
    from my_revision_helper.subjects import subject_from_filename

    assert subject_from_filename("Chemistry_Week1_Workbook.docx") == "Chemistry"
    assert subject_from_filename("Maths_Week1_Workbook.docx") == "Mathematics"
    assert subject_from_filename("Biology_Week1_Workbook.docx") == "Biology"
    # A more specific subject wins over the one-word match.
    assert subject_from_filename("english lit week 3 paper.pdf") == "English Literature"


@pytest.mark.unit
def test_subject_inference_declines_rather_than_guessing_wrong():
    """
    Matching on substrings would make short aliases catch almost anything, so a
    filename with no subject in it has to return nothing.
    """
    from my_revision_helper.subjects import subject_from_filename

    assert subject_from_filename("scan001.jpg") is None
    assert subject_from_filename("Yuri_Study_Tracker.xlsx") is None
    # "chem" must not match inside "Chemical".
    assert subject_from_filename("Chemical_reactions_notes.docx") is None
    assert subject_from_filename(None) is None


@pytest.mark.unit
def test_week_label_is_normalised_from_the_filename():
    from my_revision_helper.subjects import week_from_filename

    assert week_from_filename("Maths_Week1_Workbook.docx") == "Week 1"
    assert week_from_filename("2024 CS Paper wk4.pdf") == "Week 4"
    assert week_from_filename("english lit week 12.pdf") == "Week 12"
    assert week_from_filename("no numbers here.docx") is None


# ---------------------------------------------------------------------------
# Dates as the household sees them
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_local_date_follows_the_household_not_the_server():
    """
    Railway runs in UTC. During BST that is an hour behind, so work finished at
    half past midnight would otherwise be filed under the previous day.
    """
    from my_revision_helper.clock import to_local_date

    # 23:30 UTC on 27 July is 00:30 on 28 July in London.
    assert to_local_date(datetime(2026, 7, 27, 23, 30)) == datetime(2026, 7, 28).date()
    # In winter the two agree.
    assert to_local_date(datetime(2026, 1, 27, 23, 30)) == datetime(2026, 1, 27).date()
    assert to_local_date(None) is None


@pytest.mark.unit
def test_week_starts_on_monday_in_both_frames():
    from my_revision_helper.clock import week_bounds, week_bounds_utc

    # A Wednesday.
    start, end = week_bounds(datetime(2026, 7, 29, 14, 0))
    assert start == datetime(2026, 7, 27)
    assert end == datetime(2026, 8, 3)

    # The same week as UTC instants: London midnight in summer is 23:00 UTC the
    # day before, so timestamps compare correctly.
    utc_start, utc_end = week_bounds_utc(datetime(2026, 7, 29, 14, 0))
    assert utc_start == datetime(2026, 7, 26, 23, 0)
    assert utc_end == datetime(2026, 8, 2, 23, 0)


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
def test_uploading_a_workbook_picks_up_its_own_links(client, child):
    """A workbook that already names its videos should not need them retyped."""
    content = _docx_with_hyperlinks(
        [
            ("https://www.khanacademy.org/math/algebra/exponents", "Khan Academy: Exponents"),
            ("https://www.bbc.co.uk/bitesize/subjects/z3kw2hv", "BBC Bitesize: Maths"),
        ]
    )

    paper = client.post(
        "/api/papers",
        data={"subject": "Mathematics", "title": "Week 1"},
        files={
            "files": (
                "Maths_Week1_Workbook.docx",
                content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    ).json()

    assert [l["label"] for l in paper["resources"]] == [
        "Khan Academy: Exponents",
        "BBC Bitesize: Maths",
    ]

    # And they reach the student's worksheet without further work.
    assignment = client.post(
        "/api/assignments",
        json={
            "childId": child,
            "title": "Week 1",
            "subject": "Mathematics",
            "assignmentType": "paper",
            "paperId": paper["id"],
        },
    ).json()

    body = client.get(f"/api/assignments/{assignment['id']}/worksheet").text
    assert "khanacademy.org/math/algebra/exponents" in body
    assert "Khan Academy: Exponents" in body


@pytest.mark.integration
def test_extracted_links_come_before_ones_added_by_hand(client):
    content = _docx_with_hyperlinks(
        [("https://www.khanacademy.org/math/algebra/exponents", "Khan Academy: Exponents")]
    )

    paper = client.post(
        "/api/papers",
        data={
            "subject": "Mathematics",
            "resourceUrl": "https://example.com/my-own-note",
            "resourceLabel": "Read my note",
        },
        files={"files": ("Maths_Week1.docx", content, "text/plain")},
    ).json()

    assert [l["label"] for l in paper["resources"]] == [
        "Khan Academy: Exponents",
        "Read my note",
    ]


@pytest.mark.integration
def test_scanning_an_existing_paper_adds_links_without_losing_manual_ones(client):
    """
    Papers uploaded before extraction existed need a way to catch up, and it must
    not discard links a parent curated in the meantime.
    """
    content = _docx_with_hyperlinks(
        [("https://www.khanacademy.org/math/algebra/exponents", "Khan Academy: Exponents")]
    )

    paper = client.post(
        "/api/papers",
        data={"subject": "Mathematics"},
        files={"files": ("Maths_Week1.docx", content, "text/plain")},
    ).json()

    # Simulate the pre-extraction state: only a hand-added link.
    updated = client.patch(
        f"/api/papers/{paper['id']}",
        json={"resources": [{"url": "https://example.com/mine", "label": "Mine", "kind": "read"}]},
    ).json()
    assert [l["url"] for l in updated["resources"]] == ["https://example.com/mine"]

    scanned = client.post(f"/api/papers/{paper['id']}/extract-links").json()

    # The document's link is found and put first; the manual one survives.
    assert [l["label"] for l in scanned["resources"]] == ["Khan Academy: Exponents", "Mine"]

    # Scanning again is idempotent rather than duplicating.
    again = client.post(f"/api/papers/{paper['id']}/extract-links").json()
    assert len(again["resources"]) == 2


@pytest.mark.integration
def test_link_scan_is_not_reachable_from_another_account(client):
    paper = client.post(
        "/api/papers",
        data={"subject": "Mathematics"},
        files={"files": ("wb.txt", WORKBOOK_TEXT.encode(), "text/plain")},
    ).json()

    from fastapi.testclient import TestClient

    from my_revision_helper.api import app

    other = TestClient(app)
    other.cookies.set("session_id", "not-mine")

    assert other.post(f"/api/papers/{paper['id']}/extract-links").status_code == 404


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
def test_bulk_upload_makes_one_paper_per_file_and_infers_the_subject(client):
    """Setting up a term is uploading a folder, not filling in a form five times."""
    files = [
        ("files", ("Maths_Week1_Workbook.txt", WORKBOOK_TEXT.encode(), "text/plain")),
        ("files", ("Chemistry_Week1_Workbook.txt", b"1. Name the products.", "text/plain")),
        ("files", ("Biology_Week2_Workbook.txt", b"1. Define osmosis.", "text/plain")),
    ]

    response = client.post("/api/papers/bulk", files=files)
    assert response.status_code == 200

    body = response.json()
    assert body["succeeded"] == 3
    assert body["failed"] == 0

    by_name = {item["filename"]: item for item in body["items"]}
    assert by_name["Maths_Week1_Workbook.txt"]["paper"]["subject"] == "Mathematics"
    assert by_name["Chemistry_Week1_Workbook.txt"]["paper"]["subject"] == "Chemistry"
    assert by_name["Biology_Week2_Workbook.txt"]["paper"]["subject"] == "Biology"

    # The week comes off the filename too.
    assert by_name["Maths_Week1_Workbook.txt"]["paper"]["weekLabel"] == "Week 1"
    assert by_name["Biology_Week2_Workbook.txt"]["paper"]["weekLabel"] == "Week 2"

    # Each is its own library item, not one merged paper.
    titles = {item["paper"]["id"] for item in body["items"]}
    assert len(titles) == 3


@pytest.mark.integration
def test_one_unreadable_file_does_not_lose_the_others(client):
    """
    The acceptance criterion for bulk upload: a single failure neither blocks the
    others nor loses them.
    """
    files = [
        ("files", ("Maths_Week1.txt", WORKBOOK_TEXT.encode(), "text/plain")),
        # Nothing extractable, so this one cannot become a paper.
        ("files", ("Physics_Week1.zip", b"PK\x03\x04 not really a zip", "application/zip")),
        ("files", ("Biology_Week1.txt", b"1. Define osmosis.", "text/plain")),
    ]

    body = client.post("/api/papers/bulk", files=files).json()

    assert body["succeeded"] == 2
    assert body["failed"] == 1

    by_name = {item["filename"]: item for item in body["items"]}
    assert by_name["Physics_Week1.zip"]["status"] == "failed"
    assert by_name["Physics_Week1.zip"]["error"]
    # The good ones survived and were committed.
    assert by_name["Maths_Week1.txt"]["status"] == "ok"
    assert by_name["Biology_Week1.txt"]["status"] == "ok"

    library = client.get("/api/papers").json()
    stored = {p["title"] for p in library["items"]}
    assert by_name["Maths_Week1.txt"]["paper"]["title"] in stored


@pytest.mark.integration
def test_bulk_upload_reports_files_whose_subject_cannot_be_guessed(client):
    body = client.post(
        "/api/papers/bulk",
        files=[("files", ("scan001.txt", b"1. Something.", "text/plain"))],
    ).json()

    assert body["failed"] == 1
    assert "subject" in body["items"][0]["error"].lower()


@pytest.mark.integration
def test_bulk_upload_accepts_per_file_subject_and_link(client):
    """The per-file override is how a parent fixes a failed guess and retries."""
    meta = json.dumps(
        {
            "scan001.txt": {
                "subject": "Maths",
                "title": "Scanned homework",
                "resourceUrl": "https://www.khanacademy.org/math/fractions",
                "resourceLabel": "Watch: fractions",
            }
        }
    )

    body = client.post(
        "/api/papers/bulk",
        data={"meta": meta},
        files=[("files", ("scan001.txt", b"1. Add the fractions.", "text/plain"))],
    ).json()

    assert body["succeeded"] == 1
    paper = body["items"][0]["paper"]
    # The alias was normalised on the way in.
    assert paper["subject"] == "Mathematics"
    assert paper["title"] == "Scanned homework"
    assert paper["resources"][0]["url"] == "https://www.khanacademy.org/math/fractions"


def _task(client, child, title, **kwargs):
    """A self-reported task, which needs no paper or marking."""
    payload = {
        "childId": child,
        "title": title,
        "subject": "Mathematics",
        "assignmentType": "task",
        "verification": "self_report",
    }
    payload.update(kwargs)
    return client.post("/api/assignments", json=payload).json()


@pytest.mark.integration
def test_today_separates_todays_work_from_what_slipped(client, child):
    today = datetime.now().date()

    _task(client, child, "For today", scheduledDate=today.isoformat())
    _task(client, child, "Slipped", scheduledDate=(today - timedelta(days=2)).isoformat())
    _task(client, child, "Later this week", scheduledDate=(today + timedelta(days=3)).isoformat())

    body = client.get(f"/api/children/{child}/today").json()

    assert body["date"] == today.isoformat()
    assert [a["title"] for a in body["dueToday"]] == ["For today"]
    assert [a["title"] for a in body["overdue"]] == ["Slipped"]
    assert [a["title"] for a in body["upcoming"]] == ["Later this week"]


@pytest.mark.integration
def test_work_scheduled_for_a_day_is_not_late_before_its_deadline(client, child):
    """
    The planned day and the deadline are different things: work set for Monday
    and due Friday is not late on Tuesday, it is just not done yet.
    """
    today = datetime.now().date()

    _task(
        client,
        child,
        "Start Monday, hand in Friday",
        scheduledDate=(today - timedelta(days=1)).isoformat(),
        dueDate=(today + timedelta(days=4)).isoformat(),
    )

    body = client.get(f"/api/children/{child}/today").json()
    assert body["overdue"] == []

    progress = client.get(f"/api/children/{child}/progress").json()
    assert progress["assignmentsOverdue"] == 0


@pytest.mark.integration
def test_work_with_only_a_due_date_still_appears_on_its_day(client, child):
    """Assignments created before scheduling existed must not vanish from the day view."""
    today = datetime.now().date()
    _task(client, child, "Due today, never scheduled", dueDate=today.isoformat())

    body = client.get(f"/api/children/{child}/today").json()
    assert [a["title"] for a in body["dueToday"]] == ["Due today, never scheduled"]


@pytest.mark.integration
def test_undated_work_is_upcoming_rather_than_due_now(client, child):
    _task(client, child, "Someday")

    body = client.get(f"/api/children/{child}/today").json()
    assert body["dueToday"] == []
    assert body["overdue"] == []
    assert [a["title"] for a in body["upcoming"]] == ["Someday"]


@pytest.mark.integration
def test_scheduling_can_be_changed_and_cleared(client, child):
    today = datetime.now().date()
    assignment = _task(client, child, "Movable", scheduledDate=today.isoformat())
    assert assignment["plannedOn"] == today.isoformat()

    moved = client.patch(
        f"/api/assignments/{assignment['id']}",
        json={"scheduledDate": (today + timedelta(days=1)).isoformat()},
    ).json()
    assert moved["plannedOn"] == (today + timedelta(days=1)).isoformat()

    cleared = client.patch(
        f"/api/assignments/{assignment['id']}", json={"scheduledDate": ""}
    ).json()
    assert cleared["scheduledDate"] is None
    assert cleared["plannedOn"] is None


@pytest.mark.integration
def test_assigning_a_paper_to_both_kids_schedules_it_for_both(client, child):
    """Handing out a week's work is one action, and the day has to survive it."""
    second = client.post("/api/children", json={"name": "Second Child"}).json()["id"]
    paper, _ = _assign_workbook(client, child)
    today = datetime.now().date()

    response = client.post(
        "/api/assignments/bulk",
        json={
            "childIds": [child, second],
            "assignments": [
                {
                    "childId": child,
                    "title": "Week 1 workbook",
                    "subject": "Mathematics",
                    "assignmentType": "paper",
                    "paperId": paper["id"],
                    "scheduledDate": today.isoformat(),
                }
            ],
        },
    )
    assert response.status_code == 201

    created = response.json()["items"]
    assert len(created) == 2
    assert all(a["plannedOn"] == today.isoformat() for a in created)

    for kid in (child, second):
        titles = [a["title"] for a in client.get(f"/api/children/{kid}/today").json()["dueToday"]]
        assert "Week 1 workbook" in titles


@pytest.mark.integration
def test_today_is_not_reachable_from_another_account(client, child):
    from fastapi.testclient import TestClient

    from my_revision_helper.api import app

    other = TestClient(app)
    other.cookies.set("session_id", "someone-else-entirely")

    assert other.get(f"/api/children/{child}/today").status_code == 404


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
