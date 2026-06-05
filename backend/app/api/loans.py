from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from calendar import monthrange
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db
from app.services.balance import apply_transaction

router = APIRouter(tags=["loans"])


def _round2(v: Decimal) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _add_period(base: datetime, step: int, unit: str) -> datetime:
    if unit == "day":
        from datetime import timedelta
        return base + timedelta(days=step)
    if unit == "year":
        y = base.year + step
        d = min(base.day, monthrange(y, base.month)[1])
        return base.replace(year=y, day=d)
    # default month
    month = base.month - 1 + step
    y = base.year + month // 12
    m = month % 12 + 1
    d = min(base.day, monthrange(y, m)[1])
    return base.replace(year=y, month=m, day=d)


def _period_rate(annual_rate: Decimal, interval: int, interval_unit: str) -> Decimal:
    annual = Decimal(annual_rate or 0) / Decimal("100")
    if interval_unit == "year":
        return annual * Decimal(interval)
    if interval_unit == "day":
        # 近似按 365 天折算
        return annual * Decimal(interval) / Decimal("365")
    # month
    return annual * Decimal(interval) / Decimal("12")


def _sync_loan_account_balance(db: Session, loan: models.Loan) -> None:
    if not loan.account_id:
        return
    acc = db.get(models.Account, loan.account_id)
    if not acc:
        return
    if acc.type != "loan":
        return
    remain = Decimal(loan.amount or 0) - Decimal(loan.settled or 0)
    signed = -remain if loan.direction == "payable" else remain
    acc.current_balance = _round2(signed)


def _ensure_default_rate_adjustment(db: Session, loan: models.Loan) -> None:
    _ensure_rate_adjustment_table(db)
    exists = (
        db.query(models.LoanRateAdjustment)
        .filter(models.LoanRateAdjustment.loan_id == loan.id)
        .first()
    )
    if exists:
        return
    ra = models.LoanRateAdjustment(
        ledger_id=loan.ledger_id,
        loan_id=loan.id,
        occurred_at=loan.occurred_at or datetime.now(),
        interest_rate=Decimal(loan.interest_rate or 0),
        remark="初始利率",
    )
    db.add(ra)


def _ensure_rate_adjustment_table(db: Session) -> None:
    # 对已运行中的账本，兼容补建新表。
    models.LoanRateAdjustment.__table__.create(bind=db.connection(), checkfirst=True)


