<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useTradeStore } from '../stores/trade'
import type { Account, Tag, Holding, TradeFeeRate, Instrument, InstrumentPrice, Currency, ExchangeRate } from '../types'

const ledgerStore = useLedgerStore()
const tradeStore = useTradeStore()

const accounts = ref<Account[]>([])
const tags = ref<Tag[]>([])
const holdings = ref<Holding[]>([])
const feeRates = ref<TradeFeeRate[]>([])
const instruments = ref<Instrument[]>([])
const instrumentPrices = ref<InstrumentPrice[]>([])
const currencies = ref<Currency[]>([])
const exchangeRates = ref<ExchangeRate[]>([])

const STOCK_TYPES = ['stock', 'fund', 'open_fund', 'money_fund', 'bond', 'reverse_repo', 'wealth', 'metal', 'metal_td', 'futures', 'margin']
const CASH_TYPES = ['cash', 'bank', 'wallet', 'prepaid']

// 账户记账组：同组账户才可在买卖弹窗里互选（货币基金只选货币基金账户，贵金属只选贵金属账户…）
const TRADE_GROUP: Record<string, string> = {
  stock: 'securities', bond: 'securities', reverse_repo: 'securities', futures: 'securities', margin: 'securities',
  fund: 'open_fund', open_fund: 'open_fund',
  money_fund: 'money_fund',
  metal: 'metal', metal_td: 'metal',
  wealth: 'wealth',
}
function tradeGroupOf(type?: string): string {
  // 未在映射中的类型（如外汇）归到自身的独立组，避免误并入证券组
  return (type && TRADE_GROUP[type]) || type || 'securities'
}
// 打开弹窗时锁定的记账组（以初始账户类型为准），账户下拉只列同组账户
const lockedGroup = ref<string | null>(null)

const stockAccounts = computed(() => {
  const g = lockedGroup.value
  return accounts.value.filter((a) => STOCK_TYPES.includes(a.type) && (!g || tradeGroupOf(a.type) === g))
})
// 资金账户可以是现金类账户，也可以是股票账户
const cashAccounts = computed(() => accounts.value.filter((a) => CASH_TYPES.includes(a.type) || STOCK_TYPES.includes(a.type)))
// 理财外币申购：资金账户必须与所选币种一致（直接从外币账户扣款）
const wealthCashAccounts = computed(() => {
  if (!isWealth.value || !isBuy.value || wealthCurrency.value === 'CNY') return cashAccounts.value
  // 外币申购：显示币种完全匹配的账户，以及外汇账户（外汇账户持有多种货币，以实际持仓扣款）
  return accounts.value.filter((a) => a.currency === wealthCurrency.value || a.type === 'forex')
})
// 理财外币赎回：资金账户过滤
const wealthRedeemCashAccounts = computed(() => {
  if (!isWealth.value || isBuy.value) return cashAccounts.value
  const cur = redeemHoldingCurrency.value
  if (cur === 'CNY') return cashAccounts.value
  if (wealthRedeemToCny.value) {
    // 兑换为人民币：支持 CNY 账户
    return accounts.value.filter((a) => a.currency === 'CNY' || CASH_TYPES.includes(a.type))
  }
  // 原币退回：支持同币种账户和外汇账户
  return accounts.value.filter((a) => a.currency === cur || a.type === 'forex')
})

const FUND_TYPES = ['fund', 'open_fund', 'money_fund']
const isFund = computed(() => {
  const acc = accounts.value.find((a) => a.id === securityAccountId.value)
  return acc ? FUND_TYPES.includes(acc.type) : false
})
// 银行理财账户：以「申购金额」记账，无价格×数量/费用
const isWealth = computed(() => {
  const acc = accounts.value.find((a) => a.id === securityAccountId.value)
  return acc ? acc.type === 'wealth' : false
})
// 贵金属账户
const isMetal = computed(() => {
  const acc = accounts.value.find((a) => a.id === securityAccountId.value)
  return acc ? ['metal', 'metal_td'].includes(acc.type) : false
})

