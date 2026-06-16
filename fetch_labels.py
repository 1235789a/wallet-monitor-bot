# -*- coding: utf-8 -*-
"""
fetch_labels.py · 聪明钱地址自动采集

从公开标签数据集拉取真实链上地址，按 label 自动分类到
category / tier / participate_alpha，输出 wallets_v2.json。

数据源（无需 API Key，raw.githubusercontent 直连）：
  brianleect/etherscan-labels  —— ~30k 个带标签的以太坊地址

用法：
  python fetch_labels.py            # 拉取并生成 wallets_v2.json
  python fetch_labels.py --seed     # 拉取后直接写入数据库
"""

import json
import os
import sys
import urllib.request
from collections import Counter

# ============================================================
# 数据源
# ============================================================
SOURCES = {
    "ethereum": "https://raw.githubusercontent.com/brianleect/etherscan-labels/main/data/etherscan/combined/combinedAllLabels.json",
}

USER_AGENT = "Mozilla/5.0 (wallet-monitor-bot fetch_labels)"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wallets_v2.json")

# ============================================================
# 标签 → 分类映射
# ----------------------------------------------------------
# 每条 (匹配关键词集合) -> (category, tier, participate_alpha)
# tier:               1=核心聪明钱  2=可信机构/交易员  3=观察池
# participate_alpha:  1=参与代币热度Alpha  0=仅作资金流向参考(交易所/桥/合约)
# ============================================================

# 做市商 / 高频交易机构 —— Tier 1，强 Alpha 信号
MARKET_MAKERS = {
    "wintermute", "jump-trading", "jump trading", "gsr", "dwf",
    "amber", "cumberland", "flow-traders", "b2c2", "kronos",
    "galaxy", "genesis", "qcp", "folkvang", "selini", "auros",
    "keyrock", "ledgerprime", "ledger-prime", "pulsar", "tower-research",
    "alphagrep", "wootrade", "woo", "gravity-team",
}

# 知名基金 / VC —— Tier 1
FUNDS = {
    "a16z", "paradigm", "polychain", "pantera", "jump-capital",
    "three-arrows", "alameda", "multicoin", "framework", "dragonfly",
    "spartan", "defiance", "blockchain-capital",
    "sequoia", "coinbase-ventures", "binance-labs", "animoca",
    "delphi", "electric-capital", "1confirmation", "placeholder",
    "variant", "hashed", "nascent", "robot-ventures", "digital-currency-group",
    "grayscale", "jump-crypto", "wintermute-ventures", "consensys",
    "fenbushi", "hashkey", "ldn-firm", "amber-group",
}


# 鲸鱼 / 知名个人 —— Tier 2
WHALES = {
    "vitalik", "whale", "fund", "heavy-dex-trader", "high-value",
}

# 交易所 —— Tier 2，participate_alpha=0（热钱包资金流向，不算建仓信号）
EXCHANGES = {
    "binance", "coinbase", "kraken", "okx", "okex", "bitfinex",
    "huobi", "kucoin", "gate.io", "gate", "bybit", "crypto-com",
    "bitstamp", "gemini", "mexc", "bithumb", "upbit", "exchange",
}

# 永久排除：合约 / 桥 / 协议 / 攻击者 / 团队多签 —— 不入池
EXCLUDE = {
    "token-contract", "contract", "bridge", "router", "factory",
    "proxy", "vault", "pool", "uniswap", "sushiswap", "balancer",
    "curve", "aave", "compound", "maker", "1inch", "0x-protocol",
    "hack", "heist", "exploit", "phish", "scam", "fake", "blocked",
    "ronin-bridge", "wormhole", "multichain", "spam",
}


def _classify(name: str, labels: list) -> tuple | None:
    """
    根据 name + labels 判定 (category, tier, participate_alpha)。
    返回 None 表示该地址应被排除（合约/桥/攻击者等）。
    """
    hay = (name + " " + " ".join(labels)).lower()

    # 1. 永久排除
    for kw in EXCLUDE:
        if kw in hay:
            return None

    # 2. 交易所（participate_alpha=0）
    for kw in EXCHANGES:
        if kw in hay:
            return ("exchange", 2, 0)

    # 3. 做市商（Tier 1）
    for kw in MARKET_MAKERS:
        if kw in hay:
            return ("market_maker", 1, 1)

    # 4. 基金 / VC（Tier 1）
    for kw in FUNDS:
        if kw in hay:
            return ("fund", 1, 1)

    # 5. 鲸鱼 / 知名个人（Tier 2）
    for kw in WHALES:
        if kw in hay:
            return ("whale", 2, 1)

    # 6. 其余带标签地址 → 观察池 Tier 3（交易员）
    return ("trader", 3, 1)


