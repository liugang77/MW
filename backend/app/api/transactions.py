from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db
from app.services.balance import apply_transaction

router = APIRouter(tags=["transactions"])


def _add_months(d: datetime, n: int) -> datetime:
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    # 防止越界（如 1月31日 + 1 个月）
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return d.replace(year=year, month=month, day=day)


def _to_out(txn: models.Transaction) -> dict:
    data = {
        "id": txn.id,
        "ledger_id": txn.ledger_id,
        "type": txn.type,
        "amount": txn.amount,
        "currency": txn.currency,
        "account_id": txn.account_id,
        "to_account_id": txn.to_account_id,
        "category_id": txn.category_id,
        "fee": txn.fee,
        "occurred_at": txn.occurred_at,
        "remark": txn.remark,
        "merchant": txn.merchant,
        "created_at": txn.created_at,
        "tag_ids": [t.id for t in txn.tags],
    }
    data["split_group"] = txn.split_group
    data["trade_price"] = txn.trade_price
    data["trade_qty"] = txn.trade_qty
    data["trade_commission"] = txn.trade_commission
    data["trade_fee"] = txn.trade_fee
    data["trade_cost"] = txn.trade_cost
    data["trade_symbol"] = txn.trade_symbol
    data["loan_id"] = txn.loan_id
    data["collect_group"] = txn.collect_group
    data["voucher_id"] = txn.voucher_id
    data["insurance_activity"] = txn.insurance_activity
    data["ipo_status"] = txn.ipo_status
    return data


def _attach_tags(db: Session, txn: models.Transaction, tag_ids: list[int]) -> None:
    if not tag_ids:
        return
    tags = db.query(models.Tag).filter(models.Tag.id.in_(tag_ids)).all()
    txn.tags = tags


def _check_balance_limit(db: Session, txn: models.Transaction) -> None:
    """资金可用性校验：

    - 现金 / 三方储值 / 银行卡：余额不能为负（先有钱才能花）。
    - 信用卡：可透支（余额为负），但不得超过信用额度。
    其余类型（投资、保险、债权债务、重大资产等）不在此校验范围内。
    """
    # 只有支出 / 转出会减少出账账户余额
    if txn.type not in ("expense", "transfer"):
        return
    acc = db.get(models.Account, txn.account_id)
    if acc is None:
        return
    outflow = Decimal(txn.amount) + Decimal(txn.fee or 0)
    projected = Decimal(acc.current_balance) - outflow
    if acc.type in ("cash", "wallet", "bank"):
        if projected < 0:
            raise HTTPException(
                400,
                f"「{acc.name}」余额不足：可用 {acc.current_balance}，本次需 {outflow}。请先记一笔余额调整或收入。",
            )
    elif acc.type == "credit":
        limit = Decimal(acc.credit_limit or 0)
        if limit > 0 and projected < -limit:
            raise HTTPException(
                400,
                f"「{acc.name}」超出信用额度：额度 {limit}，透支后将达 {-projected}。",
            )


# ---------- 标签 ----------
@router.get("/ledgers/{ledger_id}/tags", response_model=list[schemas.TagOut])
def list_tags(ledger_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.Tag)
        .filter(models.Tag.ledger_id == ledger_id)
        .order_by(models.Tag.sort_order, models.Tag.id)
        .all()
    )


@router.post("/ledgers/{ledger_id}/tags", response_model=schemas.TagOut)
def create_tag(ledger_id: int, payload: schemas.TagCreate, db: Session = Depends(get_db)):
    tag = models.Tag(ledger_id=ledger_id, **payload.model_dump())
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = db.get(models.Tag, tag_id)
    if not tag:
        raise HTTPException(404, "标签不存在")
    db.delete(tag)
    db.commit()
    return {"detail": "已删除"}


