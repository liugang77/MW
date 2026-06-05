from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db
from app.services.balance import recompute_account, apply_transaction

router = APIRouter(tags=["accounts"])


# ---------- 账户组 ----------
@router.get("/ledgers/{ledger_id}/account-groups", response_model=list[schemas.AccountGroupOut])
def list_account_groups(ledger_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.AccountGroup)
        .filter(models.AccountGroup.ledger_id == ledger_id)
        .order_by(models.AccountGroup.sort_order, models.AccountGroup.id)
        .all()
    )


@router.post("/ledgers/{ledger_id}/account-groups", response_model=schemas.AccountGroupOut)
def create_account_group(ledger_id: int, payload: schemas.AccountGroupCreate, db: Session = Depends(get_db)):
    group = models.AccountGroup(ledger_id=ledger_id, **payload.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.delete("/account-groups/{group_id}")
def delete_account_group(group_id: int, db: Session = Depends(get_db)):
    group = db.get(models.AccountGroup, group_id)
    if not group:
        raise HTTPException(404, "账户组不存在")
    db.query(models.Account).filter(models.Account.group_id == group_id).update({"group_id": None})
    db.delete(group)
    db.commit()
    return {"detail": "已删除"}


# ---------- 人员与机构 ----------
@router.get("/ledgers/{ledger_id}/parties", response_model=list[schemas.PartyOut])
def list_parties(ledger_id: int, type: str | None = None, db: Session = Depends(get_db)):
    q = db.query(models.Party).filter(models.Party.ledger_id == ledger_id)
    if type:
        q = q.filter(models.Party.type == type)
    return q.order_by(models.Party.id).all()


@router.post("/ledgers/{ledger_id}/parties", response_model=schemas.PartyOut)
def create_party(ledger_id: int, payload: schemas.PartyCreate, db: Session = Depends(get_db)):
    party = models.Party(ledger_id=ledger_id, **payload.model_dump())
    db.add(party)
    db.commit()
    db.refresh(party)
    return party


@router.put("/parties/{party_id}", response_model=schemas.PartyOut)
def update_party(party_id: int, payload: schemas.PartyUpdate, db: Session = Depends(get_db)):
    party = db.get(models.Party, party_id)
    if not party:
        raise HTTPException(404, "记录不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(party, field, value)
    db.commit()
    db.refresh(party)
    return party


@router.delete("/parties/{party_id}")
def delete_party(party_id: int, db: Session = Depends(get_db)):
    party = db.get(models.Party, party_id)
    if not party:
        raise HTTPException(404, "记录不存在")
    db.delete(party)
    db.commit()
    return {"detail": "已删除"}


@router.get("/ledgers/{ledger_id}/accounts", response_model=list[schemas.AccountOut])
def list_accounts(ledger_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.Account)
        .filter(models.Account.ledger_id == ledger_id)
        .order_by(models.Account.sort_order, models.Account.id)
        .all()
    )


@router.post("/ledgers/{ledger_id}/accounts", response_model=schemas.AccountOut)
def create_account(ledger_id: int, payload: schemas.AccountCreate, db: Session = Depends(get_db)):
    from decimal import Decimal
    from datetime import datetime

    data = payload.model_dump()
    # 账户名称：必填且同账本内不可重复
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "请输入账户名称")
    data["name"] = name
    dup = (
        db.query(models.Account)
        .filter(models.Account.ledger_id == ledger_id, models.Account.name == name)
        .first()
    )
    if dup:
        raise HTTPException(400, f"账户名称「{name}」已存在")
    # 账户余额一律由交易明细累计而来：开户的初始余额以一笔「期初余额」调整交易体现，
    # 账户本身始终从 0 起算，保证“余额=交易明细累计”。
    opening = Decimal(str(data.get("initial_balance") or 0))
    data["initial_balance"] = Decimal("0")
    data["current_balance"] = Decimal("0")
    account = models.Account(ledger_id=ledger_id, **data)
    db.add(account)
    db.flush()
    if opening != 0:
        txn = models.Transaction(
            ledger_id=ledger_id,
            type="adjust",
            amount=opening,
            account_id=account.id,
            remark="期初余额",
        )
        start_date = data.get("start_date")
        if start_date:
            try:
                txn.occurred_at = datetime.fromisoformat(str(start_date))
            except ValueError:
                pass
        db.add(txn)
        db.flush()
        apply_transaction(db, txn, sign=1)
    db.commit()
    db.refresh(account)
    return account


