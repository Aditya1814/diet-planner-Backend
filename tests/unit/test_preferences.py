"""Unit tests for dietary preferences endpoint."""

from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.main import app
from app.routes.preferences import (
    get_week_start_date,
    VALID_PREFERENCES,
    _get_preferences_for_week,
)

client = TestClient(app)


def _create_auth_token(user_id: str = "user-123") -> str:
    """Create a valid JWT token for testing."""
    payload = {"sub": user_id, "aud": "authenticated", "exp": 9999999999}
    return jwt.encode(payload, "test-secret", algorithm="HS256")


def _auth_headers(user_id: str = "user-123") -> dict:
    """Create authorization headers with a valid JWT."""
    token = _create_auth_token(user_id)
    return {"Authorization": f"Bearer {token}"}


class TestGetWeekStartDate:
    """Tests for week start date calculation."""

    def test_monday_returns_same_date(self):
        # 2024-01-01 is a Monday
        monday = date(2024, 1, 1)
        assert get_week_start_date(monday) == monday

    def test_wednesday_returns_monday(self):
        # 2024-01-03 is a Wednesday
        wednesday = date(2024, 1, 3)
        expected_monday = date(2024, 1, 1)
        assert get_week_start_date(wednesday) == expected_monday

    def test_sunday_returns_monday(self):
        # 2024-01-07 is a Sunday
        sunday = date(2024, 1, 7)
        expected_monday = date(2024, 1, 1)
        assert get_week_start_date(sunday) == expected_monday

    def test_saturday_returns_monday(self):
        # 2024-01-06 is a Saturday
        saturday = date(2024, 1, 6)
        expected_monday = date(2024, 1, 1)
        assert get_week_start_date(saturday) == expected_monday

    def test_no_reference_date_uses_today(self):
        result = get_week_start_date()
        today = date.today()
        days_since_monday = today.weekday()
        expected = today - timedelta(days=days_since_monday)
        assert result == expected


class TestValidPreferences:
    """Tests for predefined dietary preference options."""

    def test_contains_vegetarian(self):
        assert "vegetarian" in VALID_PREFERENCES

    def test_contains_vegan(self):
        assert "vegan" in VALID_PREFERENCES

    def test_contains_low_carb(self):
        assert "low-carb" in VALID_PREFERENCES

    def test_contains_gluten_free(self):
        assert "gluten-free" in VALID_PREFERENCES

    def test_contains_dairy_free(self):
        assert "dairy-free" in VALID_PREFERENCES

    def test_contains_nut_free(self):
        assert "nut-free" in VALID_PREFERENCES

    def test_has_exactly_six_options(self):
        assert len(VALID_PREFERENCES) == 6


