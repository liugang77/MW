<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useLoanStore } from '../stores/loan'
import type { Loan, Account, Tag, LoanRateAdjustment, LoanSchedule } from '../types'
import { fmtMoney } from '../utils/format'

const route = useRoute()
const ledgerStore = useLedgerStore()
const loanStore = useLoanStore()

const loans = ref<Loan[]>([])
const accounts = ref<Account[]>([])
const tags = ref<Tag[]>([])

const dialog = ref(false)
const editingId = ref<number | null>(null)
const selectedLoanId = ref<number | null>(null)

const filterDir = ref<'all' | 'receivable' | 'payable'>('all')
const showClosed = ref(false)
const collapsed = ref<Record<string, boolean>>({})

const rateDialog = ref(false)
const editingRateId = ref<number | null>(null)
const rateForm = ref({ occurred_at: '', interest_rate: '', remark: '' })
const rateAdjustments = ref<LoanRateAdjustment[]>([])
const schedule = ref<LoanSchedule | null>(null)
const createQueryHandled = ref(false)

const form = ref<any>({
  direction: 'payable', counterparty: '', item: '', currency: 'CNY', account_id: null,
  amount: 0, settled: 0, interest_rate: 0, total_periods: null, remaining_periods: null,
  repay_method: '等额本息', occurred_at: null, due_at: null, remark: '', tag_ids: [],
  first_collect_at: null, term_value: 1, term_unit: 'year',
  collect_interval: 1, collect_interval_unit: 'month', collected_periods: 0
})

const repayMethods = ['不定', '等额本息', '等额本金', '自由还款', '分期付息一次还本']
const installmentMethods = ['等额本息', '等额本金', '分期付息一次还本']
const termUnits = [
  { v: 'year', t: '年' },
  { v: 'month', t: '月' },
  { v: 'day', t: '日' }
]

const isPayable = computed(() => form.value.direction === 'payable')
const isInstallment = computed(() => installmentMethods.includes(form.value.repay_method))
const selectedLoan = computed(() => loans.value.find((x) => x.id === selectedLoanId.value) || null)
const showSchedulePanel = computed(() => !!selectedLoan.value && installmentMethods.includes(selectedLoan.value.repay_method || ''))

const labels = computed(() => isPayable.value
  ? { who: '债权人', amount: '借入金额', method: '还款方式', account: '收入账户', hint: '比如“一般借款；买房贷款”，在返还时可以选择' }
  : { who: '债务人', amount: '借出金额', method: '收款方式', account: '支出账户', hint: '比如“一般借款；他要买房”，在收回时可以选择' }
)

const fmt = (v: string | number | null | undefined) => fmtMoney(v)
const signedRemaining = (l: Loan) => (l.direction === 'payable' ? -1 : 1) * Number(l.remaining)

const filtered = computed(() => loans.value.filter((l) => {
  if (l.loan_kind === 'p2p') return false
  if (!showClosed.value && l.is_closed) return false
  if (filterDir.value !== 'all' && l.direction !== filterDir.value) return false
  return true
}))

const groups = computed(() => {
  const map = new Map<string, Loan[]>()
  for (const l of filtered.value) {
    const key = l.counterparty || '未命名'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(l)
  }
  return Array.from(map.entries()).map(([name, items]) => ({
    name,
    items,
    total: items.reduce((s, l) => s + signedRemaining(l), 0)
  }))
})

const grandTotal = computed(() => filtered.value.reduce((s, l) => s + signedRemaining(l), 0))

function toggle(name: string) {
  collapsed.value[name] = !collapsed.value[name]
}

function selectLoan(l: Loan) {
  selectedLoanId.value = l.id
}

const dirText = (l: Loan) => l.direction === 'receivable' ? '【债权】应收款' : '【债务】应付款'

