<template>
  <div class="max-w-3xl mx-auto py-4 sm:py-6 px-3 sm:px-5 space-y-6 sm:space-y-8">
    <h1 class="text-lg sm:text-xl font-semibold text-text-primary dark:text-text-on-dark font-display">系统设置</h1>

    <!-- 存储路径配置 -->
    <section class="card-apple dark:bg-surface-card-dark p-5">
      <h2 class="text-base font-semibold text-text-primary dark:text-text-on-dark mb-4">存储路径</h2>
      <div v-if="sysConfigLoading" class="text-sm text-text-tertiary dark:text-text-on-dark-tertiary">加载中…</div>
      <div v-else class="space-y-4">
        <div>
          <label class="text-sm font-medium text-text-secondary dark:text-text-on-dark-secondary">媒体存储目录</label>
          <p class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mb-1">照片、视频、缩略图的存储根目录。修改后需手动迁移已有文件。</p>
          <input
            v-model="sysConfig.media_dir"
            type="text"
            class="w-full bg-surface-light dark:bg-white/10 border-0 rounded-lg px-3 py-2 text-sm dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40"
            placeholder="/path/to/media"
          />
        </div>
        <div>
          <label class="text-sm font-medium text-text-secondary dark:text-text-on-dark-secondary">扫描白名单目录</label>
          <p class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mb-1">允许扫描导入照片的目录列表（每行一个路径）。</p>
          <textarea
            v-model="scanRootsText"
            rows="3"
            class="w-full bg-surface-light dark:bg-white/10 border-0 rounded-lg px-3 py-2 text-sm dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40 font-mono"
            placeholder="/Volumes/ExternalDisk&#10;~/Pictures"
          ></textarea>
        </div>
        <div class="flex items-center gap-3">
          <button
            @click="testSysConfig"
            :disabled="sysConfigTesting"
            class="btn-secondary !text-sm !px-4 !py-2"
          >
            {{ sysConfigTesting ? '验证中…' : '测试/验证' }}
          </button>
          <button
            @click="saveSysConfig"
            :disabled="sysConfigSaving"
            class="btn-primary !text-sm !px-4 !py-2"
          >
            {{ sysConfigSaving ? '保存中…' : '保存存储配置' }}
          </button>
        </div>
      </div>
    </section>

    <!-- 用户管理 -->
    <section class="card-apple dark:bg-surface-card-dark p-5">
      <h2 class="text-base font-semibold text-text-primary dark:text-text-on-dark mb-4">用户管理</h2>

      <!-- 创建用户 -->
      <form @submit.prevent="createUser" class="grid grid-cols-1 sm:grid-cols-2 lg:flex lg:flex-wrap items-end gap-3 mb-5">
        <div class="sm:col-span-1">
          <label class="block text-sm font-medium text-text-secondary dark:text-text-on-dark-secondary mb-1">用户名</label>
          <input
            v-model="newUser.username"
            type="text"
            required
            class="bg-surface-light dark:bg-white/10 border-0 rounded-lg px-3 py-2 text-sm dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40 w-full lg:w-40"
            placeholder="用户名"
          />
        </div>
        <div class="sm:col-span-1">
          <label class="block text-sm font-medium text-text-secondary dark:text-text-on-dark-secondary mb-1">密码</label>
          <input
            v-model="newUser.password"
            type="password"
            required
            minlength="4"
            class="bg-surface-light dark:bg-white/10 border-0 rounded-lg px-3 py-2 text-sm dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40 w-full lg:w-40"
            placeholder="密码"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-secondary dark:text-text-on-dark-secondary mb-1">角色</label>
          <select
            v-model="newUser.role"
            class="bg-surface-light dark:bg-white/10 border-0 rounded-lg px-3 py-2 text-sm dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40 w-full lg:w-auto"
          >
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select>
        </div>
        <button
          type="submit"
          :disabled="creatingUser"
          class="btn-primary !text-sm !px-4 !py-2"
        >
          {{ creatingUser ? '创建中…' : '创建用户' }}
        </button>
      </form>

      <!-- 用户列表 -->
      <div v-if="usersLoading" class="text-sm text-text-tertiary dark:text-text-on-dark-tertiary">加载中…</div>
      <!-- 移动端卡片布局 -->
      <div v-else-if="users.length" class="sm:hidden space-y-2">
        <div v-for="u in users" :key="u.id" class="flex items-center justify-between p-3 bg-surface-light dark:bg-white/5 rounded-lg">
          <div>
            <p class="text-sm font-medium text-text-primary dark:text-text-on-dark">{{ u.username }}</p>
            <div class="flex items-center gap-2 mt-0.5">
              <span
                class="px-2 py-0.5 rounded-full text-xs font-medium"
                :class="u.role === 'admin' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'"
              >
                {{ u.role === 'admin' ? '管理员' : '普通用户' }}
              </span>
              <span class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary">{{ u.created_at?.slice(0, 10) }}</span>
            </div>
          </div>
          <button
            v-if="u.username !== authStore.username"
            @click="deleteUser(u)"
            class="text-xs text-red-500 hover:text-red-700 shrink-0"
          >删除</button>
          <span v-else class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary shrink-0">当前用户</span>
        </div>
      </div>
      <!-- 桌面端表格 -->
      <table v-else-if="users.length" class="hidden sm:table w-full text-sm">
        <thead>
          <tr class="border-b border-black/5 dark:border-white/10">
            <th class="text-left py-2 text-text-secondary dark:text-text-on-dark-secondary font-medium">用户名</th>
            <th class="text-left py-2 text-text-secondary dark:text-text-on-dark-secondary font-medium">角色</th>
            <th class="text-left py-2 text-text-secondary dark:text-text-on-dark-secondary font-medium">创建时间</th>
            <th class="text-right py-2 text-gray-600 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id" class="border-b border-black/5 dark:border-white/10">
            <td class="py-2 text-text-primary dark:text-text-on-dark">{{ u.username }}</td>
            <td class="py-2">
              <span
                class="px-2 py-0.5 rounded-full text-xs font-medium"
                :class="u.role === 'admin' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'"
              >
                {{ u.role === 'admin' ? '管理员' : '普通用户' }}
              </span>
            </td>
            <td class="py-2 text-text-tertiary dark:text-text-on-dark-tertiary">{{ u.created_at?.slice(0, 16).replace('T', ' ') }}</td>
            <td class="py-2 text-right">
              <button
                v-if="u.username !== authStore.username"
                @click="deleteUser(u)"
                class="text-xs text-red-500 hover:text-red-700"
              >
                删除
              </button>
              <span v-else class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary">当前用户</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="text-sm text-text-tertiary dark:text-text-on-dark-tertiary">暂无用户</p>
    </section>

    <!-- 修改密码 -->
    <section class="card-apple dark:bg-surface-card-dark p-5">
      <h2 class="text-base font-semibold text-text-primary dark:text-text-on-dark mb-4">修改密码</h2>
      <form @submit.prevent="changePassword" class="space-y-3 max-w-sm">
        <div>
          <label class="block text-sm font-medium text-text-secondary dark:text-text-on-dark-secondary mb-1">当前密码</label>
          <input
            v-model="pwForm.old_password"
            type="password"
            required
            class="w-full bg-surface-light dark:bg-white/10 border-0 rounded-lg px-3 py-2 text-sm dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-secondary dark:text-text-on-dark-secondary mb-1">新密码</label>
          <input
            v-model="pwForm.new_password"
            type="password"
            required
            minlength="4"
            class="w-full bg-surface-light dark:bg-white/10 border-0 rounded-lg px-3 py-2 text-sm dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-secondary dark:text-text-on-dark-secondary mb-1">确认新密码</label>
          <input
            v-model="pwForm.confirm"
            type="password"
            required
            minlength="4"
            class="w-full bg-surface-light dark:bg-white/10 border-0 rounded-lg px-3 py-2 text-sm dark:text-text-on-dark focus:ring-2 focus:ring-apple-blue/40"
          />
        </div>
        <button
          type="submit"
          :disabled="changingPw"
          class="btn-primary !text-sm !px-4 !py-2"
        >
          {{ changingPw ? '修改中…' : '修改密码' }}
        </button>
      </form>
    </section>

    <hr class="border-black/5 dark:border-white/10" />

    <h2 class="text-lg font-semibold text-text-primary dark:text-text-on-dark font-display">评分设置</h2>

    <!-- 评分逻辑说明 -->
    <section class="card-apple dark:bg-surface-card-dark border-l-4 border-l-apple-blue p-5">
      <h2 class="text-base font-semibold text-apple-blue mb-3">评分逻辑</h2>
      <ol class="space-y-1.5 text-sm text-text-primary dark:text-text-on-dark list-none">
        <li v-for="(line, i) in scoringLogic" :key="i" class="flex items-start gap-2">
          <span class="shrink-0 mt-0.5">{{ i + 1 }}.</span>
          <span>{{ line }}</span>
        </li>
      </ol>
    </section>

    <!-- 阈值调整 -->
    <section class="card-apple dark:bg-surface-card-dark p-5">
      <h2 class="text-base font-semibold text-text-primary dark:text-text-on-dark mb-4">阈值参数</h2>
      <Spinner v-if="loading" />
      <div v-else class="space-y-6">
        <div v-for="rule in rules" :key="rule.key" class="space-y-1">
          <div class="flex items-center justify-between">
            <label class="text-sm font-medium text-text-secondary dark:text-text-on-dark-secondary">{{ rule.label }}</label>
            <span class="text-sm font-mono text-apple-blue">{{ displayValue(rule) }}{{ rule.unit }}</span>
          </div>
          <p class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary">{{ rule.desc }}</p>
          <div class="flex items-center gap-3">
            <span class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary w-10">{{ rule.min }}</span>
            <input
              type="range"
              :min="rule.min"
              :max="rule.max"
              :step="rule.step"
              :value="config[rule.key]"
              @input="onSliderChange(rule.key, $event)"
              class="flex-1 h-2 rounded-lg appearance-none cursor-pointer accent-apple-blue bg-black/5 dark:bg-white/10"
            />
            <span class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary w-10 text-right">{{ rule.max }}</span>
          </div>
          <div class="flex justify-end">
            <button
              v-if="config[rule.key] !== defaults[rule.key]"
              @click="config[rule.key] = defaults[rule.key]; dirty = true"
              class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary hover:text-gray-600"
            >
              恢复默认 ({{ defaults[rule.key] }})
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- 操作按钮 -->
    <section class="flex flex-wrap items-center gap-3">
      <button
        @click="saveConfig"
        :disabled="!dirty || saving"
        class="btn-primary !text-sm !px-4 !py-2"
      >
        {{ saving ? '保存中…' : '保存配置' }}
      </button>
      <button
        @click="recalculate"
        :disabled="recalculating"
        class="px-4 py-2 bg-amber-500 text-white text-sm rounded-xl hover:bg-amber-600 disabled:opacity-50 transition-colors"
      >
        <span v-if="recalculating">重算中 ({{ recalcProgress }}%)…</span>
        <span v-else>按新配置重算评分</span>
      </button>
      <button
        @click="resetConfig"
        class="btn-secondary !text-sm !px-4 !py-2"
      >
        恢复全部默认
      </button>
    </section>

    <!-- 评分预览表 -->
    <section class="card-apple dark:bg-surface-card-dark border border-black/5 dark:border-white/10 rounded-lg p-5">
      <h2 class="text-base font-semibold text-text-primary dark:text-text-on-dark mb-3">调参效果预览</h2>
      <p class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary mb-3">当前配置下，各等级的判定条件</p>
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-black/5 dark:border-white/10">
            <th class="text-left py-2 text-text-secondary dark:text-text-on-dark-secondary font-medium">等级</th>
            <th class="text-left py-2 text-text-secondary dark:text-text-on-dark-secondary font-medium">条件</th>
          </tr>
        </thead>
        <tbody class="text-text-primary dark:text-text-on-dark">
          <tr class="border-b border-black/5 dark:border-white/10">
            <td class="py-2">❌ -1 星</td>
            <td class="py-2">未检测到鸟类</td>
          </tr>
          <tr class="border-b border-black/5 dark:border-white/10">
            <td class="py-2">0 星</td>
            <td class="py-2">
              置信度 &lt; {{ config.min_confidence }}
              或 锐度 &lt; {{ config.min_sharpness }}
              或 美学 &lt; {{ config.min_nima }}
            </td>
          </tr>
          <tr class="border-b border-black/5 dark:border-white/10">
            <td class="py-2">★ 1 星</td>
            <td class="py-2">
              通过最低标准，但锐度 &lt; {{ config.sharpness_threshold }}
              且 美学 &lt; {{ config.nima_threshold }}
            </td>
          </tr>
          <tr class="border-b border-black/5 dark:border-white/10">
            <td class="py-2">★★ 2 星</td>
            <td class="py-2">
              锐度 ≥ {{ config.sharpness_threshold }}
              或 美学 ≥ {{ config.nima_threshold }}
            </td>
          </tr>
          <tr>
            <td class="py-2">★★★ 3 星</td>
            <td class="py-2">
              锐度 ≥ {{ config.sharpness_threshold }}
              且 美学 ≥ {{ config.nima_threshold }}
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { photoAPI } from '@/api/photos'
import { taskAPI } from '@/api/admin'
import { useToastStore } from '@/stores/toastStore'
import { useAuthStore } from '@/stores/authStore'
import authAPI from '@/api/auth'
import type { UserItem } from '@/api/auth'
import Spinner from '@/components/common/Spinner.vue'
import client from '@/api/client'

