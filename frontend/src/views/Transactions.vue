<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useRecordStore } from '../stores/record'
import { useTradeStore } from '../stores/trade'
import { useLoanStore } from '../stores/loan'
import AccountOperations from '../components/AccountOperations.vue'
import type { Account, Category, Transaction, Tag, Holding, Instrument } from '../types'
import { fmtMoney } from '../utils/format'
const route = useRoute()
const ledgerStore = useLedgerStore()
const recordStore = useRecordStore()
const tradeStore = useTradeStore()
const loanStore = useLoanStore()

const items = ref<Transaction[]>([])
const billItems = ref<Transaction[]>([])
const accounts = ref<Account[]>([])
const categories = ref<Category[]>([])
const holdings = ref<Holding[]>([])
const wealthInstruments = ref<Instrument[]>([])
const page = ref(1)
const pageSize = 20
const total = ref(0)
const filterType = ref('')
const keyword = ref('')
const selectedAccountId = ref<number | null>(null)
const tags = ref<Tag[]>([])
const filterTagId = ref<number | null>(null)

// 是否处于单账户视图（来自账户中心点击）
const accountMode = computed(() => selectedAccountId.value != null)
const selectedAccount = computed(() => accounts.value.find((a) => a.id === selectedAccountId.value) || null)
const isCreditAccount = computed(() => selectedAccount.value?.type === 'credit')

// 投资类账户视角（证券 / 基金）
const FUND_TYPES = ['fund', 'open_fund', 'money_fund']
const STOCK_TYPES = ['stock', 'bond', 'reverse_repo', 'metal', 'metal_td', 'forex', 'futures', 'margin']
const isFundAccount = computed(() => FUND_TYPES.includes(selectedAccount.value?.type || ''))
const isWealthAccount = computed(() => selectedAccount.value?.type === 'wealth')
const isStockAccount = computed(() => STOCK_TYPES.includes(selectedAccount.value?.type || ''))
const isInvestAccount = computed(() => isFundAccount.value || isStockAccount.value || isWealthAccount.value)

const accountHoldings = computed(() =>
  holdings.value.filter((h) => h.account_id === selectedAccountId.value)
)
const totalHoldMarket = computed(() => accountHoldings.value.reduce((s, h) => s + toNum(h.market_value), 0))
const sharePct = (h: Holding) =>
  totalHoldMarket.value > 0 ? (toNum(h.market_value) / totalHoldMarket.value) * 100 : 0

// 银行理财产品资料（机构/购买日/到期日/预计年收益率），按代码或名称匹配持仓
const wealthInstMap = computed(() => {
  const m = new Map<string, Instrument>()
  for (const i of wealthInstruments.value) {
    if (i.code) m.set(i.code, i)
    m.set(i.name, i)
  }
  return m
})
function wealthInfo(h: Holding): Instrument | undefined {
  return wealthInstMap.value.get(h.symbol || '') || wealthInstMap.value.get(h.name)
}

// 投资账户汇总
const investSummary = computed(() => {
  let inflow = 0
  let outflow = 0
  for (const t of billItems.value) {
    const isIn = (t.type === 'income' && t.account_id === selectedAccountId.value) ||
      (t.type === 'transfer' && t.to_account_id === selectedAccountId.value)
    const isOut = (t.type === 'expense' && t.account_id === selectedAccountId.value) ||
      (t.type === 'transfer' && t.account_id === selectedAccountId.value)
    if (isIn) inflow += toNum(t.amount)
    if (isOut) outflow += toNum(t.amount)
  }
  const market = totalHoldMarket.value
  const cost = accountHoldings.value.reduce((s, h) => s + toNum(h.cost), 0)
  const floatProfit = accountHoldings.value.reduce((s, h) => s + toNum(h.profit), 0)
  const avail = toNum(selectedAccount.value?.current_balance)
  return {
    inflow, outflow, cost, market, floatProfit, avail,
    total: avail + market
  }
})

const fmtDate = (v: string) => (v || '').slice(0, 10)
const toNum = (v: string | number | null | undefined) => Number(v || 0)

function accountName(id?: number | null): string {
  return accounts.value.find((a) => a.id === id)?.name || '-'
}

function categoryName(id?: number | null): string {
  return categories.value.find((c) => c.id === id)?.name || ''
}

