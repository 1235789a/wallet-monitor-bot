# 部署指南 · Whale Tracker TG Bot

本 Bot 采用 **long-polling（长轮询）** 方式运行，不需要公网端口/域名，
因此最适合以 **后台 worker** 形式部署到云平台（Railway / Render / Fly.io / 任意 VPS）。

> ⚠️ 安全第一：你在对话里贴出的 GitHub 令牌（ghp_...）和下面的 Telegram Token
> 已经暴露，请立即作废重置（见文末「安全清单」）。

---

## 一、上线前必须改的 1 个配置

云服务器在海外，可直连 Telegram，**不要用本地代理**。
部署时把环境变量 `TG_PROXY` 设为空（不要填 `http://127.0.0.1:7890`），否则连不上。

---

## 二、需要在云平台填的环境变量

| 变量 | 值 | 说明 |
|------|-----|------|
| `TG_BOT_TOKEN` | 你的 BotFather token | **必填**，请重置后填新值 |
| `TG_PROXY` | （留空） | 海外服务器直连，务必为空 |
| `PAYOUT_WALLET` | `TWiDbdetRhXF3cnMHciM1EK8AjTPKHMjJF` | USDT 收款地址 |
| `ETHERSCAN_API_KEY` | 你的 key | 建议重置后填新值 |
| `BSCSCAN_API_KEY` | 你的 key | 选填 |
| `TRONGRID_API_KEY` | 你的 key | 选填，建议申请 |
| `ADMIN_USER_IDS` | `7224621521` | 管理员 TG ID |
| `PRICE_USDT` | `5` | 可选，默认值即可 |
| `CHECK_INTERVAL_MINUTES` | `10` | 可选 |

> 注意：SQLite 数据库 `whale_tracker.db` 存在容器本地磁盘。
> Railway/Render 的容器重建会清空数据。若要持久化订阅/用户数据，
> 需挂载持久卷（Railway Volume）并把 `DATABASE_PATH` 指到卷目录，
> 例如 `/data/whale_tracker.db`。

---

## 三、Railway 部署步骤（推荐，最简单）

1. 打开 https://railway.app ，用 GitHub 登录。
2. New Project → Deploy from GitHub repo → 选 `wallet-monitor-bot`。
3. 部署后进入 Variables 标签，按上表逐个添加环境变量（`TG_PROXY` 留空）。
4. Railway 会自动读取本仓库的 `railway.json` / `Procfile`，用 `python bot.py` 启动。
5. 进入 Deploy Logs，看到 `✅ Bot is running` 即成功。
6. （可选）Settings → Volumes 挂一个卷到 `/data`，并把 `DATABASE_PATH=/data/whale_tracker.db`。

## 四、用 CLI 部署（可选）

```bash
npm i -g @railway/cli
railway login
cd wallet-monitor-bot
railway init
railway up
```

---

## 五、安全清单（务必执行）

- [ ] **作废刚才暴露的 GitHub 令牌**：GitHub → Settings → Developer settings →
      Personal access tokens → 删除 / Regenerate。
- [ ] **重置 Telegram Bot Token**：@BotFather → /revoke，拿新 token 填到云平台。
- [ ] **重置 Etherscan API Key**（已出现在 `.env` 与日志里）。
- [ ] 确认 `.env` 在 `.gitignore` 中（已确认，不会上传）。
