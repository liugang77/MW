<script setup lang="ts">
import { ref, onMounted, watch, computed, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useRecordStore } from '../stores/record'
import type { Account, Category, Tag } from '../types'

const ledgerStore = useLedgerStore()
const recordStore = useRecordStore()

const type = ref('expense')
const amount = ref('')
const accountId = ref<number | null>(null)
const toAccountId = ref<number | null>(null)
const categoryId = ref<number | null>(null)
const remark = ref('')
const merchant = ref('')
const tagIds = ref<number[]>([])
const occurredAt = ref<string>(new Date().toISOString().slice(0, 10) + 'T00:00:00')
const suppressWatch = ref(false)

const accounts = ref<Account[]>([])
const expenseCats = ref<Category[]>([])
const incomeCats = ref<Category[]>([])
const tags = ref<Tag[]>([])

const categories = computed(() => (type.value === 'income' ? incomeCats.value : expenseCats.value))
const selectedAccount = computed(() => accounts.value.find((a) => a.id === accountId.value) || null)

type TemplateType = 'expense' | 'income' | 'transfer'
interface TxTemplate {
  key: string
  label: string
  txType: TemplateType
  hint: string
  remarkPrefix: string
}

const templateMap: Record<string, TxTemplate[]> = {
  credit: [
    { key: 'credit-consume', label: '刷卡消费', txType: 'expense', hint: '信用卡日常消费', remarkPrefix: '刷卡消费' },
    { key: 'credit-repay', label: '还信用卡', txType: 'transfer', hint: '从储蓄账户还款', remarkPrefix: '信用卡还款' },
    { key: 'credit-cashout', label: '信用取现', txType: 'expense', hint: '信用额度取现', remarkPrefix: '信用卡取现' },
    { key: 'credit-installment', label: '分期还款', txType: 'expense', hint: '分期账单归还', remarkPrefix: '分期还款' }
  ],
  bank: [
    { key: 'bank-deposit', label: '存款', txType: 'income', hint: '资金转入银行', remarkPrefix: '存款' },
    { key: 'bank-withdraw', label: '取款', txType: 'expense', hint: '银行提现/取现', remarkPrefix: '取款' },
    { key: 'bank-transfer', label: '转账', txType: 'transfer', hint: '银行账户转账', remarkPrefix: '银行转账' },
    { key: 'bank-income', label: '利息收入', txType: 'income', hint: '银行利息或返现', remarkPrefix: '利息收入' }
  ],
  cash: [
    { key: 'cash-spend', label: '现金支出', txType: 'expense', hint: '线下现金消费', remarkPrefix: '现金支出' },
    { key: 'cash-income', label: '现金收入', txType: 'income', hint: '临时现金收入', remarkPrefix: '现金收入' },
    { key: 'cash-transfer', label: '现金转账', txType: 'transfer', hint: '现金转入账户', remarkPrefix: '现金转账' }
  ],
  wallet: [
    { key: 'wallet-pay', label: '扫码支付', txType: 'expense', hint: '微信/支付宝支付', remarkPrefix: '扫码支付' },
    { key: 'wallet-refund', label: '退款到账', txType: 'income', hint: '电商/外卖退款', remarkPrefix: '退款到账' },
    { key: 'wallet-transfer', label: '钱包转账', txType: 'transfer', hint: '钱包与银行卡互转', remarkPrefix: '钱包转账' }
  ],
  stock: [
    { key: 'stock-buy', label: '买入证券', txType: 'expense', hint: '股票或ETF买入', remarkPrefix: '买入证券' },
    { key: 'stock-sell', label: '卖出证券', txType: 'income', hint: '股票或ETF卖出', remarkPrefix: '卖出证券' },
    { key: 'stock-dividend', label: '分红到账', txType: 'income', hint: '分红/红利收入', remarkPrefix: '分红到账' }
  ],
  fund: [
    { key: 'fund-buy', label: '申购基金', txType: 'expense', hint: '基金申购/定投', remarkPrefix: '申购基金' },
    { key: 'fund-redeem', label: '赎回基金', txType: 'income', hint: '基金赎回到账', remarkPrefix: '赎回基金' }
  ],
  loan: [
    { key: 'loan-borrow', label: '借入资金', txType: 'income', hint: '新增贷款/借款', remarkPrefix: '借入资金' },
    { key: 'loan-repay', label: '归还贷款', txType: 'expense', hint: '偿还贷款本金', remarkPrefix: '归还贷款' }
  ]
}

