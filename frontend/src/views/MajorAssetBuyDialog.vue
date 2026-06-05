<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { fmtMoney } from '../utils/format'
import { useLedgerStore } from '../stores/ledger'
import { useLoanStore } from '../stores/loan'
import { useMajorAssetStore } from '../stores/majorAsset'
import type { Account, Loan, Party, Tag } from '../types'

const ledgerStore = useLedgerStore()
const loanStore = useLoanStore()
const majorAssetStore = useMajorAssetStore()

const accounts = ref<Account[]>([])
const loans = ref<Loan[]>([])
const parties = ref<Party[]>([])
const tags = ref<Tag[]>([])
const saving = ref(false)

const fmt = (v: string | number) => fmtMoney(v)

const FUNDING_TYPES = ['cash', 'bank', 'wallet', 'prepaid']
const fundingAccounts = computed(() => accounts.value.filter((a) => FUNDING_TYPES.includes(a.type)))
const payableLoans = computed(() => loans.value.filter((l) => l.direction === 'payable' && !l.is_closed))

const visible = computed({
  get: () => majorAssetStore.visible,
  set: (v: boolean) => { if (!v) majorAssetStore.close() }
})

const form = reactive<{
  name: string
  owner: string
  total: number | null
  currency: string
  asset_nature: 'invest' | 'own'
  payment_account_id: number | null
  has_loan: boolean
  selected_loan_ids: number[]
  tag_ids: number[]
  remark: string
  occurred_at: string
}>({
  name: '', owner: '', total: null, currency: 'CNY', asset_nature: 'invest',
  payment_account_id: null, has_loan: false, selected_loan_ids: [],
  tag_ids: [], remark: '', occurred_at: new Date().toISOString().slice(0, 10)
})

const selectedLoanTotal = computed(() =>
  payableLoans.value
    .filter((l) => form.selected_loan_ids.includes(l.id))
    .reduce((s, l) => s + Number(l.amount || 0), 0)
)
const downPayment = computed(() => Math.max(Number(form.total || 0) - selectedLoanTotal.value, 0))

function toggleLoan(id: number, checked: boolean) {
  if (checked) {
    if (!form.selected_loan_ids.includes(id)) form.selected_loan_ids.push(id)
  } else {
    form.selected_loan_ids = form.selected_loan_ids.filter((x) => x !== id)
  }
}

// 点「新增贷款」：打开全局借入弹窗；保存后回到本窗口并自动选中新贷款
const loanIdsBeforeAdd = ref<number[]>([])
function addLoan() {
  loanIdsBeforeAdd.value = loans.value.map((l) => l.id)
  loanStore.open('payable')
}
watch(() => loanStore.savedAt, async () => {
  if (!majorAssetStore.visible) return
  const lid = ledgerStore.currentId
  if (!lid) return
  loans.value = await api.listLoans(lid)
  const added = loans.value.filter(
    (l) => l.direction === 'payable' && !loanIdsBeforeAdd.value.includes(l.id)
  )
  for (const l of added) {
    if (!form.selected_loan_ids.includes(l.id)) form.selected_loan_ids.push(l.id)
  }
  if (added.length) form.has_loan = true
})

async function loadRefs() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  loans.value = await api.listLoans(lid)
  parties.value = await api.listParties(lid)
  tags.value = await api.listTags(lid)
}

function resetForm() {
  Object.assign(form, {
    name: '', owner: '', total: null, currency: 'CNY',
    asset_nature: majorAssetStore.presetNature,
    payment_account_id: null, has_loan: false, selected_loan_ids: [],
    tag_ids: [], remark: '', occurred_at: new Date().toISOString().slice(0, 10)
  })
}

async function submit() {
  const lid = ledgerStore.currentId
  if (!lid) return
  if (!form.name.trim()) return ElMessage.warning('请输入资产名称')
  if (!(Number(form.total) > 0)) return ElMessage.warning('请输入资产总额')
  saving.value = true
  try {
    await api.buyMajorAsset(lid, {
      name: form.name.trim(),
      owner: form.owner || null,
      currency: form.currency || 'CNY',
      asset_nature: form.asset_nature,
      total: Number(form.total).toFixed(2),
      payment_account_id: form.payment_account_id,
      loan_ids: form.has_loan ? form.selected_loan_ids : [],
      tag_ids: form.tag_ids,
      remark: form.remark || null,
      occurred_at: form.occurred_at + 'T00:00:00'
    })
    ElMessage.success('已买入')
    majorAssetStore.markSaved()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '买入失败')
  } finally {
    saving.value = false
  }
}

