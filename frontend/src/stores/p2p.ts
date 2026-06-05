import { defineStore } from 'pinia'
import type { Loan } from '../types'

export interface CollectEdit {
  group: string
  loanId: number
  principal: number
  interest: number
  incomeAccountId: number | null
  occurredAt: string | null
  remark: string | null
  tagIds?: number[]
}

interface P2pState {
  visible: boolean
  mode: 'lend' | 'collect'
  savedAt: number
  presetAccountId: number | null
  presetLoanId: number | null
  editLoan: Loan | null
  editCollect: CollectEdit | null
}

export const useP2pStore = defineStore('p2p', {
  state: (): P2pState => ({
    visible: false,
    mode: 'lend',
    savedAt: 0,
    presetAccountId: null,
    presetLoanId: null,
    editLoan: null,
    editCollect: null
  }),
  actions: {
    open(mode: 'lend' | 'collect' = 'lend', presetAccountId?: number, presetLoanId?: number) {
      this.mode = mode
      this.presetAccountId = presetAccountId ?? null
      this.presetLoanId = presetLoanId ?? null
      this.editLoan = null
      this.editCollect = null
      this.visible = true
    },
    openEditLend(loan: Loan) {
      this.mode = 'lend'
      this.presetAccountId = loan.account_id ?? null
      this.presetLoanId = null
      this.editLoan = loan
      this.editCollect = null
      this.visible = true
    },
    openEditCollect(edit: CollectEdit) {
      this.mode = 'collect'
      this.presetAccountId = null
      this.presetLoanId = edit.loanId
      this.editLoan = null
      this.editCollect = edit
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
