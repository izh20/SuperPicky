<template>
  <div class="max-w-5xl mx-auto px-3 sm:px-6 py-4 sm:py-6">
    <div class="flex flex-wrap items-center justify-between gap-3 mb-5 sm:mb-8">
      <div>
        <h1 class="text-2xl sm:text-[28px] font-semibold text-text-primary dark:text-text-on-dark font-display" style="line-height: 1.14; letter-spacing: 0.196px;">视频</h1>
        <p v-if="videoStore.list.length" class="text-[14px] text-text-tertiary dark:text-text-on-dark-tertiary mt-1" style="letter-spacing: -0.224px;">{{ videoStore.list.length }} 个视频</p>
      </div>
      <div class="flex items-center gap-2 flex-wrap">
        <!-- 选择模式 -->
        <button
          @click="toggleSelectMode"
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors"
          :class="selectMode
            ? 'bg-apple-blue/10 text-apple-blue'
            : 'text-text-tertiary dark:text-text-on-dark-tertiary hover:bg-black/5 dark:hover:bg-white/10'"
        >
          <CheckSquare class="w-4 h-4" />
          {{ selectMode ? '退出选择' : '选择' }}
        </button>
        <template v-if="selectMode">
          <button
            @click="selectAll"
            class="flex items-center gap-1 px-2 py-1.5 text-xs text-text-secondary dark:text-text-on-dark-secondary hover:text-apple-blue"
          >
            {{ selected.size === videoStore.list.length ? '取消全选' : '全选' }}
          </button>
          <span v-if="selected.size > 0" class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary">已选 {{ selected.size }} 个</span>
          <button
            v-if="selected.size > 0 && authStore.isAdmin"
            @click="batchDelete"
            :disabled="deleting"
            class="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 text-white text-sm rounded hover:bg-red-700 disabled:opacity-50 transition-colors"
          >
            <Trash2 class="w-4 h-4" />
            {{ deleting ? '删除中…' : `删除 (${selected.size})` }}
          </button>
        </template>
        <RouterLink
          to="/upload"
          class="flex items-center gap-1.5 px-4 py-1.5 bg-text-primary dark:bg-white text-white dark:text-black text-[14px] rounded-full hover:opacity-90 transition-all shadow-sm"
          style="letter-spacing: -0.224px;"
        >
          <Upload class="w-4 h-4" /> 上传
        </RouterLink>
        <button
          @click="batchAnalyze"
          :disabled="batchAnalyzing"
          class="flex items-center gap-1.5 px-4 py-1.5 text-[14px] rounded-full transition-all shadow-sm"
          :class="batchAnalyzing
            ? 'bg-apple-blue/10 text-apple-blue cursor-wait'
            : 'bg-apple-blue text-white hover:brightness-110'"
          style="letter-spacing: -0.224px;"
        >
          <Scan class="w-4 h-4" :class="{ 'animate-spin': batchAnalyzing }" />
          {{ batchAnalyzing ? `分析中 ${batchProgress}%` : '一键分析全部' }}
        </button>
      </div>
    </div>

    <Spinner v-if="videoStore.loading" />
    <EmptyState
      v-else-if="!videoStore.list.length"
      title="暂无视频"
      description="上传视频文件后可在此查看和分析"
      :icon="Video"
    />
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
      <div
        v-for="v in videoStore.list"
        :key="v.id"
        class="video-card group relative cursor-pointer rounded-xl overflow-hidden bg-white dark:bg-[#1c1c1e]"
        @click="onCardClick(v.id)"
      >
        <!-- 选择复选框 -->
        <div
          v-if="selectMode"
          class="absolute top-3 left-3 z-20"
          @click.stop="toggleSelect(v.id)"
        >
          <div
            class="w-6 h-6 rounded-full flex items-center justify-center transition-all duration-200"
            :class="selected.has(v.id) ? 'bg-apple-blue shadow-lg scale-110' : 'bg-black/30 backdrop-blur-sm hover:bg-black/50'"
          >
            <svg v-if="selected.has(v.id)" class="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
        </div>
        <!-- 封面 -->
        <div class="aspect-video bg-black flex items-center justify-center overflow-hidden relative">
          <img
            :src="videoAPI.thumbnailUrl(v.id)"
            class="w-full h-full object-cover transition-transform duration-500 ease-out group-hover:scale-105"
            loading="lazy"
            @error="(e: Event) => (e.target as HTMLImageElement).style.display = 'none'"
          />
          <Video class="w-10 h-10 opacity-20 absolute pointer-events-none" />
          <!-- 播放按钮 overlay -->
          <div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300">
            <div class="w-12 h-12 rounded-full bg-white/90 flex items-center justify-center shadow-lg">
              <svg class="w-5 h-5 text-text-primary ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z"/>
              </svg>
            </div>
          </div>
          <!-- 时长标签 -->
          <span v-if="v.duration_seconds" class="absolute bottom-2 right-2 px-1.5 py-0.5 rounded bg-black/60 text-[11px] text-white font-medium backdrop-blur-sm">
            {{ formatDuration(v.duration_seconds) }}
          </span>
        </div>
        <!-- 信息区 -->
        <div class="px-3.5 py-3">
          <p class="text-[14px] font-semibold truncate text-text-primary dark:text-text-on-dark" style="letter-spacing: -0.224px;">{{ v.filename }}</p>
          <div class="flex items-center gap-2 mt-1 text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary" style="letter-spacing: -0.12px;">
            <span v-if="v.width && v.height">{{ v.width }}×{{ v.height }}</span>
            <span
              class="ml-auto px-2 py-0.5 rounded-full text-white text-[11px] font-medium"
              :class="statusClass(v.status)"
            >{{ statusLabel(v.status) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Upload, Video, CheckSquare, Trash2, Scan } from 'lucide-vue-next'
import { useVideoStore } from '@/stores/videoStore'
import { useToastStore } from '@/stores/toastStore'
import { useAuthStore } from '@/stores/authStore'
import { useTaskStore } from '@/stores/taskStore'
import { videoAPI } from '@/api/videos'
import { taskAPI } from '@/api/admin'
import Spinner from '@/components/common/Spinner.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const router = useRouter()
const videoStore = useVideoStore()
const toast = useToastStore()
const authStore = useAuthStore()
const taskStore = useTaskStore()
const selectMode = ref(false)
const selected = ref<Set<string>>(new Set())
const deleting = ref(false)
const batchAnalyzing = ref(false)
const batchProgress = ref(0)

onMounted(() => videoStore.fetchList())

function onCardClick(id: string) {
  if (selectMode.value) {
    toggleSelect(id)
  } else {
    router.push(`/videos/${id}`)
  }
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) {
    selected.value = new Set()
  }
}

