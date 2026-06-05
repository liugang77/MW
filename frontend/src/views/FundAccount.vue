<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useTradeStore } from '../stores/trade'
import type { Account, Category, Transaction, Tag, Holding } from '../types'
import { fmtMoney, fmtNum } from '../utils/format'

const route = useRoute()
const ledgerStore = useLedgerStore()
const tradeStore = useTradeStore()

const accounts = ref<Account[]>([])
const categories = ref<Category[]>([])
const tags = ref<Tag[]>([])
const holdings = ref<Holding[]>([])
const transactions = ref<Transaction[]>([])
const selectedAccountId = ref<number | null>(null)
const holdingScope = ref<'current' | 'all'>('current')
const bottomTab = ref<'txns' | 'pnl'>('txns')

const FUND_TYPES = ['fund', 'open_fund', 'money_fund']
const fundAccounts = computed(() => accounts.value.filter((a) => FUND_TYPES.includes(a.type)))
const selectedAccount = computed(() => accounts.value.find((a) => a.id === selectedAccountId.value) || null)
// 净值式基金（开放式基金）：净值波动，按「数量×净值」展示，含均价/净值/收益率
const isNavFund = computed(() => ['fund', 'open_fund'].includes(selectedAccount.value?.type || ''))
// 货币基金：净值恒为 1，按累计金额展示
const isAmountStyle = computed(() => selectedAccount.value?.type === 'money_fund')

const fmt = (v: string | number | null | undefined) => fmtMoney(v)
const fmt4 = (v: string | number | null | undefined) => fmtNum(v, 4)
const fmtDate = (v: string) => (v || '').slice(0, 10)
const toNum = (v: string | number | null | undefined) => Number(v || 0)
const floatRate = (h: Holding) => (toNum(h.cost) ? (toNum(h.profit) / toNum(h.cost)) * 100 : 0)

const accountHoldings = computed(() =>
  selectedAccountId.value ? holdings.value.filter((h) => h.account_id === selectedAccountId.value) : []
)
const totalHoldMarket = computed(() => accountHoldings.value.reduce((s, h) => s + toNum(h.market_value), 0))
const sharePct = (h: Holding) =>
  totalHoldMarket.value > 0 ? (toNum(h.market_value) / totalHoldMarket.value) * 100 : 0

const tradedSymbolMap = computed(() => {
  const m = new Map<string, string>()
  for (const t of accountTxns.value) {
    if (!t.trade_symbol) continue
    const nm = (t.remark || '')
      .replace(/^(申购|赎回|基金申购|基金赎回|买入|卖出)[：:]/, '')
      .replace(/\s*\d.*$/, '')
      .trim()
    if (!m.has(t.trade_symbol) || (!m.get(t.trade_symbol) && nm)) m.set(t.trade_symbol, nm || t.trade_symbol)
  }
  return m
})

const displayHoldings = computed(() => {
  const rows: Holding[] = [...accountHoldings.value]
  if (holdingScope.value === 'all') {
    const held = new Set(accountHoldings.value.map((h) => h.symbol))
    for (const [sym, name] of tradedSymbolMap.value) {
      if (held.has(sym)) continue
      rows.push({
        id: -1 * rows.length - 1,
        account_id: selectedAccountId.value as number,
        symbol: sym, name, type: selectedAccount.value?.type || 'fund',
        quantity: 0, cost: 0, price: 0, market_value: 0, profit: 0, profit_rate: 0,
      } as unknown as Holding)
    }
  }
  return rows
})

const realizedPnl = computed(() =>
  accountTxns.value
    .filter((t) => t.type === 'income' && t.trade_symbol)
    .map((t) => {
      const amount = toNum(t.amount)
      const costBasis = toNum(t.trade_cost)
      const profit = amount - costBasis
      const rate = costBasis > 0 ? (profit / costBasis) * 100 : 0
      const name = holdings.value.find((h) => h.symbol === t.trade_symbol)?.name
        || tradedSymbolMap.value.get(t.trade_symbol || '') || t.trade_symbol || ''
      return {
        id: t.id, occurred_at: t.occurred_at, name, activity: '基金赎回',
        price: t.trade_price, quantity: t.trade_qty, amount, profit, rate,
      }
    })
    .sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : -1))
)
const realizedTotal = computed(() => realizedPnl.value.reduce((s, r) => s + r.profit, 0))

