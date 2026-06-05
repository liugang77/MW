from datetime import datetime
from decimal import Decimal
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db
from app.services.balance import apply_transaction

router = APIRouter(tags=["trades"])


def _attach_tags(db: Session, txn: models.Transaction, tag_ids: list[int]) -> None:
    if not tag_ids:
        return
    tags = db.query(models.Tag).filter(models.Tag.id.in_(tag_ids)).all()
    txn.tags = tags


def _find_holding(db: Session, ledger_id: int, account_id: int, symbol: str) -> models.Holding | None:
    return (
        db.query(models.Holding)
        .filter(
            models.Holding.ledger_id == ledger_id,
            models.Holding.account_id == account_id,
            models.Holding.symbol == symbol,
        )
        .first()
    )


def _reverse_trade_txn(db: Session, txn: models.Transaction) -> None:
    """回滚一笔证券买卖流水（含持仓影响）并删除该流水。

    买入（expense）：持仓数量与成本各减去本笔；不足则删除持仓。
    卖出（income）：持仓数量加回本笔数量，成本加回本笔结转成本（trade_cost）。
    """
    if txn.trade_qty is not None and txn.trade_symbol:
        # 持仓记在证券账户：优先 to_account_id（资金≠证券时的关联），否则同 account_id
        acc_id = txn.to_account_id or txn.account_id
        holding = _find_holding(db, txn.ledger_id, acc_id, txn.trade_symbol)
        qty = Decimal(txn.trade_qty or 0)
        if txn.type == "expense":  # 买入回滚
            if holding:
                holding.quantity = Decimal(holding.quantity) - qty
                holding.cost = Decimal(holding.cost) - Decimal(txn.amount or 0)
                if Decimal(holding.quantity) <= 0:
                    db.delete(holding)
        elif txn.type == "income":  # 卖出回滚
            cost_back = Decimal(txn.trade_cost or 0)
            if holding:
                holding.quantity = Decimal(holding.quantity) + qty
                holding.cost = Decimal(holding.cost) + cost_back
            else:
                holding = models.Holding(
                    ledger_id=txn.ledger_id, account_id=acc_id,
                    symbol=txn.trade_symbol, name=txn.trade_symbol, type="stock",
                    quantity=qty, cost=cost_back,
                    price=Decimal(txn.trade_price or 0),
                )
                db.add(holding)
    apply_transaction(db, txn, sign=-1)
    db.delete(txn)
    db.flush()


@router.post("/ledgers/{ledger_id}/trades/buy", response_model=schemas.HoldingOut)
def trade_buy(ledger_id: int, payload: schemas.TradeBuy, db: Session = Depends(get_db)):
    """证券买入：从资金账户的可用现金支出买入成本，生成一笔持仓。

    资金账户余额 = 可用现金；买入后现金减少，持仓作为投资资产单独计算市值。
    不再向证券账户记一笔“买入持仓”收入，避免与持仓市值重复计入净资产。
    """
    if payload.quantity <= 0:
        raise HTTPException(400, "数量必须大于 0")
    if payload.price < 0:
        raise HTTPException(400, "价格不能为负")

    # 编辑模式：先回滚并删除原流水（含持仓影响）
    if payload.edit_txn_id:
        old = db.get(models.Transaction, payload.edit_txn_id)
        if old:
            _reverse_trade_txn(db, old)

    gross = (Decimal(payload.price) * Decimal(payload.quantity)).quantize(Decimal("0.01"))
    fee = Decimal(payload.fee_total or 0)
    total = Decimal(payload.amount_total) if payload.amount_total is not None else gross + fee
    occurred = payload.occurred_at or datetime.now()
    name = payload.name or payload.symbol

    # 资金账户支出（含费用）——现金转为持仓
    pay = models.Transaction(
        ledger_id=ledger_id, type="expense", amount=total,
        account_id=payload.cash_account_id, occurred_at=occurred,
        to_account_id=(payload.security_account_id
                       if payload.security_account_id != payload.cash_account_id else None),
        remark=payload.remark or f"买入：{name} {payload.quantity}股",
        trade_price=Decimal(payload.price), trade_qty=Decimal(payload.quantity),
        trade_commission=Decimal(payload.commission or 0), trade_fee=fee,
        trade_cost=total, trade_symbol=payload.symbol,
    )
    db.add(pay)
    db.flush()
    _attach_tags(db, pay, payload.tag_ids)
    apply_transaction(db, pay, sign=1)

    # 更新/创建持仓
    holding = _find_holding(db, ledger_id, payload.security_account_id, payload.symbol)
    if holding:
        holding.quantity = Decimal(holding.quantity) + Decimal(payload.quantity)
        holding.cost = Decimal(holding.cost) + total
        holding.price = Decimal(payload.price)
    else:
        holding = models.Holding(
            ledger_id=ledger_id, account_id=payload.security_account_id,
            symbol=payload.symbol, name=name, type=payload.sec_type,
            quantity=Decimal(payload.quantity), cost=total, price=Decimal(payload.price),
        )
        db.add(holding)
    db.flush()
    db.commit()
    db.refresh(holding)
    return _holding_out(holding)


