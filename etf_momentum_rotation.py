import akshare as ak
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ------------------------------
# 1. 配置参数
# ------------------------------
# 欲轮动的 ETF 池，按字典顺序对应脚本中的 A、B、C
# 示例1：股债组合（创业板+上证50+国债）
ETF_POOL = {
 "159915": "创业板ETF",
 "510050": "上证50ETF",
 "511090": "30年国债ETF"
}

# 示例2：跨境/商品组合（如需测试可替换上方）
# ETF_POOL = {
# "159915": "创业板ETF",
# "162411": "华宝油气",
# "513100": "纳指ETF"
# }

START_DATE = "20220101" # 回测起始日期 (AKShare 参数)
END_DATE = "20501231" # 结束日期，设未来以保证取到最新数据
WINDOW = 22 # 动量计算窗口（交易日）
INIT_CASH = 1.0 # 初始资金净值
COST_RATE = 0.0003 # 单边交易成本（万三）

# ------------------------------
# 2. 获取真实 ETF 日线数据
# ------------------------------
print("正在从 AKShare 获取数据，请稍候...")
dfs = []
etf_codes = list(ETF_POOL.keys()) # 按顺序 ['A','B','C']
for code in etf_codes:
 name = ETF_POOL[code]
 try:
 df_etf = ak.fund_etf_hist_em(
 symbol=code,
 period="daily",
 start_date=START_DATE,
 end_date=END_DATE,
 adjust="qfq" # 前复权，避免分红拆分导致价格断崖
 )
 # 只保留日期、开盘、收盘
 df_etf = df_etf[['日期', '开盘', '收盘']].copy()
 df_etf['日期'] = pd.to_datetime(df_etf['日期'])
 df_etf.rename(columns={'开盘': f'open_{code}', '收盘': f'close_{code}'}, inplace=True)
 df_etf.set_index('日期', inplace=True)
 dfs.append(df_etf)
 print(f" {name}({code}) 数据获取成功，共 {len(df_etf)} 条记录")
 except Exception as e:
 print(f" {name}({code}) 获取失败：{e}")

# 合并所有ETF数据，并丢弃缺失值
if len(dfs) != len(etf_codes):
 raise RuntimeError("部分 ETF 数据获取失败，请检查网络或代码是否正确")
df = pd.concat(dfs, axis=1).dropna()
print(f"合并后有效数据量: {df.shape[0]} 行, 列: {list(df.columns)}")

# 为适配原有策略代码，将三个ETF的列重命名为 A/B/C
# 顺序与 ETF_POOL 一致
df.rename(columns={
 f'open_{etf_codes[0]}': 'open_A', f'close_{etf_codes[0]}': 'close_A',
 f'open_{etf_codes[1]}': 'open_B', f'close_{etf_codes[1]}': 'close_B',
 f'open_{etf_codes[2]}': 'open_C', f'close_{etf_codes[2]}': 'close_C'
}, inplace=True)

# 显示数据概况
print("\n数据尾部预览：")
print(df.tail(3))

# ------------------------------
# 3. 计算动量信号（基于收盘价）
# ------------------------------
for col in ['close_A', 'close_B', 'close_C']:
 df[f'mom_{col}'] = df[col] / df[col].shift(WINDOW) - 1

# 每天最强涨幅的ETF索引 (0:A, 1:B, 2:C)
df['best_idx'] = np.argmax(df[['mom_close_A', 'mom_close_B', 'mom_close_C']].values, axis=1)
df['best_mom'] = np.max(df[['mom_close_A', 'mom_close_B', 'mom_close_C']].values, axis=1)

# 构造信号：如果最强涨幅 ≤ 0，则空仓（-1），否则持有最强ETF
df['signal'] = df['best_idx']
df.loc[df['best_mom'] <= 0, 'signal'] = -1

# 信号滞后一天：今天收盘的判断，在下一个交易日执行
df['trade_signal'] = df['signal'].shift(1)

