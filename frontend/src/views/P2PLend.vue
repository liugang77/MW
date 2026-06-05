<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useP2pStore } from '../stores/p2p'
import type { Account, Tag } from '../types'

const ledgerStore = useLedgerStore()
const p2pStore = useP2pStore()

const accounts = ref<Account[]>([])
const tags = ref<Tag[]>([])

// 网贷账户类型 p2p；出借资金从网贷账户自身可用现金扣除（需先转账充值进该账户）
const P2P_TYPES = ['p2p']
const p2pAccounts = computed(() => accounts.value.filter((a) => P2P_TYPES.includes(a.type)))

const repayMethods = [
  '分期付息一次还本', '等额本息', '等额本金', '先息后本', '到期还本付息', '一次性还本付息'
]
const interestMethods = [
  '按月|年利率按360天计算', '按月|年利率按365天计算', '按日|年利率按360天计算', '按日|年利率按365天计算'
]
const unitOptions = [
  { v: 'day', t: '日' }, { v: 'month', t: '月' }, { v: 'year', t: '年' }
]

// 表单
const p2pAccountId = ref<number | null>(null)
const cashAccountId = ref<number | null>(null)
const name = ref('')
const amount = ref('')
const repayMethod = ref(repayMethods[0])
const annualRate = ref('')
const interestMethod = ref(interestMethods[0])
const mgmtFeeRate = ref('')
const termValue = ref('')
const termUnit = ref('month')
const collectInterval = ref('1')
const collectIntervalUnit = ref('month')
const totalPeriods = ref('')
const collectedPeriods = ref('0')
const perInterest = ref('')
const remainingPI = ref('')
const tagIds = ref<number[]>([])
const remark = ref('')
const occurredAt = ref(new Date().toISOString().slice(0, 10))
const firstCollectAt = ref('')
const autoExecute = ref(false)

const num = (v: string) => Number(v || 0)
const round2 = (n: number) => Math.round(n * 100) / 100

// 计息天数基数
const dayBase = computed(() => (interestMethod.value.includes('365') ? 365 : 360))

// 每期间隔折算的月数（用于估算每期利息）
const intervalMonths = computed(() => {
  const v = num(collectInterval.value)
  if (collectIntervalUnit.value === 'year') return v * 12
  if (collectIntervalUnit.value === 'day') return v / 30
  return v
})

// 估算每期还息与剩余本息
function recalc() {
  const principal = num(amount.value)
  const rate = num(annualRate.value) / 100
  const months = intervalMonths.value
  // 按年利率换算到每期：principal * rate * (天数 / 基数)
  const days = collectIntervalUnit.value === 'day'
    ? num(collectInterval.value)
    : months * (dayBase.value / 12)
  const interest = round2(principal * rate * (days / dayBase.value))
  perInterest.value = interest ? String(interest) : '0.00'
  const remainPeriods = Math.max(num(totalPeriods.value) - num(collectedPeriods.value), 0)
  remainingPI.value = String(round2(principal + interest * remainPeriods))
}

watch([amount, annualRate, collectInterval, collectIntervalUnit, totalPeriods, collectedPeriods, interestMethod], recalc)
// 出借资金始终来自所选网贷账户
watch(p2pAccountId, (v) => { cashAccountId.value = v })

async function loadMeta() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  tags.value = await api.listTags(lid)
  if (p2pStore.presetAccountId && p2pAccounts.value.some((a) => a.id === p2pStore.presetAccountId)) {
    p2pAccountId.value = p2pStore.presetAccountId
  } else if (!p2pAccountId.value && p2pAccounts.value.length) {
    p2pAccountId.value = p2pAccounts.value[0].id
  }
  cashAccountId.value = p2pAccountId.value
}

