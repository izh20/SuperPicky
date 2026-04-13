<template>
  <div class="max-w-5xl mx-auto px-3 sm:px-5 py-4 sm:py-6">
    <div class="flex items-center justify-between mb-4 sm:mb-6">
      <h1 class="dark:text-text-on-dark text-lg sm:text-xl">仪表盘</h1>
      <button
        @click="store.fetchAll()"
        :disabled="store.loading"
        class="flex items-center gap-1.5 text-[14px] text-text-tertiary dark:text-text-on-dark-tertiary hover:text-text-primary dark:hover:text-text-on-dark disabled:opacity-50"
      >
        <RefreshCw class="w-4 h-4" :class="store.loading ? 'animate-spin' : ''" />
        刷新
      </button>
    </div>

    <Spinner v-if="store.loading && !store.stats" />

    <!-- 统计卡片 -->
    <div v-if="store.stats" class="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-4 sm:mb-6">
      <StatCard icon="📷" label="照片总数" :value="store.stats.photos.toLocaleString()" />
      <StatCard icon="🎬" label="视频总数" :value="store.stats.videos.toLocaleString()" />
      <StatCard icon="🐦" label="鸟种数" :value="store.stats.species.toLocaleString()" />
      <StatCard icon="⚡" label="连拍组数" :value="store.stats.bursts.toLocaleString()" />
    </div>

    <div class="grid md:grid-cols-2 gap-4 sm:gap-6">
      <!-- 系统指标 -->
      <div v-if="store.metrics" class="card-apple dark:bg-[#1c1c1e] rounded-xl p-5">
        <h2 class="font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <Cpu class="w-5 h-5 text-apple-blue" /> 系统内存
        </h2>
        <div class="space-y-2 text-sm">
          <MemBar label="系统已用" :used="store.metrics.memory.system_used_gb" :total="store.metrics.memory.system_total_gb" color="bg-blue-400" />
          <MemBar label="应用 RSS" :used="store.metrics.memory.app_used_gb" :total="store.metrics.memory.system_total_gb" color="bg-primary-500" />
        </div>
        <div class="mt-4 text-xs text-gray-400 flex gap-4">
          <span>运行任务: <strong class="text-gray-700">{{ store.metrics.tasks.running }}</strong></span>
          <span>队列任务: <strong class="text-gray-700">{{ store.metrics.tasks.queued }}</strong></span>
        </div>
      </div>

      <!-- 模型状态 -->
      <div v-if="store.metrics?.models" class="card-apple dark:bg-[#1c1c1e] rounded-xl p-5">
        <h2 class="font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <Layers class="w-5 h-5 text-apple-blue" /> AI 模型状态
        </h2>
        <div class="space-y-3">
          <div
            v-for="[name, m] in Object.entries(store.metrics.models)"
            :key="name"
            class="flex items-start gap-3 text-sm"
          >
            <div class="w-2 h-2 rounded-full mt-1.5 shrink-0" :class="m.loaded ? 'bg-green-400' : 'bg-gray-300'" />
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-medium uppercase">{{ name }}</span>
                <span v-if="m.loaded" class="text-xs text-green-600">已加载</span>
                <span v-else class="text-xs text-gray-400">未加载</span>
                <span v-if="m.last_used" class="text-xs text-gray-400">{{ formatModelTime(m.last_used) }}</span>
              </div>
              <p class="text-xs text-gray-400 mt-0.5">{{ modelDesc[name] }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 管理操作 -->
      <div class="card-apple dark:bg-[#1c1c1e] rounded-xl p-5 md:col-span-2">
        <h2 class="font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <Settings class="w-5 h-5 text-apple-blue" /> 管理操作
        </h2>
        <div class="flex flex-wrap gap-3">
          <AdminBtn @click="releaseModels" :loading="releasing" icon="🧹">
            释放空闲模型
          </AdminBtn>
          <AdminBtn @click="rescorePhotos" :loading="rescoring" icon="🔄">
            重新评分
          </AdminBtn>
          <AdminBtn @click="resetRecognition" :loading="resetting" icon="⚠️">
            重置识别
          </AdminBtn>
          <AdminBtn @click="openScan" icon="🔍">
            扫描本地目录
          </AdminBtn>
          <RouterLink to="/birds" class="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200 transition-colors">
            🐦 鸟种目录
          </RouterLink>
        </div>
      </div>

      <!-- 后台任务 -->
      <div class="card-apple dark:bg-[#1c1c1e] rounded-xl p-5 md:col-span-2">
        <div class="flex items-center justify-between gap-3 mb-4">
          <h2 class="font-semibold text-gray-700 flex items-center gap-2">
            <Layers class="w-5 h-5 text-apple-blue" /> 后台任务
          </h2>
          <div class="text-xs text-gray-400 flex gap-3">
            <span>运行中 {{ store.runningTasks }}</span>
            <span>排队中 {{ store.queuedTasks }}</span>
          </div>
        </div>

        <div v-if="store.tasks.length === 0" class="text-sm text-gray-400">
          当前没有后台任务
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="task in store.tasks"
            :key="task.id"
            class="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-black/10 p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-medium text-text-primary dark:text-text-on-dark">{{ taskTitle(task.type) }}</span>
                  <span class="px-2 py-0.5 rounded-full text-[11px]" :class="taskStatusClass(task.status)">
                    {{ taskStatusLabel(task.status) }}
                  </span>
                  <span class="text-xs text-gray-400 font-mono">{{ task.id.slice(0, 8) }}</span>
                </div>
                <div v-if="task.target_name" class="text-sm text-text-primary dark:text-text-on-dark mt-1 truncate">
                  {{ task.target_name }}
                </div>
                <div v-if="task.detail" class="text-xs text-gray-500 mt-1">
                  {{ task.detail }}
                </div>
                <div v-if="task.error_msg" class="text-xs text-red-500 mt-1 break-all">
                  {{ task.error_msg }}
                </div>
                <div class="text-xs text-gray-400 mt-1">
                  创建 {{ formatTaskTime(task.created_at) }}
                  <span v-if="task.updated_at"> · 更新 {{ formatTaskTime(task.updated_at) }}</span>
                </div>
              </div>

              <div class="shrink-0 flex gap-2">
                <button
                  v-if="task.can_retry"
                  @click="retryTask(task.id)"
                  :disabled="retryingTaskId === task.id"
                  class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {{ retryingTaskId === task.id ? '重试中…' : '一键重试' }}
                </button>
                <button
                  v-if="task.can_cancel"
                  @click="stopTask(task.id)"
                  :disabled="cancelingTaskId === task.id"
                  class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm bg-red-50 text-red-600 hover:bg-red-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {{ cancelingTaskId === task.id ? '停止中…' : '停止任务' }}
                </button>
              </div>
            </div>

            <div class="mt-3">
              <div class="flex justify-between text-xs text-gray-500 mb-1">
                <span>{{ task.progress }}%</span>
                <span>{{ task.status === 'running' ? '执行中' : task.status === 'pending' ? '排队中' : '已结束' }}</span>
              </div>
              <div class="h-2 bg-gray-100 rounded-full overflow-hidden dark:bg-white/10">
                <div
                  class="h-full rounded-full transition-all duration-300"
                  :class="taskProgressClass(task.status)"
                  :style="{ width: `${Math.max(0, Math.min(task.progress ?? 0, 100))}%` }"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, defineComponent, h } from 'vue'
