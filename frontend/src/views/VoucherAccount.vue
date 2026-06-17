<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useVoucherStore } from '../stores/voucher'
import type { Account, Category, Transaction, Tag, Voucher } from '../types'
import { fmtMoney } from '../utils/format'

const route = useRoute()
const ledgerStore = useLedgerStore()
const voucherStore = useVoucherStore()

const accounts = ref<Account[]>([])
const categories = ref<Category[]>([])
const tags = ref<Tag[]>([])
const vouchers = ref<Voucher[]>([])
const transactions = ref<Transaction[]>([])
const selectedAccountId = ref<number | null>(null)
const bottomTab = ref<'vouchers' | 'txns'>('vouchers')

const voucherAccounts = computed(() => accounts.value.filter((a) => a.type === 'voucher'))
const selectedAccount = computed(() => accounts.value.find((a) => a.id === selectedAccountId.value) || null)

// 购买资金账户 / 补差价账户：现金、储蓄卡、第三方储值等
const FUNDING_TYPES = ['cash', 'bank', 'wallet', 'prepaid']
const fundingAccounts = computed(() => accounts.value.filter((a) => FUNDING_TYPES.includes(a.type)))
const expenseCategories = computed(() => categories.value.filter((c) => c.kind === 'expense'))

const fmt = (v: string | number | null | undefined) => fmtMoney(v)
const fmtDate = (v: string | null | undefined) => (v || '').slice(0, 10)
const toNum = (v: string | number | null | undefined) => Number(v || 0)

const STATUS_TEXT: Record<string, string> = {
  active: '有效', used: '已用完', expired: '已过期', refunded: '已退货'
}
function statusText(v: Voucher): string {
  if (v.status === 'active' && v.is_expired) return '已过期待退货'
  return STATUS_TEXT[v.status] || v.status
}
function statusType(v: Voucher): string {
  if (v.status === 'refunded') return 'info'
  if (v.status === 'used') return 'success'
  if (v.is_expired) return 'danger'
  return 'warning'
}

const accountVouchers = computed(() =>
  selectedAccountId.value ? vouchers.value.filter((v) => v.account_id === selectedAccountId.value) : []
)

const summary = computed(() => {
  let remainingValue = 0
  let discount = 0
  let activeCount = 0
  for (const v of accountVouchers.value) {
    remainingValue += toNum(v.occupied_value)
    if (v.status !== 'refunded') discount += toNum(v.discount)
    if (v.status === 'active') activeCount += v.remaining
  }
  const avail = toNum(selectedAccount.value?.current_balance)
  return { remainingValue, discount, activeCount, avail }
})

function categoryName(id?: number | null): string {
  return categories.value.find((c) => c.id === id)?.name || ''
}
const tagName = (id: number) => tags.value.find((t) => t.id === id)?.name || ''
const txnTags = (t: Transaction) => (t.tag_ids || []).map(tagName).filter(Boolean).join('、')

const accountTxns = computed(() =>
  selectedAccountId.value
    ? transactions.value.filter(
        (t) => t.account_id === selectedAccountId.value || t.to_account_id === selectedAccountId.value
      )
    : []
)

function txnActivity(t: Transaction): string {
  if (t.type === 'transfer') {
    return t.to_account_id === selectedAccountId.value ? '购券' : '退券退款'
  }
  if (t.type === 'adjust') {
    return toNum(t.amount) >= 0 ? '购券' : '退券'
  }
  if (t.type === 'expense') {
    return t.account_id === selectedAccountId.value ? '核销' : '核销补差价'
  }
  const cat = categoryName(t.category_id)
  return cat ? `【${cat}】` : (t.type === 'income' ? '收入' : '支出')
}

// 判断某交易记录可以用哪种「修改」界面
function txnEditKind(t: Transaction): 'buy' | 'redeem' | 'refund' | null {
  if (!t.voucher_id) return null
  const vid = selectedAccountId.value
  if (t.type === 'expense' && t.account_id === vid) return 'redeem'
  if (t.type === 'transfer' && t.to_account_id === vid) return 'buy'
  if (t.type === 'adjust' && toNum(t.amount) >= 0) return 'buy'
  if (t.type === 'transfer' && t.account_id === vid) return 'refund'
  if (t.type === 'adjust' && toNum(t.amount) < 0) return 'refund'
  return null
}
function onEditTxn(t: Transaction) {
  const k = txnEditKind(t)
  if (k === 'buy') return openBuyEdit(t)
  if (k === 'redeem') return openRedeemEdit(t)
  if (k === 'refund') return openRefundEdit(t)
  ElMessage.info('该记录暂不支持修改')
}

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  const exp = await api.listCategories(lid, 'expense')
  const inc = await api.listCategories(lid, 'income')
  categories.value = [...exp, ...inc]
  tags.value = await api.listTags(lid)
  const qid = route.query.account_id ? Number(route.query.account_id) : null
  if (qid && voucherAccounts.value.some((a) => a.id === qid)) {
    selectedAccountId.value = qid
  } else if (!selectedAccountId.value && voucherAccounts.value.length) {
    selectedAccountId.value = voucherAccounts.value[0].id
  }
  await loadVouchers()
  await loadTxns()
}

