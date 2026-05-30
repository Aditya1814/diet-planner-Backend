from datetime import date
from decimal import Decimal

import pytest

from app.schemas.grocery import GroceryItemCreate
from app.schemas.inventory import InventoryItemResponse
from app.schemas.meal import DailyMealResponse, MealIngredient, MealPlanResponse
from app.services.inventory_service import InventoryService


@pytest.fixture
def service():
    return InventoryService()


@pytest.fixture
def sample_groceries():
    return [
        GroceryItemCreate(name="Chicken Breast", quantity=Decimal("2.0"), unit="kg"),
        GroceryItemCreate(name="Rice", quantity=Decimal("5.0"), unit="kg"),
        GroceryItemCreate(name="Olive Oil", quantity=Decimal("1.0"), unit="liters"),
        GroceryItemCreate(name="Tomatoes", quantity=Decimal("3.0"), unit="kg"),
    ]


@pytest.fixture
def sample_meal_plan():
    return MealPlanResponse(
        week_start_date=date(2024, 1, 1),
        meals=[
            DailyMealResponse(
                day_of_week="Monday",
                meal_type="dinner",
                meal_date=date(2024, 1, 1),
                meal_name="Grilled Chicken with Rice",
                ingredients=[
                    MealIngredient(ingredient_name="chicken breast", quantity=Decimal("0.5"), unit="kg"),
                    MealIngredient(ingredient_name="rice", quantity=Decimal("0.3"), unit="kg"),
                ],
                instructions=["Grill the chicken", "Cook the rice"],
            ),
            DailyMealResponse(
                day_of_week="Tuesday",
                meal_type="lunch",
                meal_date=date(2024, 1, 2),
                meal_name="Tomato Rice",
                ingredients=[
                    MealIngredient(ingredient_name="rice", quantity=Decimal("0.4"), unit="kg"),
                    MealIngredient(ingredient_name="tomatoes", quantity=Decimal("0.5"), unit="kg"),
                    MealIngredient(ingredient_name="olive oil", quantity=Decimal("0.1"), unit="liters"),
                ],
                instructions=["Cook rice with tomatoes"],
            ),
            DailyMealResponse(
                day_of_week="Wednesday",
                meal_type="dinner",
                meal_date=date(2024, 1, 3),
                meal_name="Chicken Stir Fry",
                ingredients=[
                    MealIngredient(ingredient_name="chicken breast", quantity=Decimal("0.4"), unit="kg"),
                    MealIngredient(ingredient_name="olive oil", quantity=Decimal("0.1"), unit="liters"),
                ],
                instructions=["Stir fry the chicken"],
            ),
        ],
    )


