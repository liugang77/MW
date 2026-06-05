<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import type { Instrument, InstrumentPrice, Currency, Party } from '../types'

const CATEGORY = 'major_asset'

const ledgerStore = useLedgerStore()

const all = ref<Instrument[]>([])
const prices = ref<InstrumentPrice[]>([])
const currencies = ref<Currency[]>([])
const owners = ref<Party[]>([])
const selectedId = ref<number | null>(null)

const list = computed(() => all.value.filter((i) => i.category === CATEGORY))

// 选中资产的价格历史；未选中时展示全部
const priceList = computed(() => {
  if (!selectedId.value) return prices.value
  return prices.value.filter((p) => p.instrument_id === selectedId.value)
})

const fmtMoney = (v: unknown) =>
  v == null || v === '' ? '0.00' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

// 资产当前价格 = 最新日期的价格
function currentPrice(id: number): number | null {
  const rows = prices.value.filter((p) => p.instrument_id === id)
  if (!rows.length) return null
  const latest = rows.reduce((a, b) => (b.price_date > a.price_date ? b : a))
  return Number(latest.price)
}

const natureText = (v?: string | null) => (v === 'invest' ? '投资' : '自用')

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  all.value = await api.listInstruments(lid, CATEGORY)
  currencies.value = await api.listCurrencies(lid)
  owners.value = await api.listParties(lid, 'member')
  await loadPrices()
}

async function loadPrices() {
  const lid = ledgerStore.currentId
  if (!lid) return
  prices.value = await api.listInstrumentPrices(lid, { category: CATEGORY })
}

// ---- 资产 CRUD ----
const dialog = ref(false)
const editingId = ref<number | null>(null)
const form = ref<{
  name: string; currency: string; owner: string; remark: string
  start_date: string; asset_nature: string
}>({
  name: '', currency: 'CNY', owner: '', remark: '',
  start_date: new Date().toISOString().slice(0, 10), asset_nature: 'own'
})

function blankForm() {
  return {
    name: '', currency: 'CNY', owner: '', remark: '',
    start_date: new Date().toISOString().slice(0, 10), asset_nature: 'own'
  }
}

function openCreate() {
  editingId.value = null
  form.value = blankForm()
  dialog.value = true
}

function openEdit(i: Instrument) {
  editingId.value = i.id
  form.value = {
    name: i.name,
    currency: i.currency || 'CNY',
    owner: i.owner || '',
    remark: i.remark || '',
    start_date: i.start_date || new Date().toISOString().slice(0, 10),
    asset_nature: i.asset_nature || 'own'
  }
  dialog.value = true
}

async function save() {
  if (!form.value.name.trim()) return ElMessage.warning('请输入资产名称')
  const payload: Partial<Instrument> = {
    category: CATEGORY,
    name: form.value.name.trim(),
    currency: form.value.currency || 'CNY',
    owner: form.value.owner || null,
    remark: form.value.remark || null,
    start_date: form.value.start_date || null,
    asset_nature: form.value.asset_nature
  }
  if (editingId.value) {
    await api.updateInstrument(editingId.value, payload)
    ElMessage.success('已更新')
  } else {
    await api.createInstrument(ledgerStore.currentId as number, payload)
    ElMessage.success('已创建')
  }
  dialog.value = false
  load()
}

async function remove(i: Instrument) {
  try {
    await ElMessageBox.confirm(`确定删除「${i.name}」吗？`, '提示', { type: 'warning' })
    await api.deleteInstrument(i.id)
    ElMessage.success('已删除')
    if (selectedId.value === i.id) selectedId.value = null
    load()
  } catch (e) { /* cancelled */ }
}

function onRowClick(row: Instrument) {
  selectedId.value = row.id
}

// ---- 价格 CRUD ----
const priceDialog = ref(false)
const editingPriceId = ref<number | null>(null)
const priceForm = ref<{ instrument_id: number | null; price_date: string; price: string }>(
  { instrument_id: null, price_date: new Date().toISOString().slice(0, 10), price: '' }
)

function openCreatePrice() {
  if (!list.value.length) return ElMessage.warning('请先新增重大资产')
  editingPriceId.value = null
  priceForm.value = {
    instrument_id: selectedId.value ?? list.value[0].id,
    price_date: new Date().toISOString().slice(0, 10),
    price: ''
  }
  priceDialog.value = true
}

function openEditPrice(p: InstrumentPrice) {
  editingPriceId.value = p.id
  priceForm.value = { instrument_id: p.instrument_id, price_date: p.price_date, price: String(p.price) }
  priceDialog.value = true
}

async function savePrice() {
  if (!priceForm.value.instrument_id) return ElMessage.warning('请选择资产')
  if (!priceForm.value.price_date) return ElMessage.warning('请选择日期')
  const payload: Partial<InstrumentPrice> = {
    instrument_id: priceForm.value.instrument_id,
    price_date: priceForm.value.price_date,
    price: priceForm.value.price || '0'
  }
  if (editingPriceId.value) {
    await api.updateInstrumentPrice(editingPriceId.value, payload)
    ElMessage.success('已更新')
  } else {
    await api.createInstrumentPrice(ledgerStore.currentId as number, payload)
    ElMessage.success('已创建')
  }
  priceDialog.value = false
  loadPrices()
}

async function removePrice(p: InstrumentPrice) {
  try {
    await ElMessageBox.confirm(`确定删除 ${p.price_date} 的价格吗？`, '提示', { type: 'warning' })
    await api.deleteInstrumentPrice(p.id)
    ElMessage.success('已删除')
    loadPrices()
  } catch (e) { /* cancelled */ }
}

