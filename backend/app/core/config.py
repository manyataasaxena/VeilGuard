from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    HF_TOKEN: str = ""
    HF_INJECTION_MODEL: str = ""
    JWT_SECRET: str

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.DATABASE_URL.strip()
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    class Config:
        env_file = ".env"


settings = Settings()