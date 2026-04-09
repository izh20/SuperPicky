<template>
  <div class="max-w-6xl mx-auto px-5 py-6">
    <Spinner v-if="loading" />
    <div v-else-if="!video" class="text-center py-20 text-text-tertiary dark:text-text-on-dark-tertiary">视频不存在</div>
    <div v-else class="flex flex-col gap-6">
      <!-- 导航 -->
      <div class="flex items-center gap-2">
        <button @click="$router.back()" class="flex items-center gap-1 text-sm text-text-tertiary dark:text-text-on-dark-tertiary hover:text-text-primary dark:hover:text-text-on-dark">
          <ArrowLeft class="w-4 h-4" /> 返回
        </button>
        <span class="text-black/10 dark:text-white/20">|</span>
        <span class="text-sm text-text-primary dark:text-text-on-dark font-medium">{{ video.filename }}</span>
        <span class="ml-2 px-2 py-0.5 rounded text-xs text-white" :class="statusClass(video.status)">
          {{ statusLabel(video.status) }}
        </span>
        <div class="flex-1" />
        <button
          v-if="authStore.isAdmin"
          @click="deleteVideo"
          :disabled="deletingVideo"
          class="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 text-white text-sm rounded hover:bg-red-700 disabled:opacity-50 transition-colors"
        >
          <Trash2 class="w-4 h-4" />
          {{ deletingVideo ? '删除中…' : '删除视频' }}
        </button>
      </div>

      <div class="flex gap-6">
        <!-- 左：播放器 + 时间轴 -->
        <div class="flex-1 flex flex-col gap-4">
          <!-- 视频播放器 -->
          <div class="bg-black rounded-xl overflow-hidden">
            <video
              ref="videoEl"
              controls
              class="w-full max-h-[50vh]"
              :src="videoAPI.streamUrl(video.id)"
            />
          </div>

          <!-- 鸟种时间轴 -->
          <div v-if="videoStore.segments.length" class="card-apple dark:bg-surface-card-dark p-4">
            <h3 class="font-semibold text-text-primary dark:text-text-on-dark mb-3 text-sm">鸟种时间轴</h3>
            <div class="relative h-8 bg-black/5 dark:bg-white/10 rounded overflow-hidden">
              <div
                v-for="(seg, i) in videoStore.segments"
                :key="i"
                class="absolute h-full cursor-pointer opacity-80 hover:opacity-100 transition-opacity flex items-center"
                :style="segmentStyle(seg)"
                :title="`${seg.species_cn} (${formatTime(seg.start_seconds)} - ${formatTime(seg.end_seconds)})`"
                @click="seekTo(seg.start_seconds)"
              >
                <span class="text-white text-xs px-1 truncate">{{ seg.species_cn }}</span>
              </div>
            </div>
            <div class="flex flex-wrap gap-2 mt-2">
              <div v-for="(seg, i) in uniqueSpecies" :key="i" class="flex items-center gap-1 text-xs text-text-secondary dark:text-text-on-dark-secondary">
                <div class="w-3 h-3 rounded-sm" :style="{ background: speciesColor(i) }" />
                {{ seg }}
              </div>
            </div>
          </div>

          <!-- 分析控制 -->
          <div class="card-apple dark:bg-surface-card-dark p-4 flex items-center gap-3">
            <select v-model="strategy" class="px-2 py-1.5 text-sm bg-surface-light dark:bg-white/10 border-0 rounded-lg dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40">
              <option value="interval">等间隔（默认）</option>
              <option value="keyframe">关键帧</option>
              <option value="scene">场景变化</option>
              <option value="full">全帧（慢）</option>
            </select>
            <button
              @click="analyze"
              :disabled="analyzing"
              class="px-4 py-1.5 btn-primary text-sm"
            >
              <span v-if="analyzing">分析中… {{ progress }}%</span>
              <span v-else>{{ video.status === 'done' ? '重新分析' : '开始分析' }}</span>
            </button>
          </div>

          <!-- 导出片段 -->
          <div v-if="video.status === 'done'" class="card-apple dark:bg-surface-card-dark p-4">
            <h3 class="font-semibold text-text-primary dark:text-text-on-dark mb-3 text-sm">导出片段</h3>
            <div class="flex items-center gap-2">
              <label class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary">起始(秒)</label>
              <input v-model.number="clipStart" type="number" min="0" step="0.1"
                class="w-20 px-2 py-1 text-sm bg-surface-light dark:bg-white/10 border-0 rounded-lg dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40" />
              <label class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary">结束(秒)</label>
              <input v-model.number="clipEnd" type="number" min="0" step="0.1"
                class="w-20 px-2 py-1 text-sm bg-surface-light dark:bg-white/10 border-0 rounded-lg dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40" />
              <button
                @click="exportClip"
                :disabled="exporting || clipStart >= clipEnd"
                class="px-3 py-1 bg-text-primary dark:bg-white text-white dark:text-black text-sm rounded-lg hover:opacity-80 disabled:opacity-50 transition-colors"
              >
                {{ exporting ? '导出中…' : '导出' }}
              </button>
            </div>
          </div>
        </div>

        <!-- 右：精彩帧 + 统计 -->
        <div class="w-72 flex flex-col gap-4">
          <!-- 精彩帧 -->
          <div v-if="videoStore.highlights.length" class="card-apple dark:bg-surface-card-dark p-4">
            <h3 class="font-semibold text-text-primary dark:text-text-on-dark mb-3 text-sm">精彩帧</h3>
            <div class="flex flex-col gap-2">
              <div
                v-for="f in videoStore.highlights"
                :key="f.id"
                class="flex items-center gap-2 p-2 bg-surface-light dark:bg-white/5 rounded-lg cursor-pointer hover:bg-black/5 dark:hover:bg-white/10"
                @click="seekTo(f.timestamp_sec)"
              >
                <div class="w-16 h-10 bg-black/5 dark:bg-white/5 rounded overflow-hidden shrink-0">
                  <img :src="f.file_path" class="w-full h-full object-cover" loading="lazy" @error="e => ((e.target as HTMLImageElement).style.display='none')" />
                </div>
                <div class="flex-1 min-w-0">
                  <p class="text-xs font-medium truncate dark:text-text-on-dark">
                    {{ f.birds?.[0]?.species_cn ?? '未识别' }}
                  </p>
                  <p class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary">{{ formatTime(f.timestamp_sec) }}</p>
                </div>
              </div>
            </div>
          </div>

          <!-- 物种统计 -->
          <div v-if="videoStore.segments.length" class="card-apple dark:bg-surface-card-dark p-4">
            <h3 class="font-semibold text-text-primary dark:text-text-on-dark mb-3 text-sm">鸟种统计</h3>
            <div class="flex flex-col gap-1">
              <div v-for="(seg, i) in speciesStats" :key="i" class="flex items-center gap-2 text-sm">
                <div class="w-2 h-2 rounded-full shrink-0" :style="{ background: speciesColor(i) }" />
                <span class="flex-1 truncate dark:text-text-on-dark">{{ seg.species }}</span>
                <span class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary">{{ formatDuration(seg.duration) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Trash2 } from 'lucide-vue-next'
