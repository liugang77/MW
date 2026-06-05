<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => String(route.meta.title || '功能'))
</script>

<template>
  <div class="page placeholder-page">
    <div class="ph-card">
      <div class="ph-icon">📄</div>
      <h2>{{ title }}</h2>
      <p>该报表功能正在开发中，敬请期待。</p>
    </div>
  </div>
</template>

<style scoped>
.placeholder-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
.ph-card {
  text-align: center;
  color: #8a98a8;
}
.ph-icon {
  font-size: 64px;
  opacity: 0.5;
  margin-bottom: 12px;
}
.ph-card h2 {
  color: #55677a;
  margin: 0 0 8px;
}
.ph-card p {
  font-size: 14px;
}
</style>
