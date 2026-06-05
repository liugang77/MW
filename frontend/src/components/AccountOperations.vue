<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useLoanStore } from '../stores/loan'
import type { Account, Category, Tag } from '../types'

const props = defineProps<{
  account: Account | null
  accounts: Account[]
  tags?: Tag[]
}>()
const emit = defineEmits<{ (e: 'saved'): void }>()

const ledgerStore = useLedgerStore()
const loanStore = useLoanStore()

const today = () => new Date().toISOString().slice(0, 10) + 'T00:00:00'
const toNum = (v: string | number | null | undefined) => Number(v || 0)

// 收支项目（按需加载）
const expenseCats = ref<Category[]>([])
const incomeCats = ref<Category[]>([])
async function ensureCategories() {
  const lid = ledgerStore.currentId
  if (!lid) return
  if (!expenseCats.value.length) expenseCats.value = await api.listCategories(lid, 'expense')
  if (!incomeCats.value.length) incomeCats.value = await api.listCategories(lid, 'income')
}

interface Op { key: string; label: string }
const FUND_LIKE = ['cash', 'wallet', 'bank']

// 按账户类型展示可用操作
const ops = computed<Op[]>(() => {
  const t = props.account?.type || ''
  const daily: Op[] = [
    { key: 'expense', label: '日常支出' },
    { key: 'income', label: '日常收入' },
    { key: 'split', label: '分拆收支' }
  ]
  const common: Op[] = [
    { key: 'transfer', label: '转账' },
    { key: 'exchange', label: '货币兑换' },
    { key: 'borrow', label: '借入' },
    { key: 'lend', label: '借出' },
    { key: 'adjust', label: '余额调整' }
  ]
  if (FUND_LIKE.includes(t)) {
    return [
      ...daily,
      { key: 'transfer', label: '转账' },
      { key: 'deposit', label: '存款' },
      { key: 'withdraw', label: '取款' },
      { key: 'exchange', label: '货币兑换' },
      { key: 'borrow', label: '借入' },
      { key: 'lend', label: '借出' },
      { key: 'adjust', label: '余额调整' }
    ]
  }
  if (t === 'credit') {
    return [
      { key: 'expense', label: '刷卡消费' },
      { key: 'transfer', label: '还款' },
      { key: 'adjust', label: '余额调整' }
    ]
  }
  return [...daily, ...common]
})

function onCommand(cmd: string) {
  const accId = props.account?.id ?? null
  switch (cmd) {
    case 'expense':
      return openDaily('expense')
    case 'income':
      return openDaily('income')
    case 'split':
      return openSplit()
    case 'transfer':
      return openTransfer('transfer')
    case 'deposit':
      return openTransfer('deposit')
    case 'withdraw':
      return openTransfer('withdraw')
    case 'exchange':
      return openExchange()
    case 'adjust':
      return openAdjust()
    case 'borrow':
      return loanStore.open('payable')
    case 'lend':
      return loanStore.open('receivable')
  }
}

// ---------- 日常收支 ----------
const dailyVisible = ref(false)
const dailyType = ref<'expense' | 'income'>('expense')
const dailyCats = computed(() => (dailyType.value === 'income' ? incomeCats.value : expenseCats.value))
const dailyTitle = computed(() => (dailyType.value === 'income' ? '日常收入' : '日常支出'))
const daily = ref({
  categoryId: null as number | null,
  amount: 0,
  accountId: null as number | null,
  tagIds: [] as number[],
  occurredAt: today(),
  remark: ''
})

async function openDaily(t: 'expense' | 'income') {
  dailyType.value = t
  daily.value = {
    categoryId: null, amount: 0, accountId: props.account?.id ?? null,
    tagIds: [], occurredAt: today(), remark: ''
  }
  await ensureCategories()
  dailyVisible.value = true
}

async function saveDaily(keepOpen: boolean): Promise<boolean> {
  const lid = ledgerStore.currentId
  if (!lid) return false
  if (!daily.value.categoryId) { ElMessage.warning('请选择收支项目'); return false }
  if (toNum(daily.value.amount) <= 0) { ElMessage.warning('请输入金额'); return false }
  if (!daily.value.accountId) { ElMessage.warning('请选择收支账户'); return false }
  try {
    await api.createTransaction(lid, {
      type: dailyType.value,
      amount: String(daily.value.amount),
      account_id: daily.value.accountId,
      category_id: daily.value.categoryId,
      tag_ids: daily.value.tagIds,
      occurred_at: daily.value.occurredAt,
      remark: daily.value.remark || null
    })
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '记账失败')
    return false
  }
  ElMessage.success('已记账')
  emit('saved')
  if (keepOpen) {
    daily.value.categoryId = null
    daily.value.amount = 0
    daily.value.remark = ''
  } else {
    dailyVisible.value = false
  }
  return true
}

