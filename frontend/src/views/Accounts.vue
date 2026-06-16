<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useP2pStore } from '../stores/p2p'
import { useLoanStore } from '../stores/loan'
import { useMajorAssetStore } from '../stores/majorAsset'
import type { Account, AccountGroup, Party } from '../types'
import { fmtMoney } from '../utils/format'

const router = useRouter()
const ledgerStore = useLedgerStore()
const p2pStore = useP2pStore()
const loanStore = useLoanStore()
const majorAssetStore = useMajorAssetStore()

// 打开账户记账：网贷账户有自己的记账模式（展示已有网贷项目，点记账再弹窗）
function openAccountRecord(a: Account) {
  if (a.type === 'p2p') return router.push({ path: '/p2p', query: { account_id: String(a.id) } })
  if (a.type === 'loan') return router.push({ path: '/loans', query: { account_id: String(a.id) } })
  if (a.type === 'insurance') return router.push({ path: '/insurance', query: { account_id: String(a.id) } })
  if (a.type === 'major_asset') return router.push({ path: '/major-assets', query: { account_id: String(a.id) } })
  if (a.type === 'credit') return router.push({ path: '/credit', query: { account_id: String(a.id) } })
  if (a.type === 'forex') return router.push({ path: '/forex', query: { account_id: String(a.id) } })
  if (a.type === 'metal' || a.type === 'metal_td') return router.push({ path: '/metal', query: { account_id: String(a.id) } })
  if (a.type === 'voucher') return router.push({ path: '/voucher', query: { account_id: String(a.id) } })
  if (['fund', 'open_fund', 'money_fund'].includes(a.type)) return router.push({ path: '/funds', query: { account_id: String(a.id) } })
  if (a.type === 'wealth') return router.push({ path: '/wealth', query: { account_id: String(a.id) } })
  // 证券类投资账户进入独立的证券账户页面
  const INVEST_TYPES = ['stock', 'bond', 'reverse_repo', 'futures', 'margin']
  if (INVEST_TYPES.includes(a.type)) return router.push({ path: '/securities', query: { account_id: String(a.id) } })
  router.push({ path: '/transactions', query: { account_id: String(a.id) } })
}
const accounts = ref<Account[]>([])
const accountGroups = ref<AccountGroup[]>([])
const parties = ref<Party[]>([])
const dialog = ref(false)
const editingId = ref<number | null>(null)
const form = ref<any>({ name: '', type: 'cash', group_id: null, icon: '💰', initial_balance: 0, currency: 'CNY', credit_limit: null, bill_day: null, repay_day: null, owner: '', remark: '', card_no: '', bank_name: '', start_date: '', expiry: '', cash_limit: null, min_repay_ratio: null, annual_fee: null, fee_waiver_type: 'count', fee_waiver_count: null, fee_waiver_amount: null, repay_type: 'fixed', repay_after_days: null, bill_day_txn: 'next', overdraft_remind: false, platform_name: '', platform_url: '', insured_person: '', city: '', social_code: '', premium_as_stat: false, include_in_net: true })
const collapsed = ref<Record<string, boolean>>({})
const filterType = ref('')
const viewMode = ref<'type' | 'group'>('type')
const showHidden = ref(false)
const showClosed = ref(false)

// 新增账户：类型选择器
const typePicker = ref(false)
// 币种列表（双币信用卡向导 / 外汇向导用）
const currencies = ref<{ id: number; name: string; code: string; rate: string | number }[]>([])
// 双币信用卡向导
const cwVisible = ref(false)
const cwStep = ref(1)
const cwForm = ref<{
  name: string; owner: string; remark: string;
  start_date: string; bill_day: number | null; bill_day_last: boolean;
  repay_type: string; repay_after_days: number | null; repay_day: number | null;
  currency: string; overdraft1: number | null; overdraft_remind: boolean;
  currency2: string; overdraft2: number | null; overdraft_remind2: boolean;
}>({
  name: '我的双币信用卡', owner: '', remark: '',
  start_date: new Date().toISOString().slice(0, 10), bill_day: 1, bill_day_last: false,
  repay_type: 'after_bill', repay_after_days: 1, repay_day: null,
  currency: 'CNY', overdraft1: null, overdraft_remind: false,
  currency2: 'USD', overdraft2: null, overdraft_remind2: false
})
// 上市证券账户向导
const STOCK_MARKETS = [
  { v: 'A', t: 'A股', currency: 'CNY' },
  { v: 'SHB', t: '沪B股', currency: 'USD' },
  { v: 'SZB', t: '深B股', currency: 'HKD' },
  { v: 'H', t: 'H股', currency: 'HKD' },
  { v: 'US', t: 'NASDAQ、NYSE', currency: 'USD' },
  { v: 'OTHER', t: '其它', currency: 'CNY' }
]
// 投资账户向导元信息：哪些账户类型走两步向导，及其标题/说明/图标/是否带市场类型
const INVEST_WIZARDS: Record<string, { title: string; intro: string; icon: string; market: boolean; defaultName: string }> = {
  stock: {
    title: '上市证券账户', icon: '📈', market: true, defaultName: '我的上市证券',
    intro: '您可创建证券交易账户，专业管理在证券公司开立的股票、权证、上市基金及债券等投资账户。完整记录买卖委托、成交明细、持仓变动等交易活动，实时跟踪投资组合表现，为您提供专业的投资管理解决方案。'
  },
  wealth: {
    title: '银行理财产品账户', icon: '🏦', market: false, defaultName: '我的银行理财产品',
    intro: '您可创建多个银行理财账户，专业管理不同币种的理财产品投资。每个账户支持记录多款同币种理财产品的申购、赎回、收益分配等完整交易流程，实现银行理财产品的精细化管理和收益分析。'
  },
  fund: {
    title: '开放式基金账户', icon: '📊', market: false, defaultName: '我的开放式基金',
    intro: '您可创建多个开放式基金账户，专业管理在不同基金公司开立的基金投资。完整记录申购、赎回、分红及净值变动等交易明细，跟踪持仓收益与收益率，为您提供便捷的基金投资管理工具。'
  },
  money_fund: {
    title: '货币基金账户', icon: '💰', market: false, defaultName: '我的货币基金',
    intro: '您可创建多个货币基金账户，专业管理在不同基金公司开立的货币基金投资。完整记录申购、赎回及收益结转等交易明细，监控资金流动性和收益率，为您提供便捷的现金管理工具。'
  },
  forex: {
    title: '外汇交易账户', icon: '💱', market: false, defaultName: '我的外汇',
    intro: '您可创建外汇交易账户，专业管理在银行及金融机构开立的外汇投资账户。支持多币种管理，完整记录外汇买卖、汇率转换及利息收支等交易明细，实时跟踪各币种持仓与折算价值。'
  }
}
const swVisible = ref(false)
const swStep = ref(1)
const swType = ref<string>('stock')
const swMeta = computed(() => INVEST_WIZARDS[swType.value] || INVEST_WIZARDS.stock)
const swForm = ref<{
  name: string; market: string; currency: string; owner: string; remark: string; group_id: number | null;
  date: string; fund_source: 'self' | 'other'; amount: number | null; from_account_id: number | null;
  asset_nature: 'invest' | 'save';
  extra_currencies: { code: string; amount: number | null }[];
}>({
  name: '我的上市证券', market: 'A', currency: 'CNY', owner: '', remark: '', group_id: null,
  date: new Date().toISOString().slice(0, 10), fund_source: 'self', amount: 0, from_account_id: null,
  asset_nature: 'invest', extra_currencies: []
})
// 外汇账户向导：含第三步「增加其它币种」
const isForexWizard = computed(() => swType.value === 'forex')
const swMaxStep = computed(() => (isForexWizard.value ? 3 : 2))
function swCurRate(code: string): number {
  const c = currencies.value.find((x) => x.code === code)
  return c ? Number(c.rate) || 1 : 1
}
function addExtraCurrency() {
  const used = new Set([swForm.value.currency, ...swForm.value.extra_currencies.map((x) => x.code)])
  const next = currencies.value.find((c) => !used.has(c.code))
  swForm.value.extra_currencies.push({ code: next ? next.code : 'USD', amount: null })
}
function removeExtraCurrency(i: number) {
  swForm.value.extra_currencies.splice(i, 1)
}
const groupDialog = ref(false)
const groupForm = ref<{ name: string; remark: string }>({ name: '', remark: '' })
// 人员与机构弹窗
const partyDialog = ref(false)
const partyTarget = ref<'owner' | 'bank'>('owner')
const partyForm = ref<{ name: string; type: string; contact: string; address: string }>({ name: '', type: 'org', contact: '', address: '' })
const partyTypes = [
  { v: 'member', t: '家庭成员' },
  { v: 'contact', t: '往来人员' },
  { v: 'org', t: '机构' }
]

