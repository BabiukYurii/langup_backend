from fastapi import APIRouter

from app.routers.auth import router as auth_router
from app.routers.health_check import router as health_router
from app.routers.user import router as user_router
from app.routers.vocabulary import router as vocabulary_router

__all__ = ["router"]

router = APIRouter(prefix="/api")
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(user_router)
router.include_router(vocabulary_router)
