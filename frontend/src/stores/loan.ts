import { defineStore } from 'pinia'

interface LoanState {
  visible: boolean
  direction: 'payable' | 'receivable'
  savedAt: number
}

export const useLoanStore = defineStore('loan', {
  state: (): LoanState => ({
    visible: false,
    direction: 'payable',
    savedAt: 0
  }),
  actions: {
    open(direction: 'payable' | 'receivable' = 'payable') {
      this.direction = direction
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
