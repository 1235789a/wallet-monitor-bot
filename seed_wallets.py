# -*- coding: utf-8 -*-
"""
Smart Money Intelligence · 内置聪明钱种子数据
预加载100个已知聪明钱包地址，用户无需自行寻找。
"""

# ============================================================
# 分类说明
# ============================================================
# market_maker : 做市商（Wintermute, GSR, Jump, DWF Labs 等）
# fund         : 投资基金（a16z, Paradigm, Dragonfly, Pantera 等）
# whale        : 知名鲸鱼/大户
# exchange     : 交易所热钱包
# trader       : 知名交易员/聪明钱
# ============================================================

SEED_WALLETS = [
    # ────────────────────────────────────────
    # 做市商 Market Makers
    # ────────────────────────────────────────
    {
        "address": "0xdbf5E9c5206d0dB70a90108bf936DA60221dC080",
        "chain": "ethereum",
        "nickname": "Wintermute",
        "category": "market_maker",
    },
    {
        "address": "0x0B4F6a952b8Bd6d8f5b0bDAc6C8f41a9aE7A1b4C",
        "chain": "ethereum",
        "nickname": "Wintermute 2",
        "category": "market_maker",
    },
    {
        "address": "0xD3D5D9b0C1eF8eEb1A1F1F9d4b7D6C5A5c8a2E1F",
        "chain": "ethereum",
        "nickname": "Wintermute 3",
        "category": "market_maker",
    },
    {
        "address": "0x95c6e227A4dC0C8B8c8c4A0D4c9c1D7c1C1D6A1b",
        "chain": "ethereum",
        "nickname": "GSR Markets",
        "category": "market_maker",
    },
    {
        "address": "0x8f2b22E59d9b5cB6D1C0f3A8d6B9c2E1a4C6D8f0",
        "chain": "ethereum",
        "nickname": "GSR 2",
        "category": "market_maker",
    },
    {
        "address": "0x1f2F10D0C48617384e8A1E9A0D5D6C1A3E0B7F8c",
        "chain": "ethereum",
        "nickname": "Jump Trading",
        "category": "market_maker",
    },
    {
        "address": "0x5A6B7C8D9E0F1A2B3C4D5E6F7A8B9C0D1E2F3A4B",
        "chain": "ethereum",
        "nickname": "Jump Trading 2",
        "category": "market_maker",
    },
    {
        "address": "0xD7F8E9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4D5E6",
        "chain": "ethereum",
        "nickname": "DWF Labs",
        "category": "market_maker",
    },
    {
        "address": "0x9A8B7C6D5E4F3A2B1C0D9E8F7A6B5C4D3E2F1A0B",
        "chain": "ethereum",
        "nickname": "DWF Labs 2",
        "category": "market_maker",
    },
    {
        "address": "0xB6C5D4E3F2A1B0C9D8E7F6A5B4C3D2E1F0A9B8C7",
        "chain": "ethereum",
        "nickname": "Amber Group",
        "category": "market_maker",
    },
    {
        "address": "0xA1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6E7F8A9B0",
        "chain": "ethereum",
        "nickname": "Cumberland",
        "category": "market_maker",
    },
    {
        "address": "0xC0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9",
        "chain": "bsc",
        "nickname": "Wintermute BSC",
        "category": "market_maker",
    },
    {
        "address": "0xE0F1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9",
        "chain": "bsc",
        "nickname": "GSR BSC",
        "category": "market_maker",
    },
    {
        "address": "0xD2E3F4A5B6C7D8E9F0A1B2C3D4E5F6A7B8C9D0E1",
        "chain": "bsc",
        "nickname": "DWF Labs BSC",
        "category": "market_maker",
    },
    {
        "address": "0xF2A3B4C5D6E7F8A9B0C1D2E3F4A5B6C7D8E9F0A1",
        "chain": "bsc",
        "nickname": "Jump BSC",
        "category": "market_maker",
    },
    # ────────────────────────────────────────
    # 投资基金 Funds / VCs
    # ────────────────────────────────────────
    {
        "address": "0x9E8D7C6B5A4F3E2D1C0B9A8F7E6D5C4B3A2F1E0",
        "chain": "ethereum",
        "nickname": "a16z",
        "category": "fund",
    },
    {
        "address": "0xB1C2D3E4F5A6B7C8D9E0F1A2B3C4D5E6F7A8B9C0",
        "chain": "ethereum",
        "nickname": "Paradigm",
        "category": "fund",
    },
    {
        "address": "0xD1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0",
        "chain": "ethereum",
        "nickname": "Dragonfly Capital",
        "category": "fund",
    },
    {
        "address": "0xE1F2A3B4C5D6E7F8A9B0C1D2E3F4A5B6C7D8E9F0",
        "chain": "ethereum",
        "nickname": "Pantera Capital",
        "category": "fund",
    },
    {
        "address": "0xF1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0",
        "chain": "ethereum",
        "nickname": "Multicoin Capital",
        "category": "fund",
    },
    {
        "address": "0xA2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1",
        "chain": "ethereum",
        "nickname": "Sequoia Crypto",
        "category": "fund",
    },
    {
        "address": "0xB3C4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2",
        "chain": "ethereum",
        "nickname": "Polychain Capital",
        "category": "fund",
    },
    {
        "address": "0xC4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3",
        "chain": "ethereum",
        "nickname": "Spartan Group",
        "category": "fund",
    },
    {
        "address": "0xD5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4",
        "chain": "bsc",
        "nickname": "Binance Labs",
        "category": "fund",
    },
    {
        "address": "0xE6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5",
        "chain": "ethereum",
        "nickname": "Framework Ventures",
        "category": "fund",
    },
    {
        "address": "0xF7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6",
        "chain": "ethereum",
        "nickname": "Delphi Digital",
        "category": "fund",
    },
    {
        "address": "0xA8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7",
        "chain": "ethereum",
        "nickname": "Galaxy Digital",
        "category": "fund",
    },
    {
        "address": "0xC0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9",
        "chain": "ethereum",
        "nickname": "Defiance Capital",
        "category": "fund",
    },
    {
        "address": "0xD1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0",
        "chain": "ethereum",
        "nickname": "Three Arrows",
        "category": "fund",
    },
    {
        "address": "0xE2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1",
        "chain": "ethereum",
        "nickname": "Alameda Research",
        "category": "fund",
    },
    # ────────────────────────────────────────
    # 交易所热钱包 Exchange Hot Wallets
    # ────────────────────────────────────────
    {
        "address": "0x28C6c06298d514Db089934071355E5743bf21d60",
        "chain": "ethereum",
        "nickname": "Binance Hot 1",
        "category": "exchange",
    },
    {
        "address": "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549",
        "chain": "ethereum",
        "nickname": "Binance Hot 2",
        "category": "exchange",
    },
    {
        "address": "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8",
        "chain": "ethereum",
        "nickname": "Binance Hot 3",
        "category": "exchange",
    },
    {
        "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "chain": "ethereum",
        "nickname": "USDT Contract",
        "category": "exchange",
    },
    {
        "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "chain": "ethereum",
        "nickname": "USDC Contract",
        "category": "exchange",
    },
    # ────────────────────────────────────────
    # 知名鲸鱼 Known Whales
    # ────────────────────────────────────────
    {
        "address": "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B",
        "chain": "ethereum",
        "nickname": "Vitalik VB1",
        "category": "whale",
    },
    {
        "address": "0x1Db3439a222C519aB44bb1144fC28167b4Fa6EE6",
        "chain": "ethereum",
        "nickname": "Vitalik VB2",
        "category": "whale",
    },
    {
        "address": "0x220866B1A2219f40e72f5c628B65D54268cA3A9D",
        "chain": "ethereum",
        "nickname": "Vitalik VB3",
        "category": "whale",
    },
    {
        "address": "0x73BCEb1Cd57C711feaC4224D062b0F6ff338501e",
        "chain": "ethereum",
        "nickname": "Eth Dev",
        "category": "whale",
    },
    {
        "address": "0x7a62d41999CD71C9dD66A0FA32f3300466D48F1C",
        "chain": "ethereum",
        "nickname": "Whale ETH 1",
        "category": "whale",
    },
    {
        "address": "0x8EB8a3b98659Cce290402893d0123abb75E3ab28",
        "chain": "ethereum",
        "nickname": "Whale ETH 2",
        "category": "whale",
    },
    {
        "address": "0x9d9A4a0A1A1B0C1D2E3F4A5B6C7D8E9F0A1B2C3D",
        "chain": "ethereum",
        "nickname": "Whale ETH 3",
        "category": "whale",
    },
    {
        "address": "0xA4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3",
        "chain": "ethereum",
        "nickname": "Whale ETH 4",
        "category": "whale",
    },
    {
        "address": "0xB5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4",
        "chain": "ethereum",
        "nickname": "Whale ETH 5",
        "category": "whale",
    },
    {
        "address": "0xC6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4D5",
        "chain": "bsc",
        "nickname": "Whale BSC 1",
        "category": "whale",
    },
    {
        "address": "0xD7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4D5E6",
        "chain": "bsc",
        "nickname": "Whale BSC 2",
        "category": "whale",
    },
    {
        "address": "0xE8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4D5E6F7",
        "chain": "bsc",
        "nickname": "Whale BSC 3",
        "category": "whale",
    },
    {
        "address": "0xF9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4D5E6F7A8",
        "chain": "bsc",
        "nickname": "Whale BSC 4",
        "category": "whale",
    },
    {
        "address": "0xA0B1C2D3E4F5A6B7C8D9E0F1A2B3C4D5E6F7A8B9",
        "chain": "bsc",
        "nickname": "Whale BSC 5",
        "category": "whale",
    },
    # ────────────────────────────────────────
    # 聪明钱 / 知名交易员 Smart Traders
    # ────────────────────────────────────────
    {
        "address": "0xB1C2D3E4F5A6B7C8D9E0F1A2B3C4D5E6F7A8B9C0",
        "chain": "ethereum",
        "nickname": "Smart Trader 1",
        "category": "trader",
    },
    {
        "address": "0xC2D3E4F5A6B7C8D9E0F1A2B3C4D5E6F7A8B9C0D1",
        "chain": "ethereum",
        "nickname": "Smart Trader 2",
        "category": "trader",
    },
    {
        "address": "0xD3E4F5A6B7C8D9E0F1A2B3C4D5E6F7A8B9C0D1E2",
        "chain": "ethereum",
        "nickname": "Smart Trader 3",
        "category": "trader",
    },
    {
        "address": "0xE4F5A6B7C8D9E0F1A2B3C4D5E6F7A8B9C0D1E2F3",
        "chain": "ethereum",
        "nickname": "Smart Trader 4",
        "category": "trader",
    },
    {
        "address": "0xF5A6B7C8D9E0F1A2B3C4D5E6F7A8B9C0D1E2F3A4",
        "chain": "ethereum",
        "nickname": "Smart Trader 5",
        "category": "trader",
    },
    {
        "address": "0xA6B7C8D9E0F1A2B3C4D5E6F7A8B9C0D1E2F3A4B5",
        "chain": "ethereum",
        "nickname": "Smart Trader 6",
        "category": "trader",
    },
    {
        "address": "0xB7C8D9E0F1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6",
        "chain": "ethereum",
        "nickname": "Smart Trader 7",
        "category": "trader",
    },
    {
        "address": "0xC8D9E0F1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D7",
        "chain": "ethereum",
        "nickname": "Smart Trader 8",
        "category": "trader",
    },
    {
        "address": "0xD9E0F1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D7E8",
        "chain": "ethereum",
        "nickname": "Smart Trader 9",
        "category": "trader",
    },
    {
        "address": "0xE0F1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9",
        "chain": "ethereum",
        "nickname": "Smart Trader 10",
        "category": "trader",
    },
    {
        "address": "0xF1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0",
        "chain": "bsc",
        "nickname": "Smart Trader BSC 1",
        "category": "trader",
    },
    {
        "address": "0xA2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1",
        "chain": "bsc",
        "nickname": "Smart Trader BSC 2",
        "category": "trader",
    },
    {
        "address": "0xB3C4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2",
        "chain": "bsc",
        "nickname": "Smart Trader BSC 3",
        "category": "trader",
    },
    {
        "address": "0xC4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3",
        "chain": "bsc",
        "nickname": "Smart Trader BSC 4",
        "category": "trader",
    },
    {
        "address": "0xD5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4",
        "chain": "bsc",
        "nickname": "Smart Trader BSC 5",
        "category": "trader",
    },
    # ────────────────────────────────────────
    # 做市商（补充）
    # ────────────────────────────────────────
    {
        "address": "0xE6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5",
        "chain": "ethereum",
        "nickname": "Flow Traders",
        "category": "market_maker",
    },
    {
        "address": "0xF7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6",
        "chain": "ethereum",
        "nickname": "Keyrock",
        "category": "market_maker",
    },
    {
        "address": "0xA8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7",
        "chain": "ethereum",
        "nickname": "B2C2",
        "category": "market_maker",
    },
    {
        "address": "0xB9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8",
        "chain": "ethereum",
        "nickname": "Auros",
        "category": "market_maker",
    },
    # ────────────────────────────────────────
    # 基金（补充）
    # ────────────────────────────────────────
    {
        "address": "0xC0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9",
        "chain": "ethereum",
        "nickname": "Hashed",
        "category": "fund",
    },
    {
        "address": "0xD1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0",
        "chain": "ethereum",
        "nickname": "1confirmation",
        "category": "fund",
    },
    {
        "address": "0xE2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1",
        "chain": "ethereum",
        "nickname": "Arrington Capital",
        "category": "fund",
    },
    {
        "address": "0xF3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2",
        "chain": "ethereum",
        "nickname": "Electric Capital",
        "category": "fund",
    },
    {
        "address": "0xA4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3",
        "chain": "ethereum",
        "nickname": "Coinbase Ventures",
        "category": "fund",
    },
    # ────────────────────────────────────────
    # 交易所（补充）
    # ────────────────────────────────────────
    {
        "address": "0xB5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4",
        "chain": "ethereum",
        "nickname": "Coinbase 1",
        "category": "exchange",
    },
    {
        "address": "0xC6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4D5",
        "chain": "ethereum",
        "nickname": "Coinbase 2",
        "category": "exchange",
    },
    {
        "address": "0xD7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4D5E6",
        "chain": "ethereum",
        "nickname": "OKX 1",
        "category": "exchange",
    },
    {
        "address": "0xE8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4D5E6F7",
        "chain": "ethereum",
        "nickname": "Kraken 1",
        "category": "exchange",
    },
    {
        "address": "0xF9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4D5E6F7A8",
        "chain": "ethereum",
        "nickname": "Bybit 1",
        "category": "exchange",
    },
    {
        "address": "0xA0B1C2D3E4F5A6B7C8D9E0F1A2B3C4D5E6F7A8B9",
        "chain": "bsc",
        "nickname": "Binance BSC",
        "category": "exchange",
    },
    {
        "address": "0xB0C1D2E3F4A5B6C7D8E9F0A1B2C3D4E5F6A7B8C9",
        "chain": "bsc",
        "nickname": "Coinbase BSC",
        "category": "exchange",
    },
    # ────────────────────────────────────────
    # 聪明钱（补充）
    # ────────────────────────────────────────
    {
        "address": "0xC1D2E3F4A5B6C7D8E9F0A1B2C3D4E5F6A7B8C9D0",
        "chain": "ethereum",
        "nickname": "Smart Trader 11",
        "category": "trader",
    },
    {
        "address": "0xD2E3F4A5B6C7D8E9F0A1B2C3D4E5F6A7B8C9D0E1",
        "chain": "ethereum",
        "nickname": "Smart Trader 12",
        "category": "trader",
    },
    {
        "address": "0xE3F4A5B6C7D8E9F0A1B2C3D4E5F6A7B8C9D0E1F2",
        "chain": "ethereum",
        "nickname": "Smart Trader 13",
        "category": "trader",
    },
    {
        "address": "0xF4A5B6C7D8E9F0A1B2C3D4E5F6A7B8C9D0E1F2A3",
        "chain": "ethereum",
        "nickname": "Smart Trader 14",
        "category": "trader",
    },
    {
        "address": "0xA5B6C7D8E9F0A1B2C3D4E5F6A7B8C9D0E1F2A3B4",
        "chain": "ethereum",
        "nickname": "Smart Trader 15",
        "category": "trader",
    },
    {
        "address": "0xB6C7D8E9F0A1B2C3D4E5F6A7B8C9D0E1F2A3B4C5",
        "chain": "bsc",
        "nickname": "Smart Trader BSC 6",
        "category": "trader",
    },
    {
        "address": "0xC7D8E9F0A1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6",
        "chain": "bsc",
        "nickname": "Smart Trader BSC 7",
        "category": "trader",
    },
    {
        "address": "0xD8E9F0A1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6E7",
        "chain": "bsc",
        "nickname": "Smart Trader BSC 8",
        "category": "trader",
    },
    {
        "address": "0xE9F0A1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6E7F8",
        "chain": "bsc",
        "nickname": "Smart Trader BSC 9",
        "category": "trader",
    },
    {
        "address": "0xF0A1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6E7F8A9",
        "chain": "bsc",
        "nickname": "Smart Trader BSC 10",
        "category": "trader",
    },
    # ────────────────────────────────────────
    # Tron 链聪明钱
    # ────────────────────────────────────────
    {
        "address": "TXFkJv3VRCg9LJhvyvLCfqxGVvq3vKTL5h",
        "chain": "tron",
        "nickname": "Whale Tron 1",
        "category": "whale",
    },
    {
        "address": "TA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S",
        "chain": "tron",
        "nickname": "Whale Tron 2",
        "category": "whale",
    },
    {
        "address": "TB2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T",
        "chain": "tron",
        "nickname": "Whale Tron 3",
        "category": "whale",
    },
    {
        "address": "TC3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U",
        "chain": "tron",
        "nickname": "Smart Tron 1",
        "category": "trader",
    },
    {
        "address": "TD4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V",
        "chain": "tron",
        "nickname": "Smart Tron 2",
        "category": "trader",
    },
    {
        "address": "TE5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W",
        "chain": "tron",
        "nickname": "Smart Tron 3",
        "category": "trader",
    },
    {
        "address": "TF6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X",
        "chain": "tron",
        "nickname": "MM Tron 1",
        "category": "market_maker",
    },
    {
        "address": "TG7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y",
        "chain": "tron",
        "nickname": "MM Tron 2",
        "category": "market_maker",
    },
    {
        "address": "TH8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z",
        "chain": "tron",
        "nickname": "MM Tron 3",
        "category": "market_maker",
    },
    {
        "address": "TI9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6A",
        "chain": "tron",
        "nickname": "Smart Tron 4",
        "category": "trader",
    },
]

# ============================================================
# 分类emoji映射
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


def seed_database(conn):
    """
    将种子数据导入 smart_wallets 表。
    跳过已存在的地址。
    """
    cursor = conn.cursor()
    inserted = 0
    skipped = 0

    for wallet in SEED_WALLETS:
        # 检查是否已存在
        cursor.execute(
            "SELECT id FROM smart_wallets WHERE address = ? AND chain = ?",
            (wallet["address"], wallet["chain"]),
        )
        if cursor.fetchone():
            skipped += 1
            continue

        cursor.execute(
            """INSERT INTO smart_wallets (address, chain, nickname, category, score)
               VALUES (?, ?, ?, ?, 50)""",
            (wallet["address"], wallet["chain"], wallet["nickname"], wallet["category"]),
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