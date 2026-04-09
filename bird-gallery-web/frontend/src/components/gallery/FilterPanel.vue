<template>
  <div class="px-5 py-3 text-[14px]">
    <div class="flex flex-wrap items-end gap-3">
      <!-- 搜索 -->
      <div class="flex flex-col gap-1">
        <label class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary">搜索</label>
        <input
          type="text"
          :value="modelValue.q ?? ''"
          class="filter-input w-44"
          placeholder="文件名 / 物种"
          @input="emit('update', 'q', ($event.target as HTMLInputElement).value || undefined)"
        />
      </div>

      <!-- 物种 -->
      <div class="flex flex-col gap-1">
        <label class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary">鸟种</label>
        <select
          :value="modelValue.species ?? ''"
          class="filter-input w-36"
          @change="emit('update', 'species', ($event.target as HTMLSelectElement).value || undefined)"
        >
          <option value="">全部</option>
          <option v-for="s in options.species" :key="s" :value="s">{{ s }}</option>
        </select>
      </div>

      <!-- 相机 -->
      <div class="flex flex-col gap-1">
        <label class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary">相机</label>
        <select
          :value="modelValue.camera ?? ''"
          class="filter-input w-36"
          @change="emit('update', 'camera', ($event.target as HTMLSelectElement).value || undefined)"
        >
          <option value="">全部</option>
          <option v-for="c in options.cameras" :key="c" :value="c">{{ c }}</option>
        </select>
      </div>

      <!-- 日期 -->
      <div class="flex flex-col gap-1">
        <label class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary">日期</label>
        <select
          :value="modelValue.date_from ?? ''"
          class="filter-input w-36"
          @change="onDateSelect(($event.target as HTMLSelectElement).value)"
        >
          <option value="">全部</option>
          <option v-for="d in options.dates" :key="d" :value="d">{{ d }}</option>
        </select>
      </div>

      <!-- 评分 -->
      <div class="flex flex-col gap-1">
        <label class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary">评分</label>
        <div class="flex gap-1.5">
          <select
            :value="modelValue.rating_min ?? ''"
            class="filter-input w-20"
            @change="emit('update', 'rating_min', toNumSelect($event))"
          >
            <option value="">最低</option>
            <option v-for="r in [0, 1, 2, 3]" :key="r" :value="r">≥ {{ r }}★</option>
          </select>
          <select
            :value="modelValue.rating_max ?? ''"
            class="filter-input w-20"
            @change="emit('update', 'rating_max', toNumSelect($event))"
          >
            <option value="">最高</option>
            <option v-for="r in [0, 1, 2, 3]" :key="r" :value="r">≤ {{ r }}★</option>
          </select>
        </div>
      </div>

      <!-- 识别状态 -->
      <div class="flex flex-col gap-1">
        <label class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary">状态</label>
        <select
          :value="modelValue.recognized ?? ''"
          class="filter-input w-28"
          @change="emit('update', 'recognized', ($event.target as HTMLSelectElement).value || undefined)"
        >
          <option value="">全部</option>
          <option value="yes">已识别</option>
          <option value="no">未识别</option>
          <option value="no_bird">无鸟</option>
        </select>
      </div>

      <!-- 置信度 -->
      <div class="flex flex-col gap-1">
        <label class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary">
          置信度 ≥ <strong class="text-text-primary dark:text-text-on-dark">{{ confidenceVal }}%</strong>
        </label>
        <input
          type="range"
          :value="confidenceVal"
          min="0" max="100" step="5"
          class="w-28 accent-apple-blue"
          @input="onConfidenceInput(($event.target as HTMLInputElement).value)"
        />
      </div>

      <!-- 复选框组 -->
      <div class="flex items-center gap-4 py-1">
        <label class="flex items-center gap-1.5 text-[14px] text-text-secondary dark:text-text-on-dark-secondary cursor-pointer">
          <input
            type="checkbox"
            :checked="modelValue.has_gps ?? false"
            class="accent-apple-blue"
            @change="emit('update', 'has_gps', ($event.target as HTMLInputElement).checked || undefined)"
          />
          GPS
        </label>
        <label class="flex items-center gap-1.5 text-[14px] text-text-secondary dark:text-text-on-dark-secondary cursor-pointer">
          <input
            type="checkbox"
            :checked="modelValue.has_flying ?? false"
            class="accent-apple-blue"
            @change="emit('update', 'has_flying', ($event.target as HTMLInputElement).checked || undefined)"
          />
          飞版
        </label>
      </div>

      <!-- 重置 -->
      <button
        class="btn-ghost text-[12px] py-1"
        @click="emit('reset')"
      >
        重置
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { PhotoFilters } from '@/types'
import { photoAPI } from '@/api/photos'

const props = defineProps<{
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

const confidenceVal = computed(() => props.modelValue.confidence_min ?? 70)

onMounted(() => fetchOptions(confidenceVal.value))

async function fetchOptions(confMin: number) {
  try {
    options.value = await photoAPI.filterOptions(confMin)
  } catch {
    // 静默失败
  }
}

let _confTimer: ReturnType<typeof setTimeout> | null = null
function onConfidenceInput(val: string) {
  const num = Number(val)
  emit('update', 'confidence_min', num)
  // 防抖刷新鸟种列表
  if (_confTimer) clearTimeout(_confTimer)
  _confTimer = setTimeout(() => fetchOptions(num), 300)
}

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

<style scoped>
.filter-input {
  @apply px-2.5 py-1.5 text-[14px] rounded-lg
         bg-surface-light dark:bg-white/10
         text-text-primary dark:text-text-on-dark
         border-none outline-none
         focus:ring-2 focus:ring-apple-blue/30
         transition-all;
}
</style>
