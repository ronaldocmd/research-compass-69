from fastapi import APIRouter

from app.api.v1.endpoints import health, plan, researches, run

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(researches.router, prefix="/researches", tags=["researches"])
api_router.include_router(plan.router, prefix="/researches", tags=["planning"])
api_router.include_router(run.router, prefix="/researches", tags=["orchestration"])

