from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Looper Reports AI"
    MONGO_CONNECTION_STRING: str
    GEMINI_API_KEY: str
    REPORT_PROMPT: str
    MONGO_DB_NAME: str = "mario_bot_db"
    API_V1_STR: str = "/api/v1"

    class Config:
        env_file = ".env"

settings = Settings()
