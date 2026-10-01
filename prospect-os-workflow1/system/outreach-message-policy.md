# 首轮 WhatsApp / Telegram 话术政策

本阶段只做 research → prepare draft → human review，绝不发送。Buyer Priority Rating 衡量潜客，不得与 message_quality 混用。

## 写作前

只读取 prospect record 已有的官网、买家查询、竞品/可见性、决策人、活跃度和 PRELOCK 证据；不在写话术时重新研究，也不补猜测。每个可核验陈述都要能回指 evidence id、来源 URL 与证据状态。

- PRELOCK_REVIEW：只请求许可去测试一个真实买家搜索。不能说已发现竞品差距、已检查可见度、客户正在流失或已有 GEO 问题。未测试的查询、竞品与 visibility gap 必须留空。
- PRELOCK_PASS + 已测试查询及可见性证据：可以用一条实际 query observation 和真实竞品比较，轻描淡写地给出结果，并问是否发送 exact query / comparison。没有这些证据时仍用 REVIEW 模式。

## 消息风格

- WhatsApp/TG 首条目标 25–45 词；通常 20–55 词，硬上限 60 词；葡语/西语最多 65 词。最多 2–3 个短段落。
- 用 prospect 市场的自然语言。Track A 说“买家搜索这种服务时会看到什么”；Track B 用“附近找 vape 店”“找本地葡萄酒配送”这种简单说法。
- 一句短身份说明，使用字面占位符 [Your Name]；不造姓名、不装成顾客。身份可按语境表达为 buyer-search visibility 从业者，不必逐字模板化。
- 先提一个有来源的具体业务事实，再连接买家场景。不要夸赞、堆服务、解释 GEO/SEO，也不默认提 AI Search。
- 每条消息只留一个低摩擦 CTA，能用 Yes / Sure / Sim 回答。禁止首条索要审计/PDF、报价或会议。
- WhatsApp 语气直接自然；Telegram 技术客群可稍直接。不能装熟或滥用行话。

## 禁止与审查

禁止研究员口吻（如 “I am analyzing how buyers find…” / “Estou analisando como compradores encontram…”）、空泛的 organic discovery/visibility optimization 话术、无证据夸赞、恐惧式断言和未测试的搜索结果。不要机械逐字翻译模板。

内部生成 observation-first 与 buyer-query-first 两稿；按证据、个性化、自然度、压缩、单 CTA、低摩擦、少推销、少行话、主张安全逐项审查。通用稿（换公司名仍完全适用）必须重写。确定性约束由代码校验，语义判断由 reviewer 做；最多重写两次。

- 90–100：PASS / 可供人工检查。
- 80–89：至少重写一次；重写后仍有硬问题则 MESSAGE_REVIEW_REQUIRED。
- <80：拒绝并重写。两次仍未过门，输出 MESSAGE_REVIEW_REQUIRED，不伪装成 ready。
- 任何无证据事实、虚构竞品/query/gap、REVIEW 越权、多个 CTA、假姓名、冒充顾客或假称测试过搜索，均为硬失败，不看总分。

输出 outreach.language、channel、message_mode、recommended_first_message、cta、personalization_fact、buyer_query_used、visibility_evidence_used、message_candidates 与 message_quality。REVIEW 时 buyer_query_used 必须为 null，visibility_evidence_used 必须为 false。

WhatsApp 仅认明确的 WhatsApp 直聊链接；电话不能升级为 WA。Telegram 必须是经核验的真人/企业账号直聊页，群、频道、bot、邀请和分享页均不能作为直聊入口。联系路由不合格时不生成可发送话术。