// ---------- 分拆收支 ----------
interface SplitRow {
  categoryId: number | null
  income: number
  expense: number
  tagIds: number[]
  remark: string
}
const splitVisible = ref(false)
const splitAccountId = ref<number | null>(null)
const splitOccurredAt = ref(today())
const splitRows = ref<SplitRow[]>([])
const splitEditGroup = ref<string | null>(null)
const splitTitle = computed(() => (splitEditGroup.value ? '修改分拆收支' : '分拆收支'))

// 第一行收支项目决定本次交易类型（收入/支出）
const splitType = computed<'income' | 'expense'>(() => {
  const first = splitRows.value.find((r) => r.categoryId != null)
  if (!first) return 'expense'
  return rowIsIncome(first) ? 'income' : 'expense'
})
// 某行的收支类型由该行所选项目决定；未选项目时跟随整体类型
function rowIsIncome(row: SplitRow): boolean {
  if (row.categoryId == null) return splitType.value === 'income'
  return incomeCats.value.some((c) => c.id === row.categoryId)
}
const splitTotal = computed(() =>
  splitRows.value.reduce((s, r) => s + (rowIsIncome(r) ? toNum(r.income) : toNum(r.expense)), 0)
)

function blankSplitRow(): SplitRow {
  return { categoryId: null, income: 0, expense: 0, tagIds: [], remark: '' }
}

async function openSplit() {
  splitEditGroup.value = null
  splitAccountId.value = props.account?.id ?? null
  splitOccurredAt.value = today()
  splitRows.value = [blankSplitRow(), blankSplitRow()]
  await ensureCategories()
  splitVisible.value = true
}

// 编辑已存在的一组分拆收支
async function openSplitEdit(group: string) {
  const lid = ledgerStore.currentId
  if (!lid) return
  await ensureCategories()
  let rows: { category_id?: number | null; amount: string; remark?: string | null; tag_ids?: number[]; account_id: number; occurred_at: string; type: string }[]
  try {
    rows = await api.getSplitGroup(lid, group) as unknown as typeof rows
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载分拆记录失败')
    return
  }
  if (!rows.length) return
  splitEditGroup.value = group
  splitAccountId.value = rows[0].account_id
  splitOccurredAt.value = (rows[0].occurred_at || today()).slice(0, 19)
  splitRows.value = rows.map((r) => {
    const isIncome = incomeCats.value.some((c) => c.id === r.category_id)
    return {
      categoryId: r.category_id ?? null,
      income: isIncome ? Number(r.amount) : 0,
      expense: isIncome ? 0 : Number(r.amount),
      tagIds: r.tag_ids ?? [],
      remark: r.remark === '分拆收支' ? '' : (r.remark || '')
    }
  })
  splitRows.value.push(blankSplitRow())
  splitVisible.value = true
}

function ensureTrailingRow() {
  const last = splitRows.value[splitRows.value.length - 1]
  if (!last || last.categoryId != null) splitRows.value.push(blankSplitRow())
}

function onSplitCategoryChange(row: SplitRow) {
  // 选择<无>（null）则删除该行
  if (row.categoryId == null) {
    const i = splitRows.value.indexOf(row)
    if (i >= 0 && splitRows.value.length > 1) splitRows.value.splice(i, 1)
  }
  ensureTrailingRow()
}

async function saveSplit(keepOpen: boolean): Promise<boolean> {
  const lid = ledgerStore.currentId
  if (!lid) return false
  if (!splitAccountId.value) { ElMessage.warning('请选择收支账户'); return false }
  const items = splitRows.value
    .filter((r) => r.categoryId != null)
    .map((r) => ({
      category_id: r.categoryId as number,
      amount: String(rowIsIncome(r) ? r.income : r.expense),
      remark: r.remark || '分拆收支',
      tag_ids: r.tagIds
    }))
    .filter((i) => Number(i.amount) > 0)
  if (items.length < 2) { ElMessage.warning('至少填写两条有效明细'); return false }
  try {
    if (splitEditGroup.value) {
      await api.updateSplitGroup(lid, splitEditGroup.value, {
        type: splitType.value,
        account_id: splitAccountId.value,
        occurred_at: splitOccurredAt.value,
        items
      })
    } else {
      await api.splitTransaction(lid, {
        type: splitType.value,
        account_id: splitAccountId.value,
        occurred_at: splitOccurredAt.value,
        items
      })
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '分拆记账失败')
    return false
  }
  ElMessage.success('已记账')
  emit('saved')
  if (keepOpen && !splitEditGroup.value) {
    splitRows.value = [blankSplitRow(), blankSplitRow()]
  } else {
    splitVisible.value = false
  }
  return true
}

