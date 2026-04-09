<template>
  <div>
    <Spinner v-if="loading" class="py-20" />
    <div v-else-if="!photo" class="text-center py-20 text-text-tertiary">照片不存在</div>
    <template v-else>
      <!-- 暗色沉浸区：照片 -->
      <section class="bg-black relative">
        <!-- 顶部导航条 -->
        <div class="absolute top-0 inset-x-0 z-10 flex items-center justify-between px-5 py-3">
          <button @click="$router.back()" class="flex items-center gap-1 text-[14px] text-white/70 hover:text-white transition-colors">
            <ArrowLeft class="w-4 h-4" /> 返回
          </button>
          <span class="text-[14px] text-white/50 truncate max-w-xs">{{ photo.filename }}</span>
          <div class="flex items-center gap-2">
            <button
              :disabled="!prevId"
              @click="goTo(prevId!)"
              class="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white/80 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              title="上一张"
            >
              <ChevronLeft class="w-4 h-4" />
            </button>
            <span class="text-[12px] text-white/40 min-w-[4rem] text-center">{{ currentIndex >= 0 ? `${currentIndex + 1} / ${photoStore.items.length}` : '' }}</span>
            <button
              :disabled="!nextId"
              @click="goTo(nextId!)"
              class="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white/80 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              title="下一张"
            >
              <ChevronRight class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- 照片 -->
        <div class="flex items-center justify-center relative pt-12 pb-4 px-4" style="min-height: 50vh;">
          <img
            ref="imgEl"
            :src="`/api/photos/${photo.id}/thumbnail?size=lg`"
            :alt="photo.filename"
            class="max-w-full max-h-[70vh] object-contain"
            @load="onImageLoad"
          />
          <!-- 检测框 -->
          <svg
            v-if="showBoxes && imgRect"
            class="absolute pointer-events-none"
            :style="{ left: imgRect.left + 'px', top: imgRect.top + 'px', width: imgRect.width + 'px', height: imgRect.height + 'px' }"
          >
            <template v-for="b in photo.birds" :key="b.rank">
              <rect
                v-if="b.detection_box?.length === 4"
                :x="b.detection_box[0] / (photo.width ?? 1) * imgRect.width"
                :y="b.detection_box[1] / (photo.height ?? 1) * imgRect.height"
                :width="(b.detection_box[2] - b.detection_box[0]) / (photo.width ?? 1) * imgRect.width"
                :height="(b.detection_box[3] - b.detection_box[1]) / (photo.height ?? 1) * imgRect.height"
                fill="none" stroke="#22c55e" stroke-width="2" rx="2"
              />
              <text
                v-if="b.detection_box?.length === 4"
                :x="b.detection_box[0] / (photo.width ?? 1) * imgRect.width"
                :y="b.detection_box[1] / (photo.height ?? 1) * imgRect.height - 4"
                class="fill-emerald-400 font-semibold" style="font-size: 12px;"
              >{{ b.species_cn }} {{ b.confidence.toFixed(1) }}%</text>
            </template>
          </svg>
        </div>

        <!-- 照片下方：鸟种名 + 评分 + 操作 -->
        <div class="flex items-center justify-between px-5 pb-4">
          <div class="flex items-center gap-3">
            <StarRating :rating="photo.score?.rating" />
            <span v-if="photo.birds?.length" class="text-white/90 text-[17px] font-medium">
              {{ photo.birds[0].species_cn }}
            </span>
            <span v-else class="text-white/40 text-[14px]">未识别</span>
          </div>
          <div class="flex items-center gap-2">
            <label v-if="hasDetectionBoxes" class="flex items-center gap-1.5 text-[12px] text-white/50 cursor-pointer">
              <input type="checkbox" v-model="showBoxes" class="accent-apple-blue rounded" />
              检测框
            </label>
            <button
              @click="recognize"
              :disabled="recognizing"
              class="btn-primary !text-[14px] !px-3 !py-1.5 flex items-center gap-1.5"
            >
              <Cpu class="w-4 h-4" />
              {{ recognizing ? '识别中…' : '识别' }}
            </button>
            <a
              :href="photoAPI.originalUrl(photo.id)"
              download
              class="px-3 py-1.5 rounded-lg text-[14px] text-white/70 bg-white/10 hover:bg-white/20 transition-all flex items-center gap-1.5"
            >
              <Download class="w-4 h-4" /> 下载
            </a>
            <button
              v-if="authStore.isAdmin"
              @click="deletePhoto"
              class="px-3 py-1.5 rounded-lg text-[14px] text-red-400 bg-white/10 hover:bg-red-500/20 transition-all flex items-center gap-1.5"
            >
              <Trash2 class="w-4 h-4" /> 删除
            </button>
          </div>
        </div>
      </section>

      <!-- 标注图（可选） -->
      <section v-if="hasBirds && !annotatedError" class="bg-[#111] flex items-center justify-center py-4">
        <img
          :src="`/api/photos/${photo.id}/annotated`"
          :alt="`${photo.filename} - 标注图`"
          class="max-w-full max-h-[50vh] object-contain"
          @error="onAnnotatedError"
        />
      </section>

      <!-- 浅色信息区 -->
      <section class="bg-surface-light dark:bg-surface-card-dark py-8">
        <div class="max-w-5xl mx-auto px-5 grid md:grid-cols-3 gap-6">
          <!-- 识别结果 -->
          <div class="card-apple p-5 dark:bg-[#1c1c1e]">
            <h3 class="text-text-primary dark:text-text-on-dark mb-3">识别结果</h3>
            <div v-if="photo.birds?.length" class="flex flex-col gap-2">
              <div
                v-for="b in photo.birds"
                :key="b.rank"
                class="flex items-center gap-2 p-2.5 rounded-lg transition-colors"
                :class="b.rank === 1
                  ? 'bg-apple-blue/5 dark:bg-apple-blue/10'
                  : 'bg-surface-light dark:bg-white/5'"
              >
                <span class="text-[12px] font-bold text-text-tertiary dark:text-text-on-dark-tertiary w-4">{{ b.rank }}</span>
                <div class="flex-1 min-w-0">
                  <p class="font-medium text-text-primary dark:text-text-on-dark truncate">{{ b.species_cn }}</p>
                  <p class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary truncate">{{ b.species_en }}</p>
                  <p class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary italic truncate">{{ b.scientific_name }}</p>
                </div>
                <span class="text-[12px] font-semibold text-apple-blue">{{ b.confidence.toFixed(1) }}%</span>
              </div>
            </div>
            <p v-else class="text-text-tertiary dark:text-text-on-dark-tertiary text-[14px]">暂未识别</p>
          </div>

          <!-- 评分 -->
          <div class="card-apple p-5 dark:bg-[#1c1c1e]">
            <h3 class="text-text-primary dark:text-text-on-dark mb-3">评分</h3>
            <StarRating :rating="photo.score?.rating" />
            <div v-if="photo.score" class="mt-3 text-[14px] text-text-tertiary dark:text-text-on-dark-tertiary space-y-1">
              <div v-if="photo.score.head_sharp != null">头部锐度: {{ photo.score.head_sharp?.toFixed(2) }}</div>
              <div v-if="photo.score.nima_score != null">美学评分: {{ photo.score.nima_score?.toFixed(2) }}</div>
            </div>
          </div>

          <!-- EXIF -->
          <div class="card-apple p-5 dark:bg-[#1c1c1e]">
            <h3 class="text-text-primary dark:text-text-on-dark mb-3">EXIF 信息</h3>
            <table class="w-full text-[14px]">
              <tbody>
                <ExifRow label="相机" :value="`${photo.exif_make ?? ''} ${photo.exif_model ?? ''}`.trim()" />
                <ExifRow label="拍摄时间" :value="photo.exif_datetime" />
                <ExifRow label="ISO" :value="photo.exif_iso?.toString()" />
                <ExifRow label="光圈" :value="photo.exif_aperture ? `f/${photo.exif_aperture}` : undefined" />
                <ExifRow label="快门" :value="photo.exif_shutter_speed" />
                <ExifRow label="焦距" :value="photo.exif_focal_length ? `${photo.exif_focal_length}mm` : undefined" />
                <ExifRow label="分辨率" :value="photo.width && photo.height ? `${photo.width}×${photo.height}` : undefined" />
                <ExifRow label="文件大小" :value="formatBytes(photo.file_size)" />
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Cpu, Download, Trash2, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { photoAPI } from '@/api/photos'
import { useToastStore } from '@/stores/toastStore'
import { useAuthStore } from '@/stores/authStore'
import { usePhotoStore } from '@/stores/photoStore'
import type { PhotoDetail } from '@/types'
import Spinner from '@/components/common/Spinner.vue'
import StarRating from '@/components/common/StarRating.vue'
import ExifRow from '@/components/common/ExifRow.vue'

