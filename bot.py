# -*- coding: utf-8 -*-
"""
Whale Tracker TG Bot · 主程序
Reddit: "How do you guys track whale wallet movements?" (👍198)
"""

import asyncio
import sys
import traceback
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
)
from models import (
    init_db, upsert_user, activate_paid, is_user_active,
    add_tracked_wallet, remove_tracked_wallet, get_user_wallets,
    get_all_active_users, save_tx_history,
)
from payment import check_payment, validate_wallet_address, detect_chain_from_address
from monitor import scan_all_chains, format_alert

# ============================================================
# 键盘 Markup
# ============================================================

def main_menu_keyboard(status: str):
    """主菜单按钮"""
    buttons = [
        [InlineKeyboardButton("📋 我的追踪列表", callback_data="list")],
        [InlineKeyboardButton("➕ 添加追踪地址", callback_data="add_help")],
        [InlineKeyboardButton("➖ 移除追踪地址", callback_data="remove_help")],
    ]
    if status != "paid":
        buttons.append([InlineKeyboardButton(f"💎 升级付费 (${PRICE_USDT} USDT/月)", callback_data="pay")])
    buttons.append([InlineKeyboardButton("📊 账户状态", callback_data="status")])
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
        msg += "💎 续费 ${PRICE_USDT} USDT/月，点击下方按钮\n"

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
            "系统会检查该地址是否已向你的收款地址转了 ${PRICE_USDT} USDT",
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


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员广播（仅 admin user_ids 列表）"""
    user_id = str(update.effective_user.id)
    ADMIN_IDS = ["你的Telegram ID"]  # TODO: 改为你的 TG ID

    if user_id not in ADMIN_IDS:
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
    """后台监控循环：定期扫描链上数据并推送"""
    print("🐋 Monitoring loop started...")
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
            print(f"Scan error: {e}")
            traceback.print_exc()

        await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)


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

    app = Application.builder().token(TG_BOT_TOKEN).build()

    # 命令
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("pay", cmd_pay))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("verify", cmd_verify))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    # 按钮
    app.add_handler(CallbackQueryHandler(callback_handler))

    # 文本消息（地址验证）
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_verify_message))

    # 后台监控
    loop = asyncio.get_event_loop()
    loop.create_task(monitoring_loop(app))

    print("✅ Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()