<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import type { Budget, Category } from '../types'

const ledgerStore = useLedgerStore()
const budgets = ref<Budget[]>([])
const categories = ref<Category[]>([])
const dialog = ref(false)
const editingId = ref<number | null>(null)
const form = ref<any>({ category_id: null, period: 'month', amount: 0 })

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  budgets.value = await api.listBudgets(lid)
  categories.value = await api.listCategories(lid, 'expense')
}

function openCreate() {
  editingId.value = null
  form.value = { category_id: null, period: 'month', amount: 0 }
  dialog.value = true
}

function openEdit(b: Budget) {
  editingId.value = b.id
  form.value = { category_id: b.category_id, period: b.period, amount: b.amount }
  dialog.value = true
}

async function save() {
  if (!form.value.amount || Number(form.value.amount) <= 0) return ElMessage.warning('请输入预算金额')
  if (editingId.value) {
    await api.updateBudget(editingId.value, form.value)
    ElMessage.success('已更新')
  } else {
    await api.createBudget(ledgerStore.currentId as number, form.value)
    ElMessage.success('已创建')
  }
  dialog.value = false
  load()
}

async function remove(b: Budget) {
  try {
    await ElMessageBox.confirm('确定删除该预算吗？', '提示', { type: 'warning' })
    await api.deleteBudget(b.id)
    ElMessage.success('已删除')
    load()
  } catch (e) { /* cancelled */ }
}

function ratio(b: Budget) {
  const a = Number(b.amount)
  return a ? Math.min(100, Math.round(Number(b.spent) / a * 100)) : 0
}
function barStatus(b: Budget) {
  const r = ratio(b)
  if (r >= 100) return 'exception'
  if (r >= 80) return 'warning'
  return 'success'
}

onMounted(load)
watch(() => ledgerStore.currentId, load)
</script>

<template>
  <div class="page">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <h2>预算</h2>
      <el-button type="primary" @click="openCreate">新增预算</el-button>
    </div>

    <el-empty v-if="!budgets.length" description="还没有预算，添加一个吧" />
    <el-card v-for="b in budgets" :key="b.id" shadow="never" style="margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <div style="font-weight:600">{{ b.category_name }}<span style="color:#909399;font-size:12px;margin-left:8px">{{ b.period === 'year' ? '年度' : '月度' }}</span></div>
        <div>
          <span :class="Number(b.spent) > Number(b.amount) ? 'expense' : ''">{{ b.spent }}</span>
          <span style="color:#909399"> / {{ b.amount }}</span>
        </div>
      </div>
      <el-progress :percentage="ratio(b)" :status="barStatus(b)" :stroke-width="14" />
      <div style="margin-top:8px;text-align:right">
        <el-button link type="primary" size="small" @click="openEdit(b)">编辑</el-button>
        <el-button link type="danger" size="small" @click="remove(b)">删除</el-button>
      </div>
    </el-card>

    <el-dialog v-model="dialog" :title="editingId ? '编辑预算' : '新增预算'" width="90%" style="max-width:420px">
      <el-form label-width="80px">
        <el-form-item label="分类">
          <el-select v-model="form.category_id" style="width:100%" clearable placeholder="总预算（不限分类）">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="周期">
          <el-radio-group v-model="form.period">
            <el-radio-button value="month">月度</el-radio-button>
            <el-radio-button value="year">年度</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="金额"><el-input v-model="form.amount" type="number" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
