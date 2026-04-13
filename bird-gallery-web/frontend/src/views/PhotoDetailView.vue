<template>
  <div>
    <Spinner v-if="loading" class="py-20" />
    <div v-else-if="!photo" class="text-center py-20 text-text-tertiary">照片不存在</div>
    <template v-else>
      <section class="bg-black relative">
        <div class="absolute top-0 inset-x-0 z-10 flex items-center justify-between px-3 sm:px-5 py-2 sm:py-3">
          <button @click="$router.back()" class="flex items-center gap-1 text-[13px] sm:text-[14px] text-white/70 hover:text-white transition-colors shrink-0">
            <ArrowLeft class="w-4 h-4" /> 返回
          </button>
          <span class="text-[12px] sm:text-[14px] text-white/50 truncate max-w-[30vw] sm:max-w-xs mx-2">{{ photo.filename }}</span>
          <div class="flex items-center gap-1.5 sm:gap-2 shrink-0">
            <button
              :disabled="!prevId"
              @click="goTo(prevId!)"
              class="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white/80 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              title="上一张"
            >
              <ChevronLeft class="w-4 h-4" />
            </button>
            <span class="text-[12px] text-white/40 min-w-[4rem] text-center">{{ currentIndex >= 0 ? `${currentIndex + 1} / ${photoStore.items.length}` : '' }}</span>
            <button
              :disabled="!nextId"
              @click="goTo(nextId!)"
              class="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white/80 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              title="下一张"
            >
              <ChevronRight class="w-4 h-4" />
            </button>
          </div>
        </div>

        <div class="flex items-center justify-center relative pt-12 pb-4 px-4" style="min-height: 50vh;">
          <img
            ref="imgEl"
            :src="displayImageSrc"
            :alt="photo.filename"
            class="max-w-full max-h-[70vh] object-contain"
            @load="onImageLoad"
          />
          <svg
            v-if="showBoxes && imgRect"
            class="absolute pointer-events-none"
            :style="{ left: imgRect.left + 'px', top: imgRect.top + 'px', width: imgRect.width + 'px', height: imgRect.height + 'px' }"
          >
            <template v-for="b in photo.birds" :key="b.rank">
              <rect
                v-if="b.detection_box?.length === 4"
                :x="b.detection_box[0] / (photo.width ?? 1) * imgRect.width"
                :y="b.detection_box[1] / (photo.height ?? 1) * imgRect.height"
                :width="(b.detection_box[2] - b.detection_box[0]) / (photo.width ?? 1) * imgRect.width"
                :height="(b.detection_box[3] - b.detection_box[1]) / (photo.height ?? 1) * imgRect.height"
                fill="none" stroke="#22c55e" stroke-width="2" rx="2"
              />
              <text
                v-if="b.detection_box?.length === 4"
                :x="b.detection_box[0] / (photo.width ?? 1) * imgRect.width"
                :y="b.detection_box[1] / (photo.height ?? 1) * imgRect.height - 4"
                class="fill-emerald-400 font-semibold"
                style="font-size: 12px;"
              >{{ b.species_cn }} {{ b.confidence.toFixed(1) }}%</text>
            </template>
          </svg>
        </div>

        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-0 px-3 sm:px-5 pb-4">
          <div class="flex items-center gap-2 sm:gap-3">
            <StarRating :rating="photo.score?.rating" />
            <span v-if="photo.birds?.length" class="text-white/90 text-[15px] sm:text-[17px] font-medium">
              {{ photo.birds[0].species_cn }}
            </span>
            <span v-else class="text-white/40 text-[13px] sm:text-[14px]">未识别</span>
            <span v-if="isRawPhoto" class="px-2 py-0.5 rounded-full bg-white/10 text-[11px] text-white/60 uppercase tracking-[0.12em]">RAW</span>
            <span v-if="isRawPhoto && photoEditState?.has_auto_tone_result" class="px-2 py-0.5 rounded-full bg-emerald-500/20 text-[11px] text-emerald-300">已有调色版本</span>
          </div>
          <div class="flex items-center gap-1.5 sm:gap-2 flex-wrap">
            <label v-if="hasDetectionBoxes" class="flex items-center gap-1.5 text-[12px] text-white/50 cursor-pointer">
              <input type="checkbox" v-model="showBoxes" class="accent-apple-blue rounded" />
              检测框
            </label>
            <button
              v-if="canEditRaw"
              @click="showEditedPreview = !showEditedPreview"
              class="px-2.5 sm:px-3 py-1.5 rounded-lg text-[13px] sm:text-[14px] text-white/70 bg-white/10 hover:bg-white/20 transition-all flex items-center gap-1"
            >
              <SlidersHorizontal class="w-4 h-4" /> {{ showEditedPreview ? '看原图' : '看调色稿' }}
            </button>
            <button
              @click="recognize"
              :disabled="recognizing"
              class="!text-[13px] sm:!text-[14px] !px-2.5 sm:!px-3 !py-1.5 flex items-center gap-1 rounded-lg text-white transition-all"
              :class="recognizing ? 'bg-apple-blue/70 animate-pulse' : 'bg-apple-blue hover:brightness-110 active:brightness-95'"
            >
              <Cpu class="w-4 h-4" :class="{ 'animate-spin': recognizing }" />
              {{ recognizing ? '识别中…' : '识别' }}
            </button>
            <a
              :href="photoAPI.originalUrl(photo.id)"
              download
              class="px-2.5 sm:px-3 py-1.5 rounded-lg text-[13px] sm:text-[14px] text-white/70 bg-white/10 hover:bg-white/20 transition-all flex items-center gap-1"
            >
              <Download class="w-4 h-4" /> <span class="hidden sm:inline">下载</span>
            </a>
            <button
              v-if="authStore.isAdmin"
              @click="deletePhoto"
              class="px-2.5 sm:px-3 py-1.5 rounded-lg text-[13px] sm:text-[14px] text-red-400 bg-white/10 hover:bg-red-500/20 transition-all flex items-center gap-1"
            >
              <Trash2 class="w-4 h-4" /> <span class="hidden sm:inline">删除</span>
            </button>
          </div>
        </div>
      </section>

      <section v-if="isRawPhoto" class="bg-[#0d0d0e] border-t border-white/10">
        <div class="max-w-6xl mx-auto px-3 sm:px-5 py-5 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px] gap-4">
          <div class="rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-5">
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
              <div>
                <h3 class="text-white text-[18px] font-medium">RAW 调色</h3>
                <p class="text-white/45 text-[13px] mt-1">
                  基于当前草稿实时渲染 A7R5 RAW 预览，支持自动调色和手动微调。
                </p>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <button
                  @click="runAutoTone"
                  :disabled="!authStore.isLoggedIn || autoToneBusy || renderBusy || loadingEditState"
                  class="px-3 py-2 rounded-xl bg-emerald-500 text-white text-[13px] hover:brightness-110 disabled:opacity-50 transition-all flex items-center gap-1.5"
                >
                  <Wand2 class="w-4 h-4" /> {{ autoToneBusy ? '自动调色中…' : '自动调色' }}
                </button>
                <button
                  @click="discardDraft"
                  :disabled="!authStore.isLoggedIn || discardBusy || renderBusy || loadingEditState"
                  class="px-3 py-2 rounded-xl bg-white/10 text-white/80 text-[13px] hover:bg-white/15 disabled:opacity-50 transition-all flex items-center gap-1.5"
                >
                  <RotateCcw class="w-4 h-4" /> {{ discardBusy ? '恢复中…' : '恢复当前版本' }}
                </button>
                <button
                  @click="commitDraft"
                  :disabled="!authStore.isLoggedIn || saveBusy || renderBusy || loadingEditState || !photoEditState"
                  class="px-3 py-2 rounded-xl bg-apple-blue text-white text-[13px] hover:brightness-110 disabled:opacity-50 transition-all flex items-center gap-1.5"
                >
                  <Save class="w-4 h-4" /> {{ saveBusy ? '保存中…' : '保存为版本' }}
                </button>
                <button
                  @click="exportCurrentVersion('jpeg')"
                  :disabled="!authStore.isLoggedIn || exportBusy || saveBusy || loadingEditState || !photoEditState"
                  class="px-3 py-2 rounded-xl bg-white/10 text-white/80 text-[13px] hover:bg-white/15 disabled:opacity-50 transition-all flex items-center gap-1.5"
                >
                  <Download class="w-4 h-4" /> {{ exportBusy && exportFormat === 'jpeg' ? '导出 JPG…' : '导出 JPG' }}
                </button>
                <button
                  @click="exportCurrentVersion('tiff')"
                  :disabled="!authStore.isLoggedIn || exportBusy || saveBusy || loadingEditState || !photoEditState"
                  class="px-3 py-2 rounded-xl bg-white/10 text-white/80 text-[13px] hover:bg-white/15 disabled:opacity-50 transition-all flex items-center gap-1.5"
                >
                  <Download class="w-4 h-4" /> {{ exportBusy && exportFormat === 'tiff' ? '导出 TIFF…' : '导出 TIFF' }}
                </button>
              </div>
            </div>

            <div v-if="loadingEditState" class="py-10">
              <Spinner />
            </div>
            <div v-else-if="editorError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-[13px] text-red-200">
              {{ editorError }}
            </div>
            <div v-else-if="photoEditState && editParams" class="space-y-4">
              <div class="flex flex-wrap items-center gap-2 text-[12px] text-white/45">
                <span class="px-2 py-1 rounded-full bg-white/8">当前版本 V{{ photoEditState.current_version.version_no }}</span>
                <span class="px-2 py-1 rounded-full bg-white/8">草稿基于 V{{ draftBaseVersionNo }}</span>
                <span class="px-2 py-1 rounded-full" :class="renderBusy ? 'bg-amber-500/20 text-amber-200' : 'bg-emerald-500/15 text-emerald-200'">
                  {{ renderBusy ? '正在渲染预览' : '预览已同步' }}
                </span>
                <span v-if="!authStore.isLoggedIn" class="px-2 py-1 rounded-full bg-white/8 text-white/60">登录后可保存/调色</span>
                <span class="px-2 py-1 rounded-full bg-white/8 text-white/55">导出仅针对已保存版本，未保存草稿请先保存</span>
              </div>

              <div v-if="lastExport" class="flex flex-wrap items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-3 text-[13px] text-emerald-100">
                <span>最近导出：V{{ lastExport.versionNo }} {{ lastExport.label }}</span>
                <a
                  :href="lastExport.downloadUrl"
                  :download="lastExport.fileName"
                  class="inline-flex items-center gap-1 rounded-lg bg-white/10 px-2.5 py-1.5 text-white hover:bg-white/15 transition-all"
                >
                  <Download class="w-4 h-4" /> 下载文件
                </a>
              </div>

              <div v-if="compareVersion && compareBeforeSrc && compareAfterSrc" class="rounded-xl border border-white/10 bg-black/20 px-3 py-3 sm:px-4 sm:py-4">
                <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <div>
                    <div class="text-[14px] font-medium text-white">版本对比</div>
                    <div class="text-[12px] text-white/45 mt-1">拖动滑块比较历史版本与当前预览的差异，双击分割线可回到 50%。</div>
                  </div>
                  <div class="flex items-center gap-2">
                    <button
                      @click="resetCompareSplit"
                      class="px-2.5 py-1.5 rounded-lg text-[12px] bg-white/10 text-white/75 hover:bg-white/15 transition-all"
                    >
                      重置 50%
                    </button>
                    <button
                      @click="clearCompareVersion"
                      class="px-2.5 py-1.5 rounded-lg text-[12px] bg-white/10 text-white/75 hover:bg-white/15 transition-all"
                    >
                      关闭对比
                    </button>
                  </div>
                </div>

                <div
                  class="relative overflow-hidden rounded-xl border border-white/10 bg-black/30 aspect-[4/3] select-none"
                >
                  <img
                    :src="compareBeforeSrc"
                    :alt="compareBeforeLabel"
                    class="absolute inset-0 w-full h-full object-contain"
                  />
                  <div
                    class="absolute inset-0 overflow-hidden"
                    :style="{ clipPath: `inset(0 ${100 - compareSplit}% 0 0)` }"
                  >
                    <img
                      :src="compareAfterSrc"
                      :alt="compareAfterLabel"
                      class="absolute inset-0 w-full h-full object-contain"
                    />
                  </div>
                  <div v-if="compareInteracting" class="absolute inset-x-0 top-3 z-10 flex items-center justify-between gap-2 px-3 pointer-events-none">
                    <span class="max-w-[45%] truncate rounded-full border border-white/15 bg-black/55 px-2.5 py-1 text-[11px] text-white/85 backdrop-blur-sm">
                      历史版本 · {{ compareBeforeLabel }}
                    </span>
                    <span class="max-w-[45%] truncate rounded-full border border-white/15 bg-black/55 px-2.5 py-1 text-[11px] text-white/85 backdrop-blur-sm text-right">
                      当前预览 · {{ compareAfterLabel }}
                    </span>
                  </div>
                  <div
                    class="absolute inset-y-0 w-px bg-white/90 shadow-[0_0_0_1px_rgba(0,0,0,0.2)]"
                    :style="{ left: `calc(${compareSplit}% - 0.5px)` }"
                  ></div>
                  <button
                    type="button"
                    class="absolute inset-y-0 z-10 w-12 -translate-x-1/2 cursor-ew-resize bg-transparent"
                    :style="{ left: `clamp(18px, ${compareSplit}%, calc(100% - 18px))` }"
                    title="双击分割线回到 50%"
                    @dblclick.stop="resetCompareSplit"
                  ></button>
                  <div
                    class="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 flex h-9 w-9 items-center justify-center rounded-full border border-white/20 bg-black/55 text-white/90 shadow-[0_8px_24px_rgba(0,0,0,0.35)] backdrop-blur-sm pointer-events-none"
                    :style="{ left: `clamp(18px, ${compareSplit}%, calc(100% - 18px))` }"
                  >
                    <span class="text-[13px] tracking-[-0.08em]">&#8596;</span>
                  </div>
                  <div
                    class="absolute top-3 -translate-x-1/2 rounded-full border border-white/20 bg-black/50 px-2 py-1 text-[11px] text-white/90 backdrop-blur-sm"
                    :style="{ left: `clamp(28px, ${compareSplit}%, calc(100% - 28px))` }"
                  >
                    {{ Math.round(compareSplit) }}%
                  </div>
                </div>

                <div class="mt-3 px-1">
                  <input
                    v-model.number="compareSplit"
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    class="w-full accent-apple-blue"
                    @input="markCompareInteraction"
                    @change="settleCompareInteraction"
                    @focus="markCompareInteraction"
                    @blur="settleCompareInteraction"
                  />
                </div>

                <div class="mt-2 flex flex-wrap items-center gap-2 sm:justify-between text-[12px] text-white/55">
                  <span class="rounded-full bg-white/8 px-2 py-1">历史版本：{{ compareBeforeLabel }}</span>
                  <span class="rounded-full bg-white/8 px-2 py-1">当前预览：{{ compareAfterLabel }}</span>
                </div>
              </div>

              <div class="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
                <div
                  v-for="control in sliderControls"
                  :key="control.key"
                  class="rounded-xl bg-white/[0.04] border border-white/8 px-3 py-3"
                >
                  <div class="flex items-center justify-between gap-3 mb-2">
                    <label class="text-[13px] text-white/85">{{ control.label }}</label>
                    <span class="text-[12px] font-mono text-white/50">{{ formatControlValue(control.key, editParams[control.key]) }}</span>
                  </div>
                  <input
                    v-model.number="editParams[control.key]"
                    type="range"
                    :min="control.min"
                    :max="control.max"
                    :step="control.step"
                    :disabled="!authStore.isLoggedIn || renderBusy"
                    class="w-full accent-apple-blue disabled:opacity-50"
                    @input="scheduleDraftSync"
                  />
                </div>
              </div>
            </div>
          </div>

          <div class="rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-5">
            <div class="flex items-center justify-between gap-3 mb-4">
              <div>
                <h3 class="text-white text-[16px] font-medium">版本历史</h3>
                <p class="text-white/45 text-[12px] mt-1">保存后可回切任意调色版本</p>
              </div>
              <History class="w-4 h-4 text-white/40" />
            </div>

            <div v-if="photoEditState?.versions?.length" class="space-y-3">
              <div
                v-for="version in photoEditState.versions"
                :key="version.version_id"
                class="rounded-xl border px-3 py-3 transition-all"
                :class="version.is_current ? 'border-apple-blue/60 bg-apple-blue/10 text-white' : 'border-white/10 bg-white/[0.04] text-white/80 hover:bg-white/[0.07] disabled:opacity-60'"
              >
                <div class="flex items-start gap-3">
                  <img
                    v-if="version.preview_url"
                    :src="versionThumbnailSrc(version)"
                    :alt="`V${version.version_no}`"
                    class="w-20 h-20 rounded-lg object-cover bg-black/20 shrink-0 border border-white/10"
                  />
                  <div v-else class="w-20 h-20 rounded-lg bg-black/20 shrink-0 border border-white/10 flex items-center justify-center text-[11px] text-white/30">
                    无预览
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center justify-between gap-3">
                      <div>
                        <div class="text-[13px] font-medium">V{{ version.version_no }}{{ version.is_auto_tone ? ' · 自动调色' : '' }}</div>
                        <div class="text-[11px] text-white/45 mt-1">{{ formatVersionMeta(version) }}</div>
                      </div>
                      <span class="text-[11px] px-2 py-1 rounded-full shrink-0" :class="version.is_current ? 'bg-apple-blue text-white' : 'bg-white/10 text-white/55'">
                        {{ version.is_current ? '当前' : '历史' }}
                      </span>
                    </div>
                    <div class="mt-3 flex flex-wrap items-center gap-2">
                      <button
                        @click="toggleCompareVersion(version.version_id)"
                        :disabled="!version.preview_url"
                        class="px-2.5 py-1.5 rounded-lg text-[12px] transition-all disabled:opacity-40"
                        :class="compareVersionId === version.version_id ? 'bg-emerald-500/20 text-emerald-200' : 'bg-white/10 text-white hover:bg-white/15'"
                      >
                        {{ compareVersionId === version.version_id ? '取消对比' : '对比' }}
                      </button>
                      <button
                        @click="activateVersion(version.version_id)"
                        :disabled="activatingVersionId === version.version_id || version.is_current || !authStore.isLoggedIn"
                        class="px-2.5 py-1.5 rounded-lg text-[12px] transition-all"
                        :class="version.is_current ? 'bg-white/10 text-white/45 cursor-default' : 'bg-white/10 text-white hover:bg-white/15 disabled:opacity-50'"
                      >
                        {{ activatingVersionId === version.version_id ? '切换中…' : version.is_current ? '当前版本' : '切换为当前' }}
                      </button>
                      <button
                        @click="exportVersion(version.version_id, 'jpeg')"
                        :disabled="exportingVersionId === version.version_id || exportBusy || !authStore.isLoggedIn"
                        class="px-2.5 py-1.5 rounded-lg text-[12px] bg-white/10 text-white hover:bg-white/15 disabled:opacity-50 transition-all"
                      >
                        {{ exportingVersionId === version.version_id && exportFormat === 'jpeg' ? '导出中…' : '导出 JPG' }}
                      </button>
                      <button
                        @click="exportVersion(version.version_id, 'tiff')"
                        :disabled="exportingVersionId === version.version_id || exportBusy || !authStore.isLoggedIn"
                        class="px-2.5 py-1.5 rounded-lg text-[12px] bg-white/10 text-white hover:bg-white/15 disabled:opacity-50 transition-all"
                      >
                        {{ exportingVersionId === version.version_id && exportFormat === 'tiff' ? '导出中…' : '导出 TIFF' }}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-[13px] text-white/45">还没有已保存的调色版本。</div>
          </div>
        </div>
      </section>

      <section v-if="hasBirds && !annotatedError" class="bg-[#111] flex items-center justify-center py-4">
        <img
          :src="`/api/photos/${photo.id}/annotated`"
          :alt="`${photo.filename} - 标注图`"
          class="max-w-full max-h-[50vh] object-contain"
          @error="onAnnotatedError"
        />
      </section>

      <section class="bg-surface-light dark:bg-surface-card-dark py-6 sm:py-8">
        <div class="max-w-5xl mx-auto px-3 sm:px-5 grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6">
          <div class="card-apple p-5 dark:bg-[#1c1c1e]">
            <h3 class="text-text-primary dark:text-text-on-dark mb-3">识别结果</h3>
            <div v-if="photo.birds?.length" class="flex flex-col gap-2">
              <div
                v-for="b in photo.birds"
                :key="b.rank"
                class="flex items-center gap-2 p-2.5 rounded-lg transition-colors"
                :class="b.rank === 1 ? 'bg-apple-blue/5 dark:bg-apple-blue/10' : 'bg-surface-light dark:bg-white/5'"
              >
                <span class="text-[12px] font-bold text-text-tertiary dark:text-text-on-dark-tertiary w-4">{{ b.rank }}</span>
                <div class="flex-1 min-w-0">
                  <p class="font-medium text-text-primary dark:text-text-on-dark truncate">{{ b.species_cn }}</p>
                  <p class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary truncate">{{ b.species_en }}</p>
                  <p class="text-[12px] text-text-tertiary dark:text-text-on-dark-tertiary italic truncate">{{ b.scientific_name }}</p>
                </div>
                <span class="text-[12px] font-semibold text-apple-blue">{{ b.confidence.toFixed(1) }}%</span>
              </div>
            </div>
            <p v-else class="text-text-tertiary dark:text-text-on-dark-tertiary text-[14px]">暂未识别</p>
          </div>

          <div class="card-apple p-5 dark:bg-[#1c1c1e]">
            <h3 class="text-text-primary dark:text-text-on-dark mb-3">评分</h3>
            <StarRating :rating="photo.score?.rating" />
            <div v-if="photo.score" class="mt-3 text-[14px] text-text-tertiary dark:text-text-on-dark-tertiary space-y-1">
              <div v-if="photo.score.head_sharp != null">头部锐度: {{ photo.score.head_sharp?.toFixed(2) }}</div>
              <div v-if="photo.score.nima_score != null">美学评分: {{ photo.score.nima_score?.toFixed(2) }}</div>
            </div>
          </div>

          <div class="card-apple p-5 dark:bg-[#1c1c1e]">
            <h3 class="text-text-primary dark:text-text-on-dark mb-3">EXIF 信息</h3>
            <table class="w-full text-[14px]">
              <tbody>
                <ExifRow label="相机" :value="`${photo.exif_make ?? ''} ${photo.exif_model ?? ''}`.trim()" />
                <ExifRow label="拍摄时间" :value="photo.exif_datetime" />
                <ExifRow label="ISO" :value="photo.exif_iso?.toString()" />
                <ExifRow label="光圈" :value="photo.exif_aperture ? `f/${photo.exif_aperture}` : undefined" />
                <ExifRow label="快门" :value="photo.exif_shutter_speed" />
                <ExifRow label="焦距" :value="photo.exif_focal_length ? `${photo.exif_focal_length}mm` : undefined" />
                <ExifRow label="分辨率" :value="photo.width && photo.height ? `${photo.width}×${photo.height}` : undefined" />
                <ExifRow label="文件大小" :value="formatBytes(photo.file_size)" />
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ChevronLeft, ChevronRight, Cpu, Download, History, RotateCcw, Save, SlidersHorizontal, Trash2, Wand2 } from 'lucide-vue-next'
import { photoAPI } from '@/api/photos'
import { photoEditAPI } from '@/api/photoEdits'
import { taskAPI } from '@/api/admin'
import { useToastStore } from '@/stores/toastStore'
import { useAuthStore } from '@/stores/authStore'
import { usePhotoStore } from '@/stores/photoStore'
import { useTaskStore } from '@/stores/taskStore'
import type { PhotoDetail, PhotoEditParams, PhotoEditState, PhotoEditVersionSummary } from '@/types'
import Spinner from '@/components/common/Spinner.vue'
import StarRating from '@/components/common/StarRating.vue'
import ExifRow from '@/components/common/ExifRow.vue'

