<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import dayjs from 'dayjs'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, BarChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useMediaQuery } from '../composables/useMediaQuery'
import type { Overview, NetWorth, TrendItem, CategoryStat, Account, Loan, InvestmentOverview, Budget } from '../types'

use([CanvasRenderer, PieChart, BarChart, TooltipComponent, LegendComponent, GridComponent])

const PIE_COLORS = ['#d9534f', '#e6a23c', '#2e9c4f', '#409eff', '#9b59b6', '#5fb878', '#e8746f', '#f0a59f', '#7ec1d6', '#c0a16b']

const ledgerStore = useLedgerStore()
const { isMobile } = useMediaQuery()

const month = ref<string>(dayjs().format('YYYY-MM'))
const overview = ref<Overview>({ income: '0', expense: '0', balance: '0' })
const net = ref<NetWorth>({ assets: '0', liabilities: '0', net_worth: '0', asset_groups: [], liability_groups: [] })
const trendRows = ref<TrendItem[]>([])
const expenseCat = ref<CategoryStat>({ total: '0', items: [] })
const accounts = ref<Account[]>([])
const loans = ref<Loan[]>([])
const inv = ref<InvestmentOverview>({ total_cost: '0', total_market_value: '0', total_float_profit: '0', total_change_pct: 0, rows: [] })
const budgets = ref<Budget[]>([])

const activeTab = ref('trend')

