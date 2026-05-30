"""Meal plan routes — generates ONE day at a time (4 meals: breakfast, lunch, dinner, snacks)."""

from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.database import get_supabase_client
from app.middleware.auth import get_current_user_id
from app.routes.groceries import get_week_start_date
from app.schemas.grocery import GroceryItemCreate
from app.schemas.meal import DailyMealResponse, MealIngredient, MealPlanResponse
from app.services.gemini_service import GeminiService, MEAL_TYPES, MealGenerationError
from app.services.image_service import ImageService
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/api/meal-plan", tags=["meal-plan"])

DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _get_current_day_name(today: Optional[date] = None) -> str:
    if today is None:
        today = date.today()
    return DAYS_OF_WEEK[today.weekday()]


async def _generate_single_day(user_id: str, target_date: Optional[date] = None):
    """
    Core logic: generate 4 meals for a SINGLE day using remaining grocery inventory.
    If meals already exist for that day, delete them first (regenerate).
    """
    settings = get_settings()
    supabase = get_supabase_client()

    if target_date is None:
        target_date = date.today()

    week_start = get_week_start_date(target_date)
    day_name = DAYS_OF_WEEK[target_date.weekday()]

    # 1. Fetch grocery list for this week
    grocery_list_result = (
        supabase.table("grocery_lists")
        .select("id")
        .eq("user_id", user_id)
        .eq("week_start_date", week_start.isoformat())
        .execute()
    )

    if not grocery_list_result.data:
        raise HTTPException(
            status_code=404,
            detail="No grocery list found for the current week. Please submit groceries first.",
        )

    grocery_list_id = grocery_list_result.data[0]["id"]

    # Fetch grocery items (use remaining_quantity as available inventory)
    items_result = (
        supabase.table("grocery_items")
        .select("id, name, quantity, unit, remaining_quantity")
        .eq("grocery_list_id", grocery_list_id)
        .execute()
    )

    if not items_result.data:
        raise HTTPException(status_code=400, detail="Grocery list has no items.")

    # Fetch dietary preferences
    prefs_result = (
        supabase.table("dietary_preferences")
        .select("preference")
        .eq("grocery_list_id", grocery_list_id)
        .execute()
    )
    dietary_preferences = [p["preference"] for p in prefs_result.data]

    # Use remaining_quantity as available inventory for generation
    grocery_items_for_gemini = [
        {"name": item["name"], "quantity": float(item["remaining_quantity"]), "unit": item["unit"]}
        for item in items_result.data
        if float(item["remaining_quantity"]) > 0
    ]

    if not grocery_items_for_gemini:
        raise HTTPException(status_code=400, detail="No remaining groceries available to generate meals.")

    # 2. Call Gemini for just 1 day (4 meals)
    gemini_service = GeminiService()
    try:
        generated_meals = await gemini_service.generate_meal_plan(
            grocery_items=grocery_items_for_gemini,
            dietary_preferences=dietary_preferences,
            days=[day_name],
        )
    except MealGenerationError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Meal generation failed: {str(e)}",
        )

    # 3. Fetch images for each meal
    image_service = ImageService(
        api_key=settings.google_search_api_key,
        search_engine_id=settings.google_search_engine_id,
    )
    for meal in generated_meals:
        meal["image_url"] = await image_service.get_meal_image(meal["meal_name"])

    # 4. Ensure meal_plan record exists for this week
    existing_plan = (
        supabase.table("meal_plans")
        .select("id")
        .eq("user_id", user_id)
        .eq("week_start_date", week_start.isoformat())
        .execute()
    )

    if existing_plan.data:
        meal_plan_id = existing_plan.data[0]["id"]
    else:
        plan_result = (
            supabase.table("meal_plans")
            .insert({"user_id": user_id, "week_start_date": week_start.isoformat()})
            .execute()
        )
        meal_plan_id = plan_result.data[0]["id"]

    # 5. Delete existing meals for this day (if regenerating) and refund ingredients
    existing_day_meals = (
        supabase.table("daily_meals")
        .select("id")
        .eq("meal_plan_id", meal_plan_id)
        .eq("meal_date", target_date.isoformat())
        .execute()
    )
    
    # Refund old meal ingredients back to inventory before deleting
    for old_meal in existing_day_meals.data:
        old_ingredients = (
            supabase.table("meal_ingredients")
            .select("ingredient_name, quantity, unit")
            .eq("daily_meal_id", old_meal["id"])
            .execute()
        )
        # Add back each ingredient to the matching grocery item
        for ing in old_ingredients.data:
            ing_name = ing["ingredient_name"].lower()
            for item in items_result.data:
                if ing_name in item["name"].lower() or item["name"].lower() in ing_name:
                    new_remaining = float(item["remaining_quantity"]) + float(ing["quantity"])
                    supabase.table("grocery_items").update(
                        {"remaining_quantity": new_remaining}
                    ).eq("id", item["id"]).execute()
                    item["remaining_quantity"] = new_remaining  # update local copy too
                    break
        
        # Now delete the old meal data
        supabase.table("meal_ingredients").delete().eq("daily_meal_id", old_meal["id"]).execute()
        supabase.table("daily_meals").delete().eq("id", old_meal["id"]).execute()

    # 6. Insert new meals for today
    daily_meals_response = []
    for meal in generated_meals:
        instructions_text = "\n".join(meal["instructions"])

        daily_meal_result = (
            supabase.table("daily_meals")
            .insert({
                "meal_plan_id": meal_plan_id,
                "day_of_week": day_name,
                "meal_type": meal["meal_type"],
                "meal_date": target_date.isoformat(),
                "meal_name": meal["meal_name"],
                "instructions": instructions_text,
                "image_url": meal.get("image_url"),
                "is_preserved": False,
            })
            .execute()
        )
        daily_meal_id = daily_meal_result.data[0]["id"]

        # Insert ingredients
        ingredients_to_insert = [
            {
                "daily_meal_id": daily_meal_id,
                "ingredient_name": ing["ingredient_name"],
                "quantity": float(ing["quantity"]),
                "unit": ing["unit"],
            }
            for ing in meal["ingredients"]
        ]
        if ingredients_to_insert:
            supabase.table("meal_ingredients").insert(ingredients_to_insert).execute()

        # Build response
        ingredients = [
            MealIngredient(
                ingredient_name=ing["ingredient_name"],
                quantity=Decimal(str(ing["quantity"])),
                unit=ing["unit"],
            )
            for ing in meal["ingredients"]
        ]
        daily_meals_response.append(
            DailyMealResponse(
                day_of_week=day_name,
                meal_type=meal["meal_type"],
                meal_date=target_date,
                meal_name=meal["meal_name"],
                ingredients=ingredients,
                instructions=meal["instructions"],
                image_url=meal.get("image_url"),
            )
        )

    # 7. Deduct today's meals from grocery inventory
    # We need to map deductions back to ALL items (including zero-remaining ones)
    # First, restore any previous deductions if regenerating (refund old meals)
    # Then deduct new meals
    
    # Build inventory items only from items that have remaining > 0
    # But we need to track which DB items they correspond to
    items_with_remaining = []
    item_index_map = []  # maps inventory index -> items_result.data index
    
    for i, item in enumerate(items_result.data):
        remaining = float(item["remaining_quantity"])
        if remaining >= 0.01:
            items_with_remaining.append(
                GroceryItemCreate(
                    name=item["name"],
                    quantity=Decimal(str(remaining)),
                    unit=item["unit"],
                )
            )
            item_index_map.append(i)

    if items_with_remaining:
        today_plan = MealPlanResponse(week_start_date=week_start, meals=daily_meals_response)
        inventory_service = InventoryService()
        inventory = inventory_service.calculate_inventory(
            grocery_items=items_with_remaining,
            meal_plan=today_plan,
        )

        # Update remaining quantities in DB for items that had remaining > 0
        for inv_idx, inv_item in enumerate(inventory):
            db_idx = item_index_map[inv_idx]
            item_data = items_result.data[db_idx]
            new_remaining = float(inv_item.remaining_quantity)
            supabase.table("grocery_items").update(
                {"remaining_quantity": new_remaining}
            ).eq("id", item_data["id"]).execute()

    return daily_meals_response


