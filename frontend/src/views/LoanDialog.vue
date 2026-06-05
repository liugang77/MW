<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useLoanStore } from '../stores/loan'
import type { Account, Tag, Party } from '../types'

const ledgerStore = useLedgerStore()
const loanStore = useLoanStore()

const accounts = ref<Account[]>([])
const tags = ref<Tag[]>([])
const parties = ref<Party[]>([])

const repayMethods = ['不定', '等额本息', '等额本金', '自由还款', '分期付息一次还本']
const installmentMethods = ['等额本息', '等额本金', '分期付息一次还本']
const termUnits = [
  { v: 'year', t: '年' },
  { v: 'month', t: '月' },
  { v: 'day', t: '日' }
]

const form = ref<any>({
  direction: 'payable', counterparty: '', item: '', currency: 'CNY', account_id: null,
  amount: 0, settled: 0, interest_rate: 0, total_periods: null, remaining_periods: null,
  repay_method: '等额本息', occurred_at: null, due_at: null, remark: '', tag_ids: [],
  first_collect_at: null, term_value: 1, term_unit: 'year',
  collect_interval: 1, collect_interval_unit: 'month', collected_periods: 0
})

const isPayable = computed(() => form.value.direction === 'payable')
const isInstallment = computed(() => installmentMethods.includes(form.value.repay_method))

const labels = computed(() => isPayable.value
  ? { who: '债权人', amount: '借入金额', method: '还款方式', account: '收入账户', hint: '比如“一般借款；买房贷款”，在返还时可以选择' }
  : { who: '债务人', amount: '借出金额', method: '收款方式', account: '支出账户', hint: '比如“一般借款；他要买房”，在收回时可以选择' }
)

const visible = computed({
  get: () => loanStore.visible,
  set: (v: boolean) => { if (!v) loanStore.close() }
})

function resetForm(dir: 'payable' | 'receivable') {
  form.value = {
    direction: dir, counterparty: '', item: '', currency: 'CNY', account_id: null,
    amount: 0, settled: 0, interest_rate: 0, total_periods: null, remaining_periods: null,
    repay_method: '等额本息', occurred_at: new Date().toISOString().slice(0, 10) + 'T00:00:00', due_at: null, remark: '', tag_ids: [],
    first_collect_at: new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10) + 'T00:00:00',
    term_value: 1, term_unit: 'year', collect_interval: 1, collect_interval_unit: 'month', collected_periods: 0
  }
}

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

async function loadRefs() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  tags.value = await api.listTags(lid)
  parties.value = await api.listParties(lid)
}

// 保证所选值在人员列表中；不在则新建一个联系人
async function ensureParty(name: string) {
  const lid = ledgerStore.currentId
  if (!lid || !name) return
  if (parties.value.some((p) => p.name === name)) return
  try {
    const created = await api.createParty(lid, { name, type: 'contact' })
    parties.value.push(created)
  } catch { /* 忽略重复或创建失败，不阻断主流程 */ }
}

async function save() {
  if (!form.value.counterparty) return ElMessage.warning('请输入债权人/债务人')
  if (!(Number(form.value.amount) > 0)) return ElMessage.warning('请输入借入/借出金额')

  await ensureParty(form.value.counterparty)

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

  await api.createLoan(ledgerStore.currentId as number, form.value)
  ElMessage.success('已创建')
  loanStore.markSaved()
}

watch(() => loanStore.visible, (v) => {
  if (v) {
    resetForm(loanStore.direction)
    loadRefs()
  }
})
</script>

<template>
  <el-dialog v-model="visible" :title="isPayable ? '借入' : '借出'" width="92%" style="max-width:760px">
    <el-form label-width="92px">
      <el-row :gutter="16">
        <el-col :span="12" :xs="24"><el-form-item :label="labels.who" required><el-select v-model="form.counterparty" filterable allow-create default-first-option :reserve-keyword="false" placeholder="选择或输入新增" style="width:100%"><el-option v-for="p in parties" :key="p.id" :label="p.name" :value="p.name" /></el-select></el-form-item></el-col>
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
      <el-button @click="loanStore.close()">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.dual-field { display: flex; gap: 8px; width: 100%; }
.dual-field .el-input { flex: 1 1 auto; }
</style>
