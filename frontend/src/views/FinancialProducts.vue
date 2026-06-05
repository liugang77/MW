<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import type { Instrument, InstrumentPrice, TradeFeeRate } from '../types'

const ledgerStore = useLedgerStore()
const route = useRoute()

const categories = [
  { key: 'securities', label: '上市证券', addLabel: '新增证券', priceLabel: '价格', noCode: false },
  { key: 'open_fund', label: '开放式基金', addLabel: '新增基金', priceLabel: '净值', noCode: false },
  { key: 'money_fund', label: '货币基金', addLabel: '新增基金', priceLabel: '净值', noCode: false },
  { key: 'bond', label: '债券', addLabel: '新增债券', priceLabel: '价格', noCode: false },
  { key: 'metal', label: '贵金属', addLabel: '新增产品', priceLabel: '价格', noCode: true },
  { key: 'bank_wealth', label: '银行理财产品', addLabel: '新增理财产品', priceLabel: '净值', noCode: false },
  { key: 'futures_contract', label: '期货合约', addLabel: '新增合约', priceLabel: '价格', noCode: false },
  { key: 'futures_kind', label: '期货品种', addLabel: '新增品种', priceLabel: '价格', noCode: true },
  { key: 'metal_td', label: '贵金属TD品种', addLabel: '新增品种', priceLabel: '价格', noCode: true },
  { key: 'trade_fees', label: '证券交易费率', addLabel: '', priceLabel: '', noCode: true }
]

const cat = ref('securities')
const all = ref<Instrument[]>([])
const prices = ref<InstrumentPrice[]>([])
const keyword = ref('')
const selectedId = ref<number | null>(null)
const showAllDaily = ref(false)

const currentCat = computed(() => categories.find((c) => c.key === cat.value)!)
const isFund = computed(() => ['open_fund', 'money_fund'].includes(cat.value))
const isBankWealth = computed(() => cat.value === 'bank_wealth')
const isSecurities = computed(() => cat.value === 'securities')
const isTradeFees = computed(() => cat.value === 'trade_fees')

// 上市证券「类型」选项
const SECURITY_TYPES = ['沪市股票', '深市股票', '创业板股票', '科创板股票', '北交所股票', '港股', '美股', 'ETF基金', 'LOF基金', '可转债', '其它']
const noCode = computed(() => currentCat.value.noCode)
const hasPrice = computed(() => !['money_fund', 'bank_wealth', 'trade_fees'].includes(cat.value))
const priceLabel = computed(() => currentCat.value.priceLabel)

const list = computed(() => {
  const kw = keyword.value.trim()
  return all.value
    .filter((i) => i.category === cat.value)
    .filter((i) => !kw || (i.code || '').includes(kw) || i.name.includes(kw))
})

// 列表分页（产品较多时避免一次渲染整张长表）
const page = ref(1)
const pageSize = ref(20)
const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return list.value.slice(start, start + pageSize.value)
})
watch([cat, keyword], () => { page.value = 1 })
watch(list, () => {
  const maxPage = Math.max(Math.ceil(list.value.length / pageSize.value), 1)
  if (page.value > maxPage) page.value = maxPage
})

// 价格列表：默认仅显示选中产品；勾选「显示单日所有价格」时取最新日期每只产品一条
const priceList = computed(() => {
  if (showAllDaily.value) {
    const latestDate = prices.value.reduce((d, p) => (p.price_date > d ? p.price_date : d), '')
    return prices.value.filter((p) => p.price_date === latestDate)
  }
  if (!selectedId.value) return prices.value
  return prices.value.filter((p) => p.instrument_id === selectedId.value)
})

