from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, ForeignKey, Numeric, DateTime, Boolean, Integer, Text, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Ledger(Base):
    __tablename__ = "ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    icon: Mapped[str] = mapped_column(String(32), default="book")
    color: Mapped[str] = mapped_column(String(16), default="#409EFF")
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    remark: Mapped[str | None] = mapped_column(Text, default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class AccountGroup(Base):
    __tablename__ = "account_group"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    remark: Mapped[str | None] = mapped_column(Text, default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Party(Base):
    """人员与机构：家庭成员 / 往来人员 / 机构（含开户银行）。"""
    __tablename__ = "party"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(16), default="org")  # member / contact / org
    gender: Mapped[str | None] = mapped_column(String(8), default=None)  # male / female
    birthday_type: Mapped[str | None] = mapped_column(String(8), default=None)  # solar / lunar
    birthday: Mapped[str | None] = mapped_column(String(10), default=None)
    contact: Mapped[str | None] = mapped_column(String(128), default=None)
    address: Mapped[str | None] = mapped_column(String(255), default=None)


class Account(Base):
    __tablename__ = "account"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(24), default="cash")
    group_id: Mapped[int | None] = mapped_column(ForeignKey("ledger.account_group.id"), default=None)
    icon: Mapped[str] = mapped_column(String(32), default="wallet")
    color: Mapped[str] = mapped_column(String(16), default="#409EFF")
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), default=None)
    bill_day: Mapped[int | None] = mapped_column(Integer, default=None)
    repay_day: Mapped[int | None] = mapped_column(Integer, default=None)
    # 信用卡扩展信息
    owner: Mapped[str | None] = mapped_column(String(64), default=None)
    remark: Mapped[str | None] = mapped_column(Text, default=None)
    card_no: Mapped[str | None] = mapped_column(String(32), default=None)
    bank_name: Mapped[str | None] = mapped_column(String(64), default=None)
    start_date: Mapped[str | None] = mapped_column(String(10), default=None)
    expiry: Mapped[str | None] = mapped_column(String(8), default=None)
    cash_limit: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), default=None)
    min_repay_ratio: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), default=None)
    annual_fee: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), default=None)
    fee_waiver_type: Mapped[str] = mapped_column(String(12), default="count")  # count / amount / none
    fee_waiver_count: Mapped[int | None] = mapped_column(Integer, default=None)
    fee_waiver_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), default=None)
    repay_type: Mapped[str] = mapped_column(String(12), default="fixed")  # fixed / after_bill
    repay_after_days: Mapped[int | None] = mapped_column(Integer, default=None)
    bill_day_txn: Mapped[str] = mapped_column(String(8), default="next")  # next / current
    overdraft_remind: Mapped[bool] = mapped_column(Boolean, default=False)
    # 双币信用卡扩展
    bill_day_last: Mapped[bool] = mapped_column(Boolean, default=False)  # 每月最后一天是账单日
    currency2: Mapped[str | None] = mapped_column(String(3), default=None)  # 币种2
    overdraft1: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), default=None)  # 币种1已透支金额
    overdraft2: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), default=None)  # 币种2已透支金额
    overdraft_remind2: Mapped[bool] = mapped_column(Boolean, default=False)  # 币种2透支提醒
    # 投资/平台类扩展
    platform_name: Mapped[str | None] = mapped_column(String(64), default=None)
    platform_url: Mapped[str | None] = mapped_column(String(255), default=None)
    stock_market: Mapped[str | None] = mapped_column(String(16), default=None)  # 上市证券市场类型（A股/沪B/深B/H股/美股等）
    asset_nature: Mapped[str | None] = mapped_column(String(16), default=None)  # 重大资产性质 invest/own
    # 保险账户扩展
    insured_person: Mapped[str | None] = mapped_column(String(64), default=None)  # 参保人
    city: Mapped[str | None] = mapped_column(String(64), default=None)  # 城市
    social_code: Mapped[str | None] = mapped_column(String(64), default=None)  # 社保编码
    premium_as_stat: Mapped[bool] = mapped_column(Boolean, default=False)  # 将保费做为收支统计
    include_in_net: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(8), default="active")  # active / hidden / closed(注销)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledger.id"))
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(8))  # income / expense
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"), default=None)
    icon: Mapped[str] = mapped_column(String(32), default="tag")
    color: Mapped[str] = mapped_column(String(16), default="#909399")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Transaction(Base):
    __tablename__ = "transaction"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(12))  # expense / income / transfer
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    account_id: Mapped[int] = mapped_column(ForeignKey("ledger.account.id"))
    to_account_id: Mapped[int | None] = mapped_column(ForeignKey("ledger.account.id"), default=None)
    category_id: Mapped[int | None] = mapped_column(Integer, default=None)
    fee: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    remark: Mapped[str | None] = mapped_column(Text, default=None)
    merchant: Mapped[str | None] = mapped_column(String(128), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # 分拆收支：同一组明细共享的分组标识
    split_group: Mapped[str | None] = mapped_column(String(32), default=None)

    # 证券/基金交易逐笔参数（仅证券买卖记账时填写）
    trade_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), default=None)
    trade_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), default=None)
    trade_commission: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), default=None)
    trade_fee: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), default=None)
    trade_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), default=None)
    trade_symbol: Mapped[str | None] = mapped_column(String(32), default=None)
    trade_exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=None)

    # 保险记账活动类型：缴纳保费 / 保费返还 / 退保 / 保险分红
    insurance_activity: Mapped[str | None] = mapped_column(String(16), default=None)

    # 新股申购状态：pending(申购中/已冻结资金) / won(已中签建仓) / lost(未中签) / refund(申购返款)
    ipo_status: Mapped[str | None] = mapped_column(String(12), default=None)

    # 网贷流水与债权（Loan）的关联：用于删除/编辑时回滚项目状态
    loan_id: Mapped[int | None] = mapped_column(Integer, default=None)
    # 同一次网贷收回的本金+利息流水共享的分组标识
    collect_group: Mapped[str | None] = mapped_column(String(32), default=None)

    # 团购券（Voucher）的关联：购券/核销/退券流水回滚时恢复券状态
    voucher_id: Mapped[int | None] = mapped_column(Integer, default=None)

    tags: Mapped[list["Tag"]] = relationship(
        secondary=lambda: transaction_tag, lazy="selectin"
    )


