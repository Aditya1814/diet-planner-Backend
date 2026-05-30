"""Unit tests for the Gemini service."""

import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.gemini_service import GeminiService, MealGenerationError, MEAL_TYPES


class TestBuildPrompt:
    """Tests for prompt construction."""

    def setup_method(self):
        """Create a GeminiService instance with mocked config."""
        with patch("app.services.gemini_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                gemini_credentials_path="/fake/path.json",
                gemini_project_id="test-project",
                gemini_region="us-central1",
                gemini_model="gemini-2.5-pro",
            )
            self.service = GeminiService(credentials_path="/fake/path.json")

    def test_prompt_includes_grocery_items(self):
        grocery_items = [
            {"name": "Chicken breast", "quantity": 2, "unit": "kg"},
            {"name": "Rice", "quantity": 1, "unit": "kg"},
        ]
        prompt = self.service._build_prompt(grocery_items, [], ["Monday"])
        assert "Chicken breast: 2 kg" in prompt
        assert "Rice: 1 kg" in prompt

    def test_prompt_includes_dietary_preferences(self):
        grocery_items = [{"name": "Tofu", "quantity": 1, "unit": "kg"}]
        prompt = self.service._build_prompt(
            grocery_items, ["vegetarian", "gluten-free"], ["Monday"]
        )
        assert "vegetarian, gluten-free" in prompt

    def test_prompt_no_preferences_shows_none(self):
        grocery_items = [{"name": "Tofu", "quantity": 1, "unit": "kg"}]
        prompt = self.service._build_prompt(grocery_items, [], ["Monday"])
        assert "None" in prompt

    def test_prompt_includes_days(self):
        grocery_items = [{"name": "Eggs", "quantity": 12, "unit": "pieces"}]
        days = ["Monday", "Tuesday", "Wednesday"]
        prompt = self.service._build_prompt(grocery_items, [], days)
        assert "Monday, Tuesday, Wednesday" in prompt

    def test_prompt_requests_4_meals_per_day(self):
        grocery_items = [{"name": "Pasta", "quantity": 2, "unit": "kg"}]
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        prompt = self.service._build_prompt(grocery_items, [], days)
        assert "28 meals total" in prompt
        assert "4 meals per day" in prompt
        assert "breakfast" in prompt
        assert "lunch" in prompt
        assert "dinner" in prompt
        assert "snacks" in prompt

    def test_prompt_requests_json_format(self):
        grocery_items = [{"name": "Bread", "quantity": 1, "unit": "loaf"}]
        prompt = self.service._build_prompt(grocery_items, [], ["Monday"])
        assert "JSON" in prompt
        assert "meal_name" in prompt
        assert "meal_type" in prompt
        assert "ingredients" in prompt
        assert "instructions" in prompt

    def test_prompt_single_day_requests_4_meals(self):
        grocery_items = [{"name": "Eggs", "quantity": 12, "unit": "pieces"}]
        prompt = self.service._build_prompt(grocery_items, [], ["Monday"])
        assert "4 meals total" in prompt


