<script setup lang="ts">
import { ref, computed, onMounted, watch, reactive } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useP2pStore } from '../stores/p2p'
import { useRecordStore } from '../stores/record'
import type { Account, Loan, Transaction, Tag } from '../types'
import { fmtMoney } from '../utils/format'

const route = useRoute()
const ledgerStore = useLedgerStore()
const p2pStore = useP2pStore()
const recordStore = useRecordStore()

const accounts = ref<Account[]>([])
const loans = ref<Loan[]>([])
const transactions = ref<Transaction[]>([])
const tags = ref<Tag[]>([])
const selectedAccountId = ref<number | null>(null)
const activeTab = ref<'trades' | 'list' | 'pending'>('list')

const P2P_TYPES = ['p2p']
const p2pAccounts = computed(() => accounts.value.filter((a) => P2P_TYPES.includes(a.type)))

const fmt = (v: string | number) => fmtMoney(v)
const unitText = (u?: string | null) => (u === 'year' ? '年' : u === 'day' ? '日' : u === 'month' ? '月' : '')

// 某账户下的网贷项目
function projectsOf(accountId: number) {
  return loans.value.filter((l) => l.loan_kind === 'p2p' && l.account_id === accountId)
}

// 单条项目的待收利息（每期利息 × 剩余期数）
function pendingInterestOf(l: Loan): number {
  const remainPeriods = Math.max(Number(l.total_periods || 0) - Number(l.collected_periods || 0), 0)
  return Number(l.per_interest || 0) * remainPeriods
}
// 单条项目的已实现利息（每期利息 × 已收期数）
function earnedInterestOf(l: Loan): number {
  return Number(l.per_interest || 0) * Number(l.collected_periods || 0)
}

// 账户级汇总行（对应原设计上方账户表）
interface AccountRow {
  id: number
  name: string
  expectedRate: number
  realizedPnl: number
  pendingInterest: number
  pendingPrincipal: number
  available: number
  assetValue: number
}

const accountRows = computed<AccountRow[]>(() =>
  p2pAccounts.value.map((a) => {
    const projects = projectsOf(a.id)
    const pendingPrincipal = projects.reduce((s, l) => s + Number(l.remaining || 0), 0)
    const pendingInterest = projects.reduce((s, l) => s + pendingInterestOf(l), 0)
    const realizedPnl = projects.reduce((s, l) => s + earnedInterestOf(l), 0)
    const assetValue = Number(a.current_balance || 0)
    const available = Math.max(assetValue - pendingPrincipal, 0)
    const totalAmount = projects.reduce((s, l) => s + Number(l.amount || 0), 0)
    const expectedRate = totalAmount
      ? projects.reduce((s, l) => s + Number(l.interest_rate || 0) * Number(l.amount || 0), 0) / totalAmount
      : 0
    return {
      id: a.id,
      name: a.name,
      expectedRate,
      realizedPnl,
      pendingInterest,
      pendingPrincipal,
      available,
      assetValue,
    }
  })
)

const totalRow = computed<AccountRow>(() => {
  const rows = accountRows.value
  const sum = (k: keyof AccountRow) => rows.reduce((s, r) => s + Number(r[k] || 0), 0)
  return {
    id: 0,
    name: '合计',
    expectedRate: rows.length ? sum('expectedRate') / rows.length : 0,
    realizedPnl: sum('realizedPnl'),
    pendingInterest: sum('pendingInterest'),
    pendingPrincipal: sum('pendingPrincipal'),
    available: sum('available'),
    assetValue: sum('assetValue'),
  }
})

// 当前选中账户的项目
const projects = computed(() => (selectedAccountId.value ? projectsOf(selectedAccountId.value) : []))

// 投资列表筛选：当前持有 / 已完成 / 所有
const listFilter = ref<'holding' | 'closed' | 'all'>('holding')
const listFilterText = computed(
  () => ({ holding: '当前持有网贷', closed: '已完成网贷', all: '所有' }[listFilter.value])
)
const filteredProjects = computed(() => {
  if (listFilter.value === 'holding') return projects.value.filter((l) => !l.is_closed)
  if (listFilter.value === 'closed') return projects.value.filter((l) => l.is_closed)
  return projects.value
})