const route = useRoute()
const router = useRouter()
const toast = useToastStore()
const authStore = useAuthStore()
const photoStore = usePhotoStore()
const taskStore = useTaskStore()

const DEFAULT_EDIT_PARAMS: PhotoEditParams = {
  exposure: 0,
  contrast: 0,
  highlights: 0,
  shadows: 0,
  whites: 0,
  blacks: 0,
  temperature: 6500,
  tint: 0,
  vibrance: 0,
  saturation: 0,
}

const sliderControls: Array<{ key: keyof PhotoEditParams; label: string; min: number; max: number; step: number }> = [
  { key: 'exposure', label: '曝光', min: -3, max: 3, step: 0.05 },
  { key: 'contrast', label: '对比度', min: -100, max: 100, step: 1 },
  { key: 'highlights', label: '高光', min: -100, max: 100, step: 1 },
  { key: 'shadows', label: '阴影', min: -100, max: 100, step: 1 },
  { key: 'whites', label: '白色色阶', min: -100, max: 100, step: 1 },
  { key: 'blacks', label: '黑色色阶', min: -100, max: 100, step: 1 },
  { key: 'temperature', label: '色温', min: 2000, max: 12000, step: 50 },
  { key: 'tint', label: '色调', min: -150, max: 150, step: 1 },
  { key: 'vibrance', label: '自然饱和度', min: -100, max: 100, step: 1 },
  { key: 'saturation', label: '饱和度', min: -100, max: 100, step: 1 },
]