// 编辑模式：从原网贷项目回填表单
function prefillEdit() {
  const l = p2pStore.editLoan
  if (!l) return
  p2pAccountId.value = l.account_id ?? p2pAccountId.value
  cashAccountId.value = p2pAccountId.value
  name.value = l.item || l.counterparty || ''
  amount.value = l.amount != null ? String(l.amount) : ''
  repayMethod.value = l.repay_method || repayMethods[0]
  annualRate.value = l.interest_rate != null ? String(l.interest_rate) : ''
  interestMethod.value = l.interest_method || interestMethods[0]
  mgmtFeeRate.value = l.mgmt_fee_rate != null ? String(l.mgmt_fee_rate) : ''
  termValue.value = l.term_value != null ? String(l.term_value) : ''
  termUnit.value = l.term_unit || 'month'
  collectInterval.value = l.collect_interval != null ? String(l.collect_interval) : '1'
  collectIntervalUnit.value = l.collect_interval_unit || 'month'
  totalPeriods.value = l.total_periods != null ? String(l.total_periods) : ''
  collectedPeriods.value = l.collected_periods != null ? String(l.collected_periods) : '0'
  tagIds.value = l.tag_ids ? [...l.tag_ids] : []
  remark.value = l.remark || ''
  if (l.occurred_at) occurredAt.value = l.occurred_at.slice(0, 10)
  if (l.first_collect_at) firstCollectAt.value = l.first_collect_at.slice(0, 10)
  autoExecute.value = !!l.auto_execute
  recalc()
}
function reset() {
  name.value = ''
  amount.value = ''
  repayMethod.value = repayMethods[0]
  annualRate.value = ''
  interestMethod.value = interestMethods[0]
  mgmtFeeRate.value = ''
  termValue.value = ''
  termUnit.value = 'month'
  collectInterval.value = '1'
  collectIntervalUnit.value = 'month'
  totalPeriods.value = ''
  collectedPeriods.value = '0'
  perInterest.value = '0.00'
  remainingPI.value = '0.00'
  tagIds.value = []
  remark.value = ''
  autoExecute.value = false
  occurredAt.value = new Date().toISOString().slice(0, 10)
  firstCollectAt.value = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10)
}

function validate(): boolean {
  if (!p2pAccountId.value) { ElMessage.warning('请选择网贷账户'); return false }
  if (!name.value.trim()) { ElMessage.warning('请输入投资名称'); return false }
  if (!(num(amount.value) > 0)) { ElMessage.warning('请输入借出金额'); return false }
  if (!(num(annualRate.value) >= 0)) { ElMessage.warning('请输入年利率'); return false }
  if (!(num(totalPeriods.value) > 0)) { ElMessage.warning('请输入收款总期数'); return false }
  if (!occurredAt.value) { ElMessage.warning('请选择投资计息日'); return false }
  if (!firstCollectAt.value) { ElMessage.warning('请选择首次收款日'); return false }
  return true
}

function buildPayload() {
  return {
    direction: 'receivable',
    loan_kind: 'p2p',
    counterparty: name.value.trim(),
    item: name.value.trim(),
    currency: 'CNY',
    account_id: p2pAccountId.value,
    cash_account_id: cashAccountId.value,
    amount: amount.value || 0,
    settled: 0,
    interest_rate: annualRate.value || 0,
    repay_method: repayMethod.value,
    interest_method: interestMethod.value,
    mgmt_fee_rate: mgmtFeeRate.value || 0,
    term_value: termValue.value !== '' ? Number(termValue.value) : null,
    term_unit: termUnit.value,
    collect_interval: collectInterval.value !== '' ? Number(collectInterval.value) : null,
    collect_interval_unit: collectIntervalUnit.value,
    total_periods: Number(totalPeriods.value),
    remaining_periods: Math.max(num(totalPeriods.value) - num(collectedPeriods.value), 0),
    collected_periods: Number(collectedPeriods.value || 0),
    per_interest: perInterest.value || 0,
    remaining_principal_interest: remainingPI.value || 0,
    occurred_at: occurredAt.value + 'T00:00:00',
    first_collect_at: firstCollectAt.value + 'T00:00:00',
    auto_execute: autoExecute.value,
    remark: remark.value || null,
    tag_ids: tagIds.value,
    ...(p2pStore.editLoan ? { edit_loan_id: p2pStore.editLoan.id } : {})
  }
}