class TestCalculateInventory:
    def test_basic_deduction(self, service, sample_groceries, sample_meal_plan):
        """Test that ingredients are correctly deducted from grocery items."""
        result = service.calculate_inventory(sample_groceries, sample_meal_plan)

        assert len(result) == 4

        # Chicken: 2.0 - 0.5 (Mon) - 0.4 (Wed) = 1.1
        chicken = result[0]
        assert chicken.name == "Chicken Breast"
        assert chicken.original_quantity == Decimal("2.0")
        assert chicken.remaining_quantity == Decimal("1.1")

        # Rice: 5.0 - 0.3 (Mon) - 0.4 (Tue) = 4.3
        rice = result[1]
        assert rice.name == "Rice"
        assert rice.remaining_quantity == Decimal("4.3")

        # Olive Oil: 1.0 - 0.1 (Tue) - 0.1 (Wed) = 0.8
        oil = result[2]
        assert oil.name == "Olive Oil"
        assert oil.remaining_quantity == Decimal("0.8")

        # Tomatoes: 3.0 - 0.5 (Tue) = 2.5
        tomatoes = result[3]
        assert tomatoes.name == "Tomatoes"
        assert tomatoes.remaining_quantity == Decimal("2.5")

    def test_floor_at_zero(self, service):
        """Test that remaining quantity never goes below zero."""
        groceries = [
            GroceryItemCreate(name="Butter", quantity=Decimal("0.2"), unit="kg"),
        ]
        meal_plan = MealPlanResponse(
            week_start_date=date(2024, 1, 1),
            meals=[
                DailyMealResponse(
                    day_of_week="Monday",
                    meal_type="breakfast",
                    meal_date=date(2024, 1, 1),
                    meal_name="Buttery Toast",
                    ingredients=[
                        MealIngredient(ingredient_name="butter", quantity=Decimal("0.5"), unit="kg"),
                    ],
                    instructions=["Spread butter on toast"],
                ),
            ],
        )

        result = service.calculate_inventory(groceries, meal_plan)
        assert result[0].remaining_quantity == Decimal("0")

    def test_unmatched_ingredients_skipped(self, service):
        """Test that unmatched ingredients don't affect any grocery item."""
        groceries = [
            GroceryItemCreate(name="Rice", quantity=Decimal("5.0"), unit="kg"),
        ]
        meal_plan = MealPlanResponse(
            week_start_date=date(2024, 1, 1),
            meals=[
                DailyMealResponse(
                    day_of_week="Monday",
                    meal_type="lunch",
                    meal_date=date(2024, 1, 1),
                    meal_name="Mystery Meal",
                    ingredients=[
                        MealIngredient(ingredient_name="unknown spice", quantity=Decimal("1.0"), unit="tsp"),
                        MealIngredient(ingredient_name="rice", quantity=Decimal("0.5"), unit="kg"),
                    ],
                    instructions=["Cook it"],
                ),
            ],
        )

        result = service.calculate_inventory(groceries, meal_plan)
        # Only rice is deducted; unknown spice is skipped
        assert result[0].remaining_quantity == Decimal("4.5")

    def test_preserved_days_not_deducted(self, service, sample_groceries, sample_meal_plan):
        """Test that preserved days' meals are not deducted."""
        result = service.calculate_inventory(
            sample_groceries, sample_meal_plan, preserved_days=["Monday", "Tuesday"]
        )

        # Only Wednesday's meals should be deducted
        # Chicken: 2.0 - 0.4 (Wed only) = 1.6
        assert result[0].remaining_quantity == Decimal("1.6")
        # Rice: 5.0 - 0 = 5.0 (no rice on Wed)
        assert result[1].remaining_quantity == Decimal("5.0")
        # Olive Oil: 1.0 - 0.1 (Wed only) = 0.9
        assert result[2].remaining_quantity == Decimal("0.9")
        # Tomatoes: 3.0 - 0 = 3.0 (no tomatoes on Wed)
        assert result[3].remaining_quantity == Decimal("3.0")

    def test_preserved_days_case_insensitive(self, service, sample_groceries, sample_meal_plan):
        """Test that preserved_days matching is case-insensitive."""
        result = service.calculate_inventory(
            sample_groceries, sample_meal_plan, preserved_days=["monday", "TUESDAY"]
        )

        # Same as above — only Wednesday deducted
        assert result[0].remaining_quantity == Decimal("1.6")

    def test_empty_meal_plan(self, service, sample_groceries):
        """Test with no meals — all quantities remain unchanged."""
        empty_plan = MealPlanResponse(week_start_date=date(2024, 1, 1), meals=[])

        result = service.calculate_inventory(sample_groceries, empty_plan)

        for i, item in enumerate(sample_groceries):
            assert result[i].remaining_quantity == item.quantity

    def test_all_days_preserved(self, service, sample_groceries, sample_meal_plan):
        """Test that preserving all days results in no deductions."""
        result = service.calculate_inventory(
            sample_groceries,
            sample_meal_plan,
            preserved_days=["Monday", "Tuesday", "Wednesday"],
        )

        for i, item in enumerate(sample_groceries):
            assert result[i].remaining_quantity == item.quantity

    def test_returns_inventory_item_response(self, service, sample_groceries, sample_meal_plan):
        """Test that the return type is a list of InventoryItemResponse."""
        result = service.calculate_inventory(sample_groceries, sample_meal_plan)

        for item in result:
            assert isinstance(item, InventoryItemResponse)


class TestMatchIngredientToGrocery:
    def test_exact_match_case_insensitive(self, service):
        """Test exact match with different casing."""
        groceries = [
            GroceryItemCreate(name="Chicken Breast", quantity=Decimal("2.0"), unit="kg"),
        ]
        result = service.match_ingredient_to_grocery("chicken breast", groceries)
        assert result is not None
        assert result.name == "Chicken Breast"

    def test_ingredient_is_substring_of_grocery(self, service):
        """Test when ingredient name is a substring of grocery item name."""
        groceries = [
            GroceryItemCreate(name="Chicken Breast Boneless", quantity=Decimal("2.0"), unit="kg"),
        ]
        result = service.match_ingredient_to_grocery("chicken breast", groceries)
        assert result is not None
        assert result.name == "Chicken Breast Boneless"

    def test_grocery_is_substring_of_ingredient(self, service):
        """Test when grocery item name is a substring of ingredient name."""
        groceries = [
            GroceryItemCreate(name="Chicken", quantity=Decimal("2.0"), unit="kg"),
        ]
        result = service.match_ingredient_to_grocery("grilled chicken breast", groceries)
        assert result is not None
        assert result.name == "Chicken"

    def test_no_match_returns_none(self, service):
        """Test that no match returns None."""
        groceries = [
            GroceryItemCreate(name="Rice", quantity=Decimal("5.0"), unit="kg"),
        ]
        result = service.match_ingredient_to_grocery("chicken", groceries)
        assert result is None

    def test_first_match_returned(self, service):
        """Test that the first matching grocery item is returned."""
        groceries = [
            GroceryItemCreate(name="Olive Oil", quantity=Decimal("1.0"), unit="liters"),
            GroceryItemCreate(name="Olive Oil Extra Virgin", quantity=Decimal("0.5"), unit="liters"),
        ]
        result = service.match_ingredient_to_grocery("olive oil", groceries)
        assert result is not None
        assert result.name == "Olive Oil"

    def test_empty_grocery_list(self, service):
        """Test matching against an empty grocery list."""
        result = service.match_ingredient_to_grocery("chicken", [])
        assert result is None
