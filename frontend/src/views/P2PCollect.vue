<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useP2pStore } from '../stores/p2p'
import type { Account, Tag, Loan } from '../types'

const ledgerStore = useLedgerStore()
const p2pStore = useP2pStore()

const accounts = ref<Account[]>([])
const tags = ref<Tag[]>([])
const loans = ref<Loan[]>([])

const P2P_TYPES = ['p2p']
const CASH_TYPES = ['cash', 'bank', 'wallet', 'prepaid']
const p2pAccounts = computed(() => accounts.value.filter((a) => P2P_TYPES.includes(a.type)))
const incomeAccounts = computed(() => accounts.value.filter((a) => CASH_TYPES.includes(a.type) || P2P_TYPES.includes(a.type)))

// 表单
const p2pAccountId = ref<number | null>(null)
const loanId = ref<number | null>(null)
const principal = ref('')
const interest = ref('')
const incomeAccountId = ref<number | null>(null)
const tagIds = ref<number[]>([])
const remark = ref('')
const occurredAt = ref(new Date().toISOString().slice(0, 10))

const num = (v: string) => Number(v || 0)
const totalPI = computed(() => (num(principal.value) + num(interest.value)).toFixed(2))

// 该账户之前购买（借出）的网贷产品
const accountLoans = computed(() => {
  const editId = p2pStore.editCollect?.loanId
  return loans.value.filter(
    (l) =>
      l.loan_kind === 'p2p' &&
      l.account_id === p2pAccountId.value &&
      (!l.is_closed || l.id === editId)
  )
})

const dialogVisible = computed({
  get: () => p2pStore.visible && p2pStore.mode === 'collect',
  set: (v: boolean) => { if (!v) p2pStore.close() }
})

async function loadMeta() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  tags.value = await api.listTags(lid)
  loans.value = await api.listLoans(lid)
  if (p2pStore.presetAccountId && p2pAccounts.value.some((a) => a.id === p2pStore.presetAccountId)) {
    p2pAccountId.value = p2pStore.presetAccountId
  } else if (!p2pAccountId.value && p2pAccounts.value.length) {
    p2pAccountId.value = p2pAccounts.value[0].id
  }
  // 回款默认回到网贷账户的可用现金
  if (!incomeAccountId.value) incomeAccountId.value = p2pAccountId.value ?? (incomeAccounts.value[0]?.id ?? null)
  // 编辑模式：回填原收回明细
  if (p2pStore.editCollect) {
    const e = p2pStore.editCollect
    const l = loans.value.find((x) => x.id === e.loanId)
    applyingPreset.value = true
    if (l && l.account_id) p2pAccountId.value = l.account_id
    loanId.value = e.loanId
    principal.value = e.principal ? String(e.principal) : ''
    interest.value = e.interest ? String(e.interest) : ''
    incomeAccountId.value = e.incomeAccountId ?? p2pAccountId.value
    tagIds.value = e.tagIds ? [...e.tagIds] : []
    remark.value = e.remark || ''
    if (e.occurredAt) occurredAt.value = e.occurredAt.slice(0, 10)
    nextTick(() => { applyingPreset.value = false })
    return
  }
  // 从待收明细带入指定项目，并预填本金/利息
  if (p2pStore.presetLoanId && accountLoans.value.some((l) => l.id === p2pStore.presetLoanId)) {
    applyingPreset.value = true
    loanId.value = p2pStore.presetLoanId
    onLoanChange()
    nextTick(() => { applyingPreset.value = false })
  }
}

function reset() {
  loanId.value = null
  principal.value = ''
  interest.value = ''
  tagIds.value = []
  remark.value = ''
  occurredAt.value = new Date().toISOString().slice(0, 10)
}

// 选择投资名称后，默认带出剩余本金
function onLoanChange() {
  const l = accountLoans.value.find((x) => x.id === loanId.value)
  if (l) {
    principal.value = l.remaining || ''
    if (l.per_interest) interest.value = l.per_interest
  }
}

// 切换网贷账户时清空已选产品（应用预设时跳过）
const applyingPreset = ref(false)
watch(p2pAccountId, () => { if (!applyingPreset.value) loanId.value = null })

function validate(): boolean {
  if (!p2pAccountId.value) { ElMessage.warning('请选择网贷账户'); return false }
  if (!loanId.value) { ElMessage.warning('请选择投资名称'); return false }
  if (!(num(principal.value) + num(interest.value) > 0)) { ElMessage.warning('请输入本金或利息'); return false }
  if (!occurredAt.value) { ElMessage.warning('请选择日期'); return false }
  return true
}

async function submit(keepOpen: boolean) {
  if (!validate()) return
  await api.collectLoan(loanId.value as number, {
    income_account_id: incomeAccountId.value,
    principal: principal.value || 0,
    interest: interest.value || 0,
    occurred_at: occurredAt.value + 'T00:00:00',
    remark: remark.value || null,
    tag_ids: tagIds.value,
    ...(p2pStore.editCollect ? { edit_group: p2pStore.editCollect.group } : {})
  })
  ElMessage.success(p2pStore.editCollect ? '网贷收回已修改' : '网贷收回已记录')
  p2pStore.savedAt = Date.now()
  if (keepOpen && !p2pStore.editCollect) {
    reset()
    await loadMeta()
  } else {
    p2pStore.close()
  }
}

watch(() => p2pStore.visible, (v) => {
  if (v && p2pStore.mode === 'collect') { reset(); loadMeta() }
})
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    :title="p2pStore.editCollect ? '编辑网贷收回' : '网贷收回'"
    width="92%"
    style="max-width:680px"
    :close-on-click-modal="false"
  >
    <el-form label-width="90px" class="p2p-form">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="网贷账户" required>
            <el-select v-model="p2pAccountId" placeholder="选择网贷账户" style="width:100%">
              <el-option v-for="a in p2pAccounts" :key="a.id" :label="a.name" :value="a.id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="投资名称" required>
            <el-select
              v-model="loanId"
              filterable
              placeholder="在此处输入文字以进行过滤"
              style="width:100%"
              @change="onLoanChange"
            >
              <el-option v-for="l in accountLoans" :key="l.id" :label="l.item || l.counterparty" :value="l.id" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="本金">
            <el-input v-model="principal" type="number" placeholder="0.00" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="利息">
            <el-input v-model="interest" type="number" placeholder="0.00" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="收入账户">
            <el-select v-model="incomeAccountId" placeholder="选择收入账户" style="width:100%">
              <el-option v-for="a in incomeAccounts" :key="a.id" :label="a.name" :value="a.id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="本息合计">
            <el-input :model-value="totalPI" readonly />
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

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="日期" required>
            <el-date-picker v-model="occurredAt" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <template #footer>
      <el-button @click="submit(true)">保存并继续</el-button>
      <el-button type="primary" @click="submit(false)">确定</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.p2p-form :deep(input[readonly]) {
  background: #f5f7fa;
}
</style>
