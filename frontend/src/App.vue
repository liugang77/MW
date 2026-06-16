<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useLedgerStore } from './stores/ledger'
import { useRecordStore } from './stores/record'
import { useTradeStore } from './stores/trade'
import { useP2pStore } from './stores/p2p'
import { useFundStore } from './stores/fund'
import { usePlanStore } from './stores/plan'
import { useLoanStore } from './stores/loan'
import { useForexStore } from './stores/forex'
import { useMajorAssetStore } from './stores/majorAsset'
import { useSalaryStore } from './stores/salary'
import { useIpoStore } from './stores/ipo'
import { useVoucherStore } from './stores/voucher'
import { api } from './api'
import { isLoading } from './api/loading'
import type { Account, Holding } from './types'
import { fmtMoney } from './utils/format'
import NewTransaction from './views/NewTransaction.vue'
import StockTrade from './views/StockTrade.vue'
import P2PLend from './views/P2PLend.vue'
import P2PCollect from './views/P2PCollect.vue'
import FundBuy from './views/FundBuy.vue'
import PlansDialog from './views/PlansDialog.vue'
import LoanDialog from './views/LoanDialog.vue'
import MajorAssetBuyDialog from './views/MajorAssetBuyDialog.vue'
import ForexTrade from './views/ForexTrade.vue'
import SalaryDialog from './views/SalaryDialog.vue'
import IpoConfirm from './views/IpoConfirm.vue'
const ledgerStore = useLedgerStore()
const recordStore = useRecordStore()
const tradeStore = useTradeStore()
const p2pStore = useP2pStore()
const fundStore = useFundStore()
const planStore = usePlanStore()
const loanStore = useLoanStore()
const forexStore = useForexStore()
const majorAssetStore = useMajorAssetStore()
const salaryStore = useSalaryStore()
const ipoStore = useIpoStore()
const voucherStore = useVoucherStore()
const route = useRoute()
const router = useRouter()
const isMobileTab = computed(() => ['/', '/transactions', '/accounts', '/statistics'].includes(route.path))

const accounts = ref<Account[]>([])
const holdings = ref<Holding[]>([])
const collapsed = ref<Record<string, boolean>>({})
const brandPopover = ref<{ hide: () => void } | null>(null)

// 投资类账户：价值 = 可用现金余额 + 持仓市值（含外汇折算人民币）
const INVEST_VALUE_TYPES = ['stock', 'fund', 'open_fund', 'money_fund', 'bond', 'reverse_repo', 'wealth', 'metal', 'metal_td', 'forex', 'futures', 'margin']
const holdingMarketByAccount = computed(() => {
  const m = new Map<number, number>()
  for (const h of holdings.value) {
    if (h.account_id == null) continue
    m.set(h.account_id, (m.get(h.account_id) || 0) + Number(h.market_value || 0))
  }
  return m
})
function accountValue(a: { id: number; type: string; current_balance: number | string }): number {
  const bal = Number(a.current_balance || 0)
  if (INVEST_VALUE_TYPES.includes(a.type)) {
    return bal + (holdingMarketByAccount.value.get(a.id) || 0)
  }
  return bal
}

// 侧栏账户条目：普通账户或合并后的「网贷」入口
interface SidebarItem {
  id: number
  name: string
  type: string
  current_balance: number | string
  isP2pGroup?: boolean
  insurancePerson?: string
}

interface SidebarGroup {
  name: string
  items: SidebarItem[]
  total: number
  flat?: boolean
  to?: string
}

// 顶部模块切换：财务数据 / 财务报表 / 财务分析
interface NavItem { label: string; to: string }
interface NavModule { key: string; name: string; items: NavItem[] }
const modules: NavModule[] = [
  {
    key: 'data',
    name: '财务数据',
    items: [
      { label: '概况', to: '/' },
      { label: '财务记录', to: '/transactions' },
      { label: '投资一览', to: '/investments' },
      { label: '标签', to: '/categories' },
      { label: '账户中心', to: '/accounts' }
    ]
  },
  {
    key: 'report',
    name: '财务报表',
    items: [
      { label: '日常收支表', to: '/report/income-expense' },
      { label: '日常收支明细表', to: '/report/income-expense-detail' },
      { label: '账户日常收支', to: '/report/account-ie' },
      { label: '标签日常收支表', to: '/report/tag-ie' },
      { label: '两段时间收支对比表', to: '/report/compare' },
      { label: '收支统计表', to: '/report/stat' },
      { label: '收支走势图', to: '/report/trend' },
      { label: '月平均收支', to: '/report/monthly-avg' },
      { label: '现金流表', to: '/report/cashflow' },
      { label: '投资收益一览表', to: '/report/investment-income' }
    ]
  },
  {
    key: 'analysis',
    name: '财务分析',
    items: [
      { label: '财务预算', to: '/analysis/budget' },
      { label: '财务诊断', to: '/analysis/diagnosis' },
      { label: '财务规划', to: '/analysis/plan' },
      { label: '财务目标', to: '/analysis/goal' }
    ]
  }
]