// ---------- 转账 / 存款 / 取款 ----------
const transferVisible = ref(false)
const transferTitle = ref('转账')
const tf = ref({
  fromId: null as number | null,
  toId: null as number | null,
  amount: 0,
  fee: 0,
  feeAccountId: null as number | null,
  occurredAt: today(),
  remark: '',
  tagIds: [] as number[]
})

function openTransfer(mode: 'transfer' | 'deposit' | 'withdraw') {
  const accId = props.account?.id ?? null
  tf.value = {
    fromId: accId, toId: null, amount: 0, fee: 0,
    feeAccountId: null, occurredAt: today(), remark: '', tagIds: []
  }
  if (mode === 'deposit') {
    // 存款：资金存入本账户
    tf.value.fromId = null
    tf.value.toId = accId
    transferTitle.value = '存款'
  } else if (mode === 'withdraw') {
    // 取款：从本账户取出
    tf.value.fromId = accId
    tf.value.toId = null
    transferTitle.value = '取款'
  } else {
    transferTitle.value = '转账'
  }
  transferVisible.value = true
}

async function submitTransfer() {
  const lid = ledgerStore.currentId
  if (!lid) return
  if (!tf.value.fromId || !tf.value.toId) return ElMessage.warning('请选择转出与转入账户')
  if (tf.value.fromId === tf.value.toId) return ElMessage.warning('转出与转入账户不能相同')
  if (toNum(tf.value.amount) <= 0) return ElMessage.warning('请输入转账金额')
  try {
    await api.transferTransaction(lid, {
      from_account_id: tf.value.fromId,
      to_account_id: tf.value.toId,
      amount: String(tf.value.amount),
      fee: String(tf.value.fee || 0),
      fee_account_id: tf.value.feeAccountId,
      currency: props.account?.currency || 'CNY',
      occurred_at: tf.value.occurredAt,
      remark: tf.value.remark || null,
      tag_ids: tf.value.tagIds
    })
  } catch (e) {
    return ElMessage.error(e instanceof Error ? e.message : '转账失败')
  }
  ElMessage.success('已记账')
  transferVisible.value = false
  emit('saved')
}

// ---------- 货币兑换 ----------
const exchangeVisible = ref(false)
const ex = ref({
  fromId: null as number | null,
  fromAmount: 0,
  toId: null as number | null,
  toAmount: 0,
  fee: 0,
  feeAccountId: null as number | null,
  occurredAt: today(),
  remark: ''
})

function openExchange() {
  ex.value = {
    fromId: props.account?.id ?? null, fromAmount: 0, toId: null, toAmount: 0,
    fee: 0, feeAccountId: null, occurredAt: today(), remark: ''
  }
  exchangeVisible.value = true
}

const exRate = computed(() => {
  const f = toNum(ex.value.fromAmount)
  const t = toNum(ex.value.toAmount)
  return f > 0 && t > 0 ? (t / f).toFixed(4) : '-'
})

async function submitExchange() {
  const lid = ledgerStore.currentId
  if (!lid) return
  if (!ex.value.fromId || !ex.value.toId) return ElMessage.warning('请选择卖出与买入账户')
  if (ex.value.fromId === ex.value.toId) return ElMessage.warning('卖出与买入账户不能相同')
  if (toNum(ex.value.fromAmount) <= 0 || toNum(ex.value.toAmount) <= 0)
    return ElMessage.warning('请输入兑换金额')
  try {
    await api.exchangeTransaction(lid, {
      from_account_id: ex.value.fromId,
      from_amount: String(ex.value.fromAmount),
      to_account_id: ex.value.toId,
      to_amount: String(ex.value.toAmount),
      fee: String(ex.value.fee || 0),
      fee_account_id: ex.value.feeAccountId,
      occurred_at: ex.value.occurredAt,
      remark: ex.value.remark || null
    })
  } catch (e) {
    return ElMessage.error(e instanceof Error ? e.message : '兑换失败')
  }
  ElMessage.success('已记账')
  exchangeVisible.value = false
  emit('saved')
}

