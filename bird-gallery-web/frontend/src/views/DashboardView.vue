<template>
  <div class="max-w-5xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-bold text-gray-800">仪表盘</h1>
      <button
        @click="store.fetchAll()"
        :disabled="store.loading"
        class="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 disabled:opacity-50"
      >
        <RefreshCw class="w-4 h-4" :class="store.loading ? 'animate-spin' : ''" />
        刷新
      </button>
    </div>

    <Spinner v-if="store.loading && !store.stats" />

    <!-- 统计卡片 -->
    <div v-if="store.stats" class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <StatCard icon="📷" label="照片总数" :value="store.stats.photos.toLocaleString()" />
      <StatCard icon="🎬" label="视频总数" :value="store.stats.videos.toLocaleString()" />
      <StatCard icon="🐦" label="鸟种数" :value="store.stats.species.toLocaleString()" />
      <StatCard icon="⚡" label="连拍组数" :value="store.stats.bursts.toLocaleString()" />
    </div>

    <div class="grid md:grid-cols-2 gap-6">
      <!-- 系统指标 -->
      <div v-if="store.metrics" class="bg-white rounded-xl p-5 border border-gray-100">
        <h2 class="font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <Cpu class="w-5 h-5 text-primary-600" /> 系统内存
        </h2>
        <div class="space-y-2 text-sm">
          <MemBar label="系统总量" :used="store.metrics.memory.system_total_gb" :total="store.metrics.memory.system_total_gb" color="bg-gray-200" />
          <MemBar label="系统已用" :used="store.metrics.memory.system_used_gb" :total="store.metrics.memory.system_total_gb" color="bg-blue-400" />
          <MemBar label="应用 RSS" :used="store.metrics.memory.app_used_gb" :total="store.metrics.memory.system_total_gb" color="bg-primary-500" />
        </div>
        <div class="mt-4 text-xs text-gray-400 flex gap-4">
          <span>运行任务: <strong class="text-gray-700">{{ store.metrics.tasks.running }}</strong></span>
          <span>队列任务: <strong class="text-gray-700">{{ store.metrics.tasks.queued }}</strong></span>
        </div>
      </div>

      <!-- 模型状态 -->
      <div v-if="store.metrics?.models" class="bg-white rounded-xl p-5 border border-gray-100">
        <h2 class="font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <Layers class="w-5 h-5 text-primary-600" /> AI 模型状态
        </h2>
        <div class="space-y-2">
          <div
            v-for="[name, m] in Object.entries(store.metrics.models)"
            :key="name"
            class="flex items-center gap-3 text-sm"
          >
            <div class="w-2 h-2 rounded-full" :class="m.loaded ? 'bg-green-400' : 'bg-gray-300'" />
            <span class="flex-1 font-medium uppercase">{{ name }}</span>
            <span class="text-xs text-gray-400">{{ m.loaded ? `${((m.memory_mb ?? 0) / 1024).toFixed(2)} GB` : '未加载' }}</span>
          </div>
        </div>
      </div>

      <!-- 管理操作 -->
      <div class="bg-white rounded-xl p-5 border border-gray-100 md:col-span-2">
        <h2 class="font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <Settings class="w-5 h-5 text-primary-600" /> 管理操作
        </h2>
        <div class="flex flex-wrap gap-3">
          <AdminBtn @click="releaseModels" :loading="releasing" icon="🧹">
            释放空闲模型
          </AdminBtn>
          <AdminBtn @click="openScan" icon="🔍">
            扫描本地目录
          </AdminBtn>
          <RouterLink to="/birds" class="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200 transition-colors">
            🐦 鸟种目录
          </RouterLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, defineComponent, h } from 'vue'
import { RefreshCw, Cpu, Layers, Settings } from 'lucide-vue-next'
import { useDashboardStore } from '@/stores/dashboardStore'
import { useToastStore } from '@/stores/toastStore'
import Spinner from '@/components/common/Spinner.vue'

const store = useDashboardStore()
const toast = useToastStore()
const releasing = ref(false)

onMounted(() => store.fetchAll())

async function releaseModels() {
  releasing.value = true
  try {
    await store.releaseModels()
    toast.success('已释放空闲模型')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    releasing.value = false
  }
}

function openScan() {
  window.location.href = '/upload'
}

// 行内辅助组件
const StatCard = defineComponent({
  props: ['icon', 'label', 'value'],
  setup(p) {
    return () => h('div', { class: 'bg-white rounded-xl p-4 border border-gray-100 text-center' }, [
      h('div', { class: 'text-2xl mb-1' }, p.icon),
      h('div', { class: 'text-2xl font-bold text-gray-800' }, p.value),
      h('div', { class: 'text-xs text-gray-500 mt-1' }, p.label),
    ])
  },
})

const MemBar = defineComponent({
  props: ['label', 'used', 'total', 'color'],
  setup(p) {
    return () => h('div', {}, [
      h('div', { class: 'flex justify-between text-xs text-gray-500 mb-0.5' }, [
        h('span', {}, p.label),
        h('span', {}, `${p.used.toFixed(1)} / ${p.total.toFixed(1)} GB`),
      ]),
      h('div', { class: 'h-2 bg-gray-100 rounded-full overflow-hidden' }, [
        h('div', {
          class: `h-full ${p.color} rounded-full transition-all duration-500`,
          style: { width: `${Math.min((p.used / p.total) * 100, 100).toFixed(1)}%` },
        }),
      ]),
    ])
  },
})

const AdminBtn = defineComponent({
  props: ['loading', 'icon'],
  emits: ['click'],
  setup(p, { emit, slots }) {
    return () => h('button', {
      onClick: () => emit('click'),
      disabled: p.loading,
      class: 'flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200 disabled:opacity-50 transition-colors',
    }, [
      h('span', {}, p.icon),
      slots.default?.(),
    ])
  },
})
</script>
