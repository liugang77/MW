import { createApp } from 'vue'
import { watch } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import './styles.css'
import { useLedgerStore } from './stores/ledger'
import { activeLedger } from './api/activeLedger'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)

// 同步当前账本 id 到 http 拦截器（用于 X-Ledger-Id 头部）
const ledgerStore = useLedgerStore()
activeLedger.set(ledgerStore.currentId)
watch(() => ledgerStore.currentId, (v) => activeLedger.set(v))

app.mount('#app')
