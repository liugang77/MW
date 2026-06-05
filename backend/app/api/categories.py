from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db

router = APIRouter(tags=["categories"])


@router.get("/ledgers/{ledger_id}/categories", response_model=list[schemas.CategoryOut])
def list_categories(ledger_id: int, kind: str | None = None, db: Session = Depends(get_db)):
    q = db.query(models.Category).filter(models.Category.ledger_id == ledger_id)
    if kind:
        q = q.filter(models.Category.kind == kind)
    return q.order_by(models.Category.sort_order, models.Category.id).all()


@router.post("/ledgers/{ledger_id}/categories", response_model=schemas.CategoryOut)
def create_category(ledger_id: int, payload: schemas.CategoryCreate, db: Session = Depends(get_db)):
    category = models.Category(ledger_id=ledger_id, **payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    category = db.get(models.Category, category_id)
    if not category:
        raise HTTPException(404, "分类不存在")
    category.is_active = False
    db.commit()
    return {"detail": "已停用"}


@router.put("/categories/{category_id}", response_model=schemas.CategoryOut)
def update_category(category_id: int, payload: schemas.CategoryUpdate, db: Session = Depends(get_db)):
    category = db.get(models.Category, category_id)
    if not category:
        raise HTTPException(404, "分类不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(category, k, v)
    db.commit()
    db.refresh(category)
    return category
