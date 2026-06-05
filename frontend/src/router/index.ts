import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import Transactions from '../views/Transactions.vue'
import Securities from '../views/Securities.vue'
import CreditCard from '../views/CreditCard.vue'
import ForexAccount from '../views/ForexAccount.vue'
import MetalAccount from '../views/MetalAccount.vue'
import FundAccount from '../views/FundAccount.vue'
import WealthAccount from '../views/WealthAccount.vue'
import Accounts from '../views/Accounts.vue'
import Statistics from '../views/Statistics.vue'
import Budgets from '../views/Budgets.vue'
import Investments from '../views/Investments.vue'
import Loans from '../views/Loans.vue'
import P2PProjects from '../views/P2PProjects.vue'
import Insurance from '../views/Insurance.vue'
import MajorAssetsView from '../views/MajorAssetsView.vue'
import Categories from '../views/Categories.vue'
import Parties from '../views/Parties.vue'
import FinancialProducts from '../views/FinancialProducts.vue'
import CurrencyRates from '../views/CurrencyRates.vue'
import MajorAssets from '../views/MajorAssets.vue'
import GoodsItems from '../views/GoodsItems.vue'
import DepositRates from '../views/DepositRates.vue'
import Placeholder from '../views/Placeholder.vue'
import InvestmentIncomeReport from '../views/InvestmentIncomeReport.vue'
const routes: RouteRecordRaw[] = [
  { path: '/', name: 'dashboard', component: Dashboard, meta: { title: '首页' } },
  { path: '/transactions', name: 'transactions', component: Transactions, meta: { title: '流水' } },
  { path: '/securities', name: 'securities', component: Securities, meta: { title: '证券账户' } },
  { path: '/funds', name: 'funds', component: FundAccount, meta: { title: '基金账户' } },
  { path: '/wealth', name: 'wealth', component: WealthAccount, meta: { title: '银行理财' } },
  { path: '/credit', name: 'credit', component: CreditCard, meta: { title: '信用卡' } },
  { path: '/forex', name: 'forex', component: ForexAccount, meta: { title: '外汇账户' } },
  { path: '/metal', name: 'metal', component: MetalAccount, meta: { title: '贵金属账户' } },
  { path: '/accounts', name: 'accounts', component: Accounts, meta: { title: '账户' } },
  { path: '/investments', name: 'investments', component: Investments, meta: { title: '投资' } },
  { path: '/p2p', name: 'p2p', component: P2PProjects, meta: { title: '网贷' } },
  { path: '/insurance', name: 'insurance', component: Insurance, meta: { title: '保险' } },
  { path: '/major-assets', name: 'major-assets', component: MajorAssetsView, meta: { title: '重大资产' } },
  { path: '/budgets', name: 'budgets', component: Budgets, meta: { title: '预算' } },
  { path: '/loans', name: 'loans', component: Loans, meta: { title: '债务' } },
  { path: '/categories', name: 'categories', component: Categories, meta: { title: '分类' } },
  { path: '/statistics', name: 'statistics', component: Statistics, meta: { title: '统计' } },
  // 财务报表
  { path: '/report/income-expense', component: Statistics, meta: { title: '日常收支表' } },
  { path: '/report/income-expense-detail', component: Transactions, meta: { title: '日常收支明细表' } },
  { path: '/report/account-ie', component: Placeholder, meta: { title: '账户日常收支' } },
  { path: '/report/tag-ie', component: Placeholder, meta: { title: '标签日常收支表' } },
  { path: '/report/compare', component: Placeholder, meta: { title: '两段时间收支对比表' } },
  { path: '/report/stat', component: Statistics, meta: { title: '收支统计表' } },
  { path: '/report/trend', component: Placeholder, meta: { title: '收支走势图' } },
  { path: '/report/monthly-avg', component: Placeholder, meta: { title: '月平均收支' } },
  { path: '/report/cashflow', component: Placeholder, meta: { title: '现金流表' } },
  { path: '/report/investment-income', component: InvestmentIncomeReport, meta: { title: '投资收益一览表' } },
  // 财务分析
  { path: '/analysis/budget', component: Budgets, meta: { title: '财务预算' } },
  { path: '/analysis/diagnosis', component: Statistics, meta: { title: '财务诊断' } },
  { path: '/analysis/plan', component: Placeholder, meta: { title: '财务规划' } },
  { path: '/analysis/goal', component: Placeholder, meta: { title: '财务目标' } },
  // 资料管理
  { path: '/data/categories', component: Categories, meta: { title: '收支项目' } },
  { path: '/data/parties', component: Parties, meta: { title: '人员与机构' } },
  { path: '/data/securities', component: FinancialProducts, meta: { title: '上市证券' } },
  { path: '/data/funds', component: FinancialProducts, meta: { title: '货币基金' } },
  { path: '/data/major-assets', component: MajorAssets, meta: { title: '重大资产' } },
  { path: '/data/goods', component: GoodsItems, meta: { title: '家居物品' } },
  { path: '/data/trade-fees', component: FinancialProducts, meta: { title: '证券交易费率' } },
  { path: '/data/other-finance', component: Placeholder, meta: { title: '其它金融产品' } },
  { path: '/data/currency-rate', component: CurrencyRates, meta: { title: '币种与汇率' } },
  { path: '/data/deposit-rate', component: DepositRates, meta: { title: '存款利率' } },
  { path: '/data/remarks', component: Placeholder, meta: { title: '常用备注' } }
]

export default createRouter({
  history: createWebHistory(),
  routes
})
