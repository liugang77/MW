from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db

router = APIRouter(tags=["currencies"])

# 默认币种（与桌面版一致）
_DEFAULT_CURRENCIES = [
    ("人民币", "CNY", True, 1.0000),
    ("美元", "USD", False, 6.8738),
    ("港元", "HKD", False, 0.7968),
    ("加拿大元", "CAD", False, 5.2441),
    ("欧元", "EUR", False, 7.2611),
    ("日元", "JPY", False, 0.0606),
    ("瑞士法郎", "CHF", False, 6.8224),
]

# 常见币种全集（补全用）：名称 / 英文缩写 / 对人民币参考牌价
_COMMON_CURRENCIES = [
    ("人民币", "CNY", 1.0000),
    ("美元", "USD", 7.1800),
    ("欧元", "EUR", 7.7900),
    ("港元", "HKD", 0.9200),
    ("英镑", "GBP", 9.1000),
    ("日元", "JPY", 0.0480),
    ("澳大利亚元", "AUD", 4.7500),
    ("加拿大元", "CAD", 5.2400),
    ("瑞士法郎", "CHF", 8.0000),
    ("新加坡元", "SGD", 5.3500),
    ("新西兰元", "NZD", 4.3500),
    ("韩元", "KRW", 0.0052),
    ("泰铢", "THB", 0.2000),
    ("马来西亚林吉特", "MYR", 1.5500),
    ("卢布", "RUB", 0.0800),
    ("新台币", "TWD", 0.2250),
    ("澳门元", "MOP", 0.8900),
    ("印度卢比", "INR", 0.0860),
    ("巴西雷亚尔", "BRL", 1.2500),
    ("南非兰特", "ZAR", 0.4000),
]


def _seed_currencies(ledger_id: int, db: Session) -> None:
    for idx, (name, code, is_home, rate) in enumerate(_DEFAULT_CURRENCIES):
        db.add(models.Currency(
            ledger_id=ledger_id, name=name, code=code, is_home=is_home, rate=rate, sort_order=idx
        ))
    db.commit()


@router.get("/ledgers/{ledger_id}/currencies", response_model=list[schemas.CurrencyOut])
def list_currencies(ledger_id: int, db: Session = Depends(get_db)):
    q = db.query(models.Currency).filter(models.Currency.ledger_id == ledger_id)
    if q.count() == 0:
        _seed_currencies(ledger_id, db)
    return (
        db.query(models.Currency)
        .filter(models.Currency.ledger_id == ledger_id)
        .order_by(models.Currency.sort_order, models.Currency.id)
        .all()
    )


@router.post("/ledgers/{ledger_id}/currencies", response_model=schemas.CurrencyOut)
def create_currency(ledger_id: int, payload: schemas.CurrencyCreate, db: Session = Depends(get_db)):
    cur = models.Currency(ledger_id=ledger_id, **payload.model_dump())
    db.add(cur)
    db.commit()
    db.refresh(cur)
    return cur


@router.post("/ledgers/{ledger_id}/currencies/supplement")
def supplement_currencies(ledger_id: int, db: Session = Depends(get_db)):
    """补全币种：把常见币种中、当前账簿尚不存在的补充进来（按英文缩写去重）。"""
    existing = {
        (c or "").strip().upper()
        for (c,) in db.query(models.Currency.code)
        .filter(models.Currency.ledger_id == ledger_id)
        .all()
        if c
    }
    base = (
        db.query(func.max(models.Currency.sort_order))
        .filter(models.Currency.ledger_id == ledger_id)
        .scalar()
        or 0
    )
    added: list[str] = []
    for name, code, rate in _COMMON_CURRENCIES:
        if code.upper() in existing:
            continue
        base += 1
        db.add(models.Currency(
            ledger_id=ledger_id, name=name, code=code,
            is_home=False, rate=rate, sort_order=base,
        ))
        added.append(code)
    db.commit()
    return {"added": len(added), "items": added}


@router.put("/currencies/{currency_id}", response_model=schemas.CurrencyOut)
def update_currency(currency_id: int, payload: schemas.CurrencyUpdate, db: Session = Depends(get_db)):
    cur = db.get(models.Currency, currency_id)
    if not cur:
        raise HTTPException(404, "记录不存在")
    data = payload.model_dump(exclude_unset=True)
    # 设为本币时，清除同账簿其它本币标记
    if data.get("is_home"):
        for other in db.query(models.Currency).filter(
            models.Currency.ledger_id == cur.ledger_id, models.Currency.id != currency_id
        ):
            other.is_home = False
    for field, value in data.items():
        setattr(cur, field, value)
    db.commit()
    db.refresh(cur)
    return cur


@router.delete("/currencies/{currency_id}")
def delete_currency(currency_id: int, db: Session = Depends(get_db)):
    cur = db.get(models.Currency, currency_id)
    if not cur:
        raise HTTPException(404, "记录不存在")
    db.delete(cur)
    db.commit()
    return {"detail": "已删除"}


# ---------- 汇率历史 ----------
@router.get("/ledgers/{ledger_id}/exchange-rates", response_model=list[schemas.ExchangeRateOut])
def list_exchange_rates(
    ledger_id: int,
    currency_code: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.ExchangeRate).filter(models.ExchangeRate.ledger_id == ledger_id)
    if currency_code:
        q = q.filter(models.ExchangeRate.currency_code == currency_code)
    return q.order_by(models.ExchangeRate.rate_date.desc(), models.ExchangeRate.id.desc()).all()


