```

关键资金仍双人审批。

---

## 110. Author

能：

```text
创建章节
提交审核
修改草稿
```

不能：

```text
自己设VIP
删差评
直接标记签约
```

---

## 111. Agent

能：

```text
总结
查询
草拟
建议
```

不能：

```text
直接数据库
永久封禁
批准资金
自动发大额奖励
签版权合同
```

---

# 第十篇：下架 / 恢复 / 权益案例

## 112. 章节临时下架

```text
用户买过Chapter A
↓
Chapter A整改临时下架
```

结果：

```text
Entitlement保留
暂时不能读
不自动退款
作者收入不自动反转
```

恢复同一个 chapter_id：

```text
用户直接可读
不重新购买
```

---

## 113. 整书永久下架

默认：

```text
不自动真实退款
```

可：

```text
Goodwill Compensation
```

例如根据政策：

```text
历史有效消费约5%赠币补偿
```

但这是 Compensation，不是 Refund。

法律/支付/平台重大责任：

```text
可触发真实退款Override
```

---

# 第十一篇：Platform Governance

## 114. Parameter Center

所有关键规则版本化。

但：

```text
1 RMB = 100 RechargeCoin
```

不是普通运营可修改参数。

可以标：

```text
SYSTEM_LOCKED
```

---

## 115. Metric Center

统一“有效读者”。

不能：

```text
作者后台=1000
运营后台=1300
排行榜=900
```

必须引用同一个 Metric Version。

---

## 116. Job Center

统一：

```text
定时发布
会员到期
赠币过期
榜单计算
结算
通知
Retention
```

Celery只是执行器。

业务真相在：

```text
job_runs
```

---

## 117. File Service

文件：

```text
PUBLIC
PRIVATE
HIGH_SENSITIVE
LEGAL_EVIDENCE
```

高敏使用：

```text
短时Signed URL
权限
Audit
```

---

## 118. Change Center

重大规则改动：

```text
Impact Analysis
Approval
Schedule
Preflight
Activate
Rollback Plan
```

“回滚参数”不能让过去已经发出的GiftCoin凭空消失。

---

## 119. Retention

不能：

```text
所有数据永久保留
```

也不能：

```text
用户点删除 → 财务账本一起DELETE
```

分类：

```text
DELETE
ANONYMIZE
ARCHIVE
KEEP
DOMAIN_CONTROLLED
```

Legal Hold 优先级最高。

---

# 第十二篇：最终技术栈 —— 保持此前设计不变

## 120. Frontend

Reader：

```text
Nuxt 4
Vue 3
TypeScript
SSR/Hybrid
Pinia
Reader Design System
```

Writer：

```text
Vue 3
Vite
TypeScript
Pinia
TanStack Vue Query
Element Plus（自定义Theme）
```

Admin：

```text
Vue 3
Vite
TypeScript
Pinia
TanStack Vue Query
Element Plus（自定义Theme）
```

Monorepo：

```text
pnpm workspace
Node 24 LTS release line
```

---

## 121. Backend

```text
Python 3.14 release line
FastAPI
Pydantic v2
SQLAlchemy 2.0
Alembic
Uvicorn
uv
pytest
Ruff
Mypy
```

架构：

```text
Modular Monolith
+
Pragmatic DDD
```

---

## 122. Data / Infra

```text
MySQL 8.4 LTS
Redis
RabbitMQ 4.3 release line
Celery
OpenSearch
ClickHouse
S3-compatible Object Storage
MinIO local
Docker
Docker Compose
Nginx
GitHub Actions
OpenTelemetry
Prometheus
Grafana
```

一期：

```text
不Kubernetes
不Kafka作为主业务Broker
```

---

# 第十三篇：工程目录

## 123. Monorepo

```text
novel-platform/
├─ apps/
│  ├─ reader-web/
│  ├─ writer-web/
│  └─ admin-web/
├─ packages/
│  ├─ api-client/
│  ├─ api-types/
│  ├─ reader-ui/
│  ├─ workbench-ui/
│  ├─ design-tokens/
│  └─ shared-utils/
├─ services/
│  └─ backend/
├─ infra/
├─ docs/
├─ scripts/
└─ .github/
```

---

## 124. Backend

```text
src/novel_platform/
├─ core/
├─ interfaces/http/
│  ├─ reader/
│  ├─ writer/
│  └─ admin/
├─ modules/
│  ├─ iam/
│  ├─ author/
│  ├─ content/
│  ├─ review/
│  ├─ reading/
│  ├─ library/
│  ├─ community/
│  ├─ membership/
│  ├─ commerce/
│  ├─ wallet/
│  ├─ author_finance/
│  ├─ contract/
│  ├─ copyright/
│  ├─ legal/
│  ├─ search/
│  ├─ recommendation/
│  ├─ ranking/
│  ├─ operation/
│  ├─ support/
│  ├─ risk/
│  ├─ notification/
│  └─ platform/
└─ shared/
```

每个Domain：

```text
domain
application
infrastructure
api
events
```

---

# 第十四篇：Codex 一次性并行直线开发方案

## 125. 目标

不是：

```text
用户：“先写IAM”
↓
Codex完成
↓
用户：“下一步”
↓
Codex再写Content
```

而是：

```text
用户一次发送总控任务
↓
Codex读取主规格书
↓
自动拆Workstream
↓
并行/连续开发
↓
Wave Gate
↓
自动下一Wave
↓
直到V1.2完成或真正硬阻塞
```

---

## 126. Wave 0 Foundation

并行：

```text
Monorepo
Backend Core
Docker
MySQL/Alembic
Redis
RabbitMQ
OpenSearch
MinIO
CI
OpenAPI
RequestContext
Reader Shell
Writer Shell
Admin Shell
Docs/AGENTS
```

---

## 127. Wave 1 Identity + Content Foundation

并行：

```text
IAM
AuthorProfile
Content Core
Staff/RBAC/Audit
File基础
三端Auth/Layout
```

硬依赖通过接口契约解决。

---

## 128. Wave 2 First Vertical Slice

并行：

```text
Review
Publish
Reader Public Book
Reading
Bookshelf
Search Basic
Writer Review UI
Admin Review UI
```

Gate：

```text
作者创建
→ 章节
→ 首发审核
→ Reader公开
→ 阅读
→ 书架
→ 进度
```

---

## 129. Wave 3 Paid Reading

并行：

```text
Wallet Ledger
Asset Lots
Fake Payment
Recharge
Commerce
Entitlement
VIP Access
Reader Wallet UI
Admin Finance Query
```

Gate：

```text
Fake充值
→ Wallet到账
→ VIP购买
→ 扣款
→ Entitlement
→ 阅读
```

---

## 130. Wave 4 Consumer Economy

并行：

```text
Refund
Membership
Gift
Ticket
Community
Notification
```

Refund Golden Tests 必须通过。

---

## 131. Wave 5 Author Economy + Governance

并行：

```text
Contract
AuthorFinance
Settlement
Withdrawal
Risk
Approval
Support
Audit Advanced
Chargeback
Reconciliation
```

达到真实收费治理门槛。

---

## 132. Wave 6 Growth

并行：

```text
Search Advanced
Recommendation
Cold Start
Ranking
Operation
Campaign
Reward
Audience
Metric
```

---

## 133. Wave 7 Legal / Governance

并行：

```text
Copyright
Legal
Agreement
Change
Export
Retention
Job Advanced
Platform Governance
```

---

# 第十五篇：Codex不得中途反复询问用户

## 134. 默认自主决策

Codex必须根据本主规格书自行解决：

```text
字段命名
DTO结构
Repository实现
页面拆分
组件拆分
测试夹具
普通错误码
索引细节
非业务关键默认值
```

不能每件事都问用户。

---

## 135. 只有这些情况允许暂停

1. 真实支付/短信/实名/人脸等生产凭据必须由用户提供。
2. 需要不可逆生产操作。
3. 本文两条冻结业务彼此矛盾。
4. 不改变业务规则无法保证资金/数据一致性。
5. 法律/税务/财务具体参数必须由业务负责人确认。

即使某一个 Workstream 遇到上述阻塞：

> 其他不依赖 Workstream 继续开发。

---

# 第十六篇：Golden Tests —— Codex不得修改

永久测试：

```text
同实名最多3账号
Wallet并发不透支
Payment callback幂等
Gift expiry-first + FIFO
Refund consumed recharge扣减
Refund consumed promo gift扣减
Refund expired promo gift扣减
refund<=0不执行且不回收
Entitlement不重复
Member expiry relock
Temporary offline保留Entitlement
Chargeback普通Wallet不变负数
AuthorRevenue Ledger append-only
Requester不能自批关键Approval
```

除非用户正式修改 V1.2 业务规则，否则：

```text
不得修改这些预期值
```

---

# 第十七篇：最终验收

功能完成必须有：

```text
代码
Migration
API
权限
错误码
日志
Audit
幂等
Unit Test
Integration Test
Contract Test
E2E
文档
