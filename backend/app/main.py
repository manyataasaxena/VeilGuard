from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db, redis_client, engine, Base
from app.models import db_models  # noqa: F401
from app.api import auth, documents

Base.metadata.create_all(bind=engine)

app = FastAPI(title="VeilGuard AI Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(documents.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    redis_ok = redis_client.ping()
    return {
        "status": "ok",
        "service": "VeilGuard Gateway",
        "postgres_connected": True,
        "redis_connected": redis_ok,
    }