async function loadVouchers() {
  const lid = ledgerStore.currentId
  if (!lid) {
    vouchers.value = []
    return
  }
  vouchers.value = await api.listVouchers(lid, selectedAccountId.value ?? undefined)
}

async function loadTxns() {
  const lid = ledgerStore.currentId
  if (!lid || !selectedAccountId.value) {
    transactions.value = []
    return
  }
  const res = await api.listTransactions(lid, { account_id: selectedAccountId.value, page_size: 500 })
  transactions.value = res.items
}

// ---------------- 购券（新增 / 修改） ----------------
const buyDialog = ref(false)
const savingBuy = ref(false)
const buyEditTxnId = ref<number | null>(null)
const buyMinQty = ref(1)
const buyForm = reactive<{
  product: string
  quantity: number | null
  face_value: number | null
  unit_price: number | null
  source_account_id: number | null
  purchased_at: string
  expiry_at: string
  category_id: number | null
  remark: string
  tag_ids: number[]
}>({
  product: '', quantity: 1, face_value: null, unit_price: null,
  source_account_id: null, purchased_at: '', expiry_at: '',
  category_id: null, remark: '', tag_ids: []
})
const buyTitle = computed(() => (buyEditTxnId.value ? '修改购券' : '购券'))

function resetBuyForm() {
  buyForm.product = ''
  buyForm.quantity = 1
  buyForm.face_value = null
  buyForm.unit_price = null
  buyForm.source_account_id = fundingAccounts.value[0]?.id ?? null
  buyForm.purchased_at = new Date().toISOString().slice(0, 10)
  buyForm.expiry_at = ''
  buyForm.category_id = null
  buyForm.remark = ''
  buyForm.tag_ids = []
}

function openBuy() {
  if (!voucherAccounts.value.length) {
    ElMessage.warning('请先创建一个「团购券」类型的账户')
    return
  }
  buyEditTxnId.value = null
  buyMinQty.value = 1
  resetBuyForm()
  buyDialog.value = true
}

function openBuyEdit(t: Transaction) {
  const v = vouchers.value.find((x) => x.id === t.voucher_id)
  if (!v) return ElMessage.info('未找到对应的团购券')
  buyEditTxnId.value = t.id
  buyMinQty.value = Math.max(v.redeemed || 0, 1)
  selectedAccountId.value = v.account_id
  buyForm.product = v.product
  buyForm.quantity = v.quantity
  buyForm.face_value = toNum(v.face_value)
  buyForm.unit_price = toNum(v.unit_price)
  buyForm.source_account_id = v.source_account_id ?? null
  buyForm.purchased_at = fmtDate(v.purchased_at)
  buyForm.expiry_at = fmtDate(v.expiry_at)
  buyForm.category_id = v.category_id ?? null
  // 修改即按新内容重建该券：不沿用原券备注（避免带入“忘记使用，已过期”等旧状态说明）
  buyForm.remark = ''
  buyForm.tag_ids = t.tag_ids ? [...t.tag_ids] : []
  buyDialog.value = true
}

async function submitBuy() {
  const lid = ledgerStore.currentId
  if (!lid || !selectedAccountId.value) return
  if (!buyForm.product.trim()) return ElMessage.warning('请输入商品名称')
  if (!buyForm.quantity || buyForm.quantity <= 0) return ElMessage.warning('请输入购买张数')
  if (buyForm.unit_price == null || buyForm.unit_price < 0) return ElMessage.warning('请输入实付单价')
  savingBuy.value = true
  try {
    await api.voucherBuy(lid, {
      account_id: selectedAccountId.value,
      product: buyForm.product.trim(),
      quantity: buyForm.quantity,
      unit_price: Number(buyForm.unit_price).toFixed(2),
      face_value: buyForm.face_value != null ? Number(buyForm.face_value).toFixed(2) : undefined,
      source_account_id: buyForm.source_account_id ?? undefined,
      purchased_at: buyForm.purchased_at || undefined,
      expiry_at: buyForm.expiry_at || undefined,
      category_id: buyForm.category_id ?? undefined,
      remark: buyForm.remark || undefined,
      tag_ids: buyForm.tag_ids,
      edit_txn_id: buyEditTxnId.value ?? undefined
    })
    ElMessage.success(buyEditTxnId.value ? '已修改购券' : '购券成功')
    buyDialog.value = false
    voucherStore.markSaved()
    await load()
  } finally {
    savingBuy.value = false
  }
}

