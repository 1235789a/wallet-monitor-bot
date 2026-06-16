# -*- coding: utf-8 -*-
"""
Whale Tracker + Smart Money Scanner · 链上监控引擎 v2
- 原有：轮询 EVM 链 + Tron，检测用户追踪地址的大额转账
- 新增：扫描聪明钱地址的交易→送给 AlphaAggregator 生成代币热度
"""

import requests
import hashlib
from datetime import datetime, timedelta
from config import (
    CHAINS, STABLECOIN_CONTRACTS, MIN_USD_VALUE,
    ETHERSCAN_API_KEY, BSCSCAN_API_KEY, TRONGRID_API_KEY,
    SMART_MONEY_CHAINS, SMART_USD_THRESHOLD,
)
from models import (
    get_all_active_wallets, was_tx_pushed, save_tx_history,
    get_all_smart_wallets, get_smart_wallet,
    update_smart_wallet_score, upsert_token_heat,
)
from alpha import AlphaAggregator
from scorer import estimate_score_from_onchain


def tx_fingerprint(tx_hash: str, from_addr: str, to_addr: str, token: str, amount: str) -> str:
    """交易唯一指纹（防重复推送）"""
    raw = f"{tx_hash}{from_addr}{to_addr}{token}{amount}"
    return hashlib.md5(raw.encode()).hexdigest()


# ====================================================================
# 原有：用户追踪地址的鲸鱼监控
# ====================================================================

