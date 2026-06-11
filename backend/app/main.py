from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.db import Base, engine, SessionLocal, init_common_db
from app.api import ledgers, accounts, categories, transactions, stats, budgets, holdings, loans, trades, instruments, currencies, plans, market
from app.seed import seed

# 建表：通用库（common.db）的通用表；每个账本文件的表在首次访问时按需创建
init_common_db()


def _ensure_columns() -> None:
    """轻量迁移：为既有 SQLite 数据库补充新增列。"""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "account" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("account")}
    new_cols = {
        "group_id": "INTEGER",
        "owner": "VARCHAR(64)",
        "remark": "TEXT",
        "card_no": "VARCHAR(32)",
        "bank_name": "VARCHAR(64)",
        "start_date": "VARCHAR(10)",
        "expiry": "VARCHAR(8)",
        "cash_limit": "NUMERIC(15, 2)",
        "min_repay_ratio": "NUMERIC(6, 2)",
        "annual_fee": "NUMERIC(15, 2)",
        "fee_waiver_type": "VARCHAR(12) DEFAULT 'count'",
        "fee_waiver_count": "INTEGER",
        "fee_waiver_amount": "NUMERIC(15, 2)",
        "repay_type": "VARCHAR(12) DEFAULT 'fixed'",
        "repay_after_days": "INTEGER",
        "bill_day_txn": "VARCHAR(8) DEFAULT 'next'",
        "overdraft_remind": "BOOLEAN DEFAULT 0",
        "platform_name": "VARCHAR(64)",
        "platform_url": "VARCHAR(255)",
        "insured_person": "VARCHAR(64)",
        "city": "VARCHAR(64)",
        "social_code": "VARCHAR(64)",
        "premium_as_stat": "BOOLEAN DEFAULT 0",
        "status": "VARCHAR(8) DEFAULT 'active'",
        "bill_day_last": "BOOLEAN DEFAULT 0",
        "currency2": "VARCHAR(3)",
        "overdraft1": "NUMERIC(15, 2)",
        "overdraft2": "NUMERIC(15, 2)",
        "overdraft_remind2": "BOOLEAN DEFAULT 0",
        "stock_market": "VARCHAR(16)",
    }
    missing = {name: ddl for name, ddl in new_cols.items() if name not in cols}
    if missing:
        with engine.begin() as conn:
            for name, ddl in missing.items():
                conn.execute(text(f"ALTER TABLE account ADD COLUMN {name} {ddl}"))

    # loan 表新增列
    if "loan" in inspector.get_table_names():
        loan_cols = {c["name"] for c in inspector.get_columns("loan")}
        loan_new = {
            "item": "VARCHAR(64)",
            "interest_rate": "NUMERIC(6, 2)",
            "total_periods": "INTEGER",
            "remaining_periods": "INTEGER",
            "repay_method": "VARCHAR(16)",
            "currency": "VARCHAR(3) DEFAULT 'CNY'",
            "account_id": "INTEGER",
            "loan_kind": "VARCHAR(16)",
            "cash_account_id": "INTEGER",
            "interest_method": "VARCHAR(24)",
            "mgmt_fee_rate": "NUMERIC(6, 2)",
            "term_value": "INTEGER",
            "term_unit": "VARCHAR(8)",
            "collect_interval": "INTEGER",
            "collect_interval_unit": "VARCHAR(8)",
            "collected_periods": "INTEGER",
            "per_interest": "NUMERIC(15, 2)",
            "remaining_principal_interest": "NUMERIC(15, 2)",
            "first_collect_at": "DATETIME",
            "auto_execute": "BOOLEAN DEFAULT 0",
        }
        loan_missing = {n: d for n, d in loan_new.items() if n not in loan_cols}
        if loan_missing:
            with engine.begin() as conn:
                for name, ddl in loan_missing.items():
                    conn.execute(text(f"ALTER TABLE loan ADD COLUMN {name} {ddl}"))

    # transaction 表新增列（证券交易逐笔参数）
    if "transaction" in inspector.get_table_names():
        txn_cols = {c["name"] for c in inspector.get_columns("transaction")}
        txn_new = {
            "trade_price": "NUMERIC(15, 4)",
            "trade_qty": "NUMERIC(18, 4)",
            "trade_commission": "NUMERIC(15, 2)",
            "trade_fee": "NUMERIC(15, 2)",
            "trade_cost": "NUMERIC(18, 2)",
            "trade_symbol": "VARCHAR(32)",
            "trade_exchange_rate": "NUMERIC(10, 4)",
            "loan_id": "INTEGER",
            "collect_group": "VARCHAR(32)",
            "insurance_activity": "VARCHAR(16)",
            "ipo_status": "VARCHAR(12)",
        }
        txn_missing = {n: d for n, d in txn_new.items() if n not in txn_cols}
        if txn_missing:
            with engine.begin() as conn:
                for name, ddl in txn_missing.items():
                    conn.execute(text(f'ALTER TABLE "transaction" ADD COLUMN {name} {ddl}'))

    # party 表新增列（人员资料）
    if "party" in inspector.get_table_names():
        party_cols = {c["name"] for c in inspector.get_columns("party")}
        party_new = {
            "gender": "VARCHAR(8)",
            "birthday_type": "VARCHAR(8)",
            "birthday": "VARCHAR(10)",
        }
        party_missing = {n: d for n, d in party_new.items() if n not in party_cols}
        if party_missing:
            with engine.begin() as conn:
                for name, ddl in party_missing.items():
                    conn.execute(text(f"ALTER TABLE party ADD COLUMN {name} {ddl}"))

    # instrument 表新增列（基金费率）
    if "instrument" in inspector.get_table_names():
        inst_cols = {c["name"] for c in inspector.get_columns("instrument")}
        inst_new = {
            "buy_fee_rate": "NUMERIC(8, 4)",
            "redeem_fee_rate": "NUMERIC(8, 4)",
            "issuer": "VARCHAR(64)",
            "start_date": "VARCHAR(10)",
            "end_date": "VARCHAR(10)",
            "term_value": "INTEGER",
            "term_unit": "VARCHAR(8)",
            "expected_rate": "NUMERIC(8, 4)",
            "guaranteed": "BOOLEAN DEFAULT 0",
            "owner": "VARCHAR(64)",
            "asset_nature": "VARCHAR(16)",
            "subcategory": "VARCHAR(32)",
        }
        inst_missing = {n: d for n, d in inst_new.items() if n not in inst_cols}
        if inst_missing:
            with engine.begin() as conn:
                for name, ddl in inst_missing.items():
                    conn.execute(text(f"ALTER TABLE instrument ADD COLUMN {name} {ddl}"))


_ensure_columns()
seed()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
for module in (ledgers, accounts, categories, transactions, stats, budgets, holdings, loans, trades, instruments, currencies, plans, market):
    app.include_router(module.router, prefix=settings.api_prefix)


@app.get(f"{settings.api_prefix}/health")
def health():
    return {"status": "ok"}


# ---------- 托管前端打包产物（单进程模式） ----------
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        target = DIST / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