const previewSize = 1600
const photo = ref<PhotoDetail | null>(null)
const photoEditState = ref<PhotoEditState | null>(null)
const editParams = ref<PhotoEditParams | null>(null)
const lastExport = ref<{ versionId: number; versionNo: number; format: 'jpeg' | 'tiff'; label: string; downloadUrl: string; fileName: string } | null>(null)
const compareVersionId = ref<number | null>(null)
const compareSplit = ref(50)
const compareInteracting = ref(false)
const loading = ref(true)
const loadingEditState = ref(false)
const recognizing = ref(false)
const autoToneBusy = ref(false)
const discardBusy = ref(false)
const saveBusy = ref(false)
const exportBusy = ref(false)
const exportFormat = ref<'jpeg' | 'tiff' | null>(null)
const exportingVersionId = ref<number | null>(null)
const renderBusy = ref(false)
const activatingVersionId = ref<number | null>(null)
const showEditedPreview = ref(true)
const imgEl = ref<HTMLImageElement | null>(null)
const imgRect = ref<{ left: number; top: number; width: number; height: number } | null>(null)
const showBoxes = ref(true)
const annotatedError = ref(false)
const editorError = ref('')
const previewBuster = ref(0)

let syncTimer: ReturnType<typeof setTimeout> | null = null
let compareInteractionTimer: ReturnType<typeof setTimeout> | null = null
let syncSequence = 0

