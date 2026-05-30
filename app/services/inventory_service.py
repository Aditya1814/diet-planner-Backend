from decimal import Decimal
from typing import Dict, List, Optional

from app.schemas.grocery import GroceryItemCreate
from app.schemas.inventory import InventoryItemResponse
from app.schemas.meal import DailyMealResponse, MealPlanResponse


class InventoryService:
    """
    Pure calculation service for inventory management.
    Computes remaining grocery quantities after meal plan deductions.
    """

    def calculate_inventory(
        self,
        grocery_items: List[GroceryItemCreate],
        meal_plan: MealPlanResponse,
        preserved_days: Optional[List[str]] = None,
    ) -> List[InventoryItemResponse]:
        """
        Calculate remaining inventory after meal plan deductions.

        For each grocery item, deducts the total quantity consumed across all
        non-preserved daily meals. Quantities floor at zero. Unmatched
        ingredients are skipped.

        Args:
            grocery_items: The original grocery list with quantities.
            meal_plan: The meal plan containing daily meals with ingredients.
            preserved_days: Optional list of day names (e.g., ["Monday", "Tuesday"])
                whose meals should NOT be deducted (already accounted for).

        Returns:
            List of InventoryItemResponse with remaining quantities.
        """
        if preserved_days is None:
            preserved_days = []

        # Normalize preserved days for case-insensitive comparison
        preserved_days_lower = [day.lower() for day in preserved_days]

        # Build a dictionary to accumulate deductions per grocery item index
        deductions: Dict[int, Decimal] = {i: Decimal("0") for i in range(len(grocery_items))}

        # Iterate over meals and deduct ingredients
        for meal in meal_plan.meals:
            # Skip preserved days — their deductions were already applied
            if meal.day_of_week.lower() in preserved_days_lower:
                continue

            for ingredient in meal.ingredients:
                matched_index = self._match_ingredient_to_grocery_index(
                    ingredient.ingredient_name, grocery_items
                )
                if matched_index is not None:
                    deductions[matched_index] += ingredient.quantity

        # Build inventory response with floor-at-zero logic
        inventory: List[InventoryItemResponse] = []
        for i, item in enumerate(grocery_items):
            remaining = item.quantity - deductions[i]
            remaining = max(remaining, Decimal("0"))
            inventory.append(
                InventoryItemResponse(
                    name=item.name,
                    original_quantity=item.quantity,
                    remaining_quantity=remaining,
                    unit=item.unit,
                )
            )

        return inventory

    def match_ingredient_to_grocery(
        self,
        ingredient_name: str,
        grocery_items: List[GroceryItemCreate],
    ) -> Optional[GroceryItemCreate]:
        """
        Match an ingredient name to a grocery item using case-insensitive
        substring matching.

        Returns the first grocery item whose name contains the ingredient name
        as a substring (case-insensitive), or whose name is contained within
        the ingredient name.

        Args:
            ingredient_name: The ingredient name from a meal recipe.
            grocery_items: The list of grocery items to match against.

        Returns:
            The matched GroceryItemCreate, or None if no match found.
        """
        index = self._match_ingredient_to_grocery_index(ingredient_name, grocery_items)
        if index is not None:
            return grocery_items[index]
        return None

    def _match_ingredient_to_grocery_index(
        self,
        ingredient_name: str,
        grocery_items: List[GroceryItemCreate],
    ) -> Optional[int]:
        """
        Internal helper that returns the index of the matched grocery item,
        or None if no match is found.

        Matching logic: case-insensitive substring match.
        - ingredient_name is a substring of grocery item name, OR
        - grocery item name is a substring of ingredient_name
        """
        ingredient_lower = ingredient_name.lower()

        for i, item in enumerate(grocery_items):
            item_lower = item.name.lower()
            if ingredient_lower in item_lower or item_lower in ingredient_lower:
                return i

        return None
