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
    # timeout 让写操作在锁竞争时等待而非立即抛错
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL 模式允许读写并发，显著降低高频监控下的 "database is locked"
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
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

        CREATE TABLE IF NOT EXISTS smart_wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT NOT NULL,
            chain TEXT NOT NULL,
            nickname TEXT,
            category TEXT,
            score INTEGER DEFAULT 50,
            followers INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            tier INTEGER DEFAULT 3,                 -- 1=核心聪明钱 2=可信机构/交易员 3=观察池
            source TEXT DEFAULT 'unverified',       -- github:eth-labels / arkham / dune / etherscan / user / unverified
            participate_alpha INTEGER DEFAULT 1,    -- 1=参与Alpha评分 0=仅作资金流向参考(交易所)
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(address, chain)
        );


        CREATE TABLE IF NOT EXISTS token_heat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chain TEXT NOT NULL,
            token_address TEXT NOT NULL,
            token_symbol TEXT,
            token_name TEXT,
            heat_score INTEGER DEFAULT 0,
            wallet_count INTEGER DEFAULT 0,
            total_usd_value REAL DEFAULT 0,
            last_updated TEXT,
            UNIQUE(chain, token_address)
        );

        CREATE TABLE IF NOT EXISTS daily_digest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            digest_json TEXT,
            pushed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(date)
        );

        CREATE INDEX IF NOT EXISTS idx_sw_score ON smart_wallets(score DESC);
        CREATE INDEX IF NOT EXISTS idx_sw_chain ON smart_wallets(chain, is_active);
        CREATE INDEX IF NOT EXISTS idx_th_score ON token_heat(heat_score DESC);
        CREATE INDEX IF NOT EXISTS idx_th_chain ON token_heat(chain);
    """)
    conn.commit()
    conn.close()
    migrate_smart_wallets()


def migrate_smart_wallets():
    """
    为已存在的旧库补充 tier / source / participate_alpha 三列。
    新建库由 CREATE TABLE 直接带这三列，本函数对其为 no-op。
    """
    conn = get_conn()
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(smart_wallets)").fetchall()}

    migrations = []
    if "tier" not in cols:
        migrations.append("ALTER TABLE smart_wallets ADD COLUMN tier INTEGER DEFAULT 3")
    if "source" not in cols:
        migrations.append("ALTER TABLE smart_wallets ADD COLUMN source TEXT DEFAULT 'unverified'")
    if "participate_alpha" not in cols:
        migrations.append("ALTER TABLE smart_wallets ADD COLUMN participate_alpha INTEGER DEFAULT 1")

    for sql in migrations:
        conn.execute(sql)

    if migrations:
        conn.commit()
        print(f"[migrate] smart_wallets: applied {len(migrations)} column migration(s)")

    # tier 列已确保存在，可安全建立索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sw_tier ON smart_wallets(tier, is_active)")
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
# 聪明钱地址库 (smart_wallets)
# ============================================================

def get_smart_wallet(address: str, chain: str) -> dict | None:
    """获取单个聪明钱包信息"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM smart_wallets WHERE address = ? AND chain = ? AND is_active = 1",
        (address, chain),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_leaderboard(limit: int = 10, offset: int = 0) -> list:
    """获取聪明钱排行榜（按score降序）"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM smart_wallets WHERE is_active = 1 ORDER BY score DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_smart_wallets(chain: str = None) -> list:
    """获取所有活跃聪明钱包，可按链筛选"""
    conn = get_conn()
    if chain:
        rows = conn.execute(
            "SELECT * FROM smart_wallets WHERE is_active = 1 AND chain = ?",
            (chain,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM smart_wallets WHERE is_active = 1",
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_alpha_smart_wallets(chain: str = None) -> list:
    """
    获取参与 Alpha 评分的聪明钱包（participate_alpha=1）。
    交易所热钱包(participate_alpha=0)会被排除，避免污染代币热度榜。
    """
    conn = get_conn()
    if chain:
        rows = conn.execute(
            """SELECT * FROM smart_wallets
               WHERE is_active = 1 AND participate_alpha = 1 AND chain = ?
               ORDER BY tier ASC, score DESC""",
            (chain,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM smart_wallets
               WHERE is_active = 1 AND participate_alpha = 1
               ORDER BY tier ASC, score DESC""",
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_smart_wallets_by_tier(tier: int, chain: str = None) -> list:
    """按 tier 获取聪明钱包（1=核心 2=可信 3=观察）"""
    conn = get_conn()
    if chain:
        rows = conn.execute(
            "SELECT * FROM smart_wallets WHERE is_active = 1 AND tier = ? AND chain = ? ORDER BY score DESC",
            (tier, chain),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM smart_wallets WHERE is_active = 1 AND tier = ? ORDER BY score DESC",
            (tier,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pool_stats() -> dict:
    """地址池统计：按 tier / source / 是否参与alpha 汇总，用于 /pool 管理命令"""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM smart_wallets WHERE is_active = 1").fetchone()["c"]
    by_tier = {
        row["tier"]: row["c"]
        for row in conn.execute(
            "SELECT tier, COUNT(*) c FROM smart_wallets WHERE is_active = 1 GROUP BY tier"
        ).fetchall()
    }
    by_source = {
        row["source"]: row["c"]
        for row in conn.execute(
            "SELECT source, COUNT(*) c FROM smart_wallets WHERE is_active = 1 GROUP BY source"
        ).fetchall()
    }
    alpha_count = conn.execute(
        "SELECT COUNT(*) c FROM smart_wallets WHERE is_active = 1 AND participate_alpha = 1"
    ).fetchone()["c"]
    conn.close()
    return {
        "total": total,
        "by_tier": by_tier,
        "by_source": by_source,
        "alpha_participants": alpha_count,
    }


def upsert_smart_wallet(address: str, chain: str, nickname: str, category: str,
                        tier: int = 3, source: str = "unverified",
                        participate_alpha: int = 1, score: int = 50) -> bool:
    """
    插入或更新一条聪明钱地址（带 tier/source/participate_alpha）。
    已存在则按更高可信度更新（tier 取更小值，source 非 unverified 时覆盖）。
    返回 True=新插入, False=已存在(已更新)。
    """
    conn = get_conn()
    existing = conn.execute(
        "SELECT id, tier, source FROM smart_wallets WHERE address = ? AND chain = ?",
        (address, chain),
    ).fetchone()

    if existing:
        new_tier = min(existing["tier"] or 3, tier)
        new_source = source if source != "unverified" else existing["source"]
        conn.execute(
            """UPDATE smart_wallets
               SET nickname = ?, category = ?, tier = ?, source = ?, participate_alpha = ?
               WHERE id = ?""",
            (nickname, category, new_tier, new_source, participate_alpha, existing["id"]),
        )
        conn.commit()
        conn.close()
        return False

    conn.execute(
        """INSERT INTO smart_wallets
           (address, chain, nickname, category, score, tier, source, participate_alpha)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (address, chain, nickname, category, score, tier, source, participate_alpha),
    )
    conn.commit()
    conn.close()
    return True


def update_smart_wallet_score(address: str, chain: str, score: int) -> None:

    """更新聪明钱包评分"""
    conn = get_conn()
    conn.execute(
        "UPDATE smart_wallets SET score = ? WHERE address = ? AND chain = ?",
        (score, address, chain),
    )
    conn.commit()
    conn.close()


def increment_followers(address: str, chain: str) -> int:
    """增加关注者数量，返回新值"""
    conn = get_conn()
    conn.execute(
        "UPDATE smart_wallets SET followers = followers + 1 WHERE address = ? AND chain = ?",
        (address, chain),
    )
    row = conn.execute(
        "SELECT followers FROM smart_wallets WHERE address = ? AND chain = ?",
        (address, chain),
    ).fetchone()
    conn.commit()
    conn.close()
    return row["followers"] if row else 0


# ============================================================
# 代币热度 (token_heat)
# ============================================================

def upsert_token_heat(chain: str, token_address: str, token_symbol: str,
                       token_name: str = "", wallet_count_inc: int = 1,
                       usd_value_add: float = 0) -> None:
    """更新或插入代币热度记录"""
    conn = get_conn()
    now = datetime.now().isoformat()
    existing = conn.execute(
        "SELECT id, wallet_count, total_usd_value FROM token_heat WHERE chain = ? AND token_address = ?",
        (chain, token_address),
    ).fetchone()

    if existing:
        new_wc = existing["wallet_count"] + wallet_count_inc
        new_tv = (existing["total_usd_value"] or 0) + usd_value_add
        import math
        heat = int(new_wc * 15 + math.log(max(new_tv, 1)) * 10)
        heat = min(heat, 100)
        conn.execute(
            """UPDATE token_heat
               SET token_symbol = ?, token_name = ?, wallet_count = ?,
                   total_usd_value = ?, heat_score = ?, last_updated = ?
               WHERE id = ?""",
            (token_symbol, token_name, new_wc, new_tv, heat, now, existing["id"]),
        )
    else:
        import math
        heat = int(wallet_count_inc * 15 + math.log(max(usd_value_add, 1)) * 10)
        heat = min(heat, 100)
        conn.execute(
            """INSERT INTO token_heat
               (chain, token_address, token_symbol, token_name, heat_score,
                wallet_count, total_usd_value, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (chain, token_address, token_symbol, token_name, heat,
             wallet_count_inc, usd_value_add, now),
        )
    conn.commit()
    conn.close()


def get_hot_tokens(limit: int = 10, chain: str = None) -> list:
    """获取热门代币排行"""
    conn = get_conn()
    if chain:
        rows = conn.execute(
            "SELECT * FROM token_heat WHERE chain = ? ORDER BY heat_score DESC LIMIT ?",
            (chain, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM token_heat ORDER BY heat_score DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def reset_daily_token_heat() -> None:
    """每日重置代币热度（24小时窗口）"""
    conn = get_conn()
    conn.execute("UPDATE token_heat SET wallet_count = 0, total_usd_value = 0, heat_score = 0")
    conn.commit()
    conn.close()


# ============================================================
# 每日摘要 (daily_digest)
# ============================================================

def save_daily_digest(date_str: str, digest: dict) -> None:
    """保存或更新每日摘要"""
    conn = get_conn()
    import json
    digest_json = json.dumps(digest, ensure_ascii=False)
    conn.execute(
        """INSERT OR REPLACE INTO daily_digest (date, digest_json, pushed)
           VALUES (?, ?, 0)""",
        (date_str, digest_json),
    )
    conn.commit()
    conn.close()


def get_daily_digest(date_str: str) -> dict | None:
    """获取指定日期的摘要"""
    conn = get_conn()
    import json
    row = conn.execute(
        "SELECT * FROM daily_digest WHERE date = ?",
        (date_str,),
    ).fetchone()
    conn.close()
    if row:
        digest = json.loads(row["digest_json"])
        digest["pushed"] = bool(row["pushed"])
        return digest
    return None


def mark_digest_pushed(date_str: str) -> None:
    """标记摘要已推送"""
    conn = get_conn()
    conn.execute("UPDATE daily_digest SET pushed = 1 WHERE date = ?", (date_str,))
    conn.commit()
    conn.close()


# ============================================================
# 初始化
# ============================================================
if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
