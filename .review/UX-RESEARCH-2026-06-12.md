# TrendRod UX 提升研究 — 6.12 晚

**用户原话（6.12 23:50 提的）**：
> "明天要看下这个docker的功能实现，你可以先自己研究下，同时记录自己的想法到一个md文件，我先睡觉了，你就研究怎么让界面更好看，结构更合理，可以更好用这些，这些都交给cc处理，你记得记录"

## 任务定位

- **不是**改代码 → 是**研究 + 出方案**
- **目标**：界面更好看、结构更合理、更好用
- **交付**：方案文档（不是 PR），明天用户看了再决定哪些做

## 当前现状

### 文件结构
- `static/index.html`：**1932 行单文件**（HTML + CSS + JS 全混一起）
- `static/chart.umd.min.js`：Chart.js 库（CDN/local，CC 已 6.11 整改过 fill:false）
- 没有拆分 SPA、没有 router、没有 component

### API 端点（17 个）
- 组合管理：`/api/portfolios`（GET/POST/PUT/DELETE/reorder）
- 标的池：`/api/search_indices` `/api/portfolios/{pfid}/indices` (POST/DELETE)
- 数据：`/api/refresh` `/api/status`
- 调度：`/api/schedules` `/api/schedules/run-now`
- 日志：`/api/update-log`

### 已知问题（来自 .review/issues.md，6.12 全项目 code review）
- **CRITICAL (6)**: API 鉴权、apscheduler 缺、C3 全局锁、C4 闭包、C5 XSS、C6 inline onclick+CSP
- **HIGH (14)**: 写文件不原子、空 nav 早 return、请求线程同步、客户端入参无校验、id 无校验、compute 300 行耦合、H7/H8 mom 配置不一致...
- **MEDIUM/LOW 共 30 个**

### UI 现状
- 顶部固定 pf bar（横向 portfolio 切换）
- 主区：净值曲线 + 轮动记录 + 指标卡
- 抽屉：组合配置（标的池 / 权重 / 周期 / 调仓频率 / 止损）
- 调度器：cron 表达式列表
- 全部功能塞在 1932 行单页

---

## 研究方向（给 cc 重点深挖）

### 1. 信息架构（IA）
- **多组合并存**：现在 pf bar 横向滚 — 10+ 组合时怎么办？
- **导航**：现在只有顶部 pf bar + 抽屉；是不是缺**"全局视图"**（所有组合对比）、**"单组合详情"**、**"调度中心"** 三层结构
- **响应式**：手机/平板/桌面 — 抽屉/双栏/单栏怎么自适应
- **数据 vs 配置**：现在混在一起；是不是拆 `/dashboard`、`/portfolios/{id}/config`、`/schedules` 三个路由

### 2. 视觉系统
- **现在**：没有设计 token、颜色都是 hardcoded、spacing 散乱
- **建议**：
  - CSS variable 设计 token：`--color-up: #ff4757`（红涨）`--color-down: #00e5a0`（绿跌）`--bg-primary: #0a0e1a`（暗色）...
  - 间距 4/8/16/24/32 节奏
  - 字体：数字用 tabular-nums、标签用 sans
  - 颜色：**金融数据红涨绿跌**（中国惯例，与国际相反）
  - 暗色 + 亮色双主题
- **参考**：popular-web-designs skill 有 54 套真实设计系统（Stripe/Linear/Vercel/TradingView）

### 3. 交互细节
- **加载态**：现在 `暂无数据，请刷新` 太粗暴
  - skeleton（骨架屏）
  - 进度条（akshare 抓取时显示"已抓 N/总 N"）
  - 上次更新时间 + 自动刷新
- **错误态**：现在 500 直接报 `Internal Server Error` 弹窗
  - toast 通知（5s 自动消失）
  - 错误分类：网络/数据/权限 — 不同颜色
  - 重试按钮
- **成功态**：保存 portfolio 后有没有反馈？调仓完成后呢？
- **空态**：组合没标的 / 标的没数据 / 选日期范围空 — 三种空态区分
- **确认态**：删除 portfolio 直接 confirm() — 能不能用危险按钮 + 二次确认 + undo？

