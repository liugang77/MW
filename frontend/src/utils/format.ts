// 通用格式化工具：金额、数值、日期、币种。
// 金额统一使用千分位分隔（与财智8 显示一致，如 553,833.90）。

type Numish = string | number | null | undefined

const toNumber = (v: Numish): number => Number(v ?? 0) || 0

/** 金额：千分位 + 两位小数（如 1,234,567.89）。 */
export function fmtMoney(v: Numish): string {
  return toNumber(v).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/** 数值：千分位 + 指定小数位（默认 4 位，用于价格/净值/份额）。 */
export function fmtNum(v: Numish, digits = 4): string {
  return toNumber(v).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/** 百分比：保留两位小数（不含 % 号）。 */
export function fmtPct(v: Numish): string {
  return toNumber(v).toFixed(2)
}

/** 日期：截取 ISO 字符串到 YYYY-MM-DD。 */
export function fmtDate(v: string | null | undefined): string {
  return (v || '').slice(0, 10)
}

const CURRENCY_NAMES: Record<string, string> = {
  CNY: '人民币',
  USD: '美元',
  HKD: '港币',
  EUR: '欧元',
  GBP: '英镑',
  JPY: '日元',
}

/** 币种代码 → 中文名称。 */
export function currencyText(code: string | null | undefined): string {
  return CURRENCY_NAMES[code || 'CNY'] || code || '人民币'
}
