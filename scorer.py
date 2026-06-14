# -*- coding: utf-8 -*-
"""
Smart Money Scorer · 聪明钱评分引擎

评分维度：
1. 交易胜率 (win_rate)           — 获利TX占比
2. 平均回报率 (avg_roi)           — 每笔交易的平均ROI
3. 持仓时间 (hold_time)           — 越短越像聪明钱（短线高手）
4. 大额交易占比 (large_tx_ratio)  — 大额交易多=鲸鱼/机构
5. 活跃度 (activity)              — 最近N天的交易频率
6. 资产多样性 (diversity)         — 交易过多少不同代币
"""

import math
from datetime import datetime, timedelta


def calculate_score(
    win_rate: float = 0.0,
    avg_roi: float = 0.0,
    avg_hold_hours: float = 24.0,
    large_tx_ratio: float = 0.0,
    tx_count_7d: int = 0,
    unique_tokens: int = 1,
) -> int:
    """
    综合评分 (0-100)

    Parameters
    ----------
    win_rate : float  (0.0 ~ 1.0) 交易胜率
    avg_roi : float  (-1.0 ~ ...) 平均ROI，例如0.5表示50%
    avg_hold_hours : float 平均持仓时间（小时）
    large_tx_ratio : float (0.0 ~ 1.0) 大额交易占比
    tx_count_7d : int 近7天交易数
    unique_tokens : int 交易过的不同代币数
    """
    score = 50.0  # 基准分

    # 1. 胜率加权 (最高+20)
    if win_rate > 0:
        score += win_rate * 20

    # 2. ROI加权 (最高+15)
    if avg_roi > 0:
        roi_bonus = min(math.log(1 + avg_roi) * 10, 15)
        score += roi_bonus
    elif avg_roi < 0:
        roi_penalty = min(math.log(1 - avg_roi) * 5, 10)
        score -= roi_penalty

    # 3. 持仓时间加权 (短线加分，最高+10)
    if avg_hold_hours > 0:
        # <240h(10天)秒交易: 短=高分
        hold_score = max(0, 10 - (avg_hold_hours / 24) * 0.5)
        score += min(hold_score, 10)

    # 4. 大额交易占比 (最高+8)
    score += large_tx_ratio * 8

    # 5. 活跃度 (有交易基础分)
    if tx_count_7d >= 20:
        score += 8
    elif tx_count_7d >= 10:
        score += 5
    elif tx_count_7d >= 3:
        score += 2

    # 6. 资产多样性 (交易多个代币=见多识广)
    if unique_tokens >= 10:
        score += 5
    elif unique_tokens >= 5:
        score += 3
    elif unique_tokens >= 3:
        score += 1

    # 惩罚项: 0交易 = 不活跃
    if tx_count_7d == 0:
        score -= 20

    return max(0, min(100, round(score)))


def compute_win_rate(tx_list: list) -> float:
    """
    根据交易列表计算胜率
    tx_list: [{"buy_price": float, "sell_price": float, "sold": bool}, ...]
    """
    if not tx_list:
        return 0.0
    sold = [t for t in tx_list if t.get("sold")]
    if not sold:
        return 0.0
    wins = sum(1 for t in sold if t.get("sell_price", 0) > t.get("buy_price", 0))
    return wins / len(sold)


def compute_avg_roi(tx_list: list) -> float:
    """计算平均ROI"""
    sold = [t for t in tx_list if t.get("sold")]
    if not sold:
        return 0.0
    rois = []
    for t in sold:
        buy = t.get("buy_price", 0)
        if buy > 0:
            rois.append((t.get("sell_price", 0) - buy) / buy)
    return sum(rois) / len(rois) if rois else 0.0


def estimate_score_from_onchain(tx_list: list) -> dict:
    """
    从链上交易记录估算评分
    返回 {"score": int, "details": dict}
    """
    if not tx_list:
        return {"score": 0, "details": {"win_rate": 0, "avg_roi": 0,
                "avg_hold_hours": 0, "large_tx_ratio": 0,
                "tx_count_7d": 0, "unique_tokens": 0}}

    win_rate = compute_win_rate(tx_list)
    avg_roi = compute_avg_roi(tx_list)
    large_tx_ratio = sum(1 for t in tx_list if t.get("usd_value", 0) >= 10000) / max(len(tx_list), 1)
    unique_tokens = len(set(t.get("token", "") for t in tx_list))
    tx_count_7d = len(tx_list)

    # 估算持仓时间（无法精确知道，默认24h）
    avg_hold_hours = 24.0

    score = calculate_score(
        win_rate=win_rate,
        avg_roi=avg_roi,
        avg_hold_hours=avg_hold_hours,
        large_tx_ratio=large_tx_ratio,
        tx_count_7d=tx_count_7d,
        unique_tokens=unique_tokens,
    )

    return {
        "score": score,
        "details": {
            "win_rate": round(win_rate, 3),
            "avg_roi": round(avg_roi, 4),
            "avg_hold_hours": avg_hold_hours,
            "large_tx_ratio": round(large_tx_ratio, 3),
            "tx_count_7d": tx_count_7d,
            "unique_tokens": unique_tokens,
        },
    }


# ============================================================
# 简单测试
# ============================================================
if __name__ == "__main__":
    # 模拟一个高手
    sample_tx = [
        {"buy_price": 100, "sell_price": 150, "sold": True, "usd_value": 50000, "token": "PEPE"},
        {"buy_price": 200, "sell_price": 180, "sold": True, "usd_value": 30000, "token": "WIF"},
        {"buy_price": 50, "sell_price": 80, "sold": True, "usd_value": 20000, "token": "BONK"},
        {"buy_price": 300, "sell_price": 450, "sold": True, "usd_value": 100000, "token": "WIF"},
        {"buy_price": 100, "sell_price": 120, "sold": True, "usd_value": 15000, "token": "SHIB"},
    ]

    result = estimate_score_from_onchain(sample_tx)
    print(f"Score: {result['score']}")
    print(f"Details: {result['details']}")