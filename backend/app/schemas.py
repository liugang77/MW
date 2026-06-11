from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# ---------- Ledger ----------
class LedgerBase(BaseModel):
    name: str
    icon: str = "book"
    color: str = "#409EFF"
    currency: str = "CNY"
    remark: str | None = None


class LedgerCreate(LedgerBase):
    pass


class LedgerUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    color: str | None = None
    currency: str | None = None
    remark: str | None = None


class LedgerOut(LedgerBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_default: bool


# ---------- AccountGroup ----------
class AccountGroupBase(BaseModel):
    name: str
    remark: str | None = None
    sort_order: int = 0


class AccountGroupCreate(AccountGroupBase):
    pass


class AccountGroupOut(AccountGroupBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int


# ---------- Party 人员与机构 ----------
class PartyBase(BaseModel):
    name: str
    type: str = "org"  # member / contact / org
    gender: str | None = None  # male / female
    birthday_type: str | None = None  # solar / lunar
    birthday: str | None = None
    contact: str | None = None
    address: str | None = None


class PartyCreate(PartyBase):
    pass


class PartyUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    gender: str | None = None
    birthday_type: str | None = None
    birthday: str | None = None
    contact: str | None = None
    address: str | None = None


class PartyOut(PartyBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int


# ---------- Account ----------
class AccountBase(BaseModel):
    name: str
    type: str = "cash"
    group_id: int | None = None
    icon: str = "wallet"
    color: str = "#409EFF"
    currency: str = "CNY"
    initial_balance: Decimal = Decimal("0")
    credit_limit: Decimal | None = None
    bill_day: int | None = None
    repay_day: int | None = None
    owner: str | None = None
    remark: str | None = None
    card_no: str | None = None
    bank_name: str | None = None
    start_date: str | None = None
    expiry: str | None = None
    cash_limit: Decimal | None = None
    min_repay_ratio: Decimal | None = None
    annual_fee: Decimal | None = None
    fee_waiver_type: str = "count"
    fee_waiver_count: int | None = None
    fee_waiver_amount: Decimal | None = None
    repay_type: str = "fixed"
    repay_after_days: int | None = None
    bill_day_txn: str = "next"
    overdraft_remind: bool = False
    bill_day_last: bool = False
    currency2: str | None = None
    overdraft1: Decimal | None = None
    overdraft2: Decimal | None = None
    overdraft_remind2: bool = False
    platform_name: str | None = None
    platform_url: str | None = None
    insured_person: str | None = None
    city: str | None = None
    social_code: str | None = None
    premium_as_stat: bool = False
    stock_market: str | None = None
    asset_nature: str | None = None
    include_in_net: bool = True


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    group_id: int | None = None
    icon: str | None = None
    color: str | None = None
    credit_limit: Decimal | None = None
    bill_day: int | None = None
    repay_day: int | None = None
    owner: str | None = None
    remark: str | None = None
    card_no: str | None = None
    bank_name: str | None = None
    start_date: str | None = None
    expiry: str | None = None
    cash_limit: Decimal | None = None
    min_repay_ratio: Decimal | None = None
    annual_fee: Decimal | None = None
    fee_waiver_type: str | None = None
    fee_waiver_count: int | None = None
    fee_waiver_amount: Decimal | None = None
    repay_type: str | None = None
    repay_after_days: int | None = None
    bill_day_txn: str | None = None
    overdraft_remind: bool | None = None
    bill_day_last: bool | None = None
    currency2: str | None = None
    overdraft1: Decimal | None = None
    overdraft2: Decimal | None = None
    overdraft_remind2: bool | None = None
    platform_name: str | None = None
    platform_url: str | None = None
    include_in_net: bool | None = None
    insured_person: str | None = None
    city: str | None = None
    social_code: str | None = None
    premium_as_stat: bool | None = None
    stock_market: str | None = None
    asset_nature: str | None = None
    is_active: bool | None = None
    status: str | None = None
    sort_order: int | None = None


class AccountOut(AccountBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int
    current_balance: Decimal
    is_active: bool
    status: str = "active"
    sort_order: int


class BalanceAdjust(BaseModel):
    target_balance: Decimal
    mode: str = "adjust"  # adjust(记为余额调整) / income_expense(记为收支)


class MajorAssetBuy(BaseModel):
    """重大资产买入：创建资产账户并记录出资（支付账户 + 所选贷款）。"""
    name: str
    owner: str | None = None
    currency: str = "CNY"
    asset_nature: str = "invest"  # invest / own
    total: Decimal
    payment_account_id: int | None = None
    loan_ids: list[int] = []
    tag_ids: list[int] = []
    remark: str | None = None
    occurred_at: str | None = None


# ---------- Category ----------
class CategoryBase(BaseModel):
    name: str
    kind: str  # income / expense
    parent_id: int | None = None
    icon: str = "tag"
    color: str = "#909399"
    sort_order: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    color: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class CategoryOut(CategoryBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int
    is_active: bool


# ---------- Transaction ----------
class TransactionBase(BaseModel):
    type: str  # expense / income / transfer
    amount: Decimal
    currency: str = "CNY"
    account_id: int
    to_account_id: int | None = None
    category_id: int | None = None
    fee: Decimal = Decimal("0")
    occurred_at: datetime | None = None
    remark: str | None = None
    merchant: str | None = None
    insurance_activity: str | None = None


class TransactionCreate(TransactionBase):
    tag_ids: list[int] = []


class TransactionUpdate(BaseModel):
    type: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    account_id: int | None = None
    to_account_id: int | None = None
    category_id: int | None = None
    fee: Decimal | None = None
    occurred_at: datetime | None = None
    remark: str | None = None
    merchant: str | None = None
    tag_ids: list[int] | None = None


class TransactionOut(TransactionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int
    occurred_at: datetime
    created_at: datetime
    trade_price: Decimal | None = None
    trade_qty: Decimal | None = None
    trade_commission: Decimal | None = None
    trade_fee: Decimal | None = None
    trade_cost: Decimal | None = None
    trade_symbol: str | None = None
    trade_exchange_rate: Decimal | None = None
    loan_id: int | None = None
    collect_group: str | None = None
    ipo_status: str | None = None
    tag_ids: list[int] = []
    split_group: str | None = None


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int


# ---------- 保险明细（后台计算） ----------
class InsuranceTxnRow(BaseModel):
    id: int
    occurred_at: datetime
    type: str
    premium: Decimal      # 缴费
    collect: Decimal      # 领取
    activity: str         # 活动类型
    remark: str | None = None


class InsuranceDetailOut(BaseModel):
    account_id: int
    cash_value: Decimal     # 现金价值（= 当前余额）
    premium_total: Decimal  # 缴费总额
    collect_total: Decimal  # 领取总额
    count: int              # 记录数
    rows: list[InsuranceTxnRow]


# ---------- Tag 标签 ----------
class TagBase(BaseModel):
    name: str
    color: str = "#3f79a8"
    sort_order: int = 0


class TagCreate(TagBase):
    pass


class TagOut(TagBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int


# ---------- 分拆收支 ----------
class SplitItem(BaseModel):
    category_id: int | None = None
    amount: Decimal
    remark: str | None = None
    tag_ids: list[int] = []


class SplitCreate(BaseModel):
    type: str = "expense"  # expense / income
    account_id: int
    occurred_at: datetime | None = None
    items: list[SplitItem]


# ---------- 工资收入 ----------
class SalaryItem(BaseModel):
    category_id: int | None = None
    name: str | None = None       # 项目名称（无分类时用作备注，如「基本工资」「个税」）
    amount: Decimal


class SalaryCreate(BaseModel):
    account_id: int               # 收入账户（到账账户）
    currency: str = "CNY"
    incomes: list[SalaryItem]     # 收入项目（基本工资/奖金/津贴…）
    deductions: list[SalaryItem] = []  # 扣款项目（个税/社保/公积金…）
    insured_person: str | None = None  # 社保人员
    occurred_at: datetime | None = None
    remark: str | None = None
    tag_ids: list[int] = []


# ---------- 转账（含手续费账户） ----------
class TransferCreate(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: Decimal
    fee: Decimal = Decimal("0")
    fee_account_id: int | None = None  # 手续费账户；为空则手续费从转出账户扣除
    currency: str = "CNY"
    occurred_at: datetime | None = None
    remark: str | None = None
    tag_ids: list[int] = []


# ---------- 货币兑换 ----------
class ExchangeCreate(BaseModel):
    from_account_id: int
    from_amount: Decimal               # 卖出金额（转出账户币种）
    to_account_id: int
    to_amount: Decimal                 # 买入金额（转入账户币种）
    fee: Decimal = Decimal("0")
    fee_account_id: int | None = None  # 手续费账户；为空则从转出账户扣除
    occurred_at: datetime | None = None
    remark: str | None = None


# ---------- 外汇买卖 ----------
class ForexTradeCreate(BaseModel):
    account_id: int                    # 外汇交易账户
    sell_currency: str                 # 卖出货币代码
    sell_amount: Decimal               # 卖出金额
    buy_currency: str                  # 买入货币代码
    buy_amount: Decimal                # 买入金额
    rate: Decimal                      # 交易汇率（每1卖出币兑换的买入币数量）
    funding_account_id: int | None = None  # 资金账户：用其本币余额购汇；为空则用外汇账户内的本币持仓
    occurred_at: datetime | None = None
    remark: str | None = None
    tag_ids: list[int] = []
    edit_txn_id: int | None = None     # 编辑：先删除原流水再重建


# ---------- 外汇转账（资金转入/转出某币种） ----------
class ForexTransferCreate(BaseModel):
    account_id: int                    # 外汇账户
    direction: str                     # 'in' 转入 / 'out' 转出
    counter_account_id: int            # 对方资金账户
    currency: str                      # 转账币种（=对方账户币种）
    amount: Decimal                    # 金额（该币种）
    occurred_at: datetime | None = None
    remark: str | None = None
    edit_txn_id: int | None = None     # 编辑：先删除原流水再重建


# ---------- 待摊费用 ----------
class DeferredCreate(BaseModel):
    name: str                       # 款项名称
    account_id: int                 # 支付账户
    category_id: int | None = None  # 收支项目
    total: Decimal                  # 待摊总金额
    periods: int                    # 待摊次数
    start: datetime | None = None   # 首期分摊日期
    remark: str | None = None


# ---------- Stats ----------
class OverviewOut(BaseModel):
    income: Decimal
    expense: Decimal
    balance: Decimal


class CategoryStatItem(BaseModel):
    category_id: int | None
    name: str
    amount: Decimal
    percent: float


class CategoryStatOut(BaseModel):
    total: Decimal
    items: list[CategoryStatItem]


class TrendItem(BaseModel):
    period: str
    income: Decimal
    expense: Decimal


# ---------- 投资一览 ----------
class InvestmentRow(BaseModel):
    id: int
    name: str
    symbol: str | None = None
    type: str
    quantity: Decimal
    avg_cost: Decimal       # 买入/持仓均价
    position_cost: Decimal  # 持仓成本
    price: Decimal          # 现价/收盘价
    market_value: Decimal   # 持仓市值
    float_profit: Decimal   # 浮动盈亏
    change_pct: float       # 涨幅%


class InvestmentOverview(BaseModel):
    total_cost: Decimal
    total_market_value: Decimal
    total_float_profit: Decimal
    total_change_pct: float
    rows: list[InvestmentRow]


# ---------- 投资收益一览表 ----------
class InvestmentIncomeItem(BaseModel):
    symbol: str | None = None
    name: str
    profit: Decimal          # 盈亏（已实现 + 浮动）


class InvestmentIncomeGroup(BaseModel):
    account_id: int
    account_name: str
    account_type: str
    total_profit: Decimal
    rows: list[InvestmentIncomeItem]


class InvestmentIncomeReport(BaseModel):
    total_profit: Decimal
    groups: list[InvestmentIncomeGroup]


# ---------- 财务诊断 ----------
class DiagnosisOut(BaseModel):
    salary_income: Decimal     # 年工资收入
    rent_income: Decimal       # 年租金收入
    invest_income: Decimal     # 年投资收入
    other_income: Decimal      # 年其它收入
    total_income: Decimal      # 年总收入
    total_expense: Decimal     # 年总支出
    surplus: Decimal           # 年结余
    surplus_ratio: float       # 结余比率 %
    invest_ratio: float        # 投资收入占总收入 %


# ---------- Budget ----------
class BudgetBase(BaseModel):
    category_id: int | None = None
    period: str = "month"
    amount: Decimal


class BudgetCreate(BudgetBase):
    pass


class BudgetUpdate(BaseModel):
    category_id: int | None = None
    period: str | None = None
    amount: Decimal | None = None
    is_active: bool | None = None


class BudgetOut(BudgetBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int
    is_active: bool
    category_name: str | None = None
    spent: Decimal = Decimal("0")


# ---------- Holding ----------
class HoldingBase(BaseModel):
    account_id: int | None = None
    symbol: str | None = None
    name: str
    type: str = "stock"
    currency: str = "CNY"
    quantity: Decimal = Decimal("0")
    cost: Decimal = Decimal("0")
    price: Decimal = Decimal("0")


class HoldingCreate(HoldingBase):
    pass


class HoldingUpdate(BaseModel):
    account_id: int | None = None
    symbol: str | None = None
    name: str | None = None
    type: str | None = None
    quantity: Decimal | None = None
    cost: Decimal | None = None
    price: Decimal | None = None


class HoldingOut(HoldingBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int
    market_value: Decimal = Decimal("0")
    profit: Decimal = Decimal("0")
    profit_rate: float = 0.0


# ---------- 证券买入 / 卖出 ----------
class TradeBuy(BaseModel):
    security_account_id: int          # 证券账户
    cash_account_id: int              # 资金账户
    symbol: str                       # 证券代码
    name: str | None = None           # 证券名称
    sec_type: str = "stock"           # stock/fund/bond...
    price: Decimal                    # 价格
    quantity: Decimal                 # 数量
    stamp_tax: Decimal = Decimal("0")     # 印花税费
    commission: Decimal = Decimal("0")    # 佣金
    transfer_fee: Decimal = Decimal("0")  # 过户费
    surcharge: Decimal = Decimal("0")     # 附加费
    fee_total: Decimal = Decimal("0")     # 费用小计
    amount_total: Decimal | None = None   # 金额合计
    occurred_at: datetime | None = None
    remark: str | None = None
    tag_ids: list[int] = []
    edit_txn_id: int | None = None        # 编辑模式：先回滚并删除该笔后重建
    currency: str | None = None           # 理财专用：申购币种
    exchange_rate: Decimal | None = None  # 理财专用：汇率（CNY->currency）


class TradeSell(TradeBuy):
    pnl_as: str = "invest_income"     # 本次盈亏记为
    redeem_to_cny: bool = False       # 外币理财赎回：是否兑换为人民币


# ---------- 新股申购 / 中签确认 ----------
class IpoSubscribe(TradeBuy):
    """新股申购：复用证券买入字段，仅冻结资金不建仓。"""
    pass


class IpoPendingOut(BaseModel):
    """一笔待中签确认的新股申购。"""
    txn_id: int
    symbol: str
    name: str
    amount: Decimal                  # 申购金额
    quantity: Decimal | None = None
    price: Decimal | None = None
    funding_account_id: int          # 资金账户
    security_account_id: int         # 证券账户
    occurred_at: datetime


class IpoConfirm(BaseModel):
    """中签确认：中签则买入建仓，未中签则返款。"""
    txn_id: int                      # 待确认的申购流水
    won: bool = False                # 是否中签
    refund_amount: Decimal = Decimal("0")  # 申购返款
    occurred_at: datetime | None = None
    remark: str | None = None
    tag_ids: list[int] = []



# ---------- Loan（债权债务） ----------
class LoanBase(BaseModel):
    direction: str = "receivable"  # receivable / payable
    counterparty: str
    item: str | None = None
    currency: str = "CNY"
    account_id: int | None = None
    amount: Decimal
    settled: Decimal = Decimal("0")
    interest_rate: Decimal | None = None
    total_periods: int | None = None
    remaining_periods: int | None = None
    repay_method: str | None = None
    occurred_at: datetime | None = None
    due_at: datetime | None = None
    remark: str | None = None
    # 网贷（P2P）专用字段
    loan_kind: str | None = None
    cash_account_id: int | None = None
    interest_method: str | None = None
    mgmt_fee_rate: Decimal | None = None
    term_value: int | None = None
    term_unit: str | None = None
    collect_interval: int | None = None
    collect_interval_unit: str | None = None
    collected_periods: int | None = None
    per_interest: Decimal | None = None
    remaining_principal_interest: Decimal | None = None
    first_collect_at: datetime | None = None
    auto_execute: bool | None = None


class LoanCreate(LoanBase):
    tag_ids: list[int] = []
    edit_loan_id: int | None = None      # 编辑模式：先回滚并删除该网贷项目后重建


class LoanUpdate(BaseModel):
    direction: str | None = None
    counterparty: str | None = None
    item: str | None = None
    currency: str | None = None
    account_id: int | None = None
    amount: Decimal | None = None
    settled: Decimal | None = None
    interest_rate: Decimal | None = None
    total_periods: int | None = None
    remaining_periods: int | None = None
    repay_method: str | None = None
    occurred_at: datetime | None = None
    due_at: datetime | None = None
    remark: str | None = None
    is_closed: bool | None = None
    tag_ids: list[int] | None = None
    # 网贷（P2P）专用字段
    loan_kind: str | None = None
    cash_account_id: int | None = None
    interest_method: str | None = None
    mgmt_fee_rate: Decimal | None = None
    term_value: int | None = None
    term_unit: str | None = None
    collect_interval: int | None = None
    collect_interval_unit: str | None = None
    collected_periods: int | None = None
    per_interest: Decimal | None = None
    remaining_principal_interest: Decimal | None = None
    first_collect_at: datetime | None = None
    auto_execute: bool | None = None


class LoanOut(LoanBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int
    occurred_at: datetime
    is_closed: bool
    remaining: Decimal = Decimal("0")
    tag_ids: list[int] = []


class LoanCollect(BaseModel):
    """网贷收回：收回本金 + 利息。"""
    income_account_id: int | None = None
    principal: Decimal = Decimal("0")
    interest: Decimal = Decimal("0")
    occurred_at: datetime | None = None
    remark: str | None = None
    tag_ids: list[int] = []
    edit_group: str | None = None        # 编辑模式：先回滚该笔收回后重建


class LoanRateAdjustmentBase(BaseModel):
    occurred_at: datetime | None = None
    interest_rate: Decimal
    remark: str | None = None


class LoanRateAdjustmentCreate(LoanRateAdjustmentBase):
    pass


class LoanRateAdjustmentUpdate(BaseModel):
    occurred_at: datetime | None = None
    interest_rate: Decimal | None = None
    remark: str | None = None


class LoanRateAdjustmentOut(LoanRateAdjustmentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int
    loan_id: int
    occurred_at: datetime


class LoanScheduleItem(BaseModel):
    period_no: int
    due_at: datetime
    annual_rate: Decimal
    payment: Decimal
    principal: Decimal
    interest: Decimal
    balance: Decimal
    is_paid: bool = False


class LoanScheduleOut(BaseModel):
    loan_id: int
    paid_periods: int
    total_periods: int
    paid_principal: Decimal
    paid_interest: Decimal
    remaining_principal: Decimal
    remaining_interest: Decimal
    items: list[LoanScheduleItem]


# ---------- Instrument（金融产品资料）----------
class InstrumentBase(BaseModel):
    category: str = "securities"
    code: str | None = None
    name: str
    currency: str = "CNY"
    buy_fee_rate: Decimal | None = None
    redeem_fee_rate: Decimal | None = None
    issuer: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    term_value: int | None = None
    term_unit: str | None = None
    expected_rate: Decimal | None = None
    guaranteed: bool = False
    owner: str | None = None
    asset_nature: str | None = None
    subcategory: str | None = None
    remark: str | None = None


class InstrumentCreate(InstrumentBase):
    pass


class InstrumentUpdate(BaseModel):
    category: str | None = None
    code: str | None = None
    name: str | None = None
    currency: str | None = None
    buy_fee_rate: Decimal | None = None
    redeem_fee_rate: Decimal | None = None
    issuer: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    term_value: int | None = None
    term_unit: str | None = None
    expected_rate: Decimal | None = None
    guaranteed: bool | None = None
    owner: str | None = None
    asset_nature: str | None = None
    subcategory: str | None = None
    remark: str | None = None


class InstrumentOut(InstrumentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int


# ---------- InstrumentPrice（每日价格 / 基金净值）----------
class InstrumentPriceBase(BaseModel):
    instrument_id: int
    price_date: str
    price: Decimal = Decimal("0")


class InstrumentPriceCreate(InstrumentPriceBase):
    pass


class InstrumentPriceUpdate(BaseModel):
    price_date: str | None = None
    price: Decimal | None = None


class InstrumentPriceOut(InstrumentPriceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str | None = None
    name: str | None = None


# ---------- TradeFeeRate（证券交易费率）----------
class TradeFeeRateBase(BaseModel):
    group_key: str
    security_type: str
    sort_order: int = 0
    buy_stamp_tax: Decimal = Decimal("0")
    sell_stamp_tax: Decimal = Decimal("0")
    buy_commission: Decimal = Decimal("0")
    buy_min_commission: Decimal = Decimal("0")
    sell_commission: Decimal = Decimal("0")
    sell_min_commission: Decimal = Decimal("0")
    surcharge: Decimal = Decimal("0")
    transfer_fee: Decimal = Decimal("0")
    settle_fee: Decimal = Decimal("0")
    settle_cap: Decimal = Decimal("0")
    trade_reg_fee: Decimal = Decimal("0")


class TradeFeeRateUpdate(BaseModel):
    buy_stamp_tax: Decimal | None = None
    sell_stamp_tax: Decimal | None = None
    buy_commission: Decimal | None = None
    buy_min_commission: Decimal | None = None
    sell_commission: Decimal | None = None
    sell_min_commission: Decimal | None = None
    surcharge: Decimal | None = None
    transfer_fee: Decimal | None = None
    settle_fee: Decimal | None = None
    settle_cap: Decimal | None = None
    trade_reg_fee: Decimal | None = None


class TradeFeeRateOut(TradeFeeRateBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int


# ---------- Currency（币种）----------
class CurrencyBase(BaseModel):
    name: str
    code: str
    is_home: bool = False
    rate: Decimal = Decimal("1")
    sort_order: int = 0


class CurrencyCreate(CurrencyBase):
    pass


class CurrencyUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    is_home: bool | None = None
    rate: Decimal | None = None
    sort_order: int | None = None


class CurrencyOut(CurrencyBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int


# ---------- ExchangeRate（汇率历史）----------
class ExchangeRateBase(BaseModel):
    rate_date: str
    currency_code: str
    base_code: str = "CNY"
    rate: Decimal = Decimal("0")


class ExchangeRateCreate(ExchangeRateBase):
    pass


class ExchangeRateUpdate(BaseModel):
    rate_date: str | None = None
    currency_code: str | None = None
    base_code: str | None = None
    rate: Decimal | None = None


class ExchangeRateOut(ExchangeRateBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int


# ---------- DepositRate（存款利率）----------
class DepositRateBase(BaseModel):
    group_key: str
    sort_order: int = 0
    save_type: str | None = None
    term: str | None = None
    rate: Decimal = Decimal("0")
    currency_code: str | None = None
    currency_name: str | None = None
    r_current: Decimal = Decimal("0")
    r_1m: Decimal = Decimal("0")
    r_3m: Decimal = Decimal("0")
    r_6m: Decimal = Decimal("0")
    r_1y: Decimal = Decimal("0")
    r_2y: Decimal = Decimal("0")
    r_7d_notice: Decimal = Decimal("0")


class DepositRateUpdate(BaseModel):
    save_type: str | None = None
    term: str | None = None
    rate: Decimal | None = None
    currency_name: str | None = None
    r_current: Decimal | None = None
    r_1m: Decimal | None = None
    r_3m: Decimal | None = None
    r_6m: Decimal | None = None
    r_1y: Decimal | None = None
    r_2y: Decimal | None = None
    r_7d_notice: Decimal | None = None


class DepositRateOut(DepositRateBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int


# ---------- Plan（财务计划与提醒）----------
class PlanBase(BaseModel):
    plan_type: str
    name: str
    frequency: str = "once"
    start_date: str
    end_date: str | None = None
    next_run_date: str | None = None
    status: str = "active"
    auto_execute: bool = False
    remind_days: int = 0
    account_id: int | None = None
    to_account_id: int | None = None
    fee_account_id: int | None = None
    category_id: int | None = None
    amount: Decimal = Decimal("0")
    fee: Decimal = Decimal("0")
    txn_type: str | None = None
    instrument_id: int | None = None
    fund_symbol: str | None = None
    fee_rate: Decimal | None = None
    loan_id: int | None = None
    remark: str | None = None


class PlanCreate(PlanBase):
    tag_ids: list[int] = []


class PlanUpdate(BaseModel):
    name: str | None = None
    frequency: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    next_run_date: str | None = None
    status: str | None = None
    auto_execute: bool | None = None
    remind_days: int | None = None
    account_id: int | None = None
    to_account_id: int | None = None
    fee_account_id: int | None = None
    category_id: int | None = None
    amount: Decimal | None = None
    fee: Decimal | None = None
    txn_type: str | None = None
    instrument_id: int | None = None
    fund_symbol: str | None = None
    fee_rate: Decimal | None = None
    remark: str | None = None
    tag_ids: list[int] | None = None


class PlanOut(PlanBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ledger_id: int
    last_run_at: datetime | None = None
    tags: list[TagOut] = []


class PlanExecute(BaseModel):
    """执行计划时可覆盖的字段；省略则按计划默认值执行。"""
    occurred_at: datetime | None = None
    amount: Decimal | None = None
    fee: Decimal | None = None
    interest: Decimal | None = None          # 网贷收回：利息
    principal: Decimal | None = None         # 网贷收回：本金
    account_id: int | None = None
    to_account_id: int | None = None
    remark: str | None = None
    tag_ids: list[int] | None = None
    keep_open: bool = True                   # 执行后是否保留计划（推进到下次）




# ---------- Net Worth ----------
class NetWorthGroup(BaseModel):
    name: str
    amount: Decimal


class NetWorthOut(BaseModel):
    assets: Decimal
    liabilities: Decimal
    net_worth: Decimal
    asset_groups: list[NetWorthGroup]
    liability_groups: list[NetWorthGroup]
