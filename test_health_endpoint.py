"""Tests for the GET /api/health endpoint."""

from fastapi.testclient import TestClient

from my_revision_helper.api import app

client = TestClient(app)


def test_health_returns_200():
    """Health check endpoint returns 200 OK."""
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_response_body():
    """Health check endpoint returns the expected JSON payload."""
    response = client.get("/api/health")
    data = response.json()
    assert data == {"status": "healthy", "version": "1.0.0"}


def test_health_status_field():
    """Health check response contains 'healthy' status."""
    response = client.get("/api/health")
    assert response.json()["status"] == "healthy"


def test_health_version_field():
    """Health check response contains version '1.0.0'."""
    response = client.get("/api/health")
    assert response.json()["version"] == "1.0.0"


def test_health_content_type():
    """Health check endpoint returns application/json content type."""
    response = client.get("/api/health")
    assert response.headers["content-type"] == "application/json"


def test_health_no_auth_required():
    """Health check endpoint is accessible without authentication headers."""
    # Explicitly send no Authorization header
    response = client.get("/api/health", headers={})
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_health_route_registered():
    """The /api/health route is registered in the FastAPI app."""
    routes = [route.path for route in app.routes]
    assert "/api/health" in routes
