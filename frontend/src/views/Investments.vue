<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useTradeStore } from '../stores/trade'
import { useP2pStore } from '../stores/p2p'
import type { Holding, Account, Loan } from '../types'
import { fmtMoney } from '../utils/format'

const route = useRoute()
const ledgerStore = useLedgerStore()
const tradeStore = useTradeStore()
const p2pStore = useP2pStore()
const holdings = ref<Holding[]>([])
const accounts = ref<Account[]>([])
const loans = ref<Loan[]>([])
const selectedAccountId = ref<number | null>(null)

const STOCK_TYPES = ['stock', 'open_fund', 'fund', 'money_fund', 'bond', 'reverse_repo', 'wealth', 'metal', 'metal_td', 'forex', 'futures', 'margin']
const stockAccounts = computed(() => accounts.value.filter((a) => STOCK_TYPES.includes(a.type)))

const fmt = (v: string | number) => fmtMoney(v)
const fmt4 = (v: string | number) => Number(v || 0).toFixed(4)

// 仅展示「投入成本」的账户类型（货币基金 / 网贷 等无浮动盈亏）
const COST_ONLY_TYPES = ['money_fund', 'p2p', 'reverse_repo', 'wealth', 'bond']
const isCostOnly = (type: string) => COST_ONLY_TYPES.includes(type)

interface GroupRow {
  id: number
  name: string
  symbol?: string | null
  type: string
  quantity: number
  avg_price: number
  cost: number
  market_value: number
  float_profit: number
  change_pct: number
  abs_ratio: number
}

interface InvGroup {
  account: Account
  costOnly: boolean
  rows: GroupRow[]
  cost: number
  market_value: number
  float_profit: number
  change_pct: number
}

// 按账户分组（财智8 投资一览样式）
const groups = computed<InvGroup[]>(() => {
  return stockAccounts.value
    .map((a): InvGroup => {
      const items = holdings.value.filter((h) => h.account_id === a.id)
      const cost = items.reduce((s, h) => s + Number(h.cost), 0)
      const mv = items.reduce((s, h) => s + Number(h.market_value), 0)
      const profit = items.reduce((s, h) => s + Number(h.profit), 0)
      const absTotal = items.reduce((s, h) => s + Math.abs(Number(h.profit)), 0)
      const rows: GroupRow[] = items.map((h) => {
        const qty = Number(h.quantity)
        const c = Number(h.cost)
        const p = Number(h.profit)
        return {
          id: h.id,
          name: h.name,
          symbol: h.symbol,
          type: h.type,
          quantity: qty,
          avg_price: qty ? c / qty : 0,
          cost: c,
          market_value: Number(h.market_value),
          float_profit: p,
          change_pct: c ? (p / c) * 100 : 0,
          abs_ratio: absTotal ? (Math.abs(p) / absTotal) * 100 : 0
        }
      })
      return {
        account: a,
        costOnly: isCostOnly(a.type),
        rows,
        cost,
        market_value: mv,
        float_profit: profit,
        change_pct: cost ? (profit / cost) * 100 : 0
      }
    })
    .filter((g) => g.rows.length)
})

interface P2pRow {
  id: number
  name: string
  item?: string | null
  cost: number
}
interface P2pGroup {
  account: Account
  rows: P2pRow[]
  cost: number
}

// 网贷（P2P）账户：以未结清本金作为投入成本
const p2pAccounts = computed(() => accounts.value.filter((a) => a.type === 'p2p'))
const p2pGroups = computed<P2pGroup[]>(() =>
  p2pAccounts.value
    .map((a): P2pGroup => {
      const projects = loans.value.filter((l) => l.loan_kind === 'p2p' && l.account_id === a.id && !l.is_closed)
      const rows: P2pRow[] = projects.map((l) => ({
        id: l.id,
        name: l.counterparty,
        item: l.item,
        cost: Number(l.remaining || 0)
      }))
      return { account: a, rows, cost: rows.reduce((s, r) => s + r.cost, 0) }
    })
    .filter((g) => g.rows.length)
)

// 底部汇总：总投入成本 / 总市值 / 总浮动盈亏
const grandTotal = computed(() => {
  let cost = 0
  let market = 0
  for (const g of groups.value) {
    cost += g.cost
    // 仅成本展示的账户（货币基金/理财/债券等）市值按成本计
    market += g.costOnly ? g.cost : g.market_value
  }
  for (const g of p2pGroups.value) {
    cost += g.cost
    market += g.cost
  }
  return { cost, market, profit: market - cost }
})

