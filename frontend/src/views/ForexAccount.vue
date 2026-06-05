<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useForexStore } from '../stores/forex'
import type { Account, Holding, Transaction, Currency } from '../types'
import { fmtMoney, fmtNum } from '../utils/format'

const route = useRoute()
const ledgerStore = useLedgerStore()
const forexStore = useForexStore()

const accounts = ref<Account[]>([])
const holdings = ref<Holding[]>([])
const transactions = ref<Transaction[]>([])
const currencies = ref<Currency[]>([])
const selectedAccountId = ref<number | null>(null)
const refreshing = ref(false)

const FUNDING_TYPES = ['cash', 'bank', 'wallet', 'prepaid']
const forexAccounts = computed(() => accounts.value.filter((a) => a.type === 'forex'))
const selectedAccount = computed(() => accounts.value.find((a) => a.id === selectedAccountId.value) || null)
const fundingAccounts = computed(() => accounts.value.filter((a) => FUNDING_TYPES.includes(a.type)))

const toNum = (v: string | number | null | undefined) => Number(v || 0)
const fmt = (v: string | number | null | undefined) => fmtMoney(v)
const fmt4 = (v: string | number | null | undefined) => fmtNum(v, 4)
const fmtDate = (v: string) => (v || '').slice(0, 10)

function curName(code: string): string {
  const c = currencies.value.find((x) => x.code === code)
  return c ? c.name : code
}
function curRate(code: string): number {
  const c = currencies.value.find((x) => x.code === code)
  return c ? toNum(c.rate) || 1 : 1
}
function acctName(id: number | null | undefined): string {
  const a = accounts.value.find((x) => x.id === id)
  return a ? a.name : ''
}

// 本币代码（人民币）：外汇构成中不展示本币
const homeCode = computed(() => currencies.value.find((c) => c.is_home)?.code || 'CNY')

// 当前账户各外币持仓（含余额为 0 的币种），不含本币
const accountHoldings = computed(() =>
  holdings.value.filter((h) => h.account_id === selectedAccountId.value && h.type === 'forex'
    && (h.symbol || '').toUpperCase() !== homeCode.value.toUpperCase())
)
// 折算金额(人民币) = 当前余额 × 当前牌价（取币种实时牌价）
const liveValue = (h: Holding) => toNum(h.quantity) * curRate(h.symbol || '')
const liveProfit = (h: Holding) => liveValue(h) - toNum(h.cost)
const totalCny = computed(() => accountHoldings.value.reduce((s, h) => s + liveValue(h), 0))
const totalCost = computed(() => accountHoldings.value.reduce((s, h) => s + toNum(h.cost), 0))
const totalProfit = computed(() => totalCny.value - totalCost.value)

// 上半部表格「合计」行
function holdingSummary(param: { columns: unknown[] }) {
  const out: string[] = []
  param.columns.forEach((_, i) => {
    if (i === 0) out.push('合计')
    else if (i === 3) out.push(fmt(totalCny.value))
    else if (i === 4) out.push(fmt(totalCost.value))
    else if (i === 5) out.push(fmt(totalProfit.value))
    else out.push('')
  })
  return out
}

// 下半部交易记录：外汇买卖 + 转入/转出
interface FxRecord {
  id: number
  kind: 'trade' | 'transfer'
  date: string
  biz: string
  detail: string
  amountText: string
  remark: string
  txn: Transaction
}
const records = computed<FxRecord[]>(() => {
  const fid = selectedAccountId.value
  const list: FxRecord[] = []
  for (const t of transactions.value) {
    const sym = t.trade_symbol || ''
    if (sym.includes('/')) {
      // 外汇买卖
      const sell = sym.split('/')[0]
      const buy = sym.split('/')[1]
      list.push({
        id: t.id,
        kind: 'trade',
        date: fmtDate(t.occurred_at),
        biz: '外汇买卖',
        detail: `卖出 ${fmt(t.amount)} ${sell} → 买入 ${fmt(t.trade_qty)} ${buy}`,
        amountText: `${fmt(t.amount)} ${sell}`,
        remark: t.remark || '',
        txn: t,
      })
    } else if (t.type === 'transfer') {
      // 转入/转出
      const isIn = t.to_account_id === fid
      const counter = isIn ? t.account_id : t.to_account_id
      list.push({
        id: t.id,
        kind: 'transfer',
        date: fmtDate(t.occurred_at),
        biz: isIn ? '转入' : '转出',
        detail: `${curName(t.currency)} ${isIn ? '←' : '→'} ${acctName(counter)}`,
        amountText: `${isIn ? '+' : '-'}${fmt(t.amount)} ${t.currency}`,
        remark: t.remark || '',
        txn: t,
      })
    }
  }
  return list
})

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  currencies.value = await api.listCurrencies(lid)
  holdings.value = await api.listHoldings(lid)
  const qid = route.query.account_id ? Number(route.query.account_id) : null
  if (qid && forexAccounts.value.some((a) => a.id === qid)) {
    selectedAccountId.value = qid
  } else if (!selectedAccountId.value && forexAccounts.value.length) {
    selectedAccountId.value = forexAccounts.value[0].id
  }
  await loadTxns()
}