def _is_evm_address(addr: str) -> bool:
    """简单校验 EVM 地址格式"""
    return (
        isinstance(addr, str)
        and addr.startswith("0x")
        and len(addr) == 42
    )


def fetch_chain(chain: str, url: str) -> list:
    """拉取单条链的标签数据并分类"""
    print(f"[fetch] {chain}: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    raw = urllib.request.urlopen(req, timeout=60).read()
    data = json.loads(raw)
    print(f"[fetch] {chain}: {len(data)} raw labeled addresses")

    wallets = []
    excluded = 0
    for addr, info in data.items():
        if not _is_evm_address(addr):
            continue
        name = (info.get("name") or "").strip()
        labels = info.get("labels") or []
        result = _classify(name, labels)
        if result is None:
            excluded += 1
            continue
        category, tier, participate_alpha = result
        wallets.append({
            "address": addr,
            "chain": chain,
            "nickname": name or (labels[0] if labels else "Unknown"),
            "category": category,
            "tier": tier,
            "source": "github:etherscan-labels",
            "participate_alpha": participate_alpha,
        })

    print(f"[fetch] {chain}: kept {len(wallets)}, excluded {excluded}")
    return wallets


def _balance_pool(wallets: list, t1_max=400, t2_max=2000, t3_max=4000) -> list:
    """
    控制各 tier 数量上限，避免 Tier 3 过度膨胀。
    Tier 1/2 全保留（高价值），Tier 3 截断到上限。
    """
    by_tier = {1: [], 2: [], 3: []}
    for w in wallets:
        by_tier[w["tier"]].append(w)

    out = []
    out += by_tier[1][:t1_max]
    out += by_tier[2][:t2_max]
    out += by_tier[3][:t3_max]
    return out


def fetch_all() -> list:
    """拉取所有配置的链，合并去重并平衡数量"""
    all_wallets = []
    seen = set()
    for chain, url in SOURCES.items():
        try:
            chain_wallets = fetch_chain(chain, url)
        except Exception as e:
            print(f"[fetch] {chain} FAILED: {type(e).__name__}: {e}")
            continue
        for w in chain_wallets:
            key = (w["address"].lower(), w["chain"])
            if key in seen:
                continue
            seen.add(key)
            all_wallets.append(w)

    all_wallets = _balance_pool(all_wallets)
    return all_wallets


def write_json(wallets: list, path: str = OUTPUT_FILE) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wallets, f, ensure_ascii=False, indent=2)
    print(f"[write] {len(wallets)} wallets -> {path}")


def _print_summary(wallets: list) -> None:
    tiers = Counter(w["tier"] for w in wallets)
    cats = Counter(w["category"] for w in wallets)
    alpha = sum(1 for w in wallets if w["participate_alpha"] == 1)
    print("=" * 50)
    print(f"总计: {len(wallets)} 个地址")
    print(f"Tier 分布: T1={tiers[1]}  T2={tiers[2]}  T3={tiers[3]}")
    print(f"分类分布: {dict(cats)}")
    print(f"参与 Alpha 评分: {alpha}  (交易所等仅作流向参考: {len(wallets)-alpha})")
    print("=" * 50)


def seed_to_db(wallets: list) -> None:
    """将采集结果写入 smart_wallets 表"""
    from models import init_db, upsert_smart_wallet
    init_db()
    inserted = 0
    updated = 0
    for w in wallets:
        is_new = upsert_smart_wallet(
            address=w["address"],
            chain=w["chain"],
            nickname=w["nickname"],
            category=w["category"],
            tier=w["tier"],
            source=w["source"],
            participate_alpha=w["participate_alpha"],
        )
        if is_new:
            inserted += 1
        else:
            updated += 1
    print(f"[seed] DB: {inserted} inserted, {updated} updated")


if __name__ == "__main__":
    wallets = fetch_all()
    _print_summary(wallets)
    write_json(wallets)
    if "--seed" in sys.argv:
        seed_to_db(wallets)
