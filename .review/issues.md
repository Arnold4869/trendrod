# TrendRod Code Review — Full Issue List (cc review, 2026-06-12)

Total: 6 CRITICAL, 14 HIGH, 18 MEDIUM, 12 LOW

**Issues below are grouped by priority for fixing. The user wants to fix them one-by-one.**

---

## 🔴 CRITICAL (6 个 — 优先修)

### C1. [CRITICAL] 全部 API 端点无任何鉴权
- **位置**: `app/main.py` 全部 13 个端点（line 681–906）
- **影响**: 任何能访问 8000 端口的网络客户端都能 `DELETE /api/portfolios/{id}`、`POST /api/refresh`（触发全量 akshare 抓取 + 回测）等
- **修法**: 加 token 鉴权中间件（`Depends(verify_token)`），加 per-IP rate limit，前置反代

### C2. [CRITICAL] `requirements.txt` 缺 `apscheduler`
- **位置**: `requirements.txt` 第 1-7 行；`main.py` 第 12 行 `from apscheduler.schedulers.background import BackgroundScheduler`
- **影响**: Docker build 时 `pip install -r requirements.txt` 不装 apscheduler，容器启动 `_init_scheduler()` 时崩溃
- **修法**: 加 `apscheduler>=3.10` + 显式 `pytz>=2023.3`

### C3. [CRITICAL] `_caches` / `PORTFOLIOS` / `_schedules` 全局字典无锁
- **位置**: `main.py` 第 25-27 行声明；scheduler 后台线程和 HTTP 端点并发修改
- **影响**: 缓存竞争导致脏数据、portfolio 配置被破坏、scheduler 偶发崩溃
- **修法**: `threading.RLock()` 包住所有写操作；或迁到 thread-safe store

### C4. [CRITICAL] `_sync_scheduler` 引用 `_do_refresh` 跨闭包作用域
- **位置**: `_sync_scheduler` 第 566-588 行调用 `_do_refresh`（只在 `_init_scheduler` 第 595 行的闭包内定义）
- **影响**: 启动时未跑 `_init_scheduler` 直接调 `_sync_scheduler` 触发 `NameError`；同时内部 `_sync` 函数（611-637 行）几乎一样 = 死代码重复
- **修法**: 把 `_do_refresh` 提到模块作用域；删掉内部 `_sync` 重复

### C5. [CRITICAL] Stored XSS via `name` 字段
- **位置**: `static/index.html` 683 行（`renderPfBar`）、843-844（`renderPoolBar`）、865-869（`renderPfDrawer`）、1795-1796（`renderSchedules`）
- **影响**: 用户创建 portfolio 名 `<img src=x onerror=alert(1)>` → 存储 → 渲染时直接 innerHTML 注入 → 所有加载页面的浏览器执行任意 JS。C6 加持下可放大
- **修法**: `textContent` 替代 `innerHTML`；或 `escHtml(s)` 助手；或 `createElement` + `textContent` 构建 DOM

### C6. [CRITICAL] 内联 onclick + 无 CSP = 完整 XSS 攻击面
- **位置**: 全局 — 几乎每个 `onclick="..."`（line 502, 522, 534, 543, 552, 553, 567, 585）
- **影响**: 与 C5 叠加，trivial XSS-to-cookie-theft；本服务无 cookie 也能劫持 SPA
- **修法**: 迁到 `addEventListener` + 委托；`/` 路由加 `Content-Security-Policy` 头（要接受 inline script 需挪到外部文件或用 hash）

---

## 🟠 HIGH (14 个)

### H1. [HIGH] portfolio/schedule/log JSON 文件写不原子
- **位置**: `_save_portfolios` (line 70-73), `_save_schedules` (561-564), `_append_log` (644-656)
- **影响**: SIGKILL / 断电中途写 → JSON 损坏 → `except: pass` 静默丢失
- **修法**: 写 `*.tmp` → `os.replace(tmp, final)`；异常要 log 而非 pass