const fmtRate = (v: unknown) => (v == null || v === '' ? '0.00' : Number(v).toFixed(2))
const fmtPrice = (v: unknown) => (v == null || v === '' ? '0.0000' : Number(v).toFixed(4))
const termUnitText = (u?: string | null) => (u === 'day' ? '日' : u === 'month' ? '月' : u === 'year' ? '年' : '')
const termText = (i: Instrument) => (i.term_value != null ? `${i.term_value}${termUnitText(i.term_unit)}` : '')

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  all.value = isTradeFees.value ? [] : await api.listInstruments(lid, cat.value)
  await loadPrices()
}

async function loadPrices() {
  const lid = ledgerStore.currentId
  if (!lid) return
  prices.value = await api.listInstrumentPrices(lid, { category: cat.value })
}

// 同步已持仓品种的当日行情
const syncingPrices = ref(false)
async function syncPrices() {
  const lid = ledgerStore.currentId
  if (!lid) return
  syncingPrices.value = true
  try {
    const r = await api.syncMarketPrices(lid)
    if (r.updated) ElMessage.success(`已同步 ${r.updated} 只品种的最新价格`)
    else ElMessage.info('暂无可同步的持仓品种')
    if (r.failed?.length) ElMessage.warning(`未成功：${r.failed.join('、')}`)
    await loadPrices()
  } catch (e) {
    ElMessage.error('同步行情失败，请稍后重试')
  } finally {
    syncingPrices.value = false
  }
}

// 同步全量产品目录（按当前分类导入缺失的代码）
const canSyncCatalog = computed(() => ['securities', 'open_fund', 'money_fund', 'metal'].includes(cat.value))
const syncingCatalog = ref(false)
async function syncCatalog() {
  const lid = ledgerStore.currentId
  if (!lid) return
  const isMetal = cat.value === 'metal'
  try {
    await ElMessageBox.confirm(
      isMetal
        ? '将补充常见「贵金属」品种（如 Au(T+D)、Ag(T+D)、Au99.99 等），仅新增本地不存在的品种。是否继续？'
        : `将从公开数据源同步全部「${currentCat.value.label}」代码，仅新增本地不存在的产品，可能需要较长时间。是否继续？`,
      isMetal ? '补充品种' : '同步全部', { type: 'warning' }
    )
  } catch { return }
  syncingCatalog.value = true
  try {
    const r = await api.syncMarketCatalog(lid, cat.value)
    if (r.added) ElMessage.success(`已新增 ${r.added} 个产品，当前共 ${r.total_existing} 个`)
    else ElMessage.info('已是最新，无需新增')
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message || '同步失败，请稍后重试')
  } finally {
    syncingCatalog.value = false
  }
}

// ---- 产品 CRUD ----
const dialog = ref(false)
const editingId = ref<number | null>(null)
const form = ref<{
  code: string; name: string; currency: string; buy_fee_rate: string; redeem_fee_rate: string
  issuer: string; start_date: string; end_date: string; term_value: string; term_unit: string
  expected_rate: string; guaranteed: boolean; subcategory: string
}>({
  code: '', name: '', currency: 'CNY', buy_fee_rate: '', redeem_fee_rate: '',
  issuer: '', start_date: '', end_date: '', term_value: '', term_unit: 'month',
  expected_rate: '', guaranteed: false, subcategory: ''
})

function blankForm() {
  return {
    code: '', name: '', currency: 'CNY', buy_fee_rate: '', redeem_fee_rate: '',
    issuer: '', start_date: '', end_date: '', term_value: '', term_unit: 'month',
    expected_rate: '', guaranteed: false, subcategory: isSecurities.value ? '沪市股票' : ''
  }
}

function openCreate() {
  editingId.value = null
  form.value = blankForm()
  dialog.value = true
}

