# TrendRod UX 提升方案 — 2026.06.13

> **范围**：仅 `static/index.html`（1932 行单文件 SPA-like 单页），不动后端 `app/main.py`。
> **目标**：让一个动量轮动策略监控工具变成"打开就懂、一眼能看、敢动手"的产品。
> **基调**：金融数据红涨绿跌（中国惯例）；4 主题保留；暗色 + 亮色双轨。
> **不涉及**：后端 API 改造（C1 鉴权）、Docker 安全（H14）、算法（H7/H8 除外）。

---

## 0. TL;DR（决策摘要）

| 项 | 当前 | 提议 | 引用 |
|---|---|---|---|
| 信息架构 | 1 个 1932 行单页 | **3 视图**（Dashboard / Portfolio / Scheduler），URL 路由 | L14 无 README |
| 设计令牌 | 4 主题 + 16 个色变量（**命名错乱**：`--green` 在 light-blue 是蓝） | 重构令牌层，命名语义化 | **L8** |
| 状态反馈 | alert/confirm（破坏主题） + 3 秒 msgBar（无 aria） | 统一 **Toast** + **Dialog** + **Skeleton** + **EmptyState** | **M24 / M28** |
| Chart | 净值 + 5 个 marker，无 benchmark 副轴独立区间 | 净值面积图 + **drawdown 副图** + **benchmark 虚线** + 区间段 | H20 / H21 / L3 |
| 表格 | 轮动只显示 60 条（last 60 截断） | 分页/虚拟滚动 + 排序 + 筛选 | **M25** |
| 性能感知 | 同步 fetch，5–10s 等待 | **骨架屏 → 旧数据 + 后台增量** | H3 |

---

## 1. 当前状态审计（结合 issues.md）

### 1.1 文件与结构
- `static/index.html` 1932 行（HTML 484–599 + CSS 8–483 + JS 602–1931 全混）
- `static/chart.umd.min.js` 已 6.11 整改（fill:false），但仍有视觉 bug（H20 双 fill）
- **没有** 路由、组件、状态管理；`let activePf / portfolios / filteredRot` 全局变量散落

### 1.2 直接关联 UI 的 issues（按严重度）
**CRITICAL** — 必须先解决，否则后面改动会被波及：
- **C5** XSS via name 字段（已修：`escHtml()` 已存在，但 683/843/865/1795 全部 innerHTML 仍要审计）
- **C6** inline onclick + 无 CSP（**已整改**：`data-action` 委托机制 line 619–634；剩余 `ondragstart/over/leave/drop/end` line 911 待迁移）

**HIGH — UI 直接相关**：
- **H2** `filterAndRender` 空 nav 早 return 留下旧 chart（line 1231）— **UI 错位**，必修
- **H19** `addIndex/removeIndex/duplicatePf` 不 await，状态竞态 → 偶发空 portfolio
- **H20** chart 双 fill 已修（dataset[0].fill=false + gradientFill plugin 单写），但 **drawdownZones plugin** 还在 `rgba(255,71,87,0.06)` hardcoded 红色（H20 修一半）
- **H21** `renderBenchDisplay` shortcut `#1m` 不解析（line 1727-1728 仍 `p.date >= '#1m'`）

**MEDIUM — UI 体感**：
- **M19** `closePresetsDropdown` 闭包 stale element（line 1188-1191）
- **M20** `d.toISOString()` UTC 偏移 1 天（line 1147, 1224 — `toISOString` 是 UTC，凌晨取前一天）
- **M21** `pctClass(0)` 当 up（line 676 — `v >= 0` 应为 `v > 0`）
- **M22** `animateValue` regex 替换 `[\d.-]+` 多数字失效（line 1704）
- **M23** 主题切换/刷新按钮缺 `aria-label`（line 492-498）
- **M24** `alert()`/`confirm()` 破坏主题（line 773 `prompt`, 792, 969, 1096, 1097, 1858）
- **M25** rotation 只显示 last 60（line 1752 — 三年回测可见上限 60 轮，太少）
- **M26** rotation filter 顺序敏感（line 1755 — 同日先卖后买配对错位）
- **M27** `window.onerror` 注入 unescaped msg/line（line 616 — XSS 路径）
- **M28** `showMsg` 无 `aria-live="polite"`（line 177-178, 694-699）
- **M29** 搜索 debounce 无 `AbortController`（line 1025-1030）
- **M30** 全局 `* { margin:0; padding:0 }` reset 太粗暴（line 9）