@router.put("/accounts/{account_id}", response_model=schemas.AccountOut)
def update_account(account_id: int, payload: schemas.AccountUpdate, db: Session = Depends(get_db)):
    account = db.get(models.Account, account_id)
    if not account:
        raise HTTPException(404, "账户不存在")
    data = payload.model_dump(exclude_unset=True)
    # 改名校验：必填且同账本内不可与其它账户重名
    if "name" in data:
        new_name = (data.get("name") or "").strip()
        if not new_name:
            raise HTTPException(400, "请输入账户名称")
        data["name"] = new_name
        dup = (
            db.query(models.Account)
            .filter(
                models.Account.ledger_id == account.ledger_id,
                models.Account.name == new_name,
                models.Account.id != account_id,
            )
            .first()
        )
        if dup:
            raise HTTPException(400, f"账户名称「{new_name}」已存在")
    for k, v in data.items():
        setattr(account, k, v)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(models.Account, account_id)
    if not account:
        raise HTTPException(404, "账户不存在")
    has_txn = db.query(models.Transaction).filter(
        (models.Transaction.account_id == account_id)
        | (models.Transaction.to_account_id == account_id)
    ).first()
    if has_txn:
        account.is_active = False
        db.commit()
        return {"detail": "账户存在流水，已停用"}
    db.delete(account)
    db.commit()
    return {"detail": "已删除"}


@router.get("/accounts/{account_id}/insurance-detail", response_model=schemas.InsuranceDetailOut)
def insurance_detail(account_id: int, db: Session = Depends(get_db)):
    """保险账户明细：按缴费/领取分类每笔流水并汇总（后台计算）。"""
    from decimal import Decimal

    account = db.get(models.Account, account_id)
    if not account:
        raise HTTPException(404, "账户不存在")

    txns = (
        db.query(models.Transaction)
        .filter(
            (models.Transaction.account_id == account_id)
            | (models.Transaction.to_account_id == account_id)
        )
        .order_by(models.Transaction.occurred_at.desc(), models.Transaction.id.desc())
        .all()
    )

    rows: list[schemas.InsuranceTxnRow] = []
    premium_total = Decimal("0")
    collect_total = Decimal("0")

    # 对方账户名称缓存（转账类记账时在活动类型后附上「|对方账户」）
    _acc_name_cache: dict[int, str] = {}

    def _counter_name(t: models.Transaction) -> str:
        counter_id = t.to_account_id if t.account_id == account_id else t.account_id
        if not counter_id or counter_id == account_id:
            return ""
        if counter_id not in _acc_name_cache:
            ca = db.get(models.Account, counter_id)
            _acc_name_cache[counter_id] = ca.name if ca else ""
        return _acc_name_cache[counter_id]

    for t in txns:
        amount = Decimal(t.amount)
        premium = Decimal("0")
        collect = Decimal("0")
        # 已标记的保险活动类型优先（缴纳保费/保费返还/退保/保险分红）
        act = getattr(t, "insurance_activity", None)
        if act:
            activity = act
            if act == "缴纳保费":
                premium = amount
            else:
                # 保费返还 / 退保 / 保险分红：均为领取方向
                collect = amount
            if t.type == "transfer":
                counter = _counter_name(t)
                if counter:
                    activity = f"{act}|{counter}"
        elif t.type == "transfer":
            if t.to_account_id == account_id:
                activity = "缴纳保费"
                premium = amount
            else:
                activity = "领取/支取"
                collect = amount
        elif t.type == "income":
            activity = "领取"
            collect = amount
        elif t.type == "expense":
            activity = "缴纳保费"
            premium = amount
        else:  # adjust
            activity = "余额调整"
            if amount > 0:
                premium = amount
            elif amount < 0:
                collect = -amount
        premium_total += premium
        collect_total += collect
        rows.append(
            schemas.InsuranceTxnRow(
                id=t.id,
                occurred_at=t.occurred_at,
                type=t.type,
                premium=premium,
                collect=collect,
                activity=activity,
                remark=t.remark,
            )
        )

    return schemas.InsuranceDetailOut(
        account_id=account_id,
        cash_value=Decimal(account.current_balance),
        premium_total=premium_total,
        collect_total=collect_total,
        count=len(rows),
        rows=rows,
    )


@router.post("/accounts/{account_id}/recompute", response_model=schemas.AccountOut)
def recompute(account_id: int, db: Session = Depends(get_db)):
    account = db.get(models.Account, account_id)
    if not account:
        raise HTTPException(404, "账户不存在")
    recompute_account(db, account_id)
    db.commit()
    db.refresh(account)
    return account


@router.post("/accounts/{account_id}/status", response_model=schemas.AccountOut)
def set_account_status(account_id: int, status: str, db: Session = Depends(get_db)):
    """设置账户状态：active(正常) / hidden(隐藏) / closed(注销)。"""
    if status not in ("active", "hidden", "closed"):
        raise HTTPException(400, "无效的状态")
    account = db.get(models.Account, account_id)
    if not account:
        raise HTTPException(404, "账户不存在")
    account.status = status
    account.is_active = status != "closed"
    db.commit()
    db.refresh(account)
    return account


