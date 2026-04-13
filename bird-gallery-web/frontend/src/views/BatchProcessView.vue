<template>
  <div class="max-w-4xl mx-auto py-4 sm:py-6 px-3 sm:px-4">
    <h1 class="text-xl sm:text-2xl font-semibold mb-4 sm:mb-6 text-text-primary dark:text-text-on-dark font-display">RAW 批量处理</h1>

    <!-- 任务进行中 -->
    <div v-if="store.running" class="space-y-4">
      <div class="card-apple dark:bg-surface-card-dark border-l-4 border-l-apple-blue p-6">
        <h2 class="text-lg font-semibold mb-3 text-text-primary dark:text-text-on-dark text-text-primary dark:text-text-on-dark">处理中...</h2>
        <p class="text-sm text-text-secondary dark:text-text-on-dark-secondary mb-2">{{ store.statusText }}</p>

        <!-- 总进度 -->
        <div class="w-full bg-black/5 dark:bg-white/10 rounded-full h-3 mb-4">
          <div
            class="bg-apple-blue h-3 rounded-full transition-all duration-300"
            :style="{ width: store.progress + '%' }"
          />
        </div>

        <!-- 阶段进度 -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-center dark:text-text-on-dark-tertiary">
          <div v-for="(label, key) in phaseLabels" :key="key">
            <div class="mb-1 text-text-tertiary dark:text-text-on-dark-tertiary">{{ label }}</div>
            <div class="w-full bg-black/5 dark:bg-white/10 rounded h-1.5">
              <div
                class="bg-emerald-500 h-1.5 rounded transition-all"
                :style="{ width: (store.phaseProgress[key] || 0) + '%' }"
              />
            </div>
          </div>
        </div>

        <div class="mt-4 flex items-center justify-between text-sm text-text-tertiary dark:text-text-on-dark-tertiary">
          <span>{{ store.completed }} / {{ store.total }} 完成</span>
          <button
            @click="store.cancel()"
            class="px-4 py-1.5 text-red-500 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10"
          >
            取消
          </button>
        </div>
      </div>
    </div>

    <!-- 完成/错误状态 -->
    <div v-else-if="store.status === 'done'" class="mb-6">
      <div class="card-apple dark:bg-surface-card-dark border-l-4 border-l-emerald-500 p-6 mb-6">
        <h2 class="text-lg font-semibold text-emerald-600 dark:text-emerald-400 mb-2">处理完成</h2>
        <p class="text-sm text-text-secondary dark:text-text-on-dark-secondary">
          共 {{ store.completed }} 张完成，{{ store.failed }} 张失败
        </p>
        <button
          @click="resetForm"
          class="mt-3 btn-primary"
        >
          开始新任务
        </button>
      </div>

      <!-- 结果照片画廊 -->
      <div v-if="store.results && store.results.items.length > 0">
        <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h2 class="text-lg font-semibold">处理结果预览</h2>
          <div class="flex items-center gap-2 sm:gap-3 text-sm text-text-tertiary dark:text-text-on-dark-tertiary flex-wrap">
            <span>共 {{ doneItems.length }} 张</span>
            <span>第 {{ galleryPage }} / {{ galleryTotalPages }} 页</span>
            <button
              :disabled="galleryPage <= 1"
              @click="galleryPage--"
              class="px-2 py-1 border border-black/10 dark:border-white/20 rounded-lg disabled:opacity-30 dark:text-text-on-dark"
            >上一页</button>
            <button
              :disabled="galleryPage >= galleryTotalPages"
              @click="galleryPage++"
              class="px-2 py-1 border border-black/10 dark:border-white/20 rounded-lg disabled:opacity-30 dark:text-text-on-dark"
            >下一页</button>
          </div>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          <div
            v-for="item in pagedItems"
            :key="item.photo_id"
            class="relative group cursor-pointer overflow-hidden rounded-lg border border-black/5 dark:border-white/10 bg-surface-light dark:bg-surface-card-dark"
            @click="openLightbox(item)"
          >
            <img
              :src="thumbUrl(item)"
              :alt="item.filename"
              class="w-full aspect-[4/3] object-cover transition-transform group-hover:scale-105"
              loading="lazy"
            />
            <div class="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/60 to-transparent p-2">
              <p class="text-xs text-white truncate">{{ item.filename }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Lightbox 全屏预览 -->
      <div
        v-if="lightboxItem"
        class="fixed inset-0 z-50 bg-black/90 flex items-center justify-center"
        @click.self="lightboxItem = null"
      >
        <button
          @click="lightboxItem = null"
          class="absolute top-4 right-4 text-white text-3xl hover:text-gray-300 z-10"
        >&times;</button>
        <button
          v-if="lightboxIndex > 0"
          @click="lightboxIndex--; lightboxItem = doneItems[lightboxIndex]"
          class="absolute left-4 text-white text-4xl hover:text-gray-300 z-10"
        >&#8249;</button>
        <button
          v-if="lightboxIndex < doneItems.length - 1"
          @click="lightboxIndex++; lightboxItem = doneItems[lightboxIndex]"
          class="absolute right-16 text-white text-4xl hover:text-gray-300 z-10"
        >&#8250;</button>
        <img
          :src="fullUrl(lightboxItem)"
          :alt="lightboxItem.filename"
          class="max-h-[90vh] max-w-[95vw] object-contain"
        />
        <div class="absolute bottom-4 text-center text-white text-sm">
          {{ lightboxItem.filename }} ({{ lightboxIndex + 1 }} / {{ doneItems.length }})
        </div>
      </div>
    </div>

    <div v-else-if="store.status === 'error'" class="mb-6">
      <div class="card-apple dark:bg-surface-card-dark border-l-4 border-l-red-500 p-6">
        <h2 class="text-lg font-semibold text-red-500 mb-2">处理失败</h2>
        <p class="text-sm text-red-400">{{ store.errorMsg }}</p>
        <button
          @click="resetForm"
          class="mt-3 btn-secondary"
        >
          重试
        </button>
      </div>
    </div>

    <!-- 配置表单 -->
    <form v-else @submit.prevent="handleSubmit" class="space-y-6">
      <!-- 筛选 -->
      <section class="card-apple dark:bg-surface-card-dark p-5">
        <h2 class="font-semibold mb-3 text-text-primary dark:text-text-on-dark">照片筛选</h2>
        <label class="flex items-center gap-3">
          <span class="text-sm text-text-secondary dark:text-text-on-dark-secondary w-20">最低星级</span>
          <select v-model.number="config.min_rating" class="bg-surface-light dark:bg-white/10 border-0 rounded-lg px-3 py-1.5 text-sm dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40">
            <option :value="0">0 星及以上</option>
            <option :value="1">1 星及以上</option>
            <option :value="2">2 星及以上</option>
            <option :value="3">3 星</option>
          </select>
        </label>
      </section>

      <!-- 降噪 -->
      <section class="card-apple dark:bg-surface-card-dark p-5">
        <h2 class="font-semibold mb-3 text-text-primary dark:text-text-on-dark">降噪设置</h2>
        <label class="flex items-center gap-2 mb-3">
          <input type="checkbox" v-model="config.denoise_enabled" class="rounded" />
          <span class="text-sm">启用 DxO PureRAW 降噪</span>
        </label>
        <div v-if="config.denoise_enabled" class="space-y-3 ml-6">
          <label class="flex items-center gap-3">
            <span class="text-sm text-text-secondary dark:text-text-on-dark-secondary w-20">算法</span>
            <select v-model="config.denoise_algorithm" class="bg-surface-light dark:bg-white/10 border-0 rounded-lg px-3 py-1.5 text-sm dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40">
              <option value="DeepPRIME_XD3">DeepPRIME XD3</option>
              <option value="DeepPRIME_3">DeepPRIME 3</option>
            </select>
          </label>
          <label class="flex items-center gap-3">
            <span class="text-sm text-text-secondary dark:text-text-on-dark-secondary w-20">亮度降噪</span>
            <input type="range" v-model.number="config.denoise_luminance" min="0" max="100" class="flex-1" />
            <span class="text-sm w-8 dark:text-text-on-dark-secondary text-right dark:text-text-on-dark-secondary">{{ config.denoise_luminance }}</span>
          </label>
          <label class="flex items-center gap-3">
            <span class="text-sm text-text-secondary dark:text-text-on-dark-secondary w-20">色度降噪</span>
            <input type="range" v-model.number="config.denoise_chrominance" min="0" max="100" class="flex-1" />
            <span class="text-sm w-8 dark:text-text-on-dark-secondary text-right dark:text-text-on-dark-secondary">{{ config.denoise_chrominance }}</span>
          </label>
        </div>
      </section>

      <!-- 调色 -->
      <section class="card-apple dark:bg-surface-card-dark p-5">
        <h2 class="font-semibold mb-3 text-text-primary dark:text-text-on-dark">调色设置</h2>
        <label class="flex items-center gap-2 mb-3">
          <input type="checkbox" v-model="config.auto_tone_enabled" class="rounded" />
          <span class="text-sm">启用调色阶段</span>
        </label>
        <div v-if="config.auto_tone_enabled" class="ml-6 space-y-4">
          <div class="flex flex-wrap gap-4">
            <label class="flex items-center gap-2">
              <input type="radio" v-model="config.tone_mode" value="reference_version" />
              <span class="text-sm">使用单张 RAW 编辑版本模板</span>
            </label>
            <label class="flex items-center gap-2">
              <input type="radio" v-model="config.tone_mode" value="legacy_auto" />
              <span class="text-sm">使用旧自动调色管线</span>
            </label>
          </div>

          <div v-if="config.tone_mode === 'reference_version'" class="space-y-3 rounded-2xl border border-black/5 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/[0.03]">
            <p class="text-sm text-text-secondary dark:text-text-on-dark-secondary">
              先在单张 RAW 编辑页保存一个版本，这里会把该版本的调色参数批量套用到所有照片。
            </p>

            <div v-if="tonePresets.length > 0" class="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]">
              <label class="space-y-2">
                <span class="text-sm text-text-secondary dark:text-text-on-dark-secondary">模板版本</span>
                <select
                  v-model.number="selectedTonePresetId"
                  class="w-full bg-surface-light dark:bg-white/10 border-0 rounded-lg px-3 py-2 text-sm dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40"
                >
                  <option v-for="preset in tonePresets" :key="preset.version_id" :value="preset.version_id">
                    {{ tonePresetLabel(preset) }}
                  </option>
                </select>
              </label>

              <div v-if="selectedTonePreset" class="overflow-hidden rounded-xl border border-black/5 bg-surface-light dark:border-white/10 dark:bg-surface-card-dark">
                <img
                  v-if="selectedTonePreset.preview_url"
                  :src="selectedTonePreset.preview_url"
                  :alt="selectedTonePreset.filename"
                  class="h-32 w-full object-cover"
                />
                <div class="space-y-1 p-3 text-sm">
                  <div class="font-medium text-text-primary dark:text-text-on-dark">{{ selectedTonePreset.filename }}</div>
                  <div class="text-text-secondary dark:text-text-on-dark-secondary">版本 V{{ selectedTonePreset.version_no }}{{ selectedTonePreset.is_current ? ' · 当前版本' : '' }}</div>
                  <div class="text-text-tertiary dark:text-text-on-dark-tertiary">{{ selectedTonePreset.is_auto_tone ? '自动调色版本' : '手动调色版本' }}</div>
                </div>
              </div>
            </div>

            <p v-else class="text-sm text-amber-600 dark:text-amber-400">
              还没有可用的 RAW 编辑版本。先到单张照片详情页保存一个版本，再回来批量套用。
            </p>
          </div>

          <div v-else class="flex gap-4">
            <label class="flex items-center gap-2">
              <input type="radio" v-model="config.auto_tone_tool" value="lightroom" />
              <span class="text-sm">Lightroom Classic</span>
            </label>
            <label class="flex items-center gap-2">
              <input type="radio" v-model="config.auto_tone_tool" value="darktable" />
              <span class="text-sm">darktable-cli</span>
            </label>
          </div>
        </div>
      </section>

      <!-- 裁切 -->
      <section class="card-apple dark:bg-surface-card-dark p-5">
        <h2 class="font-semibold mb-3 text-text-primary dark:text-text-on-dark">裁切设置</h2>
        <div class="flex flex-wrap gap-2 mb-3">
          <button
            v-for="(preset, key) in cropPresets"
            :key="key"
            type="button"
            @click="config.crop_preset = key as string"
            class="px-3 py-1.5 text-sm rounded border transition-colors"
            :class="config.crop_preset === key
              ? 'bg-apple-blue text-white border-apple-blue'
              : 'bg-surface-light dark:bg-white/10 text-text-secondary dark:text-text-on-dark-secondary border-black/10 dark:border-white/20 hover:border-apple-blue'"
          >
            {{ preset.label }}
          </button>
        </div>
      </section>

      <!-- 水印 -->
      <section class="card-apple dark:bg-surface-card-dark p-5">
        <h2 class="font-semibold mb-3 text-text-primary dark:text-text-on-dark">水印设置</h2>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="(preset, key) in watermarkPresets"
            :key="key"
            type="button"
            @click="config.watermark_preset = key as string"
            class="px-3 py-1.5 text-sm rounded border transition-colors"
            :class="config.watermark_preset === key
              ? 'bg-apple-blue text-white border-apple-blue'
              : 'bg-surface-light dark:bg-white/10 text-text-secondary dark:text-text-on-dark-secondary border-black/10 dark:border-white/20 hover:border-apple-blue'"
          >
            {{ preset.label }}
          </button>
        </div>
      </section>

      <!-- 输出 -->
      <section class="card-apple dark:bg-surface-card-dark p-5">
        <h2 class="font-semibold mb-3 text-text-primary dark:text-text-on-dark">输出设置</h2>
        <div class="flex gap-6">
          <label class="flex items-center gap-3">
            <span class="text-sm text-text-secondary dark:text-text-on-dark-secondary w-12">格式</span>
            <select v-model="config.output_format" class="bg-surface-light dark:bg-white/10 border-0 rounded-lg px-3 py-1.5 text-sm dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40">
              <option value="jpeg">JPEG</option>
              <option value="tiff">TIFF</option>
              <option value="png">PNG</option>
            </select>
          </label>
          <label v-if="config.output_format === 'jpeg'" class="flex items-center gap-3">
            <span class="text-sm text-text-secondary dark:text-text-on-dark-secondary w-12">质量</span>
            <input type="range" v-model.number="config.output_quality" min="70" max="100" class="w-32" />
            <span class="text-sm w-8 dark:text-text-on-dark-secondary">{{ config.output_quality }}</span>
          </label>
        </div>
      </section>

      <!-- 提交 -->
      <div class="flex justify-end">
        <button
          type="submit"
          :disabled="submitting"
          class="px-6 py-3 bg-apple-blue text-white font-semibold rounded-xl
                 hover:bg-apple-blue/90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ submitting ? '提交中...' : '开始处理' }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useBatchProcessStore } from '@/stores/batchProcessStore'