const isBuy = computed(() => tradeStore.mode === 'buy')
const isEdit = computed(() => tradeStore.editTxn != null)
// 新股申购：本质为证券买入（建仓），仅标题与文案不同
const isIpo = computed(() => tradeStore.ipo && isBuy.value && !isEdit.value)
const title = computed(() => {
  const prefix = isEdit.value ? '编辑' : ''
  if (isIpo.value) return '新股申购'
  if (isWealth.value) return prefix + (isBuy.value ? '银行理财产品申购' : '银行理财产品赎回')
  if (isFund.value) return prefix + (isBuy.value ? '申购基金' : '赎回基金')
  if (isMetal.value) return prefix + (isBuy.value ? '贵金属买入' : '贵金属卖出')
  return prefix + (isBuy.value ? '证券买入' : '证券卖出')
})
// 账户类型对应的「标的」称谓：贵金属=产品/基金=基金/理财=产品/其它=证券
const itemNoun = computed(() => isWealth.value ? '产品' : isFund.value ? '基金' : isMetal.value ? '产品' : '证券')
const accountLabel = computed(() => isWealth.value ? '理财账户' : isFund.value ? '基金账户' : isMetal.value ? '贵金属账户' : '证券账户')

// 理财申购金额（理财专用，等价于 price=1 × quantity=金额）
const wealthAmount = ref('')
const wealthCurrency = ref('CNY')
const wealthExchangeRate = ref('')
// 赎回时：是否将外币兑换为人民币（true=兑换CNY，false=原币退回）
const wealthRedeemToCny = ref(false)

// 当前赎回持仓的币种
const redeemHoldingCurrency = computed(() => {
  if (!isWealth.value || isBuy.value) return 'CNY'
  const h = accountHoldings.value.find((x) => x.symbol === symbol.value)
  return h?.currency || 'CNY'
})

const securityAccountId = ref<number | null>(null)
const cashAccountId = ref<number | null>(null)
const symbol = ref('')
const name = ref('')
const price = ref('')
const quantity = ref('')
const showFee = ref(false)
const stampRate = ref('')
const stampTax = ref('')
const commissionRate = ref('')
const commission = ref('')
const transferFee = ref('')
const surcharge = ref('')
const feeTotal = ref('')
const amountTotal = ref('')
const tagIds = ref<number[]>([])
const remark = ref('')
const occurredAt = ref(new Date().toISOString().slice(0, 10))
const pnlAs = ref('invest_income')

// 当前证券账户内的持仓（卖出时选择）
const accountHoldings = computed(() =>
  holdings.value.filter((h) => h.account_id === securityAccountId.value)
)

// 账户类型 → 金融产品分类，用于筛选可选证券代码
const ACCOUNT_TO_CATEGORY: Record<string, string> = {
  stock: 'securities',
  fund: 'open_fund',
  open_fund: 'open_fund',
  money_fund: 'money_fund',
  bond: 'bond',
  wealth: 'bank_wealth',
  metal: 'metal',
  metal_td: 'metal_td',
  futures: 'futures_contract'
}

const currentCategory = computed(() => {
  const acc = accounts.value.find((a) => a.id === securityAccountId.value)
  return acc ? ACCOUNT_TO_CATEGORY[acc.type] : undefined
})

// 可选证券代码：来自「管理金融产品」里创建的产品（按账户类型对应分类筛选）
const symbolOptions = computed(() => {
  const cat = currentCategory.value
  return instruments.value.filter((i) => !cat || i.category === cat)
})

// 取某产品最新价格
function latestPrice(code: string): string {
  const inst = instruments.value.find((i) => (i.code || i.name) === code)
  if (!inst) return ''
  const ps = instrumentPrices.value
    .filter((p) => p.instrument_id === inst.id)
    .sort((a, b) => (a.price_date < b.price_date ? 1 : -1))
  return ps.length ? String(ps[0].price) : ''
}

const num = (v: string) => Number(v || 0)
const round2 = (n: number) => Math.round(n * 100) / 100

function recalc() {
  const gross = num(price.value) * num(quantity.value)
  const st = stampRate.value !== '' ? round2(gross * num(stampRate.value) / 100) : num(stampTax.value)
  if (stampRate.value !== '') stampTax.value = st ? String(st) : '0.00'
  const cm = commissionRate.value !== '' ? round2(gross * num(commissionRate.value) / 100) : num(commission.value)
  if (commissionRate.value !== '') commission.value = cm ? String(cm) : '0.00'
  const ft = round2(st + cm + num(transferFee.value) + num(surcharge.value))
  feeTotal.value = String(ft)
  amountTotal.value = String(round2(isBuy.value ? gross + ft : gross - ft))
}

