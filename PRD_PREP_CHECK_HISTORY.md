# PRD: Prep Check History (Paginated List + Detail View + Stored Outcomes)

## Summary
Add a **Prep Check History** experience that lets users:
- **Browse past prep checks** (similar to how we show past revisions)
- Use **pagination**
- **Select a prep check** to view the **stored assessed work** (reconstructed from extracted/pasted text) and the **stored AI assessment**

Assessments **must not be recalculated** on each view; they are stored at creation time. The history list shows an **approximate 0–100 score** (stored).

## In Scope (v1)
### UX
- A paginated **history list** of prep checks
- A **detail view** for a selected prep check that shows:
  - **Subject**
  - **Created timestamp**
  - **Uploaded file names** (if any)
  - **Assessed work text** (`prep_work_text`, i.e., OCR/extracted text + user-provided criteria)
  - **Stored AI feedback** (`feedback`)
  - **Approx score (0–100)** (stored)

### Backend
- API endpoint to **list** prep checks with pagination for the current user/session
- API endpoint to **get** a single prep check by ID (with access control)
- Persist **approximate score (0–100)** at the time of assessment (no recompute later)

### Math readability
- Ensure both the assessed work and the feedback are **readable for students**, especially for mathematical expressions.
- Avoid markdown rendering quirks that mangle common math notation (e.g., underscores in `x_1`).

## Out of Scope (Future Work)
### Ageing out / retention
- Clearing old prep-check feedback after 30 days (TTL)
- Cron/scheduled job for retention/cleanup
- Reassess-on-view behavior for expired items

### File storage
- Storing and re-serving original uploaded binary files (images/PDFs). For now, we show filenames + extracted text only.

## User stories
- **U1**: As a student, I can see my past prep checks with subject, date, and approximate score.
- **U2**: As a student, I can select a prep check and see what content was assessed and the AI feedback.
- **U3**: As a student, math notation is readable when viewing assessed work and feedback.

## Functional requirements
### List prep checks
- Paginated list
- Scoped to:
  - authenticated user (`user_id`), or
  - anonymous session (`session_id`)
- List item fields:
  - `id`
  - `subject`
  - `createdAt`
  - `assessedAt` (if present)
  - `approxScore` (0–100)
  - `preview` (short snippet)
  - `uploadedFilesCount`

### Prep check detail
- Returns the persisted record:
  - `prepWorkText`
  - `uploadedFiles[]`
  - `feedback`
  - `approxScore`
  - timestamps and linkage metadata

## API (v1)
- `GET /api/prep-checks?limit=20&offset=0`
  - Response:
    - `items: PrepCheckListItem[]`
    - `total: number`
- `GET /api/prep-checks/{id}`
  - Response: `PrepCheckDetail`

## Acceptance criteria
- **AC1**: Prep checks are listed paginated and scoped correctly to the current user/session.
- **AC2**: Selecting an item shows stored assessed work + stored feedback (no recomputation).
- **AC3**: List shows stored **approx score (0–100)** without calling OpenAI.
- **AC4**: Mathematical expressions render/read cleanly (no mangled underscores, preserved line breaks).

# PRD: Prep Check History (Paginated List + Detail View + Stored Results + Approx Score)

## Summary
Add a **Prep Check History** experience similar to past revisions:

- Users can **browse past prep checks** with **pagination**
- Selecting an item shows the **stored assessed work** (combined extracted OCR + pasted text/criteria) and **stored AI feedback**
- The list shows an **approximate score (0–100)** computed at assessment time and stored
- **No TTL / cron aging in this iteration** (explicitly deferred to future work)

---

## Decisions locked in
- **Approx score**: store an **integer 0–100** (approximate)
- **Viewing content**: reconstruct from stored **`prep_work_text`** + uploaded file names (no raw upload storage yet)
- **Math readability**: ensure student-friendly rendering (avoid odd formula representations; preserve line breaks)
- **TTL/aging**: deferred (future work)

---

## Goals
- **G1: History access**: list prep checks with pagination for the current user/session
- **G2: Detail view**: show what was assessed + stored AI feedback
- **G3: Stored outcomes**: list/detail should not call OpenAI (no recomputation in this iteration)
- **G4: Approx score**: list shows 0–100 score without AI
- **G5: Math readability**: assessed work is readable by students (esp. formulas/working)

---

## Non-goals (v1)
- Background cleanup / retention policies (TTL + cron)
- Reassess-on-view behavior (depends on TTL clearing)
- Storing and re-rendering original binary uploads (images/PDFs)
- Teacher/admin workflows and sharing

---

## Users / permissions
- **Authenticated user**: can see only their prep checks
- **Anonymous session**: can see only prep checks tied to their session cookie
- No cross-user access

---

## User stories
- **U1**: I can page through my past prep checks and see subject, date, and score /100
- **U2**: I can click a past prep check to review what I submitted and the AI feedback
- **U3**: When my prep contains math, the content is displayed in a readable way

---

## UX requirements

### Prep Check history list
- **Row fields**:
  - Subject
  - Created date/time
  - **Approx score (0–100)**
  - Optional preview snippet (first ~80–120 chars of assessed text)
- **Pagination**:
  - Default page size 10–20
  - Next/Previous controls (or page numbers)
- **No recompute**:
  - Loading list must not trigger OpenAI

### Prep Check detail view
- Shows:
  - Subject, createdAt, assessedAt
  - Uploaded file names
  - **Assessed work** (stored combined text)
  - **Stored AI feedback**

### Math readability requirement
- Preserve line breaks and spacing (e.g., show in a pre-wrapped block)
- Normalize obvious OCR artifacts where possible (minus signs, weird unicode, broken spacing)
- Avoid collapsing whitespace in a way that breaks multi-step working

---

## Backend requirements

### Data model
Prep check persistence must include:
- `prep_work_text` (combined extracted + pasted/criteria text)
- `uploaded_files` (names list)
- `feedback` (stored AI assessment text)
- `approx_score` (int 0–100)
- `assessed_at` (timestamp for when feedback/score were produced)

### API endpoints (v1)
- `GET /api/prep-checks?limit=&offset=`
  - Returns: `items[]`, `total`, `nextOffset`
  - Item fields:
    - `id`, `subject`, `createdAt`, `assessedAt`
    - `approxScore` (0–100, nullable if missing)
    - `preview` (short snippet)
    - `uploadedFilesCount`
- `GET /api/prep-checks/{id}`
  - Returns full detail:
    - `id`, `subject`, `createdAt`, `assessedAt`
    - `uploadedFiles[]`
    - `prepWorkText`
    - `feedback`
    - `approxScore`

### Storage rules
- Listing and detail retrieval must be served entirely from stored DB values (no OpenAI calls).

---

## Acceptance criteria
- **AC1**: List is paginated and shows approxScore (0–100) without calling AI
- **AC2**: Selecting an item shows stored assessed work + stored feedback
- **AC3**: Auth/session scoping is correct (users only see their own items)
- **AC4**: Math/working is readable (no odd formatting regressions)

---

## Future work (explicitly deferred)
- TTL aging of feedback and other DB cleanup
- Cron/scheduled job to clear old data
- Reassess-on-view for expired items (using stored `prep_work_text`)


