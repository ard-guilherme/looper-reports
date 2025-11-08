from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.router import api_router

from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.router import api_router
from app.db.session import mongodb_client

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

@app.on_event("startup")
async def startup_db_client():
    await mongodb_client.connect()

@app.on_event("shutdown")
async def shutdown_db_client():
    await mongodb_client.close()

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Looper Reports AI API is running!"}
