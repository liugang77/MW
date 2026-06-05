<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import type { Currency, ExchangeRate } from '../types'

const ledgerStore = useLedgerStore()

const currencies = ref<Currency[]>([])
const rates = ref<ExchangeRate[]>([])
const keyword = ref('')
const selectedCode = ref<string | null>(null)
const showAllRates = ref(false)

const list = computed(() => {
  const kw = keyword.value.trim()
  return currencies.value.filter(
    (c) => !kw || c.name.includes(kw) || c.code.toUpperCase().includes(kw.toUpperCase())
  )
})

const homeCode = computed(() => currencies.value.find((c) => c.is_home)?.code || 'CNY')

const rateList = computed(() => {
  if (showAllRates.value) return rates.value
  if (!selectedCode.value) return rates.value
  return rates.value.filter((r) => r.currency_code === selectedCode.value)
})

const fmtRate = (v: unknown) => (v == null || v === '' ? '0.0000' : Number(v).toFixed(4))
const currencyName = (code: string) => currencies.value.find((c) => c.code === code)?.name || code

async function loadCurrencies() {
  const lid = ledgerStore.currentId
  if (!lid) return
  currencies.value = await api.listCurrencies(lid)
}

async function loadRates() {
  const lid = ledgerStore.currentId
  if (!lid) return
  rates.value = await api.listExchangeRates(lid)
}

// 补全币种：把常见币种里列表中不存在的补充进来
const syncing = ref(false)
async function supplementCurrencies() {
  const lid = ledgerStore.currentId
  if (!lid) return
  syncing.value = true
  try {
    const r = await api.supplementCurrencies(lid)
    if (r.added) ElMessage.success(`已补全 ${r.added} 个币种：${r.items.join('、')}`)
    else ElMessage.info('常见币种均已存在，无需补全')
    loadCurrencies()
  } catch (e) {
    ElMessage.error('补全币种失败，请稍后重试')
  } finally {
    syncing.value = false
  }
}

function load() {
  loadCurrencies()
  loadRates()
}

// ---- 币种 CRUD ----
const dialog = ref(false)
const editingId = ref<number | null>(null)
const form = ref<{ name: string; code: string; rate: string; is_home: boolean }>({
  name: '', code: '', rate: '1', is_home: false
})

function openCreate() {
  editingId.value = null
  form.value = { name: '', code: '', rate: '1', is_home: false }
  dialog.value = true
}

function openEdit(c: Currency) {
  editingId.value = c.id
  form.value = { name: c.name, code: c.code, rate: String(c.rate), is_home: !!c.is_home }
  dialog.value = true
}

async function save() {
  if (!form.value.name.trim()) return ElMessage.warning('请输入货币名称')
  if (!form.value.code.trim()) return ElMessage.warning('请输入英文缩写')
  const payload: Partial<Currency> = {
    name: form.value.name,
    code: form.value.code.toUpperCase(),
    rate: form.value.rate || '0',
    is_home: form.value.is_home
  }
  if (editingId.value) {
    await api.updateCurrency(editingId.value, payload)
    ElMessage.success('已更新')
  } else {
    await api.createCurrency(ledgerStore.currentId as number, payload)
    ElMessage.success('已创建')
  }
  dialog.value = false
  loadCurrencies()
}

async function remove(c: Currency) {
  if (c.is_home) return ElMessage.warning('本币不可删除')
  try {
    await ElMessageBox.confirm(`确定删除「${c.name}」？`, '提示', { type: 'warning' })
    await api.deleteCurrency(c.id)
    ElMessage.success('已删除')
    loadCurrencies()
  } catch (e) { /* cancelled */ }
}

function onRowClick(row: Currency) {
  selectedCode.value = row.code
}

// 行内修改牌价
const inlineEditId = ref<number | null>(null)
const inlineValue = ref('')

function startInlineEdit(c: Currency) {
  if (c.is_home) return
  inlineEditId.value = c.id
  inlineValue.value = String(c.rate)
}

function cancelInlineEdit() {
  inlineEditId.value = null
  inlineValue.value = ''
}