**LOW — 影响细节**：
- **L4** `pctClass(0)` 同 M21
- **L5** `loadStatus` 无 loading 指示（line 1102-1121 — skeleton 已存在但只在初次加载用）
- **L6** 离线/网络错处理不足（line 1118-1120）
- **L7** 日期算术固定 `86400000ms` 跨夏令时错位（line 1258, 1658, 1780）
- **L8** **主题色变量名与值不匹配**（`--green: #0066cc` 实际是蓝 — 视觉系统根本性 bug）
- **L9** `buildDateBar` 重建丢失 datePicker 焦点（line 1096-1130）
- **L14** 无 README（IA 没文档化）

---

## 2. 信息架构（IA）提议

### 2.1 当前 IA（隐式 1 层）
```
[header: title + refresh + 主题切换]
[pf bar] [⚙️]                      ← portfolio 切换 + 管理
[标的 chip bar] [搜索]
[持仓卡]
[动量/前N/仓位/均线/持期/止损 + 保存 + 基准]   ← 全部 CRUD 在一行
[定时刷新 chips + 日志按钮]
[主区：8 个指标卡]
[区间选择]
[净值曲线 / 收益率切换]
[年度收益]
[轮动历史]
```

### 2.2 提议 IA（**3 视图 + URL 路由**）
```
/                       → Dashboard（全部组合对比）
/p/:pfid                → Portfolio 详情（**当前单页改造成这个**）
/p/:pfid/config         → Portfolio 配置（标的池 / 动量 / 调仓）
/scheduler              → 调度中心（日志 + cron）
```

**为什么不拆 SPA**：
- `index.html` 已 1932 行，但**功能其实只 4 块**（组合切换 / 数据可视化 / 配置 CRUD / 调度）
- 拆 SPA 引入 bundler + router，反而提高 L14/H6 复杂度
- **建议**：保留单页，用 **hash router**（`#pf=xxx / #cfg / #sch`）切 3 视图，URL 可分享

### 2.3 视图职责
| 视图 | 内容 | 当前对应 |
|---|---|---|
| **Dashboard** (`/`) | 全部组合小卡（迷你 sparkline + 关键指标 + 持仓 ticker） | 无（**新增**） |
| **Portfolio Detail** (`/p/:pfid`) | 当前单页的核心 — 净值/轮动/持仓 | 主区全部 |
| **Portfolio Config** (`/p/:pfid/config`) | 标的池 + 动量 + 调仓 + 止损参数 | ctl-row + 抽屉 + pool-bar |
| **Scheduler** (`/scheduler`) | cron chips + 日志 + 立即运行 + 健康状态 | sch-row + sch-log-area |

### 2.4 导航组件
- **顶部 nav**：`TrendRod 标识 / Dashboard / Scheduler / 当前组合名 breadcrumb / 主题切换 / 刷新`
- **左侧侧栏（桌面 ≥1024px）/ 底部 tabbar（手机）**：Dashboard / 当前组合 / Scheduler
- **Portfolio 切换**：从顶部 pf-bar 移入 **Portfolio Detail 内的二级 nav**（dropdown 或 tab）

> 引用：**L14**（无 README → IA 没文档）+ 新组件：`TabBar` `SideNav` `Breadcrumb`

### 2.5 响应式断点
| 断点 | 行为 |
|---|---|
| < 640px | 单栏 / 底部 tabbar / pf-bar 抽屉式 |
| 640–1024px | 双栏（chart 左 / stats 右）/ pf-bar 顶部 |
| ≥ 1024px | 三栏（侧栏 / 主区 / 配置抽屉可悬浮）/ pf-bar 改 SideNav 子项 |

---

## 3. 设计令牌（Design Token）草案

### 3.1 命名重构 — 修 L8
**核心问题**：现在 `--green` 在 light-blue 主题里是 `#0066cc`（蓝），变量名误导。

