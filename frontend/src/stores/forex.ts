import { defineStore } from 'pinia'

export interface ForexEditTxn {
  id: number
  buy_currency: string
  buy_amount: number
  rate: number
  funding_account_id: number | null
  occurred_at: string | null
  remark: string | null
  tag_ids?: number[]
}

interface ForexState {
  visible: boolean
  savedAt: number
  presetAccountId: number | null
  editTxn: ForexEditTxn | null
}

export const useForexStore = defineStore('forex', {
  state: (): ForexState => ({
    visible: false,
    savedAt: 0,
    presetAccountId: null,
    editTxn: null
  }),
  actions: {
    open(presetAccountId?: number) {
      this.presetAccountId = presetAccountId ?? null
      this.editTxn = null
      this.visible = true
    },
    openEdit(presetAccountId: number, editTxn: ForexEditTxn) {
      this.presetAccountId = presetAccountId
      this.editTxn = editTxn
      this.visible = true
    },
    close() {
      this.visible = false
    },
    markSaved() {
      this.savedAt = Date.now()
      this.visible = false
    }
  }
})
