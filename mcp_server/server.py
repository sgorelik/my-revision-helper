"""
The revision helper as an MCP server.

Lets an assistant load a term's worth of papers, hand in work that was done on
paper, put work on a child's plan and read back how they are getting on —
without any of it going through the browser one file at a time.

Runs on this machine over stdio, reads the files named to it from this disk,
and talks to the deployed app as the account the personal access token belongs
to. Configure with:

    REVISION_HELPER_URL     the app, defaulting to the Railway deployment
    REVISION_HELPER_TOKEN   the personal access token (API_TOKEN on the server)
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from .api import ApiError, RevisionHelper
from .files import collect_files, describe_skipped

# stdout carries the protocol on stdio, so logs go the other way.
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("revision-helper-mcp")

mcp = FastMCP("revision-helper")

# Each paper is parsed by a model as it lands, so a big drop is slow. Enough
# for a week of work in one go, and the caller is told to come back for more.
MAX_FILES_PER_CALL = 12


def _api() -> RevisionHelper:
    return RevisionHelper()


def _resolve_child(api: RevisionHelper, wanted: str) -> Dict[str, Any]:
    """
    A child from whatever they were called.

    Accepts the id or the name, because an assistant is told "upload this for
    Yuri", never "for 42753c30-a0c5-48c1".
    """
    children = api.children()
    if not children:
        raise ApiError("There are no children set up in the app yet.")

    wanted = (wanted or "").strip()
    if not wanted:
        if len(children) == 1:
            return children[0]
        names = ", ".join(child["name"] for child in children)
        raise ApiError(f"Say which child this is for: {names}")

    lowered = wanted.lower()
    for child in children:
        if child["id"] == wanted or child["name"].lower() == lowered:
            return child

    partial = [child for child in children if lowered in child["name"].lower()]
    if len(partial) == 1:
        return partial[0]

    names = ", ".join(child["name"] for child in children)
    raise ApiError(f"No child called {wanted!r}. There is: {names}")


def _resolve_paper(api: RevisionHelper, wanted: str) -> Dict[str, Any]:
    """A library paper from its id or its title."""
    papers = api.papers(limit=200)
    wanted = (wanted or "").strip()
    lowered = wanted.lower()

    for paper in papers:
        if paper["id"] == wanted or paper["title"].lower() == lowered:
            return paper

    partial = [paper for paper in papers if lowered and lowered in paper["title"].lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        titles = ", ".join(f"{paper['title']!r}" for paper in partial[:6])
        raise ApiError(f"More than one paper matches {wanted!r}: {titles}")

    raise ApiError(f"No paper matches {wanted!r}. Use list_papers to see what is there.")


def _fail(e: Exception) -> str:
    """Errors come back as readable text, so the assistant can pass them on."""
    logger.warning(f"tool failed: {e}")
    return f"Failed: {e}"


@mcp.tool()
def check_connection() -> str:
    """
    Check the MCP server can reach the app and is recognised as the right account.

    Worth running first if anything else behaves as though the data is missing.
    """
    api = _api()
    try:
        if not api.token:
            return (
                "No REVISION_HELPER_TOKEN is set, so the app would treat this as a "
                "stranger and none of your children or papers would be visible."
            )
        who = api.whoami()
        if not who.get("authenticated"):
            return (
                f"Reached {api.base_url}, but the token was not accepted. Check API_TOKEN "
                "on the server matches REVISION_HELPER_TOKEN here, and that "
                "API_TOKEN_USER_ID is set to your Auth0 user id."
            )
        children = api.children()
        names = ", ".join(child["name"] for child in children) or "nobody yet"
        return f"Connected to {api.base_url} as {who.get('user_id')}. Children: {names}."
    except Exception as e:
        return _fail(e)


@mcp.tool()
def list_children() -> str:
    """List the children set up in the app, with their year groups."""
    try:
        children = _api().children()
        if not children:
            return "No children are set up yet."
        return "\n".join(
            f"- {child['name']}"
            + (f" ({child['yearGroup']})" if child.get("yearGroup") else "")
            + f" — id {child['id']}"
            for child in children
        )
    except Exception as e:
        return _fail(e)


@mcp.tool()
def list_papers(subject: str = "") -> str:
    """
    List what is already in the paper library, optionally filtered by subject.

    Use before uploading to avoid adding the same paper twice.
    """
    try:
        papers = _api().papers(subject=subject)
        if not papers:
            return f"No papers{f' for {subject}' if subject else ''} yet."
        lines = []
        for paper in papers:
            bits = [f"- {paper['title']} ({paper['subject']}"]
            if paper.get("weekLabel"):
                bits.append(f", {paper['weekLabel']}")
            bits.append(f") — {paper.get('questionCount', 0)} questions")
            if paper.get("hasAnswerKey"):
                bits.append(", answer key")
            lines.append("".join(bits))
        return f"{len(papers)} paper(s):\n" + "\n".join(lines)
    except Exception as e:
        return _fail(e)


@mcp.tool()
def upload_papers(
    paths: List[str],
    subject: str = "",
    week_label: str = "",
    year_group: str = "",
    paper_type: str = "workbook",
) -> str:
    """
    Add papers and worksheets to the library, in bulk.

    Each path may be a file, a folder (searched right through), or a pattern
    like ~/Downloads/*.pdf. Leave subject empty to have it guessed from each
    filename, which works when they are named like Maths_Week1_Workbook.docx.

    Every document is parsed into questions as it lands, and an answer key at
    the back is split off and hidden from the child. Files are handled one at a
    time, so a document that cannot be read does not stop the rest.
    """
    collected = collect_files(paths, limit=MAX_FILES_PER_CALL)
    if collected.is_empty:
        return f"Nothing to upload.{describe_skipped(collected)}"

    api = _api()
    lines: List[str] = []
    succeeded = failed = 0

    # In small batches: one request per file is slow to start up, and one
    # request for everything risks timing out with nothing to show for it.
    batch_size = 3
    for start in range(0, len(collected.files), batch_size):
        batch = collected.files[start : start + batch_size]
        try:
            result = api.upload_papers(
                batch,
                subject=subject,
                week_label=week_label,
                year_group=year_group,
                paper_type=paper_type,
            )
        except Exception as e:
            failed += len(batch)
            for path in batch:
                lines.append(f"  ✗ {path.name} — {e}")
            continue

        for item in result.get("items", []):
            if item["status"] == "ok":
                succeeded += 1
                paper = item.get("paper") or {}
                detail = f"{paper.get('questionCount', 0)} questions"
                if paper.get("hasAnswerKey"):
                    detail += ", answer key hidden"
                lines.append(f"  ✓ {paper.get('title') or item['filename']} — {detail}")
            else:
                failed += 1
                lines.append(f"  ✗ {item['filename']} — {item.get('error')}")

    summary = f"Added {succeeded} paper(s) to the library"
    if failed:
        summary += f", {failed} failed"
    return f"{summary}:\n" + "\n".join(lines) + describe_skipped(collected)


@mcp.tool()
def hand_in_work(
    child: str,
    subject: str,
    paths: Optional[List[str]] = None,
    title: str = "",
    done_on: str = "",
    minutes_spent: Optional[int] = None,
    marks_awarded: Optional[float] = None,
    marks_available: Optional[float] = None,
    note: str = "",
    save_to_library: bool = True,
) -> str:
    """
    Hand in work that was never assigned, and have it marked.

    For work done away from the app: a worksheet done on paper, an exercise set
    in class. An assignment and a completion are created after the fact, dated
    to done_on (an ISO date, defaulting to today) so it counts in the right week.

    Send a scan in paths and it is marked question by question — this works
    without the original paper as long as the questions are visible next to the
    answers. The blank worksheet is then kept in the library for the other
    child, with the answers stripped out, unless save_to_library is false.

    Send no files to record work you are not scanning. Give marks_awarded and
    marks_available if you marked it yourself, and that score is used as it
    stands and reaches the progress chart.

    A scan of a long paper takes several minutes to come back.
    """
    api = _api()
    try:
        found = _resolve_child(api, child)
    except Exception as e:
        return _fail(e)

    collected = collect_files(paths or [], limit=MAX_FILES_PER_CALL)
    if paths and collected.is_empty:
        return f"None of those files could be sent.{describe_skipped(collected)}"

    try:
        result = api.hand_in(
            child_id=found["id"],
            subject=subject,
            files=collected.files,
            title=title,
            note=note,
            done_on=done_on,
            minutes_spent=minutes_spent,
            marks_awarded=marks_awarded,
            marks_available=marks_available,
            save_to_library=save_to_library,
        )
    except Exception as e:
        return _fail(e)

    lines = [f"Recorded “{result['title']}” for {found['name']}."]

    marking = result.get("marking")
    if marking:
        awarded, available = marking.get("marksAwarded"), marking.get("marksAvailable")
        percentage = marking.get("percentage")
        lines.append(
            f"Marked {awarded}/{available}"
            + (f" ({percentage}%)" if percentage is not None else "")
            + (" by you" if marking.get("markedBy") == "parent" else " by the app")
        )
        weak = marking.get("weakTopics") or []
        if weak:
            lines.append(f"Weak topics: {', '.join(weak[:8])}")
    else:
        lines.append("Counted as done. Nothing was marked — no scan and no score.")

    if result.get("savedToLibrary"):
        lines.append(
            f"Kept the blank worksheet in the library ({result.get('questionCount')} questions), "
            "answers stripped out."
        )

    return "\n".join(lines) + describe_skipped(collected)


@mcp.tool()
def assign_work(
    child: str,
    title: str = "",
    subject: str = "",
    paper: str = "",
    due_date: str = "",
    scheduled_date: str = "",
    instructions: str = "",
    estimated_minutes: Optional[int] = None,
) -> str:
    """
    Put work on a child's plan.

    Give paper (an id or a title from the library) to set a paper to be handed
    in and marked. Leave it empty and give a title instead for work that is
    just checked off, like "read two chapters".

    scheduled_date is the day to do it, due_date the deadline; both are ISO
    dates and they can differ.
    """
    api = _api()
    try:
        found = _resolve_child(api, child)

        paper_id = None
        if paper:
            match = _resolve_paper(api, paper)
            paper_id = match["id"]
            title = title or match["title"]
            subject = subject or match["subject"]

        if not title:
            return "Failed: give a title, or a paper to assign."
        if not subject:
            return "Failed: give a subject."

        api.assign(
            child_id=found["id"],
            title=title,
            subject=subject,
            paper_id=paper_id,
            due_date=due_date,
            scheduled_date=scheduled_date,
            instructions=instructions,
            estimated_minutes=estimated_minutes,
        )
    except Exception as e:
        return _fail(e)

    when = scheduled_date or due_date
    return (
        f"Assigned “{title}” ({subject}) to {found['name']}"
        + (f" for {when}" if when else "")
        + ("." if paper_id else " — to be checked off rather than marked.")
    )


@mcp.tool()
def get_progress(child: str) -> str:
    """
    How a child is getting on: work done, average score, time, and weak topics.
    """
    api = _api()
    try:
        found = _resolve_child(api, child)
        progress = api.progress(found["id"])
    except Exception as e:
        return _fail(e)

    average = progress.get("averagePercentage")
    streak = progress.get("streakDays") or 0
    lines = [
        f"{found['name']}:",
        f"- Work done: {progress.get('assignmentsDone')}/{progress.get('assignmentsTotal')}"
        + (f", {progress['assignmentsOverdue']} overdue" if progress.get("assignmentsOverdue") else ""),
        f"- Average score: {round(average) if average is not None else '—'}%",
        f"- Time this week: {progress.get('minutesLoggedThisWeek')} min",
        f"- Streak: {streak} day{'' if streak == 1 else 's'}",
    ]

    weak = [topic["topic"] for topic in progress.get("weakTopics", [])][:8]
    if weak:
        lines.append(f"- Weak topics: {', '.join(weak)}")

    subjects = progress.get("subjects") or []
    if subjects:
        lines.append("- By subject:")
        for entry in subjects:
            latest = entry.get("latestScore")
            gap = entry.get("gapToAverage")
            lines.append(
                f"    {entry['subject']}: "
                + (f"{round(latest)}%" if latest is not None else "no score yet")
                + (f", {gap:+.0f} vs year average" if gap is not None else "")
            )

    return "\n".join(lines)


def main() -> None:
    """Run over stdio, which is how a desktop client starts it."""
    mcp.run()


if __name__ == "__main__":
    main()