**重命名方案**（**双语义层**）：
```css
:root {
  /* ─── 语义层（应用代码只用这层） ─── */
  --color-bull: var(--palette-up);   /* 涨 = 红（中国惯例）*/
  --color-bear: var(--palette-down); /* 跌 = 绿 */

  /* ─── 调色板层（主题切换的实体） ─── */
  --palette-up: #ff4757;             /* 红 */
  --palette-down: #00e5a0;           /* 绿 */
  --palette-neutral: #6c7adb;        /* 调仓（蓝紫）*/
  --palette-stop: #00e5a0;           /* 止损 = bear */

  /* ─── 中性层 ─── */
  --palette-bg: #0a0e1a;
  --palette-surface: #12122a;
  --palette-surface-hover: #1a1a3a;
  --palette-text: #e0e7ff;
  --palette-text-dim: #8090b0;
  --palette-text-muted: #5060a0;
  --palette-border: #1e2040;

  /* ─── 尺寸节奏 ─── */
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px;
  --space-4: 16px; --space-5: 24px; --space-6: 32px; --space-7: 48px;

  /* ─── 圆角 ─── */
  --radius-sm: 6px; --radius-md: 10px; --radius-lg: 14px; --radius-pill: 999px;

  /* ─── 字号 + 行高（金融数字 tabular-nums） ─── */
  --font-xs: 11px; --font-sm: 12px; --font-md: 13px; --font-lg: 15px;
  --font-xl: 18px; --font-2xl: 22px; --font-3xl: 28px;
  --font-numeric: ui-monospace, 'SF Mono', Menlo, monospace;
  --leading-tight: 1.25; --leading-normal: 1.5; --leading-relaxed: 1.75;

  /* ─── 阴影 / 聚焦 ─── */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.18);
  --shadow-lg: 0 12px 32px rgba(0,0,0,0.32);
  --focus-ring: 0 0 0 2px var(--palette-up);
  --focus-ring-bear: 0 0 0 2px var(--palette-down);

  /* ─── 动效 ─── */
  --ease-out: cubic-bezier(.16,1,.3,1);
  --ease-in-out: cubic-bezier(.4,0,.2,1);
  --dur-fast: 150ms; --dur-base: 220ms; --dur-slow: 360ms;
}
```

### 3.2 主题映射（修 L8）
| 主题 | palette-up | palette-down | palette-bg | palette-surface |
|---|---|---|---|---|
| **starry**（默认） | `#ff4757` 红 | `#00e5a0` 绿 | `#0a0e1a` | `#12122a` |
| **dark-gray** | `#f87171` 红 | `#4ade80` 绿 | `#1a1a1a` | `#252525` |
| **light-blue** | `#cc2200` 红 | `#0066cc` 蓝绿 | `#f0f4f8` | `#ffffff` |
| **warm** | `#c0392b` 红 | `#2d7a4f` 绿 | `#f5f0e8` | `#fffdf8` |

**保留规则**：`color-bull` 永远是红，`color-bear` 永远是绿 — 不被主题覆盖。

### 3.3 受 popular-web-designs 启发的细节
- **Linear 的 command palette**（`Cmd+K` 模糊搜索标的 / 跳配置）→ 减少 pf-bar 横向滚动痛点
- **Vercel 的统计数字 typography**（`tabular-nums` + 字重对比 + 小字下标单位 "次/年"）
- **TradingView 的 chart crosshair + tooltip 联动**（已有 crosshairPlugin — 升级成完整 OHLC tooltip）
- **Stripe 的渐变 + 微阴影**（stat-card 用 `--shadow-sm` 提升层级感）
- **Apple Health 的 card stack**（持仓 + 轮动用卡片堆叠而非表格）

---

## 4. 组件清单（前端组件库）

### 4.1 基础原语
| 组件 | 描述 | 替换现有 |
|---|---|---|
| `Button` | 主/次/危险/幽灵 4 变体；loading state | 散落的 `ctl-btn` `pfcARD-btn` |
| `Input` | 数字 / 文本 / select；focus ring；error state | `ctl-input` `sch-input` |
| `Chip` | 可关闭 / 不可关闭 / 加号 | `pool-chip` `pf-tab` `sch-chip` |
| `Icon` | SVG sprite + 自定义 token（涨跌箭头 / ⚙ / ↻） | emoji 散落 |

