"""
TrendRod V2 — 指数动量轮动系统 (多组合版)
"""
import json, logging, traceback, os
from datetime import datetime
from typing import Optional
import numpy as np, pandas as pd
import akshare as ak
from fastapi import FastAPI, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trendrod")

INIT_CASH, COST_RATE = 1.0, 0.0003
DB_PATH = os.getenv("DATABASE_PATH", "/data/trendrod.db")
CONFIG_PATH = os.getenv("CONFIG_PATH", "/data/trendrod_portfolios.json")
SCHEDULES_PATH = "/data/trendrod_schedules.json"
UPDATE_LOG_PATH = "/data/trendrod_update_log.json"

# 启动时检查 data 目录可写性（必须在 DB_PATH 定义之后）
try:
    _data_dir = os.path.dirname(DB_PATH)
    os.makedirs(_data_dir, exist_ok=True)
    if not os.access(_data_dir, os.W_OK):
        st = os.stat(_data_dir)
        raise RuntimeError(f'CRITICAL: {_data_dir} not writable for uid={os.getuid()}, owner={st.st_uid}, mode={oct(st.st_mode)} — fix: chown -R 1000:1000 /volume1/docker/trendrod/data on host')
    logger.info(f'Data dir OK: {_data_dir} (uid={os.getuid()})')
except Exception as _e:
    logger.error(f'Startup check failed: {_e}')

_caches = {}  # {portfolio_id: cache_dict}
_scheduler = None
_schedules = []  # [{id, time, enabled}]

# ─── 数据库 ──────────────────────────────────────────
import sqlite3

def _db():
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        c = sqlite3.connect(DB_PATH, timeout=5)
        c.execute('CREATE TABLE IF NOT EXISTS idx(sym TEXT,dt TEXT,o REAL,c REAL,h REAL,l REAL,v REAL,PRIMARY KEY(sym,dt))')
        c.commit()
        return c
    except sqlite3.OperationalError as e:
        logger.error(f'sqlite3 cannot open {DB_PATH}: {e}')
        return None
    except Exception as e:
        logger.error(f'_db unexpected: {e}')
        return None

def db_latest(sym):
    r = _db().execute("SELECT max(dt) FROM idx WHERE sym=?",(sym,)).fetchone()
    return r[0] if r and r[0] else None

def db_save(records):
    c = _db()
    c.executemany("INSERT OR IGNORE INTO idx VALUES(?,?,?,?,?,?,?)", records)
    c.commit(); c.close()

def db_load(symbols):
    dfs = []
    for sym in symbols:
        rows = _db().execute("SELECT dt,o,c FROM idx WHERE sym=? ORDER BY dt",(sym,)).fetchall()
        if not rows: continue
        df = pd.DataFrame(rows, columns=["date",f"open_{sym}",f"close_{sym}"])
        df["date"] = pd.to_datetime(df["date"]); df.set_index("date", inplace=True)
        dfs.append(df)
    if not dfs: return pd.DataFrame()
    df = pd.concat(dfs, axis=1)    # 保留所有日期，由策略层按标的处理缺失
    logger.info(f"加载: {len(df)}个交易日, {len(dfs)}个标的")
    return df