watch([price, quantity, stampRate, commissionRate, transferFee, surcharge, () => tradeStore.mode], recalc)
watch(stampTax, () => { if (stampRate.value === '') recalc() })
watch(commission, () => { if (commissionRate.value === '') recalc() })
// 切换证券账户时，资金账户默认跟随为该证券账户（从其可用现金扣款）
// 编辑回填期间抑制此联动，避免覆盖原始资金账户
let suppressCashFollow = false
watch(securityAccountId, (val) => { if (val != null && !suppressCashFollow) cashAccountId.value = val })
// 切换账户分类时，重新加载对应分类的可选代码与价格
watch(currentCategory, () => { loadInstruments() })

// 理财货币改变时：自动加载最新汇率 + 重置资金账户到匹配币种的账户
watch(wealthCurrency, async (currency) => {
  if (currency && currency !== 'CNY') {
    const rate = exchangeRates.value.find((r) => r.currency_code === currency)
    wealthExchangeRate.value = rate ? String(rate.rate) : ''
  } else {
    wealthExchangeRate.value = currency === 'CNY' ? '1' : ''
  }
  // 自动选第一个匹配币种的资金账户
  const matched = wealthCashAccounts.value[0]
  cashAccountId.value = matched ? matched.id : null
})

// 赎回「兑换为人民币」切换时：更新汇率默认值并重置资金账户
watch(wealthRedeemToCny, async (toCny) => {
  if (!isWealth.value || isBuy.value) return
  const cur = redeemHoldingCurrency.value
  if (cur !== 'CNY') {
    if (toCny) {
      const rate = exchangeRates.value.find((r) => r.currency_code === cur)
      wealthExchangeRate.value = rate ? String(rate.rate) : ''
    } else {
      wealthExchangeRate.value = ''
    }
  }
  const matched = wealthRedeemCashAccounts.value[0]
  cashAccountId.value = matched ? matched.id : null
})

// 赎回选择持仓时：如果是外币产品，自动处理外汇账户
watch(symbol, () => {
  if (!isWealth.value || isBuy.value) return
  const cur = redeemHoldingCurrency.value
  if (cur !== 'CNY') {
    const matched = wealthRedeemCashAccounts.value[0]
    cashAccountId.value = matched ? matched.id : null
  }
})

async function loadMeta() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  // 锁定记账组：以打开时的账户（编辑账户优先，否则 preset）类型为准；无则默认证券组
  const anchorId = tradeStore.editTxn?.security_account_id ?? tradeStore.editTxn?.account_id ?? tradeStore.presetAccountId
  const anchor = anchorId ? accounts.value.find((a) => a.id === anchorId) : null
  lockedGroup.value = anchor ? tradeGroupOf(anchor.type) : 'securities'
  tags.value = await api.listTags(lid)
  holdings.value = await api.listHoldings(lid)
  feeRates.value = await api.listTradeFeeRates(lid)
  currencies.value = await api.listCurrencies(lid)
  exchangeRates.value = await api.listExchangeRates(lid)
  if (tradeStore.presetAccountId && stockAccounts.value.some((a) => a.id === tradeStore.presetAccountId)) {
    securityAccountId.value = tradeStore.presetAccountId
  } else if (!securityAccountId.value && stockAccounts.value.length) {
    securityAccountId.value = stockAccounts.value[0].id
  }
  // 资金默认从证券账户自身的可用现金扣除（需先转账充值进该账户）
  if (!cashAccountId.value) cashAccountId.value = securityAccountId.value ?? (cashAccounts.value[0]?.id ?? null)
  // 仅按当前账户对应的产品分类加载可选代码与价格，避免一次拉取数万条
  await loadInstruments()
}

// 按当前账户的产品分类加载金融产品与价格（数据量大时避免全量拉取）
async function loadInstruments() {
  const lid = ledgerStore.currentId
  if (!lid) return
  const cat = currentCategory.value
  // 无对应分类时不加载（避免一次性拉取数万条产品导致卡死）
  if (!cat) {
    instruments.value = []
    instrumentPrices.value = []
    return
  }
  // 证券代码极多：初始仅加载前 20 条，输入关键字时远程搜索更多
  instruments.value = await api.listInstruments(lid, cat, { limit: 20 })
  instrumentPrices.value = await api.listInstrumentPrices(lid, { category: cat })
}

