from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db, redis_client

app = FastAPI(title="VeilGuard AI Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    # 1. Test Neon PostgreSQL + pgvector
    db.execute(text("SELECT 1"))
    # 2. Test Upstash Redis
    redis_ok = redis_client.ping()

    return {
        "status": "ok",
        "service": "VeilGuard Gateway",
        "postgres_connected": True,
        "redis_connected": redis_ok,
    }