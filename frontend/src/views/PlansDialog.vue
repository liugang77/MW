<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { usePlanStore } from '../stores/plan'
import type { Account, Tag, Category, Instrument, InstrumentPrice, Loan, Plan, PlanType } from '../types'

const ledgerStore = useLedgerStore()
const planStore = usePlanStore()

const plans = ref<Plan[]>([])
const accounts = ref<Account[]>([])
const tags = ref<Tag[]>([])
const categories = ref<Category[]>([])
const instruments = ref<Instrument[]>([])
const instrumentPrices = ref<InstrumentPrice[]>([])
const loans = ref<Loan[]>([])

const CASH_TYPES = ['cash', 'bank', 'wallet', 'prepaid']
const FUND_TYPES = ['fund', 'money_fund']
const cashAccounts = computed(() => accounts.value.filter((a) => CASH_TYPES.includes(a.type)))
const fundAccounts = computed(() => accounts.value.filter((a) => FUND_TYPES.includes(a.type)))

const today = () => new Date().toISOString().slice(0, 10)
const num = (v: string | number | null | undefined) => Number(v || 0)

// ---- 主对话框 ----
const dialogVisible = computed({
  get: () => planStore.visible,
  set: (v: boolean) => { if (!v) planStore.close() }
})

const FREQ_OPTS = [
  { v: 'once', t: '一次性' },
  { v: 'daily', t: '每天' },
  { v: 'weekly', t: '每周' },
  { v: 'monthly', t: '每月' },
  { v: 'quarterly', t: '每季' },
  { v: 'yearly', t: '每年' }
]
const freqText = (f: string) => FREQ_OPTS.find((x) => x.v === f)?.t || f

const TYPE_TEXT: Record<PlanType, string> = {
  reminder: '提醒',
  income_expense: '收支计划',
  transfer: '转账计划',
  fund_invest: '基金定投',
  loan_repay: '贷款还款',
  p2p_collect: '网贷收回'
}
const typeText = (t: string) => TYPE_TEXT[t as PlanType] || t
const statusText = (s: string) => (s === 'active' ? '执行中' : s === 'done' ? '已完成' : '已暂停')

async function loadPlans() {
  const lid = ledgerStore.currentId
  if (!lid) return
  plans.value = await api.listPlans(lid)
}

async function loadMeta() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  tags.value = await api.listTags(lid)
  categories.value = await api.listCategories(lid)
  instruments.value = await api.listInstruments(lid)
  instrumentPrices.value = await api.listInstrumentPrices(lid)
  loans.value = await api.listLoans(lid)
}

watch(() => planStore.visible, async (v) => {
  if (v) {
    await loadMeta()
    await loadPlans()
  }
})

// ---- 新增 / 编辑对话框 ----
const formVisible = ref(false)
const editingId = ref<number | null>(null)
const formType = ref<PlanType>('reminder')
const form = ref({
  name: '',
  frequency: 'monthly',
  start_date: today(),
  end_date: '',
  remind_days: 0,
  account_id: null as number | null,
  to_account_id: null as number | null,
  fee_account_id: null as number | null,
  category_id: null as number | null,
  amount: '',
  fee: '',
  instrument_id: null as number | null,
  fund_symbol: '',
  fee_rate: '',
  auto_execute: false,
  tag_ids: [] as number[],
  remark: ''
})

const formTitle = computed(() => (editingId.value ? '编辑计划' : '新增' + TYPE_TEXT[formType.value]))

function openCreate(t: PlanType) {
  editingId.value = null
  formType.value = t
  form.value = {
    name: '',
    frequency: t === 'reminder' ? 'monthly' : 'monthly',
    start_date: today(),
    end_date: '',
    remind_days: 0,
    account_id: null,
    to_account_id: null,
    fee_account_id: null,
    category_id: null,
    amount: '',
    fee: '',
    instrument_id: null,
    fund_symbol: '',
    fee_rate: '',
    auto_execute: false,
    tag_ids: [],
    remark: ''
  }
  formVisible.value = true
}

function openEdit(p: Plan) {
  editingId.value = p.id
  formType.value = p.plan_type
  form.value = {
    name: p.name,
    frequency: p.frequency,
    start_date: p.start_date || today(),
    end_date: p.end_date || '',
    remind_days: p.remind_days || 0,
    account_id: p.account_id ?? null,
    to_account_id: p.to_account_id ?? null,
    fee_account_id: p.fee_account_id ?? null,
    category_id: p.category_id ?? null,
    amount: p.amount != null ? String(p.amount) : '',
    fee: p.fee != null ? String(p.fee) : '',
    instrument_id: p.instrument_id ?? null,
    fund_symbol: p.fund_symbol || '',
    fee_rate: p.fee_rate != null ? String(p.fee_rate) : '',
    auto_execute: p.auto_execute,
    tag_ids: p.tags.map((t) => t.id),
    remark: p.remark || ''
  }
  formVisible.value = true
}