// 证券代码下拉的远程搜索（输入关键字时按代码/名称过滤，限制返回条数）
const symbolLoading = ref(false)
let searchSeq = 0
async function searchSymbols(query: string) {
  const lid = ledgerStore.currentId
  const cat = currentCategory.value
  if (!lid || !cat) return
  const seq = ++searchSeq
  symbolLoading.value = true
  try {
    const kw = (query || '').trim()
    const rows = await api.listInstruments(lid, cat, { q: kw || undefined, limit: kw ? 50 : 20 })
    if (seq === searchSeq) instruments.value = rows
  } finally {
    if (seq === searchSeq) symbolLoading.value = false
  }
}

// 「更新代码」：从公开数据源同步当前账户分类的产品目录，补全本地缺失的代码后刷新列表
const SYNC_CATALOG_CATS = ['securities', 'open_fund', 'money_fund', 'metal']
const syncingCode = ref(false)
async function syncCodes() {
  const lid = ledgerStore.currentId
  const cat = currentCategory.value
  if (!lid || !cat) return
  if (!SYNC_CATALOG_CATS.includes(cat)) {
    // 不支持目录同步的分类（债券/期货等）：仅按当前输入回填名称与现价
    onSymbolChange()
    return
  }
  syncingCode.value = true
  try {
    const r = await api.syncMarketCatalog(lid, cat)
    if (r.added) ElMessage.success(`已同步 ${r.added} 个代码，当前共 ${r.total_existing} 个`)
    else ElMessage.info('代码已是最新')
    await loadInstruments()
  } catch (e) {
    ElMessage.error((e as Error).message || '同步代码失败，请稍后重试')
  } finally {
    syncingCode.value = false
  }
}


// 依据全局证券交易费率，回填印花税率与佣金比例（仅证券，非基金）
function applyDefaultRates() {
  if (isFund.value) return
  const row = feeRates.value.find((r) => r.security_type.includes('股票')) || feeRates.value[0]
  if (!row) return
  const stamp = isBuy.value ? Number(row.buy_stamp_tax) : Number(row.sell_stamp_tax)
  const comm = isBuy.value ? Number(row.buy_commission) : Number(row.sell_commission)
  if (stampRate.value === '') stampRate.value = stamp ? String(stamp) : '0'
  if (commissionRate.value === '') commissionRate.value = comm ? String(comm) : '0'
}

function reset() {
  symbol.value = ''
  name.value = ''
  price.value = ''
  quantity.value = ''
  wealthAmount.value = ''
  stampRate.value = ''
  stampTax.value = ''
  commissionRate.value = ''
  commission.value = ''
  transferFee.value = ''
  surcharge.value = ''
  feeTotal.value = '0.00'
  amountTotal.value = '0.00'
  tagIds.value = []
  remark.value = ''
  pnlAs.value = 'invest_income'
  occurredAt.value = new Date().toISOString().slice(0, 10)
  wealthCurrency.value = 'CNY'
  wealthExchangeRate.value = ''
  wealthRedeemToCny.value = false
}

// 选择证券代码时回填名称与现价
function onSymbolChange() {
  // 特殊项：[新增] —— 打开「新增理财产品」对话框
  if (symbol.value === '__add__') {
    symbol.value = ''
    openProductDialog()
    return
  }
  // 持仓信息（卖出时用于回填可卖数量）
  const h = accountHoldings.value.find((x) => x.symbol === symbol.value)
  // 优先从金融产品（之前创建的证券）匹配
  const inst = symbolOptions.value.find((i) => (i.code || i.name) === symbol.value)
  if (inst) {
    name.value = inst.name
    const p = latestPrice(symbol.value)
    if (p && !price.value) price.value = p
  } else if (h) {
    // 其次从持仓匹配
    name.value = h.name
    if (!price.value) price.value = h.price
  }
  // 卖出时自动回填当前持仓数量/份额（理财以金额记账，单独处理）
  if (!isBuy.value && h) {
    if (isWealth.value) {
      // 理财赎回：默认赎回全部累计金额（份额=金额，单价 1）
      wealthAmount.value = String(Number(h.quantity || 0))
    } else {
      // 证券卖出 / 基金赎回：回填当前持仓数量（份额）
      quantity.value = String(Number(h.quantity || 0))
    }
  }
}