@router.get("/ledgers/{ledger_id}/transactions", response_model=schemas.TransactionPage)
def list_transactions(
    ledger_id: int,
    type: str | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    tag_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(models.Transaction).filter(models.Transaction.ledger_id == ledger_id)
    if type:
        q = q.filter(models.Transaction.type == type)
    if account_id:
        q = q.filter(
            (models.Transaction.account_id == account_id)
            | (models.Transaction.to_account_id == account_id)
        )
    if category_id:
        q = q.filter(models.Transaction.category_id == category_id)
    if tag_id:
        q = q.filter(models.Transaction.tags.any(models.Tag.id == tag_id))
    if start:
        q = q.filter(models.Transaction.occurred_at >= start)
    if end:
        q = q.filter(models.Transaction.occurred_at <= end)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            models.Transaction.remark.like(like) | models.Transaction.merchant.like(like)
        )

    total = q.count()
    items = (
        q.order_by(models.Transaction.occurred_at.desc(), models.Transaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"items": [_to_out(t) for t in items], "total": total, "page": page, "page_size": page_size}


@router.post("/ledgers/{ledger_id}/transactions", response_model=schemas.TransactionOut)
def create_transaction(
    ledger_id: int, payload: schemas.TransactionCreate, db: Session = Depends(get_db)
):
    data = payload.model_dump()
    tag_ids = data.pop("tag_ids", [])
    if data.get("occurred_at") is None:
        data["occurred_at"] = datetime.now()
    txn = models.Transaction(ledger_id=ledger_id, **data)
    db.add(txn)
    db.flush()
    _attach_tags(db, txn, tag_ids)
    _check_balance_limit(db, txn)
    apply_transaction(db, txn, sign=1)
    db.commit()
    db.refresh(txn)
    return _to_out(txn)


# ---------- 分拆收支 ----------
@router.post("/ledgers/{ledger_id}/transactions/split", response_model=list[schemas.TransactionOut])
def split_transaction(ledger_id: int, payload: schemas.SplitCreate, db: Session = Depends(get_db)):
    """将一笔总额拆为多笔收支记录，共用同一资金账户。"""
    if payload.type not in ("expense", "income"):
        raise HTTPException(400, "分拆仅支持收入或支出")
    if not payload.items:
        raise HTTPException(400, "请至少添加一笔明细")
    occurred = payload.occurred_at or datetime.now()
    group = uuid4().hex[:24]
    created: list[models.Transaction] = []
    for item in payload.items:
        txn = models.Transaction(
            ledger_id=ledger_id,
            type=payload.type,
            amount=item.amount,
            account_id=payload.account_id,
            category_id=item.category_id,
            occurred_at=occurred,
            remark=item.remark,
            split_group=group,
        )
        db.add(txn)
        db.flush()
        _attach_tags(db, txn, item.tag_ids)
        _check_balance_limit(db, txn)
        apply_transaction(db, txn, sign=1)
        created.append(txn)
    db.commit()
    return [_to_out(t) for t in created]


@router.post("/ledgers/{ledger_id}/salary", response_model=list[schemas.TransactionOut])
def create_salary(ledger_id: int, payload: schemas.SalaryCreate, db: Session = Depends(get_db)):
    """工资收入：将收入项目（income）与扣款项目（expense）记为同一分组的多笔流水。

    净到账 = 收入合计 − 扣款合计，由这些流水共同累计到收入账户余额。
    """
    if not payload.incomes:
        raise HTTPException(400, "请至少添加一项收入")
    when = payload.occurred_at or datetime.now()
    group = uuid4().hex[:24]
    created: list[models.Transaction] = []

    def _add(txn_type: str, item: schemas.SalaryItem, default_prefix: str) -> None:
        amt = Decimal(item.amount or 0)
        if amt <= 0:
            return
        note = (item.name or "").strip() or default_prefix
        txn = models.Transaction(
            ledger_id=ledger_id, type=txn_type, amount=amt,
            currency=payload.currency, account_id=payload.account_id,
            category_id=item.category_id, occurred_at=when,
            remark=note, split_group=group,
        )
        db.add(txn)
        db.flush()
        _attach_tags(db, txn, payload.tag_ids)
        _check_balance_limit(db, txn)
        apply_transaction(db, txn, sign=1)
        created.append(txn)

    for it in payload.incomes:
        _add("income", it, "工资收入")
    for it in payload.deductions:
        _add("expense", it, "工资扣款")

    if not created:
        raise HTTPException(400, "请输入有效的收入金额")

    db.commit()
    return [_to_out(t) for t in created]


@router.get("/ledgers/{ledger_id}/transactions/split/{group}", response_model=list[schemas.TransactionOut])
def get_split_group(ledger_id: int, group: str, db: Session = Depends(get_db)):
    """获取一组分拆收支的全部明细。"""
    rows = (
        db.query(models.Transaction)
        .filter(models.Transaction.ledger_id == ledger_id, models.Transaction.split_group == group)
        .order_by(models.Transaction.id)
        .all()
    )
    if not rows:
        raise HTTPException(404, "分拆记录不存在")
    return [_to_out(t) for t in rows]


@router.put("/ledgers/{ledger_id}/transactions/split/{group}", response_model=list[schemas.TransactionOut])
def update_split_group(ledger_id: int, group: str, payload: schemas.SplitCreate, db: Session = Depends(get_db)):
    """整组替换分拆收支：先回滚并删除旧明细，再按新明细重建（沿用原分组标识）。"""
    if payload.type not in ("expense", "income"):
        raise HTTPException(400, "分拆仅支持收入或支出")
    if not payload.items:
        raise HTTPException(400, "请至少添加一笔明细")
    old = (
        db.query(models.Transaction)
        .filter(models.Transaction.ledger_id == ledger_id, models.Transaction.split_group == group)
        .all()
    )
    if not old:
        raise HTTPException(404, "分拆记录不存在")
    for t in old:
        apply_transaction(db, t, sign=-1)
        db.delete(t)
    db.flush()
    occurred = payload.occurred_at or datetime.now()
    created: list[models.Transaction] = []
    for item in payload.items:
        txn = models.Transaction(
            ledger_id=ledger_id,
            type=payload.type,
            amount=item.amount,
            account_id=payload.account_id,
            category_id=item.category_id,
            occurred_at=occurred,
            remark=item.remark,
            split_group=group,
        )
        db.add(txn)
        db.flush()
        _attach_tags(db, txn, item.tag_ids)
        _check_balance_limit(db, txn)
        apply_transaction(db, txn, sign=1)
        created.append(txn)
    db.commit()
    return [_to_out(t) for t in created]


# ---------- 待摊费用 ----------
def _get_deferred_account(db: Session, ledger_id: int) -> models.Account:
    acc = (
        db.query(models.Account)
        .filter(models.Account.ledger_id == ledger_id, models.Account.type == "deferred")
        .first()
    )
    if not acc:
        acc = models.Account(
            ledger_id=ledger_id, name="待摊费用", type="deferred", icon="calendar",
            initial_balance=0, current_balance=0, include_in_net=True,
        )
        db.add(acc)
        db.flush()
    return acc


@router.post("/ledgers/{ledger_id}/transactions/transfer", response_model=list[schemas.TransactionOut])
def create_transfer(ledger_id: int, payload: schemas.TransferCreate, db: Session = Depends(get_db)):
    """转账：从转出账户转入转入账户；手续费可由单独的手续费账户承担。"""
    if payload.from_account_id == payload.to_account_id:
        raise HTTPException(400, "转出账户与转入账户不能相同")
    when = payload.occurred_at or datetime.now()
    created: list[models.Transaction] = []

    # 手续费独立账户：转账本身不含手续费，手续费单独记一笔支出
    sep_fee = bool(payload.fee and payload.fee > 0 and payload.fee_account_id
                   and payload.fee_account_id != payload.from_account_id)
    bundled_fee = Decimal("0") if sep_fee else Decimal(payload.fee or 0)

    txn = models.Transaction(
        ledger_id=ledger_id, type="transfer", amount=payload.amount,
        currency=payload.currency, account_id=payload.from_account_id,
        to_account_id=payload.to_account_id, fee=bundled_fee,
        occurred_at=when, remark=payload.remark,
    )
    db.add(txn)
    db.flush()
    _check_balance_limit(db, txn)
    apply_transaction(db, txn, sign=1)
    _attach_tags(db, txn, payload.tag_ids)
    created.append(txn)

    if sep_fee:
        fee_txn = models.Transaction(
            ledger_id=ledger_id, type="expense", amount=Decimal(payload.fee),
            currency=payload.currency, account_id=payload.fee_account_id,
            occurred_at=when, remark=(payload.remark or "转账") + "（手续费）",
        )
        db.add(fee_txn)
        db.flush()
        _check_balance_limit(db, fee_txn)
        apply_transaction(db, fee_txn, sign=1)
        created.append(fee_txn)

    db.commit()
    return [_to_out(t) for t in created]


@router.post("/ledgers/{ledger_id}/transactions/exchange", response_model=list[schemas.TransactionOut])
def create_exchange(ledger_id: int, payload: schemas.ExchangeCreate, db: Session = Depends(get_db)):
    """货币兑换：在两个账户间换汇，金额可不等。记为两笔余额调整（不计入收支统计）。"""
    if payload.from_account_id == payload.to_account_id:
        raise HTTPException(400, "卖出账户与买入账户不能相同")
    when = payload.occurred_at or datetime.now()
    note = payload.remark or "货币兑换"
    created: list[models.Transaction] = []

    # 卖出：转出账户减少 from_amount
    out_txn = models.Transaction(
        ledger_id=ledger_id, type="adjust", amount=-Decimal(payload.from_amount),
        account_id=payload.from_account_id, occurred_at=when, remark=note,
    )
    db.add(out_txn)
    db.flush()
    apply_transaction(db, out_txn, sign=1)
    created.append(out_txn)

    # 买入：转入账户增加 to_amount
    in_txn = models.Transaction(
        ledger_id=ledger_id, type="adjust", amount=Decimal(payload.to_amount),
        account_id=payload.to_account_id, occurred_at=when, remark=note,
    )
    db.add(in_txn)
    db.flush()
    apply_transaction(db, in_txn, sign=1)
    created.append(in_txn)

    # 手续费
    if payload.fee and payload.fee > 0:
        fee_acc_id = payload.fee_account_id or payload.from_account_id
        fee_txn = models.Transaction(
            ledger_id=ledger_id, type="expense", amount=Decimal(payload.fee),
            account_id=fee_acc_id, occurred_at=when, remark=note + "（手续费）",
        )
        db.add(fee_txn)
        db.flush()
        _check_balance_limit(db, fee_txn)
        apply_transaction(db, fee_txn, sign=1)
        created.append(fee_txn)

    db.commit()
    return [_to_out(t) for t in created]


def _currency_rate(db: Session, ledger_id: int, code: str) -> Decimal:
    """取币种对人民币牌价（1 单位外币 = ? 人民币）；本币或未知按 1 计。"""
    cur = (db.query(models.Currency)
           .filter(models.Currency.ledger_id == ledger_id, models.Currency.code == code)
           .first())
    return Decimal(cur.rate) if cur and cur.rate else Decimal("1")


def _get_forex_holding(db: Session, ledger_id: int, account_id: int, code: str,
                       name: str, rate: Decimal) -> models.Holding:
    """取/建外汇账户下某币种的持仓（type='forex'，symbol=币种代码）。"""
    h = (db.query(models.Holding)
         .filter(models.Holding.account_id == account_id,
                 models.Holding.type == "forex",
                 models.Holding.symbol == code)
         .first())
    if not h:
        h = models.Holding(ledger_id=ledger_id, account_id=account_id, symbol=code,
                           name=name or code, type="forex",
                           quantity=Decimal("0"), cost=Decimal("0"), price=rate)
        db.add(h)
        db.flush()
    return h


def _rebuild_forex_holdings(db: Session, ledger_id: int, account_id: int) -> None:
    """根据该外汇账户现存的全部外汇买卖/转账流水，按时间顺序重算各币种持仓。

    采用「全量回放」而非「增量回滚」，确保删除/编辑后持仓始终自洽。
    """
    # 现有外汇持仓清零
    existing = (
        db.query(models.Holding)
        .filter(models.Holding.account_id == account_id, models.Holding.type == "forex")
        .all()
    )
    for h in existing:
        h.quantity = Decimal("0")
        h.cost = Decimal("0")

    txns = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.ledger_id == ledger_id,
            or_(
                models.Transaction.account_id == account_id,
                models.Transaction.to_account_id == account_id,
            ),
        )
        .order_by(models.Transaction.occurred_at, models.Transaction.id)
        .all()
    )

    state: dict[str, dict] = {}

    def st(code: str) -> dict:
        return state.setdefault(code, {"qty": Decimal("0"), "cost": Decimal("0")})

    for t in txns:
        if t.trade_symbol and "/" in (t.trade_symbol or ""):
            # 外汇买卖：卖出币减少、买入币增加
            sell_code, buy_code = t.trade_symbol.split("/", 1)
            sell_amt = Decimal(t.amount or 0)
            buy_amt = Decimal(t.trade_qty or 0)
            sell_rate = _currency_rate(db, ledger_id, sell_code)
            cny_value = sell_amt * sell_rate
            # 用外部资金账户购汇（to_account_id 指向非本外汇账户）：卖出币不从持仓扣，仅增加买入币
            ext_funding = bool(t.to_account_id) and t.to_account_id != account_id
            if not ext_funding:
                s = st(sell_code)
                if s["qty"] > 0:
                    keep = (s["qty"] - sell_amt) / s["qty"]
                    if keep < 0:
                        keep = Decimal("0")
                    s["cost"] = s["cost"] * keep
                s["qty"] = s["qty"] - sell_amt
            b = st(buy_code)
            b["qty"] = b["qty"] + buy_amt
            b["cost"] = b["cost"] + cny_value
        elif t.type == "transfer":
            # 外汇转账：转入增加该币种、转出减少
            code = t.currency or "CNY"
            amount = Decimal(t.amount or 0)
            rate = _currency_rate(db, ledger_id, code)
            h = st(code)
            if t.to_account_id == account_id:
                h["qty"] = h["qty"] + amount
                h["cost"] = h["cost"] + amount * rate
            else:
                if h["qty"] > 0:
                    keep = (h["qty"] - amount) / h["qty"]
                    if keep < 0:
                        keep = Decimal("0")
                    h["cost"] = h["cost"] * keep
                h["qty"] = h["qty"] - amount

    for code, s in state.items():
        cur = (db.query(models.Currency)
               .filter(models.Currency.ledger_id == ledger_id,
                       models.Currency.code == code).first())
        rate = _currency_rate(db, ledger_id, code)
        h = _get_forex_holding(db, ledger_id, account_id, code,
                               cur.name if cur else code, rate)
        h.quantity = s["qty"].quantize(Decimal("0.0001"))
        h.cost = s["cost"].quantize(Decimal("0.01"))
        h.price = rate
        h.updated_at = datetime.now()


