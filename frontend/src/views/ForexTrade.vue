<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useForexStore } from '../stores/forex'
import type { Account, Tag, Currency } from '../types'
import { fmtMoney } from '../utils/format'

const ledgerStore = useLedgerStore()
const forexStore = useForexStore()

const accounts = ref<Account[]>([])
const tags = ref<Tag[]>([])
const currencies = ref<Currency[]>([])

const accountId = ref<number | null>(null)
const buyCurrency = ref('USD')
const buyAmount = ref('')
const rate = ref('')
const fundingAccountId = ref<number | null>(null)
const tagIds = ref<number[]>([])
const remark = ref('')
const occurredAt = ref(new Date().toISOString().slice(0, 10))

const forexAccounts = computed(() => accounts.value.filter((a) => a.type === 'forex'))

function curName(code: string): string {
  const c = currencies.value.find((x) => x.code === code)
  return c ? c.name : code
}
function curRate(code: string): number {
  const c = currencies.value.find((x) => x.code === code)
  return c ? Number(c.rate) || 1 : 1
}

// 卖出货币固定为本币（人民币）：用人民币买外币
const homeCode = computed(() => currencies.value.find((c) => c.is_home)?.code || 'CNY')
const homeName = computed(() => curName(homeCode.value))
const buyName = computed(() => curName(buyCurrency.value))
// 可买入的外币（排除本币）
const foreignCurrencies = computed(() => currencies.value.filter((c) => !c.is_home))

// 资金账户：用本币（人民币）现金类账户支付购汇款；默认（值 0）= 用外汇账户内的人民币持仓
const FUNDING_TYPES = ['cash', 'bank', 'wallet', 'prepaid']
const fundingAccounts = computed(() =>
  accounts.value.filter((a) => FUNDING_TYPES.includes(a.type) && a.currency === homeCode.value)
)

const num = (v: string) => Number(v || 0)
const round2 = (n: number) => Math.round(n * 100) / 100

// 默认交易汇率：每 1 本币 = (本币牌价 / 买入币牌价) 买入币
function defaultRate(): number {
  const r = curRate(homeCode.value) / curRate(buyCurrency.value)
  return Math.round(r * 1e6) / 1e6
}

// 人民币总额 = 买入外币金额 / 交易汇率（即需要卖出的人民币）
const cnyTotal = computed(() => {
  const r = num(rate.value)
  return r > 0 ? round2(num(buyAmount.value) / r) : 0
})

function resetRate() {
  rate.value = String(defaultRate())
}

// 回填编辑时抑制「切换买入货币自动取牌价」覆盖原汇率
let suppressRateReset = false
watch(buyCurrency, () => {
  if (suppressRateReset) return
  resetRate()
})

async function loadMeta() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  tags.value = await api.listTags(lid)
  currencies.value = await api.listCurrencies(lid)
  const foreign = foreignCurrencies.value[0]
  buyCurrency.value = foreign ? foreign.code : (currencies.value[1]?.code || 'USD')
  if (forexStore.presetAccountId && forexAccounts.value.some((a) => a.id === forexStore.presetAccountId)) {
    accountId.value = forexStore.presetAccountId
  } else if (forexAccounts.value.length) {
    accountId.value = forexAccounts.value[0].id
  }
  resetRate()
}

function reset() {
  buyAmount.value = ''
  fundingAccountId.value = null
  tagIds.value = []
  remark.value = ''
  occurredAt.value = new Date().toISOString().slice(0, 10)
}

function validate(): boolean {
  if (!accountId.value) { ElMessage.warning('请选择交易账户'); return false }
  if (!buyCurrency.value || buyCurrency.value === homeCode.value) { ElMessage.warning('请选择买入货币'); return false }
  if (!(num(buyAmount.value) > 0)) { ElMessage.warning('请输入买入金额'); return false }
  if (!(num(rate.value) > 0)) { ElMessage.warning('请输入交易汇率'); return false }
  return true
}

