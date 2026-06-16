// 全局数据类型定义

export interface Ledger {
  id: number
  name: string
  icon: string
  color: string
  currency: string
  remark?: string | null
  is_default: boolean
}

export type AccountType =
  | 'cash' | 'bank' | 'credit' | 'wallet' | 'prepaid'
  | 'stock' | 'fund' | 'money_fund' | 'bond' | 'reverse_repo' | 'wealth'
  | 'metal' | 'metal_td' | 'forex' | 'futures' | 'margin' | 'p2p'
  | 'goods' | 'major_asset' | 'insurance' | 'loan' | 'voucher'

export interface Account {
  id: number
  ledger_id: number
  name: string
  type: AccountType | string
  group_id?: number | null
  icon: string
  color: string
  currency: string
  initial_balance: string
  current_balance: string
  credit_limit?: string | null
  bill_day?: number | null
  repay_day?: number | null
  owner?: string | null
  remark?: string | null
  card_no?: string | null
  bank_name?: string | null
  start_date?: string | null
  expiry?: string | null
  cash_limit?: string | null
  min_repay_ratio?: string | null
  annual_fee?: string | null
  fee_waiver_type?: string
  fee_waiver_count?: number | null
  fee_waiver_amount?: string | null
  repay_type?: string
  repay_after_days?: number | null
  bill_day_txn?: string
  overdraft_remind?: boolean
  bill_day_last?: boolean
  currency2?: string | null
  overdraft1?: string | number | null
  overdraft2?: string | number | null
  overdraft_remind2?: boolean
  platform_name?: string | null
  platform_url?: string | null
  insured_person?: string | null
  city?: string | null
  social_code?: string | null
  premium_as_stat?: boolean
  stock_market?: string | null
  asset_nature?: string | null
  include_in_net: boolean
  is_active: boolean
  status?: string
  sort_order: number
}

export interface AccountGroup {
  id: number
  ledger_id: number
  name: string
  remark?: string | null
  sort_order: number
}
export interface Party {
  id: number
  ledger_id: number
  name: string
  type: 'member' | 'contact' | 'org' | string
  gender?: 'male' | 'female' | null
  birthday_type?: 'solar' | 'lunar' | null
  birthday?: string | null
  contact?: string | null
  address?: string | null
}

export interface Instrument {
  id: number
  ledger_id: number
  category: string
  code?: string | null
  name: string
  currency: string
  buy_fee_rate?: string | number | null
  redeem_fee_rate?: string | number | null
  issuer?: string | null
  start_date?: string | null
  end_date?: string | null
  term_value?: number | null
  term_unit?: string | null
  expected_rate?: string | number | null
  guaranteed?: boolean
  owner?: string | null
  asset_nature?: string | null
  subcategory?: string | null
  remark?: string | null
}

export interface InstrumentPrice {
  id: number
  instrument_id: number
  price_date: string
  price: string | number
  code?: string | null
  name?: string | null
}

export interface TradeFeeRate {
  id: number
  ledger_id: number
  group_key: string
  security_type: string
  sort_order: number
  buy_stamp_tax: string | number
  sell_stamp_tax: string | number
  buy_commission: string | number
  buy_min_commission: string | number
  sell_commission: string | number
  sell_min_commission: string | number
  surcharge: string | number
  transfer_fee: string | number
  settle_fee: string | number
  settle_cap: string | number
  trade_reg_fee: string | number
}

export interface Currency {
  id: number
  ledger_id: number
  name: string
  code: string
  is_home: boolean
  rate: string | number
  sort_order: number
}

export interface ExchangeRate {
  id: number
  ledger_id: number
  rate_date: string
  currency_code: string
  base_code: string
  rate: string | number
}

export interface DepositRate {
  id: number
  ledger_id: number
  group_key: 'cny' | 'foreign'
  sort_order: number
  save_type?: string | null
  term?: string | null
  rate: string | number
  currency_code?: string | null
  currency_name?: string | null
  r_current: string | number
  r_1m: string | number
  r_3m: string | number
  r_6m: string | number
  r_1y: string | number
  r_2y: string | number
  r_7d_notice: string | number
}

export type CategoryKind = 'income' | 'expense'
export interface Category {
  id: number
  ledger_id: number
  name: string
  kind: CategoryKind
  parent_id?: number | null
  icon: string
  color: string
  sort_order: number
  is_active: boolean
}

export type TransactionType = 'expense' | 'income' | 'transfer' | 'adjust'

export interface Transaction {
  id: number
  ledger_id: number
  type: TransactionType
  amount: string
  currency: string
  account_id: number
  to_account_id?: number | null
  category_id?: number | null
  fee: string
  occurred_at: string
  remark?: string | null
  merchant?: string | null
  created_at: string
  trade_price?: string | null
  trade_qty?: string | null
  trade_commission?: string | null
  trade_fee?: string | null
  trade_cost?: string | null
  trade_symbol?: string | null
  trade_exchange_rate?: string | null
  loan_id?: number | null
  collect_group?: string | null
  voucher_id?: number | null
  insurance_activity?: string | null
  ipo_status?: string | null
  tag_ids?: number[]
  split_group?: string | null
}

export interface TransactionPage {
  items: Transaction[]
  total: number
  page: number
  page_size: number
}