const summary = computed(() => {
  let inflow = 0
  let outflow = 0
  for (const t of transactions.value) {
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
  return { inflow, outflow, cost, market, floatProfit, realized: realizedTotal.value, avail, total: avail + market }
})

const accountTxns = computed(() =>
  selectedAccountId.value
    ? transactions.value.filter(
        (t) => t.account_id === selectedAccountId.value || t.to_account_id === selectedAccountId.value
      )
    : []
)

function categoryName(id?: number | null): string {
  return categories.value.find((c) => c.id === id)?.name || ''
}
const tagName = (id: number) => tags.value.find((t) => t.id === id)?.name || ''
const txnTags = (t: Transaction) => (t.tag_ids || []).map(tagName).filter(Boolean).join('、')

function tradeMeta(t: Transaction) {
  return {
    price: t.trade_price != null ? fmt(t.trade_price) : '-',
    qty: t.trade_qty != null ? String(Number(t.trade_qty)) : '-',
    commission: t.trade_commission != null ? fmt(t.trade_commission) : '-',
    fee: t.trade_fee != null ? fmt(t.trade_fee) : '-',
  }
}

function txnActivity(t: Transaction): string {
  if (t.type === 'transfer') return t.to_account_id === selectedAccountId.value ? '资金转入' : '资金转出'
  if (t.trade_symbol) return t.type === 'income' ? '基金赎回' : '基金申购'
  const cat = categoryName(t.category_id)
  if (cat) return `【${cat}】`
  return t.type === 'income' ? '收入' : '支出'
}

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  const exp = await api.listCategories(lid, 'expense')
  const inc = await api.listCategories(lid, 'income')
  categories.value = [...exp, ...inc]
  tags.value = await api.listTags(lid)
  holdings.value = await api.listHoldings(lid)
  const qid = route.query.account_id ? Number(route.query.account_id) : null
  if (qid && fundAccounts.value.some((a) => a.id === qid)) {
    selectedAccountId.value = qid
  } else if (!selectedAccountId.value && fundAccounts.value.length) {
    selectedAccountId.value = fundAccounts.value[0].id
  }
  await loadTxns()
}

async function loadTxns() {
  const lid = ledgerStore.currentId
  if (!lid || !selectedAccountId.value) {
    transactions.value = []
    return
  }
  const res = await api.listTransactions(lid, { account_id: selectedAccountId.value, page_size: 500 })
  transactions.value = res.items
}

function onRecord(mode: 'buy' | 'sell') {
  tradeStore.open(mode, selectedAccountId.value ?? undefined)
}

const syncingQuote = ref(false)
async function syncQuote() {
  const lid = ledgerStore.currentId
  if (!lid) return
  syncingQuote.value = true
  try {
    const r = await api.syncMarketPrices(lid)
    if (r.updated) ElMessage.success(`已同步 ${r.updated} 只基金的最新净值`)
    else ElMessage.info('暂无可同步的持仓基金')
    if (r.failed?.length) ElMessage.warning(`未成功：${r.failed.join('、')}`)
    await load()
  } catch (e) {
    ElMessage.error('同步净值失败，请稍后重试')
  } finally {
    syncingQuote.value = false
  }
}

// ---- 转账 ----
const FUNDING_TYPES = ['cash', 'bank', 'wallet', 'prepaid']
const fundingAccounts = computed(() =>
  accounts.value.filter((a) => FUNDING_TYPES.includes(a.type) && a.id !== selectedAccountId.value)
)
const transferDialog = ref(false)
const savingTransfer = ref(false)
const transferForm = reactive<{
  direction: 'in' | 'out'
  occurred_at: string
  amount: number | null
  counter_account_id: number | null
  remark: string
}>({ direction: 'in', occurred_at: '', amount: null, counter_account_id: null, remark: '' })
const transferIsIn = computed(() => transferForm.direction === 'in')
const transferCounterLabel = computed(() => (transferIsIn.value ? '转出账户' : '转入账户'))

function openTransfer() {
  if (!selectedAccount.value) {
    ElMessage.warning('请先选择基金账户')
    return
  }
  transferForm.direction = 'in'
  transferForm.occurred_at = new Date().toISOString().slice(0, 10)
  transferForm.amount = null
  transferForm.counter_account_id = null
  transferForm.remark = ''
  transferDialog.value = true
}

