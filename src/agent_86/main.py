from fastapi import FastAPI

from agent_86.api.router import router
from agent_86.core.config import settings


app = FastAPI(title=settings.app_name)
app.include_router(router)