# -*- coding: utf-8 -*-
"""
Whale Tracker TG Bot · 配置
Reddit 需求: "How do you guys track whale wallet movements?" (👍198)
"""

import os

# ============================================================
# 自动加载 .env 文件（如果存在）
# ============================================================
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _, _value = _line.partition("=")
            _key = _key.strip()
            _value = _value.strip().strip('"').strip("'")
            if _key and _key not in os.environ:
                os.environ[_key] = _value

# ============================================================
# Telegram Bot 配置
# ============================================================
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")

# ============================================================
# 链上 API Key
# ============================================================
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
BSCSCAN_API_KEY = os.environ.get("BSCSCAN_API_KEY", "")
TRONGRID_API_KEY = os.environ.get("TRONGRID_API_KEY", "")

# ============================================================
# USDT 收款配置
# ============================================================
PAYOUT_WALLET = os.environ.get("PAYOUT_WALLET", "")
PAYOUT_CHAIN = os.environ.get("PAYOUT_CHAIN", "tron")

# ============================================================
# 定价
# ============================================================
PRICE_USDT = float(os.environ.get("PRICE_USDT", "5"))        # 月费 USDT（比报告便宜，走量）
TRIAL_DAYS = int(os.environ.get("TRIAL_DAYS", "3"))          # 免费试用天数
SUBSCRIPTION_DAYS = int(os.environ.get("SUBSCRIPTION_DAYS", "30"))

# ============================================================
# 数据库
# ============================================================
DATABASE_PATH = os.environ.get("DATABASE_PATH", "whale_tracker.db")

# ============================================================
# 监控配置
# ============================================================
CHECK_INTERVAL_MINUTES = int(os.environ.get("CHECK_INTERVAL_MINUTES", "10"))  # 轮询间隔
FREE_WALLET_LIMIT = int(os.environ.get("FREE_WALLET_LIMIT", "3"))            # 免费版可追踪地址数
PAID_WALLET_LIMIT = int(os.environ.get("PAID_WALLET_LIMIT", "50"))           # 付费版可追踪地址数
MIN_USD_VALUE = float(os.environ.get("MIN_USD_VALUE", "1000"))               # 最低推送金额（美元）

# USDT / USDC 合约地址（用于过滤稳定币大额转账）
STABLECOIN_CONTRACTS = {
    "ethereum": [
        "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
    ],
    "bsc": [
        "0x55d398326f99059fF775485246999027B3197955",   # USDT
        "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",   # USDC
    ],
    "tron": [
        "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",          # USDT
    ],
}

# ============================================================
# 链配置
# ============================================================
CHAINS = {
    "ethereum": {
        "name": "Ethereum",
        "emoji": "🔷",
        "type": "evm",
        "api_url": "https://api.etherscan.io/api",
        "api_key_env": "ETHERSCAN_API_KEY",
        "explorer": "https://etherscan.io",
        "native_symbol": "ETH",
    },
    "bsc": {
        "name": "BSC",
        "emoji": "🟡",
        "type": "evm",
        "api_url": "https://api.bscscan.com/api",
        "api_key_env": "BSCSCAN_API_KEY",
        "explorer": "https://bscscan.com",
        "native_symbol": "BNB",
    },
    "tron": {
        "name": "Tron",
        "emoji": "🔴",
        "type": "tron",
        "api_base": "https://api.trongrid.io",
        "api_key_env": "TRONGRID_API_KEY",
        "explorer": "https://tronscan.org",
        "native_symbol": "TRX",
    },
}

# ============================================================
# 聪明钱监控配置
# ============================================================
# 跟踪哪些链上的聪明钱
SMART_MONEY_CHAINS = os.environ.get("SMART_MONEY_CHAINS", "ethereum,bsc,tron").split(",")
# 聪明钱地址更新热度的最低USD阈值
SMART_USD_THRESHOLD = float(os.environ.get("SMART_USD_THRESHOLD", "5000"))
# 每日摘要推送时间（UTC）
DIGEST_HOUR_UTC = int(os.environ.get("DIGEST_HOUR_UTC", "12"))
# 热度榜Top N
HEAT_TOP_N = int(os.environ.get("HEAT_TOP_N", "10"))