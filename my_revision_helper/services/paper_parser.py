"""
Turn an uploaded workbook into a structured, markable paper.

Two things happen here, in order:

1. The answer key is split off the back of the document by heading match. This
   is deterministic and must not depend on the model — it is the boundary that
   keeps solutions away from the student.
2. The question half is parsed into individual questions, each tagged with its
   session, difficulty band and topic, and paired with its expected answer
   from the key.

Step 2 uses the model, and degrades to a regex-based parse if the model is
unavailable or returns something unusable. A paper with no parsed questions is
still assignable — it just gets marked holistically instead of per question.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Headings that mark the start of the solutions section. Ordered longest-first
# so that "Model Answers & Mark Guidance" wins over a bare "Answers".
ANSWER_KEY_HEADINGS = [
    "model answers & mark guidance",
    "model answers and mark guidance",
    "answer key — worked solutions",
    "answer key - worked solutions",
    "model answers",
    "answer key",
    "mark scheme",
    "worked solutions",
    "solutions",
    "answers",
]

# Difficulty bands as printed in the workbooks.
BAND_PATTERNS = [
    ("warm-up", re.compile(r"^\s*warm[-\s]?up\b", re.I)),
    ("standard", re.compile(r"^\s*standard\b", re.I)),
    ("exam-style", re.compile(r"^\s*exam[-\s]?style\b", re.I)),
    ("stretch", re.compile(r"^\s*stretch\b", re.I)),
]

SESSION_PATTERN = re.compile(r"^\s*(session\s+\d+.*)$", re.I)
NUMBERED_ITEM_PATTERN = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
MARKS_PATTERN = re.compile(r"\[(\d+)\s*marks?\]", re.I)


@dataclass
class ParsedQuestion:
    """One question lifted out of a paper."""

    order_index: int
    number: str
    question_text: str
    session_label: Optional[str] = None
    band: Optional[str] = None
    topic: Optional[str] = None
    marks: int = 1
    expected_answer: Optional[str] = None
    marking_notes: Optional[str] = None


@dataclass
class ParsedPaper:
    """The result of parsing an uploaded document."""

    question_text: str
    answer_key_text: Optional[str]
    questions: List[ParsedQuestion] = field(default_factory=list)
    title: Optional[str] = None
    topics: List[str] = field(default_factory=list)
    estimated_minutes: Optional[int] = None
    total_marks: Optional[int] = None
    parse_status: str = "parsed"
    parse_error: Optional[str] = None


def split_answer_key(full_text: str) -> Tuple[str, Optional[str]]:
    """
    Split a document into its student-facing half and its answer key.

    Matches on a line that is *only* an answer-key heading, so a passing
    mention such as "check it against the mark scheme" in the instructions
    does not truncate the paper. Returns (question_text, answer_key_text).
    """
    lines = full_text.split("\n")

    for index, line in enumerate(lines):
        stripped = line.strip().lower().rstrip(":")
        # Ignore leading bullets/numbering when matching the heading.
        stripped = re.sub(r"^[\s\d.)•\-–—]*", "", stripped)

        for heading in ANSWER_KEY_HEADINGS:
            if stripped == heading or stripped.startswith(heading + " "):
                # A real heading sits on a short line of its own.
                if len(line.strip()) > len(heading) + 40:
                    continue
                questions = "\n".join(lines[:index]).strip()
                answers = "\n".join(lines[index:]).strip()
                # Guard against a heading appearing near the very top.
                if len(questions) < 200:
                    continue
                logger.info(
                    f"Split answer key at line {index}: "
                    f"{len(questions)} chars of questions, {len(answers)} chars of answers"
                )
                return questions, answers

    logger.info("No answer key heading found — treating the whole document as questions")
    return full_text.strip(), None


def _heuristic_questions(question_text: str) -> List[ParsedQuestion]:
    """
    Fallback parse: walk the document tracking the current session and band,
    and treat each numbered line as a question.
    """
    questions: List[ParsedQuestion] = []
    current_session: Optional[str] = None
    current_band: Optional[str] = None
    order = 0

    for raw_line in question_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        session_match = SESSION_PATTERN.match(line)
        if session_match:
            current_session = session_match.group(1).strip()
            current_band = None
            continue

        matched_band = None
        for band_name, pattern in BAND_PATTERNS:
            if pattern.match(line) and len(line) < 80:
                matched_band = band_name
                break
        if matched_band:
            current_band = matched_band
            continue

        item_match = NUMBERED_ITEM_PATTERN.match(line)
        if item_match and current_session:
            text = item_match.group(2).strip()
            if len(text) < 5:
                continue
            marks_match = MARKS_PATTERN.search(text)
            order += 1
            questions.append(
                ParsedQuestion(
                    order_index=order,
                    number=item_match.group(1),
                    question_text=text,
                    session_label=current_session,
                    band=current_band,
                    topic=topic_from_session(current_session),
                    marks=int(marks_match.group(1)) if marks_match else 1,
                )
            )

    return questions


def _heuristic_answers(answer_key_text: str) -> Dict[Tuple[Optional[str], str], str]:
    """
    Map (session label, question number) -> answer text from the key.

    The key repeats the session headings, which is what makes matching
    reliable when question numbers restart at 1 in each session.
    """
    answers: Dict[Tuple[Optional[str], str], str] = {}
    current_session: Optional[str] = None
    current_key: Optional[Tuple[Optional[str], str]] = None

    for raw_line in answer_key_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        session_match = SESSION_PATTERN.match(line)
        if session_match:
            current_session = session_match.group(1).strip()
            current_key = None
            continue

        item_match = NUMBERED_ITEM_PATTERN.match(line)
        if item_match:
            current_key = (current_session, item_match.group(1))
            answers[current_key] = item_match.group(2).strip()
        elif current_key:
            # Continuation of a multi-line answer.
            answers[current_key] += " " + line

    return answers


def topic_from_session(label: Optional[str]) -> Optional[str]:
    """
    Derive a topic from a session heading.

    Workbook sessions are titled "Session 1 — Indices (laws of powers)", so the
    part after the dash is the topic. Without this, a paper parsed by the regex
    path carries no topics at all and nothing can be retested from it.
    """
    if not label:
        return None

    match = re.match(r"\s*session\s+\d+\s*[—–\-:]\s*(.+)$", label, re.I)
    topic = match.group(1) if match else label.strip()

    # Drop a trailing parenthetical and any duration suffix like "· ~40 min".
    topic = re.sub(r"\s*·.*$", "", topic)
    topic = re.sub(r"\s*\([^)]*\)\s*$", "", topic)
    topic = topic.strip(" .:—–-")

    return topic or None


def _normalise_session(label: Optional[str]) -> Optional[str]:
    """
    Reduce a session heading to 'session N' so that the questions half and the
    answers half match even when their subtitles differ.
    """
    if not label:
        return None
    match = re.match(r"\s*session\s+(\d+)", label, re.I)
    return f"session {match.group(1)}" if match else label.strip().lower()


def _pair_heuristic(
    questions: List[ParsedQuestion], answer_key_text: Optional[str]
) -> List[ParsedQuestion]:
    """Attach expected answers to questions by session and number."""
    if not answer_key_text:
        return questions

    answers = _heuristic_answers(answer_key_text)
    lookup = {
        (_normalise_session(session), number): text for (session, number), text in answers.items()
    }

    for question in questions:
        key = (_normalise_session(question.session_label), question.number)
        if key in lookup:
            question.expected_answer = lookup[key]

    matched = sum(1 for q in questions if q.expected_answer)
    logger.info(f"Heuristic pairing matched {matched}/{len(questions)} answers")
    return questions


PARSE_SYSTEM_PROMPT = """You are a precise exam-paper parser for a study app.