async function submitTransfer() {
  const lid = ledgerStore.currentId
  if (!lid || !selectedAccount.value) return
  const amt = Number(transferForm.amount)
  if (!amt || amt <= 0) {
    ElMessage.warning('请输入金额')
    return
  }
  if (!transferForm.counter_account_id) {
    ElMessage.warning(`请选择${transferCounterLabel.value}`)
    return
  }
  savingTransfer.value = true
  try {
    const investId = selectedAccount.value.id
    const counter = transferForm.counter_account_id
    await api.createTransaction(lid, {
      type: 'transfer',
      amount: amt.toFixed(2),
      account_id: transferIsIn.value ? counter : investId,
      to_account_id: transferIsIn.value ? investId : counter,
      occurred_at: transferForm.occurred_at,
      remark: transferForm.remark || (transferIsIn.value ? '资金转入' : '资金转出'),
    })
    ElMessage.success('已记账')
    transferDialog.value = false
    await load()
  } finally {
    savingTransfer.value = false
  }
}

function canEditTxn(t: Transaction): boolean {
  return t.trade_qty != null && !!t.trade_symbol
}
function onEditTxn(row: Transaction) {
  if (!canEditTxn(row)) {
    ElMessage.info('该记录请在「财务记录」中编辑')
    return
  }
  const mode = row.type === 'income' ? 'sell' : 'buy'
  const secAcctId = row.to_account_id ?? selectedAccountId.value ?? row.account_id
  const h = holdings.value.find((x) => x.symbol === row.trade_symbol && x.account_id === secAcctId)
  const nameFromRemark = (row.remark || '').replace(/^(申购|赎回|买入|卖出)[：:]/, '').replace(/\s*\d.*$/, '')
  tradeStore.openEdit(mode, {
    id: row.id,
    symbol: row.trade_symbol ?? null,
    name: h?.name || nameFromRemark || row.trade_symbol || '',
    account_id: row.account_id,
    security_account_id: secAcctId,
    price: row.trade_price != null ? Number(row.trade_price) : null,
    quantity: row.trade_qty != null ? Number(row.trade_qty) : null,
    fee_total: row.trade_fee != null ? Number(row.trade_fee) : null,
    commission: row.trade_commission != null ? Number(row.trade_commission) : null,
    occurred_at: row.occurred_at,
    remark: row.remark ?? null,
    tag_ids: row.tag_ids ? [...row.tag_ids] : [],
  })
}
async function onDeleteTxn(row: Transaction) {
  await ElMessageBox.confirm('确定删除这笔交易记录？', '提示', { type: 'warning' })
  await api.deleteTransaction(row.id)
  ElMessage.success('已删除')
  await load()
}

watch(
  () => route.query.account_id,
  (v) => {
    if (v) selectedAccountId.value = Number(v)
  },
  { immediate: true }
)

onMounted(load)
watch(() => ledgerStore.currentId, load)
watch(() => tradeStore.savedAt, load)
watch(selectedAccountId, () => { loadTxns() })
</script>