class TestParseResponse:
    """Tests for response parsing and validation."""

    def setup_method(self):
        """Create a GeminiService instance with mocked config."""
        with patch("app.services.gemini_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                gemini_credentials_path="/fake/path.json",
                gemini_project_id="test-project",
                gemini_region="us-central1",
                gemini_model="gemini-2.5-pro",
            )
            self.service = GeminiService(credentials_path="/fake/path.json")

    def _make_valid_meal(self, meal_type="breakfast"):
        return {
            "meal_type": meal_type,
            "meal_name": f"Test {meal_type.title()}",
            "ingredients": [
                {"ingredient_name": "Chicken", "quantity": 0.5, "unit": "kg"}
            ],
            "instructions": ["Cook the chicken."],
        }

    def _make_valid_day(self, day="Monday"):
        return {
            "day_of_week": day,
            "meals": [self._make_valid_meal(mt) for mt in MEAL_TYPES],
        }

    def test_parse_valid_single_day(self):
        response = json.dumps({"days": [self._make_valid_day()]})
        result = self.service._parse_response(response, 1)
        assert len(result) == 4  # 4 meals per day
        assert result[0]["meal_type"] == "breakfast"
        assert result[1]["meal_type"] == "lunch"
        assert result[2]["meal_type"] == "dinner"
        assert result[3]["meal_type"] == "snacks"
        assert result[0]["day_of_week"] == "Monday"

    def test_parse_valid_seven_days(self):
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_data = [self._make_valid_day(day) for day in days]
        response = json.dumps({"days": day_data})
        result = self.service._parse_response(response, 7)
        assert len(result) == 28  # 7 days × 4 meals

    def test_parse_strips_markdown_code_fences(self):
        day_json = json.dumps({"days": [self._make_valid_day()]})
        response = f"```json\n{day_json}\n```"
        result = self.service._parse_response(response, 1)
        assert len(result) == 4

    def test_parse_invalid_json_raises(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            self.service._parse_response("not json at all", 1)

    def test_parse_missing_days_key_raises(self):
        with pytest.raises(ValueError, match="'days' key"):
            self.service._parse_response(json.dumps({"meals": []}), 1)

    def test_parse_wrong_day_count_raises(self):
        days_data = [self._make_valid_day("Monday"), self._make_valid_day("Tuesday")]
        response = json.dumps({"days": days_data})
        with pytest.raises(ValueError, match="Expected exactly 1 days, got 2"):
            self.service._parse_response(response, 1)

    def test_parse_wrong_meal_count_per_day_raises(self):
        day_data = {
            "day_of_week": "Monday",
            "meals": [self._make_valid_meal("breakfast"), self._make_valid_meal("lunch")],
        }
        response = json.dumps({"days": [day_data]})
        with pytest.raises(ValueError, match="must have exactly 4 meals, got 2"):
            self.service._parse_response(response, 1)

    def test_parse_invalid_meal_type_raises(self):
        day_data = self._make_valid_day()
        day_data["meals"][0]["meal_type"] = "brunch"
        response = json.dumps({"days": [day_data]})
        with pytest.raises(ValueError, match="invalid meal_type"):
            self.service._parse_response(response, 1)

    def test_parse_meal_name_too_long_raises(self):
        day_data = self._make_valid_day()
        day_data["meals"][0]["meal_name"] = "A" * 101
        response = json.dumps({"days": [day_data]})
        with pytest.raises(ValueError, match="exceeds 100 characters"):
            self.service._parse_response(response, 1)

    def test_parse_empty_meal_name_raises(self):
        day_data = self._make_valid_day()
        day_data["meals"][0]["meal_name"] = ""
        response = json.dumps({"days": [day_data]})
        with pytest.raises(ValueError, match="non-empty 'meal_name'"):
            self.service._parse_response(response, 1)

    def test_parse_no_ingredients_raises(self):
        day_data = self._make_valid_day()
        day_data["meals"][0]["ingredients"] = []
        response = json.dumps({"days": [day_data]})
        with pytest.raises(ValueError, match="at least 1 ingredient"):
            self.service._parse_response(response, 1)

    def test_parse_no_instructions_raises(self):
        day_data = self._make_valid_day()
        day_data["meals"][0]["instructions"] = []
        response = json.dumps({"days": [day_data]})
        with pytest.raises(ValueError, match="at least 1 instruction"):
            self.service._parse_response(response, 1)

    def test_parse_ingredient_missing_quantity_raises(self):
        day_data = self._make_valid_day()
        day_data["meals"][0]["ingredients"] = [{"ingredient_name": "Chicken", "unit": "kg"}]
        response = json.dumps({"days": [day_data]})
        with pytest.raises(ValueError, match="numeric 'quantity'"):
            self.service._parse_response(response, 1)

    def test_parse_ingredient_missing_name_raises(self):
        day_data = self._make_valid_day()
        day_data["meals"][0]["ingredients"] = [{"quantity": 1, "unit": "kg"}]
        response = json.dumps({"days": [day_data]})
        with pytest.raises(ValueError, match="non-empty 'ingredient_name'"):
            self.service._parse_response(response, 1)

    def test_parse_ingredient_missing_unit_raises(self):
        day_data = self._make_valid_day()
        day_data["meals"][0]["ingredients"] = [{"ingredient_name": "Chicken", "quantity": 1}]
        response = json.dumps({"days": [day_data]})
        with pytest.raises(ValueError, match="non-empty 'unit'"):
            self.service._parse_response(response, 1)

    def test_parse_instruction_empty_string_raises(self):
        day_data = self._make_valid_day()
        day_data["meals"][0]["instructions"] = [""]
        response = json.dumps({"days": [day_data]})
        with pytest.raises(ValueError, match="non-empty string"):
            self.service._parse_response(response, 1)

    def test_parse_multiple_ingredients_and_instructions(self):
        day_data = self._make_valid_day()
        day_data["meals"][0]["ingredients"] = [
            {"ingredient_name": "Chicken", "quantity": 0.5, "unit": "kg"},
            {"ingredient_name": "Rice", "quantity": 0.3, "unit": "kg"},
            {"ingredient_name": "Onion", "quantity": 2, "unit": "pieces"},
        ]
        day_data["meals"][0]["instructions"] = [
            "Dice the onion.",
            "Cook the rice.",
            "Grill the chicken.",
            "Combine and serve.",
        ]
        response = json.dumps({"days": [day_data]})
        result = self.service._parse_response(response, 1)
        assert len(result[0]["ingredients"]) == 3
        assert len(result[0]["instructions"]) == 4

    def test_parse_returns_meal_type_in_result(self):
        response = json.dumps({"days": [self._make_valid_day()]})
        result = self.service._parse_response(response, 1)
        meal_types_in_result = [m["meal_type"] for m in result]
        assert meal_types_in_result == MEAL_TYPES

    def test_parse_missing_day_of_week_raises(self):
        day_data = self._make_valid_day()
        day_data["day_of_week"] = ""
        response = json.dumps({"days": [day_data]})
        with pytest.raises(ValueError, match="non-empty 'day_of_week'"):
            self.service._parse_response(response, 1)


class TestGenerateMealPlan:
    """Tests for the generate_meal_plan method with retry logic."""

    def setup_method(self):
        """Create a GeminiService instance with mocked config."""
        with patch("app.services.gemini_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                gemini_credentials_path="/fake/path.json",
                gemini_project_id="test-project",
                gemini_region="us-central1",
                gemini_model="gemini-2.5-pro",
            )
            self.service = GeminiService(credentials_path="/fake/path.json")

    def _make_valid_response(self, days=None):
        """Build a valid multi-meal-per-day response."""
        if days is None:
            days = ["Monday"]
        day_data = []
        for day in days:
            day_data.append({
                "day_of_week": day,
                "meals": [
                    {
                        "meal_type": mt,
                        "meal_name": f"{mt.title()} for {day}",
                        "ingredients": [{"ingredient_name": "Chicken", "quantity": 0.5, "unit": "kg"}],
                        "instructions": [f"Prepare {mt}."],
                    }
                    for mt in MEAL_TYPES
                ],
            })
        return json.dumps({"days": day_data})

    @pytest.mark.asyncio
    async def test_generate_success_first_attempt(self):
        valid_response = self._make_valid_response(["Monday"])

        with patch.object(self.service, "_call_gemini", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = valid_response
            result = await self.service.generate_meal_plan(
                [{"name": "Chicken", "quantity": 1, "unit": "kg"}],
                [],
                ["Monday"],
            )
            assert len(result) == 4  # 4 meals for 1 day
            assert result[0]["meal_type"] == "breakfast"
            assert result[0]["day_of_week"] == "Monday"
            assert mock_call.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_retries_on_failure(self):
        valid_response = self._make_valid_response(["Monday"])

        with patch.object(self.service, "_call_gemini", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = [
                MealGenerationError("API error"),
                valid_response,
            ]
            with patch("app.services.gemini_service.asyncio.sleep", new_callable=AsyncMock):
                result = await self.service.generate_meal_plan(
                    [{"name": "Chicken", "quantity": 1, "unit": "kg"}],
                    [],
                    ["Monday"],
                )
                assert len(result) == 4
                assert mock_call.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_fails_after_max_retries(self):
        with patch.object(self.service, "_call_gemini", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = MealGenerationError("API error")
            with patch("app.services.gemini_service.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(MealGenerationError, match="Failed after 3 attempts"):
                    await self.service.generate_meal_plan(
                        [{"name": "Chicken", "quantity": 1, "unit": "kg"}],
                        [],
                        ["Monday"],
                    )
                assert mock_call.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_retries_on_parse_error(self):
        valid_response = self._make_valid_response(["Monday"])

        with patch.object(self.service, "_call_gemini", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = [
                "invalid json response",
                valid_response,
            ]
            with patch("app.services.gemini_service.asyncio.sleep", new_callable=AsyncMock):
                result = await self.service.generate_meal_plan(
                    [{"name": "Chicken", "quantity": 1, "unit": "kg"}],
                    [],
                    ["Monday"],
                )
                assert len(result) == 4
                assert mock_call.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_retries_on_timeout(self):
        valid_response = self._make_valid_response(["Monday"])

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            return valid_response

        with patch.object(self.service, "_call_gemini", side_effect=side_effect):
            with patch("app.services.gemini_service.asyncio.sleep", new_callable=AsyncMock):
                with patch("asyncio.wait_for", side_effect=side_effect):
                    result = await self.service.generate_meal_plan(
                        [{"name": "Chicken", "quantity": 1, "unit": "kg"}],
                        [],
                        ["Monday"],
                    )
                    assert len(result) == 4

    @pytest.mark.asyncio
    async def test_generate_full_week_returns_28_meals(self):
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        valid_response = self._make_valid_response(days)

        with patch.object(self.service, "_call_gemini", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = valid_response
            result = await self.service.generate_meal_plan(
                [{"name": "Chicken", "quantity": 5, "unit": "kg"}],
                [],
                days,
            )
            assert len(result) == 28  # 7 days × 4 meals


class TestCallGemini:
    """Tests for the _call_gemini method."""

    def setup_method(self):
        """Create a GeminiService instance with mocked config."""
        with patch("app.services.gemini_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                gemini_credentials_path="/fake/path.json",
                gemini_project_id="test-project",
                gemini_region="us-central1",
                gemini_model="gemini-2.5-pro",
            )
            self.service = GeminiService(credentials_path="/fake/path.json")

    def test_endpoint_url_format(self):
        url = self.service._get_endpoint_url()
        assert "us-central1-aiplatform.googleapis.com" in url
        assert "test-project" in url
        assert "gemini-2.5-pro" in url
        assert "generateContent" in url

    @pytest.mark.asyncio
    async def test_call_gemini_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {"content": {"parts": [{"text": "response text"}]}}
            ]
        }

        with patch.object(self.service, "_get_credentials") as mock_creds:
            mock_creds.return_value = MagicMock(token="fake-token")
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                result = await self.service._call_gemini("test prompt")
                assert result == "response text"

    @pytest.mark.asyncio
    async def test_call_gemini_api_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch.object(self.service, "_get_credentials") as mock_creds:
            mock_creds.return_value = MagicMock(token="fake-token")
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                with pytest.raises(MealGenerationError, match="status 500"):
                    await self.service._call_gemini("test prompt")

    @pytest.mark.asyncio
    async def test_call_gemini_unexpected_response_structure(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpected": "format"}

        with patch.object(self.service, "_get_credentials") as mock_creds:
            mock_creds.return_value = MagicMock(token="fake-token")
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                with pytest.raises(MealGenerationError, match="Unexpected Gemini response"):
                    await self.service._call_gemini("test prompt")
