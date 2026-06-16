# 🐋 Whale Tracker TG Bot

实时监控链上鲸鱼钱包动向的 Telegram Bot。支持 Ethereum、BSC、Tron 三链，USDT 收款，并内置「聪明钱 Alpha 信号」与每日日报。

**Reddit 原始需求**: [/r/ethereum: "How do you guys track whale wallet movements?"](https://reddit.com/r/ethereum/comments/1dz71h6/how_do_you_guys_track_whale_wallet_movements/) (👍198 upvotes, 109 comments)

## 功能

- 🆓 免费试用 3 天，追踪 3 个钱包
- 💎 付费 USDT/月，追踪 50 个钱包
- 🔔 实时推送大额转账（≥$1,000，可配置）
- 🧠 Alpha 聪明钱信号：代币热度榜 + 聪明钱排行（Pro 全量，Free 脱敏）
- 📊 每日定时 Alpha 日报推送
- 🔗 支持 Ethereum / BSC / Tron
- 💰 USDT (TRC20) 链上自动验证支付
- 📱 Telegram 交互式按钮菜单

## 上线前准备清单

要让 Bot 真正跑起来并能收钱，你需要准备：

### 必填
1. **TG_BOT_TOKEN** — 在 Telegram 找 [@BotFather](https://t.me/BotFather)，发送 `/newbot`，按提示创建后获得 token。
2. **PAYOUT_WALLET** — 你自己的 USDT 收款地址（推荐 Tron TRC20）。用户付款直接进这个地址。

### 强烈建议
3. **链上 API Key**（免费注册）：
   - `TRONGRID_API_KEY` — https://www.trongrid.io
   - `ETHERSCAN_API_KEY` — https://etherscan.io/apis
   - `BSCSCAN_API_KEY` — https://bscscan.com/apis
4. **ADMIN_USER_IDS** — 你的 Telegram 数字 ID（用 [@userinfobot](https://t.me/userinfobot) 查询），用于 `/broadcast` 群发功能。

把以上都填到 `.env` 文件里（见下方「快速开始」）。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，至少填入 TG_BOT_TOKEN 和 PAYOUT_WALLET

# 3. 运行
python bot.py
```

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `TG_BOT_TOKEN` | ✅ | Telegram Bot Token (从 @BotFather 获取) |
| `PAYOUT_WALLET` | ✅ | 你的 USDT 收款地址 (Tron TRC20) |
| `TRONGRID_API_KEY` | 推荐 | TronGrid API Key (免费注册) |
| `ETHERSCAN_API_KEY` | 推荐 | Etherscan API Key |
| `BSCSCAN_API_KEY` | 推荐 | BSCscan API Key |
| `ADMIN_USER_IDS` | 推荐 | 管理员 TG ID，逗号分隔，用于 /broadcast |
| `PRICE_USDT` | 可选 | 月费（默认 5） |
| `TRIAL_DAYS` | 可选 | 试用天数（默认 3） |
| `MIN_USD_VALUE` | 可选 | 最低推送金额（默认 1000） |
| `CHECK_INTERVAL_MINUTES` | 可选 | 鲸鱼扫描间隔（默认 10） |
| `DIGEST_HOUR_UTC` | 可选 | 日报推送时间 UTC 小时（默认 12） |

完整可调参数见 `.env.example`。

## 命令列表

| 命令 | 说明 |
|------|------|
| `/start` | 注册/欢迎 |
| `/add eth <地址> <标签>` | 添加追踪地址 |
| `/remove <地址>` | 移除追踪地址 |
| `/list` | 查看追踪列表 |
| `/status` | 账户状态 |
| `/pay` | 升级付费 |
| `/verify <地址>` | 验证支付 |
| `/alpha` | 查看聪明钱 Alpha 信号 |
| `/digest` | 查看今日 Alpha 日报 |
| `/smart` | 查看追踪的聪明钱地址 |
| `/broadcast <消息>` | 管理员群发（仅 ADMIN_USER_IDS） |

## 项目结构

```
wallet-monitor-bot/
├── bot.py          # TG Bot 主程序（命令 + 按钮 + 后台循环）
├── config.py       # 配置（自动加载 .env）
├── models.py       # SQLite 数据库模型
├── monitor.py      # 链上监控引擎 + 聪明钱扫描
├── alpha.py        # 聪明钱聚合器
├── payment.py      # USDT 支付检测
├── scorer.py       # 聪明钱评分
├── seed_wallets.py # 初始聪明钱种子地址
├── requirements.txt
├── .env.example
└── README.md
```

## 部署（长期运行）

Bot 需要 7x24 运行才能持续监控和推送。几种常见方式：

### 方式 A：云服务器 + systemd（推荐）

在 Linux 服务器上创建 `/etc/systemd/system/whale-bot.service`：

```ini
[Unit]
Description=Whale Tracker TG Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/wallet-monitor-bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

然后：

```bash
sudo systemctl daemon-reload
sudo systemctl enable whale-bot
sudo systemctl start whale-bot
sudo systemctl status whale-bot       # 查看状态
journalctl -u whale-bot -f            # 查看实时日志
```

### 方式 B：本地长期挂机

```bash
# Windows: 直接运行，保持终端开启
python bot.py

# Linux/Mac: 后台运行
nohup python3 bot.py > bot.log 2>&1 &
```

注意本地挂机时电脑不能休眠/关机。

### 方式 C：Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

```bash
docker build -t whale-bot .
docker run -d --restart=always --env-file .env --name whale-bot whale-bot
```

## 安全提示

- ⚠️ **切勿把 `.env`、`*.db` 提交到 GitHub**（已在 `.gitignore` 中排除）。
- ⚠️ 如果任何 API Key 或 Token 曾经泄露（例如贴到聊天/截图里），请立即去对应平台**吊销并重新生成**。
- Bot 通过 Telegram 官方 API 通信，本身不持有用户私钥，只读取公开链上数据。

## 获客策略

1. **Reddit 原帖投饵**: 去 [/r/ethereum 原帖](https://reddit.com/r/ethereum/comments/1dz71h6/how_do_you_guys_track_whale_wallet_movements/) 回复你的 Bot 链接
2. **Crypto Twitter**: 在钱包追踪相关话题下推广
3. **Telegram 群组**: 在加密货币社群安利

## License

MIT
