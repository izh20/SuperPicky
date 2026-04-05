import { defineStore } from 'pinia'
import { ref } from 'vue'
import { videoAPI } from '@/api/videos'
import type { Video, BirdSegment, VideoFrame } from '@/types'

export const useVideoStore = defineStore('videos', () => {
  const list = ref<Video[]>([])
  const current = ref<Video | null>(null)
  const segments = ref<BirdSegment[]>([])
  const frames = ref<VideoFrame[]>([])
  const highlights = ref<VideoFrame[]>([])
  const loading = ref(false)

  async function fetchList() {
    loading.value = true
    try {
      list.value = await videoAPI.list()
    } finally {
      loading.value = false
    }
  }

  async function fetchVideo(id: string) {
    current.value = await videoAPI.get(id)
  }

  async function fetchTimeline(id: string) {
    const res = await videoAPI.timeline(id)
    segments.value = res.segments ?? []
  }

  async function fetchFrames(id: string) {
    const res = await videoAPI.frames(id)
    frames.value = res.frames ?? []
  }

  async function fetchHighlights(id: string) {
    const res = await videoAPI.highlights(id)
    highlights.value = res.highlights ?? []
  }

  return { list, current, segments, frames, highlights, loading, fetchList, fetchVideo, fetchTimeline, fetchFrames, fetchHighlights }
})
