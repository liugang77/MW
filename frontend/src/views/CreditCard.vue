<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useRecordStore } from '../stores/record'
import AccountOperations from '../components/AccountOperations.vue'
import type { Account, Category, Transaction, Tag } from '../types'
import { fmtMoney } from '../utils/format'

const route = useRoute()
const ledgerStore = useLedgerStore()
const recordStore = useRecordStore()

const accounts = ref<Account[]>([])
const categories = ref<Category[]>([])
const tags = ref<Tag[]>([])
const billItems = ref<Transaction[]>([])
const selectedAccountId = ref<number | null>(null)
const selectedCycleKey = ref<string>('')
// 账单筛选：recent3=显示最近3期已出账单；all=显示所有已出账单
const billFilter = ref<'recent3' | 'all'>('all')

const selectedAccount = computed(() => accounts.value.find((a) => a.id === selectedAccountId.value) || null)

const fmtDate = (v: string) => (v || '').slice(0, 10)
const toNum = (v: string | number | null | undefined) => Number(v || 0)

function accountName(id?: number | null): string {
  return accounts.value.find((a) => a.id === id)?.name || '-'
}
function categoryName(id?: number | null): string {
  return categories.value.find((c) => c.id === id)?.name || ''
}

// 单账户视角的流入/流出
function inAmount(t: Transaction): string {
  const sel = selectedAccountId.value
  if (t.type === 'adjust') return toNum(t.amount) > 0 ? fmtMoney(t.amount) : ''
  if (t.type === 'income' && t.account_id === sel) return fmtMoney(t.amount)
  if (t.type === 'transfer' && t.to_account_id === sel) return fmtMoney(t.amount)
  return ''
}
function outAmount(t: Transaction): string {
  const sel = selectedAccountId.value
  if (t.type === 'adjust') return toNum(t.amount) < 0 ? fmtMoney(-toNum(t.amount)) : ''
  if (t.type === 'expense' && t.account_id === sel) return fmtMoney(t.amount)
  if (t.type === 'transfer' && t.account_id === sel) return fmtMoney(t.amount)
  return ''
}
function activityLabel(t: Transaction): string {
  if (t.type === 'transfer') return `转账 | ${accountName(t.account_id)} → ${accountName(t.to_account_id)}`
  if (t.type === 'adjust') return '余额调整'
  if (t.remark === '分拆收支') return '分拆收支'
  const cat = categoryName(t.category_id)
  if (cat) return `【${cat}】`
  return t.type === 'income' ? '收入' : '支出'
}
function assetAccount(t: Transaction): string {
  return accountName(t.account_id)
}

// ---------- 账单周期 ----------
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

const pad = (n: number) => String(n).padStart(2, '0')
const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

// 账单周期截止日（账单日）：根据交易日期与账单日推算其所属账单周期
function billCycleEnd(dateStr: string, billDay: number, billDayTxn: string): Date {
  const s = (dateStr || '').slice(0, 10)
  const d = new Date(s + 'T00:00:00')
  const day = d.getDate()
  let y = d.getFullYear()
  let m = d.getMonth()
  if (day > billDay || (day === billDay && billDayTxn === 'next')) {
    m += 1
    if (m > 11) { m = 0; y += 1 }
  }
  return new Date(y, m, billDay)
}

const allBillRows = computed<BillRow[]>(() => {
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
    const start = new Date(end.getFullYear(), end.getMonth() - 1, billDay + 1)
    const key = ymd(end)
    if (!byCycle.has(key)) {
      const pending = end.getTime() > today.getTime()
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
})

// 按筛选限制展示的账单（未出账单始终保留，已出账单按近 3 期 / 全部）
const billRows = computed<BillRow[]>(() => {
  const rows = allBillRows.value
  if (billFilter.value === 'all') return rows.slice(0, 36)
  const pending = rows.filter((r) => r.pending)
  const issued = rows.filter((r) => !r.pending).slice(0, 3)
  return [...pending, ...issued]
})

const billFilterText = computed(() => (billFilter.value === 'recent3' ? '显示最近3期已出账单' : '显示所有已出账单'))

// 选中某账单周期后的明细
const cycleDetail = computed<Transaction[]>(() => {
  const acc = selectedAccount.value
  if (!acc || !selectedCycleKey.value) return []
  const billDay = acc.bill_day || 1
  const billDayTxn = acc.bill_day_txn || 'next'
  return collapseSplits(billItems.value.filter(
    (t) => t.occurred_at && ymd(billCycleEnd(t.occurred_at, billDay, billDayTxn)) === selectedCycleKey.value
  ))
})

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
      out[idx].amount = String(toNum(out[idx].amount) + toNum(t.amount))
    }
  }
  return out
}

