"""Dietary preferences routes for retrieving user preferences."""

from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_supabase_client
from app.middleware.auth import get_current_user_id

router = APIRouter(prefix="/api/preferences", tags=["preferences"])

# Predefined dietary preference options
VALID_PREFERENCES = [
    "vegetarian",
    "vegan",
    "low-carb",
    "gluten-free",
    "dairy-free",
    "nut-free",
]


def get_week_start_date(reference_date: Optional[date] = None) -> date:
    """Calculate the Monday of the current week."""
    today = reference_date or date.today()
    # Monday is weekday 0
    days_since_monday = today.weekday()
    return today - timedelta(days=days_since_monday)


@router.get("/current", response_model=dict)
async def get_current_preferences(
    user_id: str = Depends(get_current_user_id),
):
    """
    Get the current week's dietary preferences for the authenticated user.

    If no preferences exist for the current week, returns the previous week's
    preferences (carry-over behavior per Requirement 4.5).

    Returns:
        - preferences: list of dietary preference strings
        - week_start_date: the week the preferences belong to
        - is_carry_over: whether the preferences are carried over from a previous week
    """
    supabase = get_supabase_client()
    current_week_start = get_week_start_date()

    # Try to get current week's grocery list and its preferences
    preferences = _get_preferences_for_week(supabase, user_id, current_week_start)

    if preferences is not None:
        return {
            "preferences": preferences,
            "week_start_date": current_week_start.isoformat(),
            "is_carry_over": False,
        }

    # Fall back to previous week's preferences (carry-over)
    previous_week_start = current_week_start - timedelta(days=7)
    previous_preferences = _get_preferences_for_week(
        supabase, user_id, previous_week_start
    )

    if previous_preferences is not None:
        return {
            "preferences": previous_preferences,
            "week_start_date": previous_week_start.isoformat(),
            "is_carry_over": True,
        }

    # No preferences found for current or previous week
    return {
        "preferences": [],
        "week_start_date": current_week_start.isoformat(),
        "is_carry_over": False,
    }


def _get_preferences_for_week(
    supabase, user_id: str, week_start: date
) -> Optional[List[str]]:
    """
    Retrieve dietary preferences for a specific week.

    Returns a list of preference strings if a grocery list exists for that week,
    or None if no grocery list exists for that week.
    """
    # Find the grocery list for this user and week
    grocery_list_response = (
        supabase.table("grocery_lists")
        .select("id")
        .eq("user_id", user_id)
        .eq("week_start_date", week_start.isoformat())
        .execute()
    )

    if not grocery_list_response.data:
        return None

    grocery_list_id = grocery_list_response.data[0]["id"]

    # Get dietary preferences for this grocery list
    preferences_response = (
        supabase.table("dietary_preferences")
        .select("preference")
        .eq("grocery_list_id", grocery_list_id)
        .execute()
    )

    return [row["preference"] for row in preferences_response.data]
