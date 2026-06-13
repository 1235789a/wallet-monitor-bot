# 🔔 Wallet Token Monitor

> **基于 GitHub Actions 的免费地址代币到账监控**——零服务器成本，24/7 自动运行，发现 Token 转入立即通过 Telegram 推送通知。

---

## 📦 产品简介

你有一笔 USDT 要收，但不想一直守着 Etherscan 看？  
你在跑项目收款，需要一个实时到账通知？

Wallet Token Monitor 让你用 **GitHub 免费资源** 搭一个全天候运行的地址监控系统：

- 🆓 **完全免费**：GitHub Actions（公开仓库）+ Telegram Bot + Etherscan 免费 API
- ⚡ **实时推送**：每 5 分钟自动检测，新到账秒推送到手机
- 🏦 **多链支持**：Ethereum 主网 + BSC 链，可扩展
- 🔒 **仅看收入**：只监控 Token 转入，不关注转出
- 💾 **防重复**：每笔转账唯一指纹，不会重复提醒

---

## 🏗️ 架构

```
┌──────────────────────────────────────────────────┐
│                  GitHub Actions                     │
│                 (每 5 分钟触发)                      │
│                                                    │
│  ┌──────────┐     ┌──────────┐     ┌───────────┐ │
│  │ 读取      │     │ 查询      │     │ 推送       │ │
│  │ wallets. │ ──► │ Etherscan│ ──► │ Telegram  │ │
│  │ json     │     │ / BSCScan│     │ Bot       │ │
│  └──────────┘     └──────────┘     └───────────┘ │
│                         │                         │
│                    ┌────▼─────┐                    │
│                    │ 对比状态   │                    │
│                    │ 去重指纹   │                    │
│                    └──────────┘                    │
└──────────────────────────────────────────────────┘
```

---

## 🚀 1 分钟部署

### ① Fork 本仓库

点击右上角 **Fork**，把代码拷贝到你自己的 GitHub 账户。

### ② 获取 API Key

| 服务 | 地址 | 费用 |
|------|------|------|
| Etherscan | [etherscan.io/register](https://etherscan.io/register) | 免费（5次/秒） |
| BSCScan（可选） | [bscscan.com/register](https://bscscan.com/register) | 免费（5次/秒） |

### ③ 创建 Telegram Bot

1. 在 Telegram 搜索 **@BotFather**
2. 发送 `/newbot`，按提示设置名称和用户名
3. 拿到 Bot Token（类似 `123456:ABCdefGHIjklMNOpqrsTUVwxyz`）
4. 给你的 Bot 随便发一条消息
5. 浏览器访问 `https://api.telegram.org/bot<你的Token>/getUpdates`
6. 找到返回的 `chat.id`（纯数字）

### ④ 设置 GitHub Secrets

进入仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加：

| Secret Name | 示例值 |
|-------------|--------|
| `TELEGRAM_BOT_TOKEN` | `123456:ABCdefGHIjklMNOpqrsTUVwxyz` |
| `TELEGRAM_CHAT_ID` | `987654321` |
| `ETHERSCAN_API_KEY` | `ABCDEFG123456...` |
| `BSCSCAN_API_KEY` | `HJKLMNOP789...`（BSC 可选，不需要则随便填） |

### ⑤ 配置监控地址

编辑仓库里的 `wallets.json`：

```json
{
  "wallets": [
    {
      "address": "0x你的钱包地址",
      "chains": ["ethereum", "bsc"]
    }
  ]
}
```

- `address`：你要监控的钱包地址
- `chains`：要监控的链，可选 `["ethereum"]`, `["bsc"]`, `["ethereum", "bsc"]`

### ⑥ 提交 & 运行

Push 代码到 GitHub 后，Actions 会自动开始工作。

你也可以手动触发：**Actions → Wallet Token Monitor → Run workflow**。

---

## 📱 通知效果

收到到账时，你的 Telegram 会收到：

```
🔷 新到账！

📬 地址: 0x1a2b3...c4d5
💰 数量: 1500.00 USDT
🪙 Token: Tether USD (USDT)
📤 发送方: 0xabcd12...
⛓️  链: BSC
🕐 时间: 2026-06-13 12:30:00 UTC
🔗 查看交易
```

---

## 📁 文件说明

| 文件 | 用途 |
|------|------|
| `monitor.py` | 核心监控脚本 |
| `wallets.json` | 监控地址配置 |
| `last_state.json` | 上次状态（自动更新，不需要手动改） |
| `.github/workflows/monitor.yml` | GitHub Actions 定时触发配置 |
| `index.html` | GitHub Pages 产品落地页 |

---

## 🔧 扩展更多链

在 `monitor.py` 的 `CHAINS` 字典中添加新链即可，例如 Polygon：

```python
"polygon": {
    "name": "Polygon",
    "emoji": "🟣",
    "api_url": "https://api.polygonscan.com/api",
    "api_key": os.environ.get("POLYGONSCAN_API_KEY", ""),
    "explorer": "https://polygonscan.com",
},
```

同时在 GitHub Secrets 添加 `POLYGONSCAN_API_KEY`，并在 `.github/workflows/monitor.yml` 中传入环境变量。

---

## ⚠️ 注意事项

- **公开仓库**：wallets.json 中的地址任何人可见。如需隐私，使用**私有仓库**（但 GitHub Actions 私有仓库每月 2000 分钟限额）
- **API 限制**：Etherscan 免费版 5 次/秒，足够每 5 分钟轮询多个地址
- **时区**：GitHub Actions cron 用 UTC 时间，`*/5 * * * *` = 每 5 分钟 UTC
- **GitHub Pages**：在 Settings → Pages 启用，选择 `main` 分支 `/ (root)`，你的落地页就上线了

---

## 🛠️ 本地测试

```bash
# 安装依赖
pip install requests

# 设置环境变量
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="987654321"
export ETHERSCAN_API_KEY="YourApiKey"

# 运行
python monitor.py
```

---

## 📄 License

MIT — 随便用，随便改，随便赚钱。