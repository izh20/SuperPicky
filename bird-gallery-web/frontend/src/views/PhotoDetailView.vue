<template>
  <div class="max-w-6xl mx-auto">
    <Spinner v-if="loading" />
    <div v-else-if="!photo" class="text-center py-20 text-gray-400">照片不存在</div>
    <div v-else class="flex gap-6">
      <!-- 左：图片查看 -->
      <div class="flex-1 flex flex-col gap-4">
        <!-- 导航 -->
        <div class="flex items-center gap-2">
          <button @click="$router.back()" class="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
            <ArrowLeft class="w-4 h-4" /> 返回
          </button>
          <span class="text-gray-300">|</span>
          <span class="text-sm text-gray-500 flex-1 truncate">{{ photo.filename }}</span>
          <div class="flex items-center gap-1 ml-auto">
            <button
              :disabled="!prevId"
              @click="goTo(prevId!)"
              class="px-2 py-1 text-sm rounded hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed text-gray-500"
              title="上一张"
            >
              <ChevronLeft class="w-4 h-4" />
            </button>
            <span class="text-xs text-gray-400">{{ currentIndex >= 0 ? `${currentIndex + 1}/${photoStore.items.length}` : '' }}</span>
            <button
              :disabled="!nextId"
              @click="goTo(nextId!)"
              class="px-2 py-1 text-sm rounded hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed text-gray-500"
              title="下一张"
            >
              <ChevronRight class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- 图片 + 检测框 -->
        <div class="bg-black rounded-xl overflow-hidden flex items-center justify-center relative" style="min-height: 400px;">
          <img
            ref="imgEl"
            :src="`/api/photos/${photo.id}/thumbnail?size=lg`"
            :alt="photo.filename"
            class="max-w-full max-h-[70vh] object-contain"
            @load="onImageLoad"
          />
          <!-- 检测框覆盖层 -->
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
                class="text-xs fill-green-500 font-semibold" style="font-size: 12px;"
              >{{ b.species_cn }} {{ b.confidence.toFixed(1) }}%</text>
            </template>
          </svg>
        </div>

        <!-- 检测框切换 -->
        <div class="flex items-center gap-4 text-sm text-gray-500" v-if="hasDetectionBoxes">
          <label class="flex items-center gap-1 cursor-pointer">
            <input type="checkbox" v-model="showBoxes" class="rounded" />
            显示检测框
          </label>
        </div>

        <!-- 过程标注图（自动显示，只要照片有识别结果） -->
        <div v-if="hasBirds && !annotatedError" class="bg-gray-900 rounded-xl overflow-hidden flex items-center justify-center" style="min-height: 200px;">
          <img
            :src="`/api/photos/${photo.id}/annotated`"
            :alt="`${photo.filename} - 标注图`"
            class="max-w-full max-h-[50vh] object-contain"
            @error="onAnnotatedError"
          />
        </div>
        <p v-if="hasBirds && annotatedError" class="text-xs text-gray-400">
          暂无标注数据，请重新识别该照片以生成过程图
        </p>

        <!-- 操作栏 -->
        <div class="flex gap-2">
          <button
            @click="recognize"
            :disabled="recognizing"
            class="flex items-center gap-1.5 px-3 py-1.5 bg-primary-600 text-white text-sm rounded hover:bg-primary-700 disabled:opacity-50 transition-colors"
          >
            <Cpu class="w-4 h-4" />
            <span v-if="recognizing">识别中…</span>
            <span v-else>识别鸟种</span>
          </button>
          <a
            :href="photoAPI.originalUrl(photo.id)"
            download
            class="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 text-gray-700 text-sm rounded hover:bg-gray-200 transition-colors"
          >
            <Download class="w-4 h-4" /> 下载
          </a>
          <button
            v-if="authStore.isAdmin"
            @click="deletePhoto"
            class="flex items-center gap-1.5 px-3 py-1.5 bg-red-50 text-red-600 text-sm rounded hover:bg-red-100 transition-colors ml-auto"
          >
            <Trash2 class="w-4 h-4" /> 删除
          </button>
        </div>
      </div>

      <!-- 右：元数据+识别结果 -->
      <div class="w-80 flex flex-col gap-4 text-sm">
        <!-- 评分 -->
        <div class="bg-white rounded-xl p-4 border border-gray-100">
          <h3 class="font-semibold text-gray-700 mb-2">评分</h3>
          <StarRating :rating="photo.score?.rating" />
          <div v-if="photo.score" class="mt-2 text-xs text-gray-400 space-y-0.5">
            <div v-if="photo.score.head_sharp != null">头部锐度: {{ photo.score.head_sharp?.toFixed(2) }}</div>
            <div v-if="photo.score.nima_score != null">美学评分: {{ photo.score.nima_score?.toFixed(2) }}</div>
          </div>
        </div>

        <!-- 识别结果 -->
        <div class="bg-white rounded-xl p-4 border border-gray-100">
          <h3 class="font-semibold text-gray-700 mb-2">识别结果</h3>
          <div v-if="photo.birds?.length" class="flex flex-col gap-2">
            <div
              v-for="b in photo.birds"
              :key="b.rank"
              class="flex items-center gap-2 p-2 rounded-lg"
              :class="b.rank === 1 ? 'bg-primary-50 border border-primary-200' : 'bg-gray-50'"
            >
              <span class="text-xs font-bold text-gray-400 w-4">{{ b.rank }}</span>
              <div class="flex-1 min-w-0">
                <p class="font-medium text-gray-800 truncate">{{ b.species_cn }}</p>
                <p class="text-xs text-gray-500 truncate">{{ b.species_en }}</p>
                <p class="text-xs text-gray-400 italic truncate">{{ b.scientific_name }}</p>
              </div>
              <span class="text-xs font-semibold text-primary-600">{{ b.confidence.toFixed(1) }}%</span>
            </div>
          </div>
          <p v-else class="text-gray-400">暂未识别</p>
        </div>

        <!-- EXIF -->
        <div class="bg-white rounded-xl p-4 border border-gray-100">
          <h3 class="font-semibold text-gray-700 mb-2">EXIF 信息</h3>
          <table class="w-full text-xs">
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
    </div>
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
