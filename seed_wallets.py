# -*- coding: utf-8 -*-
"""
Smart Money Intelligence · 内置聪明钱种子数据 v2（已清洗）

v1 → v2 变更（详见 audit_report.md）：
- 删除 ~80 条占位 / 重复 / 非法 Tron / 合约地址
- 仅保留链上真实存在、来源可追溯的地址
- 每条地址带 tier / source / participate_alpha 三个字段

字段说明
--------
tier              : 1=核心聪明钱  2=可信机构/交易员  3=观察池
source            : 来源可追溯标记（etherscan / eth-labels / user ...）
participate_alpha : 1=参与代币热度Alpha评分  0=仅作资金流向参考（交易所热钱包）

分类 category
-------------
market_maker : 做市商      fund    : 投资基金
whale        : 知名鲸鱼    exchange: 交易所热钱包
trader       : 知名交易员
"""

# ============================================================
# 合约黑名单：代币合约，不是钱包，永久不入池（防热度榜污染）
# ============================================================
CONTRACT_BLACKLIST = {
    "ethereum": [
        "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT 合约
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC 合约
    ],
    "bsc": [
        "0x55d398326f99059ff775485246999027b3197955",  # USDT 合约
        "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",  # USDC 合约
    ],
    "tron": [
        "tr7nhqjekqxgtci8q8zy4pl8otszgjlj6t",          # USDT 合约
    ],
}


def is_blacklisted_contract(address: str, chain: str) -> bool:
    """判断地址是否为已知代币合约（黑名单）"""
    return address.lower() in CONTRACT_BLACKLIST.get(chain, [])


