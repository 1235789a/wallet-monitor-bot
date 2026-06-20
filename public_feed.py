# -*- coding: utf-8 -*-
"""
Public DEX Feed · 公开链上数据源（免费、无需 API key）

用途
----
当聪明钱扫描（固定名人钱包）近 24h 没有产生 alpha 买入、导致 Hot Tokens /
Live Signals / Daily Digest 为空时，回退到真实的公开 DEX 数据，
让 demo 有真实、实时的链上热门代币可展示。

数据源（按优先级）
------------------
1. GeckoTerminal API  —— 免费、无需 key，专做 DEX trending pools
   https://api.geckoterminal.com/api/v2
2. DexScreener API    —— 免费、无需 key，备用
   https://api.dexscreener.com

设计原则
--------
- 纯只读、对外请求，不写库、不碰 schema、不动支付逻辑
- 全部带超时 + 异常兜底，任何失败都返回空列表，绝不抛到上层导致 Bot 崩溃
- 轻量内存缓存（默认 5 分钟），避免每次命令都打外部 API
- 诚实标注数据来源，不伪装成"聪明钱信号"
"""

import time
import requests

# ---- 链名映射：内部 chain key → GeckoTerminal network id ----
_GT_NETWORK = {
    "ethereum": "eth",
    "bsc": "bsc",
    "tron": "tron",
}

# ---- 链名映射：内部 chain key → DexScreener chain id ----
_DS_CHAIN = {
    "ethereum": "ethereum",
    "bsc": "bsc",
    "tron": "tron",
}

_GT_BASE = "https://api.geckoterminal.com/api/v2"
_DS_BASE = "https://api.dexscreener.com"

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "whale-tracker-bot/1.0 (+demo)",
}

# ---- 简单内存缓存：{cache_key: (timestamp, data)} ----
_CACHE = {}
_CACHE_TTL = 300  # 5 分钟


def _cache_get(key: str):
    item = _CACHE.get(key)
    if not item:
        return None
    ts, data = item
    if time.time() - ts > _CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return data


def _cache_set(key: str, data):
    _CACHE[key] = (time.time(), data)


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ============================================================
# GeckoTerminal（主数据源）
# ============================================================

def _fetch_geckoterminal_trending(chain_key: str, limit: int = 10) -> list:
    """
    拉取某条链上的 trending pools（真实 DEX 交易热度）。

    返回标准化列表：
    [{symbol, name, chain, price_usd, change_24h, volume_24h, address, source}, ...]
    """
    network = _GT_NETWORK.get(chain_key)
    if not network:
        return []

    url = f"{_GT_BASE}/networks/{network}/trending_pools"
    try:
        resp = requests.get(url, headers=_HEADERS, params={"page": 1}, timeout=12)
        if resp.status_code != 200:
            return []
        payload = resp.json()
    except Exception as e:
        print(f"  [public_feed] GeckoTerminal error ({chain_key}): {e}")
        return []

    items = payload.get("data", []) or []
    results = []
    for pool in items[:limit]:
        attrs = pool.get("attributes", {}) or {}

        # pool name 形如 "PEPE / WETH"，取基础代币符号
        name = attrs.get("name", "") or ""
        symbol = name.split("/")[0].strip() if "/" in name else name.strip()
        if not symbol:
            continue

        price = _safe_float(attrs.get("base_token_price_usd"))

        change = attrs.get("price_change_percentage", {}) or {}
        change_24h = _safe_float(change.get("h24"))

        vol = attrs.get("volume_usd", {}) or {}
        volume_24h = _safe_float(vol.get("h24"))

        results.append({
            "symbol": symbol[:20],
            "name": name[:40],
            "chain": chain_key,
            "price_usd": price,
            "change_24h": change_24h,
            "volume_24h": volume_24h,
            "address": attrs.get("address", "") or "",
            "source": "GeckoTerminal",
        })

    return results


# ============================================================
# DexScreener（备用数据源）
# ============================================================

def _fetch_dexscreener_trending(chain_key: str, limit: int = 10) -> list:
    """
    DexScreener 备用源：用 token-boosts/latest 拿热门代币，按链过滤。
    DexScreener 没有官方 trending 端点，这里用 boosts（被推广/活跃）作为热度近似。
    """
    ds_chain = _DS_CHAIN.get(chain_key)
    if not ds_chain:
        return []

    url = f"{_DS_BASE}/token-boosts/latest/v1"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        if resp.status_code != 200:
            return []
        payload = resp.json()
    except Exception as e:
        print(f"  [public_feed] DexScreener boosts error ({chain_key}): {e}")
        return []

    # payload 是 list，元素含 chainId / tokenAddress
    boosts = payload if isinstance(payload, list) else payload.get("data", [])
    token_addrs = []
    for b in boosts:
        if (b.get("chainId") or "").lower() == ds_chain:
            addr = b.get("tokenAddress")
            if addr:
                token_addrs.append(addr)
        if len(token_addrs) >= limit:
            break

    results = []
    for addr in token_addrs[:limit]:
        info = _dexscreener_token_pair(ds_chain, addr)
        if info:
            results.append(info)

    return results


