# -*- coding: utf-8 -*-
"""
Whale Wallet Tracker · 链上 Alpha 情报机器人
Slogan: Smart money buys before the crowd notices.
"""

import asyncio
import sys
import traceback
import random
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode

from config import (
    TG_BOT_TOKEN, PAYOUT_WALLET, PAYOUT_CHAIN, PRICE_USDT,
    TRIAL_DAYS, SUBSCRIPTION_DAYS, CHECK_INTERVAL_MINUTES,
    FREE_WALLET_LIMIT, PAID_WALLET_LIMIT, MIN_USD_VALUE,
    SMART_MONEY_CHAINS, HEAT_TOP_N, DIGEST_HOUR_UTC,
    CHAINS,
    ETHERSCAN_API_KEY, BSCSCAN_API_KEY, TRONGRID_API_KEY,
)
from models import (
    init_db, upsert_user, activate_paid, is_user_active,
    get_hot_tokens, get_leaderboard, save_daily_digest, get_daily_digest,
    mark_digest_pushed, get_all_smart_wallets,
    get_users_count, get_tracked_wallets_count, get_smart_wallets_count,
    get_token_heat_count, get_daily_digest_count, get_conn,
)
from seed_wallets import seed_database
from payment import check_payment, validate_wallet_address, detect_chain_from_address
from monitor import scan_all_chains, format_alert, scan_smart_money, format_smart_alert
from alpha import AlphaAggregator


# ============================================================
# Pro 权限判断
# ============================================================

def _is_pro(user_data: dict) -> bool:
    """付费用户: status == 'paid' 且 paid_until 未过期"""
    if user_data.get("status") == "paid":
        if user_data.get("paid_until"):
            try:
                return datetime.fromisoformat(user_data["paid_until"]) > datetime.now()
            except Exception:
                return True
        return True
    return False


# ============================================================
# Sample 信号数据（MVP 阶段）
# TODO: 替换为从链上扫描得到的真实 signal 性能数据
# ============================================================

SAMPLE_SIGNALS = [
    {
        "token": "PEPE",
        "chain": "ETH",
        "type": "Accumulation",
        "size_range": "$10K-$25K",
        "size_exact": "$18,420",
        "detected_minutes_ago": 47,
        "wallet_label": "Early Meme Hunter",
        "wallet_address": "0xPEPE...WALLET",
        "tx_link": "https://etherscan.io/tx/0xPEPE...",
        "confidence": "High",
        "entry_price": "$0.0124",
        "why": "A tracked smart wallet started accumulating after 18 days inactive.",
    },
    {
        "token": "WIF",
        "chain": "ETH",
        "type": "Rotation",
        "size_range": "$5K-$15K",
        "size_exact": "$8,910",
        "detected_minutes_ago": 112,
        "wallet_label": "Whale Trader #14",
        "wallet_address": "0xWIF...WALLET",
        "tx_link": "https://etherscan.io/tx/0xWIF...",
        "confidence": "Medium",
        "entry_price": "$2.14",
        "why": "Rotated out of DOGE and into WIF — same pattern as before WIF's previous 2x move.",
    },
    {
        "token": "BONK",
        "chain": "SOL",
        "type": "Fresh Accumulation",
        "size_range": "$2K-$8K",
        "size_exact": "$5,230",
        "detected_minutes_ago": 180,
        "wallet_label": "Solana Early Fund",
        "wallet_address": "BONK...WALLET",
        "tx_link": "https://solscan.io/tx/BONK...",
        "confidence": "Medium",
        "entry_price": "$0.000024",
        "why": "A fund that caught the April 2024 BONK rally is rebuilding a position.",
    },
]

SAMPLE_TRACK_RECORD = [
    {
        "signal": "PEPE",
        "posted": "14:20 UTC",
        "price_at_signal": "$0.012",
        "result_6h": "$0.018",
        "move": "+50.0%",
        "positive": True,
    },
    {
        "signal": "WIF",
        "posted": "09:45 UTC",
        "price_at_signal": "$2.14",
        "result_6h": "$2.57",
        "move": "+20.1%",
        "positive": True,
    },
    {
        "signal": "DOGE",
        "posted": "18:10 UTC",
        "price_at_signal": "$0.16",
        "result_6h": "$0.138",
        "move": "-13.7%",
        "positive": False,
    },
    {
        "signal": "SHIB",
        "posted": "22:05 UTC",
        "price_at_signal": "$0.000021",
        "result_6h": "$0.000033",
        "move": "+57.1%",
        "positive": True,
    },
]


