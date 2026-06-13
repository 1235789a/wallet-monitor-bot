#!/usr/bin/env python3
"""
钱包地址 Token 到账监控 - 核心脚本
由 GitHub Actions 每 30 分钟自动执行
支持: Ethereum, BSC, Tron(TRC20)
检测指定钱包地址的 Token 到账，发现新到账时通过 Telegram 推送通知
"""

import json
import os
import time
import hashlib
import requests
from datetime import datetime, timezone

# ============================================================
# 配置 - 从 GitHub Secrets 读取
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
BSCSCAN_API_KEY = os.environ.get("BSCSCAN_API_KEY", "")
# TronGrid 免费，无需 API Key，但可用 Secret 传自定义 key 提高限额
TRONGRID_API_KEY = os.environ.get("TRONGRID_API_KEY", "")

# 波场 USDT 合约地址
USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

# 链配置
CHAINS = {
    "ethereum": {
        "name": "Ethereum",
        "emoji": "🔷",
        "type": "evm",
        "api_url": "https://api.etherscan.io/api",
        "api_key": ETHERSCAN_API_KEY,
        "explorer": "https://etherscan.io",
    },
    "bsc": {
        "name": "BSC",
        "emoji": "🟡",
        "type": "evm",
        "api_url": "https://api.bscscan.com/api",
        "api_key": BSCSCAN_API_KEY,
        "explorer": "https://bscscan.com",
    },
    "tron": {
        "name": "Tron",
        "emoji": "🔴",
        "type": "tron",
        "api_base": "https://api.trongrid.io",
        "api_key": TRONGRID_API_KEY,
        "explorer": "https://tronscan.org",
    },
}

STATE_FILE = "last_state.json"
WALLETS_FILE = "wallets.json"

# 每笔转账的唯一指纹（防重复通知）
EVENT_FINGERPRINT = lambda tx_data: hashlib.md5(
    f"{tx_data['hash']}{tx_data['from']}{tx_data['to']}{tx_data['tokenSymbol']}{tx_data['value']}".encode()
).hexdigest()


def send_telegram(message: str):
    """通过 Telegram Bot 发送消息"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        if not resp.ok:
            print(f"Telegram send failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Telegram error: {e}")


def load_json(path: str, default=None):
    """安全加载 JSON 文件"""
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: str, data):
    """保存 JSON 文件"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================
# EVM 链 (Ethereum / BSC) - 通过 Etherscan/BSCScan API
# ============================================================
def fetch_evm_transfers(chain: dict, address: str, startblock: int = 0) -> list:
    """获取 EVM 链的 Token 转账（仅收账）"""
    params = {
        "module": "account",
        "action": "tokentx",
        "address": address,
        "startblock": startblock,
        "endblock": 99999999,
        "sort": "desc",
        "apikey": chain["api_key"],
    }

    try:
        resp = requests.get(chain["api_url"], params=params, timeout=15)
        data = resp.json()

        if data["status"] != "1":
            if data.get("message") not in ("No transactions found", "OK"):
                print(f"  API warning ({chain['name']}): {data.get('message')}")
            return []

        transfers = []
        for tx in data["result"]:
            if tx["to"].lower() != address.lower():
                continue

            decimals = int(tx.get("tokenDecimal", "18"))
            raw_value = int(tx["value"])
            value = raw_value / (10 ** decimals)

            transfers.append({
                "hash": tx["hash"],
                "from": tx["from"],
                "to": tx["to"],
                "tokenSymbol": tx.get("tokenSymbol", "UNKNOWN"),
                "tokenName": tx.get("tokenName", "Unknown Token"),
                "value": str(round(value, 4)),
                "timestamp": tx["timeStamp"],
                "chain": chain["name"],
                "chain_emoji": chain["emoji"],
                "explorer_url": f"{chain['explorer']}/tx/{tx['hash']}",
            })
        return transfers

    except Exception as e:
        print(f"  Error fetching {chain['name']} transfers: {e}")
        return []


