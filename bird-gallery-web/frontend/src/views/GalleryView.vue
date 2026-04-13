<template>
  <div class="flex flex-col h-[calc(100vh-48px)] overflow-hidden bg-surface-light dark:bg-surface-dark">
    <!-- 工具栏 -->
    <div class="bg-white/90 dark:bg-[#1c1c1e]/90 backdrop-blur-xl border-b border-black/[0.06] dark:border-white/[0.08] shrink-0">
      <!-- 第一行：核心操作 -->
      <div class="flex items-center gap-2 sm:gap-3 px-3 sm:px-6 py-2.5 sm:py-3">
        <span class="text-[13px] sm:text-[14px] text-text-tertiary dark:text-text-on-dark-tertiary shrink-0" style="letter-spacing: -0.224px;">
          共 <strong class="text-text-primary dark:text-text-on-dark font-semibold">{{ photoStore.total }}</strong> 张
        </span>

        <!-- 筛选切换 -->
        <button
          @click="filterOpen = !filterOpen"
          class="flex items-center gap-1.5 px-3 py-1.5 text-[13px] sm:text-[14px] rounded-full transition-all shrink-0"
          :class="filterOpen
            ? 'bg-apple-blue text-white shadow-sm'
            : 'text-text-secondary dark:text-text-on-dark-secondary hover:bg-black/[0.04] dark:hover:bg-white/[0.08]'"
          style="letter-spacing: -0.224px;"
        >
          <SlidersHorizontal class="w-3.5 h-3.5" />
          <span class="hidden xs:inline">筛选</span>
        </button>

        <div class="flex-1 min-w-0"></div>

        <!-- 选择模式 -->
        <button
          @click="toggleSelectMode"
          class="flex items-center gap-1.5 px-3 py-1.5 text-[13px] sm:text-[14px] rounded-full transition-all shrink-0"
          :class="selectMode
            ? 'bg-apple-blue text-white shadow-sm'
            : 'text-text-secondary dark:text-text-on-dark-secondary hover:bg-black/[0.04] dark:hover:bg-white/[0.08]'"
          style="letter-spacing: -0.224px;"
        >
          <CheckSquare class="w-3.5 h-3.5" />
          <span class="hidden sm:inline">{{ selectMode ? '退出' : '选择' }}</span>
        </button>

        <!-- 一键识别 -->
        <button
          @click="recognizeAll"
          :disabled="recognizing || recognizeSubmitting"
          class="flex items-center gap-1.5 px-3 sm:px-4 py-1.5 text-white text-[13px] sm:text-[14px] rounded-full transition-all shrink-0 shadow-sm"
          :class="(recognizing || recognizeSubmitting) ? 'bg-apple-blue/70 animate-pulse' : 'bg-apple-blue hover:brightness-110 active:brightness-95'"
          style="letter-spacing: -0.224px;"
        >
          <Zap class="w-4 h-4" />
          <span v-if="recognizeSubmitting">提交中</span>
          <span v-else-if="recognizing">{{ recognizeProgress }}%</span>
          <span v-else>一键识别</span>
        </button>

        <!-- 视图切换 -->
        <div class="flex bg-black/[0.04] dark:bg-white/[0.08] rounded-full p-0.5 shrink-0">
          <button
            v-for="v in ['grid', 'list']"
            :key="v"
            @click="viewMode = v as 'grid' | 'list'"
            class="px-2 py-1.5 rounded-full transition-all duration-200"
            :class="viewMode === v
              ? 'bg-white dark:bg-white/20 text-text-primary dark:text-text-on-dark shadow-sm'
              : 'text-text-tertiary dark:text-text-on-dark-tertiary hover:text-text-primary dark:hover:text-text-on-dark'"
          >
            <LayoutGrid v-if="v === 'grid'" class="w-4 h-4" />
            <List v-else class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- 第二行：选择模式操作 -->
      <div v-if="selectMode" class="flex items-center gap-2 px-3 sm:px-6 pb-2.5 flex-wrap">
        <button
          @click="selectAll"
          class="text-[12px] text-apple-link-light dark:text-apple-link-dark hover:underline"
        >
          {{ selected.size > 0 ? '取消全选' : `全选 (${Math.min(photoStore.total, 500)})` }}
        </button>
        <span v-if="selected.size > 0" class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary">已选 {{ selected.size }} 张</span>
        <button
          v-if="selected.size > 0 && authStore.isAdmin"
          @click="batchDelete"
          :disabled="deleting"
          class="flex items-center gap-1 px-2.5 py-1 bg-red-600 text-white text-[13px] rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
        >
          <Trash2 class="w-3.5 h-3.5" />
          {{ deleting ? '删除中…' : `删除 (${selected.size})` }}
        </button>
        <button
          v-if="selected.size > 0"
          @click="batchRecognize"
          class="btn-primary !text-[13px] !px-2.5 !py-1 flex items-center gap-1"
        >
          <Cpu class="w-3.5 h-3.5" />识别选中 ({{ selected.size }})
        </button>
      </div>
    </div>

    <!-- 可折叠筛选面板 -->
    <Transition name="filter-slide">
      <div v-if="filterOpen" class="bg-white/95 dark:bg-[#1c1c1e]/95 backdrop-blur-xl border-b border-black/[0.06] dark:border-white/[0.08] shrink-0">
        <FilterPanel
          :model-value="photoStore.filters"
          @update="onFilterUpdate"
          @reset="onReset"
        />
      </div>
    </Transition>

    <!-- 照片网格 / 列表 -->
    <div ref="scrollEl" class="flex-1 flex flex-col overflow-hidden px-3 sm:px-6">
      <!-- 识别进度条 -->
      <div v-if="recognizing" class="mb-3 mt-3 shrink-0 rounded-xl bg-white dark:bg-[#1c1c1e] p-4 sm:p-5 shadow-sm dark:text-text-on-dark">
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <Zap class="w-4 h-4 text-emerald-500 animate-pulse" />
            <span class="text-[14px] font-medium">{{ recognizeTitle }}</span>
          </div>
          <div class="flex items-center gap-3">
            <span class="text-[14px] font-mono text-emerald-500">{{ recognizeProgress }}%</span>
            <button
              @click="stopRecognize"
              class="flex items-center gap-1 px-2.5 py-1 text-[12px] text-red-500 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
            >
              <Square class="w-3 h-3" />
              停止
            </button>
          </div>
        </div>
        <div class="w-full bg-black/5 dark:bg-white/10 rounded-full h-1.5">
          <div
            class="bg-emerald-500 h-1.5 rounded-full transition-all duration-300"
            :style="{ width: recognizeProgress + '%' }"
          ></div>
        </div>
        <p class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary mt-1.5">
          {{ recognizeStatusText }}
        </p>
        <!-- 实时识别结果日志 -->
        <div
          v-if="recognizeResults.length > 0"
          ref="logEl"
          class="mt-3 max-h-48 overflow-y-auto bg-surface-light dark:bg-black/20 rounded-lg p-2 space-y-0.5"
        >
          <div
            v-for="(item, idx) in recognizeResults"
            :key="idx"
            class="text-[12px] font-mono leading-5 flex items-center gap-1.5"
          >
            <template v-if="item.error">
              <span class="text-red-500">✗</span>
              <span class="text-text-tertiary dark:text-text-on-dark-tertiary truncate">{{ item.filename }}</span>
              <span class="text-red-400">— 识别失败</span>
              <span v-if="item.elapsed" class="text-text-tertiary dark:text-text-on-dark-tertiary ml-auto shrink-0">{{ item.elapsed }}s</span>
            </template>
            <template v-else-if="item.species_cn">
              <span class="text-emerald-500">✓</span>
              <span class="text-text-tertiary dark:text-text-on-dark-tertiary truncate">{{ item.filename }}</span>
              <span class="text-text-tertiary dark:text-text-on-dark-tertiary">—</span>
              <span class="text-emerald-600 dark:text-emerald-400 font-medium">{{ item.species_cn }}</span>
              <span v-if="item.rating != null && item.rating >= 0" class="text-amber-500">{{ '⭐'.repeat(item.rating) }}{{ item.rating === 0 ? '☆' : '' }}</span>
              <span v-if="item.head_sharp != null" class="text-text-tertiary dark:text-text-on-dark-tertiary">锐度 {{ item.head_sharp.toFixed(2) }}</span>
              <span v-if="item.nima_score != null" class="text-text-tertiary dark:text-text-on-dark-tertiary">美学 {{ item.nima_score.toFixed(2) }}</span>
              <span v-if="item.elapsed" class="text-text-tertiary dark:text-text-on-dark-tertiary ml-auto shrink-0">{{ item.elapsed }}s</span>
            </template>
            <template v-else>
              <span class="text-text-tertiary dark:text-text-on-dark-tertiary">○</span>
              <span class="text-text-tertiary dark:text-text-on-dark-tertiary truncate">{{ item.filename }}</span>
              <span class="text-text-tertiary dark:text-text-on-dark-tertiary">— 未检测到鸟类</span>
              <span v-if="item.elapsed" class="text-text-tertiary dark:text-text-on-dark-tertiary ml-auto shrink-0">{{ item.elapsed }}s</span>
            </template>
          </div>
        </div>
      </div>

      <Spinner v-if="photoStore.loading && photoStore.items.length === 0" class="py-20" />

      <EmptyState
        v-else-if="!photoStore.loading && photoStore.items.length === 0"
        title="暂无照片"
        description="上传照片或扫描本地目录"
      />

      <!-- 网格模式（虚拟滚动，按行渲染） -->
      <RecycleScroller
        v-else-if="viewMode === 'grid'"
        class="flex-1 pt-3 pb-4"
        :items="gridRows"
        :item-size="gridRowHeight"
        key-field="rowKey"
        v-slot="{ item: row }"
        @scroll.native="onScroll"
      >
        <div class="grid gap-3 sm:gap-4 pb-3" :style="gridStyle">
          <PhotoCard
            v-for="photo in row.photos"
            :key="photo.id"
            :photo="photo"
            :selectable="selectMode"
            :selected="selected.has(photo.id)"
              @click="openPhoto(photo.id)"
              @toggle-select="toggleSelect"
            />
          </div>
        </RecycleScroller>

        <!-- 列表模式 -->
        <RecycleScroller
          v-else
          class="flex-1 pt-3 pb-4"
          :items="photoStore.items"
          key-field="id"
          :item-size="58"
          v-slot="{ item: photo }"
          @scroll.native="onScroll"
        >
          <div
            class="flex items-center gap-3 px-3 sm:px-4 py-2.5 rounded-xl bg-white dark:bg-[#1c1c1e] hover:bg-black/[0.02] dark:hover:bg-white/[0.04] cursor-pointer mb-1 transition-colors"
            @click="openPhoto(photo.id)"
          >
            <img
              :src="photoAPI.thumbnailUrl(photo.id, 'sm')"
              class="w-10 h-10 object-cover rounded"
              loading="lazy"
            />
            <div class="flex-1 min-w-0">
              <p class="text-[14px] font-medium truncate dark:text-text-on-dark">{{ photo.filename }}</p>
              <p class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary">{{ photo.species_cn || '未识别' }}</p>
            </div>
            <span class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary">{{ formatDate(photo.exif_datetime || photo.created_at) }}</span>
            <StarRating :rating="photo.rating" />
          </div>
        </RecycleScroller>

        <!-- 加载指示 -->
        <div v-if="photoStore.loading && photoStore.items.length > 0" class="flex justify-center py-4 shrink-0">
          <Spinner />
        </div>
      </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { LayoutGrid, List, Cpu, Zap, CheckSquare, Trash2, Square, SlidersHorizontal } from 'lucide-vue-next'
