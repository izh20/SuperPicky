<template>
  <div class="max-w-3xl mx-auto px-3 sm:px-5 py-4 sm:py-6">
    <h1 class="dark:text-text-on-dark mb-4 sm:mb-6 text-lg sm:text-xl">上传照片/视频</h1>

    <!-- 拖拽区域 -->
    <div
      ref="dropZone"
      class="border-2 border-dashed rounded-xl p-6 sm:p-12 text-center transition-colors"
      :class="dragging ? 'border-apple-blue bg-apple-blue/5' : 'border-black/10 dark:border-white/10 bg-surface-light dark:bg-surface-card-dark hover:border-black/20 dark:hover:border-white/20'"
      @dragover.prevent="dragging = true"
      @dragleave="dragging = false"
      @drop.prevent="onDrop"
      @click="fileInput?.click()"
    >
      <Upload class="w-10 h-10 sm:w-12 sm:h-12 mx-auto mb-3 text-gray-400" />
      <p class="text-gray-600 font-medium text-sm sm:text-base">拖拽文件到此处，或点击选择</p>
      <p class="text-xs text-gray-400 mt-1">
        支持：JPG / PNG / HEIC / RAW（CR2/NEF/ARW/DNG/RAF/ORF/RW2）/ MP4 / MOV / AVI / MKV
      </p>
      <p class="text-xs text-gray-400">单文件最大 10GB，自动分块上传</p>
      <button
        type="button"
        class="mt-3 px-3 py-1.5 text-xs text-gray-700 dark:text-gray-200 bg-white dark:bg-white/10 border border-gray-200 dark:border-white/20 rounded hover:bg-gray-100 dark:hover:bg-white/20"
        @click.stop="folderInput?.click()"
      >
        选择文件夹上传
      </button>
    </div>

    <input
      ref="fileInput"
      type="file"
      multiple
      accept="image/*,video/*,.cr2,.cr3,.nef,.arw,.dng,.raf,.orf,.rw2"
      class="hidden"
      @change="onFileSelect"
    />

    <input
      ref="folderInput"
      type="file"
      multiple
      webkitdirectory
      directory
      class="hidden"
      @change="onFolderSelect"
    />

    <!-- 文件加载进度 -->
    <div v-if="uploadStore.addingFiles" class="mt-4 sm:mt-6 flex items-center gap-3 p-4 rounded-xl bg-apple-blue/5 border border-apple-blue/20">
      <Loader class="w-5 h-5 text-apple-blue animate-spin shrink-0" />
      <span class="text-sm text-gray-700 dark:text-gray-200">{{ uploadStore.addingProgress }}</span>
    </div>

    <!-- 文件队列（虚拟滚动，支持数万文件不卡顿） -->
    <div v-if="uploadStore.queue.length > 0" class="mt-4 sm:mt-6 flex flex-col gap-2">
      <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
        <span class="font-semibold text-gray-700 text-sm sm:text-base">待上传文件 ({{ uploadStore.queue.length }})</span>
        <div class="flex gap-2 flex-wrap">
          <button
            v-if="hasCompleted"
            @click="uploadStore.clearDone()"
            class="text-xs text-gray-500 hover:text-gray-700"
          >清除已完成</button>
          <button
            v-if="!uploadStore.uploading && uploadStore.queue.length > 0"
            @click="clearAll"
            class="text-xs text-red-500 hover:text-red-700"
          >清空队列</button>
          <button
            @click="startUpload"
            :disabled="uploadStore.uploading"
            class="px-4 py-1.5 bg-primary-600 text-white text-sm rounded hover:bg-primary-700 disabled:opacity-50 transition-colors"
          >
            {{ uploadStore.uploading ? '上传中…' : hasRetryable ? '重新上传' : '开始上传' }}
          </button>
          <button
            v-if="uploadStore.uploading"
            @click="abortUpload"
            class="px-4 py-1.5 bg-red-600 text-white text-sm rounded hover:bg-red-700 transition-colors flex items-center gap-1"
          >
            <StopCircle class="w-4 h-4" /> 终止上传
          </button>
        </div>
      </div>

      <!-- 总进度概览 -->
      <div v-if="hasAnyProgress" class="bg-white border border-primary-200 rounded-lg px-3 sm:px-4 py-2.5 sm:py-3 shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-1 mb-1.5">
          <div class="flex items-center gap-2 text-sm font-medium text-gray-700">
            <Upload class="w-4 h-4 text-primary-500" />
            <span>总进度：{{ overallStats.done }}/{{ overallStats.total }} 个文件</span>
          </div>
          <div class="flex items-center gap-2 sm:gap-3 text-xs sm:text-sm">
            <span class="font-mono text-primary-600">{{ overallStats.percent }}%</span>
            <span class="text-gray-500">{{ formatSpeed(overallStats.speed) }}</span>
            <span v-if="overallStats.eta" class="text-gray-400">剩余 {{ overallStats.eta }}</span>
          </div>
        </div>
        <div class="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            class="h-full bg-primary-500 transition-all duration-300 rounded-full"
            :style="{ width: `${overallStats.percent}%` }"
          />
        </div>
        <div class="flex justify-between mt-1 text-xs text-gray-400">
          <span>{{ formatBytes(overallStats.loaded) }} / {{ formatBytes(overallStats.totalSize) }}</span>
          <span v-if="overallStats.errors > 0" class="text-red-500">{{ overallStats.errors }} 个失败</span>
        </div>
      </div>

      <RecycleScroller
        :items="uploadStore.queue"
        :item-size="72"
        key-field="id"
        class="max-h-[480px] overflow-y-auto"
        v-slot="{ item }"
      >
        <div
          class="bg-white border border-gray-100 rounded-lg px-4 py-3 flex items-center gap-3 mb-1"
        >
          <component
            :is="item.type === 'video' ? Video : Image"
            class="w-5 h-5 text-gray-400 shrink-0"
          />
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium truncate">{{ item.filename }}</p>
            <p class="text-xs text-gray-400">{{ formatBytes(item.size) }} · {{ item.type === 'video' ? '视频' : '照片' }}</p>
            <div v-if="item.status === 'uploading'" class="mt-1">
              <div class="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  class="h-full bg-primary-500 transition-all duration-300 rounded-full"
                  :style="{ width: `${item.progress}%` }"
                />
              </div>
              <div class="flex items-center justify-between mt-0.5">
                <span class="text-xs text-gray-400">{{ item.progress }}%</span>
                <span class="text-xs text-gray-400">{{ formatSpeed(item.speed) }}</span>
              </div>
            </div>
            <p v-if="item.error" class="text-xs text-red-500 mt-0.5">{{ item.error }}</p>
          </div>
          <div class="shrink-0">
            <CheckCircle v-if="item.status === 'done'" class="w-5 h-5 text-green-500" />
            <AlertCircle v-else-if="item.status === 'error'" class="w-5 h-5 text-red-500" />
            <Loader v-else-if="item.status === 'uploading'" class="w-5 h-5 text-primary-500 animate-spin" />
            <button
              v-if="item.status === 'queued'"
              @click="uploadStore.removeItem(item.id)"
              class="w-5 h-5 text-gray-300 hover:text-red-400"
            ><X class="w-5 h-5" /></button>
          </div>
        </div>
      </RecycleScroller>
    </div>


  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Upload, Video, Image, CheckCircle, AlertCircle, Loader, X, StopCircle } from 'lucide-vue-next'
