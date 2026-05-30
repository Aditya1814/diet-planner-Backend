"""Image service for retrieving meal photos."""

from __future__ import annotations
import hashlib
import httpx
from urllib.parse import quote


class ImageService:
    """Retrieves meal image URLs. Uses multiple free sources."""

    def __init__(self, api_key: str = "", search_engine_id: str = ""):
        self.api_key = api_key
        self.search_engine_id = search_engine_id

    async def get_meal_image(self, meal_name: str) -> str:
        """
        Get an image URL for a meal. Tries multiple free sources:
        1. Spoonacular-style URL (food-specific, free)
        2. Fallback to a seeded placeholder
        """
        # Try fetching from foodish (random food images API - free, no key)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://foodish-api.com/api/")
                if response.status_code == 200:
                    data = response.json()
                    image_url = data.get("image")
                    if image_url:
                        return image_url
        except Exception:
            pass

        # Fallback: use picsum with a seed based on meal name (consistent per meal)
        seed = int(hashlib.md5(meal_name.encode()).hexdigest()[:8], 16) % 1000
        return f"https://picsum.photos/seed/{seed}/400/300"
