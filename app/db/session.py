from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

class MongoClient:
    client: AsyncIOMotorClient = None
    db = None

    async def connect(self):
        self.client = AsyncIOMotorClient(settings.MONGO_CONNECTION_STRING)
        self.db = self.client.get_database()
        print("Connected to MongoDB...")

    async def close(self):
        if self.client:
            self.client.close()
            print("MongoDB connection closed.")

mongodb_client = MongoClient()

async def get_database():
    return mongodb_client.db