You receive the QUESTIONS half of a student workbook and, separately, its ANSWER KEY.
Return a single JSON object describing every question in the workbook.

Schema:
{
  "title": "short title of the paper",
  "topics": ["topic name", ...],
  "estimated_minutes": 40,
  "questions": [
    {
      "number": "the question number exactly as printed, e.g. '7' or '8(a)'",
      "session_label": "the session heading the question sits under, or null",
      "band": "one of: warm-up, standard, exam-style, stretch, or null",
      "topic": "the specific skill this question tests, e.g. 'index laws'",
      "marks": 1,
      "question_text": "the full question text, self-contained",
      "expected_answer": "the answer for this question taken from the ANSWER KEY, or null if absent",
      "marking_notes": "what a full-mark response must contain, or null"
    }
  ]
}

Rules:
- Include EVERY numbered question, in document order. Do not summarise or skip any.
- Copy question_text faithfully. If a question depends on a passage or extract printed
  earlier in the workbook, include the relevant passage inside question_text so the
  question stands alone.
- Take expected_answer verbatim from the ANSWER KEY where one exists. Never invent one.
- Question numbers restart in each session; match answers to questions using BOTH the
  session heading and the number.
- "marks" is the credit for the question. Use the printed value like [12 marks] when
  present, otherwise estimate: warm-up 1, standard 2, exam-style 3, stretch 3.