// 待收明细：仅未完成项目；可选中一行后点「网贷收回」
const pendingProjects = computed(() => projects.value.filter((l) => !l.is_closed))
const selectedPendingId = ref<number | null>(null)
function selectPending(row: Loan) {
  selectedPendingId.value = row.id
}
function pendingRowClass({ row }: { row: Loan }) {
  return row.id === selectedPendingId.value ? 'cur-row' : ''
}

// 当前账户交易明细（转入/借出/收回/奖励/转出）
const accountTxns = computed(() =>
  selectedAccountId.value
    ? transactions.value.filter(
        (t) => t.account_id === selectedAccountId.value || t.to_account_id === selectedAccountId.value
      )
    : []
)

const tagName = (id: number) => tags.value.find((t) => t.id === id)?.name || ''
const txnTags = (t: Transaction) => (t.tag_ids || []).map(tagName).filter(Boolean).join('、')

// 活动类型 + 本金/利息拆分
function txnActivity(t: Transaction): string {
  const r = t.remark || ''
  if (r.startsWith('网贷借出')) return '网贷借出'
  if (r.startsWith('网贷收回')) return '网贷回收'
  if (t.type === 'transfer') return t.to_account_id === selectedAccountId.value ? '转入' : '转出'
  if (t.type === 'income') return '网贷投资奖励'
  if (t.type === 'expense') return '支出'
  return '其他'
}
// 发生额：流入为正、流出为负
function txnDelta(t: Transaction): number {
  const amt = Number(t.amount || 0)
  if (t.type === 'transfer') return t.to_account_id === selectedAccountId.value ? amt : -amt
  if (t.type === 'income') return amt
  if (t.type === 'expense') return -amt
  return amt
}
// 本金：网贷借出/收回的本金部分
function txnPrincipal(t: Transaction): number {
  const r = t.remark || ''
  if (r.startsWith('网贷借出') || r.startsWith('网贷收回本金')) return Number(t.amount || 0)
  return 0
}
// 利息：网贷收回利息部分
function txnInterest(t: Transaction): number {
  return (t.remark || '').startsWith('网贷收回利息') ? Number(t.amount || 0) : 0
}

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  loans.value = await api.listLoans(lid)
  tags.value = await api.listTags(lid)
  if (!selectedAccountId.value && p2pAccounts.value.length) {
    selectedAccountId.value = p2pAccounts.value[0].id
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

function openLend() {
  p2pStore.open('lend', selectedAccountId.value ?? undefined)
}
function openCollect() {
  p2pStore.open('collect', selectedAccountId.value ?? undefined, selectedPendingId.value ?? undefined)
}

// 资金转账：在资金账户与网贷账户之间划转（转入/转出）
const selectedAccount = computed(() => accounts.value.find((a) => a.id === selectedAccountId.value) || null)
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
    ElMessage.warning('请先选择网贷账户')
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
    const p2pId = selectedAccount.value.id
    const counter = transferForm.counter_account_id
    await api.createTransaction(lid, {
      type: 'transfer',
      amount: amt.toFixed(2),
      account_id: transferIsIn.value ? counter : p2pId,
      to_account_id: transferIsIn.value ? p2pId : counter,
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

// 交易明细行操作：修改 / 删除
function canEditTxn(t: Transaction): boolean {
  const r = t.remark || ''
  // 转入（转账到本网贷账户）也可修改
  if (t.type === 'transfer' && t.to_account_id === selectedAccountId.value) return true
  return r.startsWith('网贷借出') || r.startsWith('网贷收回')
}
function onEditTxn(row: Transaction) {
  const r = row.remark || ''
  // 转入：用转账窗口编辑
  if (row.type === 'transfer' && row.to_account_id === selectedAccountId.value) {
    recordStore.edit(row)
    return
  }
  if (r.startsWith('网贷借出') && row.loan_id) {
    const loan = loans.value.find((l) => l.id === row.loan_id)
    if (loan) p2pStore.openEditLend(loan)
    return
  }
  if (r.startsWith('网贷收回') && row.collect_group && row.loan_id) {
    const group = row.collect_group
    const groupTxns = transactions.value.filter((t) => t.collect_group === group)
    const principal = groupTxns
      .filter((t) => (t.remark || '').startsWith('网贷收回本金'))
      .reduce((s, t) => s + Number(t.amount || 0), 0)
    const interest = groupTxns
      .filter((t) => (t.remark || '').startsWith('网贷收回利息'))
      .reduce((s, t) => s + Number(t.amount || 0), 0)
    p2pStore.openEditCollect({
      group,
      loanId: row.loan_id,
      principal,
      interest,
      incomeAccountId: row.account_id,
      occurredAt: row.occurred_at,
      remark: groupTxns.find((t) => (t.remark || '').startsWith('网贷收回利息'))?.remark ?? null,
      tagIds: row.tag_ids ? [...row.tag_ids] : []
    })
  }
}
async function onDeleteTxn(row: Transaction) {
  const r = row.remark || ''
  const tip = r.startsWith('网贷借出')
    ? '删除该笔借出将同时移除对应的网贷项目，确定？'
    : r.startsWith('网贷收回')
      ? '删除该笔收回将恢复项目的待收本金与期数，确定？'
      : '确定删除这笔流水？'
  await ElMessageBox.confirm(tip, '提示', { type: 'warning' })
  await api.deleteTransaction(row.id)
  ElMessage.success('已删除')
  await load()
}

function selectAccount(row: AccountRow) {
  if (row.id) selectedAccountId.value = row.id
}

function accountRowClass({ row }: { row: AccountRow }) {
  return row.id === selectedAccountId.value ? 'cur-row' : ''
}

// 跟随路由 query 中的 account_id 切换账户
watch(
  () => route.query.account_id,
  (v) => {
    if (v) selectedAccountId.value = Number(v)
  },
  { immediate: true }
)

onMounted(load)
watch(() => ledgerStore.currentId, load)
watch(() => p2pStore.savedAt, load)
watch(() => recordStore.savedAt, load)
watch(selectedAccountId, () => { selectedPendingId.value = null; loadTxns() })
</script>

<template>
  <div class="p2p-page">
    <!-- 上方：网贷账户列表 -->
    <div class="panel">
      <div class="panel-head">
        <span class="panel-title">网贷</span>
        <div class="head-spacer" />
      </div>

      <el-table
        :data="accountRows"
        size="small"
        border
        :row-class-name="accountRowClass"
        @row-click="selectAccount"
      >
        <el-table-column label="账户名称" min-width="160" fixed="left">
          <template #default="{ row }"><span style="font-weight:600">{{ row.name }}</span></template>
        </el-table-column>
        <el-table-column label="预期年化收益率" align="right" min-width="130">
          <template #default="{ row }">{{ fmt(row.expectedRate) }}%</template>
        </el-table-column>
        <el-table-column label="实现盈亏" align="right" min-width="110">
          <template #default="{ row }">{{ fmt(row.realizedPnl) }}</template>
        </el-table-column>
        <el-table-column label="待收利息" align="right" min-width="110">
          <template #default="{ row }">{{ fmt(row.pendingInterest) }}</template>
        </el-table-column>
        <el-table-column label="待收本金" align="right" min-width="120">
          <template #default="{ row }">{{ fmt(row.pendingPrincipal) }}</template>
        </el-table-column>
        <el-table-column label="可用资金" align="right" min-width="110">
          <template #default="{ row }">{{ fmt(row.available) }}</template>
        </el-table-column>
        <el-table-column label="资产值" align="right" min-width="120">
          <template #default="{ row }">{{ fmt(row.assetValue) }}</template>
        </el-table-column>
        <template #empty>暂无网贷账户，请在账户中心新增「P2P/网贷」账户</template>
      </el-table>

      <!-- 汇总条 -->
      <div v-if="accountRows.length" class="p2p-summary">
        <div class="sum-item"><span class="lbl">预期年化收益率</span><span class="val">{{ fmt(totalRow.expectedRate) }}%</span></div>
        <div class="sum-item"><span class="lbl">实现盈亏</span><span class="val">{{ fmt(totalRow.realizedPnl) }}</span></div>
        <div class="sum-item"><span class="lbl">待收利息</span><span class="val">{{ fmt(totalRow.pendingInterest) }}</span></div>
        <div class="sum-item"><span class="lbl">待收本金</span><span class="val">{{ fmt(totalRow.pendingPrincipal) }}</span></div>
        <div class="sum-item"><span class="lbl">可用资金</span><span class="val">{{ fmt(totalRow.available) }}</span></div>
        <div class="sum-item"><span class="lbl">资产值</span><span class="val">{{ fmt(totalRow.assetValue) }}</span></div>
      </div>
    </div>

    <!-- 下方：选中账户下的产品/明细 -->
    <div class="panel">
      <!-- 操作按钮：按当前标签显示 -->
      <div class="tab-actions">
        <template v-if="activeTab === 'trades'">
          <el-button size="small" @click="openLend">网贷借出</el-button>
          <el-button size="small" @click="openTransfer">转账</el-button>
        </template>
        <el-button v-else-if="activeTab === 'pending'" size="small" :disabled="!selectedPendingId" @click="openCollect">网贷收回</el-button>
      </div>
      <div class="tabs">
        <span class="tab" :class="{ active: activeTab === 'trades' }" @click="activeTab = 'trades'">交易明细</span>
        <span class="tab" :class="{ active: activeTab === 'list' }" @click="activeTab = 'list'">投资列表</span>
        <span class="tab" :class="{ active: activeTab === 'pending' }" @click="activeTab = 'pending'">待收明细</span>
        <el-dropdown v-if="activeTab === 'list'" class="list-filter" trigger="click" @command="listFilter = $event">
          <span class="filter-trigger">{{ listFilterText }}<el-icon class="el-icon--right"><arrow-down /></el-icon></span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="holding" :class="{ on: listFilter === 'holding' }">当前持有网贷</el-dropdown-item>
              <el-dropdown-item command="closed" :class="{ on: listFilter === 'closed' }">已完成网贷</el-dropdown-item>
              <el-dropdown-item command="all" :class="{ on: listFilter === 'all' }">所有</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <!-- 交易明细：当前账户的资金流水 -->
      <template v-if="activeTab === 'trades'">
        <el-table :data="accountTxns" size="small" border>
        <el-table-column label="日期" min-width="110" fixed="left">
          <template #default="{ row }">{{ (row.occurred_at || '').slice(0, 10) }}</template>
        </el-table-column>
        <el-table-column label="投资名称" min-width="160">
          <template #default="{ row }">{{ (row.remark || '').replace(/^网贷(借出|收回本金|收回利息|收回)：/, '') }}</template>
        </el-table-column>
        <el-table-column label="本金" align="right" min-width="100">
          <template #default="{ row }">{{ fmt(txnPrincipal(row)) }}</template>
        </el-table-column>
        <el-table-column label="利息" align="right" min-width="100">
          <template #default="{ row }">{{ fmt(txnInterest(row)) }}</template>
        </el-table-column>
        <el-table-column label="发生额" align="right" min-width="110">
          <template #default="{ row }">
            <span :class="txnDelta(row) >= 0 ? 'pos' : 'neg'">{{ fmt(txnDelta(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="活动类型" min-width="120">
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
            <el-button v-if="canEditTxn(row)" link type="primary" size="small" @click="onEditTxn(row)">修改</el-button>
            <el-button link type="danger" size="small" @click="onDeleteTxn(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>当前账户暂无交易明细</template>
      </el-table>
      </template>

      <!-- 投资列表：账户下不同产品 -->
      <el-table v-else-if="activeTab === 'list'" :data="filteredProjects" size="small" border>
        <el-table-column label="名称" min-width="160" fixed="left">
          <template #default="{ row }"><span style="font-weight:600">{{ row.item || row.counterparty }}</span></template>
        </el-table-column>
        <el-table-column label="投资日期" min-width="120">
          <template #default="{ row }">{{ (row.occurred_at || '').slice(0, 10) }}</template>
        </el-table-column>
        <el-table-column label="期限" align="center" min-width="100">
          <template #default="{ row }">{{ row.term_value ? row.term_value + unitText(row.term_unit) : '—' }}</template>
        </el-table-column>
        <el-table-column label="收款方式" min-width="160">
          <template #default="{ row }">{{ row.interest_method || row.repay_method || '—' }}</template>
        </el-table-column>
        <el-table-column label="收款间隔" align="center" min-width="120">
          <template #default="{ row }">
            {{ row.collect_interval ? row.collect_interval + unitText(row.collect_interval_unit) : '到期收款' }}
          </template>
        </el-table-column>
        <el-table-column label="剩余期数" align="center" min-width="100">
          <template #default="{ row }">{{ Math.max((row.total_periods || 0) - (row.collected_periods || 0), 0) }}</template>
        </el-table-column>
        <el-table-column label="年利率" align="right" min-width="100">
          <template #default="{ row }">{{ fmt(row.interest_rate || 0) }}%</template>
        </el-table-column>
        <el-table-column label="待收本金" align="right" min-width="120">
          <template #default="{ row }">{{ fmt(row.remaining || 0) }}</template>
        </el-table-column>
        <el-table-column label="状态" align="center" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_closed ? 'info' : 'success'" size="small" effect="plain">
              {{ row.is_closed ? '已完成' : '持有中' }}
            </el-tag>
          </template>
        </el-table-column>
        <template #empty>当前账户暂无网贷项目，点击「网贷借出」开始记账</template>
      </el-table>

      <!-- 待收明细 -->
      <template v-else>
        <el-table :data="pendingProjects" size="small" border highlight-current-row
                  :row-class-name="pendingRowClass" @row-click="selectPending">
          <el-table-column label="投资名称" min-width="160" fixed="left">
            <template #default="{ row }"><span style="font-weight:600">{{ row.item || row.counterparty }}</span></template>
          </el-table-column>
          <el-table-column label="待收本金" align="right" min-width="120">
            <template #default="{ row }">{{ fmt(row.remaining || 0) }}</template>
          </el-table-column>
          <el-table-column label="待收利息" align="right" min-width="120">
            <template #default="{ row }">{{ fmt(pendingInterestOf(row)) }}</template>
          </el-table-column>
          <el-table-column label="应收合计" align="right" min-width="120">
            <template #default="{ row }">{{ fmt(Number(row.remaining || 0) + pendingInterestOf(row)) }}</template>
          </el-table-column>
          <el-table-column label="剩余期数" align="center" min-width="110">
            <template #default="{ row }">{{ Math.max((row.total_periods || 0) - (row.collected_periods || 0), 0) }}</template>
          </el-table-column>
          <el-table-column label="下次收款" min-width="120">
            <template #default="{ row }">{{ (row.first_collect_at || '').slice(0, 10) }}</template>
          </el-table-column>
          <template #empty>当前账户暂无待收明细</template>
        </el-table>
      </template>
    </div>

    <!-- 资金转账对话框 -->
    <el-dialog v-model="transferDialog" title="资金转账" width="440px" append-to-body>
      <el-form label-width="90px">
        <el-form-item label="网贷账户">
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
.p2p-page { padding: 12px 16px; display: flex; flex-direction: column; gap: 14px; }
.panel { background: #fff; border: 1px solid #ebeef2; border-radius: 8px; padding: 12px 14px; }
.panel-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.panel-title { font-size: 16px; font-weight: 600; color: #3c4b59; }
.head-spacer { flex: 1; }
.tabs { display: flex; align-items: center; gap: 18px; margin-bottom: 10px; border-bottom: 1px solid #f2f4f6; }
.tab { padding: 6px 2px; font-size: 14px; color: #909399; cursor: pointer; border-bottom: 2px solid transparent; }
.tab.active { color: #409eff; border-bottom-color: #409eff; font-weight: 600; }
.list-filter { margin-left: auto; }
.tab-actions { display: flex; justify-content: flex-end; gap: 8px; align-items: center; min-height: 32px; margin-bottom: 8px; }
.filter-trigger { display: inline-flex; align-items: center; font-size: 13px; color: #606266; cursor: pointer; padding: 4px 10px; border: 1px solid #dcdfe6; border-radius: 4px; }
.filter-trigger:hover { color: #409eff; border-color: #c6e2ff; }
:deep(.el-dropdown-menu__item.on) { color: #409eff; font-weight: 600; }
.p2p-summary { display: flex; flex-wrap: wrap; gap: 28px; margin-top: 12px; padding: 10px 16px; background: #f7f8fa; border-radius: 6px; }
.sum-item { display: flex; flex-direction: column; gap: 2px; }
.sum-item .lbl { font-size: 12px; color: #909399; }
.sum-item .val { font-size: 15px; font-weight: 600; color: #303133; }
:deep(.cur-row > td) { background: #edf4fb !important; }
.pending-bar { display: flex; justify-content: flex-end; margin-bottom: 10px; }:deep(.el-table__row) { cursor: pointer; }
.pos { color: #f56c6c; }
.neg { color: #67c23a; }
</style>