@router.post("/ledgers/{ledger_id}/trades/sell", response_model=schemas.HoldingOut | None)
def trade_sell(ledger_id: int, payload: schemas.TradeSell, db: Session = Depends(get_db)):
    """证券卖出：资金账户收入（扣费用），证券账户按成本减少持仓。"""
    if payload.quantity <= 0:
        raise HTTPException(400, "数量必须大于 0")

    # 编辑模式：先回滚并删除原流水（含持仓影响），再按新值卖出
    if payload.edit_txn_id:
        old = db.get(models.Transaction, payload.edit_txn_id)
        if old:
            _reverse_trade_txn(db, old)

    holding = _find_holding(db, ledger_id, payload.security_account_id, payload.symbol)
    if not holding:
        raise HTTPException(400, "该证券账户没有此持仓")
    held = Decimal(holding.quantity)
    sell_qty = Decimal(payload.quantity)
    if sell_qty > held:
        raise HTTPException(400, "卖出数量超过持仓")

    gross = (Decimal(payload.price) * sell_qty).quantize(Decimal("0.01"))
    fee = Decimal(payload.fee_total or 0)
    net = gross - fee  # 实际到账
    occurred = payload.occurred_at or datetime.now()
    name = holding.name

    # 按比例结转成本
    cost_removed = (Decimal(holding.cost) * sell_qty / held).quantize(Decimal("0.01")) if held else Decimal("0")

    # 资金账户收入（净额）——持仓转为现金
    recv = models.Transaction(
        ledger_id=ledger_id, type="income", amount=net,
        account_id=payload.cash_account_id, occurred_at=occurred,
        to_account_id=(payload.security_account_id
                       if payload.security_account_id != payload.cash_account_id else None),
        remark=payload.remark or f"卖出：{name} {sell_qty}股",
        trade_price=Decimal(payload.price), trade_qty=sell_qty,
        trade_commission=Decimal(payload.commission or 0), trade_fee=fee,
        trade_cost=cost_removed, trade_symbol=payload.symbol,
    )
    db.add(recv)
    db.flush()
    _attach_tags(db, recv, payload.tag_ids)
    apply_transaction(db, recv, sign=1)

    # 更新持仓
    holding.quantity = held - sell_qty
    holding.cost = Decimal(holding.cost) - cost_removed
    holding.price = Decimal(payload.price)
    if Decimal(holding.quantity) <= 0:
        db.delete(holding)
        db.commit()
        return None
    db.flush()
    db.commit()
    db.refresh(holding)
    return _holding_out(holding)


def _holding_out(h: models.Holding) -> schemas.HoldingOut:
    out = schemas.HoldingOut.model_validate(h)
    market_value = Decimal(h.quantity) * Decimal(h.price)
    out.market_value = market_value
    out.profit = market_value - Decimal(h.cost)
    out.profit_rate = float(round(out.profit / Decimal(h.cost) * 100, 2)) if h.cost else 0.0
    return out


def _ipo_name(txn: models.Transaction) -> str:
    """从申购流水备注中解析证券名称（备注格式：新股申购：名称 数量股）。"""
    raw = re.sub(r"^新股(申购|中签)[：:]", "", txn.remark or "")
    name = re.sub(r"\s*\d.*$", "", raw).strip()
    return name or (txn.trade_symbol or "")