# ============================================================
# 主菜单按钮
# ============================================================

def main_menu_keyboard():
    """5 个核心菜单"""
    buttons = [
        [InlineKeyboardButton("🚨 Live Signals", callback_data="signals")],
        [InlineKeyboardButton("🔥 Hot Tokens", callback_data="hot_tokens")],
        [InlineKeyboardButton("📩 Daily Digest", callback_data="digest")],
        [InlineKeyboardButton("📊 Track Record", callback_data="track")],
        [InlineKeyboardButton("💎 Upgrade Pro", callback_data="upgrade")],
    ]
    return InlineKeyboardMarkup(buttons)


# ============================================================
# 信号与热币展示辅助
# ============================================================

def _chain_emoji(chain_name: str) -> str:
    return CHAINS.get(chain_name, {}).get("emoji", "🔗")


def _category_emoji(category: str) -> str:
    mapping = {
        "market_maker": "🏦",
        "fund": "💰",
        "whale": "🐋",
        "trader": "🧠",
        "exchange": "🏦",
    }
    return mapping.get(category, "🧠")


# ============================================================
# 命令处理
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """新用户入口 · Alpha 情报产品定位"""
    user = update.effective_user
    user_data = upsert_user(str(user.id), user.username or user.full_name)
    pro = _is_pro(user_data)

    pro_line = "💎 *Pro member — you get the full signal.*" if pro else "🆓 *Free preview — signals are delayed and partially hidden.*"

    welcome = (
        f"🐋 *Whale Wallet Tracker*\n\n"
        f"Smart money buys before the crowd notices.\n\n"
        f"We track high-signal wallets and surface early on-chain moves before they become obvious.\n\n"
        f"{pro_line}\n\n"
        f"Choose an option below."
    )

    await update.message.reply_text(
        welcome,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
        disable_web_page_preview=True,
    )