### 4.2 复合组件
| 组件 | 描述 | 替换现有 |
|---|---|---|
| **`Toast`** | 4 象限自动消失；success/error/warn/info；`aria-live` | `msgBar`（**修 M28**） |
| **`Dialog`** | 危险/确认/输入；ESC 关闭；focus trap | `prompt/confirm/alert`（**修 M24**） |
| **`Drawer`** | 右滑出；3 宽度（sm 320 / md 420 / lg 560） | `pfDrawer`（**保留扩展**） |
| **`Skeleton`** | 4 形态：card / chart / row / stat | `.skeleton`（已有，**统一接口**） |
| **`EmptyState`** | 标题 + 描述 + CTA 图标 | 散落的"暂无数据" div（**修 M22**） |
| **`DataTable`** | 排序/筛选/分页/虚拟滚动 | rotation 直接渲染（**修 M25**） |
| **`Tabs`** | 受控 / 非受控；URL hash 同步 | `.pf-bar` `.date-bar` |
| **`StatCard`** | label + value + 趋势 + delta | `.stat-card`（已有，**token 重构**） |
| **`HoldingCard`** | ticker + 名称 + 入场 + 动量 + 持仓收益 | `.holding-card` |

### 4.3 复合视图
| 组件 | 描述 |
|---|---|
| **`NavChart`** | 净值面积 + drawdown 副图 + benchmark 虚线 + 调仓/买入/止损 marker |
| **`RotationTimeline`** | 垂直时间线卡片（持期 + 调仓动作 + 配对显示） |
| **`PortfolioCard`**（Dashboard 用） | 迷你 sparkline + 关键 3 指标 + 持仓 ticker |
| **`SchedulerTable`** | cron 列表 + 最近运行 + 错误高亮 + 手动触发 |
| **`SearchPalette`** | `Cmd+K` 全局模糊搜索（标的 / 组合 / 配置） |

---

## 5. 交互细节表（5 态全覆盖）

### 5.1 加载态
| 场景 | 当前 | 提议 |
|---|---|---|
| 首屏 | skeleton（已有 line 309–316，**仅显示在 `loading` div 内**） | skeleton + **版本号/构建时间**（底部 footer） |
| 刷新中 | 按钮旋转 + skeleton | 旋转 + **进度条**（后端报 `done/total`） + **保留旧数据** |
| akshare 慢 | 30s+ 无反馈（H3） | 后端 SSE/WebSocket 推进度；前端显示 "已抓 3/9" |
| 切换 pf | 全屏 skeleton（line 1090–1091） | **只 skeleton 主区**，header/pf-bar 不动 |
| 搜索输入 | 300ms debounce（**M29 无 abort**） | debounce + `AbortController` + 上次结果保留直到新结果到 |

### 5.2 错误态
| 场景 | 当前 | 提议 |
|---|---|---|
| API 500 | `alert()`（M24）+ 红字 div（line 1118） | **Toast error** + 错误码（`ERR_DB` / `ERR_AKSHARE` / `ERR_AUTH`）+ 重试按钮 |
| XSS 尝试 | 已被 `escHtml` 拦截但用户无感知 | Toast warn "输入包含非法字符" + 字段红框 |
| 网络断 | `请求失败` 红字（L6） | **离线 banner**（顶部黄条）+ 自动重试 + 失败队列 |
| 鉴权失效（C1） | 当前无鉴权，假设已加 | Toast `会话过期` + 重定向登录 |

### 5.3 成功态
| 场景 | 当前 | 提议 |
|---|---|---|
| 保存参数 | `showMsg` 3 秒绿字 | **Toast success** 2 秒 + **输入框微绿色脉冲**（确认变化已写入） |
| 添加标的 | showMsg | Toast + chip 滑入动画（`transform-origin: left`） |
| 删除组合 | `confirm()` → showMsg | Dialog（修 M24）→ **Undo 5 秒**（toast 底部"撤销"按钮） |
| 调度执行完 | `showMsg('刷新完成,新增 N 条')` | Toast + **Dashboard 卡片数字 pulse**（让用户感知到变化） |

### 5.4 空态（**3 种区分**）
| 场景 | 当前 | 提议 |
|---|---|---|
| 无组合 | 自动创建 default | EmptyState 图标 + "创建第一个组合" CTA |
| 组合无标的 | "暂无数据，请刷新" 粗暴 | EmptyState 插画 + "+ 添加标的" 按钮（直接 focus 搜索框） |
| 选区间无数据 | **H2 bug**：旧 chart 不刷新 | EmptyState + "清除区间筛选" CTA（**修 H2**） |

