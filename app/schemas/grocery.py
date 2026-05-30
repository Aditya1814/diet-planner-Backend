from decimal import Decimal
from typing import List

from pydantic import BaseModel, Field


class GroceryItemCreate(BaseModel):
    """Schema for creating a single grocery item."""

    name: str = Field(min_length=1, max_length=100)
    quantity: Decimal = Field(ge=Decimal("0.01"), le=Decimal("9999.99"))
    unit: str = Field(min_length=1, max_length=20)


class GroceryListCreate(BaseModel):
    """Schema for creating a grocery list with dietary preferences."""

    items: List[GroceryItemCreate] = Field(min_length=1, max_length=50)
    dietary_preferences: List[str] = Field(default_factory=list)