@router.post("/generate", status_code=201, response_model=List[DailyMealResponse])
async def generate_today_plan(user_id: str = Depends(get_current_user_id)):
    """
    Generate meals for TODAY only (4 meals: breakfast, lunch, dinner, snacks).
    If today already has meals, regenerates them.
    Uses remaining grocery inventory.
    """
    return await _generate_single_day(user_id)


@router.get("/today", response_model=List[DailyMealResponse])
async def get_today_meals(user_id: str = Depends(get_current_user_id)):
    """
    Get today's meals. If none exist yet, auto-generates them.
    """
    supabase = get_supabase_client()
    today = date.today()
    week_start = get_week_start_date(today)

    # Check if meal plan exists
    plan_result = (
        supabase.table("meal_plans")
        .select("id")
        .eq("user_id", user_id)
        .eq("week_start_date", week_start.isoformat())
        .execute()
    )

    if plan_result.data:
        meal_plan_id = plan_result.data[0]["id"]

        # Check if today has meals
        today_meals_result = (
            supabase.table("daily_meals")
            .select("id, day_of_week, meal_type, meal_date, meal_name, instructions, image_url")
            .eq("meal_plan_id", meal_plan_id)
            .eq("meal_date", today.isoformat())
            .execute()
        )

        if today_meals_result.data:
            # Return existing meals
            meals = []
            for meal_row in today_meals_result.data:
                ingredients_result = (
                    supabase.table("meal_ingredients")
                    .select("ingredient_name, quantity, unit")
                    .eq("daily_meal_id", meal_row["id"])
                    .execute()
                )
                ingredients = [
                    MealIngredient(
                        ingredient_name=ing["ingredient_name"],
                        quantity=Decimal(str(ing["quantity"])),
                        unit=ing["unit"],
                    )
                    for ing in ingredients_result.data
                ]
                instructions_text = meal_row["instructions"] or ""
                instructions = [s for s in instructions_text.split("\n") if s.strip()]

                meals.append(DailyMealResponse(
                    day_of_week=meal_row["day_of_week"],
                    meal_type=meal_row.get("meal_type", "main"),
                    meal_date=meal_row["meal_date"],
                    meal_name=meal_row["meal_name"],
                    ingredients=ingredients,
                    instructions=instructions,
                    image_url=meal_row["image_url"],
                ))

            # Sort by meal type order
            meal_type_order = {mt: i for i, mt in enumerate(MEAL_TYPES)}
            meals.sort(key=lambda m: meal_type_order.get(m.meal_type, 99))
            return meals

    # No meals for today — check if groceries exist, then auto-generate
    grocery_check = (
        supabase.table("grocery_lists")
        .select("id")
        .eq("user_id", user_id)
        .eq("week_start_date", week_start.isoformat())
        .execute()
    )

    if not grocery_check.data:
        raise HTTPException(status_code=404, detail="No meal plan found for the current week.")

    # Auto-generate today's meals
    return await _generate_single_day(user_id)


