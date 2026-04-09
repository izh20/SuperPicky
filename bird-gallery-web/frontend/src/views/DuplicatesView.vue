<template>
  <div class="max-w-6xl mx-auto px-5 py-6">
    <div class="flex items-center justify-between mb-5">
      <h1 class="text-xl font-semibold text-text-primary dark:text-text-on-dark font-display">重复/相似照片</h1>
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
          <button
            class="ml-auto text-sm text-apple-link-light dark:text-apple-link-dark hover:underline"
            @click="loadGroup(g.group_id)"
          >查看详情</button>
        </div>

        <div v-if="details[g.group_id]" class="grid gap-2" style="grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));">
          <div
            v-for="p in details[g.group_id]"
            :key="p.photo_id"
            class="border border-black/5 dark:border-white/10 rounded-lg p-2 flex flex-col gap-1"
          >
            <img
              :src="`/api/photos/${p.photo_id}/thumbnail?size=sm`"
              class="w-full aspect-square object-cover rounded"
              loading="lazy"
            />
            <p class="text-xs text-text-secondary dark:text-text-on-dark-secondary truncate">{{ p.filename }}</p>
            <p class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary">相似度: {{ p.similarity ?? 1 }}</p>
            <div class="flex gap-1 mt-1">
              <button
                class="flex-1 py-1 text-xs bg-apple-blue/10 text-apple-blue rounded-lg hover:bg-apple-blue/20"
                @click="keep(g.group_id, p.photo_id)"
              >保留此张</button>
              <button
                v-if="authStore.isAdmin"
                class="flex-1 py-1 text-xs bg-red-50 text-red-600 rounded hover:bg-red-100"
                @click="deleteDup(g.group_id, p.photo_id, g)"
              >删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Copy } from 'lucide-vue-next'
import { photoAPI } from '@/api/photos'
import { useToastStore } from '@/stores/toastStore'
import { useAuthStore } from '@/stores/authStore'
import Spinner from '@/components/common/Spinner.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const toast = useToastStore()
const authStore = useAuthStore()
const loading = ref(false)
const groups = ref<any[]>([])
const details = ref<Record<string, any[]>>({})

onMounted(() => detect())

async function detect() {
  loading.value = true
  try {
    const res = await photoAPI.findDuplicates()
    groups.value = res.groups ?? []
    details.value = {}
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
  } catch (e: any) {
    toast.error(e.message)
  }
}

async function keep(groupId: string, photoId: string) {
  try {
    const res = await photoAPI.keepDuplicate(groupId, photoId)
    toast.success(`已保留 ${res.kept.slice(0, 8)}，其余 ${res.others.length} 张待清理`)
    // 移除该组
    groups.value = groups.value.filter(g => g.group_id !== groupId)
    delete details.value[groupId]
  } catch (e: any) {
    toast.error(e.message)
  }
}

async function deleteDup(groupId: string, photoId: string, group: any) {
  if (!confirm('确定删除此照片？（仅删除索引，不删除源文件）')) return
  try {
    const res = await photoAPI.deleteDuplicate(groupId, photoId)
    toast.success('已删除')
    if (res.remaining <= 1) {
      // 组已解散
      groups.value = groups.value.filter(g => g.group_id !== groupId)
      delete details.value[groupId]
    } else {
      // 从详情中移除该照片
      if (details.value[groupId]) {
        details.value[groupId] = details.value[groupId].filter((p: any) => p.photo_id !== photoId)
      }
      group.photo_count = res.remaining
    }
  } catch (e: any) {
    toast.error(e.message)
  }
}
</script>
