# 🐋 Whale Tracker TG Bot

实时监控链上鲸鱼钱包动动的 Telegram Bot。支持 Ethereum、BSC、Tron 三链，USDT 收款。

**Reddit 原始需求**: [/r/ethereum: "How do you guys track whale wallet movements?"](https://reddit.com/r/ethereum/comments/1dz71h6/how_do_you_guys_track_whale_wallet_movements/) (👍198 upvotes, 109 comments)

## 功能

- 🆓 免费试用 3 天，追踪 3 个钱包
- 💎 付费 $9.9 USDT/月，追踪 10 个钱包
- 🔔 实时推送大额转账（≥$10,000，可配置）
- 🔗 支持 Ethereum / BSC / Tron
- 💰 USDT (TRC20) 链上自动验证支付
- 📱 Telegram 交互式按钮菜单

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 TG_BOT_TOKEN 和 PAYOUT_WALLET

# 3. 运行
python bot.py
```

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `TG_BOT_TOKEN` | ✅ | Telegram Bot Token (从 @BotFather 获取) |
| `PAYOUT_WALLET` | ✅ | 你的 USDT 收款地址 (Tron TRC20) |
| `TRONGRID_API_KEY` | 推荐 | TronGrid API Key (免费注册) |
| `ETHERSCAN_API_KEY` | 可选 | Etherscan API Key |
| `BSCSCAN_API_KEY` | 可选 | BSCscan API Key |

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

## 项目结构

```
whale_tracker_bot/
├── bot.py          # TG Bot 主程序
├── config.py       # 配置
├── models.py       # SQLite 数据库模型
├── monitor.py      # 链上监控引擎
├── payment.py      # USDT 支付检测
├── requirements.txt
├── .env.example
└── README.md
```

## 获客策略

1. **Reddit 原帖投饵**: 去 [/r/ethereum 原帖](https://reddit.com/r/ethereum/comments/1dz71h6/how_do_you_guys_track_whale_wallet_movements/) 回复你的 Bot 链接
2. **Crypto Twitter**: 在钱包追踪相关话题下推广
3. **Telegram 群组**: 在加密货币社群安利

## License

MIT