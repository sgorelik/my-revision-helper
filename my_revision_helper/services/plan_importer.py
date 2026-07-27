"""
Import a study programme from the plan document and tracker spreadsheet.

The tracker is highly structured — a weekly timetable, a score log against the
year-group average, and a per-subject time split — so this parses it directly
rather than asking a model to interpret it. Deterministic, free, and it cannot
hallucinate a baseline score.

Expected sheets (matched by name, case-insensitive):

- "Weekly Tracker": Day | Block | Subject | Focus | Planned min
- "Score Log":      Subject | Test/date | Score % | Year avg % | Gap | Notes
- "Time Summary":   Subject | Blocks/week | Minutes/week | Approx hours
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..subjects import is_rotation_label, normalise_subject

logger = logging.getLogger(__name__)

DAY_NAMES = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "weds": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


@dataclass
class ScoreEntry:
    """One row of the score log."""

    subject: str
    label: str
    score_pct: Optional[float]
    year_average_pct: Optional[float]
    notes: Optional[str] = None


@dataclass
class TimetableBlock:
    """One slot in the weekly timetable."""

    day_of_week: int
    block_index: int
    subject: str
    focus: Optional[str]
    planned_minutes: int = 50
    week_cycle: Optional[str] = None


@dataclass
class ImportedProgramme:
    """Everything extracted from a tracker and plan."""

    scores: List[ScoreEntry] = field(default_factory=list)
    blocks: List[TimetableBlock] = field(default_factory=list)
    weekly_minutes: Dict[str, int] = field(default_factory=dict)
    weekly_minutes_target: int = 0
    days_per_week: int = 5
    plan_summary: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def _sheets(text: str) -> Dict[str, List[str]]:
    """Split extracted spreadsheet text back into named sheets of rows."""
    sheets: Dict[str, List[str]] = {}
    current: Optional[str] = None

    for line in text.split("\n"):
        header = re.match(r"^---\s*Sheet:\s*(.+?)\s*---$", line.strip())
        if header:
            current = header.group(1).strip().lower()
            sheets[current] = []
            continue
        if current is not None and line.strip():
            sheets[current].append(line)

    return sheets


def _cells(row: str) -> List[str]:
    return [c.strip() for c in row.split("|")]


def _number(value: str) -> Optional[float]:
    """Parse a percentage-ish cell, tolerating '%', 'n/a' and stray text."""
    if not value:
        return None
    cleaned = value.replace("%", "").strip()
    if cleaned.lower() in {"n/a", "na", "-", "—", ""}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    return float(match.group()) if match else None


def parse_score_log(rows: List[str]) -> List[ScoreEntry]:
    """
    Read the score log.

    Rows look like:
      Maths | Summer 2026 (non-calc) | 53 | 76 | -23 | Index laws, brackets
    """
    entries: List[ScoreEntry] = []

    for row in rows:
        cells = _cells(row)
        if len(cells) < 3:
            continue

        subject = normalise_subject(cells[0])
        if not subject or subject.lower() in {"subject", "total"}:
            continue

        score = _number(cells[2]) if len(cells) > 2 else None
        if score is None:
            continue

        year_average = _number(cells[3]) if len(cells) > 3 else None
        # The gap column is derived, so ignore it and recompute from the scores.
        notes = cells[5] if len(cells) > 5 and cells[5] else None

        entries.append(
            ScoreEntry(
                subject=subject,
                label=cells[1] or "Baseline",
                score_pct=score,
                year_average_pct=year_average,
                notes=notes,
            )
        )

    return entries


def parse_weekly_tracker(rows: List[str]) -> List[TimetableBlock]:
    """
    Read the weekly timetable.

    Rows look like:
      Mon | 1 | Maths | Index laws & expanding brackets | 50
    """
    blocks: List[TimetableBlock] = []

    for row in rows:
        cells = _cells(row)
        if len(cells) < 3:
            continue

        day_key = cells[0].strip().lower().rstrip(".")
        if day_key not in DAY_NAMES:
            continue

        try:
            block_index = int(re.sub(r"\D", "", cells[1]) or 0)
        except ValueError:
            continue
        if not block_index:
            continue

        raw_subject = cells[2]
        if not raw_subject:
            continue

        # Rotation slots keep their printed label so the timetable still reads
        # correctly, but they are not treated as a single subject.
        subject = raw_subject if is_rotation_label(raw_subject) else normalise_subject(raw_subject)
        if not subject:
            continue

        focus = cells[3] if len(cells) > 3 and cells[3] else None
        minutes = int(_number(cells[4]) or 50) if len(cells) > 4 else 50

        blocks.append(
            TimetableBlock(
                day_of_week=DAY_NAMES[day_key],
                block_index=block_index,
                subject=subject,
                focus=focus,
                planned_minutes=minutes,
            )
        )

    return blocks


def parse_time_summary(rows: List[str]) -> tuple[Dict[str, int], int]:
    """
    Read the per-subject weekly time split.

    Returns (subject -> minutes, total minutes). Rows look like:
      Maths | 3 | 150 | 2.5
    """
    minutes: Dict[str, int] = {}
    total = 0

    for row in rows:
        cells = _cells(row)
        if len(cells) < 3:
            continue

        raw_subject = cells[0]
        value = _number(cells[2])
        if value is None:
            continue

        if raw_subject.strip().lower() == "total":
            total = int(value)
            continue

        if is_rotation_label(raw_subject):
            # e.g. "History / Geography / PRE" — split the allowance evenly so
            # each subject shows a realistic weekly target.
            parts = [normalise_subject(p) for p in raw_subject.split("/")]
            parts = [p for p in parts if p]
            if parts:
                share = int(value / len(parts))
                for part in parts:
                    minutes[part] = minutes.get(part, 0) + share
            continue

        subject = normalise_subject(raw_subject)
        if subject and subject.lower() != "subject":
            minutes[subject] = int(value)

    if not total:
        total = sum(minutes.values())

    return minutes, total


def parse_focus_topics(notes: Optional[str]) -> List[str]:
    """
    Split a score-log notes cell into topic names.

    "Index laws, brackets, sequences, straight lines" becomes four topics.
    """
    if not notes:
        return []

    parts = re.split(r"[,;]| and ", notes)
    topics = []
    for part in parts:
        topic = part.strip(" .;")
        # Drop fragments too short to be a topic or too long to be anything but prose.
        if 3 <= len(topic) <= 60:
            topics.append(topic)
    return topics


def extract_plan_summary(plan_text: Optional[str]) -> Optional[str]:
    """
    Pull the headline explanation out of the plan document.

    Takes the paragraph following "The idea in one line", which is where these
    plans state their rationale, and falls back to the first substantial
    paragraph.
    """
    if not plan_text:
        return None

    lines = [line.strip() for line in plan_text.split("\n") if line.strip()]

    for index, line in enumerate(lines):
        if line.lower().startswith("the idea in one line"):
            remainder = re.sub(r"^the idea in one line\.?\s*", "", line, flags=re.I).strip()
            # The summary usually continues on the same line, but some documents
            # put the heading alone and the text underneath.
            if remainder:
                return remainder
            if index + 1 < len(lines):
                return lines[index + 1]

    for line in lines[1:]:
        if len(line) > 120:
            return line

    return None


def import_programme(
    tracker_text: Optional[str], plan_text: Optional[str] = None
) -> ImportedProgramme:
    """
    Build a programme from the tracker spreadsheet and plan document.

    Neither input is required: a tracker alone gives baselines and a timetable,
    a plan alone gives the summary.
    """
    programme = ImportedProgramme()

    if tracker_text:
        sheets = _sheets(tracker_text)

        def find(*keywords: str) -> List[str]:
            for name, rows in sheets.items():
                if all(keyword in name for keyword in keywords):
                    return rows
            return []

        programme.scores = parse_score_log(find("score"))
        programme.blocks = parse_weekly_tracker(find("weekly"))
        programme.weekly_minutes, programme.weekly_minutes_target = parse_time_summary(
            find("time")
        )

        if programme.blocks:
            programme.days_per_week = len({b.day_of_week for b in programme.blocks})

        if not programme.scores:
            programme.warnings.append("No score log rows found in the tracker")
        if not programme.blocks:
            programme.warnings.append("No weekly timetable rows found in the tracker")
    else:
        programme.warnings.append("No tracker supplied — no baselines or timetable imported")

    programme.plan_summary = extract_plan_summary(plan_text)

    logger.info(
        f"Imported programme: {len(programme.scores)} score(s), "
        f"{len(programme.blocks)} timetable block(s), "
        f"{programme.weekly_minutes_target} min/week target"
    )
    return programme