function calcTotalPeriods(): number | null {
  const termValue = Number(form.value.term_value || 0)
  const interval = Number(form.value.collect_interval || 0)
  if (!termValue || !interval) return null

  const unitDays: Record<string, number> = { day: 1, month: 30, year: 365 }
  const termDays = termValue * (unitDays[form.value.term_unit] || 0)
  const intervalDays = interval * (unitDays[form.value.collect_interval_unit] || 0)
  if (!intervalDays) return null
  return Math.max(Math.ceil(termDays / intervalDays), 1)
}

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  loans.value = await api.listLoans(lid)
  accounts.value = await api.listAccounts(lid)
  tags.value = await api.listTags(lid)

  const qAccount = Number(route.query.account_id || 0)
  if (qAccount) {
    const matched = filtered.value.find((l) => l.account_id === qAccount)
    if (matched) selectedLoanId.value = matched.id
  }

  if (!selectedLoanId.value && filtered.value.length) selectedLoanId.value = filtered.value[0].id
  if (selectedLoanId.value && !filtered.value.some((l) => l.id === selectedLoanId.value)) {
    selectedLoanId.value = filtered.value.length ? filtered.value[0].id : null
  }

  if (route.query.create && !createQueryHandled.value) {
    createQueryHandled.value = true
    openCreate(route.query.create === 'receivable' ? 'receivable' : 'payable')
  }

  await loadSelectedLoanDetails()
}

async function loadSelectedLoanDetails() {
  if (!selectedLoan.value || !showSchedulePanel.value) {
    rateAdjustments.value = []
    schedule.value = null
    return
  }
  rateAdjustments.value = await api.listLoanRateAdjustments(selectedLoan.value.id)
  schedule.value = await api.getLoanSchedule(selectedLoan.value.id)
}

function openCreate(dir: 'payable' | 'receivable' = 'payable') {
  editingId.value = null
  form.value = {
    direction: dir, counterparty: '', item: '', currency: 'CNY', account_id: null,
    amount: 0, settled: 0, interest_rate: 0, total_periods: null, remaining_periods: null,
    repay_method: '等额本息', occurred_at: new Date().toISOString().slice(0, 10) + 'T00:00:00', due_at: null, remark: '', tag_ids: [],
    first_collect_at: new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10) + 'T00:00:00',
    term_value: 1, term_unit: 'year', collect_interval: 1, collect_interval_unit: 'month', collected_periods: 0
  }
  dialog.value = true
}

function openEdit(l: Loan) {
  editingId.value = l.id
  form.value = {
    direction: l.direction, counterparty: l.counterparty, item: l.item || '', currency: l.currency || 'CNY',
    account_id: l.account_id ?? null, amount: l.amount, settled: l.settled, interest_rate: l.interest_rate,
    total_periods: l.total_periods, remaining_periods: l.remaining_periods, repay_method: l.repay_method || '',
    occurred_at: l.occurred_at, due_at: l.due_at, remark: l.remark || '', tag_ids: l.tag_ids || [],
    first_collect_at: l.first_collect_at ?? null, term_value: l.term_value ?? 1, term_unit: l.term_unit || 'year',
    collect_interval: l.collect_interval ?? 1, collect_interval_unit: l.collect_interval_unit || 'month', collected_periods: l.collected_periods ?? 0
  }
  dialog.value = true
}

async function save() {
  if (!form.value.counterparty) return ElMessage.warning('请输入债权人/债务人')
  if (!(Number(form.value.amount) > 0)) return ElMessage.warning('请输入借入/借出金额')

  if (isInstallment.value) {
    if (!form.value.first_collect_at) return ElMessage.warning('请选择首次还款日')
    const inferred = calcTotalPeriods()
    if (!form.value.total_periods && inferred) form.value.total_periods = inferred
    const total = Number(form.value.total_periods || 0)
    const paid = Number(form.value.collected_periods || 0)
    form.value.remaining_periods = Math.max(total - paid, 0)
  } else {
    form.value.first_collect_at = null
    form.value.term_value = null
    form.value.total_periods = null
    form.value.collect_interval = null
    form.value.collect_interval_unit = null
    form.value.collected_periods = null
  }

  if (editingId.value) {
    await api.updateLoan(editingId.value, form.value)
    ElMessage.success('已更新')
  } else {
    const row = await api.createLoan(ledgerStore.currentId as number, form.value)
    selectedLoanId.value = row.id
    ElMessage.success('已创建')
  }
  dialog.value = false
  await load()
}

