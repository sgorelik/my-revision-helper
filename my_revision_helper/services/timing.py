"""
Timing a sitting: start, pause, resume, finish.

Replaces asking a child how long something took, which is a question nobody
answers accurately at the end of a paper.

The clock is server-side and always derived rather than stored as a countdown,
because the browser cannot be trusted to stay open: a page reload, a locked
iPad, or moving to another device must not lose or alter the time. Elapsed time
is `accumulated_seconds` for the stretches already finished, plus the live
stretch since `timer_started_at` when running.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

IDLE, RUNNING, PAUSED, STOPPED = "idle", "running", "paused", "stopped"

# A forgotten timer would otherwise report a whole day of revision and distort
# every weekly total, so what gets logged is capped. The raw time is still
# visible on the assignment.
MAX_LOGGED_MINUTES = 8 * 60


class TimerError(ValueError):
    """An action that does not make sense for the timer's current state."""


@dataclass
class TimerView:
    """The timer as the frontend needs it."""

    state: str
    elapsedSeconds: int
    pauseCount: int
    startedAt: Optional[str]
    stoppedAt: Optional[str]
    loggedMinutes: Optional[int]


def elapsed_seconds(assignment, *, now: Optional[datetime] = None) -> int:
    """
    Total time spent, including the stretch currently running.

    Never trusts a stored total on its own: while the timer runs, the live
    stretch is measured from the start of it.
    """
    total = int(assignment.timer_accumulated_seconds or 0)

    if assignment.timer_state == RUNNING and assignment.timer_started_at:
        moment = now or datetime.utcnow()
        live = (moment - assignment.timer_started_at).total_seconds()
        # Clock adjustments on the server could make this negative.
        total += max(0, int(live))

    return total


def logged_minutes(assignment, *, now: Optional[datetime] = None) -> Optional[int]:
    """
    Minutes to record against the work, or None if it was never timed.

    Rounds to the nearest minute, but anything measured at all counts as one
    minute rather than zero.
    """
    if assignment.timer_state == IDLE and not assignment.timer_first_started_at:
        return None

    seconds = elapsed_seconds(assignment, now=now)
    if seconds <= 0:
        return None

    return min(max(1, round(seconds / 60)), MAX_LOGGED_MINUTES)


def view(assignment, *, now: Optional[datetime] = None) -> TimerView:
    """Serialise the timer for the API."""
    return TimerView(
        state=assignment.timer_state or IDLE,
        elapsedSeconds=elapsed_seconds(assignment, now=now),
        pauseCount=int(assignment.timer_pause_count or 0),
        startedAt=(
            assignment.timer_first_started_at.isoformat()
            if assignment.timer_first_started_at
            else None
        ),
        stoppedAt=(
            assignment.timer_stopped_at.isoformat() if assignment.timer_stopped_at else None
        ),
        loggedMinutes=logged_minutes(assignment, now=now),
    )


def start(assignment, *, now: Optional[datetime] = None) -> None:
    """
    Begin timing.

    Starting an already-running timer is ignored rather than treated as an
    error: a double tap, or two tabs open on the same paper, should not reset
    the clock or raise at the child.
    """
    moment = now or datetime.utcnow()

    if assignment.timer_state == RUNNING:
        return

    if assignment.timer_state == STOPPED:
        raise TimerError("This one has already been finished. Reset it to time it again.")

    assignment.timer_state = RUNNING
    assignment.timer_started_at = moment
    if assignment.timer_first_started_at is None:
        assignment.timer_first_started_at = moment
        assignment.timer_accumulated_seconds = 0
        assignment.timer_pause_count = 0

    # Starting work is the clearest signal there is that it is underway.
    if assignment.status == "todo":
        assignment.status = "in_progress"


def pause(assignment, *, now: Optional[datetime] = None) -> None:
    """
    Stop the clock and bank the stretch just finished.

    Pausing something already paused is ignored, so the pause count cannot be
    inflated by tapping twice.
    """
    if assignment.timer_state == PAUSED:
        return
    if assignment.timer_state != RUNNING:
        raise TimerError("The timer is not running.")

    assignment.timer_accumulated_seconds = elapsed_seconds(assignment, now=now)
    assignment.timer_started_at = None
    assignment.timer_state = PAUSED
    assignment.timer_pause_count = int(assignment.timer_pause_count or 0) + 1


def resume(assignment, *, now: Optional[datetime] = None) -> None:
    """Restart the clock after a pause without counting another pause."""
    if assignment.timer_state == RUNNING:
        return
    if assignment.timer_state != PAUSED:
        raise TimerError("The timer is not paused.")

    assignment.timer_state = RUNNING
    assignment.timer_started_at = now or datetime.utcnow()


def stop(assignment, *, now: Optional[datetime] = None) -> None:
    """
    Finish the sitting and freeze the total.

    Finishing while paused is allowed: a child who steps away and then decides
    they are done should not have to resume first.
    """
    moment = now or datetime.utcnow()

    if assignment.timer_state == STOPPED:
        return
    if assignment.timer_state == IDLE:
        raise TimerError("This one was never started.")

    assignment.timer_accumulated_seconds = elapsed_seconds(assignment, now=moment)
    assignment.timer_started_at = None
    assignment.timer_state = STOPPED
    assignment.timer_stopped_at = moment

    logger.info(
        f"Timer finished on assignment {assignment.id}: "
        f"{assignment.timer_accumulated_seconds}s over "
        f"{assignment.timer_pause_count or 0} pause(s)"
    )


def reset(assignment) -> None:
    """
    Clear the timer so the work can be timed again.

    For a mistimed sitting — started early, or left running overnight.
    """
    assignment.timer_state = IDLE
    assignment.timer_started_at = None
    assignment.timer_accumulated_seconds = 0
    assignment.timer_pause_count = 0
    assignment.timer_first_started_at = None
    assignment.timer_stopped_at = None


ACTIONS = {"start": start, "pause": pause, "resume": resume, "stop": stop}
