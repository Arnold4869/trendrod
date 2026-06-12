# TrendRod Bug Fix Log

按优先级顺序修复。每次修复记录：commit/状态/测试。

## 进度

- [x] **C2** requirements.txt 缺 apscheduler — 1 行 + 1 行 (apscheduler>=3.10 + pytz>=2023.3)
- [ ] **H7+H8** 双引擎 mom_weights/mom_periods 不一致
- [ ] **H20** chart 双 fill
- [ ] **C5** XSS via name 字段
- [ ] **C6** 内联 onclick + CSP
- [ ] **H1** JSON 写不原子
- [ ] **H9** except: 改具体异常类型
- [ ] **C3** 全局 dict 加 RLock
- [ ] **C4** _sync_scheduler / _do_refresh 闭包作用域
- [ ] **C1** API 鉴权中间件
- [ ] **H3** 长任务进 BackgroundTasks
- [ ] **H4** Pydantic 校验请求体
- [ ] **H5+H15** portfolio id 字符集校验
- [ ] **H14+H40-H42** Docker 安全加固
- [ ] **H13** Dockerfile 代理 build-arg
- [ ] **H10+H11** backtrader 多持仓 + pnl 回填
- [ ] **H2** filterAndRender 早 return 清空
- [ ] **H21** renderBenchDisplay shortcut 解析
- [ ] **H6** compute() 拆函数
