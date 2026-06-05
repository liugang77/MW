from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db

router = APIRouter(tags=["holdings"])


def _to_out(h: models.Holding) -> schemas.HoldingOut:
    out = schemas.HoldingOut.model_validate(h)
    market_value = Decimal(h.quantity) * Decimal(h.price)
    out.market_value = market_value
    out.profit = market_value - Decimal(h.cost)
    out.profit_rate = float(round(out.profit / Decimal(h.cost) * 100, 2)) if h.cost else 0.0
    return out


def _validate_holding_amounts(data: dict) -> None:
    """持仓的数量/成本/价格不应为负，避免手工编辑写入非法值。"""
    for field, label in (("quantity", "数量"), ("cost", "成本"), ("price", "价格")):
        if field in data and data[field] is not None and Decimal(str(data[field])) < 0:
            raise HTTPException(400, f"持仓{label}不能为负")


@router.get("/ledgers/{ledger_id}/holdings", response_model=list[schemas.HoldingOut])
def list_holdings(ledger_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(models.Holding)
        .filter(models.Holding.ledger_id == ledger_id)
        .order_by(models.Holding.id)
        .all()
    )
    return [_to_out(h) for h in rows]


@router.post("/ledgers/{ledger_id}/holdings", response_model=schemas.HoldingOut)
def create_holding(ledger_id: int, payload: schemas.HoldingCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    _validate_holding_amounts(data)
    holding = models.Holding(ledger_id=ledger_id, **data)
    db.add(holding)
    db.commit()
    db.refresh(holding)
    return _to_out(holding)


@router.put("/holdings/{holding_id}", response_model=schemas.HoldingOut)
def update_holding(holding_id: int, payload: schemas.HoldingUpdate, db: Session = Depends(get_db)):
    holding = db.get(models.Holding, holding_id)
    if not holding:
        raise HTTPException(404, "持仓不存在")
    data = payload.model_dump(exclude_unset=True)
    _validate_holding_amounts(data)
    for k, v in data.items():
        setattr(holding, k, v)
    db.commit()
    db.refresh(holding)
    return _to_out(holding)


@router.delete("/holdings/{holding_id}")
def delete_holding(holding_id: int, db: Session = Depends(get_db)):
    holding = db.get(models.Holding, holding_id)
    if not holding:
        raise HTTPException(404, "持仓不存在")
    db.delete(holding)
    db.commit()
    return {"detail": "已删除"}