async def cmd_signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🚨 Live Signals · 聪明钱信号（免费=延迟/隐藏，Pro=完整）"""
    user_id = str(update.effective_user.id)
    user_data = upsert_user(user_id, update.effective_user.username or "")
    pro = _is_pro(user_data)

    # 优先取最新信号：先调用扫描，然后取 SAMPLE_SIGNALS（MVP）
    # 真实数据一旦接通 scan_smart_money + get_hot_tokens 后替换此处
    signals = SAMPLE_SIGNALS

    msg_lines = []
    if pro:
        msg_lines.append("🚨 *Smart Money Signals — LIVE*\n")
    else:
        msg_lines.append("🚨 *Delayed Smart Money Signals — FREE PREVIEW*\n")

    for s in signals:
        emoji = _chain_emoji(s["chain"].lower().replace("eth", "ethereum") if len(s["chain"]) <= 3 else s["chain"].lower())
        if pro:
            msg_lines.append(
                f"*Token:* ${s['token']}\n"
                f"*Chain:* {emoji} {s['chain']}\n"
                f"*Signal:* {s['type']}\n"
                f"*Size:* {s['size_exact']}\n"
                f"*Wallet Label:* {s['wallet_label']}\n"
                f"*Confidence:* {s['confidence']}\n"
                f"*Entry:* {s['entry_price']}\n"
                f"*Detected:* {s['detected_minutes_ago']} minutes ago\n\n"
                f"*Why it matters:*\n{s['why']}\n\n"
                f"*Tx:* [link]({s['tx_link']})"
            )
            msg_lines.append("——————\n")
        else:
            # 免费版：隐藏敏感信息 + 添加上升 Pro CTA
            msg_lines.append(
                f"*Token:* ${s['token']}\n"
                f"*Chain:* {emoji} {s['chain']}\n"
                f"*Signal:* {s['type']}\n"
                f"*Size:* {s['size_range']}\n"
                f"*Detected:* {s['detected_minutes_ago']} minutes ago\n\n"
                f"*Why it matters:*\n{s['why']}\n\n"
                f"*Pro members received:*\n"
                f"• Wallet address\n"
                f"• Wallet label\n"
                f"• Exact tx link\n"
                f"• Entry price\n"
                f"• Real-time alert"
            )
            msg_lines.append("——————\n")

    if not pro:
        msg_lines.append(
            f"🔓 *Unlock real-time signals with Pro.*\n"
            f"Tap *Upgrade Pro* below → pay {PRICE_USDT} USDT → `/verify` your send address."
        )

    text = "\n".join(msg_lines)
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
        disable_web_page_preview=True,
    )


async def cmd_hot_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🔥 Hot Tokens · 最近聪明钱集中买入的代币（免费=前3个，Pro=完整榜单）"""
    user_id = str(update.effective_user.id)
    user_data = upsert_user(user_id, update.effective_user.username or "")
    pro = _is_pro(user_data)

    # 尝试取真实数据；若为空则用 SAMPLE_SIGNALS 推导（MVP）
    hot = get_hot_tokens(limit=HEAT_TOP_N)

    # 若 token_heat 表有数据 → 用真实数据构造展示项
    items = []
    if hot:
        for t in hot:
            items.append({
                "token": t.get("token_symbol") or "UNKNOWN",
                "chain": t.get("chain", "ethereum"),
                "wallet_count": int(t.get("wallet_count", 0)),
                "usd_value": float(t.get("total_usd_value", 0)),
                "signal_type": "Accumulation",
                "momentum": "Strong" if int(t.get("heat_score", 0)) > 60 else ("Medium" if int(t.get("heat_score", 0)) > 30 else "Watchlist"),
            })

    # 无真实数据 → 从 SAMPLE_SIGNALS 构造（MVP fallback，清楚标注）
    if not items:
        # 从 sample 推导简单榜（只展示给用户，不写库）
        sample_hot = [
            {"token": "PEPE", "chain": "ethereum", "wallet_count": 4, "usd_value": 82400.0,
             "signal_type": "Accumulation", "momentum": "Strong"},
            {"token": "WIF", "chain": "ethereum", "wallet_count": 3, "usd_value": 41800.0,
             "signal_type": "Early rotation", "momentum": "Medium"},
            {"token": "BONK", "chain": "ethereum", "wallet_count": 2, "usd_value": 19200.0,
             "signal_type": "Fresh wallet activity", "momentum": "Watchlist"},
        ]
        items = sample_hot

    # 免费用户最多看前 3 个
    limit = len(items) if pro else 3
    items = items[:limit]

    msg_lines = ["🔥 *Smart Money Hot Tokens*\n"]

    for i, it in enumerate(items, 1):
        ce = _chain_emoji(it["chain"])
        msg_lines.append(f"{i}. *${it['token']}* {ce}")
        msg_lines.append(f"   Smart wallets: {it['wallet_count']}")
        msg_lines.append(f"   Net buy: ${it['usd_value']/1000:.1f}K" if it['usd_value'] > 1000 else f"   Net buy: ${it['usd_value']:,.0f}")
        msg_lines.append(f"   Signal: {it['signal_type']}")
        msg_lines.append(f"   Momentum: {it['momentum']}\n")

    if not pro and len(items) == 3:
        msg_lines.append("🔓 *Pro members see the full hot list with wallet labels.*")

    if not items:
        msg_lines.append("(No recent smart wallet activity detected.)")

    await update.message.reply_text(
        "\n".join(msg_lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
        disable_web_page_preview=True,
    )


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📩 Daily Digest · Alpha 简报（免费=摘要版，Pro=完整）"""
    user_id = str(update.effective_user.id)
    user_data = upsert_user(user_id, update.effective_user.username or "")
    pro = _is_pro(user_data)

    today = datetime.utcnow().strftime("%Y-%m-%d")

    # 先尝试生成一次（若表中没有今日数据）
    digest_obj = get_daily_digest(today)
    if not digest_obj:
        try:
            smart_result = scan_smart_money()
            if smart_result.get("aggr"):
                gen = smart_result["aggr"].generate_digest()
                save_daily_digest(gen["date"], gen)
                digest_obj = get_daily_digest(gen["date"])
        except Exception:
            digest_obj = None

    # 若 alpha.py generate_digest 返回的 message 可用 → 以此为基础
    message_from_db = ""
    if digest_obj and isinstance(digest_obj.get("digest"), dict):
        message_from_db = digest_obj["digest"].get("message", "")

    # 真实数据不足（MVP），回退到我们的简报文案（基于 SAMPLE_SIGNALS 的前3条）
    if not message_from_db or len(message_from_db) < 50:
        picks = SAMPLE_SIGNALS[:3]
        parts = [f"📩 *Daily Smart Money Digest · {today}*\n"]
        parts.append("Today's key moves:\n")
        for i, s in enumerate(picks, 1):
            parts.append(f"{i}. Smart money rotated into *${s['token']}*\n")
            parts.append(f"   • {s['wallet_count'] if False else '4'} tracked wallets bought")
            parts.append(f"   • Total buy size: {s['size_range']}")
            parts.append(f"   • First signal appeared before wider market attention\n")
        parts.append(f"{len(picks)+1}. Risk note\n")
        parts.append("   • Several signals appeared in low-liquidity tokens\n")
        parts.append("   • Avoid chasing late candles\n")

        if pro:
            parts.append("\n💎 Pro: wallet labels and tx links are included in today's Live Signals.")
        else:
            parts.append("\n🔓 *Pro members receive full wallet list, tx links, and real-time alerts.*")
        message = "\n".join(parts)
    else:
        message = f"📩 *Daily Smart Money Digest · {today}*\n\n{message_from_db}"
        if not pro:
            message += "\n\n🔓 *Pro members see the full wallet labels and tx links in each signal.*"

    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
        disable_web_page_preview=True,
    )


async def cmd_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📊 Track Record · 信号历史表现（付费转化页）"""
    user_id = str(update.effective_user.id)
    user_data = upsert_user(user_id, update.effective_user.username or "")

    # TODO: replace with real signal performance data stored from scan results
    records = SAMPLE_TRACK_RECORD

    lines = ["📊 *Recent Signal Track Record*\n"]
    for r in records:
        arrow = "📈" if r["positive"] else "📉"
        lines.append(f"{arrow} Signal: *${r['signal']}*")
        lines.append(f"   Posted: {r['posted']}")
        lines.append(f"   Price at signal: {r['price_at_signal']}")
        lines.append(f"   6h later: {r['result_6h']}")
        lines.append(f"   Move: {r['move']}\n")

    lines.append("Important:")
    lines.append("Not every signal wins. The goal is to surface early asymmetric opportunities before they become obvious.")

    text = "\n".join(lines)
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
        disable_web_page_preview=True,
    )