def _dexscreener_token_pair(ds_chain: str, token_address: str):
    """查询单个代币在 DexScreener 上的最活跃交易对，返回标准化字典。"""
    url = f"{_DS_BASE}/tokens/v1/{ds_chain}/{token_address}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        pairs = resp.json()
    except Exception:
        return None

    if not isinstance(pairs, list) or not pairs:
        return None

    # 取流动性最高的交易对
    pairs.sort(key=lambda p: _safe_float((p.get("liquidity") or {}).get("usd")), reverse=True)
    p = pairs[0]

    base = p.get("baseToken", {}) or {}
    symbol = base.get("symbol", "") or ""
    if not symbol:
        return None

    return {
        "symbol": symbol[:20],
        "name": (base.get("name", "") or symbol)[:40],
        "chain": _chain_key_from_ds(ds_chain),
        "price_usd": _safe_float(p.get("priceUsd")),
        "change_24h": _safe_float((p.get("priceChange") or {}).get("h24")),
        "volume_24h": _safe_float((p.get("volume") or {}).get("h24")),
        "address": token_address,
        "source": "DexScreener",
    }


def _chain_key_from_ds(ds_chain: str) -> str:
    for k, v in _DS_CHAIN.items():
        if v == ds_chain:
            return k
    return ds_chain


# ============================================================
# 对外统一入口
# ============================================================

def get_trending_tokens(chains=None, limit: int = 10) -> list:
    """
    获取真实公开 DEX 热门代币（多链聚合，按 24h 交易量降序）。

    Parameters
    ----------
    chains : list[str] | None  内部 chain key 列表，缺省 ['ethereum', 'bsc']
    limit  : 每条链最多取多少，最终聚合后也按此截断

    Returns
    -------
    list[dict] —— 失败时返回空列表（绝不抛异常）
    """
    if chains is None:
        chains = ["ethereum", "bsc"]

    cache_key = f"trending:{','.join(chains)}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    aggregated = []
    for chain_key in chains:
        # 主源
        rows = _fetch_geckoterminal_trending(chain_key, limit=limit)
        # 主源失败 → 备用源
        if not rows:
            rows = _fetch_dexscreener_trending(chain_key, limit=limit)
        aggregated.extend(rows)

    # 按 24h 交易量降序
    aggregated.sort(key=lambda r: r.get("volume_24h", 0), reverse=True)
    aggregated = aggregated[:limit]

    _cache_set(cache_key, aggregated)
    return aggregated


def _fmt_price(p: float) -> str:
    """价格友好格式化（处理 meme 币极小价格）。"""
    if p <= 0:
        return "—"
    if p >= 1:
        return f"${p:,.4f}"
    if p >= 0.0001:
        return f"${p:.6f}"
    return f"${p:.2e}"


def _fmt_vol(v: float) -> str:
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:,.0f}"


def render_public_hot(limit: int = 8) -> str:
    """
    渲染"公开真实热门代币"文本块（Markdown）。
    供 Hot Tokens / Daily Digest 空态回退使用。失败返回空串。
    """
    tokens = get_trending_tokens(chains=["ethereum", "bsc"], limit=limit)
    if not tokens:
        return ""

    lines = ["🔥 *Trending Tokens · 真实 DEX 实时热度*\n"]
    chain_emoji = {"ethereum": "🔷", "bsc": "🟡", "tron": "🔴"}
    for i, t in enumerate(tokens, 1):
        ce = chain_emoji.get(t["chain"], "📊")
        chg = t.get("change_24h", 0)
        arrow = "🟢" if chg >= 0 else "🔴"
        lines.append(
            f"  {i}. {ce} *{t['symbol']}* — {_fmt_price(t['price_usd'])} "
            f"{arrow}{chg:+.1f}% | Vol {_fmt_vol(t['volume_24h'])}"
        )

    src = tokens[0].get("source", "GeckoTerminal")
    lines.append(f"\n_数据来源: {src} 公开 DEX 数据（真实实时）_")
    return "\n".join(lines)


def render_public_signals(limit: int = 5) -> str:
    """
    渲染"公开真实市场动向"作为 Live Signals 空态回退。失败返回空串。
    用 24h 涨幅最大的代币作为"市场正在关注"的近似信号。
    """
    tokens = get_trending_tokens(chains=["ethereum", "bsc"], limit=limit * 2)
    if not tokens:
        return ""

    # 按 24h 涨幅排序，展示市场动向
    movers = sorted(tokens, key=lambda r: r.get("change_24h", 0), reverse=True)[:limit]
    lines = ["🚨 *Market Signals · 真实 DEX 市场动向*\n"]
    chain_emoji = {"ethereum": "🔷", "bsc": "🟡", "tron": "🔴"}
    for t in movers:
        ce = chain_emoji.get(t["chain"], "📊")
        chg = t.get("change_24h", 0)
        arrow = "🟢" if chg >= 0 else "🔴"
        lines.append(
            f"{ce} *{t['symbol']}* {arrow} {chg:+.1f}% (24h) "
            f"| {_fmt_price(t['price_usd'])} | Vol {_fmt_vol(t['volume_24h'])}"
        )

    src = movers[0].get("source", "GeckoTerminal")
    lines.append(f"\n_数据来源: {src} 公开 DEX 数据（真实实时）_")
    return "\n".join(lines)


# ============================================================
# 自测
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("Public DEX Feed · 自测")
    print("=" * 50)
    print("\n--- Trending tokens ---")
    for t in get_trending_tokens(limit=8):
        print(t)
    print("\n--- render_public_hot ---")
    print(render_public_hot())
    print("\n--- render_public_signals ---")
    print(render_public_signals())
