import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 1800_000, // 30 分钟（大文件/长任务）
})

// 请求拦截器：自动附加 JWT token
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：统一解包 data
client.interceptors.response.use(
  (res) => res.data,
  (err) => {
    // 401 未授权：清除 token 并跳转登录页
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname)
      }
    }
    const msg = err.response?.data?.detail || err.message || '请求失败'
    return Promise.reject(new Error(String(msg)))
  },
)

export default client
