import { ref, onMounted, onUnmounted } from 'vue'

/**
 * 响应式断点工具：监听窗口宽度变化，提供手机 / 平板判断。
 * - isMobile：窗口宽度 ≤ 768px（手机）
 * - isTablet：769px ~ 1024px（iPad 等中等屏幕）
 */
export function useMediaQuery() {
  const width = ref(typeof window !== 'undefined' ? window.innerWidth : 1280)
  const isMobile = ref(width.value <= 768)
  const isTablet = ref(width.value > 768 && width.value <= 1024)

  function update() {
    width.value = window.innerWidth
    isMobile.value = width.value <= 768
    isTablet.value = width.value > 768 && width.value <= 1024
  }

  onMounted(() => {
    update()
    window.addEventListener('resize', update)
  })
  onUnmounted(() => {
    window.removeEventListener('resize', update)
  })

  return { width, isMobile, isTablet }
}
