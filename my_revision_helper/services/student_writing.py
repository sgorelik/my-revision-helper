"""
Separate a printed paper from the child's handwriting on it.

Work that arrives already done — a worksheet the child filled in on paper, never
assigned through the app — carries both halves in one scan. The OCR prompt
already marks which words the child wrote, so removing them leaves the blank
paper behind. That blank paper can then go through the ordinary parser and be
kept in the library, ready to hand to the other child.

The tags come from OCR_SYSTEM_PROMPT in file_processing.py:
    Answer: [written] 490  ......... (2)
    [no answer]
    [FIGURE: drawn by student — a pie chart in four equal sectors]
    [illegible], [crossed out]
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

WRITTEN_TAG = "[written]"

# The child's writing runs from the tag until the printed page resumes. What
# resumes it is either the row of dots they wrote on, or the mark allocation at
# the end of the line, and keeping both matters: the dots are what make the
# question readable and the "(2)" is what it is worth.
_WRITTEN_RUN = re.compile(r"\[written\]\s*.*?(?=\.{4,}|\(\d{1,2}\)\s*$|$)", re.M)

# A line that is nothing but the child's work once the tag is taken off.
_WRITTEN_WHOLE_LINE = re.compile(r"^\s*\[written\]\s*\S.*$")

# Their drawing, as opposed to a figure printed on the paper.
_DRAWN_FIGURE = re.compile(r"^\s*\[FIGURE:\s*drawn by student\b.*$", re.I)

# Annotations that only ever describe the child's own marks on the page.
_STUDENT_NOTES = re.compile(r"\[(?:no answer|crossed out)\]", re.I)

# What is left of an answer line after the writing goes: "Answer:", the dots to
# write on, and what the question was worth.
_EMPTY_ANSWER_LINE = re.compile(r"^\s*(answer\s*:?)?\s*[.\s]*(\(\d{1,2}\))?\s*$", re.I)


def has_student_writing(text: Optional[str]) -> bool:
    """
    Whether the transcription actually marks up any handwriting.

    Worth checking before treating a document as completed work: if nothing is
    tagged, either the page was blank or the transcription ignored the
    convention, and stripping would be a no-op that left the child's answers
    sitting in the library copy.
    """
    return WRITTEN_TAG in (text or "")


def strip_student_writing(text: Optional[str]) -> str:
    """
    The printed paper on its own, with the child's answers taken out.

    Keeps the question, the answer space and the marks; drops what the child
    wrote in that space and anything they drew.
    """
    if not text:
        return ""

    kept = []
    for raw_line in text.split("\n"):
        if _DRAWN_FIGURE.match(raw_line):
            continue

        line = _STUDENT_NOTES.sub("", raw_line)

        if _WRITTEN_WHOLE_LINE.match(line):
            continue

        line = _WRITTEN_RUN.sub("", line)
        kept.append(line.rstrip())

    # Collapse the runs of blank lines left behind, so the parser sees a tidy
    # document rather than one full of holes.
    out: list[str] = []
    for line in kept:
        if line.strip() or (out and out[-1].strip()):
            out.append(line)

    return "\n".join(out).strip()


def looks_self_contained(text: Optional[str]) -> bool:
    """
    Whether this scan carries its own questions, not just answers.

    A page of "1. 490  2. 12cm" with no question in sight cannot be turned into
    a paper, and marking it needs the questions from somewhere else. The test is
    whether anything substantial survives having the handwriting removed.
    """
    printed = strip_student_writing(text)
    if not printed:
        return False

    # Answer scaffolding on its own does not count as a question.
    substance = [
        line
        for line in printed.split("\n")
        if line.strip() and not _EMPTY_ANSWER_LINE.match(line)
    ]
    return len("\n".join(substance)) >= 120
