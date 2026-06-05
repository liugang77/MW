<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import type { Account, Party, InsuranceDetail } from '../types'
import { fmtMoney } from '../utils/format'

const route = useRoute()
const router = useRouter()
const ledgerStore = useLedgerStore()

const accounts = ref<Account[]>([])
const parties = ref<Party[]>([])
const selectedPerson = ref<string>('')
const selectedAccountId = ref<number | null>(null)
const activeTab = ref<'trades' | 'cash' | 'overview'>('trades')

const fmt = (v: string | number | null | undefined) => fmtMoney(v)

const insuranceAccounts = computed(() => accounts.value.filter((a) => a.type === 'insurance'))

// 所有人列表（保险按投保人/所有人分组）
const persons = computed(() => {
  const set = new Set<string>()
  for (const a of insuranceAccounts.value) set.add(a.insured_person || '未指定')
  return Array.from(set)
})

// 当前所有人的保险项目（可能多个）
const items = computed(() =>
  insuranceAccounts.value.filter((a) => (a.insured_person || '未指定') === selectedPerson.value)
)

const balanceOf = (person: string) =>
  insuranceAccounts.value
    .filter((a) => (a.insured_person || '未指定') === person)
    .reduce((s, a) => s + Number(a.current_balance || 0), 0)

const selectedAccount = computed(() =>
  insuranceAccounts.value.find((a) => a.id === selectedAccountId.value) || null
)

// 选中条目的明细由后台计算（缴费/领取分类与汇总）
const detail = ref<InsuranceDetail | null>(null)

async function loadDetail() {
  if (!selectedAccountId.value) {
    detail.value = null
    return
  }
  detail.value = await api.insuranceDetail(selectedAccountId.value)
}

// ============ 记账：保险活动（缴纳保费 / 保费返还 / 退保 / 保险分红）============
// 缴纳保费为资金流入（现金价值增加），其余三种为领取方向（现金价值减少）
const INS_ACTIVITIES = ['缴纳保费', '保费返还', '退保', '保险分红'] as const

// 缴费/收款账户：现金储蓄类活跃账户
const fundingAccounts = computed(() =>
  accounts.value.filter(
    (a) => ['cash', 'bank', 'wallet', 'prepaid'].includes(a.type) && (a.status || 'active') === 'active'
  )
)

const recordDialog = ref(false)
const savingRecord = ref(false)
const recordForm = reactive({
  activity: '缴纳保费' as string,
  occurred_at: new Date().toISOString().slice(0, 10),
  amount: null as number | null,
  counter_account_id: null as number | null,
  remark: '',
})
const recordIsIn = computed(() => recordForm.activity === '缴纳保费')
const counterLabel = computed(() => (recordForm.activity === '缴纳保费' ? '缴费账户' : '领取账户'))

function openRecord(activity: string) {
  if (!selectedAccount.value) {
    ElMessage.warning('请先选择保险项目')
    return
  }
  recordForm.activity = activity
  recordForm.occurred_at = new Date().toISOString().slice(0, 10)
  recordForm.amount = null
  recordForm.counter_account_id = null
  recordForm.remark = ''
  recordDialog.value = true
}

async function submitRecord() {
  const lid = ledgerStore.currentId
  if (!lid || !selectedAccount.value) return
  const amt = Number(recordForm.amount)
  if (!amt || amt <= 0) {
    ElMessage.warning('请输入金额')
    return
  }
  if (!recordForm.counter_account_id) {
    ElMessage.warning(recordIsIn.value ? '请选择缴费账户' : '请选择领取账户')
    return
  }
  savingRecord.value = true
  try {
    const insId = selectedAccount.value.id
    const counter = recordForm.counter_account_id
    await api.createTransaction(lid, {
      type: 'transfer',
      amount: amt.toFixed(2),
      account_id: recordIsIn.value ? counter : insId,
      to_account_id: recordIsIn.value ? insId : counter,
      occurred_at: recordForm.occurred_at,
      remark: recordForm.remark || recordForm.activity,
      insurance_activity: recordForm.activity,
    })
    ElMessage.success('已记账')
    recordDialog.value = false
    await load()
    await loadDetail()
    router.replace({ path: '/insurance', query: { account_id: String(insId), _t: String(Date.now()) } })
  } finally {
    savingRecord.value = false
  }
}