transaction_tag = Table(
    "transaction_tag",
    Base.metadata,
    Column("transaction_id", ForeignKey("ledger.transaction.id"), primary_key=True),
    Column("tag_id", ForeignKey("ledger.tag.id"), primary_key=True),
    schema="ledger",
)


loan_tag = Table(
    "loan_tag",
    Base.metadata,
    Column("loan_id", ForeignKey("ledger.loan.id"), primary_key=True),
    Column("tag_id", ForeignKey("ledger.tag.id"), primary_key=True),
    schema="ledger",
)


class Tag(Base):
    """标签：将收支记录或资产按目的归类（人员、装修、育儿等）。"""
    __tablename__ = "tag"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(16), default="#3f79a8")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Budget(Base):
    __tablename__ = "budget"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(Integer)
    category_id: Mapped[int | None] = mapped_column(Integer, default=None)
    period: Mapped[str] = mapped_column(String(8), default="month")  # month / year
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Holding(Base):
    __tablename__ = "holding"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(Integer)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("ledger.account.id"), default=None)
    symbol: Mapped[str | None] = mapped_column(String(32), default=None)
    name: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(24), default="stock")  # stock/fund/bond/metal/forex...
    currency: Mapped[str] = mapped_column(String(3), default="CNY")  # 持仓币种（外币理财/外汇持仓为对应外币代码）
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    price: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Voucher(Base):
    """团购券：买入后作为预付资产计入账户余额；核销时确认支出（可补差价），
    到期未用可手动退货，本金退回原购买资金账户。

    账户余额铁律：团购券账户余额 = 所有未核销且未退货券的「剩余张数 × 实付单价」，
    由购券(转入)/核销(支出)/退券(转出)三类流水自动维护。
    """
    __tablename__ = "voucher"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(Integer)
    account_id: Mapped[int] = mapped_column(ForeignKey("ledger.account.id"))  # 所属团购券账户
    product: Mapped[str] = mapped_column(String(128))  # 商品名称
    quantity: Mapped[int] = mapped_column(Integer, default=1)  # 购买张数
    redeemed: Mapped[int] = mapped_column(Integer, default=0)  # 已核销张数
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)  # 单张实付价（成本/优惠后）
    face_value: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)  # 单张面值（实际价值）
    source_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("ledger.account.id"), default=None
    )  # 购买资金账户（= 退货退款目标）
    purchased_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    expiry_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)  # 有效期截止
    category_id: Mapped[int | None] = mapped_column(Integer, default=None)  # 默认核销支出分类
    status: Mapped[str] = mapped_column(String(12), default="active")  # active / used / expired / refunded
    remark: Mapped[str | None] = mapped_column(Text, default=None)