// ---- 新增理财产品（内嵌，对应「管理金融产品 / 银行理财产品」） ----
const productDialog = ref(false)
const savingProduct = ref(false)
const TERM_UNITS = [
  { v: 'day', t: '日' },
  { v: 'month', t: '月' },
  { v: 'year', t: '年' },
]
const productForm = ref({
  name: '', code: '', currency: 'CNY', issuer: '',
  start_date: new Date().toISOString().slice(0, 10), end_date: '',
  term_value: '1', term_unit: 'month', expected_rate: '', guaranteed: false,
})

function openProductDialog() {
  productForm.value = {
    name: '', code: '', currency: 'CNY', issuer: '',
    start_date: new Date().toISOString().slice(0, 10), end_date: '',
    term_value: '1', term_unit: 'month', expected_rate: '', guaranteed: false,
  }
  productDialog.value = true
}

async function saveProduct() {
  const f = productForm.value
  if (!f.name.trim()) { ElMessage.warning('请输入产品名称'); return }
  if (!f.start_date) { ElMessage.warning('请选择收益起始日'); return }
  savingProduct.value = true
  try {
    const lid = ledgerStore.currentId as number
    const created = await api.createInstrument(lid, {
      category: 'bank_wealth',
      name: f.name.trim(),
      code: f.code || null,
      currency: f.currency || 'CNY',
      issuer: f.issuer || null,
      start_date: f.start_date || null,
      end_date: f.end_date || null,
      term_value: f.term_value !== '' ? Number(f.term_value) : null,
      term_unit: f.term_unit || null,
      expected_rate: f.expected_rate !== '' ? f.expected_rate : null,
      guaranteed: f.guaranteed,
    })
    instruments.value.push(created)
    // 自动选中新建的产品
    symbol.value = created.code || created.name
    name.value = created.name
    productDialog.value = false
    ElMessage.success('理财产品已新增')
  } finally {
    savingProduct.value = false
  }
}

function buildPayload() {
  const acc = accounts.value.find((a) => a.id === securityAccountId.value)
  // 银行理财：以「申购金额」记账，单价记为 1、份额即金额，无额外费用
  const wAmt = num(wealthAmount.value)
  // 外币理财：amount_total 保持外币金额（直接从外币账户扣款）；CNY 折算由 exchange_rate 在后端完成
  // CNY 理财：amount_total = wAmt
  const wealthRate = isWealth.value && wealthCurrency.value !== 'CNY' ? num(wealthExchangeRate.value) : 1
  const _ = wealthRate  // exchange_rate 传给后端折算持仓成本（unused in amtT）
  const p = isWealth.value ? '1' : (price.value || 0)
  const q = isWealth.value ? String(wAmt) : (quantity.value || 0)
  const feeT = isWealth.value ? '0' : (feeTotal.value || 0)
  const amtT = isWealth.value ? String(wAmt) : (amountTotal.value || 0)
  return {
    security_account_id: securityAccountId.value,
    cash_account_id: cashAccountId.value,
    symbol: symbol.value.trim(),
    name: name.value || symbol.value.trim(),
    sec_type: acc?.type || 'stock',
    price: p,
    quantity: q,
    stamp_tax: isWealth.value ? 0 : (stampTax.value || 0),
    commission: isWealth.value ? 0 : (commission.value || 0),
    transfer_fee: isWealth.value ? 0 : (transferFee.value || 0),
    surcharge: isWealth.value ? 0 : (surcharge.value || 0),
    fee_total: feeT,
    amount_total: amtT,
    occurred_at: occurredAt.value + 'T00:00:00',
    remark: remark.value || null,
    tag_ids: tagIds.value,
    ...(tradeStore.editTxn ? { edit_txn_id: tradeStore.editTxn.id } : {}),
    ...(isBuy.value ? {} : { pnl_as: pnlAs.value }),
    ...(isWealth.value && isBuy.value ? { 
      currency: wealthCurrency.value,
      exchange_rate: wealthExchangeRate.value ? num(wealthExchangeRate.value) : (wealthCurrency.value === 'CNY' ? 1 : null)
    } : {}),
    ...(isWealth.value && !isBuy.value && redeemHoldingCurrency.value !== 'CNY' ? {
      currency: redeemHoldingCurrency.value,
      exchange_rate: wealthRedeemToCny.value && wealthExchangeRate.value ? num(wealthExchangeRate.value) : null,
      redeem_to_cny: wealthRedeemToCny.value,
    } : {})
  }
}