// 按代码同步行情资料（名称等）
const lookingUp = ref(false)
const syncableCode = computed(() => !noCode.value && !['metal', 'futures_kind', 'metal_td', 'trade_fees'].includes(cat.value))
async function fetchByCode() {
  const code = form.value.code.trim()
  if (!code) return ElMessage.warning('请先输入代码')
  const kind = isFund.value || isBankWealth.value ? 'fund' : 'stock'
  lookingUp.value = true
  try {
    const data = await api.marketQuote(code, kind)
    form.value.name = data.name || form.value.name
    ElMessage.success(`已同步：${data.name}（最新价 ${Number(data.price).toFixed(4)}）`)
  } catch (e) {
    ElMessage.error('未查询到该代码的行情，请检查代码')
  } finally {
    lookingUp.value = false
  }
}

function openEdit(i: Instrument) {
  editingId.value = i.id
  form.value = {
    code: i.code || '',
    name: i.name,
    currency: i.currency || 'CNY',
    buy_fee_rate: i.buy_fee_rate != null ? String(i.buy_fee_rate) : '',
    redeem_fee_rate: i.redeem_fee_rate != null ? String(i.redeem_fee_rate) : '',
    issuer: i.issuer || '',
    start_date: i.start_date || '',
    end_date: i.end_date || '',
    term_value: i.term_value != null ? String(i.term_value) : '',
    term_unit: i.term_unit || 'month',
    expected_rate: i.expected_rate != null ? String(i.expected_rate) : '',
    guaranteed: !!i.guaranteed,
    subcategory: i.subcategory || ''
  }
  dialog.value = true
}

async function save() {
  if (!form.value.name.trim()) return ElMessage.warning('请输入名称')
  const payload: Partial<Instrument> = {
    category: cat.value,
    code: form.value.code || null,
    name: form.value.name,
    currency: form.value.currency || 'CNY',
    buy_fee_rate: isFund.value && form.value.buy_fee_rate !== '' ? form.value.buy_fee_rate : null,
    redeem_fee_rate: isFund.value && form.value.redeem_fee_rate !== '' ? form.value.redeem_fee_rate : null
  }
  if (isSecurities.value) {
    payload.subcategory = form.value.subcategory || null
  }
  if (isBankWealth.value) {
    payload.issuer = form.value.issuer || null
    payload.start_date = form.value.start_date || null
    payload.end_date = form.value.end_date || null
    payload.term_value = form.value.term_value !== '' ? Number(form.value.term_value) : null
    payload.term_unit = form.value.term_unit || null
    payload.expected_rate = form.value.expected_rate !== '' ? form.value.expected_rate : null
    payload.guaranteed = form.value.guaranteed
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
  if (!list.value.length) return ElMessage.warning('请先新增' + currentCat.value.label)
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
  priceForm.value = {
    instrument_id: p.instrument_id,
    price_date: p.price_date,
    price: String(p.price)
  }
  priceDialog.value = true
}

async function savePrice() {
  if (!priceForm.value.instrument_id) return ElMessage.warning('请选择' + currentCat.value.label)
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
    await ElMessageBox.confirm(`确定删除 ${p.price_date} 的${priceLabel.value}吗？`, '提示', { type: 'warning' })
    await api.deleteInstrumentPrice(p.id)
    ElMessage.success('已删除')
    loadPrices()
  } catch (e) { /* cancelled */ }
}

// ---- 行内单独修改价格/净值 ----
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

async function saveInlineEdit(p: InstrumentPrice) {
  const id = inlineEditId.value
  if (id == null) return
  await api.updateInstrumentPrice(id, { price: inlineValue.value || '0' })
  ElMessage.success('已更新')
  inlineEditId.value = null
  inlineValue.value = ''
  loadPrices()
}

// ---- 证券交易费率 ----
const feeRates = ref<TradeFeeRate[]>([])
const aShareRows = computed(() => feeRates.value.filter((r) => r.group_key === 'a_share'))
const bShareRows = computed(() => feeRates.value.filter((r) => r.group_key === 'b_share'))
const feeEditCell = ref('') // `${id}:${field}`
const feeEditValue = ref('')

