"""
The student's worksheet.

The original uploaded document still contains its answer key, so it is never
handed to a student. This builds a clean worksheet from the parsed questions
instead — the same `question_text` and `PaperQuestion` rows that the student
already sees on screen, and which carry no expected answers.

Output is HTML with print styling rather than a generated PDF. It needs no
rendering dependency, and the browser's own "Save as PDF" produces a better
result than anything worth hand-rolling here.

Prerequisite links are printed at the top with the full URL and a QR code,
because a worksheet's whole purpose is to leave the screen. A link that only
exists in the web page is lost the moment the sheet is printed.
"""

from __future__ import annotations

import html
import io
import logging
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# Answer space per mark, in millimetres. Generous enough to write in, and it is
# what makes the printed sheet usable rather than merely correct.
MM_PER_MARK = 9
MIN_ANSWER_MM = 12
MAX_ANSWER_MM = 90


def normalise_resources(raw: Any) -> List[Dict[str, str]]:
    """
    Coerce stored resource links into a predictable shape.

    Accepts the JSON column's list of dicts, and tolerates a bare string so the
    legacy single `resource_url` field can be passed straight in.
    """
    if not raw:
        return []

    items = raw if isinstance(raw, list) else [raw]
    cleaned: List[Dict[str, str]] = []

    for item in items:
        if isinstance(item, str):
            url, label, kind = item.strip(), "", "watch"
        elif isinstance(item, dict):
            url = str(item.get("url") or "").strip()
            label = str(item.get("label") or "").strip()
            kind = str(item.get("kind") or "watch").strip() or "watch"
        else:
            continue

        if not url:
            continue
        # Only http(s) is printed or linked; anything else could be a
        # javascript: or data: URL rendered into a page.
        if not url.lower().startswith(("http://", "https://")):
            logger.warning(f"Skipping non-http resource link: {url[:60]}")
            continue

        cleaned.append({"url": url, "label": label or "Watch this first", "kind": kind})

    # Same link twice adds nothing, and the paper's copy wins on ordering.
    seen: set[str] = set()
    deduped: List[Dict[str, str]] = []
    for item in cleaned:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        deduped.append(item)

    return deduped


def merge_resources(paper_resources: Any, assignment_resources: Any, legacy_url: Any = None):
    """
    Combine a paper's own links with an assignment's extras.

    The paper's come first: they are the prerequisites belonging to the material,
    and the point of holding them there is that they arrive in the same order
    every time the paper is set.
    """
    return normalise_resources(
        normalise_resources(paper_resources)
        + normalise_resources(assignment_resources)
        + normalise_resources(legacy_url)
    )


def qr_svg(url: str) -> Optional[str]:
    """
    Inline SVG QR code for a link, or None if it cannot be produced.

    Returned as inline SVG so the worksheet is a single self-contained file that
    prints correctly without fetching anything.
    """
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:  # pragma: no cover - dependency is declared
        logger.warning("qrcode is not installed; worksheets will print without QR codes")
        return None

    try:
        image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
        buffer = io.BytesIO()
        image.save(buffer)
        svg = buffer.getvalue().decode("utf-8")
        # Strip the XML prolog so the fragment can be embedded mid-document.
        return svg.split("?>", 1)[-1].strip()
    except Exception as e:
        logger.warning(f"Could not build QR code for {url[:60]}: {e}")
        return None


def _answer_height_mm(marks: Optional[int]) -> int:
    return max(MIN_ANSWER_MM, min(MAX_ANSWER_MM, (marks or 1) * MM_PER_MARK))


def _resource_block(resources: List[Dict[str, str]]) -> str:
    if not resources:
        return ""

    cards = []
    for item in resources:
        code = qr_svg(item["url"])
        qr = f'<div class="qr">{code}</div>' if code else ""
        cards.append(
            f"""
      <div class="resource">
        {qr}
        <div class="resource-text">
          <div class="resource-label">{html.escape(item['label'])}</div>
          <div class="resource-url">{html.escape(item['url'])}</div>
        </div>
      </div>"""
        )

    return f"""
  <section class="resources">
    <h2>Before you start</h2>
    {''.join(cards)}
    <p class="resource-hint">
      Scan the code or type the address to watch it. Come back to it any time you
      get stuck — you are not expected to remember it all first time.
    </p>
  </section>"""


