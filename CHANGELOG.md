## 0.1.14 ✅ (2026-06-13) — UX P1 (轻量): 视觉/数据 bug 全修

### CSS Token 重构（L8 真修 — 双层语义）
- **新 token**：`--up`/`--up-dim`（红涨，中国惯例）、`--down`/`--down-dim`（绿跌）、`--accent`/`--accent-dim`（品牌强调，主题独立）、`--dd-zone`（回撤区底色）
- **旧 `--green`/`--red` 全替换**：58 处 CSS + JS 引用按"金融涨跌语义 vs 品牌强调"分类：
  - 金融 up/down 位置（`.stat-value.up` / `.holding-tag.up|down` / `.rot-pnl.up|down` / `.yearly-*` / `.rot-card.*` / `.rot-adj-buy|sell` / `.log-ok|fail` / 最大回撤等）→ `var(--up)` / `var(--down)`
  - 品牌强调位置（spinner / focus / active tab / 主题按钮 / pf-card / schedule / 主按钮 / 等）→ `var(--accent)`
- **空仓色修正**：`.holding-tag.empty` 从 `--up-dim` 改 `--orange`（真正语义化，不再和 up 撞色）
- **结果**：4 主题下金融涨跌永远红/绿（不被主题覆盖）；light-blue 主题的 down 不再显示蓝；focus/active 仍是品牌色

### 数据/逻辑 bug
- **M21/L4 `pctClass(0)` 当 up** → `v >= 0` 改 `v > 0`，0% 显示 down（持平不是涨）
- **M20 `toISOString()` UTC 偏移** → 新 `dateStr(d)` helper（用本地时间），buildDateBar / filterAndRender 两处替换
- **H2 `filterAndRender` 空 nav 早 return** → 清空 chart + statsGrid + holdingArea + rotationArea + 显示空态文案
- **H21 `renderBenchDisplay` shortcut 不解析** → 新 `resolveCutoff(range, nav)` helper，filterAndRender + renderBenchDisplay 都复用（避免 ASCII 比较 `'2024-04-01' >= '#1m'` 错误）
- **H20 续 `drawdownZones` hardcoded 红色** → 改读 CSS var `--dd-zone`，4 主题各自定义（不再被主题覆盖）

### A11y（M23/M28）
- 5 个 `aria-label` 给关键按钮（refresh / 4 个主题切换 / 管理组合）
- `msgBar` 加 `role="status"` + `aria-live="polite"` + `aria-atomic="true"`

### 排版（M22）
- 4 类数字位置加 `font-variant-numeric: tabular-nums` + `letter-spacing: -0.02em`（金融数字等宽对齐不抖）

### 验证
- JS 语法：2 个 script block parse OK
- 本地 ↔ 容器 md5 一致：`f8d0b4f4726edde0f29e4a4744c1f55d`
- 容器 healthy / API 200 / 数据完整（nav 5690 / rot 481 / holding 有）
- var(--green) / var(--red) 残留 0
- deploy：hotfix（`docker cp + restart`，5 秒上线）

### P1 范围说明
按 UX 方案 `.review/TRENDROD-UX-PROPOSAL-2026-06-13.md` 的轻量化执行：纯前端 CSS/JS bug 修复，**不动架构、不引入新组件、不拆分视图、不引入构建工具**。完整 P1 包含 11 项，本版先做 9 项最高性价比的 1 天工作量，剩 2 项（M30 全局 reset / M24 alert 替换）风险大于收益，留 P2 单独评估。

### 待办（0.1.15+）
- P2：M24 Toast/Dialog 替换 alert/confirm（独立 commit，需要先实现 Toast 组件）
- P2：M29 搜索 AbortController
- P3：3 视图 + hash router（如果用户组合数增长）
- 阻塞项：C5 XSS 全量审计 / C6 drag 5 个 handler / M27 window.onerror

## 0.1.13 ✅ (2026-06-13) — H1 已 deploy

### 修复
- **H1 JSON 写不原子**：`app/main.py` 三处写入路径（`_save_portfolios` / `_save_schedules` / `_append_log`）直接 `open('w')` 写 JSON，掉电/异常会导致文件半截损坏。改为先写 `path.tmp` 再 `os.replace(tmp, path)` 的原子写。
- 顺手收窄 `_load_portfolios` / `_append_log` 读路径的 `except:` → `(json.JSONDecodeError, OSError) as e`，错误不再静默（`_load_schedules` 的 `except:` 留给 H9 一并处理）
- 测试：容器内 5 个用例通过（含真实 CONFIG_PATH 写入 + 读出比对 + 中文 UTF-8 + tmp cleanup）
- 端到端验证：POST /api/schedules 后 `trendrod_schedules.json` 写入正确 + `/data/` 无 .tmp 残留