async function settle(l: Loan) {
  try {
    const { value } = await ElMessageBox.prompt(`本次收/还款金额（剩余 ${l.remaining}）`, '收/还款', {
      inputValue: String(l.remaining),
      inputPattern: /^\d+(\.\d{1,2})?$/,
      inputErrorMessage: '请输入有效金额'
    })
    const settled = Number(l.settled) + Number(value)
    const patch: Record<string, unknown> = { settled }
    if (l.remaining_periods && l.remaining_periods > 0) patch.remaining_periods = l.remaining_periods - 1
    if (l.collected_periods != null) patch.collected_periods = Number(l.collected_periods || 0) + 1
    await api.updateLoan(l.id, patch)
    ElMessage.success('已记录')
    await load()
  } catch (e) { /* cancelled */ }
}

async function recordNextPeriod() {
  if (!selectedLoan.value || !schedule.value) return
  const next = schedule.value.items.find((x) => !x.is_paid)
  if (!next) return ElMessage.info('已没有未还期次')

  await api.updateLoan(selectedLoan.value.id, {
    settled: Number(selectedLoan.value.settled || 0) + Number(next.principal),
    collected_periods: Number(selectedLoan.value.collected_periods || 0) + 1,
    remaining_periods: Math.max(Number(selectedLoan.value.remaining_periods || 0) - 1, 0)
  })
  ElMessage.success(`已记账：第 ${next.period_no} 期`)
  await load()
}

async function remove(l: Loan) {
  try {
    await ElMessageBox.confirm('确定删除该记录吗？', '提示', { type: 'warning' })
    await api.deleteLoan(l.id)
    if (selectedLoanId.value === l.id) selectedLoanId.value = null
    ElMessage.success('已删除')
    await load()
  } catch (e) { /* cancelled */ }
}

function openCreateRateAdjustment() {
  if (!selectedLoan.value) return
  editingRateId.value = null
  rateForm.value = {
    occurred_at: new Date().toISOString().slice(0, 10) + 'T00:00:00',
    interest_rate: String(selectedLoan.value.interest_rate || 0),
    remark: ''
  }
  rateDialog.value = true
}

function openEditRateAdjustment(row: LoanRateAdjustment) {
  editingRateId.value = row.id
  rateForm.value = {
    occurred_at: row.occurred_at,
    interest_rate: String(row.interest_rate || 0),
    remark: row.remark || ''
  }
  rateDialog.value = true
}

async function saveRateAdjustment() {
  if (!selectedLoan.value) return
  if (editingRateId.value) {
    await api.updateLoanRateAdjustment(editingRateId.value, rateForm.value)
    ElMessage.success('利率调整已更新')
  } else {
    await api.createLoanRateAdjustment(selectedLoan.value.id, rateForm.value)
    ElMessage.success('利率调整已新增')
  }
  rateDialog.value = false
  await loadSelectedLoanDetails()
}

async function removeRateAdjustment(row: LoanRateAdjustment) {
  try {
    await ElMessageBox.confirm('确定删除这条利率调整吗？', '提示', { type: 'warning' })
    await api.deleteLoanRateAdjustment(row.id)
    ElMessage.success('已删除')
    await loadSelectedLoanDetails()
  } catch (e) { /* cancelled */ }
}

onMounted(load)
watch(() => ledgerStore.currentId, load)
watch(() => route.query.account_id, load)
watch(() => loanStore.savedAt, load)
watch(selectedLoanId, loadSelectedLoanDetails)
</script>