def _questions_block(questions: Iterable[Any], fallback_text: Optional[str]) -> str:
    rows: List[str] = []
    current_session: Optional[str] = None

    for question in questions:
        session = getattr(question, "session_label", None)
        if session and session != current_session:
            current_session = session
            rows.append(f'<h3 class="session">{html.escape(session)}</h3>')

        marks = getattr(question, "marks", 1) or 1
        number = getattr(question, "number", None) or ""
        text = getattr(question, "question_text", "") or ""

        rows.append(
            f"""
    <div class="question">
      <div class="question-head">
        <span class="number">{html.escape(str(number))}</span>
        <span class="text">{html.escape(text)}</span>
        <span class="marks">[{int(marks)}]</span>
      </div>
      <div class="answer" style="min-height:{_answer_height_mm(marks)}mm"></div>
    </div>"""
        )

    if rows:
        return f'<section class="questions">{"".join(rows)}</section>'

    # No parsed questions: fall back to the student-safe text of the document,
    # which has already had any answer key removed.
    if fallback_text:
        return f'<section class="questions"><pre class="raw">{html.escape(fallback_text)}</pre></section>'

    return '<section class="questions"><p>This paper has no questions recorded yet.</p></section>'


STYLES = """
  :root { --ink: #0f172a; --muted: #64748b; --line: #cbd5e1; }
  * { box-sizing: border-box; }
  body {
    font-family: ui-sans-serif, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: var(--ink); margin: 0; padding: 24px; line-height: 1.5;
  }
  .sheet { max-width: 760px; margin: 0 auto; }
  header { border-bottom: 2px solid var(--ink); padding-bottom: 12px; margin-bottom: 18px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .meta { color: var(--muted); font-size: 13px; }
  .namebar { display: flex; gap: 24px; margin-top: 12px; font-size: 13px; color: var(--muted); }
  .namebar span { flex: 1; border-bottom: 1px solid var(--line); padding-bottom: 2px; }
  h2 { font-size: 15px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); margin: 0 0 10px; }
  .resources { border: 1.5px solid var(--ink); border-radius: 10px; padding: 14px; margin-bottom: 22px; }
  .resource { display: flex; gap: 14px; align-items: center; margin-bottom: 10px; }
  .resource:last-of-type { margin-bottom: 0; }
  .qr { width: 78px; height: 78px; flex: none; }
  .qr svg { width: 100%; height: 100%; display: block; }
  .resource-label { font-weight: 700; }
  .resource-url { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; word-break: break-all; color: #1e40af; }
  .resource-hint { font-size: 12px; color: var(--muted); margin: 10px 0 0; }
  .session { font-size: 14px; margin: 20px 0 8px; color: var(--muted); }
  .question { margin-bottom: 14px; }
  .question-head { display: flex; gap: 8px; align-items: baseline; }
  .number { font-weight: 700; min-width: 26px; }
  .text { flex: 1; }
  .marks { color: var(--muted); font-size: 13px; white-space: nowrap; }
  .answer { border-bottom: 1px solid var(--line); margin: 6px 0 0 34px; }
  .raw { white-space: pre-wrap; font-family: inherit; font-size: 14px; }
  footer { margin-top: 24px; padding-top: 10px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }
  .print-hint { margin-bottom: 16px; }
  .print-hint button {
    font: inherit; padding: 8px 14px; border-radius: 8px; border: 0;
    background: var(--ink); color: #fff; cursor: pointer;
  }
  @media print {
    body { padding: 0; }
    .print-hint { display: none; }
    /* Keep the links on page one and never split an answer space. */
    .resources { break-inside: avoid; }
    .question { break-inside: avoid; }
  }
"""


def render_worksheet(
    *,
    title: str,
    subject: str,
    student_name: Optional[str] = None,
    due_text: Optional[str] = None,
    total_marks: Optional[int] = None,
    resources: Optional[List[Dict[str, str]]] = None,
    questions: Optional[Iterable[Any]] = None,
    fallback_text: Optional[str] = None,
) -> str:
    """
    Build the printable worksheet.

    Callers must pass only student-safe content: `questions` are expected to be
    PaperQuestion rows, of which only the number, text and marks are read —
    never `expected_answer`.
    """
    meta_parts = [subject]
    if total_marks:
        meta_parts.append(f"{total_marks} marks")
    if due_text:
        meta_parts.append(due_text)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{STYLES}</style>
</head>
<body>
<div class="sheet">
  <div class="print-hint"><button onclick="window.print()">Print this worksheet</button></div>
  <header>
    <h1>{html.escape(title)}</h1>
    <div class="meta">{html.escape(' · '.join(meta_parts))}</div>
    <div class="namebar">
      <span>Name: {html.escape(student_name or '')}</span>
      <span>Date:</span>
      <span>Score:</span>
    </div>
  </header>
  {_resource_block(resources or [])}
  {_questions_block(questions or [], fallback_text)}
  <footer>Work through this on paper, then photograph it and hand it in.</footer>
</div>
</body>
</html>"""
