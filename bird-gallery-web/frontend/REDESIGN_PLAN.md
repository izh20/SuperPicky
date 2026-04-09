# Bird Gallery Web — Apple 风格视觉重构方案

## 一、现状分析

| 维度 | 当前状态 | 问题 |
|------|----------|------|
| **字体** | 系统默认 sans-serif | 无品牌感，中文字体未指定 |
| **配色** | Tailwind sky-blue (#0ea5e9) 为主色，gray-50 灰底白卡 | 过于"通用 Tailwind 风"，缺乏高级感 |
| **布局** | 固定侧栏 (w-48) + 白色顶栏 + p-4 内容区 | 传统后台布局，非内容优先 |
| **导航** | 白色实心顶栏 + 白色实心侧栏 | 无毛玻璃（glass）效果，割裂感强 |
| **卡片** | `bg-white border border-gray-200 rounded-lg` | 大量可见边框，与 Apple 无边框理念冲突 |
| **阴影** | 多处 `shadow-lg` / `shadow-md` | 未统一，偏重 |
| **按钮** | 蓝底白字矩形，圆角 rounded-lg | 无 pill 形态，hover 反馈弱 |
| **图片区** | 灰底 + 圆角 | 照片应以纯黑/纯白为底，产品化呈现 |
| **响应式** | 桌面优先，移动端未适配 | 侧栏无折叠，小屏不可用 |
| **动效** | 仅 `transition-colors` | 缺乏进入/退出动画 |

---

## 二、重构目标

> 将 Bird Gallery 从"Tailwind 后台模板"提升为"Apple 产品化照片应用"。

### 核心原则
1. **内容优先** — 鸟类照片是主角，UI 退到最后
2. **极简交互** — 单一蓝色 (#0071e3) 作为唯一彩色；黑白灰承载一切
3. **电影感节奏** — 暗色沉浸区（照片浏览） vs 浅色信息区（列表/筛选）交替
4. **精确排印** — SF Pro + 苹方 回退链，负字间距，紧凑行高

---

## 三、分阶段实施计划

### Phase 1：设计令牌 & 全局基础（影响所有页面）

**1.1 Tailwind 配色令牌**

```js
// tailwind.config.js — 替换现有 colors
colors: {
  apple: {
    blue: '#0071e3',        // 唯一强调色 — CTA、链接、焦点环
    'link-light': '#0066cc', // 浅底链接
    'link-dark': '#2997ff',  // 暗底链接
  },
  surface: {
    white: '#ffffff',
    light: '#f5f5f7',        // 浅色区背景（替代 gray-50）
    dark: '#000000',         // 暗色区背景
    card: '#272729',         // 暗色区卡片
  },
  text: {
    primary: '#1d1d1f',      // 浅底主文字
    secondary: 'rgba(0,0,0,0.8)',
    tertiary: 'rgba(0,0,0,0.48)',
    'on-dark': '#ffffff',
    'on-dark-secondary': 'rgba(255,255,255,0.8)',
  },
}
```

**1.2 字体系统**

```css
/* style.css — 新增 */
@layer base {
  :root {
    --font-display: 'SF Pro Display', -apple-system, 'PingFang SC', 
                    'Helvetica Neue', Arial, sans-serif;
    --font-text: 'SF Pro Text', -apple-system, 'PingFang SC', 
                 'Helvetica Neue', Arial, sans-serif;
  }
  body {
    font-family: var(--font-text);
    -webkit-font-smoothing: antialiased;
    letter-spacing: -0.374px;   /* Apple 全局负字间距 */
    line-height: 1.47;
  }
  h1, h2, h3 {
    font-family: var(--font-display);
  }
  h1 { font-size: 2.5rem; font-weight: 600; line-height: 1.10; letter-spacing: normal; }
  h2 { font-size: 1.75rem; font-weight: 400; line-height: 1.14; letter-spacing: 0.196px; }
  h3 { font-size: 1.31rem; font-weight: 600; line-height: 1.19; letter-spacing: 0.231px; }
}
```

> macOS 自带 SF Pro 和苹方，无需额外加载字体文件。

**1.3 按钮组件类**

```css
@layer components {
  /* 主 CTA */
  .btn-primary {
    @apply bg-[#0071e3] text-white px-4 py-2 rounded-lg text-[17px]
           hover:brightness-110 active:brightness-95
           focus:outline-none focus:ring-2 focus:ring-[#0071e3]/50
           transition-all duration-200;
  }
  /* 深色按钮 */
  .btn-dark {
    @apply bg-[#1d1d1f] text-white px-4 py-2 rounded-lg text-[17px]
           hover:bg-[#333336] active:brightness-95
           focus:outline-none focus:ring-2 focus:ring-[#0071e3]/50
           transition-all duration-200;
  }
  /* Pill 链接 */  
  .btn-pill {
    @apply border border-[#0066cc] text-[#0066cc] px-4 py-1.5
           rounded-[980px] text-sm
           hover:bg-[#0066cc] hover:text-white
           transition-all duration-200;
  }
  /* 次要/幽灵按钮 */
  .btn-ghost {
    @apply text-[#0066cc] text-sm hover:underline transition-colors;
  }
}
```

**1.4 卡片 & 阴影**

```css
@layer components {
  .card-apple {
    @apply bg-white rounded-lg;
    /* 无边框 — Apple 几乎不用 border */
  }
  .card-apple-elevated {
    @apply bg-white rounded-lg;
    box-shadow: rgba(0, 0, 0, 0.22) 3px 5px 30px 0px;
  }
  .card-apple-dark {
    @apply bg-[#272729] rounded-lg text-white;
  }
}
```

**1.5 全局滚动条更新（暗色友好）**

```css
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { @apply bg-black/20 rounded-full; }
::-webkit-scrollbar-thumb:hover { @apply bg-black/30; }
```

---

### Phase 2：导航重构

**2.1 顶部导航栏 → Apple Glass Nav**

当前：白色实心 + 下边框  
目标：`rgba(0,0,0,0.8)` 半透明 + `backdrop-filter: saturate(180%) blur(20px)` + 固定在顶部

```
┌──────────────────────────────────────────────────────────────┐
│  🐦 Bird Gallery    照片库  视频  连拍  鸟种   │  用户名  退出  │
│  ← 毛玻璃暗色导航 (48px高, sticky)                           │
└──────────────────────────────────────────────────────────────┘
```

- 高度 48px
- 文字：白色 12px `SF Pro Text` weight 400
- 当前页面：下划线高亮
- Logo + 导航链接 + 右侧用户信息

**2.2 取消侧栏**

当前侧栏（w-48）移入顶部导航链接中。释放水平空间给照片内容。  
移动端：汉堡菜单 → 全屏覆盖菜单。

- 筛选面板改为页面内折叠式面板或点击弹出抽屉

---

### Phase 3：核心页面 — 照片库 (GalleryView)

**3.1 照片网格**

| 项 | 当前 | 目标 |
|----|------|------|
| 背景 | `bg-gray-50` | `#f5f5f7` (surface-light) |
| 卡片底色 | `bg-white border` | 无边框，照片本身即是卡片 |
| 圆角 | `rounded-lg` | 5px (Apple 小圆角) |
| Hover | `bg-gray-100` | 轻微 scale(1.02) + 柔和阴影浮起 |
| 间距 | gap-2 (8px) | gap-3 (12px) — 更多呼吸空间 |
| 文字 | `text-xs text-gray-600` | `text-[14px] text-text-primary` SF Pro |
| 星级评分 | 黄色 ⭐ 叠加 | 保留，移至卡片下方文字行 |

**3.2 筛选面板**

当前：左侧固定 w-56 栏  
目标：
- 默认收起（仅显示搜索框 + 筛选图标）
- 点击展开为浮层抽屉（从左滑出，毛玻璃背景）
- 或作为顶栏下方的折叠条（类似 Apple Store 筛选器）

**3.3 工具栏**

当前：杂色按钮散布  
目标：
- 简洁工具栏：选择模式 / 识别按钮 / 排序
- 按钮统一使用 `btn-primary` + `btn-ghost` 两种形态
- 识别进度条：保持 emerald 绿条，但加上更优雅的圆角和动画

---

### Phase 4：照片详情页 (PhotoDetailView)

**4.1 图片展示区**

| 项 | 当前 | 目标 |
|----|------|------|
| 背景 | `bg-black` 局部 | 全宽纯黑区域，照片居中 |
| 布局 | 两栏 flex | 上方全宽暗色沉浸图片区 + 下方浅色信息区 |
| 翻页按钮 | 文字按钮 | 半透明圆形媒体控制按钮 (Apple 风格) |

```
┌─────────────────────────────────────────────────┐
│               ← 纯黑背景，照片居中 →              │  ← 暗色沉浸区
│     ◂  [        照片 (max-h-70vh)       ]  ▸    │
│               ★★★☆☆  ·  北红尾鸲               │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│  识别结果              │  EXIF 数据              │  ← 浅色信息区
│  #1 北红尾鸲 92.3%    │  相机: Sony A7M4        │
│  ...                  │  焦距: 200mm            │
└─────────────────────────────────────────────────┘
```

**4.2 信息区**

- 背景：`#f5f5f7`
- 表格行：无显式边框，靠 padding 分隔
- 标签：`text-[14px]` tertiary 色
- 值：`text-[14px]` primary 色

---

### Phase 5：仪表盘 (DashboardView)

**5.1 统计卡片**

当前：emoji + 数字 + 白底带边框  
目标：
- 两行/四列网格
- 暗色卡片 (`#272729`) + 白字大数字 + 浅灰标签
- 无边框，统一圆角 8px
- 数字使用 `SF Pro Display` 40px weight 600

**5.2 系统信息区**

- 浅色区 `#f5f5f7` 背景
- 进度条保持绿色但更扁平 (h-1.5)
- 操作按钮统一 `btn-primary` / `btn-dark`

---

### Phase 6：登录页 & 上传页

**6.1 登录页**

当前：居中白色卡片 shadow-lg  
目标：
- 全屏 `#f5f5f7` 背景
- 居中卡片无阴影无边框，仅靠白色对比
- 蓝色提交按钮 `btn-primary`
- 输入框：底部 1px 灰线，聚焦蓝色（Apple 极简表单风格）

**6.2 上传页**

当前：虚线拖拽区  
目标：
- 保持虚线拖拽语义，但改为 `border-[rgba(0,0,0,0.12)]`
- 拖入时高亮边框改为 Apple Blue
- 进度条使用 Apple Blue 填充

---

### Phase 7：其余页面 (视频 / 连拍 / 鸟种 / 去重 / 设置)

统一应用 Phase 1 的令牌和组件类：
- 所有 `bg-gray-50` → `bg-surface-light`
- 所有 `bg-white border border-gray-200` → `card-apple`（去掉 border）
- 所有按钮 → `btn-primary` / `btn-dark` / `btn-pill` / `btn-ghost`
- 所有 `text-blue-600` → `text-apple-link-light`
- 暗区内链接 → `text-apple-link-dark`
- 表格行：去掉 `border-b`，改用内边距 + 斑马纹或 hover 灰底

---

### Phase 8：响应式适配

| 断点 | 策略 |
|------|------|
| < 640px | 汉堡菜单，照片单列 / 两列，筛选全屏抽屉 |
| 640-1024px | 顶部导航完整展示，照片 3-4 列，详情页单栏堆叠 |
| > 1024px | 完整桌面布局，照片 5-6 列，详情页上下分区 |

---

## 四、不改动的部分

| 项 | 原因 |
|----|------|
| **虚拟滚动** (RecycleScroller) | 性能关键，保留 |
| **Pinia 状态管理** | 与 UI 无关 |
| **API 调用层** | 纯数据层 |
| **路由结构** | URL 不变 |
| **后端** | 完全不动 |
| **Toast 逻辑** | 仅更新样式 |

---

## 五、变更文件清单

| 文件 | 变更类型 | 描述 |
|------|----------|------|
| `tailwind.config.js` | 修改 | 替换 colors 令牌，添加 fontFamily |
| `style.css` | 修改 | 字体回退链 + 按钮组件类 + 卡片类 + 全局排印 |
| `index.html` | 修改 | body class 更新 (`bg-surface-light`) |
| `App.vue` | **重写** | 去掉侧栏 flex 布局，改为单列 |
| `AppHeader.vue` | **重写** | → Glass Nav（毛玻璃暗色导航 + 内联链接） |
| `AppSidebar.vue` | **删除/存档** | 导航移入 Header；移动端作为全屏菜单保留逻辑 |
| `GalleryView.vue` | 修改 | 网格样式 + 筛选面板交互 + 工具栏 |
| `PhotoDetailView.vue` | 修改 | 暗色沉浸图片区 + 浅色信息区 |
| `PhotoCard.vue` | 修改 | 去 border、调圆角、hover 效果 |
| `FilterPanel.vue` | 修改 | 可折叠/抽屉化 |
| `DashboardView.vue` | 修改 | 暗色统计卡 + 布局优化 |
| `LoginView.vue` | 修改 | 极简表单风格 |
| `UploadView.vue` | 修改 | 拖拽区 + 进度条样式 |
| `Toast.vue` | 修改 | 颜色令牌替换 |
| 其余视图 | 修改 | 统一应用令牌 (bg/text/border/btn) |

---

## 六、风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| 去掉侧栏后导航项溢出 | 中 | 顶栏在 > 8 项时缩写 + "更多"下拉 |
| SF Pro 在非 macOS 设备上缺失 | 低 | 回退链包含 `-apple-system` + `PingFang SC` + `Helvetica Neue` |
| 暗色区对比度不足 (WCAG) | 中 | 所有文字确保 4.5:1 以上对比度 |
| 虚拟滚动与新样式冲突 | 低 | RecycleScroller 只管布局位置，样式独立 |
| 大范围 class 替换引发遗漏 | 中 | 分 Phase 逐步替换，每 Phase 完成后视觉 Review |

---

## 七、建议实施顺序

```
Phase 1 (设计令牌)  ← 基础，后续依赖
  ↓
Phase 2 (导航重构)  ← 全局布局变更
  ↓
Phase 3 (照片库)    ← 核心页面，用户最常用
  ↓
Phase 4 (照片详情)  ← 核心页面
  ↓
Phase 5-7 (其余页面) ← 批量应用令牌
  ↓
Phase 8 (响应式)    ← 最后统一适配
```

**预计改动约 15 个文件，以样式/类名替换为主，不涉及业务逻辑变更。**

---

请审阅后告知：
1. 是否同意取消侧栏、改为顶部导航？
2. 照片详情页是否采用上下分区（暗色图片 + 浅色信息）还是保持左右分栏？
3. 是否需要暗色模式 (dark mode) 切换支持？
4. 是否有特定页面需要优先处理？