// 更新行情数据
const updateDialog = ref(false)
const updating = ref(false)
const updateTab = ref<'latest' | 'history'>('latest')
const UPDATE_ITEMS = [
  { key: 'stock', label: '股票收盘价' },
  { key: 'fund', label: '开放式基金净值' }
]
const updateChecked = ref<string[]>(['stock', 'fund'])

function openUpdate() {
  updateChecked.value = ['stock', 'fund']
  updateDialog.value = true
}

async function doUpdate() {
  const lid = ledgerStore.currentId
  if (!lid) return
  if (!updateChecked.value.length) {
    ElMessage.warning('请至少选择一项数据')
    return
  }
  updating.value = true
  try {
    const r = await api.syncMarketPrices(lid)
    if (r.updated) ElMessage.success(`已更新 ${r.updated} 只品种的最新行情`)
    else ElMessage.info('暂无可更新的持仓品种')
    if (r.failed?.length) ElMessage.warning(`未成功：${r.failed.join('、')}`)
    updateDialog.value = false
    await load()
  } catch (e) {
    ElMessage.error('更新行情失败，请稍后重试')
  } finally {
    updating.value = false
  }
}

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  try {
    accounts.value = await api.listAccounts(lid)
    holdings.value = await api.listHoldings(lid)
    loans.value = await api.listLoans(lid)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载投资数据失败')
    return
  }
  const qid = Number(route.query.account_id)
  if (qid && stockAccounts.value.some((a) => a.id === qid)) {
    selectedAccountId.value = qid
  } else if (!selectedAccountId.value && stockAccounts.value.length) {
    selectedAccountId.value = stockAccounts.value[0].id
  }
}

onMounted(load)
watch(() => ledgerStore.currentId, load)
watch(() => tradeStore.savedAt, load)
watch(() => p2pStore.savedAt, load)
watch(() => route.query.account_id, (id) => {
  const qid = Number(id)
  if (qid && stockAccounts.value.some((a) => a.id === qid)) selectedAccountId.value = qid
})
</script>