// 行内修改价格
const inlineEditId = ref<number | null>(null)
const inlineValue = ref('')

function startInlineEdit(p: InstrumentPrice) {
  inlineEditId.value = p.id
  inlineValue.value = String(p.price)
}
function cancelInlineEdit() {
  inlineEditId.value = null
  inlineValue.value = ''
}
async function saveInlineEdit() {
  const id = inlineEditId.value
  if (id == null) return
  await api.updateInstrumentPrice(id, { price: inlineValue.value || '0' })
  ElMessage.success('已更新')
  inlineEditId.value = null
  inlineValue.value = ''
  loadPrices()
}

onMounted(load)
watch(() => ledgerStore.currentId, load)
</script>

<template>
  <div class="fp-page">
    <div class="fp-header">
      <h2 class="fp-title">管理重大资产</h2>
    </div>

    <section class="ma-main">
      <!-- 资产列表 -->
      <div class="fp-toolbar">
        <el-button @click="openCreate">新增重大资产</el-button>
      </div>

      <el-table
        :data="list"
        class="fp-table"
        highlight-current-row
        @row-click="onRowClick"
        @row-dblclick="openEdit"
      >
        <el-table-column prop="name" label="资产名称" min-width="200" />
        <el-table-column label="所有者" width="120">
          <template #default="{ row }">{{ row.owner || '—' }}</template>
        </el-table-column>
        <el-table-column label="资产性质" width="100" align="center">
          <template #default="{ row }">{{ natureText(row.asset_nature) }}</template>
        </el-table-column>
        <el-table-column label="币种" width="100">
          <template #default="{ row }">{{ row.currency === 'CNY' ? '人民币' : row.currency }}</template>
        </el-table-column>
        <el-table-column label="当前价格" width="180" align="right">
          <template #default="{ row }">{{ currentPrice(row.id) == null ? '—' : fmtMoney(currentPrice(row.id)) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" align="right" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click.stop="openEdit(row)">修改</el-button>
            <el-button link type="danger" size="small" @click.stop="remove(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无数据</template>
      </el-table>

      <!-- 价格历史 -->
      <div class="fp-price-toolbar">
        <el-button @click="openCreatePrice">新增价格</el-button>
        <div class="toolbar-spacer" />
        <span v-if="selectedId" class="price-hint">当前显示选中资产的价格</span>
      </div>

      <el-table :data="priceList" class="fp-table">
        <el-table-column prop="price_date" label="日期" width="160" />
        <el-table-column prop="name" label="资产名称" min-width="200" />
        <el-table-column label="价格" width="200" align="right">
          <template #default="{ row }">
            <el-input
              v-if="inlineEditId === row.id"
              v-model="inlineValue"
              type="number"
              size="small"
              style="width: 120px"
              @keyup.enter="saveInlineEdit"
              @keyup.esc="cancelInlineEdit"
            />
            <span v-else class="price-cell" @click="startInlineEdit(row)">{{ fmtMoney(row.price) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="right">
          <template #default="{ row }">
            <template v-if="inlineEditId === row.id">
              <el-button link type="primary" size="small" @click="saveInlineEdit">保存</el-button>
              <el-button link size="small" @click="cancelInlineEdit">取消</el-button>
            </template>
            <template v-else>
              <el-button link type="primary" size="small" @click="openEditPrice(row)">修改</el-button>
              <el-button link type="danger" size="small" @click="removePrice(row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
        <template #empty>暂无价格记录</template>
      </el-table>
    </section>

    <!-- 重大资产概况弹窗 -->
    <el-dialog v-model="dialog" title="重大资产概况" width="92%" style="max-width:640px">
      <el-form label-width="80px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="资产名称" required>
              <el-input v-model="form.name" placeholder="请输入资产名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="币种">
              <el-select v-model="form.currency" style="width:100%" :disabled="!!editingId">
                <el-option v-for="c in currencies" :key="c.id" :label="`${c.name} ${c.code}`" :value="c.code" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="所有者">
              <el-select v-model="form.owner" placeholder="<无>" clearable style="width:100%">
                <el-option v-for="o in owners" :key="o.id" :label="o.name" :value="o.name" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="备注">
              <el-input v-model="form.remark" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="创建日期">
              <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="资产性质">
              <el-radio-group v-model="form.asset_nature">
                <el-radio value="invest">投资</el-radio>
                <el-radio value="own">自用</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">确定</el-button>
      </template>
    </el-dialog>

    <!-- 价格弹窗 -->
    <el-dialog v-model="priceDialog" title="资产价格" width="90%" style="max-width:420px">
      <el-form label-width="80px">
        <el-form-item label="资产名称">
          <el-select v-model="priceForm.instrument_id" filterable style="width:100%">
            <el-option v-for="i in list" :key="i.id" :label="i.name" :value="i.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="priceForm.price_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="价格">
          <el-input v-model="priceForm.price" type="number" placeholder="0.00" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="priceDialog = false">取消</el-button>
        <el-button type="primary" @click="savePrice">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.fp-page {
  background: #f3f6f9;
  min-height: calc(100vh - 52px);
}
.fp-header {
  background: #fff;
  border-bottom: 1px solid #c8d3de;
  padding: 12px 16px;
}
.fp-title {
  margin: 0;
  font-size: 16px;
  color: #415163;
}
.ma-main {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.fp-toolbar,
.fp-price-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
}
.toolbar-spacer {
  flex: 1;
}
.price-hint {
  color: #909aa6;
  font-size: 12px;
}
.price-cell {
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px dashed transparent;
}
.price-cell:hover {
  border-color: #c0c8d2;
  color: #3f79a8;
}
.fp-table {
  width: 100%;
  background: #fff;
}
</style>
