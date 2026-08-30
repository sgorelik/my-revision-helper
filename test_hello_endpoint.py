#!/usr/bin/env python3
"""Tests for the /api/hello endpoint.

Verifies that the HelloWorld API endpoint returns the correct status code,
JSON payload, and content-type header.
"""

from fastapi.testclient import TestClient

from my_revision_helper.api import app

client = TestClient(app)


def test_hello_endpoint_returns_200():
    """GET /api/hello should return a 200 OK status code."""
    response = client.get("/api/hello")
    assert response.status_code == 200


def test_hello_endpoint_returns_correct_json():
    """GET /api/hello should return exactly {"message": "Hello World"}."""
    response = client.get("/api/hello")
    data = response.json()
    assert data == {"message": "Hello World"}


def test_hello_endpoint_content_type():
    """GET /api/hello should return application/json content type."""
    response = client.get("/api/hello")
    assert "application/json" in response.headers["content-type"]


def test_hello_endpoint_message_field():
    """GET /api/hello response should contain a 'message' key with value 'Hello World'."""
    response = client.get("/api/hello")
    data = response.json()
    assert "message" in data
    assert data["message"] == "Hello World"
