
# -*- coding: utf-8 -*-
"""
Alpha Detection · 聪明钱信号聚合器

功能：
1. 统计聪明钱地址在24h内共同买入/卖出的代币→生成热度排行榜
2. 生成每日摘要（日报）
3. 定期更新智能钱包评分
"""

import asyncio
import os
import json
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import (
    init_db, get_all_smart_wallets, get_smart_wallet,
    update_smart_wallet_score, upsert_token_heat,
    get_hot_tokens, save_daily_digest, get_daily_digest,
    mark_digest_pushed, reset_daily_token_heat,
    get_leaderboard, get_alpha_smart_wallets, get_pool_stats,
)
from scorer import estimate_score_from_onchain, calculate_score
from alpha_score import compute_alpha_score, signal_strength_label
from config import (
    SMART_MONEY_CHAINS, SMART_USD_THRESHOLD,
    HEAT_TOP_N, CHAINS,
)
from seed_wallets import seed_database, CATEGORY_EMOJI, CATEGORY_LABEL, TIER_LABEL



# ============================================================
# 交易聚合器
# ============================================================

class AlphaAggregator:
    """
    聚合同类型地址的交易信号，生成代币热度和日报
    """

    def __init__(self):
        self.token_buys = defaultdict(lambda: {
            "address": "",
            "symbol": "",
            "name": "",
            "chain": "",
            "wallet_count": 0,
            "total_usd": 0.0,
            "buyers": [],
            "sellers": [],
            "tier_counts": Counter(),
            "buy_count": 0,
            "sell_count": 0,
            "first_ts": None,
            "last_ts": None,
        })
        self.token_sells = defaultdict(lambda: {
            "wallet_count": 0,
            "total_usd": 0.0,
            "sellers": [],
        })

    def add_tx(self, chain: str, token_address: str, token_symbol: str,
               token_name: str, direction: str, usd_value: float,
               wallet_info: str, tier: int = 3, ts: datetime = None):
        """
        添加一笔聪明钱交易

        Parameters
        ----------
        direction : 'buy' or 'sell'
        wallet_info : 钱包nickname
        tier : 钱包层级 (1=核心聪明钱, 2=可信机构, 3=观察池)
        ts : 交易时间（UTC），用于计算活跃度；缺省取当前时间
        """
        key = f"{chain}:{token_address}"
        ts = ts or datetime.now(timezone.utc)

        # buy/sell 命中率与活跃度统计都挂在 buy entry 上，作为该代币的综合信号
        entry = self.token_buys[key]
        entry["address"] = token_address
        entry["symbol"] = token_symbol
        entry["name"] = token_name
        entry["chain"] = chain
        if entry["first_ts"] is None or ts < entry["first_ts"]:
            entry["first_ts"] = ts
        if entry["last_ts"] is None or ts > entry["last_ts"]:
            entry["last_ts"] = ts

        if direction == "buy":
            entry["wallet_count"] += 1
            entry["total_usd"] += usd_value
            entry["buyers"].append(f"{wallet_info}(${usd_value:,.0f})")
            entry["tier_counts"][tier] += 1
            entry["buy_count"] += 1

        elif direction == "sell":
            entry["sell_count"] += 1
            entry["sellers"].append(f"{wallet_info}(${usd_value:,.0f})")

            sell_entry = self.token_sells[key]
            sell_entry["wallet_count"] += 1
            sell_entry["total_usd"] += usd_value
            sell_entry["sellers"].append(f"{wallet_info}(${usd_value:,.0f})")


    def flush_to_db(self):
        """将缓存数据写入数据库"""
        for key, data in self.token_buys.items():
            chain, address = key.split(":", 1)
            wc = data["wallet_count"]
            tv = data["total_usd"]
            upsert_token_heat(
                chain=chain,
                token_address=address,
                token_symbol=data["symbol"],
                token_name=data["name"],
                wallet_count_inc=wc,
                usd_value_add=tv,
            )

        for key, data in self.token_sells.items():
            chain, address = key.split(":", 1)
            wc = data["wallet_count"]
            tv = data["total_usd"]
            # 卖出也是关注信号（聪明钱离场）
            upsert_token_heat(
                chain=chain,
                token_address=address,
                token_symbol=data.get("symbol", ""),
                token_name=data.get("name", ""),
                wallet_count_inc=wc,
                usd_value_add=tv,
            )

    def generate_digest(self) -> dict:
        """生成每日摘要"""
        hot = get_hot_tokens(limit=HEAT_TOP_N)
        leaderboard = get_leaderboard(limit=10)

        # 按链分组的代币热度
        by_chain = defaultdict(list)
        for t in hot:
            by_chain[t["chain"]].append(t)

        sections = []
        for chain, tokens in by_chain.items():
            chain_info = CHAINS.get(chain, {"emoji": "📊", "name": chain.upper()})
            lines = [f"\n{chain_info['emoji']} {chain_info['name']} 热度榜"]
            for i, t in enumerate(tokens[:5], 1):
                symbol = t["token_symbol"] or "?"
                lines.append(
                    f"  {i}. {symbol} — 🔥{t['heat_score']} "
                    f"| {t['wallet_count']}个聪明钱包参与 | "
                    f"${t['total_usd_value']:,.0f}"
                )
            sections.append("\n".join(lines))

        # 聪明钱排行榜
        lb_lines = ["\n🧠 聪明钱 Top10"]
        for i, w in enumerate(leaderboard, 1):
            cat = w.get("category", "trader")
            emoji = CATEGORY_EMOJI.get(cat, "❓")
            lb_lines.append(
                f"  {i}. {emoji} {w['nickname']} — ⭐{w['score']}"
            )
        sections.append("\n".join(lb_lines))

        # 汇总建议
        top_token = hot[0] if hot else None
        summary_lines = ["\n💡 今日关注"]
        if top_token:
            summary_lines.append(
                f"  🔥 最热代币: {top_token['token_symbol']} "
                f"({top_token['wallet_count']}钱包参与)"
            )
        activity_count = sum(
            t["wallet_count"] for t in hot
        )
        if activity_count > 0:
            summary_lines.append(
                f"  📊 今日总共有 {activity_count} 次聪明钱活动被记录"
            )
        sections.append("\n".join(summary_lines))

        return {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "hot_tokens": [dict(t) for t in hot],
            "leaderboard": [dict(w) for w in leaderboard],
            "total_activity": sum(t["wallet_count"] for t in hot),
            "message": "\n".join(sections),
        }

    def rank_alpha_signals(self) -> list:
        """
        基于本轮缓存的交易，对每个代币计算 Alpha Score 并降序排名。

        Returns
        -------
        list[dict] —— 每个元素含 symbol/chain/alpha_score/label/components
        """
        now = datetime.now(timezone.utc)
        results = []
        for key, data in self.token_buys.items():
            # 平均距今小时数（用 first/last 的中点近似活跃度）
            last_ts = data["last_ts"] or now
            recency_hours = max(0.0, (now - last_ts).total_seconds() / 3600.0)

            scored = compute_alpha_score(
                tier_counts=dict(data["tier_counts"]),
                buy_count=data["buy_count"],
                sell_count=data["sell_count"],
                total_usd=data["total_usd"],
                recency_hours=recency_hours,
            )
            results.append({
                "chain": data["chain"],
                "symbol": data["symbol"],
                "name": data["name"],
                "address": data["address"],
                "alpha_score": scored["alpha_score"],
                "label": signal_strength_label(scored["alpha_score"]),
                "buyers": data["buyers"],
                "sellers": data["sellers"],
                "components": scored["components"],
            })

        results.sort(key=lambda r: r["alpha_score"], reverse=True)
        return results



