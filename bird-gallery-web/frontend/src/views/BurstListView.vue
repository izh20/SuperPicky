<template>
  <div class="flex gap-6 max-w-7xl mx-auto px-5 py-6">
    <!-- 筛选侧边栏 -->
    <aside class="w-56 flex-shrink-0 space-y-4">
      <div class="card-apple dark:bg-surface-card-dark p-4 space-y-3">
        <h3 class="text-sm font-semibold text-text-primary dark:text-text-on-dark flex items-center gap-1.5">
          <Filter class="w-4 h-4" /> 筛选
        </h3>

        <!-- 鸟种 -->
        <div>
          <label class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mb-1 block">鸟种</label>
          <select
            :value="burstStore.filters.species || ''"
            @change="burstStore.updateFilter('species', ($event.target as HTMLSelectElement).value || undefined)"
            class="w-full text-sm bg-surface-light dark:bg-white/10 border-0 rounded-lg px-2 py-1.5 dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40"
          >
            <option value="">全部</option>
            <option v-for="s in filterOpts.species" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>

        <!-- 相机 -->
        <div>
          <label class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mb-1 block">相机</label>
          <select
            :value="burstStore.filters.camera || ''"
            @change="burstStore.updateFilter('camera', ($event.target as HTMLSelectElement).value || undefined)"
            class="w-full text-sm bg-surface-light dark:bg-white/10 border-0 rounded-lg px-2 py-1.5 dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40"
          >
            <option value="">全部</option>
            <option v-for="c in filterOpts.cameras" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>

        <!-- 最低评分 -->
        <div>
          <label class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mb-1 block">最低评分</label>
          <select
            :value="burstStore.filters.rating_min ?? ''"
            @change="burstStore.updateFilter('rating_min', ($event.target as HTMLSelectElement).value ? Number(($event.target as HTMLSelectElement).value) : undefined)"
            class="w-full text-sm bg-surface-light dark:bg-white/10 border-0 rounded-lg px-2 py-1.5 dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40"
          >
            <option value="">不限</option>
            <option v-for="r in [1,2,3,4,5]" :key="r" :value="r">{{ '⭐'.repeat(r) }}</option>
          </select>
        </div>

        <!-- 最少张数 -->
        <div>
          <label class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mb-1 block">最少张数</label>
          <input
            type="number"
            :value="burstStore.filters.min_photos ?? 1"
            @change="burstStore.updateFilter('min_photos', Number(($event.target as HTMLInputElement).value) || 1)"
            min="1" max="500"
            class="w-full text-sm bg-surface-light dark:bg-white/10 border-0 rounded-lg px-2 py-1.5 dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40"
          />
        </div>

        <!-- 置信度阈值 -->
        <div>
          <label class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mb-1 block">鸟种置信度 ≥ {{ confidenceMin }}%</label>
          <input
            type="range"
            v-model.number="confidenceMin"
            min="0" max="100" step="5"
            class="w-full"
            @change="refreshFilterOptions"
          />
        </div>

        <!-- 飞版筛选 -->
        <div>
          <label class="flex items-center gap-2 text-xs text-text-tertiary dark:text-text-on-dark-tertiary cursor-pointer">
            <input
              type="checkbox"
              :checked="burstStore.filters.has_flying ?? false"
              @change="burstStore.updateFilter('has_flying', ($event.target as HTMLInputElement).checked)"
              class="rounded border-black/10 dark:border-white/20"
            />
            仅看飞版连拍
          </label>
          <div v-if="burstStore.filters.has_flying" class="mt-1.5">
            <label class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mb-1 block">最少飞版张数</label>
            <input
              type="number"
              :value="burstStore.filters.flying_min_count ?? 1"
              @change="burstStore.updateFilter('flying_min_count', Number(($event.target as HTMLInputElement).value) || 1)"
              min="1" max="100"
              class="w-full text-sm bg-surface-light dark:bg-white/10 border-0 rounded-lg px-2 py-1.5 dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40"
            />
          </div>
        </div>

        <button
          @click="resetAll"
          class="w-full text-xs text-text-tertiary dark:text-text-on-dark-tertiary hover:text-text-primary dark:hover:text-text-on-dark py-1"
        >
          重置筛选
        </button>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div class="flex-1 min-w-0">
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-xl font-semibold text-text-primary dark:text-text-on-dark font-display">
          连拍组
          <span class="text-sm font-normal text-text-tertiary dark:text-text-on-dark-tertiary ml-2">{{ burstStore.list.length }} 组</span>
        </h1>
        <div class="flex items-center gap-2">
          <!-- 选择模式 -->
          <button
            @click="toggleSelectMode"
            :class="selectMode
              ? 'bg-apple-blue text-white'
              : 'text-text-tertiary dark:text-text-on-dark-tertiary hover:bg-black/5 dark:hover:bg-white/10'"
            class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors"
          >
            <CheckSquare class="w-4 h-4" />
            {{ selectMode ? '退出选择' : '选择' }}
          </button>

          <!-- 选择模式下的操作栏 -->
          <template v-if="selectMode">
            <button
              @click="selectAll"
              class="flex items-center gap-1 px-2.5 py-1.5 text-sm text-text-secondary dark:text-text-on-dark-secondary hover:bg-black/5 dark:hover:bg-white/10 rounded-lg"
            >
              {{ selected.size > 0 ? '取消全选' : `全选(${burstStore.list.length})` }}
            </button>
            <span v-if="selected.size > 0" class="text-sm text-text-tertiary dark:text-text-on-dark-tertiary">已选 {{ selected.size }}</span>
            <button
              v-if="selected.size > 0 && authStore.isAdmin"
              @click="batchDelete"
              :disabled="deleting"
              class="flex items-center gap-1 px-2.5 py-1.5 text-sm bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50"
            >
              <Trash2 class="w-4 h-4" />
              {{ deleting ? '删除中…' : '删除' }}
            </button>
          </template>

          <button
            v-if="!selectMode"
            @click="recognizeAll"
            :disabled="recognizing"
            class="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors"
          >
            <Cpu class="w-4 h-4" />
            <span v-if="recognizing">识别中 ({{ taskStore.recognizeProgress }}%)…</span>
            <span v-else>一键识别全部</span>
          </button>
          <button
            v-if="!selectMode"
            @click="showDetectDialog = true"
            :disabled="detecting"
            class="flex items-center gap-1.5 px-3 py-1.5 bg-apple-blue text-white text-sm rounded-lg hover:bg-apple-blue/90 disabled:opacity-50 transition-colors"
          >
            <Zap class="w-4 h-4" />
            {{ detecting ? '检测中…' : '检测连拍' }}
          </button>
        </div>
      </div>

      <!-- 检测连拍对话框 -->
      <div v-if="showDetectDialog" class="mb-4 card-apple dark:bg-surface-card-dark p-4">
        <h3 class="text-sm font-semibold text-text-primary dark:text-text-on-dark mb-3">连拍检测设置</h3>
        <div class="flex items-end gap-4">
          <div>
            <label class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mb-1 block">时间阈值（秒）</label>
            <input
              v-model.number="detectThreshold"
              type="number" min="0.05" max="60" step="0.5"
              class="w-24 text-sm bg-surface-light dark:bg-white/10 border-0 rounded-lg px-2 py-1.5 dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40"
            />
          </div>
          <div>
            <label class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mb-1 block">最少帧数</label>
            <input
              v-model.number="detectMinCount"
              type="number" min="2" max="100"
              class="w-24 text-sm bg-surface-light dark:bg-white/10 border-0 rounded-lg px-2 py-1.5 dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40"
            />
          </div>
          <button
            @click="detectBursts"
            :disabled="detecting"
            class="px-3 py-1.5 bg-apple-blue text-white text-sm rounded-lg hover:bg-apple-blue/90 disabled:opacity-50"
          >
            {{ detecting ? '检测中…' : '开始检测' }}
          </button>
          <button
            @click="showDetectDialog = false"
            class="px-3 py-1.5 text-text-tertiary dark:text-text-on-dark-tertiary text-sm rounded-lg hover:bg-black/5 dark:hover:bg-white/10"
          >
            取消
          </button>
        </div>
        <p class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mt-2">将重新检测所有连拍组。最少帧数默认 15，低于此数量的连拍不会被分组。</p>
      </div>

      <!-- 识别进度条 -->
      <div v-if="recognizing" class="mb-4 card-apple dark:bg-surface-card-dark p-4">
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <Zap class="w-4 h-4 text-emerald-500 animate-pulse" />
            <span class="text-sm font-medium text-text-primary dark:text-text-on-dark">正在识别鸟类并评分…</span>
          </div>
          <div class="flex items-center gap-3">
            <span class="text-sm font-mono text-emerald-500">{{ taskStore.recognizeProgress }}%</span>
            <button
              @click="stopRecognize"
              class="flex items-center gap-1 px-2.5 py-1 text-xs text-red-500 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
            >
              <Square class="w-3 h-3" />
              停止
            </button>
          </div>
        </div>
        <div class="w-full bg-black/5 dark:bg-white/10 rounded-full h-1.5">
          <div
            class="bg-emerald-500 h-1.5 rounded-full transition-all duration-300"
            :style="{ width: taskStore.recognizeProgress + '%' }"
          ></div>
        </div>
        <p class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mt-1.5">{{ taskStore.recognizeStatusText }}</p>
        <!-- 实时识别结果日志 -->
        <div
          v-if="taskStore.recognizeResults.length > 0"
          ref="logEl"
          class="mt-3 max-h-48 overflow-y-auto bg-surface-light dark:bg-black/20 rounded-lg p-2 space-y-0.5"
        >
          <div
            v-for="(item, idx) in taskStore.recognizeResults"
            :key="idx"
            class="text-xs font-mono leading-5 flex items-center gap-1.5"
          >
            <template v-if="item.error">
              <span class="text-red-500">✗</span>
              <span class="text-text-tertiary dark:text-text-on-dark-tertiary truncate">{{ item.filename }}</span>
              <span class="text-red-400">— 识别失败</span>
            </template>
            <template v-else-if="item.species_cn">
              <span class="text-emerald-500">✓</span>
              <span class="text-text-tertiary dark:text-text-on-dark-tertiary truncate">{{ item.filename }}</span>
              <span class="text-text-tertiary dark:text-text-on-dark-tertiary">—</span>
              <span class="text-emerald-600 dark:text-emerald-400 font-medium">{{ item.species_cn }}</span>
              <span v-if="item.rating != null && item.rating >= 0" class="text-amber-500">{{ '⭐'.repeat(item.rating) }}{{ item.rating === 0 ? '☆' : '' }}</span>
              <span v-if="item.head_sharp != null" class="text-text-tertiary dark:text-text-on-dark-tertiary">锐度 {{ item.head_sharp }}</span>
              <span v-if="item.nima_score != null" class="text-text-tertiary dark:text-text-on-dark-tertiary">美学 {{ item.nima_score }}</span>
            </template>
            <template v-else>
              <span class="text-text-tertiary dark:text-text-on-dark-tertiary">○</span>
              <span class="text-text-tertiary dark:text-text-on-dark-tertiary truncate">{{ item.filename }}</span>
              <span class="text-text-tertiary dark:text-text-on-dark-tertiary">— 未检测到鸟类</span>
            </template>
          </div>
        </div>
      </div>

      <Spinner v-if="burstStore.loading" />
      <EmptyState
        v-else-if="!burstStore.list.length"
        title="暂无连拍组"
        description="点击「检测连拍」按钮自动分组时间相近的照片"
        :icon="Layers"
      />
      <div v-else class="grid gap-4" style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));">
        <div
          v-for="b in burstStore.list"
          :key="b.id"
          class="card-apple dark:bg-surface-card-dark overflow-hidden hover:shadow-apple transition-shadow p-3 relative cursor-pointer"
          :class="{ 'ring-2 ring-apple-blue': selected.has(b.id) }"
          @click="selectMode ? toggleSelect(b.id) : $router.push(`/bursts/${b.id}`)"
        >
          <!-- 选择复选框 -->
          <div
            v-if="selectMode"
            class="absolute top-2 left-2 z-20 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors"
            :class="selected.has(b.id) ? 'bg-apple-blue border-apple-blue' : 'bg-white dark:bg-surface-card-dark border-black/10 dark:border-white/20'"
          >
            <Check v-if="selected.has(b.id)" class="w-3.5 h-3.5 text-white" />
          </div>
          <!-- 叠加缩略图效果 -->
          <div class="relative h-28 mb-3">
            <div class="absolute inset-0 bg-black/5 dark:bg-white/5 rounded-lg" />
            <div class="absolute inset-0 translate-x-1 translate-y-1 bg-black/10 dark:bg-white/10 rounded-lg" />
            <div class="absolute inset-0 translate-x-2 translate-y-2 bg-black/5 dark:bg-white/5 rounded-lg overflow-hidden">
              <img
                v-if="b.best_photo_id"
                :src="`/api/photos/${b.best_photo_id}/thumbnail?size=sm`"
                class="w-full h-full object-cover"
                loading="lazy"
              />
              <div v-else class="w-full h-full flex items-center justify-center">
                <Layers class="w-8 h-8 text-text-tertiary dark:text-text-on-dark-tertiary" />
              </div>
            </div>
            <div class="absolute top-1 right-1 bg-apple-blue text-white text-xs px-1.5 py-0.5 rounded-full font-bold z-10">
              {{ b.photo_count }}
            </div>
          </div>
          <p class="text-sm font-medium text-text-primary dark:text-text-on-dark truncate">{{ b.species_cn || '未识别' }}</p>
          <p class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mt-0.5">{{ formatDate(b.first_shot_at) }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed, watch, nextTick, ref, reactive } from 'vue'