type FeeCol = { field: keyof TradeFeeRate; label: string }
const aShareCols: FeeCol[] = [
  { field: 'buy_stamp_tax', label: '买入印花税' },
  { field: 'sell_stamp_tax', label: '卖出印花税' },
  { field: 'buy_commission', label: '买入佣金' },
  { field: 'buy_min_commission', label: '买入最低佣金(元)' },
  { field: 'sell_commission', label: '卖出佣金' },
  { field: 'sell_min_commission', label: '卖出最低佣金(元)' },
  { field: 'surcharge', label: '附加费' },
  { field: 'transfer_fee', label: '过户费' }
]
const bShareCols: FeeCol[] = [
  { field: 'buy_stamp_tax', label: '买入印花税' },
  { field: 'sell_stamp_tax', label: '卖出印花税' },
  { field: 'buy_commission', label: '买入佣金' },
  { field: 'buy_min_commission', label: '买入最低佣金(元)' },
  { field: 'sell_commission', label: '卖出佣金' },
  { field: 'sell_min_commission', label: '卖出最低佣金(元)' },
  { field: 'settle_fee', label: '结算费(%)' },
  { field: 'settle_cap', label: '结算费上限' },
  { field: 'trade_reg_fee', label: '交易规费(%)' }
]
const fmtFee = (v: unknown) => (v == null || v === '' ? '0' : String(Number(v)))

async function loadFeeRates() {
  const lid = ledgerStore.currentId
  if (!lid) return
  feeRates.value = await api.listTradeFeeRates(lid)
}

function cellKey(id: number, field: string) {
  return `${id}:${field}`
}

function startFeeEdit(row: TradeFeeRate, field: keyof TradeFeeRate) {
  feeEditCell.value = cellKey(row.id, field as string)
  feeEditValue.value = String(row[field] ?? '')
}

function cancelFeeEdit() {
  feeEditCell.value = ''
  feeEditValue.value = ''
}

async function saveFeeEdit(row: TradeFeeRate, field: keyof TradeFeeRate) {
  const val = feeEditValue.value === '' ? '0' : feeEditValue.value
  await api.updateTradeFeeRate(row.id, { [field]: val } as Partial<TradeFeeRate>)
  feeEditCell.value = ''
  feeEditValue.value = ''
  await loadFeeRates()
}

// 依据进入路由预选分类
function applyRouteCategory() {
  if (route.path === '/data/trade-fees') cat.value = 'trade_fees'
  else if (route.path === '/data/funds') cat.value = 'money_fund'
  else cat.value = 'securities'
}

watch(cat, () => {
  selectedId.value = null
  if (isTradeFees.value) loadFeeRates()
  else load()
})
onMounted(() => { applyRouteCategory(); load(); loadFeeRates() })
watch(() => route.path, () => { applyRouteCategory(); load(); loadFeeRates() })
watch(() => ledgerStore.currentId, () => { load(); loadFeeRates() })
</script>

