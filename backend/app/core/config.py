from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    JWT_SECRET: str

    @property
    def sqlalchemy_database_url(self) -> str:
        # Neon 'postgresql://' deta hai, hum usse psycopg driver format mein convert kar rahe hain
        url = self.DATABASE_URL.strip()
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    class Config:
        env_file = ".env"


settings = Settings()