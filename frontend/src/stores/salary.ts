import { defineStore } from 'pinia'

interface SalaryState {
  visible: boolean
  savedAt: number
}

export const useSalaryStore = defineStore('salary', {
  state: (): SalaryState => ({
    visible: false,
    savedAt: 0
  }),
  actions: {
    open() {
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
