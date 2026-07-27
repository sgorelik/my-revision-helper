#!/usr/bin/env python3
"""
Load a child's study programme into the app.

Reads the tracker spreadsheet (baselines, weekly timetable, time split), the
plan document (rationale), and any number of workbooks, then creates the child,
their subject baselines, their timetable, the paper library and the first
week's assignments.

Usage:

    python import_study_plan.py --name Yuri --owner parent@example.com \\
        --tracker  ~/Downloads/Yuri_Study_Tracker.xlsx \\
        --plan     ~/Downloads/Yuri_Summer_Study_Plan.docx \\
        --workbook ~/Downloads/Maths_Week1_Workbook.docx \\
        --workbook ~/Downloads/Physics_Week1_Workbook.docx \\
        --year-group "5th Form"

Or point it at a folder of workbooks:

    python import_study_plan.py --name Yuri --tracker t.xlsx --workbooks-dir ./week1

Everything is imported into one parent account, since that is what the app
filters on when it serves the data. With a single account in the database the
--owner flag can be left off.

Re-running for the same child updates their baselines and plan rather than
creating a duplicate. Papers already in the library are not uploaded twice.
Pass --assign-week to also hand out assignments for the coming week.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

WORKBOOK_SUFFIXES = {".docx", ".pdf", ".pptx", ".txt", ".md"}


def fail(message: str) -> None:
    print(f"❌ {message}")
    sys.exit(1)


def resolve_owner(db, requested: Optional[str], session_id: Optional[str]):
    """
    Work out which account the imported programme belongs to.

    Everything the app serves is filtered by owner, so an import with no owner
    is invisible in the UI. Anonymous sessions are no help here — their id is a
    per-browser cookie — so in practice the owner is the parent's Auth0 account.

    Accepts an Auth0 user id or an email address. With neither, a database
    holding exactly one account uses it, since that is the single-family case.
    """
    from my_revision_helper.models_db import User

    if session_id:
        return {"user_id": None, "session_id": session_id}

    if requested:
        user = (
            db.query(User)
            .filter((User.id == requested) | (User.email == requested))
            .first()
        )
        if user:
            return {"user_id": user.id, "session_id": None}
        if "@" in requested:
            fail(
                f"No account found for {requested}. Sign in to the app once, then "
                f"re-run with that email."
            )
        # A raw Auth0 id for an account that has not signed in yet is still
        # usable: the users row is created on their first write anyway.
        return {"user_id": requested, "session_id": None}

    users = db.query(User).all()
    if len(users) == 1:
        owner = users[0]
        print(f"   Importing into the only account present: {owner.email or owner.id}")
        return {"user_id": owner.id, "session_id": None}

    if not users:
        fail(
            "No accounts exist yet, so there is nobody to import for. Sign in to "
            "the app once, then re-run with --owner <your email>."
        )

    listed = ", ".join(u.email or u.id for u in users[:10])
    fail(f"Several accounts exist — choose one with --owner. Found: {listed}")


def extract_text(path: Path) -> Optional[str]:
    """Extract text from a document by suffix, without going through FastAPI."""
    from my_revision_helper.file_processing import _docx_text_from_bytes, _xlsx_text_from_bytes

    raw = path.read_bytes()
    suffix = path.suffix.lower()

    if suffix == ".docx":
        return _docx_text_from_bytes(raw)
    if suffix == ".xlsx":
        return _xlsx_text_from_bytes(raw)
    if suffix in {".txt", ".md"}:
        return raw.decode("utf-8", errors="replace")
    if suffix == ".pdf":
        try:
            import pdfplumber
            from io import BytesIO

            with pdfplumber.open(BytesIO(raw)) as pdf:
                return "\n\n".join(p.extract_text() or "" for p in pdf.pages).strip()
        except Exception as e:
            print(f"   ⚠️  Could not read {path.name}: {e}")
            return None

    print(f"   ⚠️  Unsupported file type: {path.name}")
    return None


def guess_subject(path: Path, text: str) -> str:
    """Infer a workbook's subject from its filename, then its opening line."""
    from my_revision_helper.subjects import CANONICAL_SUBJECTS, normalise_subject

    stem = path.stem.lower()
    for candidate in CANONICAL_SUBJECTS + ["maths", "chem", "bio", "phys"]:
        if candidate.lower().split()[0] in stem:
            return normalise_subject(candidate) or "Other"

    first_line = (text or "").split("\n")[0]
    for candidate in CANONICAL_SUBJECTS:
        if candidate.lower() in first_line.lower():
            return candidate

    return "Other"


