from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class MealIngredient(BaseModel):
    """Schema for a single meal ingredient."""

    ingredient_name: str
    quantity: Decimal
    unit: str


class DailyMealResponse(BaseModel):
    """Schema for a single meal response (one of 4 meals per day)."""

    day_of_week: str
    meal_type: str  # "breakfast", "lunch", "dinner", "snacks"
    meal_date: date
    meal_name: str
    ingredients: List[MealIngredient]
    instructions: List[str]
    image_url: Optional[str] = None


class MealPlanResponse(BaseModel):
    """Schema for a full week's meal plan response.

    Contains all meals across all days (4 meals per day × number of days).
    """

    week_start_date: date
    meals: List[DailyMealResponse]
