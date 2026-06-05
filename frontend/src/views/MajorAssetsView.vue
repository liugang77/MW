<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowDown } from '@element-plus/icons-vue'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useMajorAssetStore } from '../stores/majorAsset'
import type { Account, Transaction } from '../types'
import { fmtMoney } from '../utils/format'

const route = useRoute()
const ledgerStore = useLedgerStore()
const majorAssetStore = useMajorAssetStore()

const accounts = ref<Account[]>([])
const transactions = ref<Transaction[]>([])
const selectedAccountId = ref<number | null>(null)
const activeTab = ref<'trades' | 'value' | 'composition' | 'overview'>('trades')

const fmt = (v: string | number | null | undefined) => fmtMoney(v)
const currencyText = (v?: string | null) =>
  ({ CNY: '人民币', USD: '美元', HKD: '港币', EUR: '欧元' } as Record<string, string>)[v || 'CNY'] || v || '人民币'
const natureText = (a: Account) =>
  a.asset_nature === 'invest' ? '投资' : a.asset_nature === 'own' ? '自用' : (a.remark?.includes('投资') ? '投资' : '自用')

const assetAccounts = computed(() => accounts.value.filter((a) => a.type === 'major_asset'))


// 资产行：当前成本 = 期初余额；资产市值 = 当前余额；累计收益 = 市值 - 成本
interface AssetRow {
  id: number
  name: string
  currency: string
  cost: number
  profit: number
  marketValue: number
  nature: string
}

const assetRows = computed<AssetRow[]>(() =>
  assetAccounts.value.map((a) => {
    const cost = Number(a.initial_balance || 0)
    const marketValue = Number(a.current_balance || 0)
    return {
      id: a.id,
      name: a.name,
      currency: currencyText(a.currency),
      cost,
      marketValue,
      profit: marketValue - cost,
      nature: natureText(a),
    }
  })
)

const totalProfit = computed(() => assetRows.value.reduce((s, r) => s + r.profit, 0))
const totalValue = computed(() => assetRows.value.reduce((s, r) => s + r.marketValue, 0))

const selectedAccount = computed(() => assetAccounts.value.find((a) => a.id === selectedAccountId.value) || null)

// 选中资产的交易明细
const detailTxns = computed(() =>
  selectedAccountId.value
    ? transactions.value.filter(
        (t) => t.account_id === selectedAccountId.value || t.to_account_id === selectedAccountId.value
      )
    : []
)

const txnActivity = (t: Transaction) => {
  if ((t.remark || '').startsWith('重大资产买入')) return '重大资产买入'
  if (t.type === 'transfer') return t.to_account_id === selectedAccountId.value ? '追加投资' : '资产支取'
  if (t.type === 'income') return '资产增值'
  if (t.type === 'expense') return '资产减值'
  return '余额调整'
}

function selectAsset(row: AssetRow) {
  selectedAccountId.value = row.id
}
function assetRowClass({ row }: { row: AssetRow }) {
  return row.id === selectedAccountId.value ? 'cur-row' : ''
}

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  const res = await api.listTransactions(lid, { page_size: 500 })
  transactions.value = res.items
  syncSelection()
}

// 重大资产买入：使用全局对话框（账户中心「新增资产账户」也复用同一窗口）
function openBuy() {
  majorAssetStore.open('invest')
}


function syncSelection() {
  const qid = Number(route.query.account_id)
  if (qid && assetAccounts.value.some((a) => a.id === qid)) {
    selectedAccountId.value = qid
    return
  }
  if (!assetAccounts.value.some((a) => a.id === selectedAccountId.value)) {
    selectedAccountId.value = assetAccounts.value.length ? assetAccounts.value[0].id : null
  }
}

watch(() => route.query.account_id, syncSelection)

onMounted(load)
watch(() => ledgerStore.currentId, load)
watch(() => majorAssetStore.savedAt, async () => {
  await load()
  if (assetAccounts.value.length) selectedAccountId.value = assetAccounts.value[assetAccounts.value.length - 1].id
})
</script>