const toastStore = useToastStore()
const authStore = useAuthStore()
const loading = ref(true)
const saving = ref(false)
const dirty = ref(false)
const recalculating = ref(false)
const recalcProgress = ref(0)

// ── 系统存储配置 ──
const sysConfigLoading = ref(true)
const sysConfigSaving = ref(false)
const sysConfigTesting = ref(false)
const sysConfig = reactive({ media_dir: '', scan_roots: [] as string[] })
const scanRootsText = computed({
  get: () => sysConfig.scan_roots.join('\n'),
  set: (val: string) => { sysConfig.scan_roots = val.split('\n').map(s => s.trim()).filter(Boolean) },
})

async function loadSysConfig() {
  try {
    const data: any = await client.get('/admin/config')
    sysConfig.media_dir = data.media_dir || ''
    sysConfig.scan_roots = data.scan_roots || []
  } catch (e: any) {
    toastStore.error('加载存储配置失败: ' + e.message)
  } finally {
    sysConfigLoading.value = false
  }
}

async function saveSysConfig() {
  // 安全警告
  const confirmed = window.confirm(
    '正在更改媒体库存储路径或扫描白名单。\n\n' +
    '⚠️ 重要提示：\n' +
    '• 系统不会自动移动旧文件\n' +
    '• 请确保已在操作系统层面将原有文件迁移到新位置\n' +
    '• 否则历史照片将无法显示\n\n' +
    '是否继续保存？'
  )
  if (!confirmed) return

  sysConfigSaving.value = true
  try {
    const data: any = await client.put('/admin/config', {
      media_dir: sysConfig.media_dir || undefined,
      scan_roots: sysConfig.scan_roots.length ? sysConfig.scan_roots : undefined,
    })
    sysConfig.media_dir = data.media_dir || ''
    sysConfig.scan_roots = data.scan_roots || []
    toastStore.success('存储配置已保存')
  } catch (e: any) {
    toastStore.error('保存失败: ' + e.message)
  } finally {
    sysConfigSaving.value = false
  }
}