import { Zap, Layers, Cpu, Square, Filter, CheckSquare, Check, Trash2 } from 'lucide-vue-next'
import { useBurstStore } from '@/stores/burstStore'
import { useToastStore } from '@/stores/toastStore'
import { useTaskStore } from '@/stores/taskStore'
import { useAuthStore } from '@/stores/authStore'
import { photoAPI } from '@/api/photos'
import { burstAPI } from '@/api/bursts'
import { taskAPI } from '@/api/admin'
import Spinner from '@/components/common/Spinner.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const burstStore = useBurstStore()
const toast = useToastStore()
const taskStore = useTaskStore()
const authStore = useAuthStore()
const detecting = ref(false)
const logEl = ref<HTMLElement | null>(null)
const showDetectDialog = ref(false)
const detectThreshold = ref(2.0)
const detectMinCount = ref(15)
const confidenceMin = ref(70)

// 选择模式
const selectMode = ref(false)
const selected = ref<Set<string>>(new Set())
const deleting = ref(false)

// 筛选选项
const filterOpts = reactive<{ species: string[]; cameras: string[] }>({ species: [], cameras: [] })

const recognizing = computed(() => taskStore.recognizing)

// 日志自动滚动到底部
watch(() => taskStore.recognizeResults, () => {
  nextTick(() => {
    if (logEl.value) {
      logEl.value.scrollTop = logEl.value.scrollHeight
    }
  })
}, { deep: true })

