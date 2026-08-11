"""
Match numbered answers to the questions they belong to.

Children often work in printed workbooks and hand back a scan where the question
pages come first and the handwritten answers sit on later pages as a numbered
list ("1) …, 2) …"), without the questions repeated next to them. The marker
used to hunt for each answer in the whole transcript and often came back with
"not attempted" for everything — or worse, a silent zero.

Two places the questions can come from:

1. Earlier parts of the same scan (question pages before the answer sheet).
2. A library paper the hand-in is linked to (or an assigned paper).

Either way the numbered answers are pulled out first and handed to the marker
as an explicit map, so it does not have to rediscover which line is which.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from .student_writing import looks_self_contained, strip_student_writing

# A page or file boundary inserted while reading a multi-page upload.
_SECTION_BREAK = re.compile(
    r"(?m)^\s*---\s*(?:Page\s+\d+|[^-\n]+)\s*---\s*$"
)

# Handwritten (or typed) numbered answers. Tolerates OCR noise around the
# number and the separators children actually use: "1.", "1)", "1:", "Q1".
_NUMBERED_ANSWER = re.compile(
    r"(?im)^\s*(?:\[written\]\s*)?"
    r"(?:q(?:uestion)?\s*)?"
    r"(\d{1,3}[a-z]?)\s*[.):\-]\s+"
    r"(.+?)\s*$"
)

# A heading that announces the answers section has begun.
_ANSWER_HEADING = re.compile(
    r"(?im)^\s*(?:\[written\]\s*)?"
    r"(?:answers?(?:\s+sheet)?|my\s+answers?|solutions?)\s*:?\s*$"
)

# Question stems that show up on the left of a numbered line. A line that
# starts this way is the question itself, not the child's answer to it.
_QUESTION_STEM = re.compile(
    r"(?i)^(work out|calculate|find|write|draw|explain|describe|show that|"
    r"complete|solve|simplify|expand|factorise|evaluate|determine|state|"
    r"give|name|list|compare|how many|what is|which of)\b"
)


@dataclass
class NumberedAnswer:
    number: str
    text: str


@dataclass
class ScanParts:
    """
    A scan split into the bits that carry questions and the bits that carry
    answers. Either half can be empty — a same-page worksheet leaves everything
    in `questions`, an answer-only sheet leaves everything in `answers`.
    """

    questions: str = ""
    answers: str = ""
    numbered: List[NumberedAnswer] = field(default_factory=list)

    @property
    def has_separate_answers(self) -> bool:
        """Whether the answers live apart from the questions."""
        return bool(self.numbered) and (
            bool(self.questions.strip()) or not looks_self_contained(self.answers)
        )


def split_sections(text: str) -> List[str]:
    """Break a multi-page / multi-file transcription into its pieces."""
    if not text or not text.strip():
        return []

    parts: List[str] = []
    last = 0
    for match in _SECTION_BREAK.finditer(text):
        chunk = text[last : match.start()].strip()
        if chunk:
            parts.append(chunk)
        last = match.end()
    tail = text[last:].strip()
    if tail:
        parts.append(tail)
    return parts or [text.strip()]


def _clean_answer_body(body: str) -> str:
    """Drop trailing mark allocations and dotted answer lines."""
    body = re.sub(r"\s*\(\d{1,2}\)\s*$", "", body).strip()
    body = re.sub(r"\.{4,}\s*$", "", body).strip()
    return body


def _looks_like_answer_body(body: str, *, tagged: bool) -> bool:
    """
    Whether this numbered line is an answer rather than a question.

    Tagged handwriting is trusted: OCR already decided the child wrote it.
    Untagged lines have to look like short answers, otherwise "1. Work out…"
    on a question page would be harvested as the answer to question 1.
    """
    if not body or body.lower() in {"[no answer]", "[illegible]", "...", "……"}:
        return False
    if tagged:
        return True
    if "?" in body:
        return False
    if len(body) > 80:
        return False
    if _QUESTION_STEM.match(body):
        return False
    return True


def extract_numbered_answers(text: str) -> List[NumberedAnswer]:
    """
    Pull out a numbered answer list from a transcription.

    Prefers lines the OCR tagged as handwriting. Bare typed lists ("1. 45")
    still work, but question stems on a worksheet are left alone.
    """
    if not text:
        return []

    tagged: List[NumberedAnswer] = []
    untagged: List[NumberedAnswer] = []
    seen: set[str] = set()

    for raw_line in text.split("\n"):
        match = _NUMBERED_ANSWER.match(raw_line)
        if not match:
            continue
        number = match.group(1).strip().lower()
        body = _clean_answer_body(match.group(2))
        is_tagged = "[written]" in raw_line.lower()
        if not _looks_like_answer_body(body, tagged=is_tagged):
            continue
        if number in seen:
            continue
        seen.add(number)
        entry = NumberedAnswer(number=number, text=body)
        (tagged if is_tagged else untagged).append(entry)

    # Handwriting wins when both are present — the typed "1. Work out…" lines
    # on the question pages must not override "[written] 1. 45" on the answer
    # sheet of the same upload.
    return tagged or untagged


def _is_answer_section(section: str) -> bool:
    """
    Whether this page looks like an answer sheet rather than a question page.

    A page that still carries its own questions after the handwriting is
    stripped is treated as a question page even when it also has numbered
    answers written on it — that is the ordinary same-page worksheet.
    """
    if looks_self_contained(section):
        return False
    if _ANSWER_HEADING.search(section):
        return True
    numbered = extract_numbered_answers(section)
    printed_len = len(strip_student_writing(section))
    # Enough numbered answers and nothing much left once the writing is gone
    # means this page is the answers.
    if len(numbered) >= 2 and printed_len < 80:
        return True
    if len(numbered) >= 1 and printed_len < 40:
        return True
    return False


def partition_scan(text: str) -> ScanParts:
    """
    Separate the question pages from the answer pages of a completed scan.

    Walks the scan in order. Pages that carry questions stay in the questions
    half; pages that look like a numbered answer sheet move to the answers
    half. When nothing separates cleanly the whole scan is treated as both —
    which is what a same-page worksheet already is.
    """
    sections = split_sections(text)
    if not sections:
        return ScanParts()

    question_bits: List[str] = []
    answer_bits: List[str] = []
    saw_answers = False

    for section in sections:
        if _is_answer_section(section):
            answer_bits.append(section)
            saw_answers = True
            continue
        # Once an answer sheet has begun, later pages that are short and mostly
        # handwriting are more answers, not a late question page.
        if saw_answers and not looks_self_contained(section):
            answer_bits.append(section)
            continue
        question_bits.append(section)

    questions = "\n\n".join(question_bits).strip()
    answers = "\n\n".join(answer_bits).strip()

    # Nothing separated: the whole scan is the work, questions and answers
    # together. Numbered answers are still useful to the marker as a map.
    if not saw_answers:
        return ScanParts(
            questions=text.strip(),
            answers=text.strip(),
            numbered=extract_numbered_answers(text),
        )

    numbered = extract_numbered_answers(answers) or extract_numbered_answers(text)
    return ScanParts(questions=questions, answers=answers or text.strip(), numbered=numbered)


def format_answer_map(answers: Sequence[NumberedAnswer]) -> str:
    """A plain list the marker can read without hunting through the OCR."""
    if not answers:
        return ""
    lines = [
        "=== ANSWERS BY NUMBER ===",
        "The student wrote their answers as a numbered list, possibly on a "
        "separate sheet from the questions. Match each answer to the question "
        "with the same number. Prefer this map over searching the raw transcript.",
    ]
    for answer in answers:
        lines.append(f"{answer.number}. {answer.text}")
    return "\n".join(lines)


def prepare_work_for_marking(student_work: str) -> Tuple[str, ScanParts]:
    """
    Ready a scan for per-question marking.

    Returns the text to send the marker (with a numbered answer map at the top
    when one can be built) and the partitioned scan, so a caller that wants the
    question pages on their own — for example to build a library paper — does
    not have to re-split.
    """
    parts = partition_scan(student_work)
    if not parts.numbered:
        return student_work, parts

    mapped = format_answer_map(parts.numbered)
    # Keep the raw transcript underneath so drawings, working and anything the
    # map missed are still visible to the marker.
    body = parts.answers if parts.has_separate_answers else student_work
    return f"{mapped}\n\n=== FULL TRANSCRIPT ===\n{body}", parts


def questions_text_for_library(parts: ScanParts, fallback: str) -> str:
    """
    The printed half to turn into a library paper.

    Prefer the question pages alone when the answers lived elsewhere — that way
    the library copy does not carry a phantom "Answers" heading and a list of
    empty numbers. Fall back to the whole scan for same-page worksheets.
    """
    if parts.questions and parts.has_separate_answers:
        return parts.questions
    return fallback