async function loadTxns() {
  const lid = ledgerStore.currentId
  if (!lid || !selectedAccountId.value) { transactions.value = []; return }
  const page = await api.listTransactions(lid, { account_id: selectedAccountId.value, page_size: 200 })
  transactions.value = page.items
}

function openTrade() {
  if (!selectedAccountId.value) { ElMessage.warning('请先选择外汇账户'); return }
  forexStore.open(selectedAccountId.value)
}

// 获取牌价：将各币种持仓的牌价刷新为币种资料中的当前牌价
async function refreshRates() {
  if (!accountHoldings.value.length) return
  refreshing.value = true
  try {
    for (const h of accountHoldings.value) {
      await api.updateHolding(h.id, { price: curRate(h.symbol || '') })
    }
    holdings.value = await api.listHoldings(ledgerStore.currentId as number)
    ElMessage.success('牌价已更新')
  } finally {
    refreshing.value = false
  }
}

// ---- 转账 ----
const transferDialog = ref(false)
const savingTransfer = ref(false)
const transferEditId = ref<number | null>(null)
const transferForm = reactive<{
  direction: 'in' | 'out'
  counter_account_id: number | null
  amount: number | null
  occurred_at: string
  remark: string
}>({ direction: 'in', counter_account_id: null, amount: null, occurred_at: '', remark: '' })

const transferCurrency = computed(() => {
  const a = accounts.value.find((x) => x.id === transferForm.counter_account_id)
  return a ? a.currency : 'CNY'
})

function openTransfer() {
  if (!selectedAccountId.value) { ElMessage.warning('请先选择外汇账户'); return }
  transferEditId.value = null
  transferForm.direction = 'in'
  transferForm.counter_account_id = fundingAccounts.value[0]?.id ?? null
  transferForm.amount = null
  transferForm.occurred_at = new Date().toISOString().slice(0, 10)
  transferForm.remark = ''
  transferDialog.value = true
}

async function submitTransfer() {
  const lid = ledgerStore.currentId
  if (!lid || !selectedAccountId.value) return
  const amt = Number(transferForm.amount)
  if (!amt || amt <= 0) { ElMessage.warning('请输入金额'); return }
  if (!transferForm.counter_account_id) { ElMessage.warning('请选择对方账户'); return }
  savingTransfer.value = true
  try {
    await api.forexTransfer(lid, {
      account_id: selectedAccountId.value,
      direction: transferForm.direction,
      counter_account_id: transferForm.counter_account_id,
      currency: transferCurrency.value,
      amount: amt,
      occurred_at: transferForm.occurred_at,
      remark: transferForm.remark || null,
      edit_txn_id: transferEditId.value
    })
    ElMessage.success(transferEditId.value ? '转账已更新' : '转账已记录')
    transferDialog.value = false
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message || '转账失败')
  } finally {
    savingTransfer.value = false
  }
}

// ---- 交易记录：编辑 / 删除 ----
function onEditRecord(rec: FxRecord) {
  const t = rec.txn
  if (rec.kind === 'trade') {
    // 外汇买卖：buy_currency=trade_symbol 后段，buy_amount=trade_qty，rate=trade_price
    const buy = (t.trade_symbol || '').split('/')[1] || ''
    forexStore.openEdit(selectedAccountId.value as number, {
      id: t.id,
      buy_currency: buy,
      buy_amount: Number(t.trade_qty || 0),
      rate: Number(t.trade_price || 0),
      funding_account_id: t.to_account_id ?? null,
      occurred_at: t.occurred_at,
      remark: t.remark ?? null,
      tag_ids: t.tag_ids ? [...t.tag_ids] : [],
    })
  } else {
    // 转账：回填方向/对方账户/金额
    const isIn = t.to_account_id === selectedAccountId.value
    transferEditId.value = t.id
    transferForm.direction = isIn ? 'in' : 'out'
    transferForm.counter_account_id = isIn ? t.account_id : (t.to_account_id ?? null)
    transferForm.amount = Number(t.amount || 0)
    transferForm.occurred_at = (t.occurred_at || '').slice(0, 10) || new Date().toISOString().slice(0, 10)
    transferForm.remark = t.remark || ''
    transferDialog.value = true
  }
}

async function onDeleteRecord(rec: FxRecord) {
  await ElMessageBox.confirm('确定删除这笔记录？相关持仓将自动重算。', '提示', { type: 'warning' })
  await api.deleteTransaction(rec.id)
  ElMessage.success('已删除')
  await load()
}

