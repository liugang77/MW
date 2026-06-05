<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useFundStore } from '../stores/fund'
import type { Account, Tag, Instrument, InstrumentPrice } from '../types'

const ledgerStore = useLedgerStore()
const fundStore = useFundStore()

const accounts = ref<Account[]>([])
const tags = ref<Tag[]>([])
const instruments = ref<Instrument[]>([])
const instrumentPrices = ref<InstrumentPrice[]>([])

const FUND_TYPES = ['fund', 'open_fund', 'money_fund']
const CASH_TYPES = ['cash', 'bank', 'wallet', 'prepaid']
const fundAccounts = computed(() => accounts.value.filter((a) => FUND_TYPES.includes(a.type)))
const cashAccounts = computed(() =>
  accounts.value.filter((a) => CASH_TYPES.includes(a.type) || FUND_TYPES.includes(a.type))
)

// 表单
const fundAccountId = ref<number | null>(null)
const cashAccountId = ref<number | null>(null)
const symbol = ref('')
const name = ref('')
const feeMode = ref('front')
const nav = ref('')
const feeRate = ref('')
const amount = ref('')
const fee = ref('')
const shares = ref('')
const tagIds = ref<number[]>([])
const remark = ref('')
const occurredAt = ref(new Date().toISOString().slice(0, 10))

const feeModes = [
  { v: 'front', t: '前端' },
  { v: 'back', t: '后端' }
]

const num = (v: string) => Number(v || 0)
const round2 = (n: number) => Math.round(n * 100) / 100
const round4 = (n: number) => Math.round(n * 10000) / 10000

// 当前基金账户对应的可选基金（开放式/货币基金资料）
const currentCategory = computed(() => {
  const acc = accounts.value.find((a) => a.id === fundAccountId.value)
  return acc?.type === 'money_fund' ? 'money_fund' : 'open_fund'
})
const symbolOptions = computed(() =>
  instruments.value.filter((i) => i.category === currentCategory.value)
)

function latestPrice(code: string): string {
  const inst = instruments.value.find((i) => (i.code || i.name) === code)
  if (!inst) return ''
  const ps = instrumentPrices.value
    .filter((p) => p.instrument_id === inst.id)
    .sort((a, b) => (a.price_date < b.price_date ? 1 : -1))
  return ps.length ? String(ps[0].price) : ''
}

// 申购：按申购金额 + 费率 + 净值 计算申购费用与申购份数（前端收费）
function recalc() {
  const amt = num(amount.value)
  const rate = num(feeRate.value) / 100
  const p = num(nav.value)
  if (amt <= 0 || p <= 0) {
    fee.value = '0.00'
    shares.value = '0.00'
    return
  }
  // 前端收费：净申购金额 = 申购金额 / (1 + 费率)
  const net = feeMode.value === 'front' ? amt / (1 + rate) : amt
  const f = feeMode.value === 'front' ? round2(amt - net) : 0
  fee.value = f.toFixed(2)
  shares.value = round2(net / p).toFixed(2)
}

watch([amount, feeRate, nav, feeMode], recalc)

function onSymbolChange() {
  const inst = symbolOptions.value.find((i) => (i.code || i.name) === symbol.value)
  if (inst) {
    name.value = inst.name
    const lp = latestPrice(symbol.value)
    if (lp) nav.value = lp
    if (inst.buy_fee_rate != null && feeRate.value === '') feeRate.value = String(inst.buy_fee_rate)
  }
}

async function loadMeta() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  tags.value = await api.listTags(lid)
  instruments.value = await api.listInstruments(lid)
  instrumentPrices.value = await api.listInstrumentPrices(lid)
  if (fundStore.presetAccountId && fundAccounts.value.some((a) => a.id === fundStore.presetAccountId)) {
    fundAccountId.value = fundStore.presetAccountId
  } else if (!fundAccountId.value && fundAccounts.value.length) {
    fundAccountId.value = fundAccounts.value[0].id
  }
  if (!cashAccountId.value && cashAccounts.value.length) cashAccountId.value = cashAccounts.value[0].id
}

