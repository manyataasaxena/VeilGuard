from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, get_current_user
from app.models.db_models import Organization, User

router = APIRouter(prefix="/auth", tags=["Authentication & RBAC"])

VALID_ROLES = {"ADMIN", "FINANCE", "HR", "INTERN"}


class RegisterRequest(BaseModel):
    org_name: str
    full_name: str
    email: str
    password: str
    role: str = "INTERN"


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    role = req.role.upper()
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of {VALID_ROLES}")

    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    org = db.query(Organization).filter(Organization.name == req.org_name).first()
    if not org:
        org = Organization(name=req.org_name)
        db.add(org)
        db.flush()

    user = User(
        org_id=org.id,
        full_name=req.full_name,
        email=req.email,
        password_hash=hash_password(req.password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.org_id, user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "role": user.role, "org_id": user.org_id},
    }


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.id, user.org_id, user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "org_id": user.org_id,
        },
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "role": current_user.role,
        "org_id": current_user.org_id,
    }


@router.post("/demo-seed")
def seed_demo_users(db: Session = Depends(get_db)):
    """3 demo roles (Admin, Finance, Intern) create karta hai."""
    org = db.query(Organization).filter(Organization.name == "FinCorp Global").first()
    if not org:
        org = Organization(name="FinCorp Global")
        db.add(org)
        db.flush()

    demo_accounts = [
        ("admin@fincorp.com", "Aarav (Admin)", "ADMIN"),
        ("finance@fincorp.com", "Meera (Finance)", "FINANCE"),
        ("intern@fincorp.com", "Rohan (Intern)", "INTERN"),
    ]

    created = []
    for email, name, role in demo_accounts:
        if not db.query(User).filter(User.email == email).first():
            user = User(
                org_id=org.id,
                email=email,
                full_name=name,
                password_hash=hash_password("demo1234"),
                role=role,
            )
            db.add(user)
            created.append(email)
    db.commit()

    return {"org": org.name, "newly_created": created, "default_password": "demo1234"}