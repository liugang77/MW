"""账本数据导入 / 导出。

导出：将一个账本的全部数据打包为 JSON——包含
  - 账本记录（通用库 ledger）
  - 该账本的通用数据（分类、币种、汇率、存款利率、证券费率、金融产品资料及其同步价格）
  - 该账本独立数据文件中的全部业务数据（账户/人员/流水/标签/预算/持仓/团购券/借贷/计划等）

导入：先彻底清除「对应账本」（同 id 的通用行 + 独立数据文件），再完整重建。
  - 通用库主键全部重映射为新自增 id（避免跨机器导入时与其它账本主键冲突），
    并同步改写引用（流水/预算/团购券/计划的 category_id、计划的 instrument_id、价格的 instrument_id、分类 parent_id）。
  - 账本独立文件整库重建，文件内 id 原样保留（单账本文件内不存在跨账本冲突）。
"""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import Numeric, DateTime, Boolean, Integer

from app import models
from app.core import db as core_db
from app.core.config import settings
from app.core.db import SessionLocal, ledger_session

router = APIRouter(prefix="/ledgers", tags=["ledger-io"])

EXPORT_FORMAT = "mw-ledger"
EXPORT_VERSION = 1

# 通用库（common.db）中按 ledger_id 归属的表
_COMMON_MODELS = [
    ("category", models.Category),
    ("currency", models.Currency),
    ("exchange_rate", models.ExchangeRate),
    ("deposit_rate", models.DepositRate),
    ("trade_fee_rate", models.TradeFeeRate),
    ("instrument", models.Instrument),
]
# 账本独立文件（ledger_{id}.db）中的 ORM 表（整库导出，按 FK 安全顺序导入）
_LEDGER_MODELS = [
    ("account_group", models.AccountGroup),
    ("party", models.Party),
    ("account", models.Account),
    ("tag", models.Tag),
    ("transaction", models.Transaction),
    ("budget", models.Budget),
    ("holding", models.Holding),
    ("voucher", models.Voucher),
    ("loan", models.Loan),
    ("loan_rate_adjustment", models.LoanRateAdjustment),
    ("plan", models.Plan),
]
# 账本独立文件中的多对多关联表（Core Table）
_LEDGER_M2M = [
    ("transaction_tag", models.transaction_tag),
    ("loan_tag", models.loan_tag),
    ("plan_tag", models.plan_tag),
]


def _enc(v):
    """序列化为 JSON 友好类型。"""
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _row_dict(obj) -> dict:
    return {c.name: _enc(getattr(obj, c.name)) for c in obj.__table__.columns}


def _coerce(col, v):
    """按列类型把 JSON 值还原为合适的 Python 类型。"""
    if v is None:
        return None
    t = col.type
    if isinstance(t, DateTime):
        return datetime.fromisoformat(v) if isinstance(v, str) else v
    if isinstance(t, Numeric):
        return Decimal(str(v))
    if isinstance(t, Boolean):
        return bool(v)
    if isinstance(t, Integer):
        return int(v)
    return v


def _build_kwargs(model, row: dict, *, drop_id: bool = False, overrides: dict | None = None) -> dict:
    kwargs = {}
    for c in model.__table__.columns:
        if drop_id and c.name == "id":
            continue
        if c.name in row:
            kwargs[c.name] = _coerce(c, row[c.name])
    if overrides:
        kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------- 导出
@router.get("/{ledger_id}/export")
def export_ledger(ledger_id: int):
    com = SessionLocal()
    try:
        ledger = com.get(models.Ledger, ledger_id)
        if not ledger:
            raise HTTPException(404, "账本不存在")
        data = {
            "format": EXPORT_FORMAT,
            "version": EXPORT_VERSION,
            "exported_at": datetime.now().isoformat(),
            "ledger": _row_dict(ledger),
            "common": {},
            "ledger_data": {},
        }
        for key, model in _COMMON_MODELS:
            rows = com.query(model).filter(model.ledger_id == ledger_id).all()
            data["common"][key] = [_row_dict(r) for r in rows]
        # 金融产品同步价格：无 ledger_id，按本账本的产品 id 过滤
        inst_ids = [r["id"] for r in data["common"]["instrument"]]
        if inst_ids:
            prices = (
                com.query(models.InstrumentPrice)
                .filter(models.InstrumentPrice.instrument_id.in_(inst_ids))
                .all()
            )
            data["common"]["instrument_price"] = [_row_dict(p) for p in prices]
        else:
            data["common"]["instrument_price"] = []
    finally:
        com.close()

    # 账本独立文件：整库导出（该文件仅含本账本数据，无需过滤）
    with ledger_session(ledger_id) as ldb:
        for key, model in _LEDGER_MODELS:
            data["ledger_data"][key] = [_row_dict(r) for r in ldb.query(model).all()]
        for key, table in _LEDGER_M2M:
            rows = ldb.execute(table.select()).mappings().all()
            data["ledger_data"][key] = [dict(r) for r in rows]
    return data


