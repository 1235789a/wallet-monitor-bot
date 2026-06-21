# -*- coding: utf-8 -*-
"""
Whale Tracker TG Bot · 主程序
Reddit: "How do you guys track whale wallet movements?" (👍198)
"""

import asyncio
import os
import sys
import traceback
from datetime import datetime, timezone

# Windows 控制台默认 GBK 编码，遇到 emoji 会崩溃；强制 stdout/stderr 用 UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, MenuButtonCommands,
)
from telegram.error import Conflict, NetworkError, TimedOut
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode

from config import (
    TG_BOT_TOKEN, TG_PROXY, PAYOUT_WALLET, PAYOUT_CHAIN, PRICE_USDT,
    TRIAL_DAYS, SUBSCRIPTION_DAYS, CHECK_INTERVAL_MINUTES,
    FREE_WALLET_LIMIT, PAID_WALLET_LIMIT, MIN_USD_VALUE,
    SMART_MONEY_CHAINS, HEAT_TOP_N, DIGEST_HOUR_UTC,
    CHAINS, ADMIN_USER_IDS,
    ETHERSCAN_API_KEY, BSCSCAN_API_KEY, TRONGRID_API_KEY,
)

from models import (
    init_db, get_conn, upsert_user, activate_paid, is_user_active,
    add_tracked_wallet, remove_tracked_wallet, get_user_wallets,
    get_all_active_users, save_tx_history,
    get_hot_tokens, get_leaderboard, save_daily_digest, get_daily_digest,
    mark_digest_pushed, get_all_smart_wallets, get_smart_wallet,
    get_users_count, get_tracked_wallets_count, get_smart_wallets_count,
    get_token_heat_count, get_daily_digest_count, upsert_token_heat,
)
from seed_wallets import seed_database

from payment import check_payment, validate_wallet_address, detect_chain_from_address
from monitor import (
    scan_all_chains, format_alert, scan_smart_money, format_smart_alert,
)

from alpha import AlphaAggregator
from public_feed import (
    render_public_hot, render_public_signals,
    render_public_hot_page, render_public_signals_page,
)

# 分页：每页条数
HOT_PER_PAGE = 5
SIGNALS_PER_PAGE = 5
REFRESH_FAIL_MSG = "Unable to refresh data right now. Please try again later."


# Founding Pro 限量名额（用于 /upgrade 文案 "first N users"）。仅 bot.py 读取，不改 config。
FOUNDING_USER_LIMIT = int(os.environ.get("FOUNDING_USER_LIMIT", "20"))

# ============================================================
# 键盘 Markup
# ============================================================

def tier_of(user: dict) -> str:
    """把 user.status 归一为信号分层 tier：paid / trial / free(expired)"""
    status = user.get("status", "trial")
    if status == "paid":
        return "paid"
    if status == "trial":
        return "trial"
    return "free"


# ============================================================
# 用户状态栏（Free / Trial / Paid 体验提示）
# ============================================================