function moduleOfPath(path: string): NavModule {
  if (path.startsWith('/report/')) return modules[1]
  if (path.startsWith('/analysis/') || path === '/budgets') return modules[2]
  return modules[0]
}

const activeModuleKey = ref(moduleOfPath(route.path).key)
const activeModule = computed(() => modules.find((m) => m.key === activeModuleKey.value) || modules[0])

function switchModule(key: string) {
  const mod = modules.find((m) => m.key === key)
  if (!mod) return
  activeModuleKey.value = key
  router.push(mod.items[0].to)
}

watch(() => route.path, (p) => {
  activeModuleKey.value = moduleOfPath(p).key
})

const accountTypeLabel: Record<string, string> = {
  cash: '现金', bank: '银行存款', wallet: '第三方储值', prepaid: '第三方储值',
  credit: '信用卡', stock: '金融投资', fund: '金融投资', open_fund: '金融投资', money_fund: '金融投资',
  bond: '金融投资', reverse_repo: '金融投资', wealth: '金融投资', metal: '金融投资',
  metal_td: '金融投资', forex: '金融投资', futures: '金融投资', margin: '金融投资',
  p2p: '金融投资', goods: '重大资产', major_asset: '重大资产', insurance: '保险', loan: '债权债务',
  voucher: '团购券'
}

const accountGroups = computed(() => {
  const g = new Map<string, Account[]>()
  for (const a of accounts.value) {
    const group = accountTypeLabel[a.type] || '其他账户'
    if (!g.has(group)) g.set(group, [])
    g.get(group)!.push(a)
  }
  // 侧栏分组固定显示顺序：现金、银行存款、第三方储值、信用卡、金融投资，其余在后
  const GROUP_ORDER = ['现金', '银行存款', '第三方储值', '团购券', '信用卡', '金融投资', '保险', '债权债务', '重大资产']
  const orderIndex = (name: string) => {
    const i = GROUP_ORDER.indexOf(name)
    return i === -1 ? GROUP_ORDER.length : i
  }
  const entries = Array.from(g.entries()).sort((a, b) => orderIndex(a[0]) - orderIndex(b[0]))
  return entries.map(([name, items]): SidebarGroup => {
    const total = items.reduce((s, a) => s + accountValue(a), 0)
    // 债权债务、重大资产在侧栏作为单条汇总入口，不展开明细
    if (name === '债权债务') {
      return { name, items: [] as SidebarItem[], total, flat: true, to: '/loans' }
    }
    if (name === '重大资产') {
      return { name, items: [] as SidebarItem[], total, flat: true, to: '/major-assets' }
    }
    // 保险账户在侧栏按所有人合并为每人一个入口
    if (name === '保险') {
      const byPerson = new Map<string, Account[]>()
      for (const a of items) {
        const p = a.insured_person || '未指定'
        if (!byPerson.has(p)) byPerson.set(p, [])
        byPerson.get(p)!.push(a)
      }
      const personItems: SidebarItem[] = Array.from(byPerson.entries()).map(([person, accs], idx) => ({
        id: -100 - idx,
        name: person,
        type: 'insurance',
        current_balance: accs.reduce((s, a) => s + accountValue(a), 0),
        insurancePerson: person,
      }))
      return {
        name,
        items: personItems,
        total: items.reduce((s, a) => s + accountValue(a), 0),
      }
    }
    // 网贷（P2P）账户在侧栏合并为一个「网贷」入口
    const p2pItems = items.filter((a) => a.type === 'p2p')
    let displayItems: SidebarItem[] = items.filter((a) => a.type !== 'p2p')
    if (p2pItems.length) {
      displayItems = [
        ...displayItems,
        {
          id: -1,
          name: '网贷',
          type: 'p2p',
          current_balance: p2pItems.reduce((s, a) => s + accountValue(a), 0),
          isP2pGroup: true,
        },
      ]
    }
    return {
      name,
      items: displayItems,
      total: items.reduce((s, a) => s + accountValue(a), 0),
    }
  })
})