async function saveInlineEdit(c: Currency) {
  if (inlineEditId.value == null) return
  await api.updateCurrency(inlineEditId.value, { rate: inlineValue.value || '0' })
  ElMessage.success('已更新')
  inlineEditId.value = null
  inlineValue.value = ''
  loadCurrencies()
}

// ---- 汇率 CRUD ----
const rateDialog = ref(false)
const editingRateId = ref<number | null>(null)
const rateForm = ref<{ rate_date: string; currency_code: string; rate: string }>({
  rate_date: new Date().toISOString().slice(0, 10),
  currency_code: '',
  rate: ''
})

function openCreateRate() {
  editingRateId.value = null
  rateForm.value = {
    rate_date: new Date().toISOString().slice(0, 10),
    currency_code: selectedCode.value && selectedCode.value !== homeCode.value ? selectedCode.value : '',
    rate: ''
  }
  rateDialog.value = true
}

function openEditRate(r: ExchangeRate) {
  editingRateId.value = r.id
  rateForm.value = { rate_date: r.rate_date, currency_code: r.currency_code, rate: String(r.rate) }
  rateDialog.value = true
}

async function saveRate() {
  if (!rateForm.value.currency_code) return ElMessage.warning('请选择货币')
  if (!rateForm.value.rate_date) return ElMessage.warning('请选择日期')
  const payload: Partial<ExchangeRate> = {
    rate_date: rateForm.value.rate_date,
    currency_code: rateForm.value.currency_code,
    base_code: homeCode.value,
    rate: rateForm.value.rate || '0'
  }
  if (editingRateId.value) {
    await api.updateExchangeRate(editingRateId.value, payload)
    ElMessage.success('已更新')
  } else {
    await api.createExchangeRate(ledgerStore.currentId as number, payload)
    ElMessage.success('已创建')
  }
  rateDialog.value = false
  loadRates()
}

async function removeRate(r: ExchangeRate) {
  try {
    await ElMessageBox.confirm('确定删除该汇率记录？', '提示', { type: 'warning' })
    await api.deleteExchangeRate(r.id)
    ElMessage.success('已删除')
    loadRates()
  } catch (e) { /* cancelled */ }
}

const foreignCurrencies = computed(() => currencies.value.filter((c) => !c.is_home))

onMounted(load)
watch(() => ledgerStore.currentId, load)
</script>