<template>
  <div class="inv-page">
    <!-- 顶部工具栏 -->
    <div class="inv-head">
      <span class="inv-title">投资一览</span>
      <div class="head-spacer" />
      <el-button @click="openUpdate">更新行情数据</el-button>
    </div>

    <el-empty v-if="!groups.length && !p2pGroups.length" description="暂无投资持仓" />

    <!-- 按账户分组 -->
    <el-card v-for="g in groups" :key="g.account.id" shadow="never" class="grp">
      <div class="grp-head">
        <span class="grp-name">{{ g.account.name }}</span>
        <div class="grp-stats">
          <template v-if="g.costOnly">
            <div class="gstat"><div class="lbl">投入成本</div><div class="num">{{ fmt(g.cost) }}</div></div>
          </template>
          <template v-else>
            <div class="gstat"><div class="lbl">投入成本</div><div class="num">{{ fmt(g.cost) }}</div></div>
            <div class="gstat"><div class="lbl">当前市值</div><div class="num">{{ fmt(g.market_value) }}</div></div>
            <div class="gstat"><div class="lbl">浮动盈亏</div><div class="num" :class="g.float_profit >= 0 ? 'income' : 'expense'">{{ fmt(g.float_profit) }}</div></div>
            <div class="gstat"><div class="lbl">涨幅</div><div class="num" :class="g.change_pct >= 0 ? 'income' : 'expense'">{{ g.change_pct.toFixed(2) }}%</div></div>
          </template>
        </div>
      </div>

      <!-- 货币基金 / 网贷等：仅显示投入成本 -->
      <el-table v-if="g.costOnly" :data="g.rows" size="small">
        <el-table-column label="名称" min-width="220">
          <template #default="{ row }">
            <span class="sec-name">{{ row.name }}</span>
            <span class="sec-code">{{ row.symbol }}</span>
          </template>
        </el-table-column>
        <el-table-column label="投入成本" align="right" min-width="140">
          <template #default="{ row }">{{ fmt(row.cost) }}</template>
        </el-table-column>
      </el-table>

      <!-- 上市证券 / 开放式基金等：完整列 -->
      <el-table v-else :data="g.rows" size="small">
        <el-table-column label="名称" min-width="180">
          <template #default="{ row }">
            <span class="sec-name">{{ row.name }}</span>
            <span class="sec-code">{{ row.symbol }}</span>
          </template>
        </el-table-column>
        <el-table-column label="持仓数量" align="right" min-width="100">
          <template #default="{ row }">{{ fmt(row.quantity) }}</template>
        </el-table-column>
        <el-table-column label="购买均价" align="right" min-width="100">
          <template #default="{ row }">{{ fmt4(row.avg_price) }}</template>
        </el-table-column>
        <el-table-column label="持仓成本" align="right" min-width="110">
          <template #default="{ row }">{{ fmt(row.cost) }}</template>
        </el-table-column>
        <el-table-column label="当前市值" align="right" min-width="110">
          <template #default="{ row }">{{ fmt(row.market_value) }}</template>
        </el-table-column>
        <el-table-column label="浮动盈亏" align="right" min-width="110">
          <template #default="{ row }">
            <span :class="row.float_profit >= 0 ? 'income' : 'expense'">{{ fmt(row.float_profit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="涨幅" align="right" min-width="100">
          <template #default="{ row }">
            <span :class="row.change_pct >= 0 ? 'income' : 'expense'">{{ row.change_pct.toFixed(2) }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="浮盈绝对值占比" align="right" min-width="130">
          <template #default="{ row }">{{ row.abs_ratio.toFixed(2) }}%</template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 网贷（P2P）分组：投入成本 -->
    <el-card v-for="g in p2pGroups" :key="'p2p-' + g.account.id" shadow="never" class="grp">
      <div class="grp-head">
        <span class="grp-name">{{ g.account.name }}</span>
        <div class="grp-stats">
          <div class="gstat"><div class="lbl">投入成本</div><div class="num">{{ fmt(g.cost) }}</div></div>
        </div>
      </div>
      <el-table :data="g.rows" size="small">
        <el-table-column label="名称" min-width="220">
          <template #default="{ row }">
            <span class="sec-name">{{ row.name }}</span>
            <span class="sec-code">{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="投入成本" align="right" min-width="140">
          <template #default="{ row }">{{ fmt(row.cost) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 底部汇总状态栏 -->
    <div v-if="groups.length || p2pGroups.length" class="inv-summary">
      <span class="sum-item">总投入成本：<b>{{ fmt(grandTotal.cost) }}</b></span>
      <span class="sum-sep">|</span>
      <span class="sum-item">总市值：<b>{{ fmt(grandTotal.market) }}</b></span>
      <span class="sum-sep">|</span>
      <span class="sum-item">总浮动盈亏：<b :class="grandTotal.profit >= 0 ? 'income' : 'expense'">{{ fmt(grandTotal.profit) }}</b></span>
    </div>

    <!-- 更新行情数据 -->
    <el-dialog v-model="updateDialog" title="更新行情数据" width="520px" append-to-body>
      <el-tabs v-model="updateTab">
        <el-tab-pane label="获取最新行情数据" name="latest">
          <el-table :data="UPDATE_ITEMS" size="small">
            <el-table-column width="56">
              <template #default="{ row }">
                <el-checkbox
                  :model-value="updateChecked.includes(row.key)"
                  @change="(v: boolean) => v ? updateChecked.push(row.key) : (updateChecked = updateChecked.filter((k) => k !== row.key))"
                />
              </template>
            </el-table-column>
            <el-table-column prop="label" label="数据项" />
          </el-table>
          <p class="upd-hint">将联网获取已持仓股票/基金的最新价格，并更新持仓盈亏。</p>
        </el-tab-pane>
        <el-tab-pane label="获取历史行情数据" name="history">
          <el-empty description="暂不支持历史行情批量获取" :image-size="80" />
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button @click="updateDialog = false">取消</el-button>
        <el-button type="primary" :loading="updating" :disabled="updateTab !== 'latest'" @click="doUpdate">更新</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.inv-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
}

.inv-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.inv-title {
  font-size: 18px;
  font-weight: 600;
}

.head-spacer {
  flex: 1;
}

.grp :deep(.el-card__body) {
  padding: 0;
}

.grp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  padding: 14px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}

.grp-name {
  font-size: 15px;
  font-weight: 600;
}

.grp-stats {
  display: flex;
  gap: 28px;
}

.gstat {
  text-align: right;
}

.gstat .lbl {
  color: #909399;
  font-size: 12px;
}

.gstat .num {
  font-weight: 600;
}

.sec-name {
  font-weight: 600;
}

.sec-code {
  color: #909399;
  margin-left: 6px;
  font-size: 12px;
}

.income {
  color: #f56c6c;
}

.expense {
  color: #67c23a;
}

.inv-summary {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  font-size: 14px;
  color: #606266;
}

.inv-summary b {
  color: #303133;
  font-weight: 600;
}

.inv-summary .sum-sep {
  color: #dcdfe6;
}

.upd-hint {
  margin: 12px 0 0;
  color: #909399;
  font-size: 12px;
}
</style>

