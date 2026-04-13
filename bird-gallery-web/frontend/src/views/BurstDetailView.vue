<template>
  <div class="max-w-5xl mx-auto px-3 sm:px-5 py-4 sm:py-6">
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
            <span class="text-sm font-medium text-text-primary dark:text-text-on-dark">{{ taskStore.recognizeTitle }}</span>
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
              <span v-if="item.head_sharp != null" class="text-text-tertiary dark:text-text-on-dark-tertiary">锐度 {{ item.head_sharp.toFixed(2) }}</span>
              <span v-if="item.nima_score != null" class="text-text-tertiary dark:text-text-on-dark-tertiary">美学 {{ item.nima_score.toFixed(2) }}</span>
              <span v-if="item.elapsed" class="text-text-tertiary dark:text-text-on-dark-tertiary ml-auto shrink-0">{{ item.elapsed }}s</span>
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
      <div class="flex flex-col lg:flex-row gap-4 lg:gap-6">
        <!-- 当前帧大图 -->
        <div class="flex-1 min-w-0">
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
        <div class="w-full lg:w-72 flex flex-col gap-4">
          <!-- 识别按钮 -->
          <div class="card-apple dark:bg-surface-card-dark p-4">
            <h3 class="font-semibold text-text-primary dark:text-text-on-dark mb-2 text-sm">鸟种识别</h3>
            <button
              @click="recognize"
              :disabled="recognizing || recognizeSubmitting"
              class="w-full py-1.5 btn-primary text-sm flex items-center justify-center gap-1.5"
            >
              <Zap class="w-4 h-4" />
              {{ recognizeSubmitting ? '提交中…' : recognizing ? `识别中… ${taskStore.recognizeProgress}%` : '批量识别此组' }}
            </button>
            <div v-if="recognizeSubmitting || recognizing" class="mt-3 rounded-lg bg-surface-light dark:bg-black/20 p-3">
              <div class="flex items-center justify-between text-xs mb-1.5">
                <span class="text-text-primary dark:text-text-on-dark font-medium">
                  {{ recognizeSubmitting ? '正在提交识别任务…' : taskStore.recognizeTitle }}
                </span>
                <span class="font-mono text-emerald-500">{{ recognizeSubmitting ? '...' : `${taskStore.recognizeProgress}%` }}</span>
              </div>
              <div class="w-full bg-black/5 dark:bg-white/10 rounded-full h-1.5">
                <div
                  class="bg-emerald-500 h-1.5 rounded-full transition-all duration-300"
                  :style="{ width: `${recognizeSubmitting ? 12 : taskStore.recognizeProgress}%` }"
                ></div>
              </div>
              <p class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mt-1.5">
                {{ recognizeSubmitting ? '后台任务创建后会自动开始轮询进度' : taskStore.recognizeStatusText }}
              </p>
            </div>
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
                :disabled="synthesizing || synthSubmitting"
                class="w-full py-1.5 bg-text-primary dark:bg-white text-white dark:text-black text-sm rounded-lg hover:opacity-80 disabled:opacity-50 transition-colors"
              >
                {{ synthSubmitting ? '提交中…' : synthesizing ? `合成中… ${synthProgress}%` : '生成视频' }}
              </button>
              <div v-if="synthSubmitting || synthesizing" class="rounded-lg bg-surface-light dark:bg-black/20 p-3">
                <div class="flex items-center justify-between text-xs mb-1.5">
                  <span class="text-text-primary dark:text-text-on-dark font-medium">{{ synthTitle }}</span>
                  <span class="font-mono text-apple-blue">{{ synthSubmitting ? '...' : `${synthProgress}%` }}</span>
                </div>
                <div class="w-full bg-black/5 dark:bg-white/10 rounded-full h-1.5">
                  <div
                    class="bg-apple-blue h-1.5 rounded-full transition-all duration-300"
                    :style="{ width: `${synthSubmitting ? 10 : synthProgress}%` }"
                  ></div>
                </div>
                <p class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mt-1.5">{{ synthStatusText }}</p>
              </div>
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