<template>
  <div class="loans">
    <div class="ln-header">
      <div class="ln-title">债权债务</div>
      <div class="ln-tools">
        <el-select v-model="filterDir" style="width:150px">
          <el-option label="所有债权和债务" value="all" />
          <el-option label="仅债权（应收款）" value="receivable" />
          <el-option label="仅债务（应付款）" value="payable" />
        </el-select>
        <el-dropdown trigger="click">
          <el-button>操作 <span style="margin-left:4px">▾</span></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="showClosed = !showClosed">
                <span :class="{ 'grp-checked': showClosed }">{{ showClosed ? '✓ ' : '　' }}显示已结清记录</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <div class="ln-table">
      <div class="ln-row ln-head">
        <span class="c-name">债权人/债务人　款项</span>
        <span class="c-kind">款项类型</span>
        <span class="c-method">收/还款方式</span>
        <span class="c-rate">利率</span>
        <span class="c-periods">剩余期数</span>
        <span class="c-amount">待收/还本金</span>
        <span class="c-op"></span>
      </div>

      <el-empty v-if="!filtered.length" description="还没有债权债务记录" />

      <template v-for="g in groups" :key="g.name">
        <template v-if="g.items.length > 1">
          <div class="ln-row ln-group" @click="toggle(g.name)">
            <span class="c-name"><span class="caret">{{ collapsed[g.name] ? '▸' : '▾' }}</span>{{ g.name }}</span>
            <span class="c-kind"></span>
            <span class="c-method"></span>
            <span class="c-rate"></span>
            <span class="c-periods"></span>
            <span class="c-amount" :class="{ neg: g.total < 0 }">{{ fmt(g.total) }}</span>
            <span class="c-op"></span>
          </div>
          <template v-if="!collapsed[g.name]">
            <div v-for="l in g.items" :key="l.id" class="ln-row ln-sub" :class="[{ closed: l.is_closed }, { selected: selectedLoanId === l.id }]" @click="selectLoan(l)">
              <span class="c-name indent">{{ l.item || '—' }}</span>
              <span class="c-kind">{{ dirText(l) }}</span>
              <span class="c-method">{{ l.repay_method || '—' }}</span>
              <span class="c-rate">{{ l.interest_rate != null ? l.interest_rate + '%' : '' }}</span>
              <span class="c-periods">{{ l.remaining_periods ?? '' }}</span>
              <span class="c-amount" :class="{ neg: signedRemaining(l) < 0 }">{{ fmt(signedRemaining(l)) }}</span>
              <span class="c-op">
                <el-dropdown trigger="click">
                  <span class="more" @click.stop>⋯</span>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item v-if="!l.is_closed" @click="settle(l)">收/还款</el-dropdown-item>
                      <el-dropdown-item @click="openEdit(l)">编辑</el-dropdown-item>
                      <el-dropdown-item divided @click="remove(l)">删除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </span>
            </div>
          </template>
        </template>

        <template v-else>
          <div v-for="l in g.items" :key="l.id" class="ln-row" :class="[{ closed: l.is_closed }, { selected: selectedLoanId === l.id }]" @click="selectLoan(l)">
            <span class="c-name">{{ l.counterparty }}<span v-if="l.item"> | {{ l.item }}</span></span>
            <span class="c-kind">{{ dirText(l) }}</span>
            <span class="c-method">{{ l.repay_method || '—' }}</span>
            <span class="c-rate">{{ l.interest_rate != null ? l.interest_rate + '%' : '' }}</span>
            <span class="c-periods">{{ l.remaining_periods ?? '' }}</span>
            <span class="c-amount" :class="{ neg: signedRemaining(l) < 0 }">{{ fmt(signedRemaining(l)) }}</span>
            <span class="c-op">
              <el-dropdown trigger="click">
                <span class="more" @click.stop>⋯</span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-if="!l.is_closed" @click="settle(l)">收/还款</el-dropdown-item>
                    <el-dropdown-item @click="openEdit(l)">编辑</el-dropdown-item>
                    <el-dropdown-item divided @click="remove(l)">删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </span>
          </div>
        </template>
      </template>

      <div class="ln-foot">
        <span>债权债务合计</span>
        <span class="total" :class="{ neg: grandTotal < 0 }">{{ fmt(grandTotal) }}</span>
      </div>
    </div>

    <div v-if="selectedLoan" class="plan-wrap">
      <div class="plan-head">
        <div class="plan-title">{{ selectedLoan.counterparty }}【{{ selectedLoan.item || '借贷项目' }}】</div>
        <div class="plan-summary" v-if="showSchedulePanel && schedule">
          <span>已还本金: {{ fmt(schedule.paid_principal) }}</span>
          <span>已还利息: {{ fmt(schedule.paid_interest) }}</span>
          <span>剩余本金: {{ fmt(schedule.remaining_principal) }}</span>
          <span>剩余利息: {{ fmt(schedule.remaining_interest) }}</span>
        </div>
        <div class="plan-summary" v-else>
          <span>{{ selectedLoan.direction === 'payable' ? '借入金额' : '借出金额' }}: {{ fmt(selectedLoan.amount) }}</span>
          <span>{{ selectedLoan.direction === 'payable' ? '已还' : '已收' }}: {{ fmt(selectedLoan.settled) }}</span>
          <span>{{ selectedLoan.direction === 'payable' ? '待还本金' : '待收本金' }}: {{ fmt(selectedLoan.remaining) }}</span>
        </div>
      </div>

      <div v-if="showSchedulePanel" class="plan-body">
        <div>
          <div class="rate-tools"><el-button size="small" @click="openCreateRateAdjustment">添加</el-button></div>
          <el-table :data="rateAdjustments" size="small" border>
            <el-table-column label="日期" min-width="120">
              <template #default="{ row }">{{ (row.occurred_at || '').slice(0, 10) }}</template>
            </el-table-column>
            <el-table-column label="利率(%)" align="right" min-width="90">
              <template #default="{ row }">{{ fmt(row.interest_rate) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="120" align="right">
              <template #default="{ row }">
                <el-button link size="small" @click="openEditRateAdjustment(row)">修改</el-button>
                <el-button link type="danger" size="small" @click="removeRateAdjustment(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div>
          <div class="sch-tools"><el-button size="small" type="primary" @click="recordNextPeriod">记账（下一期）</el-button></div>
          <el-table :data="schedule?.items || []" size="small" border>
            <el-table-column label="期次" align="right" min-width="70"><template #default="{ row }">{{ row.period_no }}</template></el-table-column>
            <el-table-column label="日期" min-width="120"><template #default="{ row }">{{ (row.due_at || '').slice(0, 10) }}</template></el-table-column>
            <el-table-column label="本期还款" align="right" min-width="110"><template #default="{ row }">{{ fmt(row.payment) }}</template></el-table-column>
            <el-table-column label="本金" align="right" min-width="100"><template #default="{ row }">{{ fmt(row.principal) }}</template></el-table-column>
            <el-table-column label="利息" align="right" min-width="100"><template #default="{ row }">{{ fmt(row.interest) }}</template></el-table-column>
            <el-table-column label="剩余本金" align="right" min-width="110"><template #default="{ row }">{{ fmt(row.balance) }}</template></el-table-column>
            <el-table-column label="状态" min-width="80"><template #default="{ row }">{{ row.is_paid ? '已还' : '未还' }}</template></el-table-column>
          </el-table>
        </div>
      </div>

      <div v-else class="plan-detail">
        <table class="detail-table">
          <tbody>
            <tr><th>款项类型</th><td>{{ dirText(selectedLoan) }}</td><th>币种</th><td>{{ selectedLoan.currency || 'CNY' }}</td></tr>
            <tr><th>利率</th><td>{{ selectedLoan.interest_rate != null ? selectedLoan.interest_rate + '%' : '—' }}</td><th>收/还款方式</th><td>{{ selectedLoan.repay_method || '—' }}</td></tr>
            <tr><th>发生日期</th><td>{{ (selectedLoan.occurred_at || '').slice(0, 10) || '—' }}</td><th>到期日期</th><td>{{ (selectedLoan.due_at || '').slice(0, 10) || '—' }}</td></tr>
            <tr><th>备注</th><td colspan="3">{{ selectedLoan.remark || '—' }}</td></tr>
          </tbody>
        </table>
        <div class="detail-ops">
          <el-button v-if="!selectedLoan.is_closed" size="small" type="primary" @click="settle(selectedLoan)">收/还款</el-button>
          <el-button size="small" @click="openEdit(selectedLoan)">编辑</el-button>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialog" :title="editingId ? (isPayable ? '编辑借入' : '编辑借出') : (isPayable ? '借入' : '借出')" width="92%" style="max-width:760px">
      <el-form label-width="92px">
        <el-row :gutter="16">
          <el-col :span="12" :xs="24"><el-form-item :label="labels.who" required><el-input v-model="form.counterparty" /></el-form-item></el-col>
          <el-col :span="12" :xs="24"><el-form-item label="款项" required><el-input v-model="form.item" :placeholder="labels.hint" /></el-form-item></el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12" :xs="24">
            <el-form-item label="币种" required>
              <el-select v-model="form.currency" style="width:100%">
                <el-option label="人民币 CNY" value="CNY" />
                <el-option label="美元 USD" value="USD" />
                <el-option label="港币 HKD" value="HKD" />
                <el-option label="欧元 EUR" value="EUR" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12" :xs="24"><el-form-item :label="labels.amount" required><el-input v-model="form.amount" type="number" /></el-form-item></el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12" :xs="24">
            <el-form-item :label="labels.method" required>
              <el-select v-model="form.repay_method" style="width:100%">
                <el-option v-for="m in repayMethods" :key="m" :label="m" :value="m" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12" :xs="24"><el-form-item label="年利率(%)"><el-input v-model="form.interest_rate" type="number" /></el-form-item></el-col>
        </el-row>

        <template v-if="isInstallment">
          <el-row :gutter="16">
            <el-col :span="12" :xs="24"><el-form-item :label="isPayable ? '首次还款日' : '首次收款日'" required><el-date-picker v-model="form.first_collect_at" type="date" value-format="YYYY-MM-DDTHH:mm:ss" style="width:100%" /></el-form-item></el-col>
            <el-col :span="12" :xs="24"><el-form-item label="贷款期限" required><div class="dual-field"><el-input v-model="form.term_value" type="number" /><el-select v-model="form.term_unit" style="width:88px"><el-option v-for="u in termUnits" :key="u.v" :label="u.t" :value="u.v" /></el-select></div></el-form-item></el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12" :xs="24"><el-form-item :label="isPayable ? '还款频率' : '收款频率'" required><div class="dual-field"><el-input v-model="form.collect_interval" type="number" /><el-select v-model="form.collect_interval_unit" style="width:88px"><el-option v-for="u in termUnits" :key="u.v" :label="u.t" :value="u.v" /></el-select></div></el-form-item></el-col>
            <el-col :span="12" :xs="24"><el-form-item :label="isPayable ? '还款总期数' : '收款总期数'"><el-input v-model="form.total_periods" type="number" placeholder="可自动推算" /></el-form-item></el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12" :xs="24"><el-form-item :label="isPayable ? '已还款期数' : '已收款期数'"><el-input v-model="form.collected_periods" type="number" /></el-form-item></el-col>
          </el-row>
        </template>

        <el-row :gutter="16">
          <el-col :span="12" :xs="24"><el-form-item :label="labels.account"><el-select v-model="form.account_id" clearable :placeholder="isPayable ? '<自动创建应付款账户>' : '<自动创建应收款账户>'" style="width:100%"><el-option v-for="a in accounts" :key="a.id" :label="`${a.icon} ${a.name}`" :value="a.id" /></el-select></el-form-item></el-col>
          <el-col :span="12" :xs="24"><el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="3" /></el-form-item></el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12" :xs="24"><el-form-item label="标签"><el-select v-model="form.tag_ids" multiple filterable style="width:100%"><el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" /></el-select></el-form-item></el-col>
          <el-col :span="12" :xs="24"><el-form-item label="借贷发生日" required><el-date-picker v-model="form.occurred_at" type="date" value-format="YYYY-MM-DDTHH:mm:ss" style="width:100%" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="rateDialog" :title="editingRateId ? '修改利率调整' : '新增利率调整'" width="90%" style="max-width:420px">
      <el-form label-width="92px">
        <el-form-item label="日期" required><el-date-picker v-model="rateForm.occurred_at" type="date" value-format="YYYY-MM-DDTHH:mm:ss" style="width:100%" /></el-form-item>
        <el-form-item label="利率(%)" required><el-input v-model="rateForm.interest_rate" type="number" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="rateForm.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rateDialog = false">取消</el-button>
        <el-button type="primary" @click="saveRateAdjustment">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.loans { padding: 4px; }