def fetch_evm_transfers(chain_key: str, tracked_addresses: list) -> list:
    """
    拉取 EVM 链的大额转账（用户追踪的地址）。
    tracked_addresses: [(address, user_id, label), ...]
    返回: [tx_dict, ...]
    """
    chain = CHAINS.get(chain_key)
    if not chain:
        return []

    api_key = ETHERSCAN_API_KEY if chain_key == "ethereum" else BSCSCAN_API_KEY
    if not api_key:
        return []

    results = []

    for addr, user_id, label in tracked_addresses:
        params = {
            "module": "account",
            "action": "tokentx",
            "address": addr,
            "startblock": 0,
            "endblock": 99999999,
            "sort": "desc",
            "apikey": api_key,
        }
        try:
            resp = requests.get(chain["api_url"], params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "1":
                    for tx in data.get("result", []):
                        raw_value = tx.get("value", "0")
                        decimals = int(tx.get("tokenDecimal", "18"))
                        amount = float(raw_value) / (10 ** decimals)

                        token_symbol = tx.get("tokenSymbol", "UNKNOWN")

                        usd_value = amount if token_symbol in ("USDT", "USDC", "USDT.e") else 0
                        if usd_value < MIN_USD_VALUE:
                            continue

                        tx_hash = tx.get("hash", "")
                        if was_tx_pushed(tx_hash, chain_key, user_id):
                            continue

                        timestamp = int(tx.get("timeStamp", "0"))
                        tx_time = datetime.fromtimestamp(timestamp)
                        if tx_time < datetime.now() - timedelta(hours=1):
                            continue

                        results.append({
                            "tx_hash": tx_hash,
                            "from": tx["from"],
                            "to": tx["to"],
                            "token": token_symbol,
                            "amount": str(round(amount, 4)),
                            "usd_value": str(round(usd_value, 2)),
                            "chain": chain_key,
                            "chain_name": chain["name"],
                            "chain_emoji": chain["emoji"],
                            "explorer": f"{chain['explorer']}/tx/{tx_hash}",
                            "timestamp": tx_time.isoformat(),
                            "user_id": user_id,
                            "tracked_address": addr,
                            "label": label or "",
                        })
        except Exception as e:
            print(f"  EVM fetch error ({chain_key}, {addr[:10]}...): {e}")

    return results


def fetch_evm_native_transfers(chain_key: str, tracked_addresses: list) -> list:
    """
    拉取 EVM 链的 Native 代币（ETH/BNB）转账（用户追踪的地址）
    """
    chain = CHAINS.get(chain_key)
    if not chain:
        return []

    api_key = ETHERSCAN_API_KEY if chain_key == "ethereum" else BSCSCAN_API_KEY
    if not api_key:
        return []

    results = []

    for addr, user_id, label in tracked_addresses:
        params = {
            "module": "account",
            "action": "txlist",
            "address": addr,
            "startblock": 0,
            "endblock": 99999999,
            "sort": "desc",
            "apikey": api_key,
        }
        try:
            resp = requests.get(chain["api_url"], params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "1":
                    for tx in data.get("result", []):
                        raw_value = tx.get("value", "0")
                        amount = float(raw_value) / 1e18

                        eth_price = 2000 if chain_key == "ethereum" else 300
                        usd_value = amount * eth_price
                        if usd_value < MIN_USD_VALUE:
                            continue

                        tx_hash = tx.get("hash", "")
                        if was_tx_pushed(tx_hash, chain_key, user_id):
                            continue

                        timestamp = int(tx.get("timeStamp", "0"))
                        tx_time = datetime.fromtimestamp(timestamp)
                        if tx_time < datetime.now() - timedelta(hours=1):
                            continue

                        results.append({
                            "tx_hash": tx_hash,
                            "from": tx["from"],
                            "to": tx["to"],
                            "token": chain["native_symbol"],
                            "amount": str(round(amount, 4)),
                            "usd_value": str(round(usd_value, 2)),
                            "chain": chain_key,
                            "chain_name": chain["name"],
                            "chain_emoji": chain["emoji"],
                            "explorer": f"{chain['explorer']}/tx/{tx_hash}",
                            "timestamp": tx_time.isoformat(),
                            "user_id": user_id,
                            "tracked_address": addr,
                            "label": label or "",
                        })
        except Exception as e:
            print(f"  EVM native fetch error ({chain_key}, {addr[:10]}...): {e}")

    return results


def fetch_tron_transfers(tracked_addresses: list) -> list:
    """
    拉取 Tron 链的 USDT 转账（用户追踪的地址）
    """
    chain = CHAINS.get("tron")
    if not chain:
        return []

    api_key = TRONGRID_API_KEY
    headers = {"TRON-PRO-API-KEY": api_key} if api_key else {}

    trc20_contracts = STABLECOIN_CONTRACTS.get("tron", [])

    results = []

    for addr, user_id, label in tracked_addresses:
        for contract_addr in trc20_contracts:
            params = {
                "limit": 50,
                "contract_address": contract_addr,
            }
            try:
                url = f"{chain['api_base']}/v1/accounts/{addr}/transactions/trc20"
                resp = requests.get(url, params=params, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                for tx in data.get("data", []):
                    raw_value = int(tx.get("value", "0"))
                    amount = raw_value / 1e6

                    usd_value = amount
                    if usd_value < MIN_USD_VALUE:
                        continue

                    tx_id = tx.get("transaction_id", "")
                    if was_tx_pushed(tx_id, "tron", user_id):
                        continue

                    tx_ts = int(tx.get("block_timestamp", "0"))
                    tx_time = datetime.fromtimestamp(tx_ts / 1000)
                    if tx_time < datetime.now() - timedelta(hours=1):
                        continue

                    token = "USDT"
                    results.append({
                        "tx_hash": tx_id,
                        "from": tx.get("from", ""),
                        "to": tx.get("to", ""),
                        "token": token,
                        "amount": str(round(amount, 4)),
                        "usd_value": str(round(usd_value, 2)),
                        "chain": "tron",
                        "chain_name": chain["name"],
                        "chain_emoji": chain["emoji"],
                        "explorer": f"{chain['explorer']}/#/transaction/{tx_id}",
                        "timestamp": tx_time.isoformat(),
                        "user_id": user_id,
                        "tracked_address": addr,
                        "label": label or "",
                    })
            except Exception as e:
                print(f"  Tron fetch error ({addr[:10]}...): {e}")

    return results


# ====================================================================
# 新增：聪明钱地址扫描 → Alpha Detection
# ====================================================================

def fetch_smart_money_evm(chain_key: str, smart_addresses: list) -> list:
    """
    拉取聪明钱地址的近期交易（用于代币热度分析）

    smart_addresses: [(wallet_address, nickname, category), ...]
    返回: [tx_dict, ...] 原始交易数据，交给 AlphaAggregator 处理
    """
    chain = CHAINS.get(chain_key)
    if not chain:
        return []

    api_key = ETHERSCAN_API_KEY if chain_key == "ethereum" else BSCSCAN_API_KEY
    if not api_key:
        return []

    results = []

    for addr, nickname, category in smart_addresses:
        params = {
            "module": "account",
            "action": "tokentx",
            "address": addr,
            "startblock": 0,
            "endblock": 99999999,
            "sort": "desc",
            "offset": 50,  # 只取最近50笔
            "apikey": api_key,
        }
        try:
            resp = requests.get(chain["api_url"], params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "1":
                    for tx in data.get("result", []):
                        raw_value = tx.get("value", "0")
                        decimals = int(tx.get("tokenDecimal", "18"))
                        amount = float(raw_value) / (10 ** decimals)

                        token_symbol = tx.get("tokenSymbol", "UNKNOWN")
                        token_name = tx.get("tokenName", token_symbol)

                        # 稳定币估值 1:1，其他估算或忽略
                        if token_symbol in ("USDT", "USDC", "USDT.e", "BUSD"):
                            usd_value = amount
                        else:
                            # 非稳定币暂用0（实际应接入价格API）
                            usd_value = amount * 0.01  # 粗略估计

                        if usd_value < SMART_USD_THRESHOLD:
                            continue

                        timestamp = int(tx.get("timeStamp", "0"))
                        tx_time = datetime.fromtimestamp(timestamp)
                        if tx_time < datetime.now() - timedelta(hours=24):
                            continue

                        contract_address = tx.get("contractAddress", "")
                        from_addr = tx.get("from", "").lower()
                        addr_lower = addr.lower()

                        direction = "buy"  # 粗略判断：转出=卖，转入=买
                        if from_addr == addr_lower:
                            direction = "sell"
                        elif tx.get("to", "").lower() == addr_lower:
                            direction = "buy"

                        results.append({
                            "tx_hash": tx.get("hash", ""),
                            "from": tx["from"],
                            "to": tx["to"],
                            "token": token_symbol,
                            "token_name": token_name,
                            "token_address": contract_address,
                            "amount": str(round(amount, 4)),
                            "usd_value": str(round(usd_value, 2)),
                            "chain": chain_key,
                            "chain_name": chain["name"],
                            "chain_emoji": chain["emoji"],
                            "explorer": f"{chain['explorer']}/tx/{tx.get('hash', '')}",
                            "timestamp": tx_time.isoformat(),
                            "direction": direction,
                            "wallet_address": addr,
                            "wallet_nickname": nickname,
                            "wallet_category": category,
                            "source": "smart_money",
                        })
        except Exception as e:
            print(f"  Smart EVM fetch error ({chain_key}, {addr[:10]}...): {e}")

    return results


def fetch_smart_money_tron(smart_addresses: list) -> list:
    """
    拉取聪明钱地址在 Tron 上的 USDT 交易
    """
    chain = CHAINS.get("tron")
    if not chain:
        return []

    api_key = TRONGRID_API_KEY
    headers = {"TRON-PRO-API-KEY": api_key} if api_key else {}
    trc20_contracts = STABLECOIN_CONTRACTS.get("tron", [])

    results = []

    for addr, nickname, category in smart_addresses:
        for contract_addr in trc20_contracts:
            params = {
                "limit": 50,
                "contract_address": contract_addr,
            }
            try:
                url = f"{chain['api_base']}/v1/accounts/{addr}/transactions/trc20"
                resp = requests.get(url, params=params, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                for tx in data.get("data", []):
                    raw_value = int(tx.get("value", "0"))
                    amount = raw_value / 1e6

                    usd_value = amount
                    if usd_value < SMART_USD_THRESHOLD:
                        continue

                    tx_ts = int(tx.get("block_timestamp", "0"))
                    tx_time = datetime.fromtimestamp(tx_ts / 1000)
                    if tx_time < datetime.now() - timedelta(hours=24):
                        continue

                    from_addr = tx.get("from", "").lower()
                    addr_lower = addr.lower()

                    direction = "sell" if from_addr == addr_lower else "buy"

                    results.append({
                        "tx_hash": tx.get("transaction_id", ""),
                        "from": tx.get("from", ""),
                        "to": tx.get("to", ""),
                        "token": "USDT",
                        "token_name": "Tether USD",
                        "token_address": contract_addr,
                        "amount": str(round(amount, 4)),
                        "usd_value": str(round(usd_value, 2)),
                        "chain": "tron",
                        "chain_name": chain["name"],
                        "chain_emoji": chain["emoji"],
                        "explorer": f"{chain['explorer']}/#/transaction/{tx.get('transaction_id', '')}",
                        "timestamp": tx_time.isoformat(),
                        "direction": direction,
                        "wallet_address": addr,
                        "wallet_nickname": nickname,
                        "wallet_category": category,
                        "source": "smart_money",
                    })
            except Exception as e:
                print(f"  Smart Tron fetch error ({addr[:10]}...): {e}")

    return results


def scan_smart_money() -> dict:
    """
    扫描所有聪明钱地址，聚合信号到 AlphaAggregator

    返回: {
        "aggr": AlphaAggregator 实例,
        "txs": 所有聪明钱交易列表,
        "smart_tx_count": 聪明钱交易总数,
    }
    """
    smart_wallets = get_all_smart_wallets()
    if not smart_wallets:
        print("  No smart wallets found.")
        return {"aggr": None, "txs": [], "smart_tx_count": 0}

    # 按链分组
    by_chain = {}
    for w in smart_wallets:
        chain = w["chain"]
        if chain not in by_chain:
            by_chain[chain] = []
        by_chain[chain].append(
            (w["address"], w["nickname"], w["category"])
        )

    all_txs = []

    for chain_key, addresses in by_chain.items():
        if chain_key not in SMART_MONEY_CHAINS:
            continue

        print(f"  Scanning smart money on {chain_key}: {len(addresses)} wallets")
        if chain_key in ("ethereum", "bsc"):
            all_txs.extend(fetch_smart_money_evm(chain_key, addresses))
        elif chain_key == "tron":
            all_txs.extend(fetch_smart_money_tron(addresses))

    # 路由到 AlphaAggregator
    aggr = AlphaAggregator()
    for tx in all_txs:
        aggr.add_tx(
            chain=tx["chain"],
            token_address=tx["token_address"],
            token_symbol=tx["token"],
            token_name=tx.get("token_name", ""),
            direction=tx["direction"],
            usd_value=float(tx["usd_value"]),
            wallet_info=f"{tx['wallet_category']} {tx['wallet_nickname']}",
        )

    # 写入数据库
    aggr.flush_to_db()

    return {
        "aggr": aggr,
        "txs": all_txs,
        "smart_tx_count": len(all_txs),
    }


# ====================================================================
# 原有：用户追踪地址的聚合扫描
# ====================================================================

def scan_all_chains() -> list:
    """
    扫描所有链（用户追踪的地址），返回所有新的大额转账。
    """
    all_wallets = get_all_active_wallets()

    if not all_wallets:
        return []

    # 按链分组
    by_chain = {}
    for w in all_wallets:
        chain = w["chain"]
        if chain not in by_chain:
            by_chain[chain] = []
        by_chain[chain].append(
            (w["address"], w["owner_user_id"], w.get("label", ""))
        )

    all_results = []

    for chain_key, addresses in by_chain.items():
        if chain_key in ("ethereum", "bsc"):
            all_results.extend(fetch_evm_transfers(chain_key, addresses))
            all_results.extend(fetch_evm_native_transfers(chain_key, addresses))
        elif chain_key == "tron":
            all_results.extend(fetch_tron_transfers(addresses))

    return all_results


# ====================================================================
# 统一信号格式 + Free / Pro 分层
# ====================================================================

def _mask_address(addr: str) -> str:
    """脱敏地址（Free 版只给前 6 位）"""
    if not addr:
        return "0x…"
    return f"{addr[:6]}…"


def _full_address(addr: str) -> str:
    """完整脱敏地址（Pro 版给首尾）"""
    if not addr:
        return "0x…"
    return f"{addr[:10]}...{addr[-6:]}"


def format_signal(tx: dict, kind: str = "whale", tier: str = "paid") -> str:
    """
    统一的信号格式化入口。

    Parameters
    ----------
    tx   : 交易字典
    kind : 'whale'（用户追踪的鲸鱼）或 'smart'（Alpha 聪明钱）
    tier : 'paid' / 'trial' 给完整内容；'free' 给脱敏 + 升级引导
    """
    is_free = tier not in ("paid", "trial")

    # 方向判断（兼容 smart 信号的 direction 与 whale 的转入/转出）
    if tx.get("direction"):
        dir_emoji = "🟢" if tx["direction"] == "buy" else "🔴"
        dir_text = "买入" if tx["direction"] == "buy" else "卖出"
    else:
        tracked = tx.get("tracked_address", "").lower()
        is_out = tx.get("to", "").lower() == tracked
        dir_emoji = "📤" if is_out else "📥"
        dir_text = "转出" if is_out else "转入"

    addr = tx.get("tracked_address") or tx.get("wallet_address", "")

    if kind == "smart":
        title = f"{tx['chain_emoji']} *Alpha 信号 · {dir_emoji} {dir_text}*"
        owner = f"\n🏷 聪明钱: {tx.get('wallet_category', '')} {tx.get('wallet_nickname', '')}"
    else:
        title = f"{tx['chain_emoji']} *鲸鱼异动 · {tx['chain_name']}*"
        owner = f"\n🏷 标签: {tx['label']}" if tx.get("label") else ""

    if is_free:
        # Free：金额按量级模糊化，地址脱敏，去掉交易链接，附升级引导
        try:
            usd = float(tx.get("usd_value", 0))
        except (TypeError, ValueError):
            usd = 0.0
        if usd >= 1_000_000:
            amount_line = "💰 金额量级: 🐋🐋🐋 百万美元级"
        elif usd >= 100_000:
            amount_line = "💰 金额量级: 🐋🐋 十万美元级"
        else:
            amount_line = "💰 金额量级: 🐋 万美元级"
        return (
            f"{title}\n\n"
            f"{dir_emoji} {dir_text}{owner}\n"
            f"{amount_line}\n"
            f"📬 地址: `{_mask_address(addr)}`\n"
            f"⏰ {tx['timestamp'][:19]}\n\n"
            f"🔒 _完整金额 / 地址 / 交易链接为 Pro 专享_\n"
            f"💎 升级 Pro 解锁实时全量信号 → /pay"
        )

    # Paid / Trial：完整内容
    return (
        f"{title}\n\n"
        f"{dir_emoji} {dir_text}{owner}\n"
        f"💰 {tx['amount']} {tx['token']} (≈${tx['usd_value']})\n"
        f"📬 地址: `{_full_address(addr)}`\n\n"
        f"🔗 [查看交易]({tx['explorer']})\n"
        f"⏰ {tx['timestamp'][:19]}"
    )


def format_alert(tx: dict, tier: str = "paid") -> str:
    """格式化鲸鱼异动推送（向后兼容封装）"""
    return format_signal(tx, kind="whale", tier=tier)


def format_smart_alert(tx: dict, tier: str = "paid") -> str:
    """格式化 Alpha 聪明钱信号推送（向后兼容封装）"""
    return format_signal(tx, kind="smart", tier=tier)



# ============================================================
# 测试
# ============================================================
if __name__ == "__main__":
    from models import init_db, get_conn
    from seed_wallets import seed_database

    init_db()

    # 播种聪明钱包
    conn = get_conn()
    imported, skipped = seed_database(conn)
    conn.close()
    if imported:
        print(f"Seed wallets: {imported} imported ({skipped} skipped)")

    print("=" * 50)
    print("Whale Tracker + Smart Money Scanner · 测试")
    print("=" * 50)

    # 1. 原有鲸鱼追踪
    print("\n--- 用户追踪的鲸鱼地址 ---")
    results = scan_all_chains()
    print(f"发现 {len(results)} 笔新的大额转账:")
    for tx in results:
        print(format_alert(tx))
        print("-" * 40)

    # 2. 聪明钱扫描
    print("\n--- 聪明钱 Alpha 扫描 ---")
    smart_result = scan_smart_money()
    print(f"发现 {smart_result['smart_tx_count']} 笔聪明钱交易")

    if smart_result.get("aggr"):
        digest = smart_result["aggr"].generate_digest()
        print("\n" + digest["message"])