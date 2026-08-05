"""
Tests for the personal access token.

This is the credential a script or the MCP server presents instead of an Auth0
token. It stands for one named account, so the important properties are that
the right token reaches that account, and that everything else does not.
"""

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from my_revision_helper.auth import (
    MIN_TOKEN_LENGTH,
    get_current_user_optional,
    personal_token_user,
)

GOOD_TOKEN = "x" * 48
USER = "auth0|1234567890abcdef"


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("API_TOKEN_USER_ID", USER)
    # Auth0 deliberately left unconfigured: the token has to work without it.
    monkeypatch.delenv("AUTH0_DOMAIN", raising=False)
    monkeypatch.delenv("AUTH0_AUDIENCE", raising=False)


@pytest.mark.unit
class TestWhenTheTokenIsConfigured:
    def test_it_is_reported_as_configured(self, configured):
        assert personal_token_user()["user_id"] == USER

    async def test_the_right_token_arrives_as_the_named_user(self, configured):
        user = await get_current_user_optional(_credentials(GOOD_TOKEN))

        assert user is not None
        assert user["user_id"] == USER

    async def test_a_wrong_token_stays_anonymous(self, configured):
        assert await get_current_user_optional(_credentials("y" * 48)) is None

    async def test_a_token_of_the_right_length_but_wrong_value_stays_anonymous(self, configured):
        assert await get_current_user_optional(_credentials("x" * 47 + "y")) is None

    async def test_no_token_at_all_stays_anonymous(self, configured):
        assert await get_current_user_optional(None) is None

    async def test_an_empty_token_stays_anonymous(self, configured):
        assert await get_current_user_optional(_credentials("")) is None

    async def test_it_does_not_claim_a_name_or_email_it_does_not_know(self, configured):
        """The Auth0 profile is the source of those, and must not be overwritten."""
        user = await get_current_user_optional(_credentials(GOOD_TOKEN))

        assert user["email"] is None
        assert user["name"] is None


@pytest.mark.unit
class TestWhenItIsNotConfiguredProperly:
    async def test_nothing_is_set_so_nothing_authenticates(self, monkeypatch):
        monkeypatch.delenv("API_TOKEN", raising=False)
        monkeypatch.delenv("API_TOKEN_USER_ID", raising=False)

        assert personal_token_user() is None
        assert await get_current_user_optional(_credentials(GOOD_TOKEN)) is None

    async def test_a_token_with_no_user_id_is_refused(self, monkeypatch):
        """Otherwise a script lands in an empty world of its own."""
        monkeypatch.setenv("API_TOKEN", GOOD_TOKEN)
        monkeypatch.delenv("API_TOKEN_USER_ID", raising=False)

        assert personal_token_user() is None
        assert await get_current_user_optional(_credentials(GOOD_TOKEN)) is None

    async def test_a_user_id_with_no_token_authenticates_nobody(self, monkeypatch):
        monkeypatch.delenv("API_TOKEN", raising=False)
        monkeypatch.setenv("API_TOKEN_USER_ID", USER)

        assert personal_token_user() is None
        assert await get_current_user_optional(_credentials("")) is None

    async def test_a_short_token_is_refused_rather_than_trusted(self, monkeypatch, caplog):
        """A guessable secret that looks like security is worse than none."""
        short = "x" * (MIN_TOKEN_LENGTH - 1)
        monkeypatch.setenv("API_TOKEN", short)
        monkeypatch.setenv("API_TOKEN_USER_ID", USER)

        assert personal_token_user() is None
        assert await get_current_user_optional(_credentials(short)) is None
        assert "too short" in caplog.text

    async def test_whitespace_around_the_value_is_ignored(self, monkeypatch):
        """Copying out of a terminal or a Railway variable box picks up spaces."""
        monkeypatch.setenv("API_TOKEN", f"  {GOOD_TOKEN}\n")
        monkeypatch.setenv("API_TOKEN_USER_ID", f" {USER} ")

        user = await get_current_user_optional(_credentials(GOOD_TOKEN))
        assert user["user_id"] == USER


@pytest.mark.integration
class TestThroughTheApi:
    """The token has to work on a real request, not just on the dependency."""

    def test_it_is_recognised_by_the_who_am_i_endpoint(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", GOOD_TOKEN)
        monkeypatch.setenv("API_TOKEN_USER_ID", USER)

        from fastapi.testclient import TestClient

        from my_revision_helper.api import app

        client = TestClient(app)
        response = client.get("/api/user/me", headers={"Authorization": f"Bearer {GOOD_TOKEN}"})

        assert response.status_code == 200
        body = response.json()
        assert body["authenticated"] is True
        assert body["user_id"] == USER

    def test_without_it_the_same_request_is_anonymous(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", GOOD_TOKEN)
        monkeypatch.setenv("API_TOKEN_USER_ID", USER)

        from fastapi.testclient import TestClient

        from my_revision_helper.api import app

        client = TestClient(app)

        assert client.get("/api/user/me").json()["authenticated"] is False
