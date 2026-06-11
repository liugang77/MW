import { defineStore } from 'pinia'

export interface TradeEditTxn {
  id: number
  symbol: string | null
  name: string | null
  account_id: number              // 资金账户（流水 account_id）
  security_account_id?: number    // 证券/投资账户（持仓所在）；缺省时同 account_id
  price: number | null
  quantity: number | null
  fee_total: number | null
  commission: number | null
  occurred_at: string | null
  remark: string | null
  tag_ids?: number[]
  currency?: string | null        // 理财外币申购：币种
  exchange_rate?: number | null   // 理财外币申购：申购时汇率
}

interface TradeState {
  visible: boolean
  mode: 'buy' | 'sell'
  ipo: boolean
  savedAt: number
  presetAccountId: number | null
  editTxn: TradeEditTxn | null
}

export const useTradeStore = defineStore('trade', {
  state: (): TradeState => ({
    visible: false,
    mode: 'buy',
    ipo: false,
    savedAt: 0,
    presetAccountId: null,
    editTxn: null
  }),
  actions: {
    open(mode: 'buy' | 'sell', presetAccountId?: number, opts?: { ipo?: boolean }) {
      this.mode = mode
      this.ipo = opts?.ipo ?? false
      this.presetAccountId = presetAccountId ?? null
      this.editTxn = null
      this.visible = true
    },
    openEdit(mode: 'buy' | 'sell', editTxn: TradeEditTxn) {
      this.mode = mode
      this.ipo = false
      this.presetAccountId = editTxn.security_account_id ?? editTxn.account_id
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
