# -*- coding: utf-8 -*-
"""
Whale Tracker TG Bot · 主程序
Reddit: "How do you guys track whale wallet movements?" (👍198)
"""

import asyncio
import sys
import traceback
from datetime import datetime, timezone

# Windows 控制台默认 GBK 编码，遇到 emoji 会崩溃；强制 stdout/stderr 用 UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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


def main_menu_keyboard(status: str):
    """主菜单按钮 · 精简为 4 键"""
    buttons = [
        [
            InlineKeyboardButton("📋 我的追踪", callback_data="list"),
            InlineKeyboardButton("➕ 添加地址", callback_data="add_help"),
        ],
        [InlineKeyboardButton("🧠 Alpha 聪明钱信号", callback_data="alpha")],
    ]
    if status == "paid":
        buttons.append([InlineKeyboardButton("📊 账户状态", callback_data="status")])
    else:
        buttons.append([InlineKeyboardButton(f"💎 升级 Pro (${PRICE_USDT} USDT/月)", callback_data="pay")])
    return InlineKeyboardMarkup(buttons)



# ============================================================
# 命令处理
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """新用户注册 / 老用户欢迎"""
    user = update.effective_user
    user_data = upsert_user(str(user.id), user.username or user.full_name)

    days_left = ""
    if user_data["status"] == "trial":
        trial_end = datetime.fromisoformat(user_data["trial_end"])
        hours = (trial_end - datetime.now()).total_seconds() / 3600
        days_left = f"\n🆓 试用期剩余: {max(0, int(hours))} 小时"

    welcome = f"""🐋 *Whale Tracker · 鲸鱼钱包追踪*

欢迎 {user.full_name}！
实时监控大额链上转账，第一时间掌握鲸鱼动向。

🔷 支持: Ethereum · BSC · Tron
💰 最低推送金额: ≥${MIN_USD_VALUE:,.0f}
🆓 免费版: 追踪 {FREE_WALLET_LIMIT} 个地址
💎 付费版: 追踪 {PAID_WALLET_LIMIT} 个地址 (${PRICE_USDT} USDT/月){days_left}

*添加追踪地址:*
`/add <链> <地址> <标签>`
例: `/add eth 0x28C6c06298d514Db089934071355E5743bf21d60 币安热钱包`
"""

    await update.message.reply_text(
        welcome,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(user_data["status"]),
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
    """显示付款信息"""
    user_id = str(update.effective_user.id)
    user = upsert_user(user_id, update.effective_user.username or "")
    chain = PAYOUT_CHAIN.upper()

    pay_msg = f"""💎 *升级付费版 · ${PRICE_USDT} USDT/月*

📤 支付 *{PRICE_USDT} USDT* 到以下地址:

🔗 链: *{chain} (Tron TRC20)*
📬 地址:
`{PAYOUT_WALLET}`

⚠️ *重要*: 支付后，请用你的付款钱包地址执行:
`/verify <你的付款钱包地址>`

或直接回复你的付款地址。

📊 付费版权益:
• 追踪 {PAID_WALLET_LIMIT} 个钱包地址
• 实时推送，{CHECK_INTERVAL_MINUTES} 分钟刷新
• 支持 ETH/BSC/Tron 三链
• 大额转账 + 稳定币监控
"""
    await update.message.reply_text(
        pay_msg,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


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
            "用法: `/verify <你的付款钱包地址>`\n"
            f"系统会检查该地址是否已向你的收款地址转了 ${PRICE_USDT} USDT",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    wallet = context.args[0].strip()
    chain = detect_chain_from_address(wallet)
    if chain == "unknown":
        await update.message.reply_text("❌ 地址格式无效。支持 Tron (T开头) 和 EVM (0x开头)")
        return

    await update.message.reply_text("🔍 正在检查链上支付记录...")

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
            f"✅ *支付验证成功！*\n\n"
            f"💰 收到: {amount:.2f} USDT\n"
            f"🔗 TX: `{tx_hash[:20]}...`\n"
            f"📅 有效期至: {datetime.now().strftime('%m/%d %H:%M')}\n\n"
            f"现在可以用 /add 添加更多追踪地址了！",
            parse_mode=ParseMode.MARKDOWN,
        )
    elif result.get("error"):
        await update.message.reply_text(
            f"⚠️ 检查失败: {result['error']}\n请稍后重试或联系客服。"
        )
    else:
        await update.message.reply_text(
            "❌ 未检测到支付记录。\n\n"
            "请确认:\n"
            f"• 已向 `{PAYOUT_WALLET[:10]}...` 转了 ≥ {PRICE_USDT} USDT\n"
            "• 使用正确链 (Tron TRC20)\n"
            "• 交易已经上链确认\n\n"
            "然后重试: `/verify <你的付款地址>`"
        )


async def cmd_alpha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看 Alpha 聪明钱信号：代币热度榜 + 聪明钱排行"""
    user_id = str(update.effective_user.id)
    user = upsert_user(user_id, update.effective_user.username or "")

    # 强制触发一次聪明钱扫描
    await update.message.reply_text("🔍 正在扫描聪明钱信号...")

    try:
        smart_result = scan_smart_money()
        hot_tokens = get_hot_tokens(limit=HEAT_TOP_N)
        leaderboard = get_leaderboard(limit=10)

        if not hot_tokens:
            await update.message.reply_text(
                "📊 *Alpha 信号*\n\n暂无数据。稍后再试！",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        msg_lines = ["🧠 *Alpha 聪明钱信号*\n"]

        # 热度榜
        msg_lines.append("🔥 *24h 代币热度 Top10*\n")
        for i, t in enumerate(hot_tokens[:10], 1):
            symbol = t["token_symbol"] or "?"
            chain_emoji = CHAINS.get(t.get("chain", "ethereum"), {}).get("emoji", "📊")
            msg_lines.append(
                f"  {i}. {chain_emoji} *{symbol}* — 🔥{t['heat_score']}"
            )

        # 汇总
        total_activity = sum(t["wallet_count"] for t in hot_tokens)
        msg_lines.append(f"\n📊 总活动: {total_activity} 次聪明钱交易")

        # 聪明钱排行
        if leaderboard:
            msg_lines.append("\n🏆 *聪明钱 Top5*")
            for w in leaderboard[:5]:
                cat_emoji = {"mm": "🏦", "vc": "💰", "trader": "🧠", "exchange": "🏦", "unknown": "❓"}
                emoji = cat_emoji.get(w.get("category", ""), "🧠")
                msg_lines.append(f"  {emoji} {w['nickname']} — ⭐{w['score']}")

        if smart_result.get("aggr"):
            digest = smart_result["aggr"].generate_digest()
            save_daily_digest(digest["date"], digest)

        await update.message.reply_text(
            "\n".join(msg_lines),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Alpha 扫描出错: {e}\n请稍后重试。"
        )


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看今日 Alpha 日报"""
    user_id = str(update.effective_user.id)
    user = upsert_user(user_id, update.effective_user.username or "")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = get_daily_digest(today)

    if not digest:
        # 尝试生成
        await update.message.reply_text("📊 正在生成今日日报...")
        smart_result = scan_smart_money()
        if smart_result.get("aggr"):
            digest = smart_result["aggr"].generate_digest()
            save_daily_digest(today, digest)
            digest = get_daily_digest(today)

    if not digest:
        await update.message.reply_text(
            "📊 *Alpha 日报*\n\n今日暂无明显聪明钱动向。",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    digest_data = digest
    message = digest_data.get("message", "日报数据异常")
    pushed = digest_data.get("pushed", False)

    status_line = "✅ 已推送" if pushed else "📋 待推送"
    msg = f"📊 *Alpha 日报 · {today}* [{status_line}]\n{message}"

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.MARKDOWN,
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

    elif data == "alpha":
        await query.edit_message_text("🔍 正在扫描聪明钱信号...")
        try:
            smart_result = scan_smart_money()
            hot_tokens = get_hot_tokens(limit=HEAT_TOP_N)
            leaderboard = get_leaderboard(limit=10)
        except Exception as e:
            await query.edit_message_text(
                f"⚠️ Alpha 扫描出错: {e}\n请稍后重试。",
                reply_markup=main_menu_keyboard(user["status"]),
            )
            return

        tier = tier_of(user)
        if not hot_tokens:
            await query.edit_message_text(
                "📊 *Alpha 信号*\n\n暂无数据。稍后再试！",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard(user["status"]),
            )
            return

        # Free 用户只看 Top3 + 升级引导；Pro 看完整 Top10 + 排行
        top_n = 10 if tier in ("paid", "trial") else 3
        msg_lines = ["🧠 *Alpha 聪明钱信号*\n", "🔥 *24h 代币热度*\n"]
        for i, t in enumerate(hot_tokens[:top_n], 1):
            symbol = t["token_symbol"] or "?"
            ce = CHAINS.get(t.get("chain", "ethereum"), {}).get("emoji", "📊")
            msg_lines.append(f"  {i}. {ce} *{symbol}* — 🔥{t['heat_score']}")

        if tier in ("paid", "trial"):
            total_activity = sum(t["wallet_count"] for t in hot_tokens)
            msg_lines.append(f"\n📊 总活动: {total_activity} 次聪明钱交易")
            if leaderboard:
                msg_lines.append("\n🏆 *聪明钱 Top5*")
                cat_emoji = {"mm": "🏦", "vc": "💰", "trader": "🧠", "exchange": "🏦", "unknown": "❓"}
                for w in leaderboard[:5]:
                    emoji = cat_emoji.get(w.get("category", ""), "🧠")
                    msg_lines.append(f"  {emoji} {w['nickname']} — ⭐{w['score']}")
        else:
            msg_lines.append("\n🔒 _完整 Top10 + 聪明钱排行为 Pro 专享_")
            msg_lines.append("💎 升级 Pro 解锁 → /pay")

        if smart_result.get("aggr"):
            digest = smart_result["aggr"].generate_digest()
            save_daily_digest(digest["date"], digest)

        await query.edit_message_text(
            "\n".join(msg_lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(user["status"]),
            disable_web_page_preview=True,
        )

    elif data == "pay":
        chain = PAYOUT_CHAIN.upper()
        await query.edit_message_text(
            f"💎 *升级付费版 · ${PRICE_USDT} USDT/月*\n\n"

            f"📤 支付到:\n`{PAYOUT_WALLET}`\n({chain} TRC20)\n\n"
            "支付后用 /verify 验证",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 返回", callback_data="status")
            ]]),
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
        await update.message.reply_text("💎 你已是付费用户！")
        return

    text = update.message.text.strip()
    chain = detect_chain_from_address(text)

    if chain == "unknown":
        return  # 不是地址，忽略

    await update.message.reply_text("🔍 检测到钱包地址，正在查询支付记录...")
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
            f"✅ *支付验证成功！*\n收到 {result['amount']:.2f} USDT\n有效期: {SUBSCRIPTION_DAYS} 天",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            "❌ 未找到支付记录。\n请用你的*付款钱包地址*重试。",
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

    async def post_init(application: Application):
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

    # 命令
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("pay", cmd_pay))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("verify", cmd_verify))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("alpha", cmd_alpha))
    app.add_handler(CommandHandler("digest", cmd_digest))
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