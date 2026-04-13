import { defineStore } from 'pinia'
import { shallowRef, ref, triggerRef } from 'vue'
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

  // 上传状态
  const uploading = ref(false)

  // 添加文件进度
  const addingFiles = ref(false)
  const addingProgress = ref('')

  // ── sessionStorage 持久化（刷新后恢复摘要） ──
  const SS_KEY = 'upload_summary'

  function _saveSummary() {
    const q = queue.value
    if (q.length === 0) {
      sessionStorage.removeItem(SS_KEY)
      return
    }
    const summary = {
      total: q.length,
      done: q.filter(u => u.status === 'done').length,
      errors: q.filter(u => u.status === 'error').length,
      uploading: uploading.value,
      items: q.map(u => ({
        id: u.id, filename: u.filename, size: u.size, type: u.type,
        status: u.status, progress: u.progress, loaded: u.loaded, error: u.error,
      })),
    }
    try { sessionStorage.setItem(SS_KEY, JSON.stringify(summary)) } catch { /* quota */ }
  }

  function _restoreFromSession() {
    try {
      const raw = sessionStorage.getItem(SS_KEY)
      if (!raw) return
      const summary = JSON.parse(raw)
      if (!summary?.items?.length) return
      // 恢复队列（File 引用已丢失，正在上传的标记为中断）
      const items: UploadItem[] = summary.items.map((u: any) => ({
        ...u,
        status: u.status === 'uploading' ? 'error' : u.status,
        error: u.status === 'uploading' ? '页面刷新，上传中断' : u.error,
        speed: 0,
      }))
      queue.value = items
      uploading.value = false
    } catch { /* ignore */ }
  }

  // 启动时恢复
  _restoreFromSession()

  let _notifyTimer: ReturnType<typeof setTimeout> | null = null
  function _notify() {
    // 节流：最多 200ms 触发一次 UI 更新，防止 5000+ 文件时频繁重渲染
    if (_notifyTimer) return
    _notifyTimer = setTimeout(() => {
      _notifyTimer = null
      triggerRef(queue)
    }, 200)
  }
  function _notifyNow() {
    if (_notifyTimer) { clearTimeout(_notifyTimer); _notifyTimer = null }
    triggerRef(queue)
  }

  const ADD_BATCH = 500 // 每批处理 500 个文件

  async function addFiles(files: File[]) {
    if (files.length <= ADD_BATCH) {
      // 少量文件直接同步添加
      const items = _buildItems(files)
      queue.value = [...queue.value, ...items]
      return
    }
    // 大量文件：先在内存中构建所有 UploadItem，最后一次性赋值到 queue
    addingFiles.value = true
    addingProgress.value = `正在加载 0/${files.length} 个文件…`
    const allItems: UploadItem[] = []
    let processed = 0
    for (let i = 0; i < files.length; i += ADD_BATCH) {
      const batch = files.slice(i, i + ADD_BATCH)
      const items = _buildItems(batch)
      allItems.push(...items)
      processed += batch.length
      addingProgress.value = `正在加载 ${processed}/${files.length} 个文件…`
      // 让出主线程，保持 UI 响应
      await new Promise(r => setTimeout(r, 0))
    }
    // 一次性赋值，只触发一次 Vue 响应式更新
    queue.value = [...queue.value, ...allItems]
    addingFiles.value = false
    addingProgress.value = ''
  }

  function _buildItems(files: File[]): UploadItem[] {
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
    return items
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

    uploading.value = true
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
    uploading.value = false
    _saveSummary()
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
    uploading.value = false
    _notify()
    _saveSummary()
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
    _saveSummary()
  }

  function clearQueue() {
    queue.value = []
    _fileMap.clear()
    sessionStorage.removeItem(SS_KEY)
  }

  return { queue, uploading, addFiles, removeItem, clearDone, startAll, abortAll, retryFailed, clearQueue, addingFiles, addingProgress }
})