# ------------------------------
# 4. 回测主循环
# ------------------------------
positions = pd.DataFrame(index=df.index, columns=['A', 'B', 'C', 'cash'], data=0.0)
net_value = pd.Series(0.0, index=df.index, dtype=float)
net_value.iloc[0] = INIT_CASH

current_pos = {'A': 0, 'B': 0, 'C': 0, 'cash': INIT_CASH}

for i in range(1, len(df)):
 today = df.index[i]
 signal_today = df.loc[today, 'trade_signal'] # 今日开盘要执行的信号

 # ---------- 平仓：按今日开盘价清空所有持仓 ----------
 cash = current_pos['cash']
 for asset in ['A', 'B', 'C']:
 shares = current_pos[asset]
 if shares > 0:
 cash += shares * df.loc[today, f'open_{asset}'] * (1 - COST_RATE)
 current_pos[asset] = 0

 # ---------- 开仓：全仓买入信号指向的ETF ----------
 if signal_today == 0:
 shares = cash / df.loc[today, 'open_A']
 cash_after = cash - shares * df.loc[today, 'open_A'] * (1 + COST_RATE)
 current_pos['A'] = shares
 current_pos['cash'] = cash_after
 elif signal_today == 1:
 shares = cash / df.loc[today, 'open_B']
 cash_after = cash - shares * df.loc[today, 'open_B'] * (1 + COST_RATE)
 current_pos['B'] = shares
 current_pos['cash'] = cash_after
 elif signal_today == 2:
 shares = cash / df.loc[today, 'open_C']
 cash_after = cash - shares * df.loc[today, 'open_C'] * (1 + COST_RATE)
 current_pos['C'] = shares
 current_pos['cash'] = cash_after
 else: # -1 : 空仓
 current_pos['cash'] = cash

 # 记录每日持仓
 positions.loc[today, 'A'] = current_pos['A']
 positions.loc[today, 'B'] = current_pos['B']
 positions.loc[today, 'C'] = current_pos['C']
 positions.loc[today, 'cash'] = current_pos['cash']

 # 按当日收盘价计算总资产
 total_value = current_pos['cash']
 total_value += current_pos['A'] * df.loc[today, 'close_A']
 total_value += current_pos['B'] * df.loc[today, 'close_B']
 total_value += current_pos['C'] * df.loc[today, 'close_C']
 net_value[today] = total_value

# 补齐第一天净值
net_value.iloc[0] = INIT_CASH

# ------------------------------
# 5. 计算并显示业绩指标
# ------------------------------
# 基准：等权买入并持有
benchmark = (df['close_A'] / df['close_A'].iloc[0] +
 df['close_B'] / df['close_B'].iloc[0] +
 df['close_C'] / df['close_C'].iloc[0]) / 3

total_return = net_value.iloc[-1] / INIT_CASH - 1
years = (net_value.index[-1] - net_value.index[0]).days / 365.25
ann_return = (1 + total_return) ** (1 / years) - 1
ret = net_value.pct_change().dropna()
max_drawdown = (net_value / net_value.cummax() - 1).min()
sharpe = (ret.mean() / ret.std()) * np.sqrt(252) if ret.std() != 0 else 0

print("\n===== 策略业绩 =====")
print(f"总收益率: {total_return:.2%}")
print(f"年化收益率: {ann_return:.2%}")
print(f"最大回撤: {max_drawdown:.2%}")
print(f"夏普比率: {sharpe:.2f}")
print(f"总交易日数: {len(df)}")
switches = (df['trade_signal'] != df['trade_signal'].shift(1)).sum()
print(f"调仓次数: {switches}")

# ------------------------------
# 6. 绘制净值曲线
# ------------------------------
plt.figure(figsize=(12, 6))
plt.plot(net_value.index, net_value.values, label='策略净值', linewidth=1.5)
plt.plot(df.index, benchmark, label='等权持有基准', linewidth=1, alpha=0.7)
plt.title('ETF动量轮动策略 (22日窗口)', fontsize=14)
plt.legend()
plt.grid(True, alpha=0.3)
plt.ylabel('净值')
plt.xticks(rotation=30)
plt.tight_layout()
plt.show()
