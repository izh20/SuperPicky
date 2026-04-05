<template>
  <div class="max-w-5xl mx-auto">
    <Spinner v-if="loading" />
    <div v-else-if="!burstStore.current" class="text-center py-20 text-gray-400">连拍组不存在</div>
    <div v-else class="flex flex-col gap-6">
      <!-- 导航 -->
      <div class="flex items-center gap-2">
        <button @click="$router.back()" class="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
          <ArrowLeft class="w-4 h-4" /> 返回
        </button>
        <span class="text-gray-300">|</span>
        <span class="text-sm font-medium text-gray-700">连拍组 · {{ burst.photo_count }} 张</span>
      </div>

      <!-- 帧列表（横向滚动）-->
      <div class="bg-white rounded-xl p-4 border border-gray-100">
        <h3 class="font-semibold text-gray-700 mb-3 text-sm">帧预览</h3>
        <div class="flex gap-2 overflow-x-auto pb-2">
          <div
            v-for="(photo, i) in burst.photos"
            :key="photo.id"
            class="shrink-0 cursor-pointer rounded-lg overflow-hidden border-2 transition-all"
            :class="selectedIdx === i ? 'border-primary-500' : 'border-transparent'"
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
          <div v-if="currentPhoto" class="mt-3 bg-white rounded-xl p-3 border border-gray-100 text-sm text-gray-600">
            <span>帧 {{ selectedIdx + 1 }} / {{ burst.photo_count }}</span>
            <span v-if="currentPhoto.exif_datetime" class="ml-3">{{ currentPhoto.exif_datetime }}</span>
            <span v-if="currentPhoto.species_cn" class="ml-3 font-medium text-primary-700">{{ currentPhoto.species_cn }}</span>
          </div>
        </div>

        <!-- 右侧：识别+合成 -->
        <div class="w-72 flex flex-col gap-4">
          <!-- 识别按钮 -->
          <div class="bg-white rounded-xl p-4 border border-gray-100">
            <h3 class="font-semibold text-gray-700 mb-2 text-sm">鸟种识别</h3>
            <button
              @click="recognize"
              :disabled="recognizing"
              class="w-full py-1.5 bg-primary-600 text-white text-sm rounded hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {{ recognizing ? '识别中…' : '批量识别此组' }}
            </button>
          </div>

          <!-- 合成视频 -->
          <div class="bg-white rounded-xl p-4 border border-gray-100">
            <h3 class="font-semibold text-gray-700 mb-3 text-sm">合成视频</h3>
            <div class="flex flex-col gap-2">
              <div>
                <label class="text-xs text-gray-500">帧率（fps）</label>
                <input
                  v-model.number="framerate"
                  type="range"
                  min="1"
                  max="30"
                  class="w-full mt-1"
                />
                <span class="text-xs text-gray-600">{{ framerate }} fps</span>
              </div>
              <div>
                <label class="text-xs text-gray-500">分辨率</label>
                <select v-model="resolution" class="w-full mt-1 px-2 py-1 text-sm border border-gray-200 rounded">
                  <option value="1280x720">720p</option>
                  <option value="1920x1080">1080p</option>
                  <option value="3840x2160">4K</option>
                </select>
              </div>
              <button
                @click="synthesize"
                :disabled="synthesizing"
                class="w-full py-1.5 bg-gray-700 text-white text-sm rounded hover:bg-gray-800 disabled:opacity-50 transition-colors"
              >
                {{ synthesizing ? `合成中… ${synthProgress}%` : '生成视频' }}
              </button>
            </div>
          </div>

          <!-- 视频预览 -->
          <div v-if="videoReady" class="bg-white rounded-xl p-4 border border-gray-100">
            <h3 class="font-semibold text-gray-700 mb-2 text-sm">合成预览</h3>
            <video
              controls
              class="w-full rounded"
              :src="burstAPI.videoUrl(burst.id)"
            />
            <a
              :href="burstAPI.videoUrl(burst.id)"
              download
              class="mt-2 flex items-center justify-center gap-1.5 text-xs text-primary-600 hover:text-primary-700"
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
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Download } from 'lucide-vue-next'
import { useBurstStore } from '@/stores/burstStore'
import { useToastStore } from '@/stores/toastStore'
import { burstAPI } from '@/api/bursts'
import { taskAPI } from '@/api/admin'
import Spinner from '@/components/common/Spinner.vue'

const route = useRoute()
const burstStore = useBurstStore()
const toast = useToastStore()
const loading = ref(true)
const selectedIdx = ref(0)
const framerate = ref(20)
const resolution = ref('1920x1080')
const recognizing = ref(false)
const synthesizing = ref(false)
const synthProgress = ref(0)
const videoReady = ref(false)

const burst = computed(() => burstStore.current!)
const currentPhoto = computed(() => burst.value?.photos?.[selectedIdx.value])

onMounted(async () => {
  try {
    await burstStore.fetchBurst(route.params.id as string)
    // 检查是否已有合成视频
    videoReady.value = (burstStore.current as any)?.['video_path'] != null
  } finally {
    loading.value = false
  }
})

async function recognize() {
  recognizing.value = true
  try {
    const task = await burstAPI.recognize(burst.value.id)
    toast.info('识别任务已提交')
    await taskAPI.poll((task as any).task_id ?? task.id)
    toast.success('识别完成')
    await burstStore.fetchBurst(burst.value.id)
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    recognizing.value = false
  }
}

async function synthesize() {
  synthesizing.value = true
  synthProgress.value = 0
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
    videoReady.value = true
    toast.success('视频合成完成')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    synthesizing.value = false
  }
}
</script>