def _forex_account_of(db: Session, txn: models.Transaction) -> models.Account | None:
    """返回该流水涉及的外汇账户（account_id 或 to_account_id 任一为 forex）。"""
    for aid in (txn.account_id, txn.to_account_id):
        if aid:
            a = db.get(models.Account, aid)
            if a and a.type == "forex":
                return a
    return None


def _reverse_forex_counter_balance(db: Session, txn: models.Transaction, forex_acc_id: int) -> None:
    """回滚一笔外汇流水对「对方资金账户」余额的影响（持仓由重算处理）。"""
    # 外汇买卖：若用外部资金账户购汇（to_account_id 指向资金账户），曾扣减 amount → 回补
    if txn.trade_symbol and "/" in (txn.trade_symbol or ""):
        if txn.to_account_id and txn.to_account_id != forex_acc_id:
            funding = db.get(models.Account, txn.to_account_id)
            if funding:
                funding.current_balance = Decimal(funding.current_balance) + Decimal(txn.amount)
        return
    if txn.type != "transfer":
        return
    if txn.to_account_id == forex_acc_id:
        # 转入：对方账户曾被扣减 → 回补
        counter = db.get(models.Account, txn.account_id)
        if counter:
            counter.current_balance = Decimal(counter.current_balance) + Decimal(txn.amount)
    else:
        # 转出：对方账户曾被增加 → 扣回
        counter = db.get(models.Account, txn.to_account_id)
        if counter:
            counter.current_balance = Decimal(counter.current_balance) - Decimal(txn.amount)