@router.get("/current", response_model=MealPlanResponse)
async def get_current_meal_plan(user_id: str = Depends(get_current_user_id)):
    """
    Get all generated meals for the current week (whatever days have been generated so far).
    """
    supabase = get_supabase_client()
    week_start = get_week_start_date()

    plan_result = (
        supabase.table("meal_plans")
        .select("id, week_start_date")
        .eq("user_id", user_id)
        .eq("week_start_date", week_start.isoformat())
        .execute()
    )

    if not plan_result.data:
        raise HTTPException(status_code=404, detail="No meal plan found for the current week.")

    meal_plan_id = plan_result.data[0]["id"]

    meals_result = (
        supabase.table("daily_meals")
        .select("id, day_of_week, meal_type, meal_date, meal_name, instructions, image_url")
        .eq("meal_plan_id", meal_plan_id)
        .order("meal_date")
        .execute()
    )

    daily_meals = []
    for meal_row in meals_result.data:
        ingredients_result = (
            supabase.table("meal_ingredients")
            .select("ingredient_name, quantity, unit")
            .eq("daily_meal_id", meal_row["id"])
            .execute()
        )
        ingredients = [
            MealIngredient(
                ingredient_name=ing["ingredient_name"],
                quantity=Decimal(str(ing["quantity"])),
                unit=ing["unit"],
            )
            for ing in ingredients_result.data
        ]
        instructions_text = meal_row["instructions"] or ""
        instructions = [s for s in instructions_text.split("\n") if s.strip()]

        daily_meals.append(DailyMealResponse(
            day_of_week=meal_row["day_of_week"],
            meal_type=meal_row.get("meal_type", "main"),
            meal_date=meal_row["meal_date"],
            meal_name=meal_row["meal_name"],
            ingredients=ingredients,
            instructions=instructions,
            image_url=meal_row["image_url"],
        ))

    return MealPlanResponse(week_start_date=week_start, meals=daily_meals)
