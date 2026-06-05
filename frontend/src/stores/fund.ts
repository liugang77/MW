import { defineStore } from 'pinia'

interface FundState {
  visible: boolean
  mode: 'buy' | 'redeem'
  savedAt: number
  presetAccountId: number | null
}

export const useFundStore = defineStore('fund', {
  state: (): FundState => ({
    visible: false,
    mode: 'buy',
    savedAt: 0,
    presetAccountId: null
  }),
  actions: {
    open(mode: 'buy' | 'redeem' = 'buy', presetAccountId?: number) {
      this.mode = mode
      this.presetAccountId = presetAccountId ?? null
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
