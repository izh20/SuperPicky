import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/gallery',
  },
  {
    path: '/login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', guest: true },
  },
  {
    path: '/gallery',
    component: () => import('@/views/GalleryView.vue'),
    meta: { title: '照片库' },
  },
  {
    path: '/photos/:id',
    component: () => import('@/views/PhotoDetailView.vue'),
    meta: { title: '照片详情' },
  },
  {
    path: '/upload',
    component: () => import('@/views/UploadView.vue'),
    meta: { title: '上传', requiresAuth: true },
  },
  {
    path: '/videos',
    component: () => import('@/views/VideoListView.vue'),
    meta: { title: '视频' },
  },
  {
    path: '/videos/:id',
    component: () => import('@/views/VideoDetailView.vue'),
    meta: { title: '视频详情' },
  },
  {
    path: '/bursts',
    component: () => import('@/views/BurstListView.vue'),
    meta: { title: '连拍' },
  },
  {
    path: '/bursts/:id',
    component: () => import('@/views/BurstDetailView.vue'),
    meta: { title: '连拍详情' },
  },
  {
    path: '/birds',
    component: () => import('@/views/BirdListView.vue'),
    meta: { title: '鸟种目录' },
  },
  {
    path: '/birds/:species',
    component: () => import('@/views/BirdSpeciesView.vue'),
    meta: { title: '鸟种照片' },
  },
  {
    path: '/duplicates',
    component: () => import('@/views/DuplicatesView.vue'),
    meta: { title: '重复照片' },
  },
  {
    path: '/settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: '系统设置', requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: '仪表盘' },
  },
  {
    path: '/batch-process',
    component: () => import('@/views/BatchProcessView.vue'),
    meta: { title: '批量处理', requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  const title = (to.meta.title as string) ?? 'Bird Gallery'
  document.title = `${title} — Bird Gallery`
})

// 路由守卫：需要登录的页面跳转到登录页
router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  // 管理员页面：需要 token 中包含 admin 角色
  if (to.meta.requiresAdmin && token) {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      if (payload.role !== 'admin') return '/gallery'
    } catch {
      return '/gallery'
    }
  }
  // 已登录用户访问登录页，跳转首页
  if (to.meta.guest && token) {
    return '/gallery'
  }
})

export default router