# ============================================================
# 评分更新
# ============================================================

def update_wallet_scores(tx_data: dict):
    """
    根据最新交易数据更新聪明钱包评分

    tx_data: {wallet_address: [tx_list, ...]}
    每笔tx包含: token, usd_value, direction (buy/sell)
    """
    for address, tx_list in tx_data.items():
        # 简单估算（实际应从链上获取更完整的交易历史）
        result = estimate_score_from_onchain(tx_list)
        chain = tx_list[0].get("chain", "ethereum") if tx_list else "ethereum"
        update_smart_wallet_score(address, chain, result["score"])


# ============================================================
# 每日任务调度
# ============================================================

async def run_daily_digest_task():
    """定时任务：生成并保存每日摘要"""
    print(f"[{datetime.now()}] Running daily digest task...")

    try:
        # 1. 初始化并播种
        init_db()
        from models import get_conn
        conn = get_conn()
        imported, skipped = seed_database(conn)
        conn.close()
        if imported > 0:
            print(f"  Seed wallets: {imported} new imported ({skipped} skipped)")

        # 2. 生成摘要
        aggr = AlphaAggregator()
        # 实际场景中，aggr.flush_to_db() 的数据来自 monitor.py 的实时监控
        digest = aggr.generate_digest()
        date_str = digest["date"]
        save_daily_digest(date_str, digest)
        print(f"  Digest saved for {date_str}")

        # 3. 输出摘要内容
        print(f"  Top tokens: {[(t['token_symbol'], t['heat_score']) for t in digest['hot_tokens'][:5]]}")

    except Exception as e:
        print(f"  Error in daily digest: {e}")