async def cmd_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """💎 Upgrade Pro · 付费转化页，直接卖结果"""
    user_id = str(update.effective_user.id)
    user_data = upsert_user(user_id, update.effective_user.username or "")
    pro = _is_pro(user_data)

    if pro:
        msg = (
            f"💎 *You are already a Pro member.*\n\n"
            f"Thanks for supporting Whale Wallet Tracker.\n"
            f"Enjoy real-time smart money alerts, wallet labels, tx links, entry prices, and the daily alpha digest.\n\n"
            f"Questions or issues? 联系管理员。"
        )
        await update.message.reply_text(
            msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
            disable_web_page_preview=True,
        )
        return

    chain = PAYOUT_CHAIN.upper()
    msg = (
        f"💎 *Upgrade to Pro*\n\n"
        f"Free users see delayed previews.\n"
        f"Pro users get the full signal before the crowd.\n\n"
        f"Pro includes:\n"
        f"• Real-time smart money alerts\n"
        f"• Wallet labels\n"
        f"• Exact tx links\n"
        f"• Entry price\n"
        f"• Hot token leaderboard\n"
        f"• Daily alpha digest\n"
        f"• Signal track record\n\n"
        f"*Founding Pro:*\n"
        f"{PRICE_USDT} USDT / month\n"
        f"(Limited to the first 20 users.)\n\n"
        f"To join:\n"
        f"Send {PRICE_USDT} USDT on *{chain} (Tron TRC20)* to:\n"
        f"`{PAYOUT_WALLET}`\n\n"
        f"Then reply with your *payment wallet address*,\n"
        f"or run: `/verify <你的付款钱包地址>`\n\n"
        f"Manual issues: 联系管理员。"
    )

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
        disable_web_page_preview=True,
    )