### 5.5 确认态
| 场景 | 当前 | 提议 |
|---|---|---|
| 删除组合 | `confirm()` 破坏主题（M24） | Dialog：标题 + 红色"删除"按钮 + 输入组合名确认（防误删） |
| 重置参数 | 无 | Dialog："放弃当前编辑？" |
| 危险刷新 | `runScheduleNow` 直接触发 | 加 debounce 按钮 + 3s 倒计时 |

---

## 6. 视觉细节（具体改 L8 / M20 / M21 等）

### 6.1 颜色语义（L8 修）
```css
/* 应用代码全部用语义层 */
.up    { color: var(--color-bull); }   /* 涨 = 红 */
.down  { color: var(--color-bear); }   /* 跌 = 绿 */
.neutral { color: var(--palette-neutral); }
```

### 6.2 数字字体（M22 修 + Vercel 启发）
- 所有数值 `font-family: var(--font-numeric); font-feature-settings: 'tnum';`
- 单位（"次/年"、"天"）用 `font-size: var(--font-xs); color: var(--palette-text-dim);` 下标化
- 大数字（年化、sharpe）`font-size: var(--font-2xl); font-weight: 700; letter-spacing: -0.02em;`

### 6.3 间距节奏
- 现在 spacing 散乱（`4/6/8/10/12/14/16`），统一到 `--space-1..7` (4/8/12/16/24/32/48)
- 卡片 padding 从 `12px 14px` 改为 `--space-3 var(--space-4)` (= 12/16)

### 6.4 阴影层级
- stat-card 从无阴影 → `--shadow-sm` + hover `--shadow-md`
- toast 从无 → `--shadow-lg`
- drawer 从无 → `--shadow-lg`

### 6.5 focus ring
- 所有可交互元素 `:focus-visible { outline: none; box-shadow: var(--focus-ring); }`
- 危险操作 focus ring 用 `--focus-ring-bear`（绿）

---

## 7. 表格 / 图表增强

### 7.1 NavChart（H20 续修 + 副图 + benchmark 独立）
**当前状态**：dataset[0] `fill:false` + gradientFill plugin + drawdownZones plugin 仍有 hardcoded 红色。
**提议**：
- 颜色全部走 token：`rgba(var(--palette-up-rgb), 0.15)`（在 `:root` 加 RGB 三元组 token）
- **drawdown 副图**：拆成上下两个 y axis，上为净值（`y`），下为 drawdown %（`yDD`）；副图背景红区淡 0.06 → 0.12
- **benchmark 虚线**：当前 y2 已存在，但 user 看不到基准回报数字（修 **H21** — `renderBenchDisplay` 解析 `#1m`）
- **区间段**：在 chart 顶部加区段标记条（"924 → 21顶" 等 preset 高亮）
- **OHLC tooltip**（TradingView 启发）：hover 显示当日 NAV + 持仓 + 当日动作 + 基准差

### 7.2 RotationTimeline（M25 / M26 修）
**当前**：直接 innerHTML 渲染 + last 60 截断 + 同日配对错位。
**提议**：
- 用 `DataTable` 组件，支持分页（25/50/100）
- 列：开始日 / 持仓期(天) / 标的 / 持仓收益 / 同期基准 / 超额
- 行 hover → 弹 Popover 显示"为什么买"（动量分值 + 排名变化 — 后端 `compute()` 需扩字段，**仅前端能改的部分**先做 UI）
- 排序：日期 / 收益 / 持仓期
- 筛选：只看盈利 / 只看亏损 / 按标的筛选
- **虚拟滚动**（row > 100 时）— 用 `IntersectionObserver` 简单实现，不用 library

### 7.3 Dashboard PortfolioCard（新增）
- 顶部 mini-sparkline（60px 高，用 canvas 渲染 1 个 dataset）
- 中部组合名 + 持仓 ticker（`sh000300` 等，带涨跌色）
- 底部 3 指标：本期间收益 / 年化 / 最大回撤
- 整卡点击 → 跳 `/p/:pfid`

---

## 8. 性能感知策略（H3 修 + 增量加载）

### 8.1 问题
- `fetch_new` 9 标的 × 26 portfolio = 234 次串行同步（H3 已标 HIGH）
- 用户首屏等 5–10 秒看到 skeleton
- 刷新时整页骨架屏，体验"硬切"

