from datetime import datetime, date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db
from app.services.balance import apply_transaction

router = APIRouter(tags=["plans"])


# ---------- 工具 ----------
def _parse(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    # 处理月末
    import calendar
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _advance(d: date, frequency: str) -> date | None:
    if frequency == "daily":
        return d + timedelta(days=1)
    if frequency == "weekly":
        return d + timedelta(days=7)
    if frequency == "monthly":
        return _add_months(d, 1)
    if frequency == "quarterly":
        return _add_months(d, 3)
    if frequency == "yearly":
        return _add_months(d, 12)
    return None  # once


def _attach_tags(db: Session, obj, tag_ids: list[int] | None) -> None:
    if tag_ids is None:
        return
    obj.tags = db.query(models.Tag).filter(models.Tag.id.in_(tag_ids)).all() if tag_ids else []


def _attach_txn_tags(db: Session, txn: models.Transaction, tag_ids: list[int] | None) -> None:
    if tag_ids:
        txn.tags = db.query(models.Tag).filter(models.Tag.id.in_(tag_ids)).all()


def _out(plan: models.Plan) -> schemas.PlanOut:
    return schemas.PlanOut.model_validate(plan)


# ---------- 贷款/网贷计划同步 ----------
def _unit_to_freq(unit: str | None) -> str:
    return {"day": "daily", "week": "weekly", "month": "monthly", "year": "yearly"}.get(unit or "", "monthly")


def _sync_loan_plans(ledger_id: int, db: Session) -> None:
    """根据未结清的网贷/分期贷款，自动生成或更新对应的收/还款计划。"""
    loans = (
        db.query(models.Loan)
        .filter(models.Loan.ledger_id == ledger_id, models.Loan.is_closed == False)  # noqa: E712
        .all()
    )
    existing = {
        p.loan_id: p
        for p in db.query(models.Plan).filter(
            models.Plan.ledger_id == ledger_id, models.Plan.loan_id.isnot(None)
        ).all()
    }
    seen: set[int] = set()
    for loan in loans:
        name = loan.item or loan.counterparty or "贷款"
        if loan.loan_kind == "p2p":
            plan_type = "p2p_collect"
            freq = _unit_to_freq(loan.collect_interval_unit)
            start = loan.first_collect_at.date() if loan.first_collect_at else (loan.occurred_at.date() if loan.occurred_at else date.today())
            collected = loan.collected_periods or 0
            nxt = start
            for _ in range(collected):
                adv = _advance(nxt, freq)
                nxt = adv or nxt
            label = f"{loan.counterparty or '网贷'}｜{loan.item or name} 收款"
        else:
            plan_type = "loan_repay"
            freq = "monthly"
            start = loan.due_at.date() if loan.due_at else (loan.occurred_at.date() if loan.occurred_at else date.today())
            nxt = start
            label = f"贷款[{name}]还款计划"
        seen.add(loan.id)
        p = existing.get(loan.id)
        if p:
            # 仅更新随贷款变化的字段，保留用户对名称等的修改
            p.next_run_date = nxt.isoformat()
            p.frequency = freq
            p.status = "done" if loan.is_closed else "active"
        else:
            p = models.Plan(
                ledger_id=ledger_id, plan_type=plan_type, name=label,
                frequency=freq, start_date=start.isoformat(),
                end_date=loan.due_at.date().isoformat() if loan.due_at else None,
                next_run_date=nxt.isoformat(), status="active",
                auto_execute=bool(loan.auto_execute),
                account_id=loan.account_id, to_account_id=loan.cash_account_id,
                amount=loan.per_interest or 0, loan_id=loan.id,
                remark=f"{name} 计划自动入账",
            )
            db.add(p)
    # 关闭已结清贷款对应的计划
    for loan_id, p in existing.items():
        if loan_id not in seen and p.plan_type in ("p2p_collect", "loan_repay"):
            p.status = "done"
    db.commit()


# ---------- CRUD ----------
@router.get("/ledgers/{ledger_id}/plans", response_model=list[schemas.PlanOut])
def list_plans(ledger_id: int, db: Session = Depends(get_db)):
    _sync_loan_plans(ledger_id, db)
    rows = (
        db.query(models.Plan)
        .filter(models.Plan.ledger_id == ledger_id)
        .order_by(models.Plan.status, models.Plan.next_run_date.desc(), models.Plan.id.desc())
        .all()
    )
    return [_out(p) for p in rows]


@router.post("/ledgers/{ledger_id}/plans", response_model=schemas.PlanOut)
def create_plan(ledger_id: int, payload: schemas.PlanCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    tag_ids = data.pop("tag_ids", [])
    if not data.get("next_run_date"):
        data["next_run_date"] = data["start_date"]
    plan = models.Plan(ledger_id=ledger_id, **data)
    _attach_tags(db, plan, tag_ids)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _out(plan)


@router.put("/plans/{plan_id}", response_model=schemas.PlanOut)
def update_plan(plan_id: int, payload: schemas.PlanUpdate, db: Session = Depends(get_db)):
    plan = db.get(models.Plan, plan_id)
    if not plan:
        raise HTTPException(404, "记录不存在")
    data = payload.model_dump(exclude_unset=True)
    tag_ids = data.pop("tag_ids", None)
    for k, v in data.items():
        setattr(plan, k, v)
    _attach_tags(db, plan, tag_ids)
    db.commit()
    db.refresh(plan)
    return _out(plan)


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(models.Plan, plan_id)
    if not plan:
        raise HTTPException(404, "记录不存在")
    db.delete(plan)
    db.commit()
    return {"detail": "已删除"}


# ---------- 执行 ----------
def _advance_plan(plan: models.Plan) -> None:
    """执行后推进到下次执行日期；一次性或超过结束日期则标记完成。"""
    plan.last_run_at = datetime.now()
    cur = _parse(plan.next_run_date) or _parse(plan.start_date) or date.today()
    nxt = _advance(cur, plan.frequency)
    end = _parse(plan.end_date)
    if nxt is None or (end and nxt > end):
        plan.status = "done"
        plan.next_run_date = None
    else:
        plan.next_run_date = nxt.isoformat()


@router.post("/plans/{plan_id}/execute", response_model=schemas.PlanOut)
def execute_plan(plan_id: int, payload: schemas.PlanExecute, db: Session = Depends(get_db)):
    plan = db.get(models.Plan, plan_id)
    if not plan:
        raise HTTPException(404, "记录不存在")
    if plan.status != "active":
        raise HTTPException(400, "该计划已完成或已暂停")

    lid = plan.ledger_id
    occurred = payload.occurred_at or (
        datetime.combine(_parse(plan.next_run_date) or date.today(), datetime.min.time())
    )
    amount = Decimal(payload.amount) if payload.amount is not None else Decimal(plan.amount or 0)
    remark = payload.remark if payload.remark is not None else (plan.remark or plan.name)
    tag_ids = payload.tag_ids if payload.tag_ids is not None else [t.id for t in plan.tags]

    if plan.plan_type == "reminder":
        # 仅提醒，不产生交易
        pass

    elif plan.plan_type == "income_expense":
        if not plan.account_id:
            raise HTTPException(400, "缺少资金账户")
        txn = models.Transaction(
            ledger_id=lid, type=plan.txn_type or "expense", amount=amount,
            account_id=plan.account_id, category_id=plan.category_id,
            occurred_at=occurred, remark=remark,
        )
        db.add(txn)
        db.flush()
        _attach_txn_tags(db, txn, tag_ids)
        apply_transaction(db, txn, sign=1)

    elif plan.plan_type == "transfer":
        if not plan.account_id or not plan.to_account_id:
            raise HTTPException(400, "缺少转出或转入账户")
        fee = Decimal(payload.fee) if payload.fee is not None else Decimal(plan.fee or 0)
        # 手续费账户与转出账户不同时，单独记一笔手续费支出
        sep_fee = fee > 0 and plan.fee_account_id and plan.fee_account_id != plan.account_id
        txn = models.Transaction(
            ledger_id=lid, type="transfer", amount=amount,
            account_id=plan.account_id, to_account_id=plan.to_account_id,
            fee=Decimal("0") if sep_fee else fee, occurred_at=occurred, remark=remark,
        )
        db.add(txn)
        db.flush()
        _attach_txn_tags(db, txn, tag_ids)
        apply_transaction(db, txn, sign=1)
        if sep_fee:
            fee_txn = models.Transaction(
                ledger_id=lid, type="expense", amount=fee,
                account_id=plan.fee_account_id, occurred_at=occurred,
                remark=f"{remark} 手续费",
            )
            db.add(fee_txn)
            db.flush()
            apply_transaction(db, fee_txn, sign=1)

    elif plan.plan_type == "fund_invest":
        if not plan.account_id or not plan.to_account_id:
            raise HTTPException(400, "缺少基金账户或资金账户")
        symbol = plan.fund_symbol or (str(plan.instrument_id) if plan.instrument_id else "FUND")
        inst = db.get(models.Instrument, plan.instrument_id) if plan.instrument_id else None
        name = inst.name if inst else symbol
        rate = Decimal(plan.fee_rate or 0)
        fee = (amount * rate / Decimal(100)).quantize(Decimal("0.01"))
        net = amount - fee
        # 最新净值
        price = Decimal("0")
        if plan.instrument_id:
            pr = (
                db.query(models.InstrumentPrice)
                .filter(models.InstrumentPrice.instrument_id == plan.instrument_id)
                .order_by(models.InstrumentPrice.price_date.desc())
                .first()
            )
            if pr:
                price = Decimal(pr.price)
        shares = (net / price).quantize(Decimal("0.0001")) if price > 0 else Decimal("0")
        # 资金账户支出
        pay = models.Transaction(
            ledger_id=lid, type="expense", amount=amount,
            account_id=plan.to_account_id, occurred_at=occurred,
            remark=remark or f"基金定投：{name}",
        )
        db.add(pay)
        db.flush()
        _attach_txn_tags(db, pay, tag_ids)
        apply_transaction(db, pay, sign=1)
        # 基金账户增加持仓成本
        gain = models.Transaction(
            ledger_id=lid, type="income", amount=amount,
            account_id=plan.account_id, occurred_at=occurred,
            remark=f"基金定投：{name}",
            trade_price=price or None, trade_qty=shares or None, trade_fee=fee,
        )
        db.add(gain)
        db.flush()
        apply_transaction(db, gain, sign=1)
        # 更新/创建持仓
        holding = (
            db.query(models.Holding)
            .filter(
                models.Holding.ledger_id == lid,
                models.Holding.account_id == plan.account_id,
                models.Holding.symbol == symbol,
            )
            .first()
        )
        if holding:
            holding.quantity = Decimal(holding.quantity) + shares
            holding.cost = Decimal(holding.cost) + amount
            if price > 0:
                holding.price = price
        else:
            holding = models.Holding(
                ledger_id=lid, account_id=plan.account_id, symbol=symbol,
                name=name, type=inst.category if inst else "open_fund",
                quantity=shares, cost=amount, price=price,
            )
            db.add(holding)
        db.flush()

    elif plan.plan_type == "p2p_collect":
        loan = db.get(models.Loan, plan.loan_id) if plan.loan_id else None
        if not loan:
            raise HTTPException(400, "关联网贷不存在")
        principal = Decimal(payload.principal) if payload.principal is not None else (
            Decimal(loan.amount or 0) - Decimal(loan.settled or 0)
        )
        interest = Decimal(payload.interest) if payload.interest is not None else Decimal(loan.per_interest or 0)
        income_account = payload.to_account_id or plan.to_account_id or loan.cash_account_id
        total = principal + interest
        name = loan.item or loan.counterparty or "网贷"
        if income_account and total > 0:
            recv = models.Transaction(
                ledger_id=lid, type="income", amount=total,
                account_id=income_account, occurred_at=occurred,
                remark=remark or f"网贷收回：{name}",
            )
            db.add(recv)
            db.flush()
            _attach_txn_tags(db, recv, tag_ids)
            apply_transaction(db, recv, sign=1)
        if loan.account_id and principal > 0:
            out_txn = models.Transaction(
                ledger_id=lid, type="expense", amount=principal,
                account_id=loan.account_id, occurred_at=occurred,
                remark=f"网贷收回本金：{name}",
            )
            db.add(out_txn)
            db.flush()
            apply_transaction(db, out_txn, sign=1)
        loan.settled = Decimal(loan.settled or 0) + principal
        if loan.collected_periods is not None:
            loan.collected_periods = (loan.collected_periods or 0) + 1
        if Decimal(loan.settled) >= Decimal(loan.amount):
            loan.is_closed = True

    elif plan.plan_type == "loan_repay":
        loan = db.get(models.Loan, plan.loan_id) if plan.loan_id else None
        if not loan:
            raise HTTPException(400, "关联贷款不存在")
        pay_account = payload.account_id or plan.account_id or loan.account_id
        repay = amount if amount > 0 else (Decimal(loan.amount or 0) / Decimal(loan.total_periods or 1))
        repay = repay.quantize(Decimal("0.01"))
        name = loan.item or loan.counterparty or "贷款"
        if pay_account and repay > 0:
            txn = models.Transaction(
                ledger_id=lid, type="expense", amount=repay,
                account_id=pay_account, occurred_at=occurred,
                remark=remark or f"贷款还款：{name}",
            )
            db.add(txn)
            db.flush()
            _attach_txn_tags(db, txn, tag_ids)
            apply_transaction(db, txn, sign=1)
        loan.settled = Decimal(loan.settled or 0) + repay
        if loan.remaining_periods is not None:
            loan.remaining_periods = max((loan.remaining_periods or 0) - 1, 0)
        if Decimal(loan.settled) >= Decimal(loan.amount):
            loan.is_closed = True

    else:
        raise HTTPException(400, "未知的计划类型")

    if payload.keep_open:
        _advance_plan(plan)
    else:
        plan.last_run_at = datetime.now()
        plan.status = "done"
        plan.next_run_date = None

    db.commit()
    db.refresh(plan)
    return _out(plan)
