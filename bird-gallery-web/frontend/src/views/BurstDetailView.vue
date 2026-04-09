<template>
  <div class="max-w-5xl mx-auto px-5 py-6">
    <Spinner v-if="loading" />
    <div v-else-if="!burstStore.current" class="text-center py-20 text-text-tertiary dark:text-text-on-dark-tertiary">连拍组不存在</div>
    <div v-else class="flex flex-col gap-6">
      <!-- 导航 -->
      <div class="flex items-center gap-2">
        <button @click="$router.back()" class="flex items-center gap-1 text-sm text-text-tertiary dark:text-text-on-dark-tertiary hover:text-text-primary dark:hover:text-text-on-dark">
          <ArrowLeft class="w-4 h-4" /> 返回
        </button>
        <span class="text-black/10 dark:text-white/20">|</span>
        <span class="text-sm font-medium text-text-primary dark:text-text-on-dark">连拍组 · {{ burst.photo_count }} 张</span>
      </div>

      <!-- 识别进度条（与照片库一致） -->
      <div v-if="recognizing" class="card-apple dark:bg-surface-card-dark p-4">
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

      <!-- 帧列表（横向滚动）-->
      <div class="card-apple dark:bg-surface-card-dark p-4">
        <h3 class="font-semibold text-text-primary dark:text-text-on-dark mb-3 text-sm">帧预览</h3>
        <div class="flex gap-2 overflow-x-auto pb-2">
          <div
            v-for="(photo, i) in burst.photos"
            :key="photo.id"
            class="shrink-0 cursor-pointer rounded-lg overflow-hidden border-2 transition-all"
            :class="selectedIdx === i ? 'border-apple-blue' : 'border-transparent'"
            style="width: 80px; height: 80px;"
            @click="selectedIdx = i"
          >
            <img
              :src="`/api/photos/${photo.id}/thumbnail?size=sm`"
              class="w-full h-full object-cover"
              loading="lazy"
            />
          </div>
        </div>
      </div>

      <!-- 主视图 + 合成控制 -->
      <div class="flex gap-6">
        <!-- 当前帧大图 -->
        <div class="flex-1">
          <div v-if="currentPhoto" class="bg-black rounded-xl overflow-hidden flex items-center justify-center" style="min-height: 300px;">
            <img
              :src="`/api/photos/${currentPhoto.id}/thumbnail?size=lg`"
              class="max-w-full max-h-[50vh] object-contain"
            />
          </div>
          <div v-if="currentPhoto" class="mt-3 card-apple dark:bg-surface-card-dark p-3 text-sm text-text-secondary dark:text-text-on-dark-secondary">
            <span>帧 {{ selectedIdx + 1 }} / {{ burst.photo_count }}</span>
            <span v-if="currentPhoto.exif_datetime" class="ml-3">{{ currentPhoto.exif_datetime }}</span>
            <span v-if="currentPhoto.species_cn" class="ml-3 font-medium text-apple-blue">{{ currentPhoto.species_cn }}</span>
          </div>
        </div>

        <!-- 右侧：识别+合成 -->
        <div class="w-72 flex flex-col gap-4">
          <!-- 识别按钮 -->
          <div class="card-apple dark:bg-surface-card-dark p-4">
            <h3 class="font-semibold text-text-primary dark:text-text-on-dark mb-2 text-sm">鸟种识别</h3>
            <button
              @click="recognize"
              :disabled="recognizing"
              class="w-full py-1.5 btn-primary text-sm flex items-center justify-center gap-1.5"
            >
              <Zap class="w-4 h-4" />
              {{ recognizing ? '识别中…' : '批量识别此组' }}
            </button>
          </div>

          <!-- 合成视频 -->
          <div class="card-apple dark:bg-surface-card-dark p-4">
            <h3 class="font-semibold text-text-primary dark:text-text-on-dark mb-3 text-sm">合成视频</h3>
            <div class="flex flex-col gap-2">
              <div>
                <label class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary">帧率（fps）</label>
                <input
                  v-model.number="framerate"
                  type="range"
                  min="1"
                  max="30"
                  class="w-full mt-1"
                />
                <span class="text-xs text-text-secondary dark:text-text-on-dark-secondary">{{ framerate }} fps</span>
              </div>
              <div>
                <label class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary">分辨率</label>
                <select v-model="resolution" class="w-full mt-1 px-2 py-1 text-sm bg-surface-light dark:bg-white/10 border-0 rounded-lg dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40">
                  <option value="1280x720">720p</option>
                  <option value="1920x1080">1080p</option>
                  <option value="3840x2160">4K</option>
                </select>
              </div>
              <button
                @click="synthesize"
                :disabled="synthesizing"
                class="w-full py-1.5 bg-text-primary dark:bg-white text-white dark:text-black text-sm rounded-lg hover:opacity-80 disabled:opacity-50 transition-colors"
              >
                {{ synthesizing ? `合成中… ${synthProgress}%` : '生成视频' }}
              </button>
            </div>
          </div>

          <!-- 视频预览 -->
          <div v-if="videoReady" class="card-apple dark:bg-surface-card-dark p-4">
            <h3 class="font-semibold text-text-primary dark:text-text-on-dark mb-2 text-sm">合成预览</h3>
            <video
              controls
              class="w-full rounded"
              :key="videoVersion"
              :src="`${burstAPI.videoUrl(burst.id)}?v=${videoVersion}`"
            />
            <a
              :href="burstAPI.videoUrl(burst.id)"
              download
              class="mt-2 flex items-center justify-center gap-1.5 text-xs text-apple-link-light dark:text-apple-link-dark hover:underline"
            >
              <Download class="w-3 h-3" /> 下载视频
            </a>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Download, Zap, Square } from 'lucide-vue-next'