function selectItem(row: Account) {
  selectedAccountId.value = row.id
}
function itemRowClass({ row }: { row: Account }) {
  return row.id === selectedAccountId.value ? 'cur-row' : ''
}

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  await loadParties()
  syncSelection()
}

// 参保人来自“人员与机构”（家庭成员 / 往来人员，不含机构）
async function loadParties() {
  const lid = ledgerStore.currentId
  if (!lid) return
  const all = await api.listParties(lid)
  parties.value = all.filter((p) => p.type !== 'org')
}

// 可选参保人 = 人员与机构中的人 ∪ 已有保险的参保人
const personOptions = computed(() => {
  const set = new Set<string>()
  for (const p of parties.value) set.add(p.name)
  for (const a of insuranceAccounts.value) if (a.insured_person) set.add(a.insured_person)
  return Array.from(set)
})

function syncSelection() {
  const person = route.query.person ? String(route.query.person) : ''
  if (person && persons.value.includes(person)) {
    selectedPerson.value = person
    if (!items.value.some((a) => a.id === selectedAccountId.value)) {
      selectedAccountId.value = items.value.length ? items.value[0].id : null
    }
    return
  }
  const qid = Number(route.query.account_id)
  if (qid && insuranceAccounts.value.some((a) => a.id === qid)) {
    const acc = insuranceAccounts.value.find((a) => a.id === qid)!
    selectedPerson.value = acc.insured_person || '未指定'
    selectedAccountId.value = qid
    return
  }
  if (!selectedPerson.value && persons.value.length) selectedPerson.value = persons.value[0]
  if (!items.value.some((a) => a.id === selectedAccountId.value)) {
    selectedAccountId.value = items.value.length ? items.value[0].id : null
  }
}

watch(selectedPerson, () => {
  if (!items.value.some((a) => a.id === selectedAccountId.value)) {
    selectedAccountId.value = items.value.length ? items.value[0].id : null
  }
})

watch(() => [route.query.account_id, route.query.person], syncSelection)

watch(selectedAccountId, loadDetail, { immediate: true })

// ============ 新建社保向导 ============
interface XiangZhong { key: string; name: string; short: string }
const XIANZHONG: XiangZhong[] = [
  { key: 'pension', name: '养老保险', short: '养老' },
  { key: 'injury', name: '工伤保险', short: '工伤' },
  { key: 'unemployment', name: '失业保险', short: '失业' },
  { key: 'medical', name: '医疗保险', short: '医疗' },
  { key: 'maternity', name: '生育保险', short: '生育' },
  { key: 'fund', name: '住房公积金', short: '住房公积金' },
]

const wizardVisible = ref(false)
const wizardStep = ref(1)
const saving = ref(false)
const wizard = reactive({
  insured_person: '',
  social_code: '',
  city: '',
  record_date: new Date().toISOString().slice(0, 10),
  items: {} as Record<string, { checked: boolean; balance: number | null }>,
})

function resetWizard() {
  wizardStep.value = 1
  wizard.insured_person = ''
  wizard.social_code = ''
  wizard.city = ''
  wizard.record_date = new Date().toISOString().slice(0, 10)
  const m: Record<string, { checked: boolean; balance: number | null }> = {}
  for (const x of XIANZHONG) m[x.key] = { checked: false, balance: null }
  wizard.items = m
}

function openWizard() {
  resetWizard()
  if (selectedPerson.value && selectedPerson.value !== '未指定') {
    wizard.insured_person = selectedPerson.value
  }
  wizardVisible.value = true
}

// 该参保人已创建的险种名称集合（用于禁用并标注“已创建”）
function isCreated(name: string) {
  const person = wizard.insured_person || ''
  if (!person) return false
  return insuranceAccounts.value.some(
    (a) => (a.insured_person || '') === person && a.name === name
  )
}

function nextStep() {
  if (!wizard.insured_person.trim()) {
    ElMessage.warning('请填写参保人')
    return
  }
  wizardStep.value = 2
}

const checkedCount = computed(
  () => XIANZHONG.filter((x) => wizard.items[x.key]?.checked && !isCreated(x.name)).length
)

