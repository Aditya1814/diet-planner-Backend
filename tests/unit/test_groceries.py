"""Unit tests for grocery list endpoints."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.main import app
from app.routes.groceries import get_week_start_date

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
    """Tests for week boundary calculation (Monday–Sunday)."""

    def test_monday_returns_same_date(self):
        monday = date(2024, 1, 1)  # Monday
        assert get_week_start_date(monday) == monday

    def test_tuesday_returns_monday(self):
        tuesday = date(2024, 1, 2)
        assert get_week_start_date(tuesday) == date(2024, 1, 1)

    def test_wednesday_returns_monday(self):
        wednesday = date(2024, 1, 3)
        assert get_week_start_date(wednesday) == date(2024, 1, 1)

    def test_thursday_returns_monday(self):
        thursday = date(2024, 1, 4)
        assert get_week_start_date(thursday) == date(2024, 1, 1)

    def test_friday_returns_monday(self):
        friday = date(2024, 1, 5)
        assert get_week_start_date(friday) == date(2024, 1, 1)

    def test_saturday_returns_monday(self):
        saturday = date(2024, 1, 6)
        assert get_week_start_date(saturday) == date(2024, 1, 1)

    def test_sunday_returns_monday(self):
        sunday = date(2024, 1, 7)
        assert get_week_start_date(sunday) == date(2024, 1, 1)

    def test_no_argument_uses_today(self):
        result = get_week_start_date()
        today = date.today()
        expected = today - timedelta(days=today.weekday())
        assert result == expected

    def test_result_is_always_a_monday(self):
        # Test multiple dates across different weeks
        for day_offset in range(14):
            test_date = date(2024, 3, 1) + timedelta(days=day_offset)
            result = get_week_start_date(test_date)
            assert result.weekday() == 0  # 0 = Monday


class TestSubmitGroceryListValidation:
    """Tests for POST /api/groceries input validation."""

    @patch("app.middleware.auth.get_settings")
    def test_requires_authentication(self, mock_settings):
        response = client.post("/api/groceries", json={
            "items": [{"name": "Chicken", "quantity": 2.0, "unit": "kg"}]
        })
        assert response.status_code == 403

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_rejects_empty_items_list(self, mock_settings, mock_supabase):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        response = client.post(
            "/api/groceries",
            json={"items": []},
            headers=_auth_headers(),
        )
        assert response.status_code == 422

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_rejects_more_than_50_items(self, mock_settings, mock_supabase):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        items = [
            {"name": f"Item {i}", "quantity": 1.0, "unit": "kg"}
            for i in range(51)
        ]
        response = client.post(
            "/api/groceries",
            json={"items": items},
            headers=_auth_headers(),
        )
        assert response.status_code == 422

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_rejects_empty_item_name(self, mock_settings, mock_supabase):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        response = client.post(
            "/api/groceries",
            json={"items": [{"name": "", "quantity": 1.0, "unit": "kg"}]},
            headers=_auth_headers(),
        )
        assert response.status_code == 422

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_rejects_item_name_over_100_chars(self, mock_settings, mock_supabase):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        response = client.post(
            "/api/groceries",
            json={"items": [{"name": "A" * 101, "quantity": 1.0, "unit": "kg"}]},
            headers=_auth_headers(),
        )
        assert response.status_code == 422

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_rejects_quantity_below_minimum(self, mock_settings, mock_supabase):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        response = client.post(
            "/api/groceries",
            json={"items": [{"name": "Chicken", "quantity": 0.001, "unit": "kg"}]},
            headers=_auth_headers(),
        )
        assert response.status_code == 422

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_rejects_quantity_above_maximum(self, mock_settings, mock_supabase):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        response = client.post(
            "/api/groceries",
            json={"items": [{"name": "Chicken", "quantity": 10000.0, "unit": "kg"}]},
            headers=_auth_headers(),
        )
        assert response.status_code == 422

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_rejects_zero_quantity(self, mock_settings, mock_supabase):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        response = client.post(
            "/api/groceries",
            json={"items": [{"name": "Chicken", "quantity": 0, "unit": "kg"}]},
            headers=_auth_headers(),
        )
        assert response.status_code == 422

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_rejects_empty_unit(self, mock_settings, mock_supabase):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        response = client.post(
            "/api/groceries",
            json={"items": [{"name": "Chicken", "quantity": 1.0, "unit": ""}]},
            headers=_auth_headers(),
        )
        assert response.status_code == 422

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_rejects_unit_over_20_chars(self, mock_settings, mock_supabase):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        response = client.post(
            "/api/groceries",
            json={"items": [{"name": "Chicken", "quantity": 1.0, "unit": "x" * 21}]},
            headers=_auth_headers(),
        )
        assert response.status_code == 422


class TestSubmitGroceryListSuccess:
    """Tests for successful POST /api/groceries submissions."""

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_creates_new_grocery_list(self, mock_settings, mock_supabase):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        mock_client = MagicMock()
        mock_supabase.return_value = mock_client

        # Mock: no existing grocery list
        existing_response = MagicMock()
        existing_response.data = []

        # Mock: insert grocery list
        insert_list_response = MagicMock()
        insert_list_response.data = [{"id": "list-abc"}]

        # Mock: insert grocery items
        insert_items_response = MagicMock()
        insert_items_response.data = [
            {
                "id": "item-1",
                "name": "Chicken",
                "quantity": 2.0,
                "unit": "kg",
                "remaining_quantity": 2.0,
            }
        ]

        # Mock: insert preferences
        insert_prefs_response = MagicMock()
        insert_prefs_response.data = [{"id": "pref-1", "preference": "low-carb"}]

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            mock_table = MagicMock()

            if call_count[0] == 1:
                # grocery_lists select (check existing)
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_eq2.execute.return_value = existing_response
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select
            elif call_count[0] == 2:
                # grocery_lists insert
                mock_insert = MagicMock()
                mock_insert.execute.return_value = insert_list_response
                mock_table.insert.return_value = mock_insert
            elif call_count[0] == 3:
                # grocery_items insert
                mock_insert = MagicMock()
                mock_insert.execute.return_value = insert_items_response
                mock_table.insert.return_value = mock_insert
            elif call_count[0] == 4:
                # dietary_preferences insert
                mock_insert = MagicMock()
                mock_insert.execute.return_value = insert_prefs_response
                mock_table.insert.return_value = mock_insert

            return mock_table

        mock_client.table.side_effect = table_side_effect

        response = client.post(
            "/api/groceries",
            json={
                "items": [{"name": "Chicken", "quantity": 2.0, "unit": "kg"}],
                "dietary_preferences": ["low-carb"],
            },
            headers=_auth_headers(),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "list-abc"
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Chicken"
        assert float(data["items"][0]["quantity"]) == 2.0
        assert data["items"][0]["unit"] == "kg"
        assert float(data["items"][0]["remaining_quantity"]) == 2.0
        assert data["dietary_preferences"] == ["low-carb"]

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_replaces_existing_grocery_list(self, mock_settings, mock_supabase):
        """On new submission, replaces previous inventory."""
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        mock_client = MagicMock()
        mock_supabase.return_value = mock_client

        # Mock: existing grocery list found
        existing_response = MagicMock()
        existing_response.data = [{"id": "list-existing"}]

        # Mock: insert grocery items (new items with remaining_quantity = quantity)
        insert_items_response = MagicMock()
        insert_items_response.data = [
            {
                "id": "item-new",
                "name": "Rice",
                "quantity": 5.0,
                "unit": "kg",
                "remaining_quantity": 5.0,
            }
        ]

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            mock_table = MagicMock()

            if call_count[0] == 1:
                # grocery_lists select (check existing)
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_eq2.execute.return_value = existing_response
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select
            elif call_count[0] == 2:
                # grocery_items delete
                mock_delete = MagicMock()
                mock_eq = MagicMock()
                mock_eq.execute.return_value = MagicMock()
                mock_delete.eq.return_value = mock_eq
                mock_table.delete.return_value = mock_delete
            elif call_count[0] == 3:
                # dietary_preferences delete
                mock_delete = MagicMock()
                mock_eq = MagicMock()
                mock_eq.execute.return_value = MagicMock()
                mock_delete.eq.return_value = mock_eq
                mock_table.delete.return_value = mock_delete
            elif call_count[0] == 4:
                # grocery_lists update (updated_at)
                mock_update = MagicMock()
                mock_eq = MagicMock()
                mock_eq.execute.return_value = MagicMock()
                mock_update.eq.return_value = mock_eq
                mock_table.update.return_value = mock_update
            elif call_count[0] == 5:
                # grocery_items insert
                mock_insert = MagicMock()
                mock_insert.execute.return_value = insert_items_response
                mock_table.insert.return_value = mock_insert
            # No call 6 since no dietary_preferences in this test

            return mock_table

        mock_client.table.side_effect = table_side_effect

        response = client.post(
            "/api/groceries",
            json={
                "items": [{"name": "Rice", "quantity": 5.0, "unit": "kg"}],
                "dietary_preferences": [],
            },
            headers=_auth_headers(),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "list-existing"
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Rice"
        # remaining_quantity should equal submitted quantity (inventory replacement)
        assert float(data["items"][0]["remaining_quantity"]) == 5.0

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_accepts_boundary_valid_quantity_min(self, mock_settings, mock_supabase):
        """Accepts quantity at minimum boundary (0.01)."""
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        mock_client = MagicMock()
        mock_supabase.return_value = mock_client

        existing_response = MagicMock()
        existing_response.data = []

        insert_list_response = MagicMock()
        insert_list_response.data = [{"id": "list-1"}]

        insert_items_response = MagicMock()
        insert_items_response.data = [
            {
                "id": "item-1",
                "name": "Salt",
                "quantity": 0.01,
                "unit": "kg",
                "remaining_quantity": 0.01,
            }
        ]

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            mock_table = MagicMock()

            if call_count[0] == 1:
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_eq2.execute.return_value = existing_response
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select
            elif call_count[0] == 2:
                mock_insert = MagicMock()
                mock_insert.execute.return_value = insert_list_response
                mock_table.insert.return_value = mock_insert
            elif call_count[0] == 3:
                mock_insert = MagicMock()
                mock_insert.execute.return_value = insert_items_response
                mock_table.insert.return_value = mock_insert

            return mock_table

        mock_client.table.side_effect = table_side_effect

        response = client.post(
            "/api/groceries",
            json={"items": [{"name": "Salt", "quantity": 0.01, "unit": "kg"}]},
            headers=_auth_headers(),
        )
        assert response.status_code == 201

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_accepts_boundary_valid_quantity_max(self, mock_settings, mock_supabase):
        """Accepts quantity at maximum boundary (9999.99)."""
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        mock_client = MagicMock()
        mock_supabase.return_value = mock_client

        existing_response = MagicMock()
        existing_response.data = []

        insert_list_response = MagicMock()
        insert_list_response.data = [{"id": "list-1"}]

        insert_items_response = MagicMock()
        insert_items_response.data = [
            {
                "id": "item-1",
                "name": "Water",
                "quantity": 9999.99,
                "unit": "liters",
                "remaining_quantity": 9999.99,
            }
        ]

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            mock_table = MagicMock()

            if call_count[0] == 1:
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_eq2.execute.return_value = existing_response
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select
            elif call_count[0] == 2:
                mock_insert = MagicMock()
                mock_insert.execute.return_value = insert_list_response
                mock_table.insert.return_value = mock_insert
            elif call_count[0] == 3:
                mock_insert = MagicMock()
                mock_insert.execute.return_value = insert_items_response
                mock_table.insert.return_value = mock_insert

            return mock_table

        mock_client.table.side_effect = table_side_effect

        response = client.post(
            "/api/groceries",
            json={"items": [{"name": "Water", "quantity": 9999.99, "unit": "liters"}]},
            headers=_auth_headers(),
        )
        assert response.status_code == 201


class TestGetCurrentGroceryList:
    """Tests for GET /api/groceries/current."""

    def test_requires_authentication(self):
        response = client.get("/api/groceries/current")
        assert response.status_code == 403

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_returns_404_when_no_list_exists(self, mock_settings, mock_supabase):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        mock_client = MagicMock()
        mock_supabase.return_value = mock_client

        empty_response = MagicMock()
        empty_response.data = []

        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()
        mock_eq2.execute.return_value = empty_response
        mock_eq1.eq.return_value = mock_eq2
        mock_select.eq.return_value = mock_eq1
        mock_table.select.return_value = mock_select
        mock_client.table.return_value = mock_table

        response = client.get(
            "/api/groceries/current",
            headers=_auth_headers(),
        )
        assert response.status_code == 404
        assert "No grocery list found" in response.json()["detail"]

    @patch("app.routes.groceries.get_supabase_client")
    @patch("app.middleware.auth.get_settings")
    def test_returns_current_week_list_with_remaining_quantities(
        self, mock_settings, mock_supabase
    ):
        mock_settings.return_value = MagicMock(supabase_jwt_secret="test-secret")

        mock_client = MagicMock()
        mock_supabase.return_value = mock_client

        week_start = get_week_start_date()

        # Mock: grocery list found
        list_response = MagicMock()
        list_response.data = [
            {"id": "list-123", "week_start_date": week_start.isoformat()}
        ]

        # Mock: grocery items
        items_response = MagicMock()
        items_response.data = [
            {
                "id": "item-1",
                "name": "Chicken",
                "quantity": 3.0,
                "unit": "kg",
                "remaining_quantity": 1.5,
            },
            {
                "id": "item-2",
                "name": "Rice",
                "quantity": 2.0,
                "unit": "kg",
                "remaining_quantity": 2.0,
            },
        ]

        # Mock: dietary preferences
        prefs_response = MagicMock()
        prefs_response.data = [
            {"preference": "gluten-free"},
        ]

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            mock_table = MagicMock()

            if call_count[0] == 1:
                # grocery_lists select
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_eq2.execute.return_value = list_response
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select
            elif call_count[0] == 2:
                # grocery_items select
                mock_select = MagicMock()
                mock_eq = MagicMock()
                mock_eq.execute.return_value = items_response
                mock_select.eq.return_value = mock_eq
                mock_table.select.return_value = mock_select
            elif call_count[0] == 3:
                # dietary_preferences select
                mock_select = MagicMock()
                mock_eq = MagicMock()
                mock_eq.execute.return_value = prefs_response
                mock_select.eq.return_value = mock_eq
                mock_table.select.return_value = mock_select

            return mock_table

        mock_client.table.side_effect = table_side_effect

        response = client.get(
            "/api/groceries/current",
            headers=_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "list-123"
        assert len(data["items"]) == 2
        assert data["items"][0]["name"] == "Chicken"
        assert float(data["items"][0]["remaining_quantity"]) == 1.5
        assert data["items"][1]["name"] == "Rice"
        assert float(data["items"][1]["remaining_quantity"]) == 2.0
        assert data["dietary_preferences"] == ["gluten-free"]