def _build_schedule(loan: models.Loan, adjustments: list[models.LoanRateAdjustment]) -> schemas.LoanScheduleOut:
    total_periods = int(loan.total_periods or 0)
    if total_periods <= 0 or not loan.first_collect_at:
        return schemas.LoanScheduleOut(
            loan_id=loan.id,
            paid_periods=int(loan.collected_periods or 0),
            total_periods=total_periods,
            paid_principal=Decimal("0"),
            paid_interest=Decimal("0"),
            remaining_principal=Decimal(loan.amount or 0) - Decimal(loan.settled or 0),
            remaining_interest=Decimal("0"),
            items=[],
        )

    interval = int(loan.collect_interval or 1)
    unit = loan.collect_interval_unit or "month"
    paid_periods = max(int(loan.collected_periods or 0), 0)
    principal_left = Decimal(loan.amount or 0)
    items: list[schemas.LoanScheduleItem] = []
    paid_principal = Decimal("0")
    paid_interest = Decimal("0")

    sorted_adj = sorted(adjustments, key=lambda x: x.occurred_at)
    if not sorted_adj:
        sorted_adj = [
            models.LoanRateAdjustment(
                loan_id=loan.id,
                ledger_id=loan.ledger_id,
                occurred_at=loan.occurred_at or datetime.now(),
                interest_rate=Decimal(loan.interest_rate or 0),
            )
        ]

    def rate_for_date(due_at: datetime) -> Decimal:
        current = Decimal(sorted_adj[0].interest_rate or 0)
        for row in sorted_adj:
            if row.occurred_at <= due_at:
                current = Decimal(row.interest_rate or 0)
            else:
                break
        return current

    for i in range(1, total_periods + 1):
        due_at = _add_period(loan.first_collect_at, (i - 1) * interval, unit)
        annual_rate = rate_for_date(due_at)
        r = _period_rate(annual_rate, interval, unit)
        remain_n = total_periods - i + 1

        if loan.repay_method == "等额本金":
            principal = _round2(principal_left / Decimal(remain_n)) if remain_n > 1 else _round2(principal_left)
            interest = _round2(principal_left * r)
            payment = _round2(principal + interest)
        elif loan.repay_method == "分期付息一次还本":
            principal = _round2(principal_left) if i == total_periods else Decimal("0")
            interest = _round2(principal_left * r)
            payment = _round2(principal + interest)
        else:
            # 默认按等额本息
            if r == 0:
                payment = _round2(principal_left / Decimal(remain_n))
            else:
                factor = (Decimal("1") + r) ** remain_n
                payment = _round2(principal_left * r * factor / (factor - Decimal("1")))
            interest = _round2(principal_left * r)
            principal = _round2(payment - interest)
            if i == total_periods:
                principal = _round2(principal_left)
                payment = _round2(principal + interest)

        principal_left = _round2(principal_left - principal)
        is_paid = i <= paid_periods
        if is_paid:
            paid_principal += principal
            paid_interest += interest

        items.append(
            schemas.LoanScheduleItem(
                period_no=i,
                due_at=due_at,
                annual_rate=_round2(annual_rate),
                payment=payment,
                principal=principal,
                interest=interest,
                balance=max(principal_left, Decimal("0")),
                is_paid=is_paid,
            )
        )

    remaining_interest = sum((x.interest for x in items if not x.is_paid), Decimal("0"))
    return schemas.LoanScheduleOut(
        loan_id=loan.id,
        paid_periods=paid_periods,
        total_periods=total_periods,
        paid_principal=_round2(paid_principal),
        paid_interest=_round2(paid_interest),
        remaining_principal=_round2(max(Decimal(loan.amount or 0) - Decimal(loan.settled or 0), Decimal("0"))),
        remaining_interest=_round2(remaining_interest),
        items=items,
    )


def _attach_tags_txn(db: Session, txn: models.Transaction, tag_ids: list[int]) -> None:
    if tag_ids:
        txn.tags = db.query(models.Tag).filter(models.Tag.id.in_(tag_ids)).all()


def _to_out(loan: models.Loan) -> schemas.LoanOut:
    out = schemas.LoanOut.model_validate(loan)
    out.remaining = Decimal(loan.amount) - Decimal(loan.settled)
    out.tag_ids = [t.id for t in loan.tags]
    return out


def _attach_tags(db: Session, loan: models.Loan, tag_ids: list[int]) -> None:
    if tag_ids:
        loan.tags = db.query(models.Tag).filter(models.Tag.id.in_(tag_ids)).all()
    else:
        loan.tags = []


def _reverse_loan_lend(db: Session, loan: models.Loan) -> None:
    """回滚一笔网贷借出项目：删除其出借流水（回滚余额）并删除项目本身。"""
    lend_txns = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.ledger_id == loan.ledger_id,
            models.Transaction.loan_id == loan.id,
        )
        .all()
    )
    for t in lend_txns:
        apply_transaction(db, t, sign=-1)
        db.delete(t)
    # 删除利率调整记录
    _ensure_rate_adjustment_table(db)
    db.query(models.LoanRateAdjustment).filter(
        models.LoanRateAdjustment.loan_id == loan.id
    ).delete(synchronize_session=False)
    db.delete(loan)
    db.flush()