function validate(): boolean {
  if (!securityAccountId.value) { ElMessage.warning('请选择' + accountLabel.value); return false }
  if (!cashAccountId.value) { ElMessage.warning('请选择资金账户'); return false }
  if (!symbol.value.trim()) { ElMessage.warning(isWealth.value ? '请选择产品名称' : (isMetal.value ? '请选择贵金属品种' : '请输入证券代码')); return false }
  // 卖出/赎回：标的必须是当前账户已有持仓
  if (!isBuy.value && !accountHoldings.value.some((h) => h.symbol === symbol.value)) {
    ElMessage.warning(isWealth.value ? '该账户没有此理财产品的持仓，无法赎回' : `该账户没有此${itemNoun.value}的持仓，无法卖出`)
    return false
  }
  if (isWealth.value) {
    if (!(num(wealthAmount.value) > 0)) { ElMessage.warning(isBuy.value ? '请输入申购金额' : '请输入赎回金额'); return false }
    if (isBuy.value && wealthCurrency.value !== 'CNY') {
      const cashAcc = accounts.value.find((a) => a.id === cashAccountId.value)
      if (!cashAcc) { ElMessage.warning('请选择资金账户'); return false }
      // 外汇账户（type=forex）持有多种货币，允许直接选用；普通账户需币种匹配
      if (cashAcc.type !== 'forex' && cashAcc.currency !== wealthCurrency.value) {
        ElMessage.warning(`外币理财申购的资金账户必须是 ${wealthCurrency.value} 账户或外汇账户`); return false
      }
      if (!(num(wealthExchangeRate.value) > 0)) { ElMessage.warning('请输入汇率'); return false }
    }
    return true
  }
  if (!(num(price.value) >= 0)) { ElMessage.warning('请输入价格'); return false }
  if (!(num(quantity.value) > 0)) { ElMessage.warning('请输入数量'); return false }
  return true
}

async function submit(keepOpen: boolean) {
  if (!validate()) return
  const lid = ledgerStore.currentId as number
  const payload = buildPayload()
  if (isBuy.value) {
    if (isIpo.value) {
      await api.ipoSubscribe(lid, payload)
      ElMessage.success('新股申购已记录')
    } else {
      await api.tradeBuy(lid, payload)
      ElMessage.success(isWealth.value ? '理财申购已记录' : (isMetal.value ? '贵金属买入已记录' : '证券买入已记录'))
    }
  } else {
    await api.tradeSell(lid, payload)
    ElMessage.success(isWealth.value ? '理财赎回已记录' : (isMetal.value ? '贵金属卖出已记录' : '证券卖出已记录'))
  }
  tradeStore.savedAt = Date.now()
  await loadMeta()
  if (keepOpen) {
    reset()
  } else {
    tradeStore.close()
  }
}

// 编辑模式：从原流水回填表单
function prefillEdit() {
  const e = tradeStore.editTxn
  if (!e) return
  // 证券账户=持仓所在；资金账户=流水 account_id。抑制「资金跟随证券」联动以保留原始资金账户
  suppressCashFollow = true
  securityAccountId.value = e.security_account_id ?? e.account_id
  cashAccountId.value = e.account_id
  symbol.value = e.symbol || ''
  name.value = e.name || ''
  price.value = e.price != null ? String(e.price) : ''
  quantity.value = e.quantity != null ? String(e.quantity) : ''
  // 理财：金额 = 价格×份额（price=1 时即份额）
  wealthAmount.value = e.quantity != null && e.price != null ? String(round2(Number(e.price) * Number(e.quantity))) : ''
  // 理财外币申购：回填币种和申购时汇率
  if (e.currency && e.currency !== 'CNY') {
    wealthCurrency.value = e.currency
    wealthExchangeRate.value = e.exchange_rate != null ? String(e.exchange_rate) : ''
  } else {
    wealthCurrency.value = 'CNY'
    wealthExchangeRate.value = ''
  }
  const comm = Number(e.commission || 0)
  const feeAll = Number(e.fee_total || 0)
  stampRate.value = ''
  commissionRate.value = ''
  stampTax.value = '0'
  commission.value = comm ? String(comm) : '0'
  transferFee.value = '0'
  surcharge.value = String(round2(feeAll - comm))
  tagIds.value = e.tag_ids ? [...e.tag_ids] : []
  remark.value = e.remark || ''
  if (e.occurred_at) occurredAt.value = e.occurred_at.slice(0, 10)
  recalc()
  // 待 securityAccountId 的 watch（post-flush）执行后再恢复联动
  nextTick(() => { suppressCashFollow = false })
}