### 8.2 提议（**仅前端能做的部分**）
1. **保留旧数据 + skeleton 局部化**
   - 切换 pf / 改区间：不要 `loading.style.display='block'`，只 skeleton 主区
   - chart 不销毁，navChart.destroy() 改为 `chart.data = newData; chart.update('none')`
2. **进度反馈**（需要后端 SSE/进度端点，但**前端 UI 先就绪**）
   - 在刷新按钮旁加进度条 `<progress value=0 max=100>`
   - 后端若有进度回报 → UI 显示 "已抓 3/9"
3. **乐观更新**
   - 添加标的：UI 立刻 chip 滑入（无需等 API 返回）
   - 失败回滚 + Toast error
4. **Web Worker 计算动量分值**（H6 拆 compute 后的下游优化）
   - 现阶段优先：把 stats-grid 数字从同步 `innerHTML` → `requestIdleCallback` 分批渲染
5. **debounce + AbortController**（M29 修）
   - 搜索、参数变更、日期选择全部用 AbortController 取消 in-flight

### 8.3 渲染优化
- `fullNavData` 按日期索引（Map），区间筛选 O(1) start
- rotation 列表按 pfid 索引缓存
- chart options `animation: { duration: 220, easing: 'easeOutCubic' }`

---

## 9. 可访问性（A11y） — 顺手修

| 问题 | 修法 | 引用 |
|---|---|---|
| 主题切换按钮缺 aria-label | 加 `aria-label="切换主题：深灰"` | M23 |
| `showMsg` 缺 aria-live | `<div role="status" aria-live="polite">` | M28 |
| 键盘焦点不可见 | `:focus-visible` 统一 ring | 新增 |
| `ondragstart` 内联 + 缺键盘等价 | 加"上下移动"按钮 + Space 触发 | C6 |
| Toast 缺 `role="alert"` | `role="alert" aria-atomic="true"` | 新增 |
| 抽屉缺 focus trap | 打开时锁定 Tab 在内部 + ESC 关闭 | 新增 |

---

## 10. 实现路线图（Phase 1 / 2 / 3）

### Phase 1 — **设计基础 + 关键 bug**（估 1–2 天，**风险低**）
**目标**：视觉系统统一、修影响体感的高优 bug。

| # | 任务 | 引用 | 风险 |
|---|---|---|---|
| 1.1 | 重构 CSS token（语义层 + 调色板层） | L8 | 低（纯 CSS 替换） |
| 1.2 | 4 主题颜色重映射 | L8 | 低 |
| 1.3 | 修 `pctClass(0)` 为 `v > 0` | M21 / L4 | 极低（1 行） |
| 1.4 | 修 `d.toISOString()` UTC 偏移 | M20 | 低（`toISOString().split('T')[0]` → 字符串算术） |
| 1.5 | 修 `filterAndRender` 空 nav 早 return（H2） | H2 | 中（要清空 chart + rotation + 显示 empty） |
| 1.6 | 修 `renderBenchDisplay` shortcut `#1m` 解析 | H21 | 低（复用 filterAndRender 的解析） |
| 1.7 | 加 `aria-label` 给按钮 + `role="status"` 给 msgBar | M23 / M28 | 极低 |
| 1.8 | 字体数字 tabular-nums + 字号节奏统一 | M22 | 低 |
| 1.9 | 全局 reset 改成定向 reset | M30 | 中（可能破坏现有布局） |

**Phase 1 交付**：主题切换视觉正常；`pctClass(0)` 显示 green down；空区间显示 EmptyState 而非旧 chart。

### Phase 2 — **状态系统 + Toast/Dialog 替换**（估 2–3 天，**风险中**）
**目标**：替换 alert/confirm/prompt；统一 Toast；5 态全覆盖。

| # | 任务 | 引用 | 风险 |
|---|---|---|---|
| 2.1 | 实现 Toast 组件（4 type + auto-dismiss + 队列） | M28 | 低 |
| 2.2 | 实现 Dialog 组件（focus trap + ESC + 危险样式） | M24 | 中（替换 5+ 处 prompt/confirm/alert） |
| 2.3 | 替换所有 `alert()` → Dialog | M24 | 中（onerror 也要修 M27） |
| 2.4 | 替换所有 `confirm()` → Dialog（删除组合、添加标的等） | M24 | 中 |
| 2.5 | `window.onerror` 用 textContent 注入 | M27 | 低 |
| 2.6 | 实现 EmptyState 组件 + 3 场景文案 | 新增 | 低 |
| 2.7 | Skeleton 局部化（切 pf 不全屏 skeleton） | H3 | 中 |
| 2.8 | 搜索 AbortController + 上次结果保留 | M29 | 低 |
| 2.9 | 离线 banner（navigator.onLine） | L6 | 低 |