// 单账户视角的流入/流出；全局视角下收入计入流入、支出计入流出
function inAmount(t: Transaction): string {
  const selected = selectedAccountId.value
  if (t.type === 'adjust') return toNum(t.amount) > 0 ? fmtMoney(t.amount) : ''
  if (selected != null) {
    if (t.type === 'income' && t.account_id === selected) return fmtMoney(t.amount)
    if (t.type === 'transfer' && t.to_account_id === selected) return fmtMoney(t.amount)
    return ''
  }
  return t.type === 'income' ? fmtMoney(t.amount) : ''
}

function outAmount(t: Transaction): string {
  const selected = selectedAccountId.value
  if (t.type === 'adjust') return toNum(t.amount) < 0 ? fmtMoney(-toNum(t.amount)) : ''
  if (selected != null) {
    if (t.type === 'expense' && t.account_id === selected) return fmtMoney(t.amount)
    if (t.type === 'transfer' && t.account_id === selected) return fmtMoney(t.amount)
    return ''
  }
  return t.type === 'expense' ? fmtMoney(t.amount) : ''
}

function activityLabel(t: Transaction): string {
  if (t.type === 'transfer') {
    return `转账 | ${accountName(t.account_id)} → ${accountName(t.to_account_id)}`
  }
  if (t.type === 'adjust') return '余额调整'
  if (t.remark === '分拆收支') return '分拆收支'
  const cat = categoryName(t.category_id)
  if (cat) return `【${cat}】`
  return t.type === 'income' ? '收入' : '支出'
}

function assetAccount(t: Transaction): string {
  return accountName(t.account_id)
}

// 证券明细中的逐笔交易元数据（价格/数量/佣金/总费用）
function tradeMeta(t: Transaction) {
  return {
    price: t.trade_price != null ? fmtMoney(t.trade_price) : '-',
    qty: t.trade_qty != null ? String(Number(t.trade_qty)) : '-',
    commission: t.trade_commission != null ? fmtMoney(t.trade_commission) : '-',
    fee: t.trade_fee != null ? fmtMoney(t.trade_fee) : '-'
  }
}

const summaryIncome = computed(() => displayItems.value.reduce((s, t) => s + toNum(inAmount(t)), 0))
const summaryExpense = computed(() => displayItems.value.reduce((s, t) => s + toNum(outAmount(t)), 0))
const summaryDiff = computed(() => summaryIncome.value - summaryExpense.value)

async function loadMeta() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  const exp = await api.listCategories(lid, 'expense')
  const inc = await api.listCategories(lid, 'income')
  categories.value = [...exp, ...inc]
  tags.value = await api.listTags(lid)
  holdings.value = await api.listHoldings(lid)
  await loadWealthInstruments()
  const qAccount = Number(route.query.account_id || 0)
  if (qAccount && accounts.value.some((a) => a.id === qAccount)) {
    selectedAccountId.value = qAccount
  } else {
    selectedAccountId.value = null
  }
}

async function loadWealthInstruments() {
  const lid = ledgerStore.currentId
  if (!lid || !isWealthAccount.value) {
    wealthInstruments.value = []
    return
  }
  wealthInstruments.value = await api.listInstruments(lid, 'bank_wealth')
}

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  const res = await api.listTransactions(lid, {
    page: page.value,
    page_size: pageSize,
    account_id: selectedAccountId.value || undefined,
    type: filterType.value || undefined,
    keyword: keyword.value || undefined,
    tag_id: filterTagId.value || undefined
  })
  items.value = res.items
  total.value = res.total
}

async function loadBillData() {
  const lid = ledgerStore.currentId
  if (!lid || !selectedAccountId.value) {
    billItems.value = []
    return
  }
  const res = await api.listTransactions(lid, {
    page: 1,
    page_size: 100,
    account_id: selectedAccountId.value
  })
  billItems.value = res.items
}

async function remove(id: number) {
  await ElMessageBox.confirm('确定删除这笔流水？', '提示', { type: 'warning' })
  await api.deleteTransaction(id)
  ElMessage.success('已删除')
  load()
  loadBillData()
}

// 投资账户记账：打开买入/卖出弹窗（预选当前账户；基金账户自动显示为申购/赎回）
function onInvestRecord(mode: string) {
  tradeStore.open(mode === 'sell' ? 'sell' : 'buy', selectedAccountId.value || undefined)
}

