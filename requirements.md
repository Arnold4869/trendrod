# trendrod 项目需求

## 基本信息
- **项目目录**: /docker/trendrod/
- **状态**: 需求收集中

---

## 需求列表

## 功能需求

### 1. 网页访问
- 可以在网页上访问和操作

### 2. 净值数据管理
- 查看、设置**轮动标的**和**候选标的**
- 保存最近180天的净值数据到本地
- 净值数据本地持久化，随时可用
- 可随时切换轮动的标的

### 3. 轮动历史查看
- 根据保存的净值数据，查看不同配置的轮动历史回测结果

### 4. 通知渠道
- 可配置通知渠道（如飞书、Telegram等）
- 满足条件时推送通知

### 5. 历史轮动记录
- 记录历史轮动信息
- 知道之前什么时候轮到哪个标的


---

## 技术方案

- **技术栈**: FastAPI + Uvicorn + SQLite + APScheduler + HTML/JS
- **容器**: Docker + docker-compose，端口 8000
- **数据持久化**: SQLite 文件 + ETF净值数据
- **通知**: 预留接口，待实现

## 项目结构

```
trendrod/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── app/
    ├── __init__.py
    ├── main.py           # FastAPI 入口
    ├── config.py        # 配置
    ├── model.py         # 数据模型
    ├── database.py      # SQLite 操作
    ├── fetcher.py       # AKShare 数据拉取
    ├── strategy.py      # 轮动策略（基于原脚本）
    ├── scheduler.py     # 定时任务
    ├── notification.py  # 通知接口（预留）
    └── routers/
        ├── etf.py       # ETF标的管理
        ├── history.py   # 轮动历史
        └── config.py    # 配置管理
```

## 状态

- ✅ 需求收集完成
- 🚧 构建中

## 构建结果

- **镜像**: trendrod:latest，构建成功
- **容器**: trendrod，已运行（`docker run -d`）
- **端口**: 8000
- **API验证**:
  - `GET /api/etf/list` ✅ 返回空列表正常
  - `POST /api/etf/add` ✅ 添加ETF成功
  - `POST /api/etf/set_active` ✅ 设置轮动标的成功
  - `POST /api/etf/fetch/{code}` ✅ 获取净值数据成功（159915/510050/511090 各139条）
  - `GET /api/history/backtest` ✅ 回测正常（117交易日，总收益-11.1%，15次调仓）
  - `GET /` ✅ 主页重定向到 /static/index.html
- **定时任务**: 已启动，每天 15:30 执行
- **已知问题**: 无

## 状态

- ✅ 需求收集完成
- ✅ 构建完成，镜像正常运行
