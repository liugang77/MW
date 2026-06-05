// 当前账本 id 的轻量持有者：供 http 拦截器读取、ledger store 写入，避免循环依赖
let current: number | null = null

export const activeLedger = {
  get: (): number | null => current,
  set: (v: number | null): void => {
    current = v
  }
}