import { RecycleScroller } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import { useUploadStore } from '@/stores/uploadStore'
import { useToastStore } from '@/stores/toastStore'

const uploadStore = useUploadStore()
const toast = useToastStore()
const fileInput = ref<HTMLInputElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const dragging = ref(false)


const ALLOWED_EXTENSIONS = new Set([
  'jpg', 'jpeg', 'png', 'heif', 'heic',
  'cr2', 'cr3', 'nef', 'arw', 'dng', 'raf', 'orf', 'rw2',
  'mp4', 'mov', 'avi', 'mkv',
])

const hasCompleted = computed(() => uploadStore.queue.some(u => u.status === 'done'))
const hasRetryable = computed(() => !uploadStore.uploading && uploadStore.queue.some(u => u.status === 'error'))
const hasAnyProgress = computed(() => uploadStore.queue.some(u => u.status === 'uploading' || u.status === 'done' || u.status === 'error'))

const overallStats = computed(() => {
  const q = uploadStore.queue
  const total = q.length
  const done = q.filter(u => u.status === 'done').length
  const errors = q.filter(u => u.status === 'error').length
  const totalSize = q.reduce((s, u) => s + u.size, 0)
  const loaded = q.reduce((s, u) => {
    if (u.status === 'done') return s + u.size
    if (u.status === 'uploading') return s + u.loaded
    return s
  }, 0)
  const percent = totalSize > 0 ? Math.round((loaded / totalSize) * 100) : 0
  const speed = q.filter(u => u.status === 'uploading').reduce((s, u) => s + u.speed, 0)
  const remaining = totalSize - loaded
  let eta = ''
  if (speed > 0 && remaining > 0) {
    const secs = Math.round(remaining / speed)
    if (secs < 60) eta = `${secs}s`
    else if (secs < 3600) eta = `${Math.floor(secs / 60)}m${secs % 60}s`
    else eta = `${Math.floor(secs / 3600)}h${Math.floor((secs % 3600) / 60)}m`
  }
  return { total, done, errors, totalSize, loaded, percent, speed, eta }
})

