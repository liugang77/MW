<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useSalaryStore } from '../stores/salary'
import type { Account, Tag, Category, Party, Currency } from '../types'
import { fmtMoney } from '../utils/format'

const ledgerStore = useLedgerStore()
const salaryStore = useSalaryStore()

const accounts = ref<Account[]>([])
const tags = ref<Tag[]>([])
const incomeCats = ref<Category[]>([])
const expenseCats = ref<Category[]>([])
const parties = ref<Party[]>([])
const currencies = ref<Currency[]>([])

// 可收款的资金账户（现金/银行/钱包/储值）
const FUNDING_TYPES = ['cash', 'bank', 'wallet', 'prepaid']
const fundingAccounts = computed(() => accounts.value.filter((a) => FUNDING_TYPES.includes(a.type)))
const members = computed(() => parties.value.filter((p) => p.type === 'member'))

interface Row { category_id: number | null; name: string; amount: string }
const currency = ref('CNY')
const accountId = ref<number | null>(null)
const incomes = ref<Row[]>([])
const deductions = ref<Row[]>([])
const insuredPerson = ref('')
const tagIds = ref<number[]>([])
const remark = ref('')
const occurredAt = ref(new Date().toISOString().slice(0, 10))

const num = (v: string) => Number(v || 0)
const round2 = (n: number) => Math.round(n * 100) / 100
const incomeTotal = computed(() => round2(incomes.value.reduce((s, r) => s + num(r.amount), 0)))
const deductionTotal = computed(() => round2(deductions.value.reduce((s, r) => s + num(r.amount), 0)))
const netTotal = computed(() => round2(incomeTotal.value - deductionTotal.value))

function addIncome() {
  incomes.value.push({ category_id: salaryCatId.value, name: '', amount: '' })
}
function addDeduction() {
  deductions.value.push({ category_id: null, name: '', amount: '' })
}
function removeIncome(i: number) { incomes.value.splice(i, 1) }
function removeDeduction(i: number) { deductions.value.splice(i, 1) }

// 默认收入分类「工资」
const salaryCatId = computed(() => {
  const c = incomeCats.value.find((x) => x.name === '工资')
  return c ? c.id : (incomeCats.value[0]?.id ?? null)
})

async function loadMeta() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  tags.value = await api.listTags(lid)
  incomeCats.value = await api.listCategories(lid, 'income')
  expenseCats.value = await api.listCategories(lid, 'expense')
  parties.value = await api.listParties(lid)
  currencies.value = await api.listCurrencies(lid)
  const home = currencies.value.find((c) => c.is_home)
  currency.value = home ? home.code : 'CNY'
  if (!accountId.value && fundingAccounts.value.length) {
    accountId.value = fundingAccounts.value[0].id
  }
}

function reset() {
  accountId.value = fundingAccounts.value[0]?.id ?? null
  incomes.value = [{ category_id: salaryCatId.value, name: '基本工资', amount: '' }]
  deductions.value = []
  insuredPerson.value = ''
  tagIds.value = []
  remark.value = ''
  occurredAt.value = new Date().toISOString().slice(0, 10)
}

function validate(): boolean {
  if (!accountId.value) { ElMessage.warning('请选择收入账户'); return false }
  const validIncomes = incomes.value.filter((r) => num(r.amount) > 0)
  if (!validIncomes.length) { ElMessage.warning('请至少填写一项有效的收入金额'); return false }
  if (netTotal.value < 0) { ElMessage.warning('扣款合计不能大于收入合计'); return false }
  return true
}

async function submit(keepOpen: boolean) {
  if (!validate()) return
  const lid = ledgerStore.currentId as number
  const incomesPayload = incomes.value
    .filter((r) => num(r.amount) > 0)
    .map((r) => ({ category_id: r.category_id, name: r.name || null, amount: r.amount }))
  const deductionsPayload = deductions.value
    .filter((r) => num(r.amount) > 0)
    .map((r) => ({ category_id: r.category_id, name: r.name || null, amount: r.amount }))
  try {
    await api.salaryIncome(lid, {
      account_id: accountId.value,
      currency: currency.value,
      incomes: incomesPayload,
      deductions: deductionsPayload,
      insured_person: insuredPerson.value || null,
      occurred_at: occurredAt.value,
      remark: remark.value || null,
      tag_ids: tagIds.value,
    })
  } catch (e) {
    return ElMessage.error((e as Error).message || '记账失败')
  }
  ElMessage.success('工资收入已记录')
  salaryStore.savedAt = Date.now()
  if (keepOpen) {
    reset()
  } else {
    salaryStore.close()
  }
}