const currentIndex = computed(() => {
  if (!photo.value) return -1
  return photoStore.items.findIndex(p => p.id === photo.value!.id)
})

const prevId = computed(() => {
  const idx = currentIndex.value
  return idx > 0 ? photoStore.items[idx - 1].id : null
})

const nextId = computed(() => {
  const idx = currentIndex.value
  return idx >= 0 && idx < photoStore.items.length - 1 ? photoStore.items[idx + 1].id : null
})

const isRawPhoto = computed(() => /\.(cr2|cr3|nef|arw|dng|raf|orf|rw2)$/i.test(photo.value?.filename ?? ''))

const canEditRaw = computed(() => Boolean(isRawPhoto.value && photoEditState.value))

const displayImageSrc = computed(() => {
  if (photo.value && canEditRaw.value && showEditedPreview.value && photoEditState.value?.current_draft.preview_url) {
    return `${photoEditState.value.current_draft.preview_url}&ts=${previewBuster.value}`
  }
  return photo.value ? photoAPI.thumbnailUrl(photo.value.id, 'lg') : ''
})

const hasDetectionBoxes = computed(() =>
  photo.value?.birds?.some(b => b.detection_box?.length === 4) ?? false,
)

const hasBirds = computed(() =>
  (photo.value?.birds?.length ?? 0) > 0,
)

