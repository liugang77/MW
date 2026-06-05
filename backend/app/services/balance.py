from decimal import Decimal

from sqlalchemy.orm import Session

from app import models


def apply_transaction(db: Session, txn: models.Transaction, sign: int = 1) -> None:
    """根据交易对相关账户余额进行增减。sign=1 应用，sign=-1 回滚。"""
    amount = Decimal(txn.amount) * sign
    fee = Decimal(txn.fee or 0) * sign

    acc = db.get(models.Account, txn.account_id)
    if txn.type == "expense":
        acc.current_balance = Decimal(acc.current_balance) - amount
    elif txn.type == "income":
        acc.current_balance = Decimal(acc.current_balance) + amount
    elif txn.type == "adjust":
        # 余额调整：amount 为带符号的差额，不计入日常收支
        acc.current_balance = Decimal(acc.current_balance) + amount
    elif txn.type == "transfer":
        # 转出账户减少（含手续费），转入账户增加
        acc.current_balance = Decimal(acc.current_balance) - amount - fee
        if txn.to_account_id:
            to_acc = db.get(models.Account, txn.to_account_id)
            to_acc.current_balance = Decimal(to_acc.current_balance) + amount


def recompute_account(db: Session, account_id: int) -> None:
    """重算某账户当前余额（维护用）。"""
    acc = db.get(models.Account, account_id)
    balance = Decimal(acc.initial_balance)
    txns = db.query(models.Transaction).filter(
        (models.Transaction.account_id == account_id)
        | (models.Transaction.to_account_id == account_id)
    ).all()
    for t in txns:
        if t.account_id == account_id:
            if t.type == "expense":
                balance -= Decimal(t.amount)
            elif t.type == "income":
                balance += Decimal(t.amount)
            elif t.type == "adjust":
                balance += Decimal(t.amount)
            elif t.type == "transfer":
                balance -= Decimal(t.amount) + Decimal(t.fee or 0)
        if t.to_account_id == account_id and t.type == "transfer":
            balance += Decimal(t.amount)
    acc.current_balance = balance