const defaultTemplates: TxTemplate[] = [
  { key: 'normal-expense', label: '日常支出', txType: 'expense', hint: '普通消费场景', remarkPrefix: '日常支出' },
  { key: 'normal-income', label: '日常收入', txType: 'income', hint: '普通收入场景', remarkPrefix: '日常收入' },
  { key: 'normal-transfer', label: '账户转账', txType: 'transfer', hint: '账户间资金调拨', remarkPrefix: '账户转账' }
]

const templates = computed(() => {
  const t = selectedAccount.value?.type || ''
  return templateMap[t] || defaultTemplates
})
const activeTemplate = ref('')

async function loadMeta() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  expenseCats.value = await api.listCategories(lid, 'expense')
  incomeCats.value = await api.listCategories(lid, 'income')
  tags.value = await api.listTags(lid)
  if (accounts.value.length && !accountId.value) accountId.value = accounts.value[0].id
  applyStoreTemplate()
}

async function createTag(name: string) {
  const lid = ledgerStore.currentId
  if (!lid || !name) return
  const t = await api.createTag(lid, { name })
  tags.value.push(t)
  tagIds.value.push(t.id)
}

async function quickAddTag() {
  try {
    const { value } = await ElMessageBox.prompt('输入标签名称', '新增标签', {
      inputValidator: (v) => !!v || '请输入名称'
    })
    await createTag(value)
  } catch (e) { /* cancelled */ }
}

function applyStoreTemplate() {
  if (recordStore.editing) {
    populateFromEditing()
    return
  }
  const qAccount = Number(recordStore.accountId || 0)
  const qTpl = recordStore.template || ''
  if (qAccount && accounts.value.some((a) => a.id === qAccount)) {
    accountId.value = qAccount
  }
  if (!qTpl) return
  const picked = templates.value.find((t) => t.key === qTpl)
  if (picked) {
    useTemplate(picked)
  }
}

function populateFromEditing() {
  const t = recordStore.editing
  if (!t) return
  suppressWatch.value = true
  type.value = t.type
  amount.value = String(t.amount ?? '')
  accountId.value = t.account_id ?? null
  toAccountId.value = t.to_account_id ?? null
  categoryId.value = t.category_id ?? null
  remark.value = t.remark || ''
  merchant.value = t.merchant || ''
  tagIds.value = Array.isArray(t.tag_ids) ? [...t.tag_ids] : []
  activeTemplate.value = ''
  occurredAt.value = (t.occurred_at || '').slice(0, 19) || (new Date().toISOString().slice(0, 10) + 'T00:00:00')
  nextTick(() => { suppressWatch.value = false })
}

function resetForm() {
  type.value = 'expense'
  amount.value = ''
  toAccountId.value = null
  categoryId.value = null
  remark.value = ''
  merchant.value = ''
  tagIds.value = []
  activeTemplate.value = ''
  occurredAt.value = new Date().toISOString().slice(0, 10) + 'T00:00:00'
}

function useTemplate(t: TxTemplate) {
  activeTemplate.value = t.key
  type.value = t.txType
  remark.value = t.remarkPrefix
  if (t.txType !== 'transfer') toAccountId.value = null
}

async function submit() {
  if (!amount.value || Number(amount.value) <= 0) return ElMessage.warning('请输入金额')
  if (!accountId.value) return ElMessage.warning('请选择账户')
  if (type.value === 'transfer' && !toAccountId.value) return ElMessage.warning('请选择转入账户')

  const data = {
    type: type.value,
    amount: amount.value,
    account_id: accountId.value,
    to_account_id: type.value === 'transfer' ? toAccountId.value : null,
    category_id: type.value === 'transfer' ? null : categoryId.value,
    remark: remark.value || null,
    merchant: merchant.value || null,
    tag_ids: type.value === 'transfer' ? [] : tagIds.value,
    occurred_at: occurredAt.value
  }
  if (recordStore.editing) {
    await api.updateTransaction(recordStore.editing.id, data)
    ElMessage.success('已保存修改')
  } else {
    try {
      await api.createTransaction(ledgerStore.currentId as number, data)
    } catch (e) {
      return ElMessage.error(e instanceof Error ? e.message : '记账失败')
    }
    ElMessage.success('记账成功')
  }
  recordStore.markSaved()
}

// 分拆收支
const splitDialog = ref(false)
const splitType = ref('expense')
const splitAccountId = ref<number | null>(null)
const splitItems = ref<{ category_id: number | null; amount: string; remark: string }[]>([])
const splitCats = computed(() => (splitType.value === 'income' ? incomeCats.value : expenseCats.value))
const splitTotal = computed(() => splitItems.value.reduce((s, i) => s + Number(i.amount || 0), 0))

