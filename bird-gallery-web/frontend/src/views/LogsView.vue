<template>
  <div class="logs-view">
    <h2>📊 系统监控</h2>
    <p class="subtitle">实时查看谁在访问你的网站、有没有出错</p>

    <!-- 顶部选项卡 -->
    <div class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        :class="['tab', { active: activeTab === tab.key }]"
        @click="switchTab(tab.key)"
      >
        <span class="tab-icon">{{ tab.icon }}</span>
        <span>{{ tab.label }}</span>
      </button>
      <div class="tab-actions">
        <button class="btn-refresh" @click="refresh" :disabled="loading">
          {{ loading ? '加载中...' : '🔄 刷新' }}
        </button>
        <label class="auto-label">
          <input type="checkbox" v-model="autoRefresh" /> 自动刷新
        </label>
      </div>
    </div>

    <div v-if="error" class="error-banner">⚠️ {{ error }}</div>

    <!-- ============ 访问记录 ============ -->
    <div v-if="activeTab === 'access' && accessData" class="panel-content">
      <!-- 概览卡片 -->
      <div class="stat-cards">
        <div class="stat-card">
          <div class="stat-number">{{ accessData.summary.total_requests }}</div>
          <div class="stat-label">总访问次数</div>
        </div>
        <div class="stat-card">
          <div class="stat-number">{{ accessData.summary.unique_visitors }}</div>
          <div class="stat-label">访问设备数</div>
        </div>
        <div class="stat-card" :class="{ 'stat-warn': accessData.summary.error_count > 0 }">
          <div class="stat-number">{{ accessData.summary.error_count }}</div>
          <div class="stat-label">出错次数</div>
        </div>
        <div class="stat-card">
          <div class="stat-number">{{ accessData.summary.avg_response_ms }}ms</div>
          <div class="stat-label">平均响应</div>
        </div>
      </div>

      <!-- 两列布局 -->
      <div class="two-cols">
        <!-- 谁在访问 -->
        <div class="info-card">
          <h3>📱 访问设备</h3>
          <div v-if="accessData.summary.devices.length" class="bar-list">
            <div v-for="d in accessData.summary.devices" :key="d.name" class="bar-item">
              <span class="bar-label">{{ d.name }}</span>
              <div class="bar-track">
                <div
                  class="bar-fill"
                  :style="{ width: (d.count / accessData.summary.total_requests * 100) + '%' }"
                ></div>
              </div>
              <span class="bar-count">{{ d.count }}</span>
            </div>
          </div>
          <div v-else class="empty-hint">暂无数据</div>
        </div>

        <!-- 在看什么 -->
        <div class="info-card">
          <h3>🔍 用户在做什么</h3>
          <div v-if="accessData.summary.popular_actions.length" class="bar-list">
            <div v-for="a in accessData.summary.popular_actions" :key="a.name" class="bar-item">
              <span class="bar-label">{{ a.name }}</span>
              <div class="bar-track">
                <div
                  class="bar-fill fill-blue"
                  :style="{ width: (a.count / maxActionCount * 100) + '%' }"
                ></div>
              </div>
              <span class="bar-count">{{ a.count }}</span>
            </div>
          </div>
          <div v-else class="empty-hint">暂无数据</div>
        </div>
      </div>

      <!-- 访问者 IP -->
      <div class="info-card" v-if="accessData.summary.visitors.length">
        <h3>🌐 访问者</h3>
        <div class="visitor-list">
          <div v-for="v in accessData.summary.visitors" :key="v.ip" class="visitor-item">
            <span class="visitor-ip">{{ v.ip }}</span>
            <span class="visitor-count">{{ v.count }} 次访问</span>
          </div>
        </div>
      </div>

      <!-- 最近访问 -->
      <div class="info-card">
        <h3>📋 最近访问记录</h3>
        <div class="activity-list" v-if="accessData.recent.length">
          <div
            v-for="(r, i) in accessData.recent"
            :key="i"
            :class="['activity-item', { 'activity-error': r.status >= 400 }]"
          >
            <div class="activity-main">
              <span :class="['status-dot', statusColor(r.status)]"></span>
              <span class="activity-action">{{ r.action }}</span>
              <span class="activity-device">{{ r.device }}</span>
              <span class="activity-ip">{{ r.ip }}</span>
            </div>
            <div class="activity-meta">
              <span v-if="r.status >= 400" class="activity-status-badge error">{{ r.status_label }}</span>
              <span class="activity-time">{{ formatTime(r.time) }}</span>
              <span class="activity-duration">{{ r.duration_ms }}ms</span>
            </div>
          </div>
        </div>
        <div v-else class="empty-hint">还没有访问记录</div>
      </div>

      <!-- 错误 -->
      <div class="info-card warn-card" v-if="accessData.errors.length">
        <h3>❌ 出错的请求</h3>
        <div class="activity-list">
          <div v-for="(e, i) in accessData.errors" :key="i" class="activity-item activity-error">
            <div class="activity-main">
              <span class="status-dot red"></span>
              <span class="activity-action">{{ e.action }}</span>
              <span class="activity-status-badge error">{{ e.status }} {{ e.status_label }}</span>
            </div>
            <div class="activity-meta">
              <span class="activity-path">{{ e.path }}</span>
              <span class="activity-time">{{ formatTime(e.time) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ 后端状态 ============ -->
    <div v-if="activeTab === 'backend' && backendData" class="panel-content">
      <div class="stat-cards">
        <div class="stat-card">
          <div class="stat-number">{{ backendData.summary.total_entries }}</div>
          <div class="stat-label">日志条数</div>
        </div>
        <div class="stat-card" :class="{ 'stat-ok': !backendData.summary.has_errors }">
          <div class="stat-number">{{ backendData.summary.has_errors ? '⚠️' : '✅' }}</div>
          <div class="stat-label">{{ backendData.summary.has_errors ? '有错误' : '运行正常' }}</div>
        </div>
      </div>

      <div class="info-card" v-if="backendData.summary.level_counts && backendData.summary.level_counts.length">
        <h3>📊 日志统计</h3>
        <div class="level-chips">
          <span
            v-for="l in backendData.summary.level_counts"
            :key="l.level"
            :class="['level-chip', 'level-' + l.level.toLowerCase()]"
          >
            {{ l.label }}: {{ l.count }}
          </span>
        </div>
      </div>

      <div class="info-card warn-card" v-if="backendData.issues && backendData.issues.length">
        <h3>⚠️ 需要注意</h3>
        <div class="issue-list">
          <div v-for="(e, i) in backendData.issues" :key="i" :class="['issue-item', 'issue-' + e.level.toLowerCase()]">
            <span class="issue-level">{{ e.level_label }}</span>
            <span class="issue-msg">{{ e.message }}</span>
            <span class="issue-time" v-if="e.time">{{ e.time }}</span>
          </div>
        </div>
      </div>

      <div class="info-card">
        <h3>📋 最近运行日志</h3>
        <div class="backend-log-list" v-if="backendData.recent && backendData.recent.length">
          <div v-for="(e, i) in backendData.recent" :key="i" :class="['backend-entry', 'entry-' + e.level.toLowerCase()]">
            <span class="entry-level">{{ e.level_label }}</span>
            <span class="entry-msg">{{ e.message }}</span>
          </div>
        </div>
        <div v-else class="empty-hint">暂无日志</div>
      </div>
    </div>

    <!-- ============ 原始日志 ============ -->
    <div v-if="activeTab === 'raw'" class="panel-content">
      <div class="raw-controls">
        <select v-model="rawLogName">
          <option v-for="log in logList" :key="log.name" :value="log.name">
            {{ logLabels[log.name] || log.name }} ({{ formatSize(log.size_bytes) }})
          </option>
        </select>
        <select v-model.number="rawTail">
          <option :value="50">最后 50 行</option>
          <option :value="200">最后 200 行</option>
          <option :value="500">最后 500 行</option>
          <option :value="1000">最后 1000 行</option>
        </select>
        <button class="btn-refresh" @click="loadRaw">加载</button>
      </div>
      <div class="log-container" ref="rawContainer">
        <pre class="log-content" v-if="rawData && rawData.lines.length">{{ rawData.lines.join('\n') }}</pre>
        <div v-else class="empty-hint" style="padding:40px">暂无日志</div>
      </div>
    </div>

    <div v-if="!loading && !accessData && !backendData && activeTab !== 'raw'" class="empty-state">
      <p>📭 暂无日志数据，使用网站后这里会出现访问记录</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { adminAPI } from '@/api/admin'

const logLabels: Record<string, string> = {
  nginx_access: '访问日志',
  nginx_error: '错误日志',
  backend: '后端日志',
  frontend: '前端日志',
  gui: 'GUI 日志',
}

const tabs = [
  { key: 'access', icon: '👥', label: '谁在访问' },
  { key: 'backend', icon: '⚙️', label: '后端状态' },
  { key: 'raw', icon: '📄', label: '原始日志' },
]

const activeTab = ref('access')
const loading = ref(false)
const error = ref('')
const autoRefresh = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const accessData = ref<any>(null)
const backendData = ref<any>(null)
const rawData = ref<any>(null)
const rawLogName = ref('nginx_access')
const rawTail = ref(200)
const rawContainer = ref<HTMLElement | null>(null)
const logList = ref<Array<{ name: string; path: string; exists: boolean; size_bytes: number }>>([])

const maxActionCount = computed(() => {
  if (!accessData.value?.summary?.popular_actions?.length) return 1
  return Math.max(...accessData.value.summary.popular_actions.map((a: any) => a.count), 1)
})

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatTime(time: string): string {
  const match = time.match(/(\d{2}:\d{2}:\d{2})/)
  return match ? match[1] : time
}

function statusColor(status: number): string {
  if (status < 300) return 'green'
  if (status < 400) return 'yellow'
  return 'red'
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const [logsRes] = await Promise.all([adminAPI.listLogs()])
    logList.value = logsRes

    if (activeTab.value === 'access') {
      accessData.value = await adminAPI.analyzeLog('nginx_access', 500)
    } else if (activeTab.value === 'backend') {
      backendData.value = await adminAPI.analyzeLog('backend', 500)
    } else if (activeTab.value === 'raw') {
      await loadRaw()
    }
  } catch (e: any) {
    error.value = '加载失败: ' + (e.message || e)
  } finally {
    loading.value = false
  }
}

async function loadRaw() {
  try {
    rawData.value = await adminAPI.readLog(rawLogName.value, rawTail.value)
    await nextTick()
    if (rawContainer.value) {
      rawContainer.value.scrollTop = rawContainer.value.scrollHeight
    }
  } catch (e: any) {
    error.value = '读取失败: ' + (e.message || e)
  }
}

function switchTab(key: string) {
  activeTab.value = key
  refresh()
}

watch(autoRefresh, (val) => {
  if (timer) { clearInterval(timer); timer = null }
  if (val) {
    timer = setInterval(() => refresh(), 5000)
  }
})

onMounted(() => refresh())
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.logs-view { max-width: 1100px; margin: 0 auto; padding: 16px 12px; }
.logs-view h2 { margin: 0 0 4px 0; font-size: 20px; }
.subtitle { color: #888; font-size: 14px; margin: 0 0 16px 0; }

.tab-bar { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; margin-bottom: 16px; border-bottom: 2px solid #eee; padding-bottom: 8px; }
.tab { display: flex; align-items: center; gap: 4px; padding: 6px 10px; border: none; background: #f5f5f5; border-radius: 8px; cursor: pointer; font-size: 13px; transition: all .15s; }
.tab:hover { background: #e8e8e8; }
.tab.active { background: #1a73e8; color: #fff; }
.tab-icon { font-size: 14px; }
.tab-actions { margin-left: auto; display: flex; gap: 8px; align-items: center; }
.btn-refresh { padding: 5px 12px; background: #1a73e8; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-refresh:disabled { opacity: .5; cursor: not-allowed; }
.auto-label { font-size: 12px; display: flex; align-items: center; gap: 4px; color: #666; cursor: pointer; }

.error-banner { background: #fff3cd; color: #856404; padding: 10px 14px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; }

.stat-cards { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 16px; }
.stat-card { background: #fff; border: 1px solid #e8e8e8; border-radius: 12px; padding: 14px 12px; text-align: center; }
.stat-number { font-size: 22px; font-weight: 700; color: #333; }
.stat-label { font-size: 12px; color: #888; margin-top: 4px; }
.stat-warn { border-color: #f5c6cb; }
.stat-warn .stat-number { color: #dc3545; }
.stat-ok { border-color: #c3e6cb; }

.two-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
@media (max-width: 700px) { .two-cols { grid-template-columns: 1fr; } }

.info-card { background: #fff; border: 1px solid #e8e8e8; border-radius: 12px; padding: 14px; margin-bottom: 12px; }
.info-card h3 { margin: 0 0 10px 0; font-size: 15px; font-weight: 600; }
.warn-card { border-color: #f5c6cb; background: #fff8f8; }

.bar-list { display: flex; flex-direction: column; gap: 8px; }
.bar-item { display: flex; align-items: center; gap: 6px; }
.bar-label { min-width: 50px; font-size: 12px; color: #555; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-track { flex: 1; height: 20px; background: #f0f0f0; border-radius: 10px; overflow: hidden; }
.bar-fill { height: 100%; background: linear-gradient(90deg, #34c759, #30d158); border-radius: 10px; min-width: 4px; transition: width .3s; }
.bar-fill.fill-blue { background: linear-gradient(90deg, #007aff, #5ac8fa); }
.bar-count { min-width: 32px; font-size: 13px; color: #888; text-align: right; }

.visitor-list { display: flex; flex-wrap: wrap; gap: 10px; }
.visitor-item { background: #f5f5f5; border-radius: 8px; padding: 8px 14px; display: flex; align-items: center; gap: 10px; }
.visitor-ip { font-family: 'Menlo', monospace; font-size: 13px; color: #333; }
.visitor-count { font-size: 12px; color: #888; }

.activity-list { display: flex; flex-direction: column; gap: 6px; }
.activity-item { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; padding: 8px 10px; background: #fafafa; border-radius: 8px; font-size: 12px; gap: 4px; }
.activity-error { background: #fff5f5; }
.activity-main { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; overflow: hidden; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.status-dot.green { background: #34c759; }
.status-dot.yellow { background: #ff9500; }
.status-dot.red { background: #ff3b30; }
.activity-action { font-weight: 500; color: #333; }
.activity-device { color: #888; font-size: 12px; }
.activity-ip { font-family: 'Menlo', monospace; font-size: 11px; color: #aaa; }
.activity-meta { display: flex; align-items: center; gap: 6px; flex-shrink: 0; flex-wrap: wrap; }
.activity-status-badge { font-size: 11px; padding: 2px 8px; border-radius: 4px; }
.activity-status-badge.error { background: #ff3b30; color: #fff; }
.activity-time { font-size: 12px; color: #999; font-family: 'Menlo', monospace; }
.activity-duration { font-size: 11px; color: #bbb; }
.activity-path { font-size: 11px; color: #999; font-family: 'Menlo', monospace; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.level-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.level-chip { padding: 4px 12px; border-radius: 16px; font-size: 13px; font-weight: 500; }
.level-info { background: #e3f2fd; color: #1565c0; }
.level-warning { background: #fff3e0; color: #e65100; }
.level-error { background: #fce4ec; color: #c62828; }
.level-critical { background: #f8d7da; color: #721c24; }
.level-debug { background: #f5f5f5; color: #666; }

.issue-list { display: flex; flex-direction: column; gap: 6px; }
.issue-item { display: flex; gap: 10px; align-items: flex-start; padding: 8px 12px; border-radius: 8px; font-size: 13px; background: #fff; }
.issue-warning { border-left: 3px solid #ff9500; }
.issue-error, .issue-critical { border-left: 3px solid #ff3b30; }
.issue-level { font-weight: 600; flex-shrink: 0; min-width: 50px; }
.issue-msg { flex: 1; color: #333; word-break: break-word; }
.issue-time { font-size: 11px; color: #aaa; flex-shrink: 0; }

.backend-log-list { display: flex; flex-direction: column; gap: 3px; }
.backend-entry { display: flex; gap: 8px; padding: 5px 10px; border-radius: 6px; font-size: 12px; }
.entry-info { background: #f8f9fa; }
.entry-warning { background: #fff8e1; }
.entry-error, .entry-critical { background: #fef0f0; }
.entry-level { font-weight: 600; min-width: 40px; flex-shrink: 0; }
.entry-info .entry-level { color: #1565c0; }
.entry-warning .entry-level { color: #e65100; }
.entry-error .entry-level, .entry-critical .entry-level { color: #c62828; }
.entry-msg { color: #444; word-break: break-word; }

.raw-controls { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.raw-controls select { padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; flex: 1; min-width: 100px; }
.log-container { background: #1e1e1e; border-radius: 8px; overflow: auto; max-height: calc(100vh - 320px); min-height: 200px; -webkit-overflow-scrolling: touch; }
.log-content { color: #d4d4d4; font-family: 'Menlo', 'Monaco', 'Courier New', monospace; font-size: 10px; line-height: 1.5; padding: 10px; margin: 0; white-space: pre-wrap; word-break: break-all; }

.empty-hint { color: #aaa; font-size: 14px; text-align: center; padding: 12px; }
.empty-state { text-align: center; padding: 60px 20px; color: #888; font-size: 16px; }
</style>
