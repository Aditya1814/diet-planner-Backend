"""Gemini AI service for meal plan generation using Vertex AI."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2 import service_account
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
TIMEOUT_SECONDS = 120

# Supported meal types per day
MEAL_TYPES = ["breakfast", "lunch", "dinner", "snacks"]


class MealGenerationError(Exception):
    """Raised when meal plan generation fails after all retries."""

    pass


class GeminiService:
    """Service for generating meal plans using Google Gemini via Vertex AI."""

    def __init__(self, credentials_path: str | None = None):
        """Initialize with service account JSON path.

        Args:
            credentials_path: Path to the service account credential JSON file.
                If None, uses the path from application config.
        """
        settings = get_settings()
        self._credentials_path = credentials_path or settings.gemini_credentials_path
        self._project_id = settings.gemini_project_id
        self._region = settings.gemini_region
        self._model = settings.gemini_model
        self._credentials = None

    def _get_credentials(self) -> service_account.Credentials:
        """Load and return service account credentials with token refresh.
        Supports loading from file path OR from GEMINI_CREDENTIALS_JSON env variable.
        """
        import os
        import json as json_module
        import tempfile

        if self._credentials is None or not self._credentials.valid:
            # Try loading from env variable first (for cloud deployment)
            creds_json = os.environ.get("GEMINI_CREDENTIALS_JSON")
            if creds_json:
                creds_dict = json_module.loads(creds_json)
                self._credentials = service_account.Credentials.from_service_account_info(
                    creds_dict,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            else:
                # Fall back to file path (for local development)
                self._credentials = service_account.Credentials.from_service_account_file(
                    self._credentials_path,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
        if not self._credentials.valid:
            self._credentials.refresh(Request())
        return self._credentials

    def _get_endpoint_url(self) -> str:
        """Build the Vertex AI Gemini endpoint URL."""
        return (
            f"https://{self._region}-aiplatform.googleapis.com/v1/"
            f"projects/{self._project_id}/locations/{self._region}/"
            f"publishers/google/models/{self._model}:generateContent"
        )

    def _build_prompt(
        self,
        grocery_items: list[dict[str, Any]],
        dietary_preferences: list[str],
        days: list[str],
    ) -> str:
        """Construct the Gemini prompt with structured output instructions.

        Args:
            grocery_items: List of grocery items with name, quantity, and unit.
            dietary_preferences: List of dietary constraints (e.g., "vegetarian").
            days: List of day names to generate meals for (e.g., ["Monday", "Tuesday"]).

        Returns:
            The formatted prompt string.
        """
        num_days = len(days)
        num_meals = num_days * len(MEAL_TYPES)
        days_str = ", ".join(days)
        meal_types_str = ", ".join(MEAL_TYPES)

        grocery_list_str = "\n".join(
            f"- {item['name']}: {item['quantity']} {item['unit']}"
            for item in grocery_items
        )

        preferences_str = (
            ", ".join(dietary_preferences) if dietary_preferences else "None"
        )

        prompt = f"""You are a professional meal planner. Generate a complete meal plan for the following days: {days_str}.

For EACH day, generate exactly 4 meals: {meal_types_str}.
That means {num_meals} meals total ({num_days} days × 4 meals per day).

Use ONLY the following available groceries:
{grocery_list_str}

Dietary preferences to respect: {preferences_str}

Rules:
1. Generate exactly 4 meals per day (breakfast, lunch, dinner, snacks) for each day listed above.
2. Each meal must use only ingredients from the provided grocery list.
3. Respect all dietary preferences — do not include any ingredients or preparation methods that violate them.
4. Each meal must have a descriptive name (maximum 100 characters).
5. Each meal must have at least 1 ingredient with a numeric quantity and unit.
6. Each meal must have DETAILED step-by-step preparation instructions (at least 4-6 steps per meal). Write instructions for a complete beginner who has never cooked before. Include specific temperatures, cooking times, utensils needed, and visual cues (e.g., "cook until golden brown", "stir every 2 minutes").
7. Snacks should be lighter/simpler than main meals.
8. Distribute grocery usage across all meals to avoid running out early in the week.
9. BE CREATIVE AND VARIED — do NOT repeat the same meals. Each time you generate, suggest DIFFERENT recipes, cooking styles, and flavor combinations. Think of diverse cuisines (Indian, Italian, Mexican, Asian, Mediterranean, etc.).

