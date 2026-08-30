"""
Tests for the /api/hello endpoint.

Verifies the HelloWorld API endpoint returns the correct status code,
JSON payload, and Content-Type header.
"""

from fastapi.testclient import TestClient

from my_revision_helper.api import app

client = TestClient(app)


def test_hello_returns_200():
    """Test that GET /api/hello returns a 200 OK status code."""
    response = client.get("/api/hello")
    assert response.status_code == 200


def test_hello_returns_correct_json():
    """Test that GET /api/hello returns exactly {"message": "Hello World"}."""
    response = client.get("/api/hello")
    data = response.json()
    assert data == {"message": "Hello World"}


def test_hello_content_type_is_json():
    """Test that the Content-Type header is set to application/json."""
    response = client.get("/api/hello")
    assert "application/json" in response.headers["content-type"]