async function testSysConfig() {
  sysConfigTesting.value = true
  try {
    const data: any = await client.put('/admin/config', {
      media_dir: sysConfig.media_dir || undefined,
      scan_roots: sysConfig.scan_roots.length ? sysConfig.scan_roots : undefined,
    })
    // 同步返回的有效配置
    sysConfig.media_dir = data.media_dir || sysConfig.media_dir
    sysConfig.scan_roots = data.scan_roots || sysConfig.scan_roots
    toastStore.success('验证通过：后端已接受该路径')
  } catch (e: any) {
    toastStore.error('验证失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    sysConfigTesting.value = false
  }
}

// ── 用户管理 ──
const usersLoading = ref(true)
const creatingUser = ref(false)
const users = ref<UserItem[]>([])
const newUser = reactive({ username: '', password: '', role: 'user' })

async function loadUsers() {
  try {
    const data = await authAPI.listUsers()
    users.value = data.users
  } catch (e: any) {
    toastStore.error('加载用户列表失败: ' + e.message)
  } finally {
    usersLoading.value = false
  }
}

async function createUser() {
  creatingUser.value = true
  try {
    await authAPI.register(newUser.username, newUser.password, newUser.role)
    toastStore.success(`用户「${newUser.username}」创建成功`)
    newUser.username = ''
    newUser.password = ''
    newUser.role = 'user'
    await loadUsers()
  } catch (e: any) {
    toastStore.error('创建失败: ' + e.message)
  } finally {
    creatingUser.value = false
  }
}

async function deleteUser(u: UserItem) {
  if (!window.confirm(`确定要删除用户「${u.username}」？此操作不可撤销。`)) return
  try {
    await authAPI.deleteUser(u.id)
    toastStore.success('用户已删除')
    await loadUsers()
  } catch (e: any) {
    toastStore.error('删除失败: ' + e.message)
  }
}

// ── 修改密码 ──
const changingPw = ref(false)
const pwForm = reactive({ old_password: '', new_password: '', confirm: '' })

async function changePassword() {
  if (pwForm.new_password !== pwForm.confirm) {
    toastStore.error('两次输入的新密码不一致')
    return
  }
  changingPw.value = true
  try {
    await authAPI.changePassword(pwForm.old_password, pwForm.new_password)
    toastStore.success('密码修改成功')
    pwForm.old_password = ''
    pwForm.new_password = ''
    pwForm.confirm = ''
  } catch (e: any) {
    toastStore.error('密码修改失败: ' + e.message)
  } finally {
    changingPw.value = false
  }
}

const config = reactive<Record<string, number>>({})
const defaults = reactive<Record<string, number>>({})
const rules = ref<Array<{ key: string; label: string; desc: string; unit: string; min: number; max: number; step: number }>>([])
const scoringLogic = ref<string[]>([])

onMounted(async () => {
  loadSysConfig()
  loadUsers()
  try {
    const data = await photoAPI.ratingConfig()
    Object.assign(config, data.config)
    Object.assign(defaults, data.defaults)
    rules.value = data.rules
    scoringLogic.value = data.scoring_logic
  } catch (e: any) {
    toastStore.error('加载配置失败: ' + e.message)
  } finally {
    loading.value = false
  }
})

function displayValue(rule: { key: string; step: number }) {
  const v = config[rule.key]
  if (v == null) return '-'
  return rule.step < 1 ? v.toFixed(2) : String(v)
}

function onSliderChange(key: string, event: Event) {
  const target = event.target as HTMLInputElement
  config[key] = parseFloat(target.value)
  dirty.value = true
}

async function saveConfig() {
  saving.value = true
  try {
    const data = await photoAPI.updateRatingConfig({ ...config })
    Object.assign(config, data.config)
    dirty.value = false
    toastStore.success('配置已保存')
  } catch (e: any) {
    toastStore.error('保存失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

async function recalculate() {
  recalculating.value = true
  recalcProgress.value = 0
  try {
    // 先保存配置
    if (dirty.value) {
      await photoAPI.updateRatingConfig({ ...config })
      dirty.value = false
    }
    const task = await photoAPI.recalculateRatings()
    if (task.total === 0) {
      toastStore.info('没有需要重算的照片')
      recalculating.value = false
      return
    }
    const taskId = task.id ?? task.task_id
    // 轮询进度
    await new Promise<void>((resolve, reject) => {
      const tick = async () => {
        try {
          const t = await taskAPI.get(taskId)
          recalcProgress.value = t.progress ?? 0
          if (t.status === 'done') return resolve()
          if (t.status === 'error') return reject(new Error(t.error_msg || '重算失败'))
          setTimeout(tick, 1000)
        } catch (e) {
          reject(e)
        }
      }
      tick()
    })
    toastStore.success('评分重算完成')
  } catch (e: any) {
    toastStore.error(e.message)
  } finally {
    recalculating.value = false
  }
}

async function resetConfig() {
  try {
    const data = await photoAPI.resetRatingConfig()
    Object.assign(config, data.config)
    dirty.value = false
    toastStore.success('已恢复默认配置')
  } catch (e: any) {
    toastStore.error(e.message)
  }
}
</script>