function openSplit() {
  splitType.value = 'expense'
  splitAccountId.value = accountId.value
  splitItems.value = [
    { category_id: null, amount: '', remark: '' },
    { category_id: null, amount: '', remark: '' }
  ]
  splitDialog.value = true
}
function addSplitRow() { splitItems.value.push({ category_id: null, amount: '', remark: '' }) }
function removeSplitRow(i: number) { splitItems.value.splice(i, 1) }

async function submitSplit() {
  if (!splitAccountId.value) return ElMessage.warning('请选择账户')
  const items = splitItems.value.filter((i) => i.category_id && Number(i.amount) > 0)
  if (items.length < 2) return ElMessage.warning('至少填写两条明细')
  await api.splitTransaction(ledgerStore.currentId as number, {
    type: splitType.value,
    account_id: splitAccountId.value,
    occurred_at: occurredAt.value,
    items: items.map((i) => ({ category_id: i.category_id as number, amount: i.amount, remark: i.remark || undefined }))
  })
  ElMessage.success('分拆记账成功')
  splitDialog.value = false
  recordStore.markSaved()
}

// 待摊费用
const deferredDialog = ref(false)
const deferredForm = ref<any>({ name: '', account_id: null, category_id: null, total: '', periods: 12, remark: '' })

function openDeferred() {
  deferredForm.value = { name: '', account_id: accountId.value, category_id: null, total: '', periods: 12, remark: '' }
  deferredDialog.value = true
}

async function submitDeferred() {
  const f = deferredForm.value
  if (!f.name) return ElMessage.warning('请输入名称')
  if (!f.account_id) return ElMessage.warning('请选择支付账户')
  if (!f.category_id) return ElMessage.warning('请选择分类')
  if (!(Number(f.total) > 0)) return ElMessage.warning('请输入总金额')
  if (!(Number(f.periods) >= 1)) return ElMessage.warning('期数至少 1')
  await api.deferredExpense(ledgerStore.currentId as number, {
    name: f.name, account_id: f.account_id, category_id: f.category_id,
    total: f.total, periods: Number(f.periods), remark: f.remark || undefined
  })
  ElMessage.success('待摊费用已创建')
  deferredDialog.value = false
  recordStore.markSaved()
}

onMounted(() => { if (recordStore.visible) loadMeta() })
watch(() => ledgerStore.currentId, () => { if (recordStore.visible) loadMeta() })
watch(() => recordStore.visible, (v) => {
  if (v) { resetForm(); loadMeta() }
})
watch(type, () => { if (!suppressWatch.value) categoryId.value = null })
watch(accountId, () => { if (!suppressWatch.value) activeTemplate.value = '' })
</script>