import { usePhotoStore } from '@/stores/photoStore'
import { useToastStore } from '@/stores/toastStore'
import { useAuthStore } from '@/stores/authStore'
import { useTaskStore } from '@/stores/taskStore'
import { photoAPI } from '@/api/photos'
import { taskAPI } from '@/api/admin'
import FilterPanel from '@/components/gallery/FilterPanel.vue'
import PhotoCard from '@/components/gallery/PhotoCard.vue'
import Spinner from '@/components/common/Spinner.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import StarRating from '@/components/common/StarRating.vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import type { PhotoFilters } from '@/types'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const photoStore = usePhotoStore()
const toastStore = useToastStore()
const taskStore = useTaskStore()
const scrollEl = ref<HTMLElement | null>(null)
const logEl = ref<HTMLElement | null>(null)
const viewMode = ref<'grid' | 'list'>('grid')
const selected = ref<Set<string>>(new Set())
const selectMode = ref(false)
const deleting = ref(false)
const filterOpen = ref(false)

// 从全局 taskStore 引用识别状态
const recognizing = computed(() => taskStore.recognizing)
const recognizeProgress = computed(() => taskStore.recognizeProgress)
const recognizeTitle = computed(() => taskStore.recognizeTitle)
const recognizeStatusText = computed(() => taskStore.recognizeStatusText)
const recognizeResults = computed(() => taskStore.recognizeResults)