watch(() => forexStore.savedAt, () => { load() })
watch(() => route.query.account_id, () => { load() })
watch(selectedAccountId, () => { loadTxns() })
onMounted(load)
</script>

<template>
  <div class="fx-page">
    <!-- 上半：各外汇持有 -->
    <div class="panel">
      <div class="panel-head">
        <span class="panel-title">{{ selectedAccount?.name || '外汇账户' }}</span>
        <span class="panel-balance">{{ fmt(totalCny) }}</span>
        <span class="panel-unit">折算人民币</span>
        <div class="head-spacer" />
        <el-select v-if="forexAccounts.length > 1" v-model="selectedAccountId" size="small" style="width:160px">
          <el-option v-for="a in forexAccounts" :key="a.id" :label="a.name" :value="a.id" />
        </el-select>
        <el-button size="small" :loading="refreshing" @click="refreshRates">获取牌价</el-button>
        <el-button size="small" @click="openTransfer">转账</el-button>
        <el-button size="small" type="primary" @click="openTrade">外汇买卖</el-button>
      </div>

      <el-table :data="accountHoldings" size="small" border show-summary :summary-method="holdingSummary">
        <el-table-column label="币种" min-width="160">
          <template #default="{ row }">{{ curName(row.symbol) }} {{ row.symbol }}</template>
        </el-table-column>
        <el-table-column label="当前余额" align="right" min-width="130">
          <template #default="{ row }">{{ fmt4(row.quantity) }}</template>
        </el-table-column>
        <el-table-column label="当前牌价" align="right" min-width="120">
          <template #default="{ row }">{{ fmt4(curRate(row.symbol)) }}</template>
        </el-table-column>
        <el-table-column label="折算金额(人民币)" align="right" min-width="150">
          <template #default="{ row }">{{ fmt(liveValue(row)) }}</template>
        </el-table-column>
        <el-table-column label="持仓成本(人民币)" align="right" min-width="150">
          <template #default="{ row }">{{ fmt(row.cost) }}</template>
        </el-table-column>
        <el-table-column label="浮动盈亏" align="right" min-width="130">
          <template #default="{ row }">
            <span :class="liveProfit(row) >= 0 ? 'up' : 'down'">{{ fmt(liveProfit(row)) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!accountHoldings.length" description="暂无外汇持仓，点击「外汇买卖」记录交易" />
    </div>

    <!-- 下半：交易记录 -->
    <div class="panel">
      <div class="panel-head">
        <span class="panel-title">交易记录</span>
      </div>
      <el-table :data="records" size="small" border>
        <el-table-column label="日期" min-width="120" prop="date" />
        <el-table-column label="业务" min-width="90" prop="biz" />
        <el-table-column label="明细" min-width="240" prop="detail" />
        <el-table-column label="金额" align="right" min-width="140" prop="amountText" />
        <el-table-column label="备注" min-width="140" prop="remark" />
        <el-table-column label="操作" width="130" fixed="right" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="onEditRecord(row)">修改</el-button>
            <el-button link type="danger" size="small" @click="onDeleteRecord(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!records.length" description="暂无交易记录" />
    </div>

    <!-- 转账弹窗 -->
    <el-dialog v-model="transferDialog" :title="transferEditId ? '编辑外汇转账' : '外汇账户转账'" width="92%" style="max-width:520px" :close-on-click-modal="false">
      <el-form label-width="92px">
        <el-form-item label="转账方向">
          <el-radio-group v-model="transferForm.direction">
            <el-radio value="in">转入（存入外汇账户）</el-radio>
            <el-radio value="out">转出（取出至账户）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="transferForm.direction === 'in' ? '转出账户' : '转入账户'" required>
          <el-select v-model="transferForm.counter_account_id" placeholder="选择资金账户" style="width:100%">
            <el-option v-for="a in fundingAccounts" :key="a.id" :label="`${a.name}（余额 ${fmt(a.current_balance)} ${a.currency}）`" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额" required>
          <el-input v-model="transferForm.amount" type="number" placeholder="0.00">
            <template #append>{{ transferCurrency }}</template>
          </el-input>
        </el-form-item>
        <el-form-item label="日期" required>
          <el-date-picker v-model="transferForm.occurred_at" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="transferForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="transferDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingTransfer" @click="submitTransfer">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.fx-page { padding: 12px 16px; display: flex; flex-direction: column; gap: 14px; }
.panel { background: #fff; border: 1px solid #ebeef2; border-radius: 8px; padding: 12px 14px; }
.panel-head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.panel-title { font-size: 16px; font-weight: 600; color: #3c4b59; }
.panel-balance { font-size: 18px; font-weight: 700; color: #3c4b59; }
.panel-unit { font-size: 12px; color: #909399; }
.head-spacer { flex: 1; }
.up { color: #f56c6c; }
.down { color: #2e9c4f; }
</style>