const fundOptions = computed(() =>
  instruments.value.filter((i) => i.category === 'open_fund' || i.category === 'money_fund')
)

function onFundChange() {
  const inst = fundOptions.value.find((i) => i.id === form.value.instrument_id)
  if (inst) form.value.fund_symbol = inst.code || inst.name
}

function validateForm(): boolean {
  if (!form.value.name) { ElMessage.warning('请输入计划名称'); return false }
  if (!form.value.start_date) { ElMessage.warning('请选择开始日期'); return false }
  const t = formType.value
  if (t === 'income_expense') {
    if (!form.value.account_id) { ElMessage.warning('请选择资金账户'); return false }
    if (!form.value.category_id) { ElMessage.warning('请选择收支项目'); return false }
  } else if (t === 'transfer') {
    if (!form.value.account_id) { ElMessage.warning('请选择转出账户'); return false }
    if (!form.value.to_account_id) { ElMessage.warning('请选择转入账户'); return false }
  } else if (t === 'fund_invest') {
    if (!form.value.account_id) { ElMessage.warning('请选择基金账户'); return false }
    if (!form.value.to_account_id) { ElMessage.warning('请选择资金账户'); return false }
    if (!form.value.instrument_id) { ElMessage.warning('请选择申购基金'); return false }
  }
  return true
}

async function saveForm() {
  if (!validateForm()) return
  const lid = ledgerStore.currentId
  if (!lid) return
  const t = formType.value
  let txnType: string | null = null
  if (t === 'income_expense') {
    const cat = categories.value.find((c) => c.id === form.value.category_id)
    txnType = cat?.kind === 'income' ? 'income' : 'expense'
  }
  const payload: Record<string, unknown> = {
    plan_type: t,
    name: form.value.name,
    frequency: form.value.frequency,
    start_date: form.value.start_date,
    end_date: form.value.end_date || null,
    remind_days: form.value.remind_days || 0,
    account_id: form.value.account_id,
    to_account_id: form.value.to_account_id,
    fee_account_id: form.value.fee_account_id,
    category_id: form.value.category_id,
    amount: form.value.amount || 0,
    fee: form.value.fee || 0,
    txn_type: txnType,
    instrument_id: form.value.instrument_id,
    fund_symbol: form.value.fund_symbol || null,
    fee_rate: form.value.fee_rate || 0,
    auto_execute: form.value.auto_execute,
    remark: form.value.remark || null,
    tag_ids: form.value.tag_ids
  }
  if (editingId.value) {
    await api.updatePlan(editingId.value, payload)
    ElMessage.success('已保存')
  } else {
    await api.createPlan(lid, payload)
    ElMessage.success('已创建')
  }
  formVisible.value = false
  planStore.markSaved()
  await loadPlans()
}

