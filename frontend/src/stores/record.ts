import { defineStore } from 'pinia'
import type { Transaction } from '../types'

interface RecordState {
  visible: boolean
  accountId: number | null
  template: string
  editing: Transaction | null
  savedAt: number // 记账成功后更新，供列表页监听刷新
}

export const useRecordStore = defineStore('record', {
  state: (): RecordState => ({
    visible: false,
    accountId: null,
    template: '',
    editing: null,
    savedAt: 0
  }),
  actions: {
    open(opts: { accountId?: number | null; template?: string } = {}) {
      this.editing = null
      this.accountId = opts.accountId ?? null
      this.template = opts.template ?? ''
      this.visible = true
    },
    edit(txn: Transaction) {
      this.editing = txn
      this.accountId = txn.account_id ?? null
      this.template = ''
      this.visible = true
    },
    close() {
      this.visible = false
      this.editing = null
    },
    markSaved() {
      this.savedAt = Date.now()
      this.visible = false
      this.editing = null
    }
  }
})