### H2. [HIGH] `filterAndRender` 在空 nav 时早 return，留旧 chart 和旧轮动列表
- **位置**: `static/index.html` 第 1185 行
- **影响**: 选了无数据的日期范围 → chart 不刷新、rotation 列表不更新，与其他地方显示的"空"状态不一致
- **修法**: 销毁 chart + 清空 rotation 区 + 显示空状态，再 return

### H3. [HIGH] `fetch_new` / `_recompute_cache` 在请求线程里同步跑
- **位置**: `api_refresh` line 804-818, `api_status` 820-839
- **影响**: akshare 慢时请求卡 30+ 秒；用户堆积请求；与 C3 叠加产生撕裂缓存
- **修法**: 长任务走 `BackgroundTasks` 或 Celery/RQ；只 warmup 激活的 portfolio；显示 skeleton 而非卡死

### H4. [HIGH] `api_update_portfolio` 盲目信任客户端输入类型
- **位置**: lines 727-744
- **影响**: `int(data["window"])` 对 string 抛 TypeError → 500；`data["indices"]` 接受任意类型；`top_n` 接受负数/0；无 Pydantic 校验
- **修法**: Pydantic `BaseModel` + field validators；非法类型返 422

### H5. [HIGH] `api_create_portfolio` 接受任意 id 字符串
- **位置**: line 686-707 — `pfid = data.get("id", "").strip()` 无校验
- **影响**: id `"../etc"` 或带空格/控制字符；id 进 HTML 属性触发 XSS
- **修法**: 服务端正则 `^[a-zA-Z0-9_-]{1,32}$`

### H6. [HIGH] `compute()` 300 行做了 6 件事
- **位置**: line 159-488
- **影响**: 不可测；动量计算、MA 过滤、排名、持仓期、模拟、benchmark、统计、序列化全耦合
- **修法**: 拆成 `_mom_score` / `_rank` / `_simulate` / `_compute_stats` / `_current_holding`

### H7. [HIGH] `main.py` 与 `backtest_bt.py` 默认 `mom_weights` 不一致
- **位置**: `main.py` line 76, 173 → `[0.0, 1.0, 0.0]`；`backtest_bt.py` line 322 → `[0.25, 0.5, 0.25]`
- **影响**: Backtest CLI 结果 ≠ in-app 结果，用户以为 backtest 脚本坏了
- **修法**: 统一一个 `DEFAULT_MOM_WEIGHTS` 源；backtest_bt 读 portfolio 存储值

### H8. [HIGH] `backtest_bt` 的 `mom_periods` 从 `window` 派生，main 用固定 `[5,22,60]`
- **位置**: `backtest_bt.py` 314-321；`main.py` 157 `MOM_PERIODS = [5, 22, 60]`
- **影响**: 同一数据算出不同动量，交叉验证失效
- **修法**: `mom_periods` 提为 portfolio 参数，两引擎共用

### H9. [HIGH] `except:` 裸 except 吞所有异常
- **位置**: line 67, 134, 556, 651, 906（main.py） + 1 处（backtest_bt.py）
- **影响**: 捕获 `KeyboardInterrupt`/`SystemExit`/所有异常/SyntaxError；JSON 损坏时静默回退默认
- **修法**: `except (json.JSONDecodeError, OSError) as e: logger.error(...); return _default()`

### H10. [HIGH] backtrader `stop()` 不回填最后一条 buy 的 pnl_pct
- **位置**: `backtest_bt.py` line 286-293
- **影响**: 最近一笔买入永远显示 `--`，跟 main.py 不一致
- **修法**: `stop()` 末尾 append 一条 pnl_pct 已设的 rot_log

### H11. [HIGH] Backtrader `MomentumRotation.next()` 单标的假设
- **位置**: `backtest_bt.py` 215-261 — `sig = list(self.datas).index(target)` 单目标
- **影响**: `top_n > 1` 的 portfolio 无法用 backtrader 验证
- **修法**: `candidates.sort(reverse=True)[:top_n]`；按 `weight_ratios` 分配

### H12. [HIGH] `mom_weights` 默认值 backtest_bt vs main 不一致（重复 H7，cc 列两次）