<template>
  <div class="ma-page">
    <!-- 上方：资产列表 -->
    <div class="panel">
      <div class="panel-head">
        <span class="panel-title">重大资产</span>
        <div class="head-spacer" />
        <el-dropdown trigger="click" @command="(c: string) => c === 'buy' && openBuy()">
          <el-button size="small">
            操作<el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="buy">重大资产买入</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <el-table
        :data="assetRows"
        size="small"
        border
        :row-class-name="assetRowClass"
        @row-click="selectAsset"
      >
        <el-table-column label="资产名称" min-width="200" fixed="left">
          <template #default="{ row }"><span style="font-weight:600">{{ row.name }}</span></template>
        </el-table-column>
        <el-table-column label="币种" min-width="100">
          <template #default="{ row }">{{ row.currency }}</template>
        </el-table-column>
        <el-table-column label="当前成本" align="right" min-width="140">
          <template #default="{ row }">{{ fmt(row.cost) }}</template>
        </el-table-column>
        <el-table-column label="累计收益" align="right" min-width="130">
          <template #default="{ row }">
            <span :class="row.profit >= 0 ? 'income' : 'expense'">{{ fmt(row.profit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资产市值" align="right" min-width="150">
          <template #default="{ row }">{{ fmt(row.marketValue) }}</template>
        </el-table-column>
        <el-table-column label="资产性质" align="center" min-width="100">
          <template #default="{ row }">{{ row.nature }}</template>
        </el-table-column>
        <template #empty>暂无重大资产，请在账户中心新增「重大资产」账户</template>
      </el-table>

      <!-- 汇总条 -->
      <div v-if="assetRows.length" class="ma-summary">
        <div class="sum-item"><span class="lbl">收益合计</span><span class="val" :class="totalProfit >= 0 ? 'income' : 'expense'">{{ fmt(totalProfit) }}</span></div>
        <div class="sum-item"><span class="lbl">资产合计</span><span class="val">{{ fmt(totalValue) }}</span></div>
      </div>
    </div>

    <!-- 下方：选中资产明细 -->
    <div class="panel">
      <div class="tabs">
        <span class="tab" :class="{ active: activeTab === 'trades' }" @click="activeTab = 'trades'">交易明细</span>
        <span class="tab" :class="{ active: activeTab === 'value' }" @click="activeTab = 'value'">市值管理</span>
        <span class="tab" :class="{ active: activeTab === 'composition' }" @click="activeTab = 'composition'">成本市值构成</span>
        <span class="tab" :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">资产概况</span>
        <span class="cur-acct" v-if="selectedAccount">{{ selectedAccount.name }}</span>
      </div>

      <!-- 交易明细 -->
      <template v-if="activeTab === 'trades'">
        <el-table :data="detailTxns" size="small" border>
          <el-table-column label="日期" min-width="120">
            <template #default="{ row }">{{ (row.occurred_at || '').slice(0, 10) }}</template>
          </el-table-column>
          <el-table-column label="发生金额" align="right" min-width="140">
            <template #default="{ row }">{{ fmt(row.amount) }}</template>
          </el-table-column>
          <el-table-column label="活动类型" min-width="140">
            <template #default="{ row }">{{ txnActivity(row) }}</template>
          </el-table-column>
          <el-table-column label="备注" min-width="220">
            <template #default="{ row }">{{ row.remark }}</template>
          </el-table-column>
          <template #empty>暂无交易明细</template>
        </el-table>
        <div class="ma-summary">
          <div class="sum-item"><span class="lbl">资产市值</span><span class="val">{{ fmt(selectedAccount?.current_balance) }}</span></div>
          <div class="sum-item"><span class="lbl">当前成本</span><span class="val">{{ fmt(selectedAccount?.initial_balance) }}</span></div>
          <div class="sum-item"><span class="lbl">记录数</span><span class="val">{{ detailTxns.length }}</span></div>
        </div>
      </template>

      <!-- 市值管理 -->
      <template v-else-if="activeTab === 'value'">
        <el-empty :description="selectedAccount ? `当前资产市值 ${fmt(selectedAccount.current_balance)}` : '暂无数据'" />
      </template>

      <!-- 成本市值构成 -->
      <template v-else-if="activeTab === 'composition'">
        <el-empty description="暂无数据" />
      </template>

      <!-- 资产概况 -->
      <template v-else>
        <el-descriptions v-if="selectedAccount" :column="2" border size="small">
          <el-descriptions-item label="资产名称">{{ selectedAccount.name }}</el-descriptions-item>
          <el-descriptions-item label="币种">{{ currencyText(selectedAccount.currency) }}</el-descriptions-item>
          <el-descriptions-item label="资产市值">{{ fmt(selectedAccount.current_balance) }}</el-descriptions-item>
          <el-descriptions-item label="当前成本">{{ fmt(selectedAccount.initial_balance) }}</el-descriptions-item>
          <el-descriptions-item label="资产性质">{{ natureText(selectedAccount) }}</el-descriptions-item>
          <el-descriptions-item label="所有者">{{ selectedAccount.owner || '—' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ selectedAccount.remark || '—' }}</el-descriptions-item>
        </el-descriptions>
        <el-empty v-else description="暂无数据" />
      </template>
    </div>
  </div>
</template>


<style scoped>
.ma-page { padding: 12px 16px; display: flex; flex-direction: column; gap: 14px; }
.panel { background: #fff; border: 1px solid #ebeef2; border-radius: 8px; padding: 12px 14px; }
.panel-head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.panel-title { font-size: 16px; font-weight: 600; color: #3c4b59; }
.head-spacer { flex: 1; }
.tabs { display: flex; align-items: center; gap: 18px; margin-bottom: 10px; border-bottom: 1px solid #f2f4f6; }
.tab { padding: 6px 2px; font-size: 14px; color: #909399; cursor: pointer; border-bottom: 2px solid transparent; }
.tab.active { color: #409eff; border-bottom-color: #409eff; font-weight: 600; }
.cur-acct { margin-left: auto; font-size: 13px; color: #606266; }
.ma-summary { display: flex; flex-wrap: wrap; gap: 36px; margin-top: 12px; padding: 10px 16px; background: #f7f8fa; border-radius: 6px; justify-content: flex-end; }
.sum-item { display: flex; flex-direction: column; gap: 2px; }
.sum-item .lbl { font-size: 12px; color: #909399; }
.sum-item .val { font-size: 15px; font-weight: 600; color: #3c4b59; }
.income { color: #67c23a; }
.expense { color: #f56c6c; }
:deep(.cur-row) { background: #ecf5ff !important; }
:deep(.el-table__row) { cursor: pointer; }
</style>