### 部署
- 镜像：`registry.cn-hangzhou.aliyuncs.com/docker-pusher/trendrod:0.1.13` + `latest`
- commit：551d3f0（fix H1）+ cd2d2ea（UX 提案文档，独立 commit）
- md5 一致性：本地 ↔ 容器 `212062e802c444043c8009b31f37ddf1`

### 待办（0.1.14+）
- UX 方案已出 (`.review/TRENDROD-UX-PROPOSAL-2026-06-13.md`)，等用户拍板 8 个开放问题 → 决定 Phase 1 范围
- 阻塞项（C5 全量审计、C6 drag 5 个、M27、H2）

## 0.1.12 ✅ (2026-06-12) — btrfs ugacl 修复收尾

### 修复
- **2b93f21**：0.1.11 的启动 data dir 可写检查顺序 bug — 启动 check 移到 `DB_PATH` 定义之后

## 0.1.11 ✅ (2026-06-12) — btrfs ugacl 修复

### 修复
- **5ef74b0**：三件事一起发版
  1. 宿主机 `chown -R 1000:1000 /volume1/docker/trendrod/data`（btrfs ugacl 阻挡容器内 uid=1000 → sqlite `cannot open database file`）
  2. `app/main.py` 启动时检查 data dir 可写性，失败打印修复命令（不要静默）
  3. `_db()` 包 try/except OperationalError 返回 None + 记录错误（不再静默 500）

## 0.1.10 ✅ (2026-06-12) — Docker 加固

### 修复
- **3049d2f** Docker 容器加固（H13/H14/M36/M37/H40-H42）
  - USER trendrod（uid 1000）— 不再 root
  - no-new-privileges / cap_drop ALL / read_only tmpfs /usr/tmp /tmp
  - HEALTHCHECK curl localhost:8000
  - mem_limit / cpus / pids_limit
  - apt-get --no-install-recommends
  - ARG HTTP_PROXY build-arg（替代 Dockerfile 硬编码 203.0.113.10:7890）
  - compose 安全选项全套

## 0.1.7 ✅ (2026-05-24) — 生产可用

### 修复
- **前端 `addIndex()` 截断 name 到4字符**：搜索添加指数时 `name.slice(0, 4)` 把"中证1000"传成"中证1"，后端再截10字符变成"中证1"，已改为发完整 name
- **数据库截断名称**：sh000852 名称为 `'中证10'`（4字符截断残留），已修复为 `'中证1000'`

## 0.1.6 ✅ (2026-05-24) — 生产可用

### 修复
- **top-N 多持仓显示**：后端 `compute()` `current_holding` 原来只返回 entry_price 最高的1个标的，改为返回按 entry_price 降序排列的所有持仓列表
- **止损 marker 坐标 bug**：`stopLossOffsetPlugin` 中 `ctx2.rect(x, y, w, h)` 参数顺序写反（y/x 颠倒），导致方块画在图表可见区域外，已修复

### 技术
- 后端：`holding` 变量改为 `h`（列表），按 `entry_prices` 降序排列后逐个 append
- 前端：持有卡片改为 `for` 循环渲染，支持 top_n > 1 时显示多个持仓卡片

## 0.1.5 ✅ (2026-05-24) — 生产可用

### 修复
- **topNInput 缺失**：前端 HTML 缺少"前N"输入框，导致 `updateWSum()` 抛出 TypeError，页面加载失败
- **标的名称截断阈值**：从 `name[:8]` 扩大至 `name[:10]`，避免科创50、创业板50等较长名称被截断
- **数据库名称修正**：沪深30→沪深300、创业板5→创业板50、中证10→中证1000、中证50→中证500

### 技术
- 补齐缺失的 `topNInput` HTML 元素（id="topNInput"，位于权重求和后）

## 0.1.0 ✅ (2026-05-24) — 生产可用

### 新增
- **三动量权重配置**：支持 5天/22天/60天 权重独立配置（0.0~1.0），前端实时显示求和校验（绿色=1.0，红色≠1.0）
- **Top-N 持仓支持**：`top_n` 参数（默认1，最大5）+ `weight_ratios` 不等比例分配（50/30/20 等），后端 `compute()` 重构支持多标的差量调仓
- **动量权重持久化**：组合配置新增 `mom_weights` 字段，创建/复制/切换组合时均恢复权重输入框状态