async function finishWizard() {
  const lid = ledgerStore.currentId
  if (!lid) return
  const picks = XIANZHONG.filter((x) => wizard.items[x.key]?.checked && !isCreated(x.name))
  if (!picks.length) {
    ElMessage.warning('下面至少选择一项')
    return
  }
  saving.value = true
  try {
    const person = wizard.insured_person.trim()
    // 参保人与“人员与机构”关联：若为新参保人，则同步新增一名家庭成员
    if (person && !parties.value.some((p) => p.name === person)) {
      const np = await api.createParty(lid, { name: person, type: 'member' } as Partial<Party>)
      parties.value.push(np)
    }
    for (const x of picks) {
      // 账户初始余额为 0，期初余额通过「余额调整」交易体现，
      // 保证“余额=交易明细累计”
      const acc = await api.createAccount(lid, {
        name: x.name,
        type: 'insurance',
        icon: '🛡️',
        insured_person: person,
        social_code: wizard.social_code.trim() || null,
        city: wizard.city.trim() || null,
        start_date: wizard.record_date || null,
        initial_balance: '0',
        include_in_net: true,
      } as Partial<Account>)
      const opening = Number(wizard.items[x.key].balance ?? 0)
      if (opening !== 0) {
        await api.adjustAccount(acc.id, opening, 'adjust')
      }
    }
    ElMessage.success(`已创建 ${picks.length} 项社保`)
    wizardVisible.value = false
    await load()
    if (persons.value.includes(person)) {
      selectedPerson.value = person
      selectedAccountId.value = items.value.length ? items.value[0].id : null
    }
    // 触发左下账户列表刷新（App 监听 route.fullPath）
    router.replace({ path: '/insurance', query: { person, _t: String(Date.now()) } })
  } finally {
    saving.value = false
  }
}

onMounted(load)
watch(() => ledgerStore.currentId, load)
</script>

