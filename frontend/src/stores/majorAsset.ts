import { defineStore } from 'pinia'

interface MajorAssetState {
  visible: boolean
  // 预设资产性质（图2 入口：房产/汽车 = 自用，其它 = 投资）
  presetNature: 'invest' | 'own'
  savedAt: number
}

export const useMajorAssetStore = defineStore('majorAsset', {
  state: (): MajorAssetState => ({
    visible: false,
    presetNature: 'invest',
    savedAt: 0
  }),
  actions: {
    open(nature: 'invest' | 'own' = 'invest') {
      this.presetNature = nature
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