# ============================================================
# 波场 (Tron) - 通过 TronGrid API
# ============================================================
def fetch_tron_transfers(chain: dict, address: str, contracts: list = None, last_timestamp: int = 0) -> list:
    """
    获取波场 TRC20 转账
    contracts: 要监控的合约地址列表，默认 USDT
    last_timestamp: 上次查询到的最新时间戳(ms)，用于增量查询
    """
    if not contracts:
        contracts = [USDT_TRC20_CONTRACT]

    all_transfers = []

    headers = {}
    if chain.get("api_key"):
        headers["TRON-PRO-API-KEY"] = chain["api_key"]

    for contract_addr in contracts:
        params = {
            "limit": 50,
            "contract_address": contract_addr,
        }
        # TronGrid 支持 min_block_timestamp 过滤
        if last_timestamp > 0:
            params["min_block_timestamp"] = last_timestamp

        try:
            url = f"{chain['api_base']}/v1/accounts/{address}/transactions/trc20"
            resp = requests.get(url, params=params, headers=headers, timeout=15)

            if resp.status_code == 400:
                err = resp.json()
                if "valid account address" in err.get("error", "").lower():
                    print(f"  Invalid Tron address: {address}")
                    return []
                print(f"  TronGrid 400: {resp.text[:200]}")
                return []

            if resp.status_code != 200:
                print(f"  TronGrid error: {resp.status_code} {resp.text[:200]}")
                return []

            data = resp.json()
            txs = data.get("data", [])

            for tx in txs:
                # 只关心收账
                to_addr = tx.get("to", "")
                if to_addr.lower() != address.lower():
                    continue

                token_info = tx.get("token_info", {})
                decimals = int(token_info.get("decimals", 6))
                raw_value = int(tx.get("value", "0"))
                value = raw_value / (10 ** decimals)

                all_transfers.append({
                    "hash": tx.get("transaction_id", ""),
                    "from": tx.get("from", ""),
                    "to": to_addr,
                    "tokenSymbol": token_info.get("symbol", "TRC20"),
                    "tokenName": token_info.get("name", "TRC20 Token"),
                    "value": str(round(value, 4)),
                    "timestamp": str(tx.get("block_timestamp", 0))[:10],  # ms -> seconds
                    "chain": chain["name"],
                    "chain_emoji": chain["emoji"],
                    "explorer_url": f"{chain['explorer']}/#/transaction/{tx.get('transaction_id', '')}",
                })

        except Exception as e:
            print(f"  Error fetching Tron transfers from {contract_addr[:8]}...: {e}")
            continue

    return all_transfers


# ============================================================
# 通用工具
# ============================================================
def format_transfer_msg(tx: dict, address: str) -> str:
    """格式化单笔到账通知消息"""
    ts = int(tx["timestamp"])
    if ts > 10**12:  # 如果是毫秒
        ts = ts // 1000
    time_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    short_addr = f"{address[:6]}...{address[-4:]}"
    is_tron = tx["chain"] == "Tron"

    from_display = tx['from'][:8] + "..."
    if is_tron and tx["explorer_url"]:
        from_link = f"<a href='{tx['explorer_url'].split('/#/')[0]}/#/address/{tx['from']}'>{from_display}</a>"
    elif not is_tron and tx["explorer_url"]:
        from_link = f"<a href='{tx['explorer_url'].split('/tx')[0]}/address/{tx['from']}'>{from_display}</a>"
    else:
        from_link = from_display

    return (
        f"{tx['chain_emoji']} <b>新到账！</b>\n\n"
        f"📬 地址: <code>{short_addr}</code>\n"
        f"💰 数量: <b>{tx['value']} {tx['tokenSymbol']}</b>\n"
        f"🪙 Token: {tx['tokenName']} ({tx['tokenSymbol']})\n"
        f"📤 发送方: {from_link}\n"
        f"⛓️  链: {tx['chain']}\n"
        f"🕐 时间: {time_str}\n"
        f"🔗 <a href='{tx['explorer_url']}'>查看交易</a>"
    )


