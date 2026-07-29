"""
Prep-check business logic.

Goal: keep the FastAPI layer thin by moving orchestration and transformations
into a service module that can be unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from fastapi import UploadFile

from ..file_processing import process_uploaded_files
from ..llm import chat_completion
from ..storage import StorageAdapter


@dataclass(frozen=True)
class PrepCheckResult:
    prep_check_id: str
    feedback: str
    approx_score: int
    assessed_at: datetime


def extract_approx_score_and_clean_feedback(feedback: str) -> tuple[Optional[int], str]:
    """
    Try to extract an approximate 0-100 score from the model output, and return
    (score, cleaned_feedback).

    Expected optional header patterns (case-insensitive), e.g.:
      - "Score: 78/100"
      - "SCORE: 78"
      - "Approx score - 78/100"
    """
    import re

    if not feedback:
        return None, feedback

    lines = feedback.splitlines()
    if not lines:
        return None, feedback

    first = lines[0].strip()
    m = re.match(r"(?i)^\s*(approx\s*)?score\s*[:\-]\s*(\d{1,3})(\s*/\s*100)?\s*$", first)
    if m:
        raw = int(m.group(2))
        score = max(0, min(100, raw))
        # Drop the score line + a single following blank line if present
        remaining = lines[1:]
        if remaining and remaining[0].strip() == "":
            remaining = remaining[1:]
        cleaned = "\n".join(remaining).strip()
        return score, cleaned or feedback.strip()

    return None, feedback.strip()


def heuristic_approx_score_from_feedback(feedback: str) -> int:
    """
    Fallback approximate score when the model didn't provide one.
    Intentionally simple & stable: start from a baseline and subtract
    for issue-indicating keywords.
    """
    import re

    text = (feedback or "").lower()
    baseline = 85
    penalties = 0
    signals = [
        r"\bincorrect\b",
        r"\bwrong\b",
        r"\bmisunderstand",
        r"\bmissing\b",
        r"\bneeds\b",
        r"\bunclear\b",
        r"\bnot\s+enough\b",
        r"\bshow\s+your\s+work\b",
    ]
    for pat in signals:
        penalties += len(re.findall(pat, text))
    score = baseline - penalties * 4
    return max(0, min(100, score))


async def run_prep_check(
    *,
    subject: str,
    description: str,
    files: list[UploadFile],
    previous_prep_check_id: Optional[str],
    user: Optional[dict[str, str]],
    db: Any,
    session_id: str,
    openai_cls: Any,
    openai_api_key: str,
    openai_model: str,
    prompt_general_context: str,
    fetch_prompt: Any,
    render_prompt: Any,
    create_trace: Any,
    create_generation: Any,
    get_langfuse: Any,
) -> PrepCheckResult:
    """
    Perform prep check assessment and persist the result.

    This function:
    - Extracts text from uploaded files
    - Builds the prompt (Langfuse prompt preferred, fallback built-in)
    - Calls OpenAI for feedback
    - Extracts/stabilizes approx score
    - Stores the result via StorageAdapter
    """
    # Process uploaded files to extract text
    client = openai_cls(api_key=openai_api_key)
    extracted_texts = await process_uploaded_files(files, client)

    combined_text = description or ""
    if extracted_texts:
        for filename, text in extracted_texts.items():
            if text:
                combined_text += f"\n\n--- Content from {filename} ---\n{text}"

    combined_text = combined_text.strip()
    if not combined_text:
        raise ValueError("No text could be extracted from the provided files.")

    # Langfuse trace (optional)
    user_id = user.get("user_id") if user else None
    trace = create_trace(
        name="prep-check",
        user_id=user_id,
        metadata={
            "subject": subject,
            "has_description": bool(description),
            "file_count": len(files),
            "file_names": [f.filename for f in files] if files else [],
        },
    )

    # Try to fetch prep-check prompt from Langfuse (subject-specific first, then generic)
    langfuse_prompt_data = fetch_prompt("prep-check", subject=subject)

    default_prompt = """{general_context}

You are a helpful AI tutor reviewing a student's prep work. Your role is to provide constructive feedback WITHOUT revealing correct answers.

Review the following prep work and provide feedback that:
1. Identifies answers that need more work or are incorrect (but DO NOT provide the correct answer)
2. Reiterates rubrics and requirements (e.g., "provide evidence", "show your work", "be more specific")
3. Identifies specific issues such as:
   - Calculation errors (but don't give the correct calculation)
   - Spelling errors
   - Grammatical errors
   - Lack of specificity
   - Not showing work/steps
   - Illegible or unclear content
   - Missing required elements

Subject: {subject}
{additional_criteria}

Prep work to review:
{prep_work}

Provide your feedback:"""

    prompt_template = (
        langfuse_prompt_data["prompt"] if langfuse_prompt_data and langfuse_prompt_data.get("prompt") else default_prompt
    )

    prompt = render_prompt(
        prompt_template,
        {
            "general_context": prompt_general_context,
            "subject": subject,
            "additional_criteria": f"Additional criteria: {description}" if description else "",
            "prep_work": combined_text,
        },
    )

    # Ask the model to include a 0-100 approximate score on the first line.
    prompt = (
        "IMPORTANT OUTPUT FORMAT:\n"
        "First line must be: Score: NN/100 (NN is an integer 0-100)\n"
        "Then a blank line, then your feedback.\n\n"
    ) + prompt

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful AI tutor that provides constructive feedback on student prep work "
                "without revealing correct answers."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    response = chat_completion(
        client,
        model=openai_model,
        messages=messages,
        temperature=0.7,
        max_tokens=2000,
    )

    raw_feedback = response.choices[0].message.content or "No feedback generated."
    approx_score, cleaned_feedback = extract_approx_score_and_clean_feedback(raw_feedback)
    if approx_score is None:
        approx_score = heuristic_approx_score_from_feedback(cleaned_feedback)

    assessed_at = datetime.utcnow()

    # Log to Langfuse (best-effort)
    if trace:
        try:
            create_generation(
                trace=trace,
                name="prep-check-generation",
                model=openai_model,
                input_data={"messages": messages},
                output=cleaned_feedback,
                metadata={
                    "subject": subject,
                    "has_description": bool(description),
                    "file_count": len(files),
                },
            )
            trace.end()
            lf = get_langfuse()
            if lf:
                lf.flush()
        except Exception:
            # Observability must not break functionality
            pass

    # Persist
    storage = StorageAdapter(user, db, session_id)
    uploaded_file_names = [f.filename for f in files] if files else []
    prep_check_id = storage.store_prep_check(
        subject=subject,
        description=description if description else None,
        prep_work_text=combined_text,
        uploaded_files=uploaded_file_names,
        feedback=cleaned_feedback,
        approx_score=approx_score,
        assessed_at=assessed_at,
        langfuse_trace_id=str(getattr(trace, "id", "")) or None,
        previous_prep_check_id=previous_prep_check_id,
    )

    return PrepCheckResult(
        prep_check_id=prep_check_id,
        feedback=cleaned_feedback,
        approx_score=approx_score,
        assessed_at=assessed_at,
    )

