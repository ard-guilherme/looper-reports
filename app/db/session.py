from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings

client: AsyncIOMotorClient = None

async def get_database() -> AsyncIOMotorDatabase:
    if client is None:
        raise Exception("MongoDB client not initialized. Make sure to call connect_to_mongo on startup.")
    return client.get_database(settings.MONGO_DB_NAME)

async def connect_to_mongo():
    global client
    client = AsyncIOMotorClient(settings.MONGO_CONNECTION_STRING)
    print("Connected to MongoDB...")

async def close_mongo_connection():
    global client
    if client:
        client.close()
        print("MongoDB connection closed.")