# ============================================================
# 种子地址池 v2（清洗后的真实地址）
# 全部来源于 Etherscan 公开标签 / eth-labels 公共数据集 / 用户提供
# ============================================================
SEED_WALLETS = [
    {
        "address": "0x073dca8acbc11ffb0b5ae7ef171e4c0b065ffa47",
        "chain": "ethereum",
        "nickname": "Alameda Research 1",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x882a812d75aee53efb8a144f984b258b6c4807f0",
        "chain": "ethereum",
        "nickname": "Alameda Research 10",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xbefe4f86f189c1c817446b71eb6ac90e3cb68e60",
        "chain": "ethereum",
        "nickname": "Alameda Research 11",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xb78e90e2ec737a2c0a24d68a0e54b410fff3bd6b",
        "chain": "ethereum",
        "nickname": "Alameda Research 12",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x964d9d1a532b5a5daeacbac71d46320de313ae9c",
        "chain": "ethereum",
        "nickname": "Alameda Research 13",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xfa453aec042a837e4aebbadab9d4e25b15fad69d",
        "chain": "ethereum",
        "nickname": "Alameda Research 14",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x4deb3edd991cfd2fcdaa6dcfe5f1743f6e7d16a6",
        "chain": "ethereum",
        "nickname": "Alameda Research 15",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x477573f212a7bdd5f7c12889bd1ad0aa44fb82aa",
        "chain": "ethereum",
        "nickname": "Alameda Research 16",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xce31190a03fc3c5f23167e88e75066824823222d",
        "chain": "ethereum",
        "nickname": "Alameda Research 17",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x73c0ae50756c7921d1f32ada71b8e50c5de7ff9c",
        "chain": "ethereum",
        "nickname": "Alameda Research 19",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x712d0f306956a6a4b4f9319ad9b9de48c5345996",
        "chain": "ethereum",
        "nickname": "Alameda Research 2",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x60ae578abdfded1fb0555f54148fdd7b400a34ed",
        "chain": "ethereum",
        "nickname": "Alameda Research 20",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0c0fe4e0236480e16b679ee1fd0c5247f9cf35f0",
        "chain": "ethereum",
        "nickname": "Alameda Research 22",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0f4ee9631f4be0a63756515141281a3e2b293bbe",
        "chain": "ethereum",
        "nickname": "Alameda Research 23",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x97137466bc8018531795217f0ecc4ba24dcba5c1",
        "chain": "ethereum",
        "nickname": "Alameda Research 24",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x84d34f4f83a87596cd3fb6887cff8f17bf5a7b83",
        "chain": "ethereum",
        "nickname": "Alameda Research 25",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x78835265ac857bf3420830c71987b1a55f73c2dc",
        "chain": "ethereum",
        "nickname": "Alameda Research 26",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x4c8cfe078a5b989cea4b330197246ced82764c63",
        "chain": "ethereum",
        "nickname": "Alameda Research 27",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x93c08a3168fc469f3fc165cd3a471d19a37ca19e",
        "chain": "ethereum",
        "nickname": "Alameda Research 3",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xca436e14855323927d6e6264470ded36455fc8bd",
        "chain": "ethereum",
        "nickname": "Alameda Research 4",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x83a127952d266a6ea306c40ac62a4a70668fe3bd",
        "chain": "ethereum",
        "nickname": "Alameda Research 5",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xc5ed2333f8a2c351fca35e5ebadb2a82f5d254c3",
        "chain": "ethereum",
        "nickname": "Alameda Research 6",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x89183c0a8965c0299997be9af700a801bdccc2da",
        "chain": "ethereum",
        "nickname": "Alameda Research 7",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xe5d0ef77aed07c302634dc370537126a2cd26590",
        "chain": "ethereum",
        "nickname": "Alameda Research 8",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x5d13f4bf21db713e17e04d711e0bf7eaf18540d6",
        "chain": "ethereum",
        "nickname": "Alameda Research 9",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xa726c00cda1f60aaab19bc095d02a46556837f31",
        "chain": "ethereum",
        "nickname": "Alameda Research: WBTC Merchant Deposit ",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x05e793ce0c6027323ac150f6d45c2344d28b6019",
        "chain": "ethereum",
        "nickname": "a16z",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xe11970f2f3de9d637fb786f2d869f8fea44195ac",
        "chain": "ethereum",
        "nickname": "Amber Group",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x23a5efe19aa966388e132077d733672cf5798c03",
        "chain": "ethereum",
        "nickname": "Arca: 0x23a...c03",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xff0cefdbd6bf757cc0cc361ddfbde432186ccaa6",
        "chain": "ethereum",
        "nickname": "Auros Global",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x40c20da8d0214a7ef33a84e287992858db744e6d",
        "chain": "ethereum",
        "nickname": "BridgeTower Capital: Lido Node Operator",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x9b5ea8c719e29a5bd0959faf79c9e5c8206d0499",
        "chain": "ethereum",
        "nickname": "DeFiance Capital",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x1157a2076b9bb22a85cc2c162f20fab3898f4101",
        "chain": "ethereum",
        "nickname": "FalconX: 0x115...101",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x60009b78da046ac64ef789c29ca05b79cdf73c10",
        "chain": "ethereum",
        "nickname": "FalconX: Foster City",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xfe78617ec612ac67bcc9cc145d376400f15a82cb",
        "chain": "ethereum",
        "nickname": "Figment Capital: Lido Node Operator",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0716a17fbaee714f1e6ab0f9d59edbc5f09815c0",
        "chain": "ethereum",
        "nickname": "Fund: 0x071...5C0",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x112b69178d416cd03222de9e6dd6b3adf36412aa",
        "chain": "ethereum",
        "nickname": "Fund: 0x112...2aa",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x11577a8a5baf1e25b9a2d89f39670f447d75c3cd",
        "chain": "ethereum",
        "nickname": "Fund: 0x115...3cD",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x2e675eeae4747c248bfddbafaa3a8a2fdddaa44b",
        "chain": "ethereum",
        "nickname": "Fund: 0x2e6...44b",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x3ba21b6477f48273f41d241aa3722ffb9e07e247",
        "chain": "ethereum",
        "nickname": "Fund: 0x3BA...247",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x4655b7ad0b5f5bacb9cf960bbffceb3f0e51f363",
        "chain": "ethereum",
        "nickname": "Fund: 0x465...363",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x66b870ddf78c975af5cd8edc6de25eca81791de1",
        "chain": "ethereum",
        "nickname": "Fund: 0x66b...de1",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x74c749a9987b2cd6913bbf71a9a139bcd372f441",
        "chain": "ethereum",
        "nickname": "Fund: 0x74c...441",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x82ac5170a837f6554d518c71c0590723437e6b64",
        "chain": "ethereum",
        "nickname": "Fund: 0x82a...b64",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x8e04af7f7c76daa9ab429b1340e0327b5b835748",
        "chain": "ethereum",
        "nickname": "Fund: 0x8e0...748",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x946254eb330d15a4a158f253948b2cb61a6e64ed",
        "chain": "ethereum",
        "nickname": "Fund: 0x946...4ed",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x9799b475dec92bd99bbdd943013325c36157f383",
        "chain": "ethereum",
        "nickname": "Fund: 0x979...383",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xa294cca691e4c83b1fc0c8d63d9a3eef0a196de1",
        "chain": "ethereum",
        "nickname": "Fund: 0xa29...de1",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xadd48281714eeafac2a266f4929406b90f8d9029",
        "chain": "ethereum",
        "nickname": "Fund: 0xadd...029",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xaeb7855a713b4d8354f659c15a25cda11f466c28",
        "chain": "ethereum",
        "nickname": "Fund: 0xAeb...C28",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xafa64cca337efee0ad827f6c2684e69275226e90",
        "chain": "ethereum",
        "nickname": "Fund: 0xafa...e90",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xd9b012a168fb6c1b71c24db8cee1a256b3caa2a2",
        "chain": "ethereum",
        "nickname": "Fund: 0xd9b...2a2",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xef9a85ff6fc161e88b58056a3b94a7f207d20336",
        "chain": "ethereum",
        "nickname": "Fund: 0xef9...336",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xf1556137e7f45817e774096c5922f32c68ab15ae",
        "chain": "ethereum",
        "nickname": "Fund: 0xf15...5ae",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xfa9b5f7fdc8ab34aaf3099889475d47febf830d7",
        "chain": "ethereum",
        "nickname": "Fund: 0xfa9...0d7",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x9d9588c082634fd4c7f54cb0243d6792cfd7b4c4",
        "chain": "ethereum",
        "nickname": "Infinity Ventures Crypto",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xf584f8728b874a6a5c7a8d4d387c9aae9172d621",
        "chain": "ethereum",
        "nickname": "Jump Trading",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x6633a4a14209d40694db630c251d1e8036663c5c",
        "chain": "ethereum",
        "nickname": "Spartan Group",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x23b4cd421b7cb7d274689b2a7c100baf8546941b",
        "chain": "ethereum",
        "nickname": "Taureon Capital",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x4862733b5fddfd35f35ea8ccf08f5045e57388b3",
        "chain": "ethereum",
        "nickname": "Three Arrows Capital",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xf30026fe8a2c0d01b70b1949ceaf2e09efd8b4a5",
        "chain": "ethereum",
        "nickname": "Three Arrows Capital 2",
        "category": "fund",
        "tier": 2,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0xeb4c5ab9b36437f969888be99af42fc9087005a5",
        "chain": "ethereum",
        "nickname": "AMB Flashbot Helper",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x00000007f7a9056880d057f611e80c419f9b20c8",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x00...0c8",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x000000000005af2ddc1a93a03e9b7014064d3b8d",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x00...b8D",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000009076d16e15bb69d35f4717e9d4268efc7b",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x00...c7B",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000000036414940324055c43e75f56b7d016",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...016",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000009cb38fb8a1bbb8ada23c8261118f019",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...019",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x000000000085359dbc0eb45911e5f3f7a532a07e",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...07E",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x000000000000084e91743124a982076c59f10084",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...084",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x000000000a08a7ca00e4239dd97d8542c51b9086",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...086",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000007c68390193776e8b44df3b698d311070b9",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...0B9",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x00000000000123685885532dcb685c442dc83126",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...126",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000023191c8382251c0a1ae2f4db983d414c",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...14C",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x00000000003eea204b86b877632d9ee88b179150",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...150",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x000000004b614af95d1bb7c236a3aa800b722173",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...173",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000000d41c96294ccdac8612bdfe29c641af",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...1af",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000084f794716fa5485d1424b8bd562291f9",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...1f9",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x00000000000c66b8cb2836c3620f88a9c812d208",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...208",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000000b92ac90d898eba87fa5f2483f32234",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...234",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x00000000000a47b1298f18cf67de547bbe0d723f",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...23F",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000000a84d1a9b0063a910315c7ffa9cd248",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...248",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000004f2f05a8223b89edb700848d70970742bf",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...2bF",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x000000000dfde7deaf24138722987c9a6991e2d4",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...2D4",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x00000000f6e788341c1acb3c2d49fa9263b8a2f7",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...2F7",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000050fd1220ecf21d84687ebad194fd537f",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...37F",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x000000000b8a22fdae0233faa785df7974ff0391",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...391",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000000e43e0c383403dd18066ff60d5003b3",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...3b3",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000000710a9c1f6db5f504be77ffb3b583ec",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...3ec",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x000000004b5ad44f70781462233d177d32d993f1",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...3f1",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000000208d4805eb97db796e74b48547445d",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...45d",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x000000000000660def84e69995117c0176ba446e",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...46E",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x00000000000062f06c7007906b2a4034fa5c4818",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...4818",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x000000000003c42172c0bdd69d6afb6b0bf4b488",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...488",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x000000000025d4386f7fb58984cbe110aee3a4c4",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...4c4",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000096b674bb0ea9c74c28be782bb48724de",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...4de",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x000000000000f0bc41c73af48f022f8c27b5350e",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...50e",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x0000000000cbba74c365869ae50225f5596ad59c",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...59c",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x00000000b7ca7e12dcc72290d1fe47b2ef14c607",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...607",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "0x00000000726422a6fecb4759b44d47e48cf746aa",
        "chain": "ethereum",
        "nickname": "MEV Bot: 0x000...6aa",
        "category": "trader",
        "tier": 1,
        "source": "etherscan-labels",
        "participate_alpha": 1,
    },
    {
        "address": "TAFyvB8GALgHVF6jGUYseEZTc6BjHMjqMc",
        "chain": "tron",
        "nickname": "User Tron Wallet",
        "category": "whale",
        "tier": 3,
        "source": "user",
        "participate_alpha": 1,
    },
]