interface BillRow {
  key: string
  period: string
  billDay: string
  repayDay: string
  inAmount: number
  outAmount: number
  billAmount: number
  pending: boolean
}

const selectedCycleKey = ref<string>('')
const pad = (n: number) => String(n).padStart(2, '0')
const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

// 账单周期截止日（账单日）：根据交易日期与账单日推算其所属账单周期
function billCycleEnd(dateStr: string, billDay: number, billDayTxn: string): Date {
  const s = (dateStr || '').slice(0, 10)
  const d = new Date(s + 'T00:00:00')
  const day = d.getDate()
  let y = d.getFullYear()
  let m = d.getMonth() // 0-based
  // 账单日当天：计入下期则归入下一周期
  if (day > billDay || (day === billDay && billDayTxn === 'next')) {
    m += 1
    if (m > 11) { m = 0; y += 1 }
  }
  return new Date(y, m, billDay)
}

const billRows = computed<BillRow[]>(() => {
  const acc = selectedAccount.value
  if (!acc) return []
  const billDay = acc.bill_day || 1
  const billDayTxn = acc.bill_day_txn || 'next'
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const byCycle = new Map<string, BillRow>()
  for (const t of billItems.value) {
    if (!t.occurred_at) continue
    const end = billCycleEnd(t.occurred_at, billDay, billDayTxn)
    // 周期起始日：上一账单日的次日
    const start = new Date(end.getFullYear(), end.getMonth() - 1, billDay + 1)
    const key = ymd(end)
    if (!byCycle.has(key)) {
      // 账单日尚未到达（含当天）：账单未出
      const pending = end.getTime() > today.getTime()
      // 还款日推算：固定还款日（小于等于账单日则落在次月），或账单日之后 N 天
      let repayDate: Date
      if (acc.repay_type === 'after_bill' && acc.repay_after_days != null) {
        repayDate = new Date(end.getFullYear(), end.getMonth(), end.getDate() + Number(acc.repay_after_days))
      } else {
        const repayDay = acc.repay_day || 10
        let ry = end.getFullYear()
        let rm = end.getMonth()
        if (repayDay <= billDay) { rm += 1; if (rm > 11) { rm = 0; ry += 1 } }
        repayDate = new Date(ry, rm, repayDay)
      }
      byCycle.set(key, {
        key,
        period: pending ? `${ymd(start)} ~ 未出账单` : `${ymd(start)} ~ ${ymd(end)}`,
        billDay: pending ? '未出账单' : ymd(end),
        repayDay: pending ? '—' : ymd(repayDate),
        inAmount: 0,
        outAmount: 0,
        billAmount: 0,
        pending
      })
    }
    const row = byCycle.get(key)!
    const isIn = (t.type === 'income' && t.account_id === acc.id) || (t.type === 'transfer' && t.to_account_id === acc.id)
    const isOut = (t.type === 'expense' && t.account_id === acc.id) || (t.type === 'transfer' && t.account_id === acc.id)
    if (isIn) row.inAmount += toNum(t.amount)
    if (isOut) row.outAmount += toNum(t.amount)
    row.billAmount = row.outAmount - row.inAmount
  }
  return Array.from(byCycle.entries())
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([, v]) => v)
    .slice(0, 12)
})

// 选中某个账单周期后，明细表只显示该周期的记录
const displayItems = computed(() => {
  if (!(accountMode.value && isCreditAccount.value) || !selectedCycleKey.value) return collapseSplits(items.value)
  const acc = selectedAccount.value
  if (!acc) return collapseSplits(items.value)
  const billDay = acc.bill_day || 1
  const billDayTxn = acc.bill_day_txn || 'next'
  return collapseSplits(billItems.value.filter(
    (t) => t.occurred_at && ymd(billCycleEnd(t.occurred_at, billDay, billDayTxn)) === selectedCycleKey.value
  ))
})

// 将同一分拆组的多笔明细折叠为一行（金额累加，活动类型显示“分拆收支”）
function collapseSplits(list: Transaction[]): Transaction[] {
  const out: Transaction[] = []
  const groupIndex = new Map<string, number>()
  for (const t of list) {
    const g = t.split_group
    if (!g) { out.push(t); continue }
    const idx = groupIndex.get(g)
    if (idx == null) {
      groupIndex.set(g, out.length)
      out.push({ ...t, category_id: null, remark: '分拆收支' })
    } else {
      const row = out[idx]
      row.amount = String(toNum(row.amount) + toNum(t.amount))
    }
  }
  return out
}

