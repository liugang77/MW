"""数据库初始化与演示数据生成。

提供两个入口：
    init_database()  —— 清空数据目录并重建为初始默认状态（一个空的默认账本）。
    build_demo()     —— 清空数据目录并生成一套覆盖全部功能的演示数据。

数据文件位于 backend/data/：
    common.db        通用设置（账本、分类、币种、汇率、存款利率、交易费率、产品资料与价格）
    ledger_{id}.db   每个账本独立文件（账户、人员机构、流水、标签、预算、持仓、借贷、计划）
"""
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app import models
from app.core import db as core_db
from app.core.config import settings
from app.core.db import SessionLocal, init_common_db, ledger_session
from app.seed import EXPENSE_CATEGORIES, INCOME_CATEGORIES, seed, seed_ledger_defaults
from app.services.balance import apply_transaction


# --------------------------------------------------------------------------- #
# 公共工具
# --------------------------------------------------------------------------- #
def reset_data_files() -> None:
    """删除 data 目录下所有数据库文件，并清空建表缓存。"""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    for f in settings.data_dir.glob("*.db"):
        try:
            f.unlink()
        except OSError as exc:  # 文件被占用时给出明确提示
            raise SystemExit(f"无法删除 {f}，请先关闭正在运行的后端服务：{exc}")
    # 清空“已建表账本”缓存，使新文件会重新建表
    core_db._initialized_ledgers.clear()


def init_database() -> None:
    """重置为初始默认状态：一个空的默认账本（含默认分类与账户）。"""
    reset_data_files()
    init_common_db()
    seed()
    print(f"[init] 已重置为默认数据库 -> {settings.data_dir}")


# --------------------------------------------------------------------------- #
# 演示数据
# --------------------------------------------------------------------------- #
def _months_ago(months: int, day: int = 1, clamp_past: bool = True) -> datetime:
    base = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    month_index = base.month - 1 - months
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    safe_day = min(day, 28)
    result = base.replace(year=year, month=month, day=safe_day)
    # 历史流水不应落在未来：当月使用的日期若晚于今天，回拨到今天，
    # 避免产生“未来账单周期”（如信用卡多出一条未出账单）。
    if clamp_past and result > base:
        result = base
    return result


def _create_categories(ledger_id: int) -> dict[tuple[str, str], int]:
    """在 common.db 创建默认分类，返回 {(kind, name): id} 映射。"""
    with SessionLocal() as s:
        for i, (name, icon) in enumerate(EXPENSE_CATEGORIES):
            s.add(models.Category(ledger_id=ledger_id, name=name, kind="expense", icon=icon, sort_order=i))
        for i, (name, icon) in enumerate(INCOME_CATEGORIES):
            s.add(models.Category(ledger_id=ledger_id, name=name, kind="income", icon=icon, sort_order=i))
        s.commit()
        rows = s.query(models.Category).filter(models.Category.ledger_id == ledger_id).all()
        return {(c.kind, c.name): c.id for c in rows}