**Phase 2 交付**：所有弹窗主题一致；切换 pf 不"闪"；空态有引导。

### Phase 3 — **IA + 视图拆分 + 性能**（估 3–5 天，**风险高**）
**目标**：拆 3 视图；性能感知；表格升级。

| # | 任务 | 引用 | 风险 |
|---|---|---|---|
| 3.1 | Hash router（`#pf=xxx / #cfg / #sch`） | 新增 | 中（破坏现有 `#1m` 等区间 hash）— **要兼容**：把区间改 query string |
| 3.2 | Dashboard 视图（PortfolioCard × N） | 新增 | 中（需要后端批量 API，若没有则前端 N 次 fetch） |
| 3.3 | Portfolio Detail 视图（当前主区） | 重构 | 高（结构大改） |
| 3.4 | Portfolio Config 视图（标的池 / 动量 / 调仓） | 重构 | 高 |
| 3.5 | Scheduler 视图（日志表 + cron + 手动） | 重构 | 中 |
| 3.6 | SideNav（桌面）+ BottomTabBar（手机） | 新增 | 中 |
| 3.7 | RotationTimeline DataTable 化（分页 + 排序 + 虚拟滚动） | M25 / M26 | 中（虚拟滚动要小心 chart 重新渲染） |
| 3.8 | NavChart drawdown 副图 + benchmark 独立轴 | H20 / L3 | 中 |
| 3.9 | 响应式断点（640 / 1024） | 新增 | 中 |
| 3.10 | Web Worker 计算统计（数字大时分批渲染） | 新增 | 低 |
| 3.11 | README 写 IA 文档 | L14 | 极低 |

**Phase 3 交付**：3 视图 + 路由；手机可看；轮动表 1000+ 条不卡。

---

## 11. 风险与开放问题

### 11.1 已知风险（标在 Phase 表里）
| 风险 | Phase | 缓解 |
|---|---|---|
| 主题色 token 重构可能打破现有 CSS 选择器 | P1 | 一次性 grep + Playwright 视觉回归（无则手动截图 4 主题） |
| alert/confirm 替换 5+ 处可能漏 | P2 | 全局 grep `alert\(\|confirm\(\|prompt\(`，每处单测 |
| Hash router 与 `#1m` 区间 hash 冲突 | P3 | 区间改 `?range=1m` query string；URL 兼容旧 hash |
| Dashboard 视图需要后端批量 API | P3 | 若无 → 前端 N 次 fetch + 缓存；Phase 3.2 标注为"可降级" |
| 移动端断点改动可能影响平板体验 | P3 | P3.9 先做 `max-width: 1023` 单栏，`min-width: 1024` 三栏，中间区保留 |

### 11.2 不能由 cc 决定、需用户拍板

1. **是否真要拆 3 视图**？当前单页 dpr 适合"一个组合看到底"的场景，Dashboard 在小屏（< 5 组合）反而是浪费。
   - **建议**：用户组合数 ≤ 5 时不做 Dashboard，只把 Scheduler 拆出去。

2. **导航形式**：顶部 nav vs 侧栏 vs 底部 tabbar？
   - **建议**：桌面侧栏 + 手机底部 tabbar（最常见模式）。

3. **toast 保留时长**：2s / 3s / 5s？undo 按钮 5s 是否够？
   - **建议**：默认 3s；带 undo 的 5s；error 不自动消失。

4. **轮动表分页 vs 无限滚动**？无限滚动对长回测更顺，分页更精确。
   - **建议**：默认分页 25 条/页，提供"加载更多"按钮降级到无限滚动。

5. **保留 emoji 图标 vs 换 SVG sprite**？
   - **建议**：保留 emoji（轻量），但**关键功能图标**（⚙ 刷新 ⚠ 错误 ✕ 关闭）换 SVG token。

6. **是否引入构建工具**（Vite）来拆 CSS/JS 文件？
   - **建议**：暂不引入。1932 行单文件单页用 hash router + 模块化命名空间（IIFE）足够。

