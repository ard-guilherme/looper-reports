from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8')

    PROJECT_NAME: str = "Looper Reports AI"
    MONGO_CONNECTION_STRING: str
    GEMINI_API_KEY: str
    REPORT_TEMPLATE_FILE: str = "app/templates/report_template.html"
    PROMPTS_DIR: str = "app/agents/prompts"
    MONGO_DB_NAME: str = "mario_bot_db"
    LOG_LEVEL: str = "INFO"
    API_V1_STR: str = "/api/v1"

settings = Settings()
