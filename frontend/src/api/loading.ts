import { ref } from 'vue'

// 全局请求计数：>0 表示有正在进行的网络请求
const pending = ref(0)

// 对外暴露的可见状态（带防抖，避免连续请求间隙闪烁）
export const isLoading = ref(false)

// 延迟显示：请求很快完成则完全不显示遮罩
const SHOW_DELAY = 180
// 最短显示时长：一旦显示，至少保持这么久，避免一闪而过
const MIN_VISIBLE = 350

let showTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null
let shownAt = 0

function clearShowTimer() {
  if (showTimer != null) { clearTimeout(showTimer); showTimer = null }
}
function clearHideTimer() {
  if (hideTimer != null) { clearTimeout(hideTimer); hideTimer = null }
}

function scheduleShow() {
  if (isLoading.value || showTimer != null) return
  showTimer = setTimeout(() => {
    showTimer = null
    isLoading.value = true
    shownAt = Date.now()
  }, SHOW_DELAY)
}

function scheduleHide() {
  // 还有未完成请求，不隐藏
  if (pending.value > 0) return
  // 尚未真正显示（仍在延迟窗口内）：直接取消，不显示
  clearShowTimer()
  if (!isLoading.value) return
  const elapsed = Date.now() - shownAt
  const wait = Math.max(MIN_VISIBLE - elapsed, 0)
  clearHideTimer()
  hideTimer = setTimeout(() => {
    hideTimer = null
    if (pending.value === 0) isLoading.value = false
  }, wait)
}

export function startLoading() {
  pending.value++
  clearHideTimer()
  scheduleShow()
}

export function stopLoading() {
  if (pending.value > 0) pending.value--
  if (pending.value === 0) scheduleHide()
}