@router.post("/ledgers/{ledger_id}/forex/trade", response_model=list[schemas.TransactionOut])
def create_forex_trade(ledger_id: int, payload: schemas.ForexTradeCreate, db: Session = Depends(get_db)):
    """外汇买卖：卖出一种货币换入另一种货币。
    记一笔余额调整流水（不计入收支），随后按全部外汇流水重算持仓。
    买入金额 = 卖出金额 × 交易汇率。支持编辑（先删原流水再重建）。
    """
    if payload.sell_currency == payload.buy_currency:
        raise HTTPException(400, "卖出货币与买入货币不能相同")
    sell_amt = Decimal(payload.sell_amount)
    buy_amt = Decimal(payload.buy_amount)
    if sell_amt <= 0 or buy_amt <= 0:
        raise HTTPException(400, "买卖金额必须大于 0")

    acc = db.get(models.Account, payload.account_id)
    if not acc:
        raise HTTPException(404, "交易账户不存在")

    when = payload.occurred_at or datetime.now()

    # 资金账户：用外部资金账户的本币余额购汇（为空或指向外汇账户自身则用账户内本币持仓）
    funding_id = payload.funding_account_id
    if funding_id == acc.id:
        funding_id = None
    funding = db.get(models.Account, funding_id) if funding_id else None
    if funding_id and not funding:
        raise HTTPException(404, "资金账户不存在")

    # 编辑：先回滚原流水对资金账户余额的影响并删除（持仓由稍后重算处理）
    if payload.edit_txn_id:
        old = db.get(models.Transaction, payload.edit_txn_id)
        if old:
            _reverse_forex_counter_balance(db, old, acc.id)
            db.delete(old)
            db.flush()

    # 用外部资金账户购汇：从该账户扣减本次人民币总额（现金类不可透支）
    if funding:
        if funding.type in ("cash", "wallet", "bank", "prepaid") and Decimal(funding.current_balance) < sell_amt:
            raise HTTPException(400, f"{funding.name} 余额不足")
        funding.current_balance = Decimal(funding.current_balance) - sell_amt

    note = payload.remark or f"外汇买卖：卖出{sell_amt}{payload.sell_currency} 买入{buy_amt}{payload.buy_currency}"
    txn = models.Transaction(
        ledger_id=ledger_id, type="adjust", amount=sell_amt, currency=payload.sell_currency,
        account_id=acc.id, to_account_id=(funding.id if funding else None),
        occurred_at=when, remark=note,
        trade_symbol=f"{payload.sell_currency}/{payload.buy_currency}",
        trade_price=Decimal(payload.rate), trade_qty=buy_amt,
    )
    db.add(txn)
    db.flush()
    _attach_tags(db, txn, payload.tag_ids)

    _rebuild_forex_holdings(db, ledger_id, acc.id)
    db.commit()
    return [_to_out(txn)]