class Loan(Base):
    __tablename__ = "loan"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(Integer)
    direction: Mapped[str] = mapped_column(String(12), default="receivable")  # receivable(应收/借出) / payable(应付/借入)
    counterparty: Mapped[str] = mapped_column(String(64))
    item: Mapped[str | None] = mapped_column(String(64), default=None)  # 款项（垫付/外借/房款…）
    currency: Mapped[str] = mapped_column(String(3), default="CNY")  # 币种
    account_id: Mapped[int | None] = mapped_column(ForeignKey("ledger.account.id"), default=None)  # 收入/支出账户
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    settled: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), default=None)  # 利率 %
    total_periods: Mapped[int | None] = mapped_column(Integer, default=None)  # 总期数
    remaining_periods: Mapped[int | None] = mapped_column(Integer, default=None)  # 剩余期数
    repay_method: Mapped[str | None] = mapped_column(String(16), default=None)  # 收/还款方式
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    remark: Mapped[str | None] = mapped_column(Text, default=None)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)

    # 网贷（P2P）专用字段
    loan_kind: Mapped[str | None] = mapped_column(String(16), default=None)  # normal / p2p
    cash_account_id: Mapped[int | None] = mapped_column(ForeignKey("ledger.account.id"), default=None)  # 资金账户
    interest_method: Mapped[str | None] = mapped_column(String(24), default=None)  # 计息方式
    mgmt_fee_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), default=None)  # 管理费率 %
    term_value: Mapped[int | None] = mapped_column(Integer, default=None)  # 借出期限
    term_unit: Mapped[str | None] = mapped_column(String(8), default=None)  # 借出期限单位 day/month/year
    collect_interval: Mapped[int | None] = mapped_column(Integer, default=None)  # 收款间隔
    collect_interval_unit: Mapped[str | None] = mapped_column(String(8), default=None)  # 收款间隔单位
    collected_periods: Mapped[int | None] = mapped_column(Integer, default=None)  # 已收款期数
    per_interest: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), default=None)  # 每期还息
    remaining_principal_interest: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), default=None)  # 剩余本息
    first_collect_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)  # 首次收款日
    auto_execute: Mapped[bool] = mapped_column(Boolean, default=False)  # 收款计划到期自动执行

    tags: Mapped[list["Tag"]] = relationship(secondary=lambda: loan_tag, lazy="selectin")
    rate_adjustments: Mapped[list["LoanRateAdjustment"]] = relationship(
        back_populates="loan", cascade="all, delete-orphan", lazy="selectin"
    )


class LoanRateAdjustment(Base):
    __tablename__ = "loan_rate_adjustment"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(Integer)
    loan_id: Mapped[int] = mapped_column(ForeignKey("ledger.loan.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    remark: Mapped[str | None] = mapped_column(String(128), default=None)

    loan: Mapped["Loan"] = relationship(back_populates="rate_adjustments")



class Instrument(Base):
    """金融产品资料：上市证券/开放式基金/货币基金/债券/贵金属/银行理财/期货等。"""
    __tablename__ = "instrument"

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledger.id"))
    category: Mapped[str] = mapped_column(String(24), default="securities")
    code: Mapped[str | None] = mapped_column(String(32), default=None)
    name: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    buy_fee_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), default=None)
    redeem_fee_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), default=None)
    issuer: Mapped[str | None] = mapped_column(String(64), default=None)  # 发行机构
    start_date: Mapped[str | None] = mapped_column(String(10), default=None)  # 收益起始日
    end_date: Mapped[str | None] = mapped_column(String(10), default=None)  # 收益终止日
    term_value: Mapped[int | None] = mapped_column(Integer, default=None)  # 委托期数值
    term_unit: Mapped[str | None] = mapped_column(String(8), default=None)  # 委托期单位 day/month
    expected_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), default=None)  # 预期年收益率 %
    guaranteed: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否保本
    owner: Mapped[str | None] = mapped_column(String(64), default=None)  # 所有者（重大资产）
    asset_nature: Mapped[str | None] = mapped_column(String(16), default=None)  # 资产性质 invest/own（重大资产）
    subcategory: Mapped[str | None] = mapped_column(String(32), default=None)  # 分类（家居物品）
    remark: Mapped[str | None] = mapped_column(Text, default=None)


class InstrumentPrice(Base):
    """金融产品每日价格 / 基金净值。"""
    __tablename__ = "instrument_price"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument.id"))
    price_date: Mapped[str] = mapped_column(String(10))
    price: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=0)


class TradeFeeRate(Base):
    """证券交易费率：按市场分组（A股 / B股）的全局费率设置。"""
    __tablename__ = "trade_fee_rate"

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledger.id"))
    group_key: Mapped[str] = mapped_column(String(16))  # a_share / b_share
    security_type: Mapped[str] = mapped_column(String(64))  # 证券类型
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    buy_stamp_tax: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)      # 买入印花税
    sell_stamp_tax: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)     # 卖出印花税
    buy_commission: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)     # 买入佣金
    buy_min_commission: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0) # 买入最低佣金
    sell_commission: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)    # 卖出佣金
    sell_min_commission: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)# 卖出最低佣金
    surcharge: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)          # 附加费(A股)
    transfer_fee: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)       # 过户费(A股)
    settle_fee: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)         # 结算费%(B股)
    settle_cap: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)         # 结算费上限(B股)
    trade_reg_fee: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)      # 交易规费%(B股)