// 日志自动滚动到底部
watch(recognizeResults, () => {
  nextTick(() => {
    if (logEl.value) {
      logEl.value.scrollTop = logEl.value.scrollHeight
    }
  })
}, { deep: true })

const gridStyle = computed(() => ({
  gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
}))

// 网格虚拟滚动：将照片分成行
const gridColCount = 5  // 与 minmax(180px, 1fr) 在常见宽度下的列数近似
const gridRowHeight = 160 // 180px * 0.75 (4:3 ratio) + 12px gap

const gridRows = computed(() => {
  const rows: { rowKey: string; photos: typeof photoStore.items }[] = []
  const items = photoStore.items
  for (let i = 0; i < items.length; i += gridColCount) {
    rows.push({
      rowKey: `row-${i}`,
      photos: items.slice(i, i + gridColCount),
    })
  }
  return rows
})

const hasMore = computed(
  () => photoStore.items.length < photoStore.total,
)

onMounted(async () => {
  // 从路由携带 q 参数
  if (route.query.q) {
    photoStore.setFilter('q', String(route.query.q))
  }
  await photoStore.fetchPhotos(true)
  // 恢复识别进度轮询（如果之前在其他页面时任务仍在运行）
  taskStore.resumeIfActive()
  await taskStore.resumeLatestRecognizeAll()
})

