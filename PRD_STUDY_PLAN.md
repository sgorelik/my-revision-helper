# Study plan and assignment tracking

A plan against the spec of 27 Jul. Written as a delta: much of what the spec
asks for is already built and tested, so the value here is separating the four
things that genuinely do not exist from the six that mostly do.

## Where the spec meets the code

| # | Requirement | State | What is actually missing |
|---|---|---|---|
| 1 | Session/account consistency | Partly done | Auth race fixed in `aed50fe`. Stale JS bundle after deploy is not handled. |
| 2 | Durable student setup | Done | Nothing. The "disappearing students" symptom was the auth race, not data loss. |
| 3 | Assigned file download | **Broken** | Returns 404, and cannot be fixed as written without leaking answer keys. |
| 4 | Bulk upload | **Missing** | `POST /papers` merges every file into one paper. |
| 5 | Worksheet vs answer key | Done | Nothing at the data layer. The student *file* path is the hole — see 3. |
| 6 | Subject configuration | Partly done | Subjects are a hardcoded list; topics are free-text JSON, not entities. |
| 7 | Study plan layer | Partly done | `StudyPlan`/`PlanBlock` are a recurring weekly timetable, not dated tasks. |
| 8 | Instructional links | Partly done | `Assignment.resource_url` is one unlabelled string. |
| 9 | Submission → marking → history | Done | Nothing. Includes per-question marking, parent override, holistic fallback. |
| 10 | Progress tracking | Done | Nothing. Overdue is the one view not surfaced explicitly. |

Two of the eight "must-have" MVP items are already finished (5 and 9), and a
third (basic progress history) is finished. That reshapes the plan considerably.

## The two problems worth deciding first

### Student download and answer-key protection are in direct conflict

`GET /api/papers/{id}/file` returns the *original uploaded document*. For a
workbook that document still contains its answer key — the endpoint's own
docstring says so and restricts it to the account holder. But
`AssignmentPage.tsx:235` links to it from the **student** view, labelled
"Download original".

It currently 404s, which is why download appears broken: the link is a plain
`<a href>`, and a browser navigation carries no `Authorization` header because
the Auth0 token lives in JavaScript rather than a cookie. The request falls
through to anonymous session scoping, the paper is owned by a `user_id`, and
nothing matches.

So the bug is protecting us by accident. Fixing the auth on that URL — by making
it public, or by moving to cookie auth — would immediately hand students the
answer key and violate requirement 5.

**Recommendation.** Treat "download my worksheet" and "download the original"
as two different things.

- `GET /api/assignments/{id}/worksheet` — a generated, student-safe worksheet
  built from `question_text` / `paper_questions`, which are already
  answer-key-stripped and already proven clean by test. Served as printable
  HTML in v1; PDF later if it matters.
- `GET /api/papers/{id}/file` — stays parent-only, and stays as-is.
- The original may be offered to a student only when `has_answer_key` is false,
  i.e. the upload never contained a key to begin with.

For the missing header, fetch with the token and open a blob URL rather than
navigating. That reuses the existing client and needs no signed-URL infra.

On rendering: the worksheet is HTML with print CSS, not a server-built PDF. That
needs no new rendering dependency and lets the browser's own "Save as PDF" do
the work. Worth noting `reportlab` is importable locally but absent from
`requirements.txt`, so it is not actually present in the deployed image and must
not be relied on. The one dependency this does add is `qrcode` for the printed
link, using its SVG factory so it needs nothing from Pillow.

### A combined file should block assignment, not fail silently

Requirement 5 asks that a combined worksheet+key file be flagged unsuitable for
students. The splitter already records this: `has_answer_key` is true when a key
was found and separated. What is missing is the consequence — assigning such a
paper should not offer the original file to the student, and the library should
say so on the card.

## Recommended answers to the spec's open questions

**Should study plan and assignment be separate objects in v1?** No. Extend
`Assignment`. It already carries `due_date`, `week_label`, `status`,
`instructions`, `resource_url`, `verification` and `estimated_minutes`. A
parallel `StudyPlanTask` would duplicate all of that and, worse, fork the
submission and marking path — the most valuable and best-tested part of the
system. Adding `scheduled_date` gives dated daily tasks for one column.