async function loadAccounts() {
  const lid = ledgerStore.currentId
  if (!lid) return
  const [accs, hs] = await Promise.all([api.listAccounts(lid), api.listHoldings(lid)])
  accounts.value = accs
  holdings.value = hs
}

function toggleGroup(name: string) {
  collapsed.value[name] = !collapsed.value[name]
}

function openAccount(id: number) {
  const acc = accounts.value.find((a) => a.id === id)
  // 网贷账户有自己的记账模式：展示该账户已有的网贷项目，点「记账」再弹窗
  if (acc && acc.type === 'p2p') {
    return router.push({ path: '/p2p', query: { account_id: String(id) } })
  }
  // 借入/借出账户进入债权债务页面
  if (acc && acc.type === 'loan') {
    return router.push({ path: '/loans', query: { account_id: String(id) } })
  }
  // 保险账户进入保险页面
  if (acc && acc.type === 'insurance') {
    return router.push({ path: '/insurance', query: { account_id: String(id) } })
  }
  // 重大资产账户进入重大资产页面
  if (acc && acc.type === 'major_asset') {
    return router.push({ path: '/major-assets', query: { account_id: String(id) } })
  }
  // 信用卡进入独立的信用卡页面
  if (acc && acc.type === 'credit') {
    return router.push({ path: '/credit', query: { account_id: String(id) } })
  }
  // 外汇交易账户进入独立的外汇账户页面
  if (acc && acc.type === 'forex') {
    return router.push({ path: '/forex', query: { account_id: String(id) } })
  }
  // 贵金属账户进入独立的贵金属账户页面
  if (acc && (acc.type === 'metal' || acc.type === 'metal_td')) {
    return router.push({ path: '/metal', query: { account_id: String(id) } })
  }
  // 团购券账户进入独立的团购券账户页面
  if (acc && acc.type === 'voucher') {
    return router.push({ path: '/voucher', query: { account_id: String(id) } })
  }
  // 基金账户进入独立的基金账户页面
  if (acc && ['fund', 'open_fund', 'money_fund'].includes(acc.type)) {
    return router.push({ path: '/funds', query: { account_id: String(id) } })
  }
  // 银行理财账户进入独立的理财账户页面
  if (acc && acc.type === 'wealth') {
    return router.push({ path: '/wealth', query: { account_id: String(id) } })
  }
  // 证券类投资账户进入独立的证券账户页面
  const INVEST_TYPES = ['stock', 'bond', 'reverse_repo', 'futures', 'margin']
  if (acc && INVEST_TYPES.includes(acc.type)) {
    return router.push({ path: '/securities', query: { account_id: String(id) } })
  }
  router.push({ path: '/transactions', query: { account_id: String(id) } })
}

function openSidebarItem(item: SidebarItem) {
  // 合并的「网贷」入口：进入网贷页面（展示全部网贷账户）
  if (item.isP2pGroup) {
    return router.push({ path: '/p2p' })
  }
  // 按所有人合并的「保险」入口：进入保险页面并定位该所有人
  if (item.insurancePerson) {
    return router.push({ path: '/insurance', query: { person: item.insurancePerson } })
  }
  openAccount(item.id)
}

function goNewAccount() {
  router.push('/accounts')
}