function onDrop(e: DragEvent) {
  dragging.value = false
  const dropped = Array.from(e.dataTransfer?.files ?? [])
  addFiles(dropped)
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const selected = Array.from(input.files ?? [])
  input.value = '' // 允许重复选择同一文件
  addFiles(selected)
}

function onFolderSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const selected = Array.from(input.files ?? [])
  input.value = ''
  if (!selected.length) return

  // 过滤出支持的文件类型，跳过 .DS_Store / ._ 等系统文件
  const valid = selected.filter(f => {
    const name = f.name
    if (name.startsWith('._') || name.startsWith('.')) return false
    const ext = name.split('.').pop()?.toLowerCase() ?? ''
    return ALLOWED_EXTENSIONS.has(ext)
  })

  if (valid.length === 0) {
    toast.error('文件夹中没有支持的照片/视频文件')
    return
  }

  const skipped = selected.length - valid.length
  if (skipped > 0) {
    toast.info(`已跳过 ${skipped} 个不支持的文件`)
  }

  addFiles(valid)
}

function addFiles(newFiles: File[]) {
  // 过滤不支持的扩展名和 macOS 隐藏文件（._ 资源分叉）
  const valid = newFiles.filter(f => {
    const name = f.name
    if (name.startsWith('._') || name.startsWith('.')) return false
    const ext = name.split('.').pop()?.toLowerCase() ?? ''
    return ALLOWED_EXTENSIONS.has(ext)
  })
  if (valid.length === 0) return
  // File 引用由 uploadStore 的 _fileMap 管理，不再在 View 层存储
  uploadStore.addFiles(valid)
}

async function startUpload() {
  try {
    // 先把被终止/失败的项重置为 queued，使其可以重新上传
    uploadStore.retryFailed()
    await uploadStore.startAll()
    const hasAborted = uploadStore.queue.some(u => u.error === '已终止')
    if (hasAborted) {
      toast.info('上传已终止')
    } else {
      toast.success('上传完成')
    }
  } catch (e: any) {
    toast.error(e.message)
  }
}

function abortUpload() {
  if (confirm('确认终止所有上传？已完成的文件不受影响。')) {
    uploadStore.abortAll()
  }
}

function clearAll() {
  if (confirm('确认清空上传队列？')) {
    uploadStore.clearQueue()
  }
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 ** 3) return `${(b / (1024 * 1024)).toFixed(1)} MB`
  return `${(b / 1024 ** 3).toFixed(2)} GB`
}

function formatSpeed(bytesPerSec: number): string {
  if (bytesPerSec <= 0) return ''
  if (bytesPerSec < 1024) return `${bytesPerSec} B/s`
  if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(1)} KB/s`
  return `${(bytesPerSec / (1024 * 1024)).toFixed(1)} MB/s`
}
</script>