@router.post("/accounts/{account_id}/adjust", response_model=schemas.AccountOut)
def adjust_balance(account_id: int, payload: schemas.BalanceAdjust, db: Session = Depends(get_db)):
    """余额调整：将账户余额校准到目标值，差额记一笔流水。

    mode=adjust         差额记为「余额调整」，不计入日常收支（type=adjust）。
    mode=income_expense 差额记为「对账收入/支出」，计入日常收支（type=income/expense）。
    """
    from decimal import Decimal

    account = db.get(models.Account, account_id)
    if not account:
        raise HTTPException(404, "账户不存在")
    target = Decimal(payload.target_balance)
    diff = target - Decimal(account.current_balance)
    if diff != 0:
        if payload.mode == "income_expense":
            txn = models.Transaction(
                ledger_id=account.ledger_id,
                type="income" if diff > 0 else "expense",
                amount=abs(diff),
                account_id=account_id,
                remark="对账" + ("收入" if diff > 0 else "支出"),
            )
        else:
            txn = models.Transaction(
                ledger_id=account.ledger_id,
                type="adjust",
                amount=diff,
                account_id=account_id,
                remark="余额调整",
            )
        db.add(txn)
        db.flush()
        apply_transaction(db, txn, sign=1)
    db.commit()
    db.refresh(account)
    return account


@router.post("/ledgers/{ledger_id}/major-assets/buy", response_model=schemas.AccountOut)
def buy_major_asset(ledger_id: int, payload: schemas.MajorAssetBuy, db: Session = Depends(get_db)):
    """重大资产买入：创建重大资产账户，并按「支付账户 + 所选贷款」记录出资。

    - 资产成本（initial_balance）= 总额；资产市值（current_balance）由出资流水累计得到；
    - 首付部分：从支付账户转入资产（transfer），扣减支付账户；
    - 贷款部分：按每笔所选贷款在资产上记一笔入账（income，挂 loan_id 不计入收支统计），
      贷款负债本身由贷款记录单独维护。
    """
    from decimal import Decimal
    from datetime import datetime

    total = Decimal(str(payload.total or 0))
    if total <= 0:
        raise HTTPException(400, "请输入资产总额")

    occurred = None
    if payload.occurred_at:
        try:
            occurred = datetime.fromisoformat(str(payload.occurred_at))
        except ValueError:
            occurred = None
    occurred = occurred or datetime.now()

    loans: list[models.Loan] = []
    if payload.loan_ids:
        loans = (
            db.query(models.Loan)
            .filter(models.Loan.ledger_id == ledger_id, models.Loan.id.in_(payload.loan_ids))
            .all()
        )
    loan_total = sum((Decimal(l.amount or 0) for l in loans), Decimal("0"))
    down_payment = total - loan_total
    if down_payment < 0:
        down_payment = Decimal("0")

    asset = models.Account(
        ledger_id=ledger_id,
        name=payload.name,
        type="major_asset",
        icon="🏠",
        currency=payload.currency or "CNY",
        owner=payload.owner,
        asset_nature=payload.asset_nature or "invest",
        initial_balance=total,
        current_balance=Decimal("0"),
        remark=payload.remark,
    )
    db.add(asset)
    db.flush()

    def _tags(txn: models.Transaction) -> None:
        if payload.tag_ids:
            txn.tags = db.query(models.Tag).filter(models.Tag.id.in_(payload.tag_ids)).all()

    # 首付出资
    if down_payment > 0:
        if payload.payment_account_id:
            txn = models.Transaction(
                ledger_id=ledger_id, type="transfer", amount=down_payment,
                account_id=payload.payment_account_id, to_account_id=asset.id,
                occurred_at=occurred, remark="重大资产买入",
            )
        else:
            txn = models.Transaction(
                ledger_id=ledger_id, type="adjust", amount=down_payment,
                account_id=asset.id, occurred_at=occurred, remark="重大资产买入",
            )
        db.add(txn)
        db.flush()
        _tags(txn)
        apply_transaction(db, txn, sign=1)

    # 贷款出资
    for l in loans:
        amt = Decimal(l.amount or 0)
        if amt <= 0:
            continue
        txn = models.Transaction(
            ledger_id=ledger_id, type="income", amount=amt,
            account_id=asset.id, occurred_at=occurred,
            remark="重大资产买入（贷款）", loan_id=l.id,
        )
        db.add(txn)
        db.flush()
        apply_transaction(db, txn, sign=1)
        if not l.item:
            l.item = payload.name

    db.commit()
    db.refresh(asset)
    return asset