# ─── 组合持久化 ──────────────────────────────────────
def _atomic_write_json(path, obj):
    """原子写 JSON：先写 path.tmp 再 os.replace，掉电/异常不会损坏原文件。
    失败时记录错误但不删除 tmp（保留现场便于排查）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def _load_portfolios():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"加载 portfolios 失败: {e}")
    return _default_portfolios()

def _save_portfolios(pfs):
    _atomic_write_json(CONFIG_PATH, pfs)

def _default_portfolios():
    return [{"id":"default","name":"默认组合","window":22,"ma_period":60,"min_hold_days":5,"stop_loss":0,"mom_weights":[0.25,0.5,0.25],"indices":[
        {"sym":"sh000016","name":"上证50"},
        {"sym":"sz399006","name":"创业板指"},
        {"sym":"sh000012","name":"国债指数"}
    ]}]

PORTFOLIOS = _load_portfolios()

def _get_pf(pfid):
    for p in PORTFOLIOS:
        if p["id"] == pfid: return p
    return None

# ─── 数据获取 ──────────────────────────────────────────
def fetch_new(symbols):
    total = 0
    for sym in symbols:
        latest = db_latest(sym)
        try:
            df = ak.stock_zh_index_daily(symbol=sym)
            if df is None or df.empty: continue
            if latest: df = df[pd.to_datetime(df["date"]) > pd.to_datetime(latest)]
            if df.empty: continue
            records = [(sym,r["date"],float(r["open"]),float(r["close"]),
                        float(r["high"]),float(r["low"]),float(r["volume"])) for _,r in df.iterrows()]
            db_save(records); total += len(records)
        except Exception as e: logger.error(f"{sym}: {e}")
    return total

def fetch_one(sym):
    try:
        df = ak.stock_zh_index_daily(symbol=sym)
        if df is None or df.empty: return 0
        latest = db_latest(sym)
        if latest: df = df[pd.to_datetime(df["date"]) > pd.to_datetime(latest)]
        if df.empty: return 0
        records = [(sym,r["date"],float(r["open"]),float(r["close"]),
                    float(r["high"]),float(r["low"]),float(r["volume"])) for _,r in df.iterrows()]
        db_save(records)
        return len(records)
    except Exception as e:
        logger.error(f"fetch {sym}: {e}")
        return 0

# ─── 指数搜索 ──────────────────────────────────────────
_SEARCH_CACHE = None

def _load_search_cache():
    global _SEARCH_CACHE
    if _SEARCH_CACHE is not None: return
    # 1. 尝试本地缓存文件
    cache_file = "/app/static/indices_cache.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                _SEARCH_CACHE = [{"sym": s, "name": n} for s, n in json.load(f)]
                logger.info(f"本地指数缓存: {len(_SEARCH_CACHE)} 条")
                return
        except: pass
    # 2. 尝试 AKShare
    try:
        df = ak.stock_zh_index_spot_em()
        _SEARCH_CACHE = [{"sym": r["代码"], "name": r["名称"]} for _, r in df.iterrows()]
        logger.info(f"AKShare 指数缓存: {len(_SEARCH_CACHE)} 条")
    except Exception as e:
        logger.warning(f"AKShare 指数列表加载失败: {e}")
        _SEARCH_CACHE = []

def _search_indices(q: str):
    global _SEARCH_CACHE
    _load_search_cache()
    q = q.strip().lower()
    if not q: return []
    results = []
    for item in (_SEARCH_CACHE or []):
        if q in item["sym"].lower() or q in item["name"]:
            results.append(item)
        if len(results) >= 20: break
    return results

# ─── 策略 + 回测 ───────────────────────────────────────
MOM_PERIODS = [5, 22, 60]       # 固定3个动量窗口（5天/22天/60天）# 双引擎对齐: 与 backtest_bt.py 同步使用 [0.25, 0.5, 0.25]

def compute(df, indices, window, ma_period=60, min_hold_days=5, stop_loss=0,
                 mom_weights=None, top_n=1, weight_ratios=None):
    """indices = [{"sym":"sh000016","name":"上证50"}, ...]
    mom_weights: [w_5d, w_22d, w_60d] 各周期权重，须≈1.0，默认[0.0,1.0,0.0]
    top_n: 买入前几名，默认1
    weight_ratios: top-N各位置的分配比例 list，默认等权（如[0.5,0.3,0.2] for top-3）
    """
    syms = [i["sym"] for i in indices]
    names = {i["sym"]: i["name"] for i in indices}
    if not syms or df.empty:
        return [],[],[],[],None

    # 权重
    if not mom_weights or len(mom_weights) != 3:
        mom_weights = [0.25, 0.5, 0.25]
    wgt_sum = sum(mom_weights)
    if wgt_sum > 0:
        mom_weights = [w/wgt_sum for w in mom_weights]

    # top_n & weight_ratios
    top_n = max(1, int(top_n if top_n else 1))
    if not weight_ratios or len(weight_ratios) < top_n:
        weight_ratios = [1.0 / top_n] * top_n
    else:
        weight_ratios = list(weight_ratios)
    # 归一化
    ws = sum(weight_ratios)
    if ws > 0:
        weight_ratios = [w/ws for w in weight_ratios]
    # 补齐到 top_n 长度
    while len(weight_ratios) < top_n:
        weight_ratios.append(0.0)

    # ── 1. 多周期动量合成 ──
    for sym in syms:
        c = f"close_{sym}"
        if c in df.columns:
            parts = []
            for per, w in zip(MOM_PERIODS, mom_weights):
                if w > 0:
                    parts.append(df[c].pct_change(per) * w)
            df[f"mom_{sym}"] = sum(parts) if parts else 0.0

    # ── 2. 均线过滤 ──
    if ma_period > 0:
        for sym in syms:
            c = f"close_{sym}"
            if c in df.columns:
                df[f"ma_{sym}"] = df[c].rolling(ma_period).mean()

    # ── 3. 每日动量排名（向量化） ──
    mom_cols = [f"mom_{sym}" for sym in syms]
    available = [c for c in mom_cols if c in df.columns]
    if not available:
        return [],[],[],[],None

    mom_mat = np.column_stack([df[c].values for c in available])
    ma_ok = np.ones_like(mom_mat, dtype=bool)
    if ma_period > 0:
        for j, sym in enumerate(syms):
            mc, cc, mac = f"mom_{sym}", f"close_{sym}", f"ma_{sym}"
            if mc in df.columns and mac in df.columns:
                ma_ok[:, j] = df[cc].values >= df[mac].values

    masked = np.where(ma_ok & ~np.isnan(mom_mat), mom_mat, -np.inf)

    # 每日排名索引（0=动量最高，1=第二...）
    ranked_idx = np.argsort(-masked, axis=1).astype(float)  # 降序排列
    # 将无效行（全-Inf）的排名全置 NaN
    all_bad = np.all(masked == -np.inf, axis=1)
    ranked_idx[all_bad] = np.nan

    # top-N 标的下标（symbol index，不是syms直接index——需考虑available）
    # available 的顺序对应 mom_mat 的列顺序
    sym_idx_map = {available[j]: j for j in range(len(available))}  # col -> sym_idx
    top_n_syms = np.full((len(df), top_n), -1, dtype=float)
    for row in range(len(df)):
        if all_bad[row]:
            continue
        seen = set()
        col_i = 0
        for rank in range(len(available)):
            sym_col_idx = int(ranked_idx[row, rank])
            # 找到对应的 sym index
            actual_col = available[sym_col_idx]
            sym_idx = sym_idx_map[actual_col]
            if sym_idx not in seen:
                seen.add(sym_idx)
                if col_i < top_n:
                    top_n_syms[row, col_i] = sym_idx
                col_i += 1
            if col_i >= top_n:
                break

    df["top_n_syms"] = [top_n_syms[i] for i in range(len(df))]
    df["best_mom"] = np.where(all_bad, np.nan, np.max(masked, axis=1))

    # 持仓字典: {sym_idx: {shares, entry_price, entry_date, weight, hold_days}}
    current_holdings = {}
    # 单只标的止损追踪（sym -> entry_price）
    entry_prices = {}  # sym_idx -> entry_price

    # 信号：shift(1) 表示用昨天的信号决策今天的操作
    desired_raw = df["top_n_syms"].shift(1).copy()

    # ── 4. 最小持有期强制 ──
    final_desired = desired_raw.copy()
    if min_hold_days > 0:
        hold_cnt_map = {}
        last_sig_key = None
        for i in range(1, len(df)):
            t = df.index[i]
            sig = desired_raw.iloc[i]
            sig_key = None
            if sig is not None and hasattr(sig, '__iter__') and not isinstance(sig, str):
                try:
                    sig_key = tuple(float(x) for x in sig if not (isinstance(x, float) and np.isnan(x)))
                except:
                    sig_key = None
            if sig_key is not None:
                if last_sig_key == sig_key:
                    hold_cnt_map[sig_key] = hold_cnt_map.get(sig_key, 0) + 1
                else:
                    hold_cnt_map[sig_key] = 1
                if hold_cnt_map.get(sig_key, 0) < min_hold_days:
                    final_desired.iloc[i] = final_desired.iloc[i-1]
                last_sig_key = sig_key
            else:
                last_sig_key = None

    # get_desired_top_n: 读取 final_desired 中已过滤的 top-N sym indices list
    def get_desired_top_n(row_idx):
        arr = final_desired.iloc[row_idx]
        # Handle 0-d arrays and scalars
        if arr is None or (isinstance(arr, float) and np.isnan(arr)):
            return []
        if isinstance(arr, np.ndarray) and arr.ndim == 0:
            return []
        if not hasattr(arr, '__iter__') or isinstance(arr, str):
            return []
        result = []
        for x in arr:
            if isinstance(x, float) and np.isnan(x):
                break
            xi = int(x)
            if xi < 0:
                break
            result.append(xi)
        return result

    # ── 6. 回测：增量调仓 ──
    nv = pd.Series(INIT_CASH, index=df.index, dtype=float)
    nv.iloc[0] = INIT_CASH
    cash = INIT_CASH
    rot = []
    last_open_idx = None

    for i in range(1, len(df)):
        t = df.index[i]
        desired_list = get_desired_top_n(i - 1)  # 用前一天的最终信号
        if not desired_list or any(np.isnan(x) for x in desired_list):
            desired_list = []
        desired_set = set(desired_list)

        # 当天持有的 sym indices
        current_keys = set(current_holdings.keys())
        already_held = desired_set & current_keys

        # 止损检查：对每只持仓标的检查
        stop_sold = []
        if stop_loss > 0:
            for sym_idx in list(current_keys):
                ep = entry_prices.get(sym_idx, 0)
                if ep <= 0:
                    continue
                cp = df.loc[t, f"close_{syms[sym_idx]}"]
                if np.isnan(cp) or cp <= 0:
                    continue
                if cp <= ep * (1 - stop_loss / 100):
                    stop_sold.append(sym_idx)

        # 需要清仓的：止损的 + 不在 desired_list 的
        to_sell = set(stop_sold) | (current_keys - desired_set)
        # 当天止损的标的，同天不得再买回（防止止损触发后又立刻被desired捡回来）
        stopped_out_today = set(stop_sold)
        sell_details = []
        for sym_idx in to_sell:
            if current_holdings[sym_idx]["shares"] <= 0:
                continue
            sp = df.loc[t, f"close_{syms[sym_idx]}"]
            if np.isnan(sp) or sp <= 0:
                sp = entry_prices.get(sym_idx, 0)
            if sp <= 0:
                sp = 1.0
            sh = current_holdings[sym_idx]["shares"]
            cash_before = cash
            proceeds = sh * sp * (1 - COST_RATE)
            entry_ep = entry_prices.get(sym_idx, 0)
            pnl_pct = round(float((sp - entry_ep) / entry_ep * 100), 1) if entry_ep > 0 else 0
            cash += proceeds
            sell_details.append({
                "sym_idx": sym_idx, "sym": syms[sym_idx],
                "name": names.get(syms[sym_idx], syms[sym_idx]),
                "pnl_pct": pnl_pct
            })
            del current_holdings[sym_idx]
            del entry_prices[sym_idx]

        # 卖出记录
        for sd in sell_details:
            is_stop = sd["sym_idx"] in stop_sold
            sig_label = "卖出(止损)" if is_stop else "卖出(空仓)"
            rot.append({
                "date": t.strftime("%Y-%m-%d"),
                "signal": sig_label,
                "symbol": sd["sym"],
                "name": sd["name"],
                "pnl_pct": sd["pnl_pct"],
                "net_value": round(float(cash + sum(v["shares"] * entry_prices.get(si, 0) for si, v in current_holdings.items() if entry_prices.get(si, 0) > 0)), 4)
            })
            # 回填上一个开仓行
            if last_open_idx is not None:
                rot[last_open_idx]["pnl_pct"] = sd["pnl_pct"]
                last_open_idx = None

        # 需要买入的：新进入 top-N 且未持有的（排除当天止损卖出的）
        to_buy = [si for si in desired_list if si not in current_holdings and si >= 0 and si not in stopped_out_today]
        # 按 weight_ratios 分配现金
        if to_buy and cash > 0:
            # 计算总权重
            total_w = sum(weight_ratios[j] for j in range(len(to_buy)) if j < len(weight_ratios))
            if total_w <= 0:
                total_w = 1.0
            for j, sym_idx in enumerate(to_buy):
                w = weight_ratios[j] if j < len(weight_ratios) else 0.0
                alloc = cash * w / total_w
                bp = df.loc[t, f"close_{syms[sym_idx]}"]
                if pd.isna(bp) or bp <= 0:
                    continue
                shares = alloc * (1 - COST_RATE) / bp
                if shares <= 0:
                    continue
                ep = bp
                cash -= alloc
                current_holdings[sym_idx] = {
                    "shares": shares, "entry_price": ep,
                    "entry_date": t.strftime("%Y-%m-%d"),
                    "weight": w
                }
                entry_prices[sym_idx] = ep

                # 买入记录
                rot.append({
                    "date": t.strftime("%Y-%m-%d"),
                    "signal": "买入",
                    "symbol": syms[sym_idx],
                    "name": names.get(syms[sym_idx], syms[sym_idx]),
                    "pnl_pct": None,
                    "net_value": round(float(cash + sum(v["shares"] * entry_prices.get(si, 0) for si, v in current_holdings.items() if entry_prices.get(si, 0) > 0)), 4)
                })
                last_open_idx = len(rot) - 1

        # 计算当日净值
        tv = cash
        for sym_idx, v in current_holdings.items():
            ep = entry_prices.get(sym_idx, 0)
            if ep <= 0:
                continue
            cp = df.loc[t, f"close_{syms[sym_idx]}"]
            if np.isnan(cp) or cp <= 0:
                tv += v["shares"] * ep
            else:
                tv += v["shares"] * cp
        nv[t] = tv

    nv.iloc[0] = INIT_CASH
    if len(nv) < 2:
        return [],[],[],[],None

    # 最后一条开仓行：用当前累积收益回填
    if last_open_idx is not None and current_holdings:
        entry_date = pd.Timestamp(rot[last_open_idx]["date"])
        if entry_date in nv.index:
            rot[last_open_idx]["pnl_pct"] = round(float((nv.iloc[-1] / nv.loc[entry_date] - 1) * 100), 1)

    # 净值序列
    nv = nv.replace([np.inf, -np.inf], np.nan).ffill()
    pct = nv.pct_change()
    nav = [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 4),
            "daily_pct": round(float(pct.get(d)) * 100, 2) if pct.get(d) and pct.get(d) == pct.get(d) else 0}
           for d, v in nv.items()]

    # 基准（等权）
    fcs = {sym: df[f"close_{sym}"].iloc[0] for sym in syms if f"close_{sym}" in df.columns}
    bench = sum(df[f"close_{s}"] / v for s, v in fcs.items()) / len(fcs) if fcs else pd.Series(1.0, index=df.index)
    bench_nav = [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)} for d, v in bench.items()]

    # 统计
    tr = nv.iloc[-1] / INIT_CASH - 1
    yrs = (nv.index[-1] - nv.index[0]).days / 365.25
    ar = (1 + tr) ** (1 / yrs) - 1 if yrs > 0 else 0
    ret = nv.pct_change().dropna()
    mdd = float((nv / nv.cummax() - 1).min())
    shrp = float((ret.mean() / ret.std()) * np.sqrt(252)) if ret.std() != 0 else 0
    stats = {"total_return": round(tr * 100, 1), "ann_return": round(ar * 100, 1),
             "max_drawdown": round(mdd * 100, 1), "sharpe": round(shrp, 2),
             "trading_days": len(df), "switches": len(rot)}

    # 当前持仓（多头中按 entry_price 排序的所有标的）
    h = []
    if current_holdings:
        sorted_holds = sorted(current_holdings.keys(),
                              key=lambda si: entry_prices.get(si, 0), reverse=True)
        last_date = nv.index[-1]
        for sym_idx in sorted_holds:
            sym = syms[sym_idx]
            last_price = df.loc[last_date, f"close_{sym}"]
            ep = entry_prices.get(sym_idx, 0)
            if ep > 0 and not np.isnan(last_price):
                ret_pct = round(float(last_price / ep - 1) * 100, 1)
                mom_latest = df.loc[last_date, "best_mom"]
                h.append({
                    "name": names.get(sym, sym), "symbol": sym,
                    "entry_date": current_holdings[sym_idx]["entry_date"],
                    "period_return_pct": ret_pct if np.isfinite(ret_pct) else 0,
                    "momentum_latest": round(float(mom_latest * 100), 1) if not np.isnan(mom_latest) and np.isfinite(mom_latest) else 0
                })

    stats = {k: (v if np.isfinite(v) else 0) for k, v in stats.items()}
    return nav, stats, rot, h, bench_nav

def _benchmark_nav(bench_sym):
    """加载基准指数的累计收益净值序列"""
    try:
        bdf = db_load([bench_sym])
        if bdf.empty: return None
        close_col = f"close_{bench_sym}"
        if close_col not in bdf.columns: return None
        closes = bdf[close_col].dropna()
        if len(closes) < 2: return None
        base = closes.iloc[0]
        if base <= 0: return None
        nv = closes / base
        return [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)}
                for d, v in nv.items()]
    except Exception as e:
        logger.error(f"基准计算失败 [{bench_sym}]: {e}")
        return None

def _recompute_cache(pfid, bench_sym=None):
    global _caches
    pf = _get_pf(pfid)
    if not pf: return
    syms = [i["sym"] for i in pf["indices"]]
    logger.info(f"缓存重算 [{pfid}]: syms={syms}")
    try:
        dfall = db_load(syms)
        logger.info(f"缓存重算 [{pfid}]: db_load={len(dfall)}行")
        if dfall.empty:
            logger.warning(f"缓存重算 [{pfid}]: 数据为空")
            return
        nav, stats, rot, h, _ = compute(dfall, pf["indices"], pf.get("window", 22),
                                          pf.get("ma_period", 60), pf.get("min_hold_days", 5),
                                          pf.get("stop_loss", 0), pf.get("mom_weights", [0.25, 0.5, 0.25]),
                                          pf.get("top_n", 1), pf.get("weight_ratios", None))
        if nav:
            # 清理所有 NaN/Inf 值
            def _ok(v):
                if isinstance(v, str) or v is None: return True
                try: return bool(np.isfinite(float(v)))
                except: return False
            nav = [{k: (v if _ok(v) else 0) for k, v in x.items()} for x in nav]
            rot = [{k: (v if _ok(v) else 0) for k, v in x.items()} for x in rot]
            # 基准数据
            bench_nav_data = None
            if bench_sym:
                bench_nav_data = _benchmark_nav(bench_sym)
                logger.info(f"[api_status] 基准数据 bench_sym={bench_sym}, 条数={len(bench_nav_data) if bench_nav_data else 0}")
            _caches[pfid] = {
                "nav": nav, "stats": stats,
                "rotation_log": rot, "current_holding": h,
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "benchmark": bench_nav_data if bench_nav_data else None
            }
            logger.info(f"缓存重算 [{pfid}]: nav={len(nav)}点, rot={len(rot)}条")
        else:
            logger.warning(f"缓存重算 [{pfid}]: compute 返回空 nav")
    except Exception as e:
        logger.error(f"缓存重算 [{pfid}]: {e}")

# ─── 定时调度管理 ─────────────────────────────────────
def _load_schedules():
    global _schedules
    if os.path.exists(SCHEDULES_PATH):
        try:
            with open(SCHEDULES_PATH, 'r', encoding='utf-8') as f:
                _schedules = json.load(f)
        except:
            _schedules = []
    else:
        _schedules = []

def _save_schedules():
    _atomic_write_json(SCHEDULES_PATH, _schedules)

def _sync_scheduler():
    """对比当前内存中的 _schedules 与 scheduler 内部任务，增量更新"""
    if _scheduler is None: return
    existing_ids = {_j.id for _j in _scheduler.get_jobs()}
    want_ids = {s["id"] for s in _schedules if s.get("enabled", True)}

    for _jid in existing_ids - want_ids:
        _scheduler.remove_job(_jid)
        logger.info(f"[调度] 移除任务 {_jid}")

    tz = pytz.timezone("Asia/Shanghai")
    for s in _schedules:
        if not s.get("enabled", True): continue
        job_id = s["id"]
        hh, mm = s["time"].split(":")
        _scheduler.add_job(
            _do_refresh,
            trigger=CronTrigger(hour=int(hh), minute=int(mm), second=0, timezone=tz),
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.info(f"[调度] 注册任务 {job_id} @ {s['time']}")

def _init_scheduler():
    global _scheduler
    tz = pytz.timezone("Asia/Shanghai")
    _scheduler = BackgroundScheduler(timezone=tz)

    def _do_refresh():
        """执行一次完整刷新（拉数据+重算所有组合缓存）并记录结果"""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            all_new = 0
            for pf in PORTFOLIOS:
                syms = [i["sym"] for i in pf["indices"]]
                nc = fetch_new(syms)
                all_new += nc
                _recompute_cache(pf["id"])
            _append_log({"time": ts, "ok": True, "new_count": all_new, "error": ""})
            logger.info(f"[定时刷新] 成功，新增 {all_new} 条数据")
        except Exception as e:
            _append_log({"time": ts, "ok": False, "new_count": 0, "error": str(e)})
            logger.error(f"[定时刷新] 失败: {e}")

    def _sync():
        """对比当前内存中的 _schedules 与 scheduler 内部任务，增量更新"""
        if _scheduler is None: return
        # 收集现有的 job_id 集合
        existing_ids = {_j.id for _j in _scheduler.get_jobs()}
        want_ids = {s["id"] for s in _schedules if s.get("enabled", True)}

        # 删除不在 want_ids 中的任务
        for _jid in existing_ids - want_ids:
            _scheduler.remove_job(_jid)
            logger.info(f"[调度] 移除任务 {_jid}")

        # 添加/更新任务
        tz = pytz.timezone("Asia/Shanghai")
        for s in _schedules:
            if not s.get("enabled", True): continue
            job_id = s["id"]
            hh, mm = s["time"].split(":")
            # job_id 已经是完整 id，直接用 id 字段创建/更新
            _scheduler.add_job(
                _do_refresh,
                trigger=CronTrigger(hour=int(hh), minute=int(mm), second=0, timezone=tz),
                id=job_id,
                replace_existing=True,
                misfire_grace_time=300,
            )
            logger.info(f"[调度] 注册任务 {job_id} @ {s['time']}")

    _load_schedules()
    _sync()
    _scheduler.start()
    logger.info("调度器启动完毕")

def _append_log(entry):
    logs = []
    if os.path.exists(UPDATE_LOG_PATH):
        try:
            with open(UPDATE_LOG_PATH, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"读取 update-log 失败: {e}")
            logs = []
    logs.insert(0, entry)
    logs = logs[:500]  # 最多保留 500 条
    _atomic_write_json(UPDATE_LOG_PATH, logs)

# ─── FastAPI ──────────────────────────────────────────
app = FastAPI(title="TrendRod V2")
app.mount("/static", StaticFiles(directory="/app/static"), name="static")

# ─── 安全响应头（C6: XSS 防护） ────────────────────────
# Content-Security-Policy 仍保留 'unsafe-inline' 给 script-src，因为 index.html
# 里还有大量 onclick/oninput 等内联事件（Part 2 正在迁移到 addEventListener）。
# Part 2 完成后可在后续 commit 移除 'unsafe-inline' 以收紧 CSP。
# connect-src 显式列出外部 API 域名（akshare 默认从 https://api 走，但本服务
# 自身只调用 minimaxi / wttr.in；保持最小允许列表，便于审计）。
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self' https://api.minimaxi.com https://wttr.in; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none';"
)
_SECURITY_HEADERS = {
    "Content-Security-Policy": _CSP,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}

@app.middleware("http")
async def _security_headers_middleware(request, call_next):
    """给所有响应附加安全相关 HTTP 头（CSP / X-Frame-Options 等）。

    对 HTML 和 JSON 响应均生效（多打几个 header 对 JSON 无害；浏览器会忽略
    不适用的 CSP 指令如 frame-ancestors）。"""
    response = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        # 不覆盖应用层已显式设置的同名头
        if k not in response.headers:
            response.headers[k] = v
    return response

@app.on_event("startup")
def _warmup():
    """预热默认组合缓存 + 启动调度器"""
    try:
        _recompute_cache(PORTFOLIOS[0]["id"])
        logger.info("启动预热完成")
    except Exception as e:
        logger.warning(f"预热失败: {e}")
    _init_scheduler()

@app.get("/")
def page():
    with open("/app/static/index.html", encoding="utf-8") as f:
        return HTMLResponse(
            content=f.read(),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate, max-age=0"}
        )

# ─── 组合 CRUD ──────────────────────────────────────
@app.get("/api/portfolios")
def api_list_portfolios():
    return {"portfolios": PORTFOLIOS}

# ─── name 校验（C5: 防御 XSS） ────────────────────
import re
_NAME_RE = re.compile(r'^[一-龥一-鿿 a-zA-Z0-9_.\-()（）【】「」]{1,32}$')

def _validate_name(name):
    """校验组合 name：1-32 字符；允许 CJK、拉丁字母数字、空格、
    及常见标点 - _ . ( ) （ ） 【 】 「 」 。拒绝 < > " ' & 控制字符。
    返回 None 表示通过，否则返回中文错误信息。"""
    if not isinstance(name, str):
        return "name 必须为字符串"
    s = name.strip()
    if not s:
        return "name 不能为空"
    if not _NAME_RE.match(s):
        return "name 长度须为 1-32 字符，仅允许中英文/数字与 - _ . ()（）【】「」"
    return None

@app.post("/api/portfolios")
def api_create_portfolio(data: dict = Body(...)):
    global PORTFOLIOS
    pfid = data.get("id", "").strip()
    if not pfid:
        return JSONResponse({"ok": False, "message": "id 不能为空"}, 400)
    if _get_pf(pfid):
        return JSONResponse({"ok": False, "message": "组合已存在"}, 400)
    name = data.get("name", pfid)
    err = _validate_name(name)
    if err:
        return JSONResponse({"ok": False, "message": err}, 422)
    pf = {
        "id": pfid,
        "name": name,
        "window": data.get("window", 22),
        "ma_period": data.get("ma_period", 60),
        "min_hold_days": data.get("min_hold_days", 5),
        "stop_loss": data.get("stop_loss", 0),
        "mom_weights": data.get("mom_weights", [0.25, 0.5, 0.25]),
        "top_n": data.get("top_n", 1),
        "weight_ratios": data.get("weight_ratios", None),
        "indices": data.get("indices", [])
    }
    PORTFOLIOS.append(pf)
    _save_portfolios(PORTFOLIOS)
    return {"ok": True, "portfolio": pf}

@app.put("/api/portfolios/reorder")
def api_reorder_portfolios(data: dict = Body(...)):
    """接收 {order: [pfid1, pfid2, ...]} 按给定顺序设置 sort 字段"""
    global PORTFOLIOS
    order = data.get("order", [])
    for i, pid in enumerate(order):
        pf = _get_pf(pid)
        if pf:
            pf["sort"] = i
    max_sort = len(PORTFOLIOS)
    for pf in PORTFOLIOS:
        if "sort" not in pf:
            max_sort += 1
            pf["sort"] = max_sort
    PORTFOLIOS.sort(key=lambda p: p.get("sort", 999))
    _save_portfolios(PORTFOLIOS)
    return {"ok": True}

@app.put("/api/portfolios/{pfid}")
def api_update_portfolio(pfid: str, data: dict = Body(...)):
    global PORTFOLIOS
    pf = _get_pf(pfid)
    if not pf:
        return JSONResponse({"ok": False, "message": "组合不存在"}, 404)
    if "name" in data:
        err = _validate_name(data["name"])
        if err:
            return JSONResponse({"ok": False, "message": err}, 422)
        pf["name"] = data["name"]
    if "window" in data: pf["window"] = int(data["window"])
    if "ma_period" in data: pf["ma_period"] = int(data["ma_period"])
    if "min_hold_days" in data: pf["min_hold_days"] = int(data["min_hold_days"])
    if "stop_loss" in data: pf["stop_loss"] = int(data["stop_loss"])
    if "mom_weights" in data: pf["mom_weights"] = data["mom_weights"]
    if "top_n" in data: pf["top_n"] = int(data["top_n"])
    if "weight_ratios" in data: pf["weight_ratios"] = data["weight_ratios"]
    if "indices" in data: pf["indices"] = data["indices"]
    _save_portfolios(PORTFOLIOS)
    _recompute_cache(pfid)
    return {"ok": True, "portfolio": pf}

@app.delete("/api/portfolios/{pfid}")
def api_delete_portfolio(pfid: str):
    global PORTFOLIOS
    if len(PORTFOLIOS) <= 1:
        return JSONResponse({"ok": False, "message": "至少保留一个组合"}, 400)
    pf = _get_pf(pfid)
    if not pf:
        return JSONResponse({"ok": False, "message": "组合不存在"}, 404)
    PORTFOLIOS = [p for p in PORTFOLIOS if p["id"] != pfid]
    _save_portfolios(PORTFOLIOS)
    _caches.pop(pfid, None)
    return {"ok": True}

# ─── 标的搜索 ──────────────────────────────────────
@app.get("/api/search_indices")
def api_search(q: str = Query("")):
    return {"results": _search_indices(q)}

# ─── 标的管理（针对某组合） ────────────────────────
@app.post("/api/portfolios/{pfid}/indices")
def api_add_index(pfid: str, sym: str = Query(...), name: str = Query("")):
    global PORTFOLIOS
    pf = _get_pf(pfid)
    if not pf:
        return JSONResponse({"ok": False, "message": "组合不存在"}, 404)
    # 如果没给 name，从搜索缓存中查找
    if not name:
        results = _search_indices(sym)
        if results:
            name = results[0]["name"]
        else:
            name = sym
    for idx in pf["indices"]:
        if idx["sym"] == sym:
            return JSONResponse({"ok": False, "message": "该标的已存在"}, 400)
    if len(pf["indices"]) >= 26:
        return JSONResponse({"ok": False, "message": "最多 26 个标的"}, 400)
    pf["indices"].append({"sym": sym, "name": name[:10]})
    _save_portfolios(PORTFOLIOS)
    # 尝试拉取数据
    new_count = fetch_one(sym)
    _recompute_cache(pfid)
    return {"ok": True, "new_count": new_count}

@app.delete("/api/portfolios/{pfid}/indices/{sym}")
def api_remove_index(pfid: str, sym: str):
    global PORTFOLIOS
    pf = _get_pf(pfid)
    if not pf:
        return JSONResponse({"ok": False, "message": "组合不存在"}, 404)
    if len(pf["indices"]) <= 1:
        return JSONResponse({"ok": False, "message": "至少保留一个标的"}, 400)
    pf["indices"] = [idx for idx in pf["indices"] if idx["sym"] != sym]
    _save_portfolios(PORTFOLIOS)
    _recompute_cache(pfid)
    return {"ok": True}

# ─── 数据刷新（针对某组合） ────────────────────────
@app.post("/api/refresh")
def api_refresh(portfolio: str = Query("default"), benchmark: str = Query("")):
    pf = _get_pf(portfolio)
    if not pf:
        return JSONResponse({"ok": False, "message": "组合不存在"}, 404)
    syms = [i["sym"] for i in pf["indices"]]
    try:
        nc = fetch_new(syms)
        bench_sym = benchmark.strip() if benchmark else None
        _recompute_cache(portfolio, bench_sym=bench_sym)
        cache = _caches.get(portfolio, {})
        return {"ok": True, "new_data_count": nc, "last_update": cache.get("last_update", "")}
    except Exception as e:
        logger.error(f"刷新失败 [{portfolio}]: {traceback.format_exc()}")
        return JSONResponse({"ok": False, "message": str(e)}, 500)

@app.get("/api/status")
def api_status(portfolio: str = Query("default"), benchmark: str = Query("")):
    bench_sym = benchmark.strip() if benchmark else None
    logger.info(f"[api_status] portfolio={portfolio}, bench_sym={bench_sym}")
    if portfolio not in _caches or not _caches[portfolio].get("nav"):
        _recompute_cache(portfolio, bench_sym=bench_sym)
    cache = _caches.get(portfolio, {})
    # 如果请求了基准但缓存中没有，强制重算
    if bench_sym and not cache.get("benchmark"):
        logger.info(f"[api_status] 缓存无基准数据，强制重算基准={bench_sym}")
        _recompute_cache(portfolio, bench_sym=bench_sym)
        cache = _caches.get(portfolio, {})
    if not cache.get("nav"):
        return JSONResponse({"ok": False, "message": "暂无数据，请先刷新"}, 503)
    keys = ["nav", "stats", "rotation_log", "current_holding", "last_update"]
    result = {"ok": True, **{k: cache[k] for k in keys}}
    if bench_sym and cache.get("benchmark"):
        result["benchmark"] = cache["benchmark"]
        result["benchmark_sym"] = bench_sym
    return result

# ─── 定时任务管理 ─────────────────────────────────────
@app.get("/api/schedules")
def api_list_schedules():
    return {"schedules": _schedules}

@app.post("/api/schedules")
def api_save_schedules(data: dict = Body(...)):
    global _schedules
    raw = data.get("schedules", [])
    # 校验格式，忽略无效条目
    schedules = []
    for s in raw:
        if not isinstance(s, dict): continue
        tid = str(s.get("id", "")).strip()
        if not tid: continue
        t = str(s.get("time", "")).strip()
        if not t: continue
        # 格式检查 HH:MM
        try:
            parts = t.split(":")
            hh, mm = int(parts[0]), int(parts[1])
            if not (0 <= hh <= 23 and 0 <= mm <= 59): raise ValueError()
        except:
            return JSONResponse({"ok": False, "message": f"时间格式错误: {t}，应为 HH:MM"}, 400)
        schedules.append({"id": tid, "time": t, "enabled": bool(s.get("enabled", True))})

    _schedules = schedules
    _save_schedules()
    _sync_scheduler()
    return {"ok": True, "schedules": _schedules}

@app.delete("/api/schedules/{sid}")
def api_delete_schedule(sid: str):
    global _schedules
    _schedules = [s for s in _schedules if s["id"] != sid]
    _save_schedules()
    _sync_scheduler()
    return {"ok": True}

@app.post("/api/schedules/run-now")
def api_run_now():
    """立即触发一次刷新（测试用）"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        all_new = 0
        for pf in PORTFOLIOS:
            syms = [i["sym"] for i in pf["indices"]]
            nc = fetch_new(syms)
            all_new += nc
            _recompute_cache(pf["id"])
        _append_log({"time": ts, "ok": True, "new_count": all_new, "error": ""})
        return {"ok": True, "new_count": all_new, "time": ts}
    except Exception as e:
        _append_log({"time": ts, "ok": False, "new_count": 0, "error": str(e)})
        return JSONResponse({"ok": False, "message": str(e)}, 500)

@app.get("/api/update-log")
def api_update_log(limit: int = Query(20, ge=1, le=200)):
    if not os.path.exists(UPDATE_LOG_PATH):
        return {"logs": []}
    try:
        with open(UPDATE_LOG_PATH, 'r', encoding='utf-8') as f:
            logs = json.load(f)
        return {"logs": logs[:limit]}
    except:
        return {"logs": []}