### H13. [HIGH] Dockerfile 硬编码代理 URL
- **位置**: line 17 `pip install --proxy http://203.0.113.10:7890`
- **影响**: 仅 LAN 可 build；CI/其他人 build 失败
- **修法**: `ARG HTTP_PROXY` build-arg

### H14. [HIGH] Docker 容器以 root 跑
- **位置**: 整个 Dockerfile 无 `USER` 指令
- **影响**: 任何依赖（akshare 等）有 RCE = root 权限
- **修法**: `useradd -m trendrod && USER trendrod`

### H15. [HIGH] 组合/调仓/bench 计算 key 错误 (XSS via id)
- **位置**: `renderPfDrawer` line 865-877 `onclick="duplicatePf('${p.id}')"` — 后端 id 不强制字符集
- **影响**: 攻击者可 POST `id="'); alert(1); //"` 突破 onclick 字符串
- **修法**: 服务端 id 校验（同 H5）+ 渲染时用 `JSON.stringify(p.id)`

### H16. [HIGH] 关键文件 (chart.js) 未锁定版本
- **位置**: line 7 `<script src="/static/chart.umd.min.js">` — 无 SRI hash
- **影响**: 静态文件版本未知；Chart.js v2/v4 API 不同时插件会静默坏
- **修法**: 静态目录固定 Chart.js 版本；CDN + SRI

### H17. [HIGH] `addSchedule` ID 在高频点击下可能碰撞
- **位置**: line 1807 `id = 'sch_' + t.replace(':', '') + '_' + Date.now()` — 同毫秒同 t 产生同 id
- **影响**: UI 短暂显示重复 chip
- **修法**: `crypto.randomUUID()` 或加 per-call 计数器

### H18. [HIGH] `commitRenamePf` 不校验/转义新 name
- **位置**: line 889-905 — input value 直接 POST
- **影响**: 叠加 C5 → XSS
- **修法**: 长度上限（如 32）；拒绝控制字符；渲染时转义

### H19. [HIGH] `addIndex` 不 await，状态竞态
- **位置**: line 1011-1026 — fetch 后 loadStatus() 同步触发；`removeIndex`/`duplicatePf` 类似
- **影响**: 慢网下 portfolios 数组中途 stale
- **修法**: 集中状态管理；`AbortController` 取消 in-flight

### H20. [HIGH] chart 双 fill 导致视觉重复
- **位置**: `gradientFill` plugin (1411-1432) 在 dataset[0] `fill: true` 之上又画一遍；`stopLossOffset` plugin 错位
- **影响**: NAV 双重 fill；止损 marker 错位
- **修法**: dataset[0] 设 `fill: false`；重写 `stopLossOffset` 按 `chart.data.labels[index]` 对日期

### H21. [HIGH] `renderBenchDisplay` 用 shortcut range 字符串 (`#1m`) 不解析
- **位置**: line 1666-1693 — 字符串比较 `'2024-04-01' >= '#1m'` → false（# 0x23 < 2 0x32）
- **影响**: 选快捷范围时 benchmark 显示空白；与 chart 的 benchmark 不一致
- **修法**: 复用 `filterAndRender` 的 shortcut→date 解析（1170-1179）

---

## 🟡 MEDIUM (18 个) — 摘要