def _sync_loan_funding_txn(db: Session, loan: models.Loan, tag_ids=None) -> None:
    """同步普通借贷的资金流水：所选账户为真实资金账户时，
    借入记一笔 income（资金入账）、借出记一笔 expense（资金出账）。
    可重复调用：会先回滚旧流水再按当前账户/金额/方向重建，
    用于编辑时同步「收款账户」「金额」「方向」等变更。"""
    if loan.loan_kind == "p2p":
        return
    # 找出本项目已有的资金流水（普通借贷只会有一条）
    existing = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.ledger_id == loan.ledger_id,
            models.Transaction.loan_id == loan.id,
        )
        .all()
    )
    keep_tags: list[int] = list(tag_ids) if tag_ids is not None else []
    for t in existing:
        if tag_ids is None and t.tags:
            keep_tags = [tg.id for tg in t.tags]
        apply_transaction(db, t, sign=-1)
        db.delete(t)
    db.flush()

    fund_acc = db.get(models.Account, loan.account_id) if loan.account_id else None
    if fund_acc is None or fund_acc.type == "loan":
        return
    amount = Decimal(loan.amount or 0)
    if amount <= 0:
        return
    occurred = loan.occurred_at or datetime.now()
    name = loan.item or loan.counterparty or ("借入" if loan.direction == "payable" else "借出")
    if loan.direction == "payable":
        txn = models.Transaction(
            ledger_id=loan.ledger_id, type="income", amount=amount,
            account_id=fund_acc.id, occurred_at=occurred,
            remark=f"借入：{name}", loan_id=loan.id,
        )
    else:
        txn = models.Transaction(
            ledger_id=loan.ledger_id, type="expense", amount=amount,
            account_id=fund_acc.id, occurred_at=occurred,
            remark=f"借出：{name}", loan_id=loan.id,
        )
    db.add(txn)
    db.flush()
    _attach_tags_txn(db, txn, keep_tags)
    apply_transaction(db, txn, sign=1)


def _reverse_collect_group(db: Session, ledger_id: int, group: str) -> None:
    """回滚一次网贷收回（本金+利息）：还原项目待收/已收期数并删除流水。"""
    rows = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.ledger_id == ledger_id,
            models.Transaction.collect_group == group,
        )
        .all()
    )
    if not rows:
        return
    loan_id = rows[0].loan_id
    principal_back = Decimal("0")
    for t in rows:
        if (t.remark or "").startswith("网贷收回本金"):
            principal_back += Decimal(t.amount or 0)
        apply_transaction(db, t, sign=-1)
        db.delete(t)
    if loan_id:
        loan = db.get(models.Loan, loan_id)
        if loan:
            loan.settled = max(Decimal(loan.settled or 0) - principal_back, Decimal("0"))
            if loan.collected_periods:
                loan.collected_periods = max((loan.collected_periods or 0) - 1, 0)
            loan.is_closed = Decimal(loan.settled) >= Decimal(loan.amount or 0)
            _sync_loan_account_balance(db, loan)
    db.flush()


@router.get("/ledgers/{ledger_id}/loans", response_model=list[schemas.LoanOut])
def list_loans(ledger_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(models.Loan)
        .filter(models.Loan.ledger_id == ledger_id)
        .order_by(models.Loan.is_closed, models.Loan.id.desc())
        .all()
    )
    return [_to_out(loan) for loan in rows]