Respond with ONLY valid JSON in the following format (no markdown, no extra text):
{{
  "days": [
    {{
      "day_of_week": "Monday",
      "meals": [
        {{
          "meal_type": "breakfast",
          "meal_name": "Oatmeal with Fruits",
          "ingredients": [
            {{"ingredient_name": "Oats", "quantity": 0.1, "unit": "kg"}},
            {{"ingredient_name": "Banana", "quantity": 1, "unit": "pieces"}}
          ],
          "instructions": [
            "Boil water and cook oats for 5 minutes.",
            "Slice the banana and add on top."
          ]
        }},
        {{
          "meal_type": "lunch",
          "meal_name": "Grilled Chicken Salad",
          "ingredients": [
            {{"ingredient_name": "Chicken breast", "quantity": 0.2, "unit": "kg"}},
            {{"ingredient_name": "Lettuce", "quantity": 1, "unit": "pieces"}}
          ],
          "instructions": [
            "Season and grill the chicken for 6 minutes on each side.",
            "Chop the lettuce and arrange on a plate.",
            "Slice the grilled chicken and place on top."
          ]
        }},
        {{
          "meal_type": "dinner",
          "meal_name": "Pasta with Tomato Sauce",
          "ingredients": [
            {{"ingredient_name": "Pasta", "quantity": 0.15, "unit": "kg"}},
            {{"ingredient_name": "Tomato", "quantity": 2, "unit": "pieces"}}
          ],
          "instructions": [
            "Boil pasta according to package instructions.",
            "Dice tomatoes and cook into a sauce.",
            "Combine pasta with sauce and serve."
          ]
        }},
        {{
          "meal_type": "snacks",
          "meal_name": "Mixed Nuts and Yogurt",
          "ingredients": [
            {{"ingredient_name": "Mixed nuts", "quantity": 0.05, "unit": "kg"}},
            {{"ingredient_name": "Yogurt", "quantity": 0.15, "unit": "kg"}}
          ],
          "instructions": [
            "Portion out mixed nuts into a bowl.",
            "Serve alongside yogurt."
          ]
        }}
      ]
    }}
  ]
}}

