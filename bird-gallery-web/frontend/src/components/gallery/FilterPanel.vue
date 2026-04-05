<template>
  <aside class="w-56 bg-white border-r border-gray-200 overflow-y-auto shrink-0 p-4 space-y-4 text-sm">
    <!-- 搜索 -->
    <div>
      <label class="block text-gray-500 mb-1">搜索</label>
      <input
        type="text"
        :value="modelValue.q ?? ''"
        class="w-full border border-gray-300 rounded-lg px-2.5 py-1.5 text-sm focus:border-primary-500 focus:outline-none"
        placeholder="文件名 / 物种"
        @input="emit('update', 'q', ($event.target as HTMLInputElement).value || undefined)"
      />
    </div>

    <!-- 物种（下拉） -->
    <div>
      <label class="block text-gray-500 mb-1">鸟种</label>
      <select
        :value="modelValue.species ?? ''"
        class="w-full border border-gray-300 rounded-lg px-2.5 py-1.5 text-sm focus:border-primary-500 focus:outline-none bg-white"
        @change="emit('update', 'species', ($event.target as HTMLSelectElement).value || undefined)"
      >
        <option value="">全部鸟种</option>
        <option v-for="s in options.species" :key="s" :value="s">{{ s }}</option>
      </select>
    </div>

    <!-- 相机（下拉） -->
    <div>
      <label class="block text-gray-500 mb-1">相机</label>
      <select
        :value="modelValue.camera ?? ''"
        class="w-full border border-gray-300 rounded-lg px-2.5 py-1.5 text-sm focus:border-primary-500 focus:outline-none bg-white"
        @change="emit('update', 'camera', ($event.target as HTMLSelectElement).value || undefined)"
      >
        <option value="">全部相机</option>
        <option v-for="c in options.cameras" :key="c" :value="c">{{ c }}</option>
      </select>
    </div>

    <!-- 拍摄日期（下拉） -->
    <div>
      <label class="block text-gray-500 mb-1">拍摄日期</label>
      <select
        :value="modelValue.date_from ?? ''"
        class="w-full border border-gray-300 rounded-lg px-2.5 py-1.5 text-sm focus:border-primary-500 focus:outline-none bg-white"
        @change="onDateSelect(($event.target as HTMLSelectElement).value)"
      >
        <option value="">全部日期</option>
        <option v-for="d in options.dates" :key="d" :value="d">{{ d }}</option>
      </select>
    </div>

    <!-- 评分 -->
    <div>
      <label class="block text-gray-500 mb-1">评分</label>
      <div class="grid grid-cols-2 gap-2">
        <select
          :value="modelValue.rating_min ?? ''"
          class="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none bg-white"
          @change="emit('update', 'rating_min', toNumSelect($event))"
        >
          <option value="">最低</option>
          <option v-for="r in [0, 1, 2, 3]" :key="r" :value="r">≥ {{ r }} 星</option>
        </select>
        <select
          :value="modelValue.rating_max ?? ''"
          class="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none bg-white"
          @change="emit('update', 'rating_max', toNumSelect($event))"
        >
          <option value="">最高</option>
          <option v-for="r in [0, 1, 2, 3]" :key="r" :value="r">≤ {{ r }} 星</option>
        </select>
      </div>
    </div>

    <!-- GPS -->
    <div class="flex items-center gap-2">
      <input
        type="checkbox"
        :checked="modelValue.has_gps ?? false"
        class="accent-primary-600"
        @change="emit('update', 'has_gps', ($event.target as HTMLInputElement).checked || undefined)"
      />
      <label class="text-gray-500">仅含 GPS 信息</label>
    </div>

    <!-- 重置 -->
    <button
      class="w-full text-center text-sm text-primary-600 hover:text-primary-800 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
      @click="emit('reset')"
    >
      重置筛选
    </button>
  </aside>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { PhotoFilters } from '@/types'
import { photoAPI } from '@/api/photos'

defineProps<{
  modelValue: PhotoFilters
}>()

const emit = defineEmits<{
  (e: 'update', key: string, value: any): void
  (e: 'reset'): void
}>()

const options = ref<{ species: string[]; cameras: string[]; dates: string[] }>({
  species: [],
  cameras: [],
  dates: [],
})

onMounted(async () => {
  try {
    options.value = await photoAPI.filterOptions()
  } catch {
    // 静默失败，筛选选项为空但不阻塞页面
  }
})

function onDateSelect(val: string) {
  if (val) {
    // 选中某天：date_from 和 date_to 设为同一天
    emit('update', 'date_from', val)
    emit('update', 'date_to', val)
  } else {
    emit('update', 'date_from', undefined)
    emit('update', 'date_to', undefined)
  }
}

function toNumSelect(e: Event): number | undefined {
  const v = (e.target as HTMLSelectElement).value
  return v !== '' ? Number(v) : undefined
}
</script>