| # | 位置 | 描述 | 修法 |
|---|---|---|---|
| M1 | main.py 660 | `StaticFiles` 硬编码 `/app/static` | 用 `Path(__file__).parent.parent / "static"` |
| M2 | main.py 43-46 | `db_save` `INSERT OR IGNORE` 丢弃修正数据 | `INSERT OR REPLACE` 或 UPSERT |
| M3 | main.py 全部 Body | 请求体无 size 限制 | FastAPI `max_body_size` |
| M4 | main.py 90-103 | `fetch_new` 串行同步，9 个标的 × 26 个 portfolio = 慢 | `ThreadPoolExecutor` ≤ 4 并发 |
| M5 | main.py 19, 465 | NAV 1.0 起始但 label 不清楚 | 标"净值倍数"或"归一化净值" |
| M6 | main.py _db | SQLite 连接每调用 open 不 close | `with sqlite3.connect()` context manager |
| M7 | main.py compute | mutate df 加列 | `df = df.copy()` at top |
| M8 | main.py 662 | `@app.on_event("startup")` 已 deprecated | `lifespan` 上下文管理器 |
| M9 | main.py _append_log | 每次 refresh 重写整个 500 条 log | append-only NDJSON |
| M10 | main.py _search_indices | 早期命中仍扫剩余 | 早 exit at 20 results |
| M11 | main.py 329-338 | 止损跳过 NaN 无标记 | 记录 skip 事件 |
| M12 | main.py 880-895 | `api_run_now` 无 in-progress 锁 | `RefreshLock` file/in-process；并发返 409 |
| M13 | backtest_bt 362-363 | `set_coc(True)` + buy-at-close = 偷看未来 | `set_coo(False) set_coc(False)`；下单在下一 bar open |
| M14 | backtest_bt 367 | `cerebro.run()` 默认打 daily PnL 表 | `cerebro = bt.Cerebro(stdstats=False)` |
| M15 | backtest_bt 54-57 | `db_load_csv` 只写空 CSV，不更新 | 每次重导或 on-the-fly 计算 |
| M16 | backtest_bt 244 | 整数股假设，余钱累积漂移 | 允许分数股或显式再投资残值 |
| M17 | backtest_bt 134-139 | `verbose` 默认 False，看不到诊断 | 关键事件始终 log |
| M18 | backtest_bt 322 | `mom_weights` 默认值与 main 不一致（同 H7） |
| M19 | index.html 51 | `closePresetsDropdown` 闭包 stale element | 每次 click 时重新 `getElementById` |
| M20 | index.html 1099-1101 | `d.toISOString()` UTC 偏移 1 天 | 字符串算术 YYYY-MM-DD |
| M21 | index.html 630 | `pctClass(v)`: 0 视作 up | `v > 0` |
| M22 | index.html 633-645 | `animateValue` 用 regex 替换，多数字/无数字失效 | 标 `anim-target` 槽 |
| M23 | index.html 492-498 | theme switcher/refresh 无 aria-label | 加 aria-label |
| M24 | index.html 1050,1051,727,746,923 | `alert()`/`confirm()` 破坏主题 | in-app modal |
| M25 | index.html 1700 | `renderRotationHistory` 只显示 last 60 | 分页/去上限 |
| M26 | index.html 1696-1747 | Filter 顺序敏感，PnL 可能配错 | 区分"首次建仓" vs "再平衡" |
| M27 | index.html 614-617 | `window.onerror` 注入 unescaped msg/line | `textContent` 或转义 |
| M28 | index.html 全局 | `showMsg` 无 aria-live | `role="status" aria-live="polite"` |
| M29 | index.html 979-984 | `searchInput` debounce 无 abort | `AbortController` |
| M30 | index.html 9 | `* { margin:0; padding:0; }` 全局 reset | 定向 reset |
| M31 | main.py 644-656 | `_append_log` 见 M9 | |
| M32 | backtest_bt 322 | 见 M18 | |
| M33 | backtest_bt.py 整体 + main.py | 两套 backtest 实现，不一致 | 共享模块或 backtest_bt 包装 in-app 结果 |
| M34 | 项目级 | 无 test | 加 pytest + 烟雾测试 |
| M35 | 项目级 | 无结构化日志 | structlog |
| M36 | Dockerfile 9-13 | `apt-get install` 缺 `--no-install-recommends` | |
| M37 | Dockerfile | 无 HEALTHCHECK | `HEALTHCHECK CMD curl` |
| M38 | 项目级 | 无 .dockerignore | |
| M39 | Dockerfile | 非 multi-stage build | 拆 builder/runtime |
| M40 | docker-compose | 无 `no-new-privileges/cap_drop/read_only` | |
| M41 | docker-compose | 无 healthcheck 块 | |
| M42 | docker-compose | 无 mem_limit/cpus/pids_limit | |
| M43 | docker-compose | port 8000 直出主机无 TLS/auth proxy | |

