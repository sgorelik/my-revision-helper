"""
Shared test setup.

The point of this file is to keep the suite off the live OpenAI API. With a
working key in the environment, the paper-upload tests each spend a real AI parse
of twenty to thirty seconds, which turned a one minute run into five and a half
and charged for the privilege. The parsers all fall back to their built-in path
when no key is present, so the tests still cover the behaviour they claim to.

A test that genuinely needs the network says so with @pytest.mark.requires_openai
and gets the key back.
"""

import pytest


@pytest.fixture(autouse=True)
def offline_by_default(request, monkeypatch):
    """Hide the API key unless a test asks for it."""
    if request.node.get_closest_marker("requires_openai"):
        return
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
