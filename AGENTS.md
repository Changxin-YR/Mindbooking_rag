# AGENTS.md — V1.2 最终工程纪律 V2

1. 必须完整读取 `docs/business/V1.2-FINAL-MASTER-DEVELOPMENT-SPEC-V2.md` 后开发。
2. 用户要求一次性持续开发；无真正硬阻塞不得每个模块询问“是否继续”。
3. 使用 Wave + Workstream；环境支持时使用并行 Agent/Subagent/Worktree。
4. 不允许替换冻结技术栈。
5. 不允许擅改最新版冻结业务规则。
6. 普通参数未最终确定时使用 Versioned Policy + Seed 默认值，不得因此停工。
7. 跨 Domain 禁止直接访问对方 infrastructure/repository。
8. 跨 Domain 通过 Application Port / Domain Event / API Contract。
9. Wallet Ledger、AuthorFinance Ledger append-only，禁止 UPDATE/DELETE 历史 Entry。
10. 所有 DB schema 变化使用 Alembic；共享环境 Migration 不得回改。
11. RMB=BIGINT cents，Coin=BIGINT，比例=BPS；财务禁 FLOAT/DOUBLE。
12. `1 RMB = 100 RechargeCoin` 固定；促销只能通过 GiftCoin。
13. GiftCoin spend 默认即将过期优先，其次FIFO；GiftCoin消费100%进入作者收益计费基数。
14. Refund 使用最新版公式，包含同源自然过期Promo GiftCoin等值扣减。
15. `refund <= 0` 时普通退款不执行，也不回收剩余资产。
16. Chargeback 与 Refund 分开；普通用户Wallet不得因Chargeback变负数。
17. ChapterEntitlement必须 `UNIQUE(account_id, chapter_id)`。
18. Member free / Limited free 不等于 Purchased。
19. 已发布Chapter/Version/Order/Entitlement/Contract/Ledger/Audit禁止普通物理删除。
20. StaffAccount 与 PlatformAccount 分离。
21. SuperAdmin不能绕过关键财务Maker/Checker。
22. Reviewer、Editor、Operation、Support、Risk各有边界，不得越权直接改别的Domain真相。
23. Author不能自行开VIP、不能删除正常差评、不能赋予平台精选。
24. Risk异常贡献先FROZEN/调查，不删除原始业务事实。
25. Agent永不直接DB，不绕过Business API、Risk、Approval。
26. 所有公开API使用Explicit DTO，禁止ORM直接序列化。
27. 新API进入OpenAPI并生成前端类型。
28. 关键写操作幂等；Payment callback、Refund、Reward、Purchase必须测试重复调用。
29. 关键资金并发必须用真实MySQL集成测试。
30. 禁止删除失败测试、skip关键测试、降低断言、修改Golden Test掩盖Bug。
31. Reader/Writer/Admin必须做真实最终页面并接真实后端，不以纯Mock页面宣布完成。
32. 每个功能DoD = UI + API + Domain + DB + Permission + Tests + Docs。
33. 每个Wave通过全量CI/E2E后自动进入下一Wave。
34. 只在生产凭据、不可逆生产操作、真实规则冲突、资金一致性无法满足、法律/税务必须决策时暂停相关Workstream。
35. 某Workstream阻塞时其他独立Workstream继续。
36. 最终交付必须逐项报告Coverage Matrix，不得用“基本完成”替代。