const draftBaseVersionNo = computed(() => {
  const baseVersionId = photoEditState.value?.current_draft.base_version_id
  if (!baseVersionId) return photoEditState.value?.current_version.version_no ?? '-'
  const matched = photoEditState.value?.versions.find(version => version.version_id === baseVersionId)
  return matched?.version_no ?? photoEditState.value?.current_version.version_no ?? '-'
})

const compareVersion = computed(() => {
  if (!compareVersionId.value) return null
  return photoEditState.value?.versions.find(version => version.version_id === compareVersionId.value) ?? null
})

const compareBeforeSrc = computed(() => {
  if (!compareVersion.value?.preview_url) return ''
  return `${compareVersion.value.preview_url}&ts=${previewBuster.value}`
})

const compareAfterSrc = computed(() => {
  if (photoEditState.value?.current_draft.preview_url) {
    return `${photoEditState.value.current_draft.preview_url}&ts=${previewBuster.value}`
  }
  if (photoEditState.value?.current_version.preview_url) {
    return `${photoEditState.value.current_version.preview_url}&ts=${previewBuster.value}`
  }
  return ''
})

const compareBeforeLabel = computed(() => {
  if (!compareVersion.value) return ''
  return `V${compareVersion.value.version_no}`
})

const compareAfterLabel = computed(() => {
  if (!photoEditState.value) return ''
  return `当前预览 · V${photoEditState.value.current_version.version_no}`
})