// ---------------- 核销（新增 / 修改） ----------------
const redeemDialog = ref(false)
const savingRedeem = ref(false)
const redeemTarget = ref<Voucher | null>(null)
const redeemEditTxnId = ref<number | null>(null)
const redeemEditOldQty = ref(0)
const redeemForm = reactive<{
  quantity: number | null
  category_id: number | null
  topup: number | null
  topup_account_id: number | null
  occurred_at: string
  remark: string
}>({ quantity: 1, category_id: null, topup: 0, topup_account_id: null, occurred_at: '', remark: '' })
const redeemTitle = computed(() => (redeemEditTxnId.value ? '修改核销' : '核销'))
const redeemMax = computed(() =>
  redeemTarget.value ? redeemTarget.value.remaining + (redeemEditTxnId.value ? redeemEditOldQty.value : 0) : 1
)

function openRedeem(v: Voucher) {
  if (v.is_expired) return ElMessage.info('该券已过期，只能退货')
  if (v.remaining <= 0) return ElMessage.info('该券没有可核销的剩余张数')
  redeemTarget.value = v
  redeemEditTxnId.value = null
  redeemEditOldQty.value = 0
  redeemForm.quantity = 1
  redeemForm.category_id = v.category_id ?? null
  redeemForm.topup = 0
  redeemForm.topup_account_id = fundingAccounts.value[0]?.id ?? null
  redeemForm.occurred_at = new Date().toISOString().slice(0, 10)
  redeemForm.remark = ''
  redeemDialog.value = true
}

async function openRedeemEdit(t: Transaction) {
  const v = vouchers.value.find((x) => x.id === t.voucher_id)
  if (!v) return ElMessage.info('未找到对应的团购券')
  redeemTarget.value = v
  redeemEditTxnId.value = t.id
  redeemEditOldQty.value = t.trade_qty ? Number(t.trade_qty) : 1
  redeemForm.quantity = redeemEditOldQty.value
  redeemForm.category_id = t.category_id ?? v.category_id ?? null
  redeemForm.occurred_at = fmtDate(t.occurred_at)
  redeemForm.remark = (t.remark || '').startsWith('核销：') ? '' : (t.remark || '')
  redeemForm.topup = 0
  redeemForm.topup_account_id = fundingAccounts.value[0]?.id ?? null
  // 补差价记在资金账户，需从全量流水按 split_group 找到兄弟记录回填
  if (t.split_group) {
    const lid = ledgerStore.currentId
    if (lid) {
      const all = await api.listTransactions(lid, { page_size: 1000 })
      const sib = all.items.find((x) => x.split_group === t.split_group && x.id !== t.id)
      if (sib) {
        redeemForm.topup = toNum(sib.amount)
        redeemForm.topup_account_id = sib.account_id
      }
    }
  }
  redeemDialog.value = true
}

async function submitRedeem() {
  const lid = ledgerStore.currentId
  if (!lid || !redeemTarget.value) return
  const k = Number(redeemForm.quantity)
  if (!k || k <= 0) return ElMessage.warning('请输入核销张数')
  if (k > redeemMax.value) return ElMessage.warning('核销张数超过剩余')
  savingRedeem.value = true
  try {
    await api.voucherRedeem(lid, redeemTarget.value.id, {
      quantity: k,
      category_id: redeemForm.category_id ?? undefined,
      topup: redeemForm.topup ? Number(redeemForm.topup).toFixed(2) : '0',
      topup_account_id: redeemForm.topup && Number(redeemForm.topup) > 0 ? redeemForm.topup_account_id ?? undefined : undefined,
      occurred_at: redeemForm.occurred_at || undefined,
      remark: redeemForm.remark || undefined,
      edit_txn_id: redeemEditTxnId.value ?? undefined
    })
    ElMessage.success(redeemEditTxnId.value ? '已修改核销' : '核销成功')
    redeemDialog.value = false
    voucherStore.markSaved()
    await load()
  } finally {
    savingRedeem.value = false
  }
}