7. **A11y 优先级**：键盘 + 屏读器 vs 鼠标优先？
   - **建议**：键盘 + focus ring 是底线（M23 + focus-visible）；完整 ARIA 等 Phase 3 之后再说。

8. **是否动 backtest_bt.py**（H7/H8 mom_weights 不一致）？
   - **建议**：**方案里不碰**（用户说不动后端），但 README 提醒：前端 UI 显示的"年化"和 backtest_bt 输出在某些 portfolio 上会不一致。

### 11.3 必须先修但不在本方案范围的（**阻塞项**）

> Phase 1 起步前先修这些，否则后面的改动会反复翻动

- **C5** XSS via name — 已有 `escHtml` 但要全量审计 innerHTML（建议先做静态扫描）
- **C6** inline onclick — 已大部分迁委托，剩 `ondragstart/over/leave/drop/end` 5 个
- **M27** `window.onerror` 用 textContent
- **H2** `filterAndRender` 空 nav 早 return

这些修完，Phase 1 才开始能稳定推进。

---

## 12. 不在本次范围的（明确排除）

| 类别 | 不做原因 |
|---|---|
| 后端 main.py 任何改动 | 用户明确禁止 |
| C1 鉴权 / C3 全局锁 / H1 文件原子写 / H3 长任务 BackgroundTasks | 都是后端 |
| Docker 安全（H13/H14/H40-H42） | 都是 Dockerfile / docker-compose |
| H6 compute() 拆函数 / H7/H8 双引擎一致 | 都是后端 |
| backtest_bt.py 任何改动 | 用户没提，且是后端脚本 |
| 算法改进（动量分值、夏普公式等） | 不是 UX |
| 国际化 i18n（en/zh-CN 切换） | 用户没要求，且当前文案已 zh-CN |
| 暗色/亮色跟随系统（prefers-color-scheme） | 用户保留 4 主题手动选 |

---

## 13. 引用速查表（issues.md）

| UX 改动 | 引用 issue |
|---|---|
| 主题色 token 重构 | **L8** |
| 字体 tabular-nums + 字号节奏 | M22, **L5** |
| Spacing 节奏统一 | **M30** |
| 5 态全覆盖 | M24, M28, **L5**, **L6** |
| 替换 alert/confirm/prompt | **M24**, **M27** |
| aria-live + aria-label | **M23**, **M28** |
| Date 算术（toISOString / 86400000） | **M20**, **L7** |
| pctClass(0) 当 up | **M21**, **L4** |
| filterAndRender 空 nav 早 return | **H2** |
| renderBenchDisplay shortcut 解析 | **H21** |
| Chart drawdown 副图 + benchmark 独立 | H20（续修）, **L3** |
| RotationDataTable 分页 | **M25**, **M26** |
| 性能感知（skeleton 局部 + 乐观更新） | H3（前端部分） |
| Search AbortController | **M29** |
| buildDateBar 不丢焦点 | **L9** |
| Inline onclick 收尾（drag 5 个） | **C6**（剩余） |
| README + IA 文档 | **L14** |
| A11y focus ring | 新增 |
| 3 视图 + hash router | 新增 |
| Dashboard PortfolioCard | 新增 |

---

## 14. 验收口径

每个 Phase 完成后用以下口径验证：

1. **视觉**：4 主题切换 → 主区/卡片/数字/输入框全部跟着变色，无 hardcoded 颜色泄漏（grep `#[0-9a-f]{3,8}` 在 css block 里应为 0）
2. **状态**：5 态（loading/error/success/empty/confirm）每个至少有 1 个用例能触发 + 截图
3. **响应式**：320 / 768 / 1024 / 1440 四档宽度截图无横向滚动条（pf-bar / chart / 表格各看一次）
4. **A11y**：键盘 Tab 一圈能到所有按钮 + focus ring 可见
5. **性能**：首屏 < 1.5s（本地）；切 pf < 0.3s（已缓存）；切区间 < 0.2s（已缓存）
6. **回归**：跑现有 unit test（无 → 至少烟雾测：开页 → 加标的 → 刷新 → 看 chart）
7. **XSS**：name 字段输入 `<script>alert(1)</script>` 不弹窗

---

**下一步**：等用户从 11.2 列的 8 个开放问题里选方向（尤其是 #1 是否拆 3 视图），然后再决定 Phase 1 的范围和顺序。