function normalizeEditParams(params?: Partial<PhotoEditParams> | null): PhotoEditParams {
  return {
    ...DEFAULT_EDIT_PARAMS,
    ...(params ?? {}),
  }
}

function bumpPreview() {
  previewBuster.value += 1
}

function clearDraftSyncTimer() {
  if (!syncTimer) return
  clearTimeout(syncTimer)
  syncTimer = null
}

function clearCompareInteractionTimer() {
  if (!compareInteractionTimer) return
  clearTimeout(compareInteractionTimer)
  compareInteractionTimer = null
}

function clearCompareVersion() {
  clearCompareInteractionTimer()
  compareInteracting.value = false
  compareVersionId.value = null
  compareSplit.value = 50
}

function resetCompareSplit() {
  compareSplit.value = 50
  markCompareInteraction()
}

function markCompareInteraction() {
  compareInteracting.value = true
  clearCompareInteractionTimer()
  compareInteractionTimer = setTimeout(() => {
    compareInteracting.value = false
    compareInteractionTimer = null
  }, 900)
}

function settleCompareInteraction() {
  clearCompareInteractionTimer()
  compareInteractionTimer = setTimeout(() => {
    compareInteracting.value = false
    compareInteractionTimer = null
  }, 220)
}

function toggleCompareVersion(versionId: number) {
  if (compareVersionId.value === versionId) {
    clearCompareVersion()
    return
  }
  compareVersionId.value = versionId
  compareSplit.value = 50
}