async function submit(keepOpen: boolean) {
  if (!validate()) return
  const lid = ledgerStore.currentId as number
  const editId = forexStore.editTxn?.id ?? null
  try {
    await api.forexTrade(lid, {
      account_id: accountId.value,
      sell_currency: homeCode.value,
      sell_amount: String(cnyTotal.value),
      buy_currency: buyCurrency.value,
      buy_amount: buyAmount.value,
      rate: rate.value || 0,
      funding_account_id: fundingAccountId.value,
      occurred_at: occurredAt.value,
      remark: remark.value || null,
      tag_ids: tagIds.value,
      edit_txn_id: editId,
    })
  } catch (e) {
    ElMessage.error((e as Error).message || '外汇买卖失败')
    return
  }
  ElMessage.success(editId ? '外汇买卖已更新' : '外汇买卖已记录')
  forexStore.savedAt = Date.now()
  if (keepOpen && !editId) {
    reset()
  } else {
    forexStore.close()
  }
}

// 编辑回填
function prefillEdit() {
  const e = forexStore.editTxn
  if (!e) return
  suppressRateReset = true
  buyCurrency.value = e.buy_currency
  rate.value = String(e.rate)
  buyAmount.value = String(e.buy_amount)
  fundingAccountId.value = e.funding_account_id ?? null
  occurredAt.value = e.occurred_at ? e.occurred_at.slice(0, 10) : new Date().toISOString().slice(0, 10)
  remark.value = e.remark || ''
  tagIds.value = e.tag_ids ? [...e.tag_ids] : []
  // 待 buyCurrency 的 watch 执行后再恢复
  setTimeout(() => { suppressRateReset = false }, 0)
}

watch(() => forexStore.visible, (v) => {
  if (v) {
    reset()
    loadMeta().then(() => {
      if (forexStore.editTxn) prefillEdit()
    })
  }
})
</script>

<template>
  <el-dialog
    v-model="forexStore.visible"
    :title="forexStore.editTxn ? '编辑外汇买卖' : '外汇买卖'"
    width="92%"
    style="max-width:640px"
    :close-on-click-modal="false"
  >
    <el-form label-width="92px" class="forex-form">
      <el-form-item label="交易账户" required>
        <el-select v-model="accountId" placeholder="选择外汇交易账户" style="width:100%">
          <el-option v-for="a in forexAccounts" :key="a.id" :label="a.name" :value="a.id" />
        </el-select>
      </el-form-item>

      <el-form-item label="买入货币" required>
        <el-select v-model="buyCurrency" style="width:100%">
          <el-option v-for="c in foreignCurrencies" :key="c.code" :label="`${c.name} ${c.code}`" :value="c.code" />
        </el-select>
      </el-form-item>

      <el-form-item label="交易汇率" required>
        <el-input v-model="rate" type="number" placeholder="0.0000">
          <template #append>
            <el-button @click="resetRate">取牌价</el-button>
          </template>
        </el-input>
        <div class="rate-hint">每 1 {{ homeName }} 兑换 {{ num(rate) }} {{ buyName }}</div>
      </el-form-item>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="`买入${buyName}`" required>
            <el-input v-model="buyAmount" type="number" placeholder="0.00" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="`${homeName}总额`">
            <el-input :model-value="cnyTotal.toFixed(2)" readonly placeholder="0.00" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="资金账户">
        <el-select v-model="fundingAccountId" clearable placeholder="账户内人民币（默认）" style="width:100%">
          <el-option
            v-for="a in fundingAccounts"
            :key="a.id"
            :label="`${a.name}（余额 ${fmtMoney(a.current_balance)} ${a.currency}）`"
            :value="a.id"
          />
        </el-select>
      </el-form-item>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="标签">
            <el-select v-model="tagIds" multiple filterable placeholder="选择标签" style="width:100%">
              <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="日期" required>
            <el-date-picker v-model="occurredAt" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="备注">
        <el-input v-model="remark" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="submit(true)">保存并继续</el-button>
      <el-button type="primary" @click="submit(false)">确定</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.rate-hint {
  width: 100%;
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}
</style>