import type {
  BatchProcessConfig,
  BatchProcessResultItem,
  BatchTonePresetSummary,
} from '@/types'

const store = useBatchProcessStore()
const submitting = ref(false)

const phaseLabels: Record<string, string> = {
  filter: '筛选',
  denoise: '降噪',
  tone: '调色',
  crop: '裁切',
}

const config = reactive<BatchProcessConfig>({
  min_rating: 2,
  denoise_enabled: true,
  denoise_algorithm: 'DeepPRIME_XD3',
  denoise_luminance: 40,
  denoise_chrominance: 50,
  auto_tone_enabled: true,
  tone_mode: 'reference_version',
  reference_photo_id: null,
  reference_version_id: null,
  auto_tone_tool: 'lightroom',
  crop_preset: '4k_wallpaper',
  watermark_preset: 'simple_copyright',
  output_format: 'jpeg',
  output_quality: 95,
})

const cropPresets = ref<Record<string, { label: string }>>({})
const watermarkPresets = ref<Record<string, { label: string }>>({})
const tonePresets = ref<BatchTonePresetSummary[]>([])
const selectedTonePresetId = ref<number | null>(null)

// Gallery state
const galleryPage = ref(1)
const galleryPageSize = 24
const lightboxItem = ref<BatchProcessResultItem | null>(null)
const lightboxIndex = ref(0)

