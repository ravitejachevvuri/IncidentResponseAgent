import os


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://production_memory:production_memory@localhost:5432/production_memory",
    )
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    hindsight_api_key: str = os.getenv("HINDSIGHT_API_KEY", "")
    hindsight_base_url: str = os.getenv("HINDSIGHT_BASE_URL", "")


settings = Settings()