const owners = computed(() => parties.value.filter((p) => p.type === 'member'))
const banks = computed(() => parties.value.filter((p) => p.type === 'org'))

// 证券账户向导「资金来源-其它账户」可选的现金/储蓄类账户
const fundSourceAccounts = computed(() =>
  accounts.value.filter((a) => ['cash', 'bank', 'wallet', 'prepaid'].includes(a.type) && (a.status || 'active') === 'active')
)

// 新增资产账户类型选择（图3）
const typePicker_sections = [
  {
    label: '现金储蓄',
    items: [
      { v: 'cash', t: '现金' }, { v: 'credit', t: '信用卡' },
      { v: 'dual_credit', t: '双币信用卡' },
      { v: 'bank', t: '储蓄卡' }, { v: 'prepaid', t: '第三方储值' },
      { v: 'voucher', t: '团购券' }
    ]
  },
  {
    label: '金融投资',
    items: [
      { v: 'stock', t: '上市证券' }, { v: 'fund', t: '基金' }, { v: 'money_fund', t: '货币基金' },
      { v: 'bond', t: '债券' },
      { v: 'wealth', t: '银行理财产品' }, { v: 'metal', t: '贵金属' },
      { v: 'margin', t: '融资融券' }, { v: 'p2p', t: '网贷' },
      { v: 'futures', t: '期货' }, { v: 'forex', t: '外汇' }
    ]
  },
  {
    label: '重大资产',
    items: [
      { v: 'major_asset', t: '房产' }, { v: 'major_asset', t: '汽车' },
      { v: 'goods', t: '家居物品' }, { v: 'major_asset', t: '其它重大资产' }
    ]
  },
  {
    label: '债权债务',
    items: [
      { v: 'loan:payable', t: '借入' }, { v: 'loan:receivable', t: '借出' },
      { v: 'loan:receivable', t: '预收/预付' }, { v: 'loan:payable', t: '垫付/待摊' }
    ]
  },
  {
    label: '保险',
    items: [
      { v: 'insurance', t: '社保' }, { v: 'insurance', t: '商业保险' }
    ]
  }
]

const types = [
  { v: 'cash', t: '现金' }, { v: 'bank', t: '储蓄卡' }, { v: 'credit', t: '信用卡' },
  { v: 'wallet', t: '电子钱包' }, { v: 'prepaid', t: '储值卡' }, { v: 'stock', t: '股票' },
  { v: 'fund', t: '基金' }, { v: 'money_fund', t: '货币基金' }, { v: 'bond', t: '债券' },
  { v: 'reverse_repo', t: '逆回购' }, { v: 'wealth', t: '理财' }, { v: 'metal', t: '贵金属' },
  { v: 'metal_td', t: '贵金属T+D' }, { v: 'forex', t: '外汇' }, { v: 'futures', t: '期货' },
  { v: 'margin', t: '融资融券' }, { v: 'p2p', t: 'P2P/网贷' }, { v: 'goods', t: '实物商品' },
  { v: 'major_asset', t: '大件资产' }, { v: 'insurance', t: '保险' }, { v: 'loan', t: '负债/贷款' },
  { v: 'voucher', t: '团购券' }
]

const groupLabel: Record<string, string> = {
  cash: '现金', bank: '银行存款', wallet: '第三方储值', prepaid: '第三方储值',
  credit: '信用卡', stock: '金融投资', fund: '金融投资', open_fund: '金融投资', money_fund: '金融投资',
  bond: '金融投资', reverse_repo: '金融投资', wealth: '金融投资', metal: '金融投资',
  metal_td: '金融投资', forex: '金融投资', futures: '金融投资', margin: '金融投资',
  p2p: '金融投资', goods: '重大资产', major_asset: '重大资产', insurance: '保险', loan: '债权债务',
  voucher: '团购券'
}

const typeText = (v: string) => types.find((t) => t.v === v)?.t || v

const currencyText = (v?: string | null) => {
  const map: Record<string, string> = { CNY: '人民币', USD: '美元', HKD: '港币', EUR: '欧元' }
  return map[v || 'CNY'] || v || '人民币'
}

// 账户副信息行：开户银行 | 币种 | 所有者（仅显示已填写项）
function accountSub(a: Account): string {
  return [a.bank_name, currencyText(a.currency), a.owner].filter(Boolean).join(' | ')
}

const filtered = computed(() => {
  let list = accounts.value
  // 状态过滤：默认隐藏「隐藏」与「注销」账户，可通过操作菜单显示
  list = list.filter((a) => {
    const st = a.status || 'active'
    if (st === 'hidden') return showHidden.value
    if (st === 'closed') return showClosed.value
    return true
  })
  if (filterType.value) list = list.filter((a) => a.type === filterType.value)
  return list
})

const statusText = (a: Account) =>
  a.status === 'hidden' ? '隐藏' : a.status === 'closed' ? '注销' : ''

const groups = computed(() => {
  const g = new Map<string, Account[]>()
  for (const a of filtered.value) {
    let name: string
    if (viewMode.value === 'group') {
      // 自定义分组视角：归入所属账户组，未指定则为「无账户组」
      const custom = accountGroups.value.find((x) => x.id === a.group_id)
      name = custom ? custom.name : '无账户组'
    } else if (a.type === 'loan') {
      // 债权债务账户：按余额正负分入「应收款 / 应付款」
      name = Number(a.current_balance || 0) < 0 ? '应付款' : '应收款'
    } else {
      name = groupLabel[a.type] || '其他账户'
    }
    if (!g.has(name)) g.set(name, [])
    g.get(name)!.push(a)
  }
  let entries = Array.from(g.entries())
  if (viewMode.value === 'group') {
    // 排序：无账户组在前，其余按账户组定义顺序
    const orderOf = (name: string) => {
      if (name === '无账户组') return -1
      const grp = accountGroups.value.find((x) => x.name === name)
      return grp ? grp.sort_order * 1000 + grp.id : 999999
    }
    entries = entries.sort((a, b) => orderOf(a[0]) - orderOf(b[0]))
  }
  return entries.map(([name, items]) => ({
    name,
    items,
    total: items.reduce((s, a) => s + Number(a.current_balance || 0), 0)
  }))
})

const assets = computed(() => accounts.value.reduce((s, a) => s + Math.max(0, Number(a.current_balance || 0)), 0))
const liabilities = computed(() => accounts.value.reduce((s, a) => s + Math.min(0, Number(a.current_balance || 0)), 0))
const netWorth = computed(() => assets.value + liabilities.value)

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  accountGroups.value = await api.listAccountGroups(lid)
  parties.value = await api.listParties(lid)
  currencies.value = await api.listCurrencies(lid)
}

function toggleGroup(name: string) {
  collapsed.value[name] = !collapsed.value[name]
}

// 账户名校验：必填且同账本内不可重复（excludeId 用于编辑时排除自身）。
// 校验通过返回处理后的名称，否则提示并返回 null。
function validAccountName(raw: string | null | undefined, excludeId?: number | null): string | null {
  const name = (raw || '').trim()
  if (!name) {
    ElMessage.warning('请输入账户名称')
    return null
  }
  const dup = accounts.value.some((a) => a.name === name && a.id !== excludeId)
  if (dup) {
    ElMessage.warning(`账户名称「${name}」已存在`)
    return null
  }
  return name
}

