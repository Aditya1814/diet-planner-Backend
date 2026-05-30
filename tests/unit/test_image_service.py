"""Unit tests for ImageService."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.image_service import ImageService


@pytest.fixture
def image_service():
    """Create an ImageService instance with test credentials."""
    return ImageService(api_key="test-api-key", search_engine_id="test-engine-id")


@pytest.mark.asyncio
async def test_get_meal_image_returns_first_result_url(image_service):
    """Should return the first image URL from search results."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "items": [
            {"link": "https://example.com/chicken.jpg"},
            {"link": "https://example.com/chicken2.jpg"},
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        result = await image_service.get_meal_image("Grilled Chicken")

    assert result == "https://example.com/chicken.jpg"


@pytest.mark.asyncio
async def test_get_meal_image_returns_none_on_empty_results(image_service):
    """Should return None when no search results are found."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"items": []}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        result = await image_service.get_meal_image("Nonexistent Meal XYZ")

    assert result is None


@pytest.mark.asyncio
async def test_get_meal_image_returns_none_on_no_items_key(image_service):
    """Should return None when response has no 'items' key."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        result = await image_service.get_meal_image("Some Meal")

    assert result is None


@pytest.mark.asyncio
async def test_get_meal_image_returns_none_on_http_error(image_service):
    """Should return None when the API returns an HTTP error."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403 Forbidden", request=MagicMock(), response=mock_response
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        result = await image_service.get_meal_image("Grilled Chicken")

    assert result is None


@pytest.mark.asyncio
async def test_get_meal_image_returns_none_on_timeout(image_service):
    """Should return None when the request times out."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.TimeoutException("timeout")):
        result = await image_service.get_meal_image("Grilled Chicken")

    assert result is None


@pytest.mark.asyncio
async def test_get_meal_image_returns_none_on_network_error(image_service):
    """Should return None on network connectivity errors."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("connection failed")):
        result = await image_service.get_meal_image("Grilled Chicken")

    assert result is None


@pytest.mark.asyncio
async def test_get_meal_image_returns_none_with_empty_api_key():
    """Should return None when API key is empty."""
    service = ImageService(api_key="", search_engine_id="test-engine-id")
    result = await service.get_meal_image("Grilled Chicken")
    assert result is None


@pytest.mark.asyncio
async def test_get_meal_image_returns_none_with_empty_engine_id():
    """Should return None when search engine ID is empty."""
    service = ImageService(api_key="test-api-key", search_engine_id="")
    result = await service.get_meal_image("Grilled Chicken")
    assert result is None
