"""行情同步 API：查询单个代码的最新行情、批量同步已持仓品种的每日价格。"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models
from app.core.db import get_db
from app.services import quote

router = APIRouter(tags=["market"])


@router.get("/market/quote")
def market_quote(
    code: str = Query(..., description="证券/基金代码"),
    kind: str = Query("stock", description="行情通道：stock 或 fund"),
):
    """查询单个代码的名称与最新价格（用于建档时同步代码与资料）。"""
    data = quote.lookup(kind, code)
    if not data:
        raise HTTPException(404, "未查询到该代码的行情，请检查代码或稍后重试")
    return data


@router.post("/ledgers/{ledger_id}/market/sync-prices")
def sync_prices(ledger_id: int, db: Session = Depends(get_db)):
    """同步本账本中「已持仓」品种的最新价格：

    - 写入当日 instrument_price（已有则更新）；
    - 更新对应 holding.price，从而实时反映盈亏。
    """
    holdings = (
        db.query(models.Holding)
        .filter(models.Holding.ledger_id == ledger_id)
        .all()
    )
    insts = (
        db.query(models.Instrument)
        .filter(models.Instrument.ledger_id == ledger_id)
        .all()
    )
    inst_by_code: dict[str, models.Instrument] = {}
    inst_by_name: dict[str, models.Instrument] = {}
    for i in insts:
        if i.code:
            inst_by_code.setdefault(i.code.strip(), i)
        if i.category in ("metal", "metal_td") and i.name:
            inst_by_name.setdefault(i.name.strip(), i)

    today = date.today().isoformat()
    updated: list[dict] = []
    failed: list[str] = []
    seen: set[str] = set()

    for h in holdings:
        code = (h.symbol or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        # 贵金属：以品种名称取价（新浪 SGE），不受数字代码校验限制
        is_metal = h.type in ("metal", "metal_td")
        inst = inst_by_code.get(code)
        if is_metal and inst is None:
            inst = inst_by_name.get(code)
        category = inst.category if inst else None
        if category in ("metal", "metal_td"):
            is_metal = True
        if not is_metal:
            # 非标准代码（如中文名称的理财产品）无法联网取价，跳过
            if not quote.is_valid_code(code):
                continue
            # 货币基金净值恒为 1.00（接口返回的是每万份收益），不参与价格同步
            if (category == "money_fund") or (h.type == "money_fund"):
                continue
        kind = (
            quote.kind_for_category(inst.category)
            if inst
            else quote.kind_for_holding_type(h.type)
        )
        data = quote.lookup(kind, code)
        price_raw = data.get("price") if data else None
        if not price_raw:
            failed.append(code)
            continue
        try:
            price = Decimal(str(price_raw))
        except (InvalidOperation, ValueError):
            failed.append(code)
            continue

        # 更新该代码下所有持仓的最新价
        for hh in holdings:
            if (hh.symbol or "").strip() == code:
                hh.price = price
                hh.updated_at = datetime.now()

        # 写入/更新当日价格
        if inst:
            existing = (
                db.query(models.InstrumentPrice)
                .filter(
                    models.InstrumentPrice.instrument_id == inst.id,
                    models.InstrumentPrice.price_date == today,
                )
                .first()
            )
            if existing:
                existing.price = price
            else:
                db.add(
                    models.InstrumentPrice(
                        instrument_id=inst.id, price_date=today, price=price
                    )
                )

        updated.append({"code": code, "name": (data or {}).get("name"), "price": str(price)})

    db.commit()
    return {"updated": len(updated), "failed": failed, "items": updated}


@router.post("/ledgers/{ledger_id}/market/sync-catalog")
def sync_catalog(
    ledger_id: int,
    category: str = Query(..., description="securities / open_fund / money_fund"),
    db: Session = Depends(get_db),
):
    """同步全量产品目录：把数据源中、当前账本尚不存在的代码按类型导入。

    - securities：全部 A 股（按代码前缀归类到 subcategory）
    - open_fund：非货币型公募基金
    - money_fund：货币型基金
    - metal：预置常见贵金属品种（按名称去重）
    """
    if category not in ("securities", "open_fund", "money_fund", "metal"):
        raise HTTPException(400, "暂不支持该类型的全量同步")

    # 贵金属：按名称补充预置品种（贵金属无代码）
    if category == "metal":
        existing_names = {
            (n or "").strip()
            for (n,) in db.query(models.Instrument.name)
            .filter(
                models.Instrument.ledger_id == ledger_id,
                models.Instrument.category == "metal",
            )
            .all()
            if n
        }
        metal_rows = [
            models.Instrument(
                ledger_id=ledger_id, category="metal",
                code=None, name=p["name"], currency="CNY",
            )
            for p in quote.metal_catalog()
            if p["name"] not in existing_names
        ]
        if not metal_rows:
            return {"added": 0, "total_existing": len(existing_names)}
        db.bulk_save_objects(metal_rows)
        db.commit()
        return {"added": len(metal_rows), "total_existing": len(existing_names) + len(metal_rows)}

    # 当前账本该分类已存在的代码
    existing = {
        (c or "").strip()
        for (c,) in db.query(models.Instrument.code)
        .filter(
            models.Instrument.ledger_id == ledger_id,
            models.Instrument.category == category,
        )
        .all()
        if c
    }

    new_rows: list[models.Instrument] = []
    fetched = 0
    if category == "securities":
        catalog = quote.fetch_stock_catalog()
        fetched = len(catalog)
        for it in catalog:
            if it["code"] in existing:
                continue
            new_rows.append(
                models.Instrument(
                    ledger_id=ledger_id,
                    category="securities",
                    code=it["code"],
                    name=it["name"],
                    currency="CNY",
                    subcategory=it["subcategory"],
                )
            )
    else:
        want_money = category == "money_fund"
        catalog = quote.fetch_fund_catalog()
        fetched = len(catalog)
        for it in catalog:
            if it["is_money"] != want_money:
                continue
            if it["code"] in existing:
                continue
            new_rows.append(
                models.Instrument(
                    ledger_id=ledger_id,
                    category=category,
                    code=it["code"],
                    name=it["name"],
                    currency="CNY",
                )
            )

    # 数据源完全抓取不到（接口限流/不可用）时，明确报错，避免“静默成功 0 条”
    if fetched == 0:
        raise HTTPException(503, "行情数据源暂时不可用（可能被限流），请稍后重试")

    if not new_rows:
        return {"added": 0, "total_existing": len(existing)}

    db.bulk_save_objects(new_rows)
    db.commit()
    return {"added": len(new_rows), "total_existing": len(existing) + len(new_rows)}


@router.post("/ledgers/{ledger_id}/market/sync-forex")
def sync_forex(ledger_id: int, db: Session = Depends(get_db)):
    """同步外汇牌价：仅针对本账本外汇账户中「持有及曾经持有」的币种。

    - 列表中缺失的币种自动补充为新币种；
    - 更新 currency.rate（用于折算与外汇估值）；
    - 写入/更新当日 exchange_rate（牌价历史）。
    """
    currencies = (
        db.query(models.Currency)
        .filter(models.Currency.ledger_id == ledger_id)
        .all()
    )
    cur_by_code: dict[str, models.Currency] = {(c.code or "").upper(): c for c in currencies}
    home = next((c for c in currencies if c.is_home), None)
    base_code = home.code if home else "CNY"
    today = date.today().isoformat()

    # 收集外汇账户中「持有及曾经持有」的币种代码：
    # 外汇持仓行（type='forex'）在卖出/转出清零后仍保留，故可覆盖「曾经持有」。
    codes: set[str] = set()
    for h in (
        db.query(models.Holding)
        .filter(models.Holding.ledger_id == ledger_id, models.Holding.type == "forex")
        .all()
    ):
        if h.symbol:
            codes.add(h.symbol.strip().upper())
    # 外汇买卖流水 trade_symbol = "卖出币/买入币"，作为补充来源
    for (sym,) in (
        db.query(models.Transaction.trade_symbol)
        .filter(
            models.Transaction.ledger_id == ledger_id,
            models.Transaction.trade_symbol.like("%/%"),
        )
        .all()
    ):
        if sym:
            for part in sym.split("/"):
                p = part.strip().upper()
                if p:
                    codes.add(p)

    updated: list[dict] = []
    added: list[dict] = []
    failed: list[str] = []

    for code in sorted(codes):
        if not code or code == base_code.upper():
            continue
        data = quote.fetch_forex_rate(code)
        rate_raw = data.get("rate") if data else None
        if not rate_raw:
            failed.append(code)
            continue
        try:
            rate = Decimal(str(rate_raw))
        except (InvalidOperation, ValueError):
            failed.append(code)
            continue
        if rate <= 0:
            failed.append(code)
            continue

        cur = cur_by_code.get(code)
        name = quote.forex_name(code)
        if cur is None:
            # 补充：外汇账户持有但币种列表中缺失的币种
            cur = models.Currency(
                ledger_id=ledger_id,
                name=name,
                code=code,
                is_home=False,
                rate=rate,
                sort_order=len(currencies) + len(added) + 1,
            )
            db.add(cur)
            cur_by_code[code] = cur
            added.append({"code": code, "name": name, "rate": str(rate)})
        else:
            cur.rate = rate
            updated.append({"code": code, "name": cur.name, "rate": str(rate)})

        existing = (
            db.query(models.ExchangeRate)
            .filter(
                models.ExchangeRate.ledger_id == ledger_id,
                models.ExchangeRate.currency_code == code,
                models.ExchangeRate.rate_date == today,
            )
            .first()
        )
        if existing:
            existing.rate = rate
            existing.base_code = base_code
        else:
            db.add(
                models.ExchangeRate(
                    ledger_id=ledger_id,
                    rate_date=today,
                    currency_code=code,
                    base_code=base_code,
                    rate=rate,
                )
            )

    db.commit()
    return {
        "updated": len(updated),
        "added": len(added),
        "failed": failed,
        "items": updated + added,
    }