// ---- 账户组 ----
function openGroupDialog() {
  groupForm.value = { name: '', remark: '' }
  groupDialog.value = true
}

async function saveGroup() {
  if (!groupForm.value.name) return ElMessage.warning('请输入账户组名')
  await api.createAccountGroup(ledgerStore.currentId as number, { ...groupForm.value })
  ElMessage.success('已创建账户组')
  groupDialog.value = false
  viewMode.value = 'group'
  load()
}

async function removeGroup(g: AccountGroup) {
  try {
    await ElMessageBox.confirm(`确定删除账户组「${g.name}」吗？组内账户将变为未分组`, '提示', { type: 'warning' })
    await api.deleteAccountGroup(g.id)
    ElMessage.success('已删除')
    load()
  } catch (e) { /* cancelled */ }
}

// ---- 人员与机构 ----
function openPartyDialog(target: 'owner' | 'bank') {
  partyTarget.value = target
  partyForm.value = { name: '', type: target === 'bank' ? 'org' : 'member', contact: '', address: '' }
  partyDialog.value = true
}

async function saveParty() {
  if (!partyForm.value.name) return ElMessage.warning('请输入名称')
  const p = await api.createParty(ledgerStore.currentId as number, { ...partyForm.value })
  parties.value.push(p)
  if (partyTarget.value === 'bank') form.value.bank_name = p.name
  else form.value.owner = p.name
  ElMessage.success('已保存')
  partyDialog.value = false
}

// ---- 新增账户 ----
function openTypePicker() {
  typePicker.value = true
}

function pickType(v: string, label = '') {
  typePicker.value = false
  if (v === 'dual_credit') return openCardWizard()
  if (INVEST_WIZARDS[v]) return openInvestWizard(v)
  // 重大资产：使用「重大资产买入」对话框（房产/汽车默认自用，其它默认投资）
  if (v === 'major_asset') {
    const nature = (label === '房产' || label === '汽车') ? 'own' : 'invest'
    return majorAssetStore.open(nature)
  }
  // 债权债务：直接弹出借入/借出表单，不跳转
  if (v.startsWith('loan')) {
    const dir = v === 'loan:receivable' ? 'receivable' : 'payable'
    return loanStore.open(dir)
  }
  editingId.value = null
  form.value = { name: '', type: v, group_id: null, icon: '💰', initial_balance: 0, currency: 'CNY', credit_limit: null, bill_day: null, repay_day: null, owner: '', remark: '', card_no: '', bank_name: '', start_date: '', expiry: '', cash_limit: null, min_repay_ratio: null, annual_fee: null, fee_waiver_type: 'count', fee_waiver_count: null, fee_waiver_amount: null, repay_type: 'fixed', repay_after_days: null, bill_day_txn: 'next', overdraft_remind: false, platform_name: '', platform_url: '', insured_person: '', city: '', social_code: '', premium_as_stat: false, include_in_net: true }
  dialog.value = true
}

// ---- 双币信用卡向导 ----
function openCardWizard() {
  cwStep.value = 1
  cwForm.value = {
    name: '我的双币信用卡', owner: '', remark: '',
    start_date: new Date().toISOString().slice(0, 10), bill_day: 1, bill_day_last: false,
    repay_type: 'after_bill', repay_after_days: 1, repay_day: null,
    currency: 'CNY', overdraft1: null, overdraft_remind: false,
    currency2: 'USD', overdraft2: null, overdraft_remind2: false
  }
  cwVisible.value = true
}

function cwNext() {
  if (cwStep.value === 1 && !cwForm.value.name.trim()) {
    ElMessage.warning('请输入账户名称')
    return
  }
  if (cwStep.value < 3) cwStep.value += 1
}

function cwPrev() {
  if (cwStep.value > 1) cwStep.value -= 1
}

async function cwFinish() {
  const f = cwForm.value
  if (!f.name.trim()) {
    ElMessage.warning('请输入账户名称')
    return
  }
  if (!f.currency || !f.currency2) {
    ElMessage.warning('请选择两种币种')
    return
  }
  if (f.currency === f.currency2) {
    ElMessage.warning('两种币种不能相同')
    return
  }
  // 双币信用卡 = 两个不同币种的独立信用卡账户，共享账单日/还款设置
  const base = {
    type: 'credit', group_id: null, icon: '💳',
    owner: f.owner || '', remark: f.remark || '',
    start_date: f.start_date || '',
    bill_day: f.bill_day_last ? null : f.bill_day,
    bill_day_last: f.bill_day_last,
    repay_type: f.repay_type,
    repay_after_days: f.repay_type === 'after_bill' ? f.repay_after_days : null,
    repay_day: f.repay_type === 'fixed' ? f.repay_day : null,
    include_in_net: true
  }
  const baseName = f.name.trim()
  const lid = ledgerStore.currentId as number
  // 双币信用卡生成两个带币种后缀的账户名，二者均需必填且不可重名
  const name1 = validAccountName(`${baseName}（${f.currency}）`)
  if (!name1) return
  const name2 = validAccountName(`${baseName}（${f.currency2}）`)
  if (!name2) return
  // 币种1账户
  await api.createAccount(lid, {
    ...base,
    name: `${baseName}（${f.currency}）`,
    currency: f.currency,
    initial_balance: String(-(Number(f.overdraft1) || 0)),
    overdraft1: Number(f.overdraft1) || 0,
    overdraft_remind: f.overdraft_remind
  })
  // 币种2账户
  await api.createAccount(lid, {
    ...base,
    name: `${baseName}（${f.currency2}）`,
    currency: f.currency2,
    initial_balance: String(-(Number(f.overdraft2) || 0)),
    overdraft1: Number(f.overdraft2) || 0,
    overdraft_remind: f.overdraft_remind2
  })
  ElMessage.success('双币信用卡已创建（两个币种账户）')
  cwVisible.value = false
  load()
}

// ---- 上市证券 / 银行理财等投资账户向导 ----
function openInvestWizard(type: string) {
  swType.value = type
  swStep.value = 1
  const meta = INVEST_WIZARDS[type]
  swForm.value = {
    name: meta.defaultName, market: 'A', currency: 'CNY', owner: '', remark: '', group_id: null,
    date: new Date().toISOString().slice(0, 10), fund_source: 'self', amount: 0, from_account_id: null,
    asset_nature: 'invest', extra_currencies: []
  }
  swVisible.value = true
}

// 选择市场类型后自动联动币种
function onStockMarketChange(v: string) {
  const m = STOCK_MARKETS.find((x) => x.v === v)
  if (m) swForm.value.currency = m.currency
}

function swNext() {
  if (swStep.value === 1 && !swForm.value.name.trim()) {
    ElMessage.warning('请输入账户名称')
    return
  }
  if (swStep.value < swMaxStep.value) swStep.value += 1
}

function swPrev() {
  if (swStep.value > 1) swStep.value -= 1
}