async def run_hourly_heat_reset():
    """重置24小时热度窗（可选，由调度器决定频率）"""
    print(f"[{datetime.now()}] Resetting token heat...")
    reset_daily_token_heat()


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("Alpha Detection · Smart Money Aggregator")
    print("=" * 50)

    # 初始化数据库
    init_db()

    # 播种聪明钱包
    from models import get_conn
    conn = get_conn()
    imported, skipped = seed_database(conn)
    conn.close()
    print(f"Seed wallets: {imported} imported, {skipped} skipped")

    # 演示：模拟一些交易数据
    aggr = AlphaAggregator()

    # 模拟多个聪明钱买入同个代币 —— 末位为 tier (1=核心, 2=机构, 3=观察池)
    sample_trades = [
        ("ethereum", "0xabc001", "PEPE", "Pepe", "buy", 50000, "Wintermute 🏦", 1),
        ("ethereum", "0xabc001", "PEPE", "Pepe", "buy", 30000, "Jump Trading 🏦", 1),
        ("ethereum", "0xabc001", "PEPE", "Pepe", "buy", 25000, "GSR Markets 🏦", 1),
        ("bsc", "0xbsc001", "FLOKI", "Floki", "buy", 15000, "DWF Labs BSC 🏦", 1),
        ("bsc", "0xbsc001", "FLOKI", "Floki", "buy", 12000, "Binance Labs 💰", 1),
        ("ethereum", "0xabc002", "WIF", "dogwifhat", "buy", 80000, "Wintermute 🏦", 1),
        ("ethereum", "0xabc002", "WIF", "dogwifhat", "buy", 45000, "a16z 💰", 1),
        ("ethereum", "0xabc001", "PEPE", "Pepe", "sell", 20000, "Smart Trader 1 🧠", 3),
        ("ethereum", "0xabc003", "BONK", "Bonk", "buy", 60000, "Jump Trading 🏦", 1),
    ]

    for trade in sample_trades:
        chain, addr, sym, name, direction, usd, wallet, tier = trade
        aggr.add_tx(chain, addr, sym, name, direction, usd, wallet, tier=tier)

    # 写入数据库
    aggr.flush_to_db()

    # 生成并显示日报
    digest = aggr.generate_digest()
    print("\n" + digest["message"])

    # Alpha Score 排行
    print("\n" + "=" * 50)
    print("🎯 Alpha Score 信号排行")
    print("=" * 50)
    for r in aggr.rank_alpha_signals():
        c = r["components"]
        print(
            f"  {r['symbol']:<6} [{r['chain']}] "
            f"Alpha={r['alpha_score']:>3}  {r['label']}"
        )
        print(
            f"         tier加权={c['tier_weighted']} | 地址={c['addr_count']} | "
            f"买/卖={c['buy_count']}/{c['sell_count']} | "
            f"命中率={c['hit_rate']} | ${c['total_usd']:,.0f}"
        )

    print("\n✅ Alpha detection test complete.")