def _build_common_settings(ledger_id: int) -> None:
    """币种、汇率、存款利率、证券费率、金融产品资料与价格（均存 common.db）。"""
    with SessionLocal() as s:
        # 币种
        s.add_all([
            models.Currency(ledger_id=ledger_id, name="人民币", code="CNY", is_home=True, rate=Decimal("1"), sort_order=0),
            models.Currency(ledger_id=ledger_id, name="美元", code="USD", rate=Decimal("7.18"), sort_order=1),
            models.Currency(ledger_id=ledger_id, name="欧元", code="EUR", rate=Decimal("7.79"), sort_order=2),
            models.Currency(ledger_id=ledger_id, name="港币", code="HKD", rate=Decimal("0.92"), sort_order=3),
        ])
        # 汇率历史
        today = datetime.now().strftime("%Y-%m-%d")
        s.add_all([
            models.ExchangeRate(ledger_id=ledger_id, rate_date=today, currency_code="USD", rate=Decimal("7.1800")),
            models.ExchangeRate(ledger_id=ledger_id, rate_date=today, currency_code="EUR", rate=Decimal("7.7900")),
            models.ExchangeRate(ledger_id=ledger_id, rate_date=today, currency_code="HKD", rate=Decimal("0.9200")),
        ])
        # 人民币存款利率
        s.add_all([
            models.DepositRate(ledger_id=ledger_id, group_key="cny", sort_order=0, save_type="活期", term="活期", rate=Decimal("0.20")),
            models.DepositRate(ledger_id=ledger_id, group_key="cny", sort_order=1, save_type="整存整取", term="三个月", rate=Decimal("1.15")),
            models.DepositRate(ledger_id=ledger_id, group_key="cny", sort_order=2, save_type="整存整取", term="一年", rate=Decimal("1.45")),
            models.DepositRate(ledger_id=ledger_id, group_key="cny", sort_order=3, save_type="整存整取", term="三年", rate=Decimal("1.95")),
        ])
        # 外币存款利率
        s.add(models.DepositRate(
            ledger_id=ledger_id, group_key="foreign", sort_order=0,
            currency_code="USD", currency_name="美元",
            r_current=Decimal("0.50"), r_3m=Decimal("3.50"), r_6m=Decimal("3.80"), r_1y=Decimal("4.00"),
        ))
        # 证券交易费率（A股）
        s.add(models.TradeFeeRate(
            ledger_id=ledger_id, group_key="a_share", security_type="沪深A股", sort_order=0,
            sell_stamp_tax=Decimal("0.0005"), buy_commission=Decimal("0.00025"), buy_min_commission=Decimal("5"),
            sell_commission=Decimal("0.00025"), sell_min_commission=Decimal("5"), transfer_fee=Decimal("0.00001"),
        ))
        s.commit()

        # 金融产品资料
        gzmt = models.Instrument(ledger_id=ledger_id, category="securities", code="600519", name="贵州茅台", currency="CNY")
        etf = models.Instrument(ledger_id=ledger_id, category="open_fund", code="510300", name="沪深300ETF", currency="CNY",
                                buy_fee_rate=Decimal("0.0015"), redeem_fee_rate=Decimal("0.0050"))
        mmf = models.Instrument(ledger_id=ledger_id, category="money_fund", code="000198", name="天弘余额宝货币", currency="CNY")
        wm = models.Instrument(ledger_id=ledger_id, category="bank_wealth", code="LC2024", name="某银行半年理财", currency="CNY",
                               issuer="招商银行", expected_rate=Decimal("3.20"), term_value=6, term_unit="month", guaranteed=False)
        # 银行理财产品（对应「管理金融产品 / 银行理财产品」演示）
        def _wm(name, start_days, term_days, rate, guaranteed=False, issuer="招商银行"):
            start = datetime.now() - timedelta(days=start_days)
            end = start + timedelta(days=term_days)
            return models.Instrument(
                ledger_id=ledger_id, category="bank_wealth", name=name, currency="CNY",
                issuer=issuer, start_date=start.strftime("%Y-%m-%d"), end_date=end.strftime("%Y-%m-%d"),
                term_value=term_days, term_unit="day", expected_rate=Decimal(rate), guaranteed=guaranteed,
            )
        wm1 = _wm("小银票23544", start_days=40, term_days=32, rate="6.18")
        wm2 = _wm("小银票23705", start_days=38, term_days=33, rate="6.00")
        wm3 = _wm("小银票24013", start_days=36, term_days=76, rate="6.18")
        wm4 = _wm("新手理财12期", start_days=33, term_days=30, rate="15.00", guaranteed=True, issuer="工商银行")
        # 贵金属品种（上海黄金交易所 SGE，无代码，以名称管理）
        au = models.Instrument(ledger_id=ledger_id, category="metal", name="Au99.99", currency="CNY")
        autd = models.Instrument(ledger_id=ledger_id, category="metal", name="Au(T+D)", currency="CNY")
        agtd = models.Instrument(ledger_id=ledger_id, category="metal", name="Ag(T+D)", currency="CNY")
        s.add_all([gzmt, etf, mmf, wm, wm1, wm2, wm3, wm4, au, autd, agtd])
        s.commit()

        # 价格 / 净值
        prices = [
            (gzmt.id, [("1500.00", 60), ("1620.00", 30), ("1685.00", 0)]),
            (etf.id, [("3.820", 60), ("3.910", 30), ("3.975", 0)]),
            (mmf.id, [("1.0000", 0)]),
            # 贵金属价格：黄金约 560→600 元/克，白银约 7200→7500 元/千克
            (au.id, [("560.00", 30), ("600.00", 0)]),
            (autd.id, [("568.00", 30), ("605.00", 0)]),
            (agtd.id, [("7200.00", 30), ("7500.00", 0)]),
        ]
        for inst_id, points in prices:
            for price, days in points:
                d = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                s.add(models.InstrumentPrice(instrument_id=inst_id, price_date=d, price=Decimal(price)))
        s.commit()
        return {"gzmt": gzmt.id, "etf": etf.id, "mmf": mmf.id, "wm": wm.id,
                "wm2": wm2.id, "wm4": wm4.id, "au": au.id}


