from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import redis
from app.core.config import settings

engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Upstash TLS (rediss://) + RESP2 protocol fix for redis 8.x
redis_url = settings.REDIS_URL.strip()
if redis_url.startswith("redis://") and "upstash.io" in redis_url:
    redis_url = redis_url.replace("redis://", "rediss://", 1)

redis_client = redis.from_url(
    redis_url,
    decode_responses=True,
    protocol=2,
    socket_connect_timeout=5,
    socket_timeout=5,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()