async function swFinish() {
  const f = swForm.value
  const okName = validAccountName(f.name)
  if (!okName) return
  f.name = okName
  const lid = ledgerStore.currentId as number
  const meta = swMeta.value

  // 外汇账户：创建账户后，按主币种与「其它币种」逐一建立持仓（type=forex）
  if (isForexWizard.value) {
    const acc = await api.createAccount(lid, {
      name: f.name.trim(), type: 'forex', group_id: f.group_id, icon: meta.icon,
      currency: f.currency, owner: f.owner || '', remark: f.remark || '',
      start_date: f.date || '', initial_balance: '0', include_in_net: true
    })
    // 主币种持仓（账户余额）
    const rows: { code: string; amount: number }[] = []
    const mainAmt = Number(f.amount) || 0
    rows.push({ code: f.currency, amount: mainAmt })
    for (const ec of f.extra_currencies) {
      const amt = Number(ec.amount) || 0
      if (ec.code && !rows.some((r) => r.code === ec.code)) rows.push({ code: ec.code, amount: amt })
    }
    for (const r of rows) {
      const rate = swCurRate(r.code)
      const cur = currencies.value.find((c) => c.code === r.code)
      await api.createHolding(lid, {
        account_id: acc.id, symbol: r.code, name: cur ? cur.name : r.code, type: 'forex',
        quantity: r.amount, price: rate, cost: Math.round(r.amount * rate * 100) / 100
      })
    }
    ElMessage.success(`${meta.title}已创建`)
    swVisible.value = false
    load()
    return
  }

  const amount = Number(f.amount) || 0
  if (f.fund_source === 'other') {
    if (!f.from_account_id) {
      ElMessage.warning('请选择转入资金的来源账户')
      return
    }
    if (amount <= 0) {
      ElMessage.warning('请输入大于 0 的转入金额')
      return
    }
  }
  const payload: any = {
    name: f.name.trim(), type: swType.value, group_id: f.group_id, icon: meta.icon,
    currency: f.currency,
    owner: f.owner || '', remark: f.remark || '', start_date: f.date || '',
    // 资金来源为「账户自身余额」时作为初始余额；「其它账户」时由转账形成余额
    initial_balance: f.fund_source === 'self' ? amount : 0,
    include_in_net: true
  }
  // 仅上市证券带市场类型
  if (meta.market) payload.stock_market = f.market
  // 货币基金带资产性质（投资 / 储蓄）
  if (swType.value === 'money_fund') payload.asset_nature = f.asset_nature
  const acc = await api.createAccount(lid, payload)
  // 资金来源为其它账户：创建一笔转账，把资金从来源账户转入投资账户
  if (f.fund_source === 'other' && f.from_account_id) {
    await api.transferTransaction(lid, {
      from_account_id: f.from_account_id,
      to_account_id: acc.id,
      amount,
      currency: f.currency,
      occurred_at: f.date ? `${f.date}T00:00:00` : undefined,
      remark: `${meta.title}初始资金转入：${f.name.trim()}`
    })
  }
  ElMessage.success(`${meta.title}已创建`)
  swVisible.value = false
  load()
}

function openEdit(a: Account) {
  editingId.value = a.id
  form.value = {
    name: a.name, type: a.type, group_id: a.group_id ?? null, icon: a.icon,
    initial_balance: a.initial_balance, currency: a.currency || 'CNY',
    credit_limit: a.credit_limit, bill_day: a.bill_day, repay_day: a.repay_day,
    owner: a.owner ?? '', remark: a.remark ?? '', card_no: a.card_no ?? '',
    bank_name: a.bank_name ?? '', start_date: a.start_date ?? '', expiry: a.expiry ?? '',
    cash_limit: a.cash_limit, min_repay_ratio: a.min_repay_ratio, annual_fee: a.annual_fee,
    fee_waiver_type: a.fee_waiver_type || 'count', fee_waiver_count: a.fee_waiver_count,
    fee_waiver_amount: a.fee_waiver_amount, repay_type: a.repay_type || 'fixed',
    repay_after_days: a.repay_after_days, bill_day_txn: a.bill_day_txn || 'next',
    overdraft_remind: a.overdraft_remind ?? false,
    platform_name: a.platform_name ?? '', platform_url: a.platform_url ?? '',
    insured_person: a.insured_person ?? '', city: a.city ?? '', social_code: a.social_code ?? '',
    premium_as_stat: a.premium_as_stat ?? false,
    stock_market: a.stock_market ?? null,
    include_in_net: a.include_in_net
  }
  dialog.value = true
}

async function save() {
  const name = validAccountName(form.value.name, editingId.value)
  if (!name) return
  form.value.name = name
  try {
    if (editingId.value) {
      const { initial_balance, ...rest } = form.value
      await api.updateAccount(editingId.value, rest)
      ElMessage.success('已更新')
    } else {
      await api.createAccount(ledgerStore.currentId as number, form.value)
      ElMessage.success('已创建')
    }
  } catch (e) {
    return ElMessage.error((e as Error).message || '保存失败')
  }
  dialog.value = false
  load()
}

async function adjust(a: Account) {
  try {
    const { value, action } = await ElMessageBox.prompt(
      '请输入该账户的实际余额。确定=记为余额调整（不计入收支）；可在弹窗中选择对账方式。',
      '余额调整',
      {
        inputValue: String(a.current_balance),
        inputPattern: /^-?\d+(\.\d{1,2})?$/,
        inputErrorMessage: '请输入有效金额',
        distinguishCancelAndClose: true,
        confirmButtonText: '记为余额调整',
        cancelButtonText: '记为收支(对账)'
      }
    )
    if (action !== 'confirm') return
    await api.adjustAccount(a.id, Number(value), 'adjust')
    ElMessage.success('已记为余额调整')
    load()
  } catch (e: any) {
    if (e === 'cancel') {
      // 记为收支(对账)
      try {
        const { value } = await ElMessageBox.prompt('请输入该账户的实际余额，差额将记为对账收入/支出', '余额对账', {
          inputPattern: /^-?\d+(\.\d{1,2})?$/,
          inputErrorMessage: '请输入有效金额'
        })
        await api.adjustAccount(a.id, Number(value), 'income_expense')
        ElMessage.success('已记为对账收支')
        load()
      } catch (_) { /* cancelled */ }
    }
  }
}

async function setStatus(a: Account, status: 'active' | 'hidden' | 'closed') {
  const label = status === 'hidden' ? '隐藏' : status === 'closed' ? '注销' : '恢复'
  try {
    if (status !== 'active') {
      await ElMessageBox.confirm(`确定${label}账户「${a.name}」吗？`, '提示', { type: 'warning' })
    }
    await api.setAccountStatus(a.id, status)
    ElMessage.success(`已${label}`)
    load()
  } catch (e) { /* cancelled */ }
}

async function remove(a: Account) {
  try {
    await ElMessageBox.confirm(`确定删除账户「${a.name}」吗？`, '提示', { type: 'warning' })
    await api.deleteAccount(a.id)
    ElMessage.success('已删除')
    load()
  } catch (e) { /* cancelled */ }
}

const isCredit = (t: string) => t === 'credit'
const isCash = (t: string) => t === 'cash'
const isBank = (t: string) => t === 'bank'
const isPrepaid = (t: string) => t === 'prepaid' || t === 'wallet'
const isP2P = (t: string) => t === 'p2p'
const isInsurance = (t: string) => t === 'insurance'

async function moveToGroup(a: Account, groupId: number | null) {
  await api.updateAccount(a.id, { group_id: groupId })
  ElMessage.success('已移动到账户组')
  if (groupId !== null) viewMode.value = 'group'
  load()
}

async function createGroupAndMove(a: Account) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新账户组名称', '新增账户组', {
      inputValidator: (v) => !!v || '请输入名称'
    })
    const g = await api.createAccountGroup(ledgerStore.currentId as number, { name: value })
    await moveToGroup(a, g.id)
  } catch (e) { /* cancelled */ }
}

function onCmd(c: string, a: Account) {
  if (c === 'open') openAccountRecord(a)
  else if (c === 'edit') openEdit(a)
  else if (c === 'adjust') adjust(a)
  else if (c === 'group-none') moveToGroup(a, null)
  else if (c === 'group-new') createGroupAndMove(a)
  else if (c.startsWith('group-')) moveToGroup(a, Number(c.slice(6)))
  else if (c === 'hide') setStatus(a, 'hidden')
  else if (c === 'close') setStatus(a, 'closed')
  else if (c === 'restore') setStatus(a, 'active')
  else if (c === 'delete') remove(a)
}

onMounted(load)
watch(() => ledgerStore.currentId, load)
watch(() => p2pStore.savedAt, load)
watch(() => loanStore.savedAt, load)
watch(() => majorAssetStore.savedAt, load)
</script>

