import { defineStore } from 'pinia'

interface IpoState {
  visible: boolean
  presetAccountId: number | null
  savedAt: number
}

// 新股中签确认弹窗的全局状态
export const useIpoStore = defineStore('ipo', {
  state: (): IpoState => ({
    visible: false,
    presetAccountId: null,
    savedAt: 0,
  }),
  actions: {
    open(presetAccountId?: number) {
      this.presetAccountId = presetAccountId ?? null
      this.visible = true
    },
    close() {
      this.visible = false
    },
    markSaved() {
      this.savedAt = Date.now()
      this.visible = false
    },
  },
})
