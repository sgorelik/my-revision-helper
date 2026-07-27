"""
The subject vocabulary.

School reports, trackers and workbooks all name subjects slightly differently
("Maths", "Mathematics", "PRE", "RS"). Everything stores the canonical name so
that a baseline, a paper and a marking for the same subject actually line up on
the dashboard.
"""

from __future__ import annotations

from typing import Optional

CANONICAL_SUBJECTS = [
    "Mathematics",
    "English",
    "English Literature",
    "Biology",
    "Chemistry",
    "Physics",
    "Combined Science",
    "PRE",
    "History",
    "Geography",
    "Computer Science",
    "Economics",
    "Business Studies",
    "Art",
    "Music",
    "Drama",
    "Design & Technology",
    "Physical Education",
    "French",
    "German",
    "Spanish",
    "Latin",
    "Greek",
    "Other",
]

# Lowercased alternative spellings seen in reports and trackers.
_ALIASES = {
    "maths": "Mathematics",
    "math": "Mathematics",
    "mathematics": "Mathematics",
    "further maths": "Mathematics",
    "eng": "English",
    "english language": "English",
    "english lang": "English",
    "english lit": "English Literature",
    "lit": "English Literature",
    "bio": "Biology",
    "chem": "Chemistry",
    "phys": "Physics",
    "science": "Combined Science",
    "combined science": "Combined Science",
    "double science": "Combined Science",
    # Philosophy, Religion & Ethics, and the various names schools give it.
    "pre": "PRE",
    "re": "PRE",
    "rs": "PRE",
    "religious studies": "PRE",
    "religious education": "PRE",
    "philosophy": "PRE",
    "philosophy, religion & ethics": "PRE",
    "philosophy religion and ethics": "PRE",
    "theology": "PRE",
    "hist": "History",
    "geog": "Geography",
    "geo": "Geography",
    "computing": "Computer Science",
    "computer studies": "Computer Science",
    "ict": "Computer Science",
    "cs": "Computer Science",
    "business": "Business Studies",
    "dt": "Design & Technology",
    "d&t": "Design & Technology",
    "pe": "Physical Education",
    "games": "Physical Education",
    "sport": "Physical Education",
    "art & design": "Art",
    "fine art": "Art",
}

# Labels used for rotating or shared timetable slots. These are legitimate
# block labels but must not become subjects in their own right.
ROTATION_LABELS = {
    "humanities",
    "science catch-up",
    "science catch up",
    "physics / chem",
    "physics/chem",
    "physics / chemistry",
    "sciences",
    "rotation",
    "catch-up",
    "catch up",
}


def normalise_subject(raw: Optional[str]) -> Optional[str]:
    """
    Map a subject as written to its canonical name.

    Returns None for empty input, and passes through unrecognised names
    unchanged (title-cased) rather than forcing them to "Other" — a school may
    teach something this list has never heard of.
    """
    if not raw:
        return None

    cleaned = " ".join(raw.strip().split())
    if not cleaned:
        return None

    lowered = cleaned.lower()

    if lowered in _ALIASES:
        return _ALIASES[lowered]

    for canonical in CANONICAL_SUBJECTS:
        if lowered == canonical.lower():
            return canonical

    return cleaned


def is_rotation_label(raw: Optional[str]) -> bool:
    """True when a timetable label is a rotating slot rather than a subject."""
    if not raw:
        return False
    lowered = " ".join(raw.strip().split()).lower()
    if lowered in ROTATION_LABELS:
        return True
    # "History / Geography / PRE" style rotations.
    return "/" in lowered and len(lowered.split("/")) >= 2