**Should resource links be first-class objects?** They belong to the *material*,
not to one act of assigning it. A "watch this before you start" video is a
property of the worksheet itself, so it should travel with the paper every time
it is set, rather than being retyped per assignment.

So links live primarily on `papers`, with an optional per-assignment list for
one-off additions. Storage stays a JSON column on each — nothing queries across
links, so a table plus CRUD endpoints would buy nothing at this scale. The merge
rule is: the paper's links first, in order, as prerequisites, then the
assignment's own, deduplicated by URL.

Critically, links are **not a one-time gate**. Students will print the worksheet
or download it and print that, and will want to rewatch the explanation when
they get stuck. That has two consequences, both in Phase 1:

- The generated worksheet **embeds the links at the top**, as a labelled block
  with the full URL in text and a QR code beside it, so the link survives being
  printed onto paper. A link that only exists in the web UI is lost the moment
  the worksheet leaves the screen.
- The student view keeps the links permanently visible above the questions,
  rather than hiding them once work has started.

**Manual override when parsing fails?** Already built.
`PATCH /api/markings/{id}/questions/{qid}` exists and recomputes the total, and
`mark_holistically` covers papers with no usable key. This needs a UI affordance,
not new backend work.

**Overdue: date-only or timezone-aware?** Date-only, evaluated in
`Europe/London`. Homework is due on a day, not at an instant, and a timestamp
comparison would mark work overdue during the evening it was set. Keep the
`DateTime` column, compare on local date.

**How to migrate combined worksheet+answer files?** No data migration needed.
Existing rows already have the split stored. The change is behavioural, above.

**Suggested topics: rules, AI, or weak tags?** Keep the existing rule: topic
mastery rolls up marks awarded over marks available per topic, and anything
under the threshold is offered for retest. It is deterministic and explainable
to a parent, which matters more here than sophistication.

## Backend changes

Additive only; nothing existing is dropped.

```
papers
  + resources           JSON      -- [{url, label, kind, sort}] prerequisites
                                  -- intrinsic to the material; printed onto
                                  -- the worksheet and shown for rewatching
  + is_student_safe     BOOLEAN   -- derived: no answer key in the original
  + topic_ids           JSON      -- alongside free-text topics

assignments
  + scheduled_date      DATE      -- the day this is planned for
  + resources           JSON      -- one-off extras for this setting only
  (resource_url retained, read as a single-entry fallback)

subjects        (new)  id, owner, name, canonical_name, sort_order, is_active
topics          (new)  id, subject_id, name, parent_topic_id, is_active
audit_log       (new)  id, owner, entity, entity_id, action, actor, at, detail
```

`subjects`/`topics` seed from `CANONICAL_SUBJECTS` so nothing breaks, and the
hardcoded list becomes the seed rather than the source of truth.

## API changes

```
GET    /api/assignments/{id}/worksheet     student-safe worksheet (new)
POST   /api/papers/bulk                    many files -> many papers (new)
GET    /api/version                        build id for staleness check (new)
GET    /api/children/{id}/plan/{date}      a day's tasks (new)
CRUD   /api/subjects, /api/topics          user-managed vocabulary (new)
GET    /api/children/{id}/progress         + overdue counts (extend)
POST   /api/assignments                    + scheduledDate, resources (extend)
```

## Frontend changes

- **Library**: multi-file drop zone with per-file rows, each showing parsed
  question count, key-found state, and its own retry. Replaces the current
  single-paper-from-many-files behaviour.
- **Assignment (student)**: "Open my worksheet" via blob download; the
  "Download original" link removed unless the paper is student-safe. Resource
  links rendered above the questions in "watch first" order, and left there
  permanently so they can be reopened mid-task.
- **Worksheet output**: the generated worksheet leads with the resource block —
  label, full URL as text, and a QR code — then the questions. Print CSS keeps
  that block on page one and stops questions splitting mid-answer-space.