export interface IpoPending {
  txn_id: number
  symbol: string
  name: string
  amount: string
  quantity?: string | null
  price?: string | null
  funding_account_id: number
  security_account_id: number
  occurred_at: string
}

export interface InsuranceTxnRow {
  id: number
  occurred_at: string
  type: TransactionType
  premium: string
  collect: string
  activity: string
  remark?: string | null
}

export interface InsuranceDetail {
  account_id: number
  cash_value: string
  premium_total: string
  collect_total: string
  count: number
  rows: InsuranceTxnRow[]
}

export interface Overview {
  income: string
  expense: string
  balance: string
}

export interface CategoryStatItem {
  category_id: number | null
  name: string
  amount: string
  percent: number
}

export interface CategoryStat {
  total: string
  items: CategoryStatItem[]
}

export interface TrendItem {
  period: string
  income: string
  expense: string
}

export interface NetWorthGroup {
  name: string
  amount: string
}

export interface NetWorth {
  assets: string
  liabilities: string
  net_worth: string
  asset_groups: NetWorthGroup[]
  liability_groups: NetWorthGroup[]
}

export interface Budget {
  id: number
  ledger_id: number
  category_id: number | null
  period: 'month' | 'year'
  amount: string
  is_active: boolean
  category_name?: string | null
  spent: string
}

export interface Holding {
  id: number
  ledger_id: number
  account_id?: number | null
  symbol?: string | null
  name: string
  type: string
  currency?: string
  quantity: string
  cost: string
  price: string
  market_value: string
  profit: string
  profit_rate: number
}

export type LoanDirection = 'receivable' | 'payable'

export interface Voucher {
  id: number
  ledger_id: number
  account_id: number
  product: string
  quantity: number
  redeemed: number
  unit_price: string
  face_value: string
  source_account_id?: number | null
  purchased_at: string
  expiry_at?: string | null
  category_id?: number | null
  status: string
  remark?: string | null
  remaining: number
  occupied_value: string
  discount: string
  is_expired: boolean
}

export interface Loan {
  id: number
  ledger_id: number
  direction: LoanDirection
  counterparty: string
  item?: string | null
  currency?: string
  account_id?: number | null
  amount: string
  settled: string
  interest_rate?: string | null
  total_periods?: number | null
  remaining_periods?: number | null
  repay_method?: string | null
  occurred_at: string
  due_at?: string | null
  remark?: string | null
  is_closed: boolean
  remaining: string
  tag_ids?: number[]
  // 网贷（P2P）专用字段
  loan_kind?: string | null
  cash_account_id?: number | null
  interest_method?: string | null
  mgmt_fee_rate?: string | null
  term_value?: number | null
  term_unit?: string | null
  collect_interval?: number | null
  collect_interval_unit?: string | null
  collected_periods?: number | null
  per_interest?: string | null
  remaining_principal_interest?: string | null
  first_collect_at?: string | null
  auto_execute?: boolean
}

export interface LoanRateAdjustment {
  id: number
  ledger_id: number
  loan_id: number
  occurred_at: string
  interest_rate: string
  remark?: string | null
}

export interface LoanScheduleItem {
  period_no: number
  due_at: string
  annual_rate: string
  payment: string
  principal: string
  interest: string
  balance: string
  is_paid: boolean
}

export interface LoanSchedule {
  loan_id: number
  paid_periods: number
  total_periods: number
  paid_principal: string
  paid_interest: string
  remaining_principal: string
  remaining_interest: string
  items: LoanScheduleItem[]
}

export interface Tag {
  id: number
  ledger_id: number
  name: string
  color: string
  sort_order: number
}

export type PlanType = 'reminder' | 'income_expense' | 'transfer' | 'fund_invest' | 'loan_repay' | 'p2p_collect'

export interface Plan {
  id: number
  ledger_id: number
  plan_type: PlanType
  name: string
  frequency: string
  start_date: string
  end_date?: string | null
  next_run_date?: string | null
  status: 'active' | 'done' | 'paused'
  auto_execute: boolean
  remind_days: number
  account_id?: number | null
  to_account_id?: number | null
  fee_account_id?: number | null
  category_id?: number | null
  amount: string | number
  fee: string | number
  txn_type?: string | null
  instrument_id?: number | null
  fund_symbol?: string | null
  fee_rate?: string | number | null
  loan_id?: number | null
  remark?: string | null
  last_run_at?: string | null
  tags: Tag[]
}

export interface InvestmentRow {
  id: number
  name: string
  symbol?: string | null
  type: string
  quantity: string
  avg_cost: string
  position_cost: string
  price: string
  market_value: string
  float_profit: string
  change_pct: number
}

export interface InvestmentOverview {
  total_cost: string
  total_market_value: string
  total_float_profit: string
  total_change_pct: number
  rows: InvestmentRow[]
}

export interface InvestmentIncomeItem {
  symbol?: string | null
  name: string
  profit: string
}

export interface InvestmentIncomeGroup {
  account_id: number
  account_name: string
  account_type: string
  total_profit: string
  rows: InvestmentIncomeItem[]
}

export interface InvestmentIncomeReport {
  total_profit: string
  groups: InvestmentIncomeGroup[]
}

export interface Diagnosis {
  salary_income: string
  rent_income: string
  invest_income: string
  other_income: string
  total_income: string
  total_expense: string
  surplus: string
  surplus_ratio: number
  invest_ratio: number
}