function selectCycle(row: BillRow) {
  selectedCycleKey.value = row.key
}

const cycleRowClass = ({ row }: { row: BillRow }) =>
  row.key === selectedCycleKey.value ? 'cycle-selected' : ''

// 账单周期变化后默认选中“未出账单”（无则选最近一期）
watch(billRows, (rows) => {
  if (!rows.length) { selectedCycleKey.value = ''; return }
  if (!rows.some((r) => r.key === selectedCycleKey.value)) {
    const pending = rows.find((r) => r.pending)
    selectedCycleKey.value = (pending || rows[0]).key
  }
}, { immediate: true })

onMounted(async () => {
  await loadMeta()
  await load()
  await loadBillData()
})

watch(() => ledgerStore.currentId, async () => {
  page.value = 1
  await loadMeta()
  await load()
  await loadBillData()
})

watch([filterType, page], load)
watch(() => recordStore.savedAt, async () => {
  await load()
  await loadBillData()
})
watch(() => tradeStore.savedAt, async () => {
  await loadMeta()
  await load()
  await loadBillData()
})
watch(() => loanStore.savedAt, async () => {
  await loadMeta()
  await load()
  await loadBillData()
})
async function onOpSaved() {
  await loadMeta()
  await load()
  await loadBillData()
}
watch(selectedAccountId, async () => {
  page.value = 1
  selectedCycleKey.value = ''
  await loadWealthInstruments()
  await load()
  await loadBillData()
})

watch(() => route.query.account_id, async (v) => {
  const id = Number(v || 0)
  selectedAccountId.value = id && accounts.value.some((a) => a.id === id) ? id : null
})

// 行操作：分拆组走整组编辑/删除，普通流水走单笔编辑/删除
const opsRef = ref<InstanceType<typeof AccountOperations> | null>(null)
function onEditRow(row: Transaction) {
  if (row.split_group) {
    opsRef.value?.openSplitEdit(row.split_group)
    return
  }
  // 证券/基金买卖流水：打开对应的交易对话框进行编辑
  if (row.trade_qty != null && row.trade_symbol) {
    const mode = row.type === 'income' ? 'sell' : 'buy'
    const h = holdings.value.find((x) => x.symbol === row.trade_symbol && x.account_id === row.account_id)
    const nameFromRemark = (row.remark || '').replace(/^(买入|卖出|申购|赎回)[：:]/, '').replace(/\s*\d.*$/, '')
    tradeStore.openEdit(mode, {
      id: row.id,
      symbol: row.trade_symbol,
      name: h?.name || nameFromRemark || row.trade_symbol,
      account_id: row.account_id,
      price: row.trade_price != null ? Number(row.trade_price) : null,
      quantity: row.trade_qty != null ? Number(row.trade_qty) : null,
      fee_total: row.trade_fee != null ? Number(row.trade_fee) : null,
      commission: row.trade_commission != null ? Number(row.trade_commission) : null,
      occurred_at: row.occurred_at,
      remark: row.remark ?? null,
      tag_ids: row.tag_ids ? [...row.tag_ids] : []
    })
    return
  }
  recordStore.edit(row)
}
async function onDeleteRow(row: Transaction) {
  if (row.split_group) {
    await ElMessageBox.confirm('确定删除这组分拆收支？', '提示', { type: 'warning' })
    await api.deleteSplitGroup(ledgerStore.currentId as number, row.split_group)
    ElMessage.success('已删除')
    await load()
    await loadBillData()
  } else {
    await remove(row.id)
  }
}
</script>

