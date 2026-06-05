from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db

router = APIRouter(tags=["instruments"])


@router.get("/ledgers/{ledger_id}/instruments", response_model=list[schemas.InstrumentOut])
def list_instruments(
    ledger_id: int,
    category: str | None = None,
    q: str | None = None,
    limit: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Instrument).filter(models.Instrument.ledger_id == ledger_id)
    if category:
        query = query.filter(models.Instrument.category == category)
    if q:
        kw = f"%{q.strip()}%"
        query = query.filter(
            (models.Instrument.code.like(kw)) | (models.Instrument.name.like(kw))
        )
    query = query.order_by(models.Instrument.code, models.Instrument.id)
    if limit and limit > 0:
        query = query.limit(limit)
    return query.all()


@router.post("/ledgers/{ledger_id}/instruments", response_model=schemas.InstrumentOut)
def create_instrument(ledger_id: int, payload: schemas.InstrumentCreate, db: Session = Depends(get_db)):
    inst = models.Instrument(ledger_id=ledger_id, **payload.model_dump())
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


@router.put("/instruments/{instrument_id}", response_model=schemas.InstrumentOut)
def update_instrument(instrument_id: int, payload: schemas.InstrumentUpdate, db: Session = Depends(get_db)):
    inst = db.get(models.Instrument, instrument_id)
    if not inst:
        raise HTTPException(404, "记录不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(inst, field, value)
    db.commit()
    db.refresh(inst)
    return inst


@router.delete("/instruments/{instrument_id}")
def delete_instrument(instrument_id: int, db: Session = Depends(get_db)):
    inst = db.get(models.Instrument, instrument_id)
    if not inst:
        raise HTTPException(404, "记录不存在")
    db.delete(inst)
    db.commit()
    return {"detail": "已删除"}


def _price_out(p: models.InstrumentPrice, inst: models.Instrument | None) -> schemas.InstrumentPriceOut:
    out = schemas.InstrumentPriceOut.model_validate(p)
    if inst:
        out.code = inst.code
        out.name = inst.name
    return out


@router.get("/ledgers/{ledger_id}/instrument-prices", response_model=list[schemas.InstrumentPriceOut])
def list_instrument_prices(
    ledger_id: int,
    category: str | None = None,
    instrument_id: int | None = None,
    db: Session = Depends(get_db),
):
    # 直接联表查询，仅取「有价格记录」的产品，避免把整个分类（可达数万条）全量载入。
    pq = (
        db.query(models.InstrumentPrice, models.Instrument)
        .join(models.Instrument, models.Instrument.id == models.InstrumentPrice.instrument_id)
        .filter(models.Instrument.ledger_id == ledger_id)
    )
    if category:
        pq = pq.filter(models.Instrument.category == category)
    if instrument_id:
        pq = pq.filter(models.InstrumentPrice.instrument_id == instrument_id)
    rows = pq.order_by(
        models.InstrumentPrice.price_date.desc(), models.InstrumentPrice.id.desc()
    ).all()
    return [_price_out(p, inst) for p, inst in rows]


@router.post("/ledgers/{ledger_id}/instrument-prices", response_model=schemas.InstrumentPriceOut)
def create_instrument_price(
    ledger_id: int, payload: schemas.InstrumentPriceCreate, db: Session = Depends(get_db)
):
    inst = db.get(models.Instrument, payload.instrument_id)
    if not inst or inst.ledger_id != ledger_id:
        raise HTTPException(404, "金融产品不存在")
    price = models.InstrumentPrice(**payload.model_dump())
    db.add(price)
    db.commit()
    db.refresh(price)
    return _price_out(price, inst)


@router.put("/instrument-prices/{price_id}", response_model=schemas.InstrumentPriceOut)
def update_instrument_price(
    price_id: int, payload: schemas.InstrumentPriceUpdate, db: Session = Depends(get_db)
):
    price = db.get(models.InstrumentPrice, price_id)
    if not price:
        raise HTTPException(404, "记录不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(price, field, value)
    db.commit()
    db.refresh(price)
    inst = db.get(models.Instrument, price.instrument_id)
    return _price_out(price, inst)


@router.delete("/instrument-prices/{price_id}")
def delete_instrument_price(price_id: int, db: Session = Depends(get_db)):
    price = db.get(models.InstrumentPrice, price_id)
    if not price:
        raise HTTPException(404, "记录不存在")
    db.delete(price)
    db.commit()
    return {"detail": "已删除"}


# ---------- 证券交易费率 ----------
# 默认费率（与桌面版一致）：A股 / B股
_DEFAULT_FEE_ROWS = [
    # group_key, security_type, buy_stamp, sell_stamp, buy_comm, buy_min, sell_comm, sell_min, surcharge, transfer, settle, settle_cap, reg
    ("a_share", "沪市股票｜沪市A股", 0, 0.1, 0.3, 5, 0.3, 5, 0, 0.01, 0, 0, 0),
    ("a_share", "沪市基金｜沪市A股", 0, 0, 0.3, 5, 0.3, 5, 0, 0, 0, 0, 0),
    ("a_share", "沪市投资基金｜沪市A股", 0, 0, 0.3, 5, 0.3, 5, 0, 0, 0, 0, 0),
    ("a_share", "沪市债券｜沪市A股", 0, 0, 0.1, 5, 0.1, 5, 0, 0, 0, 0, 0),
    ("a_share", "深市股票｜深市A股", 0, 0.1, 0.3, 5, 0.3, 5, 0, 0.01, 0, 0, 0),
    ("a_share", "深市基金｜深市A股", 0, 0, 0.3, 5, 0.3, 5, 0, 0, 0, 0, 0),
    ("a_share", "深市投资基金｜深市A股", 0, 0, 0.3, 0, 0.3, 0, 0, 0, 0, 0, 0),
    ("a_share", "深市债券｜深市A股", 0, 0, 0.1, 0, 0.1, 0, 0, 0, 0, 0, 0),
    ("a_share", "京市A股", 0, 0.1, 0.15, 5, 0.15, 5, 0, 0.01, 0, 0, 0),
    ("b_share", "沪市B股", 0, 0.1, 0.3, 1, 0.3, 1, 0, 0, 0.05, 0, 0),
    ("b_share", "深市B股", 0, 0.1, 0.3, 0.05, 0.3, 0.05, 0, 0, 0.05, 500, 0.0341),
]


def _seed_fee_rates(ledger_id: int, db: Session) -> None:
    for idx, row in enumerate(_DEFAULT_FEE_ROWS):
        (gk, stype, bs, ss, bc, bm, sc, sm, sur, tr, se, sec, reg) = row
        db.add(models.TradeFeeRate(
            ledger_id=ledger_id, group_key=gk, security_type=stype, sort_order=idx,
            buy_stamp_tax=bs, sell_stamp_tax=ss, buy_commission=bc, buy_min_commission=bm,
            sell_commission=sc, sell_min_commission=sm, surcharge=sur, transfer_fee=tr,
            settle_fee=se, settle_cap=sec, trade_reg_fee=reg,
        ))
    db.commit()


@router.get("/ledgers/{ledger_id}/trade-fee-rates", response_model=list[schemas.TradeFeeRateOut])
def list_trade_fee_rates(ledger_id: int, db: Session = Depends(get_db)):
    q = db.query(models.TradeFeeRate).filter(models.TradeFeeRate.ledger_id == ledger_id)
    if q.count() == 0:
        _seed_fee_rates(ledger_id, db)
    return (
        db.query(models.TradeFeeRate)
        .filter(models.TradeFeeRate.ledger_id == ledger_id)
        .order_by(models.TradeFeeRate.group_key, models.TradeFeeRate.sort_order, models.TradeFeeRate.id)
        .all()
    )


@router.put("/trade-fee-rates/{rate_id}", response_model=schemas.TradeFeeRateOut)
def update_trade_fee_rate(rate_id: int, payload: schemas.TradeFeeRateUpdate, db: Session = Depends(get_db)):
    rate = db.get(models.TradeFeeRate, rate_id)
    if not rate:
        raise HTTPException(404, "记录不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rate, field, value)
    db.commit()
    db.refresh(rate)
    return rate

