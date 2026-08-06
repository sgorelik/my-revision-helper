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


def _match_child(children: List[Dict[str, Any]], wanted: str) -> Dict[str, Any]:
    """
    A child from whatever they were called, out of a roster already fetched.

    Split from _resolve_child so a bulk call can fetch the roster once instead
    of once per row.
    """
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


def _resolve_child(api: RevisionHelper, wanted: str) -> Dict[str, Any]:
    """
    A child from whatever they were called.

    Accepts the id or the name, because an assistant is told "upload this for
    Yuri", never "for 42753c30-a0c5-48c1".
    """
    return _match_child(api.children(), wanted)


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

    awaiting = progress.get("needsReviewCount") or 0
    if awaiting:
        lines.append(
            f"- Awaiting a mark: {awaiting} "
            f"(not in the average — use list_work to see them, then update_work to score them)"
        )

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


# ---------------------------------------------------------------------------
# Correcting the record
# ---------------------------------------------------------------------------


def _match_work(items: List[Dict[str, Any]], wanted: str, whose: str) -> Dict[str, Any]:
    """One piece of work out of a record already fetched."""
    if not items:
        raise ApiError(f"{whose} has no recorded work.")

    wanted = (wanted or "").strip()
    if not wanted:
        raise ApiError("Say which piece of work, by title or id.")

    lowered = wanted.lower()
    for item in items:
        if item["id"] == wanted or item.get("markingId") == wanted:
            return item
        if item["title"].lower() == lowered:
            return item

    partial = [item for item in items if lowered in item["title"].lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        titles = ", ".join(
            f"{item['title']!r} ({item.get('doneOn', '')[:10]})" for item in partial[:6]
        )
        raise ApiError(f"More than one piece of work matches {wanted!r}: {titles}")

    raise ApiError(f"Nothing called {wanted!r} on {whose}'s record. Try list_work.")


def _resolve_work(api: RevisionHelper, child: str, wanted: str) -> Dict[str, Any]:
    """
    A piece of work from its id, or from what it is called.

    Titles are how anyone refers to a paper out loud, so an assistant asked to
    "fix the mark on the fractions worksheet" can find it without an id.
    """
    found = _resolve_child(api, child)
    return _match_work(api.work(found["id"]), wanted, found["name"])


def _describe(item: Dict[str, Any]) -> str:
    """One line describing a piece of work, as a person would read it."""
    when = (item.get("doneOn") or "")[:10]
    if item.get("status") == "needs_review":
        score = "awaiting a mark"
    elif item.get("percentage") is not None:
        score = f"{round(item['percentage'])}%"
        if item.get("marksAvailable"):
            score += f" ({item.get('marksAwarded')}/{item['marksAvailable']})"
    else:
        score = "no score"

    return f"{item['title']} — {item['subject']}, {when or 'no date'}, {score}"


@mcp.tool()
def list_work(child: str, needs_review_only: bool = False) -> str:
    """
    A child's recorded work, newest first, with the ids needed to change it.

    Set needs_review_only to see just the work the app could not mark, which is
    sitting outside the average until someone scores it.
    """
    api = _api()
    try:
        found = _resolve_child(api, child)
        items = api.work(found["id"], needs_review_only=needs_review_only)
    except Exception as e:
        return _fail(e)

    if not items:
        return (
            f"{found['name']} has nothing waiting for a mark."
            if needs_review_only
            else f"{found['name']} has no recorded work yet."
        )

    lines = [f"{found['name']} — {len(items)} piece(s) of work:"]
    for item in items:
        lines.append(f"- {_describe(item)}")
        lines.append(f"    id: {item['id']}")
        if item.get("reviewReason"):
            lines.append(f"    why it needs a look: {item['reviewReason']}")

    return "\n".join(lines)


@mcp.tool()
def update_work(
    child: str,
    work: str,
    marks_awarded: Optional[float] = None,
    marks_available: Optional[float] = None,
    title: str = "",
    subject: str = "",
    done_on: str = "",
    minutes_spent: Optional[int] = None,
    note: str = "",
) -> str:
    """
    Correct one piece of work: its mark, what it is called, or when it was done.

    Use this when the auto-marker got a paper wrong, or to score work it could
    not read. Identify the work by title or id; `child` narrows the search.
    A mark set here is taken as final and counts towards the average.

    To put several right at once, use correct_marks instead.
    """
    api = _api()
    try:
        item = _resolve_work(api, child, work)
        updated = api.update_work(
            item["id"],
            marksAwarded=marks_awarded,
            marksAvailable=marks_available,
            title=title,
            subject=subject,
            doneOn=done_on,
            minutesSpent=minutes_spent,
            note=note,
        )
    except Exception as e:
        return _fail(e)

    return f"Updated: {_describe(updated)}"


@mcp.tool()
def delete_work(child: str, work: str) -> str:
    """
    Take one piece of work off a child's record.

    Removes it from the averages and the charts immediately. It is recoverable
    with restore_work, so a wrong entry does not mean rebuilding the child.
    """
    api = _api()
    try:
        item = _resolve_work(api, child, work)
        api.delete_work(item["id"])
    except Exception as e:
        return _fail(e)

    return (
        f"Removed {item['title']!r} from the record. "
        f"Undo with restore_work using id {item['id']}."
    )


@mcp.tool()
def restore_work(child: str, work_id: str) -> str:
    """Put back a piece of work that was taken off the record."""
    api = _api()
    try:
        _resolve_child(api, child)  # So an unknown name fails clearly.
        restored = api.restore_work(work_id)
    except Exception as e:
        return _fail(e)

    return f"Put back: {_describe(restored)}"


@mcp.tool()
def move_work(work: str, from_child: str, to_child: str) -> str:
    """
    Move a piece of work to a different child.

    For work logged against the wrong one. Both children's figures are worked
    out again.
    """
    api = _api()
    try:
        item = _resolve_work(api, from_child, work)
        destination = _resolve_child(api, to_child)
        api.move_work(item["id"], destination["id"])
    except Exception as e:
        return _fail(e)

    return f"Moved {item['title']!r} to {destination['name']}."


@mcp.tool()
def rename_child(child: str, name: str = "", year_group: str = "", emoji: str = "", colour: str = "") -> str:
    """
    Change a child's name, year group, emoji or colour.

    Saves having to create a second student to fix a typo.
    """
    api = _api()
    try:
        found = _resolve_child(api, child)
        updated = api.update_child(
            found["id"], name=name, yearGroup=year_group, avatarEmoji=emoji, colour=colour
        )
    except Exception as e:
        return _fail(e)

    return f"Updated: {updated['name']}" + (
        f" ({updated['yearGroup']})" if updated.get("yearGroup") else ""
    )


# ---------------------------------------------------------------------------
# Doing a whole week at once
# ---------------------------------------------------------------------------

# Enough for a fortnight of both children's work, while still small enough that
# a failure part way through is easy to read and put right.
MAX_ROWS_PER_CALL = 40


class RowError(Exception):
    """A single row was wrong. The rest of the batch carries on."""


def _text(row: Dict[str, Any], *names: str) -> str:
    """A string field under any of the names an assistant might use for it."""
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _number(row: Dict[str, Any], *names: str) -> Optional[float]:
    """A numeric field, refusing rather than guessing at nonsense."""
    for name in names:
        value = row.get(name)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            raise RowError(f"{name} should be a number, not {value!r}")
    return None


def _whole(row: Dict[str, Any], *names: str) -> Optional[int]:
    value = _number(row, *names)
    return None if value is None else int(value)


def _report(heading: str, done: List[str], failed: List[str]) -> str:
    """One readable summary of a batch, saying plainly what did not happen."""
    lines = [heading]
    lines += [f"  ✓ {line}" for line in done]
    lines += [f"  ✗ {line}" for line in failed]

    if failed:
        lines.append(
            f"{len(done)} of {len(done) + len(failed)} went through. "
            "The rest were left alone — fix those and send them again."
        )
    return "\n".join(lines)


@mcp.tool()
def record_results(results: List[Dict[str, Any]], child: str = "") -> str:
    """
    Record a batch of already-marked work in one go. The quickest way to catch
    the app up on a week of paper worksheets.

    Each row in `results` is one piece of work:
      - title: what it was, e.g. "Level 2 calculator paper"     (required)
      - subject: e.g. "Maths"                                    (required)
      - marks_awarded and marks_available: the score, e.g. 41 and 50
      - done_on: ISO date, e.g. "2026-08-03". Defaults to today.
      - minutes_spent: how long it took
      - note: anything worth remembering
      - child: whose it is, if the batch covers more than one

    `child` sets the default for rows that do not name one, so a single call
    can cover both children.

    Nothing is scanned or marked here — the scores are taken as given and go
    straight onto the progress chart. To have the app mark a scan, use
    hand_in_work.

    A row that is wrong is reported and skipped; the others still go in.
    """
    if not results:
        return "Nothing to record."
    if len(results) > MAX_ROWS_PER_CALL:
        return (
            f"That is {len(results)} rows; {MAX_ROWS_PER_CALL} is the most in one call. "
            "Send it in batches."
        )

    api = _api()
    try:
        roster = api.children()
    except Exception as e:
        return _fail(e)

    done: List[str] = []
    failed: List[str] = []

    for index, row in enumerate(results, start=1):
        label = _text(row, "title") or f"row {index}"
        try:
            if not isinstance(row, dict):
                raise RowError("each result should be an object with a title and a subject")

            title = _text(row, "title")
            subject = _text(row, "subject")
            if not title:
                raise RowError("no title")
            if not subject:
                raise RowError("no subject")

            awarded = _number(row, "marks_awarded", "marksAwarded", "score")
            available = _number(row, "marks_available", "marksAvailable", "out_of")
            minutes = _whole(row, "minutes_spent", "minutesSpent", "minutes")

            if awarded is not None and available is None:
                raise RowError("a score needs the total it was out of")
            if awarded is None and available is not None:
                raise RowError("a total needs a score to go with it")
            if awarded is None and minutes is None:
                raise RowError("give a score, or the time it took — otherwise there is nothing to record")

            whose = _match_child(roster, _text(row, "child", "student") or child)

            api.hand_in(
                child_id=whose["id"],
                subject=subject,
                title=title,
                note=_text(row, "note"),
                done_on=_text(row, "done_on", "doneOn", "date"),
                minutes_spent=minutes,
                marks_awarded=awarded,
                marks_available=available,
                save_to_library=False,
            )
        except Exception as e:
            failed.append(f"{label} — {e}")
            continue

        scored = f"{awarded:g}/{available:g}" if awarded is not None else "no score"
        done.append(f"{title} ({whose['name']}, {subject}, {scored})")

    return _report(f"Recorded {len(done)} piece(s) of work:", done, failed)


@mcp.tool()
def correct_marks(corrections: List[Dict[str, Any]], child: str = "") -> str:
    """
    Put several marks right in one go, for when the auto-marker has been wrong
    across a batch of papers.

    Each row in `corrections` names one piece of work and what to change:
      - work: its title or id, e.g. "fractions worksheet"        (required)
      - marks_awarded and marks_available: the corrected score
      - subject, done_on, minutes_spent, note: to fix those too
      - new_title: to rename it. `work` always means the current title.
      - child: whose it is, if the batch covers more than one

    Marks set here are final and count towards the average, so this is also how
    to score work the app could not read. Use list_work first to see the titles.

    A row that cannot be found is reported and skipped; the others still apply.
    """
    if not corrections:
        return "Nothing to correct."
    if len(corrections) > MAX_ROWS_PER_CALL:
        return (
            f"That is {len(corrections)} rows; {MAX_ROWS_PER_CALL} is the most in one call. "
            "Send it in batches."
        )

    api = _api()
    try:
        roster = api.children()
    except Exception as e:
        return _fail(e)

    # One fetch per child, however many of their papers the batch touches.
    records: Dict[str, List[Dict[str, Any]]] = {}
    done: List[str] = []
    failed: List[str] = []

    for index, row in enumerate(corrections, start=1):
        label = _text(row, "work", "title") or f"row {index}"
        try:
            if not isinstance(row, dict):
                raise RowError("each correction should be an object naming the work to change")

            wanted = _text(row, "work", "work_id", "id", "title")
            if not wanted:
                raise RowError("say which piece of work")

            whose = _match_child(roster, _text(row, "child", "student") or child)
            if whose["id"] not in records:
                records[whose["id"]] = api.work(whose["id"])

            item = _match_work(records[whose["id"]], wanted, whose["name"])

            updated = api.update_work(
                item["id"],
                marksAwarded=_number(row, "marks_awarded", "marksAwarded", "score"),
                marksAvailable=_number(row, "marks_available", "marksAvailable", "out_of"),
                title=_text(row, "new_title", "rename_to"),
                subject=_text(row, "subject"),
                doneOn=_text(row, "done_on", "doneOn", "date"),
                minutesSpent=_whole(row, "minutes_spent", "minutesSpent", "minutes"),
                note=_text(row, "note"),
            )
        except Exception as e:
            failed.append(f"{label} — {e}")
            continue

        done.append(f"{whose['name']}: {_describe(updated)}")

    return _report(f"Corrected {len(done)} piece(s) of work:", done, failed)


@mcp.tool()
def work_needing_marks() -> str:
    """
    Everything across all the children that is waiting for a mark.

    Work the app could not read is recorded as done but left without a score,
    so it stays out of the averages. This is the list of what to go and score,
    which correct_marks can then do in one call.
    """
    api = _api()
    try:
        roster = api.children()
    except Exception as e:
        return _fail(e)

    lines: List[str] = []
    total = 0
    for whose in roster:
        try:
            items = api.work(whose["id"], needs_review_only=True)
        except Exception as e:
            lines.append(f"{whose['name']}: could not be read — {e}")
            continue

        if not items:
            continue

        total += len(items)
        lines.append(f"{whose['name']}:")
        for item in items:
            out_of = item.get("marksAvailable")
            lines.append(
                f"  - {item['title']} ({item['subject']}, {(item.get('doneOn') or '')[:10]})"
                + (f", out of {out_of:g}" if out_of else "")
            )
            if item.get("reviewReason"):
                lines.append(f"      {item['reviewReason']}")

    if not total:
        return "Nothing is waiting for a mark."

    return (
        f"{total} piece(s) waiting for a mark, not counted in any average:\n"
        + "\n".join(lines)
        + "\n\nScore them with correct_marks, naming each by its title."
    )


def main() -> None:
    """Run over stdio, which is how a desktop client starts it."""
    mcp.run()


if __name__ == "__main__":
    main()
