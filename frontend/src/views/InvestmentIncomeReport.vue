<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import dayjs from 'dayjs'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart } from 'echarts/charts'
import { TooltipComponent, GridComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import type { InvestmentIncomeReport } from '../types'
import { fmtMoney } from '../utils/format'

use([CanvasRenderer, BarChart, TooltipComponent, GridComponent])

const ledgerStore = useLedgerStore()
const report = ref<InvestmentIncomeReport | null>(null)
const range = ref<[string, string] | null>(null)
const reportDate = dayjs().format('YYYY-MM-DD')

const fmt = (v: string | number) => fmtMoney(v)

const rangeText = computed(() => {
  if (!range.value) return `所有 ～ ${reportDate}`
  return `${range.value[0]} 到 ${range.value[1]}`
})

const barOption = computed(() => {
  const groups = report.value?.groups || []
  return {
    tooltip: { trigger: 'axis', formatter: '{b}: {c}' },
    grid: { left: 10, right: 20, top: 20, bottom: 24, containLabel: true },
    xAxis: { type: 'category', data: groups.map((g) => g.account_name), axisLabel: { interval: 0 } },
    yAxis: { type: 'value' },
    series: [{
      type: 'bar',
      barMaxWidth: 48,
      data: groups.map((g) => ({
        value: Number(g.total_profit),
        itemStyle: { color: Number(g.total_profit) >= 0 ? '#d9534f' : '#5cb85c' }
      })),
      label: { show: true, position: 'top', formatter: (p: { value: number }) => fmt(p.value) }
    }]
  }
})

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  const params: Record<string, unknown> = {}
  if (range.value) {
    params.start = dayjs(range.value[0]).startOf('day').toISOString()
    params.end = dayjs(range.value[1]).endOf('day').toISOString()
  }
  report.value = await api.investmentIncome(lid, params)
}

onMounted(load)
watch(() => ledgerStore.currentId, load)
watch(range, load)
</script>

<template>
  <div class="rpt-page">
    <!-- 顶部筛选条 -->
    <div class="rpt-toolbar">
      <span class="range-pill">{{ rangeText }}</span>
      <el-date-picker
        v-model="range"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="到"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        size="small"
        clearable
      />
      <div class="spacer" />
    </div>

    <h2 class="rpt-title">投资收益一览表</h2>
    <div class="rpt-meta">
      <span>统计范围：{{ rangeText }}</span>
      <span>制表日期：{{ reportDate }}</span>
      <span>系统本币：人民币</span>
    </div>

    <el-empty v-if="!report || !report.groups.length" description="暂无投资收益数据" />

    <template v-else>
      <!-- 柱状图：各账户盈亏 -->
      <el-card shadow="never" class="chart-card">
        <v-chart :option="barOption" class="rpt-chart" autoresize />
      </el-card>

      <!-- 收益表：按账户分组 -->
      <table class="rpt-table">
        <thead>
          <tr>
            <th class="col-acct"></th>
            <th class="col-name">名称</th>
            <th class="col-profit">盈亏</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="g in report.groups" :key="g.account_id">
            <tr v-for="(row, idx) in g.rows" :key="g.account_id + '-' + idx">
              <td v-if="idx === 0" class="col-acct acct-cell" :rowspan="g.rows.length + 1">
                {{ g.account_name }}
              </td>
              <td class="col-name">
                <span v-if="row.symbol" class="code">{{ row.symbol }}</span>{{ row.name }}
              </td>
              <td class="col-profit" :class="Number(row.profit) >= 0 ? 'pos' : 'neg'">
                {{ fmt(row.profit) }}
              </td>
            </tr>
            <tr class="subtotal-row">
              <td class="col-name">合计</td>
              <td class="col-profit" :class="Number(g.total_profit) >= 0 ? 'pos' : 'neg'">
                {{ fmt(g.total_profit) }}
              </td>
            </tr>
          </template>
        </tbody>
        <tfoot>
          <tr class="grand-row">
            <td class="col-acct">总计</td>
            <td class="col-name"></td>
            <td class="col-profit" :class="Number(report.total_profit) >= 0 ? 'pos' : 'neg'">
              {{ fmt(report.total_profit) }}
            </td>
          </tr>
        </tfoot>
      </table>
    </template>
  </div>
</template>

<style scoped>
.rpt-page {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.rpt-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.range-pill {
  padding: 4px 12px;
  background: #f2f4f6;
  border-radius: 4px;
  font-size: 13px;
  color: #606266;
}

.spacer {
  flex: 1;
}

.rpt-title {
  text-align: center;
  font-size: 22px;
  font-weight: 700;
  color: #303133;
  margin: 4px 0;
}

.rpt-meta {
  display: flex;
  justify-content: center;
  gap: 32px;
  color: #909399;
  font-size: 13px;
}

.chart-card :deep(.el-card__body) {
  padding: 8px 12px;
}

.rpt-chart { height: 280px; width: 100%; }

.rpt-table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  font-size: 14px;
}

.rpt-table th,
.rpt-table td {
  border: 1px solid #ebeef5;
  padding: 10px 14px;
}

.rpt-table thead th {
  background: #fafafa;
  color: #909399;
  font-weight: 600;
  text-align: left;
}

.col-profit {
  text-align: right;
  width: 200px;
  font-variant-numeric: tabular-nums;
}

.col-acct {
  width: 200px;
  font-weight: 600;
  color: #303133;
}

.acct-cell {
  background: #fafafa;
  vertical-align: middle;
}

.code {
  color: #909399;
  margin-right: 8px;
  font-size: 13px;
}

.subtotal-row td {
  background: #f7f9fb;
  font-weight: 600;
  color: #303133;
}

.grand-row td {
  background: #eef3f8;
  font-weight: 700;
  color: #303133;
}

.pos {
  color: #d9534f;
}

.neg {
  color: #5cb85c;
}

/* ---------- 响应式：手机 ---------- */
@media (max-width: 768px) {
  .rpt-page { padding: 12px 12px 72px; gap: 10px; }
  .rpt-toolbar { flex-wrap: wrap; }
  .rpt-title { font-size: 18px; }
  .rpt-meta { flex-wrap: wrap; gap: 6px 16px; justify-content: flex-start; }
  .rpt-chart { height: 240px; }
  .rpt-table { font-size: 13px; }
  .rpt-table th,
  .rpt-table td { padding: 7px 8px; }
  .col-profit,
  .col-acct { width: auto; }
}
</style>
