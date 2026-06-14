# -*- coding: utf-8 -*-
"""
Whale Tracker TG Bot · USDT 支付检测
支持 Tron (TRC20) 和 Ethereum/BSC (ERC20)
"""

import requests
from datetime import datetime, timedelta
from config import (
    PAYOUT_WALLET, PAYOUT_CHAIN, PRICE_USDT,
    TRONGRID_API_KEY, ETHERSCAN_API_KEY,
)


def check_tron_payment(user_wallet: str) -> dict:
    """检查 Tron (TRC20-USDT) 链上支付"""
    if not TRONGRID_API_KEY:
        return {"found": False, "error": "未配置 TRONGRID_API_KEY"}

    USDT_TRC20 = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    url = f"https://api.trongrid.io/v1/accounts/{PAYOUT_WALLET}/transactions/trc20"
    params = {
        "contract_address": USDT_TRC20,
        "limit": 50,
        "min_timestamp": int((datetime.now() - timedelta(days=7)).timestamp() * 1000),
    }
    headers = {"TRON-PRO-API-KEY": TRONGRID_API_KEY}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            return {"found": False, "error": f"HTTP {resp.status_code}"}

        data = resp.json()
        txs = data.get("data", [])

        for tx in txs:
            from_addr = tx.get("from", "")
            to_addr = tx.get("to", "")
            if from_addr.lower() != user_wallet.lower():
                continue
            if to_addr.lower() != PAYOUT_WALLET.lower():
                continue

            raw_value = int(tx.get("value", "0"))
            amount = raw_value / 1e6
            if amount >= PRICE_USDT * 0.9:
                return {
                    "found": True,
                    "tx_hash": tx.get("transaction_id", ""),
                    "amount": amount,
                    "chain": "tron",
                }
        return {"found": False}

    except Exception as e:
        return {"found": False, "error": str(e)}


def check_evm_payment(user_wallet: str, chain: str) -> dict:
    """检查 EVM 链支付"""
    if not ETHERSCAN_API_KEY:
        return {"found": False, "error": "未配置 ETHERSCAN_API_KEY"}

    USDT_CONTRACT = {
        "ethereum": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "bsc": "0x55d398326f99059fF775485246999027B3197955",
    }

    API_BASE = {
        "ethereum": "https://api.etherscan.io/api",
        "bsc": "https://api.bscscan.com/api",
    }

    contract_addr = USDT_CONTRACT.get(chain)
    api_url = API_BASE.get(chain)

    if not contract_addr or not api_url:
        return {"found": False, "error": f"不支持的链: {chain}"}

    params = {
        "module": "account",
        "action": "tokentx",
        "contractaddress": contract_addr,
        "address": PAYOUT_WALLET,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",
        "apikey": ETHERSCAN_API_KEY,
    }

    try:
        resp = requests.get(api_url, params=params, timeout=15)
        if resp.status_code != 200:
            return {"found": False, "error": f"HTTP {resp.status_code}"}

        data = resp.json()
        if data.get("status") != "1":
            return {"found": False}

        txs = data.get("result", [])
        for tx in txs:
            from_addr = tx.get("from", "")
            to_addr = tx.get("to", "")
            if from_addr.lower() != user_wallet.lower():
                continue
            if to_addr.lower() != PAYOUT_WALLET.lower():
                continue

            raw_value = tx.get("value", "0")
            decimals = int(tx.get("tokenDecimal", "6"))
            amount = float(raw_value) / (10 ** decimals)

            timestamp = int(tx.get("timeStamp", "0"))
            tx_time = datetime.fromtimestamp(timestamp)
            if tx_time < datetime.now() - timedelta(days=7):
                continue

            if amount >= PRICE_USDT * 0.9:
                return {
                    "found": True,
                    "tx_hash": tx.get("hash", ""),
                    "amount": amount,
                    "chain": chain,
                }
        return {"found": False}

    except Exception as e:
        return {"found": False, "error": str(e)}


def check_payment(user_wallet: str, chain: str = "tron") -> dict:
    """统一支付检测入口"""
    if chain == "tron":
        return check_tron_payment(user_wallet)
    else:
        return check_evm_payment(user_wallet, chain)


def validate_wallet_address(address: str, chain: str = "tron") -> bool:
    """粗略验证钱包地址格式"""
    address = address.strip()
    if chain == "tron":
        return len(address) == 34 and address.startswith("T")
    elif chain in ("ethereum", "bsc"):
        return len(address) == 42 and address.startswith("0x")
    return False


def detect_chain_from_address(address: str) -> str:
    """根据地址格式检测链类型"""
    address = address.strip()
    if address.startswith("T") and len(address) == 34:
        return "tron"
    elif address.startswith("0x") and len(address) == 42:
        return "ethereum"
    return "unknown"