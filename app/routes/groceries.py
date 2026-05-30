"""Grocery list routes for submitting and retrieving weekly grocery lists."""

from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import get_supabase_client
from app.middleware.auth import get_current_user_id
from app.schemas.grocery import GroceryListCreate

router = APIRouter(prefix="/api/groceries", tags=["groceries"])


class GroceryItemResponse(BaseModel):
    """Response schema for a single grocery item."""

    id: str
    name: str
    quantity: Decimal
    unit: str
    remaining_quantity: Decimal


class GroceryListResponse(BaseModel):
    """Response schema for a grocery list with items."""

    id: str
    week_start_date: date
    items: List[GroceryItemResponse]
    dietary_preferences: List[str]


def get_week_start_date(today: Optional[date] = None) -> date:
    """
    Calculate the Monday of the current week.

    Week boundaries are Monday–Sunday. Given any date, returns the
    Monday of that week.
    """
    if today is None:
        today = date.today()
    # weekday() returns 0 for Monday, 6 for Sunday
    days_since_monday = today.weekday()
    return today - timedelta(days=days_since_monday)


@router.post("", status_code=201, response_model=GroceryListResponse)
async def submit_grocery_list(
    grocery_list: GroceryListCreate,
    user_id: str = Depends(get_current_user_id),
):
    """
    Submit or update the grocery list for the current week.

    On new submission, replaces previous inventory by setting
    remaining_quantity = submitted quantity for all items.
    Also persists dietary preferences associated with the grocery list.
    """
    supabase = get_supabase_client()
    week_start = get_week_start_date()

    # Check if a grocery list already exists for this user and week
    existing = (
        supabase.table("grocery_lists")
        .select("id")
        .eq("user_id", user_id)
        .eq("week_start_date", week_start.isoformat())
        .execute()
    )

    if existing.data:
        # Update existing list: delete old items and preferences, then insert new ones
        grocery_list_id = existing.data[0]["id"]

        # Delete existing grocery items
        supabase.table("grocery_items").delete().eq(
            "grocery_list_id", grocery_list_id
        ).execute()

        # Delete existing dietary preferences
        supabase.table("dietary_preferences").delete().eq(
            "grocery_list_id", grocery_list_id
        ).execute()

        # Update the updated_at timestamp
        supabase.table("grocery_lists").update(
            {"updated_at": "now()"}
        ).eq("id", grocery_list_id).execute()
    else:
        # Create new grocery list
        result = (
            supabase.table("grocery_lists")
            .insert(
                {
                    "user_id": user_id,
                    "week_start_date": week_start.isoformat(),
                }
            )
            .execute()
        )
        grocery_list_id = result.data[0]["id"]

    # Insert grocery items with remaining_quantity = quantity
    items_to_insert = [
        {
            "grocery_list_id": grocery_list_id,
            "name": item.name,
            "quantity": float(item.quantity),
            "unit": item.unit,
            "remaining_quantity": float(item.quantity),
        }
        for item in grocery_list.items
    ]

    inserted_items = (
        supabase.table("grocery_items").insert(items_to_insert).execute()
    )

    # Insert dietary preferences
    if grocery_list.dietary_preferences:
        prefs_to_insert = [
            {
                "grocery_list_id": grocery_list_id,
                "preference": pref,
            }
            for pref in grocery_list.dietary_preferences
        ]
        supabase.table("dietary_preferences").insert(prefs_to_insert).execute()

    # Build response
    response_items = [
        GroceryItemResponse(
            id=item["id"],
            name=item["name"],
            quantity=Decimal(str(item["quantity"])),
            unit=item["unit"],
            remaining_quantity=Decimal(str(item["remaining_quantity"])),
        )
        for item in inserted_items.data
    ]

    return GroceryListResponse(
        id=grocery_list_id,
        week_start_date=week_start,
        items=response_items,
        dietary_preferences=grocery_list.dietary_preferences,
    )


@router.get("/current", response_model=GroceryListResponse)
async def get_current_grocery_list(
    user_id: str = Depends(get_current_user_id),
):
    """
    Get the current week's grocery list with remaining quantities.

    Returns the grocery list for the current week (Monday–Sunday),
    including all items with their remaining quantities after any
    meal plan deductions.
    """
    supabase = get_supabase_client()
    week_start = get_week_start_date()

    # Fetch the grocery list for the current week
    result = (
        supabase.table("grocery_lists")
        .select("id, week_start_date")
        .eq("user_id", user_id)
        .eq("week_start_date", week_start.isoformat())
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="No grocery list found for the current week.",
        )

    grocery_list_id = result.data[0]["id"]
    week_start_date = result.data[0]["week_start_date"]

    # Fetch grocery items
    items_result = (
        supabase.table("grocery_items")
        .select("id, name, quantity, unit, remaining_quantity")
        .eq("grocery_list_id", grocery_list_id)
        .execute()
    )

    # Fetch dietary preferences
    prefs_result = (
        supabase.table("dietary_preferences")
        .select("preference")
        .eq("grocery_list_id", grocery_list_id)
        .execute()
    )

    response_items = [
        GroceryItemResponse(
            id=item["id"],
            name=item["name"],
            quantity=Decimal(str(item["quantity"])),
            unit=item["unit"],
            remaining_quantity=Decimal(str(item["remaining_quantity"])),
        )
        for item in items_result.data
    ]

    preferences = [pref["preference"] for pref in prefs_result.data]

    return GroceryListResponse(
        id=grocery_list_id,
        week_start_date=week_start_date,
        items=response_items,
        dietary_preferences=preferences,
    )