const route = useRoute()
const router = useRouter()
const toast = useToastStore()
const authStore = useAuthStore()
const photoStore = usePhotoStore()
const photo = ref<PhotoDetail | null>(null)
const loading = ref(true)
const recognizing = ref(false)
const imgEl = ref<HTMLImageElement | null>(null)
const imgRect = ref<{ left: number; top: number; width: number; height: number } | null>(null)
const showBoxes = ref(true)
const annotatedError = ref(false)

// 上下张导航
const currentIndex = computed(() => {
  if (!photo.value) return -1
  return photoStore.items.findIndex(p => p.id === photo.value!.id)
})
const prevId = computed(() => {
  const idx = currentIndex.value
  return idx > 0 ? photoStore.items[idx - 1].id : null
})
const nextId = computed(() => {
  const idx = currentIndex.value
  return idx >= 0 && idx < photoStore.items.length - 1 ? photoStore.items[idx + 1].id : null
})

async function goTo(id: string) {
  loading.value = true
  annotatedError.value = false
  try {
    photo.value = await photoAPI.get(id)
    router.replace(`/photos/${id}`)
  } catch {
    photo.value = null
  } finally {
    loading.value = false
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowLeft' && prevId.value) goTo(prevId.value)
  else if (e.key === 'ArrowRight' && nextId.value) goTo(nextId.value)
}

const hasDetectionBoxes = computed(() =>
  photo.value?.birds?.some(b => b.detection_box?.length === 4) ?? false
)

const hasBirds = computed(() =>
  (photo.value?.birds?.length ?? 0) > 0
)

function onImageLoad() {
  updateImgRect()
}

function onAnnotatedError() {
  annotatedError.value = true
}

function updateImgRect() {
  if (!imgEl.value) return
  const el = imgEl.value
  const parent = el.parentElement
  if (!parent) return
  const pr = parent.getBoundingClientRect()
  const ir = el.getBoundingClientRect()
  imgRect.value = { left: ir.left - pr.left, top: ir.top - pr.top, width: ir.width, height: ir.height }
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  try {
    photo.value = await photoAPI.get(route.params.id as string)
  } catch {
    photo.value = null
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})

// 快到列表末尾时预加载下一页
watch(currentIndex, (idx) => {
  if (idx >= 0 && idx >= photoStore.items.length - 3 && photoStore.items.length < photoStore.total) {
    photoStore.nextPage()
    photoStore.fetchPhotos()
  }
})

async function recognize() {
  if (!photo.value) return
  recognizing.value = true
  try {
    toast.info('识别中，请稍候…')
    await photoAPI.recognize(photo.value.id)
    photo.value = await photoAPI.get(photo.value.id)
    annotatedError.value = false
    toast.success('识别完成')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    recognizing.value = false
  }
}

async function deletePhoto() {
  if (!photo.value) return
  if (!confirm(`确认删除 ${photo.value.filename}？`)) return
  try {
    await photoAPI.delete(photo.value.id)
    toast.success('已删除')
    router.back()
  } catch (e: any) {
    toast.error(e.message)
  }
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}
</script>
