from contextlib import contextmanager

from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

# 使用 NullPool：每个会话使用全新连接，避免连接池复用导致的 ATTACH 残留
# （SQLite 本地文件连接开销极小）。
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# 每个账本独立文件附加时使用的 schema 别名（与 models 中 __table_args__ 保持一致）
LEDGER_SCHEMA = "ledger"

# 记录已建表的账本文件，避免每次请求重复 create_all
_initialized_ledgers: set[int] = set()


def _common_tables():
    """通用库（common.db）中的表：schema 为 None 的全部表。"""
    return [t for t in Base.metadata.sorted_tables if t.schema is None]


def _ledger_tables():
    """每个账本独立库中的表：schema == 'ledger' 的全部表。"""
    return [t for t in Base.metadata.sorted_tables if t.schema == LEDGER_SCHEMA]


def init_common_db() -> None:
    """在 common.db 中创建通用表。"""
    Base.metadata.create_all(bind=engine, tables=_common_tables())


def _ensure_ledger_tables(connection, ledger_id: int) -> None:
    if ledger_id in _initialized_ledgers:
        return
    Base.metadata.create_all(bind=connection, tables=_ledger_tables())
    _ensure_ledger_columns(connection)
    _initialized_ledgers.add(ledger_id)


def _ensure_ledger_columns(connection) -> None:
    """轻量迁移：为既有账本库补充新增列。忽略已存在列（防并发重入）。"""
    raw = connection.connection
    cur = raw.cursor()

    def safe_add(sql: str) -> None:
        try:
            cur.execute(sql)
        except Exception:
            pass  # 列已存在（并发或重入）时安全忽略

    try:
        cur.execute("PRAGMA ledger.table_info('transaction')")
        cols = {row[1] for row in cur.fetchall()}
        if "split_group" not in cols:
            safe_add('ALTER TABLE ledger."transaction" ADD COLUMN split_group VARCHAR(32)')
        if "insurance_activity" not in cols:
            safe_add('ALTER TABLE ledger."transaction" ADD COLUMN insurance_activity VARCHAR(16)')
        if "ipo_status" not in cols:
            safe_add('ALTER TABLE ledger."transaction" ADD COLUMN ipo_status VARCHAR(12)')
        if "trade_exchange_rate" not in cols:
            safe_add('ALTER TABLE ledger."transaction" ADD COLUMN trade_exchange_rate NUMERIC(10, 4)')
        if "voucher_id" not in cols:
            safe_add('ALTER TABLE ledger."transaction" ADD COLUMN voucher_id INTEGER')
        # holding 表新增列
        cur.execute("PRAGMA ledger.table_info('holding')")
        hold_cols = {row[1] for row in cur.fetchall()}
        if "currency" not in hold_cols:
            safe_add('ALTER TABLE ledger.holding ADD COLUMN currency VARCHAR(3) DEFAULT \'CNY\'')
        # account 表新增列
        cur.execute("PRAGMA ledger.table_info('account')")
        acc_cols = {row[1] for row in cur.fetchall()}
        if "stock_market" not in acc_cols:
            safe_add("ALTER TABLE ledger.account ADD COLUMN stock_market VARCHAR(16)")
        if "asset_nature" not in acc_cols:
            safe_add("ALTER TABLE ledger.account ADD COLUMN asset_nature VARCHAR(16)")
    finally:
        cur.close()


def _attach_on_connection(connection, ledger_id: int) -> None:
    """在给定的 SQLAlchemy Connection 上附加账本文件并确保建表。

    直接在底层 DBAPI 连接上执行 ATTACH，使其在该连接的整个生命周期内有效，
    不受 ORM 事务提交/回滚影响。
    """
    path = settings.ledger_db_path(ledger_id)
    raw = connection.connection  # 原始 DBAPI 连接
    cur = raw.cursor()
    try:
        cur.execute("ATTACH DATABASE ? AS ledger", (str(path),))
    finally:
        cur.close()
    _ensure_ledger_tables(connection, ledger_id)


def _open_session(ledger_id: int | None):
    """打开一个绑定到独享连接的会话；如指定账本则附加其数据文件。

    返回 (session, connection)。调用方需在结束时关闭 session 与 connection。
    """
    connection = engine.connect()
    if ledger_id is not None:
        _attach_on_connection(connection, ledger_id)
    # 提交附加/建表带来的事务，使连接处于干净状态；ATTACH 为连接级，提交后依然有效。
    # 之后由会话自行管理事务，session.commit() 才能真正落盘。
    connection.commit()
    db = SessionLocal(bind=connection)
    return db, connection


def _close_session(db, connection) -> None:
    try:
        db.close()
    finally:
        connection.close()  # NullPool：连接关闭即销毁，附加随之失效


@contextmanager
def ledger_session(ledger_id: int):
    """脚本/种子使用：打开一个附加了指定账本文件的会话。"""
    db, connection = _open_session(ledger_id)
    try:
        yield db
    finally:
        _close_session(db, connection)


def get_db(request: Request):
    """FastAPI 依赖：根据请求头 X-Ledger-Id 附加对应账本文件。

    通用（仅 common）接口无需账本头部；涉及账本数据的接口由前端统一带上当前账本 id。
    """
    lid = None
    raw = request.headers.get("X-Ledger-Id")
    if raw and raw.isdigit():
        lid = int(raw)
    db, connection = _open_session(lid)
    try:
        yield db
    finally:
        _close_session(db, connection)