// 记账下拉菜单（含证券相关）
function onRecordCommand(cmd: string) {
  // 常用记账
  if (cmd === 'record') return recordStore.open()
  if (cmd === 'batch-record' || cmd === 'batch-transfer') return recordStore.open()
  if (cmd === 'salary') return salaryStore.open()
  if (cmd === 'deposit') return recordStore.open({ template: 'bank-deposit' })
  if (cmd === 'withdraw') return recordStore.open({ template: 'bank-withdraw' })
  if (cmd === 'transfer') return recordStore.open({ template: 'normal-transfer' })
  // 债权债务
  if (cmd === 'loan-borrow') return loanStore.open('payable')
  if (cmd === 'loan-lend') return loanStore.open('receivable')
  // 物品买入（重大资产）
  if (cmd === 'major-buy') return majorAssetStore.open('own')
  // 团购券购买
  if (cmd === 'voucher-buy') return voucherStore.open()
  // 更多交易活动
  if (cmd === 'buy') return tradeStore.open('buy')
  if (cmd === 'sell') return tradeStore.open('sell')
  if (cmd === 'fund-buy') return fundStore.open('buy')
  if (cmd === 'forex-trade') return forexStore.open()
  if (cmd === 'currency-exchange') return recordStore.open({ template: 'normal-transfer' })
  if (cmd === 'p2p-lend') return p2pStore.open('lend')
  if (cmd === 'p2p-collect') return p2pStore.open('collect')
  ElMessage.info('该功能开发中')
}

// 品牌（财智8）主菜单
const dataRouteMap: Record<string, string> = {
  'data-categories': '/data/categories',
  'data-parties': '/data/parties',
  'data-finance': '/data/securities',
  'data-currency-rate': '/data/currency-rate',
  'data-deposit-rate': '/data/deposit-rate',
  'data-remarks': '/data/remarks'
}
function onBrandCommand(cmd: string) {
  brandPopover.value?.hide()
  if (dataRouteMap[cmd]) return router.push(dataRouteMap[cmd])
  if (cmd === 'ledger-new') return openNewLedger()
  if (cmd === 'ledger-open') return openLedgerPicker()
  if (cmd === 'ledger-delete') return deleteCurrentLedger()
  if (cmd === 'plan-remind') return planStore.open()
  ElMessage.info('该功能开发中')
}

// 新建账簿
const newLedgerVisible = ref(false)
const newLedgerName = ref('')
function openNewLedger() {
  newLedgerName.value = ''
  newLedgerVisible.value = true
}
async function confirmNewLedger() {
  const name = newLedgerName.value.trim()
  if (!name) return ElMessage.warning('请输入账簿名称')
  const ledger = await api.createLedger({ name })
  await ledgerStore.load()
  ledgerStore.setCurrent(ledger.id)
  newLedgerVisible.value = false
  ElMessage.success('账簿已创建')
}

// 打开账簿
const openLedgerVisible = ref(false)
const pickLedgerId = ref<number | null>(null)
function openLedgerPicker() {
  pickLedgerId.value = ledgerStore.currentId
  openLedgerVisible.value = true
}
function confirmOpenLedger() {
  if (pickLedgerId.value == null) return ElMessage.warning('请选择账簿')
  ledgerStore.setCurrent(pickLedgerId.value)
  openLedgerVisible.value = false
}

// 删除账簿：删除当前账簿并切换到其他账簿；若为最后一个则自动新建空账簿
async function deleteCurrentLedger() {
  const cur = ledgerStore.current
  if (!cur) return ElMessage.warning('没有可删除的账簿')
  try {
    await ElMessageBox.confirm(
      `确定要删除账簿「${cur.name}」吗？该账簿的全部数据将被永久删除，且不可恢复。`,
      '删除账簿',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
    )
  } catch {
    return
  }
  const res = await api.deleteLedger(cur.id)
  await ledgerStore.load()
  ledgerStore.setCurrent(res.next_ledger_id)
  ElMessage.success('账簿已删除')
}

onMounted(async () => {
  await ledgerStore.load()
  await loadAccounts()
})
watch(() => ledgerStore.currentId, loadAccounts)
// 路由切换回来时刷新账户余额，保持左下常驻列表最新
watch(() => route.fullPath, loadAccounts)
// 各类记账/交易保存后刷新账户与持仓，使侧栏价值实时正确
watch(() => loanStore.savedAt, loadAccounts)
watch(() => tradeStore.savedAt, loadAccounts)
watch(() => forexStore.savedAt, loadAccounts)
watch(() => fundStore.savedAt, loadAccounts)
watch(() => recordStore.savedAt, loadAccounts)
watch(() => p2pStore.savedAt, loadAccounts)
watch(() => salaryStore.savedAt, loadAccounts)
watch(() => ipoStore.savedAt, loadAccounts)
watch(() => voucherStore.savedAt, loadAccounts)
</script>