// 汇总（按当前展示的账单合计）
const summary = computed(() => {
  let inflow = 0
  let outflow = 0
  for (const r of billRows.value) {
    inflow += r.inAmount
    outflow += r.outAmount
  }
  return { inflow, outflow, diff: inflow - outflow, balance: toNum(selectedAccount.value?.current_balance) }
})

function selectCycle(row: BillRow) {
  selectedCycleKey.value = row.key
}
const cycleRowClass = ({ row }: { row: BillRow }) =>
  row.key === selectedCycleKey.value ? 'cycle-selected' : ''

watch(billRows, (rows) => {
  if (!rows.length) { selectedCycleKey.value = ''; return }
  if (!rows.some((r) => r.key === selectedCycleKey.value)) {
    const pending = rows.find((r) => r.pending)
    selectedCycleKey.value = pending ? pending.key : rows[0].key
  }
})

// ---------- 数据加载 ----------
async function loadMeta() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  const exp = await api.listCategories(lid, 'expense')
  const inc = await api.listCategories(lid, 'income')
  categories.value = [...exp, ...inc]
  tags.value = await api.listTags(lid)
  syncSelection()
}

function syncSelection() {
  const qid = Number(route.query.account_id || 0)
  const creditCards = accounts.value.filter((a) => a.type === 'credit')
  if (qid && creditCards.some((a) => a.id === qid)) {
    selectedAccountId.value = qid
  } else if (!creditCards.some((a) => a.id === selectedAccountId.value)) {
    selectedAccountId.value = creditCards.length ? creditCards[0].id : null
  }
}

async function loadBillData() {
  const lid = ledgerStore.currentId
  if (!lid || !selectedAccountId.value) {
    billItems.value = []
    return
  }
  const res = await api.listTransactions(lid, { page: 1, page_size: 500, account_id: selectedAccountId.value })
  billItems.value = res.items
}

async function reloadAll() {
  await loadMeta()
  await loadBillData()
}

const opsRef = ref<InstanceType<typeof AccountOperations> | null>(null)
async function onOpSaved() {
  await reloadAll()
}

function onEditRow(row: Transaction) {
  if (row.split_group) {
    opsRef.value?.openSplitEdit(row.split_group)
    return
  }
  recordStore.edit(row)
}
async function onDeleteRow(row: Transaction) {
  if (row.split_group) {
    await ElMessageBox.confirm('确定删除这组分拆收支？', '提示', { type: 'warning' })
    await api.deleteSplitGroup(ledgerStore.currentId as number, row.split_group)
  } else {
    await ElMessageBox.confirm('确定删除这笔流水？', '提示', { type: 'warning' })
    await api.deleteTransaction(row.id)
  }
  ElMessage.success('已删除')
  await reloadAll()
}

onMounted(reloadAll)
watch(() => ledgerStore.currentId, reloadAll)
watch(() => recordStore.savedAt, reloadAll)
watch(selectedAccountId, () => { selectedCycleKey.value = ''; loadBillData() })
watch(() => route.query.account_id, syncSelection)
</script>

