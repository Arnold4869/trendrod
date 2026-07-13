"""
TrendRod × Backtrader 回测工具
用法:
  python backtest_bt.py --portfolio default
  python backtest_bt.py --portfolio default --start_date 2020-01-01
  python backtest_bt.py --portfolio default --mom_period 22 --ma_period 60 --min_hold 5 --stop_loss 0
  python backtest_bt.py --portfolio default --output json
  python backtest_bt.py --portfolio default --refresh-cache

限制说明 (H10/H11):
  本工具为独立回测 CLI，与主引擎 app/main.py 的向量化回测逻辑重复。
  当前仅支持 top_n=1 的单标的回测（单 data feed 全仓轮动）。
  top_n>1 的多持仓场景请使用主引擎 main.py 的向量化回测（compute 支持 top_n + weight_ratios）。
  传入 top_n>1 时会打印警告并按 top_n=1 执行，避免静默错误。

默认参数与 main.py 对齐:
  mom_periods=[5,22,60] (对应 window=22 的多周期合成), ma_period=60,
  min_hold_days=5, mom_weights=[0.25,0.5,0.25], top_n=1
"""
import os, sys, json, argparse, logging, math
from datetime import datetime

import numpy as np
import pandas as pd
import backtrader as bt
import sqlite3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bt_backtest")


# ─── 路径配置 ─────────────────────────────────────────
DB_PATH   = os.getenv("DATABASE_PATH",  "/data/trendrod.db")
PF_PATH   = os.getenv("CONFIG_PATH",   "/data/trendrod_portfolios.json")
FEEDS_DIR = "/data/bt_feeds"           # 持久化 CSV 数据目录

os.makedirs(FEEDS_DIR, exist_ok=True)