<template>
  <div class="app-shell">
    <div class="cz-global-loading" :class="{ on: isLoading }"><div class="bar" /></div>
    <transition name="cz-mask-fade">
      <div v-if="isLoading" class="cz-global-mask">
        <div class="cz-global-spinner">
          <div class="cz-spin-ring" />
          <span class="cz-spin-text">加载中…</span>
        </div>
      </div>
    </transition>
    <header class="cz-topbar cz-bluebar">
      <div class="cz-top-left">
        <el-popover
          ref="brandPopover"
          placement="bottom-start"
          trigger="click"
          :width="180"
          popper-class="cz-brand-popover"
          :show-arrow="false"
        >
          <template #reference>
            <div class="cz-pill brand">财智8 <span class="caret-down">▾</span></div>
          </template>
          <el-menu class="cz-brand-menu" :unique-opened="true" @select="onBrandCommand">
            <el-sub-menu index="ledger">
              <template #title>账簿{{ ledgerStore.current ? '(' + ledgerStore.current.name + ')' : '' }}</template>
              <el-menu-item index="ledger-new">新建账簿</el-menu-item>
              <el-menu-item index="ledger-open">打开账簿</el-menu-item>
              <el-menu-item index="ledger-delete" class="cz-menu-divided">删除账簿</el-menu-item>
              <el-menu-item index="ledger-import" class="cz-menu-divided">导入账簿数据</el-menu-item>
              <el-menu-item index="ledger-export">导出账簿数据</el-menu-item>
            </el-sub-menu>
            <el-sub-menu index="data-manage">
              <template #title>资料管理</template>
              <el-menu-item index="data-categories">收支项目</el-menu-item>
              <el-menu-item index="data-parties">人员与机构</el-menu-item>
              <el-menu-item index="data-finance" class="cz-menu-divided">管理金融产品</el-menu-item>
              <el-menu-item index="data-currency-rate" class="cz-menu-divided">币种与汇率</el-menu-item>
              <el-menu-item index="data-deposit-rate">存款利率</el-menu-item>
              <el-menu-item index="data-remarks">常用备注</el-menu-item>
            </el-sub-menu>
            <el-menu-item index="plan-remind">计划提醒</el-menu-item>
            <el-menu-item index="tools">财务工具</el-menu-item>
            <el-menu-item index="help">帮助</el-menu-item>
          </el-menu>
        </el-popover>
      </div>
      <div class="cz-top-mid">
        <el-dropdown trigger="click" @command="switchModule">
          <span class="cz-pill action cz-module-pill">
            {{ activeModule.name }}<span class="caret-down">▾</span>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="m in modules" :key="m.key" :command="m.key">{{ m.name }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown trigger="click" placement="bottom-start" @command="onRecordCommand">
          <span class="cz-pill action cz-record-pill">记账 <span class="cz-record-caret-inline">▾</span></span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="record">日常收支</el-dropdown-item>
              <el-dropdown-item command="batch-record">批量记账</el-dropdown-item>
              <el-dropdown-item command="batch-transfer">批量转账</el-dropdown-item>
              <el-dropdown-item command="salary">工资收入</el-dropdown-item>
              <el-dropdown-item command="deposit" divided>存款</el-dropdown-item>
              <el-dropdown-item command="withdraw">取款</el-dropdown-item>
              <el-dropdown-item command="transfer">转账</el-dropdown-item>
              <el-dropdown-item command="loan-borrow" divided>借入</el-dropdown-item>
              <el-dropdown-item command="loan-lend">借出</el-dropdown-item>
              <el-dropdown-item command="major-buy" divided>物品买入</el-dropdown-item>
              <el-dropdown-item command="voucher-buy">购券</el-dropdown-item>
              <el-dropdown-item divided class="cz-record-more">
                <el-dropdown trigger="hover" placement="right-start" @command="onRecordCommand">
                  <span class="cz-more-trigger">更多交易活动 <span class="cz-more-arrow">›</span></span>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="buy">证券买入</el-dropdown-item>
                      <el-dropdown-item command="sell">证券卖出</el-dropdown-item>
                      <el-dropdown-item command="fund-buy" divided>开放式基金申购</el-dropdown-item>
                      <el-dropdown-item command="forex-trade" divided>外汇买卖</el-dropdown-item>
                      <el-dropdown-item command="currency-exchange" divided>货币兑换</el-dropdown-item>
                      <el-dropdown-item command="p2p-lend" divided>网贷借出</el-dropdown-item>
                      <el-dropdown-item command="p2p-collect">网贷收回</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div class="cz-top-right">
        <button class="cz-icon-btn" title="财务计划和提醒" @click="planStore.open()">◷</button>
      </div>
    </header>

    <aside class="cz-sidebar">
      <nav class="cz-nav">
        <RouterLink v-for="item in activeModule.items" :key="item.to" :to="item.to">
          <span class="ico">◫</span>{{ item.label }}
        </RouterLink>
      </nav>

      <!-- 左下：账户列表常驻显示（仅财务数据模块） -->
      <div class="cz-acct-section" v-if="activeModuleKey === 'data'">
        <div class="cz-acct-body">
          <el-empty v-if="!accounts.length" description="暂无账户" :image-size="60" />
          <template v-else>
            <div v-for="g in accountGroups" :key="g.name" class="cz-acct-group">
              <!-- 单条汇总入口（债权债务、重大资产）：直接跳转，无下拉明细 -->
              <button v-if="g.flat" class="cz-acct-group-head cz-acct-flat" @click="router.push(g.to!)">
                <span class="g-name">{{ g.name }}</span>
                <span class="g-total" :class="{ expense: g.total < 0 }">{{ fmtMoney(g.total) }}</span>
              </button>
              <template v-else>
                <div class="cz-acct-group-head" @click="toggleGroup(g.name)">
                  <span class="caret">{{ collapsed[g.name] ? '▸' : '▾' }}</span>
                  <span class="g-name">{{ g.name }}</span>
                  <span class="g-total" :class="{ expense: g.total < 0 }">{{ fmtMoney(g.total) }}</span>
                </div>
                <template v-if="!collapsed[g.name]">
                  <button
                    v-for="a in g.items"
                    :key="a.id"
                    class="cz-acct-item"
                    @click="openSidebarItem(a)"
                  >
                    <span class="name">{{ a.name }}</span>
                    <span class="amount" :class="{ expense: accountValue(a) < 0 }">{{ fmtMoney(accountValue(a)) }}</span>
                  </button>
                </template>
              </template>
            </div>
          </template>
        </div>
        <button class="cz-acct-new" @click="goNewAccount">+ 新增账户</button>
      </div>
    </aside>

    <main class="cz-content">
      <RouterView v-if="ledgerStore.currentId" />
    </main>

    <nav v-if="isMobileTab" class="tabbar">
      <RouterLink to="/" :class="{ active: route.path === '/' }">🏠<span>首页</span></RouterLink>
      <RouterLink to="/transactions" :class="{ active: route.path === '/transactions' }">📋<span>流水</span></RouterLink>
      <a class="tab-record" @click="recordStore.open()">➕<span>记一笔</span></a>
      <RouterLink to="/accounts" :class="{ active: route.path === '/accounts' }">💳<span>账户</span></RouterLink>
      <RouterLink to="/statistics" :class="{ active: route.path === '/statistics' }">📊<span>统计</span></RouterLink>
    </nav>

    <NewTransaction />
    <StockTrade />
    <P2PLend />
    <P2PCollect />
    <FundBuy />
    <FundBuy />
    <PlansDialog />
    <LoanDialog />
    <MajorAssetBuyDialog />
    <ForexTrade />
    <SalaryDialog />
    <IpoConfirm />

    <!-- 新建账簿 -->
    <el-dialog v-model="newLedgerVisible" title="新建账簿" width="400px">
      <el-form label-width="80px">
        <el-form-item label="账簿名称" required>
          <el-input v-model="newLedgerName" placeholder="请输入账簿名称" @keyup.enter="confirmNewLedger" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="newLedgerVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmNewLedger">确定</el-button>
      </template>
    </el-dialog>

    <!-- 打开账簿 -->
    <el-dialog v-model="openLedgerVisible" title="打开账簿" width="400px">
      <el-radio-group v-model="pickLedgerId" class="cz-ledger-picker">
        <el-radio v-for="l in ledgerStore.ledgers" :key="l.id" :value="l.id" border>{{ l.name }}</el-radio>
      </el-radio-group>
      <template #footer>
        <el-button @click="openLedgerVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmOpenLedger">打开</el-button>
      </template>
    </el-dialog>
  </div>
</template>

