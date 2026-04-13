<template>
  <div class="max-w-lg mx-auto px-4 py-6 flex flex-col min-h-[calc(100vh-64px)]">
    <h1 class="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">拍照识鸟</h1>

    <!-- 图片预览区 -->
    <div
      class="relative w-full aspect-[4/3] rounded-2xl overflow-hidden bg-surface-light dark:bg-surface-card-dark border border-black/5 dark:border-white/10 mb-4"
    >
      <img
        v-if="previewUrl"
        :src="previewUrl"
        class="w-full h-full object-contain"
        alt="预览"
      />
      <!-- 检测框 -->
      <div
        v-if="previewUrl && result?.detection_box && imgNatural.w"
        class="absolute border-2 border-green-400 rounded"
        :style="boxStyle"
      />
      <div v-if="!previewUrl" class="flex flex-col items-center justify-center h-full text-gray-400 gap-2">
        <Search class="w-10 h-10" />
        <span class="text-sm">选择或拍摄一张鸟类照片</span>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="flex gap-3 mb-4">
      <button
        @click="cameraInput?.click()"
        class="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-apple-blue text-white font-medium text-sm active:brightness-90 transition-all"
      >
        <Camera class="w-5 h-5" />
        拍照
      </button>
      <button
        @click="galleryInput?.click()"
        class="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-white dark:bg-white/10 text-gray-700 dark:text-gray-200 font-medium text-sm border border-gray-200 dark:border-white/20 active:bg-gray-100 dark:active:bg-white/20 transition-all"
      >
        <ImageIcon class="w-5 h-5" />
        图库选择
      </button>
    </div>

    <!-- 识别按钮 -->
    <button
      v-if="selectedFile && !identifying"
      @click="doIdentify"
      class="w-full py-3 rounded-xl bg-green-600 text-white font-medium text-sm active:brightness-90 transition-all mb-4"
    >
      开始识别
    </button>
    <button
      v-if="identifying"
      disabled
      class="w-full py-3 rounded-xl bg-green-600/70 text-white font-medium text-sm animate-pulse mb-4"
    >
      识别中，请稍候…
    </button>

    <!-- 识别结果 -->
    <div v-if="result" class="flex-1">
      <h2 class="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-2">识别结果</h2>
      <div v-if="result.birds.length === 0" class="text-sm text-gray-500">未检测到鸟类</div>
      <ul class="space-y-2">
        <li
          v-for="bird in result.birds"
          :key="bird.rank"
          class="flex items-center gap-3 p-3 rounded-xl bg-white dark:bg-surface-card-dark border border-black/5 dark:border-white/10"
        >
          <span
            class="shrink-0 w-7 h-7 flex items-center justify-center rounded-full text-xs font-bold"
            :class="bird.rank === 1 ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' : 'bg-gray-100 text-gray-500 dark:bg-white/10 dark:text-gray-400'"
          >{{ bird.rank }}</span>
          <div class="flex-1 min-w-0">
            <div class="font-medium text-sm text-gray-800 dark:text-gray-100 truncate">
              {{ bird.species_cn || bird.species_en }}
            </div>
            <div class="text-xs text-gray-400 truncate">
              {{ bird.species_en }}
              <span v-if="bird.scientific_name" class="italic"> · {{ bird.scientific_name }}</span>
            </div>
          </div>
          <div class="shrink-0 text-right">
            <span class="text-sm font-semibold" :class="confidenceColor(bird.confidence)">
              {{ bird.confidence.toFixed(1) }}%
            </span>
            <div class="mt-1 w-16 h-1.5 rounded-full bg-gray-200 dark:bg-white/10 overflow-hidden">
              <div
                class="h-full rounded-full transition-all"
                :class="confidenceBarColor(bird.confidence)"
                :style="{ width: `${Math.min(bird.confidence, 100)}%` }"
              />
            </div>
          </div>
        </li>
      </ul>
    </div>

    <!-- 错误提示 -->
    <div v-if="errorMsg" class="mt-2 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
      {{ errorMsg }}
    </div>

    <!-- 隐藏的 file inputs -->
    <input
      ref="cameraInput"
      type="file"
      accept="image/*"
      capture="environment"
      class="hidden"
      @change="onFileChange($event)"
    />
    <input
      ref="galleryInput"
      type="file"
      accept="image/*"
      class="hidden"
      @change="onFileChange($event)"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { Camera, Image as ImageIcon, Search } from 'lucide-vue-next'
import { identifyAPI, type IdentifyResponse } from '@/api/identify'
import { useTaskStore } from '@/stores/taskStore'

const taskStore = useTaskStore()

const cameraInput = ref<HTMLInputElement>()
const galleryInput = ref<HTMLInputElement>()

const selectedFile = ref<File | null>(null)
const previewUrl = ref<string | null>(null)
const identifying = ref(false)
const result = ref<IdentifyResponse | null>(null)
const errorMsg = ref('')
const imgNatural = ref({ w: 0, h: 0 })

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  // 重置状态
  result.value = null
  errorMsg.value = ''
  selectedFile.value = file

  // 释放旧 URL
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(file)

  // 获取图片原始尺寸（用于检测框定位）
  const img = new Image()
  img.onload = () => {
    imgNatural.value = { w: img.naturalWidth, h: img.naturalHeight }
  }
  img.src = previewUrl.value

  // 清除 input value 以允许重复选择同一文件
  input.value = ''
}

async function doIdentify() {
  if (!selectedFile.value || identifying.value) return
  identifying.value = true
  errorMsg.value = ''
  result.value = null
  taskStore.setActiveTask('正在识别鸟类…', 50)
  try {
    result.value = await identifyAPI.recognize(selectedFile.value)
    if (!result.value.birds?.length) {
      errorMsg.value = '未检测到鸟类，请尝试更清晰的照片'
    }
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '识别失败'
    errorMsg.value = msg
  } finally {
    identifying.value = false
    taskStore.clearActiveTask()
  }
}

const boxStyle = computed(() => {
  const box = result.value?.detection_box
  if (!box || box.length < 4 || !imgNatural.value.w) return {}
  const [x1, y1, x2, y2] = box
  const nw = imgNatural.value.w
  const nh = imgNatural.value.h
  return {
    left: `${(x1 / nw) * 100}%`,
    top: `${(y1 / nh) * 100}%`,
    width: `${((x2 - x1) / nw) * 100}%`,
    height: `${((y2 - y1) / nh) * 100}%`,
  }
})

function confidenceColor(c: number) {
  if (c >= 80) return 'text-green-600 dark:text-green-400'
  if (c >= 50) return 'text-yellow-600 dark:text-yellow-400'
  return 'text-gray-500 dark:text-gray-400'
}

function confidenceBarColor(c: number) {
  if (c >= 80) return 'bg-green-500'
  if (c >= 50) return 'bg-yellow-500'
  return 'bg-gray-400'
}

onUnmounted(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})
</script>
