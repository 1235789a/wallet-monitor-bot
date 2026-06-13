#!/usr/bin/env python3
"""
地址代币到账监控 - 核心脚本
由 GitHub Actions 每 5 分钟自动执行
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

# API 端点配置
CHAINS = {
    "ethereum": {
        "name": "Ethereum",
        "emoji": "🔷",
        "api_url": "https://api.etherscan.io/api",
        "api_key": ETHERSCAN_API_KEY,
        "explorer": "https://etherscan.io",
    },
    "bsc": {
        "name": "BSC",
        "emoji": "🟡",
        "api_url": "https://api.bscscan.com/api",
        "api_key": BSCSCAN_API_KEY,
        "explorer": "https://bscscan.com",
    },
}

STATE_FILE = "last_state.json"
WALLETS_FILE = "wallets.json"

# 每笔转账的唯一指纹（防重复通知）
TX_FINGERPRINT = lambda tx: hashlib.md5(
    f"{tx['hash']}{tx['from']}{tx['to']}{tx['tokenSymbol']}{tx['value']}".encode()
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


def fetch_token_transfers(chain: dict, address: str, startblock: int = 0) -> list:
    """
    通过 Etherscan/BSCScan API 获取地址的 Token 转账记录
    返回简化的转账列表
    """
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
            # 可能是 API key 问题或无交易，静默返回
            if data.get("message") not in ("No transactions found", "OK"):
                print(f"  API warning: {data.get('message')}")
            return []

        transfers = []
        for tx in data["result"]:
            # 只关收账（to == 监控地址）
            if tx["to"].lower() != address.lower():
                continue

            # 转换数值（考虑 decimals）
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
                "timeStamp": tx["timeStamp"],
                "chain": chain["name"],
                "chain_emoji": chain["emoji"],
                "explorer_url": f"{chain['explorer']}/tx/{tx['hash']}",
            })

        return transfers

    except Exception as e:
        print(f"  Error fetching {chain['name']} transfers: {e}")
        return []


def format_transfer_msg(tx: dict, address: str) -> str:
    """格式化单笔到账通知消息"""
    time_str = datetime.fromtimestamp(
        int(tx["timeStamp"]), tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S UTC")

    short_addr = f"{address[:6]}...{address[-4:]}"

    return (
        f"{tx['chain_emoji']} <b>新到账！</b>\n\n"
        f"📬 地址: <code>{short_addr}</code>\n"
        f"💰 数量: <b>{tx['value']} {tx['tokenSymbol']}</b>\n"
        f"🪙 Token: {tx['tokenName']} ({tx['tokenSymbol']})\n"
        f"📤 发送方: <a href='{tx['explorer_url'].split('/tx')[0]}/address/{tx['from']}'>{tx['from'][:8]}...</a>\n"
        f"⛓️  链: {tx['chain']}\n"
        f"🕐 时间: {time_str}\n"
        f"🔗 <a href='{tx['explorer_url']}'>查看交易</a>"
    )


def main():
    print(f"[{datetime.now().isoformat()}] Wallet Monitor running...")

    # 加载钱包列表
    wallets = load_json(WALLETS_FILE, {"wallets": []})
    wallet_list = wallets.get("wallets", [])

    if not wallet_list:
        print("  No wallets to monitor. Add entries to wallets.json")
        return

    # 加载上次状态（指纹集合）
    state = load_json(STATE_FILE, {"fingerprints": {}, "start_blocks": {}})
    known_fingerprints = set(state.get("fingerprints", {}).keys())
    start_blocks = state.get("start_blocks", {})

    all_new_transfers = []
    new_fingerprints = set()

    for entry in wallet_list:
        address = entry.get("address", "").strip().lower()
        chains_to_check = entry.get("chains", ["ethereum"])

        if not address:
            continue

        print(f"  Checking {address}...")

        for chain_key in chains_to_check:
            chain = CHAINS.get(chain_key)
            if not chain:
                continue
            if not chain["api_key"]:
                print(f"    Skipping {chain_key}: no API key configured")
                continue

            start_block = start_blocks.get(f"{address}:{chain_key}", 0)
            transfers = fetch_token_transfers(chain, address, start_block)

            for tx in transfers:
                fingerprint = TX_FINGERPRINT(tx)
                if fingerprint not in known_fingerprints and fingerprint not in new_fingerprints:
                    all_new_transfers.append(tx)
                    new_fingerprints.add(fingerprint)

                    if len(all_new_transfers) <= 5:
                        # 限制通知条数，避免刷屏
                        send_telegram(format_transfer_msg(tx, address))
                        time.sleep(0.5)  # Telegram rate limit

            # 更新 start_block（下次从这里开始查，减少重复请求）
            if transfers:
                block_numbers = [int(tx.get("blockNumber", "0")) for tx in transfers if tx.get("blockNumber")]
                if block_numbers:
                    latest_block = max(block_numbers) + 1
                    start_blocks[f"{address}:{chain_key}"] = max(
                        start_blocks.get(f"{address}:{chain_key}", 0), latest_block
                    )

    # 更新状态文件
    if new_fingerprints:
        for fp in new_fingerprints:
            state["fingerprints"][fp] = datetime.now(timezone.utc).isoformat()

    # 清理旧指纹（保留最近 1000 条）
    if len(state["fingerprints"]) > 1000:
        sorted_fps = sorted(state["fingerprints"].items(), key=lambda x: x[1], reverse=True)
        state["fingerprints"] = dict(sorted_fps[:1000])

    state["start_blocks"] = start_blocks
    save_json(STATE_FILE, state)

    if all_new_transfers:
        print(f"  ✅ Found {len(all_new_transfers)} new transfers, sent {min(len(all_new_transfers), 5)} notifications")
    else:
        print("  ⏸️  No new transfers")


if __name__ == "__main__":
    main()