def main():
    print(f"[{datetime.now().isoformat()}] Wallet Monitor running...")

    wallets = load_json(WALLETS_FILE, {"wallets": []})
    wallet_list = wallets.get("wallets", [])

    if not wallet_list:
        print("  No wallets to monitor. Add entries to wallets.json")
        return

    state = load_json(STATE_FILE, {
        "fingerprints": {},
        "start_blocks": {},
        "tron_last_ts": {},
    })
    known_fingerprints = set(state.get("fingerprints", {}).keys())
    start_blocks = state.get("start_blocks", {})
    tron_last_ts = state.get("tron_last_ts", {})

    all_new_transfers = []
    new_fingerprints = set()

    for entry in wallet_list:
        address = entry.get("address", "").strip()
        chains_to_check = entry.get("chains", ["ethereum"])

        if not address:
            continue

        print(f"  Checking {address}...")

        for chain_key in chains_to_check:
            chain = CHAINS.get(chain_key)
            if not chain:
                print(f"    Unknown chain: {chain_key}")
                continue

            # --- Tron ---
            if chain["type"] == "tron":
                contracts = entry.get("tron_contracts", [USDT_TRC20_CONTRACT])
                last_ts = tron_last_ts.get(address, 0)
                transfers = fetch_tron_transfers(chain, address, contracts, last_ts)

                for tx in transfers:
                    fingerprint = EVENT_FINGERPRINT(tx)
                    if fingerprint not in known_fingerprints and fingerprint not in new_fingerprints:
                        all_new_transfers.append(tx)
                        new_fingerprints.add(fingerprint)

                        if len(all_new_transfers) <= 5:
                            send_telegram(format_transfer_msg(tx, address))
                            time.sleep(0.5)

                # 更新 Tron 时间戳
                if transfers:
                    max_ts = max(int(t.get("timestamp", "0")) for t in transfers)
                    tron_last_ts[address] = max(last_ts, max_ts)
                continue

            # --- EVM (Ethereum / BSC) ---
            if not chain["api_key"]:
                print(f"    Skipping {chain_key}: no API key configured")
                continue

            start_block = start_blocks.get(f"{address}:{chain_key}", 0)
            transfers = fetch_evm_transfers(chain, address, start_block)

            for tx in transfers:
                fingerprint = EVENT_FINGERPRINT(tx)
                if fingerprint not in known_fingerprints and fingerprint not in new_fingerprints:
                    all_new_transfers.append(tx)
                    new_fingerprints.add(fingerprint)

                    if len(all_new_transfers) <= 5:
                        send_telegram(format_transfer_msg(tx, address))
                        time.sleep(0.5)

            # 更新 EVM start_block
            if transfers:
                tx_with_blocks = [t for t in transfers if t.get("hash")]
                if tx_with_blocks:
                    # EVM transfers don't include block in simplified format,
                    # we use the fingerprint approach instead.
                    pass

    # 更新状态文件
    if new_fingerprints:
        for fp in new_fingerprints:
            state["fingerprints"][fp] = datetime.now(timezone.utc).isoformat()

    # 清理旧指纹（保留最近 1000 条）
    if len(state["fingerprints"]) > 1000:
        sorted_fps = sorted(state["fingerprints"].items(), key=lambda x: x[1], reverse=True)
        state["fingerprints"] = dict(sorted_fps[:1000])

    state["start_blocks"] = start_blocks
    state["tron_last_ts"] = tron_last_ts
    save_json(STATE_FILE, state)

    if all_new_transfers:
        print(f"  ✅ Found {len(all_new_transfers)} new transfers, "
              f"sent {min(len(all_new_transfers), 5)} notifications")
    else:
        print("  ⏸️  No new transfers")


if __name__ == "__main__":
    main()