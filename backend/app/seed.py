"""初始化默认账本与常用分类（common.db），以及默认账户（账本独立文件）。"""
from decimal import Decimal

from app import models
from app.core.db import SessionLocal, ledger_session

EXPENSE_CATEGORIES = [
    ("餐饮", "🍜"), ("交通", "🚗"), ("购物", "🛍️"), ("居住", "🏠"),
    ("通讯", "📱"), ("娱乐", "🎮"), ("医疗", "💊"), ("教育", "📚"),
    ("人情", "🎁"), ("旅行", "✈️"), ("还款", "💳"), ("其他", "📦"),
]
INCOME_CATEGORIES = [
    ("工资", "💰"), ("奖金", "🏆"), ("兼职", "🛠️"), ("投资收益", "📈"),
    ("利息", "🏦"), ("红包", "🧧"), ("退款", "↩️"), ("其他", "📦"),
]


def seed_ledger_defaults(ledger_id: int) -> None:
    """为指定账本初始化默认分类（common.db）与默认账户（账本独立文件）。"""
    # 通用库：常用分类
    with SessionLocal() as db:
        if db.query(models.Category).filter(models.Category.ledger_id == ledger_id).count() == 0:
            for i, (name, icon) in enumerate(EXPENSE_CATEGORIES):
                db.add(models.Category(ledger_id=ledger_id, name=name, kind="expense", icon=icon, sort_order=i))
            for i, (name, icon) in enumerate(INCOME_CATEGORIES):
                db.add(models.Category(ledger_id=ledger_id, name=name, kind="income", icon=icon, sort_order=i))
            db.commit()

    # 账本独立文件：默认账户
    with ledger_session(ledger_id) as db:
        if db.query(models.Account).count() == 0:
            db.add_all([
                models.Account(ledger_id=ledger_id, name="现金", type="cash", icon="💵",
                               initial_balance=Decimal("0"), current_balance=Decimal("0")),
                models.Account(ledger_id=ledger_id, name="微信", type="wallet", icon="💚",
                               initial_balance=Decimal("0"), current_balance=Decimal("0")),
                models.Account(ledger_id=ledger_id, name="支付宝", type="wallet", icon="💙",
                               initial_balance=Decimal("0"), current_balance=Decimal("0")),
                models.Account(ledger_id=ledger_id, name="储蓄卡", type="bank", icon="🏦",
                               initial_balance=Decimal("0"), current_balance=Decimal("0")),
            ])
            db.commit()


def seed() -> None:
    # 通用库：默认账本
    with SessionLocal() as db:
        if db.query(models.Ledger).count() > 0:
            return
        ledger = models.Ledger(name="日常账本", is_default=True, remark="默认账本")
        db.add(ledger)
        db.commit()
        ledger_id = ledger.id

    # 默认分类与账户
    seed_ledger_defaults(ledger_id)