watch(() => salaryStore.visible, (v) => {
  if (v) {
    loadMeta().then(() => reset())
  }
})
</script>

<template>
  <el-dialog
    v-model="salaryStore.visible"
    title="工资收入"
    width="92%"
    style="max-width:820px"
    :close-on-click-modal="false"
  >
    <el-form label-width="80px" class="salary-form">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="币种" required>
            <el-select v-model="currency" style="width:100%">
              <el-option v-for="c in currencies" :key="c.code" :label="`${c.name} ${c.code}`" :value="c.code" />
            </el-select>
          </el-form-item>
          <el-form-item label="收入账户" required>
            <el-select v-model="accountId" placeholder="选择到账账户" style="width:100%">
              <el-option v-for="a in fundingAccounts" :key="a.id" :label="a.name" :value="a.id" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <!-- 收入项目 -->
        <el-col :span="12">
          <div class="grid-head">
            <span class="grid-title">收入项目</span>
            <el-button size="small" type="primary" plain @click="addIncome">+ 添加</el-button>
          </div>
          <el-table :data="incomes" size="small" border>
            <el-table-column label="收入项目" min-width="150">
              <template #default="{ row }">
                <el-select v-model="row.category_id" placeholder="选择项目" size="small" style="width:100%" filterable>
                  <el-option v-for="c in incomeCats" :key="c.id" :label="c.name" :value="c.id" />
                </el-select>
                <el-input v-model="row.name" size="small" placeholder="名称（如 基本工资）" style="margin-top:4px" />
              </template>
            </el-table-column>
            <el-table-column label="金额" align="right" width="120">
              <template #default="{ row }">
                <el-input v-model="row.amount" type="number" size="small" placeholder="0.00" />
              </template>
            </el-table-column>
            <el-table-column width="48" align="center">
              <template #default="{ $index }">
                <el-button link type="danger" size="small" @click="removeIncome($index)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="grid-total">实收：{{ fmtMoney(netTotal) }}　=　收入 {{ fmtMoney(incomeTotal) }}</div>
        </el-col>

        <!-- 扣款项目 -->
        <el-col :span="12">
          <div class="grid-head">
            <span class="grid-title">扣款项目</span>
            <el-button size="small" plain @click="addDeduction">+ 添加</el-button>
          </div>
          <el-table :data="deductions" size="small" border empty-text="可选：个税、社保、公积金等">
            <el-table-column label="扣款项目" min-width="150">
              <template #default="{ row }">
                <el-select v-model="row.category_id" placeholder="选择项目" size="small" style="width:100%" filterable clearable>
                  <el-option v-for="c in expenseCats" :key="c.id" :label="c.name" :value="c.id" />
                </el-select>
                <el-input v-model="row.name" size="small" placeholder="名称（如 个税/社保）" style="margin-top:4px" />
              </template>
            </el-table-column>
            <el-table-column label="金额" align="right" width="120">
              <template #default="{ row }">
                <el-input v-model="row.amount" type="number" size="small" placeholder="0.00" />
              </template>
            </el-table-column>
            <el-table-column width="48" align="center">
              <template #default="{ $index }">
                <el-button link type="danger" size="small" @click="removeDeduction($index)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="grid-total">扣款合计：{{ fmtMoney(deductionTotal) }}</div>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="社保人员">
            <el-select v-model="insuredPerson" placeholder="<无>" clearable filterable allow-create default-first-option style="width:100%">
              <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.name" />
            </el-select>
          </el-form-item>
          <el-form-item label="标签">
            <el-select v-model="tagIds" multiple filterable placeholder="选择标签" style="width:100%">
              <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="日期" required>
            <el-date-picker v-model="occurredAt" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="备注">
            <el-input v-model="remark" type="textarea" :rows="4" />
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
.grid-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.grid-title { font-size: 13px; font-weight: 600; color: #3c4b59; }
.grid-total {
  margin: 6px 0 12px;
  font-size: 13px;
  color: #2e9c4f;
  font-weight: 600;
}
</style>