@router.post("/ledgers/{ledger_id}/forex/transfer", response_model=list[schemas.TransactionOut])
def create_forex_transfer(ledger_id: int, payload: schemas.ForexTransferCreate, db: Session = Depends(get_db)):
    """外汇转账：在对方资金账户与外汇账户某币种持仓之间划转资金。
    转入：对方账户减少 amount，外汇该币种持仓增加 amount（成本按牌价折人民币）。
    转出：外汇该币种持仓减少 amount，对方账户增加 amount。
    外汇账户余额恒为 0（价值由持仓体现）。支持编辑（先回滚原流水再重建）。
    """
    amount = Decimal(payload.amount)
    if amount <= 0:
        raise HTTPException(400, "金额必须大于 0")
    acc = db.get(models.Account, payload.account_id)
    if not acc:
        raise HTTPException(404, "外汇账户不存在")
    counter = db.get(models.Account, payload.counter_account_id)
    if not counter:
        raise HTTPException(404, "对方账户不存在")
    is_in = payload.direction == "in"
    when = payload.occurred_at or datetime.now()
    cur = (db.query(models.Currency)
           .filter(models.Currency.ledger_id == ledger_id,
                   models.Currency.code == payload.currency).first())
    cur_name = cur.name if cur else payload.currency

    # 编辑：先回滚原流水对对方账户余额的影响并删除，再重算持仓得到不含原流水的快照
    if payload.edit_txn_id:
        old = db.get(models.Transaction, payload.edit_txn_id)
        if old:
            _reverse_forex_counter_balance(db, old, acc.id)
            db.delete(old)
            db.flush()
            _rebuild_forex_holdings(db, ledger_id, acc.id)

    if is_in:
        # 转入：对方账户支出 amount（现金类不可透支）
        if counter.type in ("cash", "wallet", "bank", "prepaid") and Decimal(counter.current_balance) < amount:
            raise HTTPException(400, f"{counter.name} 余额不足")
        counter.current_balance = Decimal(counter.current_balance) - amount
    else:
        # 转出：外汇账户该币种持仓不足时不允许（避免负持仓）
        h = (db.query(models.Holding)
             .filter(models.Holding.account_id == acc.id,
                     models.Holding.type == "forex",
                     models.Holding.symbol == payload.currency)
             .first())
        avail = Decimal(h.quantity) if h and h.quantity else Decimal("0")
        if avail < amount:
            raise HTTPException(400, f"{cur_name} 余额不足")
        counter.current_balance = Decimal(counter.current_balance) + amount

    note = payload.remark or (f"外汇转入：{cur_name}" if is_in else f"外汇转出：{cur_name}")
    txn = models.Transaction(
        ledger_id=ledger_id, type="transfer", amount=amount, currency=payload.currency,
        account_id=(counter.id if is_in else acc.id),
        to_account_id=(acc.id if is_in else counter.id),
        occurred_at=when, remark=note,
    )
    db.add(txn)
    db.flush()
    _rebuild_forex_holdings(db, ledger_id, acc.id)
    db.commit()
    return [_to_out(txn)]


