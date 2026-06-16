# -*- coding: utf-8 -*-
"""
Smart Money Intelligence · 内置聪明钱种子数据 v2（已清洗）

v1 → v2 变更（详见 audit_report.md）：
- 删除 ~80 条占位 / 重复 / 非法 Tron / 合约地址
- 仅保留链上真实存在、来源可追溯的地址
- 每条地址带 tier / source / participate_alpha 三个字段

字段说明
--------
tier              : 1=核心聪明钱  2=可信机构/交易员  3=观察池
source            : 来源可追溯标记（etherscan / eth-labels / user ...）
participate_alpha : 1=参与代币热度Alpha评分  0=仅作资金流向参考（交易所热钱包）

分类 category
-------------
market_maker : 做市商      fund    : 投资基金
whale        : 知名鲸鱼    exchange: 交易所热钱包
trader       : 知名交易员
"""

# ============================================================
# 合约黑名单：代币合约，不是钱包，永久不入池（防热度榜污染）
# ============================================================
CONTRACT_BLACKLIST = {
    "ethereum": [
        "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT 合约
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC 合约
    ],
    "bsc": [
        "0x55d398326f99059ff775485246999027b3197955",  # USDT 合约
        "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",  # USDC 合约
    ],
    "tron": [
        "tr7nhqjekqxgtci8q8zy4pl8otszgjlj6t",          # USDT 合约
    ],
}


def is_blacklisted_contract(address: str, chain: str) -> bool:
    """判断地址是否为已知代币合约（黑名单）"""
    return address.lower() in CONTRACT_BLACKLIST.get(chain, [])


# ============================================================
# 种子地址池 v2（清洗后的真实地址）
# 全部来源于 Etherscan 公开标签 / eth-labels 公共数据集 / 用户提供
# ============================================================
SEED_WALLETS = [
    # ────────────────────────────────────────
    # Tier 1 · 核心聪明钱（链上活跃、标签明确）
    # ────────────────────────────────────────
    {
        "address": "0xdbf5E9c5206d0dB70a90108bf936DA60221dC080",
        "chain": "ethereum",
        "nickname": "Wintermute",
        "category": "market_maker",
        "tier": 1,
        "source": "etherscan",
        "participate_alpha": 1,
    },
    {
        "address": "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B",
        "chain": "ethereum",
        "nickname": "Vitalik Buterin",
        "category": "whale",
        "tier": 1,
        "source": "etherscan",
        "participate_alpha": 1,
    },
    {
        "address": "0x1Db3439a222C519aB44bb1144fC28167b4Fa6EE6",
        "chain": "ethereum",
        "nickname": "Vitalik Buterin 2",
        "category": "whale",
        "tier": 1,
        "source": "etherscan",
        "participate_alpha": 1,
    },
    {
        "address": "0x220866B1A2219f40e72f5c628B65D54268cA3A9D",
        "chain": "ethereum",
        "nickname": "Vitalik Buterin 3",
        "category": "whale",
        "tier": 1,
        "source": "etherscan",
        "participate_alpha": 1,
    },

    # ────────────────────────────────────────
    # Tier 2 · 可信机构 / 早期实体
    # ────────────────────────────────────────
    {
        "address": "0x73BCEb1Cd57C711feaC4224D062b0F6ff338501e",
        "chain": "ethereum",
        "nickname": "Ethereum Foundation (early)",
        "category": "whale",
        "tier": 2,
        "source": "eth-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x8EB8a3b98659Cce290402893d0123abb75E3ab28",
        "chain": "ethereum",
        "nickname": "Avalanche/Known Whale",
        "category": "whale",
        "tier": 2,
        "source": "etherscan",
        "participate_alpha": 1,
    },

    # ────────────────────────────────────────
    # 交易所热钱包 · 仅作资金流向参考，不参与 Alpha 评分
    # ────────────────────────────────────────
    {
        "address": "0x28C6c06298d514Db089934071355E5743bf21d60",
        "chain": "ethereum",
        "nickname": "Binance 14",
        "category": "exchange",
        "tier": 2,
        "source": "etherscan",
        "participate_alpha": 0,
    },
    {
        "address": "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549",
        "chain": "ethereum",
        "nickname": "Binance 15",
        "category": "exchange",
        "tier": 2,
        "source": "etherscan",
        "participate_alpha": 0,
    },
    {
        "address": "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8",
        "chain": "ethereum",
        "nickname": "Binance 7",
        "category": "exchange",
        "tier": 2,
        "source": "etherscan",
        "participate_alpha": 0,
    },

    # ────────────────────────────────────────
    # Tier 3 · 观察池（用户提供，未经交叉验证）
    # ────────────────────────────────────────
    {
        "address": "TAFyvB8GALgHVF6jGUYseEZTc6BjHMjqMc",
        "chain": "tron",
        "nickname": "User Tron Wallet",
        "category": "whale",
        "tier": 3,
        "source": "user",
        "participate_alpha": 1,
    },
]


