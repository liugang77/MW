from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db

router = APIRouter(tags=["budgets"])


def _spent(db: Session, ledger_id: int, category_id: int | None, period: str) -> Decimal:
    now = datetime.now()
    if period == "year":
        start = datetime(now.year, 1, 1)
    else:
        start = datetime(now.year, now.month, 1)
    q = (
        db.query(func.coalesce(func.sum(models.Transaction.amount), 0))
        .filter(models.Transaction.ledger_id == ledger_id)
        .filter(models.Transaction.type == "expense")
        .filter(models.Transaction.occurred_at >= start)
    )
    if category_id:
        q = q.filter(models.Transaction.category_id == category_id)
    return Decimal(q.scalar() or 0)


def _to_out(db: Session, b: models.Budget) -> schemas.BudgetOut:
    cat = db.get(models.Category, b.category_id) if b.category_id else None
    out = schemas.BudgetOut.model_validate(b)
    out.category_name = cat.name if cat else "总预算"
    out.spent = _spent(db, b.ledger_id, b.category_id, b.period)
    return out


@router.get("/ledgers/{ledger_id}/budgets", response_model=list[schemas.BudgetOut])
def list_budgets(ledger_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(models.Budget)
        .filter(models.Budget.ledger_id == ledger_id, models.Budget.is_active == True)  # noqa: E712
        .order_by(models.Budget.id)
        .all()
    )
    return [_to_out(db, b) for b in rows]


@router.post("/ledgers/{ledger_id}/budgets", response_model=schemas.BudgetOut)
def create_budget(ledger_id: int, payload: schemas.BudgetCreate, db: Session = Depends(get_db)):
    budget = models.Budget(ledger_id=ledger_id, **payload.model_dump())
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return _to_out(db, budget)


@router.put("/budgets/{budget_id}", response_model=schemas.BudgetOut)
def update_budget(budget_id: int, payload: schemas.BudgetUpdate, db: Session = Depends(get_db)):
    budget = db.get(models.Budget, budget_id)
    if not budget:
        raise HTTPException(404, "预算不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(budget, k, v)
    db.commit()
    db.refresh(budget)
    return _to_out(db, budget)


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: int, db: Session = Depends(get_db)):
    budget = db.get(models.Budget, budget_id)
    if not budget:
        raise HTTPException(404, "预算不存在")
    db.delete(budget)
    db.commit()
    return {"detail": "已删除"}