import { RefreshCw, Cpu, Layers, Settings } from 'lucide-vue-next'
import { useDashboardStore } from '@/stores/dashboardStore'
import { useToastStore } from '@/stores/toastStore'
import { photoAPI } from '@/api/photos'
import Spinner from '@/components/common/Spinner.vue'
import type { AdminTaskSummary } from '@/types'

const store = useDashboardStore()
const toast = useToastStore()
const releasing = ref(false)
const rescoring = ref(false)
const resetting = ref(false)
const cancelingTaskId = ref<string | null>(null)
const retryingTaskId = ref<string | null>(null)
let refreshTimer: number | null = null

const modelDesc: Record<string, string> = {
  yolo: 'YOLO11L-seg 目标检测 — 定位画面中的鸟并裁剪',
  osea: 'OSEA ResNet34 鸟种分类 — 识别裁剪区域的鸟种',
  keypoint: 'ResNet50 关键点检测 — 检测鸟头/眼位置，计算锐度',
  topiq: 'CFANet 美学评分 — 评估画质与构图（1-10 分）',
}

onMounted(async () => {
  await store.fetchAll()
  refreshTimer = window.setInterval(() => {
    store.fetchAll()
  }, 5000)
})

onUnmounted(() => {
  if (refreshTimer != null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
})

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

async function rescorePhotos() {
  rescoring.value = true
  try {
    const res = await photoAPI.rescore()
    if (res.total === 0) {
      toast.success('所有照片评分已完整，无需重新评分')
    } else {
      toast.success(`正在重新评分 ${res.total} 张照片`)
    }
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    rescoring.value = false
  }
}

function openScan() {
  window.location.href = '/upload'
}

async function resetRecognition() {
  if (!confirm('确认重置所有照片的识别结果？\n\n此操作将清除所有鸟种识别和评分数据，不可撤销。')) return
  resetting.value = true
  try {
    const res = await photoAPI.resetRecognition()
    toast.success(`已重置：清除 ${res.deleted_birds} 条鸟种记录，${res.deleted_scores} 条评分记录`)
    store.fetchAll()
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    resetting.value = false
  }
}

async function stopTask(taskId: string) {
  if (!confirm('确认停止这个后台任务？')) return
  cancelingTaskId.value = taskId
  try {
    const res = await store.cancelTask(taskId)
    toast.success('任务已停止')
    return res
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    cancelingTaskId.value = null
  }
}

async function retryTask(taskId: string) {
  retryingTaskId.value = taskId
  try {
    const res = await store.retryTask(taskId)
    if (res?.task_id) {
      toast.success('已重新提交后台任务')
    } else {
      toast.success('无需重试，当前没有待处理内容')
    }
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    retryingTaskId.value = null
  }
}

function parseBackendDate(raw: string | null | undefined) {
  if (!raw) return null
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw) ? raw : `${raw}Z`
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatBackendTime(raw: string | null | undefined) {
  const date = parseBackendDate(raw)
  if (!date) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date).replace(/\//g, '-')
}

function formatModelTime(iso: string | null) {
  return formatBackendTime(iso)
}

function formatTaskTime(iso: string | null | undefined) {
  return formatBackendTime(iso)
}

function taskTitle(type: AdminTaskSummary['type']) {
  return {
    analyze: '视频分析',
    'batch-analyze': '批量视频分析',
    recognize_all: '全库照片识别',
    recognize_all_bursts: '连拍全量识别',
    recognize: '批量照片识别',
    detect_bursts: '连拍检测',
    rescore: '重新评分',
    recalculate: '重新计算评分',
    batch_process: '批量处理',
    scan: '目录扫描',
    synthesize: '连拍合成',
    organize: '鸟种整理',
    find_duplicates: '重复照片检测',
  }[type] ?? type
}

function taskStatusLabel(status: AdminTaskSummary['status']) {
  return {
    running: '运行中',
    pending: '排队中',
    done: '已完成',
    error: '失败',
    cancelled: '已停止',
  }[status] ?? status
}

function taskStatusClass(status: AdminTaskSummary['status']) {
  return {
    running: 'bg-blue-50 text-blue-600',
    pending: 'bg-amber-50 text-amber-600',
    done: 'bg-emerald-50 text-emerald-600',
    error: 'bg-red-50 text-red-600',
    cancelled: 'bg-gray-100 text-gray-500',
  }[status] ?? 'bg-gray-100 text-gray-500'
}

function taskProgressClass(status: AdminTaskSummary['status']) {
  return {
    running: 'bg-blue-500',
    pending: 'bg-amber-500',
    done: 'bg-emerald-500',
    error: 'bg-red-500',
    cancelled: 'bg-gray-400',
  }[status] ?? 'bg-gray-400'
}

// 行内辅助组件
const StatCard = defineComponent({
  props: ['icon', 'label', 'value'],
  setup(p) {
    return () => h('div', { class: 'card-apple dark:bg-[#1c1c1e] rounded-xl p-4 text-center' }, [
      h('div', { class: 'text-2xl mb-1' }, p.icon),
      h('div', { class: 'text-2xl font-bold text-text-primary dark:text-text-on-dark font-display' }, p.value),
      h('div', { class: 'text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary mt-1' }, p.label),
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
      class: 'flex items-center gap-2 px-4 py-2 btn-secondary rounded-lg text-[14px] disabled:opacity-50 transition-colors',
    }, [
      h('span', {}, p.icon),
      slots.default?.(),
    ])
  },
})
</script>