# ============================================================
# 分类 emoji / 标签映射
# ============================================================
CATEGORY_EMOJI = {
    "market_maker": "🏦",
    "fund": "💰",
    "whale": "🐋",
    "exchange": "🏛️",
    "trader": "🧠",
}

CATEGORY_LABEL = {
    "market_maker": "做市商",
    "fund": "投资基金",
    "whale": "鲸鱼",
    "exchange": "交易所",
    "trader": "聪明交易者",
}

TIER_LABEL = {
    1: "核心聪明钱",
    2: "可信机构/交易员",
    3: "观察池",
}


def seed_database(conn):
    """
    将种子数据导入 smart_wallets 表（带 tier/source/participate_alpha）。
    跳过黑名单合约地址；已存在的地址按更高可信度合并。
    返回 (inserted, skipped)。
    """
    cursor = conn.cursor()
    inserted = 0
    skipped = 0

    for wallet in SEED_WALLETS:
        addr = wallet["address"]
        chain = wallet["chain"]

        # 跳过合约黑名单
        if is_blacklisted_contract(addr, chain):
            skipped += 1
            continue

        # 检查是否已存在
        cursor.execute(
            "SELECT id, tier, source FROM smart_wallets WHERE address = ? AND chain = ?",
            (addr, chain),
        )
        row = cursor.fetchone()

        tier = wallet.get("tier", 3)
        source = wallet.get("source", "unverified")
        participate_alpha = wallet.get("participate_alpha", 1)

        if row:
            # 已存在：tier 取更小(更可信)值，source 非 unverified 时覆盖
            existing_tier = row["tier"] if "tier" in row.keys() and row["tier"] is not None else 3
            existing_source = row["source"] if "source" in row.keys() and row["source"] else "unverified"
            new_tier = min(existing_tier, tier)
            new_source = source if source != "unverified" else existing_source
            cursor.execute(
                """UPDATE smart_wallets
                   SET nickname = ?, category = ?, tier = ?, source = ?, participate_alpha = ?
                   WHERE id = ?""",
                (wallet["nickname"], wallet["category"], new_tier,
                 new_source, participate_alpha, row["id"]),
            )
            skipped += 1
            continue

        cursor.execute(
            """INSERT INTO smart_wallets
               (address, chain, nickname, category, score, tier, source, participate_alpha)
               VALUES (?, ?, ?, ?, 50, ?, ?, ?)""",
            (addr, chain, wallet["nickname"], wallet["category"],
             tier, source, participate_alpha),
        )
        inserted += 1

    conn.commit()
    return inserted, skipped


if __name__ == "__main__":
    from models import get_conn, init_db
    init_db()
    conn = get_conn()
    inserted, skipped = seed_database(conn)
    conn.close()
    print(f"Seed complete: {inserted} inserted, {skipped} skipped (total={len(SEED_WALLETS)})")
