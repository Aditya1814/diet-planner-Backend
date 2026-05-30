from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes.auth import router as auth_router
from app.routes.groceries import router as groceries_router
from app.routes.meal_plan import router as meal_plan_router
from app.routes.preferences import router as preferences_router

settings = get_settings()

app = FastAPI(
    title="Diet Planner API",
    description="AI-powered weekly meal planning based on grocery lists",
    version="1.0.0",
)

# Configure CORS middleware for frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(groceries_router)
app.include_router(meal_plan_router)
app.include_router(preferences_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
