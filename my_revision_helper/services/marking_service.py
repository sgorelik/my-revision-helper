"""
Mark a child's completed paper against the paper's own answer key.

The student hands in a photo, scan or typed copy of their work. We already know
the questions and the expected answers, so marking is a matching problem: find
each answer in the submitted work, compare it with the key, award marks and say
what was missing.

Two modes:

- Per question, when the paper was parsed successfully. This is what produces
  topic-level weakness data, and therefore what makes the retest button useful.
- Holistic, when the paper has no parsed questions. Produces an overall score
  and written feedback only.

Questions are marked in batches so that a 60-question workbook does not have to
fit in one response, and so a single malformed batch cannot lose the whole paper.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from ..llm import chat_completion
from ..models_db import (
    Marking,
    Paper,
    PaperQuestion,
    QuestionMark,
    ScoreLogEntry,
    Submission,
    TopicMastery,
)

logger = logging.getLogger(__name__)

# How many questions to mark per model call.
BATCH_SIZE = 12

# A topic counts as weak below this percentage.
WEAK_TOPIC_THRESHOLD = 60.0
SECURE_TOPIC_THRESHOLD = 80.0

VERDICTS = {"correct", "partial", "incorrect", "not_attempted"}


MARKING_SYSTEM_PROMPT = """You are an experienced GCSE examiner marking a student's completed work.

You are given a list of QUESTIONS, each with the marks available and the expected answer
from the official answer key, plus the STUDENT'S WORK as submitted (which may be OCR'd
from a photo and therefore imperfect).

For each question return a JSON object. Respond with:
{"marks": [
  {
    "number": "the question number you were given",
    "student_answer": "what the student wrote for this question, verbatim, or null if absent",
    "marks_awarded": 2,
    "verdict": "correct" | "partial" | "incorrect" | "not_attempted",
    "feedback": "one or two sentences addressed to the student"
  }
]}

Marking rules:
- Award marks for correct METHOD even when the final answer is wrong. This matters:
  the student loses marks for thin working, so credit the working that is there.
- "correct" = full marks. "partial" = some but not all. "incorrect" = no marks but
  an attempt was made. "not_attempted" = you cannot find any answer to this question.
- Never award more than the marks available.
- Accept answers that are equivalent to the key but differently worded or formatted
  (2.5 and 5/2, "increases because the outer electron is further away" and the key's
  phrasing). Do not require a word-for-word match.
- Be tolerant of OCR noise and of spelling in the working. Only penalise spelling and
  grammar where the question is explicitly assessing written accuracy.
- For extended written answers, judge against what the key says a full-mark response
  needs, and say specifically what was missing.
- When a question is answered by a drawing (a pie chart, graph, bar chart, plotted
  points, a construction) and you are shown the page, mark the drawing itself. Working
  out the right angles and then drawing them wrong is one of the commonest ways to lose
  these marks, so correct arithmetic beside the diagram is NOT evidence that the diagram
  is right. Read the drawing, compare it with the key, and say in student_answer what
  you actually saw in it.
- feedback must be usable: name what to fix, not just "incorrect". Never simply restate
  the correct answer without explaining the step the student missed.
- Return exactly one entry per question given, using the same "number" values.
- Return only the JSON object."""


HOLISTIC_SYSTEM_PROMPT = """You are an experienced GCSE examiner reviewing a student's completed work.

There is no per-question answer key available, so give an overall assessment.

Respond with JSON:
{
  "percentage": 0-100,
  "overall_feedback": "markdown feedback addressed to the student",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "weak_topics": ["specific topic names to practise"]
}

Rules:
- Judge against the standard expected for the subject and year group given.
- overall_feedback should open with what went well, then what to fix, in markdown.
- weak_topics must be specific enough to build a practice test from
  ('balancing equations', not 'chemistry').