@router.post("/ledgers/{ledger_id}/transactions/deferred", response_model=list[schemas.TransactionOut])
def create_deferred(ledger_id: int, payload: schemas.DeferredCreate, db: Session = Depends(get_db)):
    """待摊费用：先由支付账户一次性转入「待摊费用」账户，再按月分摊为支出。"""
    if payload.periods < 1:
        raise HTTPException(400, "待摊次数至少为 1")
    start = payload.start or datetime.now()
    deferred_acc = _get_deferred_account(db, ledger_id)
    created: list[models.Transaction] = []

    # 1) 支付：从支付账户转入待摊账户（资金现在流出，不计入收支）
    pay = models.Transaction(
        ledger_id=ledger_id, type="transfer", amount=payload.total,
        account_id=payload.account_id, to_account_id=deferred_acc.id,
        occurred_at=start, remark=f"待摊支付：{payload.name}",
    )
    db.add(pay)
    db.flush()
    apply_transaction(db, pay, sign=1)
    created.append(pay)

    # 2) 分摊：按月从待摊账户支出
    each = (Decimal(payload.total) / payload.periods).quantize(Decimal("0.01"))
    accumulated = Decimal("0")
    for i in range(payload.periods):
        amt = each if i < payload.periods - 1 else Decimal(payload.total) - accumulated
        accumulated += amt
        txn = models.Transaction(
            ledger_id=ledger_id, type="expense", amount=amt,
            account_id=deferred_acc.id, category_id=payload.category_id,
            occurred_at=_add_months(start, i),
            remark=f"待摊分摊：{payload.name}（{i + 1}/{payload.periods}）",
        )
        db.add(txn)
        db.flush()
        apply_transaction(db, txn, sign=1)
        created.append(txn)

    db.commit()
    return [_to_out(t) for t in created]