# ============================================================
# 分类 emoji / 标签映射
# ============================================================
CATEGORY_EMOJI = {
    "market_maker": "🏦",
    "fund": "💰",
    "whale": "🐋",
    "exchange": "🏛️",
    "trader": "🧠",
}

CATEGORY_LABEL = {
    "market_maker": "做市商",
    "fund": "投资基金",
    "whale": "鲸鱼",
    "exchange": "交易所",
    "trader": "聪明交易者",
}

TIER_LABEL = {
    1: "核心聪明钱",
    2: "可信机构/交易员",
    3: "观察池",
}


def seed_database(conn):
    """
    将种子数据导入 smart_wallets 表（带 tier/source/participate_alpha）。
    跳过黑名单合约地址；已存在的地址按更高可信度合并。
    返回 (inserted, skipped)。
    """
    cursor = conn.cursor()
    inserted = 0
    skipped = 0

    for wallet in SEED_WALLETS:
        addr = wallet["address"]
        chain = wallet["chain"]

        # 跳过合约黑名单
        if is_blacklisted_contract(addr, chain):
            skipped += 1
            continue

        # 检查是否已存在
        cursor.execute(
            "SELECT id, tier, source FROM smart_wallets WHERE address = ? AND chain = ?",
            (addr, chain),
        )
        row = cursor.fetchone()

        tier = wallet.get("tier", 3)
        source = wallet.get("source", "unverified")
        participate_alpha = wallet.get("participate_alpha", 1)

        if row:
            # 已存在：tier 取更小(更可信)值，source 非 unverified 时覆盖
            existing_tier = row["tier"] if "tier" in row.keys() and row["tier"] is not None else 3
            existing_source = row["source"] if "source" in row.keys() and row["source"] else "unverified"
            new_tier = min(existing_tier, tier)
            new_source = source if source != "unverified" else existing_source
            cursor.execute(
                """UPDATE smart_wallets
                   SET nickname = ?, category = ?, tier = ?, source = ?, participate_alpha = ?
                   WHERE id = ?""",
                (wallet["nickname"], wallet["category"], new_tier,
                 new_source, participate_alpha, row["id"]),
            )
            skipped += 1
            continue

        cursor.execute(
            """INSERT INTO smart_wallets
               (address, chain, nickname, category, score, tier, source, participate_alpha)
               VALUES (?, ?, ?, ?, 50, ?, ?, ?)""",
            (addr, chain, wallet["nickname"], wallet["category"],
             tier, source, participate_alpha),
        )
        inserted += 1

    conn.commit()
    return inserted, skipped


if __name__ == "__main__":
    from models import get_conn, init_db
    init_db()
    conn = get_conn()
    inserted, skipped = seed_database(conn)
    conn.close()
    print(f"Seed complete: {inserted} inserted, {skipped} skipped (total={len(SEED_WALLETS)})")