- Return only the JSON object."""


@dataclass
class QuestionMarkResult:
    """Marking outcome for one question."""

    paper_question_id: Optional[str]
    order_index: int
    question_number: str
    question_text: str
    expected_answer: Optional[str]
    student_answer: Optional[str]
    marks_awarded: float
    marks_available: float
    verdict: str
    feedback: Optional[str]
    topic: Optional[str]


@dataclass
class MarkingResult:
    """The full outcome of marking a submission."""

    marks_awarded: float
    marks_available: float
    percentage: Optional[float]
    overall_feedback: Optional[str]
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    weak_topics: List[str] = field(default_factory=list)
    question_marks: List[QuestionMarkResult] = field(default_factory=list)
    model: Optional[str] = None


def _extract_json(content: str) -> Optional[Dict[str, Any]]:
    """Pull a JSON object out of a model response, tolerating code fences."""
    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _describe_questions(questions: Sequence[PaperQuestion]) -> str:
    """Render a batch of questions with their answer key for the prompt."""
    lines: List[str] = []
    for question in questions:
        lines.append(f"--- Question {question.number} ---")
        if question.session_label:
            lines.append(f"Section: {question.session_label}")
        lines.append(f"Marks available: {question.marks or 1}")
        lines.append(f"Question: {question.question_text}")
        if question.expected_answer:
            lines.append(f"Expected answer (from the key): {question.expected_answer}")
        else:
            lines.append("Expected answer: not supplied — use your own subject knowledge.")
        if question.marking_notes:
            lines.append(f"Full marks requires: {question.marking_notes}")
        lines.append("")
    return "\n".join(lines)


# Questions whose answer is a drawing rather than a sentence. For these the
# transcript is not enough to mark from and the pages themselves are attached.
DRAWING_WORDS = (
    "draw",
    "sketch",
    "plot",
    "graph",
    "chart",
    "diagram",
    "shade",
    "label the",
    "construct",
    "complete the table",
    "on the grid",
    "on the axes",
)

# Attaching a page costs a Vision input, so a batch sends a handful at most.
MAX_PAGES_PER_BATCH = 6


def needs_the_page(question: PaperQuestion) -> bool:
    """
    Whether this question can only be marked by looking at the work.

    "Draw a fully-labelled pie chart" is three marks for a drawing: no
    transcription of it is good enough to mark against, so the page is sent.
    """
    text = f"{question.question_text or ''} {question.expected_answer or ''}".lower()
    return any(word in text for word in DRAWING_WORDS)


def _image_parts(pages: Sequence[bytes]) -> List[Dict[str, Any]]:
    """Page images as Vision content parts."""
    parts: List[Dict[str, Any]] = []
    for image in pages[:MAX_PAGES_PER_BATCH]:
        encoded = base64.b64encode(image).decode("utf-8")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
            }
        )
    return parts


def _mark_batch(
    client: Any,
    model: str,
    questions: Sequence[PaperQuestion],
    student_work: str,
    subject: str,
    pages: Optional[Sequence[bytes]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Mark one batch of questions. Returns question number -> result payload.

    When the batch contains a question answered by drawing, the pages of the
    work are attached so the drawing can be marked as a drawing rather than
    from a description of it.

    Raises on API failure so the caller can decide how to degrade.
    """
    user_content = (
        f"SUBJECT: {subject}\n\n"
        f"=== QUESTIONS TO MARK ===\n{_describe_questions(questions)}\n"
        f"=== STUDENT'S WORK ===\n{student_work}"
    )

    drawing_questions = [q for q in questions if needs_the_page(q)]
    attach = list(pages or []) if drawing_questions else []

    if attach:
        numbers = ", ".join(str(q.number) for q in drawing_questions)
        user_content += (
            f"\n\n=== THE PAGES THEMSELVES ===\n"
            f"Question(s) {numbers} are answered by a drawing. Images of the student's "
            f"pages follow.\n"
            f"Mark those questions from the drawing in the images, not from the "
            f"transcription above and not from the student's calculations.\n"
            f"Look at the drawing and judge it: are the sectors, bars, points or lines "
            f"the sizes and positions the key requires, and is every part labelled? "
            f"Estimate the angles or read the values off the scale and compare them "
            f"with the key. A student who calculates correctly and then draws it wrong "
            f"gets the calculation marks, not the drawing marks — check the two agree "
            f"before awarding full marks.\n"
            f"In student_answer, describe what the drawing actually shows, including "
            f"the sizes you read off it."
        )
        message: Any = [{"type": "text", "text": user_content}] + _image_parts(attach)
        logger.info(f"Marking questions {numbers} with {len(attach[:MAX_PAGES_PER_BATCH])} page image(s)")
    else:
        message = user_content

    response = chat_completion(
        client,
        model=model,
        messages=[
            {"role": "system", "content": MARKING_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=8000,
    )

    data = _extract_json(response.choices[0].message.content or "")
    if not data or not isinstance(data.get("marks"), list):
        raise ValueError("Marking response did not contain a 'marks' list")

    results: Dict[str, Dict[str, Any]] = {}
    for item in data["marks"]:
        if isinstance(item, dict) and item.get("number") is not None:
            results[str(item["number"]).strip()] = item
    return results


def _coerce_marks(value: Any, available: float) -> float:
    """Clamp an awarded-marks value into [0, available]."""
    try:
        marks = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(available, marks))


def mark_per_question(
    questions: Sequence[PaperQuestion],
    student_work: str,
    *,
    subject: str,
    client: Any,
    model: str,
    pages: Optional[Sequence[bytes]] = None,
) -> MarkingResult:
    """
    Mark a parsed paper question by question.

    `pages` are images of the handed-in work, used for questions answered by
    drawing, where the transcript cannot carry the answer.
    """
    results: Dict[str, Dict[str, Any]] = {}

    for start in range(0, len(questions), BATCH_SIZE):
        batch = questions[start : start + BATCH_SIZE]
        try:
            results.update(_mark_batch(client, model, batch, student_work, subject, pages))
        except Exception as e:
            # A failed batch leaves those questions unmarked rather than
            # failing the whole paper.
            logger.error(
                f"Failed to mark questions {batch[0].number}-{batch[-1].number}: {e}",
                exc_info=True,
            )

    question_marks: List[QuestionMarkResult] = []
    total_awarded = 0.0
    total_available = 0.0

    for question in questions:
        available = float(question.marks or 1)
        payload = results.get(str(question.number).strip(), {})

        verdict = str(payload.get("verdict") or "not_attempted").strip().lower()
        if verdict not in VERDICTS:
            verdict = "not_attempted"

        awarded = _coerce_marks(payload.get("marks_awarded"), available)
        if verdict == "not_attempted":
            awarded = 0.0
        elif verdict == "correct" and not payload.get("marks_awarded"):
            # Trust an explicit "correct" verdict when the number is missing.
            awarded = available

        total_awarded += awarded
        total_available += available

        question_marks.append(
            QuestionMarkResult(
                paper_question_id=question.id,
                order_index=question.order_index,
                question_number=question.number or str(question.order_index),
                question_text=question.question_text,
                expected_answer=question.expected_answer,
                student_answer=payload.get("student_answer"),
                marks_awarded=awarded,
                marks_available=available,
                verdict=verdict,
                feedback=payload.get("feedback"),
                topic=question.topic,
            )
        )

    percentage = round(total_awarded / total_available * 100, 1) if total_available else None
    weak_topics = _derive_weak_topics(question_marks)

    return MarkingResult(
        marks_awarded=round(total_awarded, 1),
        marks_available=round(total_available, 1),
        percentage=percentage,
        overall_feedback=_summarise(question_marks, percentage),
        strengths=_derive_strong_topics(question_marks),
        weaknesses=[
            f"{m.question_number}: {m.feedback}"
            for m in question_marks
            if m.verdict in {"incorrect", "partial"} and m.feedback
        ][:8],
        weak_topics=weak_topics,
        question_marks=question_marks,
        model=model,
    )


def _topic_totals(marks: Sequence[QuestionMarkResult]) -> Dict[str, tuple[float, float]]:
    """Aggregate awarded/available marks by topic, skipping untagged questions."""
    totals: Dict[str, tuple[float, float]] = {}
    for mark in marks:
        topic = (mark.topic or "").strip()
        if not topic:
            continue
        awarded, available = totals.get(topic, (0.0, 0.0))
        totals[topic] = (awarded + mark.marks_awarded, available + mark.marks_available)
    return totals


def _derive_weak_topics(marks: Sequence[QuestionMarkResult]) -> List[str]:
    """Topics scoring below the weak threshold, worst first."""
    scored = []
    for topic, (awarded, available) in _topic_totals(marks).items():
        if available <= 0:
            continue
        pct = awarded / available * 100
        if pct < WEAK_TOPIC_THRESHOLD:
            scored.append((pct, topic))
    scored.sort()
    return [topic for _, topic in scored]


def _derive_strong_topics(marks: Sequence[QuestionMarkResult]) -> List[str]:
    """Topics scoring at or above the secure threshold, best first."""
    scored = []
    for topic, (awarded, available) in _topic_totals(marks).items():
        if available <= 0:
            continue
        pct = awarded / available * 100
        if pct >= SECURE_TOPIC_THRESHOLD:
            scored.append((-pct, topic))
    scored.sort()
    return [topic for _, topic in scored]


def _summarise(marks: Sequence[QuestionMarkResult], percentage: Optional[float]) -> str:
    """Build the overall feedback shown above the per-question breakdown."""
    if not marks:
        return "No questions could be marked."

    full = sum(1 for m in marks if m.verdict == "correct")
    partial = sum(1 for m in marks if m.verdict == "partial")
    wrong = sum(1 for m in marks if m.verdict == "incorrect")
    missing = sum(1 for m in marks if m.verdict == "not_attempted")

    lines = [
        f"**{percentage}%** — {full} full marks, {partial} partial, {wrong} incorrect"
        + (f", {missing} not attempted" if missing else "")
        + ".",
    ]

    weak = _derive_weak_topics(marks)
    if weak:
        lines.append("")
        lines.append(f"**Worth another look:** {', '.join(weak[:6])}.")

    strong = _derive_strong_topics(marks)
    if strong:
        lines.append("")
        lines.append(f"**Solid:** {', '.join(strong[:6])}.")

    if partial:
        lines.append("")
        lines.append(
            "Several answers picked up part marks. Those are the cheapest marks to win "
            "back — check each one against the feedback and write out the step you left out."
        )

    return "\n".join(lines)


def mark_holistically(
    student_work: str,
    *,
    subject: str,
    year_group: Optional[str],
    client: Any,
    model: str,
) -> MarkingResult:
    """Assess work when there is no per-question answer key to mark against."""
    user_content = (
        f"SUBJECT: {subject}\n"
        f"YEAR GROUP: {year_group or 'GCSE preparation'}\n\n"
        f"=== STUDENT'S WORK ===\n{student_work}"
    )

    response = chat_completion(
        client,
        model=model,
        messages=[
            {"role": "system", "content": HOLISTIC_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
        max_tokens=3000,
    )

    data = _extract_json(response.choices[0].message.content or "") or {}

    percentage: Optional[float]
    try:
        percentage = max(0.0, min(100.0, float(data.get("percentage"))))
    except (TypeError, ValueError):
        percentage = None

    def _string_list(key: str) -> List[str]:
        return [v for v in (data.get(key) or []) if isinstance(v, str)]

    return MarkingResult(
        marks_awarded=percentage or 0.0,
        marks_available=100.0,
        percentage=percentage,
        overall_feedback=data.get("overall_feedback") or "No feedback could be generated.",
        strengths=_string_list("strengths"),
        weaknesses=_string_list("weaknesses"),
        weak_topics=_string_list("weak_topics"),
        question_marks=[],
        model=model,
    )


def persist_marking(
    db: Session,
    *,
    submission: Submission,
    subject: str,
    paper_id: Optional[str],
    result: MarkingResult,
    marked_by: str = "ai",
    langfuse_trace_id: Optional[str] = None,
) -> Marking:
    """
    Save a marking result and roll it into the child's progress data.

    Writes the marking and its per-question detail, updates topic mastery, and
    adds a score-log entry so the result appears on the progress chart.
    """
    marking = Marking(
        id=str(uuid.uuid4()),
        submission_id=submission.id,
        child_id=submission.child_id,
        paper_id=paper_id,
        subject=subject,
        marks_awarded=result.marks_awarded,
        marks_available=result.marks_available,
        percentage=result.percentage,
        overall_feedback=result.overall_feedback,
        strengths=result.strengths,
        weaknesses=result.weaknesses,
        weak_topics=result.weak_topics,
        marked_by=marked_by,
        model=result.model,
        langfuse_trace_id=langfuse_trace_id,
        marked_at=datetime.utcnow(),
    )
    db.add(marking)
    db.flush()

    for mark in result.question_marks:
        db.add(
            QuestionMark(
                id=str(uuid.uuid4()),
                marking_id=marking.id,
                paper_question_id=mark.paper_question_id,
                order_index=mark.order_index,
                question_number=mark.question_number,
                question_text=mark.question_text,
                student_answer=mark.student_answer,
                expected_answer=mark.expected_answer,
                marks_awarded=mark.marks_awarded,
                marks_available=mark.marks_available,
                verdict=mark.verdict,
                feedback=mark.feedback,
                topic=mark.topic,
            )
        )

    update_topic_mastery(db, child_id=submission.child_id, subject=subject, result=result)

    if result.percentage is not None:
        db.add(
            ScoreLogEntry(
                id=str(uuid.uuid4()),
                child_id=submission.child_id,
                subject=subject,
                label=_score_label(db, submission),
                score_pct=result.percentage,
                year_average_pct=_year_average(db, submission.child_id, subject),
                source="marking",
                marking_id=marking.id,
                recorded_at=datetime.utcnow(),
            )
        )

    submission.status = "marked"
    db.commit()
    db.refresh(marking)

    logger.info(
        f"Marked submission {submission.id}: {result.marks_awarded}/{result.marks_available} "
        f"({result.percentage}%), {len(result.weak_topics)} weak topic(s)"
    )
    return marking


def _score_label(db: Session, submission: Submission) -> str:
    """Name the score-log entry after the assignment it came from."""
    from ..models_db import Assignment

    assignment = db.query(Assignment).filter(Assignment.id == submission.assignment_id).first()
    if assignment:
        return assignment.title
    return f"Submission {submission.submitted_at:%d %b %Y}"


def _year_average(db: Session, child_id: str, subject: str) -> Optional[float]:
    """
    The year-group average for this child's subject, so the gap can be charted.

    Comes from the subject baseline captured when the school report was
    imported; a marked workbook has no year average of its own.
    """
    from ..models_db import ChildSubject

    row = (
        db.query(ChildSubject)
        .filter(ChildSubject.child_id == child_id, ChildSubject.subject == subject)
        .first()
    )
    return row.year_average if row else None


def update_topic_mastery(
    db: Session, *, child_id: str, subject: str, result: MarkingResult
) -> None:
    """
    Fold this marking into the child's rolling per-topic performance.

    Mastery accumulates rather than being replaced, so a topic needs sustained
    performance to move to secure and one bad paper does not erase progress.
    """
    totals = _topic_totals(result.question_marks)

    # Holistic marking has no per-question data; record its weak topics as
    # attempts with no marks so they still surface for retesting.
    if not totals:
        for topic in result.weak_topics:
            _bump_mastery(db, child_id, subject, topic, awarded=0.0, available=0.0)
        return

    for topic, (awarded, available) in totals.items():
        _bump_mastery(db, child_id, subject, topic, awarded=awarded, available=available)


def _bump_mastery(
    db: Session,
    child_id: str,
    subject: str,
    topic: str,
    *,
    awarded: float,
    available: float,
) -> None:
    """Create or update a single topic mastery row."""
    row = (
        db.query(TopicMastery)
        .filter(
            TopicMastery.child_id == child_id,
            TopicMastery.subject == subject,
            TopicMastery.topic == topic,
        )
        .first()
    )
    if not row:
        row = TopicMastery(
            id=str(uuid.uuid4()),
            child_id=child_id,
            subject=subject,
            topic=topic,
            attempts=0,
            marks_awarded=0.0,
            marks_available=0.0,
        )
        db.add(row)

    row.attempts = (row.attempts or 0) + 1
    row.marks_awarded = (row.marks_awarded or 0.0) + awarded
    row.marks_available = (row.marks_available or 0.0) + available
    row.last_assessed_at = datetime.utcnow()

    if row.marks_available and row.marks_available > 0:
        row.mastery_pct = round(row.marks_awarded / row.marks_available * 100, 1)
        if row.mastery_pct >= SECURE_TOPIC_THRESHOLD:
            row.status = "secure"
        elif row.mastery_pct >= WEAK_TOPIC_THRESHOLD:
            row.status = "developing"
        else:
            row.status = "weak"
    else:
        row.mastery_pct = None
        row.status = "weak"


def load_paper_questions(db: Session, paper_id: Optional[str]) -> List[PaperQuestion]:
    """Fetch a paper's questions in order, including their expected answers."""
    if not paper_id:
        return []
    return (
        db.query(PaperQuestion)
        .filter(PaperQuestion.paper_id == paper_id)
        .order_by(PaperQuestion.order_index)
        .all()
    )


def get_paper(db: Session, paper_id: Optional[str]) -> Optional[Paper]:
    """Fetch a paper row by id."""
    if not paper_id:
        return None
    return db.query(Paper).filter(Paper.id == paper_id).first()