@router.delete("/transactions/{txn_id}")
def delete_transaction(txn_id: int, db: Session = Depends(get_db)):
    txn = db.get(models.Transaction, txn_id)
    if not txn:
        raise HTTPException(404, "流水不存在")
    # 网贷收回流水：整组回滚（本金+利息）并恢复项目待收/期数
    if txn.collect_group:
        from app.api.loans import _reverse_collect_group
        _reverse_collect_group(db, txn.ledger_id, txn.collect_group)
        db.commit()
        return {"detail": "已删除"}
    # 网贷借出流水：回滚并删除对应项目
    if txn.loan_id:
        from app.api.loans import _reverse_loan_lend
        loan = db.get(models.Loan, txn.loan_id)
        if loan:
            _reverse_loan_lend(db, loan)
            db.commit()
            return {"detail": "已删除"}
    # 团购券流水：按购券/核销/退券性质回滚券状态
    if txn.voucher_id:
        from app.api.vouchers import _reverse_voucher_txn
        _reverse_voucher_txn(db, txn)
        db.commit()
        return {"detail": "已删除"}
    # 外汇买卖/转账流水：回滚对方账户余额并重算外汇持仓
    forex_acc = _forex_account_of(db, txn)
    if forex_acc is not None:
        _reverse_forex_counter_balance(db, txn, forex_acc.id)
        db.delete(txn)
        db.flush()
        _rebuild_forex_holdings(db, txn.ledger_id, forex_acc.id)
        db.commit()
        return {"detail": "已删除"}
    # 证券/基金买卖流水：同时回滚持仓
    if txn.trade_qty is not None and txn.trade_symbol:
        from app.api.trades import _reverse_trade_txn
        _reverse_trade_txn(db, txn)
        db.commit()
        return {"detail": "已删除"}
    apply_transaction(db, txn, sign=-1)  # 回滚余额
    db.delete(txn)
    db.commit()
    return {"detail": "已删除"}


