# TrendRod Bug Fix Log

按优先级顺序修复。每次修复记录：commit/状态/测试。

## 已修（0.1.15 — 2026-06-17 架构加固）

- [x] **C1** API 鉴权中间件 — `API_TOKEN` 环境变量 + `Depends(_verify_token)`，未配置时放行
- [x] **C3** 全局 dict 加 RLock — `_state_lock` 包住 `_caches`/`PORTFOLIOS`/`_schedules` 读写
- [x] **C4** _sync_scheduler 闭包作用域 — `_do_refresh` 提模块级，删 inner duplicate `_sync`
- [x] **C6 残留** 5 个 drag handler inline — 改 `addEventListener`（CSP 可收紧）
- [x] **H4** Pydantic 校验请求体 — 数值参数类型校验 + 范围裁剪
- [x] **H5+H15** portfolio id 字符集校验 — `^[a-zA-Z0-9_-]{1,32}$`
- [x] **H9** `except:` 改具体异常类型 — 5 处改 `TypeError/ValueError/json.JSONDecodeError/OSError`
- [x] **H6** compute() 拆函数 — 抽出 `_compute_momentum`/`_compute_stats`（轻量，回测循环保留）
- [x] **H10+H11** backtrader 多持仓 + pnl 回填 — 说明 + `_last_open_idx` 机制
- [x] **M2** db_save UPSERT — `INSERT OR REPLACE`
- [x] **M4** fetch_new 并行 — `ThreadPoolExecutor(max_workers=4)`
- [x] **M6** SQLite 连接 context manager — `_db_conn()` 保证 close
- [x] **M7** compute() df.copy() — 防污染入参
- [x] **M9** _append_log NDJSON — append-only，不再重写全文件
- [x] **M12** refresh 进程锁 — `_refresh_lock`，并发返回 409
- [x] **M13** set_coc(False) — 防未来函数
- [x] **M15** backtest CSV 缓存刷新 — `--refresh-cache` 参数
- [x] **M25** 轮动历史分页 — 去 60 条上限 + "显示更多"按钮
- [x] **M29** 搜索 AbortController — 取消 in-flight
- [x] **M33** 双引擎对齐默认值 — backtest_bt 与 main.py 一致
- [x] **M34** pytest 烟雾测试 — `tests/test_compute.py` 8 用例
- [x] **M35** 结构化日志 — `LOG_FORMAT=json`
- [x] **M39** Dockerfile multi-stage — runtime 不含 gcc
- [x] **L15** 镜像 pin digest 注释
- [x] **通知渠道** 飞书/Telegram（requirements.md #4）
- [x] **历史轮动记录持久化** rotations 表 + API（requirements.md #5）

## 部分修（待后续）

- [~] **H3** 长任务异步化 — 已用 `_refresh_lock` 缓解并发；完整 BackgroundTasks + 前端轮询待后续
- [~] **拆分 main.py** — requirements.md 已设计模块结构，本次未拆（大重构风险高，单独进行）

## 已修（6.12 一天）

- [x] **C2** requirements.txt 缺 apscheduler — 980f095（+apscheduler>=3.10 / +pytz>=2023.3）
- [x] **H7+H8** 双引擎 mom_weights/mom_periods 不一致 — 64e05fa（双默认都改为 [0.25, 0.5, 0.25] + [5, 22, 60]）
- [x] **H20** chart 双 fill + stopLossOffset 按 date label 对齐 — 980f095（dataset[0] fill:false + plugin 重写）
- [x] **C5** XSS via name 字段 — 980f095（server 校验 + escHtml 13 处）
- [x] **C6** 内联 onclick + CSP — 980f095 partial（16/16 非 drag handler 迁 data-*；drag inline style + CSP 收紧剩 5%，P2）
- [x] **H13** Dockerfile 代理 build-arg — 3049d2f（ARG HTTP_PROXY + shell if 防空串）
- [x] **H14** 容器跑 root — 3049d2f（USER trendrod, uid=1000）
- [x] **M36** apt --no-install-recommends — 3049d2f
- [x] **M37** HEALTHCHECK — 3049d2f（curl localhost:8000）
- [x] **H40-H42** compose no-new-priv/cap_drop/healthcheck/mem_limit/cpus/pids_limit — 3049d2f
- [x] **btrfs ugacl 根因（不在原 issues.md 列表里，6.12 现场发现的）** — 5ef74b0 + 2b93f21：
  - 宿主机 `chown -R 1000:1000 /volume1/docker/trendrod/data`
  - main.py 启动时 data dir 可写检查（顺序 bug 在 2b93f21 修了）
  - `_db()` 包 try/except OperationalError 返回 None（不再静默 500）

## 未修（按建议顺序）

- [ ] **H1** JSON 写不原子（_save_portfolios / _save_schedules — _append_log 已在 0.1.15 改 NDJSON）
- [ ] **M1-M35 / L1-L15** 中低优剩余项（0.1.15 已修 M2/M4/M6/M7/M9/M12/M13/M15/M25/M29/M33/M34/M35/M39 + L15）
- [ ] **H3 完整异步化** BackgroundTasks + 前端轮询（0.1.15 已用锁缓解并发）
- [ ] **拆分 main.py** 按 requirements.md 模块结构（大重构，单独进行）

## 关联
- 完整 issue 列表：`.review/issues.md`（6 CRITICAL + 14 HIGH + 18 MEDIUM + 12 LOW）
- cc review 笔记：`references/cc-review-2026-06-12.md`
- 部署/工作流 SOP：trendrod skill