async function submit(keepOpen: boolean) {
  if (!validate()) return
  const lid = ledgerStore.currentId as number
  await api.createLoan(lid, buildPayload())
  ElMessage.success(p2pStore.editLoan ? '网贷借出已修改' : '网贷借出已记录')
  p2pStore.savedAt = Date.now()
  if (keepOpen && !p2pStore.editLoan) {
    reset()
  } else {
    p2pStore.close()
  }
}

watch(() => p2pStore.visible, (v) => {
  if (v && p2pStore.mode === 'lend') {
    reset()
    loadMeta().then(() => { if (p2pStore.editLoan) prefillEdit() })
  }
})

const dialogVisible = computed({
  get: () => p2pStore.visible && p2pStore.mode === 'lend',
  set: (v: boolean) => { if (!v) p2pStore.close() }
})
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    :title="p2pStore.editLoan ? '编辑网贷借出' : '网贷借出'"
    width="92%"
    style="max-width:780px"
    :close-on-click-modal="false"
  >
    <el-form label-width="100px" class="p2p-form">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="网贷账户" required>
            <el-select v-model="p2pAccountId" placeholder="选择网贷账户" style="width:100%">
              <el-option v-for="a in p2pAccounts" :key="a.id" :label="a.name" :value="a.id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="资金来源">
            <el-input model-value="网贷账户可用余额" disabled />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="投资名称" required>
            <el-input v-model="name" placeholder="请输入投资名称" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="借出金额" required>
            <el-input v-model="amount" type="number" placeholder="0.00" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="收款方式">
            <el-select v-model="repayMethod" style="width:100%">
              <el-option v-for="m in repayMethods" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="年利率(%)" required>
            <el-input v-model="annualRate" type="number" placeholder="0.00" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="计息方式">
            <el-select v-model="interestMethod" style="width:100%">
              <el-option v-for="m in interestMethods" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="管理费率(%)">
            <el-input v-model="mgmtFeeRate" type="number" placeholder="0.00" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="借出期限" required>
            <div class="term-row">
              <el-input v-model="termValue" type="number" placeholder="0" />
              <el-select v-model="termUnit" style="width:90px">
                <el-option v-for="u in unitOptions" :key="u.v" :label="u.t" :value="u.v" />
              </el-select>
            </div>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="收款间隔" required>
            <div class="term-row">
              <el-input v-model="collectInterval" type="number" placeholder="1" />
              <el-select v-model="collectIntervalUnit" style="width:90px">
                <el-option v-for="u in unitOptions" :key="u.v" :label="u.t" :value="u.v" />
              </el-select>
            </div>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="收款总期数" required>
            <el-input v-model="totalPeriods" type="number" placeholder="0" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="已收款期数">
            <el-input v-model="collectedPeriods" type="number" placeholder="0" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="每期还息">
            <el-input v-model="perInterest" type="number" readonly />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="剩余本息">
            <el-input v-model="remainingPI" type="number" readonly />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="投资计息日" required>
            <el-date-picker v-model="occurredAt" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="首次收款日" required>
            <el-date-picker v-model="firstCollectAt" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="标签">
            <el-select v-model="tagIds" multiple filterable placeholder="选择标签" style="width:100%">
              <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="备注">
            <el-input v-model="remark" placeholder="请输入备注" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <template #footer>
      <div class="p2p-footer">
        <el-checkbox v-model="autoExecute">收款计划到期自动执行</el-checkbox>
        <div class="footer-spacer" />
        <el-button @click="submit(true)">保存并继续</el-button>
        <el-button type="primary" @click="submit(false)">确定</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.p2p-form :deep(input[readonly]) {
  background: #f5f7fa;
}

.term-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.p2p-footer {
  display: flex;
  align-items: center;
  width: 100%;
}

.footer-spacer {
  flex: 1;
}
</style>