import { useVideoStore } from '@/stores/videoStore'
import { useToastStore } from '@/stores/toastStore'
import { useAuthStore } from '@/stores/authStore'
import { videoAPI } from '@/api/videos'
import { taskAPI } from '@/api/admin'
import Spinner from '@/components/common/Spinner.vue'
import type { Video } from '@/types'

const route = useRoute()
const router = useRouter()
const videoStore = useVideoStore()
const toast = useToastStore()
const authStore = useAuthStore()
const video = ref<Video | null>(null)
const loading = ref(true)
const videoEl = ref<HTMLVideoElement | null>(null)
const strategy = ref('interval')
const analyzing = ref(false)
const progress = ref(0)
const clipStart = ref(0)
const clipEnd = ref(5)
const exporting = ref(false)
const deletingVideo = ref(false)

// 为每个物种分配颜色
const PALETTE = ['#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316']
function speciesColor(i: number) { return PALETTE[i % PALETTE.length] }

const uniqueSpecies = computed(() => [...new Set(videoStore.segments.map(s => s.species_cn))])

const speciesStats = computed(() => {
  const map = new Map<string, number>()
  for (const seg of videoStore.segments) {
    map.set(seg.species_cn, (map.get(seg.species_cn) ?? 0) + (seg.end_seconds - seg.start_seconds))
  }
  return [...map.entries()].map(([species, duration]) => ({ species, duration }))
    .sort((a, b) => b.duration - a.duration)
})