<template>
  <div class="ins-page">
    <!-- 上方：所有人的保险项目 -->
    <div class="panel">
      <div class="panel-head">
        <span class="panel-title">{{ selectedPerson || '保险' }}的保险</span>
      </div>

      <el-table
        :data="items"
        size="small"
        border
        :row-class-name="itemRowClass"
        @row-click="selectItem"
      >
        <el-table-column label="名称" min-width="200" fixed="left">
          <template #default="{ row }"><span style="font-weight:600">{{ row.name }}</span></template>
        </el-table-column>
        <el-table-column label="余额" align="right" min-width="140">
          <template #default="{ row }">{{ fmt(row.current_balance) }}</template>
        </el-table-column>
        <el-table-column label="备注" min-width="220">
          <template #default="{ row }">{{ row.remark }}</template>
        </el-table-column>
        <template #empty>该所有人暂无保险项目</template>
      </el-table>
    </div>

    <!-- 下方：选中保险项目的明细 -->
    <div class="panel">
      <!-- 操作按钮：交易明细标签下显示 -->
      <div class="tab-actions">
        <template v-if="activeTab === 'trades'">
          <el-button v-for="a in INS_ACTIVITIES" :key="a" size="small" @click="openRecord(a)">{{ a }}</el-button>
        </template>
      </div>
      <div class="tabs">
        <span class="tab" :class="{ active: activeTab === 'trades' }" @click="activeTab = 'trades'">交易明细</span>
        <span class="tab" :class="{ active: activeTab === 'cash' }" @click="activeTab = 'cash'">现金价值</span>
        <span class="tab" :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">账户概况</span>
      </div>

      <!-- 交易明细 -->
      <template v-if="activeTab === 'trades'">
        <el-table :data="detail?.rows || []" size="small" border>
          <el-table-column label="日期" min-width="120">
            <template #default="{ row }">{{ (row.occurred_at || '').slice(0, 10) }}</template>
          </el-table-column>
          <el-table-column label="缴费" align="right" min-width="110">
            <template #default="{ row }">
              <span v-if="Number(row.premium)" class="income">{{ fmt(row.premium) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="领取" align="right" min-width="110">
            <template #default="{ row }">
              <span v-if="Number(row.collect)" class="expense">{{ fmt(row.collect) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="活动类型" min-width="120">
            <template #default="{ row }">{{ row.activity }}</template>
          </el-table-column>
          <el-table-column label="备注" min-width="220">
            <template #default="{ row }">{{ row.remark }}</template>
          </el-table-column>
          <template #empty>暂无交易明细</template>
        </el-table>
        <div class="ins-summary">
          <div class="sum-item"><span class="lbl">现金价值</span><span class="val">{{ fmt(detail?.cash_value) }}</span></div>
          <div class="sum-item"><span class="lbl">缴费总额</span><span class="val income">{{ fmt(detail?.premium_total) }}</span></div>
          <div class="sum-item"><span class="lbl">领取总额</span><span class="val expense">{{ fmt(detail?.collect_total) }}</span></div>
          <div class="sum-item"><span class="lbl">记录数</span><span class="val">{{ detail?.count || 0 }}</span></div>
        </div>
      </template>

      <!-- 现金价值 -->
      <template v-else-if="activeTab === 'cash'">
        <el-empty :description="selectedAccount ? `当前现金价值 ${fmt(selectedAccount.current_balance)}` : '暂无数据'" />
      </template>

      <!-- 账户概况 -->
      <template v-else>
        <el-descriptions v-if="selectedAccount" :column="2" border size="small">
          <el-descriptions-item label="保险名称">{{ selectedAccount.name }}</el-descriptions-item>
          <el-descriptions-item label="所有人">{{ selectedAccount.insured_person || '未指定' }}</el-descriptions-item>
          <el-descriptions-item label="余额">{{ fmt(selectedAccount.current_balance) }}</el-descriptions-item>
          <el-descriptions-item label="期初余额">{{ fmt(selectedAccount.initial_balance) }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ selectedAccount.remark || '—' }}</el-descriptions-item>
        </el-descriptions>
        <el-empty v-else description="暂无数据" />
      </template>
    </div>

    <!-- 新建社保向导 -->
    <el-dialog
      v-model="wizardVisible"
      title="社保账户"
      width="560px"
      :close-on-click-modal="false"
      class="ins-wizard"
    >
      <p class="wiz-intro">
        国家立法规定的强制性社会保险体系，包含养老保险、工伤保险、失业保险、医疗保险、生育保险及住房公积金六大类别，共同构建起全面的社会保障网络。
      </p>

      <!-- 第一步：参保人 / 社保编号 / 城市 -->
      <el-form v-if="wizardStep === 1" label-width="90px" class="wiz-form">
        <el-form-item label="参保人" required>
          <el-select
            v-model="wizard.insured_person"
            filterable
            allow-create
            default-first-option
            placeholder="在此处输入文字以进行过滤"
            style="width: 100%"
          >
            <el-option v-for="p in personOptions" :key="p" :label="p" :value="p" />
          </el-select>
          <span class="wiz-link-hint">参保人来自“人员与机构”，新参保人将自动加入家庭成员</span>
        </el-form-item>
        <el-form-item label="社保编号">
          <el-input v-model="wizard.social_code" placeholder="选填" />
        </el-form-item>
        <el-form-item label="城市">
          <el-input v-model="wizard.city" placeholder="选填" />
        </el-form-item>
        <p class="wiz-tip">
          提示：保险缴费与领取款项独立于日常收支统计之外，同时保险资产价值将根据保险账户的余额计算。
        </p>
      </el-form>

      <!-- 第二步：记账日期 + 险种 -->
      <el-form v-else label-width="90px" class="wiz-form">
        <el-form-item label="记账日期">
          <el-date-picker
            v-model="wizard.record_date"
            type="date"
            value-format="YYYY-MM-DD"
            style="width: 220px"
          />
        </el-form-item>
        <div class="wiz-xz-box">
          <div class="wiz-xz-title">下面至少选择一项</div>
          <div v-for="x in XIANZHONG" :key="x.key" class="wiz-xz-row">
            <el-checkbox
              v-model="wizard.items[x.key].checked"
              :disabled="isCreated(x.name)"
            >
              {{ x.short }}<span v-if="isCreated(x.name)" class="created-tag">（已创建）</span>
            </el-checkbox>
            <el-input-number
              v-if="wizard.items[x.key].checked && !isCreated(x.name)"
              v-model="wizard.items[x.key].balance"
              :controls="false"
              :precision="2"
              placeholder="记账日余额"
              class="wiz-xz-amt"
            />
          </div>
        </div>
      </el-form>

      <template #footer>
        <el-button v-if="wizardStep === 2" @click="wizardStep = 1">&lt; 上一步</el-button>
        <el-button v-if="wizardStep === 1" type="primary" @click="nextStep">下一步 &gt;</el-button>
        <el-button
          v-else
          type="success"
          :loading="saving"
          :disabled="checkedCount === 0"
          @click="finishWizard"
        >完成</el-button>
      </template>
    </el-dialog>

    <!-- 记账：缴纳保费 / 保费返还 / 退保 / 保险分红 -->
    <el-dialog v-model="recordDialog" :title="recordForm.activity" width="440px" append-to-body>
      <el-form label-width="92px" class="wiz-form">
        <el-form-item label="保险账户">
          <span>{{ selectedAccount?.name }}</span>
        </el-form-item>
        <el-form-item :label="counterLabel" required>
          <el-select v-model="recordForm.counter_account_id" filterable placeholder="请选择账户" style="width: 220px">
            <el-option v-for="a in fundingAccounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额" required>
          <el-input-number v-model="recordForm.amount" :controls="false" :precision="2" :min="0" style="width: 220px" placeholder="请输入金额" />
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="recordForm.occurred_at" type="date" value-format="YYYY-MM-DD" style="width: 220px" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="recordForm.remark" placeholder="选填" />
        </el-form-item>
        <p class="wiz-tip">
          {{ recordIsIn ? '缴纳保费将增加保险现金价值，并从缴费账户转出，不计入日常收支。' : '该笔款项将减少保险现金价值并转入领取账户，不计入日常收支。' }}
        </p>
      </el-form>
      <template #footer>
        <el-button @click="recordDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingRecord" @click="submitRecord">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.ins-page { padding: 12px 16px; display: flex; flex-direction: column; gap: 14px; }
.panel { background: #fff; border: 1px solid #ebeef2; border-radius: 8px; padding: 12px 14px; }
.panel-head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.panel-title { font-size: 16px; font-weight: 600; color: #3c4b59; }
.person-select { width: 200px; margin-left: auto; }
.tabs { display: flex; align-items: center; gap: 18px; margin-bottom: 10px; border-bottom: 1px solid #f2f4f6; }
.tab { padding: 6px 2px; font-size: 14px; color: #909399; cursor: pointer; border-bottom: 2px solid transparent; }
.tab.active { color: #409eff; border-bottom-color: #409eff; font-weight: 600; }
.tab-actions { display: flex; justify-content: flex-end; gap: 8px; align-items: center; min-height: 32px; margin-bottom: 8px; }
.ins-summary { display: flex; flex-wrap: wrap; gap: 28px; margin-top: 12px; padding: 10px 16px; background: #f7f8fa; border-radius: 6px; }
.sum-item { display: flex; flex-direction: column; gap: 2px; }
.sum-item .lbl { font-size: 12px; color: #909399; }
.sum-item .val { font-size: 15px; font-weight: 600; color: #3c4b59; }
.income { color: #67c23a; }
.expense { color: #f56c6c; }
:deep(.cur-row) { background: #ecf5ff !important; }
:deep(.el-table__row) { cursor: pointer; }
.wiz-intro { margin: 0 0 16px; font-size: 13px; line-height: 1.7; color: #606266; text-indent: 2em; }
.wiz-form { padding: 0 4px; }
.wiz-tip { margin: 14px 0 0; font-size: 12px; line-height: 1.6; color: #67c23a; text-indent: 2em; }
.wiz-xz-box { margin-top: 4px; border: 1px solid #ebeef2; border-radius: 6px; padding: 14px 18px; }
.wiz-xz-title { font-size: 13px; color: #909399; margin-bottom: 10px; }
.wiz-xz-row { display: flex; align-items: center; gap: 16px; min-height: 40px; }
.wiz-xz-amt { width: 160px; }
.created-tag { color: #c0c4cc; font-size: 12px; }
.wiz-link-hint { display: block; margin-top: 4px; font-size: 12px; color: #909399; }
</style>
