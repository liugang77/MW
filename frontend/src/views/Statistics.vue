<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import dayjs from 'dayjs'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, BarChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import type { Diagnosis } from '../types'
import { fmtMoney } from '../utils/format'

use([CanvasRenderer, PieChart, BarChart, TooltipComponent, LegendComponent, GridComponent])

const ledgerStore = useLedgerStore()
const pieOption = ref<Record<string, unknown>>({})
const barOption = ref<Record<string, unknown>>({})
const hasPie = ref(false)
const hasBar = ref(false)
const diag = ref<Diagnosis | null>(null)
const fmt = (v: string | number) => fmtMoney(v)

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  const start = dayjs().startOf('month').toISOString()
  const end = dayjs().endOf('month').toISOString()

  try {
    const cat = await api.byCategory(lid, { kind: 'expense', start, end })
    hasPie.value = cat.items.length > 0
    pieOption.value = {
      color: ['#d9534f', '#e8746f', '#f0a59f', '#e6a23c', '#2e9c4f', '#5fb878', '#409eff', '#9b59b6', '#7f8c8d'],
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 0 },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        data: cat.items.map((i) => ({ name: i.name, value: Number(i.amount) }))
      }]
    }

    const trend = await api.trend(lid, {})
    hasBar.value = trend.some((t) => Number(t.income) || Number(t.expense))
    barOption.value = {
      tooltip: { trigger: 'axis' },
      legend: { data: ['收入', '支出'] },
      xAxis: { type: 'category', data: trend.map((t) => t.period) },
      yAxis: { type: 'value' },
      series: [
        { name: '收入', type: 'bar', data: trend.map((t) => Number(t.income)), itemStyle: { color: '#2e9c4f' } },
        { name: '支出', type: 'bar', data: trend.map((t) => Number(t.expense)), itemStyle: { color: '#d9534f' } }
      ]
    }

    diag.value = await api.diagnosis(lid)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载统计数据失败')
  }
}

onMounted(load)
watch(() => ledgerStore.currentId, load)
</script>

<template>
  <div class="page">
    <h2>统计</h2>

    <el-card v-if="diag" shadow="never" style="margin-bottom:16px">
      <div style="margin-bottom:12px;font-weight:600">财务诊断（近 12 个月）</div>
      <el-row :gutter="12">
        <el-col :span="8" :xs="12">
          <div class="diag-k">总收入</div>
          <div class="diag-v income">{{ fmt(diag.total_income) }}</div>
        </el-col>
        <el-col :span="8" :xs="12">
          <div class="diag-k">总支出</div>
          <div class="diag-v expense">{{ fmt(diag.total_expense) }}</div>
        </el-col>
        <el-col :span="8" :xs="12">
          <div class="diag-k">结余</div>
          <div class="diag-v" :class="Number(diag.surplus) >= 0 ? 'income' : 'expense'">{{ fmt(diag.surplus) }}</div>
        </el-col>
      </el-row>
      <el-divider style="margin:12px 0" />
      <el-row :gutter="12">
        <el-col :span="6" :xs="12"><div class="diag-k">薪资收入</div><div class="diag-v">{{ fmt(diag.salary_income) }}</div></el-col>
        <el-col :span="6" :xs="12"><div class="diag-k">租金收入</div><div class="diag-v">{{ fmt(diag.rent_income) }}</div></el-col>
        <el-col :span="6" :xs="12"><div class="diag-k">投资收入</div><div class="diag-v">{{ fmt(diag.invest_income) }}</div></el-col>
        <el-col :span="6" :xs="12"><div class="diag-k">其他收入</div><div class="diag-v">{{ fmt(diag.other_income) }}</div></el-col>
      </el-row>
      <el-divider style="margin:12px 0" />
      <el-row :gutter="12">
        <el-col :span="12"><div class="diag-k">结余率</div><div class="diag-v">{{ diag.surplus_ratio }}%</div></el-col>
        <el-col :span="12"><div class="diag-k">投资收入占比</div><div class="diag-v">{{ diag.invest_ratio }}%</div></el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" style="margin-bottom:16px">
      <div style="margin-bottom:8px;font-weight:600">本月支出分类占比</div>
      <v-chart v-if="hasPie" :option="pieOption" style="height:320px" autoresize />
      <el-empty v-else description="本月暂无支出数据" :image-size="80" />
    </el-card>
    <el-card shadow="never">
      <div style="margin-bottom:8px;font-weight:600">收支趋势（按月）</div>
      <v-chart v-if="hasBar" :option="barOption" style="height:320px" autoresize />
      <el-empty v-else description="暂无收支趋势数据" :image-size="80" />
    </el-card>
  </div>
</template>

<style scoped>
.diag-k { color: #909399; font-size: 13px; }
.diag-v { font-size: 20px; font-weight: 600; margin-top: 2px; }
</style>
