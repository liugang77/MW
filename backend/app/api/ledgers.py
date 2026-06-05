from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.db import get_db

router = APIRouter(prefix="/ledgers", tags=["ledgers"])


@router.get("", response_model=list[schemas.LedgerOut])
def list_ledgers(db: Session = Depends(get_db)):
    return (
        db.query(models.Ledger)
        .filter(models.Ledger.deleted_at.is_(None))
        .order_by(models.Ledger.is_default.desc(), models.Ledger.id)
        .all()
    )


@router.post("", response_model=schemas.LedgerOut)
def create_ledger(payload: schemas.LedgerCreate, db: Session = Depends(get_db)):
    is_first = db.query(models.Ledger).count() == 0
    ledger = models.Ledger(**payload.model_dump(), is_default=is_first)
    db.add(ledger)
    db.commit()
    db.refresh(ledger)
    # 为新账本创建独立数据文件、建表并初始化默认分类与账户
    from app.seed import seed_ledger_defaults

    seed_ledger_defaults(ledger.id)
    return ledger


@router.put("/{ledger_id}", response_model=schemas.LedgerOut)
def update_ledger(ledger_id: int, payload: schemas.LedgerUpdate, db: Session = Depends(get_db)):
    ledger = db.get(models.Ledger, ledger_id)
    if not ledger:
        raise HTTPException(404, "账本不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(ledger, k, v)
    db.commit()
    db.refresh(ledger)
    return ledger


@router.delete("/{ledger_id}")
def delete_ledger(ledger_id: int, db: Session = Depends(get_db)):
    """删除账本：移除账本记录、其分类与独立数据文件。

    删除后返回应切换到的账本 id：
      - 若仍有其他账本，切换到其中一个（优先默认账本）。
      - 若删除的是最后一个账本，则自动新建一个空的初始账本并切换过去。
    """
    from app.core import db as core_db
    from app.core.config import settings
    from app.seed import seed_ledger_defaults

    ledger = db.get(models.Ledger, ledger_id)
    if not ledger:
        raise HTTPException(404, "账本不存在")

    was_default = ledger.is_default

    # 删除该账本在通用库中的分类
    db.query(models.Category).filter(models.Category.ledger_id == ledger_id).delete()
    # 删除账本记录
    db.delete(ledger)
    db.commit()

    # 物理删除账本独立数据文件
    core_db._initialized_ledgers.discard(ledger_id)
    db_file = settings.ledger_db_path(ledger_id)
    try:
        if db_file.exists():
            db_file.unlink()
    except OSError:
        pass

    # 选择切换目标账本
    nxt = db.query(models.Ledger).order_by(models.Ledger.id).first()
    if nxt is None:
        # 删除的是最后一个账本：新建一个空的初始账本
        nxt = models.Ledger(name="日常账本", is_default=True, remark="默认账本")
        db.add(nxt)
        db.commit()
        db.refresh(nxt)
        seed_ledger_defaults(nxt.id)
    elif was_default:
        nxt.is_default = True
        db.commit()

    return {"detail": "已删除", "next_ledger_id": nxt.id}