.dual-field { display: flex; gap: 8px; width: 100%; }
.dual-field .el-input { flex: 1 1 auto; }
.ln-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.ln-title { font-size: 18px; font-weight: 600; color: #3c4b59; }
.ln-tools { display: flex; gap: 8px; align-items: center; }

.ln-table { background: #fff; border-radius: 8px; overflow: hidden; border: 1px solid #ebeef2; }
.ln-row { display: flex; align-items: center; padding: 0 14px; height: 40px; border-bottom: 1px solid #f2f4f6; font-size: 13px; color: #5a6776; }
.ln-row.selected { background: #edf4fb; }
.ln-head { background: #f7f9fb; color: #93a1af; font-weight: 600; height: 38px; }
.ln-group { background: #fafbfc; cursor: pointer; font-weight: 600; color: #3c4b59; }
.ln-sub { background: #fff; }
.ln-row.closed { opacity: .5; }

.c-name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c-name.indent { padding-left: 22px; }
.c-kind { width: 130px; flex: none; }
.c-method { width: 110px; flex: none; }
.c-rate { width: 70px; flex: none; text-align: right; }
.c-periods { width: 80px; flex: none; text-align: right; }
.c-amount { width: 130px; flex: none; text-align: right; font-weight: 600; color: #3c4b59; }
.c-amount.neg { color: #de6d6d; }
.c-op { width: 36px; flex: none; text-align: right; }

.caret { display: inline-block; width: 16px; color: #93a1af; }
.more { cursor: pointer; color: #93a1af; padding: 0 4px; }
.grp-checked { color: var(--cz-blue, #3f79a8); }

.ln-foot { display: flex; justify-content: flex-end; gap: 16px; align-items: center; padding: 10px 16px; color: #909399; font-size: 13px; }
.ln-foot .total { font-size: 16px; font-weight: 700; color: #3c4b59; }
.ln-foot .total.neg { color: #de6d6d; }

.plan-wrap { margin-top: 12px; border: 1px solid #ebeef2; border-radius: 8px; background: #fff; }
.plan-head { padding: 12px 14px; border-bottom: 1px solid #f2f4f6; }
.plan-title { font-size: 22px; font-weight: 600; color: #3c4b59; }
.plan-summary { display: flex; gap: 20px; margin-top: 6px; font-size: 13px; color: #606266; }
.plan-body { display: grid; grid-template-columns: 260px 1fr; gap: 10px; padding: 10px; }
.rate-tools, .sch-tools { margin-bottom: 8px; }
.plan-detail { padding: 12px 14px; }
.detail-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.detail-table th, .detail-table td { border: 1px solid #ebeef5; padding: 8px 10px; text-align: left; }
.detail-table th { background: #fafafa; color: #909399; font-weight: 500; width: 96px; white-space: nowrap; }
.detail-ops { margin-top: 12px; display: flex; gap: 8px; }

@media (max-width: 960px) {
  .plan-body { grid-template-columns: 1fr; }
  .plan-summary { flex-wrap: wrap; gap: 8px 16px; }
}
</style>
