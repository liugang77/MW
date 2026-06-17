from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db
from app.services.balance import apply_transaction

router = APIRouter(tags=["vouchers"])


def _round2(v: Decimal) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _attach_tags(db: Session, txn: models.Transaction, tag_ids: list[int] | None) -> None:
    if tag_ids:
        txn.tags = db.query(models.Tag).filter(models.Tag.id.in_(tag_ids)).all()


def _voucher_out(v: models.Voucher) -> schemas.VoucherOut:
    out = schemas.VoucherOut.model_validate(v)
    remaining = (v.quantity or 0) - (v.redeemed or 0)
    if v.status == "refunded":
        remaining = 0
    out.remaining = max(remaining, 0)
    out.occupied_value = _round2(Decimal(v.unit_price or 0) * out.remaining)
    out.discount = _round2(
        (Decimal(v.face_value or 0) - Decimal(v.unit_price or 0)) * (v.quantity or 0)
    )
    out.is_expired = bool(
        v.expiry_at and v.status == "active" and v.expiry_at < datetime.now()
    )
    return out


def _is_buy_txn(txn: models.Transaction, voucher: models.Voucher) -> bool:
    """购券流水：资金账户转入团购券账户，或无资金来源时的正向余额调整。"""
    if txn.type == "transfer" and txn.to_account_id == voucher.account_id:
        return True
    if txn.type == "adjust" and Decimal(txn.amount or 0) >= 0:
        return True
    return False


def _is_refund_txn(txn: models.Transaction, voucher: models.Voucher) -> bool:
    """退券流水：团购券账户转出至原资金账户，或无退款目标时的负向余额调整。"""
    if txn.type == "transfer" and txn.account_id == voucher.account_id:
        return True
    if txn.type == "adjust" and Decimal(txn.amount or 0) < 0:
        return True
    return False


def _reverse_voucher_all(db: Session, voucher: models.Voucher) -> None:
    """整券回滚：删除该券的全部流水（回滚余额）并删除券本身。"""
    txns = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.ledger_id == voucher.ledger_id,
            models.Transaction.voucher_id == voucher.id,
        )
        .all()
    )
    for t in txns:
        apply_transaction(db, t, sign=-1)
        db.delete(t)
    db.delete(voucher)
    db.flush()


def _reverse_voucher_txn(db: Session, txn: models.Transaction) -> None:
    """删除一笔团购券流水时按其性质回滚券状态。

    - 购券流水 → 整券回滚（删除该券及其全部流水）。
    - 退券流水 → 删除该笔并将券状态恢复为 active。
    - 核销流水 → 删除整组（券价 + 可选补差价），已核销张数回退，状态恢复。
    """
    voucher = db.get(models.Voucher, txn.voucher_id)
    if voucher and _is_buy_txn(txn, voucher):
        _reverse_voucher_all(db, voucher)
        return
    if voucher and _is_refund_txn(txn, voucher):
        apply_transaction(db, txn, sign=-1)
        db.delete(txn)
        voucher.status = "active"
        db.flush()
        return
    # 核销流水：同组（券价 + 补差价）一并回滚
    rows = [txn]
    if txn.split_group:
        rows = (
            db.query(models.Transaction)
            .filter(
                models.Transaction.ledger_id == txn.ledger_id,
                models.Transaction.split_group == txn.split_group,
            )
            .all()
        )
    qty_back = 0
    for r in rows:
        if r.voucher_id and r.trade_qty:
            qty_back = int(r.trade_qty)
            break
    if qty_back == 0:
        qty_back = int(txn.trade_qty or 0)
    for r in rows:
        apply_transaction(db, r, sign=-1)
        db.delete(r)
    if voucher:
        voucher.redeemed = max((voucher.redeemed or 0) - qty_back, 0)
        if voucher.status == "used" and voucher.redeemed < (voucher.quantity or 0):
            voucher.status = "active"
    db.flush()