class Currency(Base):
    """币种资料：名称 / 英文缩写 / 对人民币牌价 / 是否本币。"""
    __tablename__ = "currency"

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledger.id"))
    name: Mapped[str] = mapped_column(String(32))
    code: Mapped[str] = mapped_column(String(8))
    is_home: Mapped[bool] = mapped_column(Boolean, default=False)  # 本币
    rate: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=1)  # 对人民币牌价
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ExchangeRate(Base):
    """汇率历史：某币种相对本币（人民币）在某日期的牌价。"""
    __tablename__ = "exchange_rate"

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledger.id"))
    rate_date: Mapped[str] = mapped_column(String(10))
    currency_code: Mapped[str] = mapped_column(String(8))  # 报价币种
    base_code: Mapped[str] = mapped_column(String(8), default="CNY")  # 基准币种
    rate: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=0)  # 牌价/汇率


class DepositRate(Base):
    """存款利率：人民币按储蓄类型/期间，外币按币种/期限。"""
    __tablename__ = "deposit_rate"

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledger.id"))
    group_key: Mapped[str] = mapped_column(String(16))  # cny / foreign
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # 人民币：储蓄类型 + 期间 + 年利率
    save_type: Mapped[str | None] = mapped_column(String(32), default=None)  # 储蓄类型
    term: Mapped[str | None] = mapped_column(String(32), default=None)       # 储蓄期间
    rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)          # 年利率(%)
    # 外币：按币种一行，多期限列
    currency_code: Mapped[str | None] = mapped_column(String(8), default=None)  # 币种代码
    currency_name: Mapped[str | None] = mapped_column(String(32), default=None) # 币种名称
    r_current: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)   # 活期
    r_1m: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)        # 一个月
    r_3m: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)        # 三个月
    r_6m: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)        # 半年
    r_1y: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)        # 一年
    r_2y: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)        # 两年
    r_7d_notice: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0) # 七天通知存款


plan_tag = Table(
    "plan_tag",
    Base.metadata,
    Column("plan_id", ForeignKey("ledger.plan.id"), primary_key=True),
    Column("tag_id", ForeignKey("ledger.tag.id"), primary_key=True),
    schema="ledger",
)


class Plan(Base):
    """财务计划与提醒：提醒 / 收支计划 / 转账计划 / 基金定投，及贷款/网贷的周期收付计划。"""
    __tablename__ = "plan"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(Integer)
    # reminder / income_expense / transfer / fund_invest / loan_repay / p2p_collect
    plan_type: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(128))
    # once / daily / weekly / monthly / quarterly / yearly
    frequency: Mapped[str] = mapped_column(String(12), default="once")
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str | None] = mapped_column(String(10), default=None)
    next_run_date: Mapped[str | None] = mapped_column(String(10), default=None)
    status: Mapped[str] = mapped_column(String(12), default="active")  # active/done/paused
    auto_execute: Mapped[bool] = mapped_column(Boolean, default=False)
    remind_days: Mapped[int] = mapped_column(Integer, default=0)  # 提前N天提醒

    # 资金相关（收支/转账/基金/网贷）
    account_id: Mapped[int | None] = mapped_column(ForeignKey("ledger.account.id"), default=None)       # 资金/转出/基金/网贷账户
    to_account_id: Mapped[int | None] = mapped_column(ForeignKey("ledger.account.id"), default=None)    # 转入/收入账户
    fee_account_id: Mapped[int | None] = mapped_column(ForeignKey("ledger.account.id"), default=None)   # 手续费账户
    category_id: Mapped[int | None] = mapped_column(Integer, default=None)     # 收支项目
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    fee: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    txn_type: Mapped[str | None] = mapped_column(String(12), default=None)  # 收支计划：income/expense

    # 基金定投
    instrument_id: Mapped[int | None] = mapped_column(Integer, default=None)
    fund_symbol: Mapped[str | None] = mapped_column(String(64), default=None)
    fee_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), default=None)  # 申购费率 %

    # 贷款/网贷关联
    loan_id: Mapped[int | None] = mapped_column(ForeignKey("ledger.loan.id"), default=None)

    remark: Mapped[str | None] = mapped_column(Text, default=None)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    tags: Mapped[list["Tag"]] = relationship(secondary=lambda: plan_tag, lazy="selectin")




