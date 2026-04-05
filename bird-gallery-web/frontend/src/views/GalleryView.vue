<template>
  <div class="flex h-full -m-4 overflow-hidden">
    <!-- 筛选侧栏 -->
    <FilterPanel
      :model-value="photoStore.filters"
      @update="onFilterUpdate"
      @reset="onReset"
    />

    <!-- 主内容区 -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <!-- 工具栏 -->
      <div class="flex items-center gap-3 px-4 py-2 bg-white border-b border-gray-100">
        <span class="text-sm text-gray-500">
          共 <strong>{{ photoStore.total }}</strong> 张
        </span>
        <div class="flex-1" />
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
        <!-- 选择模式工具栏 -->
        <template v-if="selectMode">
          <button
            @click="selectAll"
            class="flex items-center gap-1 px-2 py-1.5 text-xs text-gray-600 hover:text-primary-600"
          >
            {{ selected.size > 0 ? '取消全选' : `全选 (${Math.min(photoStore.total, 500)})` }}
          </button>
          <span v-if="selected.size > 0" class="text-xs text-gray-500">已选 {{ selected.size }} 张</span>
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
        <!-- 一键识别 -->
        <button
          @click="recognizeAll"
          :disabled="recognizing"
          class="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white text-sm rounded hover:bg-emerald-700 disabled:opacity-50 transition-colors"
        >
          <Zap class="w-4 h-4" />
          <span v-if="recognizing">识别中 ({{ recognizeProgress }}%)…</span>
          <span v-else>一键识别全部</span>
        </button>
        <!-- 批量操作 -->
        <button
          v-if="selected.size > 0 && !selectMode"
          @click="batchRecognize"
          class="flex items-center gap-1.5 px-3 py-1.5 bg-primary-600 text-white text-sm rounded hover:bg-primary-700 transition-colors"
        >
          <Cpu class="w-4 h-4" />识别选中 ({{ selected.size }})
        </button>
        <!-- 视图切换 -->
        <div class="flex border border-gray-200 rounded overflow-hidden">
          <button
            v-for="v in ['grid', 'list']"
            :key="v"
            @click="viewMode = v as 'grid' | 'list'"
            class="px-2 py-1 text-sm transition-colors"
            :class="viewMode === v ? 'bg-primary-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'"
          >
            <LayoutGrid v-if="v === 'grid'" class="w-4 h-4" />
            <List v-else class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- 照片网格 / 列表 -->
      <div ref="scrollEl" class="flex-1 overflow-y-auto p-4">
        <!-- 识别进度条 -->
        <div v-if="recognizing" class="mb-4 bg-white border border-emerald-200 rounded-lg p-4 shadow-sm">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
              <Zap class="w-4 h-4 text-emerald-600 animate-pulse" />
              <span class="text-sm font-medium text-gray-700">正在识别鸟类并评分…</span>
            </div>
            <span class="text-sm font-mono text-emerald-600">{{ recognizeProgress }}%</span>
          </div>
          <div class="w-full bg-gray-200 rounded-full h-2.5">
            <div
              class="bg-emerald-500 h-2.5 rounded-full transition-all duration-300"
              :style="{ width: recognizeProgress + '%' }"
            ></div>
          </div>
          <p class="text-xs text-gray-500 mt-1.5">
            {{ recognizeStatusText }}
          </p>
        </div>

        <Spinner v-if="photoStore.loading && photoStore.items.length === 0" />

        <EmptyState
          v-else-if="!photoStore.loading && photoStore.items.length === 0"
          title="暂无照片"
          description="上传照片或扫描本地目录"
        />

        <!-- 网格模式（虚拟滚动，按行渲染） -->
        <RecycleScroller
          v-else-if="viewMode === 'grid'"
          class="h-[70vh]"
          :items="gridRows"
          :item-size="gridRowHeight"
          key-field="rowKey"
          v-slot="{ item: row }"
        >
          <div class="grid gap-2 pb-2" :style="gridStyle">
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
          class="h-[70vh]"
          :items="photoStore.items"
          key-field="id"
          :item-size="58"
          v-slot="{ item: photo }"
        >
          <div
            class="flex items-center gap-3 px-3 py-2 bg-white rounded-lg hover:bg-gray-50 cursor-pointer border border-gray-100 mb-1"
            @click="openPhoto(photo.id)"
          >
            <img
              :src="photoAPI.thumbnailUrl(photo.id, 'sm')"
              class="w-10 h-10 object-cover rounded"
              loading="lazy"
            />
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium truncate">{{ photo.filename }}</p>
              <p class="text-xs text-gray-500">{{ photo.species_cn || '未识别' }}</p>
            </div>
            <span class="text-xs text-gray-400">{{ formatDate(photo.exif_datetime || photo.created_at) }}</span>
            <StarRating :rating="photo.rating" />
          </div>
        </RecycleScroller>

        <!-- 加载更多 -->
        <div v-if="hasMore" class="flex justify-center mt-4">
          <button
            @click="loadMore"
            :disabled="photoStore.loading"
            class="px-6 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          >
            <span v-if="photoStore.loading">加载中…</span>
            <span v-else>加载更多</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { LayoutGrid, List, Cpu, Zap, CheckSquare, Trash2 } from 'lucide-vue-next'
import { usePhotoStore } from '@/stores/photoStore'
import { useToastStore } from '@/stores/toastStore'
import { useAuthStore } from '@/stores/authStore'
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
const scrollEl = ref<HTMLElement | null>(null)
const viewMode = ref<'grid' | 'list'>('grid')
const selected = ref<Set<string>>(new Set())
const selectMode = ref(false)
const deleting = ref(false)
const recognizing = ref(false)
const recognizeProgress = ref(0)
const recognizeTotal = ref(0)

const recognizeStatusText = computed(() => {
  if (recognizeProgress.value >= 100) return '即将完成…'
  if (recognizeTotal.value > 0) {
    const done = Math.round(recognizeTotal.value * recognizeProgress.value / 100)
    return `已处理 ${done} / ${recognizeTotal.value} 张（每张照片需加载 AI 模型进行关键点检测和美学评分）`
  }
  return '正在提交识别任务…'
})

const gridStyle = computed(() => ({
  gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
}))

// 网格虚拟滚动：将照片分成行
const gridColCount = 6  // 与 minmax(160px, 1fr) 在常见宽度下的列数近似
const gridRowHeight = 178 // 160px(aspect-square) + 8px gap + 10px padding

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

async function recognizeAll() {
  recognizing.value = true
  recognizeProgress.value = 0
  try {
    const res = await photoAPI.recognizeAll()
    if (res.total === 0) {
      toastStore.info('所有照片已识别，无需重复操作')
      recognizing.value = false
      return
    }
    toastStore.info(`已提交识别任务（${res.total} 张待识别）`)
    recognizeTotal.value = res.total
    const taskId = res.id ?? res.task_id
    await new Promise<void>((resolve, reject) => {
      const tick = async () => {
        try {
          const t = await taskAPI.get(taskId)
          recognizeProgress.value = t.progress ?? 0
          if (t.status === 'done') return resolve()
          if (t.status === 'error') return reject(new Error(t.error_msg || '识别失败'))
          setTimeout(tick, 1500)
        } catch (e) {
          reject(e)
        }
      }
      tick()
    })
    toastStore.success('全部识别完成')
    photoStore.fetchPhotos(true)
  } catch (e: any) {
    toastStore.error(e.message)
  } finally {
    recognizing.value = false
  }
}

function formatDate(s: string | undefined) {
  if (!s) return ''
  return s.slice(0, 10)
}
</script>