// ---------- 余额调整 ----------
const adjustVisible = ref(false)
const adj = ref({
  target: 0,
  mode: 'adjust' as 'adjust' | 'income_expense'
})
const bookBalance = computed(() => toNum(props.account?.current_balance))
const adjDiff = computed(() => toNum(adj.value.target) - bookBalance.value)

function openAdjust() {
  adj.value = { target: bookBalance.value, mode: 'adjust' }
  adjustVisible.value = true
}

async function submitAdjust() {
  if (!props.account) return
  try {
    await api.adjustAccount(props.account.id, Number(adj.value.target), adj.value.mode)
  } catch (e) {
    return ElMessage.error(e instanceof Error ? e.message : '调整失败')
  }
  ElMessage.success('已调整')
  adjustVisible.value = false
  emit('saved')
}

defineExpose({ openSplitEdit })
</script>

<template>
  <span>
    <el-dropdown @command="onCommand">
      <el-button type="primary">记账</el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item v-for="op in ops" :key="op.key" :command="op.key">{{ op.label }}</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <!-- 日常收支 -->
    <el-dialog v-model="dailyVisible" :title="dailyTitle" width="460px" append-to-body>
      <el-form label-width="92px">
        <el-form-item label="收支项目" required>
          <el-select v-model="daily.categoryId" filterable placeholder="选择收支项目" style="width: 100%">
            <el-option v-for="c in dailyCats" :key="c.id" :label="`${c.icon || ''} ${c.name}`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额" required>
          <el-input-number v-model="daily.amount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="收支账户" required>
          <el-select v-model="daily.accountId" filterable placeholder="选择账户" style="width: 100%">
            <el-option v-for="a in accounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="tags && tags.length" label="标签">
          <el-select v-model="daily.tagIds" multiple clearable placeholder="选择标签" style="width: 100%">
            <el-option v-for="tg in tags" :key="tg.id" :label="tg.name" :value="tg.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="daily.occurredAt" type="date" value-format="YYYY-MM-DDT00:00:00" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="daily.remark" type="textarea" :rows="2" placeholder="备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveDaily(true)">保存并继续</el-button>
        <el-button type="primary" @click="saveDaily(false)">确定</el-button>
      </template>
    </el-dialog>

    <!-- 分拆收支 -->
    <el-dialog v-model="splitVisible" :title="splitTitle" width="720px" append-to-body>
      <el-table :data="splitRows" border size="small" style="width: 100%">
        <el-table-column label="收支项目" min-width="180">
          <template #default="{ row }">
            <el-select
              v-model="row.categoryId"
              filterable
              clearable
              placeholder="在此处输入文字以进行过滤"
              style="width: 100%"
              @change="onSplitCategoryChange(row)"
            >
              <el-option-group label="支出">
                <el-option v-for="c in expenseCats" :key="'e' + c.id" :label="`【${c.name}】`" :value="c.id" />
              </el-option-group>
              <el-option-group label="收入">
                <el-option v-for="c in incomeCats" :key="'i' + c.id" :label="`【${c.name}】`" :value="c.id" />
              </el-option-group>
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="收入" width="120">
          <template #default="{ row }">
            <el-input-number
              v-if="rowIsIncome(row)"
              v-model="row.income"
              :min="0"
              :precision="2"
              :controls="false"
              style="width: 100%"
            />
            <span v-else style="color: #c0c4cc">0.00</span>
          </template>
        </el-table-column>
        <el-table-column label="支出" width="120">
          <template #default="{ row }">
            <el-input-number
              v-if="!rowIsIncome(row)"
              v-model="row.expense"
              :min="0"
              :precision="2"
              :controls="false"
              style="width: 100%"
            />
            <span v-else style="color: #c0c4cc">0.00</span>
          </template>
        </el-table-column>
        <el-table-column label="标签" width="140">
          <template #default="{ row }">
            <el-select v-model="row.tagIds" multiple clearable placeholder="标签" style="width: 100%">
              <el-option v-for="tg in tags || []" :key="tg.id" :label="tg.name" :value="tg.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <el-input v-model="row.remark" placeholder="备注" />
          </template>
        </el-table-column>
      </el-table>
      <div style="margin: 8px 0; color: #f56c6c; font-size: 12px; display: flex; justify-content: space-between">
        <span>注意：第一行[收支项目]的类型，将决定此次交易的类型；收支项目选择〈无〉，则删除该条收支记录。</span>
        <span style="color: #303133">总计：{{ splitTotal.toFixed(2) }}</span>
      </div>
      <el-table :data="[{ account: splitAccountId, amount: splitTotal }]" border size="small" style="width: 100%">
        <el-table-column label="收支账户">
          <template #default>
            <el-select v-model="splitAccountId" filterable placeholder="选择账户" style="width: 100%">
              <el-option v-for="a in accounts" :key="a.id" :label="a.name" :value="a.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="160" align="right">
          <template #default>{{ splitTotal.toFixed(2) }}</template>
        </el-table-column>
      </el-table>
      <el-form label-width="92px" style="margin-top: 12px">
        <el-form-item label="日期">
          <el-date-picker v-model="splitOccurredAt" type="date" value-format="YYYY-MM-DDT00:00:00" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="!splitEditGroup" @click="saveSplit(true)">保存并继续</el-button>
        <el-button type="primary" @click="saveSplit(false)">确定</el-button>
      </template>
    </el-dialog>

    <!-- 转账 / 存款 / 取款 -->
    <el-dialog v-model="transferVisible" :title="transferTitle" width="460px" append-to-body>
      <el-form label-width="92px">
        <el-form-item label="转出账户">
          <el-select v-model="tf.fromId" filterable placeholder="选择转出账户" style="width: 100%">
            <el-option v-for="a in accounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="转入账户">
          <el-select v-model="tf.toId" filterable placeholder="选择转入账户" style="width: 100%">
            <el-option v-for="a in accounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="转账金额">
          <el-input-number v-model="tf.amount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="手续费">
          <el-input-number v-model="tf.fee" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="手续费账户">
          <el-select v-model="tf.feeAccountId" clearable placeholder="〈无，从转出账户扣除〉" style="width: 100%">
            <el-option v-for="a in accounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="tf.occurredAt" type="date" value-format="YYYY-MM-DDT00:00:00" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="tags && tags.length" label="标签">
          <el-select v-model="tf.tagIds" multiple clearable placeholder="选择标签" style="width: 100%">
            <el-option v-for="tg in tags" :key="tg.id" :label="tg.name" :value="tg.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="tf.remark" placeholder="备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="transferVisible = false">取消</el-button>
        <el-button type="primary" @click="submitTransfer">保存</el-button>
      </template>
    </el-dialog>

    <!-- 货币兑换 -->
    <el-dialog v-model="exchangeVisible" title="货币兑换" width="460px" append-to-body>
      <el-form label-width="92px">
        <el-form-item label="卖出账户">
          <el-select v-model="ex.fromId" filterable placeholder="选择卖出账户" style="width: 100%">
            <el-option v-for="a in accounts" :key="a.id" :label="`${a.name}（${a.currency}）`" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="卖出金额">
          <el-input-number v-model="ex.fromAmount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="买入账户">
          <el-select v-model="ex.toId" filterable placeholder="选择买入账户" style="width: 100%">
            <el-option v-for="a in accounts" :key="a.id" :label="`${a.name}（${a.currency}）`" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="买入金额">
          <el-input-number v-model="ex.toAmount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="兑换汇率">
          <span style="color: #909399">1 卖出 ≈ {{ exRate }} 买入</span>
        </el-form-item>
        <el-form-item label="手续费">
          <el-input-number v-model="ex.fee" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="手续费账户">
          <el-select v-model="ex.feeAccountId" clearable placeholder="〈无，从卖出账户扣除〉" style="width: 100%">
            <el-option v-for="a in accounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="ex.occurredAt" type="date" value-format="YYYY-MM-DDT00:00:00" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="ex.remark" placeholder="备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="exchangeVisible = false">取消</el-button>
        <el-button type="primary" @click="submitExchange">保存</el-button>
      </template>
    </el-dialog>

    <!-- 余额调整 -->
    <el-dialog v-model="adjustVisible" :title="`余额调整 · ${account?.name || ''}`" width="420px" append-to-body>
      <el-form label-width="92px">
        <el-form-item label="账面余额">
          <span>{{ bookBalance.toFixed(2) }}</span>
        </el-form-item>
        <el-form-item label="真实余额">
          <el-input-number v-model="adj.target" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="差额">
          <span :style="{ color: adjDiff < 0 ? '#f56c6c' : '#67c23a' }">{{ adjDiff.toFixed(2) }}</span>
        </el-form-item>
        <el-form-item label="差额记为">
          <el-radio-group v-model="adj.mode">
            <el-radio value="adjust">余额调整</el-radio>
            <el-radio value="income_expense">收入/支出</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAdjust">保存</el-button>
      </template>
    </el-dialog>
  </span>
</template>