<template>
  <div class="cr-page">
    <div class="cr-header">
      <h2 class="cr-title">管理币种与汇率</h2>
    </div>

    <!-- 币种表 -->
    <div class="cr-toolbar">
      <div class="toolbar-spacer" />
      <el-input v-model="keyword" placeholder="请输入要搜索的关键字…" style="width: 240px" clearable />
      <el-button :loading="syncing" @click="supplementCurrencies" style="margin-left:12px">补全币种</el-button>
      <el-button @click="openCreate" style="margin-left:8px">新增币种</el-button>
    </div>

    <el-table
      :data="list"
      class="cr-table"
      highlight-current-row
      @row-click="onRowClick"
      @row-dblclick="openEdit"
    >
      <el-table-column label="本币" width="90" align="center">
        <template #default="{ row }">
          <span v-if="row.is_home" class="home-mark">√</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="货币名称" min-width="180" />
      <el-table-column prop="code" label="英文缩写" min-width="160" />
      <el-table-column label="对人民币牌价" min-width="160" align="right">
        <template #default="{ row }">
          <template v-if="inlineEditId === row.id">
            <el-input
              v-model="inlineValue"
              type="number"
              size="small"
              style="width: 120px"
              @keyup.enter="saveInlineEdit(row)"
              @keyup.esc="cancelInlineEdit"
            />
          </template>
          <span
            v-else
            class="rate-cell"
            :class="{ disabled: row.is_home }"
            @click="startInlineEdit(row)"
          >{{ fmtRate(row.rate) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" align="right">
        <template #default="{ row }">
          <template v-if="inlineEditId === row.id">
            <el-button link type="primary" size="small" @click="saveInlineEdit(row)">保存</el-button>
            <el-button link size="small" @click="cancelInlineEdit">取消</el-button>
          </template>
          <template v-else>
            <el-button link type="primary" size="small" @click.stop="openEdit(row)">修改</el-button>
            <el-button link type="danger" size="small" @click.stop="remove(row)">删除</el-button>
          </template>
        </template>
      </el-table-column>
      <template #empty>暂无币种</template>
    </el-table>

    <!-- 汇率历史 -->
    <div class="cr-rate-toolbar">
      <el-button @click="openCreateRate">新增汇率</el-button>
      <el-checkbox v-model="showAllRates" style="margin-left:12px">按日期显示全部汇率</el-checkbox>
      <div class="toolbar-spacer" />
      <span v-if="!showAllRates && selectedCode" class="rate-hint">当前显示：{{ currencyName(selectedCode) }}</span>
    </div>

    <el-table :data="rateList" class="cr-table">
      <el-table-column prop="rate_date" label="日期" width="150" />
      <el-table-column label="货币" min-width="140">
        <template #default="{ row }">{{ currencyName(row.currency_code) }}</template>
      </el-table-column>
      <el-table-column label="比" width="60" align="center">/</el-table-column>
      <el-table-column label="货币" min-width="140">
        <template #default="{ row }">{{ currencyName(row.base_code) }}</template>
      </el-table-column>
      <el-table-column label="报价方式" min-width="140">
        <template #default="{ row }">{{ row.currency_code }}/{{ row.base_code }}</template>
      </el-table-column>
      <el-table-column label="牌价/汇率" min-width="140" align="right">
        <template #default="{ row }">{{ fmtRate(row.rate) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150" align="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openEditRate(row)">修改</el-button>
          <el-button link type="danger" size="small" @click="removeRate(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>暂无汇率记录</template>
    </el-table>

    <!-- 币种弹窗 -->
    <el-dialog v-model="dialog" :title="editingId ? '修改币种' : '新增币种'" width="90%" style="max-width:440px">
      <el-form label-width="110px">
        <el-form-item label="货币名称"><el-input v-model="form.name" placeholder="如：美元" /></el-form-item>
        <el-form-item label="英文缩写"><el-input v-model="form.code" placeholder="如：USD" /></el-form-item>
        <el-form-item label="对人民币牌价"><el-input v-model="form.rate" type="number" placeholder="1.0000" /></el-form-item>
        <el-form-item label="设为本币"><el-checkbox v-model="form.is_home" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 汇率弹窗 -->
    <el-dialog v-model="rateDialog" :title="editingRateId ? '修改汇率' : '新增汇率'" width="90%" style="max-width:440px">
      <el-form label-width="90px">
        <el-form-item label="货币">
          <el-select v-model="rateForm.currency_code" filterable style="width: 100%">
            <el-option v-for="c in foreignCurrencies" :key="c.code" :label="c.name + ' ' + c.code" :value="c.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="rateForm.rate_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="牌价/汇率"><el-input v-model="rateForm.rate" type="number" placeholder="0.0000" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rateDialog = false">取消</el-button>
        <el-button type="primary" @click="saveRate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.cr-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
}

.cr-header {
  background: #4a90c2;
  color: #fff;
  padding: 8px 16px;
  border-radius: 4px;
}

.cr-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.cr-toolbar,
.cr-rate-toolbar {
  display: flex;
  align-items: center;
}

.toolbar-spacer {
  flex: 1;
}

.cr-table {
  width: 100%;
  background: #fff;
}

.home-mark {
  color: #409eff;
  font-weight: 700;
}

.rate-hint {
  color: #909399;
  font-size: 13px;
}

.rate-cell {
  display: inline-block;
  min-width: 80px;
  padding: 2px 6px;
  border: 1px dashed transparent;
  border-radius: 3px;
  cursor: pointer;
}

.rate-cell:hover:not(.disabled) {
  border-color: #c0c4cc;
}

.rate-cell.disabled {
  cursor: default;
}
</style>