<template>
  <div class="acct-center">
    <div class="ac-header">
      <div class="ac-title">账户中心</div>
      <div class="ac-tools">
        <el-select v-model="filterType" placeholder="所有账户类型" style="width: 140px">
          <el-option label="所有账户类型" value="" />
          <el-option v-for="t in types" :key="t.v" :label="t.t" :value="t.v" />
        </el-select>
        <el-select v-model="viewMode" style="width: 150px">
          <el-option label="按账户类型查看" value="type" />
          <el-option label="按自定义分组查看" value="group" />
        </el-select>
        <el-dropdown trigger="click">
          <el-button>操作 <span style="margin-left:4px">▾</span></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="showHidden = !showHidden">
                <span :class="{ 'grp-checked': showHidden }">{{ showHidden ? '✓ ' : '　' }}显示隐藏账户</span>
              </el-dropdown-item>
              <el-dropdown-item @click="showClosed = !showClosed">
                <span :class="{ 'grp-checked': showClosed }">{{ showClosed ? '✓ ' : '　' }}显示注销账户</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button @click="openGroupDialog">新增账户组</el-button>
        <el-button type="primary" @click="openTypePicker">新增账户</el-button>
      </div>
    </div>

    <div class="ac-body">
      <el-empty v-if="!accounts.length" description="暂无账户，点击右上角新增账户" />
      <div v-for="g in groups" :key="g.name" class="ac-group">
        <div class="ac-group-head">
          <span class="caret" @click="toggleGroup(g.name)">{{ collapsed[g.name] ? '▸' : '▾' }}</span>
          <span class="g-name" @click="toggleGroup(g.name)">{{ g.name }}</span>
          <span class="g-total" :class="{ expense: g.total < 0 }">{{ fmtMoney(g.total) }}</span>
          <span
            v-if="viewMode === 'group' && accountGroups.find((x) => x.name === g.name)"
            class="g-del"
            @click.stop="removeGroup(accountGroups.find((x) => x.name === g.name)!)"
          >✕</span>
        </div>
        <template v-if="!collapsed[g.name]">
          <div v-for="a in g.items" :key="a.id" class="ac-row" :class="{ neg: Number(a.current_balance) < 0 }" @click="openAccountRecord(a)">
            <div class="ac-row-left">
              <div class="ac-name">{{ a.name }}<span v-if="statusText(a)" class="ac-tag">{{ statusText(a) }}</span></div>
              <div class="ac-sub">{{ accountSub(a) }}</div>
            </div>
            <div class="ac-row-right">
              <span class="ac-amount" :class="{ expense: Number(a.current_balance) < 0 }">{{ fmtMoney(a.current_balance) }}</span>
              <el-dropdown trigger="click" @command="(c: string) => onCmd(c, a)">
                <span class="ac-more" @click.stop>⋯</span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="open">查看流水</el-dropdown-item>
                    <el-dropdown-item command="edit">修改账户</el-dropdown-item>
                    <el-dropdown-item command="adjust">余额调整</el-dropdown-item>
                    <el-dropdown-item command="group-none" divided>
                      <span :class="{ 'grp-checked': !a.group_id }">属于账户组：&lt;无账户组&gt;</span>
                    </el-dropdown-item>
                    <el-dropdown-item
                      v-for="grp in accountGroups"
                      :key="grp.id"
                      :command="`group-${grp.id}`"
                    >
                      <span :class="{ 'grp-checked': a.group_id === grp.id }">{{ a.group_id === grp.id ? '✓ ' : '　' }}{{ grp.name }}</span>
                    </el-dropdown-item>
                    <el-dropdown-item command="group-new">＋ 新增账户组…</el-dropdown-item>
                    <el-dropdown-item v-if="a.status === 'hidden' || a.status === 'closed'" command="restore" divided>恢复账户</el-dropdown-item>
                    <el-dropdown-item v-if="a.status !== 'hidden'" command="hide" :divided="a.status !== 'closed'">隐藏账户</el-dropdown-item>
                    <el-dropdown-item v-if="a.status !== 'closed'" command="close">注销账户</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除账户</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </template>
      </div>
    </div>

    <div class="ac-footer">
      <span>资产：<b class="income">{{ fmtMoney(assets) }}</b></span>
      <span>负债：<b class="expense">{{ fmtMoney(Math.abs(liabilities)) }}</b></span>
      <span>净资产：<b :class="netWorth >= 0 ? 'income' : 'expense'">{{ fmtMoney(netWorth) }}</b></span>
    </div>

    <el-dialog
      v-model="dialog"
      :title="isCredit(form.type) ? '信用卡账户' : (isCash(form.type) ? '现金' : (isBank(form.type) ? '活期存款' : (isPrepaid(form.type) ? '第三方储值' : (isP2P(form.type) ? '网贷' : (isInsurance(form.type) ? '保险账户' : (editingId ? '编辑账户' : '新增账户'))))))"
      width="92%"
      :style="{ maxWidth: isCredit(form.type) ? '760px' : ((isCash(form.type) || isBank(form.type) || isPrepaid(form.type) || isP2P(form.type) || isInsurance(form.type)) ? '640px' : '420px') }"
    >
      <!-- 信用卡账户：完整表单（图） -->
      <el-form v-if="isCredit(form.type)" label-width="110px" class="cc-form">
        <div class="cc-grid">
          <el-form-item label="账户名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="币种">
            <el-select v-model="form.currency" style="width:100%">
              <el-option label="人民币 CNY" value="CNY" />
              <el-option label="美元 USD" value="USD" />
              <el-option label="港币 HKD" value="HKD" />
              <el-option label="欧元 EUR" value="EUR" />
            </el-select>
          </el-form-item>
          <el-form-item label="所有者">
            <el-select v-model="form.owner" style="width:100%" filterable allow-create default-first-option placeholder="请选择或输入">
              <el-option v-for="p in owners" :key="p.id" :label="p.name" :value="p.name" />
              <template #footer>
                <el-button link type="primary" @click="openPartyDialog('owner')">[ 新增 ]</el-button>
              </template>
            </el-select>
          </el-form-item>
          <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
          <el-form-item label="卡号"><el-input v-model="form.card_no" /></el-form-item>
          <el-form-item label="开户银行">
            <el-select v-model="form.bank_name" style="width:100%" filterable allow-create default-first-option placeholder="在此处输入文字以进行过滤">
              <el-option v-for="p in banks" :key="p.id" :label="p.name" :value="p.name" />
              <template #footer>
                <el-button link type="primary" @click="openPartyDialog('bank')">[ 新增 ]</el-button>
              </template>
            </el-select>
          </el-form-item>
          <el-form-item label="启用日期">
            <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
          <el-form-item label="到期月年"><el-input v-model="form.expiry" placeholder="如 1512" /></el-form-item>
          <el-form-item label="透支限额"><el-input v-model="form.credit_limit" type="number" /></el-form-item>
          <el-form-item label="预借现金额度"><el-input v-model="form.cash_limit" type="number" /></el-form-item>
          <el-form-item label="最低还款比例(%)"><el-input v-model="form.min_repay_ratio" type="number" /></el-form-item>
          <el-form-item label="年费"><el-input v-model="form.annual_fee" type="number" /></el-form-item>
        </div>

        <el-form-item label="年费减免规则">
          <el-radio-group v-model="form.fee_waiver_type">
            <el-radio value="count">
              刷卡
              <el-input v-model="form.fee_waiver_count" type="number" style="width:80px;margin:0 6px" :disabled="form.fee_waiver_type !== 'count'" />
              次免年费
            </el-radio>
            <el-radio value="amount">
              刷卡金额满
              <el-input v-model="form.fee_waiver_amount" type="number" style="width:110px;margin:0 6px" :disabled="form.fee_waiver_type !== 'amount'" />
              免年费
            </el-radio>
            <el-radio value="none">不免年费</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="账单日"><el-input v-model="form.bill_day" type="number" style="width:120px" /> 日</el-form-item>

        <el-form-item label="还款日">
          <el-radio-group v-model="form.repay_type">
            <el-radio value="fixed">
              固定还款日，每月
              <el-input v-model="form.repay_day" type="number" style="width:80px;margin:0 6px" :disabled="form.repay_type !== 'fixed'" />
              日
            </el-radio>
            <el-radio value="after_bill">
              账单日之后
              <el-input v-model="form.repay_after_days" type="number" style="width:80px;margin:0 6px" :disabled="form.repay_type !== 'after_bill'" />
              天
            </el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="账单日当天交易">
          <el-radio-group v-model="form.bill_day_txn">
            <el-radio value="next">计入下期</el-radio>
            <el-radio value="current">计入本期</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="透支提醒">
          <el-checkbox v-model="form.overdraft_remind" />
        </el-form-item>

        <el-form-item v-if="!editingId" label="初始余额">
          <el-input v-model="form.initial_balance" type="number" />
        </el-form-item>
        <el-form-item label="计入净资产">
          <el-switch v-model="form.include_in_net" />
        </el-form-item>
        <el-form-item label="账户组">
          <el-select v-model="form.group_id" style="width:100%" clearable placeholder="未分组">
            <el-option v-for="g in accountGroups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
      </el-form>

      <!-- 现金账户表单（图） -->
      <el-form v-else-if="isCash(form.type)" label-width="80px" class="cc-form">
        <div class="cc-grid">
          <el-form-item label="账户名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="日期">
            <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
          <el-form-item label="币种">
            <el-select v-model="form.currency" style="width:100%">
              <el-option label="人民币 CNY" value="CNY" />
              <el-option label="美元 USD" value="USD" />
              <el-option label="港币 HKD" value="HKD" />
              <el-option label="欧元 EUR" value="EUR" />
            </el-select>
          </el-form-item>
          <el-form-item label="所有者">
            <el-select v-model="form.owner" style="width:100%" filterable allow-create default-first-option placeholder="请选择或输入">
              <el-option v-for="p in owners" :key="p.id" :label="p.name" :value="p.name" />
              <template #footer>
                <el-button link type="primary" @click="openPartyDialog('owner')">[ 新增 ]</el-button>
              </template>
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
        <el-form-item v-if="!editingId" label="初始余额">
          <el-input v-model="form.initial_balance" type="number" />
        </el-form-item>
        <el-form-item label="账户组">
          <el-select v-model="form.group_id" style="width:100%" clearable placeholder="未分组">
            <el-option v-for="g in accountGroups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
      </el-form>

      <!-- 活期存款 / 储蓄卡表单（图） -->
      <el-form v-else-if="isBank(form.type)" label-width="80px" class="cc-form">
        <div class="cc-grid">
          <el-form-item label="账户名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="币种">
            <el-select v-model="form.currency" style="width:100%">
              <el-option label="人民币 CNY" value="CNY" />
              <el-option label="美元 USD" value="USD" />
              <el-option label="港币 HKD" value="HKD" />
              <el-option label="欧元 EUR" value="EUR" />
            </el-select>
          </el-form-item>
          <el-form-item label="所有者">
            <el-select v-model="form.owner" style="width:100%" filterable allow-create default-first-option placeholder="请选择或输入">
              <el-option v-for="p in owners" :key="p.id" :label="p.name" :value="p.name" />
              <template #footer>
                <el-button link type="primary" @click="openPartyDialog('owner')">[ 新增 ]</el-button>
              </template>
            </el-select>
          </el-form-item>
          <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
          <el-form-item label="卡号"><el-input v-model="form.card_no" /></el-form-item>
          <el-form-item label="开户日期">
            <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
          <el-form-item label="开户银行">
            <el-select v-model="form.bank_name" style="width:100%" filterable allow-create default-first-option placeholder="<无>">
              <el-option v-for="p in banks" :key="p.id" :label="p.name" :value="p.name" />
              <template #footer>
                <el-button link type="primary" @click="openPartyDialog('bank')">[ 新增 ]</el-button>
              </template>
            </el-select>
          </el-form-item>
          <el-form-item label="账户组">
            <el-select v-model="form.group_id" style="width:100%" clearable placeholder="未分组">
              <el-option v-for="g in accountGroups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item v-if="!editingId" label="初始余额">
          <el-input v-model="form.initial_balance" type="number" />
        </el-form-item>
      </el-form>

      <!-- 第三方储值表单（图） -->
      <el-form v-else-if="isPrepaid(form.type)" label-width="80px" class="cc-form">
        <div class="cc-grid">
          <el-form-item label="账户别名"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="币种">
            <el-select v-model="form.currency" style="width:100%">
              <el-option label="人民币 CNY" value="CNY" />
              <el-option label="美元 USD" value="USD" />
              <el-option label="港币 HKD" value="HKD" />
              <el-option label="欧元 EUR" value="EUR" />
            </el-select>
          </el-form-item>
          <el-form-item label="所有者">
            <el-select v-model="form.owner" style="width:100%" filterable allow-create default-first-option placeholder="请选择或输入">
              <el-option v-for="p in owners" :key="p.id" :label="p.name" :value="p.name" />
              <template #footer>
                <el-button link type="primary" @click="openPartyDialog('owner')">[ 新增 ]</el-button>
              </template>
            </el-select>
          </el-form-item>
          <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
          <el-form-item label="创建日期">
            <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </div>
        <el-form-item v-if="!editingId" label="初始余额">
          <el-input v-model="form.initial_balance" type="number" />
        </el-form-item>
        <el-form-item label="账户组">
          <el-select v-model="form.group_id" style="width:100%" clearable placeholder="未分组">
            <el-option v-for="g in accountGroups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
      </el-form>

      <!-- 网贷表单（图） -->
      <el-form v-else-if="isP2P(form.type)" label-width="80px" class="cc-form">
        <div class="cc-grid">
          <el-form-item label="账户名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="日期">
            <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
          <el-form-item label="币种">
            <el-select v-model="form.currency" style="width:100%">
              <el-option label="人民币 CNY" value="CNY" />
              <el-option label="美元 USD" value="USD" />
              <el-option label="港币 HKD" value="HKD" />
              <el-option label="欧元 EUR" value="EUR" />
            </el-select>
          </el-form-item>
          <el-form-item label="所有者">
            <el-select v-model="form.owner" style="width:100%" filterable allow-create default-first-option placeholder="请选择或输入">
              <el-option v-for="p in owners" :key="p.id" :label="p.name" :value="p.name" />
              <template #footer>
                <el-button link type="primary" @click="openPartyDialog('owner')">[ 新增 ]</el-button>
              </template>
            </el-select>
          </el-form-item>
          <el-form-item label="平台名称"><el-input v-model="form.platform_name" /></el-form-item>
          <el-form-item label="平台网址"><el-input v-model="form.platform_url" placeholder="http://" /></el-form-item>
        </div>
        <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
        <el-form-item v-if="!editingId" label="初始余额">
          <el-input v-model="form.initial_balance" type="number" />
        </el-form-item>
        <el-form-item label="账户组">
          <el-select v-model="form.group_id" style="width:100%" clearable placeholder="未分组">
            <el-option v-for="g in accountGroups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
      </el-form>

      <!-- 保险账户表单（图） -->
      <el-form v-else-if="isInsurance(form.type)" label-width="92px" class="cc-form">
        <div class="cc-grid">
          <el-form-item label="账户名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
          <el-form-item label="所有者">
            <el-select v-model="form.owner" style="width:100%" filterable allow-create default-first-option placeholder="请选择或输入">
              <el-option v-for="p in owners" :key="p.id" :label="p.name" :value="p.name" />
              <template #footer>
                <el-button link type="primary" @click="openPartyDialog('owner')">[ 新增 ]</el-button>
              </template>
            </el-select>
          </el-form-item>
          <el-form-item label="社保编码"><el-input v-model="form.social_code" /></el-form-item>
          <el-form-item label="日期">
            <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
          <el-form-item label="参保人">
            <el-select v-model="form.insured_person" style="width:100%" filterable allow-create default-first-option placeholder="请选择或输入">
              <el-option v-for="p in owners" :key="p.id" :label="p.name" :value="p.name" />
              <template #footer>
                <el-button link type="primary" @click="openPartyDialog('owner')">[ 新增 ]</el-button>
              </template>
            </el-select>
          </el-form-item>
          <el-form-item label="城市"><el-input v-model="form.city" /></el-form-item>
        </div>
        <el-form-item label="将保费做为收支统计">
          <el-checkbox v-model="form.premium_as_stat" />
        </el-form-item>
        <el-form-item v-if="!editingId" label="初始余额">
          <el-input v-model="form.initial_balance" type="number" />
        </el-form-item>
        <el-form-item label="账户组">
          <el-select v-model="form.group_id" style="width:100%" clearable placeholder="未分组">
            <el-option v-for="g in accountGroups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
      </el-form>

      <!-- 普通账户表单 -->
      <el-form v-else label-width="80px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.type" style="width:100%" filterable>
            <el-option v-for="t in types" :key="t.v" :label="t.t" :value="t.v" />
          </el-select>
        </el-form-item>
        <el-form-item label="账户组">
          <el-select v-model="form.group_id" style="width:100%" clearable placeholder="未分组">
            <el-option v-for="g in accountGroups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="图标"><el-input v-model="form.icon" /></el-form-item>
        <el-form-item v-if="!editingId" label="初始余额">
          <el-input v-model="form.initial_balance" type="number" />
        </el-form-item>
        <el-form-item label="计入净资产">
          <el-switch v-model="form.include_in_net" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新增账户：类型选择器（图3） -->
    <el-dialog v-model="typePicker" title="新增资产账户" width="92%" style="max-width:680px">
      <div class="tp-intro">账户作为财务管理的基础单元，支持多账户分类管理体系。您可根据资金用途、账户类型等维度创建账户，构建清晰的账户架构。</div>
      <div v-for="sec in typePicker_sections" :key="sec.label" class="tp-section">
        <div class="tp-label">{{ sec.label }}</div>
        <div class="tp-items">
          <button
            v-for="(it, i) in sec.items"
            :key="sec.label + i"
            class="tp-item"
            @click="pickType(it.v, it.t)"
          >{{ it.t }}</button>
        </div>
      </div>
    </el-dialog>

    <!-- 双币信用卡向导 -->
    <el-dialog
      v-model="cwVisible"
      title="双币信用卡账户"
      width="92%"
      style="max-width:560px"
      :close-on-click-modal="false"
    >
      <div class="tp-intro">您可为每位家庭成员分别创建独立的双币种信用卡账户，精准记录人民币和外币的消费明细、汇率转换、还款周期及信用额度使用情况，实现家庭跨境消费的全面管理和汇率风险控制。</div>

      <!-- 第一步 -->
      <el-form v-if="cwStep === 1" label-width="90px" class="cw-form">
        <el-form-item label="账户名称" required>
          <el-input v-model="cwForm.name" />
        </el-form-item>
        <el-form-item label="所有者">
          <el-select v-model="cwForm.owner" placeholder="<无>" clearable style="width:100%">
            <el-option v-for="o in owners" :key="o.id" :label="o.name" :value="o.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="cwForm.remark" />
        </el-form-item>
      </el-form>

      <!-- 第二步 -->
      <el-form v-else-if="cwStep === 2" label-width="90px" class="cw-form">
        <el-form-item label="启用日期">
          <el-date-picker v-model="cwForm.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="账单日">
          <el-radio-group v-model="cwForm.bill_day_last" class="cw-radio-col">
            <el-radio :value="false">
              固定账单日 每月
              <el-input v-model="cwForm.bill_day" type="number" style="width:80px;margin:0 6px" :disabled="cwForm.bill_day_last" /> 日
            </el-radio>
            <el-radio :value="true">每月最后一天是账单日</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="还款日">
          <el-radio-group v-model="cwForm.repay_type" class="cw-radio-col">
            <el-radio value="after_bill">
              账单日之后
              <el-input v-model="cwForm.repay_after_days" type="number" style="width:80px;margin:0 6px" :disabled="cwForm.repay_type !== 'after_bill'" /> 天
            </el-radio>
            <el-radio value="fixed">
              固定还款日
              <el-input v-model="cwForm.repay_day" type="number" style="width:80px;margin:0 6px" :disabled="cwForm.repay_type !== 'fixed'" /> 日
            </el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <!-- 第三步 -->
      <el-form v-else label-width="90px" class="cw-form">
        <el-form-item label="币种1" required>
          <el-select v-model="cwForm.currency" style="width:100%">
            <el-option v-for="c in currencies" :key="c.id" :label="`${c.name} ${c.code}`" :value="c.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="已透支金额">
          <el-input v-model="cwForm.overdraft1" type="number" placeholder="0.00" />
        </el-form-item>
        <el-form-item label="透支提醒">
          <el-checkbox v-model="cwForm.overdraft_remind" />
        </el-form-item>
        <el-divider />
        <el-form-item label="币种2" required>
          <el-select v-model="cwForm.currency2" style="width:100%">
            <el-option v-for="c in currencies" :key="c.id" :label="`${c.name} ${c.code}`" :value="c.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="已透支金额">
          <el-input v-model="cwForm.overdraft2" type="number" placeholder="0.00" />
        </el-form-item>
        <el-form-item label="透支提醒">
          <el-checkbox v-model="cwForm.overdraft_remind2" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button :disabled="cwStep === 1" @click="cwPrev">&lt; 上一步</el-button>
        <el-button v-if="cwStep < 3" type="primary" @click="cwNext">下一步 &gt;</el-button>
        <el-button v-else type="primary" @click="cwFinish">完成</el-button>
      </template>
    </el-dialog>

    <!-- 上市证券 / 银行理财等投资账户向导 -->
    <el-dialog
      v-model="swVisible"
      :title="swMeta.title"
      width="92%"
      style="max-width:560px"
      :close-on-click-modal="false"
    >
      <div class="tp-intro">{{ swMeta.intro }}</div>

      <!-- 第一步：账户资料 -->
      <el-form v-if="swStep === 1" label-width="90px" class="cw-form">
        <el-form-item label="账户名称" required>
          <el-input v-model="swForm.name" />
        </el-form-item>
        <el-form-item v-if="swMeta.market" label="类型" required>
          <div style="display:flex;gap:8px;width:100%">
            <el-select v-model="swForm.market" style="flex:1" @change="onStockMarketChange">
              <el-option v-for="m in STOCK_MARKETS" :key="m.v" :label="m.t" :value="m.v" />
            </el-select>
            <el-select v-model="swForm.currency" style="width:140px" :disabled="swForm.market !== 'OTHER'">
              <el-option label="人民币 CNY" value="CNY" />
              <el-option label="美元 USD" value="USD" />
              <el-option label="港币 HKD" value="HKD" />
              <el-option label="欧元 EUR" value="EUR" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item v-else label="币种" required>
          <el-select v-model="swForm.currency" style="width:100%">
            <el-option label="人民币 CNY" value="CNY" />
            <el-option label="美元 USD" value="USD" />
            <el-option label="港币 HKD" value="HKD" />
            <el-option label="欧元 EUR" value="EUR" />
          </el-select>
        </el-form-item>
        <el-form-item label="所有者">
          <el-select v-model="swForm.owner" placeholder="<无>" clearable filterable allow-create default-first-option style="width:100%">
            <el-option v-for="o in owners" :key="o.id" :label="o.name" :value="o.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="swForm.remark" />
        </el-form-item>
        <el-form-item label="属于账户组">
          <el-select v-model="swForm.group_id" placeholder="<无>" clearable style="width:100%">
            <el-option v-for="g in accountGroups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
      </el-form>

      <!-- 第二步：资金来源 -->
      <el-form v-else-if="swStep === 2" label-width="90px" class="cw-form">
        <el-form-item label="日期">
          <el-date-picker v-model="swForm.date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item v-if="isForexWizard" label="账户余额">
          <el-input v-model="swForm.amount" type="number" placeholder="0.00" />
          <span class="fx-cur-tip">{{ swForm.currency }}</span>
        </el-form-item>
        <el-form-item v-else label="资金来源">
          <el-radio-group v-model="swForm.fund_source" class="cw-radio-col">
            <el-radio value="self">
              账户自身余额
              <el-input
                v-model="swForm.amount"
                type="number"
                style="width:140px;margin-left:6px"
                placeholder="0.00"
                :disabled="swForm.fund_source !== 'self'"
              />
            </el-radio>
            <el-radio value="other">其它账户</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="!isForexWizard && swForm.fund_source === 'other'">
          <el-form-item label="来源账户">
            <el-select v-model="swForm.from_account_id" placeholder="选择转出账户" style="width:100%">
              <el-option v-for="a in fundSourceAccounts" :key="a.id" :label="`${a.name}（${fmtMoney(a.current_balance)}）`" :value="a.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="转入金额">
            <el-input v-model="swForm.amount" type="number" placeholder="0.00" />
          </el-form-item>
        </template>
        <el-form-item v-if="swType === 'money_fund'" label="资产性质">
          <el-radio-group v-model="swForm.asset_nature">
            <el-radio value="invest">投资</el-radio>
            <el-radio value="save">储蓄</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <!-- 第三步（外汇）：增加其它币种 -->
      <el-form v-else label-width="90px" class="cw-form">
        <div class="fx-extra-head">
          <span>增加其它币种</span>
          <el-button size="small" type="primary" plain @click="addExtraCurrency">+ 增加</el-button>
        </div>
        <el-table :data="swForm.extra_currencies" size="small" border empty-text="可选：增加该账户持有的其它币种">
          <el-table-column label="币种" min-width="150">
            <template #default="{ row }">
              <el-select v-model="row.code" size="small" style="width:100%">
                <el-option v-for="c in currencies" :key="c.code" :label="`${c.name} ${c.code}`" :value="c.code" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="金额" min-width="130">
            <template #default="{ row }">
              <el-input v-model="row.amount" size="small" type="number" placeholder="0.00" />
            </template>
          </el-table-column>
          <el-table-column label="资金来源" min-width="140">
            <template #default>&lt;不考虑资金来源&gt;</template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center">
            <template #default="{ $index }">
              <el-button size="small" link type="danger" @click="removeExtraCurrency($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-form>

      <template #footer>
        <el-button :disabled="swStep === 1" @click="swPrev">&lt; 上一步</el-button>
        <el-button v-if="swStep < swMaxStep" type="primary" @click="swNext">下一步 &gt;</el-button>
        <el-button v-else type="primary" @click="swFinish">完成</el-button>
      </template>
    </el-dialog>

    <!-- 账户组（图1） -->
    <el-dialog v-model="groupDialog" title="账户组" width="90%" style="max-width:480px">
      <el-form label-width="80px">
        <el-form-item label="账户组名"><el-input v-model="groupForm.name" /></el-form-item>
        <el-form-item label="详细资料"><el-input v-model="groupForm.remark" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <div class="tp-intro">账户组功能可帮助您管理具有相似属性或用途的账户集合。例如，您可以将银行定期一本通下的多个存单整合为一个账户组进行统一管理；也可按家庭成员、资金用途等维度分组管理，让财务管理更加清晰有序。</div>
      <template #footer>
        <el-button @click="groupDialog = false">取消</el-button>
        <el-button type="primary" @click="saveGroup">确定</el-button>
      </template>
    </el-dialog>

    <!-- 人员与机构（图2/图3） -->
    <el-dialog v-model="partyDialog" title="人员与机构" width="90%" style="max-width:480px">
      <el-form label-width="80px">
        <el-form-item label="名称"><el-input v-model="partyForm.name" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="partyForm.type" style="width:100%">
            <el-option v-for="t in partyTypes" :key="t.v" :label="t.t" :value="t.v" />
          </el-select>
        </el-form-item>
        <el-form-item label="联系方式"><el-input v-model="partyForm.contact" /></el-form-item>
        <el-form-item label="地址"><el-input v-model="partyForm.address" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="partyDialog = false">取消</el-button>
        <el-button type="primary" @click="saveParty">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.acct-center {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 52px);
  background: #f3f6f9;
}

