"""TrendRod 烟雾测试 — 针对 compute 相关纯函数。
运行前提：已安装 requirements.txt + pytest。本地无 Python 时请在 Docker 内运行：
  docker compose exec trendrod pytest tests/ -v
"""
import sys, os
# 在 import main 前设置临时路径，避免副作用写到 /data
os.environ.setdefault("DATABASE_PATH", "/tmp/test_trendrod.db")
os.environ.setdefault("CONFIG_PATH", "/tmp/test_portfolios.json")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import numpy as np
import pandas as pd
import pytest

from main import _compute_momentum, _compute_stats, compute, MOM_PERIODS, INIT_CASH


def _make_df(syms, days=120):
    """构造合成日线 DataFrame，每个标的有 close_/open_ 列。"""
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    df = pd.DataFrame(index=dates)
    np.random.seed(42)
    for sym in syms:
        rets = np.random.randn(days) * 0.01 + 0.0005
        close = 100 * np.exp(np.cumsum(rets))
        df[f"close_{sym}"] = close
        df[f"open_{sym}"] = close * (1 + np.random.randn(days) * 0.002)
    return df


def test_mom_periods_fixed():
    """MOM_PERIODS 应为 [5, 22, 60]。"""
    assert MOM_PERIODS == [5, 22, 60]


def test_compute_momentum_basic():
    """_compute_momentum 应生成 mom_ 和 ma_ 列。"""
    syms = ["sh000016", "sh000300"]
    df = _make_df(syms)
    _compute_momentum(df, syms, [0.25, 0.5, 0.25], 20)
    for sym in syms:
        assert f"mom_{sym}" in df.columns
        assert f"ma_{sym}" in df.columns
    # mom_ 列在足够长的数据后应为有限值
    assert df["mom_sh000016"].iloc[-1] == pytest.approx(df["mom_sh000016"].iloc[-1])


def test_compute_momentum_no_ma():
    """ma_period=0 时不应生成 ma_ 列。"""
    df = _make_df(["sh000016"])
    _compute_momentum(df, ["sh000016"], [0.25, 0.5, 0.25], 0)
    assert "mom_sh000016" in df.columns
    assert "ma_sh000016" not in df.columns


def test_compute_stats_basic():
    """_compute_stats 应返回含必要 key 的 dict，数值合理。"""
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    nv = pd.Series(np.linspace(1.0, 1.2, 100), index=dates)
    df = _make_df(["sh000016"], 100)
    stats = _compute_stats(nv, [], df)
    for k in ["total_return", "ann_return", "max_drawdown", "sharpe", "trading_days", "switches"]:
        assert k in stats
    assert stats["total_return"] == pytest.approx(20.0, abs=0.1)
    assert stats["trading_days"] == 100
    assert stats["switches"] == 0
    assert stats["max_drawdown"] <= 0  # 回撤非正


def test_compute_stats_finite():
    """_compute_stats 所有值应为有限数（isfinite 兜底）。"""
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    nv = pd.Series([1.0] * 10, index=dates)
    df = _make_df(["sh000016"], 10)
    stats = _compute_stats(nv, [{"date": "2024-01-02"}], df)
    for v in stats.values():
        assert np.isfinite(v)


def test_compute_smoke():
    """compute 端到端烟雾测试：合成数据应返回非空 nav/stats。"""
    syms = ["sh000016", "sh000300", "sh000905"]
    indices = [{"sym": s, "name": f"测试{s}"} for s in syms]
    df = _make_df(syms, 120)
    nav, stats, rot, h, bench = compute(
        df, indices, window=22, ma_period=20, min_hold_days=3,
        stop_loss=0, mom_weights=[0.25, 0.5, 0.25], top_n=1
    )
    assert len(nav) > 0, "nav 不应为空"
    assert isinstance(stats, dict)
    assert "total_return" in stats
    assert isinstance(rot, list)
    assert bench is None or isinstance(bench, list)


def test_compute_empty():
    """空 DataFrame 应返回空结果。"""
    nav, stats, rot, h, bench = compute(pd.DataFrame(), [], 22)
    assert nav == []
    assert stats == []
    assert h is None


def test_compute_top_n():
    """top_n=2 应正常返回（多持仓路径不崩溃）。"""
    syms = ["sh000016", "sh000300", "sh000905"]
    indices = [{"sym": s, "name": f"测试{s}"} for s in syms]
    df = _make_df(syms, 120)
    nav, stats, rot, h, bench = compute(
        df, indices, window=22, ma_period=20, min_hold_days=3,
        mom_weights=[0.25, 0.5, 0.25], top_n=2
    )
    assert len(nav) > 0