function toggleSelect(id: string) {
  const s = new Set(selected.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selected.value = s
}

function selectAll() {
  if (selected.value.size === videoStore.list.length) {
    selected.value = new Set()
  } else {
    selected.value = new Set(videoStore.list.map(v => v.id))
  }
}

async function batchDelete() {
  const ids = [...selected.value]
  if (!confirm(`确认删除选中的 ${ids.length} 个视频？此操作不可撤销。`)) return
  deleting.value = true
  try {
    await videoAPI.batchDelete(ids)
    toast.success(`已删除 ${ids.length} 个视频`)
    selected.value = new Set()
    selectMode.value = false
    await videoStore.fetchList()
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    deleting.value = false
  }
}

async function batchAnalyze() {
  if (!confirm('确认分析全部视频？这可能需要较长时间。')) return
  batchAnalyzing.value = true
  batchProgress.value = 0
  taskStore.setActiveTask('正在分析全部视频', 0)
  try {
    const res = await videoAPI.batchAnalyze()
    if (!res.task_id) {
      toast.success('没有可分析的视频')
      return
    }
    toast.success(`开始分析 ${res.total} 个视频`)
    // 轮询进度
    await new Promise<void>((resolve, reject) => {
      const tick = async () => {
        try {
          const task = await taskAPI.get(res.task_id)
          batchProgress.value = task.progress ?? 0
          taskStore.setActiveTask(`正在分析视频 (${res.total}个)`, task.progress ?? 0)
          if (task.status === 'done') {
            await videoStore.fetchList()
            toast.success('全部视频分析完成')
            return resolve()
          }
          if (task.status === 'error') {
            toast.error(task.error_msg || '分析失败')
            return resolve()
          }
          setTimeout(tick, 2000)
        } catch (e) { reject(e) }
      }
      tick()
    })
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    batchAnalyzing.value = false
    taskStore.clearActiveTask()
    await videoStore.fetchList()
  }
}

function formatDuration(s: number) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function statusLabel(s: string) {
  return { uploaded: '已上传', transcoding: '转码中', ready: '就绪', analyzing: '分析中', processing: '分析中', done: '完成', error: '错误' }[s] ?? s
}

function statusClass(s: string) {
  return { done: 'bg-green-500', analyzing: 'bg-apple-blue', processing: 'bg-apple-blue', error: 'bg-red-500', transcoding: 'bg-amber-500', ready: 'bg-text-tertiary', uploaded: 'bg-text-tertiary' }[s] ?? 'bg-text-tertiary'
}
</script>

<style scoped>
.video-card {
  transition: transform 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94),
              box-shadow 0.3s ease;
}
.video-card:hover {
  transform: translateY(-3px);
  box-shadow: rgba(0, 0, 0, 0.12) 0px 8px 30px 0px;
}
</style>