.ac-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 12px 16px;
  border-bottom: 1px solid #d3dde6;
  background: #fff;
}

.ac-title {
  font-size: 18px;
  font-weight: 700;
  color: #44525f;
}

.ac-tools {
  display: flex;
  gap: 8px;
}

.ac-body {
  flex: 1;
  padding: 8px 16px;
  overflow-y: auto;
}

.ac-group {
  margin-bottom: 10px;
  background: #fff;
  border: 1px solid #e2e9ef;
}

.ac-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #eef2f6;
  cursor: pointer;
  color: #4a5a6a;
  font-weight: 700;
  border-bottom: 1px solid #e2e9ef;
}

.ac-group-head .caret {
  width: 12px;
  font-size: 12px;
}

.ac-group-head .g-name {
  flex: 1;
}

.ac-group-head .g-total {
  font-size: 16px;
  color: #3f79a8;
}

.ac-group-head .caret,
.ac-group-head .g-name {
  cursor: pointer;
}

.ac-group-head .g-del {
  cursor: pointer;
  color: #b9c4cf;
  font-size: 13px;
  margin-left: 10px;
}

.ac-group-head .g-del:hover {
  color: #de6d6d;
}

/* 类型选择器（图3） */
.tp-intro {
  background: #f3f6f9;
  border: 1px solid #e2e9ef;
  color: #8593a1;
  font-size: 12px;
  line-height: 1.7;
  padding: 10px 12px;
  margin-bottom: 14px;
}