def guess_week_label(path: Path) -> Optional[str]:
    """Pull a 'Week N' label out of a filename."""
    import re

    match = re.search(r"week\s*_?(\d+)", path.stem, re.I)
    return f"Week {match.group(1)}" if match else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a study programme")
    parser.add_argument("--name", required=True, help="Child's name")
    parser.add_argument("--year-group", default=None)
    parser.add_argument("--school", default=None)
    parser.add_argument("--colour", default="orange")
    parser.add_argument("--emoji", default=None)
    parser.add_argument("--tracker", default=None, help="Tracker .xlsx")
    parser.add_argument("--plan", default=None, help="Study plan .docx")
    parser.add_argument("--workbook", action="append", default=[], help="Workbook (repeatable)")
    parser.add_argument("--workbooks-dir", default=None, help="Folder of workbooks")
    parser.add_argument("--plan-title", default=None)
    parser.add_argument(
        "--owner",
        default=None,
        help="Parent account to import into: Auth0 user id or email. "
        "Defaults to the only account in the database.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Import into an anonymous browser session instead of an account",
    )
    parser.add_argument(
        "--assign-week",
        action="store_true",
        help="Create assignments for the coming week from the timetable",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip the AI parse of workbooks and use the built-in parser only",
    )
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL"):
        fail("DATABASE_URL is not set. Point it at your database and try again.")

    from my_revision_helper.database import SessionLocal, init_db
    from my_revision_helper.llm import get_openai_client, get_reasoning_model
    from my_revision_helper.models_db import (
        Assignment,
        Child,
        ChildSubject,
        Paper,
        PaperQuestion,
        ScoreLogEntry,
    )
    from my_revision_helper.routers.children import create_plan_with_blocks
    from my_revision_helper.services.file_store import store_bytes
    from my_revision_helper.services.paper_parser import guess_title, parse_paper
    from my_revision_helper.services.plan_importer import import_programme, parse_focus_topics

    init_db()
    if not SessionLocal:
        fail("Could not connect to the database.")

    db = SessionLocal()

    try:
        print("=" * 70)
        print(f"Importing study programme for {args.name}")
        print("=" * 70)
        print()

        owner = resolve_owner(db, args.owner, args.session_id)

        # --- the child ----------------------------------------------------
        # Scoped to the owner so two families can each have a child of the
        # same name without colliding.
        child = (
            db.query(Child)
            .filter(
                Child.name == args.name,
                Child.user_id == owner["user_id"],
                Child.session_id == owner["session_id"],
            )
            .first()
        )
        if child:
            print(f"\n✓ Found existing child: {child.name} ({child.id})")
        else:
            child = Child(
                id=str(uuid.uuid4()),
                **owner,
                name=args.name,
                year_group=args.year_group,
                school=args.school,
                colour=args.colour,
                avatar_emoji=args.emoji,
                is_active=True,
            )
            db.add(child)
            db.commit()
            db.refresh(child)
            print(f"\n✓ Created child: {child.name} ({child.id})")

        if args.year_group and not child.year_group:
            child.year_group = args.year_group
            db.commit()

        # --- tracker and plan ---------------------------------------------
        tracker_text = None
        if args.tracker:
            tracker_path = Path(args.tracker).expanduser()
            if not tracker_path.exists():
                fail(f"Tracker not found: {tracker_path}")
            tracker_text = extract_text(tracker_path)
            print(f"✓ Read tracker: {tracker_path.name}")

        plan_text = None
        if args.plan:
            plan_path = Path(args.plan).expanduser()
            if not plan_path.exists():
                fail(f"Plan not found: {plan_path}")
            plan_text = extract_text(plan_path)
            print(f"✓ Read plan: {plan_path.name}")

        programme = import_programme(tracker_text, plan_text)
        for warning in programme.warnings:
            print(f"   ⚠️  {warning}")

        # --- subject baselines --------------------------------------------
        # A subject can appear more than once in the score log (Maths has a
        # calculator and a non-calculator paper). Average them for the baseline
        # and keep every row in the score log.
        by_subject: Dict[str, List] = {}
        for entry in programme.scores:
            by_subject.setdefault(entry.subject, []).append(entry)

        if by_subject:
            print(f"\nSubject baselines ({len(by_subject)}):")

        priority = len(by_subject)
        ordered = sorted(
            by_subject.items(),
            key=lambda item: min(
                (e.score_pct - e.year_average_pct)
                for e in item[1]
                if e.score_pct is not None and e.year_average_pct is not None
            )
            if any(e.year_average_pct is not None for e in item[1])
            else 999,
        )

        for subject, entries in ordered:
            scores = [e.score_pct for e in entries if e.score_pct is not None]
            averages = [e.year_average_pct for e in entries if e.year_average_pct is not None]
            baseline = round(sum(scores) / len(scores), 1) if scores else None
            year_average = round(sum(averages) / len(averages), 1) if averages else None

            topics: List[str] = []
            for entry in entries:
                for topic in parse_focus_topics(entry.notes):
                    if topic not in topics:
                        topics.append(topic)

            row = (
                db.query(ChildSubject)
                .filter(ChildSubject.child_id == child.id, ChildSubject.subject == subject)
                .first()
            )
            if not row:
                row = ChildSubject(id=str(uuid.uuid4()), child_id=child.id, subject=subject)
                db.add(row)

            row.baseline_score = baseline
            row.year_average = year_average
            # Aim at the year average as the first target; that is the gap the
            # plan is explicitly trying to close.
            row.target_score = year_average
            row.weekly_minutes = programme.weekly_minutes.get(subject, 0)
            row.priority = priority
            row.focus_topics = topics
            row.report_notes = "; ".join(
                e.notes for e in entries if e.notes
            ) or None
            row.is_active = True
            priority -= 1

            gap = f"{baseline - year_average:+.0f}" if baseline and year_average else "n/a"
            print(
                f"   {subject:16} {baseline}% vs {year_average}% (gap {gap})  "
                f"{row.weekly_minutes} min/wk  {len(topics)} focus topic(s)"
            )

            # Score log: one row per test, skipping any already recorded.
            for entry in entries:
                exists = (
                    db.query(ScoreLogEntry)
                    .filter(
                        ScoreLogEntry.child_id == child.id,
                        ScoreLogEntry.subject == subject,
                        ScoreLogEntry.label == entry.label,
                    )
                    .first()
                )
                if exists:
                    continue
                db.add(
                    ScoreLogEntry(
                        id=str(uuid.uuid4()),
                        child_id=child.id,
                        subject=subject,
                        label=entry.label,
                        score_pct=entry.score_pct,
                        year_average_pct=entry.year_average_pct,
                        source="report",
                        notes=entry.notes,
                        recorded_at=datetime.utcnow(),
                    )
                )

        db.commit()

        # --- weekly plan ---------------------------------------------------
        if programme.blocks:
            plan = create_plan_with_blocks(
                db,
                child_id=child.id,
                title=args.plan_title or f"{args.name}'s study plan",
                summary=programme.plan_summary,
                source_text=plan_text,
                weekly_minutes_target=programme.weekly_minutes_target,
                days_per_week=programme.days_per_week,
                start_date=datetime.utcnow(),
                blocks=[
                    {
                        "dayOfWeek": b.day_of_week,
                        "blockIndex": b.block_index,
                        "subject": b.subject,
                        "focus": b.focus,
                        "plannedMinutes": b.planned_minutes,
                        "weekCycle": b.week_cycle,
                    }
                    for b in programme.blocks
                ],
            )
            print(
                f"\n✓ Created plan '{plan.title}': {len(programme.blocks)} blocks, "
                f"{programme.weekly_minutes_target} min/week"
            )

        # --- workbooks -----------------------------------------------------
        paths: List[Path] = [Path(p).expanduser() for p in args.workbook]
        if args.workbooks_dir:
            directory = Path(args.workbooks_dir).expanduser()
            if not directory.is_dir():
                fail(f"Not a directory: {directory}")
            paths.extend(
                sorted(
                    p
                    for p in directory.iterdir()
                    if p.is_file() and p.suffix.lower() in WORKBOOK_SUFFIXES
                )
            )

        client = None if args.no_ai else get_openai_client()
        model = get_reasoning_model() if client else None
        if paths and not client:
            print("\n   ℹ️  No OpenAI key in use — parsing workbooks with the built-in parser.")

        imported_papers: List[Paper] = []
        if paths:
            print(f"\nWorkbooks ({len(paths)}):")

        for path in paths:
            if not path.exists():
                print(f"   ⚠️  Not found: {path}")
                continue

            text = extract_text(path)
            if not text:
                continue

            subject = guess_subject(path, text)
            title = guess_title(text) or path.stem

            existing = (
                db.query(Paper)
                .filter(
                    Paper.title == title,
                    Paper.subject == subject,
                    Paper.user_id == owner["user_id"],
                    Paper.session_id == owner["session_id"],
                )
                .first()
            )
            if existing:
                print(f"   • {title} — already in the library, skipping")
                imported_papers.append(existing)
                continue

            parsed = parse_paper(text, subject=subject, client=client, model=model)

            stored = store_bytes(
                db,
                content=path.read_bytes(),
                filename=path.name,
                content_type=None,
                **owner,
            )

            paper = Paper(
                id=str(uuid.uuid4()),
                **owner,
                title=title,
                subject=subject,
                paper_type="workbook",
                topics=parsed.topics
                or sorted({q.topic for q in parsed.questions if q.topic}),
                week_label=guess_week_label(path),
                year_group=args.year_group,
                source_file_id=stored.id,
                full_text=text,
                question_text=parsed.question_text,
                answer_key_text=parsed.answer_key_text,
                total_marks=parsed.total_marks,
                estimated_minutes=parsed.estimated_minutes,
                parse_status=parsed.parse_status,
                parse_error=parsed.parse_error,
                parsed_at=datetime.utcnow(),
            )
            db.add(paper)
            db.flush()

            for question in parsed.questions:
                db.add(
                    PaperQuestion(
                        id=str(uuid.uuid4()),
                        paper_id=paper.id,
                        session_label=question.session_label,
                        band=question.band,
                        number=question.number,
                        order_index=question.order_index,
                        question_text=question.question_text,
                        marks=question.marks,
                        topic=question.topic,
                        expected_answer=question.expected_answer,
                        marking_notes=question.marking_notes,
                    )
                )

            db.commit()
            imported_papers.append(paper)

            with_answers = sum(1 for q in parsed.questions if q.expected_answer)
            key_state = "answer key found" if parsed.answer_key_text else "NO ANSWER KEY"
            print(
                f"   ✓ {title} [{subject}] — {len(parsed.questions)} questions, "
                f"{with_answers} with answers, {key_state}"
            )

        # --- first week's assignments --------------------------------------
        if args.assign_week and programme.blocks and imported_papers:
            papers_by_subject: Dict[str, Paper] = {}
            for paper in imported_papers:
                papers_by_subject.setdefault(paper.subject, paper)

            today = datetime.utcnow()
            monday = (today - timedelta(days=today.weekday())).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            if monday < today:
                monday += timedelta(days=7)

            created = 0
            print("\nAssignments for the coming week:")

            for block in sorted(programme.blocks, key=lambda b: (b.day_of_week, b.block_index)):
                paper = papers_by_subject.get(block.subject)
                due = monday + timedelta(days=block.day_of_week)
                title = f"{block.subject} — {block.focus}" if block.focus else block.subject

                if (
                    db.query(Assignment)
                    .filter(
                        Assignment.child_id == child.id,
                        Assignment.title == title,
                        Assignment.due_date == due,
                    )
                    .first()
                ):
                    continue

                db.add(
                    Assignment(
                        id=str(uuid.uuid4()),
                        **owner,
                        child_id=child.id,
                        title=title,
                        # Rotation slots have no single paper, so they become
                        # checkable tasks rather than markable papers.
                        assignment_type="paper" if paper else "task",
                        subject=block.subject,
                        paper_id=paper.id if paper else None,
                        instructions=block.focus,
                        estimated_minutes=block.planned_minutes,
                        due_date=due,
                        week_label="Week 1",
                        verification="upload" if paper else "self_report",
                        status="todo",
                        sort_order=block.block_index,
                    )
                )
                created += 1
                marker = "paper" if paper else "task"
                print(f"   ✓ {due:%a %d %b}  block {block.block_index}  {title[:48]} ({marker})")

            db.commit()
            print(f"\n✓ Created {created} assignment(s)")

        print("\n" + "=" * 70)
        print("Import complete")
        print("=" * 70)
        print(f"\nChild id: {child.id}")
        print(f"Subjects: {len(by_subject)}   Papers: {len(imported_papers)}")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Import failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
