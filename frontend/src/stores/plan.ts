import { defineStore } from 'pinia'

interface PlanState {
  visible: boolean
  savedAt: number
}

export const usePlanStore = defineStore('plan', {
  state: (): PlanState => ({
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
    }
  }
})