# ─── 读取组合配置 ─────────────────────────────────────
def load_portfolios():
    if os.path.exists(PF_PATH):
        with open(PF_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def get_portfolio(pfid: str):
    for p in load_portfolios():
        if p["id"] == pfid:
            return p
    return None


# ─── SQLite → CSV (Backtrader Data Feed) ───────────────
def refresh_sqlite_from_akshare(symbols):
    """M15: 从 akshare 拉取最新数据更新 SQLite（best-effort，失败仅告警）。
    与 main.py 的 fetch_one 语义一致：INSERT OR REPLACE 覆盖历史 bar。"""
    try:
        import akshare as ak
    except ImportError:
        logger.warning("akshare 未安装，跳过 akshare 刷新（仅用 SQLite 现有数据重建 CSV）")
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS idx(sym TEXT,dt TEXT,o REAL,c REAL,h REAL,l REAL,v REAL,PRIMARY KEY(sym,dt))')
        for sym in symbols:
            try:
                df = ak.stock_zh_index_daily(symbol=sym)
                if df is None or df.empty:
                    continue
                records = [(sym, r["date"], float(r["open"]), float(r["close"]),
                            float(r["high"]), float(r["low"]), float(r["volume"]))
                           for _, r in df.iterrows()]
                conn.executemany("INSERT OR REPLACE INTO idx VALUES(?,?,?,?,?,?,?)", records)
                conn.commit()
                logger.info(f"  [{sym}] akshare 刷新 {len(records)} 条")
            except Exception as e:
                logger.warning(f"  [{sym}] akshare 刷新失败: {e}")
    finally:
        conn.close()


def db_load_csv(symbols, force_refresh=False):
    """
    从 SQLite 读取多个标的数据，写入 /data/bt_feeds/{sym}.csv
    force_refresh=True 时强制重新生成 CSV（覆盖已有缓存）。
    返回 {sym: csv_path}
    """
    conn = sqlite3.connect(DB_PATH)
    paths = {}
    for sym in symbols:
        csv_path = os.path.join(FEEDS_DIR, f"{sym}.csv")
        # 已有完整 CSV 且非空且未要求刷新，跳过
        if not force_refresh and os.path.exists(csv_path) and os.path.getsize(csv_path) > 100:
            paths[sym] = csv_path
            continue

        rows = conn.execute(
            "SELECT dt, o, c, h, l, v FROM idx WHERE sym=? ORDER BY dt",
            (sym,)
        ).fetchall()
        if not rows:
            logger.warning(f"  [{sym}] 数据库中无数据")
            continue

        df = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume"])
        df["date"] = pd.to_datetime(df["date"])
        # Backtrader CSV 格式: Datestamp,Open,High,Low,Close,Volume,OpenInterest
        df["openinterest"] = 0
        df = df[["date", "open", "high", "low", "close", "volume", "openinterest"]]
        df.to_csv(csv_path, index=False)
        logger.info(f"  [{sym}] 写入 {csv_path}  ({len(df)} 行)")
        paths[sym] = csv_path

    conn.close()
    return paths


# ─── Backtrader 策略 ──────────────────────────────────
INIT_CASH   = 1_000_000.0   # 方便看绝对数字，回测结果同样用比例算
COST_RATE   = 0.0003


class MomentumRotation(bt.Strategy):
    """
    多标的跨截面动量轮动策略 (Backtrader 版本)

    限制 (H10/H11):
      当前仅支持 top_n=1 的单标的回测（单 data feed 全仓轮动）。
      top_n/weight_ratios 参数仅为与 main.py 配置对齐而保留；
      top_n>1 时会打印警告并按 top_n=1 执行。多持仓请用 main.py 向量化回测。

    参数:
      mom_periods   : list[int]   动量周期列表，默认 [5, 22, 60]
      mom_weights   : list[float] 对应权重，默认 [0.25, 0.5, 0.25]
      ma_period     : int         均线周期，0=关闭
      min_hold_days : int         最小持有天数，0=关闭
      stop_loss     : float       止损比例(%)，0=关闭
      top_n         : int         买入前几名（当前仅支持 1）
      weight_ratios : list[float] 各位置分配比例（当前仅 top_n=1 生效）
    """
    params = (
        ("mom_periods",   [5, 22, 60]),
        ("mom_weights",   [0.25, 0.5, 0.25]),
        ("ma_period",     60),
        ("min_hold_days", 5),
        ("stop_loss",      0.0),          # %
        ("top_n",          1),
        ("weight_ratios",  None),
        ("verbose",        False),
    )

    def __init__(self):
        # H10/H11: 多持仓限制检查
        if self.params.top_n and self.params.top_n > 1:
            logger.warning(
                f"top_n={self.params.top_n} > 1：当前 backtest_bt.py 仅支持单标的回测（top_n=1），"
                f"多持仓请使用主引擎 main.py 的向量化回测。将按 top_n=1 执行。"
            )

        # 为每个 data（标的）建立指标字典
        self.inds = {}
        for d in self.datas:
            c = d.close
            ma = bt.indicators.SMA(c, period=self.params.ma_period) \
                 if self.params.ma_period > 0 else None
            # 预计算各周期动量
            moms = {}
            for per in self.params.mom_periods:
                moms[per] = bt.indicators.PctChange(c, period=per)
            self.inds[d] = {"ma": ma, "moms": moms}

        # 状态跟踪
        self.order        = None          # 当前挂单
        self.hold_days    = 0             # 持仓计数
        self.last_sig     = None          # 上一个信号(对应标的index)
        self.entry_price  = 0.0           # 入场价（由 notify_order 用实际成交价更新）
        self.entry_sym    = None          # 标的

        # 交易日志
        self.rot_log = []

        # pnl 回填：上一个开仓记录在 rot_log 中的索引，卖出/调仓时回填其 pnl_pct
        self._last_open_idx = None

        # 净值记录: [(datetime, net_value), ...]
        self._nav_records = []

        # 初始组合净值（用于相对计算）
        self._init_cash = self.broker.getvalue()

    def log(self, txt, d=None):
        if self.params.verbose and d is not None:
            dt = d.datetime.date(0)
            logger.info(f"  [{dt}] {txt}")
        elif self.params.verbose:
            logger.info(f"  {txt}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                # M13: set_coc(False) 后，order 在下一 bar open 成交；
                # 用实际成交价更新 entry_price（覆盖 next() 中的 close 估算值）
                self.entry_price = order.executed.price
                self.log(f"买入: {order.data._name} @ {order.executed.price:.4f}")
            elif order.issell():
                self.log(f"卖出: {order.data._name} @ {order.executed.price:.4f}")
            self.order = None   # 挂单完成
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"订单失败: {order.data._name} status={order.status}", self.datas[0])
            self.order = None

    def _score(self, d):
        """计算某标的的综合动量分数（加权多周期）"""
        scores = []
        for per, w in zip(self.params.mom_periods, self.params.mom_weights):
            mom_val = self.inds[d]["moms"][per][0]
            if np.isnan(mom_val):
                return np.nan
            scores.append(mom_val * w)
        return sum(scores)

    def _ma_ok(self, d):
        """均线过滤：收盘价 > MA（MA关闭时恒True）"""
        if self.params.ma_period <= 0:
            return True
        return d.close[0] >= self.inds[d]["ma"][0]

    def _stop_loss_check(self):
        """止损检查：浮亏超过 stop_loss 则强制空仓"""
        if self.params.stop_loss <= 0 or self.entry_price <= 0:
            return False
        for d in self.datas:
            pos = self.getposition(d)
            if pos.size > 0:
                pct = (d.close[0] - self.entry_price) / self.entry_price * 100
                if pct <= -self.params.stop_loss:
                    self.log(f"止损! {d._name} 浮亏 {pct:.2f}%")
                    return True
        return False

    def next(self):
        # ── Phase 1: 如果上回合有 pending_order，等待完成 ──
        if self.order is not None:
            # 持仓天数计数
            if self.last_sig is not None and self.last_sig >= 0:
                self.hold_days += 1
            self._nav_records.append((self.datas[0].datetime.date(0), self.broker.getvalue()))
            return

        # ── Phase 2: 正常信号处理 ──
        # 构建候选列表
        candidates = []
        for i, d in enumerate(self.datas):
            score = self._score(d)
            if np.isnan(score) or score <= 0:
                continue
            if not self._ma_ok(d):
                continue
            candidates.append((score, i, d))

        if not candidates:
            target = None
        else:
            _, _, target = max(candidates, key=lambda x: x[0])

        # 止损优先 → 强制空仓
        if self._stop_loss_check():
            target = None

        # 信号转换
        sig = -1
        if target is not None:
            sig = list(self.datas).index(target)

        # 最小持有期强制
        if self.params.min_hold_days > 0 and self.last_sig is not None:
            if sig != self.last_sig and self.hold_days < self.params.min_hold_days:
                sig = self.last_sig
                target = list(self.datas)[int(sig)] if sig >= 0 else None

        # 执行调仓
        # M13: set_coc(False) —— 信号在本 bar 收盘产生后，order 于下一 bar open 成交，
        # 不再偷看本 bar 收盘价（防未来函数）。next() 中的 close 仅用于估算下单 size
        # 与日志 pnl；实际成交价由 notify_order 用 order.executed.price 记录。
        if sig != self.last_sig:
            # 计算当前持仓的 PnL（用本 bar 收盘价估算，与 main.py 一致；
            # 实际卖出成交价为下一 bar open，此处仅用于日志回填）
            prev_pnl = None
            if self.last_sig is not None and self.last_sig >= 0 and self.entry_price > 0:
                for d in self.datas:
                    pos = self.getposition(d)
                    if pos.size > 0:
                        prev_pnl = round((d.close[0] - self.entry_price) / self.entry_price * 100, 1)
                        break

            # H10/H11 pnl 回填：把上一开仓记录的 pnl_pct 补上（与 main.py 的 last_open_idx 一致）
            if self._last_open_idx is not None and prev_pnl is not None:
                self.rot_log[self._last_open_idx]["pnl_pct"] = prev_pnl
                self._last_open_idx = None

            # 平掉所有持仓
            for d in self.datas:
                pos = self.getposition(d)
                if pos.size > 0:
                    self.close(d)

            if target is not None:
                # 全仓买入新标的（预留佣金避免 Margin）
                cash  = self.broker.getcash()
                price = target.close[0]   # 仅用于估算 size；实际成交价 = 下一 bar open（notify_order 记录）
                size  = math.floor(cash / (price * (1 + COST_RATE)))   # floor 防浮点超 Margin
                if size > 0:
                    self.buy(target, size=size)
                    self.entry_price = price   # 临时估值，notify_order 会用实际成交价覆盖
                    self.entry_sym   = target._name
                    self.hold_days   = 0
                    sig_label = "买入" if (self.last_sig is None or self.last_sig < 0) else "调仓"
                    net_value = self.broker.getvalue()
                    self.rot_log.append({
                        "date":      target.datetime.date(0).strftime("%Y-%m-%d"),
                        "signal":    sig_label,
                        "symbol":    target._name,
                        "name":      target._name,
                        "pnl_pct":   None,
                        "net_value": round(net_value, 4),
                    })
                    self._last_open_idx = len(self.rot_log) - 1
                    self.log(f"信号切换 → {target._name}，净值 {net_value:.4f}")
                self.last_sig = sig
            else:
                # 直接空仓
                if self.last_sig is not None and self.last_sig >= 0:
                    net_value = self.broker.getvalue()
                    self.rot_log.append({
                        "date":      self.datas[0].datetime.date(0).strftime("%Y-%m-%d"),
                        "signal":    "卖出(空仓)",
                        "symbol":    "",
                        "name":      "空仓",
                        "pnl_pct":   prev_pnl,
                        "net_value": round(net_value, 4),
                    })
                    self.log(f"空仓，净值 {net_value:.4f}")
                self.entry_price = 0.0
                self.entry_sym   = None
                self.hold_days   = 0
                self.last_sig    = sig
        else:
            # 持仓天数计数
            if self.last_sig is not None and self.last_sig >= 0:
                self.hold_days += 1

        self._nav_records.append((self.datas[0].datetime.date(0), self.broker.getvalue()))

    def stop(self):
        # 回测结束时补充最后持仓的 pnl_pct
        for d in self.datas:
            pos = self.getposition(d)
            if pos.size > 0:
                pnl = (d.close[0] - self.entry_price) / self.entry_price * 100 \
                      if self.entry_price > 0 else 0
                self.log(f"最终持仓: {d._name} 浮盈 {pnl:.2f}%")
                # H10/H11 pnl 回填：把最后未平仓的开仓记录 pnl_pct 补上
                if self._last_open_idx is not None:
                    self.rot_log[self._last_open_idx]["pnl_pct"] = round(float(pnl), 1)
                    self._last_open_idx = None


# ─── 主回测函数 ───────────────────────────────────────
def run_backtest(pf_id: str,
                 start_date: str = None,
                 mom_periods: list = None,
                 ma_period: int = 60,
                 min_hold_days: int = 5,
                 stop_loss: float = 0.0,
                 output: str = "text",
                 verbose: bool = False,
                 refresh_cache: bool = False):
    pf = get_portfolio(pf_id)
    if not pf:
        logger.error(f"组合不存在: {pf_id}")
        return

    indices   = pf["indices"]
    syms      = [i["sym"] for i in indices]
    names     = {i["sym"]: i["name"] for i in indices}

    # mom_periods 跟随 window 参数换算
    # 双引擎对齐: 与 main.py MOM_PERIODS 同步
    if mom_periods is None:
        mom_periods = [5, 22, 60]
    mom_weights = [0.25, 0.5, 0.25]

    # H10/H11: 读取 portfolio 配置的 top_n / weight_ratios（与 main.py compute 一致）
    top_n        = pf.get("top_n", 1)
    weight_ratios = pf.get("weight_ratios", None)
    if top_n and top_n > 1:
        logger.warning(
            f"top_n={top_n} > 1：当前 backtest_bt.py 仅支持单标的回测（top_n=1），"
            f"多持仓请使用主引擎 main.py 的向量化回测。将按 top_n=1 执行。"
        )
        top_n = 1   # 强制单标的，避免静默错误

    logger.info(f"组合: {pf['name']} | 标的: {syms}")
    logger.info(f"动量周期: {mom_periods} 权重: {mom_weights}")
    logger.info(f"均线: {ma_period} | 最小持有: {min_hold_days}天 | 止损: {stop_loss}% | top_n={top_n}")

    # ── 1. 数据准备 ──
    # M15: --refresh-cache 时先从 akshare 刷新 SQLite，再强制重建 CSV
    if refresh_cache:
        logger.info("刷新缓存: 从 akshare 拉取最新数据并重建 CSV")
        refresh_sqlite_from_akshare(syms)
    csv_paths = db_load_csv(syms, force_refresh=refresh_cache)

    # ── 2. Cerebro ──
    cerebro = bt.Cerebro()

    # 注入数据
    for sym in syms:
        if sym not in csv_paths:
            continue
        data = bt.feeds.GenericCSVData(
            dataname=csv_paths[sym],
            fromdate=datetime.strptime(start_date, "%Y-%m-%d") if start_date else datetime(2000, 1, 1),
            todate=datetime(2099, 12, 31),
            dtformat="%Y-%m-%d",
            datetime=0, open=1, high=2, low=3, close=4, volume=5, openinterest=6,
            name=sym,
        )
        cerebro.adddata(data)

    # 注入策略
    cerebro.addstrategy(
        MomentumRotation,
        mom_periods=mom_periods,
        mom_weights=mom_weights,
        ma_period=ma_period,
        min_hold_days=min_hold_days,
        stop_loss=stop_loss,
        top_n=top_n,
        weight_ratios=weight_ratios,
        verbose=verbose,
    )

    # 经纪商
    cerebro.broker.setcash(INIT_CASH)
    cerebro.broker.setcommission(commission=COST_RATE)
    # M13: set_coc(False) —— 信号在 bar 收盘产生后，于下一 bar open 成交，防未来函数。
    # （原 cheat-on-close 模式会用本 bar 收盘价成交 = 偷看未来信号）
    cerebro.broker.set_coc(False)

    # 分析器（净值已由策略内部记录）
    # ── 3. 运行 ──
    logger.info(f"初始资金: {INIT_CASH:.0f}")
    results = cerebro.run()
    final_value = cerebro.broker.getvalue()
    logger.info(f"最终净值: {final_value:.4f}  ({(final_value/INIT_CASH-1)*100:.2f}%)")

    # ── 4. 提取结果 ──
    strat   = results[0]
    rot_log = strat.rot_log
    records = strat._nav_records   # [(datetime, net_value), ...]

    # 统计计算
    vals = np.array([v for _, v in records])
    dts  = [d for d, _ in records]
    nv   = vals / vals[0]
    ret  = pd.Series(nv).pct_change().dropna()

    total  = nv[-1] / nv[0] - 1
    yrs    = len(nv) / 252
    ar     = (1 + total) ** (1 / yrs) - 1 if yrs > 0 else 0
    nv_s   = pd.Series(nv)
    mdd    = float((nv_s / nv_s.cummax() - 1).min())
    shrp   = float(ret.mean() / ret.std() * np.sqrt(252)) if ret.std() > 0 else 0

    stats = {
        "total_return": round(total * 100, 1),
        "ann_return":   round(ar * 100, 1),
        "max_drawdown": round(mdd * 100, 1),
        "sharpe":       round(shrp, 2),
        "trading_days": len(nv),
        "switches":     len(rot_log),
    }

    # 净值曲线
    nav = []
    prev_v = None
    for d, v in zip(dts, nv):
        pct = (v / prev_v - 1) * 100 if prev_v else 0
        nav.append({
            "date":      d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d),
            "value":     round(float(v), 4),
            "daily_pct": round(float(pct), 2),
        })
        prev_v = v

    # 当前持仓
    holding = None
    for d in strat.datas:
        pos = strat.getposition(d)
        if pos.size > 0:
            ret_pct = (d.close[0] - strat.entry_price) / strat.entry_price * 100 if strat.entry_price > 0 else 0
            holding = {
                "name":           d._name,
                "symbol":         d._name,
                "entry_date":     "",
                "period_return_pct": round(float(ret_pct), 1),
                "momentum_latest": 0.0,
            }
            break

    # ── 5. 输出 ──
    if output == "json":
        out = {
            "ok": True,
            "portfolio": pf_id,
            "params": {
                "mom_periods": mom_periods,
                "ma_period": ma_period,
                "min_hold_days": min_hold_days,
                "stop_loss": stop_loss,
                "top_n": top_n,
            },
            "nav": nav,
            "stats": stats,
            "rotation_log": rot_log,
            "current_holding": holding,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("\n" + "=" * 50)
        print(f"  TrendRod × Backtrader 回测报告")
        print("=" * 50)
        print(f"  组合: {pf['name']} ({pf_id})")
        print(f"  标的: {syms}")
        print(f"  参数: mom={mom_periods} ma={ma_period} hold={min_hold_days}d stop={stop_loss}%")
        print("-" * 50)
        print(f"  总收益:   {stats['total_return']:>8.1f}%")
        print(f"  年化收益: {stats['ann_return']:>8.1f}%")
        print(f"  最大回撤: {stats['max_drawdown']:>8.1f}%")
        print(f"  夏普比率: {stats['sharpe']:>8.2f}")
        print(f"  交易天数: {stats['trading_days']:>8d}")
        print(f"  轮动次数: {stats['switches']:>8d}")
        print("-" * 50)
        print(f"  最终净值: {final_value/INIT_CASH:.4f}")
        print("=" * 50)
        if rot_log:
            print("\n  轮动记录:")
            for r in rot_log[-20:]:
                print(f"    {r['date']} {r['signal']:>6} {r['symbol']} pnl={r.get('pnl_pct',0)}% nv={r.get('net_value',0)}")


# ─── 入口 ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TrendRod Backtrader 回测")
    parser.add_argument("--portfolio",  default="default")
    parser.add_argument("--start_date", default=None)
    parser.add_argument("--mom_period", type=int, default=None)   # 单一周期覆盖
    parser.add_argument("--ma_period",  type=int, default=60)
    parser.add_argument("--min_hold",   type=int, default=5)
    parser.add_argument("--stop_loss",  type=float, default=0.0)
    parser.add_argument("--output",     default="text", choices=["text", "json"])
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true",
                        help="M15: 强制从 akshare 重新拉取数据并覆盖 CSV 缓存")
    args = parser.parse_args()

    run_backtest(
        pf_id         = args.portfolio,
        start_date    = args.start_date,
        mom_periods   = [args.mom_period] if args.mom_period else None,
        ma_period     = args.ma_period,
        min_hold_days = args.min_hold,
        stop_loss     = args.stop_loss,
        output        = args.output,
        verbose       = args.verbose,
        refresh_cache = args.refresh_cache,
    )
