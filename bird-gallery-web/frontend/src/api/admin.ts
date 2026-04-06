import client from './client'
import type { Task, SystemMetrics, DashboardStats } from '@/types'

export const adminAPI = {
  health: (): Promise<{ status: string }> => client.get('/admin/health'),

  metrics: (): Promise<SystemMetrics> => client.get('/admin/metrics'),

  releaseModels: (): Promise<any> => client.post('/admin/release-models'),

  dashboard: (): Promise<DashboardStats> => client.get('/stats/dashboard'),

  scan: (path: string, recursive = true): Promise<Task> =>
    client.post('/library/scan', { path, recursive }),
}

export const taskAPI = {
  get: (id: string): Promise<Task> => client.get(`/tasks/${id}`),

  cancel: (id: string): Promise<{ message: string }> => client.post(`/tasks/${id}/cancel`),

  /** 每 interval 毫秒轮询，直到状态 done/error，返回最终 Task */
  poll: (id: string, interval = 1500): Promise<Task> =>
    new Promise((resolve, reject) => {
      const tick = async () => {
        try {
          const task = await taskAPI.get(id)
          if (task.status === 'done') return resolve(task)
          if (task.status === 'error') return reject(new Error(task.error_msg || '任务失败'))
          setTimeout(tick, interval)
        } catch (e) {
          reject(e)
        }
      }
      tick()
    }),
}