// ---------------- 退货（新增 confirm / 修改 dialog） ----------------
const refundDialog = ref(false)
const savingRefund = ref(false)
const refundTarget = ref<Voucher | null>(null)
const refundEditTxnId = ref<number | null>(null)
const refundAmount = ref(0)
const refundForm = reactive<{ occurred_at: string; remark: string }>({ occurred_at: '', remark: '' })

async function onRefund(v: Voucher) {
  const lid = ledgerStore.currentId
  if (!lid) return
  if (v.remaining <= 0) return ElMessage.info('该券没有可退的剩余张数')
  const target = accounts.value.find((a) => a.id === v.source_account_id)
  const tip = target ? `退款将退回至「${target.name}」` : '该券无原购买账户，将仅冲减团购券账户余额'
  await ElMessageBox.confirm(
    `确定将「${v.product}」剩余 ${v.remaining} 张退货吗？${tip}。`,
    '退货', { type: 'warning' }
  )
  await api.voucherRefund(lid, v.id, {})
  ElMessage.success('已退货')
  voucherStore.markSaved()
  await load()
}

function openRefundEdit(t: Transaction) {
  const v = vouchers.value.find((x) => x.id === t.voucher_id)
  if (!v) return ElMessage.info('未找到对应的团购券')
  refundTarget.value = v
  refundEditTxnId.value = t.id
  refundAmount.value = toNum(t.amount)
  refundForm.occurred_at = fmtDate(t.occurred_at)
  refundForm.remark = (t.remark || '').startsWith('退券：') ? '' : (t.remark || '')
  refundDialog.value = true
}

async function submitRefundEdit() {
  const lid = ledgerStore.currentId
  if (!lid || !refundTarget.value) return
  savingRefund.value = true
  try {
    await api.voucherRefund(lid, refundTarget.value.id, {
      occurred_at: refundForm.occurred_at || undefined,
      remark: refundForm.remark || undefined,
      edit_txn_id: refundEditTxnId.value ?? undefined
    })
    ElMessage.success('已修改退货')
    refundDialog.value = false
    voucherStore.markSaved()
    await load()
  } finally {
    savingRefund.value = false
  }
}

const refundTargetName = computed(() =>
  accounts.value.find((a) => a.id === refundTarget.value?.source_account_id)?.name || '原购买账户'
)

async function onDeleteVoucher(v: Voucher) {
  await ElMessageBox.confirm(
    `确定删除「${v.product}」吗？该券的购券、核销、退货流水将一并删除并回滚余额。`,
    '删除团购券', { type: 'warning' }
  )
  await api.deleteVoucher(v.id)
  ElMessage.success('已删除')
  voucherStore.markSaved()
  await load()
}

async function onDeleteTxn(row: Transaction) {
  await ElMessageBox.confirm('确定删除这笔交易记录？相关券状态会同步回滚。', '提示', { type: 'warning' })
  await api.deleteTransaction(row.id)
  ElMessage.success('已删除')
  voucherStore.markSaved()
  await load()
}

watch(
  () => route.query.account_id,
  (v) => {
    if (v) selectedAccountId.value = Number(v)
  },
  { immediate: true }
)

onMounted(load)
watch(() => ledgerStore.currentId, load)
watch(() => voucherStore.buyTick, () => {
  if (voucherStore.presetAccountId) selectedAccountId.value = voucherStore.presetAccountId
  openBuy()
})
watch(selectedAccountId, async () => {
  await loadVouchers()
  await loadTxns()
})
</script>

