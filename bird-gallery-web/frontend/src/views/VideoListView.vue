<template>
  <div class="max-w-5xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-bold text-gray-800">视频</h1>
      <div class="flex items-center gap-2">
        <!-- 选择模式 -->
        <button
          @click="toggleSelectMode"
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded transition-colors"
          :class="selectMode
            ? 'bg-primary-100 text-primary-700 border border-primary-300'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
        >
          <CheckSquare class="w-4 h-4" />
          {{ selectMode ? '退出选择' : '选择' }}
        </button>
        <template v-if="selectMode">
          <button
            @click="selectAll"
            class="flex items-center gap-1 px-2 py-1.5 text-xs text-gray-600 hover:text-primary-600"
          >
            {{ selected.size === videoStore.list.length ? '取消全选' : '全选' }}
          </button>
          <span v-if="selected.size > 0" class="text-xs text-gray-500">已选 {{ selected.size }} 个</span>
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
          class="flex items-center gap-1.5 px-3 py-1.5 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 transition-colors"
        >
          <Upload class="w-4 h-4" /> 上传视频
        </RouterLink>
        <button
          @click="batchAnalyze"
          :disabled="batchAnalyzing"
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors"
          :class="batchAnalyzing
            ? 'bg-blue-100 text-blue-700 border border-blue-300 cursor-wait'
            : 'bg-blue-600 text-white hover:bg-blue-700'"
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
    <div v-else class="grid gap-4" style="grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));">
      <div
        v-for="v in videoStore.list"
        :key="v.id"
        class="bg-white rounded-xl overflow-hidden border border-gray-100 hover:shadow-md transition-shadow cursor-pointer relative"
        @click="onCardClick(v.id)"
      >
        <!-- 选择复选框 -->
        <div
          v-if="selectMode"
          class="absolute top-2 left-2 z-10"
          @click.stop="toggleSelect(v.id)"
        >
          <div
            class="w-5 h-5 rounded border-2 flex items-center justify-center transition-colors"
            :class="selected.has(v.id) ? 'bg-primary-600 border-primary-600' : 'bg-white/80 border-gray-300'"
          >
            <Check v-if="selected.has(v.id)" class="w-3 h-3 text-white" />
          </div>
        </div>
        <!-- 封面 -->
        <div class="aspect-video bg-gray-900 flex items-center justify-center text-gray-500 overflow-hidden relative">
          <img
            :src="videoAPI.thumbnailUrl(v.id)"
            class="w-full h-full object-cover"
            loading="lazy"
            @error="(e: Event) => (e.target as HTMLImageElement).style.display = 'none'"
          />
          <Video class="w-10 h-10 opacity-30 absolute" />
        </div>
        <div class="p-3">
          <p class="font-medium text-sm truncate">{{ v.filename }}</p>
          <div class="flex items-center gap-2 mt-1 text-xs text-gray-500">
            <span v-if="v.duration_seconds">{{ formatDuration(v.duration_seconds) }}</span>
            <span v-if="v.width && v.height">{{ v.width }}×{{ v.height }}</span>
            <span
              class="ml-auto px-1.5 py-0.5 rounded text-white text-xs"
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
import { Upload, Video, CheckSquare, Trash2, Check, Scan } from 'lucide-vue-next'
import { useVideoStore } from '@/stores/videoStore'
import { useToastStore } from '@/stores/toastStore'
import { useAuthStore } from '@/stores/authStore'
import { videoAPI } from '@/api/videos'
import { taskAPI } from '@/api/admin'
import Spinner from '@/components/common/Spinner.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const router = useRouter()
const videoStore = useVideoStore()
const toast = useToastStore()
const authStore = useAuthStore()
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
  try {
    const res = await videoAPI.batchAnalyze()
    if (!res.task_id) {
      toast.success(res.message ?? '没有可分析的视频')
      return
    }
    toast.success(`开始分析 ${res.total} 个视频`)
    // 轮询进度
    await new Promise<void>((resolve, reject) => {
      const tick = async () => {
        try {
          const task = await taskAPI.get(res.task_id)
          batchProgress.value = task.progress ?? 0
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
  return { done: 'bg-green-500', analyzing: 'bg-blue-500', processing: 'bg-blue-500', error: 'bg-red-500', transcoding: 'bg-yellow-500', ready: 'bg-gray-500', uploaded: 'bg-gray-400' }[s] ?? 'bg-gray-400'
}
</script>