def _build_home_ledger(ledger_id: int, cats: dict, instruments: dict) -> None:
    """家庭账本：账户分组、账户、人员、标签、流水、预算、持仓、借贷、计划。"""
    with ledger_session(ledger_id) as db:
        # 账户分组
        g_cash = models.AccountGroup(ledger_id=ledger_id, name="现金钱包", sort_order=0)
        g_bank = models.AccountGroup(ledger_id=ledger_id, name="银行账户", sort_order=1)
        g_credit = models.AccountGroup(ledger_id=ledger_id, name="信用卡", sort_order=2)
        g_invest = models.AccountGroup(ledger_id=ledger_id, name="投资理财", sort_order=3)
        db.add_all([g_cash, g_bank, g_credit, g_invest])
        db.flush()

        # 账户（余额一律由“期初余额”交易生成，账户本身初始为 0）
        cash = models.Account(ledger_id=ledger_id, name="现金", type="cash", icon="💵", group_id=g_cash.id,
                              initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=0)
        wechat = models.Account(ledger_id=ledger_id, name="微信钱包", type="wallet", icon="💚", group_id=g_cash.id,
                                initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=1)
        alipay = models.Account(ledger_id=ledger_id, name="支付宝", type="wallet", icon="💙", group_id=g_cash.id,
                                initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=2)
        salary = models.Account(ledger_id=ledger_id, name="工资卡", type="bank", icon="🏦", group_id=g_bank.id,
                                bank_name="招商银行", initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=3)
        saving = models.Account(ledger_id=ledger_id, name="储蓄卡", type="bank", icon="🏦", group_id=g_bank.id,
                                bank_name="工商银行", initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=4)
        credit = models.Account(ledger_id=ledger_id, name="招商信用卡", type="credit", icon="💳", group_id=g_credit.id,
                                bank_name="招商银行", credit_limit=Decimal("50000"), bill_day=5, repay_day=25,
                                initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=5)
        stock = models.Account(ledger_id=ledger_id, name="证券账户", type="stock", icon="📈", group_id=g_invest.id,
                               initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=6)
        fund_acc = models.Account(ledger_id=ledger_id, name="基金账户", type="open_fund", icon="📊", group_id=g_invest.id,
                                  initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=7)
        wealth_acc = models.Account(ledger_id=ledger_id, name="银行理财", type="wealth", icon="🏦", group_id=g_invest.id,
                                    initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=7)
        metal_acc = models.Account(ledger_id=ledger_id, name="贵金属账户", type="metal", icon="🪙", group_id=g_invest.id,
                                   initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=7)
        forex_acc = models.Account(ledger_id=ledger_id, name="外汇账户", type="forex", icon="💱", group_id=g_invest.id,
                                   currency="CNY", initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=7)
        social = models.Account(ledger_id=ledger_id, name="住房公积金", type="insurance", icon="🛡️", group_id=g_invest.id,
                                insured_person="陈志远", remark="单位+个人缴存",
                                initial_balance=Decimal("0"), current_balance=Decimal("0"), include_in_net=True, sort_order=8)
        social2 = models.Account(ledger_id=ledger_id, name="商业养老险", type="insurance", icon="🛡️", group_id=g_invest.id,
                                 insured_person="陈志远", remark="年金型",
                                 initial_balance=Decimal("0"), current_balance=Decimal("0"), include_in_net=True, sort_order=8)
        social3 = models.Account(ledger_id=ledger_id, name="重疾险", type="insurance", icon="🛡️", group_id=g_invest.id,
                                 insured_person="林婉清", remark="保额50万",
                                 initial_balance=Decimal("0"), current_balance=Decimal("0"), include_in_net=True, sort_order=8)
        p2p_acc = models.Account(ledger_id=ledger_id, name="你我贷", type="p2p", icon="💹", group_id=g_invest.id,
                                 initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=9)
        p2p_acc2 = models.Account(ledger_id=ledger_id, name="京东金融", type="p2p", icon="💹", group_id=g_invest.id,
                                  initial_balance=Decimal("0"), current_balance=Decimal("0"), sort_order=10)
        # 借入分期会创建“应付款”账户（loan 类型），余额为负表示负债
        loan_house = models.Account(ledger_id=ledger_id, name="房贷", type="loan", icon="📉", owner="工商银行",
                                    initial_balance=Decimal("0"), current_balance=Decimal("0"),
                                    remark="自动创建：借入应付款账户", sort_order=11)
        loan_consume = models.Account(ledger_id=ledger_id, name="消费贷", type="loan", icon="📉", owner="招商银行",
                                      initial_balance=Decimal("0"), current_balance=Decimal("0"),
                                      remark="自动创建：借入应付款账户", sort_order=12)
        # 借出会创建“应收款”账户（loan 类型），余额为正表示债权
        loan_lend = models.Account(ledger_id=ledger_id, name="外借", type="loan", icon="📈", owner="同事孙浩",
                                   initial_balance=Decimal("0"), current_balance=Decimal("0"),
                                   remark="自动创建：借出应收款账户", sort_order=13)
        # 重大资产
        major_house = models.Account(ledger_id=ledger_id, name="自住房产", type="major_asset", icon="🏠",
                                     asset_nature="own", initial_balance=Decimal("0"), current_balance=Decimal("0"),
                                     remark="市中心住宅", sort_order=14)
        major_car = models.Account(ledger_id=ledger_id, name="家用汽车", type="major_asset", icon="🚗",
                                   asset_nature="own", initial_balance=Decimal("0"), current_balance=Decimal("0"),
                                   remark="代步车", sort_order=15)
        db.add_all([cash, wechat, alipay, salary, saving, credit, stock, fund_acc, wealth_acc, metal_acc, forex_acc, social, social2, social3, p2p_acc, p2p_acc2, loan_house, loan_consume, loan_lend, major_house, major_car])
        db.flush()

        # 人员与机构
        db.add_all([
            models.Party(ledger_id=ledger_id, name="陈志远", type="member", gender="male", birthday="1988-06-15"),
            models.Party(ledger_id=ledger_id, name="林婉清", type="member", gender="female", birthday="1990-03-22"),
            models.Party(ledger_id=ledger_id, name="孩子", type="member", gender="male", birthday="2018-09-01"),
            models.Party(ledger_id=ledger_id, name="父母", type="member"),
            models.Party(ledger_id=ledger_id, name="房东周先生", type="contact", contact="138-0000-0000"),
            models.Party(ledger_id=ledger_id, name="招商银行", type="org", address="深圳市福田区"),
            models.Party(ledger_id=ledger_id, name="工商银行", type="org"),
        ])

        # 标签
        t_decorate = models.Tag(ledger_id=ledger_id, name="装修", color="#e6a23c", sort_order=0)
        t_baby = models.Tag(ledger_id=ledger_id, name="育儿", color="#67c23a", sort_order=1)
        t_travel = models.Tag(ledger_id=ledger_id, name="旅行", color="#409eff", sort_order=2)
        db.add_all([t_decorate, t_baby, t_travel])
        db.flush()

        def add_txn(**kw):
            tags = kw.pop("tags", None)
            txn = models.Transaction(ledger_id=ledger_id, **kw)
            if tags:
                txn.tags = tags
            db.add(txn)
            db.flush()
            apply_transaction(db, txn, sign=1)
            return txn

        c = lambda kind, name: cats[(kind, name)]

        # 期初余额：每个账户的起始余额都以一笔「余额调整」交易体现，
        # 从而保证“余额=交易明细累计”这一基本原则。
        opening_at = _months_ago(36, 1)

        def open_balance(acc, amount):
            if Decimal(str(amount)) != 0:
                add_txn(type="adjust", amount=Decimal(str(amount)), account_id=acc.id,
                        occurred_at=opening_at, remark="期初余额")

        open_balance(cash, "2000")
        open_balance(wechat, "1500")
        open_balance(alipay, "3000")
        open_balance(salary, "50000")
        open_balance(saving, "300000")
        open_balance(social, "45000")
        open_balance(social2, "12000")
        open_balance(social3, "3000")
        open_balance(loan_house, "-680000")
        open_balance(loan_consume, "-36000")
        open_balance(loan_lend, "6000")
        open_balance(major_house, "3600000")
        open_balance(major_car, "400000")

        # 投资账户的初始资金均来自储蓄卡转账充值：账户先有可用现金，
        # 再买入证券/基金或网贷借出，从而保证“余额=可用现金=交易明细累计”。
        invest_at = _months_ago(35, 2)
        add_txn(type="transfer", amount=Decimal("90000"), account_id=saving.id, to_account_id=stock.id,
                occurred_at=invest_at, remark="转入证券账户")
        add_txn(type="transfer", amount=Decimal("30000"), account_id=saving.id, to_account_id=fund_acc.id,
                occurred_at=invest_at, remark="转入基金账户")
        add_txn(type="transfer", amount=Decimal("50000"), account_id=saving.id, to_account_id=wealth_acc.id,
                occurred_at=_months_ago(2, 2), remark="转入银行理财账户")
        add_txn(type="transfer", amount=Decimal("20000"), account_id=saving.id, to_account_id=metal_acc.id,
                occurred_at=_months_ago(3, 2), remark="转入贵金属账户")
        add_txn(type="transfer", amount=Decimal("30000"), account_id=saving.id, to_account_id=p2p_acc.id,
                occurred_at=_months_ago(4, 2), remark="转入网贷账户")
        add_txn(type="transfer", amount=Decimal("8000"), account_id=saving.id, to_account_id=p2p_acc2.id,
                occurred_at=_months_ago(3, 2), remark="转入网贷账户")

        # 证券/基金买入：从对应账户可用现金支出，生成持仓（持仓成本=支出额）
        buy_at = _months_ago(34, 3)
        add_txn(type="expense", amount=Decimal("75000"), account_id=stock.id,
                occurred_at=buy_at, remark="买入：贵州茅台 50股",
                trade_symbol="600519", trade_price=Decimal("1500"), trade_qty=Decimal("50"),
                trade_commission=Decimal("0"), trade_fee=Decimal("0"), trade_cost=Decimal("75000"))
        # 部分卖出：卖出 10 股（成本价 1500），实现盈亏入账，演示证券「历史盈亏」。
        # 卖出后持仓 40 股、成本 60000 保持不变。
        add_txn(type="income", amount=Decimal("17200"), account_id=stock.id,
                category_id=c("income", "投资收益"), occurred_at=_months_ago(0, 14),
                remark="卖出：贵州茅台 10股",
                trade_symbol="600519", trade_price=Decimal("1720"), trade_qty=Decimal("10"),
                trade_commission=Decimal("0"), trade_fee=Decimal("0"), trade_cost=Decimal("15000"))
        add_txn(type="expense", amount=Decimal("19100"), account_id=fund_acc.id,
                occurred_at=buy_at, remark="买入：沪深300ETF 5000份",
                trade_symbol="510300", trade_price=Decimal("3.82"), trade_qty=Decimal("5000"),
                trade_commission=Decimal("0"), trade_fee=Decimal("0"), trade_cost=Decimal("19100"))
        add_txn(type="expense", amount=Decimal("8000"), account_id=fund_acc.id,
                occurred_at=buy_at, remark="买入：天弘余额宝货币 8000份",
                trade_symbol="000198", trade_price=Decimal("1"), trade_qty=Decimal("8000"),
                trade_commission=Decimal("0"), trade_fee=Decimal("0"), trade_cost=Decimal("8000"))

        # 银行理财申购：以「申购金额」记账（单价记为 1、份额即金额），生成理财持仓
        add_txn(type="expense", amount=Decimal("20000"), account_id=wealth_acc.id,
                occurred_at=_months_ago(2, 3), remark="理财申购：小银票23705",
                trade_symbol="小银票23705", trade_price=Decimal("1"), trade_qty=Decimal("20000"),
                trade_commission=Decimal("0"), trade_fee=Decimal("0"), trade_cost=Decimal("20000"))
        add_txn(type="expense", amount=Decimal("15000"), account_id=wealth_acc.id,
                occurred_at=_months_ago(1, 8), remark="理财申购：新手理财12期",
                trade_symbol="新手理财12期", trade_price=Decimal("1"), trade_qty=Decimal("15000"),
                trade_commission=Decimal("0"), trade_fee=Decimal("0"), trade_cost=Decimal("15000"))

        # 已到期赎回的理财产品（小银票23544）：先申购后全额赎回，
        # 赎回为收益入账（净额 > 成本），用于演示「所有交易过的产品」与「历史盈亏」。
        # 赎回后无持仓，仅在「所有交易过的产品」范围与历史盈亏中可见。
        add_txn(type="expense", amount=Decimal("10000"), account_id=wealth_acc.id,
                occurred_at=_months_ago(2, 5), remark="理财申购：小银票23544",
                trade_symbol="小银票23544", trade_price=Decimal("1"), trade_qty=Decimal("10000"),
                trade_commission=Decimal("0"), trade_fee=Decimal("0"), trade_cost=Decimal("10000"))
        add_txn(type="income", amount=Decimal("10055"), account_id=wealth_acc.id,
                occurred_at=_months_ago(0, 18), remark="理财赎回：小银票23544",
                trade_symbol="小银票23544", trade_price=Decimal("1"), trade_qty=Decimal("10000"),
                trade_commission=Decimal("0"), trade_fee=Decimal("0"), trade_cost=Decimal("10000"))

        # 贵金属买入：从贵金属账户可用现金支出，生成持仓（买入价 560，现价 600，浮盈）
        add_txn(type="expense", amount=Decimal("11200"), account_id=metal_acc.id,
                occurred_at=_months_ago(3, 4), remark="贵金属买入：Au99.99 20克",
                trade_symbol="Au99.99", trade_price=Decimal("560"), trade_qty=Decimal("20"),
                trade_commission=Decimal("0"), trade_fee=Decimal("0"), trade_cost=Decimal("11200"))

        # 外汇账户：余额恒为 0，价值由各币种持仓体现（与外汇买卖/转账端点行为一致）。
        # 流水仅作展示与历史，不通过 apply_transaction 改动外汇账户余额。
        def add_forex_txn(**kw):
            txn = models.Transaction(ledger_id=ledger_id, **kw)
            db.add(txn)
            db.flush()
            return txn

        # 1) 资金转入：从储蓄卡转入 50000 人民币（仅储蓄卡余额减少，外汇账户余额保持 0）
        add_forex_txn(type="transfer", amount=Decimal("50000"), currency="CNY",
                      account_id=saving.id, to_account_id=forex_acc.id,
                      occurred_at=_months_ago(2, 4), remark="转入外汇账户")
        saving.current_balance = Decimal(saving.current_balance) - Decimal("50000")
        # 2) 外汇买卖：卖出人民币买入美元、港币（adjust 流水，trade_symbol="卖/买"）
        add_forex_txn(type="adjust", amount=Decimal("35900"), currency="CNY", account_id=forex_acc.id,
                      occurred_at=_months_ago(2, 6), remark="外汇买卖：卖出35900CNY 买入5000USD",
                      trade_symbol="CNY/USD", trade_price=Decimal("7.18"), trade_qty=Decimal("5000"))
        add_forex_txn(type="adjust", amount=Decimal("9200"), currency="CNY", account_id=forex_acc.id,
                      occurred_at=_months_ago(1, 9), remark="外汇买卖：卖出9200CNY 买入10000HKD",
                      trade_symbol="CNY/HKD", trade_price=Decimal("0.92"), trade_qty=Decimal("10000"))

        # 网贷借出：从网贷账户可用现金支出本金（债权另计为应收资产）
        lend_t1 = add_txn(type="expense", amount=Decimal("20000"), account_id=p2p_acc.id,
                occurred_at=_months_ago(3, 5), remark="网贷借出：新手标12月")
        lend_t2 = add_txn(type="expense", amount=Decimal("10000"), account_id=p2p_acc.id,
                occurred_at=_months_ago(1, 12), remark="网贷借出：散标6月")
        lend_t3 = add_txn(type="expense", amount=Decimal("8000"), account_id=p2p_acc2.id,
                occurred_at=_months_ago(2, 8), remark="网贷借出：京东金条出借")

        # 网贷回款：本金与利息分别入账，回到网贷账户可用现金
        cg1 = uuid4().hex[:24]
        col_t1p = add_txn(type="income", amount=Decimal("5000"), account_id=p2p_acc.id,
                occurred_at=_months_ago(0, 5), remark="网贷收回本金：新手标12月", collect_group=cg1)
        col_t1i = add_txn(type="income", amount=Decimal("400"), account_id=p2p_acc.id,
                category_id=c("income", "投资收益"), occurred_at=_months_ago(0, 5),
                remark="网贷收回利息：新手标12月", collect_group=cg1)
        cg2 = uuid4().hex[:24]
        col_t2i = add_txn(type="income", amount=Decimal("79.17"), account_id=p2p_acc.id,
                category_id=c("income", "投资收益"), occurred_at=_months_ago(0, 12),
                remark="网贷收回利息：散标6月", collect_group=cg2)
        cg3 = uuid4().hex[:24]
        col_t3i = add_txn(type="income", amount=Decimal("96"), account_id=p2p_acc2.id,
                category_id=c("income", "投资收益"), occurred_at=_months_ago(0, 8),
                remark="网贷收回利息：京东金条出借", collect_group=cg3)

        # 近 3 个月的流水
        for m in (2, 1, 0):
            # 工资收入
            add_txn(type="income", amount=Decimal("18000"), account_id=salary.id,
                    category_id=c("income", "工资"), occurred_at=_months_ago(m, 10),
                    remark="月薪", merchant="某科技公司")
            # 物业费与水电（自有住房的日常居住支出，房贷另由还款计划体现）
            add_txn(type="expense", amount=Decimal("760"), account_id=saving.id,
                    category_id=c("expense", "居住"), occurred_at=_months_ago(m, 6),
                    remark="物业费与水电")
            # 餐饮（多笔）
            add_txn(type="expense", amount=Decimal("680"), account_id=alipay.id,
                    category_id=c("expense", "餐饮"), occurred_at=_months_ago(m, 8), remark="超市采购")
            add_txn(type="expense", amount=Decimal("320"), account_id=wechat.id,
                    category_id=c("expense", "餐饮"), occurred_at=_months_ago(m, 15), remark="外卖")
            # 交通
            add_txn(type="expense", amount=Decimal("260"), account_id=alipay.id,
                    category_id=c("expense", "交通"), occurred_at=_months_ago(m, 12), remark="地铁公交")
            # 育儿（标签）
            add_txn(type="expense", amount=Decimal("900"), account_id=salary.id,
                    category_id=c("expense", "教育"), occurred_at=_months_ago(m, 20),
                    remark="兴趣班", tags=[t_baby])
            # 每月定投转入基金账户
            add_txn(type="transfer", amount=Decimal("2000"), account_id=salary.id, to_account_id=fund_acc.id,
                    occurred_at=_months_ago(m, 5), remark="基金定投")

        # 信用卡：账单日 5 号、还款日 25 号。每月消费，次月 25 号还清上一期账单。
        # 历史消费（按月，含一次较大额旅行）
        add_txn(type="expense", amount=Decimal("1280"), account_id=credit.id,
                category_id=c("expense", "购物"), occurred_at=_months_ago(4, 18), remark="服饰")
        add_txn(type="expense", amount=Decimal("6800"), account_id=credit.id,
                category_id=c("expense", "旅行"), occurred_at=_months_ago(3, 22),
                remark="短途旅行", tags=[t_travel])
        add_txn(type="expense", amount=Decimal("2400"), account_id=credit.id,
                category_id=c("expense", "购物"), occurred_at=_months_ago(2, 18), remark="数码配件")
        add_txn(type="expense", amount=Decimal("1280"), account_id=credit.id,
                category_id=c("expense", "购物"), occurred_at=_months_ago(1, 18), remark="服饰")
        add_txn(type="expense", amount=Decimal("860"), account_id=credit.id,
                category_id=c("expense", "餐饮"), occurred_at=_months_ago(0, 3), remark="家庭聚餐")
        # 每月 25 号（还款日）还清上一账单周期消费：账单日 5 号出账、25 号到期。
        add_txn(type="transfer", amount=Decimal("1280"), account_id=salary.id, to_account_id=credit.id,
                occurred_at=_months_ago(3, 25), remark="信用卡还款")
        add_txn(type="transfer", amount=Decimal("6800"), account_id=salary.id, to_account_id=credit.id,
                occurred_at=_months_ago(2, 25), remark="信用卡还款")
        add_txn(type="transfer", amount=Decimal("2400"), account_id=salary.id, to_account_id=credit.id,
                occurred_at=_months_ago(1, 25), remark="信用卡还款")
        # 本月 5 号出账的上月账单（服饰 1280）将于本月 25 号到期，尚未还款；
        # 本月新消费（家庭聚餐 860）计入下期账单。当前已用额度 = 1280 + 860 = 2140。
        # 投资收益
        add_txn(type="income", amount=Decimal("1500"), account_id=stock.id,
                category_id=c("income", "投资收益"), occurred_at=_months_ago(0, 16), remark="股票分红")
        # 利息收入
        add_txn(type="income", amount=Decimal("85"), account_id=saving.id,
                category_id=c("income", "利息"), occurred_at=_months_ago(0, 25), remark="活期利息")
        # 保险缴费（公积金每月缴存）— 标记保险活动类型「缴纳保费」
        for m in range(0, 6):
            add_txn(type="transfer", amount=Decimal("700"), account_id=salary.id, to_account_id=social.id,
                    occurred_at=_months_ago(m, 6), remark="陈志远-公积金缴存", insurance_activity="缴纳保费")
        add_txn(type="transfer", amount=Decimal("500"), account_id=salary.id, to_account_id=social2.id,
                occurred_at=_months_ago(0, 8), remark="商业养老险缴费", insurance_activity="缴纳保费")
        add_txn(type="transfer", amount=Decimal("300"), account_id=salary.id, to_account_id=social3.id,
                occurred_at=_months_ago(0, 9), remark="重疾险年缴", insurance_activity="缴纳保费")
        # 保险分红（商业养老险年度分红）— 现金价值减少并转入储蓄卡，不计入日常收支
        add_txn(type="transfer", amount=Decimal("1200"), account_id=social2.id, to_account_id=saving.id,
                occurred_at=_months_ago(0, 12), remark="商业养老险年度分红", insurance_activity="保险分红")
        # 保费返还（重疾险满期返还部分保费）— 现金价值减少并转入储蓄卡
        add_txn(type="transfer", amount=Decimal("500"), account_id=social3.id, to_account_id=saving.id,
                occurred_at=_months_ago(0, 15), remark="重疾险保费返还", insurance_activity="保费返还")

        # 预算
        db.add_all([
            models.Budget(ledger_id=ledger_id, category_id=c("expense", "餐饮"), period="month", amount=Decimal("2500")),
            models.Budget(ledger_id=ledger_id, category_id=c("expense", "购物"), period="month", amount=Decimal("2000")),
            models.Budget(ledger_id=ledger_id, category_id=c("expense", "交通"), period="month", amount=Decimal("600")),
            models.Budget(ledger_id=ledger_id, category_id=None, period="year", amount=Decimal("150000")),
        ])

        # 持仓
        db.add_all([
            models.Holding(ledger_id=ledger_id, account_id=stock.id, symbol="600519", name="贵州茅台",
                           type="stock", quantity=Decimal("40"), cost=Decimal("60000"), price=Decimal("1685.00")),
            models.Holding(ledger_id=ledger_id, account_id=fund_acc.id, symbol="510300", name="沪深300ETF",
                           type="fund", quantity=Decimal("5000"), cost=Decimal("19100"), price=Decimal("3.975")),
            models.Holding(ledger_id=ledger_id, account_id=fund_acc.id, symbol="000198", name="天弘余额宝货币",
                           type="money_fund", quantity=Decimal("8000"), cost=Decimal("8000"), price=Decimal("1.0000")),
            # 银行理财持仓：累计金额=申购金额（单价 1）
            models.Holding(ledger_id=ledger_id, account_id=wealth_acc.id, symbol="小银票23705", name="小银票23705",
                           type="wealth", quantity=Decimal("20000"), cost=Decimal("20000"), price=Decimal("1.0000")),
            models.Holding(ledger_id=ledger_id, account_id=wealth_acc.id, symbol="新手理财12期", name="新手理财12期",
                           type="wealth", quantity=Decimal("15000"), cost=Decimal("15000"), price=Decimal("1.0000")),
            # 贵金属持仓：买入价 560、现价 600（浮盈 800）
            models.Holding(ledger_id=ledger_id, account_id=metal_acc.id, symbol="Au99.99", name="Au99.99",
                           type="metal", quantity=Decimal("20"), cost=Decimal("11200"), price=Decimal("600.00")),
            # 外汇持仓：人民币结余 4900 + 美元 5000（折合 35900）+ 港币 10000（折合 9200）
            models.Holding(ledger_id=ledger_id, account_id=forex_acc.id, symbol="CNY", name="人民币",
                           type="forex", quantity=Decimal("4900"), cost=Decimal("4900"), price=Decimal("1.0000")),
            models.Holding(ledger_id=ledger_id, account_id=forex_acc.id, symbol="USD", name="美元",
                           type="forex", quantity=Decimal("5000"), cost=Decimal("35900"), price=Decimal("7.1800")),
            models.Holding(ledger_id=ledger_id, account_id=forex_acc.id, symbol="HKD", name="港币",
                           type="forex", quantity=Decimal("10000"), cost=Decimal("9200"), price=Decimal("0.9200")),
        ])

        # 借贷（债权债务）
        loans = [
            # 应收：普通借出
            models.Loan(ledger_id=ledger_id, direction="receivable", counterparty="同事孙浩", item="外借",
                        account_id=loan_lend.id, amount=Decimal("10000"), settled=Decimal("4000"),
                        occurred_at=_months_ago(2, 3), due_at=_months_ago(-1, 3, clamp_past=False), remark="周转借款"),
            # 应付：等额本息房贷（自动生成 loan 账户 + 还款计划）
            models.Loan(ledger_id=ledger_id, direction="payable", counterparty="工商银行", item="房贷",
                        account_id=loan_house.id, amount=Decimal("800000"), settled=Decimal("120000"),
                        interest_rate=Decimal("4.10"), total_periods=360, remaining_periods=300,
                        collected_periods=60, repay_method="等额本息",
                        collect_interval=1, collect_interval_unit="month",
                        occurred_at=_months_ago(60, 6, clamp_past=True),
                        first_collect_at=_months_ago(59, 6, clamp_past=True), remark="按揭贷款"),
            # 应付：等额本息消费贷（自动生成 loan 账户 + 还款计划）
            models.Loan(ledger_id=ledger_id, direction="payable", counterparty="招商银行", item="消费贷",
                        account_id=loan_consume.id, amount=Decimal("50000"), settled=Decimal("14000"),
                        interest_rate=Decimal("6.50"), total_periods=36, remaining_periods=24,
                        collected_periods=12, repay_method="等额本息",
                        collect_interval=1, collect_interval_unit="month",
                        occurred_at=_months_ago(12, 8, clamp_past=True),
                        first_collect_at=_months_ago(11, 8, clamp_past=True), remark="装修消费贷"),
            # 应收：网贷出借（P2P）- 你我贷
            models.Loan(ledger_id=ledger_id, direction="receivable", counterparty="你我贷", item="新手标12月",
                        account_id=p2p_acc.id, cash_account_id=saving.id, amount=Decimal("20000"), settled=Decimal("5000"),
                        loan_kind="p2p", interest_rate=Decimal("8.00"), interest_method="等额本息",
                        term_value=12, term_unit="month", total_periods=12, collect_interval=1, collect_interval_unit="month",
                        collected_periods=3, per_interest=Decimal("133.33"), occurred_at=_months_ago(3, 5),
                        first_collect_at=_months_ago(2, 5), remark="网贷理财"),
            models.Loan(ledger_id=ledger_id, direction="receivable", counterparty="你我贷", item="散标6月",
                        account_id=p2p_acc.id, cash_account_id=saving.id, amount=Decimal("10000"), settled=Decimal("0"),
                        loan_kind="p2p", interest_rate=Decimal("9.50"), interest_method="分期付息一次还本",
                        term_value=6, term_unit="month", total_periods=6, collect_interval=1, collect_interval_unit="month",
                        collected_periods=1, per_interest=Decimal("79.17"), occurred_at=_months_ago(1, 12),
                        first_collect_at=_months_ago(0, 12), remark="散标投资"),
            # 应收：网贷出借（P2P）- 京东金融
            models.Loan(ledger_id=ledger_id, direction="receivable", counterparty="京东金融", item="京东金条出借",
                        account_id=p2p_acc2.id, cash_account_id=saving.id, amount=Decimal("8000"), settled=Decimal("0"),
                        loan_kind="p2p", interest_rate=Decimal("7.20"), interest_method="等额本息",
                        term_value=12, term_unit="month", total_periods=12, collect_interval=1, collect_interval_unit="month",
                        collected_periods=2, per_interest=Decimal("48.00"), occurred_at=_months_ago(2, 8),
                        first_collect_at=_months_ago(1, 8), remark="京东金融理财"),
        ]
        db.add_all(loans)
        db.flush()

        # 关联网贷流水与对应项目（用于删除/编辑时回滚项目状态）
        loan_xinshou, loan_sanbiao, loan_jd = loans[3], loans[4], loans[5]
        lend_t1.loan_id = loan_xinshou.id
        lend_t2.loan_id = loan_sanbiao.id
        lend_t3.loan_id = loan_jd.id
        col_t1p.loan_id = col_t1i.loan_id = loan_xinshou.id
        col_t2i.loan_id = loan_sanbiao.id
        col_t3i.loan_id = loan_jd.id
        db.flush()

        # 利率调整记录（房贷经历过 LPR 下调，影响还款计划利息）
        loan_house_obj = loans[1]
        db.add_all([
            models.LoanRateAdjustment(ledger_id=ledger_id, loan_id=loan_house_obj.id,
                                      occurred_at=_months_ago(60, 6, clamp_past=True),
                                      interest_rate=Decimal("4.9000"), remark="初始利率"),
            models.LoanRateAdjustment(ledger_id=ledger_id, loan_id=loan_house_obj.id,
                                      occurred_at=_months_ago(24, 1, clamp_past=True),
                                      interest_rate=Decimal("4.3000"), remark="LPR 下调"),
            models.LoanRateAdjustment(ledger_id=ledger_id, loan_id=loan_house_obj.id,
                                      occurred_at=_months_ago(6, 1, clamp_past=True),
                                      interest_rate=Decimal("4.1000"), remark="LPR 下调"),
        ])
        loan_consume_obj = loans[2]
        db.add(models.LoanRateAdjustment(ledger_id=ledger_id, loan_id=loan_consume_obj.id,
                                         occurred_at=_months_ago(12, 8, clamp_past=True),
                                         interest_rate=Decimal("6.5000"), remark="初始利率"))

        # 计划与提醒
        db.add_all([
            models.Plan(ledger_id=ledger_id, plan_type="reminder", name="信用卡还款提醒",
                        frequency="monthly", start_date=datetime.now().strftime("%Y-%m-25"),
                        remind_days=3, remark="每月25日还款"),
            models.Plan(ledger_id=ledger_id, plan_type="income_expense", name="每月物业水电", txn_type="expense",
                        frequency="monthly", start_date=datetime.now().strftime("%Y-%m-06"),
                        account_id=saving.id, category_id=c("expense", "居住"), amount=Decimal("760"),
                        auto_execute=False, remark="物业费与水电支出计划"),
            models.Plan(ledger_id=ledger_id, plan_type="transfer", name="每月转储蓄",
                        frequency="monthly", start_date=datetime.now().strftime("%Y-%m-11"),
                        account_id=salary.id, to_account_id=saving.id, amount=Decimal("5000")),
            models.Plan(ledger_id=ledger_id, plan_type="fund_invest", name="沪深300定投",
                        frequency="monthly", start_date=datetime.now().strftime("%Y-%m-05"),
                        account_id=fund_acc.id, instrument_id=instruments["etf"], fund_symbol="510300",
                        amount=Decimal("2000"), fee_rate=Decimal("0.0015")),
        ])
        db.commit()


