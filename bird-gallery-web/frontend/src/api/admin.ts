import client from './client'
import type { Task, SystemMetrics, DashboardStats, AdminTaskListResponse } from '@/types'

export const adminAPI = {
  health: (): Promise<{ status: string }> => client.get('/admin/health'),

  metrics: (): Promise<SystemMetrics> => client.get('/admin/metrics'),

  releaseModels: (): Promise<any> => client.post('/admin/release-models'),

  dashboard: (): Promise<DashboardStats> => client.get('/stats/dashboard'),

  listTasks: (limit = 20): Promise<AdminTaskListResponse> =>
    client.get('/admin/tasks', { params: { limit } }),

  cancelTask: (id: string): Promise<{ message: string }> =>
    client.post(`/admin/tasks/${id}/cancel`),

  retryTask: (id: string): Promise<{ message: string; task_id?: string | null; total?: number | null }> =>
    client.post(`/admin/tasks/${id}/retry`),

  scan: (path: string, recursive = true): Promise<Task> =>
    client.post('/library/scan', { path, recursive }),

  listLogs: (): Promise<Array<{ name: string; path: string; exists: boolean; size_bytes: number }>> =>
    client.get('/admin/logs'),

  readLog: (name: string, tail = 200): Promise<{ name: string; total_lines: number; returned_lines: number; lines: string[] }> =>
    client.get(`/admin/logs/${name}`, { params: { tail } }),

  analyzeLog: (name: string, tail = 500): Promise<any> =>
    client.get(`/admin/logs/${name}/analyze`, { params: { tail } }),
}

export const taskAPI = {
  get: (id: string): Promise<Task> => client.get(`/tasks/${id}`),

  cancel: (id: string): Promise<{ message: string }> => client.post(`/tasks/${id}/cancel`),

  getLatestByType: (type: string): Promise<Task> => client.get(`/tasks/latest/${type}`),

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