const doneItems = computed(() =>
  (store.results?.items || []).filter(i => i.phase === 'done')
)

const galleryTotalPages = computed(() =>
  Math.max(1, Math.ceil(doneItems.value.length / galleryPageSize))
)

const pagedItems = computed(() => {
  const start = (galleryPage.value - 1) * galleryPageSize
  return doneItems.value.slice(start, start + galleryPageSize)
})

const selectedTonePreset = computed(() =>
  tonePresets.value.find((preset) => preset.version_id === selectedTonePresetId.value) ?? null,
)

function thumbUrl(item: BatchProcessResultItem) {
  return `/api/batch-process/${store.taskId}/photo/${item.photo_id}?thumb=true`
}

function fullUrl(item: BatchProcessResultItem) {
  return `/api/batch-process/${store.taskId}/photo/${item.photo_id}`
}

function openLightbox(item: BatchProcessResultItem) {
  const idx = doneItems.value.findIndex(i => i.photo_id === item.photo_id)
  lightboxIndex.value = idx >= 0 ? idx : 0
  lightboxItem.value = item
}

function tonePresetLabel(preset: BatchTonePresetSummary) {
  const tags = [`V${preset.version_no}`]
  if (preset.is_current) {
    tags.push('当前版本')
  }
  if (preset.is_auto_tone) {
    tags.push('自动')
  }
  return `${preset.filename} · ${tags.join(' · ')}`
}