function n(v: string | number) { return Number(v || 0) }
function money(v: string | number) {
  return n(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/* ---- 信用卡一览 ---- */
const creditCards = computed(() => accounts.value.filter((a) => a.type === 'credit'))
const creditUnpaidTotal = computed(() =>
  creditCards.value.reduce((s, a) => s + Math.max(0, -n(a.current_balance)), 0)
)

/* ---- 可用资金 ---- */
const fundAccounts = computed(() =>
  accounts.value.filter((a) => ['cash', 'wallet', 'bank'].includes(String(a.type)) && n(a.current_balance) > 0)
)

/* ---- 债权 / 债务 ---- */
const receivables = computed(() => loans.value.filter((l) => !l.is_closed && l.direction === 'receivable' && n(l.remaining) > 0))
const payables = computed(() => loans.value.filter((l) => !l.is_closed && l.direction === 'payable' && n(l.remaining) > 0))

/* ---- 图表配置 ---- */
function pie(title: string, data: { name: string; value: number }[]) {
  const mobile = isMobile.value
  return {
    color: PIE_COLORS,
    title: {
      text: title,
      left: mobile ? 'center' : '37%',
      top: mobile ? '38%' : '46%',
      textAlign: 'center',
      textStyle: { fontSize: mobile ? 13 : 14, color: '#606266' }
    },
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: mobile
      ? { type: 'scroll', orient: 'horizontal', bottom: 0, left: 'center', textStyle: { fontSize: 11 } }
      : { type: 'scroll', orient: 'vertical', right: 8, top: 'middle', textStyle: { fontSize: 11 } },
    series: [{
      type: 'pie',
      radius: mobile ? ['40%', '60%'] : ['46%', '68%'],
      center: mobile ? ['50%', '42%'] : ['38%', '50%'],
      avoidLabelOverlap: true, label: { show: false },
      data
    }]
  }
}

const trendOption = computed(() => {
  const rows = trendRows.value
  return {
    color: ['#2e9c4f', '#d9534f'],
    tooltip: { trigger: 'axis' },
    legend: { data: ['收入', '支出'], top: 4 },
    grid: { left: isMobile.value ? 44 : 60, right: isMobile.value ? 12 : 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: rows.map((r) => r.period) },
    yAxis: { type: 'value' },
    series: [
      { name: '收入', type: 'bar', data: rows.map((r) => n(r.income)) },
      { name: '支出', type: 'bar', data: rows.map((r) => n(r.expense)) }
    ]
  }
})

const catOption = computed(() =>
  pie('收支构成', expenseCat.value.items.map((i) => ({ name: i.name, value: n(i.amount) })))
)
const fundOption = computed(() =>
  pie('可用资金', fundAccounts.value.map((a) => ({ name: a.name, value: n(a.current_balance) })))
)
const investOption = computed(() =>
  pie('投资构成', inv.value.rows.map((r) => ({ name: r.name, value: n(r.market_value) })))
)
const assetOption = computed(() =>
  pie('资产构成', net.value.asset_groups.map((g) => ({ name: g.name, value: n(g.amount) })))
)
const receivableOption = computed(() =>
  pie('债权', receivables.value.map((l) => ({ name: l.counterparty, value: n(l.remaining) })))
)
const payableOption = computed(() =>
  pie('债务', payables.value.map((l) => ({ name: l.counterparty, value: n(l.remaining) })))
)

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  const start = dayjs(month.value).startOf('month').toISOString()
  const end = dayjs(month.value).endOf('month').toISOString()
  const trendStart = dayjs(month.value).subtract(11, 'month').startOf('month').toISOString()
  try {
    const [ov, nw, tr, cat, accs, lns, ivo, bgs] = await Promise.all([
      api.overview(lid, { start, end }),
      api.netWorth(lid),
      api.trend(lid, { start: trendStart, end }),
      api.byCategory(lid, { kind: 'expense', start, end }),
      api.listAccounts(lid),
      api.listLoans(lid),
      api.investmentOverview(lid),
      api.listBudgets(lid)
    ])
    overview.value = ov
    net.value = nw
    trendRows.value = tr
    expenseCat.value = cat
    accounts.value = accs
    loans.value = lns
    inv.value = ivo
    budgets.value = bgs
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载首页数据失败')
  }
}

onMounted(load)
watch(() => ledgerStore.currentId, load)
watch(month, load)
</script>

<template>
  <div class="page dashboard">
    <!-- 顶部汇总条 -->
    <el-card shadow="never" class="summary-bar">
      <div class="summary-flex">
        <el-date-picker
          v-model="month" type="month" :clearable="false" size="large"
          format="M月" value-format="YYYY-MM" style="width:96px"
        />
        <div class="stat"><div class="lbl">收入</div><div class="val income">{{ money(overview.income) }}</div></div>
        <div class="stat"><div class="lbl">支出</div><div class="val expense">{{ money(overview.expense) }}</div></div>
        <div class="stat"><div class="lbl">结余</div><div class="val">{{ money(overview.balance) }}</div></div>
        <div class="spacer" />
        <div class="stat right"><div class="lbl">总资产</div><div class="val income">{{ money(net.assets) }}</div></div>
        <div class="stat right"><div class="lbl">总负债</div><div class="val expense">{{ money(net.liabilities) }}</div></div>
        <div class="stat right"><div class="lbl">净资产</div><div class="val net">{{ money(net.net_worth) }}</div></div>
      </div>
    </el-card>

    <!-- 图表区（左侧分类标签） -->
    <el-card shadow="never" class="chart-card">
      <el-tabs v-model="activeTab" :tab-position="isMobile ? 'top' : 'left'" class="chart-tabs">
        <el-tab-pane label="收支对比" name="trend">
          <v-chart v-if="trendRows.length" :option="trendOption" autoresize class="chart" />
          <el-empty v-else description="暂无收支数据" :image-size="60" />
        </el-tab-pane>
        <el-tab-pane label="收支构成" name="cat">
          <v-chart v-if="expenseCat.items.length" :option="catOption" autoresize class="chart" />
          <el-empty v-else description="暂无支出数据" :image-size="60" />
        </el-tab-pane>
        <el-tab-pane label="可用资金构成" name="fund">
          <v-chart v-if="fundAccounts.length" :option="fundOption" autoresize class="chart" />
          <el-empty v-else description="暂无资金数据" :image-size="60" />
        </el-tab-pane>
        <el-tab-pane label="债权/债务构成" name="debt">
          <div class="debt-pair" v-if="receivables.length || payables.length">
            <v-chart v-if="receivables.length" :option="receivableOption" autoresize class="chart half" />
            <el-empty v-else description="暂无债权" :image-size="50" class="half" />
            <v-chart v-if="payables.length" :option="payableOption" autoresize class="chart half" />
            <el-empty v-else description="暂无债务" :image-size="50" class="half" />
          </div>
          <el-empty v-else description="暂无债权/债务数据" :image-size="60" />
        </el-tab-pane>
        <el-tab-pane label="投资构成" name="invest">
          <v-chart v-if="inv.rows.length" :option="investOption" autoresize class="chart" />
          <el-empty v-else description="暂无投资数据" :image-size="60" />
        </el-tab-pane>
        <el-tab-pane label="资产构成" name="asset">
          <v-chart v-if="net.asset_groups.length" :option="assetOption" autoresize class="chart" />
          <el-empty v-else description="暂无资产数据" :image-size="60" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 信用卡一览 -->
    <el-card v-if="creditCards.length" shadow="never" class="block">
      <template #header>
        <div class="block-header">
          <span>信用卡一览</span>
          <span class="muted">未还总额：<span class="expense">{{ money(creditUnpaidTotal) }}</span></span>
        </div>
      </template>
      <el-table :data="creditCards" size="small">
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="账单日" width="120">
          <template #default="{ row }">{{ row.bill_day ? '每月' + row.bill_day + '日' : '—' }}</template>
        </el-table-column>
        <el-table-column label="还款日" width="120">
          <template #default="{ row }">{{ row.repay_day ? '每月' + row.repay_day + '日' : '—' }}</template>
        </el-table-column>
        <el-table-column label="信用额度" width="140" align="right">
          <template #default="{ row }">{{ row.credit_limit ? money(row.credit_limit) : '—' }}</template>
        </el-table-column>
        <el-table-column label="未还金额" width="140" align="right">
          <template #default="{ row }">
            <span class="expense">{{ money(Math.max(0, -n(row.current_balance))) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 投资一览 -->
    <el-card v-if="inv.rows.length" shadow="never" class="block">
      <template #header>
        <div class="block-header">
          <span>投资一览</span>
          <RouterLink to="/investments" class="muted link">投资详情</RouterLink>
        </div>
      </template>
      <el-table :data="inv.rows" size="small">
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="数量" align="right" width="120">
          <template #default="{ row }">{{ money(row.quantity) }}</template>
        </el-table-column>
        <el-table-column label="成本" align="right" width="130">
          <template #default="{ row }">{{ money(row.position_cost) }}</template>
        </el-table-column>
        <el-table-column label="市值" align="right" width="130">
          <template #default="{ row }">{{ money(row.market_value) }}</template>
        </el-table-column>
        <el-table-column label="浮动盈亏" align="right" width="130">
          <template #default="{ row }">
            <span :class="n(row.float_profit) >= 0 ? 'income' : 'expense'">{{ money(row.float_profit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="盈亏比例" align="right" width="120">
          <template #default="{ row }">
            <span :class="row.change_pct >= 0 ? 'income' : 'expense'">{{ row.change_pct }}%</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 财务预算 -->
    <el-card v-if="budgets.length" shadow="never" class="block">
      <template #header>
        <div class="block-header">
          <span>财务预算</span>
          <RouterLink to="/budgets" class="muted link">预算详情</RouterLink>
        </div>
      </template>
      <el-table :data="budgets" size="small">
        <el-table-column label="名称" min-width="200">
          <template #default="{ row }">{{ row.category_name || '总预算' }}</template>
        </el-table-column>
        <el-table-column label="可用预算额" align="right" width="160">
          <template #default="{ row }">
            <span :class="n(row.amount) - n(row.spent) >= 0 ? 'income' : 'expense'">
              {{ money(n(row.amount) - n(row.spent)) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="实际发生额" align="right" width="160">
          <template #default="{ row }">{{ money(row.spent) }}</template>
        </el-table-column>
        <el-table-column label="预算额" align="right" width="160">
          <template #default="{ row }">{{ money(row.amount) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 12px; }

.summary-bar :deep(.el-card__body) { padding: 14px 18px; }
.summary-flex { display: flex; align-items: center; gap: 28px; flex-wrap: wrap; }
.summary-flex .spacer { flex: 1; }
.stat .lbl { color: #909399; font-size: 12px; }
.stat .val { font-size: 22px; font-weight: 600; line-height: 1.3; }
.stat.right { text-align: right; }
.val.net { color: #d9534f; }

.chart-tabs :deep(.el-tabs__content) { height: 320px; }
.chart { height: 320px; width: 100%; }
.debt-pair { display: flex; height: 320px; }
.debt-pair .half { flex: 1; height: 320px; }

.block-header { display: flex; justify-content: space-between; align-items: center; font-weight: 600; }
.block-header .muted { color: #909399; font-weight: 400; font-size: 13px; }
.block-header .link { text-decoration: none; }
.muted .expense { font-weight: 600; }

/* ---------- 响应式：iPad ---------- */
@media (max-width: 1024px) and (min-width: 769px) {
  .chart-tabs :deep(.el-tabs__content) { height: 300px; }
  .chart { height: 300px; }
  .debt-pair, .debt-pair .half { height: 300px; }
}

/* ---------- 响应式：手机 ---------- */
@media (max-width: 768px) {
  .summary-flex { gap: 14px 18px; }
  .stat .val { font-size: 18px; }
  .stat.right { text-align: left; }
  .summary-flex .spacer { flex-basis: 100%; height: 0; }

  /* 顶部 Tab 横向滚动，图表高度收紧 */
  .chart-tabs :deep(.el-tabs__content) { height: auto; min-height: 300px; }
  .chart { height: 300px; }

  /* 债权/债务双图改为上下堆叠 */
  .debt-pair { flex-direction: column; height: auto; }
  .debt-pair .half { height: 220px; }
}

.income { color: #2e9c4f; }
.expense { color: #d9534f; }
</style>