function onFilterUpdate(key: string, val: any) {
  photoStore.setFilter(key as keyof PhotoFilters, val)
  photoStore.fetchPhotos(true)
}

function onReset() {
  photoStore.resetFilters()
  photoStore.fetchPhotos(true)
}

async function loadMore() {
  photoStore.nextPage()
  await photoStore.fetchPhotos(false)
}

function onScroll(e: Event) {
  const el = e.target as HTMLElement
  if (!el || !hasMore.value || photoStore.loading) return
  // 距底部 300px 时自动加载
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 300) {
    loadMore()
  }
}

function openPhoto(id: string) {
  if (selectMode.value) {
    toggleSelect(id)
    return
  }
  router.push(`/photos/${id}`)
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) {
    selected.value.clear()
  }
}

function toggleSelect(id: string) {
  const s = new Set(selected.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selected.value = s
}

async function selectAll() {
  if (selected.value.size > 0) {
    selected.value = new Set()
    return
  }
  // 通过独立 API 调用获取最多 500 个 ID，不影响 store 分页状态
  const cap = 500
  try {
    const res = await photoAPI.list({ ...photoStore.filters, page: 1, page_size: cap })
    selected.value = new Set(res.items.map((p: any) => p.id))
    if (res.total > cap) {
      toastStore.info(`共 ${res.total} 张照片，已选中前 ${cap} 张`)
    }
  } catch (e: any) {
    toastStore.error('全选失败: ' + e.message)
  }
}

async function batchDelete() {
  const ids = [...selected.value]
  if (!confirm(`确认删除选中的 ${ids.length} 张照片？此操作不可撤销。`)) return
  deleting.value = true
  try {
    await photoAPI.batchDelete(ids)
    toastStore.success(`已删除 ${ids.length} 张照片`)
    selected.value = new Set()
    selectMode.value = false
    await photoStore.fetchPhotos(true)
  } catch (e: any) {
    toastStore.error(e.message)
  } finally {
    deleting.value = false
  }
}

async function batchRecognize() {
  const ids = [...selected.value]
  try {
    const task = await photoAPI.batchRecognize(ids)
    toastStore.info(`已提交批量识别任务（${ids.length} 张）`)
    await taskAPI.poll(task.id ?? (task as any).task_id)
    toastStore.success('批量识别完成')
    photoStore.fetchPhotos(true)
  } catch (e: any) {
    toastStore.error(e.message)
  }
}

const recognizeSubmitting = ref(false)

async function recognizeAll() {
  if (taskStore.recognizing || recognizeSubmitting.value) return
  recognizeSubmitting.value = true
  toastStore.info('正在提交识别任务…')
  const controller = new AbortController()
  const submitTimeout = window.setTimeout(() => controller.abort(), 8000)
  try {
    const res = await photoAPI.recognizeAll(controller.signal)
    if (res.total === 0) {
      toastStore.info('所有照片已识别，无需重复操作')
      return
    }
    const taskId = res.id ?? res.task_id
    toastStore.success(`已提交识别任务（${res.total} 张待识别）`)
    taskStore.startTracking(taskId, res.total)
    // 后台轮询由 taskStore 管理，这里监听完成
    const check = setInterval(() => {
      if (!taskStore.recognizing) {
        clearInterval(check)
        if (taskStore.recognizeProgress >= 100 || !taskStore.recognizeTaskId) {
          toastStore.success('全部识别完成')
          photoStore.fetchPhotos(true)
        }
      }
    }, 2000)
  } catch (e: any) {
    const recovered = await taskStore.resumeLatestRecognizeAll()
    if (recovered) {
      toastStore.info('已恢复正在运行的识别任务')
      return
    }
    const message = controller.signal.aborted ? '提交超时，请稍后重试' : e.message
    toastStore.error(message)
  } finally {
    window.clearTimeout(submitTimeout)
    recognizeSubmitting.value = false
  }
}

async function stopRecognize() {
  await taskStore.cancelRecognize()
  toastStore.info('已停止识别任务')
  photoStore.fetchPhotos(true)
}

function formatDate(s: string | undefined) {
  if (!s) return ''
  return s.slice(0, 10)
}
</script>

<style scoped>
.filter-slide-enter-active,
.filter-slide-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}
.filter-slide-enter-from,
.filter-slide-leave-to {
  max-height: 0;
  opacity: 0;
}
.filter-slide-enter-to,
.filter-slide-leave-from {
  max-height: 400px;
  opacity: 1;
}
</style>