watch(() => majorAssetStore.visible, (v) => {
  if (v) {
    resetForm()
    loadRefs()
  }
})
</script>

<template>
  <el-dialog v-model="visible" title="重大资产买入" width="92%" style="max-width:720px" append-to-body>
    <el-form label-width="92px">
      <el-row :gutter="16">
        <el-col :span="12" :xs="24">
          <el-form-item label="资产名称" required>
            <el-input v-model="form.name" placeholder="请输入资产名称" />
          </el-form-item>
        </el-col>
        <el-col :span="12" :xs="24">
          <el-form-item label="所有者">
            <el-select v-model="form.owner" filterable allow-create clearable placeholder="选择或输入" style="width:100%">
              <el-option v-for="p in parties" :key="p.id" :label="p.name" :value="p.name" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12" :xs="24">
          <el-form-item label="总额" required>
            <el-input-number v-model="form.total" :min="0" :precision="2" :controls="false" style="width:100%" />
          </el-form-item>
        </el-col>
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
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12" :xs="24">
          <el-form-item label="资产性质">
            <el-select v-model="form.asset_nature" style="width:100%">
              <el-option label="投资" value="invest" />
              <el-option label="自用" value="own" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12" :xs="24">
          <el-form-item label="支付账户">
            <el-select v-model="form.payment_account_id" clearable placeholder="选择支付账户" style="width:100%">
              <el-option v-for="a in fundingAccounts" :key="a.id" :label="`${a.icon} ${a.name}`" :value="a.id" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <!-- 有贷款 -->
      <el-form-item label-width="0">
        <el-checkbox v-model="form.has_loan">有贷款</el-checkbox>
        <el-button v-if="form.has_loan" size="small" style="margin-left:12px" @click="addLoan">新增贷款</el-button>
      </el-form-item>

      <el-table v-if="form.has_loan" :data="payableLoans" size="small" border style="margin-bottom:14px">
        <el-table-column width="50">
          <template #default="{ row }">
            <el-checkbox
              :model-value="form.selected_loan_ids.includes(row.id)"
              @change="(v: boolean) => toggleLoan(row.id, v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="债权人" min-width="120">
          <template #default="{ row }">{{ row.counterparty }}</template>
        </el-table-column>
        <el-table-column label="款项" min-width="120">
          <template #default="{ row }">{{ row.item || '—' }}</template>
        </el-table-column>
        <el-table-column label="借贷发生日" min-width="120">
          <template #default="{ row }">{{ (row.occurred_at || '').slice(0, 10) }}</template>
        </el-table-column>
        <el-table-column label="金额" align="right" min-width="120">
          <template #default="{ row }">{{ fmt(row.amount) }}</template>
        </el-table-column>
        <template #empty>暂无借入贷款，点击「新增贷款」添加</template>
      </el-table>

      <el-row :gutter="16">
        <el-col :span="12" :xs="24">
          <el-form-item label="标签">
            <el-select v-model="form.tag_ids" multiple filterable clearable placeholder="选择标签" style="width:100%">
              <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12" :xs="24">
          <el-form-item label="备注">
            <el-input v-model="form.remark" type="textarea" :rows="2" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12" :xs="24">
          <el-form-item label="日期" required>
            <el-date-picker v-model="form.occurred_at" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12" :xs="24">
          <el-form-item v-if="form.has_loan && form.selected_loan_ids.length" label="首付">
            <span class="downpay">{{ fmt(downPayment) }}（贷款 {{ fmt(selectedLoanTotal) }}）</span>
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>
    <template #footer>
      <el-button @click="majorAssetStore.close()">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">确定</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.downpay { font-size: 14px; color: #303133; font-weight: 600; }
</style>