.cw-radio-col {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}
.cw-radio-col .el-radio {
  height: auto;
}

.fx-extra-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #3c4b59;
}
.fx-cur-tip {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}

.tp-section {
  display: flex;
  gap: 14px;
  padding: 10px 0;
  border-bottom: 1px solid #f0f3f6;
}

.tp-label {
  width: 72px;
  flex: none;
  color: #56677a;
  font-weight: 700;
  padding-top: 4px;
}

.tp-items {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 22px;
}

.tp-item {
  border: 0;
  background: transparent;
  color: #3f79a8;
  cursor: pointer;
  font-size: 14px;
  padding: 4px 2px;
}

.tp-item:hover {
  text-decoration: underline;
}

.grp-checked {
  color: #3f79a8;
  font-weight: 700;
}

/* 信用卡表单两列布局 */
.cc-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 18px;
}

.cc-form :deep(.el-radio) {
  margin-right: 18px;
  height: auto;
}

@media (max-width: 640px) {
  .cc-grid {
    grid-template-columns: 1fr;
  }
}

.ac-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px 12px 22px;
  border-bottom: 1px solid #f1f4f7;
  border-left: 3px solid #5cb85c;
  margin: 6px 10px;
  cursor: pointer;
}

.ac-row.neg {
  border-left-color: #de6d6d;
}

.ac-row:hover {
  background: #f5f8fb;
}

.ac-name {
  font-size: 15px;
  color: #3c4b59;
  font-weight: 600;
}

.ac-tag {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  font-size: 11px;
  font-weight: 400;
  line-height: 16px;
  color: #909399;
  background: #f0f2f5;
  border-radius: 3px;
  vertical-align: middle;
}

.ac-sub {
  font-size: 12px;
  color: #93a1af;
  margin-top: 2px;
}

.ac-row-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ac-amount {
  font-size: 18px;
  color: #2e9c4f;
}

.expense {
  color: #de6d6d !important;
}

.income {
  color: #2e9c4f;
}

.ac-more {
  cursor: pointer;
  color: #9aa7b3;
  font-size: 18px;
  padding: 0 4px;
}

.ac-footer {
  display: flex;
  gap: 24px;
  padding: 10px 16px;
  border-top: 1px solid #d3dde6;
  background: #edf2f7;
  color: #54657a;
}

@media (max-width: 768px) {
  .ac-footer {
    gap: 12px;
    flex-wrap: wrap;
  }
}
</style>
