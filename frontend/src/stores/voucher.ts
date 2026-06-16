import { defineStore } from 'pinia'

interface VoucherState {
  // 触发「购券」对话框的计数器（在团购券页面监听变化打开弹窗）
  buyTick: number
  presetAccountId: number | null
  // 购券/核销/退券保存后的时间戳，供侧栏刷新余额
  savedAt: number
}

export const useVoucherStore = defineStore('voucher', {
  state: (): VoucherState => ({
    buyTick: 0,
    presetAccountId: null,
    savedAt: 0
  }),
  actions: {
    open(accountId?: number) {
      this.presetAccountId = accountId ?? null
      this.buyTick += 1
    },
    markSaved() {
      this.savedAt = Date.now()
    }
  }
})