<template>
  <div class="fund-page">
    <!-- 基金持仓与汇总 -->
    <div class="panel">
      <div class="panel-head">
        <span class="panel-title">{{ selectedAccount?.name || '基金账户' }}</span>
        <span class="panel-balance" :class="{ neg: summary.total < 0 }">{{ fmt(summary.total) }}</span>
        <div class="head-spacer" />
        <el-select v-if="fundAccounts.length > 1" v-model="selectedAccountId" size="small" style="width:160px">
          <el-option v-for="a in fundAccounts" :key="a.id" :label="a.name" :value="a.id" />
        </el-select>
        <el-button size="small" :loading="syncingQuote" @click="syncQuote">同步净值</el-button>
        <el-select v-model="holdingScope" size="small" style="width:170px">
          <el-option label="当前持仓基金" value="current" />
          <el-option label="所有交易过的基金" value="all" />
        </el-select>
      </div>

      <el-table :data="displayHoldings" size="small" border>
        <!-- 货币基金：净值恒为 1，按累计金额展示 -->
        <template v-if="isAmountStyle">
          <el-table-column label="基金名称" min-width="240" fixed="left">
            <template #default="{ row }">{{ row.symbol ? row.symbol + ' ' : '' }}{{ row.name }}</template>
          </el-table-column>
          <el-table-column label="累计金额" align="right" min-width="140">
            <template #default="{ row }">{{ fmt(row.market_value) }}</template>
          </el-table-column>
          <el-table-column label="占比%" align="right" min-width="100">
            <template #default="{ row }">{{ sharePct(row).toFixed(2) }}</template>
          </el-table-column>
        </template>
        <!-- 开放式基金：净值式，含数量/成本/市值/均价/净值/收益率 -->
        <template v-else>
          <el-table-column label="基金名称" min-width="200" fixed="left">
            <template #default="{ row }">{{ row.symbol ? row.symbol + ' ' : '' }}{{ row.name }}</template>
          </el-table-column>
          <el-table-column label="持仓份额" align="right" min-width="110">
            <template #default="{ row }">{{ row.quantity }}</template>
          </el-table-column>
          <el-table-column label="持仓成本" align="right" min-width="120">
            <template #default="{ row }">{{ fmt(row.cost) }}</template>
          </el-table-column>
          <el-table-column label="市值" align="right" min-width="120">
            <template #default="{ row }">{{ fmt(row.market_value) }}</template>
          </el-table-column>
          <el-table-column label="占比%" align="right" min-width="90">
            <template #default="{ row }">{{ sharePct(row).toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="浮动盈亏" align="right" min-width="120">
            <template #default="{ row }">
              <span :class="toNum(row.profit) >= 0 ? 'pos' : 'neg'">{{ fmt(row.profit) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="成本净值" align="right" min-width="100">
            <template #default="{ row }">{{ fmt4(toNum(row.quantity) ? toNum(row.cost) / toNum(row.quantity) : 0) }}</template>
          </el-table-column>
          <el-table-column label="基金净值" align="right" min-width="100">
            <template #default="{ row }">{{ fmt4(row.price) }}</template>
          </el-table-column>
          <el-table-column label="浮动收益率%" align="right" min-width="120">
            <template #default="{ row }">
              <span :class="toNum(row.profit) >= 0 ? 'pos' : 'neg'">{{ floatRate(row).toFixed(2) }}</span>
            </template>
          </el-table-column>
        </template>
        <template #empty>当前账户暂无持仓</template>
      </el-table>

      <div class="fund-summary">
        <div class="sum-item"><span class="lbl">资金转入</span><span class="val pos">{{ fmt(summary.inflow) }}</span></div>
        <div class="sum-item"><span class="lbl">资金转出</span><span class="val neg">{{ fmt(summary.outflow) }}</span></div>
        <div class="sum-item"><span class="lbl">总买卖盈亏</span><span class="val" :class="summary.realized >= 0 ? 'pos' : 'neg'">{{ fmt(summary.realized) }}</span></div>
        <template v-if="!isAmountStyle">
          <div class="sum-item"><span class="lbl">总浮动盈亏</span><span class="val" :class="summary.floatProfit >= 0 ? 'pos' : 'neg'">{{ fmt(summary.floatProfit) }}</span></div>
          <div class="sum-item"><span class="lbl">总成本</span><span class="val">{{ fmt(summary.cost) }}</span></div>
        </template>
        <div class="sum-item"><span class="lbl">总市值</span><span class="val">{{ fmt(summary.market) }}</span></div>
        <div class="sum-item"><span class="lbl">可用资金</span><span class="val">{{ fmt(summary.avail) }}</span></div>
        <div class="sum-item"><span class="lbl">总计</span><span class="val" :class="{ neg: summary.total < 0 }">{{ fmt(summary.total) }}</span></div>
      </div>
    </div>

    <!-- 交易记录 / 历史盈亏 -->
    <div class="panel">
      <div class="panel-head">
        <div class="head-spacer" />
        <el-button size="small" type="primary" @click="onRecord('buy')">基金申购</el-button>
        <el-button size="small" @click="onRecord('sell')">基金赎回</el-button>
        <el-button size="small" @click="openTransfer">转账</el-button>
      </div>
      <el-tabs v-model="bottomTab">
        <el-tab-pane label="交易明细" name="txns">
          <el-table :data="accountTxns" size="small" border>
            <el-table-column label="日期" min-width="110" fixed="left">
              <template #default="{ row }">{{ fmtDate(row.occurred_at) }}</template>
            </el-table-column>
            <template v-if="!isAmountStyle">
              <el-table-column label="净值" align="right" min-width="100">
                <template #default="{ row }">{{ tradeMeta(row).price }}</template>
              </el-table-column>
              <el-table-column label="份额" align="right" min-width="100">
                <template #default="{ row }">{{ tradeMeta(row).qty }}</template>
              </el-table-column>
              <el-table-column label="手续费" align="right" min-width="90">
                <template #default="{ row }">{{ tradeMeta(row).fee }}</template>
              </el-table-column>
            </template>
            <el-table-column label="交易金额" align="right" min-width="120">
              <template #default="{ row }">{{ fmt(row.amount) }}</template>
            </el-table-column>
            <el-table-column label="活动类型" min-width="140">
              <template #default="{ row }">{{ txnActivity(row) }}</template>
            </el-table-column>
            <el-table-column label="标签" min-width="120">
              <template #default="{ row }">{{ txnTags(row) }}</template>
            </el-table-column>
            <el-table-column label="备注" min-width="160">
              <template #default="{ row }">{{ row.remark }}</template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="onEditTxn(row)">修改</el-button>
                <el-button link type="danger" size="small" @click="onDeleteTxn(row)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty>当前账户暂无交易记录，点击上方按钮开始记账</template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="历史盈亏" name="pnl">
          <el-table :data="realizedPnl" size="small" border>
            <el-table-column label="交易日期" min-width="110" fixed="left">
              <template #default="{ row }">{{ fmtDate(row.occurred_at) }}</template>
            </el-table-column>
            <el-table-column label="名称" min-width="200">
              <template #default="{ row }">{{ row.name }}</template>
            </el-table-column>
            <el-table-column label="活动类型" min-width="160">
              <template #default="{ row }">{{ row.activity }}</template>
            </el-table-column>
            <el-table-column label="净值" align="right" min-width="100">
              <template #default="{ row }">{{ isAmountStyle ? '-' : fmt(row.price) }}</template>
            </el-table-column>
            <el-table-column label="份额" align="right" min-width="100">
              <template #default="{ row }">{{ isAmountStyle ? '-' : Number(row.quantity || 0) }}</template>
            </el-table-column>
            <el-table-column label="交易金额" align="right" min-width="120">
              <template #default="{ row }">{{ fmt(row.amount) }}</template>
            </el-table-column>
            <el-table-column label="实现盈亏" align="right" min-width="120">
              <template #default="{ row }">
                <span :class="row.profit >= 0 ? 'pos' : 'neg'">{{ fmt(row.profit) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="盈亏比例" align="right" min-width="110">
              <template #default="{ row }">
                <span :class="row.profit >= 0 ? 'pos' : 'neg'">{{ row.rate.toFixed(2) }}%</span>
              </template>
            </el-table-column>
            <template #empty>暂无已实现盈亏记录</template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 转账弹窗 -->
    <el-dialog v-model="transferDialog" title="基金账户转账" width="90%" style="max-width:460px" :close-on-click-modal="false">
      <el-form label-width="90px">
        <el-form-item label="基金账户">
          <span>{{ selectedAccount?.name }}</span>
        </el-form-item>
        <el-form-item label="转账方向">
          <el-radio-group v-model="transferForm.direction">
            <el-radio-button label="in">转入</el-radio-button>
            <el-radio-button label="out">转出</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="transferCounterLabel">
          <el-select v-model="transferForm.counter_account_id" placeholder="请选择账户" style="width: 100%">
            <el-option v-for="a in fundingAccounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额">
          <el-input-number v-model="transferForm.amount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="transferForm.occurred_at" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="transferForm.remark" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="transferDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingTransfer" @click="submitTransfer">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.fund-page { padding: 12px 16px; display: flex; flex-direction: column; gap: 14px; }
.panel { background: #fff; border: 1px solid #ebeef2; border-radius: 8px; padding: 12px 14px; }
.panel-head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.panel-title { font-size: 16px; font-weight: 600; color: #3c4b59; }
.panel-balance { font-size: 18px; font-weight: 700; color: #2e9c4f; }
.panel-balance.neg { color: #f56c6c; }
.head-spacer { flex: 1; }
.fund-summary { display: flex; flex-wrap: wrap; gap: 28px; margin-top: 12px; padding: 10px 16px; background: #f7f8fa; border-radius: 6px; }
.sum-item { display: flex; flex-direction: column; gap: 2px; }
.sum-item .lbl { font-size: 12px; color: #909399; }
.sum-item .val { font-size: 15px; font-weight: 600; color: #303133; }
:deep(.el-table__row) { cursor: default; }
.pos { color: #f56c6c; }
.neg { color: #67c23a; }
</style>
