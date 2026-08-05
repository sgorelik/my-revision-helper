"""
Turning what someone typed into a list of files to send.

An instruction like "upload the papers in my Downloads folder" arrives as a
path, a folder or a pattern, and any of them may point at things the app cannot
read. Everything is resolved here, and whatever is left out is said out loud
rather than dropped quietly.
"""

from __future__ import annotations

import glob as globlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence

# What the app can actually parse, from file_processing.py.
SUPPORTED_SUFFIXES = (
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".txt",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".heic",
)

# The server refuses anything larger, so there is no point sending it.
MAX_FILE_BYTES = 25 * 1024 * 1024


@dataclass
class Collected:
    """The files to send, and an account of everything left behind."""

    files: List[Path] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.files


def _expand(path: str) -> List[Path]:
    """One argument into the paths it names, whether file, folder or pattern."""
    expanded = os.path.expanduser(path.strip())

    if any(char in expanded for char in "*?["):
        return sorted(Path(hit) for hit in globlib.glob(expanded, recursive=True))

    candidate = Path(expanded)
    if candidate.is_dir():
        return sorted(child for child in candidate.rglob("*") if child.is_file())

    return [candidate]


def collect_files(paths: Sequence[str], *, limit: int = 0) -> Collected:
    """
    The files behind a list of paths, folders or glob patterns.

    Unreadable, unsupported and oversized entries are left out with a reason.
    Order is stable so that repeating a call sends the same thing twice, rather
    than a different half of a folder.
    """
    collected = Collected()
    seen = set()

    for path in paths:
        matches = _expand(path)
        if not matches:
            collected.skipped.append(f"{path} — nothing matched")
            continue

        for match in matches:
            resolved = match.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)

            if not resolved.is_file():
                collected.skipped.append(f"{match} — not a file")
                continue
            if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
                collected.skipped.append(f"{match.name} — {resolved.suffix or 'no extension'} not supported")
                continue

            size = resolved.stat().st_size
            if size == 0:
                collected.skipped.append(f"{match.name} — empty")
                continue
            if size > MAX_FILE_BYTES:
                collected.skipped.append(
                    f"{match.name} — {size / 1024 / 1024:.0f}MB, over the 25MB limit"
                )
                continue

            collected.files.append(resolved)

    collected.files.sort()

    if limit and len(collected.files) > limit:
        for extra in collected.files[limit:]:
            collected.skipped.append(f"{extra.name} — over the {limit} file limit for one call")
        collected.files = collected.files[:limit]

    return collected


def describe_skipped(collected: Collected) -> str:
    """The list of what was left out, ready to show."""
    if not collected.skipped:
        return ""
    lines = "\n".join(f"  - {reason}" for reason in collected.skipped)
    return f"\nLeft out ({len(collected.skipped)}):\n{lines}"