@router.delete("/ledgers/{ledger_id}/transactions/split/{group}")
def delete_split_group(ledger_id: int, group: str, db: Session = Depends(get_db)):
    """删除整组分拆收支。"""
    rows = (
        db.query(models.Transaction)
        .filter(models.Transaction.ledger_id == ledger_id, models.Transaction.split_group == group)
        .all()
    )
    if not rows:
        raise HTTPException(404, "分拆记录不存在")
    for t in rows:
        apply_transaction(db, t, sign=-1)
        db.delete(t)
    db.commit()
    return {"detail": "已删除"}


@router.put("/transactions/{txn_id}", response_model=schemas.TransactionOut)
def update_transaction(
    txn_id: int, payload: schemas.TransactionUpdate, db: Session = Depends(get_db)
):
    txn = db.get(models.Transaction, txn_id)
    if not txn:
        raise HTTPException(404, "流水不存在")
    data = payload.model_dump(exclude_unset=True)
    tag_ids = data.pop("tag_ids", None)
    apply_transaction(db, txn, sign=-1)  # 先回滚旧余额
    for key, value in data.items():
        setattr(txn, key, value)
    if txn.occurred_at is None:
        txn.occurred_at = datetime.now()
    db.flush()
    if tag_ids is not None:
        tags = db.query(models.Tag).filter(models.Tag.id.in_(tag_ids)).all() if tag_ids else []
        txn.tags = tags
    apply_transaction(db, txn, sign=1)  # 重新应用新余额
    db.commit()
    db.refresh(txn)
    return _to_out(txn)
