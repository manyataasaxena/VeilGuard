from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.db_models import User, Document
from app.services.ingestion import ingest_pdf_document
from app.services.retrieval import hybrid_rbac_search

router = APIRouter(prefix="/docs", tags=["Documents & Hybrid RBAC Search"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    allowed_roles: str = Form("ADMIN,FINANCE"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Only ADMIN can upload documents")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    roles_list = [r.strip().upper() for r in allowed_roles.split(",") if r.strip()]
    file_bytes = await file.read()

    doc = ingest_pdf_document(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        filename=file.filename,
        file_bytes=file_bytes,
        allowed_roles=roles_list,
    )
    return {
        "id": doc.id,
        "filename": doc.filename,
        "allowed_roles": doc.allowed_roles,
        "total_pages": doc.total_pages,
        "status": doc.status,
    }


@router.get("/list")
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    docs = (
        db.query(Document)
        .filter(
            Document.org_id == current_user.org_id,
            Document.allowed_roles.any(current_user.role),
        )
        .order_by(Document.created_at.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "allowed_roles": d.allowed_roles,
            "total_pages": d.total_pages,
            "status": d.status,
        }
        for d in docs
    ]


@router.get("/search")
def search_documents(
    q: str = Query(..., min_length=2),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    results = hybrid_rbac_search(
        db=db,
        org_id=current_user.org_id,
        user_role=current_user.role,
        query=q,
        top_k=5,
    )
    return {
        "query": q,
        "user_role": current_user.role,
        "results_count": len(results),
        "results": results,
    }