# ---------------------------------------------------------------- 导入
@router.post("/import")
def import_ledger(payload: dict):
    if payload.get("format") != EXPORT_FORMAT:
        raise HTTPException(400, "文件格式不正确，不是有效的账本导出文件")
    ledger_row = payload.get("ledger") or {}
    lid = ledger_row.get("id")
    if not isinstance(lid, int):
        raise HTTPException(400, "导出文件缺少账本标识")

    common = payload.get("common") or {}
    ledger_data = payload.get("ledger_data") or {}

    com = SessionLocal()
    cat_map: dict[int, int] = {}
    inst_map: dict[int, int] = {}
    try:
        # 1) 清除对应账本在通用库中的全部数据 + 账本记录
        inst_ids = [
            r[0] for r in com.query(models.Instrument.id).filter(models.Instrument.ledger_id == lid).all()
        ]
        if inst_ids:
            com.query(models.InstrumentPrice).filter(
                models.InstrumentPrice.instrument_id.in_(inst_ids)
            ).delete(synchronize_session=False)
        for model in (
            models.Category, models.Currency, models.ExchangeRate,
            models.DepositRate, models.TradeFeeRate, models.Instrument,
        ):
            com.query(model).filter(model.ledger_id == lid).delete(synchronize_session=False)
        existing = com.get(models.Ledger, lid)
        if existing:
            com.delete(existing)
        com.flush()

        # 2) 重建账本记录（保留原 id）
        ledger = models.Ledger(**_build_kwargs(models.Ledger, ledger_row))
        ledger.deleted_at = None
        com.add(ledger)
        com.flush()

        # 3) 通用数据：分类与产品主键重映射；其余表用新自增 id
        for row in common.get("category", []):
            obj = models.Category(**_build_kwargs(
                models.Category, row, drop_id=True,
                overrides={"ledger_id": lid, "parent_id": None},
            ))
            com.add(obj)
            com.flush()
            cat_map[row.get("id")] = obj.id
        # 二次回填分类父子关系
        for row in common.get("category", []):
            pid = row.get("parent_id")
            old = row.get("id")
            if pid is not None and old in cat_map and pid in cat_map:
                com.query(models.Category).filter(models.Category.id == cat_map[old]).update(
                    {"parent_id": cat_map[pid]}, synchronize_session=False
                )

        for row in common.get("instrument", []):
            obj = models.Instrument(**_build_kwargs(
                models.Instrument, row, drop_id=True, overrides={"ledger_id": lid},
            ))
            com.add(obj)
            com.flush()
            inst_map[row.get("id")] = obj.id
        for row in common.get("instrument_price", []):
            new_iid = inst_map.get(row.get("instrument_id"))
            if new_iid is None:
                continue
            com.add(models.InstrumentPrice(**_build_kwargs(
                models.InstrumentPrice, row, drop_id=True, overrides={"instrument_id": new_iid},
            )))

        for key, model in (
            ("currency", models.Currency), ("exchange_rate", models.ExchangeRate),
            ("deposit_rate", models.DepositRate), ("trade_fee_rate", models.TradeFeeRate),
        ):
            for row in common.get(key, []):
                com.add(model(**_build_kwargs(model, row, drop_id=True, overrides={"ledger_id": lid})))
        com.commit()
    except Exception as exc:  # noqa: BLE001
        com.rollback()
        com.close()
        raise HTTPException(500, f"导入通用数据失败：{exc}") from exc
    finally:
        if com.is_active:
            com.close()

    # 4) 重建账本独立数据文件（先删除旧文件，ledger_session 会自动重建空表）
    core_db._initialized_ledgers.discard(lid)
    db_file = settings.ledger_db_path(lid)
    try:
        if db_file.exists():
            db_file.unlink()
    except OSError as exc:
        raise HTTPException(500, f"无法清除原账本数据文件：{exc}") from exc

    with ledger_session(lid) as ldb:
        for key, model in _LEDGER_MODELS:
            rewrite: dict[str, dict[int, int]] = {}
            if key in ("transaction", "budget", "voucher"):
                rewrite["category_id"] = cat_map
            if key == "plan":
                rewrite["category_id"] = cat_map
                rewrite["instrument_id"] = inst_map
            for row in ledger_data.get(key, []):
                kwargs = _build_kwargs(model, row, overrides={"ledger_id": lid})
                for field, mapping in rewrite.items():
                    if field in kwargs and kwargs[field] is not None:
                        kwargs[field] = mapping.get(kwargs[field])
                ldb.add(model(**kwargs))
            ldb.flush()
        for key, table in _LEDGER_M2M:
            rows = ledger_data.get(key, [])
            if rows:
                ldb.execute(table.insert(), [dict(r) for r in rows])
        ldb.commit()

    return {"detail": "导入成功", "ledger_id": lid, "ledger_name": ledger_row.get("name")}
