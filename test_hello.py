"""Tests for the /api/hello greeting endpoint."""

import pytest
from fastapi.testclient import TestClient

from my_revision_helper.api import app

client = TestClient(app)


@pytest.mark.unit
def test_hello_endpoint_returns_200():
    """Test that the /api/hello endpoint returns HTTP 200."""
    response = client.get("/api/hello")
    assert response.status_code == 200


@pytest.mark.unit
def test_hello_endpoint_returns_message():
    """Test that the /api/hello endpoint returns a JSON body with a 'message' key."""
    response = client.get("/api/hello")
    data = response.json()
    assert "message" in data


@pytest.mark.unit
def test_hello_endpoint_message_is_hello_world():
    """Test that the greeting message is 'Hello World'."""
    response = client.get("/api/hello")
    data = response.json()
    assert data["message"] == "Hello World"


@pytest.mark.unit
def test_hello_endpoint_json_content_type():
    """Test that the /api/hello endpoint returns JSON content type."""
    response = client.get("/api/hello")
    assert "application/json" in response.headers["content-type"]
