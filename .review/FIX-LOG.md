# TrendRod Bug Fix Log

按优先级顺序修复。每次修复记录：commit/状态/测试。

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

- [ ] **H1** JSON 写不原子（_save_portfolios / _save_schedules / _append_log）
- [ ] **H9** `except:` 改具体异常类型
- [ ] **C3** 全局 dict 加 RLock（_caches / PORTFOLIOS / _schedules）
- [ ] **C4** _sync_scheduler 闭包作用域（_do_refresh 提到模块级、删 inner duplicate）
- [ ] **C1** API 鉴权中间件
- [ ] **H3** 长任务进 BackgroundTasks（fetch_new / _recompute_cache 不再 request 线程跑）
- [ ] **H4** Pydantic 校验请求体
- [ ] **H5+H15** portfolio id 字符集校验（regex `^[a-zA-Z0-9_-]{1,32}$`）
- [ ] **H10+H11** backtrader 多持仓 + pnl 回填
- [ ] **H2** filterAndRender 早 return 清空（空 nav 不留 stale chart）
- [ ] **H21** renderBenchDisplay shortcut 解析（'2024-04-01' >= '#1m' 这种 ASCII 比较）
- [ ] **H6** compute() 拆函数（300 行做 6 件事）
- [ ] **M1-M35 / L1-L15** 中低优共 30 个
- [ ] **C6 残留 5%**：5 个 drag handler 的 inline style 阻止 CSP 收紧（P2）

## 关联
- 完整 issue 列表：`.review/issues.md`（6 CRITICAL + 14 HIGH + 18 MEDIUM + 12 LOW）
- cc review 笔记：`references/cc-review-2026-06-12.md`
- 部署/工作流 SOP：trendrod skill