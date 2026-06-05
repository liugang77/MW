<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useLedgerStore } from '../stores/ledger'
import { useIpoStore } from '../stores/ipo'
import type { Account, Tag, IpoPending } from '../types'

const ledgerStore = useLedgerStore()
const ipoStore = useIpoStore()

const accounts = ref<Account[]>([])
const tags = ref<Tag[]>([])
const pending = ref<IpoPending[]>([])

// 证券账户：可参与新股申购的证券类账户
const SEC_TYPES = ['stock', 'bond', 'reverse_repo', 'futures', 'margin']
const securityAccountId = ref<number | null>(null)
const selectedTxnId = ref<number | null>(null)
const won = ref(false)
const refund = ref('0')
const tagIds = ref<number[]>([])
const remark = ref('')
const occurredAt = ref(new Date().toISOString().slice(0, 10))

const securityAccounts = computed(() =>
  accounts.value.filter((a) => SEC_TYPES.includes(a.type))
)

// 当前证券账户下的待确认申购
const pendingForAccount = computed(() =>
  pending.value.filter(
    (p) => p.security_account_id === securityAccountId.value || p.funding_account_id === securityAccountId.value
  )
)

const selected = computed(() => pendingForAccount.value.find((p) => p.txn_id === selectedTxnId.value) || null)
const subscribeAmount = computed(() => (selected.value ? Number(selected.value.amount) : 0))
const fundingAccountName = computed(() => {
  const id = selected.value?.funding_account_id
  return accounts.value.find((a) => a.id === id)?.name || ''
})

const fmt = (v: number) => v.toFixed(2)
const tagName = (id: number) => tags.value.find((t) => t.id === id)?.name || ''

async function loadMeta() {
  const lid = ledgerStore.currentId
  if (!lid) return
  accounts.value = await api.listAccounts(lid)
  tags.value = await api.listTags(lid)
  pending.value = await api.ipoPending(lid)
}

function reset() {
  securityAccountId.value =
    ipoStore.presetAccountId ?? pendingForAccount.value[0]?.security_account_id ?? securityAccounts.value[0]?.id ?? null
  selectedTxnId.value = null
  won.value = false
  refund.value = '0'
  tagIds.value = []
  remark.value = ''
  occurredAt.value = new Date().toISOString().slice(0, 10)
}

// 选择申购证券后：默认返款金额 = 未中签时全额、中签时 0
watch(selected, (p) => {
  refund.value = p ? (won.value ? '0' : fmt(Number(p.amount))) : '0'
})
// 中签状态变化：未中签默认全额返款；中签默认不返款
watch(won, (v) => {
  refund.value = v ? '0' : fmt(subscribeAmount.value)
})
// 切换证券账户后清空已选申购
watch(securityAccountId, () => {
  selectedTxnId.value = null
})

async function submit() {
  if (!selectedTxnId.value) {
    ElMessage.warning('请选择申购证券')
    return
  }
  const lid = ledgerStore.currentId as number
  const r = Number(refund.value || 0)
  if (r < 0 || r > subscribeAmount.value) {
    ElMessage.warning('申购返款金额不合法')
    return
  }
  await api.ipoConfirm(lid, {
    txn_id: selectedTxnId.value,
    won: won.value,
    refund_amount: r,
    occurred_at: occurredAt.value + 'T00:00:00',
    remark: remark.value || null,
    tag_ids: tagIds.value,
  })
  ElMessage.success(won.value ? '中签买入已记录' : '申购返款已记录')
  ipoStore.markSaved()
}

watch(
  () => ipoStore.visible,
  (v) => {
    if (v) loadMeta().then(reset)
  }
)
</script>

<template>
  <el-dialog
    v-model="ipoStore.visible"
    title="中签确认"
    width="92%"
    style="max-width:760px"
    :close-on-click-modal="false"
  >
    <el-form label-width="90px" class="ipo-form">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="证券账户" required>
            <el-select v-model="securityAccountId" placeholder="选择证券账户" style="width:100%">
              <el-option v-for="a in securityAccounts" :key="a.id" :label="a.name" :value="a.id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="申购证券" required>
            <el-select
              v-model="selectedTxnId"
              placeholder="选择已申购的证券"
              style="width:100%"
              no-data-text="无待确认的申购"
            >
              <el-option
                v-for="p in pendingForAccount"
                :key="p.txn_id"
                :label="`${p.symbol} ${p.name}`"
                :value="p.txn_id"
              />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="资金账户">
            <el-input :model-value="fundingAccountName" disabled />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="申购金">
            <el-input :model-value="fmt(subscribeAmount)" disabled />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label=" ">
            <el-checkbox v-model="won">中签</el-checkbox>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="申购返款">
            <el-input v-model="refund" type="number" placeholder="0.00" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="标签">
            <el-select v-model="tagIds" multiple filterable placeholder="选择标签" style="width:100%">
              <el-option v-for="t in tags" :key="t.id" :label="tagName(t.id)" :value="t.id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="日期" required>
            <el-date-picker
              v-model="occurredAt"
              type="date"
              value-format="YYYY-MM-DD"
              style="width:100%"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="24">
          <el-form-item label="备注">
            <el-input v-model="remark" type="textarea" :rows="2" placeholder="备注" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <template #footer>
      <el-button @click="ipoStore.close()">取消</el-button>
      <el-button type="primary" @click="submit">确定</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.ipo-form :deep(.el-input.is-disabled .el-input__inner) {
  color: #333;
}
</style>