watch(() => tradeStore.visible, (v) => {
  if (v) {
    reset()
    loadMeta().then(() => {
      if (tradeStore.editTxn) prefillEdit()
      else applyDefaultRates()
    })
  }
})
watch(() => tradeStore.mode, () => { if (tradeStore.visible && !tradeStore.editTxn) { reset(); applyDefaultRates() } })
</script>

<template>
  <el-dialog
    v-model="tradeStore.visible"
    :title="title"
    width="92%"
    style="max-width:760px"
    :close-on-click-modal="false"
  >
    <el-form label-width="90px" class="trade-form">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="accountLabel" required>
            <el-select v-model="securityAccountId" :placeholder="'选择' + accountLabel" style="width:100%">
              <el-option v-for="a in stockAccounts" :key="a.id" :label="a.name" :value="a.id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="资金账户">
            <el-select v-model="cashAccountId" placeholder="选择资金账户" style="width:100%">
              <el-option
                v-for="a in (isWealth ? (isBuy ? wealthCashAccounts : wealthRedeemCashAccounts) : cashAccounts)"
                :key="a.id"
                :label="a.type === 'forex' ? `${a.name} [外汇]` : (a.currency !== 'CNY' ? `${a.name} (${a.currency})` : a.name)"
                :value="a.id"
              />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="isWealth ? '产品名称' : (isFund ? '基金代码' : (isMetal ? '贵金属品种' : '证券代码'))" required>
            <div class="code-row">
              <el-select
                v-model="symbol"
                filterable
                :remote="isBuy && !isWealth"
                :remote-method="searchSymbols"
                :loading="symbolLoading"
                remote-show-suffix
                reserve-keyword
                default-first-option
                :placeholder="isBuy ? (isWealth ? '在此处输入文字以进行过滤' : '输入代码或名称搜索') : ('选择持仓' + itemNoun)"
                class="code-select"
                @change="onSymbolChange"
              >
                <!-- 买入：仅「管理金融产品」里建档的产品；卖出：仅当前账户已有持仓 -->
                <template v-if="isBuy">
                  <el-option
                    v-if="symbol && symbol !== '__add__' && !symbolOptions.some((i) => (i.code || i.name) === symbol)"
                    :key="'cur-' + symbol"
                    :label="name ? (isWealth ? name : `${symbol} ${name}`) : symbol"
                    :value="symbol"
                  />
                  <el-option
                    v-for="i in symbolOptions"
                    :key="'inst-' + i.id"
                    :label="isWealth ? i.name : `${i.code || ''} ${i.name}`"
                    :value="i.code || i.name"
                  />
                  <el-option v-if="isWealth" label="[新增]" value="__add__" />
                </template>
                <template v-else>
                  <el-option
                    v-for="h in accountHoldings"
                    :key="'hold-' + h.id"
                    :label="isWealth ? h.name : `${h.symbol} ${h.name}`"
                    :value="h.symbol || ''"
                  />
                </template>
              </el-select>
              <el-button v-if="!isWealth" class="code-btn" :loading="syncingCode" @click="syncCodes">更新代码</el-button>
            </div>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item v-if="isWealth" :label="isBuy ? '申购金额' : '赎回金额'" required>
            <el-input v-model="wealthAmount" type="number" placeholder="0.00" />
          </el-form-item>
          <el-form-item v-else-if="!isBuy" label="本次盈亏记为">
            <el-select v-model="pnlAs" style="width:100%">
              <el-option label="投资收益" value="invest_income" />
              <el-option label="其它收入" value="other_income" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row v-if="isWealth && isBuy" :gutter="16">
        <el-col :span="12">
          <el-form-item label="币种">
            <el-select v-model="wealthCurrency" style="width:100%">
              <el-option
                v-for="curr in currencies"
                :key="curr.code"
                :label="`${curr.code} ${curr.name}`"
                :value="curr.code"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item v-if="wealthCurrency !== 'CNY'" label="汇率" required>
            <el-input v-model="wealthExchangeRate" type="number" placeholder="0.00" />
          </el-form-item>
        </el-col>
      </el-row>

      <!-- 外币理财赎回：选择回款方式（原币/兑换CNY）及汇率 -->
      <el-row v-if="isWealth && !isBuy && redeemHoldingCurrency !== 'CNY'" :gutter="16">
        <el-col :span="12">
          <el-form-item label="回款方式">
            <el-radio-group v-model="wealthRedeemToCny">
              <el-radio :value="false">原币（{{ redeemHoldingCurrency }}）退回</el-radio>
              <el-radio :value="true">兑换为人民币</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item v-if="wealthRedeemToCny" label="兑换汇率" required>
            <el-input v-model="wealthExchangeRate" type="number" placeholder="1 USD ≈ ? CNY" />
          </el-form-item>
        </el-col>
      </el-row>

      <template v-if="!isWealth">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="isFund ? '净值' : '价格'" required>
            <el-input v-model="price" type="number" placeholder="0.00" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="isFund ? '份额' : '数量'" required>
            <el-input v-model="quantity" type="number" placeholder="0" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label-width="20px">
        <el-checkbox v-model="showFee">显示费用详情</el-checkbox>
      </el-form-item>

      <template v-if="showFee">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="isFund ? ((isBuy ? '申购' : '赎回') + '费率 %') : '印花税率 %'">
              <el-input v-model="stampRate" type="number" placeholder="0.00" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="isFund ? ((isBuy ? '申购' : '赎回') + '费') : '印花税费'">
              <el-input v-model="stampTax" type="number" placeholder="0.00" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="佣金比例 %">
              <el-input v-model="commissionRate" type="number" placeholder="0.00" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="佣金">
              <el-input v-model="commission" type="number" placeholder="0.00" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row v-if="!isFund" :gutter="16">
          <el-col :span="12">
            <el-form-item label="过户费">
              <el-input v-model="transferFee" type="number" placeholder="0.00" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="附加费">
              <el-input v-model="surcharge" type="number" placeholder="0.00" />
            </el-form-item>
          </el-col>
        </el-row>
      </template>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="费用小计" required>
            <el-input v-model="feeTotal" type="number" readonly />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="金额合计" required>
            <el-input v-model="amountTotal" type="number" readonly />
          </el-form-item>
        </el-col>
      </el-row>
      </template>

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
            <el-input v-model="remark" type="textarea" :rows="2" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="日期" required>
        <el-date-picker v-model="occurredAt" type="date" value-format="YYYY-MM-DD" style="width:240px" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="submit(true)">保存并继续</el-button>
      <el-button type="primary" @click="submit(false)">确定</el-button>
    </template>
  </el-dialog>

  <!-- 新增理财产品（对应「管理金融产品 / 银行理财产品」） -->
  <el-dialog
    v-model="productDialog"
    title="银行理财产品"
    width="92%"
    style="max-width:620px"
    append-to-body
    :close-on-click-modal="false"
  >
    <el-form label-width="100px">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="产品名称" required>
            <el-input v-model="productForm.name" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="币种" required>
            <el-select v-model="productForm.currency" style="width:100%">
              <el-option label="人民币 CNY" value="CNY" />
              <el-option label="美元 USD" value="USD" />
              <el-option label="港币 HKD" value="HKD" />
              <el-option label="欧元 EUR" value="EUR" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="产品代码">
            <el-input v-model="productForm.code" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="发行机构">
            <el-input v-model="productForm.issuer" placeholder="<无>" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="收益起始日" required>
            <el-date-picker v-model="productForm.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="委托期">
            <div style="display:flex;gap:8px;width:100%">
              <el-input v-model="productForm.term_value" type="number" style="flex:1" />
              <el-select v-model="productForm.term_unit" style="width:90px">
                <el-option v-for="u in TERM_UNITS" :key="u.v" :label="u.t" :value="u.v" />
              </el-select>
            </div>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="收益终止日">
            <el-date-picker v-model="productForm.end_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="是否保本">
            <el-checkbox v-model="productForm.guaranteed" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="预期年收益率(%)">
            <el-input v-model="productForm.expected_rate" type="number" placeholder="0.00" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>
    <template #footer>
      <el-button @click="productDialog = false">取消</el-button>
      <el-button type="primary" :loading="savingProduct" @click="saveProduct">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.trade-form :deep(.el-input.is-disabled .el-input__inner),
.trade-form :deep(input[readonly]) {
  background: #f5f7fa;
}

.code-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.code-row .code-select {
  flex: 1;
}

.code-row .code-btn {
  flex: 0 0 auto;
}
</style>