function syncTonePresetSelection() {
  const preset = selectedTonePreset.value
  config.reference_photo_id = preset?.photo_id ?? null
  config.reference_version_id = preset?.version_id ?? null
}

onMounted(async () => {
  store.tryRestore()
  try {
    await store.fetchOptions()
    if (store.options) {
      cropPresets.value = store.options.crop_presets
      watermarkPresets.value = store.options.watermark_presets
      tonePresets.value = store.options.tone_presets || []
      if (tonePresets.value.length > 0) {
        selectedTonePresetId.value = tonePresets.value[0].version_id
        syncTonePresetSelection()
      } else {
        config.tone_mode = 'legacy_auto'
      }
    }
  } catch {}
  // If not running, try to load the latest completed task for display
  if (!store.running && store.status === 'idle') {
    await store.loadLatestDone()
  }
})

async function handleSubmit() {
  syncTonePresetSelection()
  if (config.auto_tone_enabled && config.tone_mode === 'reference_version' && !selectedTonePreset.value) {
    alert('请先选择一个 RAW 编辑版本模板')
    return
  }

  submitting.value = true
  try {
    await store.start({
      ...config,
      reference_photo_id: config.tone_mode === 'reference_version'
        ? selectedTonePreset.value?.photo_id ?? null
        : null,
      reference_version_id: config.tone_mode === 'reference_version'
        ? selectedTonePreset.value?.version_id ?? null
        : null,
    })
  } catch (e: unknown) {
    alert(e instanceof Error ? e.message : '启动失败')
  } finally {
    submitting.value = false
  }
}

function resetForm() {
  store.$reset()
  if (tonePresets.value.length > 0) {
    selectedTonePresetId.value = tonePresets.value[0].version_id
    config.tone_mode = 'reference_version'
    syncTonePresetSelection()
    return
  }
  selectedTonePresetId.value = null
  config.reference_photo_id = null
  config.reference_version_id = null
  config.tone_mode = 'legacy_auto'
}
</script>
