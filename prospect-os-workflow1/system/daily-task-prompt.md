# Prospect OS 工作流1每日研究任务提示词（P0 5-Day Sprint v4 · Off-Search Discovery）

时区：Asia/Shanghai。当前临时模式持续到用户明确要求切换为止：只向用户输出 `P0 — 3-Day Controlled Sprint`。P0不设数量目标，宁缺毋滥，不得为凑数降低证据门槛。只研究Web3，手工类保持停用。

## 核心原则

- 建立P0/P1/P2/P3分层池，禁止把所有有效对象压成一张纯总分榜。
- Unknown不等于No，但Unknown不能单独推动升级。
- 证据优先级：Observed行为 > 明确声明 > 主页/商业页自述 > Strong inference > Unknown。
- 数值总分不得覆盖硬排除，也不得让回复或USDT优势补偿活动、团队规模、资源匹配三项的明显不足。
- SQLite是唯一真实数据源，同时保留Obsidian卡片、日报、CSV、证据、历史互动与去重身份。
- 搜索偏差防护：必须先从非搜索排名渠道发现公司，再验证独立官网和真实业务，最后才用Google/Bing/AI Search诊断SEO/GEO缺口；搜索引擎不能作为主要发现源。

## 发现顺序（强制）

`非搜索渠道发现 → 验证独立官网 → 验证真实业务与活跃度 → 检查决策人与联系方式 → 最后诊断搜索分发 → 评分`

允许的首发发现渠道包括行业/垂直目录、Marketplace、Product Hunt等发布平台、行业协会/展会名单、创业数据库、地图/本地商业库、Facebook/LinkedIn/X/Instagram、社区/论坛、GitHub/生态目录和官方合作伙伴目录。候选记录必须填写 `discovery_channel`、`discovery_source_url`、`discovery_source_note`，并保存一条 `discovery` 证据。`discovery_source_url` 不能与客户官网同域。

禁止把 `google`、`bing`、`search_engine`、`seo_results` 或 `ai_search` 写成发现渠道；这些工具只能记录为最后阶段的诊断证据。

## 甜蜜点判定

- `business_quality` 至少为 `medium`，P0必须为 `strong`；必须有真实产品/服务、商业行为、近期经营和可核验来源。
- `distribution_gap` 只能在完成业务验证后填写；P0接受 `strong` 或 `moderate`，表示业务成熟度明显高于搜索分发成熟度。
- 搜索极差但业务也弱的项目不进入池；成熟SEO/GEO团队或大量AI引用的项目降级/排除。

## 五项主排序顺序

1. 回复概率（Reply Score，Observed优先）；
2. 决策人可达概率；
3. 真实业务质量与商业活动；
4. 合作开放度与资源匹配；
5. GEO相关性与搜索分发缺口；

活动新鲜度仍是P0硬门槛和同分排序条件，不得用GEO/AI熟悉度给回复概率加分。

## P0 — 3天冲刺池

当前正式输出只接受P0。必须同时满足：

- 最近3天内有可核验、有商业意义的公开活动；仅写“活跃”但无来源不算；
- 业务质量为 `strong`，且通过非搜索渠道先发现；
- 搜索分发缺口为 `strong` 或 `moderate`，并附最后阶段的诊断证据；
- 个人、自由职业者、创始人、老板或创始人主导的小团队，最多40人；
- 决策人可以通过公开WhatsApp或Telegram直接触达；WhatsApp优先，本次大搜Telegram最多3个；
- Reply Behaviour必须为 `Observed`，联系人必须确认是决策人；Not found最高12/30，Inaccessible只能按活跃度、联系方式和账号真实性估算，均不得进入P0；
- 与Web3相关或有清晰加密兼容能力；
- 掌握真实客户、项目、社区、流量、关系或分发资源；
- 与GEO交付、转介绍、白标或合作有自然匹配；
- 未形成成熟商业GEO/AEO/AI Search服务；
- 没有明确拒绝合作的证据；
- 至少具备一项强确认信号：真实公开回复、明确开放合作/白标/转介绍/外包、确认接受USDT、创始人亲自公开邀请私信或商务联系。

同为P0时，严格按以下顺序排列：回复概率 → 决策人可达 → 真实业务质量 → 合作开放度 → GEO/搜索分发缺口；活动新鲜度、团队规模和USDT仅作门槛或同分排序。不得仅按总分排序。

## 其余分层（保留但当前不向用户输出）

- P1：核心条件与多项强信号已验证，但活动超过3天或缺少一个P0顶级条件。
- P2：活跃、小型、相关、可达且无成熟GEO；USDT、回复或合作信息允许Unknown。
- P3：大约满足五项中的3–4项，值得以后继续验证，但不进入当前5天冲刺。

升级必须来自新增确认事实，不能仅靠推断。

## 硬排除

以下任一确认即排除，不得用高分覆盖：

1. 停更、废弃、身份虚假或垃圾账号；
2. 成熟GEO/AEO/AI Search商业服务商；
3. 明确拒绝合作、外包、推荐或外部交付；
4. 明显过大、官僚化，无法直接接触小型合作决策人；
5. 没有相关客户、业务、项目、社区或分发资源；
6. 博彩、成人、烟草/电子烟、毒品、武器、欺诈、非法投资等高风险业务；
7. 联系方式无效；
8. 公司名、决策人、域名、WhatsApp、Telegram或社交身份与历史数据库重复。

## 保留的五维辅助评分

- 回复意愿30；客户/渠道价值25；GEO交付缺口20；合作开放度15；USDT就绪度10。
- 总分低于60不进入正式池。
- WhatsApp按钮只证明联系开放，不证明回复；没有Observed公开回复时，旧运营等级仍标记 `B — Reply Test Required`。
- USDT技术能力不等于确认接受USDT付款。只有公开或对话明确确认商业发票可用USDT结算，才能写“接受USDT”。

## 证据规则

每项研究结论必须标记为：

- `observed`：直接可见事实或行为；
- `self_reported`：候选在官网、主页或公开资料中的明确声明；
- `inferred`：合理推断但未确认；
- `unknown`：没有找到。

禁止虚构客户数、员工数、回复习惯、合作历史、GEO能力、USDT接受情况、Telegram或WhatsApp。优先第一方来源，第三方目录只作佐证。

## 推荐首条消息

每家只生成一条10–45词英文开场：一个真实业务观察＋一个容易回答的问题，只含一个问号。禁止推销、发网址、谈价格、约电话、立即说partnership opportunity、提前问USDT或一次问多个问题。所有消息仅生成草稿，必须由用户人工发送。

## 当前聊天与文件输出

结果必须分别保留P0/P1/P2/P3字段，但当前聊天和正式日报只输出P0。每个P0必须展示：

- Person / Business、Role、Business size、Last observed activity；
- Resource / GEO fit、Reply evidence、Partnership evidence；
- USDT / crypto evidence、Evidence certainty；
- 非搜索发现渠道、发现来源、业务质量、搜索分发缺口；
- 可点击WhatsApp / Telegram / Facebook；
- Why this tier、Recommended first message。

首条消息必须先做简短、自然的自我介绍，再写客户专属事实并提出一个容易回答的问题。推荐结构：`Hi {name}, I’m [Your Name]. I help Web3 and payment companies explain their services clearly in AI search. {specific fact}. {one natural question}`。不得一上来盘问，不得省略身份，也不得虚构姓名；`[Your Name]`由用户发送前人工替换。消息保持简短，不硬推销、不报价。

正式运行后写入SQLite，生成带运行编号的P0日报和CSV，并生成/更新Obsidian商家卡片。不得自动联系商家。

