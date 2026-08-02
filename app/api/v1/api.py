from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai_coach,
    athletes,
    auth,
    coaches,
    health,
    notifications,
    red_flags,
    strava,
    telegram,
    telemetry,
    webhooks,
    workouts,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(athletes.router, prefix="/athletes", tags=["athletes"])
api_router.include_router(coaches.router, prefix="/coaches", tags=["coaches"])
api_router.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
api_router.include_router(workouts.router, prefix="/workouts", tags=["workouts"])
api_router.include_router(red_flags.router, prefix="/red-flags", tags=["red-flags"])
api_router.include_router(ai_coach.router, prefix="/ai-coach", tags=["ai-coach"])
api_router.include_router(telegram.router, prefix="/telegram", tags=["telegram"])
api_router.include_router(webhooks.router, tags=["webhooks"])
api_router.include_router(strava.router, prefix="/strava", tags=["strava"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])