### 4. 表格与图表
- **当前 chart**：Chart.js line chart + stopLossOffsetPlugin — 双 fill bug 6.11 修过
- **建议**：
  - 净值曲线用面积图（gradient fill from --color-up 30% to 0%）
  - 加 **benchmark overlay**（沪深 300 + 标的自身）
  - 加 **drawdown 副图**（max DD / current DD）
  - 鼠标 hover 十字线 + tooltip 显示当日持仓
  - 区间选择（1M/3M/6M/1Y/All）
- **轮动记录表格**：现在可能是 `<table>` 简单列表
  - 排序/筛选/分页
  - 列：日期、买入标的、卖出标的、权重、收益贡献
  - 行 hover 显示"为什么买/卖"（动量分值 + 排名变化）

### 5. 操作密度
- **CRUD 入口**：现在改一个 portfolio 要点 4 次（点 bar → 抽屉 → 字段 → 保存）
  - inline edit（直接在卡片上点编辑图标 → 输入 → 回车保存）
  - 拖拽排序（portfolio 顺序、标的池顺序）
- **批量操作**：多个标的加入池子、有没有"加入所有跟踪指数"按钮
- **键盘快捷键**：`N` 新建组合、`R` 刷新、`?` 显示帮助

### 6. 数据可观测性
- **现在**：调仓记录直接显示
- **建议**：
  - 调仓热力图（标的×日期网格，颜色=权重）
  - 单标的详情页（独立净值曲线、加入组合的所有时间点）
  - 全局统计卡（年化、夏普、最大回撤、卡玛 — **红涨绿跌**）
  - 跨组合对比视图

### 7. 性能感知
- 现在 cache 算完才显示 — 首次访问可能 5-10s
- **优化**：
  - 增量 cache（先显示已有数据 + 后台补全）
  - web worker 算动量分值（不卡 UI）
  - 路由级 code split（如果将来拆 SPA）

---

## 建议的研究输出结构（cc 明天交）

```
TRENDROD-UX-PROPOSAL-2026-06-13.md

1. 信息架构图（树状 / ASCII）
2. 关键页面 wireframe（ASCII 或低保真）
3. 设计 token 草案（CSS variable 列表 + 颜色/间距/字号/圆角）
4. 组件清单（Card / Modal / Drawer / Toast / Skeleton / EmptyState / DataTable / Chart 等）
5. 交互细节表（加载/错误/成功/空/确认 5 态全覆盖）
6. 实现路线图（Phase 1/2/3 — 哪些先做、估算工作量、风险）
7. 涉及到的现有 issue 引用（.review/issues.md C/H/M/L 编号）
8. 风险与开放问题（哪些 cc 不能决定、需用户拍板）
```

**给 cc 的指令**（明天第一次 turn 用）：

```bash
cd /volume1/docker/trendrod
claude -p "$(cat <<'EOF'
阅读 .review/UX-RESEARCH-2026-06-12.md（这是研究任务规格），
也阅读 .review/issues.md（已有 50 个 issue）和 static/index.html（1932 行），
然后输出 UX 提升方案文档到 .review/TRENDROD-UX-PROPOSAL-2026-06-13.md

关键要求：
- 不要直接改代码
- 不要碰后端 main.py
- 重点在 IA + 视觉 + 交互 + 性能感知
- 方案要分 Phase、标风险、引用现有 issue
- 输出完成后给我一段 200 字以内的概要

参考 skill：creative/popular-web-designs（54 套设计系统作灵感），但要配合红涨绿跌（中国惯例）
EOF
)" --permission-mode bypassPermissions
```

---

## 当前研究进度（agent 6.12 23:55 自评）

- ✅ 读完 .review/issues.md 80 行
- ✅ 摸清 17 个 API 端点
- ✅ 摸清 1932 行单 HTML 文件
- ✅ 写出研究规格本文档
- ⏳ 还没：读 index.html 内容（CC 明天读）
- ⏳ 还没：读 main.py 端点实现细节（CC 明天读）

**晚上不再继续** —— 用户要睡了。研究已够明天 CC 起步。
