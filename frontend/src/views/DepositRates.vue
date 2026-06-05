<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import type { DepositRate } from '../types'

const ledgerStore = useLedgerStore()

const tab = ref<'cny' | 'foreign'>('cny')
const rows = ref<DepositRate[]>([])

const cnyRows = computed(() => rows.value.filter((r) => r.group_key === 'cny'))
const foreignRows = computed(() => rows.value.filter((r) => r.group_key === 'foreign'))

// 人民币：合并相同储蓄类型的首行单元格（rowspan）
const cnySpan = ({ row, column, rowIndex }: { row: DepositRate; column: { property?: string }; rowIndex: number }) => {
  if (column.property !== 'save_type') return
  const list = cnyRows.value
  const prev = list[rowIndex - 1]
  if (prev && prev.save_type === row.save_type) return { rowspan: 0, colspan: 0 }
  let span = 1
  for (let i = rowIndex + 1; i < list.length; i++) {
    if (list[i].save_type === row.save_type) span++
    else break
  }
  return { rowspan: span, colspan: 1 }
}

const fmtCny = (v: unknown) => (v == null || v === '' ? '0.00' : Number(v).toFixed(2))
const fmtFx = (v: unknown) => (v == null || v === '' ? '0.0000' : Number(v).toFixed(4))

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  rows.value = await api.listDepositRates(lid)
}

// ---- 行内编辑 ----
const editCell = ref('') // `${id}:${field}`
const editValue = ref('')

function startEdit(row: DepositRate, field: keyof DepositRate) {
  editCell.value = `${row.id}:${field}`
  editValue.value = String(row[field] ?? '')
}
function cancelEdit() {
  editCell.value = ''
  editValue.value = ''
}
async function saveEdit(row: DepositRate, field: keyof DepositRate) {
  const val = editValue.value === '' ? '0' : editValue.value
  await api.updateDepositRate(row.id, { [field]: val } as Partial<DepositRate>)
  ;(row as unknown as Record<string, unknown>)[field] = val
  editCell.value = ''
  editValue.value = ''
  ElMessage.success('已更新')
}

type FxCol = { field: keyof DepositRate; label: string }
const fxCols: FxCol[] = [
  { field: 'r_current', label: '活期' },
  { field: 'r_1m', label: '一个月' },
  { field: 'r_3m', label: '三个月' },
  { field: 'r_6m', label: '半年' },
  { field: 'r_1y', label: '一年' },
  { field: 'r_2y', label: '两年' },
  { field: 'r_7d_notice', label: '七天通知存款' }
]

onMounted(load)
watch(() => ledgerStore.currentId, load)
</script>

<template>
  <div class="fp-page">
    <div class="fp-header">
      <h2 class="fp-title">管理存款利率</h2>
    </div>

    <div class="fp-body">
      <aside class="fp-side">
        <a class="side-item" :class="{ active: tab === 'cny' }" @click="tab = 'cny'">人民币存款利率</a>
        <a class="side-item" :class="{ active: tab === 'foreign' }" @click="tab = 'foreign'">外币存款利率</a>
      </aside>

      <section class="fp-main">
        <!-- 人民币存款利率 -->
        <el-table v-if="tab === 'cny'" :data="cnyRows" class="fp-table" border :span-method="cnySpan">
          <el-table-column prop="save_type" label="储蓄类型" min-width="180" />
          <el-table-column prop="term" label="储蓄期间" min-width="200" />
          <el-table-column label="年利率(%)" width="180" align="right">
            <template #default="{ row }">
              <el-input
                v-if="editCell === row.id + ':rate'"
                v-model="editValue"
                type="number"
                size="small"
                style="width: 110px"
                @keyup.enter="saveEdit(row, 'rate')"
                @keyup.esc="cancelEdit"
                @blur="saveEdit(row, 'rate')"
              />
              <span v-else class="price-cell" @click="startEdit(row, 'rate')">{{ fmtCny(row.rate) }}</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 外币存款利率 -->
        <el-table v-else :data="foreignRows" class="fp-table" border highlight-current-row>
          <el-table-column prop="currency_name" label="币种" min-width="140" fixed="left" />
          <el-table-column
            v-for="col in fxCols"
            :key="col.field"
            :label="col.label"
            min-width="110"
            align="right"
          >
            <template #default="{ row }">
              <el-input
                v-if="editCell === row.id + ':' + col.field"
                v-model="editValue"
                type="number"
                size="small"
                @keyup.enter="saveEdit(row, col.field)"
                @keyup.esc="cancelEdit"
                @blur="saveEdit(row, col.field)"
              />
              <span v-else class="price-cell" @click="startEdit(row, col.field)">{{ fmtFx(row[col.field]) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </div>
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
  padding: 16px;
}
.fp-table {
  width: 100%;
  background: #fff;
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
</style>
