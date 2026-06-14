# -*- coding: utf-8 -*-
"""
Whale Tracker · 链上监控引擎
轮询 EVM 链 + Tron，检测大额转账
"""

import requests
import hashlib
from datetime import datetime, timedelta
from config import (
    CHAINS, STABLECOIN_CONTRACTS, MIN_USD_VALUE,
    ETHERSCAN_API_KEY, BSCSCAN_API_KEY, TRONGRID_API_KEY,
)
from models import (
    get_all_active_wallets, was_tx_pushed, save_tx_history,
)


def tx_fingerprint(tx_hash: str, from_addr: str, to_addr: str, token: str, amount: str) -> str:
    """交易唯一指纹（防重复推送）"""
    raw = f"{tx_hash}{from_addr}{to_addr}{token}{amount}"
    return hashlib.md5(raw.encode()).hexdigest()


def fetch_evm_transfers(chain_key: str, tracked_addresses: list) -> list:
    """
    拉取 EVM 链的大额转账。
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

                        # 粗略估值：稳定币 1:1，其他代币暂不估
                        usd_value = amount if token_symbol in ("USDT", "USDC", "USDT.e") else 0
                        if usd_value < MIN_USD_VALUE:
                            continue

                        tx_hash = tx.get("hash", "")
                        if was_tx_pushed(tx_hash, chain_key, user_id):
                            continue

                        timestamp = int(tx.get("timeStamp", "0"))
                        tx_time = datetime.fromtimestamp(timestamp)
                        if tx_time < datetime.now() - timedelta(hours=1):
                            continue  # 只推送最近1小时内的

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
    拉取 EVM 链的 Native 代币（ETH/BNB）转账
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

                        # ETH: 粗略按 $2000 估算, BNB: 按 $300 估算
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
    拉取 Tron 链的 USDT 转账
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
                    amount = raw_value / 1e6  # USDT = 6 decimals

                    usd_value = amount
                    if usd_value < MIN_USD_VALUE:
                        continue

                    tx_id = tx.get("transaction_id", "")
                    if was_tx_pushed(tx_id, "tron", user_id):
                        continue

                    # Tron unix timestamp in ms
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


def scan_all_chains() -> list:
    """
    扫描所有链，返回所有新的大额转账。
    按链分组合并追踪地址以优化 API 调用。
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
            # Token transfers
            all_results.extend(fetch_evm_transfers(chain_key, addresses))
            # Native transfers
            all_results.extend(fetch_evm_native_transfers(chain_key, addresses))
        elif chain_key == "tron":
            all_results.extend(fetch_tron_transfers(addresses))

    return all_results


def format_alert(tx: dict) -> str:
    """格式化推送消息"""
    label_line = f"\n🏷 标签: {tx['label']}" if tx.get("label") else ""

    direction = "📤 转出" if tx["to"].lower() == tx["tracked_address"].lower() else "📥 转入"

    return f"""{tx['chain_emoji']} *鲸鱼异动 · {tx['chain_name']}*

{direction}
💰 {tx['amount']} {tx['token']} (≈${tx['usd_value']})
📬 地址: `{tx['tracked_address'][:10]}...{tx['tracked_address'][-6:]}`{label_line}

🔗 [查看交易]({tx['explorer']})
⏰ {tx['timestamp'][:19]}"""


# ============================================================
# 测试
# ============================================================
if __name__ == "__main__":
    from models import init_db
    init_db()

    print("=" * 50)
    print("Whale Tracker · 链上监控测试")
    print("=" * 50)

    results = scan_all_chains()
    print(f"\n发现 {len(results)} 笔新的大额转账:")
    for tx in results:
        print(format_alert(tx))
        print("-" * 40)