def _build_biz_ledger(ledger_id: int, cats: dict) -> None:
    """第二个账本（小本生意）：演示多账本，数据更精简。"""
    with ledger_session(ledger_id) as db:
        cash = models.Account(ledger_id=ledger_id, name="店面现金", type="cash", icon="💵",
                              initial_balance=Decimal("2000"), current_balance=Decimal("2000"))
        bank = models.Account(ledger_id=ledger_id, name="对公账户", type="bank", icon="🏦",
                              bank_name="建设银行", initial_balance=Decimal("80000"), current_balance=Decimal("80000"))
        db.add_all([cash, bank])
        db.flush()

        def add_txn(**kw):
            txn = models.Transaction(ledger_id=ledger_id, **kw)
            db.add(txn)
            db.flush()
            apply_transaction(db, txn, sign=1)

        c = lambda kind, name: cats[(kind, name)]
        for m in (1, 0):
            add_txn(type="income", amount=Decimal("32000"), account_id=bank.id,
                    category_id=c("income", "兼职"), occurred_at=_months_ago(m, 28), remark="月营业额")
            add_txn(type="expense", amount=Decimal("8000"), account_id=bank.id,
                    category_id=c("expense", "居住"), occurred_at=_months_ago(m, 5), remark="店面租金")
            add_txn(type="expense", amount=Decimal("12000"), account_id=bank.id,
                    category_id=c("expense", "购物"), occurred_at=_months_ago(m, 8), remark="进货")
        # 店面现金：零售收款与零星支出，使现金余额有据可查（期初 2000 → 期末 5000）
        cash_flows = [
            (1, 6, "income", "兼职", Decimal("2500"), "现金零售收款"),
            (1, 12, "expense", "餐饮", Decimal("800"), "员工餐补"),
            (0, 4, "income", "兼职", Decimal("2300"), "现金零售收款"),
            (0, 9, "expense", "购物", Decimal("1000"), "采购包装耗材"),
        ]
        for m, day, typ, cat_name, amt, note in cash_flows:
            add_txn(type=typ, amount=amt, account_id=cash.id,
                    category_id=c(typ, cat_name), occurred_at=_months_ago(m, day), remark=note)
        db.commit()


def build_demo() -> None:
    """生成一套覆盖全部功能的演示数据。"""
    reset_data_files()
    init_common_db()

    with SessionLocal() as s:
        home = models.Ledger(name="我的家庭账本", is_default=True, remark="演示数据：覆盖全部功能")
        biz = models.Ledger(name="小本生意账本", remark="演示多账本")
        s.add_all([home, biz])
        s.commit()
        home_id, biz_id = home.id, biz.id

    home_cats = _create_categories(home_id)
    biz_cats = _create_categories(biz_id)
    instruments = _build_common_settings(home_id)
    _build_home_ledger(home_id, home_cats, instruments)
    _build_biz_ledger(biz_id, biz_cats)
    print(f"[demo] 已生成演示数据库（家庭账本 + 生意账本） -> {settings.data_dir}")
