<template>
  <div class="max-w-6xl mx-auto px-3 sm:px-5 py-4 sm:py-6">
    <div class="flex flex-wrap items-center justify-between gap-3 mb-4 sm:mb-5">
      <h1 class="text-lg sm:text-xl font-semibold text-text-primary dark:text-text-on-dark font-display">重复/相似照片</h1>
      <button
        @click="detect"
        :disabled="loading"
        class="btn-primary !text-sm !px-4 !py-1.5"
      >
        {{ loading ? '检测中…' : '重新检测' }}
      </button>
    </div>

    <Spinner v-if="loading && groups.length === 0" />

    <EmptyState
      v-else-if="!loading && groups.length === 0"
      title="未发现重复照片"
      description="可点击右上角重新检测"
      :icon="Copy"
    />

    <div v-else class="space-y-4">
      <div v-for="g in groups" :key="g.group_id" class="card-apple dark:bg-surface-card-dark p-4">
        <div class="flex items-center mb-3">
          <h2 class="font-semibold text-text-primary dark:text-text-on-dark">分组 {{ g.group_id.slice(0, 8) }}</h2>
          <span class="ml-2 text-xs text-text-tertiary dark:text-text-on-dark-tertiary">{{ g.hash_type }} · {{ g.photo_count }} 张</span>
        </div>

        <div v-if="details[g.group_id]" class="space-y-2">
          <div class="flex flex-wrap items-center gap-2 mb-2">
            <button class="text-sm text-apple-link-light dark:text-apple-link-dark hover:underline" @click="selectAll(g.group_id)">全选</button>
            <button class="text-sm text-apple-link-light dark:text-apple-link-dark hover:underline" @click="clearSelection(g.group_id)">清空</button>
            <div class="ml-auto">
              <button v-if="authStore.isAdmin" class="btn-danger !px-3 !py-1 !text-sm" :disabled="!(selections[g.group_id] && selections[g.group_id].length)" @click="deleteSelected(g.group_id)">删除已选</button>
            </div>
          </div>

          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2">
            <div v-for="p in details[g.group_id]" :key="p.photo_id" class="relative border border-black/5 dark:border-white/10 rounded-lg overflow-hidden">
              <img :src="'/api/photos/' + p.photo_id + '/thumbnail?size=sm'" class="w-full h-40 object-cover cursor-zoom-in" @click="openPhoto(p.photo_id)"/>
              <label class="absolute top-2 left-2 bg-white/80 rounded-full p-0.5">
                <input type="checkbox" :checked="(selections[g.group_id] || []).includes(p.photo_id)" @change="toggleSelect(g.group_id, p.photo_id)" />
              </label>
              <div class="p-2">
                <div class="text-xs font-medium truncate">{{ p.filename }}</div>
                <div class="text-xs text-text-tertiary mt-1">相似度: {{ p.similarity ?? 1 }}</div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- modal preview -->
    <div v-if="selectedPhoto" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70" @click.self="closePhoto">
      <div class="max-w-4xl w-full p-4">
        <div class="bg-white rounded shadow-lg overflow-hidden">
          <div class="flex justify-end p-2">
            <button class="px-3 py-1" @click="closePhoto">关闭</button>
          </div>
          <img :src="'/api/photos/' + selectedPhoto + '/original'" class="w-full h-auto block" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Copy } from 'lucide-vue-next'
import { photoAPI } from '@/api/photos'
import { taskAPI } from '@/api/admin'
import { useToastStore } from '@/stores/toastStore'
import { useAuthStore } from '@/stores/authStore'
import Spinner from '@/components/common/Spinner.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const toast = useToastStore()
const authStore = useAuthStore()
const loading = ref(false)
const groups = ref<any[]>([])
const details = ref<Record<string, any[]>>({})
const selectedPhoto = ref<string | null>(null)
const selections = ref<Record<string, string[]>>({})

onMounted(() => detect())

async function detect() {
  loading.value = true
  try {
    const res: any = await photoAPI.findDuplicates()
    if (res.groups) {
      groups.value = res.groups ?? []
      details.value = {}
    } else if (res.task_id) {
      const task = await taskAPI.poll(res.task_id)
      const payload = task.result_json ? JSON.parse(task.result_json) : {}
      groups.value = payload.groups ?? []
      details.value = {}
    } else {
      groups.value = []
      details.value = {}
    }
    // preload details for direct display
    for (const g of groups.value) {
      await loadGroup(g.group_id)
    }
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    loading.value = false
  }
}

async function loadGroup(groupId: string) {
  if (details.value[groupId]) return
  try {
    const res = await photoAPI.getDuplicateGroup(groupId)
    details.value[groupId] = res.photos
    selections.value[groupId] = []
  } catch (e: any) {
    toast.error(e.message)
  }
}

function openPhoto(id: string) {
  selectedPhoto.value = id
}
function closePhoto() {
  selectedPhoto.value = null
}

function toggleSelect(groupId: string, photoId: string) {
  const arr = selections.value[groupId] || []
  const idx = arr.indexOf(photoId)
  if (idx === -1) arr.push(photoId)
  else arr.splice(idx, 1)
  selections.value[groupId] = arr
}

function selectAll(groupId: string) {
  const ids = (details.value[groupId] || []).map((p: any) => p.photo_id)
  selections.value[groupId] = ids
}

function clearSelection(groupId: string) {
  selections.value[groupId] = []
}

async function deleteSelected(groupId: string) {
  const ids = selections.value[groupId] || []
  if (!ids.length) return
  if (!confirm(`确定删除已选择的 ${ids.length} 张照片？此操作将从磁盘彻底删除`)) return
  try {
    const res = await photoAPI.batchDelete(ids)
    toast.success(`已删除 ${res.deleted} 张照片`)
    if (details.value[groupId]) {
      details.value[groupId] = details.value[groupId].filter((p: any) => !ids.includes(p.photo_id))
    }
    const group = groups.value.find((g: any) => g.group_id === groupId)
    if (group) group.photo_count = (details.value[groupId] || []).length
    if ((details.value[groupId] || []).length <= 1) {
      groups.value = groups.value.filter((g: any) => g.group_id !== groupId)
      delete details.value[groupId]
      delete selections.value[groupId]
    } else {
      selections.value[groupId] = []
    }
  } catch (e: any) {
    toast.error(e.message || '删除失败')
  }
}
</script>