onMounted(async () => {
  burstStore.fetchList()
  taskStore.resumeIfActive()
  await refreshFilterOptions()
})

async function refreshFilterOptions() {
  try {
    const opts = await burstAPI.filterOptions(confidenceMin.value)
    filterOpts.species = opts.species
    filterOpts.cameras = opts.cameras
  } catch {}
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) selected.value = new Set()
}

function toggleSelect(id: string) {
  const s = new Set(selected.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selected.value = s
}

function selectAll() {
  if (selected.value.size > 0) {
    selected.value = new Set()
  } else {
    selected.value = new Set(burstStore.list.map(b => b.id))
  }
}

async function batchDelete() {
  const ids = [...selected.value]
  if (!confirm(`确定删除选中的 ${ids.length} 个连拍组及其所有照片？此操作不可撤销。`)) return
  deleting.value = true
  try {
    const res = await burstAPI.batchDelete(ids)
    toast.success(`已删除 ${res.deleted_groups} 个连拍组，${res.deleted_photos} 张照片`)
    selected.value = new Set()
    selectMode.value = false
    await burstStore.fetchList()
    await refreshFilterOptions()
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    deleting.value = false
  }
}

async function detectBursts() {
  detecting.value = true
  showDetectDialog.value = false
  try {
    const task = await photoAPI.detectBursts(detectThreshold.value, detectMinCount.value)
    toast.info('连拍检测任务已提交')
    await taskAPI.poll((task as any).task_id ?? task.id)
    toast.success('检测完成')
    await burstStore.fetchList()
    await refreshFilterOptions()
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    detecting.value = false
  }
}

async function recognizeAll() {
  if (taskStore.recognizing) return
  try {
    const res = await burstAPI.recognizeAll()
    if (res.total === 0) {
      toast.info('所有连拍照片已识别，无需重复操作')
      return
    }
    toast.info(`已提交识别任务（${res.total} 张待识别）`)
    taskStore.startTracking(res.task_id, res.total)
    const check = setInterval(() => {
      if (!taskStore.recognizing) {
        clearInterval(check)
        if (taskStore.recognizeProgress >= 100 || !taskStore.recognizeTaskId) {
          toast.success('全部识别完成')
          burstStore.fetchList()
        }
      }
    }, 2000)
  } catch (e: any) {
    toast.error(e.message)
  }
}

async function stopRecognize() {
  await taskStore.cancelRecognize()
  toast.info('已停止识别任务')
  burstStore.fetchList()
}

function resetAll() {
  confidenceMin.value = 70
  burstStore.resetFilters()
  refreshFilterOptions()
}

function formatDate(s: string | null | undefined) {
  if (!s) return ''
  return s.slice(0, 16).replace('T', ' ')
}
</script>
