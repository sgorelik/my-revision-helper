#!/usr/bin/env python3
"""
Tests for deployment configuration and setup.

These tests verify that the application is properly configured for deployment,
including static file serving, route configuration, and environment variable handling.
"""

import os
import sys
from pathlib import Path

import pytest


def test_api_imports():
    """Test that the API module can be imported without errors."""
    from my_revision_helper.api import app  # noqa: F401
    assert True  # If we get here, import succeeded


def test_frontend_build_exists():
    """Test that the frontend build directory exists."""
    frontend_dist = Path("frontend/dist")
    assert frontend_dist.exists(), "Frontend build not found. Run: cd frontend && npm run build"
    assert frontend_dist.is_dir(), "frontend/dist should be a directory"


def test_frontend_index_html_exists():
    """Test that the frontend index.html exists."""
    index_html = Path("frontend/dist/index.html")
    assert index_html.exists(), "frontend/dist/index.html not found"


def test_api_routes_defined():
    """Test that all expected API routes are defined."""
    from my_revision_helper.api import app

    routes = [r.path for r in app.routes if hasattr(r, "path")]
    api_routes = [r for r in routes if r.startswith("/api/")]

    # Expected API routes
    expected_routes = [
        "/api/revisions",
        "/api/revisions/{revision_id}/runs",
        "/api/runs/{run_id}/next-question",
        "/api/runs/{run_id}/answers",
        "/api/runs/{run_id}/summary",
    ]

    # Check that we have at least the expected routes
    assert len(api_routes) >= len(expected_routes), f"Expected at least {len(expected_routes)} API routes, found {len(api_routes)}"

    # Verify key routes exist
    route_paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/api/revisions" in route_paths, "POST /api/revisions route not found"
    assert any("/api/runs" in r for r in route_paths), "API runs routes not found"


def test_static_file_serving_configured():
    """Test that static file serving is configured for frontend."""
    from my_revision_helper.api import app

    # Check if static files mount exists
    mounts = [m for m in app.routes if hasattr(m, "path") and hasattr(m, "directory")]
    has_static = any(hasattr(m, "directory") for m in app.routes if hasattr(m, "directory"))

    # The static serving might be conditional, so we just check the code structure
    # If frontend/dist exists, static serving should be configured
    frontend_dist = Path("frontend/dist")
    if frontend_dist.exists():
        # Check that we have a catch-all route for frontend
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        has_catch_all = any(r == "/{full_path:path}" for r in routes)
        assert has_catch_all or has_static, "Frontend static serving not configured"


def test_cors_configuration():
    """Test that CORS is configured."""
    from my_revision_helper.api import app

    # Check that CORS middleware is added
    # FastAPI stores middleware differently, check if middleware exists
    has_middleware = len(app.user_middleware) > 0
    assert has_middleware, "No middleware configured. CORS middleware should be present."

    # Check middleware string representation for CORS
    middleware_str = str(app.user_middleware)
    assert "cors" in middleware_str.lower() or "CORS" in middleware_str, "CORS middleware not found in middleware stack"


def test_environment_variables_handled():
    """Test that environment variables are properly handled."""
    import os
    from my_revision_helper.api import get_openai_model, get_ai_context

    # These functions should work even without env vars (they have defaults)
    model = get_openai_model()
    assert isinstance(model, str)
    assert len(model) > 0

    context = get_ai_context()
    assert isinstance(context, str)
    assert len(context) > 0


def test_procfile_exists():
    """Test that Procfile exists for Railway deployment."""
    procfile = Path("Procfile")
    assert procfile.exists(), "Procfile not found. Required for Railway deployment."

    # Check Procfile content
    content = procfile.read_text()
    assert "uvicorn" in content, "Procfile should contain uvicorn command"
    assert "$PORT" in content, "Procfile should use $PORT environment variable"


def test_railway_config_exists():
    """Test that Railway configuration exists."""
    railway_json = Path("railway.json")
    assert railway_json.exists(), "railway.json not found. Helpful for Railway deployment."


def test_runtime_txt_exists():
    """Test that runtime.txt exists for Python version specification."""
    runtime_txt = Path("runtime.txt")
    assert runtime_txt.exists(), "runtime.txt not found. Helps Railway use correct Python version."

    # Check it specifies Python
    content = runtime_txt.read_text()
    assert "python" in content.lower(), "runtime.txt should specify Python version"


def test_requirements_txt_exists():
    """Test that requirements.txt exists."""
    requirements = Path("requirements.txt")
    assert requirements.exists(), "requirements.txt not found. Required for deployment."

    # Check it has key dependencies
    content = requirements.read_text()
    assert "fastapi" in content.lower(), "requirements.txt should include fastapi"
    assert "uvicorn" in content.lower(), "requirements.txt should include uvicorn"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

