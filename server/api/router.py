from fastapi import APIRouter
from .admin import router as admin_router
from .assets import router as assets_router
from .auth import router as auth_router
from .event import router as event_router
from .uploads import router as uploads_router
from .users import router as users_router


api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(event_router)
api_router.include_router(assets_router)
api_router.include_router(uploads_router)
api_router.include_router(users_router)
api_router.include_router(admin_router)

