from datetime import datetime
from decimal import Decimal
import re

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db

router = APIRouter(tags=["stats"])


def _range(q, start, end):
    if start:
        q = q.filter(models.Transaction.occurred_at >= start)
    if end:
        q = q.filter(models.Transaction.occurred_at <= end)
    return q


def _real_flow(q):
    """只统计「真实收支」，排除资产转换/本金性资金流水：
    - 证券买卖：现金与持仓之间的转换，并非消费或收入；
    - 借贷本金的出入账（借入/借出，loan_id 有值且无收款分组）；
    - 网贷收回本金部分（利息部分保留为投资收益）。
    保留：普通收入/支出、借贷与网贷的利息收支。
    """
    return q.filter(
        models.Transaction.trade_symbol.is_(None),
        ~(
            models.Transaction.loan_id.isnot(None)
            & models.Transaction.collect_group.is_(None)
        ),
        ~func.coalesce(models.Transaction.remark, "").like("网贷收回本金%"),
    )


@router.get("/ledgers/{ledger_id}/stats/overview", response_model=schemas.OverviewOut)
def overview(
    ledger_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    base = db.query(func.coalesce(func.sum(models.Transaction.amount), 0)).filter(
        models.Transaction.ledger_id == ledger_id
    )
    base = _real_flow(base)
    income = _range(base.filter(models.Transaction.type == "income"), start, end).scalar()
    expense = _range(base.filter(models.Transaction.type == "expense"), start, end).scalar()
    income = Decimal(income)
    expense = Decimal(expense)
    return {"income": income, "expense": expense, "balance": income - expense}


@router.get("/ledgers/{ledger_id}/stats/by-category", response_model=schemas.CategoryStatOut)
def by_category(
    ledger_id: int,
    kind: str = "expense",
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    q = (
        db.query(
            models.Category.id,
            models.Category.name,
            func.coalesce(func.sum(models.Transaction.amount), 0).label("amount"),
        )
        .join(models.Transaction, models.Transaction.category_id == models.Category.id)
        .filter(models.Transaction.ledger_id == ledger_id)
        .filter(models.Transaction.type == kind)
    )
    q = _real_flow(q)
    q = _range(q, start, end).group_by(models.Category.id).order_by(func.sum(models.Transaction.amount).desc())
    rows = q.all()
    total = sum((Decimal(r.amount) for r in rows), Decimal("0"))
    items = [
        {
            "category_id": r.id,
            "name": r.name,
            "amount": Decimal(r.amount),
            "percent": float(round(Decimal(r.amount) / total * 100, 2)) if total else 0.0,
        }
        for r in rows
    ]
    return {"total": total, "items": items}


@router.get("/ledgers/{ledger_id}/stats/net-worth", response_model=schemas.NetWorthOut)
def net_worth(ledger_id: int, db: Session = Depends(get_db)):
    accounts = (
        db.query(models.Account)
        .filter(models.Account.ledger_id == ledger_id)
        .filter(models.Account.is_active == True)  # noqa: E712
        .filter(models.Account.include_in_net == True)  # noqa: E712
        .all()
    )
    asset_groups: dict[str, Decimal] = {}
    liability_groups: dict[str, Decimal] = {}
    for a in accounts:
        bal = Decimal(a.current_balance)
        if bal >= 0:
            asset_groups[a.name] = asset_groups.get(a.name, Decimal("0")) + bal
        else:
            liability_groups[a.name] = liability_groups.get(a.name, Decimal("0")) + (-bal)

    # 投资持仓市值计入资产
    holdings = db.query(models.Holding).filter(models.Holding.ledger_id == ledger_id).all()
    mv = sum((Decimal(h.quantity) * Decimal(h.price) for h in holdings), Decimal("0"))
    if mv > 0:
        asset_groups["投资持仓"] = asset_groups.get("投资持仓", Decimal("0")) + mv

    # 债权债务
    loans = (
        db.query(models.Loan)
        .filter(models.Loan.ledger_id == ledger_id, models.Loan.is_closed == False)  # noqa: E712
        .all()
    )
    for loan in loans:
        remaining = Decimal(loan.amount) - Decimal(loan.settled)
        if remaining <= 0:
            continue
        if loan.direction == "receivable":
            asset_groups["应收款"] = asset_groups.get("应收款", Decimal("0")) + remaining
        else:
            liability_groups["应付款"] = liability_groups.get("应付款", Decimal("0")) + remaining

    assets = sum(asset_groups.values(), Decimal("0"))
    liabilities = sum(liability_groups.values(), Decimal("0"))
    return {
        "assets": assets,
        "liabilities": liabilities,
        "net_worth": assets - liabilities,
        "asset_groups": [{"name": k, "amount": v} for k, v in asset_groups.items()],
        "liability_groups": [{"name": k, "amount": v} for k, v in liability_groups.items()],
    }


@router.get("/ledgers/{ledger_id}/stats/trend", response_model=list[schemas.TrendItem])
def trend(
    ledger_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    period = func.strftime("%Y-%m", models.Transaction.occurred_at)
    q = (
        db.query(
            period.label("period"),
            models.Transaction.type,
            func.coalesce(func.sum(models.Transaction.amount), 0).label("amount"),
        )
        .filter(models.Transaction.ledger_id == ledger_id)
        .filter(models.Transaction.type.in_(["income", "expense"]))
    )
    q = _range(_real_flow(q), start, end).group_by("period", models.Transaction.type)
    bucket: dict[str, dict] = {}
    for r in q.all():
        b = bucket.setdefault(r.period, {"income": Decimal("0"), "expense": Decimal("0")})
        b[r.type] = Decimal(r.amount)
    return [
        {"period": p, "income": v["income"], "expense": v["expense"]}
        for p, v in sorted(bucket.items())
    ]


@router.get("/ledgers/{ledger_id}/stats/investment", response_model=schemas.InvestmentOverview)
def investment_overview(ledger_id: int, db: Session = Depends(get_db)):
    """投资一览：买入均价、持仓成本、持仓市值、浮动盈亏、涨幅%。
    
    外币持仓（currency != CNY）：market_value 用最新汇率折算为人民币，
    便于体现「收益 + 汇率变化」两个因素对人民币价值的综合影响。
    """
    rows = db.query(models.Holding).filter(models.Holding.ledger_id == ledger_id).all()

    # 加载最新汇率（取每种货币最新一条记录）
    rate_rows = (
        db.query(models.ExchangeRate)
        .filter(models.ExchangeRate.ledger_id == ledger_id)
        .order_by(models.ExchangeRate.rate_date.desc())
        .all()
    )
    latest_rates: dict[str, Decimal] = {}
    for r in rate_rows:
        if r.currency_code not in latest_rates:
            latest_rates[r.currency_code] = Decimal(r.rate)

    out_rows = []
    total_cost = Decimal("0")
    total_mv = Decimal("0")
    for h in rows:
        qty = Decimal(h.quantity)
        cost = Decimal(h.cost)
        price = Decimal(h.price)
        hcurrency = getattr(h, "currency", None) or "CNY"
        # 外币持仓：market_value = 持仓数量 × 最新汇率（单位：人民币）
        # price 列对于外币理财存储的是申购时汇率，以最新汇率覆盖市值计算
        if hcurrency != "CNY" and hcurrency in latest_rates:
            current_rate = latest_rates[hcurrency]
            mv = (qty * current_rate).quantize(Decimal("0.01"))
        else:
            mv = qty * price
        avg_cost = (cost / qty) if qty else Decimal("0")
        float_profit = mv - cost
        change = float(round(float_profit / cost * 100, 2)) if cost else 0.0
        total_cost += cost
        total_mv += mv
        out_rows.append({
            "id": h.id, "name": h.name, "symbol": h.symbol, "type": h.type,
            "quantity": qty, "avg_cost": avg_cost.quantize(Decimal("0.0001")),
            "position_cost": cost, "price": price, "market_value": mv,
            "float_profit": float_profit, "change_pct": change,
        })
    total_profit = total_mv - total_cost
    total_change = float(round(total_profit / total_cost * 100, 2)) if total_cost else 0.0
    return {
        "total_cost": total_cost,
        "total_market_value": total_mv,
        "total_float_profit": total_profit,
        "total_change_pct": total_change,
        "rows": out_rows,
    }


# 投资类账户类型
_INVEST_TYPES = {
    "stock", "fund", "open_fund", "money_fund", "bond", "reverse_repo",
    "wealth", "metal", "metal_td", "forex", "futures", "margin", "p2p",
}
# 仅按成本/收益核算、无浮动盈亏的持仓类型（货币基金净值恒为 1，理财/债券按收益）
_COST_ONLY_HOLDING_TYPES = {"money_fund", "wealth", "bond", "reverse_repo"}
_REMARK_PREFIX_RE = re.compile(
    r"^(买入|卖出|申购|赎回|理财申购|理财赎回|银行理财产品申购|银行理财产品赎回|基金申购|基金赎回)[：:]"
)


def _derive_name(remark: str | None) -> str:
    if not remark:
        return ""
    s = _REMARK_PREFIX_RE.sub("", remark)
    s = re.sub(r"\s*\d.*$", "", s)
    return s.strip()


@router.get(
    "/ledgers/{ledger_id}/stats/investment-income",
    response_model=schemas.InvestmentIncomeReport,
)
def investment_income(
    ledger_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    """投资收益一览表：按账户分组，列出各投资产品的盈亏（浮动 + 已实现）。

    - 持仓类（股票/基金等）：浮动盈亏 = 市值 − 成本，并叠加历史卖出/赎回的已实现盈亏；
    - 货币基金/理财：以收益（income 流水）累计为盈亏；
    - 网贷（P2P）：每个项目已实现利息 = 每期还息 × 已收期数。
    日期范围仅作用于「已实现」收益流水。
    """
    accounts = (
        db.query(models.Account)
        .filter(
            models.Account.ledger_id == ledger_id,
            models.Account.type.in_(_INVEST_TYPES),
        )
        .order_by(models.Account.id)
        .all()
    )
    acc_ids = {a.id for a in accounts}
    if not acc_ids:
        return {"total_profit": Decimal("0"), "groups": []}

    holdings = (
        db.query(models.Holding)
        .filter(models.Holding.ledger_id == ledger_id)
        .all()
    )

    income_q = db.query(models.Transaction).filter(
        models.Transaction.ledger_id == ledger_id,
        models.Transaction.type == "income",
        models.Transaction.trade_symbol.isnot(None),
    )
    income_q = _range(income_q, start, end)
    income_txns = income_q.all()

    loans = (
        db.query(models.Loan)
        .filter(
            models.Loan.ledger_id == ledger_id,
            models.Loan.loan_kind == "p2p",
        )
        .all()
    )

    # (account_id, key) -> {symbol, name, profit}
    products: dict[tuple[int, str], dict] = {}

    def _entry(acc_id: int, key: str) -> dict:
        k = (acc_id, key)
        if k not in products:
            products[k] = {"symbol": None, "name": None, "profit": Decimal("0")}
        return products[k]

    for h in holdings:
        if h.account_id not in acc_ids:
            continue
        key = h.symbol or h.name
        mv = Decimal(h.quantity) * Decimal(h.price)
        # 成本/收益核算的品种（货币基金/理财/债券）无浮动盈亏，仅计已实现收益
        floating = Decimal("0") if h.type in _COST_ONLY_HOLDING_TYPES else mv - Decimal(h.cost)
        e = _entry(h.account_id, key)
        e["name"] = h.name
        e["symbol"] = h.symbol
        e["profit"] += floating

    for t in income_txns:
        if t.account_id not in acc_ids:
            continue
        key = t.trade_symbol or ""
        realized = Decimal(t.amount) - Decimal(t.trade_cost or 0)
        e = _entry(t.account_id, key)
        if not e["name"]:
            e["name"] = _derive_name(t.remark) or t.trade_symbol
        if not e["symbol"]:
            e["symbol"] = t.trade_symbol
        e["profit"] += realized

    # 按账户聚合持仓/收益类产品
    acc_products: dict[int, list[dict]] = {}
    for (acc_id, _key), e in products.items():
        acc_products.setdefault(acc_id, []).append(e)

    # 网贷：每个项目的已实现利息
    p2p_products: dict[int, list[dict]] = {}
    for ln in loans:
        if ln.account_id not in acc_ids:
            continue
        earned = Decimal(ln.per_interest or 0) * Decimal(ln.collected_periods or 0)
        p2p_products.setdefault(ln.account_id, []).append(
            {"symbol": ln.item, "name": ln.counterparty, "profit": earned}
        )

    groups = []
    total_profit = Decimal("0")
    for a in accounts:
        rows = p2p_products.get(a.id, []) if a.type == "p2p" else acc_products.get(a.id, [])
        if not rows:
            continue
        rows = sorted(rows, key=lambda r: r["profit"], reverse=True)
        sub = sum((r["profit"] for r in rows), Decimal("0"))
        total_profit += sub
        groups.append({
            "account_id": a.id,
            "account_name": a.name,
            "account_type": a.type,
            "total_profit": sub,
            "rows": [
                {"symbol": r["symbol"], "name": r["name"] or r["symbol"] or "", "profit": r["profit"]}
                for r in rows
            ],
        })

    return {"total_profit": total_profit, "groups": groups}


@router.get("/ledgers/{ledger_id}/stats/diagnosis", response_model=schemas.DiagnosisOut)
def diagnosis(ledger_id: int, db: Session = Depends(get_db)):
    """财务诊断（统计范围：最近 1 年）。"""
    from datetime import timedelta

    end = datetime.now()
    start = end - timedelta(days=365)

    # 收入按一级分类名称分组
    rows = (
        db.query(
            models.Category.name,
            func.coalesce(func.sum(models.Transaction.amount), 0).label("amount"),
        )
        .join(models.Transaction, models.Transaction.category_id == models.Category.id)
        .filter(models.Transaction.ledger_id == ledger_id)
        .filter(models.Transaction.type == "income")
        .filter(models.Transaction.occurred_at >= start)
    )
    rows = _real_flow(rows).group_by(models.Category.id).all()
    salary = Decimal("0")
    rent = Decimal("0")
    other_named = Decimal("0")
    total_income = Decimal("0")
    for r in rows:
        amt = Decimal(r.amount)
        total_income += amt
        name = r.name or ""
        if "薪" in name or "工资" in name:
            salary += amt
        elif "租" in name:
            rent += amt

    # 年投资收入：最近一年「已实现」的证券卖出收益（卖出净额 − 结转成本）。
    # 不再用当前持仓的「浮动盈亏」充当收入——未实现盈亏不是现金流入，
    # 且会随行情波动，混入年度收支诊断并不合理。
    sell_rows = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.ledger_id == ledger_id,
            models.Transaction.type == "income",
            models.Transaction.trade_symbol.isnot(None),
            models.Transaction.occurred_at >= start,
        )
        .all()
    )
    invest_income = sum(
        (Decimal(t.amount or 0) - Decimal(t.trade_cost or 0) for t in sell_rows),
        Decimal("0"),
    )
    other_income = total_income - salary - rent
    total_income_all = total_income + invest_income

    total_expense = Decimal(
        _range(
            _real_flow(
                db.query(func.coalesce(func.sum(models.Transaction.amount), 0)).filter(
                    models.Transaction.ledger_id == ledger_id,
                    models.Transaction.type == "expense",
                )
            ),
            start, end,
        ).scalar()
    )
    surplus = total_income_all - total_expense
    surplus_ratio = float(round(surplus / total_income_all * 100, 2)) if total_income_all else 0.0
    invest_ratio = float(round(invest_income / total_income_all * 100, 2)) if total_income_all else 0.0
    return {
        "salary_income": salary,
        "rent_income": rent,
        "invest_income": invest_income,
        "other_income": other_income,
        "total_income": total_income_all,
        "total_expense": total_expense,
        "surplus": surplus,
        "surplus_ratio": surplus_ratio,
        "invest_ratio": invest_ratio,
    }

