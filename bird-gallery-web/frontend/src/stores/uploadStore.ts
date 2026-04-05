import { defineStore } from 'pinia'
import { shallowRef, triggerRef } from 'vue'
import { uploadAPI } from '@/api/upload'

export interface UploadItem {
  id: string // upload_id or local temp id
  filename: string
  size: number
  type: 'photo' | 'video'
  status: 'queued' | 'uploading' | 'done' | 'error'
  progress: number        // 0-100
  speed: number           // bytes/sec
  loaded: number          // bytes uploaded so far
  error?: string
  resultId?: string       // photo_id or video_id
}

const CHUNK_SIZE = 10 * 1024 * 1024 // 10MB
const MAX_CONCURRENT = 3

export const useUploadStore = defineStore('upload', () => {
  // shallowRef 防止 Vue 深度代理数万 UploadItem 对象
  const queue = shallowRef<UploadItem[]>([])
  // 原生 File 对象用 Map 索引，完全脱离 Vue 响应式系统
  const _fileMap = new Map<string, File>()
  let _abortController: AbortController | null = null
  let _aborted = false

  function _notify() {
    // 手动触发 shallowRef 的更新通知
    triggerRef(queue)
  }

  function addFiles(files: File[]) {
    const items: UploadItem[] = []
    for (const f of files) {
      const ext = f.name.split('.').pop()?.toLowerCase() ?? ''
      const type: 'photo' | 'video' = ['mp4', 'mov', 'avi', 'mkv'].includes(ext) ? 'video' : 'photo'
      const id = crypto.randomUUID()
      _fileMap.set(id, f)
      items.push({
        id,
        filename: f.name,
        size: f.size,
        type,
        status: 'queued',
        progress: 0,
        speed: 0,
        loaded: 0,
      })
    }
    queue.value = [...queue.value, ...items]
  }

  function removeItem(id: string) {
    _fileMap.delete(id)
    queue.value = queue.value.filter(u => u.id !== id)
  }

  function clearDone() {
    const removed = queue.value.filter(u => u.status === 'done')
    removed.forEach(u => _fileMap.delete(u.id))
    queue.value = queue.value.filter(u => u.status !== 'done')
  }

  async function startAll() {
    // 构建待上传队列
    const pending = queue.value.filter(i => i.status === 'queued')
    if (!pending.length) return

    _abortController = new AbortController()
    _aborted = false
    const signal = _abortController.signal

    // 并发控制池
    let cursor = 0
    const workers = Array.from({ length: Math.min(MAX_CONCURRENT, pending.length) }, async () => {
      while (cursor < pending.length && !_aborted) {
        const idx = cursor++
        const item = pending[idx]
        if (_aborted) {
          item.status = 'error'
          item.error = '已终止'
          _notify()
          break
        }
        const file = _fileMap.get(item.id)
        if (!file) {
          item.status = 'error'
          item.error = 'File reference lost'
          _notify()
          continue
        }
        await _uploadOne(item, file, signal)
        // 上传完成后释放 File 引用，释放浏览器内存
        if (item.status === 'done') _fileMap.delete(item.id)
      }
    })
    await Promise.all(workers)

    // 终止后将剩余 queued 项保留为 queued 状态，以便重新上传
    _abortController = null
  }

  function abortAll() {
    _aborted = true
    _abortController?.abort()
    // 立即将 uploading 项标记为 error，queued 项保持不动（后续由 startAll 循环处理）
    for (const item of queue.value) {
      if (item.status === 'uploading') {
        item.status = 'error'
        item.error = '已终止'
        item.speed = 0
      }
    }
    _notify()
  }

  /** 将所有被终止/失败的项重置为 queued，以便重新上传 */
  function retryFailed() {
    for (const item of queue.value) {
      if (item.status === 'error' && _fileMap.has(item.id)) {
        item.status = 'queued'
        item.progress = 0
        item.speed = 0
        item.loaded = 0
        item.error = undefined
      }
    }
    _notify()
  }

  async function _uploadOne(item: UploadItem, file: File, signal?: AbortSignal) {
    item.status = 'uploading'
    item.progress = 0
    item.speed = 0
    item.loaded = 0
    _notify()

    let lastLoaded = 0
    let lastTime = Date.now()

    function updateSpeed(loaded: number) {
      const now = Date.now()
      const dt = (now - lastTime) / 1000
      if (dt >= 0.3) {
        item.speed = Math.round((loaded - lastLoaded) / dt)
        lastLoaded = loaded
        lastTime = now
      }
      item.loaded = loaded
      _notify()
    }

    function onProgress(percent: number, loaded: number) {
      if (percent > 0) {
        item.progress = percent
      } else if (loaded > 0) {
        item.progress = Math.min(99, Math.round((loaded / file.size) * 100))
      }
      updateSpeed(loaded > 0 ? loaded : Math.round(file.size * item.progress / 100))
    }

    try {
      if (file.size <= CHUNK_SIZE) {
        // 直接上传
        const form = new FormData()
        form.append('file', file)
        const res: any = await (item.type === 'photo'
          ? (await import('@/api/photos')).photoAPI.upload(form, onProgress, signal)
          : (await import('@/api/videos')).videoAPI.upload(form, onProgress, signal))
        item.resultId = res.photo_id ?? res.video_id
      } else {
        // 分块上传
        const session = await uploadAPI.init(file.name, file.size, item.type)
        item.id = session.upload_id
        const totalChunks = session.total_chunks
        let totalUploaded = 0

        for (let idx = 0; idx < totalChunks; idx++) {
          if (signal?.aborted) throw new Error('已终止')
          if (session.uploaded_chunks?.includes(idx)) {
            totalUploaded += CHUNK_SIZE
            continue
          }
          const start = idx * CHUNK_SIZE
          const chunkSize = Math.min(CHUNK_SIZE, file.size - start)
          const blob = file.slice(start, start + chunkSize)
          await uploadAPI.uploadChunk(session.upload_id, idx, blob, (p) => {
            const chunkUploaded = Math.round(chunkSize * p / 100)
            const currentTotal = totalUploaded + chunkUploaded
            item.progress = Math.round((currentTotal / file.size) * 100)
            updateSpeed(currentTotal)
          }, signal)
          totalUploaded += chunkSize
          item.progress = Math.round((totalUploaded / file.size) * 100)
        }

        const res: any = await uploadAPI.complete(session.upload_id)
        item.resultId = res.photo_id ?? res.video_id
      }

      item.status = 'done'
      item.progress = 100
      item.speed = 0
    } catch (e: any) {
      item.status = 'error'
      item.error = _aborted ? '已终止' : e.message
      item.speed = 0
    }
    _notify()
  }

  return { queue, addFiles, removeItem, clearDone, startAll, abortAll, retryFailed, _uploadOne }
})