async function removePlan(p: Plan) {
  try {
    await ElMessageBox.confirm(`确定删除计划「${p.name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await api.deletePlan(p.id)
  ElMessage.success('已删除')
  await loadPlans()
}

// ---- 执行对话框 ----
const execVisible = ref(false)
const execPlan = ref<Plan | null>(null)
const execLoan = ref<Loan | null>(null)
const exec = ref({
  occurred_at: today(),
  amount: '',
  fee: '',
  principal: '',
  interest: '',
  account_id: null as number | null,
  to_account_id: null as number | null,
  remark: '',
  tag_ids: [] as number[],
  keep_open: true
})

const execIsP2p = computed(() => execPlan.value?.plan_type === 'p2p_collect')
const execTotalPI = computed(() => (num(exec.value.principal) + num(exec.value.interest)).toFixed(2))

function openExec(p: Plan) {
  execPlan.value = p
  execLoan.value = p.loan_id ? loans.value.find((l) => l.id === p.loan_id) || null : null
  exec.value = {
    occurred_at: today(),
    amount: p.amount != null ? String(p.amount) : '',
    fee: p.fee != null ? String(p.fee) : '',
    principal: '',
    interest: '',
    account_id: p.account_id ?? null,
    to_account_id: p.to_account_id ?? null,
    remark: p.remark || '',
    tag_ids: p.tags.map((t) => t.id),
    keep_open: true
  }
  if (execLoan.value) {
    exec.value.principal = execLoan.value.remaining || ''
    exec.value.interest = execLoan.value.per_interest || ''
    if (!exec.value.to_account_id) {
      exec.value.to_account_id = execLoan.value.cash_account_id ?? null
    }
  }
  execVisible.value = true
}

async function submitExec() {
  if (!execPlan.value) return
  const payload: Record<string, unknown> = {
    occurred_at: exec.value.occurred_at + 'T00:00:00',
    amount: exec.value.amount || 0,
    fee: exec.value.fee || 0,
    principal: exec.value.principal || 0,
    interest: exec.value.interest || 0,
    account_id: exec.value.account_id,
    to_account_id: exec.value.to_account_id,
    remark: exec.value.remark || null,
    tag_ids: exec.value.tag_ids,
    keep_open: exec.value.keep_open
  }
  await api.executePlan(execPlan.value.id, payload)
  ElMessage.success('已执行')
  execVisible.value = false
  planStore.markSaved()
  await loadPlans()
}

const acctName = (id: number | null | undefined) =>
  accounts.value.find((a) => a.id === id)?.name || ''
</script>

<template>
  <el-dialog v-model="dialogVisible" title="财务计划和提醒" width="92%" style="max-width:920px" :close-on-click-modal="false">
    <div class="plan-toolbar">
      <el-dropdown @command="openCreate">
        <el-button type="primary">新增计划<el-icon class="el-icon--right"><svg viewBox="0 0 1024 1024" width="1em" height="1em"><path fill="currentColor" d="M831.872 340.864 512 652.672 192.128 340.864a30.592 30.592 0 0 0-42.752 0 29.12 29.12 0 0 0 0 41.6L489.664 714.24a32 32 0 0 0 44.672 0l340.288-331.712a29.12 29.12 0 0 0 0-41.728 30.592 30.592 0 0 0-42.752 0z"/></svg></el-icon></el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="reminder">提醒</el-dropdown-item>
            <el-dropdown-item command="income_expense">收支计划</el-dropdown-item>
            <el-dropdown-item command="transfer">转账计划</el-dropdown-item>
            <el-dropdown-item command="fund_invest">基金申购定投计划</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <el-table :data="plans" border size="small" style="width:100%">
      <el-table-column label="类型" width="90">
        <template #default="{ row }">{{ typeText(row.plan_type) }}</template>
      </el-table-column>
      <el-table-column prop="name" label="计划名称" min-width="160" />
      <el-table-column label="发生频率" width="90">
        <template #default="{ row }">{{ freqText(row.frequency) }}</template>
      </el-table-column>
      <el-table-column prop="start_date" label="开始日期" width="110" />
      <el-table-column label="结束日期" width="110">
        <template #default="{ row }">{{ row.end_date || '—' }}</template>
      </el-table-column>
      <el-table-column label="下次执行日期" width="120">
        <template #default="{ row }">{{ row.next_run_date || '—' }}</template>
      </el-table-column>
      <el-table-column label="执行状态" width="90">
        <template #default="{ row }">{{ statusText(row.status) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="170" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" :disabled="row.status === 'done'" @click="openExec(row)">执行</el-button>
          <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="removePlan(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>

  <!-- 新增 / 编辑 -->
  <el-dialog v-model="formVisible" :title="formTitle" width="92%" style="max-width:560px" :close-on-click-modal="false" append-to-body>
    <el-form label-width="100px">
      <el-form-item label="计划名称" required>
        <el-input v-model="form.name" placeholder="请输入计划名称" />
      </el-form-item>

      <template v-if="formType === 'income_expense'">
        <el-form-item label="资金账户" required>
          <el-select v-model="form.account_id" placeholder="选择账户" style="width:100%">
            <el-option v-for="a in cashAccounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="收支项目" required>
          <el-select v-model="form.category_id" placeholder="选择收支项目" filterable style="width:100%">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额">
          <el-input v-model="form.amount" placeholder="0.00" />
        </el-form-item>
      </template>

      <template v-else-if="formType === 'transfer'">
        <el-form-item label="转出账户" required>
          <el-select v-model="form.account_id" placeholder="选择账户" style="width:100%">
            <el-option v-for="a in cashAccounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="转入账户" required>
          <el-select v-model="form.to_account_id" placeholder="选择账户" style="width:100%">
            <el-option v-for="a in cashAccounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额">
          <el-input v-model="form.amount" placeholder="0.00" />
        </el-form-item>
        <el-form-item label="手续费账户">
          <el-select v-model="form.fee_account_id" placeholder="默认从转出账户扣除" clearable style="width:100%">
            <el-option v-for="a in cashAccounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="手续费">
          <el-input v-model="form.fee" placeholder="0.00" />
        </el-form-item>
      </template>

      <template v-else-if="formType === 'fund_invest'">
        <el-form-item label="基金账户" required>
          <el-select v-model="form.account_id" placeholder="选择基金账户" style="width:100%">
            <el-option v-for="a in fundAccounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="资金账户" required>
          <el-select v-model="form.to_account_id" placeholder="选择扣款账户" style="width:100%">
            <el-option v-for="a in cashAccounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="申购基金" required>
          <el-select v-model="form.instrument_id" placeholder="选择基金" filterable style="width:100%" @change="onFundChange">
            <el-option v-for="i in fundOptions" :key="i.id" :label="i.name" :value="i.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="申购费率(%)">
          <el-input v-model="form.fee_rate" placeholder="0" />
        </el-form-item>
        <el-form-item label="申购定额">
          <el-input v-model="form.amount" placeholder="0.00" />
        </el-form-item>
      </template>

      <template v-else-if="formType === 'reminder'">
        <el-form-item label="提前提醒">
          <el-input-number v-model="form.remind_days" :min="0" /> <span class="hint">天</span>
        </el-form-item>
      </template>

      <el-form-item label="重复">
        <el-select v-model="form.frequency" style="width:100%">
          <el-option v-for="f in FREQ_OPTS" :key="f.v" :label="f.t" :value="f.v" />
        </el-select>
      </el-form-item>
      <el-form-item label="开始日期" required>
        <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
      </el-form-item>
      <el-form-item label="结束日期">
        <el-date-picker v-model="form.end_date" type="date" value-format="YYYY-MM-DD" clearable style="width:100%" />
      </el-form-item>

      <el-form-item v-if="formType !== 'reminder'" label="标签">
        <el-select v-model="form.tag_ids" multiple filterable placeholder="选择标签" style="width:100%">
          <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="formType !== 'reminder'" label="自动执行">
        <el-switch v-model="form.auto_execute" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="formVisible = false">取消</el-button>
      <el-button type="primary" @click="saveForm">保存</el-button>
    </template>
  </el-dialog>

  <!-- 执行 -->
  <el-dialog
    v-model="execVisible"
    :title="execIsP2p ? '执行计划 - 网贷收回' : '执行计划'"
    width="92%"
    style="max-width:560px"
    :close-on-click-modal="false"
    append-to-body
  >
    <el-form v-if="execPlan" label-width="110px">
      <template v-if="execIsP2p">
        <el-form-item label="网贷账户">
          <el-input :model-value="acctName(execLoan?.account_id)" disabled />
        </el-form-item>
        <el-form-item label="投资名称">
          <el-input :model-value="execLoan?.item || execLoan?.counterparty || ''" disabled />
        </el-form-item>
        <el-form-item label="本金">
          <el-input v-model="exec.principal" placeholder="0.00" />
        </el-form-item>
        <el-form-item label="利息">
          <el-input v-model="exec.interest" placeholder="0.00" />
        </el-form-item>
        <el-form-item label="收入账户">
          <el-select v-model="exec.to_account_id" placeholder="选择账户" style="width:100%">
            <el-option v-for="a in cashAccounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="本息合计">
          <el-input :model-value="execTotalPI" disabled />
        </el-form-item>
      </template>
      <template v-else>
        <el-form-item label="计划名称">
          <el-input :model-value="execPlan.name" disabled />
        </el-form-item>
        <el-form-item v-if="execPlan.plan_type !== 'reminder'" label="金额">
          <el-input v-model="exec.amount" placeholder="0.00" />
        </el-form-item>
      </template>

      <el-form-item v-if="execPlan.plan_type !== 'reminder'" label="标签">
        <el-select v-model="exec.tag_ids" multiple filterable placeholder="选择标签" style="width:100%">
          <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="exec.remark" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="日期">
        <el-date-picker v-model="exec.occurred_at" type="date" value-format="YYYY-MM-DD" style="width:100%" />
      </el-form-item>
      <el-form-item label-width="0">
        <el-checkbox v-model="exec.keep_open">下次执行该计划时，使用当前交易信息</el-checkbox>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="execVisible = false">取消</el-button>
      <el-button type="primary" @click="submitExec">立即入账</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.plan-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}
.hint {
  margin-left: 8px;
  color: #909399;
}
</style>
