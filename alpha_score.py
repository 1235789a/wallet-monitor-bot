# -*- coding: utf-8 -*-
"""
alpha_score.py · Alpha 信号综合评分引擎

把"哪些聪明钱在买同一个代币"这件事，量化成一个 0-100 的 Alpha Score。
不再只靠 wallet_count，而是综合 5 个维度：

  1. Tier 权重 (tier_weight)   —— 核心聪明钱(T1)的一票 >> 观察池(T3)
  2. 参与地址数 (addr_count)   —— 多少个不同聪明钱共同建仓
  3. 资金体量 (usd_amount)     —— 总买入美元金额（对数压缩）
  4. 买入命中率 (hit_rate)     —— 买入笔数 / (买入+卖出)，越高越是建仓信号
  5. 活跃度 (recency)          —— 信号集中在近 N 小时内 = 更强

最终 Alpha Score = 各维度加权求和后归一化到 0-100。
"""

import math

# Tier → 单地址权重（核心聪明钱一票顶观察池数票）
TIER_WEIGHT = {
    1: 5.0,   # 核心聪明钱（做市商/顶级基金）
    2: 2.5,   # 可信机构 / 知名鲸鱼
    3: 1.0,   # 观察池
}

# 各维度在总分中的占比（合计 = 1.0）
W_TIER = 0.35      # tier 加权地址分
W_COUNT = 0.20     # 参与地址数
W_USD = 0.20       # 资金体量
W_HITRATE = 0.15   # 买入命中率
W_RECENCY = 0.10   # 活跃度


def _normalize(value: float, soft_cap: float) -> float:
    """对数压缩到 0-1，soft_cap 为接近 1.0 的参考量级"""
    if value <= 0:
        return 0.0
    return min(math.log1p(value) / math.log1p(soft_cap), 1.0)


def compute_alpha_score(
    tier_counts: dict,
    buy_count: int,
    sell_count: int,
    total_usd: float,
    recency_hours: float = 24.0,
) -> dict:
    """
    计算单个代币的 Alpha Score。

    Parameters
    ----------
    tier_counts : dict   {1: n1, 2: n2, 3: n3} 各 tier 参与的地址数
    buy_count   : int    买入信号笔数
    sell_count  : int    卖出信号笔数
    total_usd   : float  总买入美元额
    recency_hours : float 信号平均距今小时数（越小越新）

    Returns
    -------
    {"alpha_score": int, "components": {...}}
    """
    addr_count = sum(tier_counts.values())

    # 1. Tier 加权地址分
    weighted = sum(TIER_WEIGHT.get(t, 1.0) * n for t, n in tier_counts.items())
    tier_component = _normalize(weighted, soft_cap=30.0)

    # 2. 参与地址数
    count_component = _normalize(addr_count, soft_cap=15.0)

    # 3. 资金体量
    usd_component = _normalize(total_usd, soft_cap=1_000_000.0)

    # 4. 买入命中率（纯买入=1.0，纯卖出=0.0）
    total_signals = buy_count + sell_count
    hit_rate = (buy_count / total_signals) if total_signals > 0 else 0.0

    # 5. 活跃度（越近越高，48h 内线性衰减）
    recency_component = max(0.0, 1.0 - (recency_hours / 48.0))

    raw = (
        W_TIER * tier_component
        + W_COUNT * count_component
        + W_USD * usd_component
        + W_HITRATE * hit_rate
        + W_RECENCY * recency_component
    )
    alpha_score = round(raw * 100)

    return {
        "alpha_score": max(0, min(100, alpha_score)),
        "components": {
            "tier_weighted": round(weighted, 1),
            "tier_component": round(tier_component, 3),
            "addr_count": addr_count,
            "count_component": round(count_component, 3),
            "total_usd": round(total_usd, 0),
            "usd_component": round(usd_component, 3),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "hit_rate": round(hit_rate, 3),
            "recency_hours": recency_hours,
            "recency_component": round(recency_component, 3),
        },
    }


def signal_strength_label(score: int) -> str:
    """把 Alpha Score 映射为人类可读的信号强度标签"""
    if score >= 80:
        return "🟢 强烈建仓信号"
    if score >= 60:
        return "🟡 明显买入信号"
    if score >= 40:
        return "🟠 温和关注信号"
    if score >= 20:
        return "⚪ 弱信号"
    return "⚫ 噪音"


if __name__ == "__main__":
    # 演示：3 个核心做市商 + 5 个观察池地址共同建仓某代币
    demo = compute_alpha_score(
        tier_counts={1: 3, 2: 2, 3: 5},
        buy_count=10,
        sell_count=1,
        total_usd=850_000,
        recency_hours=6.0,
    )
    print("Alpha Score:", demo["alpha_score"], signal_strength_label(demo["alpha_score"]))
    for k, v in demo["components"].items():
        print(f"  {k}: {v}")