- **Plan view**: day and week columns for a child, built on `scheduled_date`.
- **Dashboard**: an explicit overdue tile beside assigned and completed.
- **Deploy staleness**: on focus and on API error, compare `/api/version` with
  the build id baked into the bundle; if they differ, prompt a reload rather
  than reloading under the user.

## Edge cases

- Upload succeeds but parsing finds no questions — keep the paper, mark
  `parse_status=failed`, allow reparse; never discard the stored file.
- Bulk upload partially fails — successful files land, failures stay listed and
  retryable, and the batch is never rolled back wholesale.
- Paper deleted while assigned — assignment keeps its title and shows the file
  as unavailable rather than 500ing.
- Submission arrives with no OpenAI key configured — holistic fallback, already
  covered.
- A child with marking history is deleted — fixed in `b4e14d4`.
- Two subjects differing only in case or alias — normalise through
  `normalise_subject` before insert.

## Build status

Phases 1 to 3 are implemented and deployed.

**Phase 1.** `GET /api/assignments/{id}/worksheet` renders a printable,
answer-key-free worksheet from `paper_questions`, with resource links at the top
as text plus a QR code and answer space scaled to each question's marks. Links
live on `papers.resources` and merge with `assignments.resources`. Downloads go
through an authenticated blob fetch, so the original file is reachable by the
parent and the student never gets a link to it. Overdue is surfaced on the
dashboard tile and the kid's day.

**Phase 2.** `POST /api/papers/bulk` makes one paper per file, committing each
separately so a single unreadable document neither blocks nor discards the rest,
and reporting per filename. Subject and week are inferred from the filename
(`subject_from_filename`, `week_from_filename`), which covers the real naming
convention of the workbooks being uploaded. The staging list shows each guess
for correction before upload and allows retry of failed rows alone.

**Phase 3.** `assignments.scheduled_date` separates the day work is planned for
from the day it is due, with `planned_on` / `due_on` resolving the fallback in
one place so every view agrees. `GET /api/children/{id}/today` returns today's
timetable blocks, today's work, what slipped, and a short look ahead. The week
view places work by planned day.

Dates are evaluated in `Europe/London` via `clock.py`, which keeps calendar
dates (due dates) and UTC timestamps (submissions) apart. Railway runs in UTC,
where the previous code filed late-evening work under the wrong day.

Not yet built: Phase 4 (managed subject and topic vocabulary, the deploy version
handshake, audit logging), and a dedicated overdue banner as opposed to the
current inline counts.

## Phasing

**Phase 1 — unblock the current flow.** Student-safe worksheet endpoint and the
blob download; remove the answer-key link from the student view; resource links
on papers, shown in the student view and printed onto the worksheet with a QR
code; overdue on the dashboard.

Links are in Phase 1 rather than later precisely because the worksheet is what
gets printed. Building the worksheet first and adding links afterwards would
mean reissuing every worksheet already sent home.

**Phase 2 — make setup fast.** Bulk upload with per-file status and retry,
including attaching a prerequisite link per file during upload, plus the library
card showing key-found state.

**Phase 3 — the plan layer.** `scheduled_date`, day and week views.

**Phase 4 — vocabulary and hardening.** Managed subjects and topics, the version
handshake for deploys, audit logging.

## Acceptance criteria

- A student opens an assignment, gets their worksheet, and at no point can reach
  answer-key content; a test asserts the worksheet response contains none of the
  stored expected answers.
- A parent uploads ten files in one action; each appears as its own library item
  with its own parse result, and a single failure neither blocks the others nor
  loses them.
- A parent attaches a Khan Academy link to a worksheet once; every future
  assignment of that worksheet carries it without being retyped.
- The student sees the link above the questions, can reopen it after starting,
  and — having printed the worksheet — can still reach the video from paper via
  the printed URL and QR code.
- Overdue work is visible without opening anything.
- Signing in after a deploy shows the correct children, or an explicit error —
  never an empty account.
