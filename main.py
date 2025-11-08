from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.router import api_router

from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.router import api_router
from app.db.session import connect_to_mongo, close_mongo_connection

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Looper Reports AI API is running!"}
