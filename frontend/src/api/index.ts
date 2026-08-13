import http from './http'
import type {
  Ledger, Account, AccountGroup, Party, Category, CategoryKind,
  Transaction, TransactionPage, IpoPending,
  Overview, CategoryStat, TrendItem, NetWorth,
  Budget, Holding, Loan, LoanRateAdjustment, LoanSchedule, Tag, InvestmentOverview, InvestmentIncomeReport, Diagnosis, Instrument, InstrumentPrice, TradeFeeRate, Currency, ExchangeRate, DepositRate, Plan, InsuranceDetail, Voucher
} from '../types'

// 响应拦截器已解包为 data，这里用泛型断言其真实返回类型
const get = <T>(url: string, config?: object) => http.get(url, config) as unknown as Promise<T>
const post = <T>(url: string, data?: unknown) => http.post(url, data) as unknown as Promise<T>
const put = <T>(url: string, data?: unknown) => http.put(url, data) as unknown as Promise<T>
const del = <T = { detail: string }>(url: string) => http.delete(url) as unknown as Promise<T>

export const api = {
  // 账本
  listLedgers: () => get<Ledger[]>('/ledgers'),
  createLedger: (data: Partial<Ledger>) => post<Ledger>('/ledgers', data),
  updateLedger: (id: number, data: Partial<Ledger>) => put<Ledger>(`/ledgers/${id}`, data),
  deleteLedger: (id: number) => del<{ detail: string; next_ledger_id: number }>(`/ledgers/${id}`),
  exportLedger: (lid: number) => get<Record<string, unknown>>(`/ledgers/${lid}/export`),
  importLedger: (data: unknown) =>
    post<{ detail: string; ledger_id: number; ledger_name: string }>(`/ledgers/import`, data),

  // 账户
  listAccounts: (lid: number) => get<Account[]>(`/ledgers/${lid}/accounts`),
  createAccount: (lid: number, data: Partial<Account>) => post<Account>(`/ledgers/${lid}/accounts`, data),
  updateAccount: (id: number, data: Partial<Account>) => put<Account>(`/accounts/${id}`, data),
  deleteAccount: (id: number) => del(`/accounts/${id}`),
  adjustAccount: (id: number, target_balance: number, mode: 'adjust' | 'income_expense' = 'adjust') =>
    post<Account>(`/accounts/${id}/adjust`, { target_balance, mode }),
  setAccountStatus: (id: number, status: 'active' | 'hidden' | 'closed') =>
    post<Account>(`/accounts/${id}/status?status=${status}`, {}),
  insuranceDetail: (id: number) => get<InsuranceDetail>(`/accounts/${id}/insurance-detail`),
  buyMajorAsset: (lid: number, data: Record<string, unknown>) =>
    post<Account>(`/ledgers/${lid}/major-assets/buy`, data),

  // 账户组
  listAccountGroups: (lid: number) => get<AccountGroup[]>(`/ledgers/${lid}/account-groups`),
  createAccountGroup: (lid: number, data: Partial<AccountGroup>) => post<AccountGroup>(`/ledgers/${lid}/account-groups`, data),
  deleteAccountGroup: (id: number) => del(`/account-groups/${id}`),

  // 人员与机构
  listParties: (lid: number, type?: string) => get<Party[]>(`/ledgers/${lid}/parties`, { params: { type } }),
  createParty: (lid: number, data: Partial<Party>) => post<Party>(`/ledgers/${lid}/parties`, data),
  updateParty: (id: number, data: Partial<Party>) => put<Party>(`/parties/${id}`, data),
  deleteParty: (id: number) => del(`/parties/${id}`),

  listInstruments: (lid: number, category?: string, params?: { q?: string; limit?: number }) =>
    get<Instrument[]>(`/ledgers/${lid}/instruments`, { params: { category, ...(params || {}) } }),
  createInstrument: (lid: number, data: Partial<Instrument>) => post<Instrument>(`/ledgers/${lid}/instruments`, data),
  updateInstrument: (id: number, data: Partial<Instrument>) => put<Instrument>(`/instruments/${id}`, data),
  deleteInstrument: (id: number) => del(`/instruments/${id}`),

  listInstrumentPrices: (lid: number, params?: { category?: string; instrument_id?: number }) =>
    get<InstrumentPrice[]>(`/ledgers/${lid}/instrument-prices`, { params }),
  createInstrumentPrice: (lid: number, data: Partial<InstrumentPrice>) =>
    post<InstrumentPrice>(`/ledgers/${lid}/instrument-prices`, data),
  updateInstrumentPrice: (id: number, data: Partial<InstrumentPrice>) =>
    put<InstrumentPrice>(`/instrument-prices/${id}`, data),
  deleteInstrumentPrice: (id: number) => del(`/instrument-prices/${id}`),

  listTradeFeeRates: (lid: number) => get<TradeFeeRate[]>(`/ledgers/${lid}/trade-fee-rates`),
  updateTradeFeeRate: (id: number, data: Partial<TradeFeeRate>) =>
    put<TradeFeeRate>(`/trade-fee-rates/${id}`, data),

  // 行情同步
  marketQuote: (code: string, kind: 'stock' | 'fund' = 'stock') =>
    get<{ code: string; name: string; price: string }>('/market/quote', { params: { code, kind } }),
  syncMarketPrices: (lid: number) =>
    post<{ updated: number; failed: string[]; items: { code: string; name: string; price: string }[] }>(
      `/ledgers/${lid}/market/sync-prices`, {}
    ),
  syncMarketCatalog: (lid: number, category: string) =>
    post<{ added: number; total_existing: number }>(
      `/ledgers/${lid}/market/sync-catalog?category=${encodeURIComponent(category)}`, {}
    ),
  syncForexRates: (lid: number) =>
    post<{ updated: number; added: number; failed: string[]; items: { code: string; name: string; rate: string }[] }>(
      `/ledgers/${lid}/market/sync-forex`, {}
    ),

  listCurrencies: (lid: number) => get<Currency[]>(`/ledgers/${lid}/currencies`),
  createCurrency: (lid: number, data: Partial<Currency>) =>
    post<Currency>(`/ledgers/${lid}/currencies`, data),
  supplementCurrencies: (lid: number) =>
    post<{ added: number; items: string[] }>(`/ledgers/${lid}/currencies/supplement`, {}),
  updateCurrency: (id: number, data: Partial<Currency>) => put<Currency>(`/currencies/${id}`, data),
  deleteCurrency: (id: number) => del(`/currencies/${id}`),

  listExchangeRates: (lid: number, params?: { currency_code?: string }) =>
    get<ExchangeRate[]>(`/ledgers/${lid}/exchange-rates`, { params }),
  createExchangeRate: (lid: number, data: Partial<ExchangeRate>) =>
    post<ExchangeRate>(`/ledgers/${lid}/exchange-rates`, data),
  updateExchangeRate: (id: number, data: Partial<ExchangeRate>) =>
    put<ExchangeRate>(`/exchange-rates/${id}`, data),
  deleteExchangeRate: (id: number) => del(`/exchange-rates/${id}`),

  // 存款利率
  listDepositRates: (lid: number) => get<DepositRate[]>(`/ledgers/${lid}/deposit-rates`),
  updateDepositRate: (id: number, data: Partial<DepositRate>) =>
    put<DepositRate>(`/deposit-rates/${id}`, data),

  // 计划与提醒
  listPlans: (lid: number) => get<Plan[]>(`/ledgers/${lid}/plans`),
  createPlan: (lid: number, data: Record<string, unknown>) => post<Plan>(`/ledgers/${lid}/plans`, data),
  updatePlan: (id: number, data: Record<string, unknown>) => put<Plan>(`/plans/${id}`, data),
  deletePlan: (id: number) => del(`/plans/${id}`),
  executePlan: (id: number, data: Record<string, unknown>) => post<Plan>(`/plans/${id}/execute`, data),

  // 分类
  listCategories: (lid: number, kind?: CategoryKind) => get<Category[]>(`/ledgers/${lid}/categories`, { params: { kind } }),
  createCategory: (lid: number, data: Partial<Category>) => post<Category>(`/ledgers/${lid}/categories`, data),
  updateCategory: (id: number, data: Partial<Category>) => put<Category>(`/categories/${id}`, data),
  deleteCategory: (id: number) => del(`/categories/${id}`),

  // 流水
  listTransactions: (lid: number, params?: Record<string, unknown>) => get<TransactionPage>(`/ledgers/${lid}/transactions`, { params }),
  createTransaction: (lid: number, data: Record<string, unknown>) => post<Transaction>(`/ledgers/${lid}/transactions`, data),
  updateTransaction: (id: number, data: Record<string, unknown>) => put<Transaction>(`/transactions/${id}`, data),
  deleteTransaction: (id: number) => del(`/transactions/${id}`),
  splitTransaction: (lid: number, data: Record<string, unknown>) => post<Transaction[]>(`/ledgers/${lid}/transactions/split`, data),
  salaryIncome: (lid: number, data: Record<string, unknown>) => post<Transaction[]>(`/ledgers/${lid}/salary`, data),
  getSplitGroup: (lid: number, group: string) => get<Transaction[]>(`/ledgers/${lid}/transactions/split/${group}`),
  updateSplitGroup: (lid: number, group: string, data: Record<string, unknown>) => put<Transaction[]>(`/ledgers/${lid}/transactions/split/${group}`, data),
  deleteSplitGroup: (lid: number, group: string) => del(`/ledgers/${lid}/transactions/split/${group}`),
  transferTransaction: (lid: number, data: Record<string, unknown>) => post<Transaction[]>(`/ledgers/${lid}/transactions/transfer`, data),
  exchangeTransaction: (lid: number, data: Record<string, unknown>) => post<Transaction[]>(`/ledgers/${lid}/transactions/exchange`, data),
  forexTrade: (lid: number, data: Record<string, unknown>) => post<Transaction[]>(`/ledgers/${lid}/forex/trade`, data),
  forexTransfer: (lid: number, data: Record<string, unknown>) => post<Transaction[]>(`/ledgers/${lid}/forex/transfer`, data),
  deferredExpense: (lid: number, data: Record<string, unknown>) => post<Transaction[]>(`/ledgers/${lid}/transactions/deferred`, data),

  // 标签
  listTags: (lid: number) => get<Tag[]>(`/ledgers/${lid}/tags`),
  createTag: (lid: number, data: Partial<Tag>) => post<Tag>(`/ledgers/${lid}/tags`, data),
  deleteTag: (id: number) => del(`/tags/${id}`),

  // 统计
  overview: (lid: number, params?: Record<string, unknown>) => get<Overview>(`/ledgers/${lid}/stats/overview`, { params }),
  byCategory: (lid: number, params?: Record<string, unknown>) => get<CategoryStat>(`/ledgers/${lid}/stats/by-category`, { params }),
  trend: (lid: number, params?: Record<string, unknown>) => get<TrendItem[]>(`/ledgers/${lid}/stats/trend`, { params }),
  netWorth: (lid: number) => get<NetWorth>(`/ledgers/${lid}/stats/net-worth`),
  investmentOverview: (lid: number) => get<InvestmentOverview>(`/ledgers/${lid}/stats/investment`),
  investmentIncome: (lid: number, params?: Record<string, unknown>) =>
    get<InvestmentIncomeReport>(`/ledgers/${lid}/stats/investment-income`, { params }),
  diagnosis: (lid: number) => get<Diagnosis>(`/ledgers/${lid}/stats/diagnosis`),

  // 预算
  listBudgets: (lid: number) => get<Budget[]>(`/ledgers/${lid}/budgets`),
  createBudget: (lid: number, data: Record<string, unknown>) => post<Budget>(`/ledgers/${lid}/budgets`, data),
  updateBudget: (id: number, data: Record<string, unknown>) => put<Budget>(`/budgets/${id}`, data),
  deleteBudget: (id: number) => del(`/budgets/${id}`),

  // 投资持仓
  listHoldings: (lid: number) => get<Holding[]>(`/ledgers/${lid}/holdings`),
  createHolding: (lid: number, data: Record<string, unknown>) => post<Holding>(`/ledgers/${lid}/holdings`, data),
  updateHolding: (id: number, data: Record<string, unknown>) => put<Holding>(`/holdings/${id}`, data),
  deleteHolding: (id: number) => del(`/holdings/${id}`),
  tradeBuy: (lid: number, data: Record<string, unknown>) => post<Holding>(`/ledgers/${lid}/trades/buy`, data),
  tradeSell: (lid: number, data: Record<string, unknown>) => post<Holding | null>(`/ledgers/${lid}/trades/sell`, data),
  // 新股申购 / 中签确认
  ipoSubscribe: (lid: number, data: Record<string, unknown>) => post<{ detail: string; txn_id: number }>(`/ledgers/${lid}/ipo/subscribe`, data),
  ipoPending: (lid: number, accountId?: number) =>
    get<IpoPending[]>(`/ledgers/${lid}/ipo/pending${accountId != null ? `?account_id=${accountId}` : ''}`),
  ipoConfirm: (lid: number, data: Record<string, unknown>) => post<{ detail: string; won: boolean }>(`/ledgers/${lid}/ipo/confirm`, data),

  // 债权债务
  listLoans: (lid: number) => get<Loan[]>(`/ledgers/${lid}/loans`),
  createLoan: (lid: number, data: Record<string, unknown>) => post<Loan>(`/ledgers/${lid}/loans`, data),
  updateLoan: (id: number, data: Record<string, unknown>) => put<Loan>(`/loans/${id}`, data),
  collectLoan: (id: number, data: Record<string, unknown>) => post<Loan>(`/loans/${id}/collect`, data),
  deleteLoan: (id: number) => del(`/loans/${id}`),
  listLoanRateAdjustments: (loanId: number) => get<LoanRateAdjustment[]>(`/loans/${loanId}/rate-adjustments`),
  createLoanRateAdjustment: (loanId: number, data: Record<string, unknown>) =>
    post<LoanRateAdjustment>(`/loans/${loanId}/rate-adjustments`, data),
  updateLoanRateAdjustment: (id: number, data: Record<string, unknown>) =>
    put<LoanRateAdjustment>(`/loan-rate-adjustments/${id}`, data),
  deleteLoanRateAdjustment: (id: number) => del(`/loan-rate-adjustments/${id}`),
  getLoanSchedule: (loanId: number) => get<LoanSchedule>(`/loans/${loanId}/schedule`),

  // 团购券
  listVouchers: (lid: number, accountId?: number) =>
    get<Voucher[]>(`/ledgers/${lid}/vouchers${accountId != null ? `?account_id=${accountId}` : ''}`),
  voucherBuy: (lid: number, data: Record<string, unknown>) => post<Voucher>(`/ledgers/${lid}/vouchers/buy`, data),
  voucherRedeem: (lid: number, voucherId: number, data: Record<string, unknown>) =>
    post<Voucher>(`/ledgers/${lid}/vouchers/${voucherId}/redeem`, data),
  voucherRefund: (lid: number, voucherId: number, data: Record<string, unknown>) =>
    post<Voucher>(`/ledgers/${lid}/vouchers/${voucherId}/refund`, data),
  deleteVoucher: (id: number) => del(`/vouchers/${id}`)
}