@router.get("/ledgers/{ledger_id}/vouchers", response_model=list[schemas.VoucherOut])
def list_vouchers(ledger_id: int, account_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(models.Voucher).filter(models.Voucher.ledger_id == ledger_id)
    if account_id:
        q = q.filter(models.Voucher.account_id == account_id)
    rows = q.order_by(models.Voucher.status, models.Voucher.id.desc()).all()
    return [_voucher_out(v) for v in rows]


@router.post("/ledgers/{ledger_id}/vouchers/buy", response_model=schemas.VoucherOut)
def voucher_buy(ledger_id: int, payload: schemas.VoucherBuy, db: Session = Depends(get_db)):
    """购券：买入团购券（预付资产），从资金账户转入团购券账户，不计入收支。"""
    if payload.quantity <= 0:
        raise HTTPException(400, "购买张数必须大于 0")
    if payload.unit_price < 0:
        raise HTTPException(400, "实付单价不能为负")

    # 编辑模式：先回滚并删除原购券（整券及其全部流水）
    if payload.edit_txn_id:
        old = db.get(models.Transaction, payload.edit_txn_id)
        if old and old.voucher_id:
            _reverse_voucher_txn(db, old)
            db.flush()

    occurred = payload.purchased_at or datetime.now()
    face = payload.face_value if payload.face_value is not None else payload.unit_price
    voucher = models.Voucher(
        ledger_id=ledger_id,
        account_id=payload.account_id,
        product=payload.product,
        quantity=payload.quantity,
        redeemed=0,
        unit_price=Decimal(payload.unit_price),
        face_value=Decimal(face),
        source_account_id=payload.source_account_id,
        purchased_at=occurred,
        expiry_at=payload.expiry_at,
        category_id=payload.category_id,
        status="active",
        remark=payload.remark,
    )
    db.add(voucher)
    db.flush()

    total = _round2(Decimal(payload.unit_price) * payload.quantity)
    note = payload.remark or f"购券：{payload.product} {payload.quantity}张"
    if payload.source_account_id and total > 0:
        txn = models.Transaction(
            ledger_id=ledger_id, type="transfer", amount=total,
            account_id=payload.source_account_id, to_account_id=payload.account_id,
            occurred_at=occurred, remark=note, voucher_id=voucher.id,
            category_id=payload.category_id,
        )
    else:
        # 无资金来源：直接给团购券账户做一笔正向余额调整（视为已持有的券）
        txn = models.Transaction(
            ledger_id=ledger_id, type="adjust", amount=total,
            account_id=payload.account_id, occurred_at=occurred,
            remark=note, voucher_id=voucher.id,
        )
    db.add(txn)
    db.flush()
    _attach_tags(db, txn, payload.tag_ids)
    apply_transaction(db, txn, sign=1)

    db.commit()
    db.refresh(voucher)
    return _voucher_out(voucher)


@router.post("/ledgers/{ledger_id}/vouchers/{voucher_id}/redeem", response_model=schemas.VoucherOut)
def voucher_redeem(
    ledger_id: int, voucher_id: int, payload: schemas.VoucherRedeem,
    db: Session = Depends(get_db),
):
    """核销：消费若干张券（按实付价确认支出），可选补差价从资金账户支出。"""
    voucher = db.get(models.Voucher, voucher_id)
    if not voucher:
        raise HTTPException(404, "团购券不存在")
    # 编辑模式：先回滚原核销（恢复已核销张数与状态）
    if payload.edit_txn_id:
        old = db.get(models.Transaction, payload.edit_txn_id)
        if old and old.voucher_id == voucher.id:
            _reverse_voucher_txn(db, old)
            db.flush()
    if voucher.status == "refunded":
        raise HTTPException(400, "该券已退货，无法核销")
    # 仅对新增核销检查过期；编辑已有核销记录不受过期限制
    if (payload.edit_txn_id is None and voucher.expiry_at
            and voucher.status == "active" and voucher.expiry_at < datetime.now()):
        raise HTTPException(400, "该券已过期，无法核销，请改为退货")
    remaining = (voucher.quantity or 0) - (voucher.redeemed or 0)
    k = payload.quantity
    if k <= 0:
        raise HTTPException(400, "核销张数必须大于 0")
    if k > remaining:
        raise HTTPException(400, f"核销张数超过剩余（剩余 {remaining} 张）")

    occurred = payload.occurred_at or datetime.now()
    cat = payload.category_id or voucher.category_id
    topup = Decimal(payload.topup or 0)
    group = uuid4().hex[:24] if topup > 0 and payload.topup_account_id else None
    voucher_cost = _round2(Decimal(voucher.unit_price or 0) * k)

    # 1) 团购券账户支出：券价值确认为消费支出
    exp = models.Transaction(
        ledger_id=ledger_id, type="expense", amount=voucher_cost,
        account_id=voucher.account_id, category_id=cat, occurred_at=occurred,
        remark=payload.remark or f"核销：{voucher.product} {k}张",
        voucher_id=voucher.id, split_group=group, trade_qty=Decimal(k),
    )
    db.add(exp)
    db.flush()
    _attach_tags(db, exp, payload.tag_ids)
    apply_transaction(db, exp, sign=1)

    # 2) 补差价（可选）：从指定资金账户额外支出
    if topup > 0 and payload.topup_account_id:
        top = models.Transaction(
            ledger_id=ledger_id, type="expense", amount=_round2(topup),
            account_id=payload.topup_account_id, category_id=cat, occurred_at=occurred,
            remark=f"核销补差价：{voucher.product}",
            voucher_id=voucher.id, split_group=group,
        )
        db.add(top)
        db.flush()
        _attach_tags(db, top, payload.tag_ids)
        apply_transaction(db, top, sign=1)

    voucher.redeemed = (voucher.redeemed or 0) + k
    if voucher.redeemed >= (voucher.quantity or 0):
        voucher.status = "used"
    db.commit()
    db.refresh(voucher)
    return _voucher_out(voucher)


@router.post("/ledgers/{ledger_id}/vouchers/{voucher_id}/refund", response_model=schemas.VoucherOut)
def voucher_refund(
    ledger_id: int, voucher_id: int, payload: schemas.VoucherRefund,
    db: Session = Depends(get_db),
):
    """退货：到期未用，剩余券本金（按实付价）退回原购买资金账户。"""
    voucher = db.get(models.Voucher, voucher_id)
    if not voucher:
        raise HTTPException(404, "团购券不存在")
    # 编辑模式：先回滚原退货（状态恢复为 active）
    if payload.edit_txn_id:
        old = db.get(models.Transaction, payload.edit_txn_id)
        if old and old.voucher_id == voucher.id:
            _reverse_voucher_txn(db, old)
            db.flush()
    if voucher.status == "refunded":
        raise HTTPException(400, "该券已退货")
    remaining = (voucher.quantity or 0) - (voucher.redeemed or 0)
    if remaining <= 0:
        raise HTTPException(400, "没有可退的剩余券")

    occurred = payload.occurred_at or datetime.now()
    amount = _round2(Decimal(voucher.unit_price or 0) * remaining)
    note = payload.remark or f"退券：{voucher.product} {remaining}张"
    target = voucher.source_account_id

    if target and amount > 0:
        txn = models.Transaction(
            ledger_id=ledger_id, type="transfer", amount=amount,
            account_id=voucher.account_id, to_account_id=target,
            occurred_at=occurred, remark=note, voucher_id=voucher.id,
        )
    else:
        # 无退款目标：用负向余额调整减少团购券账户余额
        txn = models.Transaction(
            ledger_id=ledger_id, type="adjust", amount=-amount,
            account_id=voucher.account_id, occurred_at=occurred,
            remark=note, voucher_id=voucher.id,
        )
    db.add(txn)
    db.flush()
    apply_transaction(db, txn, sign=1)

    voucher.status = "refunded"
    db.commit()
    db.refresh(voucher)
    return _voucher_out(voucher)


@router.delete("/vouchers/{voucher_id}")
def delete_voucher(voucher_id: int, db: Session = Depends(get_db)):
    """删除团购券：回滚其全部流水（购券/核销/退券）并删除券。"""
    voucher = db.get(models.Voucher, voucher_id)
    if not voucher:
        raise HTTPException(404, "团购券不存在")
    _reverse_voucher_all(db, voucher)
    db.commit()
    return {"detail": "已删除"}
