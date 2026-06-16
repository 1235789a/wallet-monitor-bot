# 地址池审计报告 · seed_wallets.py (v1)

> 审计对象：`seed_wallets.py` 中的 `SEED_WALLETS`（100 条）+ `wallets.json`
> 审计目标：识别占位 / 重复 / 无效 / 合约 / 无来源地址，为 v2 三级地址池提供清洗依据
> 原则：来源可追溯 > 数量 > 纯度；交易所地址保留但不参与 Alpha 评分

---

## 一、总体结论

旧地址池 **100 条中约 78 条不可用**，核心问题是大量"按十六进制顺序递增编造"的占位地址。

| 类别 | 数量 | 处置 |
|------|------|------|
| 占位地址（手写编造，链上不存在） | ~70 | ❌ 删除 |
| 重复地址（同一 hex 被复用到多个 nickname） | ~6 | ❌ 删除重复项 |
| 非法 Tron 地址（不符合 Base58Check） | 9 | ❌ 删除 |
| 稳定币合约地址（USDT/USDC 合约，非钱包） | 2 | ❌ 删除（移入黑名单） |
| 真实交易所热钱包 | ~5 | ✅ 保留，category=exchange，participate_alpha=false |
| 真实链上实体（Vitalik / Wintermute 等） | ~10 | ✅ 保留，进入 L1/L2 |
| 真实 Tron 钱包（wallets.json） | 1 | ✅ 保留 |

**旧池可信地址实际仅 ~16 个。**

---

## 二、问题明细

### 2.1 占位地址（最严重，约 70 个）

特征：十六进制按 `A1B2C3D4E5F6...` 顺序递增 / 平移生成，链上不存在。

示例：
```
0xA1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6E7F8A9B0   "Cumberland"
0xB3C4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2   "Polychain Capital"
0xC4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3   "Spartan Group"
0xD5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4   "Binance Labs"
... （Smart Trader 1~15、Whale ETH 1~5、几乎所有 fund/trader/补充项）
```
这些 nickname 是真实机构名，但**地址是假的**——把真名挂在假地址上，比纯假更危险，会让人误以为可信。全部删除。

### 2.2 重复地址（约 6 处）

按模式平移编号导致同一 hex 复用：

| 地址 | 被复用的 nickname |
|------|------|
| `0xC0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9` | "Wintermute BSC" / "Defiance Capital" / "Hashed" |
| `0xD1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0` | "Dragonfly Capital" / "Three Arrows" / "1confirmation" |
| `0xE2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1` | "Pantera" / "Alameda" / "Arrington Capital" |
| `0xE6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5` | "Framework Ventures" / "Flow Traders" |
| `0xF7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6` | "Delphi Digital" / "Keyrock" |
| `0xA4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3` | "Whale ETH 4" / "Coinbase Ventures" |

（这些本身也是占位地址，连同 2.1 一起删除）

### 2.3 非法 Tron 地址（9 个）

Tron 地址必须是 Base58Check、以 T 开头、34 字符、校验位正确。以下全是编造，无法通过校验：
```
TA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S   "Whale Tron 2"   （含非 Base58 字符 0/O/I/l 等）
TB2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T   "Whale Tron 3"
TC3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U   "Smart Tron 1"
... （Smart Tron 2~4、MM Tron 1~3 同理）
```
仅 `TXFkJv3VRCg9LJhvyvLCfqxGVvq3vKTL5h`（Whale Tron 1）格式看似合法，但**无来源**，只能进 L3 观察池且需标注 `source=unverified`。

### 2.4 稳定币合约地址（2 个，归类错误）

```
0xdAC17F958D2ee523a2206206994597C13D831ec7   标为 "USDT Contract" / category=exchange
0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48   标为 "USDC Contract" / category=exchange
```
这是**代币合约**，不是钱包。会产生海量转账噪音，污染热度榜。删除并加入 `CONTRACT_BLACKLIST`，监控层永久过滤。

### 2.5 真实可保留地址（~16 个）

| 地址 | 实体 | 来源 | 处置 tier / category |
|------|------|------|------|
| `0xdbf5E9c5206d0dB70a90108bf936DA60221dC080` | Wintermute | etherscan 公开标签 | L1 / market_maker |
| `0x28C6c06298d514Db089934071355E5743bf21d60` | Binance 14 热钱包 | etherscan | exchange / participate_alpha=false |
| `0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549` | Binance 热钱包 | etherscan | exchange / false |
| `0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8` | Binance 7 热钱包 | etherscan | exchange / false |
| `0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B` | Vitalik Buterin | etherscan/eth-labels | L1 / whale |
| `0x1Db3439a222C519aB44bb1144fC28167b4Fa6EE6` | Vitalik | etherscan/eth-labels | L1 / whale |
| `0x220866B1A2219f40e72f5c628B65D54268cA3A9D` | Vitalik | etherscan/eth-labels | L1 / whale |
| `0x73BCEb1Cd57C711feaC4224D062b0F6ff338501e` | EF / 早期以太坊 | eth-labels | L2 / whale |
| `0x8EB8a3b98659Cce290402893d0123abb75E3ab28` | 知名鲸鱼 | etherscan | L2 / whale |
| `TAFyvB8GALgHVF6jGUYseEZTc6BjHMjqMc` | 用户波场钱包(wallets.json) | user | L3 / observe |

---

## 三、旧地址池评分（满分 100）

| 维度 | 得分 | 说明 |
|------|------|------|
| 来源可追溯 | 5 / 25 | 几乎无来源标注，nickname 误导 |
| 地址有效性 | 16 / 25 | 仅 ~16% 是真实有效地址 |
| 信号可产出性 | 4 / 20 | 78% 假地址永远不会产生链上活动 |
| 分层 / 噪音控制 | 0 / 15 | 无 tier，合约地址混入 |
| 可扩展性 | 5 / 15 | 纯手工硬编码，无法自动扩充 |
| **总分** | **30 / 100** | **不可商用** |

---

## 四、清洗后进入 v2 的依据

1. 删除全部占位 / 重复 / 非法 Tron / 合约地址（共 ~80 条）
2. 保留 ~16 个真实地址，按实体性质分配 tier 与 category
3. 交易所地址 `participate_alpha=false`，保留用于资金流向参考但不计入 Alpha 评分
4. L2 / L3 由 `fetch_labels.py` 从 GitHub eth-labels / Dune / Etherscan 公开标签自动填充
5. 所有地址强制带 `source` 字段，无来源者最高只能进 L3