function reset() {
  symbol.value = ''
  name.value = ''
  feeMode.value = 'front'
  nav.value = ''
  feeRate.value = ''
  amount.value = ''
  fee.value = '0.00'
  shares.value = '0.00'
  tagIds.value = []
  remark.value = ''
  occurredAt.value = new Date().toISOString().slice(0, 10)
}

const dialogVisible = computed({
  get: () => fundStore.visible && fundStore.mode === 'buy',
  set: (v: boolean) => { if (!v) fundStore.close() }
})

function validate(): boolean {
  if (!fundAccountId.value) { ElMessage.warning('请选择基金账户'); return false }
  if (!symbol.value && !name.value.trim()) { ElMessage.warning('请选择基金名称'); return false }
  if (!(num(nav.value) > 0)) { ElMessage.warning('请输入单位净值'); return false }
  if (!(num(amount.value) > 0)) { ElMessage.warning('请输入申购金额'); return false }
  if (!(num(shares.value) > 0)) { ElMessage.warning('申购份数无效'); return false }
  return true
}

async function submit(keepOpen: boolean) {
  if (!validate()) return
  const lid = ledgerStore.currentId as number
  await api.tradeBuy(lid, {
    security_account_id: fundAccountId.value,
    cash_account_id: cashAccountId.value,
    symbol: symbol.value.trim() || name.value.trim(),
    name: name.value.trim() || symbol.value.trim(),
    sec_type: currentCategory.value === 'money_fund' ? 'money_fund' : 'fund',
    price: nav.value || 0,
    quantity: shares.value || 0,
    commission: 0,
    fee_total: fee.value || 0,
    amount_total: amount.value || 0,
    occurred_at: occurredAt.value + 'T00:00:00',
    remark: remark.value || null,
    tag_ids: tagIds.value
  })
  ElMessage.success('基金申购已记录')
  fundStore.savedAt = Date.now()
  if (keepOpen) {
    reset()
    await loadMeta()
  } else {
    fundStore.close()
  }
}

watch(() => fundStore.visible, (v) => {
  if (v && fundStore.mode === 'buy') { reset(); loadMeta() }
})
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="开放式基金申购"
    width="92%"
    style="max-width:760px"
    :close-on-click-modal="false"
  >
    <el-form label-width="90px" class="fund-form">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="基金账户" required>
            <el-select v-model="fundAccountId" placeholder="选择基金账户" style="width:100%">
              <el-option v-for="a in fundAccounts" :key="a.id" :label="a.name" :value="a.id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="资金账户">
            <el-select v-model="cashAccountId" placeholder="选择资金账户" style="width:100%">
              <el-option v-for="a in cashAccounts" :key="a.id" :label="a.name" :value="a.id" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="基金名称" required>
            <el-select
              v-model="symbol"
              filterable
              allow-create
              default-first-option
              placeholder="选择或输入基金"
              style="width:100%"
              @change="onSymbolChange"
            >
              <el-option
                v-for="i in symbolOptions"
                :key="i.id"
                :label="`${i.code ? i.code + ' ' : ''}${i.name}`"
                :value="i.code || i.name"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="收费模式">
            <el-select v-model="feeMode" style="width:100%">
              <el-option v-for="m in feeModes" :key="m.v" :label="m.t" :value="m.v" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="单位净值" required>
            <el-input v-model="nav" type="number" placeholder="0.0000" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="申购费率%">
            <el-input v-model="feeRate" type="number" placeholder="0.00" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="申购金额" required>
            <el-input v-model="amount" type="number" placeholder="0.00" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="申购费用">
            <el-input v-model="fee" type="number" readonly />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="申购份数" required>
            <el-input v-model="shares" type="number" readonly />
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
            <el-input v-model="remark" type="textarea" :rows="2" placeholder="请输入备注" />
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
.fund-form :deep(input[readonly]) {
  background: #f5f7fa;
}
</style>
