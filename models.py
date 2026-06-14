# -*- coding: utf-8 -*-
"""
Whale Tracker TG Bot · 数据库模型
"""

import sqlite3
import os
from datetime import datetime, timedelta
from config import DATABASE_PATH, TRIAL_DAYS, SUBSCRIPTION_DAYS

DB = DATABASE_PATH


def get_conn():
    """获取数据库连接（自动创建目录）"""
    os.makedirs(os.path.dirname(os.path.abspath(DB)), exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            status TEXT DEFAULT 'trial',      -- trial / paid / expired
            trial_start TEXT,
            trial_end TEXT,
            paid_until TEXT,
            wallet_address TEXT,
            wallet_chain TEXT DEFAULT 'tron',
            payment_tx_hash TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tracked_wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            chain TEXT NOT NULL,
            address TEXT NOT NULL,
            label TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            UNIQUE(user_id, chain, address)
        );

        CREATE TABLE IF NOT EXISTS tx_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            chain TEXT,
            tx_hash TEXT,
            from_address TEXT,
            to_address TEXT,
            token_symbol TEXT,
            amount TEXT,
            usd_value TEXT,
            detected_at TEXT DEFAULT (datetime('now')),
            pushed INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_tracked_user ON tracked_wallets(user_id);
        CREATE INDEX IF NOT EXISTS idx_tx_user ON tx_history(user_id);
        CREATE INDEX IF NOT EXISTS idx_tx_hash ON tx_history(tx_hash, chain);
    """)
    conn.commit()
    conn.close()


# ============================================================
# 用户管理
# ============================================================

def upsert_user(user_id: str, username: str = "") -> dict:
    """创建或获取用户，新用户自动进入试用期"""
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    if not user:
        now = datetime.now()
        trial_end = now + timedelta(days=TRIAL_DAYS)
        conn.execute(
            """INSERT INTO users (user_id, username, status, trial_start, trial_end)
               VALUES (?, ?, 'trial', ?, ?)""",
            (user_id, username, now.isoformat(), trial_end.isoformat()),
        )
        conn.commit()
        conn.close()
        return {
            "user_id": user_id,
            "username": username,
            "status": "trial",
            "trial_start": now.isoformat(),
            "trial_end": trial_end.isoformat(),
            "paid_until": None,
            "wallet_address": None,
            "wallet_chain": "tron",
        }

    # 更新用户名
    if username and username != user["username"]:
        conn.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        conn.commit()

    # 检查试用/付费是否过期
    status = user["status"]
    now = datetime.now()
    if status == "trial" and user["trial_end"]:
        trial_end = datetime.fromisoformat(user["trial_end"])
        if now > trial_end:
            status = "expired"
            conn.execute("UPDATE users SET status = 'expired' WHERE user_id = ?", (user_id,))
    elif status == "paid" and user["paid_until"]:
        paid_until = datetime.fromisoformat(user["paid_until"])
        if now > paid_until:
            status = "expired"
            conn.execute("UPDATE users SET status = 'expired' WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()

    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "status": status,
        "trial_start": user["trial_start"],
        "trial_end": user["trial_end"],
        "paid_until": user["paid_until"],
        "wallet_address": user["wallet_address"],
        "wallet_chain": user["wallet_chain"] or "tron",
    }


def activate_paid(user_id: str) -> bool:
    """将用户设为付费状态"""
    conn = get_conn()
    now = datetime.now()
    paid_until = now + timedelta(days=SUBSCRIPTION_DAYS)
    conn.execute(
        "UPDATE users SET status = 'paid', paid_until = ? WHERE user_id = ?",
        (paid_until.isoformat(), user_id),
    )
    conn.commit()
    conn.close()
    return True


def is_user_active(user_id: str) -> bool:
    """检查用户是否在有效期内（试用或付费）"""
    conn = get_conn()
    u = conn.execute("SELECT status, trial_end, paid_until FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if not u:
        return False
    if u["status"] == "paid":
        if u["paid_until"]:
            return datetime.now() <= datetime.fromisoformat(u["paid_until"])
        return True
    if u["status"] == "trial":
        if u["trial_end"]:
            return datetime.now() <= datetime.fromisoformat(u["trial_end"])
        return True
    return False


def get_all_active_users() -> list:
    """获取所有在有效期内的用户"""
    conn = get_conn()
    now = datetime.now().isoformat()
    users = conn.execute(
        """SELECT * FROM users
           WHERE (status = 'paid' AND paid_until > ?)
              OR (status = 'trial' AND trial_end > ?)""",
        (now, now),
    ).fetchall()
    conn.close()
    return [dict(u) for u in users]


# ============================================================
# 钱包追踪管理
# ============================================================

def add_tracked_wallet(user_id: str, chain: str, address: str, label: str = "") -> tuple:
    """添加追踪钱包。返回 (success: bool, message: str)"""
    from config import FREE_WALLET_LIMIT, PAID_WALLET_LIMIT

    conn = get_conn()

    # 检查数量限制
    user = conn.execute("SELECT status FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return False, "用户不存在"

    current_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM tracked_wallets WHERE user_id = ? AND active = 1",
        (user_id,),
    ).fetchone()["cnt"]

    limit = PAID_WALLET_LIMIT if user["status"] == "paid" else FREE_WALLET_LIMIT
    if current_count >= limit:
        conn.close()
        return False, f"已达上限（{limit}个地址），请升级付费版"

    # 检查是否已存在
    existing = conn.execute(
        "SELECT id FROM tracked_wallets WHERE user_id = ? AND chain = ? AND address = ?",
        (user_id, chain, address),
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE tracked_wallets SET active = 1, label = ? WHERE id = ?",
            (label or None, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO tracked_wallets (user_id, chain, address, label) VALUES (?, ?, ?, ?)",
            (user_id, chain, address, label or None),
        )

    conn.commit()
    conn.close()
    return True, f"✅ 已添加追踪: {address[:10]}... ({chain})"


def remove_tracked_wallet(user_id: str, chain: str, address: str) -> bool:
    """软删除追踪钱包"""
    conn = get_conn()
    conn.execute(
        "UPDATE tracked_wallets SET active = 0 WHERE user_id = ? AND chain = ? AND address = ?",
        (user_id, chain, address),
    )
    conn.commit()
    conn.close()
    return True


def get_user_wallets(user_id: str) -> list:
    """获取用户追踪的所有钱包"""
    conn = get_conn()
    wallets = conn.execute(
        "SELECT * FROM tracked_wallets WHERE user_id = ? AND active = 1 ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(w) for w in wallets]


def get_all_active_wallets() -> list:
    """获取所有需要监控的钱包（跨所有活跃用户）"""
    conn = get_conn()
    now = datetime.now().isoformat()
    wallets = conn.execute(
        """SELECT w.*, u.user_id as owner_user_id
           FROM tracked_wallets w
           JOIN users u ON w.user_id = u.user_id
           WHERE w.active = 1
             AND ((u.status = 'paid' AND u.paid_until > ?)
                  OR (u.status = 'trial' AND u.trial_end > ?))
           ORDER BY w.chain, w.address""",
        (now, now),
    ).fetchall()
    conn.close()
    return [dict(w) for w in wallets]


# ============================================================
# 交易历史
# ============================================================

def save_tx_history(user_id: str, chain: str, tx_hash: str,
                     from_addr: str, to_addr: str,
                     token: str, amount: str, usd_value: str = "0") -> bool:
    """保存已推送的交易（防重复）"""
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM tx_history WHERE tx_hash = ? AND chain = ? AND user_id = ?",
        (tx_hash, chain, user_id),
    ).fetchone()
    if existing:
        conn.close()
        return False  # 已存在

    conn.execute(
        """INSERT INTO tx_history
           (user_id, chain, tx_hash, from_address, to_address, token_symbol, amount, usd_value, pushed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (user_id, chain, tx_hash, from_addr, to_addr, token, amount, usd_value),
    )
    conn.commit()
    conn.close()
    return True


def was_tx_pushed(tx_hash: str, chain: str, user_id: str) -> bool:
    """检查某笔交易是否已推送给某用户"""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM tx_history WHERE tx_hash = ? AND chain = ? AND user_id = ?",
        (tx_hash, chain, user_id),
    ).fetchone()
    conn.close()
    return row is not None


# ============================================================
# 初始化
# ============================================================
if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")