class TestGetCurrentPreferencesEndpoint:
    """Tests for GET /api/preferences/current."""

    def test_requires_authentication(self):
        response = client.get("/api/preferences/current")
        assert response.status_code == 403

    @patch("app.routes.preferences.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_returns_current_week_preferences(self, mock_settings, mock_supabase):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        mock_client = MagicMock()
        # Mock grocery list query - found for current week
        grocery_list_response = MagicMock()
        grocery_list_response.data = [{"id": "list-123"}]

        # Mock preferences query
        preferences_response = MagicMock()
        preferences_response.data = [
            {"preference": "vegetarian"},
            {"preference": "gluten-free"},
        ]

        # Chain the mock calls
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq1
        mock_eq1.eq.return_value = mock_eq2
        mock_eq2.execute.return_value = grocery_list_response

        # For the second call (preferences)
        mock_table2 = MagicMock()
        mock_select2 = MagicMock()
        mock_eq3 = MagicMock()

        # We need to handle multiple calls to table()
        call_count = [0]
        original_table = mock_client.table

        def table_side_effect(name):
            call_count[0] += 1
            if call_count[0] <= 1:
                return mock_table
            else:
                return mock_table2

        mock_client.table.side_effect = table_side_effect
        mock_table2.select.return_value = mock_select2
        mock_select2.eq.return_value = mock_eq3
        mock_eq3.execute.return_value = preferences_response

        mock_supabase.return_value = mock_client

        response = client.get(
            "/api/preferences/current",
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["preferences"] == ["vegetarian", "gluten-free"]
        assert data["is_carry_over"] is False

    @patch("app.routes.preferences.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_returns_empty_when_no_preferences_exist(
        self, mock_settings, mock_supabase
    ):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        mock_client = MagicMock()
        # Mock grocery list query - not found for any week
        empty_response = MagicMock()
        empty_response.data = []

        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq1
        mock_eq1.eq.return_value = mock_eq2
        mock_eq2.execute.return_value = empty_response

        mock_supabase.return_value = mock_client

        response = client.get(
            "/api/preferences/current",
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["preferences"] == []
        assert data["is_carry_over"] is False

    @patch("app.routes.preferences.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_carries_over_previous_week_preferences(
        self, mock_settings, mock_supabase
    ):
        """When no current week preferences exist, returns previous week's (carry-over)."""
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        mock_client = MagicMock()

        # First call: current week grocery list - not found
        empty_response = MagicMock()
        empty_response.data = []

        # Second call: previous week grocery list - found
        prev_grocery_response = MagicMock()
        prev_grocery_response.data = [{"id": "prev-list-456"}]

        # Third call: previous week preferences - found
        prev_prefs_response = MagicMock()
        prev_prefs_response.data = [
            {"preference": "vegan"},
            {"preference": "dairy-free"},
        ]

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            mock_table = MagicMock()
            mock_select = MagicMock()
            mock_eq1 = MagicMock()
            mock_eq2 = MagicMock()

            if call_count[0] == 1:
                # Current week grocery list query - not found
                mock_eq2.execute.return_value = empty_response
                mock_eq1.eq.return_value = mock_eq2
            elif call_count[0] == 2:
                # Previous week grocery list query - found
                mock_eq2.execute.return_value = prev_grocery_response
                mock_eq1.eq.return_value = mock_eq2
            else:
                # Previous week preferences query
                mock_eq1.execute.return_value = prev_prefs_response

            mock_select.eq.return_value = mock_eq1
            mock_table.select.return_value = mock_select
            return mock_table

        mock_client.table.side_effect = table_side_effect
        mock_supabase.return_value = mock_client

        response = client.get(
            "/api/preferences/current",
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["preferences"] == ["vegan", "dairy-free"]
        assert data["is_carry_over"] is True


class TestGetPreferencesForWeek:
    """Tests for the _get_preferences_for_week helper function."""

    def test_returns_none_when_no_grocery_list(self):
        mock_client = MagicMock()
        empty_response = MagicMock()
        empty_response.data = []

        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq1
        mock_eq1.eq.return_value = mock_eq2
        mock_eq2.execute.return_value = empty_response

        result = _get_preferences_for_week(
            mock_client, "user-123", date(2024, 1, 1)
        )
        assert result is None

    def test_returns_empty_list_when_grocery_list_has_no_preferences(self):
        mock_client = MagicMock()

        # Grocery list found
        grocery_response = MagicMock()
        grocery_response.data = [{"id": "list-123"}]

        # No preferences
        prefs_response = MagicMock()
        prefs_response.data = []

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            mock_table = MagicMock()
            mock_select = MagicMock()
            mock_eq1 = MagicMock()
            mock_eq2 = MagicMock()

            if call_count[0] == 1:
                mock_eq2.execute.return_value = grocery_response
                mock_eq1.eq.return_value = mock_eq2
            else:
                mock_eq1.execute.return_value = prefs_response

            mock_select.eq.return_value = mock_eq1
            mock_table.select.return_value = mock_select
            return mock_table

        mock_client.table.side_effect = table_side_effect

        result = _get_preferences_for_week(
            mock_client, "user-123", date(2024, 1, 1)
        )
        assert result == []

    def test_returns_preferences_list(self):
        mock_client = MagicMock()

        # Grocery list found
        grocery_response = MagicMock()
        grocery_response.data = [{"id": "list-123"}]

        # Preferences found
        prefs_response = MagicMock()
        prefs_response.data = [
            {"preference": "vegan"},
            {"preference": "nut-free"},
        ]

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            mock_table = MagicMock()
            mock_select = MagicMock()
            mock_eq1 = MagicMock()
            mock_eq2 = MagicMock()

            if call_count[0] == 1:
                mock_eq2.execute.return_value = grocery_response
                mock_eq1.eq.return_value = mock_eq2
            else:
                mock_eq1.execute.return_value = prefs_response

            mock_select.eq.return_value = mock_eq1
            mock_table.select.return_value = mock_select
            return mock_table

        mock_client.table.side_effect = table_side_effect

        result = _get_preferences_for_week(
            mock_client, "user-123", date(2024, 1, 1)
        )
        assert result == ["vegan", "nut-free"]