<template>
  <el-dialog
    v-model="recordStore.visible"
    :title="recordStore.editing ? '修改记录' : '记一笔'"
    width="92%"
    style="max-width:620px"
    :close-on-click-modal="false"
  >
    <div class="tx-form-page">
      <div style="display:flex;justify-content:flex-end;align-items:center;margin-bottom:8px">
        <div v-if="!recordStore.editing">
          <el-button size="small" @click="openSplit">分拆收支</el-button>
          <el-button size="small" @click="openDeferred">待摊费用</el-button>
        </div>
      </div>

    <div class="template-box" v-if="templates.length && !recordStore.editing">
      <div class="template-title">按账户类型选择模板</div>
      <div class="template-list">
        <button
          v-for="tpl in templates"
          :key="tpl.key"
          class="tpl-btn"
          :class="{ active: activeTemplate === tpl.key }"
          @click="useTemplate(tpl)"
        >
          <span>{{ tpl.label }}</span>
          <small>{{ tpl.hint }}</small>
        </button>
      </div>
    </div>

    <el-radio-group v-model="type" size="large" style="margin-bottom:16px">
      <el-radio-button label="expense">支出</el-radio-button>
      <el-radio-button label="income">收入</el-radio-button>
      <el-radio-button label="transfer">转账</el-radio-button>
    </el-radio-group>

    <el-form label-width="80px">
      <el-form-item label="金额">
        <el-input v-model="amount" type="number" placeholder="0.00" size="large">
          <template #prefix>¥</template>
        </el-input>
      </el-form-item>

      <el-form-item label="日期">
        <el-date-picker v-model="occurredAt" type="date" value-format="YYYY-MM-DDTHH:mm:ss" style="width:100%" placeholder="选择日期" />
      </el-form-item>

      <el-form-item :label="type === 'transfer' ? '转出账户' : '账户'">
        <el-select v-model="accountId" placeholder="选择账户" style="width:100%">
          <el-option v-for="a in accounts" :key="a.id" :label="`${a.icon} ${a.name}`" :value="a.id" />
        </el-select>
      </el-form-item>

      <el-form-item v-if="type === 'transfer'" label="转入账户">
        <el-select v-model="toAccountId" placeholder="选择账户" style="width:100%">
          <el-option v-for="a in accounts" :key="a.id" :label="`${a.icon} ${a.name}`" :value="a.id" />
        </el-select>
      </el-form-item>

      <el-form-item v-if="type !== 'transfer'" label="分类">
        <el-select v-model="categoryId" placeholder="选择分类" style="width:100%">
          <el-option v-for="c in categories" :key="c.id" :label="`${c.icon} ${c.name}`" :value="c.id" />
        </el-select>
      </el-form-item>

      <el-form-item v-if="type !== 'transfer'" label="款项">
        <el-input v-model="merchant" placeholder="用途/商家（可选）" />
      </el-form-item>

      <el-form-item v-if="type !== 'transfer'" label="标签">
        <div style="display:flex;gap:8px;width:100%">
          <el-select v-model="tagIds" multiple filterable placeholder="选择标签" style="flex:1">
            <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
          <el-button @click="quickAddTag">＋新标签</el-button>
        </div>
      </el-form-item>

      <el-form-item label="备注">
        <el-input v-model="remark" placeholder="可选" />
      </el-form-item>
    </el-form>

    <el-dialog v-model="splitDialog" title="分拆收支" width="90%" style="max-width:520px">
      <el-form label-width="72px">
        <el-form-item label="类型">
          <el-radio-group v-model="splitType">
            <el-radio-button label="expense">支出</el-radio-button>
            <el-radio-button label="income">收入</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="账户">
          <el-select v-model="splitAccountId" placeholder="选择账户" style="width:100%">
            <el-option v-for="a in accounts" :key="a.id" :label="`${a.icon} ${a.name}`" :value="a.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <div v-for="(it, i) in splitItems" :key="i" style="display:flex;gap:8px;margin-bottom:8px">
        <el-select v-model="it.category_id" placeholder="分类" style="width:120px">
          <el-option v-for="c in splitCats" :key="c.id" :label="`${c.icon} ${c.name}`" :value="c.id" />
        </el-select>
        <el-input v-model="it.amount" type="number" placeholder="金额" style="width:100px" />
        <el-input v-model="it.remark" placeholder="备注" style="flex:1" />
        <el-button link type="danger" :disabled="splitItems.length <= 2" @click="removeSplitRow(i)">删</el-button>
      </div>
      <el-button size="small" @click="addSplitRow">＋添加明细</el-button>
      <span style="margin-left:12px;color:#909399">合计 {{ splitTotal.toFixed(2) }}</span>
      <template #footer>
        <el-button @click="splitDialog = false">取消</el-button>
        <el-button type="primary" @click="submitSplit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="deferredDialog" title="待摊费用" width="90%" style="max-width:420px">
      <el-form label-width="80px">
        <el-form-item label="名称"><el-input v-model="deferredForm.name" placeholder="如 年度会员/保险" /></el-form-item>
        <el-form-item label="支付账户">
          <el-select v-model="deferredForm.account_id" placeholder="选择账户" style="width:100%">
            <el-option v-for="a in accounts" :key="a.id" :label="`${a.icon} ${a.name}`" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="deferredForm.category_id" placeholder="选择分类" style="width:100%">
            <el-option v-for="c in expenseCats" :key="c.id" :label="`${c.icon} ${c.name}`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="总金额"><el-input v-model="deferredForm.total" type="number" /></el-form-item>
        <el-form-item label="摊销期数"><el-input v-model="deferredForm.periods" type="number" placeholder="按月摊销" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="deferredForm.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deferredDialog = false">取消</el-button>
        <el-button type="primary" @click="submitDeferred">保存</el-button>
      </template>
    </el-dialog>
    </div>
    <template #footer>
      <el-button @click="recordStore.close()">取消</el-button>
      <el-button type="primary" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.tx-form-page {
  max-width: 620px;
}

.template-box {
  margin-bottom: 14px;
  background: #f7f9fc;
  border: 1px solid #d5dfeb;
  padding: 10px;
}

.template-title {
  color: #506173;
  font-size: 13px;
  margin-bottom: 8px;
}

.template-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.tpl-btn {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  border: 1px solid #ccd8e5;
  background: #fff;
  padding: 8px;
  cursor: pointer;
  color: #3c4b5a;
}

.tpl-btn small {
  color: #7a8a9b;
  font-size: 12px;
}

.tpl-btn.active {
  border-color: #4b85b3;
  background: #e8f1f8;
}

@media (max-width: 768px) {
  .template-list {
    grid-template-columns: 1fr;
  }
}
</style>