<template>
  <div class="fp-page">
    <div class="fp-header">
      <h2 class="fp-title">管理金融产品</h2>
    </div>

    <div class="fp-body">
      <aside class="fp-side">
        <a
          v-for="c in categories"
          :key="c.key"
          class="side-item"
          :class="{ active: cat === c.key }"
          @click="cat = c.key"
        >{{ c.label }}</a>
      </aside>

      <section class="fp-main">
        <!-- 产品列表 -->
        <div v-if="!isTradeFees" class="fp-toolbar">
          <el-button @click="openCreate">{{ currentCat.addLabel }}</el-button>
          <el-button v-if="canSyncCatalog" :loading="syncingCatalog" @click="syncCatalog">{{ cat === 'metal' ? '补充品种' : '同步全部' }}</el-button>
          <div class="toolbar-spacer" />
          <el-input v-model="keyword" placeholder="请输入要搜索的关键字…" style="width: 240px" clearable />
        </div>

        <el-table
          v-if="!isTradeFees"
          :data="pagedList"
          class="fp-table"
          highlight-current-row
          @row-click="onRowClick"
          @row-dblclick="openEdit"
        >
          <el-table-column prop="code" label="代码" width="120" v-if="!noCode" />
          <el-table-column prop="name" :label="isBankWealth ? '产品名称' : '名称'" min-width="160" />
          <el-table-column v-if="isSecurities" prop="subcategory" label="类型" width="130">
            <template #default="{ row }">{{ row.subcategory || '—' }}</template>
          </el-table-column>
          <el-table-column prop="currency" label="币种" width="100">
            <template #default="{ row }">{{ row.currency === 'CNY' ? '人民币' : row.currency }}</template>
          </el-table-column>
          <el-table-column v-if="isFund" label="申购费率(%)" width="130" align="right">
            <template #default="{ row }">{{ fmtRate(row.buy_fee_rate) }}</template>
          </el-table-column>
          <el-table-column v-if="isFund" label="赎回费率(%)" width="130" align="right">
            <template #default="{ row }">{{ fmtRate(row.redeem_fee_rate) }}</template>
          </el-table-column>
          <template v-if="isBankWealth">
            <el-table-column prop="start_date" label="收益起始日" width="130" />
            <el-table-column label="委托期" width="90">
              <template #default="{ row }">{{ termText(row) }}</template>
            </el-table-column>
            <el-table-column prop="end_date" label="收益终止日" width="130" />
            <el-table-column label="预期年收益率(%)" width="150" align="right">
              <template #default="{ row }">{{ fmtRate(row.expected_rate) }}</template>
            </el-table-column>
            <el-table-column label="已保本" width="80" align="center">
              <template #default="{ row }">
                <el-checkbox :model-value="!!row.guaranteed" disabled />
              </template>
            </el-table-column>
          </template>
          <el-table-column label="操作" width="130" align="right" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click.stop="openEdit(row)">修改</el-button>
              <el-button link type="danger" size="small" @click.stop="remove(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>暂无数据</template>
        </el-table>

        <div v-if="!isTradeFees && list.length > pageSize" class="fp-pager">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="list.length"
            :page-sizes="[20, 50, 100, 200]"
            layout="total, sizes, prev, pager, next, jumper"
            background
            size="small"
          />
        </div>

        <!-- 每日价格 / 净值 -->
        <div v-if="hasPrice" class="fp-price-toolbar">
          <el-button @click="openCreatePrice">新增{{ priceLabel }}</el-button>
          <el-button :loading="syncingPrices" @click="syncPrices">同步行情</el-button>
          <el-checkbox v-model="showAllDaily" style="margin-left:12px">显示单日所有{{ priceLabel }}</el-checkbox>
          <div class="toolbar-spacer" />
          <span v-if="!showAllDaily && selectedId" class="price-hint">当前显示选中产品的{{ priceLabel }}</span>
        </div>

        <el-table v-if="hasPrice" :data="priceList" class="fp-table">
          <el-table-column prop="price_date" label="日期" width="150" />
          <el-table-column v-if="!noCode" prop="code" label="代码" width="150" />
          <el-table-column prop="name" :label="noCode ? '产品名称' : '名称'" min-width="200" />
          <el-table-column :label="priceLabel" width="180" align="right">
            <template #default="{ row }">
              <template v-if="inlineEditId === row.id">
                <el-input
                  v-model="inlineValue"
                  type="number"
                  size="small"
                  style="width: 110px"
                  @keyup.enter="saveInlineEdit(row)"
                  @keyup.esc="cancelInlineEdit"
                />
              </template>
              <span v-else class="price-cell" @click="startInlineEdit(row)">{{ fmtPrice(row.price) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" align="right">
            <template #default="{ row }">
              <template v-if="inlineEditId === row.id">
                <el-button link type="primary" size="small" @click="saveInlineEdit(row)">保存</el-button>
                <el-button link size="small" @click="cancelInlineEdit">取消</el-button>
              </template>
              <template v-else>
                <el-button link type="primary" size="small" @click="openEditPrice(row)">修改</el-button>
                <el-button link type="danger" size="small" @click="removePrice(row)">删除</el-button>
              </template>
            </template>
          </el-table-column>
          <template #empty>暂无{{ priceLabel }}记录</template>
        </el-table>

        <!-- 证券交易费率 -->
        <template v-if="isTradeFees">
          <div class="fee-hint">
            此处设置为全局费率设置，新建证券账户将自动继承当前全局费率。请注意，修改全局费率仅对新账户生效，已建立的证券账户费率将保持不变。请点击表格进行费率调整。
          </div>

          <div class="fee-group-title">A股</div>
          <el-table :data="aShareRows" class="fp-table" border>
            <el-table-column prop="security_type" label="证券类型" min-width="180" fixed="left" />
            <el-table-column
              v-for="col in aShareCols"
              :key="col.field"
              :label="col.label"
              min-width="110"
              align="right"
            >
              <template #default="{ row }">
                <el-input
                  v-if="feeEditCell === row.id + ':' + col.field"
                  v-model="feeEditValue"
                  type="number"
                  size="small"
                  @keyup.enter="saveFeeEdit(row, col.field)"
                  @keyup.esc="cancelFeeEdit"
                  @blur="saveFeeEdit(row, col.field)"
                />
                <span v-else class="price-cell" @click="startFeeEdit(row, col.field)">{{ fmtFee(row[col.field]) }}</span>
              </template>
            </el-table-column>
          </el-table>

          <div class="fee-group-title">B股</div>
          <el-table :data="bShareRows" class="fp-table" border>
            <el-table-column prop="security_type" label="证券类型" min-width="180" fixed="left" />
            <el-table-column
              v-for="col in bShareCols"
              :key="col.field"
              :label="col.label"
              min-width="110"
              align="right"
            >
              <template #default="{ row }">
                <el-input
                  v-if="feeEditCell === row.id + ':' + col.field"
                  v-model="feeEditValue"
                  type="number"
                  size="small"
                  @keyup.enter="saveFeeEdit(row, col.field)"
                  @keyup.esc="cancelFeeEdit"
                  @blur="saveFeeEdit(row, col.field)"
                />
                <span v-else class="price-cell" @click="startFeeEdit(row, col.field)">{{ fmtFee(row[col.field]) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </section>
    </div>

    <!-- 产品弹窗 -->
    <el-dialog
      v-model="dialog"
      :title="isBankWealth ? '银行理财产品' : (editingId ? '修改' : '新增') + currentCat.label"
      width="90%"
      :style="{ maxWidth: isBankWealth ? '680px' : '440px' }"
    >
      <!-- 银行理财产品：双列表单 -->
      <el-form v-if="isBankWealth" label-width="110px" class="bw-form">
        <div class="bw-grid">
          <el-form-item label="产品名称" required><el-input v-model="form.name" placeholder="请输入产品名称" /></el-form-item>
          <el-form-item label="币种" required>
            <el-select v-model="form.currency" style="width: 100%">
              <el-option label="人民币 CNY" value="CNY" />
              <el-option label="美元 USD" value="USD" />
              <el-option label="港币 HKD" value="HKD" />
              <el-option label="欧元 EUR" value="EUR" />
            </el-select>
          </el-form-item>
          <el-form-item label="产品代码">
            <div style="display:flex; gap:8px; width:100%">
              <el-input v-model="form.code" placeholder="请输入产品代码" />
              <el-button :loading="lookingUp" @click="fetchByCode">同步资料</el-button>
            </div>
          </el-form-item>
          <el-form-item label="发行机构"><el-input v-model="form.issuer" placeholder="<无>" /></el-form-item>
          <el-form-item label="收益起始日" required>
            <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width: 100%" />
          </el-form-item>
          <el-form-item label="委托期">
            <div class="bw-term">
              <el-input v-model="form.term_value" type="number" placeholder="1" />
              <el-select v-model="form.term_unit" style="width: 90px">
                <el-option label="日" value="day" />
                <el-option label="月" value="month" />
                <el-option label="年" value="year" />
              </el-select>
            </div>
          </el-form-item>
          <el-form-item label="收益终止日">
            <el-date-picker v-model="form.end_date" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width: 100%" />
          </el-form-item>
          <el-form-item label="是否保本">
            <el-checkbox v-model="form.guaranteed" />
          </el-form-item>
          <el-form-item label="预期年收益率(%)">
            <el-input v-model="form.expected_rate" type="number" placeholder="0.00" />
          </el-form-item>
        </div>
      </el-form>

      <!-- 其它产品：单列表单 -->
      <el-form v-else label-width="90px">
        <el-form-item label="代码" v-if="!noCode">
          <div style="display:flex; gap:8px; width:100%">
            <el-input v-model="form.code" placeholder="请输入代码" />
            <el-button v-if="syncableCode" :loading="lookingUp" @click="fetchByCode">同步资料</el-button>
          </div>
        </el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="请输入名称" /></el-form-item>
        <el-form-item label="类型" v-if="isSecurities">
          <el-select v-model="form.subcategory" style="width: 100%" placeholder="选择类型">
            <el-option v-for="t in SECURITY_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="币种">
          <el-select v-model="form.currency" style="width: 100%">
            <el-option label="人民币" value="CNY" />
            <el-option label="美元" value="USD" />
            <el-option label="港币" value="HKD" />
            <el-option label="欧元" value="EUR" />
          </el-select>
        </el-form-item>
        <template v-if="isFund">
          <el-form-item label="申购费率(%)"><el-input v-model="form.buy_fee_rate" type="number" placeholder="0.00" /></el-form-item>
          <el-form-item label="赎回费率(%)"><el-input v-model="form.redeem_fee_rate" type="number" placeholder="0.00" /></el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 价格 / 净值弹窗 -->
    <el-dialog
      v-model="priceDialog"
      :title="(isFund ? '基金净值' : currentCat.label + priceLabel)"
      width="90%"
      style="max-width:420px"
    >
      <el-form label-width="70px">
        <el-form-item :label="currentCat.label">
          <el-select v-model="priceForm.instrument_id" filterable style="width: 100%">
            <el-option
              v-for="i in list"
              :key="i.id"
              :label="(i.code ? i.code + ' ' : '') + i.name"
              :value="i.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker
            v-model="priceForm.price_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="priceLabel">
          <el-input v-model="priceForm.price" type="number" placeholder="0.0000" />
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

.fp-body {
  display: flex;
  min-height: calc(100vh - 105px);
}

.fp-side {
  width: 160px;
  flex-shrink: 0;
  background: #fff;
  border-right: 1px solid #e4e9ef;
  padding: 8px 0;
}

.side-item {
  display: block;
  padding: 10px 18px;
  color: #55677a;
  cursor: pointer;
  font-size: 14px;
  white-space: nowrap;
}

.side-item:hover {
  background: #f2f6fa;
}

.side-item.active {
  background: #e8f1f8;
  color: #3f79a8;
  font-weight: 600;
  border-left: 3px solid #3f79a8;
}

.fp-main {
  flex: 1;
  min-width: 0;
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

.fp-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.bw-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 16px;
}

.bw-term {
  display: flex;
  gap: 8px;
  width: 100%;
}

.fee-hint {
  background: #f4f4f5;
  border: 1px solid #e9e9eb;
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
  padding: 10px 14px;
  border-radius: 4px;
}

.fee-group-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-top: 4px;
}

@media (max-width: 640px) {
  .bw-grid {
    grid-template-columns: 1fr;
  }
}
</style>