### 修复
- **轮动记录买入行显示完整 pnl**：修复 in-loop backfill 逻辑，连续开仓（买入→调仓）时 pnl_pct 正确回填
- **止损标的同天再买回**：新增 `stopped_out_today` 集合，阻止止损触发后同一标的被立刻买回（177→0）
- **止损 marker 偏移**：引入 `stopLossOffsetPlugin`，同天止损+不同标的买入时止损方块往下偏移 8px 避免重叠
- **pool-chip/rot-name 截断**：CSS 加 `max-width: 130px`、`min-width: 0`（flex 子元素默认 min-width:auto 阻止截断生效）
- **所有 fetch 请求禁用缓存**：加上 `?_=` + Date.now() 和 `{ cache: 'no-store' }`
- **`/` 路由 HTML 响应加 Cache-Control**：后端 `no-cache, no-store, must-revalidate, max-age=0`

### 技术
- 后端 `compute()` 重构：top_N + weight_ratios 参数、最小持有期过滤（N-d array guard）
- `api_create_portfolio`/`api_update_portfolio`/`_recompute_cache` 均透传 `mom_weights`、`top_n`、`weight_ratios`
- 前端 `switchTo()` 修复双重 `if (pf)` 语法错误（第一块代码无效导致参数未加载）
- `updateWSum()` 扩展：读取 topNInput 动态显示/隐藏比例输入框，调用 `updateWRSum()`

## 0.0.27 ✅ (2026-05-23) — 生产可用

### 新增
- **基准对比**：API 支持 `?benchmark=sh000300` 参数，返回沪深300等基准指数净值序列
  - 缓存自动包含基准数据，首次请求触发计算
  - `/api/refresh` 同样支持 benchmark 参数
- **前端基准展示**：
  - 控制栏新增基准选择下拉框（沪深300/上证50/创业板指/中证500）
  - 图表叠加基准虚线（灰色，`borderDash: [5,3]`）
  - 指标卡新增"超额收益(vs基准)"卡片，含基准累计收益
- **图表渐变动态配色**：收益为正时红色渐变，为负时绿色渐变
- **年度收益分解**：新增"年度收益"区块，横向柱状图展示分年涨跌
- **回撤区域高亮**：图表回撤区间半透明红色色块标记
- **骨架屏**：替代 loading 转圈，页面加载显示卡片/图表/持仓占位
- **数值滚动动画**：指标卡数字 count-up 动画（ease-out 600ms）

### 优化
- **轮动历史加持仓天数**：卖出信号旁显示持仓天数
- **持仓卡片增强**：显示入场日期 + 持仓天数 + 动量值

### 技术
- 新增 `_benchmark_nav()` 函数：独立加载基准指数并计算累计收益净值
- `compute()` 返回值增加 `bench_nav`（等权组合基准）
- `_recompute_cache()` 接受 `bench_sym` 参数
- 前端 `dsets` 数组动态构建，条件性追加基准数据集

# TrendRod 更新日志

## 0.0.12 (2026-05-23)

### 调试
- **净值曲线空白排查**：移除 `backgroundColor` 逐点数组（可能与 Chart.js v4 `fill:true` 不兼容），改为纯线条
- **增加 Chart 初始化 try-catch**：初始化失败时显示具体错误信息，便于定位

## 0.0.8 (2026-05-23)

### 修复
- **指标卡缺失**：补回总收益、年化收益两张卡片（之前误删）
- **新增 4 张指标卡**：卡玛比率、调仓胜率、轮动次数（含年均）、交易天数（含年数）
- **8 卡双行布局**：桌面端 4×2 网格，配色顶条

## 0.0.7 (2026-05-23)

### 修复
- **前端页面白屏/卡加载**：修复 `index.html` 被截断（缺 `loadPortfolios()` 启动调用、净值图表、持仓展示、轮动历史渲染代码），页面恢复正常

## 0.0.6 (2026-05-23)

### 新增
- **Backtrader 回测引擎** (`backtest_bt.py`)：独立于主服务的回测工具，支持命令行调用
  - 用法：`python backtest_bt.py --portfolio default --start_date 2020-01-01`
  - 支持 `--output json` 输出，兼容前端展示
  - 参数对齐：`--mom_period` `--ma_period` `--min_hold` `--stop_loss`

### 技术
- 数据持久化：SQLite → CSV 写入 `/data/bt_feeds/`，可复用
- 订单执行：`set_coc(True)` 收盘价成交，与向量化引擎一致
- pnl_pct 统一用价格差计算 `(exit_price - entry_price) / entry_price × 100`
- 新增依赖：`backtrader>=1.9`

### 修复
- 两阶段 close→buy 同 bar 执行，避免 Margin 状态错误
- 买入数量使用 `math.floor()` 防止浮点精度超限
