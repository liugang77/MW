import axios, { type AxiosInstance } from 'axios'
import { activeLedger } from './activeLedger'
import { startLoading, stopLoading } from './loading'

const http: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 15000
})

// 每个请求带上当前账本 id，后端据此附加对应账本数据文件
http.interceptors.request.use((config) => {
  startLoading()
  const lid = activeLedger.get()
  if (lid != null) {
    config.headers = config.headers ?? {}
    config.headers['X-Ledger-Id'] = String(lid)
  }
  return config
}, (err) => {
  stopLoading()
  return Promise.reject(err)
})

http.interceptors.response.use(
  (res) => {
    stopLoading()
    return res.data
  },
  (err) => {
    stopLoading()
    const msg = err.response?.data?.detail || err.message || '请求失败'
    return Promise.reject(new Error(msg))
  }
)

export default http
