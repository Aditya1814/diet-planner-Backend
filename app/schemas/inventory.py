from decimal import Decimal

from pydantic import BaseModel


class InventoryItemResponse(BaseModel):
    """Schema for an inventory item showing original and remaining quantities."""

    name: str
    original_quantity: Decimal
    remaining_quantity: Decimal
    unit: str
