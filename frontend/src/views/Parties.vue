<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import type { Party } from '../types'

type PartyType = 'member' | 'contact' | 'org'

const ledgerStore = useLedgerStore()
const tab = ref<PartyType>('member')
const all = ref<Party[]>([])
const keyword = ref('')

const tabs: { key: PartyType; label: string; addLabel: string }[] = [
  { key: 'member', label: '家庭成员', addLabel: '新增家庭成员' },
  { key: 'contact', label: '往来人员', addLabel: '新增往来人员' },
  { key: 'org', label: '机构', addLabel: '新增机构' }
]

const currentTab = computed(() => tabs.find((t) => t.key === tab.value)!)
const isOrg = computed(() => tab.value === 'org')

const list = computed(() => {
  const kw = keyword.value.trim()
  return all.value
    .filter((p) => p.type === tab.value)
    .filter((p) => !kw || p.name.includes(kw) || (p.contact || '').includes(kw))
})

const dialog = ref(false)
const editingId = ref<number | null>(null)
const form = ref<{
  name: string; type: PartyType; gender: string; birthday_type: string; birthday: string
  contact: string; address: string
}>({ name: '', type: 'member', gender: 'male', birthday_type: 'solar', birthday: '', contact: '', address: '' })

const formIsOrg = computed(() => form.value.type === 'org')

function genderText(g?: string | null) {
  return g === 'male' ? '男' : g === 'female' ? '女' : ''
}
function birthdayTypeText(t?: string | null) {
  return t === 'lunar' ? '农历' : t === 'solar' ? '公历' : ''
}

async function load() {
  const lid = ledgerStore.currentId
  if (!lid) return
  all.value = await api.listParties(lid)
}

function openCreate() {
  editingId.value = null
  form.value = { name: '', type: tab.value, gender: 'male', birthday_type: 'solar', birthday: '', contact: '', address: '' }
  dialog.value = true
}

function openEdit(p: Party) {
  editingId.value = p.id
  form.value = {
    name: p.name,
    type: (p.type as PartyType) || 'member',
    gender: p.gender || 'male',
    birthday_type: p.birthday_type || 'solar',
    birthday: p.birthday || '',
    contact: p.contact || '',
    address: p.address || ''
  }
  dialog.value = true
}

async function save() {
  if (!form.value.name.trim()) return ElMessage.warning('请输入名称')
  const isOrgForm = form.value.type === 'org'
  const payload: Partial<Party> = {
    name: form.value.name,
    type: form.value.type,
    gender: isOrgForm ? null : (form.value.gender as 'male' | 'female'),
    birthday_type: isOrgForm ? null : (form.value.birthday_type as 'solar' | 'lunar'),
    birthday: isOrgForm ? null : (form.value.birthday || null),
    contact: form.value.contact || null,
    address: form.value.address || null
  }
  if (editingId.value) {
    await api.updateParty(editingId.value, payload)
    ElMessage.success('已更新')
  } else {
    await api.createParty(ledgerStore.currentId as number, payload)
    ElMessage.success('已创建')
  }
  dialog.value = false
  load()
}

async function remove(p: Party) {
  try {
    await ElMessageBox.confirm(`确定删除「${p.name}」吗？`, '提示', { type: 'warning' })
    await api.deleteParty(p.id)
    ElMessage.success('已删除')
    load()
  } catch (e) { /* cancelled */ }
}

onMounted(load)
watch(() => ledgerStore.currentId, load)
</script>

<template>
  <div class="party-page">
    <div class="party-header">
      <h2 class="party-title">管理人员与机构</h2>
    </div>

    <div class="party-body">
      <aside class="party-side">
        <a
          v-for="t in tabs"
          :key="t.key"
          class="side-item"
          :class="{ active: tab === t.key }"
          @click="tab = t.key"
        >{{ t.label }}</a>
      </aside>

      <section class="party-main">
        <div class="party-toolbar">
          <el-button @click="openCreate">{{ currentTab.addLabel }}</el-button>
          <div class="toolbar-spacer" />
          <el-input v-model="keyword" placeholder="请输入要搜索的关键字…" style="width: 240px" clearable />
        </div>

        <el-table :data="list" class="party-table" @row-dblclick="openEdit">
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column v-if="!isOrg" label="性别" width="90">
            <template #default="{ row }">{{ genderText(row.gender) }}</template>
          </el-table-column>
          <el-table-column v-if="!isOrg" label="生日类型" width="110">
            <template #default="{ row }">{{ birthdayTypeText(row.birthday_type) }}</template>
          </el-table-column>
          <el-table-column v-if="!isOrg" prop="birthday" label="出生日期" width="140" />
          <el-table-column prop="contact" label="联系方式" min-width="180" />
          <el-table-column prop="address" label="地址" min-width="200" />
          <el-table-column label="操作" width="140" align="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openEdit(row)">修改</el-button>
              <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>暂无数据</template>
        </el-table>
      </section>
    </div>

    <el-dialog
      v-model="dialog"
      title="人员与机构"
      width="90%"
      style="max-width:460px"
    >
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="请输入名称" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.type" style="width: 100%">
            <el-option label="家庭成员" value="member" />
            <el-option label="往来人员" value="contact" />
            <el-option label="机构" value="org" />
          </el-select>
        </el-form-item>
        <template v-if="!formIsOrg">
          <el-form-item label="性别">
            <el-radio-group v-model="form.gender">
              <el-radio value="male">男</el-radio>
              <el-radio value="female">女</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="生日类型">
            <el-radio-group v-model="form.birthday_type">
              <el-radio value="solar">公历</el-radio>
              <el-radio value="lunar">农历</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="出生日期">
            <el-date-picker
              v-model="form.birthday"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              style="width: 100%"
            />
          </el-form-item>
        </template>
        <el-form-item label="联系方式">
          <el-input v-model="form.contact" placeholder="电话 / 邮箱" />
        </el-form-item>
        <el-form-item label="地址">
          <el-input v-model="form.address" placeholder="请输入地址" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.party-page {
  background: #f3f6f9;
  min-height: calc(100vh - 52px);
}

.party-header {
  background: #fff;
  border-bottom: 1px solid #c8d3de;
  padding: 12px 16px;
}

.party-title {
  margin: 0;
  font-size: 16px;
  color: #415163;
}

.party-body {
  display: flex;
  min-height: calc(100vh - 105px);
}

.party-side {
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

.party-main {
  flex: 1;
  padding: 16px;
}

.party-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.toolbar-spacer {
  flex: 1;
}

.party-table {
  width: 100%;
  background: #fff;
}
</style>