@router.post("/ledgers/{ledger_id}/loans", response_model=schemas.LoanOut)
def create_loan(ledger_id: int, payload: schemas.LoanCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    tag_ids = data.pop("tag_ids", [])
    edit_loan_id = data.pop("edit_loan_id", None)
    if data.get("occurred_at") is None:
        data.pop("occurred_at", None)
    # 编辑模式：先回滚并删除原网贷项目（含出借流水）
    if edit_loan_id:
        old = db.get(models.Loan, edit_loan_id)
        if old:
            _reverse_loan_lend(db, old)
    # 借入分期可自动创建“应付款”账户
    if (
        data.get("direction") == "payable"
        and data.get("repay_method") in {"等额本息", "等额本金", "分期付息一次还本"}
        and not data.get("account_id")
    ):
        nm = data.get("item") or data.get("counterparty") or "借入"
        acc = models.Account(
            ledger_id=ledger_id,
            name=str(nm),
            type="loan",
            icon="📉",
            currency=data.get("currency") or "CNY",
            initial_balance=Decimal("0"),
            current_balance=Decimal("0"),
            owner=data.get("counterparty"),
            remark="自动创建：借入应付款账户",
        )
        db.add(acc)
        db.flush()
        data["account_id"] = acc.id
    # 借出（普通债权）可自动创建“应收款”账户
    elif (
        data.get("direction") == "receivable"
        and data.get("loan_kind") != "p2p"
        and not data.get("account_id")
    ):
        nm = data.get("item") or data.get("counterparty") or "借出"
        acc = models.Account(
            ledger_id=ledger_id,
            name=str(nm),
            type="loan",
            icon="📈",
            currency=data.get("currency") or "CNY",
            initial_balance=Decimal("0"),
            current_balance=Decimal("0"),
            owner=data.get("counterparty"),
            remark="自动创建：借出应收款账户",
        )
        db.add(acc)
        db.flush()
        data["account_id"] = acc.id

    loan = models.Loan(ledger_id=ledger_id, **data)
    _attach_tags(db, loan, tag_ids)
    db.add(loan)
    db.flush()
    _ensure_rate_adjustment_table(db)
    _ensure_default_rate_adjustment(db, loan)
    _sync_loan_account_balance(db, loan)

    # 网贷借出：从网贷账户的可用现金支出本金，债权（应收）单独计为资产
    if loan.loan_kind == "p2p":
        amount = Decimal(loan.amount or 0)
        occurred = loan.occurred_at or datetime.now()
        name = loan.item or loan.counterparty or "网贷"
        # 出借资金来源：优先使用网贷账户自身现金，其次使用指定资金账户
        source_id = loan.account_id or loan.cash_account_id
        if amount > 0 and source_id:
            pay = models.Transaction(
                ledger_id=ledger_id, type="expense", amount=amount,
                account_id=source_id, occurred_at=occurred,
                remark=f"网贷借出：{name}", loan_id=loan.id,
            )
            db.add(pay)
            db.flush()
            _attach_tags_txn(db, pay, tag_ids)
            apply_transaction(db, pay, sign=1)
    else:
        # 普通借入/借出：若所选账户为真实资金账户（非应收/应付 loan 账户），
        # 生成一条资金流水——借入则资金入账（income），借出则资金出账（expense）。
        _sync_loan_funding_txn(db, loan, tag_ids)

    db.commit()
    db.refresh(loan)
    return _to_out(loan)


@router.put("/loans/{loan_id}", response_model=schemas.LoanOut)
def update_loan(loan_id: int, payload: schemas.LoanUpdate, db: Session = Depends(get_db)):
    loan = db.get(models.Loan, loan_id)
    if not loan:
        raise HTTPException(404, "记录不存在")
    data = payload.model_dump(exclude_unset=True)
    tag_ids = data.pop("tag_ids", None)
    for k, v in data.items():
        setattr(loan, k, v)
    if tag_ids is not None:
        _attach_tags(db, loan, tag_ids)
    if Decimal(loan.settled) >= Decimal(loan.amount):
        loan.is_closed = True
    _sync_loan_account_balance(db, loan)
    # 同步资金流水：收款账户/金额/方向变更时，重建对应的入账/出账记录
    _sync_loan_funding_txn(db, loan, tag_ids)
    db.commit()
    db.refresh(loan)
    return _to_out(loan)


@router.post("/loans/{loan_id}/collect", response_model=schemas.LoanOut)
def collect_loan(loan_id: int, payload: schemas.LoanCollect, db: Session = Depends(get_db)):
    """网贷收回：本金与利息回款进入资金账户，债权（应收）按本金减少，利息计为收益。"""
    loan = db.get(models.Loan, loan_id)
    if not loan:
        raise HTTPException(404, "记录不存在")
    # 编辑模式：先回滚原收回流水与项目状态
    if payload.edit_group:
        _reverse_collect_group(db, loan.ledger_id, payload.edit_group)
        db.refresh(loan)
    principal = Decimal(payload.principal or 0)
    interest = Decimal(payload.interest or 0)
    total = principal + interest
    if total <= 0:
        raise HTTPException(400, "本息合计必须大于 0")
    occurred = payload.occurred_at or datetime.now()
    name = loan.item or loan.counterparty or "网贷"
    group = uuid4().hex[:24]

    # 回款进入资金账户（默认回到网贷账户的可用现金）：本金与利息分别入账，便于明细拆分
    target_id = payload.income_account_id or loan.account_id
    if target_id and principal > 0:
        recv_p = models.Transaction(
            ledger_id=loan.ledger_id, type="income", amount=principal,
            account_id=target_id, occurred_at=occurred,
            remark=f"网贷收回本金：{name}", loan_id=loan.id, collect_group=group,
        )
        db.add(recv_p)
        db.flush()
        _attach_tags_txn(db, recv_p, payload.tag_ids)
        apply_transaction(db, recv_p, sign=1)
    if target_id and interest > 0:
        recv_i = models.Transaction(
            ledger_id=loan.ledger_id, type="income", amount=interest,
            account_id=target_id, occurred_at=occurred,
            remark=payload.remark or f"网贷收回利息：{name}", loan_id=loan.id, collect_group=group,
        )
        db.add(recv_i)
        db.flush()
        _attach_tags_txn(db, recv_i, payload.tag_ids)
        apply_transaction(db, recv_i, sign=1)

    loan.settled = Decimal(loan.settled or 0) + principal
    if loan.collected_periods is not None:
        loan.collected_periods = (loan.collected_periods or 0) + 1
    if Decimal(loan.settled) >= Decimal(loan.amount):
        loan.is_closed = True
    _sync_loan_account_balance(db, loan)
    db.commit()
    db.refresh(loan)
    return _to_out(loan)


@router.delete("/loans/{loan_id}")
def delete_loan(loan_id: int, db: Session = Depends(get_db)):
    loan = db.get(models.Loan, loan_id)
    if not loan:
        raise HTTPException(404, "记录不存在")
    # 回滚并删除：连带回滚资金流水（借入入账/借出出账、网贷出借等）
    _reverse_loan_lend(db, loan)
    db.commit()
    return {"detail": "已删除"}


@router.get("/loans/{loan_id}/rate-adjustments", response_model=list[schemas.LoanRateAdjustmentOut])
def list_loan_rate_adjustments(loan_id: int, db: Session = Depends(get_db)):
    loan = db.get(models.Loan, loan_id)
    if not loan:
        raise HTTPException(404, "记录不存在")
    _ensure_rate_adjustment_table(db)
    rows = (
        db.query(models.LoanRateAdjustment)
        .filter(models.LoanRateAdjustment.loan_id == loan_id)
        .order_by(models.LoanRateAdjustment.occurred_at.asc(), models.LoanRateAdjustment.id.asc())
        .all()
    )
    return rows


@router.post("/loans/{loan_id}/rate-adjustments", response_model=schemas.LoanRateAdjustmentOut)
def create_loan_rate_adjustment(
    loan_id: int,
    payload: schemas.LoanRateAdjustmentCreate,
    db: Session = Depends(get_db),
):
    loan = db.get(models.Loan, loan_id)
    if not loan:
        raise HTTPException(404, "记录不存在")
    _ensure_rate_adjustment_table(db)
    row = models.LoanRateAdjustment(
        ledger_id=loan.ledger_id,
        loan_id=loan.id,
        occurred_at=payload.occurred_at or datetime.now(),
        interest_rate=payload.interest_rate,
        remark=payload.remark,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/loan-rate-adjustments/{adjustment_id}", response_model=schemas.LoanRateAdjustmentOut)
def update_loan_rate_adjustment(
    adjustment_id: int,
    payload: schemas.LoanRateAdjustmentUpdate,
    db: Session = Depends(get_db),
):
    _ensure_rate_adjustment_table(db)
    row = db.get(models.LoanRateAdjustment, adjustment_id)
    if not row:
        raise HTTPException(404, "记录不存在")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/loan-rate-adjustments/{adjustment_id}")
def delete_loan_rate_adjustment(adjustment_id: int, db: Session = Depends(get_db)):
    _ensure_rate_adjustment_table(db)
    row = db.get(models.LoanRateAdjustment, adjustment_id)
    if not row:
        raise HTTPException(404, "记录不存在")
    db.delete(row)
    db.commit()
    return {"detail": "已删除"}


@router.get("/loans/{loan_id}/schedule", response_model=schemas.LoanScheduleOut)
def get_loan_schedule(loan_id: int, db: Session = Depends(get_db)):
    loan = db.get(models.Loan, loan_id)
    if not loan:
        raise HTTPException(404, "记录不存在")
    _ensure_rate_adjustment_table(db)
    adjustments = (
        db.query(models.LoanRateAdjustment)
        .filter(models.LoanRateAdjustment.loan_id == loan_id)
        .order_by(models.LoanRateAdjustment.occurred_at.asc(), models.LoanRateAdjustment.id.asc())
        .all()
    )
    return _build_schedule(loan, adjustments)