import { useBurstStore } from '@/stores/burstStore'
import { useToastStore } from '@/stores/toastStore'
import { useTaskStore } from '@/stores/taskStore'
import { burstAPI } from '@/api/bursts'
import { taskAPI } from '@/api/admin'
import Spinner from '@/components/common/Spinner.vue'

const route = useRoute()
const burstStore = useBurstStore()
const toast = useToastStore()
const taskStore = useTaskStore()
const loading = ref(true)
const selectedIdx = ref(0)
const framerate = ref(20)
const resolution = ref('1920x1080')
const synthesizing = ref(false)
const synthProgress = ref(0)
const videoReady = ref(false)
const videoVersion = ref(0)
const logEl = ref<HTMLElement | null>(null)

const burst = computed(() => burstStore.current!)
const currentPhoto = computed(() => burst.value?.photos?.[selectedIdx.value])
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
  try {
    await burstStore.fetchBurst(route.params.id as string)
    videoReady.value = (burstStore.current as any)?.['video_path'] != null
  } finally {
    loading.value = false
  }
  taskStore.resumeIfActive()
})

async function recognize() {
  if (taskStore.recognizing) return
  try {
    const res = await burstAPI.recognize(burst.value.id)
    const total = (res as any).total ?? 0
    if (total === 0) {
      toast.info('此组所有照片已识别，无需重复操作')
      return
    }
    const taskId = (res as any).task_id ?? (res as any).id
    toast.info(`已提交识别任务（${total} 张待识别）`)
    taskStore.startTracking(taskId, total)
    const check = setInterval(() => {
      if (!taskStore.recognizing) {
        clearInterval(check)
        if (taskStore.recognizeProgress >= 100 || !taskStore.recognizeTaskId) {
          toast.success('识别完成')
          burstStore.fetchBurst(burst.value.id)
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
  burstStore.fetchBurst(burst.value.id)
}

async function synthesize() {
  synthesizing.value = true
  synthProgress.value = 0
  videoReady.value = false
  try {
    const task = await burstAPI.synthesize(burst.value.id, framerate.value, resolution.value)
    toast.info('合成任务已提交')
    const taskId = (task as any).task_id ?? task.id
    await new Promise<void>((resolve, reject) => {
      const tick = async () => {
        const t = await taskAPI.get(taskId)
        synthProgress.value = t.progress ?? 0
        if (t.status === 'done') return resolve()
        if (t.status === 'error') return reject(new Error(t.error_msg ?? '合成失败'))
        setTimeout(tick, 1500)
      }
      tick().catch(reject)
    })
    videoVersion.value++
    videoReady.value = true
    toast.success('视频合成完成')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    synthesizing.value = false
  }
}
</script>