---

## 🟢 LOW (12 个) — 摘要

- **L1**: fetch_one 每次重下全历史（main.py 105-118）
- **L2**: MOM_PERIODS 硬编码模块常量（main.py 157）
- **L3**: pool benchmark 计算后被丢弃（main.py 451-454 + 487 + 520-523）
- **L4**: pctClass 0 当 up（index.html 630，重复 M21）
- **L5**: loadStatus 无 loading 指示（index.html 1056）
- **L6**: 离线/网络错处理不足（index.html 1056）
- **L7**: Date 算术用固定 86400000 ms（index.html 1212, 1606, 1728）
- **L8**: 主题色变量名与值不匹配（light-blue 里 `--green: #0066cc` 实际是蓝，index.html 11-45）
- **L9**: buildDateBar 重建丢失 datePicker 焦点（index.html 1096-1130）
- **L10**: start_date 空串 crash（backtest_bt.py 340）
- **L11**: get_portfolio 每次 reload JSON（backtest_bt.py 37-41）
- **L12**: cerebro.broker.setcash(1,000,000) vs main.py 1.0（backtest_bt.py 81, 360）
- **L13**: 中文日志/错误信息（main.py 多处）
- **L14**: 无 README.md
- **L15**: image 未 pin digest（Dockerfile 1）

---

## 已知 2 个未修 bug（来自 skill）— 根因重分析

### 旧认知: "navChart.destroy() 没调"
**实际**: line 1289 *有* 调用。**真正原因** = H20 双 fill：`dataset[0]` 已有 `fill: true` + 静态 `backgroundColor`，`gradientFill` plugin 又画一遍渐变。视觉重复不是 chart 没销毁，是两层 fill 重叠。
**修法**: dataset[0] `fill: false`，只留 plugin 渐变。

### 旧认知: "换仓点坐标错位"
**实际**: 数据计算正确（line 1499-1530 `chartMode === 'return' ? ((p.value/baseVal-1)*100) : p.value`）。真正问题 = `stopLossOffsetPlugin` 偏移量是像素 (`OFFSET_PX = 8`)，且按 dataset index 对齐（不是按日期）— 同 index 不等于同日期。
**修法**: 重写 `stopLossOffset` 按 `chart.data.labels[index]` 对齐日期。

---

## 修复优先级建议（用户决定一个一个修）

按"影响最大 + 风险最低"排序：

1. **C2** requirements.txt 缺 apscheduler（1 行修复，零风险，立即生效）
2. **H7+H8+M18** mom_weights/mom_periods 双引擎一致（backtest_bt 读 portfolio 配置）
3. **H20** chart 双 fill（视觉问题，2 处改动）
4. **C5** XSS via name 字段（加 escHtml，所有 innerHTML 改一遍 → 一次大改）
5. **C6** 内联 onclick + CSP（结构性大改）
6. **H1** JSON 写不原子（3 个函数加 try/except + os.replace）
7. **H9** `except:` 改具体类型（5 处）
8. **C3** 全局 dict 加 RLock（结构性，影响所有端点）
9. **C4** _sync_scheduler / _do_refresh 闭包提模块作用域
10. **C1** API 鉴权（结构性，引入 Depends + token 配置）
11. **H3** 长任务进 BackgroundTasks
12. **H4** Pydantic 校验
13. **H5+H15** portfolio id 字符集校验
14. **H14+H40+H41+H42** Docker 安全（USER + no-new-privileges + cap_drop + read_only + healthcheck + mem_limit）
15. **H13** Dockerfile 代理 build-arg
16. **H10+H11** backtrader 多持仓 + pnl 回填
17. **H2** filterAndRender 早 return
18. **H21** renderBenchDisplay shortcut 解析
19. **H6** compute() 拆函数
20. **M~** 一组中型问题（按需）
21. **L~** 12 个低优，按需

用户已说 "一个一个修"，下一条消息我等用户指定先修哪个。