def _trial_time_left(user: dict) -> str:
    """试用剩余时间，粗略到 days/hours（trial_end 为 naive datetime）。"""
    te = user.get("trial_end")
    if not te:
        return "—"
    try:
        end = datetime.fromisoformat(te)
    except (TypeError, ValueError):
        return "—"
    secs = (end - datetime.now()).total_seconds()
    if secs <= 0:
        return "0h"
    days = int(secs // 86400)
    hours = int((secs % 86400) // 3600)
    if days > 0:
        return f"{days}d {hours}h"
    return f"{hours}h"


def _paid_until_str(user: dict) -> str:
    """付费到期日期（仅日期，无时间）。"""
    pu = user.get("paid_until")
    if not pu:
        return "—"
    try:
        return datetime.fromisoformat(pu).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return "—"


def render_status_bar(user: dict) -> str:
    """
    页面顶部英文状态栏，明确区分 Free / Trial / Paid。
    Trial 在本项目里等同 Pro，状态栏会如实说明用户正在体验 Pro 数据。
    """
    status = user.get("status")
    if status == "trial":
        return (
            f"🟢 *Status: Pro Trial · {_trial_time_left(user)} left*\n"
            "_You are viewing Pro-level data during your trial._"
        )
    if status == "paid":
        return f"💎 *Status: Pro Active · valid until {_paid_until_str(user)}*"
    # expired / free
    return (
        "🔒 *Status: Free Preview*\n"
        "_Upgrade to Pro to unlock the full Alpha Radar — Smart Money signals "
        "when detected, wallet details, tx links, and full Hot Tokens._"
    )



def with_status_bar(user: dict, body: str) -> str:
    """在正文顶部拼接状态栏。"""
    return f"{render_status_bar(user)}\n\n{body}"



def main_menu_keyboard(status: str = ""):
    """主菜单 · Alpha Intelligence 5 键"""
    buttons = [
        [
            InlineKeyboardButton("🚨 Live Signals", callback_data="signals"),
            InlineKeyboardButton("🔥 Hot Tokens", callback_data="hot"),
        ],
        [
            InlineKeyboardButton("📩 Daily Digest", callback_data="digest"),
            InlineKeyboardButton("📊 Track Record", callback_data="track"),
        ],
        [InlineKeyboardButton(f"💎 Upgrade Pro (${PRICE_USDT:.0f} USDT/mo)", callback_data="upgrade")],
    ]
    return InlineKeyboardMarkup(buttons)


def paging_keyboard(kind: str, page: int, has_prev: bool, has_next: bool):
    """
    分页键盘：◀️ Prev / ▶️ Next / 🔄 Refresh / 🏠 Menu
    kind: 'hot' 或 'signals'，callback_data 形如 hot_page:1 / signals_page:0 / hot_refresh / menu
    无上/下一页时该按钮不显示（避免越界与误点）。
    """
    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"{kind}_page:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton("▶️ Next", callback_data=f"{kind}_page:{page + 1}"))

    rows = []
    if nav:
        rows.append(nav)
    rows.append([
        InlineKeyboardButton("🔄 Refresh", callback_data=f"{kind}_refresh"),
        InlineKeyboardButton("🏠 Menu", callback_data="menu"),
    ])
    return InlineKeyboardMarkup(rows)


# ============================================================
# 渲染辅助（命令与按钮共用，免费/Pro 分层）
# ============================================================

# Free 锁定提示（统一文案）
FREE_SIGNALS_LOCK = (
    "\n🔒 _Pro unlocks wallet labels, tx links, exact entries, "
    "and full signal context._\n"
    "💎 Upgrade to Pro → /upgrade"
)
FREE_HOT_LOCK = (
    "\n🔒 _Pro unlocks full leaderboard, pagination, refresh, "
    "and smart money context._\n"
    "💎 Upgrade to Pro → /upgrade"
)
FREE_DIGEST_LOCK = (
    "\n🔒 _Pro unlocks full daily digest and smart money context._\n"
    "💎 Upgrade to Pro → /upgrade"
)
# 公开 DEX 数据来源标注（诚实标注，绝不伪装成 smart money）
FALLBACK_NOTE = (
    "\n_Public DEX fallback data is not counted in Track Record._\n"
    "_Smart Money signals will appear here when detected._"
)

# Live Alpha Radar fallback 头部：先诚实说明无 smart money，再标注 Early Radar
ALPHA_RADAR_FALLBACK_HEAD = (
    "🟢 Smart Money Signals\n"
    "No confirmed smart wallet buys detected in the current window.\n\n"
    "🟡 Early Radar\n"
    "Showing public DEX activity while Smart Money signals are being collected.\n\n"
    "Important:\n"
    "Public DEX fallback data is not counted in Track Record.\n"
)



def render_signals_paged(tier: str, page: int = 0, force_refresh: bool = False) -> dict:
    """
    🚨 Live Signals with pagination + Free/Pro 分层。

    - Pro (paid/trial): 标题 "Pro Signal View"，有 smart money 时展示完整信号；
      无 smart money 时回退公开 DEX，明确标注来源；可正常翻页。
    - Free: 标题 "Public Market Preview"，最多 3 条，不展示 label/tx/entry，
      底部加锁定提示；不允许翻页（has_next 永远 False）。
    """
    is_pro = tier in ("paid", "trial")

    try:
        result = scan_smart_money()
        txs = result.get("txs", []) or []
    except Exception:
        txs = []

    # 有真实聪明钱信号 → 优先展示（🟢 Smart Money Signals，真实可计入 Track Record）
    if txs:
        per_page = SIGNALS_PER_PAGE if is_pro else 3
        shown = txs[:per_page]
        if is_pro:
            lines = ["🚨 *Live Alpha Radar*\n\n🟢 *Smart Money Signals*\n"]
            for tx in shown:
                lines.append(format_smart_alert(tx, tier=tier))
                lines.append("—" * 6)
            return {"text": "\n".join(lines), "has_prev": False,
                    "has_next": False, "page": 0}
        # Free：脱敏预览（format_smart_alert free 分支已去 label/tx/entry）
        lines = ["🚨 *Live Alpha Radar · Preview*\n\n🟢 *Smart Money Signals*\n"]
        for tx in shown:
            lines.append(format_smart_alert(tx, tier="free"))
            lines.append("—" * 6)
        lines.append(FREE_SIGNALS_LOCK)
        return {"text": "\n".join(lines), "has_prev": False,
                "has_next": False, "page": 0}

    # 聪明钱为空 → Live Alpha Radar fallback：明确分 🟢 Smart Money(空) + 🟡 Early Radar(公开DEX)
    if is_pro:
        pg = render_public_signals_page(page=page, per_page=SIGNALS_PER_PAGE,
                                        force_refresh=force_refresh)
        if pg["text"]:
            base = f"🚨 *Live Alpha Radar*\n\n{ALPHA_RADAR_FALLBACK_HEAD}\n{pg['text']}"
            return {"text": base, "has_prev": pg["has_prev"],
                    "has_next": pg["has_next"], "page": pg["page"]}
        base = (
            "🚨 *Live Alpha Radar*\n\n"
            "🟢 Smart Money Signals\n"
            "No confirmed smart wallet buys detected in the current window.\n\n"
            "🟡 Early Radar\n"
            "No public DEX activity available right now. Please try again later."
        )
        return {"text": base, "has_prev": False, "has_next": False, "page": 0}

    # Free：只给第一页 preview（最多 3 条），不翻页
    pg = render_public_signals_page(page=0, per_page=3,
                                    force_refresh=force_refresh)
    if pg["text"]:
        base = (f"🚨 *Live Alpha Radar · Preview*\n\n"
                f"{ALPHA_RADAR_FALLBACK_HEAD}\n{pg['text']}{FREE_SIGNALS_LOCK}")
        return {"text": base, "has_prev": False, "has_next": False, "page": 0}

    base = (
        "🚨 *Live Alpha Radar · Preview*\n\n"
        "🟢 Smart Money Signals\n"
        "No confirmed smart wallet buys detected in the current window."
        f"{FREE_SIGNALS_LOCK}"
    )
    return {"text": base, "has_prev": False, "has_next": False, "page": 0}




def render_signals(tier: str) -> str:
    """Backward-compatible single-block render (no keyboard)."""
    return render_signals_paged(tier)["text"]



def render_hot_paged(tier: str, page: int = 0, force_refresh: bool = False) -> dict:
    """
    🔥 Hot Tokens with pagination.

    Smart money heat first; if empty, fall back to real public DEX trending
    tokens (paged). Returns {"text","has_prev","has_next","page"}.
    """
    is_pro = tier in ("paid", "trial")

    try:
        scan_smart_money()
        hot_tokens = get_hot_tokens(limit=HEAT_TOP_N)
        leaderboard = get_leaderboard(limit=10)
    except Exception:
        hot_tokens, leaderboard = [], []

    # Hot Tokens Radar 副标题（统一）
    radar_head = (
        "🔥 *Hot Tokens Radar*\n"
        "_Ranked by early activity, public DEX movement, and smart wallet "
        "confirmation when available._\n"
    )

    # 聪明钱榜单为空 → 回退到真实公开 DEX 热门代币（每条已标注 🟡 Early Radar / Pending）
    if not hot_tokens:
        if is_pro:
            pg = render_public_hot_page(page=page, per_page=HOT_PER_PAGE,
                                        force_refresh=force_refresh)
            if pg["text"]:
                base = f"{radar_head}\n{pg['text']}{FALLBACK_NOTE}"
                return {"text": base, "has_prev": pg["has_prev"],
                        "has_next": pg["has_next"], "page": pg["page"]}
            base = (
                f"{radar_head}\n"
                "No data right now. Smart wallet confirmation appears once smart money becomes active."
                f"{FALLBACK_NOTE}"
            )
            return {"text": base, "has_prev": False, "has_next": False, "page": 0}

        # Free：只给第一页 preview（最多 3 条），不翻页
        pg = render_public_hot_page(page=0, per_page=3, force_refresh=force_refresh)
        if pg["text"]:
            head = f"{radar_head} _(Preview)_\n\n"
            base = f"{head}{pg['text']}{FALLBACK_NOTE}{FREE_HOT_LOCK}"
            return {"text": base, "has_prev": False, "has_next": False, "page": 0}
        base = (
            f"{radar_head} _(Preview)_\n\n"
            "No data right now."
            f"{FREE_HOT_LOCK}"
        )
        return {"text": base, "has_prev": False, "has_next": False, "page": 0}

    # 有真实聪明钱热度 → 每条标注 🟢 Smart Money Signal / Confirmed
    top_n = HEAT_TOP_N if is_pro else 3
    suffix = "" if is_pro else " _(Preview)_"
    lines = [f"{radar_head}{suffix}\n"]
    for i, t in enumerate(hot_tokens[:top_n], 1):
        symbol = t["token_symbol"] or "?"
        ce = CHAINS.get(t.get("chain", "ethereum"), {}).get("emoji", "📊")
        lines.append(
            f"{i}. {ce} *{symbol}* — 🔥{t['heat_score']}\n"
            f"   Signal Level: 🟢 Smart Money Signal\n"
            f"   Why it matters: Tracked smart wallet activity detected.\n"
            f"   Source: Tracked smart wallet\n"
            f"   Smart wallet confirmation: Confirmed"
        )


    if is_pro:
        total_activity = sum(t["wallet_count"] for t in hot_tokens)
        lines.append(f"\n📊 Total activity: {total_activity} smart money trades")
        if leaderboard:
            lines.append("\n🏆 *Smart Money Top5*")
            cat_emoji = {"mm": "🏦", "vc": "💰", "trader": "🧠", "exchange": "🏦", "unknown": "❓"}
            for w in leaderboard[:5]:
                emoji = cat_emoji.get(w.get("category", ""), "🧠")
                lines.append(f"  {emoji} {w['nickname']} — ⭐{w['score']}")
    else:
        lines.append(FREE_HOT_LOCK)
    return {"text": "\n".join(lines), "has_prev": False,
            "has_next": False, "page": 0}



def render_hot(tier: str) -> str:
    """Backward-compatible single-block render (no keyboard)."""
    return render_hot_paged(tier)["text"]



def render_digest(tier: str) -> str:
    """📩 Daily Digest：免费看摘要，Pro 看完整。"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = get_daily_digest(today)

    if not digest:
        try:
            result = scan_smart_money()
            if result.get("aggr"):
                d = result["aggr"].generate_digest()
                save_daily_digest(today, d)
                digest = get_daily_digest(today)
        except Exception:
            digest = None

    is_pro = tier in ("paid", "trial")

    if not digest:
        # 聪明钱日报为空 → 回退到真实公开 DEX 热门代币概览（GeckoTerminal/DexScreener）
        public = render_public_hot(limit=5 if is_pro else 3)
        if public:
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            base = (
                f"📩 *Daily Digest · {today_str}*\n\n"
                "_No clear smart money moves today. Here's a live market heat overview:_\n\n"
                f"{public}"
                f"{FALLBACK_NOTE}"
            )
            if not is_pro:
                base += FREE_DIGEST_LOCK
            return base

        base = (
            "📩 *Daily Digest*\n\n"
            "No clear smart money moves today. The digest is generated once smart money becomes active."
        )
        if not is_pro:
            base += FREE_DIGEST_LOCK
        return base

    message = digest.get("message", "")

    if is_pro:
        return f"📩 *Daily Alpha Digest · {today}*\n{message}"

    # 免费：只给摘要首段 + 升级引导
    preview = message.strip().split("\n\n")[0] if message else ""
    return (
        f"📩 *Daily Alpha Digest · {today}*\n\n"
        f"{preview}\n"
        f"{FREE_DIGEST_LOCK}"
    )




def render_track() -> str:
    """📊 Track Record：透明真实战绩页，零 mock 战绩，公开 DEX fallback 不计入。"""
    return (
        "📊 *Track Record*\n\n"
        "We only track real Smart Money signals sent by this bot.\n\n"
        "Public DEX fallback data is excluded.\n"
        "No fake wins.\n"
        "No cherry-picked results.\n\n"
        "Current status:\n"
        "Track record is being built.\n\n"
        "Once enough real Smart Money signals are sent, this page will show:\n"
        "• Token\n"
        "• Chain\n"
        "• Signal time\n"
        "• Entry price\n"
        "• 6h move\n"
        "• 24h move\n"
        "• Wins and losses\n"
        "• Full transparent history\n\n"
        "This page will stay empty until real Smart Money signals exist."
    )



# Pro 解锁清单（统一文案 · Founding Pro Alpha Radar）
_PRO_UNLOCKS = (
    "Pro unlocks:\n"
    "• Full Alpha Radar\n"
    "• More token opportunities\n"
    "• Smart Money signals when detected\n"
    "• Early Radar from public DEX activity\n"
    "• Signal level labels\n"
    "• Wallet details when Smart Money is available\n"
    "• Transaction links when available\n"
    "• Full Hot Tokens Radar\n"
    "• Daily Digest\n"
    "• Real Track Record as it builds"
)

# 透明声明（统一文案，所有付费页都带上，避免被指控伪造 alpha）
_TRANSPARENCY = (
    "Transparency:\n"
    "We do not fake alpha.\n"
    "Public DEX fallback data is clearly labeled.\n"
    "Track Record only includes real Smart Money signals sent by this bot."
)



def _payment_instructions() -> str:
    """付款 / 验证说明（TRON TRC20）。"""
    chain = PAYOUT_CHAIN.upper()
    return (
        "*How to pay:*\n"
        f"🔗 Chain: *{chain} (TRC20)*\n"
        "📬 Address:\n"
        f"`{PAYOUT_WALLET}`\n\n"
        f"After sending *{PRICE_USDT:.0f} USDT*, verify with:\n"
        "`/verify <your_wallet_address>`\n\n"
        "_(use the wallet address you paid from)_"
    )


def render_upgrade(user: dict | None = None) -> str:
    """
    💎 Founding Pro 销售页，按用户状态分支：
    - paid : 已是 Pro，不展示强付款文案
    - trial: 提示试用剩余 + Founding Pro 续费引导 + 透明声明
    - free / expired（或 user=None）: 完整 Founding Pro 升级页
    """
    status = (user or {}).get("status")

    # 已付费：不再催付款
    if status == "paid":
        return (
            "✅ *You are already Pro.*\n\n"
            "Your Founding Pro access is active.\n"
            "You will continue receiving full Alpha Radar access."
        )

    # 试用中：说明 trial = Pro，并引导 Founding Pro 续费
    if status == "trial":
        return (
            "💎 *Pro Trial Active*\n\n"
            "Your Pro Trial is active.\n"
            f"Time left: *{_trial_time_left(user)}*\n\n"
            "You have full Alpha Radar access during trial.\n\n"
            "Continue with Founding Pro:\n"
            f"*{PRICE_USDT:.0f} USDT / month*\n\n"
            f"{_TRANSPARENCY}"
        )

    # Free / expired / 未知：完整 Founding Pro 升级页
    return (
        "💎 *Founding Pro*\n\n"
        "An early alpha radar for on-chain traders.\n\n"
        "Get early access to Whale Wallet Tracker Pro.\n\n"
        "What it watches:\n"
        "• Smart wallet activity\n"
        "• Early DEX movers\n"
        "• Unusual token volume\n"
        "• Hot tokens before broader attention\n"
        "• Real signal performance as track record builds\n\n"
        f"{_PRO_UNLOCKS}\n\n"
        "Founding price:\n"
        f"*{PRICE_USDT:.0f} USDT / month*\n"
        "_For early founding users._\n\n"
        f"{_TRANSPARENCY}\n\n"
        f"{_payment_instructions()}"
    )






# ============================================================
# 命令处理
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alpha Intelligence 首页 + 5 键菜单"""
    user = update.effective_user
    user_data = upsert_user(str(user.id), user.username or user.full_name)

    welcome = (
        "🐋 *Whale Wallet Tracker*\n\n"
        "An early alpha radar for on-chain traders.\n\n"
        "We track smart wallets, early DEX movers, unusual token volume, "
        "and hot tokens before broader attention.\n\n"
        "Smart Money signals show when detected. When none are confirmed, "
        "we show Early Radar from public DEX activity — always clearly labeled.\n\n"
        "Free users get a limited preview.\n"
        "Pro users unlock the full Alpha Radar.\n\n"
        "Choose an option below."
    )


    await update.message.reply_text(
        with_status_bar(user_data, welcome),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(user_data["status"]),
        disable_web_page_preview=True,
    )



# ============================================================
# Alpha Intelligence 命令（5 键菜单对应）
# ============================================================

async def cmd_signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🚨 Live Signals（分页）"""
    user = upsert_user(str(update.effective_user.id), update.effective_user.username or "")
    # signals 需扫描链上聪明钱 + 回退公开 DEX，耗时较长：先发加载占位，渲染完再就地替换
    loading = await update.message.reply_text(
        "🚨 Loading live signals...\n\nScanning smart money & market data, please wait...",
        disable_web_page_preview=True,
    )
    res = render_signals_paged(tier_of(user), page=0)
    await loading.edit_text(
        with_status_bar(user, res["text"]),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=paging_keyboard("signals", res["page"], res["has_prev"], res["has_next"]),
        disable_web_page_preview=True,
    )




async def cmd_hot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🔥 Hot Tokens（分页）"""
    user = upsert_user(str(update.effective_user.id), update.effective_user.username or "")
    res = render_hot_paged(tier_of(user), page=0)
    await update.message.reply_text(
        with_status_bar(user, res["text"]),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=paging_keyboard("hot", res["page"], res["has_prev"], res["has_next"]),
        disable_web_page_preview=True,
    )




async def cmd_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📊 Track Record（纯静态，无 mock 战绩）"""
    user = upsert_user(str(update.effective_user.id), update.effective_user.username or "")
    await update.message.reply_text(
        with_status_bar(user, render_track()),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(user["status"]),
        disable_web_page_preview=True,
    )


async def cmd_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """💎 Upgrade Pro · Founding Pro"""
    user = upsert_user(str(update.effective_user.id), update.effective_user.username or "")
    await update.message.reply_text(
        with_status_bar(user, render_upgrade(user)),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(user["status"]),
        disable_web_page_preview=True,
    )




async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看账户状态"""
    user_id = str(update.effective_user.id)
    user = upsert_user(user_id, update.effective_user.username or "")
    wallets = get_user_wallets(user_id)

    status_emoji = {"trial": "🆓", "paid": "💎", "expired": "⛔"}
    emoji = status_emoji.get(user["status"], "❓")

    limits = {
        "trial": f"{emoji} 免费版 · {len(wallets)}/{FREE_WALLET_LIMIT} 地址",
        "paid": f"{emoji} 付费版 · {len(wallets)}/{PAID_WALLET_LIMIT} 地址",
        "expired": f"{emoji} 已过期 · 请续费",
    }

    msg = f"""📊 *账户状态*

身份: {limits.get(user['status'], user['status'])}
用户: @{user.get('username', 'N/A')}

"""
    if user["status"] == "trial" and user.get("trial_end"):
        trial_end = datetime.fromisoformat(user["trial_end"])
        remaining = trial_end - datetime.now()
        hours = max(0, int(remaining.total_seconds() / 3600))
        msg += f"试用到期: {trial_end.strftime('%m/%d %H:%M')}\n剩余: {hours} 小时\n"

    if user["status"] == "paid" and user.get("paid_until"):
        paid_end = datetime.fromisoformat(user["paid_until"])
        remaining = paid_end - datetime.now()
        days = max(0, int(remaining.total_seconds() / 86400))
        msg += f"付费到期: {paid_end.strftime('%m/%d %H:%M')}\n剩余: {days} 天\n"

    if user["status"] == "expired":
        msg += f"💎 续费 ${PRICE_USDT} USDT/月，点击下方按钮\n"

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(user["status"]),
    )


async def cmd_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/pay → 重定向到 /upgrade（Founding Pro 收款页）"""
    await cmd_upgrade(update, context)



async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """添加追踪地址: /add <chain> <address> <label>"""
    user_id = str(update.effective_user.id)
    user = upsert_user(user_id, update.effective_user.username or "")

    if not is_user_active(user_id) and user["status"] != "trial":
        await update.message.reply_text(
            "⛔ 你的账户已过期。请先续费: /pay",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "用法: `/add <链> <地址> [标签]`\n\n"
            "链: `eth` (Ethereum), `bsc` (BSC), `trx` (Tron)\n\n"
            "例: `/add eth 0x28C6c06298d514Db089934071355E5743bf21d60 币安热钱包`\n"
            "例: `/add trx TXFkJv3VRCg9LJhvyvLCfqxGVvq3vKTL5h`",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        return

    chain_arg = context.args[0].lower()
    chain_map = {"eth": "ethereum", "bsc": "bsc", "trx": "tron"}
    chain = chain_map.get(chain_arg, chain_arg)

    if chain not in ("ethereum", "bsc", "tron"):
        await update.message.reply_text(
            f"❌ 不支持的链: `{chain_arg}`。支持: eth, bsc, trx",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    address = context.args[1].strip()
    if not validate_wallet_address(address, chain):
        auto_chain = detect_chain_from_address(address)
        if auto_chain != "unknown" and auto_chain != chain:
            await update.message.reply_text(
                f"⚠️ 此地址像是 *{auto_chain}* 链上的地址。\n"
                f"请检查链参数是否正确。",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        await update.message.reply_text(
            "❌ 地址格式无效，请检查后重试。\n"
            "ETH/BSC: 0x 开头，42 字符\n"
            "Tron: T 开头，34 字符",
        )
        return

    label = " ".join(context.args[2:]) if len(context.args) > 2 else ""

    ok, msg = add_tracked_wallet(user_id, chain, address, label)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """移除追踪地址: /remove <address>"""
    user_id = str(update.effective_user.id)

    if not context.args:
        await update.message.reply_text(
            "用法: `/remove <地址>`\n或用按钮交互操作。",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    address = context.args[0].strip()
    wallets = get_user_wallets(user_id)
    target = [w for w in wallets if w["address"].lower() == address.lower()]

    if not target:
        await update.message.reply_text("❌ 未找到该地址。用 /list 查看列表。")
        return

    w = target[0]
    remove_tracked_wallet(user_id, w["chain"], w["address"])
    await update.message.reply_text(
        f"✅ 已移除: `{w['address'][:10]}...` ({w['chain']})",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """列出追踪的钱包"""
    user_id = str(update.effective_user.id)
    user = upsert_user(user_id, update.effective_user.username or "")
    wallets = get_user_wallets(user_id)

    if not wallets:
        limits = {"trial": FREE_WALLET_LIMIT, "paid": PAID_WALLET_LIMIT}
        limit = limits.get(user["status"], FREE_WALLET_LIMIT)
        await update.message.reply_text(
            f"📋 尚未添加任何追踪地址。\n上限: {limit} 个地址\n用 /add 添加。",
            reply_markup=main_menu_keyboard(user["status"]),
        )
        return

    chain_emoji = {"ethereum": "🔷", "bsc": "🟡", "tron": "🔴"}
    msg_parts = ["📋 *我的追踪列表*\n"]

    for w in wallets:
        emoji = chain_emoji.get(w["chain"], "🔗")
        label = f" · {w['label']}" if w.get("label") else ""
        msg_parts.append(
            f"{emoji} `{w['address'][:10]}...{w['address'][-6:]}`{label}\n"
            f"   链: {w['chain']} | 添加: {w['created_at'][:10]}"
        )

    limits = {"trial": FREE_WALLET_LIMIT, "paid": PAID_WALLET_LIMIT}
    limit = limits.get(user["status"], FREE_WALLET_LIMIT)
    msg_parts.append(f"\n{len(wallets)}/{limit} 个地址")

    await update.message.reply_text(
        "\n".join(msg_parts),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(user["status"]),
        disable_web_page_preview=True,
    )


async def cmd_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """验证支付: /verify <付款钱包地址>"""
    user_id = str(update.effective_user.id)
    user = upsert_user(user_id, update.effective_user.username or "")

    if not context.args:
        await update.message.reply_text(
            "Usage: `/verify <your_payment_wallet_address>`\n"
            f"We'll check whether that address sent ${PRICE_USDT} USDT to our payout address.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    wallet = context.args[0].strip()
    chain = detect_chain_from_address(wallet)
    if chain == "unknown":
        await update.message.reply_text("❌ Invalid address format. Tron (starts with T) and EVM (starts with 0x) are supported.")
        return

    await update.message.reply_text("🔍 Checking on-chain payment records...")

    result = check_payment(wallet, chain)

    if result.get("found"):
        amount = result["amount"]
        tx_hash = result.get("tx_hash", "")
        activate_paid(user_id)

        from models import get_conn
        conn = get_conn()
        conn.execute(
            "UPDATE users SET wallet_address = ?, wallet_chain = ?, payment_tx_hash = ? WHERE user_id = ?",
            (wallet, chain, tx_hash, user_id),
        )
        conn.commit()
        conn.close()

        await update.message.reply_text(
            f"✅ *Payment verified!*\n\n"
            f"💰 Received: {amount:.2f} USDT\n"
            f"🔗 TX: `{tx_hash[:20]}...`\n"
            f"📅 Valid until: {datetime.now().strftime('%m/%d %H:%M')}\n\n"
            f"You can now use /add to track more wallets!",
            parse_mode=ParseMode.MARKDOWN,
        )
    elif result.get("error"):
        await update.message.reply_text(
            f"⚠️ Check failed: {result['error']}\nPlease try again later or contact support."
        )
    else:
        await update.message.reply_text(
            "❌ No payment record found.\n\n"
            "Please confirm:\n"
            f"• You sent ≥ {PRICE_USDT} USDT to `{PAYOUT_WALLET[:10]}...`\n"
            "• You used the correct chain (Tron TRC20)\n"
            "• The transaction is confirmed on-chain\n\n"
            "Then retry: `/verify <your_payment_address>`"
        )



async def cmd_alpha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/alpha → 重定向到 /hot（Hot Tokens 兼容入口）"""
    await cmd_hot(update, context)


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📩 Daily Digest（免费看摘要，Pro 看完整）"""
    user = upsert_user(str(update.effective_user.id), update.effective_user.username or "")
    await update.message.reply_text(
        with_status_bar(user, render_digest(tier_of(user))),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(user["status"]),
        disable_web_page_preview=True,
    )



async def cmd_smart_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """查看当前追踪的聪明钱地址"""
    user_id = str(update.effective_user.id)
    user = upsert_user(user_id, update.effective_user.username or "")

    wallets = get_all_smart_wallets()

    if not wallets:
        await update.message.reply_text(
            "🧠 当前没有追踪的聪明钱地址。",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    cat_emoji = {"mm": "🏦 做市商", "vc": "💰 VC", "trader": "🧠 交易员",
                 "exchange": "🏦 交易所", "unknown": "❓"}

    msg_lines = [f"🧠 *追踪的聪明钱 · {len(wallets)} 个*\n"]
    for w in wallets:
        chain_emoji = CHAINS.get(w.get("chain", "ethereum"), {}).get("emoji", "📊")
        cat = cat_emoji.get(w.get("category", ""), "🧠")
        score = w.get("score", 0)
        msg_lines.append(
            f"  {chain_emoji} {cat} {w['nickname']} — ⭐{score}"
        )
        addr = w.get("address", "")
        msg_lines.append(f"    `{addr[:10]}...{addr[-6:]}`")

    await update.message.reply_text(
        "\n".join(msg_lines),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员广播（仅 admin user_ids 列表）"""
    user_id = str(update.effective_user.id)

    if not ADMIN_USER_IDS:
        await update.message.reply_text(
            "⚠️ 未配置管理员。请在 .env 里设置 ADMIN_USER_IDS。"
        )
        return

    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("⛔ 无权限。")
        return

    if not context.args:
        await update.message.reply_text("用法: /broadcast <消息>")
        return

    msg_text = " ".join(context.args)
    all_users = get_all_active_users()
    sent = 0

    for user in all_users:
        try:
            await context.bot.send_message(
                chat_id=user["user_id"],
                text=f"📢 *系统通知*\n\n{msg_text}",
                parse_mode=ParseMode.MARKDOWN,
            )
            sent += 1
            await asyncio.sleep(0.5)  # rate limit
        except Exception:
            pass

    await update.message.reply_text(f"✅ 已发送给 {sent}/{len(all_users)} 个用户。")


# ============================================================
# 回调处理
# ============================================================

async def _safe_edit(query, text: str, reply_markup=None):
    """
    安全地 edit_message_text：
    - 翻页/刷新时若内容与当前完全一致，Telegram 会抛 "message is not modified"，
      这里吞掉该错误，避免按钮点击报错。
    - 其它异常也兜底，不让回调崩溃。
    """
    try:
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except Exception as e:
        msg = str(e).lower()
        if "not modified" in msg:
            return  # 内容没变（如刷新后数据一致），静默忽略
        # 其它错误：尝试无 markdown 再发一次，最终失败则忽略
        try:
            await query.edit_message_text(text, reply_markup=reply_markup,
                                          disable_web_page_preview=True)
        except Exception:
            pass


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """处理按钮点击"""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    user = upsert_user(user_id, query.from_user.username or "")
    data = query.data

    if data == "status":
        wallets = get_user_wallets(user_id)
        chain_emoji = {"ethereum": "🔷", "bsc": "🟡", "tron": "🔴"}

        wallet_lines = []
        for w in wallets:
            emoji = chain_emoji.get(w["chain"], "🔗")
            wallet_lines.append(f"  {emoji} {w['address'][:10]}...")

        status_text = {
            "trial": f"🆓 免费试用 (剩余 {3 - (datetime.now() - datetime.fromisoformat(user['trial_start'])).days:.0f} 天)",
            "paid": f"💎 付费用户 (至 {datetime.fromisoformat(user['paid_until']).strftime('%m/%d')})" if user.get("paid_until") else "💎 付费用户",
            "expired": "⛔ 已过期 · 请续费",
        }

        msg = f"📊 *账户状态*\n\n{status_text.get(user['status'], user['status'])}\n"
        if wallet_lines:
            msg += "\n追踪地址:\n" + "\n".join(wallet_lines)
        else:
            msg += "\n暂未添加追踪地址。"
        msg += f"\n\n价格: ${PRICE_USDT} USDT/月"

        await query.edit_message_text(
            msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(user["status"]),
        )

    elif data == "menu":
        # 🏠 返回主菜单
        await query.edit_message_text(
            "👇 Choose an option:",
            reply_markup=main_menu_keyboard(user["status"]),
            disable_web_page_preview=True,
        )

    elif data == "signals" or data == "signals_refresh" or data.startswith("signals_page:"):
        # Live Signals：首次打开 / 翻页 / 刷新（refresh 绕过缓存）
        is_pro = tier_of(user) in ("paid", "trial")
        page = 0
        force = False
        if data.startswith("signals_page:"):
            # Free 用户无翻页权限：阻止通过手动 callback 绕过限制
            if not is_pro:
                await query.answer("Full pagination is available on Pro.", show_alert=True)
                return
            try:
                page = max(0, int(data.split(":", 1)[1]))
            except ValueError:
                page = 0
        elif data == "signals_refresh":
            force = True
        # signals 渲染要扫链 + 拉公开 DEX，耗时较长：首次打开时先就地显示加载占位
        if data == "signals":
            await _safe_edit(
                query,
                "🚨 Loading live signals...\n\nScanning smart money & market data, please wait...",
            )
        try:
            res = render_signals_paged(tier_of(user), page=page, force_refresh=force)
        except Exception:
            res = {"text": REFRESH_FAIL_MSG, "has_prev": False, "has_next": False, "page": 0}
        await _safe_edit(
            query, with_status_bar(user, res["text"]),
            paging_keyboard("signals", res["page"], res["has_prev"], res["has_next"]),
        )


    elif data in ("hot", "alpha") or data == "hot_refresh" or data.startswith("hot_page:"):
        # Hot Tokens：首次打开 / 翻页 / 刷新（refresh 绕过缓存）
        is_pro = tier_of(user) in ("paid", "trial")
        page = 0
        force = False
        if data.startswith("hot_page:"):
            # Free 用户无翻页权限：阻止通过手动 callback 绕过限制
            if not is_pro:
                await query.answer("Full pagination is available on Pro.", show_alert=True)
                return
            try:
                page = max(0, int(data.split(":", 1)[1]))
            except ValueError:
                page = 0
        elif data == "hot_refresh":
            force = True
        try:
            res = render_hot_paged(tier_of(user), page=page, force_refresh=force)
        except Exception:
            res = {"text": REFRESH_FAIL_MSG, "has_prev": False, "has_next": False, "page": 0}
        await _safe_edit(
            query, with_status_bar(user, res["text"]),
            paging_keyboard("hot", res["page"], res["has_prev"], res["has_next"]),
        )


    elif data == "digest":
        await query.edit_message_text(
            with_status_bar(user, render_digest(tier_of(user))),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(user["status"]),
            disable_web_page_preview=True,
        )

    elif data == "track":
        await query.edit_message_text(
            with_status_bar(user, render_track()),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(user["status"]),
            disable_web_page_preview=True,
        )

    elif data in ("upgrade", "pay"):
        await query.edit_message_text(
            with_status_bar(user, render_upgrade(user)),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(user["status"]),
            disable_web_page_preview=True,
        )


    elif data == "list":
        wallets = get_user_wallets(user_id)
        if not wallets:
            await query.edit_message_text(
                "📋 暂无追踪地址。用 /add 添加。",
                reply_markup=main_menu_keyboard(user["status"]),
            )
            return

        chain_emoji = {"ethereum": "🔷", "bsc": "🟡", "tron": "🔴"}
        lines = ["📋 *追踪列表*\n"]
        for w in wallets:
            emoji = chain_emoji.get(w["chain"], "🔗")
            label = f" - {w['label']}" if w.get("label") else ""
            lines.append(f"{emoji} `{w['address'][:10]}...`{label}")

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(user["status"]),
            disable_web_page_preview=True,
        )

    elif data == "add_help":
        await query.edit_message_text(
            "➕ *添加追踪地址*\n\n"
            "格式: `/add <链> <地址> [标签]`\n\n"
            "链: `eth` · `bsc` · `trx`\n\n"
            "例:\n"
            "`/add eth 0x28C6c... 币安热钱包`\n"
            "`/add trx TXFkJv3... 孙宇晨`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 返回", callback_data="status")
            ]]),
        )

    elif data == "remove_help":
        wallets = get_user_wallets(user_id)
        if not wallets:
            await query.edit_message_text(
                "📋 暂无追踪地址。用 /add 添加。",
                reply_markup=main_menu_keyboard(user["status"]),
            )
            return

        buttons = []
        for w in wallets[:20]:  # 最多20个
            label = w.get("label") or w["address"][:10] + "..."
            buttons.append([InlineKeyboardButton(
                f"❌ {label} ({w['chain']})",
                callback_data=f"rm_{w['chain']}_{w['address'][:20]}"
            )])
        buttons.append([InlineKeyboardButton("🔙 返回", callback_data="status")])

        await query.edit_message_text(
            "🗑 点击要移除的地址:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif data.startswith("rm_"):
        parts = data.split("_", 2)
        if len(parts) == 3:
            chain = parts[1]
            addr_prefix = parts[2]
            wallets = get_user_wallets(user_id)
            target = [w for w in wallets if w["chain"] == chain and w["address"].startswith(addr_prefix)]
            if target:
                w = target[0]
                remove_tracked_wallet(user_id, w["chain"], w["address"])
                await query.edit_message_text(
                    f"✅ 已移除: {w['address'][:10]}...",
                    reply_markup=main_menu_keyboard(user["status"]),
                )
            else:
                await query.edit_message_text(
                    "⚠️ 未找到该地址。",
                    reply_markup=main_menu_keyboard(user["status"]),
                )


async def handle_verify_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理纯文本地址验证（用户直接发付款地址）"""
    user_id = str(update.effective_user.id)
    user = upsert_user(user_id, update.effective_user.username or "")

    if user["status"] == "paid":
        await update.message.reply_text("💎 You're already a Pro user!")
        return

    text = update.message.text.strip()
    chain = detect_chain_from_address(text)

    if chain == "unknown":
        # 不是钱包地址：弹出主菜单，方便用户无需 /start 即可看到功能入口
        await update.message.reply_text(
            "👇 Choose an option:",
            reply_markup=main_menu_keyboard(user["status"]),
            disable_web_page_preview=True,
        )
        return

    await update.message.reply_text("🔍 Wallet address detected. Checking on-chain payment records...")

    result = check_payment(text, chain)

    if result.get("found"):
        activate_paid(user_id)
        from models import get_conn
        conn = get_conn()
        conn.execute(
            "UPDATE users SET wallet_address = ?, wallet_chain = ?, payment_tx_hash = ? WHERE user_id = ?",
            (text, chain, result.get("tx_hash", ""), user_id),
        )
        conn.commit()
        conn.close()

        await update.message.reply_text(
            f"✅ *Payment verified!*\nReceived {result['amount']:.2f} USDT\nValid for: {SUBSCRIPTION_DAYS} days",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            "❌ No payment record found.\nPlease retry using your *payment wallet address*.",
            parse_mode=ParseMode.MARKDOWN,
        )



# ============================================================
# 监控循环
# ============================================================

async def monitoring_loop(app: Application):
    """后台监控循环：定期扫描链上数据并推送（鲸鱼追踪）"""
    print("🐋 Whale monitoring loop started...")
    while True:
        try:
            results = scan_all_chains()
            if results:
                print(f"[{datetime.now():%H:%M:%S}] Found {len(results)} new whale moves")

            for tx in results:
                user_id = tx.pop("user_id")
                tracked_addr = tx.pop("tracked_address")

                alert = format_alert({**tx, "tracked_address": tracked_addr})

                try:
                    await app.bot.send_message(
                        chat_id=user_id,
                        text=alert,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True,
                    )
                    save_tx_history(
                        user_id=user_id,
                        chain=tx["chain"],
                        tx_hash=tx["tx_hash"],
                        from_addr=tx["from"],
                        to_addr=tx["to"],
                        token=tx["token"],
                        amount=tx["amount"],
                        usd_value=tx["usd_value"],
                    )
                    await asyncio.sleep(0.3)  # rate limit
                except Exception as e:
                    print(f"  Push error for user {user_id}: {e}")

        except Exception as e:
            print(f"Whale scan error: {e}")
            traceback.print_exc()

        await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)


async def smart_money_loop(app: Application):
    """聪明钱 Alpha 信号扫描 + 热度榜入库"""
    print("🧠 Smart money Alpha loop started...")
    while True:
        try:
            print(f"[{datetime.now():%H:%M:%S}] Scanning smart money...")
            result = scan_smart_money()

            txs = result.get("txs", [])
            if txs:
                print(f"  Found {len(txs)} smart money moves")

                # 推送给所有活跃用户（按 tier 分层：Free 脱敏，Pro 全量）
                active_users = get_all_active_users()
                for tx in txs:
                    for user in active_users:
                        tier = tier_of(user)
                        msg = format_smart_alert(tx, tier=tier)
                        try:
                            await app.bot.send_message(
                                chat_id=user["user_id"],
                                text=msg,
                                parse_mode=ParseMode.MARKDOWN,
                                disable_web_page_preview=True,
                            )
                            await asyncio.sleep(0.15)
                        except Exception:
                            pass


            # 生成日报数据（存库，定时推送用）
            if result.get("aggr"):
                digest = result["aggr"].generate_digest()
                save_daily_digest(digest["date"], digest)

            print(f"  Smart money scan complete. Hot tokens: {len(get_hot_tokens(limit=HEAT_TOP_N))}")

        except Exception as e:
            print(f"Smart money scan error: {e}")
            traceback.print_exc()

        # 每 5 分钟扫一次
        await asyncio.sleep(300)


async def digest_push_loop(app: Application):
    """每日定时推送 Alpha 日报给所有活跃用户"""
    print(f"📊 Digest push loop started (target: {DIGEST_HOUR_UTC}:00 UTC)...")
    while True:
        try:
            now = datetime.now(timezone.utc)

            # 检查是否到了推送时间（小时匹配，且今天还没推送过）
            if now.hour == DIGEST_HOUR_UTC:
                today = now.strftime("%Y-%m-%d")
                digest = get_daily_digest(today)

                if digest and not digest.get("pushed"):
                    active_users = get_all_active_users()
                    print(f"📊 Pushing daily digest to {len(active_users)} users...")

                    for user in active_users:
                        try:
                            await app.bot.send_message(
                                chat_id=user["user_id"],
                                text=f"📊 *Alpha 聪明钱日报 · {today}*\n{digest['message']}",
                                parse_mode=ParseMode.MARKDOWN,
                                disable_web_page_preview=True,
                            )
                            await asyncio.sleep(0.2)
                        except Exception:
                            pass

                    mark_digest_pushed(today)
                    print(f"📊 Daily digest pushed for {today}")

            # 每分钟检查一次
            await asyncio.sleep(60)

        except Exception as e:
            print(f"Digest push error: {e}")
            traceback.print_exc()
            await asyncio.sleep(300)


# ============================================================
# 全局错误处理
# ============================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """全局错误处理器。

    - Conflict：同一个 token 有多个实例在 getUpdates。这是部署/运维问题
      （多副本、本地与云端同时跑、重复部署未停旧实例），代码层无法根治，
      这里只做降噪日志，避免刷屏。
    - 网络类（NetworkError/TimedOut）：常见瞬时抖动，PTB 会自动重试，记一行即可。
    - 其它异常：打印完整 traceback 方便排查。
    """
    err = context.error

    if isinstance(err, Conflict):
        print("⚠️ Conflict: 检测到另一个机器人实例正在用同一 token 轮询。"
              "请确认只有一个实例在运行（Railway 副本数=1，且未在本地同时运行）。")
        return

    if isinstance(err, (NetworkError, TimedOut)):
        print(f"🌐 网络瞬时错误（将自动重试）: {err}")
        return

    print(f"❌ 未处理异常: {err}")
    traceback.print_exception(type(err), err, err.__traceback__)


# ============================================================
# Main
# ============================================================

def main():
    if not TG_BOT_TOKEN:
        print("❌ 请设置环境变量 TG_BOT_TOKEN")
        sys.exit(1)

    if not PAYOUT_WALLET:
        print("⚠️ 未设置 PAYOUT_WALLET，支付功能不可用")

    init_db()
    print(f"🐋 Whale Tracker Bot starting...")

    # 启动时导入内置聪明钱种子地址（幂等：已存在则跳过/合并），
    # 让 /signals /hot /digest 扫描有真实地址可用。失败不阻塞启动。
    try:
        conn = get_conn()
        inserted, skipped = seed_database(conn)
        conn.close()
        print(f"🌱 Seed smart wallets: {inserted} inserted, {skipped} skipped.")
    except Exception as e:
        print(f"⚠️ Seed smart wallets skipped (non-fatal): {e}")

    async def post_init(application: Application):
        # 注册斜杠命令菜单（输入框旁蓝色 Menu 按钮），用户无需记命令即可点选。
        # 仅暴露 5 个主功能 + /start，旧钱包命令不进菜单。
        try:
            await application.bot.set_my_commands([
                BotCommand("start", "🏠 Home / 主菜单"),
                BotCommand("signals", "🚨 Live Signals"),
                BotCommand("hot", "🔥 Hot Tokens"),
                BotCommand("digest", "📩 Daily Digest"),
                BotCommand("track", "📊 Track Record"),
                BotCommand("upgrade", "💎 Upgrade Pro"),
            ])
            await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            print("✅ Bot commands & menu button registered.")
        except Exception as e:
            print(f"⚠️ set_my_commands skipped (non-fatal): {e}")

        # 在 run_polling 创建的事件循环中启动后台协程
        # 用 asyncio.create_task（而非 application.create_task）：这些是常驻后台循环，
        # 随进程生命周期运行，不需要 PTB 在关闭时 await，避免 PTBUserWarning。
        asyncio.create_task(monitoring_loop(application))   # 鲸鱼追踪
        asyncio.create_task(smart_money_loop(application))  # 聪明钱 Alpha
        asyncio.create_task(digest_push_loop(application))  # 每日日报推送
        print("✅ Background loops scheduled (Whale + Smart Money + Digest).")


    builder = Application.builder().token(TG_BOT_TOKEN).post_init(post_init)
    if TG_PROXY:
        # 国内网络通过本地代理访问 Telegram；同时给主请求和 get_updates 长轮询挂代理
        builder = builder.proxy(TG_PROXY).get_updates_proxy(TG_PROXY)
        print(f"🌐 Using proxy: {TG_PROXY}")
    app = builder.build()

    # 命令 · Alpha Intelligence 主菜单（5 键）
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("signals", cmd_signals))   # 🚨 Live Signals
    app.add_handler(CommandHandler("hot", cmd_hot))           # 🔥 Hot Tokens
    app.add_handler(CommandHandler("digest", cmd_digest))     # 📩 Daily Digest
    app.add_handler(CommandHandler("track", cmd_track))       # 📊 Track Record
    app.add_handler(CommandHandler("upgrade", cmd_upgrade))   # 💎 Upgrade Pro
    # 兼容/次要命令（不在主菜单暴露）
    app.add_handler(CommandHandler("pay", cmd_pay))           # → /upgrade
    app.add_handler(CommandHandler("alpha", cmd_alpha))       # → /hot
    app.add_handler(CommandHandler("verify", cmd_verify))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("smart", cmd_smart_wallets))


    # 按钮
    app.add_handler(CallbackQueryHandler(callback_handler))

    # 文本消息（地址验证）
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_verify_message))

    # 全局错误处理器（优雅处理 Conflict / 网络抖动等）
    app.add_error_handler(error_handler)

    print("✅ Bot is running (Whale + Smart Money + Digest). Press Ctrl+C to stop.")
    # drop_pending_updates=True：启动时丢弃积压的旧 update，
    # 避免重启/重新部署后把堆积的消息一次性重放，也降低与旧实例的冲突窗口。
    app.run_polling(drop_pending_updates=True)



if __name__ == "__main__":
    main()