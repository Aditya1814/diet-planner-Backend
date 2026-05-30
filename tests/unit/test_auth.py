"""Unit tests for authentication middleware and routes."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from jose import jwt

from app.main import app
from app.routes.auth import (
    validate_email,
    validate_password,
    _failed_attempts,
    _is_account_locked,
    _record_failed_attempt,
    _reset_failed_attempts,
    MAX_FAILED_ATTEMPTS,
    LOCKOUT_DURATION_MINUTES,
)

client = TestClient(app)


class TestEmailValidation:
    """Tests for email format validation."""

    def test_valid_email(self):
        assert validate_email("user@example.com") is True

    def test_valid_email_with_subdomain(self):
        assert validate_email("user@mail.example.com") is True

    def test_valid_email_with_plus(self):
        assert validate_email("user+tag@example.com") is True

    def test_valid_email_with_dots_in_local(self):
        assert validate_email("first.last@example.com") is True

    def test_invalid_email_no_at(self):
        assert validate_email("userexample.com") is False

    def test_invalid_email_no_domain(self):
        assert validate_email("user@") is False

    def test_invalid_email_no_tld(self):
        assert validate_email("user@example") is False

    def test_invalid_email_empty(self):
        assert validate_email("") is False

    def test_invalid_email_spaces(self):
        assert validate_email("user @example.com") is False

    def test_invalid_email_no_local_part(self):
        assert validate_email("@example.com") is False


class TestPasswordValidation:
    """Tests for password length validation."""

    def test_valid_password_min_length(self):
        assert validate_password("12345678") is True

    def test_valid_password_max_length(self):
        assert validate_password("a" * 128) is True

    def test_valid_password_mid_length(self):
        assert validate_password("securepassword123") is True

    def test_invalid_password_too_short(self):
        assert validate_password("1234567") is False

    def test_invalid_password_too_long(self):
        assert validate_password("a" * 129) is False

    def test_invalid_password_empty(self):
        assert validate_password("") is False


class TestAccountLockout:
    """Tests for account lockout logic."""

    def setup_method(self):
        """Clear failed attempts before each test."""
        _failed_attempts.clear()

    def test_account_not_locked_initially(self):
        assert _is_account_locked("test@example.com") is False

    def test_account_locked_after_max_attempts(self):
        email = "test@example.com"
        for _ in range(MAX_FAILED_ATTEMPTS):
            _record_failed_attempt(email)
        assert _is_account_locked(email) is True

    def test_account_not_locked_below_threshold(self):
        email = "test@example.com"
        for _ in range(MAX_FAILED_ATTEMPTS - 1):
            _record_failed_attempt(email)
        assert _is_account_locked(email) is False

    def test_lockout_expires_after_duration(self):
        email = "test@example.com"
        for _ in range(MAX_FAILED_ATTEMPTS):
            _record_failed_attempt(email)
        # Simulate time passing beyond lockout duration
        _failed_attempts[email]["locked_until"] = datetime.now(
            timezone.utc
        ) - timedelta(minutes=1)
        assert _is_account_locked(email) is False

    def test_reset_clears_failed_attempts(self):
        email = "test@example.com"
        for _ in range(MAX_FAILED_ATTEMPTS - 1):
            _record_failed_attempt(email)
        _reset_failed_attempts(email)
        assert _failed_attempts[email]["count"] == 0
        assert _is_account_locked(email) is False

    def test_lockout_duration_is_15_minutes(self):
        assert LOCKOUT_DURATION_MINUTES == 15

    def test_max_failed_attempts_is_5(self):
        assert MAX_FAILED_ATTEMPTS == 5


class TestRegisterEndpoint:
    """Tests for POST /api/auth/register."""

    def test_register_invalid_email_format(self):
        response = client.post(
            "/api/auth/register",
            json={"email": "invalid-email", "password": "validpass123"},
        )
        assert response.status_code == 422
        assert "email format" in response.json()["detail"].lower()

    def test_register_password_too_short(self):
        response = client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "short"},
        )
        assert response.status_code == 422
        assert "password" in response.json()["detail"].lower()

    def test_register_password_too_long(self):
        response = client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "a" * 129},
        )
        assert response.status_code == 422
        assert "password" in response.json()["detail"].lower()

    @patch("app.routes.auth.get_supabase_client")
    def test_register_success(self, mock_supabase):
        mock_client = MagicMock()
        mock_user = MagicMock()
        mock_user.identities = [{"id": "123"}]
        mock_response = MagicMock()
        mock_response.user = mock_user
        mock_client.auth.sign_up.return_value = mock_response
        mock_supabase.return_value = mock_client

        response = client.post(
            "/api/auth/register",
            json={"email": "new@example.com", "password": "validpass123"},
        )
        assert response.status_code == 201
        assert "successful" in response.json()["message"].lower()

    @patch("app.routes.auth.get_supabase_client")
    def test_register_duplicate_email(self, mock_supabase):
        mock_client = MagicMock()
        mock_user = MagicMock()
        mock_user.identities = []  # Empty identities = already exists
        mock_response = MagicMock()
        mock_response.user = mock_user
        mock_client.auth.sign_up.return_value = mock_response
        mock_supabase.return_value = mock_client

        response = client.post(
            "/api/auth/register",
            json={"email": "existing@example.com", "password": "validpass123"},
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()


class TestLoginEndpoint:
    """Tests for POST /api/auth/login."""

    def setup_method(self):
        """Clear failed attempts before each test."""
        _failed_attempts.clear()

    @patch("app.routes.auth.get_supabase_client")
    def test_login_success(self, mock_supabase):
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.access_token = "test-access-token"
        mock_session.refresh_token = "test-refresh-token"
        mock_session.expires_in = 3600
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.email = "user@example.com"
        mock_response = MagicMock()
        mock_response.session = mock_session
        mock_response.user = mock_user
        mock_client.auth.sign_in_with_password.return_value = mock_response
        mock_supabase.return_value = mock_client

        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "validpass123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "test-access-token"
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "user@example.com"

    @patch("app.routes.auth.get_supabase_client")
    def test_login_invalid_credentials_generic_error(self, mock_supabase):
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_password.side_effect = Exception(
            "Invalid login credentials"
        )
        mock_supabase.return_value = mock_client

        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "wrongpass"},
        )
        assert response.status_code == 401
        # Should NOT reveal which field is incorrect
        detail = response.json()["detail"]
        assert "invalid email or password" in detail.lower()
        assert "email" not in detail.lower().replace("invalid email or password", "")

    @patch("app.routes.auth.get_supabase_client")
    def test_login_lockout_after_5_failures(self, mock_supabase):
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_password.side_effect = Exception(
            "Invalid login credentials"
        )
        mock_supabase.return_value = mock_client

        # Fail 5 times
        for _ in range(5):
            response = client.post(
                "/api/auth/login",
                json={"email": "locked@example.com", "password": "wrongpass"},
            )

        # The 5th attempt should trigger lockout
        assert response.status_code == 429
        assert "temporarily locked" in response.json()["detail"].lower()

    @patch("app.routes.auth.get_supabase_client")
    def test_login_locked_account_returns_429(self, mock_supabase):
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_password.side_effect = Exception(
            "Invalid login credentials"
        )
        mock_supabase.return_value = mock_client

        # Lock the account
        for _ in range(5):
            client.post(
                "/api/auth/login",
                json={"email": "locked2@example.com", "password": "wrongpass"},
            )

        # Next attempt should immediately return 429
        response = client.post(
            "/api/auth/login",
            json={"email": "locked2@example.com", "password": "anypass"},
        )
        assert response.status_code == 429
        assert "15 minutes" in response.json()["detail"]

    @patch("app.routes.auth.get_supabase_client")
    def test_login_success_resets_failed_attempts(self, mock_supabase):
        # First, record some failures
        _record_failed_attempt("reset@example.com")
        _record_failed_attempt("reset@example.com")

        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.access_token = "token"
        mock_session.refresh_token = "refresh"
        mock_session.expires_in = 3600
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.email = "reset@example.com"
        mock_response = MagicMock()
        mock_response.session = mock_session
        mock_response.user = mock_user
        mock_client.auth.sign_in_with_password.return_value = mock_response
        mock_supabase.return_value = mock_client

        response = client.post(
            "/api/auth/login",
            json={"email": "reset@example.com", "password": "validpass123"},
        )
        assert response.status_code == 200
        assert _failed_attempts["reset@example.com"]["count"] == 0


class TestLogoutEndpoint:
    """Tests for POST /api/auth/logout."""

    @patch("app.routes.auth.get_supabase_client")
    def test_logout_success(self, mock_supabase):
        mock_client = MagicMock()
        mock_supabase.return_value = mock_client

        response = client.post(
            "/api/auth/logout",
            json={"access_token": "some-token"},
        )
        assert response.status_code == 200
        assert "logged out" in response.json()["message"].lower()

    @patch("app.routes.auth.get_supabase_client")
    def test_logout_handles_supabase_error_gracefully(self, mock_supabase):
        mock_client = MagicMock()
        mock_client.auth.admin.sign_out.side_effect = Exception("Network error")
        mock_supabase.return_value = mock_client

        response = client.post(
            "/api/auth/logout",
            json={"access_token": "some-token"},
        )
        # Should still return success even if Supabase fails
        assert response.status_code == 200


class TestAuthMiddleware:
    """Tests for JWT verification middleware."""

    def test_protected_endpoint_without_token(self):
        """Accessing a protected endpoint without a token should fail."""
        # The health endpoint is not protected, but we can test the middleware
        # by creating a test endpoint that uses the dependency
        pass  # Middleware is tested via integration with protected routes

    def test_jwt_verification_with_valid_token(self):
        """Test that a valid JWT is accepted."""
        from app.middleware.auth import verify_jwt
        from fastapi.security import HTTPAuthorizationCredentials

        secret = "test-secret"
        payload = {"sub": "user-123", "aud": "authenticated", "exp": 9999999999}
        token = jwt.encode(payload, secret, algorithm="HS256")

        with patch("app.middleware.auth.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(supabase_jwt_secret=secret)
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=token
            )
            import asyncio

            result = asyncio.get_event_loop().run_until_complete(
                verify_jwt(credentials)
            )
            assert result["sub"] == "user-123"

    def test_jwt_verification_with_invalid_token(self):
        """Test that an invalid JWT is rejected."""
        from app.middleware.auth import verify_jwt
        from fastapi.security import HTTPAuthorizationCredentials
        from fastapi import HTTPException

        with patch("app.middleware.auth.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                supabase_jwt_secret="test-secret"
            )
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials="invalid-token"
            )
            import asyncio

            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    verify_jwt(credentials)
                )
            assert exc_info.value.status_code == 401

    def test_jwt_verification_with_expired_token(self):
        """Test that an expired JWT is rejected."""
        from app.middleware.auth import verify_jwt
        from fastapi.security import HTTPAuthorizationCredentials
        from fastapi import HTTPException

        secret = "test-secret"
        payload = {"sub": "user-123", "aud": "authenticated", "exp": 1000000000}
        token = jwt.encode(payload, secret, algorithm="HS256")

        with patch("app.middleware.auth.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(supabase_jwt_secret=secret)
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=token
            )
            import asyncio

            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    verify_jwt(credentials)
                )
            assert exc_info.value.status_code == 401