@router.post("/ledgers/{ledger_id}/exchange-rates", response_model=schemas.ExchangeRateOut)
def create_exchange_rate(ledger_id: int, payload: schemas.ExchangeRateCreate, db: Session = Depends(get_db)):
    rate = models.ExchangeRate(ledger_id=ledger_id, **payload.model_dump())
    db.add(rate)
    db.commit()
    db.refresh(rate)
    return rate


@router.put("/exchange-rates/{rate_id}", response_model=schemas.ExchangeRateOut)
def update_exchange_rate(rate_id: int, payload: schemas.ExchangeRateUpdate, db: Session = Depends(get_db)):
    rate = db.get(models.ExchangeRate, rate_id)
    if not rate:
        raise HTTPException(404, "记录不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rate, field, value)
    db.commit()
    db.refresh(rate)
    return rate


@router.delete("/exchange-rates/{rate_id}")
def delete_exchange_rate(rate_id: int, db: Session = Depends(get_db)):
    rate = db.get(models.ExchangeRate, rate_id)
    if not rate:
        raise HTTPException(404, "记录不存在")
    db.delete(rate)
    db.commit()
    return {"detail": "已删除"}


# ---------- 存款利率 ----------
# 人民币：(储蓄类型, 期间, 年利率%)
_DEFAULT_CNY_RATES = [
    ("活期储蓄", "-", 0.35),
    ("整存整取", "三个月期", 2.85),
    ("整存整取", "半年期", 3.05),
    ("整存整取", "一年期", 3.25),
    ("整存整取", "两年期", 3.75),
    ("整存整取", "三年期", 4.25),
    ("整存整取", "五年期", 4.75),
    ("零存整取", "一年期", 2.85),
    ("零存整取", "三年期", 2.90),
    ("零存整取", "五年期", 3.00),
    ("存本取息", "一年期", 2.85),
    ("存本取息", "三年期", 2.90),
    ("存本取息", "五年期", 3.00),
    ("整存零取", "一年期", 2.85),
    ("整存零取", "三年期", 2.90),
    ("整存零取", "五年期", 3.00),
]

# 外币：(币种名, 币种代码, 活期, 一个月, 三个月, 半年, 一年, 两年, 七天通知)
_DEFAULT_FOREIGN_RATES = [
    ("美元", "USD", 0.0500, 0.2000, 0.3000, 0.5000, 0.8000, 0.8000, 0.0500),
    ("港币", "HKD", 0.0100, 0.1000, 0.2500, 0.5000, 0.7000, 0.7500, 0.0100),
    ("加拿大元", "CAD", 0.0100, 0.0500, 0.0500, 0.3000, 0.4000, 0.4000, 0.0500),
    ("欧元", "EUR", 0.0050, 0.0300, 0.0500, 0.1500, 0.2000, 0.2500, 0.0050),
    ("日元", "JPY", 0.0001, 0.0100, 0.0100, 0.0100, 0.0100, 0.0100, 0.0005),
    ("瑞士法郎", "CHF", 0.0001, 0.0100, 0.0100, 0.0100, 0.0100, 0.0100, 0.0005),
    ("英镑", "GBP", 0.0500, 0.1000, 0.1000, 0.1000, 0.1000, 0.1000, 0.0500),
]


def _seed_deposit_rates(ledger_id: int, db: Session) -> None:
    for idx, (stype, term, rate) in enumerate(_DEFAULT_CNY_RATES):
        db.add(models.DepositRate(
            ledger_id=ledger_id, group_key="cny", sort_order=idx,
            save_type=stype, term=term, rate=rate,
        ))
    for idx, (name, code, rc, r1m, r3m, r6m, r1y, r2y, r7d) in enumerate(_DEFAULT_FOREIGN_RATES):
        db.add(models.DepositRate(
            ledger_id=ledger_id, group_key="foreign", sort_order=idx,
            currency_name=name, currency_code=code,
            r_current=rc, r_1m=r1m, r_3m=r3m, r_6m=r6m, r_1y=r1y, r_2y=r2y, r_7d_notice=r7d,
        ))
    db.commit()


@router.get("/ledgers/{ledger_id}/deposit-rates", response_model=list[schemas.DepositRateOut])
def list_deposit_rates(ledger_id: int, db: Session = Depends(get_db)):
    q = db.query(models.DepositRate).filter(models.DepositRate.ledger_id == ledger_id)
    if q.count() == 0:
        _seed_deposit_rates(ledger_id, db)
    return (
        db.query(models.DepositRate)
        .filter(models.DepositRate.ledger_id == ledger_id)
        .order_by(models.DepositRate.group_key, models.DepositRate.sort_order, models.DepositRate.id)
        .all()
    )


@router.put("/deposit-rates/{rate_id}", response_model=schemas.DepositRateOut)
def update_deposit_rate(rate_id: int, payload: schemas.DepositRateUpdate, db: Session = Depends(get_db)):
    rate = db.get(models.DepositRate, rate_id)
    if not rate:
        raise HTTPException(404, "记录不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rate, field, value)
    db.commit()
    db.refresh(rate)
    return rate