<template>
  <div class="cc-page">
    <section class="cc-main">
      <!-- 标题栏：账户名 + 余额；右侧仅账单筛选 + 操作 -->
      <div class="cc-header-row">
        <div class="account-title">
          <span class="t-name">{{ selectedAccount?.name || '信用卡' }}</span>
          <span class="t-amount" :class="{ expense: toNum(selectedAccount?.current_balance) < 0 }">
            {{ selectedAccount ? fmtMoney(selectedAccount.current_balance) : '' }}
          </span>
        </div>
        <div class="toolbar-right">
          <el-dropdown trigger="click" @command="(c: 'recent3' | 'all') => billFilter = c">
            <el-button>
              {{ billFilterText }}<el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="recent3" :class="{ on: billFilter === 'recent3' }">显示最近3期已出账单</el-dropdown-item>
                <el-dropdown-item command="all" :class="{ on: billFilter === 'all' }">显示所有已出账单</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <AccountOperations
            ref="opsRef"
            :account="selectedAccount"
            :accounts="accounts"
            :tags="tags"
            @saved="onOpSaved"
          />
        </div>
      </div>

      <!-- 账单周期表 -->
      <div class="cc-bill-panel">
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
          <el-table-column prop="period" label="账单记录时段" min-width="200" />
          <el-table-column label="账单日" width="140">
            <template #default="scope">
              <span :class="{ 'bill-pending': scope.row.pending }">{{ scope.row.billDay }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="repayDay" label="还款日" width="140" />
          <el-table-column label="流入金额" width="140" align="right">
            <template #default="scope">{{ fmtMoney(scope.row.inAmount) }}</template>
          </el-table-column>
          <el-table-column label="流出金额" width="140" align="right">
            <template #default="scope">{{ fmtMoney(scope.row.outAmount) }}</template>
          </el-table-column>
          <el-table-column label="账单金额" width="140" align="right">
            <template #default="scope">
              <span :class="{ expense: scope.row.billAmount > 0, income: scope.row.billAmount <= 0 }">{{ fmtMoney(scope.row.billAmount) }}</span>
            </template>
          </el-table-column>
          <template #empty>暂无账单记录</template>
        </el-table>
      </div>

      <!-- 选中账单周期的明细 -->
      <div class="detail-wrap">
        <div class="detail-title" v-if="selectedCycleKey">账单明细</div>
        <el-table :data="cycleDetail" stripe style="width: 100%" empty-text="该账单周期暂无记录">
          <el-table-column label="日期" width="120">
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
          <el-table-column prop="remark" label="备注" min-width="180" />
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="scope">
              <el-button link type="primary" @click="onEditRow(scope.row)">修改</el-button>
              <el-button link type="danger" @click="onDeleteRow(scope.row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 底部汇总 -->
      <div class="sum-bar">
        <span>流入：<b class="income">{{ fmtMoney(summary.inflow) }}</b></span>
        <span>流出：<b class="expense">{{ fmtMoney(summary.outflow) }}</b></span>
        <span>差额：<b :class="summary.diff >= 0 ? 'income' : 'expense'">{{ fmtMoney(summary.diff) }}</b></span>
        <span>余额：<b :class="summary.balance >= 0 ? 'income' : 'expense'">{{ fmtMoney(summary.balance) }}</b></span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.cc-page { padding: 0; }
.cc-main { display: flex; flex-direction: column; min-height: calc(100vh - 52px); background: #f3f6f9; }

.cc-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  border-bottom: 1px solid #c8d3de;
  background: #fff;
  padding: 12px 16px;
}
.account-title { display: flex; align-items: baseline; gap: 12px; }
.account-title .t-name { font-size: 18px; font-weight: 700; color: #415163; }
.account-title .t-amount { font-size: 18px; color: #2e9c4f; }
.toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.cc-bill-panel { padding: 12px 16px; border-bottom: 1px solid #c8d3de; background: #f8fafc; }
.bill-title { color: #55677a; font-weight: 700; margin-bottom: 8px; }
.bill-pending { color: #e6a23c; font-weight: 600; }
.cc-bill-panel :deep(.el-table__row) { cursor: pointer; }
.cc-bill-panel :deep(.cycle-selected) > td.el-table__cell { background: #e8f1f8 !important; }

.detail-wrap { flex: 1; padding: 12px 16px; }
.detail-title { color: #55677a; font-weight: 700; margin-bottom: 8px; }

.income { color: #2e9c4f; }
.expense { color: #de6d6d !important; }

.sum-bar {
  background: #edf2f7;
  border-top: 1px solid #c8d3de;
  display: flex;
  gap: 22px;
  flex-wrap: wrap;
  padding: 10px 16px;
  color: #546576;
}

:deep(.el-table th.el-table__cell) { background: #eef2f6; color: #4a5a6a; font-weight: 700; }
:deep(.el-dropdown-menu__item.on) { color: #409eff; font-weight: 600; }
</style>