Generate meals for these days in order: {days_str}"""

        return prompt

    def _parse_response(self, response_text: str, expected_days: int) -> list[dict[str, Any]]:
        """Parse and validate Gemini's JSON response for multi-meal-per-day format.

        Args:
            response_text: Raw text response from Gemini.
            expected_days: Number of days expected in the response.

        Returns:
            List of validated meal dictionaries with day_of_week, meal_type,
            meal_name, ingredients, and instructions.

        Raises:
            ValueError: If the response structure is invalid.
        """
        # Strip markdown code fences if present
        text = response_text.strip()
        if text.startswith("```"):
            # Remove opening fence (possibly with language tag)
            first_newline = text.index("\n")
            text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Response is not valid JSON: {e}")

        if not isinstance(data, dict) or "days" not in data:
            raise ValueError("Response must be a JSON object with a 'days' key")

        days = data["days"]

        if not isinstance(days, list):
            raise ValueError("'days' must be a list")

        if len(days) != expected_days:
            raise ValueError(
                f"Expected exactly {expected_days} days, got {len(days)}"
            )

        validated_meals = []
        for day_idx, day_data in enumerate(days):
            if not isinstance(day_data, dict):
                raise ValueError(f"Day {day_idx + 1} must be a JSON object")

            day_of_week = day_data.get("day_of_week", "")
            if not day_of_week or not isinstance(day_of_week, str):
                raise ValueError(f"Day {day_idx + 1} must have a non-empty 'day_of_week' string")

            meals = day_data.get("meals")
            if not meals or not isinstance(meals, list):
                raise ValueError(f"Day {day_idx + 1} must have a 'meals' list")

            if len(meals) != len(MEAL_TYPES):
                raise ValueError(
                    f"Day {day_idx + 1} ({day_of_week}) must have exactly "
                    f"{len(MEAL_TYPES)} meals, got {len(meals)}"
                )

            for meal_idx, meal in enumerate(meals):
                if not isinstance(meal, dict):
                    raise ValueError(
                        f"Day {day_idx + 1}, meal {meal_idx + 1} must be a JSON object"
                    )

                # Validate meal_type
                meal_type = meal.get("meal_type")
                if not meal_type or not isinstance(meal_type, str):
                    raise ValueError(
                        f"Day {day_idx + 1}, meal {meal_idx + 1} must have a non-empty 'meal_type'"
                    )
                if meal_type not in MEAL_TYPES:
                    raise ValueError(
                        f"Day {day_idx + 1}, meal {meal_idx + 1} has invalid meal_type "
                        f"'{meal_type}'. Must be one of: {MEAL_TYPES}"
                    )

                # Validate meal_name
                meal_name = meal.get("meal_name")
                if not meal_name or not isinstance(meal_name, str):
                    raise ValueError(
                        f"Day {day_idx + 1}, meal {meal_idx + 1} must have a non-empty 'meal_name' string"
                    )
                if len(meal_name) > 100:
                    raise ValueError(
                        f"Day {day_idx + 1}, meal {meal_idx + 1} meal_name exceeds 100 characters: "
                        f"'{meal_name[:50]}...'"
                    )

                # Validate ingredients
                ingredients = meal.get("ingredients")
                if not ingredients or not isinstance(ingredients, list) or len(ingredients) < 1:
                    raise ValueError(
                        f"Day {day_idx + 1}, meal {meal_idx + 1} must have at least 1 ingredient"
                    )

                validated_ingredients = []
                for j, ing in enumerate(ingredients):
                    if not isinstance(ing, dict):
                        raise ValueError(
                            f"Day {day_idx + 1}, meal {meal_idx + 1}, ingredient {j + 1} "
                            f"must be a JSON object"
                        )
                    ing_name = ing.get("ingredient_name")
                    ing_qty = ing.get("quantity")
                    ing_unit = ing.get("unit")

                    if not ing_name or not isinstance(ing_name, str):
                        raise ValueError(
                            f"Day {day_idx + 1}, meal {meal_idx + 1}, ingredient {j + 1} "
                            f"must have a non-empty 'ingredient_name'"
                        )
                    if ing_qty is None or not isinstance(ing_qty, (int, float)):
                        raise ValueError(
                            f"Day {day_idx + 1}, meal {meal_idx + 1}, ingredient {j + 1} "
                            f"must have a numeric 'quantity'"
                        )
                    if not ing_unit or not isinstance(ing_unit, str):
                        raise ValueError(
                            f"Day {day_idx + 1}, meal {meal_idx + 1}, ingredient {j + 1} "
                            f"must have a non-empty 'unit'"
                        )

                    validated_ingredients.append(
                        {
                            "ingredient_name": ing_name,
                            "quantity": float(ing_qty),
                            "unit": ing_unit,
                        }
                    )

                # Validate instructions
                instructions = meal.get("instructions")
                if not instructions or not isinstance(instructions, list) or len(instructions) < 1:
                    raise ValueError(
                        f"Day {day_idx + 1}, meal {meal_idx + 1} must have at least 1 instruction step"
                    )

                for k, step in enumerate(instructions):
                    if not isinstance(step, str) or not step.strip():
                        raise ValueError(
                            f"Day {day_idx + 1}, meal {meal_idx + 1}, instruction {k + 1} "
                            f"must be a non-empty string"
                        )

                validated_meals.append(
                    {
                        "day_of_week": day_of_week,
                        "meal_type": meal_type,
                        "meal_name": meal_name,
                        "ingredients": validated_ingredients,
                        "instructions": [s.strip() for s in instructions],
                    }
                )

        return validated_meals

    async def _call_gemini(self, prompt: str) -> str:
        """Make a single call to the Vertex AI Gemini endpoint.

        Args:
            prompt: The prompt to send to Gemini.

        Returns:
            The text content from Gemini's response.

        Raises:
            MealGenerationError: If the API returns an error or unexpected format.
        """
        credentials = self._get_credentials()
        url = self._get_endpoint_url()

        headers = {
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
        }

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 1.2,
                "topP": 0.95,
                "maxOutputTokens": 8192,
            },
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
                timeout=TIMEOUT_SECONDS,
            )

        if response.status_code != 200:
            raise MealGenerationError(
                f"Gemini API returned status {response.status_code}: {response.text}"
            )

        response_data = response.json()

        # Extract text from Vertex AI response format
        try:
            candidates = response_data["candidates"]
            text = candidates[0]["content"]["parts"][0]["text"]
            return text
        except (KeyError, IndexError) as e:
            raise MealGenerationError(
                f"Unexpected Gemini response structure: {e}"
            )

    async def generate_meal_plan(
        self,
        grocery_items: list[dict[str, Any]],
        dietary_preferences: list[str],
        days: list[str],
        avoid_meals: list[str] | None = None,
        user_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """Generate meals for specified days using available groceries.

        Args:
            grocery_items: List of grocery items with name, quantity, and unit.
            dietary_preferences: List of dietary constraints.
            days: List of day names to generate meals for.
            avoid_meals: List of meal names to avoid (previously generated).
            user_prompt: Custom user preference (e.g., "high protein", "light meals").
        """
        prompt = self._build_prompt(grocery_items, dietary_preferences, days)
        
        # Append user's custom preference
        if user_prompt and user_prompt.strip():
            prompt += f"\n\nUSER'S SPECIAL REQUEST: {user_prompt.strip()}. Please prioritize this preference when selecting recipes."
        
        # Append avoidance instruction if previous meals exist
        if avoid_meals and len(avoid_meals) > 0:
            avoid_list = ", ".join(f'"{m}"' for m in avoid_meals)
            prompt += f"\n\nIMPORTANT: Do NOT suggest these meals again (they were already generated): {avoid_list}. Generate completely DIFFERENT recipes."
        
        expected_days = len(days)

        last_error: Optional[Exception] = None

        for attempt in range(MAX_RETRIES):
            try:
                response_text = await asyncio.wait_for(
                    self._call_gemini(prompt),
                    timeout=TIMEOUT_SECONDS,
                )
                meals = self._parse_response(response_text, expected_days)
                return meals
            except asyncio.TimeoutError:
                last_error = MealGenerationError(
                    f"Gemini API timed out (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                logger.warning(
                    "Gemini API timeout on attempt %d/%d", attempt + 1, MAX_RETRIES
                )
            except (MealGenerationError, ValueError) as e:
                last_error = e
                logger.warning(
                    "Gemini generation failed on attempt %d/%d: %s",
                    attempt + 1,
                    MAX_RETRIES,
                    str(e),
                )

            if attempt < MAX_RETRIES - 1:
                backoff = 2**attempt
                logger.info("Retrying in %d seconds...", backoff)
                await asyncio.sleep(backoff)

        raise MealGenerationError(
            f"Failed after {MAX_RETRIES} attempts: {last_error}"
        )