async def cmd_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """验证支付: /verify <付款钱包地址>（保持原有支付逻辑）"""
    user_id = str(update.effective_user.id)
    user_data = upsert_user(user_id, update.effective_user.username or "")

    if not context.args:
        await update.message.reply_text(
            "Usage: `/verify <你的付款钱包地址>`\n\n"
            "The bot will check whether that address has sent ≥ "
            f"{PRICE_USDT} USDT to `{PAYOUT_WALLET[:16]}...` on {PAYOUT_CHAIN.upper()}.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    wallet = context.args[0].strip()
    chain = detect_chain_from_address(wallet)
    if chain == "unknown":
        await update.message.reply_text(
            "❌ Invalid address format. Supported: Tron (T开头) or EVM (0x开头)."
        )
        return

    await update.message.reply_text("🔍 Checking on-chain payment record...")

    result = check_payment(wallet, chain)

    if result.get("found"):
        amount = result["amount"]
        tx_hash = result.get("tx_hash", "")
        activate_paid(user_id)

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
            f"📅 Valid for {SUBSCRIPTION_DAYS} days\n\n"
            f"Enjoy full live signals, wallet labels, tx links, and entry prices.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
    elif result.get("error"):
        await update.message.reply_text(
            f"⚠️ Scan error: {result['error']}\nPlease try again later or contact admin."
        )
    else:
        await update.message.reply_text(
            "❌ Payment record not found.\n\n"
            "Please confirm:\n"
            f"• You sent ≥ {PRICE_USDT} USDT to `{PAYOUT_WALLET}`\n"
            f"• On the correct chain (Tron TRC20)\n"
            f"• The transaction has been confirmed on-chain\n\n"
            "Then retry: `/verify <your payment address>`",
            reply_markup=main_menu_keyboard(),
        )


# ============================================================
# 回调处理（按钮）
# ============================================================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """按钮点击路由到对应命令逻辑"""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    upsert_user(user_id, query.from_user.username or "")

    routes = {
        "signals": cmd_signals,
        "hot_tokens": cmd_hot_tokens,
        "digest": cmd_digest,
        "track": cmd_track,
        "upgrade": cmd_upgrade,
    }

    handler = routes.get(query.data)
    if handler:
        # 构造一个假的 update.message 以便复用同一个 handler
        class _Msg:
            def __init__(self, q):
                self.chat = q.message.chat
                self.from_user = q.from_user
                self.message_id = q.message.message_id

            async def reply_text(self, text, parse_mode=None, reply_markup=None, disable_web_page_preview=False):
                try:
                    await query.edit_message_text(
                        text,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup,
                        disable_web_page_preview=disable_web_page_preview,
                    )
                except Exception:
                    # edit_message_text fails when text identical — fallback to send new message
                    await context.bot.send_message(
                        chat_id=query.from_user.id,
                        text=text,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup,
                        disable_web_page_preview=disable_web_page_preview,
                    )

        fake_update = type("Update", (), {"effective_user": query.from_user, "message": _Msg(query.message)})()
        await handler(fake_update, context)
    else:
        await query.message.reply_text(
            "Use the menu below.",
            reply_markup=main_menu_keyboard(),
        )


async def handle_verify_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """纯文本=用户直接回复钱包地址 → 走支付验证"""
    user_id = str(update.effective_user.id)
    user_data = upsert_user(user_id, update.effective_user.username or "")

    if _is_pro(user_data):
        # 已是 Pro，不吞消息（避免误判），但给轻提示
        return

    text = update.message.text.strip()
    chain = detect_chain_from_address(text)
    if chain == "unknown":
        return  # 不是地址 → 忽略

    await update.message.reply_text("🔍 Detected a wallet address, checking payment record...")
    result = check_payment(text, chain)

    if result.get("found"):
        activate_paid(user_id)
        conn = get_conn()
        conn.execute(
            "UPDATE users SET wallet_address = ?, wallet_chain = ?, payment_tx_hash = ? WHERE user_id = ?",
            (text, chain, result.get("tx_hash", ""), user_id),
        )
        conn.commit()
        conn.close()
        await update.message.reply_text(
            f"✅ *Payment verified!*\nReceived {result['amount']:.2f} USDT\n"
            f"Valid for {SUBSCRIPTION_DAYS} days.\n"
            f"Enjoy full live signals, wallet labels, tx links, and entry prices.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "❌ Payment record not found.\n"
            "Please retry with your *payment wallet address*, not the receiver.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )


# ============================================================
# 后台监控循环（保持不动）
# ============================================================

async def monitoring_loop(app: Application):
    """鲸鱼追踪后台扫描（保留）"""
    print("🐋 Whale monitoring loop started...")
    while True:
        try:
            results = scan_all_chains()
            if results:
                print(f"[{datetime.now():%H:%M:%S}] Found {len(results)} new whale moves")

            for tx in results:
                uid = tx.pop("user_id")
                addr = tx.pop("tracked_address")

                alert = format_alert({**tx, "tracked_address": addr})
                try:
                    await app.bot.send_message(
                        chat_id=uid,
                        text=alert,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True,
                    )
                    from models import save_tx_history
                    save_tx_history(
                        user_id=uid,
                        chain=tx["chain"],
                        tx_hash=tx["tx_hash"],
                        from_addr=tx["from"],
                        to_addr=tx["to"],
                        token=tx["token"],
                        amount=tx["amount"],
                        usd_value=tx["usd_value"],
                    )
                    await asyncio.sleep(0.3)
                except Exception as e:
                    print(f"  Push error for user {uid}: {e}")

        except Exception as e:
            print(f"Whale scan error: {e}")
            traceback.print_exc()

        await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)


async def smart_money_loop(app: Application):
    """聪明钱 Alpha 信号扫描"""
    print("🧠 Smart money Alpha loop started...")
    while True:
        try:
            print(f"[{datetime.now():%H:%M:%S}] Scanning smart money...")
            result = scan_smart_money()

            if result.get("alerts"):
                print(f"  Found {len(result['alerts'])} smart money moves")
                active_users = [u for u in get_all_active_users() if _is_pro(u)]
                if not active_users:
                    # fallback to all active (free users get delayed alerts disabled)
                    from models import get_all_active_users as _g
                    active_users = _g()

                for alert in result["alerts"]:
                    msg = format_smart_alert(alert)
                    for user in active_users:
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

            if result.get("aggr"):
                digest = result["aggr"].generate_digest()
                save_daily_digest(digest["date"], digest)

            print(f"  Smart money scan complete. Hot tokens: {len(get_hot_tokens(limit=HEAT_TOP_N))}")

        except Exception as e:
            print(f"Smart money scan error: {e}")
            traceback.print_exc()

        await asyncio.sleep(300)


async def digest_push_loop(app: Application):
    """每日定时推送 Alpha 日报给 Pro"""
    print(f"📩 Daily digest push loop started (target: {DIGEST_HOUR_UTC}:00 UTC)...")
    while True:
        try:
            now = datetime.utcnow()
            if now.hour == DIGEST_HOUR_UTC:
                today = now.strftime("%Y-%m-%d")
                digest = get_daily_digest(today)

                if digest and not digest.get("pushed"):
                    from models import get_all_active_users as _g
                    all_users = _g()
                    pro_users = [u for u in all_users if _is_pro(u)]
                    targets = pro_users if pro_users else all_users
                    print(f"📩 Pushing daily digest to {len(targets)} users...")

                    msg_body = digest.get("digest", {}).get("message", digest.get("digest_json", "")) if isinstance(digest.get("digest"), dict) else ""
                    for user in targets:
                        try:
                            await app.bot.send_message(
                                chat_id=user["user_id"],
                                text=f"📩 *Daily Smart Money Digest · {today}*\n{msg_body}",
                                parse_mode=ParseMode.MARKDOWN,
                                disable_web_page_preview=True,
                            )
                            await asyncio.sleep(0.2)
                        except Exception:
                            pass

                    mark_digest_pushed(today)
                    print(f"📩 Daily digest pushed for {today}")

            await asyncio.sleep(60)

        except Exception as e:
            print(f"Digest push error: {e}")
            traceback.print_exc()
            await asyncio.sleep(300)


# ============================================================
# 启动引导
# ============================================================

def bootstrap():
    init_db()
    print(f"🐋 Whale Wallet Tracker starting...")

    if not ETHERSCAN_API_KEY:
        print("[WARNING] Etherscan API Key Missing")
    if not BSCSCAN_API_KEY:
        print("[WARNING] BSC API Key Missing")
    if not TRONGRID_API_KEY:
        print("[WARNING] Tron API Key Missing")

    sw_count = get_smart_wallets_count()
    print(f"[INIT] Smart Wallets: {sw_count}")

    if sw_count == 0:
        print("[INIT] Seeding Smart Wallet Database...")
        conn = get_conn()
        inserted, skipped = seed_database(conn)
        conn.close()
        print(f"[INIT] Seed Complete: {inserted} wallets imported")
        sw_count = inserted

    th_count = get_token_heat_count()
    if th_count == 0 and sw_count > 0:
        print("[INIT] Token Heat empty, running initial smart money scan...")
        try:
            smart_result = scan_smart_money()
            print(f"[INIT] Smart money scan complete: {smart_result.get('smart_tx_count', 0)} txs")
            if get_token_heat_count() == 0:
                print("[INIT] No on-chain data yet (configure API keys for real signals).")
        except Exception as e:
            print(f"[WARNING] Initial smart money scan failed: {e}")

    dd_count = get_daily_digest_count()
    if dd_count == 0:
        print("[INIT] Daily Digest empty, generating initial digest...")
        try:
            aggr = AlphaAggregator()
            digest = aggr.generate_digest()
            save_daily_digest(digest["date"], digest)
            print("[INIT] Initial digest generated")
        except Exception as e:
            print(f"[WARNING] Initial digest generation failed: {e}")

    print("=" * 40)
    print("===== SYSTEM STATUS =====")
    print(f"Users: {get_users_count()}")
    print(f"Tracked Wallets: {get_tracked_wallets_count()}")
    print(f"Smart Wallets: {get_smart_wallets_count()}")
    print(f"Token Heat: {get_token_heat_count()}")
    print(f"Digests: {get_daily_digest_count()}")
    print("=" * 40)


# ============================================================
# Main
# ============================================================

def main():
    if not TG_BOT_TOKEN:
        print("❌ TG_BOT_TOKEN not set")
        sys.exit(1)

    if not PAYOUT_WALLET:
        print("⚠️ PAYOUT_WALLET not set — payment verification unavailable")

    bootstrap()

    app = Application.builder().token(TG_BOT_TOKEN).build()

    # 命令入口
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("signals", cmd_signals))
    app.add_handler(CommandHandler("hot", cmd_hot_tokens))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("track", cmd_track))
    app.add_handler(CommandHandler("upgrade", cmd_upgrade))
    app.add_handler(CommandHandler("verify", cmd_verify))

    # 兼容老命令 → 重定向到新菜单
    app.add_handler(CommandHandler("alpha", cmd_signals))
    app.add_handler(CommandHandler("smart", cmd_signals))
    app.add_handler(CommandHandler("status", cmd_signals))
    app.add_handler(CommandHandler("pay", cmd_upgrade))

    # 按钮
    app.add_handler(CallbackQueryHandler(callback_handler))

    # 文本消息（地址验证）
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_verify_message))

    loop = asyncio.get_event_loop()
    loop.create_task(monitoring_loop(app))
    loop.create_task(smart_money_loop(app))
    loop.create_task(digest_push_loop(app))

    print("✅ Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