<template>
  <div class="voucher-page">
    <!-- 团购券汇总 -->
    <div class="panel">
      <div class="panel-head">
        <span class="panel-title">{{ selectedAccount?.name || '团购券账户' }}</span>
        <span class="panel-balance" :class="{ neg: summary.avail < 0 }">{{ fmt(summary.avail) }}</span>
        <div class="head-spacer" />
        <el-select v-if="voucherAccounts.length > 1" v-model="selectedAccountId" size="small" style="width:160px">
          <el-option v-for="a in voucherAccounts" :key="a.id" :label="a.name" :value="a.id" />
        </el-select>
        <el-button size="small" type="primary" @click="openBuy">购券</el-button>
      </div>

      <div class="voucher-summary">
        <div class="sum-item"><span class="lbl">剩余券价值</span><span class="val">{{ fmt(summary.remainingValue) }}</span></div>
        <div class="sum-item"><span class="lbl">剩余张数</span><span class="val">{{ summary.activeCount }}</span></div>
        <div class="sum-item"><span class="lbl">累计已优惠</span><span class="val pos">{{ fmt(summary.discount) }}</span></div>
        <div class="sum-item"><span class="lbl">账户余额</span><span class="val" :class="{ neg: summary.avail < 0 }">{{ fmt(summary.avail) }}</span></div>
      </div>
    </div>

    <!-- 券列表 / 交易明细 -->
    <div class="panel">
      <el-tabs v-model="bottomTab">
        <el-tab-pane label="券明细" name="vouchers">
          <el-table :data="accountVouchers" size="small" border>
            <el-table-column label="商品名称" min-width="180" fixed="left">
              <template #default="{ row }">{{ row.product }}</template>
            </el-table-column>
            <el-table-column label="面值" align="right" min-width="100">
              <template #default="{ row }">{{ fmt(row.face_value) }}</template>
            </el-table-column>
            <el-table-column label="实付" align="right" min-width="100">
              <template #default="{ row }">{{ fmt(row.unit_price) }}</template>
            </el-table-column>
            <el-table-column label="张数" align="right" min-width="70">
              <template #default="{ row }">{{ row.quantity }}</template>
            </el-table-column>
            <el-table-column label="已核销" align="right" min-width="80">
              <template #default="{ row }">{{ row.redeemed }}</template>
            </el-table-column>
            <el-table-column label="剩余" align="right" min-width="70">
              <template #default="{ row }">{{ row.remaining }}</template>
            </el-table-column>
            <el-table-column label="剩余价值" align="right" min-width="110">
              <template #default="{ row }">{{ fmt(row.occupied_value) }}</template>
            </el-table-column>
            <el-table-column label="有效期" min-width="120">
              <template #default="{ row }">{{ fmtDate(row.expiry_at) || '—' }}</template>
            </el-table-column>
            <el-table-column label="状态" min-width="110" align="center">
              <template #default="{ row }">
                <el-tag :type="statusType(row)" size="small" effect="light">{{ statusText(row) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="190" fixed="right" align="center">
              <template #default="{ row }">
                <el-button v-if="row.status === 'active' && !row.is_expired" link type="primary" size="small" @click="openRedeem(row)">核销</el-button>
                <el-button v-if="row.status === 'active' && row.remaining > 0" link type="warning" size="small" @click="onRefund(row)">退货</el-button>
                <el-button link type="danger" size="small" @click="onDeleteVoucher(row)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty>当前账户暂无团购券，点击「购券」开始记账</template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="交易明细" name="txns">
          <el-table :data="accountTxns" size="small" border>
            <el-table-column label="日期" min-width="110" fixed="left">
              <template #default="{ row }">{{ fmtDate(row.occurred_at) }}</template>
            </el-table-column>
            <el-table-column label="交易金额" align="right" min-width="120">
              <template #default="{ row }">{{ fmt(row.amount) }}</template>
            </el-table-column>
            <el-table-column label="活动类型" min-width="120">
              <template #default="{ row }">{{ txnActivity(row) }}</template>
            </el-table-column>
            <el-table-column label="标签" min-width="120">
              <template #default="{ row }">{{ txnTags(row) }}</template>
            </el-table-column>
            <el-table-column label="备注" min-width="180">
              <template #default="{ row }">{{ row.remark }}</template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right" align="center">
              <template #default="{ row }">
                <el-button v-if="txnEditKind(row)" link type="primary" size="small" @click="onEditTxn(row)">修改</el-button>
                <el-button link type="danger" size="small" @click="onDeleteTxn(row)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty>当前账户暂无交易记录</template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 购券 / 修改购券（横板） -->
    <el-dialog v-model="buyDialog" :title="buyTitle" width="92%" style="max-width:760px" :close-on-click-modal="false">
      <el-alert v-if="buyEditTxnId" type="info" :closable="false" show-icon
                title="修改购券会按新的单价 / 张数重算该券的核销、退货金额；已有的核销 / 退货记录保留。" style="margin-bottom:12px" />
      <el-form label-width="92px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="团购券账户">
              <el-select v-model="selectedAccountId" style="width:100%">
                <el-option v-for="a in voucherAccounts" :key="a.id" :label="a.name" :value="a.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="商品名称" required>
              <el-input v-model="buyForm.product" placeholder="如：XX火锅双人套餐" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="购买张数" required>
              <el-input-number v-model="buyForm.quantity" :min="buyMinQty" :precision="0" :controls="false" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="资金账户">
              <el-select v-model="buyForm.source_account_id" clearable placeholder="支付账户（= 退货退款目标）" style="width:100%">
                <el-option v-for="a in fundingAccounts" :key="a.id" :label="a.name" :value="a.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="面值/张">
              <el-input-number v-model="buyForm.face_value" :min="0" :precision="2" :controls="false" style="width:100%" placeholder="实际价值，选填" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="实付/张" required>
              <el-input-number v-model="buyForm.unit_price" :min="0" :precision="2" :controls="false" style="width:100%" placeholder="优惠后单价" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="购买日">
              <el-date-picker v-model="buyForm.purchased_at" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="有效期至">
              <el-date-picker v-model="buyForm.expiry_at" type="date" value-format="YYYY-MM-DD" style="width:100%" placeholder="到期未用可退货" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="核销分类">
              <el-select v-model="buyForm.category_id" clearable placeholder="默认核销时记入的支出分类" style="width:100%">
                <el-option v-for="c in expenseCategories" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="标签">
              <el-select v-model="buyForm.tag_ids" multiple clearable placeholder="选填" style="width:100%">
                <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="buyForm.remark" placeholder="选填" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="buyDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingBuy" @click="submitBuy">确定</el-button>
      </template>
    </el-dialog>

    <!-- 核销 / 修改核销（横板） -->
    <el-dialog v-model="redeemDialog" :title="redeemTitle" width="92%" style="max-width:680px" :close-on-click-modal="false">
      <el-form v-if="redeemTarget" label-width="92px">
        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="商品">
              <span>{{ redeemTarget.product }}（可核销 {{ redeemMax }} 张 · 实付 {{ fmt(redeemTarget.unit_price) }}/张）</span>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="核销张数" required>
              <el-input-number v-model="redeemForm.quantity" :min="1" :max="redeemMax" :precision="0" :controls="false" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="支出分类">
              <el-select v-model="redeemForm.category_id" clearable placeholder="本次消费记入的分类" style="width:100%">
                <el-option v-for="c in expenseCategories" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="补差价">
              <el-input-number v-model="redeemForm.topup" :min="0" :precision="2" :controls="false" style="width:100%" placeholder="消费超出券值时额外支付" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item v-if="redeemForm.topup && Number(redeemForm.topup) > 0" label="补差账户">
              <el-select v-model="redeemForm.topup_account_id" placeholder="补差价的支付账户" style="width:100%">
                <el-option v-for="a in fundingAccounts" :key="a.id" :label="a.name" :value="a.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="日期">
              <el-date-picker v-model="redeemForm.occurred_at" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="备注">
              <el-input v-model="redeemForm.remark" placeholder="选填" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="redeemDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingRedeem" @click="submitRedeem">确定</el-button>
      </template>
    </el-dialog>

    <!-- 修改退货（横板） -->
    <el-dialog v-model="refundDialog" title="修改退货" width="92%" style="max-width:600px" :close-on-click-modal="false">
      <el-form v-if="refundTarget" label-width="92px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="商品">
              <span>{{ refundTarget.product }}</span>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="退款金额">
              <span>{{ fmt(refundAmount) }} → {{ refundTargetName }}</span>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="退货日期">
              <el-date-picker v-model="refundForm.occurred_at" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="备注">
              <el-input v-model="refundForm.remark" placeholder="选填" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="refundDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingRefund" @click="submitRefundEdit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.voucher-page { padding: 12px 16px; display: flex; flex-direction: column; gap: 14px; }
.panel { background: #fff; border: 1px solid #ebeef2; border-radius: 8px; padding: 12px 14px; }
.panel-head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.panel-title { font-size: 16px; font-weight: 600; color: #3c4b59; }
.panel-balance { font-size: 18px; font-weight: 700; color: #2e9c4f; }
.panel-balance.neg { color: #f56c6c; }
.head-spacer { flex: 1; }
.voucher-summary { display: flex; flex-wrap: wrap; gap: 28px; margin-top: 4px; padding: 10px 16px; background: #f7f8fa; border-radius: 6px; }
.sum-item { display: flex; flex-direction: column; gap: 2px; }
.sum-item .lbl { font-size: 12px; color: #909399; }
.sum-item .val { font-size: 15px; font-weight: 600; color: #303133; }
.pos { color: #f56c6c; }
.neg { color: #f56c6c; }
</style>
