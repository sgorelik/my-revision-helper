"""
Talking to the revision helper's HTTP API.

A thin wrapper: one method per thing the MCP tools need, with the personal
access token attached and the server's own error text passed through, so a
refusal reads the same here as it would in the app.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import requests

DEFAULT_URL = "https://web-production-35acf.up.railway.app"

# Parsing and marking call a model, which is slow and worth waiting for.
DEFAULT_TIMEOUT = 600


class ApiError(RuntimeError):
    """The server refused, and said why."""


class RevisionHelper:
    """The revision helper API, as the account the token belongs to."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.base_url = (base_url or os.getenv("REVISION_HELPER_URL") or DEFAULT_URL).rstrip("/")
        self.token = token if token is not None else os.getenv("REVISION_HELPER_TOKEN", "")
        self.timeout = timeout

    # -- plumbing ----------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}/api{path}"
        try:
            response = requests.request(
                method, url, headers=self._headers(), timeout=self.timeout, **kwargs
            )
        except requests.Timeout:
            raise ApiError(
                f"{self.base_url} did not answer within {self.timeout}s. "
                "Marking a long paper can take minutes; try fewer files at once."
            )
        except requests.RequestException as e:
            raise ApiError(f"Could not reach {self.base_url}: {e}")

        if response.status_code >= 400:
            raise ApiError(self._explain(response))

        if not response.content:
            return None
        return response.json()

    @staticmethod
    def _explain(response: requests.Response) -> str:
        """The server's own words where there are any."""
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        if isinstance(detail, list) and detail:  # FastAPI validation errors
            detail = "; ".join(str(item.get("msg", item)) for item in detail)
        return f"{response.status_code}: {detail or response.text[:300] or response.reason}"

    @staticmethod
    def _as_uploads(files: Sequence[Path]) -> List[tuple]:
        return [("files", (path.name, path.read_bytes())) for path in files]

    # -- who am I ----------------------------------------------------------

    def whoami(self) -> Dict[str, Any]:
        """The account the token reaches, for checking the setup."""
        return self._request("GET", "/user/me")

    # -- reading -----------------------------------------------------------

    def children(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/children")["items"]

    def papers(self, subject: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        query = {"limit": limit}
        if subject:
            query["subject"] = subject
        return self._request("GET", "/papers", params=query)["items"]

    def subjects(self) -> List[str]:
        return self._request("GET", "/subjects")["subjects"]

    def progress(self, child_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/children/{child_id}/progress")

    # -- writing -----------------------------------------------------------

    def upload_papers(
        self,
        files: Sequence[Path],
        *,
        subject: str = "",
        week_label: str = "",
        year_group: str = "",
        paper_type: str = "workbook",
    ) -> Dict[str, Any]:
        """Add documents to the library. Each file succeeds or fails alone."""
        return self._request(
            "POST",
            "/papers/bulk",
            files=self._as_uploads(files),
            data={
                "subject": subject,
                "weekLabel": week_label,
                "yearGroup": year_group,
                "paperType": paper_type,
            },
        )

    def hand_in(
        self,
        *,
        child_id: str,
        subject: str,
        files: Sequence[Path] = (),
        title: str = "",
        note: str = "",
        done_on: str = "",
        minutes_spent: Optional[int] = None,
        marks_awarded: Optional[float] = None,
        marks_available: Optional[float] = None,
        save_to_library: bool = True,
    ) -> Dict[str, Any]:
        """Record work that was never assigned, and mark it if it can be."""
        data: Dict[str, Any] = {
            "childId": child_id,
            "subject": subject,
            "title": title,
            "note": note,
            "doneOn": done_on,
            "saveToLibrary": str(save_to_library).lower(),
        }
        if minutes_spent is not None:
            data["minutesSpent"] = minutes_spent
        if marks_awarded is not None:
            data["marksAwarded"] = marks_awarded
        if marks_available is not None:
            data["marksAvailable"] = marks_available

        return self._request(
            "POST", "/handins", files=self._as_uploads(files) or None, data=data
        )

    def assign(
        self,
        *,
        child_id: str,
        title: str,
        subject: str,
        paper_id: Optional[str] = None,
        due_date: str = "",
        scheduled_date: str = "",
        instructions: str = "",
        estimated_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "childId": child_id,
            "title": title,
            "subject": subject,
            "assignmentType": "paper" if paper_id else "task",
        }
        if paper_id:
            payload["paperId"] = paper_id
        if due_date:
            payload["dueDate"] = due_date
        if scheduled_date:
            payload["scheduledDate"] = scheduled_date
        if instructions:
            payload["instructions"] = instructions
        if estimated_minutes is not None:
            payload["estimatedMinutes"] = estimated_minutes

        return self._request("POST", "/assignments", json=payload)

    # -- correcting the record ----------------------------------------------

    def work(self, child_id: str, *, needs_review_only: bool = False) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"childId": child_id}
        if needs_review_only:
            query["needsReviewOnly"] = "true"
        return self._request("GET", "/work", params=query)["items"]

    def update_work(self, work_id: str, **fields: Any) -> Dict[str, Any]:
        payload = {k: v for k, v in fields.items() if v is not None and v != ""}
        return self._request("PATCH", f"/work/{work_id}", json=payload)

    def delete_work(self, work_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/work/{work_id}")

    def restore_work(self, work_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/work/{work_id}/restore", json={})

    def move_work(self, work_id: str, to_child_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/work/{work_id}/move", json={"toChildId": to_child_id})

    def update_child(self, child_id: str, **fields: Any) -> Dict[str, Any]:
        payload = {k: v for k, v in fields.items() if v is not None and v != ""}
        return self._request("PATCH", f"/children/{child_id}", json=payload)
