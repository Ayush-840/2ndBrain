"""Tests for the frontend authentication module.

Tests the core auth logic (password hashing, credential verification,
session management) without requiring a running NiceGUI instance.
"""

import time
from unittest.mock import patch

from backend.frontend.auth import (
    _hash_password,
    verify_credentials,
    create_session,
    get_session,
    destroy_session,
    _sessions,
    SESSION_MAX_AGE,
    SESSION_IDLE_MAX,
    Session,
)


class TestPasswordHashing:
    def test_hash_deterministic(self):
        h1 = _hash_password("mypassword")
        h2 = _hash_password("mypassword")
        assert h1 == h2

    def test_hash_different_passwords(self):
        h1 = _hash_password("password1")
        h2 = _hash_password("password2")
        assert h1 != h2

    def test_hash_is_hex_64_chars(self):
        h = _hash_password("test")
        assert all(c in "0123456789abcdef" for c in h)
        assert len(h) == 64  # SHA-256


class TestVerifyCredentials:
    @patch("backend.frontend.auth.settings")
    def test_valid_credentials(self, mock_settings):
        mock_settings.auth_enabled = True
        mock_settings.auth_username = "admin"
        mock_settings.auth_password = "secret123"
        mock_settings.auth_password_hash = ""
        assert verify_credentials("admin", "secret123") is True

    @patch("backend.frontend.auth.settings")
    def test_wrong_password(self, mock_settings):
        mock_settings.auth_enabled = True
        mock_settings.auth_username = "admin"
        mock_settings.auth_password = "secret123"
        mock_settings.auth_password_hash = ""
        assert verify_credentials("admin", "wrong") is False

    @patch("backend.frontend.auth.settings")
    def test_wrong_username(self, mock_settings):
        mock_settings.auth_enabled = True
        mock_settings.auth_username = "admin"
        mock_settings.auth_password = "secret123"
        mock_settings.auth_password_hash = ""
        assert verify_credentials("user", "secret123") is False

    @patch("backend.frontend.auth.settings")
    def test_auth_disabled(self, mock_settings):
        mock_settings.auth_enabled = False
        assert verify_credentials("anything", "anything") is True

    @patch("backend.frontend.auth.settings")
    def test_prehashed_password(self, mock_settings):
        mock_settings.auth_enabled = True
        mock_settings.auth_username = "admin"
        mock_settings.auth_password = "ignored"
        mock_settings.auth_password_hash = _hash_password("hashed_pass")
        assert verify_credentials("admin", "hashed_pass") is True
        assert verify_credentials("admin", "wrong") is False

    @patch("backend.frontend.auth.settings")
    def test_empty_password(self, mock_settings):
        mock_settings.auth_enabled = True
        mock_settings.auth_username = "admin"
        mock_settings.auth_password = ""
        mock_settings.auth_password_hash = ""
        assert verify_credentials("admin", "") is True
        assert verify_credentials("admin", "anything") is False


class TestSessionManagement:
    def setup_method(self):
        _sessions.clear()

    def test_create_session(self):
        token = create_session("alice")
        assert isinstance(token, str)
        assert len(token) > 20
        assert token in _sessions
        assert _sessions[token].user == "alice"

    def test_get_session_valid(self):
        token = create_session("bob")
        session = get_session(token)
        assert session is not None
        assert session.user == "bob"

    def test_get_session_invalid_token(self):
        assert get_session("nonexistent") is None
        assert get_session(None) is None
        assert get_session("") is None

    def test_session_expiry(self):
        token = create_session("charlie")
        _sessions[token].created_at = time.time() - SESSION_MAX_AGE - 1
        session = get_session(token)
        assert session is None
        assert token not in _sessions

    def test_session_idle_timeout(self):
        token = create_session("dave")
        _sessions[token].last_seen = time.time() - SESSION_IDLE_MAX - 1
        session = get_session(token)
        assert session is None

    def test_session_touches_last_seen(self):
        token = create_session("eve")
        old_last_seen = _sessions[token].last_seen
        time.sleep(0.01)
        get_session(token)
        assert _sessions[token].last_seen > old_last_seen

    def test_destroy_session(self):
        token = create_session("frank")
        assert get_session(token) is not None
        destroy_session(token)
        assert get_session(token) is None

    def test_destroy_nonexistent(self):
        destroy_session("nonexistent")

    def test_multiple_sessions(self):
        t1 = create_session("user1")
        t2 = create_session("user2")
        assert get_session(t1).user == "user1"
        assert get_session(t2).user == "user2"
        assert len(_sessions) == 2

    def test_session_tokens_are_unique(self):
        tokens = {create_session("user") for _ in range(10)}
        assert len(tokens) == 10


class TestSessionDataclass:
    def test_age_seconds(self):
        s = Session(user="test")
        assert 0 <= s.age_seconds < 1

    def test_idle_seconds(self):
        s = Session(user="test")
        assert 0 <= s.idle_seconds < 1

    def test_session_defaults(self):
        s = Session(user="alice")
        assert s.user == "alice"
        assert s.created_at > 0
        assert s.last_seen > 0
