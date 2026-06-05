import { defineStore } from 'pinia'
import { api } from '../api'
import { activeLedger } from '../api/activeLedger'
import type { Ledger } from '../types'

interface LedgerState {
  ledgers: Ledger[]
  currentId: number | null
}

export const useLedgerStore = defineStore('ledger', {
  state: (): LedgerState => ({
    ledgers: [],
    currentId: null
  }),
  getters: {
    current: (s): Ledger | null => s.ledgers.find((l) => l.id === s.currentId) || null
  },
  actions: {
    setCurrent(id: number | null) {
      this.currentId = id
      activeLedger.set(id)
    },
    async load() {
      this.ledgers = await api.listLedgers()
      if (!this.currentId && this.ledgers.length) {
        const def = this.ledgers.find((l) => l.is_default) || this.ledgers[0]
        this.setCurrent(def.id)
      }
    }
  }
})
