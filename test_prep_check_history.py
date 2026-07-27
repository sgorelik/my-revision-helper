import os
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from my_revision_helper.api import app
from my_revision_helper.database import engine, Base
from my_revision_helper.models_db import PrepCheck


@pytest.mark.integration
def test_prep_check_history_list_and_detail(monkeypatch: Any):
    """
    Verifies:
    - POST /api/prep-check returns prepCheckId + approxScore and stores feedback
    - GET /api/prep-checks returns paginated items with approxScore
    - GET /api/prep-checks/{id} returns stored prepWorkText + feedback
    """
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - prep check history requires database")
    if engine is None:
        pytest.skip("Database engine not configured")

    # Ensure table exists
    Base.metadata.create_all(bind=engine, tables=[PrepCheck.__table__])

    # Ensure expected columns exist (older DBs may have table without these fields)
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("prep_checks")}
    with engine.begin() as conn:
        if "approx_score" not in cols:
            conn.execute(text("ALTER TABLE prep_checks ADD COLUMN approx_score INTEGER"))
        if "assessed_at" not in cols:
            conn.execute(text("ALTER TABLE prep_checks ADD COLUMN assessed_at TIMESTAMP"))
            conn.execute(text("UPDATE prep_checks SET assessed_at = created_at WHERE assessed_at IS NULL"))

    class _StubResponse:
        def __init__(self, content: str):
            self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]

    class _StubOpenAI:
        def __init__(self, *args: Any, **kwargs: Any):
            self.chat = type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Completions",
                        (),
                        {
                            "create": staticmethod(
                                lambda **kwargs: _StubResponse(
                                    "Score: 78/100\n\n"
                                    "## Feedback\n"
                                    "- Good structure overall.\n"
                                    "- Check your notation for x_1 and show steps for 2*3.\n"
                                )
                            )
                        },
                    )()
                },
            )()

    # Patch OpenAI used by the prep-check router
    import my_revision_helper.routers.prep_check as router_mod
    monkeypatch.setattr(router_mod, "OpenAI", _StubOpenAI)
    # Also patch the service module (API delegates to service)
    import my_revision_helper.services.prep_check_service as svc_mod
    async def _no_files(files, client):  # type: ignore[no-untyped-def]
        return {}
    monkeypatch.setattr(svc_mod, "process_uploaded_files", _no_files)  # no files in this test

    client = TestClient(app)

    # Create a prep check (description-only)
    resp = client.post(
        "/api/prep-check",
        data={"subject": "Mathematics", "description": "x_1 = 2*3"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "prepCheckId" in data
    assert data["approxScore"] == 78
    assert "Score:" not in data["feedback"]  # score line should be stripped from feedback

    prep_check_id = data["prepCheckId"]

    # List prep checks
    resp = client.get("/api/prep-checks?limit=10&offset=0")
    assert resp.status_code == 200, resp.text
    listed = resp.json()
    assert "items" in listed and "total" in listed
    assert listed["total"] >= 1
    assert any(i["id"] == prep_check_id for i in listed["items"])
    item = next(i for i in listed["items"] if i["id"] == prep_check_id)
    assert item["subject"] == "Mathematics"
    assert item["approxScore"] == 78

    # Fetch detail
    resp = client.get(f"/api/prep-checks/{prep_check_id}")
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["id"] == prep_check_id
    assert detail["prepWorkText"].strip() == "x_1 = 2*3"
    assert "x_1" in detail["feedback"]
    assert detail["approxScore"] == 78