<template>
  <div class="tx-page">
    <section class="tx-main">
      <!-- 标题栏 -->
      <div class="tx-header-row">
        <div class="account-title">
          <template v-if="accountMode">
            <span class="t-name">{{ selectedAccount?.name }}</span>
            <span class="t-amount" :class="{ expense: Number(selectedAccount?.current_balance || 0) < 0 }">
              {{ selectedAccount ? fmtMoney(selectedAccount.current_balance) : '' }}
            </span>
          </template>
          <template v-else>
            <span class="t-name">财务记录</span>
          </template>
        </div>
        <div class="toolbar-right">
          <el-dropdown v-if="isInvestAccount" @command="onInvestRecord">
            <el-button>记账</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="buy">{{ isFundAccount ? '申购基金' : '证券买入' }}</el-dropdown-item>
                <el-dropdown-item command="sell">{{ isFundAccount ? '赎回基金' : '证券卖出' }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <AccountOperations
            v-else
            ref="opsRef"
            :account="selectedAccount"
            :accounts="accounts"
            :tags="tags"
            @saved="onOpSaved"
          />
          <el-input v-model="keyword" placeholder="查找" style="width: 160px" @keyup.enter="load" clearable />
          <el-select v-model="filterType" style="width: 110px">
            <el-option label="全部记录" value="" />
            <el-option label="收入" value="income" />
            <el-option label="支出" value="expense" />
            <el-option label="转账" value="transfer" />
          </el-select>
          <el-select v-model="filterTagId" style="width: 120px" placeholder="标签" clearable @change="load">
            <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
          <el-button @click="load">查找</el-button>
        </div>
      </div>

      <!-- 信用卡账单区块（仅信用卡账户视角） -->
      <div v-if="accountMode && isCreditAccount" class="credit-bill-panel">
        <div class="bill-title">账单记录</div>
        <el-table
          :data="billRows"
          border
          size="small"
          style="width: 100%"
          highlight-current-row
          :row-class-name="cycleRowClass"
          @row-click="selectCycle"
        >
          <el-table-column prop="period" label="账单记录时段" min-width="160" />
          <el-table-column label="账单日" width="120">
            <template #default="scope">
              <span :class="{ 'bill-pending': scope.row.pending }">{{ scope.row.billDay }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="repayDay" label="还款日" width="120" />
          <el-table-column label="流入金额" width="120">
            <template #default="scope">{{ fmtMoney(scope.row.inAmount) }}</template>
          </el-table-column>
          <el-table-column label="流出金额" width="120">
            <template #default="scope">{{ fmtMoney(scope.row.outAmount) }}</template>
          </el-table-column>
          <el-table-column label="账单金额" width="120">
            <template #default="scope">
              <span :class="{ expense: scope.row.billAmount > 0, income: scope.row.billAmount <= 0 }">{{ fmtMoney(scope.row.billAmount) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 投资账户：持仓与汇总（证券 / 基金） -->
      <div v-if="accountMode && isInvestAccount" class="invest-panel">
        <el-table :data="accountHoldings" border size="small" style="width: 100%" empty-text="暂无持仓">
          <template v-if="isWealthAccount">
            <el-table-column label="产品名称" min-width="200">
              <template #default="scope">{{ scope.row.symbol ? scope.row.symbol + ' ' : '' }}{{ scope.row.name }}</template>
            </el-table-column>
            <el-table-column label="机构" min-width="130">
              <template #default="scope">{{ wealthInfo(scope.row)?.issuer || '—' }}</template>
            </el-table-column>
            <el-table-column label="累计金额" width="130" align="right">
              <template #default="scope">{{ fmtMoney(scope.row.market_value) }}</template>
            </el-table-column>
            <el-table-column label="占比%" width="100" align="right">
              <template #default="scope">{{ sharePct(scope.row).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="购买日" width="120">
              <template #default="scope">{{ wealthInfo(scope.row)?.start_date || '—' }}</template>
            </el-table-column>
            <el-table-column label="到期日" width="120">
              <template #default="scope">{{ wealthInfo(scope.row)?.end_date || '—' }}</template>
            </el-table-column>
            <el-table-column label="预计年收益率%" width="130" align="right">
              <template #default="scope">{{ wealthInfo(scope.row)?.expected_rate != null ? Number(wealthInfo(scope.row)!.expected_rate).toFixed(2) : '—' }}</template>
            </el-table-column>
          </template>
          <template v-else-if="isFundAccount">
            <el-table-column label="基金名称" min-width="240">
              <template #default="scope">{{ scope.row.symbol ? scope.row.symbol + ' ' : '' }}{{ scope.row.name }}</template>
            </el-table-column>
            <el-table-column label="累计金额" width="140" align="right">
              <template #default="scope">{{ fmtMoney(scope.row.market_value) }}</template>
            </el-table-column>
            <el-table-column label="占比%" width="100" align="right">
              <template #default="scope">{{ sharePct(scope.row).toFixed(2) }}</template>
            </el-table-column>
          </template>
          <template v-else>
            <el-table-column label="证券名称" min-width="200">
              <template #default="scope">{{ scope.row.symbol ? scope.row.symbol + ' ' : '' }}{{ scope.row.name }}</template>
            </el-table-column>
            <el-table-column label="持仓数量" width="110" align="right">
              <template #default="scope">{{ scope.row.quantity }}</template>
            </el-table-column>
            <el-table-column label="持仓成本" width="120" align="right">
              <template #default="scope">{{ fmtMoney(scope.row.cost) }}</template>
            </el-table-column>
            <el-table-column label="市值" width="120" align="right">
              <template #default="scope">{{ fmtMoney(scope.row.market_value) }}</template>
            </el-table-column>
            <el-table-column label="占比%" width="90" align="right">
              <template #default="scope">{{ sharePct(scope.row).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="浮动盈亏" width="120" align="right">
              <template #default="scope">
                <span :class="toNum(scope.row.profit) >= 0 ? 'income' : 'expense'">{{ fmtMoney(scope.row.profit) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="均价" width="110" align="right">
              <template #default="scope">{{ fmtMoney(toNum(scope.row.quantity) ? toNum(scope.row.cost) / toNum(scope.row.quantity) : 0) }}</template>
            </el-table-column>
            <el-table-column label="现价" width="110" align="right">
              <template #default="scope">{{ fmtMoney(scope.row.price) }}</template>
            </el-table-column>
          </template>
        </el-table>

        <div class="invest-summary">
          <span>资金转入<b class="income">{{ fmtMoney(investSummary.inflow) }}</b></span>
          <span>资金转出<b class="expense">{{ fmtMoney(investSummary.outflow) }}</b></span>
          <template v-if="isStockAccount">
            <span>总浮动盈亏<b :class="investSummary.floatProfit >= 0 ? 'income' : 'expense'">{{ fmtMoney(investSummary.floatProfit) }}</b></span>
            <span>总成本<b>{{ fmtMoney(investSummary.cost) }}</b></span>
          </template>
          <span>总市值<b>{{ fmtMoney(investSummary.market) }}</b></span>
          <span>可用资金<b>{{ fmtMoney(investSummary.avail) }}</b></span>
          <span>总计<b>{{ fmtMoney(investSummary.total) }}</b></span>
        </div>
      </div>

      <!-- 流水明细表 -->
      <div class="detail-wrap">
        <!-- 投资账户明细（证券 / 基金） -->
        <el-table v-if="accountMode && isInvestAccount" :data="displayItems" stripe style="width: 100%" empty-text="暂无记录">
          <el-table-column label="日期" width="110">
            <template #default="scope">{{ fmtDate(scope.row.occurred_at) }}</template>
          </el-table-column>
          <template v-if="isStockAccount">
            <el-table-column label="价格" width="100" align="right">
              <template #default="scope">{{ tradeMeta(scope.row).price }}</template>
            </el-table-column>
            <el-table-column label="数量" width="100" align="right">
              <template #default="scope">{{ tradeMeta(scope.row).qty }}</template>
            </el-table-column>
            <el-table-column label="佣金" width="100" align="right">
              <template #default="scope">{{ tradeMeta(scope.row).commission }}</template>
            </el-table-column>
            <el-table-column label="总费用" width="100" align="right">
              <template #default="scope">{{ tradeMeta(scope.row).fee }}</template>
            </el-table-column>
          </template>
          <el-table-column label="交易金额" width="130" align="right">
            <template #default="scope">{{ fmtMoney(scope.row.amount) }}</template>
          </el-table-column>
          <el-table-column label="活动类型" min-width="180">
            <template #default="scope">{{ activityLabel(scope.row) }}</template>
          </el-table-column>
          <el-table-column label="标签" min-width="100">
            <template #default="scope">{{ scope.row.type === 'transfer' ? '-' : categoryName(scope.row.category_id) || '-' }}</template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="180" />
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="scope">
              <el-button link type="primary" @click="onEditRow(scope.row)">修改</el-button>
              <el-button link type="danger" @click="onDeleteRow(scope.row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-table v-else :data="displayItems" stripe style="width: 100%" empty-text="暂无记录">
          <el-table-column label="日期" width="110">
            <template #default="scope">{{ fmtDate(scope.row.occurred_at) }}</template>
          </el-table-column>
          <el-table-column label="活动类型" min-width="180">
            <template #default="scope">{{ activityLabel(scope.row) }}</template>
          </el-table-column>
          <el-table-column label="流入" width="120" align="right">
            <template #default="scope"><span class="income">{{ inAmount(scope.row) }}</span></template>
          </el-table-column>
          <el-table-column label="流出" width="120" align="right">
            <template #default="scope"><span class="expense">{{ outAmount(scope.row) }}</span></template>
          </el-table-column>
          <el-table-column label="资产账户" min-width="140">
            <template #default="scope">{{ assetAccount(scope.row) }}</template>
          </el-table-column>
          <el-table-column label="标签" min-width="100">
            <template #default="scope">{{ scope.row.type === 'transfer' ? '-' : categoryName(scope.row.category_id) || '-' }}</template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="200" />
          <el-table-column label="币种" width="80">
            <template #default="scope">{{ scope.row.currency || '人民币' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="scope">
              <el-button link type="primary" @click="onEditRow(scope.row)">修改</el-button>
              <el-button link type="danger" @click="onDeleteRow(scope.row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div style="margin-top: 10px; text-align: center" v-if="!(accountMode && isCreditAccount && selectedCycleKey) && total > pageSize">
          <el-pagination
            layout="prev, pager, next"
            :total="total"
            :page-size="pageSize"
            :current-page="page"
            @current-change="(p: number) => (page = p)"
          />
        </div>
      </div>

      <!-- 底部汇总 -->
      <div class="sum-bar">
        <span>流入：<b class="income">{{ fmtMoney(summaryIncome) }}</b></span>
        <span>流出：<b class="expense">{{ fmtMoney(summaryExpense) }}</b></span>
        <span>差额：<b :class="summaryDiff >= 0 ? 'income' : 'expense'">{{ fmtMoney(summaryDiff) }}</b></span>
        <span>记录数：<b>{{ total }}</b></span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.tx-page {
  padding: 0;
}

.tx-main {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 52px);
  background: #f3f6f9;
}

.tx-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  border-bottom: 1px solid #c8d3de;
  background: #fff;
  padding: 12px 16px;
}

.account-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.account-title .back {
  font-size: 13px;
  color: #3f79a8;
  cursor: pointer;
}

.account-title .t-name {
  font-size: 18px;
  font-weight: 700;
  color: #415163;
}

.account-title .t-amount {
  font-size: 18px;
  color: #2e9c4f;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.credit-bill-panel {
  padding: 12px 16px;
  border-bottom: 1px solid #c8d3de;
  background: #f8fafc;
}

.bill-title {
  color: #55677a;
  font-weight: 700;
  margin-bottom: 8px;
}

.bill-pending {
  color: #e6a23c;
  font-weight: 600;
}

.credit-bill-panel :deep(.el-table__row) {
  cursor: pointer;
}

.credit-bill-panel :deep(.cycle-selected) > td.el-table__cell {
  background: #e8f1f8 !important;
}

.detail-wrap {
  flex: 1;
  padding: 12px 16px;
}

.invest-panel {
  padding: 12px 16px;
  border-bottom: 1px solid #c8d3de;
  background: #f8fafc;
}

.invest-summary {
  display: flex;
  gap: 26px;
  flex-wrap: wrap;
  margin-top: 10px;
  padding: 8px 4px;
  color: #6a7a8a;
  font-size: 13px;
}

.invest-summary b {
  display: block;
  color: #415163;
  font-size: 15px;
  margin-top: 2px;
}

.income {
  color: #2e9c4f;
}

.expense {
  color: #de6d6d !important;
}

.sum-bar {
  background: #edf2f7;
  border-top: 1px solid #c8d3de;
  display: flex;
  gap: 22px;
  flex-wrap: wrap;
  padding: 10px 16px;
  color: #546576;
}

:deep(.el-table th.el-table__cell) {
  background: #eef2f6;
  color: #4a5a6a;
  font-weight: 700;
}

@media (max-width: 768px) {
  .toolbar-right {
    width: 100%;
  }
}
</style>