onMounted(async () => {
  try {
    await videoStore.fetchVideo(route.params.id as string)
    video.value = videoStore.current
    await Promise.all([
      videoStore.fetchTimeline(route.params.id as string),
      videoStore.fetchHighlights(route.params.id as string),
    ])
  } catch { video.value = null }
  finally { loading.value = false }
})

function segmentStyle(seg: any) {
  const dur = video.value?.duration_seconds ?? 1
  const idx = uniqueSpecies.value.indexOf(seg.species_cn)
  return {
    left: `${(seg.start_seconds / dur) * 100}%`,
    width: `${((seg.end_seconds - seg.start_seconds) / dur) * 100}%`,
    background: speciesColor(idx),
  }
}

function seekTo(sec: number) {
  if (videoEl.value) videoEl.value.currentTime = sec
}

function formatTime(s: number) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function formatDuration(s: number) {
  if (s < 60) return `${Math.floor(s)}s`
  return `${Math.floor(s / 60)}m${Math.floor(s % 60)}s`
}

function statusLabel(s: string) {
  return { uploaded: '已上传', transcoding: '转码中', ready: '就绪', analyzing: '分析中', done: '完成', error: '错误' }[s] ?? s
}

function statusClass(s: string) {
  return { done: 'bg-green-500', analyzing: 'bg-blue-500', error: 'bg-red-500', transcoding: 'bg-yellow-500', ready: 'bg-gray-400', uploaded: 'bg-gray-400' }[s] ?? 'bg-gray-400'
}

async function analyze() {
  if (!video.value) return
  analyzing.value = true
  progress.value = 0
  try {
    const task = await videoAPI.analyze(video.value.id, strategy.value)
    const taskId = (task as any).task_id ?? task.id
    toast.info('分析任务已提交')
    // 轮询进度
    await new Promise<void>((resolve, reject) => {
      const tick = async () => {
        const t = await taskAPI.get(taskId)
        progress.value = t.progress ?? 0
        if (t.status === 'done') return resolve()
        if (t.status === 'error') return reject(new Error(t.error_msg ?? '分析失败'))
        setTimeout(tick, 1500)
      }
      tick().catch(reject)
    })
    toast.success('分析完成')
    await videoStore.fetchTimeline(video.value.id)
    await videoStore.fetchHighlights(video.value.id)
    video.value = await videoAPI.get(video.value.id)
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    analyzing.value = false
  }
}

async function exportClip() {
  if (!video.value || clipStart.value >= clipEnd.value) return
  exporting.value = true
  try {
    const blob = await videoAPI.exportClip(video.value.id, clipStart.value, clipEnd.value)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `clip_${clipStart.value}-${clipEnd.value}.mp4`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('片段导出完成')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    exporting.value = false
  }
}

async function deleteVideo() {
  if (!video.value) return
  if (!confirm('确认删除此视频？此操作不可撤销。')) return
  deletingVideo.value = true
  try {
    await videoAPI.delete(video.value.id)
    toast.success('视频已删除')
    router.replace('/videos')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    deletingVideo.value = false
  }
}
</script>
