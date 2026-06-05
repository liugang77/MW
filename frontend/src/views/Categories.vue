<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import type { Category, CategoryKind } from '../types'

const ledgerStore = useLedgerStore()
const kind = ref<CategoryKind>('expense')
const all = ref<Category[]>([])
const keyword = ref('')

const dialog = ref(false)
const editingId = ref<number | null>(null)
const form = ref<{ name: string; icon: string; kind: CategoryKind; parent_id: number | null }>({
  name: '', icon: '📦', kind: 'expense', parent_id: null
})
const dialogTitle = computed(() => {
  if (editingId.value) return '修改项目'
  return form.value.parent_id ? '新增二级项目' : '新增项目'
})

// 当前类型下的顶级项目
const parents = computed(() =>
  all.value.filter((c) => c.kind === kind.value && c.is_active && !c.parent_id)
)

// 顶级项目下的二级项目
function childrenOf(pid: number): Category[] {
  return all.value.filter((c) => c.kind === kind.value && c.is_active && c.parent_id === pid)
}

// 关键字过滤后的分组
const groups = computed(() => {
  const kw = keyword.value.trim()
  return parents.value
    .map((p) => ({ parent: p, children: childrenOf(p.id) }))
    .filter((g) => {
      if (!kw) return true
      return g.parent.name.includes(kw) || g.children.some((c) => c.name.includes(kw))
    })
})

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  all.value = await api.listCategories(lid)
}

function openCreateParent() {
  editingId.value = null
  form.value = { name: '', icon: '📦', kind: kind.value, parent_id: null }
  dialog.value = true
}

function openCreateChild(parent: Category) {
  editingId.value = null
  form.value = { name: '', icon: parent.icon || '📦', kind: kind.value, parent_id: parent.id }
  dialog.value = true
}

function openEdit(c: Category) {
  editingId.value = c.id
  form.value = { name: c.name, icon: c.icon, kind: c.kind, parent_id: c.parent_id ?? null }
  dialog.value = true
}

async function save() {
  if (!form.value.name.trim()) return ElMessage.warning('请输入名称')
  if (editingId.value) {
    await api.updateCategory(editingId.value, { name: form.value.name, icon: form.value.icon })
    ElMessage.success('已更新')
  } else {
    await api.createCategory(ledgerStore.currentId as number, {
      name: form.value.name,
      icon: form.value.icon,
      kind: form.value.kind,
      parent_id: form.value.parent_id
    })
    ElMessage.success('已创建')
  }
  dialog.value = false
  load()
}

async function remove(c: Category) {
  try {
    await ElMessageBox.confirm(`确定删除项目「${c.name}」吗？`, '提示', { type: 'warning' })
    await api.deleteCategory(c.id)
    ElMessage.success('已删除')
    load()
  } catch (e) { /* cancelled */ }
}

onMounted(load)
watch(() => ledgerStore.currentId, load)
</script>

<template>
  <div class="cat-page">
    <div class="cat-header">
      <h2 class="cat-title">管理收支项目</h2>
    </div>

    <div class="cat-body">
      <!-- 左侧类型切换 -->
      <aside class="cat-side">
        <a class="side-item" :class="{ active: kind === 'expense' }" @click="kind = 'expense'">支出项目</a>
        <a class="side-item" :class="{ active: kind === 'income' }" @click="kind = 'income'">收入项目</a>
      </aside>

      <!-- 右侧内容 -->
      <section class="cat-main">
        <div class="cat-tips">
          <p>隐藏的收支项目将不会在记账时的收支项目选择列表中显示。</p>
          <p>系统预置的收支项目为固定项目，不支持修改或删除操作。</p>
        </div>

        <div class="cat-toolbar">
          <el-button @click="openCreateParent">新增项目</el-button>
          <div class="toolbar-spacer" />
          <el-input v-model="keyword" placeholder="请输入要搜索的关键字…" style="width: 240px" clearable />
        </div>

        <div class="cat-groups">
          <div v-for="g in groups" :key="g.parent.id" class="cat-group">
            <div class="group-name">{{ g.parent.name }}</div>
            <div class="group-items">
              <div class="items-grid">
                <span
                  v-for="c in g.children"
                  :key="c.id"
                  class="item-cell"
                  @click="openEdit(c)"
                >
                  {{ c.name }}
                  <el-icon class="del-icon" @click.stop="remove(c)"><Close /></el-icon>
                </span>
              </div>
              <a class="add-child" @click="openCreateChild(g.parent)">＋ 新增二级项目</a>
            </div>
          </div>
          <div v-if="!groups.length" class="cat-empty">暂无收支项目</div>
        </div>
      </section>
    </div>

    <el-dialog v-model="dialog" :title="dialogTitle" width="90%" style="max-width:400px">
      <el-form label-width="70px">
        <el-form-item label="图标"><el-input v-model="form.icon" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="请输入项目名称" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.cat-page {
  background: #f3f6f9;
  min-height: calc(100vh - 52px);
}

.cat-header {
  background: #fff;
  border-bottom: 1px solid #c8d3de;
  padding: 12px 16px;
}

.cat-title {
  margin: 0;
  font-size: 16px;
  color: #415163;
}

.cat-body {
  display: flex;
  min-height: calc(100vh - 105px);
}

.cat-side {
  width: 150px;
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

.cat-main {
  flex: 1;
  padding: 16px;
}

.cat-tips {
  color: #909aa6;
  font-size: 12px;
  line-height: 1.8;
  margin-bottom: 12px;
}

.cat-tips p {
  margin: 0;
}

.cat-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.toolbar-spacer {
  flex: 1;
}

.cat-groups {
  background: #fff;
  border: 1px solid #e4e9ef;
  border-radius: 4px;
}

.cat-group {
  display: flex;
  border-bottom: 1px solid #eef2f6;
}

.cat-group:last-child {
  border-bottom: none;
}

.group-name {
  width: 130px;
  flex: 0 0 130px;
  display: flex;
  align-items: center;
  padding: 14px 16px;
  font-weight: 700;
  color: #415163;
  background: #fafbfc;
  border-right: 1px solid #eef2f6;
}

.group-items {
  flex: 1;
  padding: 10px 16px;
}

.items-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px 8px;
}

.item-cell {
  position: relative;
  color: #55677a;
  font-size: 13px;
  cursor: pointer;
  padding: 4px 0;
}

.item-cell:hover {
  color: #3f79a8;
}

.item-cell .del-icon {
  display: none;
  margin-left: 4px;
  font-size: 12px;
  color: #de6d6d;
  vertical-align: -1px;
}

.item-cell:hover .del-icon {
  display: inline-block;
}

.add-child {
  display: inline-block;
  margin-top: 10px;
  color: #909aa6;
  font-size: 13px;
  cursor: pointer;
}

.add-child:hover {
  color: #3f79a8;
}

.cat-empty {
  padding: 40px;
  text-align: center;
  color: #909aa6;
}

@media (max-width: 768px) {
  .items-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