interface SynthesizePayload {
  phase?: string
  detail?: string
  processed?: number
  total?: number
}

function parseSynthesizePayload(resultJson: string | null): SynthesizePayload | null {
  if (!resultJson) return null
  try {
    const payload = JSON.parse(resultJson)
    if (payload && typeof payload === 'object') return payload as SynthesizePayload
  } catch {}
  return null
}

const route = useRoute()
const burstStore = useBurstStore()
const toast = useToastStore()
const taskStore = useTaskStore()
const loading = ref(true)
const selectedIdx = ref(0)
const framerate = ref(20)
const resolution = ref('1920x1080')
const recognizeSubmitting = ref(false)
const synthSubmitting = ref(false)
const synthesizing = ref(false)
const synthProgress = ref(0)
const synthPhase = ref<string | null>(null)
const synthDetail = ref('')
const synthProcessed = ref(0)
const synthTotal = ref(0)
const videoReady = ref(false)
const videoVersion = ref(0)
const logEl = ref<HTMLElement | null>(null)

const burst = computed(() => burstStore.current!)
const currentPhoto = computed(() => burst.value?.photos?.[selectedIdx.value])
const recognizing = computed(() => taskStore.recognizing)
const synthTitle = computed(() => {
  if (synthSubmitting.value) return '正在提交合成任务…'
  return {
    loading_frames: '正在收集连拍照片…',
    extracting_raw: '正在提取 RAW 预览图…',
    preparing_frames: '正在准备照片帧…',
    encoding_video: '正在编码视频…',
    finalizing: '正在写入视频文件…',
    done: '视频合成完成',
    error: '视频合成失败',
  }[synthPhase.value ?? ''] ?? '正在生成视频…'
})
const synthStatusText = computed(() => {
  if (synthSubmitting.value) return '后台任务创建后会自动开始轮询进度'
  if (synthDetail.value) return synthDetail.value
  if (synthTotal.value > 0 && synthProcessed.value > 0) {
    return `已处理 ${synthProcessed.value} / ${synthTotal.value}`
  }
  return '后台正在处理，请稍候'
})

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
  recognizeSubmitting.value = true
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
  } finally {
    recognizeSubmitting.value = false
  }
}

async function stopRecognize() {
  await taskStore.cancelRecognize()
  toast.info('已停止识别任务')
  burstStore.fetchBurst(burst.value.id)
}

async function synthesize() {
  synthSubmitting.value = true
  synthesizing.value = true
  synthProgress.value = 0
  synthPhase.value = null
  synthDetail.value = ''
  synthProcessed.value = 0
  synthTotal.value = 0
  videoReady.value = false
  try {
    const task = await burstAPI.synthesize(burst.value.id, framerate.value, resolution.value)
    toast.info('合成任务已提交')
    const taskId = (task as any).task_id ?? task.id
    synthSubmitting.value = false
    taskStore.setActiveTask('正在生成连拍视频…', 0)
    await new Promise<void>((resolve, reject) => {
      const tick = async () => {
        const t = await taskAPI.get(taskId)
        synthProgress.value = t.progress ?? 0
        const payload = parseSynthesizePayload(t.result_json)
        synthPhase.value = payload?.phase ?? null
        synthDetail.value = payload?.detail ?? ''
        synthProcessed.value = typeof payload?.processed === 'number' ? payload.processed : 0
        synthTotal.value = typeof payload?.total === 'number' ? payload.total : 0
        taskStore.setActiveTask(synthTitle.value, t.progress ?? 0)
        if (t.status === 'done') return resolve()
        if (t.status === 'error') return reject(new Error(t.error_msg ?? '合成失败'))
        setTimeout(tick, 1500)
      }
      tick().catch(reject)
    })
    videoVersion.value++
    videoReady.value = true
    await burstStore.fetchBurst(burst.value.id)
    toast.success('视频合成完成')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    synthSubmitting.value = false
    synthesizing.value = false
    taskStore.clearActiveTask()
  }
}
</script>
