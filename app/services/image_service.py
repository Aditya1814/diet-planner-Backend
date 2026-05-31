"""Image service for retrieving meal photos."""

from __future__ import annotations
import hashlib
import httpx


class ImageService:
    """Retrieves meal image URLs using free sources."""

    def __init__(self, api_key: str = "", search_engine_id: str = ""):
        self.api_key = api_key
        self.search_engine_id = search_engine_id

    async def get_meal_image(self, meal_name: str) -> str:
        """
        Get an image URL for a meal.
        Uses foodish API with a short timeout, falls back to picsum.
        """
        # Try foodish API (random food images - free, no key)
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get("https://foodish-api.com/api/")
                if response.status_code == 200:
                    data = response.json()
                    image_url = data.get("image")
                    if image_url:
                        return image_url
        except Exception:
            pass

        # Fallback: picsum with seed based on meal name
        seed = int(hashlib.md5(meal_name.encode()).hexdigest()[:8], 16) % 1000
        return f"https://picsum.photos/seed/{seed}/400/300"