@router.post("/ledgers/{ledger_id}/ipo/subscribe")
def ipo_subscribe(ledger_id: int, payload: schemas.IpoSubscribe, db: Session = Depends(get_db)):
    """新股申购：从资金账户冻结申购资金（记为支出），不建仓、状态 pending。

    中签确认后才产生买入持仓；未中签则全额返款。
    """
    if payload.quantity <= 0:
        raise HTTPException(400, "数量必须大于 0")
    if payload.price < 0:
        raise HTTPException(400, "价格不能为负")

    gross = (Decimal(payload.price) * Decimal(payload.quantity)).quantize(Decimal("0.01"))
    fee = Decimal(payload.fee_total or 0)
    total = Decimal(payload.amount_total) if payload.amount_total is not None else gross + fee
    occurred = payload.occurred_at or datetime.now()
    name = payload.name or payload.symbol

    txn = models.Transaction(
        ledger_id=ledger_id, type="expense", amount=total,
        account_id=payload.cash_account_id, occurred_at=occurred,
        to_account_id=(payload.security_account_id
                       if payload.security_account_id != payload.cash_account_id else None),
        remark=payload.remark or f"新股申购：{name} {payload.quantity}股",
        trade_price=Decimal(payload.price), trade_qty=Decimal(payload.quantity),
        trade_commission=Decimal(payload.commission or 0), trade_fee=fee,
        trade_cost=total, trade_symbol=payload.symbol,
        ipo_status="pending",
    )
    db.add(txn)
    db.flush()
    _attach_tags(db, txn, payload.tag_ids)
    apply_transaction(db, txn, sign=1)
    db.commit()
    return {"detail": "已申购", "txn_id": txn.id}


@router.get("/ledgers/{ledger_id}/ipo/pending", response_model=list[schemas.IpoPendingOut])
def ipo_pending(ledger_id: int, account_id: int | None = None, db: Session = Depends(get_db)):
    """列出待中签确认的新股申购（状态 pending）。account_id 可按证券账户过滤。"""
    rows = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.ledger_id == ledger_id,
            models.Transaction.ipo_status == "pending",
        )
        .order_by(models.Transaction.occurred_at.desc())
        .all()
    )
    out: list[schemas.IpoPendingOut] = []
    for t in rows:
        sec = t.to_account_id or t.account_id
        if account_id is not None and account_id not in (sec, t.account_id):
            continue
        out.append(schemas.IpoPendingOut(
            txn_id=t.id, symbol=t.trade_symbol or "", name=_ipo_name(t),
            amount=Decimal(t.amount), quantity=t.trade_qty, price=t.trade_price,
            funding_account_id=t.account_id, security_account_id=sec,
            occurred_at=t.occurred_at,
        ))
    return out


@router.post("/ledgers/{ledger_id}/ipo/confirm")
def ipo_confirm(ledger_id: int, payload: schemas.IpoConfirm, db: Session = Depends(get_db)):
    """中签确认：

    - 中签：以「申购金额 − 申购返款」为成本建仓，产生买入记录；返款（如有）退回资金账户。
    - 未中签：申购返款退回资金账户，不建仓。
    """
    txn = db.get(models.Transaction, payload.txn_id)
    if not txn or txn.ledger_id != ledger_id or txn.ipo_status != "pending":
        raise HTTPException(400, "申购记录不存在或已确认")

    amount = Decimal(txn.amount)
    refund = Decimal(payload.refund_amount or 0)
    if refund < 0 or refund > amount:
        raise HTTPException(400, "申购返款金额不合法")
    occurred = payload.occurred_at or datetime.now()
    sec_acc = txn.to_account_id or txn.account_id
    name = _ipo_name(txn)

    if payload.won:
        cost = (amount - refund).quantize(Decimal("0.01"))
        qty = Decimal(txn.trade_qty or 0)
        price = (cost / qty).quantize(Decimal("0.0001")) if qty else Decimal(txn.trade_price or 0)
        holding = _find_holding(db, ledger_id, sec_acc, txn.trade_symbol)
        if holding:
            holding.quantity = Decimal(holding.quantity) + qty
            holding.cost = Decimal(holding.cost) + cost
            holding.price = price
        else:
            holding = models.Holding(
                ledger_id=ledger_id, account_id=sec_acc,
                symbol=txn.trade_symbol, name=name, type="stock",
                quantity=qty, cost=cost, price=price,
            )
            db.add(holding)
        txn.ipo_status = "won"
        qty_disp = int(qty) if qty == qty.to_integral_value() else qty
        txn.remark = f"新股中签：{name} {qty_disp}股"
    else:
        txn.ipo_status = "lost"
    db.flush()

    # 申购返款（未中签全额返还 / 中签部分返还）退回资金账户
    if refund > 0:
        rf = models.Transaction(
            ledger_id=ledger_id, type="income", amount=refund,
            account_id=txn.account_id, occurred_at=occurred,
            remark=(payload.remark or f"新股申购返款：{name}"),
            ipo_status="refund",
        )
        db.add(rf)
        db.flush()
        _attach_tags(db, rf, payload.tag_ids)
        apply_transaction(db, rf, sign=1)

    db.commit()
    return {"detail": "已确认", "won": payload.won}