function downloadFile(url: string, fileName: string) {
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

function applyDraftState(patch: Partial<PhotoEditState['current_draft']>) {
  if (!photoEditState.value) return
  photoEditState.value = {
    ...photoEditState.value,
    current_draft: {
      ...photoEditState.value.current_draft,
      ...patch,
    },
  }
}

async function loadPhoto(id: string) {
  loading.value = true
  annotatedError.value = false
  editorError.value = ''
  photoEditState.value = null
  editParams.value = null
  clearDraftSyncTimer()
  clearCompareVersion()
  syncSequence += 1

  try {
    photo.value = await photoAPI.get(id)
    lastExport.value = null
    if (isRawFilename(photo.value.filename)) {
      await loadPhotoEditState(id)
    }
  } catch {
    photo.value = null
  } finally {
    loading.value = false
  }
}

async function loadPhotoEditState(photoId: string) {
  loadingEditState.value = true
  try {
    const state = await photoEditAPI.getState(photoId)
    if (photo.value?.id !== photoId) return
    photoEditState.value = state
    if (compareVersionId.value && !state.versions.some(version => version.version_id === compareVersionId.value)) {
      clearCompareVersion()
    }
    editParams.value = normalizeEditParams(state.current_draft.params_json)
    showEditedPreview.value = true
    editorError.value = ''
    bumpPreview()
  } catch (e: any) {
    editorError.value = e.message || 'RAW 调色状态加载失败'
  } finally {
    if (photo.value?.id === photoId) {
      loadingEditState.value = false
    }
  }
}

function isRawFilename(filename: string | undefined) {
  return /\.(cr2|cr3|nef|arw|dng|raf|orf|rw2)$/i.test(filename ?? '')
}

async function goTo(id: string) {
  if (route.params.id === id) return
  await router.replace(`/photos/${id}`)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowLeft' && prevId.value) goTo(prevId.value)
  else if (e.key === 'ArrowRight' && nextId.value) goTo(nextId.value)
}

function onImageLoad() {
  updateImgRect()
}

function onAnnotatedError() {
  annotatedError.value = true
}

function updateImgRect() {
  if (!imgEl.value) return
  const el = imgEl.value
  const parent = el.parentElement
  if (!parent) return
  const pr = parent.getBoundingClientRect()
  const ir = el.getBoundingClientRect()
  imgRect.value = { left: ir.left - pr.left, top: ir.top - pr.top, width: ir.width, height: ir.height }
}

async function renderCurrentDraft(forceRecompute = false, sequence = ++syncSequence) {
  if (!photo.value || !photoEditState.value) return
  const photoId = photo.value.id
  renderBusy.value = true
  try {
    const render = await photoEditAPI.renderPreview(photoId, {
      preview_size: previewSize,
      quality: 90,
      force_recompute: forceRecompute,
    })
    if (sequence !== syncSequence || photo.value?.id !== photoId) return
    applyDraftState({
      render_revision: render.render_revision,
      render_status: 'ready',
      preview_url: render.preview_url ?? photoEditState.value.current_draft.preview_url,
    })
    editorError.value = ''
    bumpPreview()
  } finally {
    if (sequence === syncSequence && photo.value?.id === photoId) {
      renderBusy.value = false
    }
  }
}

async function syncDraftPreview() {
  if (!photo.value || !photoEditState.value || !editParams.value || !authStore.isLoggedIn) return
  const sequence = ++syncSequence
  const photoId = photo.value.id
  renderBusy.value = true

  try {
    const draft = await photoEditAPI.patchDraft(photoId, editParams.value)
    if (sequence !== syncSequence || photo.value?.id !== photoId) return
    applyDraftState({
      draft_id: draft.draft_id,
      params_json: normalizeEditParams(draft.params_json),
      params_hash: draft.params_hash ?? photoEditState.value.current_draft.params_hash,
      render_revision: draft.render_revision,
      render_status: 'rendering',
    })
    await renderCurrentDraft(false, sequence)
  } catch (e: any) {
    if (sequence !== syncSequence || photo.value?.id !== photoId) return
    editorError.value = e.message || 'RAW 调色预览失败'
    toast.error(editorError.value)
    renderBusy.value = false
  }
}

function scheduleDraftSync() {
  if (!authStore.isLoggedIn || !editParams.value || !photoEditState.value) return
  clearDraftSyncTimer()
  renderBusy.value = true
  syncTimer = setTimeout(() => {
    syncTimer = null
    syncDraftPreview()
  }, 220)
}

async function runAutoTone() {
  if (!photo.value || !photoEditState.value || !authStore.isLoggedIn) return
  clearDraftSyncTimer()
  autoToneBusy.value = true
  showEditedPreview.value = true
  const photoId = photo.value.id
  const sequence = ++syncSequence

  try {
    const draft = await photoEditAPI.autoTone(photoId, photoEditState.value.current_version.version_id)
    if (sequence !== syncSequence || photo.value?.id !== photoId) return
    editParams.value = normalizeEditParams(draft.params_json)
    applyDraftState({
      draft_id: draft.draft_id,
      params_json: normalizeEditParams(draft.params_json),
      params_hash: draft.params_hash ?? photoEditState.value.current_draft.params_hash,
      render_revision: draft.render_revision,
      render_status: 'rendering',
    })
    await renderCurrentDraft(true, sequence)
    toast.success('自动调色已应用')
  } catch (e: any) {
    if (sequence === syncSequence) {
      editorError.value = e.message || '自动调色失败'
      toast.error(editorError.value)
    }
  } finally {
    if (sequence === syncSequence) {
      autoToneBusy.value = false
    }
  }
}

async function discardDraft() {
  if (!photo.value || !photoEditState.value || !authStore.isLoggedIn) return
  clearDraftSyncTimer()
  discardBusy.value = true
  const photoId = photo.value.id
  const sequence = ++syncSequence

  try {
    const draft = await photoEditAPI.discardDraft(photoId)
    if (sequence !== syncSequence || photo.value?.id !== photoId) return
    editParams.value = normalizeEditParams(draft.params_json)
    applyDraftState({
      draft_id: draft.draft_id,
      base_version_id: draft.base_version_id ?? photoEditState.value.current_draft.base_version_id,
      params_json: normalizeEditParams(draft.params_json),
      render_revision: draft.render_revision,
      preview_url: draft.preview_url ?? photoEditState.value.current_draft.preview_url,
      render_status: 'ready',
    })
    editorError.value = ''
    bumpPreview()
    toast.success('已恢复到当前版本')
  } catch (e: any) {
    if (sequence === syncSequence) {
      editorError.value = e.message || '恢复失败'
      toast.error(editorError.value)
    }
  } finally {
    if (sequence === syncSequence) {
      discardBusy.value = false
    }
  }
}

async function commitDraft() {
  if (!photo.value || !photoEditState.value || !authStore.isLoggedIn) return
  clearDraftSyncTimer()
  saveBusy.value = true
  try {
    await photoEditAPI.commitDraft(photo.value.id, true)
    await loadPhotoEditState(photo.value.id)
    toast.success('调色版本已保存')
  } catch (e: any) {
    editorError.value = e.message || '保存失败'
    toast.error(editorError.value)
  } finally {
    saveBusy.value = false
  }
}

async function exportVersion(versionId: number, format: 'jpeg' | 'tiff') {
  if (!photo.value || !authStore.isLoggedIn) return
  exportBusy.value = true
  exportFormat.value = format
  exportingVersionId.value = versionId
  taskStore.setActiveTask(`正在导出 ${format.toUpperCase()}...`, 5)
  try {
    const queued = await photoEditAPI.exportVersion(photo.value.id, versionId, format)
    const task = await taskAPI.poll(queued.task_id, 1200)
    let fileName = `photo-edit-v${versionId}.${format === 'tiff' ? 'tiff' : 'jpeg'}`
    if (task.result_json) {
      try {
        const payload = JSON.parse(task.result_json)
        const exportPath = String(payload?.export_path || '')
        if (exportPath) {
          const pathName = exportPath.split('/').pop()
          if (pathName) fileName = pathName
        }
      } catch {
        fileName = `photo-edit-v${versionId}.${format === 'tiff' ? 'tiff' : 'jpeg'}`
      }
    }

    const matchedVersion = photoEditState.value?.versions.find(version => version.version_id === versionId)
    const downloadUrl = photoEditAPI.exportDownloadUrl(photo.value.id, versionId, format)
    lastExport.value = {
      versionId,
      versionNo: matchedVersion?.version_no ?? versionId,
      format,
      label: format === 'tiff' ? 'TIFF' : 'JPG',
      downloadUrl,
      fileName,
    }
    downloadFile(downloadUrl, fileName)
    toast.success('导出完成，已开始下载')
  } catch (e: any) {
    editorError.value = e.message || '导出失败'
    toast.error(editorError.value)
  } finally {
    exportBusy.value = false
    exportFormat.value = null
    exportingVersionId.value = null
    taskStore.clearActiveTask()
  }
}

async function exportCurrentVersion(format: 'jpeg' | 'tiff') {
  if (!photoEditState.value) return
  await exportVersion(photoEditState.value.current_version.version_id, format)
}

async function activateVersion(versionId: number) {
  if (!photo.value || !photoEditState.value || !authStore.isLoggedIn) return
  activatingVersionId.value = versionId
  clearDraftSyncTimer()
  syncSequence += 1
  try {
    await photoEditAPI.activateVersion(photo.value.id, versionId)
    await loadPhotoEditState(photo.value.id)
    toast.success('已切换版本')
  } catch (e: any) {
    editorError.value = e.message || '切换版本失败'
    toast.error(editorError.value)
  } finally {
    activatingVersionId.value = null
  }
}

async function recognize() {
  if (!photo.value) return
  recognizing.value = true
  const filename = photo.value.filename?.replace(/^.*[\\/]/, '') ?? '照片'
  taskStore.setActiveTask(`正在识别 ${filename}`, 50)
  try {
    toast.info('识别中，请稍候…')
    await photoAPI.recognize(photo.value.id)
    photo.value = await photoAPI.get(photo.value.id)
    annotatedError.value = false
    toast.success('识别完成')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    recognizing.value = false
    taskStore.clearActiveTask()
  }
}

async function deletePhoto() {
  if (!photo.value) return
  if (!confirm(`确认删除 ${photo.value.filename}？`)) return
  try {
    await photoAPI.delete(photo.value.id)
    toast.success('已删除')
    router.back()
  } catch (e: any) {
    toast.error(e.message)
  }
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

function formatControlValue(key: keyof PhotoEditParams, value: number) {
  if (key === 'exposure') return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`
  if (key === 'temperature') return `${Math.round(value)}K`
  return `${value >= 0 ? '+' : ''}${Math.round(value)}`
}

function formatVersionMeta(version: PhotoEditVersionSummary) {
  const parts = [version.engine || 'internal_linear_v1']
  if (version.created_at) {
    parts.push(new Date(version.created_at).toLocaleString())
  }
  return parts.join(' · ')
}

function versionThumbnailSrc(version: PhotoEditVersionSummary) {
  if (!version.preview_url) return ''
  return `${version.preview_url}&ts=${previewBuster.value}`
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  clearDraftSyncTimer()
  clearCompareInteractionTimer()
  window.removeEventListener('keydown', onKeydown)
})

watch(() => route.params.id, (id) => {
  if (typeof id === 'string' && id) {
    loadPhoto(id)
  }
}, { immediate: true })

watch(currentIndex, (idx) => {
  if (idx >= 0 && idx >= photoStore.items.length - 3 && photoStore.items.length < photoStore.total) {
    photoStore.nextPage()
    photoStore.fetchPhotos()
  }
})
</script>