- "topic" should be specific enough to retest on later ('balancing equations', not 'chemistry').
- Return only the JSON object, with no surrounding prose or code fences."""


def _extract_json(content: str) -> Optional[Dict[str, Any]]:
    """Pull a JSON object out of a model response, tolerating code fences."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _ai_parse(
    question_text: str,
    answer_key_text: Optional[str],
    subject: str,
    client: Any,
    model: str,
) -> Optional[ParsedPaper]:
    """Ask the model to structure the paper. Returns None if it cannot."""
    user_content = (
        f"SUBJECT: {subject}\n\n"
        f"=== QUESTIONS ===\n{question_text}\n\n"
        f"=== ANSWER KEY ===\n{answer_key_text or '(no answer key supplied)'}"
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": PARSE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=16000,
    )

    data = _extract_json(response.choices[0].message.content or "")
    if not data or not isinstance(data.get("questions"), list):
        logger.warning("Model returned no usable question list")
        return None

    questions: List[ParsedQuestion] = []
    for index, item in enumerate(data["questions"], start=1):
        if not isinstance(item, dict):
            continue
        text = (item.get("question_text") or "").strip()
        if not text:
            continue

        try:
            marks = int(item.get("marks") or 1)
        except (TypeError, ValueError):
            marks = 1

        band = (item.get("band") or "").strip().lower() or None
        if band not in {"warm-up", "standard", "exam-style", "stretch", None}:
            band = None

        session_label = item.get("session_label") or None
        questions.append(
            ParsedQuestion(
                order_index=index,
                number=str(item.get("number") or index),
                question_text=text,
                session_label=session_label,
                band=band,
                # Fall back to the session heading so every question carries a
                # topic; topic-level mastery is what drives retests.
                topic=(item.get("topic") or topic_from_session(session_label)),
                marks=max(1, marks),
                expected_answer=(item.get("expected_answer") or None),
                marking_notes=(item.get("marking_notes") or None),
            )
        )

    if not questions:
        return None

    topics = [t for t in (data.get("topics") or []) if isinstance(t, str)]
    try:
        estimated = int(data.get("estimated_minutes")) if data.get("estimated_minutes") else None
    except (TypeError, ValueError):
        estimated = None

    return ParsedPaper(
        question_text=question_text,
        answer_key_text=answer_key_text,
        questions=questions,
        title=(data.get("title") or None),
        topics=topics,
        estimated_minutes=estimated,
        total_marks=sum(q.marks for q in questions),
        parse_status="parsed",
    )


def parse_paper(
    full_text: str,
    *,
    subject: str,
    client: Optional[Any] = None,
    model: Optional[str] = None,
) -> ParsedPaper:
    """
    Parse a document into a markable paper.

    The answer-key split always happens locally. Question extraction prefers
    the model and falls back to the regex parse, so a missing or failing
    OpenAI key degrades the result rather than breaking the upload.
    """
    question_text, answer_key_text = split_answer_key(full_text)

    if client and model:
        try:
            parsed = _ai_parse(question_text, answer_key_text, subject, client, model)
            if parsed:
                matched = sum(1 for q in parsed.questions if q.expected_answer)
                logger.info(
                    f"Parsed {len(parsed.questions)} questions "
                    f"({matched} with answers) using {model}"
                )
                return parsed
        except Exception as e:
            logger.error(f"AI paper parse failed, falling back to heuristics: {e}", exc_info=True)

    questions = _pair_heuristic(_heuristic_questions(question_text), answer_key_text)
    return ParsedPaper(
        question_text=question_text,
        answer_key_text=answer_key_text,
        questions=questions,
        total_marks=sum(q.marks for q in questions) or None,
        parse_status="parsed" if questions else "failed",
        parse_error=None if questions else "Could not identify any questions in the document",
    )


def guess_title(text: str) -> Optional[str]:
    """
    Use the document's own heading as its title.

    Workbooks open with a line like "Mathematics — Week 1 Workbook", which is a
    far better library title than the uploaded filename.
    """
    for raw_line in text.split("\n")[:5]:
        line = raw_line.strip()
        if 4 <= len(line) <= 120 and not line.lower().startswith(("session", "how to use")):
            return line
    return None


def new_question_id() -> str:
    """Identifier for a parsed question row."""
    return str(uuid.uuid4())
