## 204. 内部工作人员风控

Staff 也进入 Risk/Audit。

例如：

```text
客服短时间查看大量高资产用户
财务深夜批量导出Payout数据
运营异常大量发放奖励
```

产生：

```text
StaffRiskEvent
```

必要时 Step-up / Block / Case。

---

## 205. 内容状态全局同步

作品/章节：

```text
下架
恢复
永久下架
```

不能只更新 Content DB。

必须通过 Event/Outbox 同步：

```text
Search
Recommendation
Ranking
Cache
TTS
Membership
Operation/Campaign
Notification（需要时）
```

### 例子

永久下架：

```text
立即退出Search/Recommendation/Ranking
```

但用户书架：

```text
《XXX》
状态：已下架/暂不可用
```

不能神秘消失。

---

## 206. 正常注销与违规终止

正常主动注销：

```text
资产
退款
合同
作者收益
案件
法律保留
```

处理完 + Safety Period：

```text
允许释放RealName slot
```

严重违规终止：

```text
不能通过
被封 → 注销 → 重建账号
```

绕过同实名最多3账号的限制。

---

## 207. 最终三端闭环

### Reader

```text
游客
→ 找书/试读
→ 登录
→ 阅读/书架
→ 评论/社区
→ 实名
→ 充值
→ 会员/VIP/礼物
→ 月票/推荐票
→ 粉丝/成长
→ 客服/通知
```

### Writer

```text
普通账号
→ 实名/作者身份
→ 一个账号一个笔名
→ 创建作品
→ 人工首审
→ 创作/发布
→ 数据
→ 签约
→ 责任编辑
→ 推荐
→ VIP/会员商业化
→ 收益
→ 结算
→ 提现
→ 版权
→ 完结
```

### Staff

```text
Staff
→ RBAC/Data Scope
→ Review
→ Editor
→ Operation
→ Governance
→ Support
→ Finance
→ Risk
→ Copyright/Legal
→ Data/Platform
→ Approval/Audit
```

---

## 208. 参数待定 ≠ 架构缺失

以下不要让 Codex 因为没有最终数字就停下来询问用户：

```text
会员具体价格
每天具体送多少推荐票
每月票券数量
礼物最终8档名称与金额
哪些场景RechargeCoin-only
各榜具体权重
推荐具体权重
审核SLA分钟数
签约最低条件
最低提现金额
免费扶持池具体公式
会员池具体权重
永久下架补偿模板
活动具体参数
```

做法：

```text
建立Versioned Policy / Parameter
提供合理开发默认值或Seed配置
标记business-configurable
继续开发
```

除非真实生产上线必须决定，否则不能因此阻塞 V1.2 全量工程实现。

---

# 第二十四篇：旧冻结基线与最新规则的冲突处理

## 209. 退款规则

旧示例：

```text
¥100
10000 RechargeCoin
2000 GiftCoin
消费2000 Recharge + 1500 Gift
→ 最多退¥65
```

这个例子在“没有自然过期 GiftCoin”的条件下仍然成立。

最新完整规则额外加入：

```text
同源促销GiftCoin自然过期
→ 也按等值金额扣减可退现金
```

因此 Codex 只能使用最新完整 Refund Formula。

---

## 210. Chapter Status

旧文档的：

```text
DRAFT / SCHEDULED / REVIEWING / PUBLISHED / REJECTED / OFFLINE
```

保留为 Writer UI 展示语义。

数据库最终必须分：

```text
publish state
review state
visibility state
commercial policy
```

避免万能状态字段。

---

## 211. Author Featured Comment

作者：

```text
reply / like / pin / report
```

平台：

```text
platform feature / platform pin
```

不把“平台精选”权限下放给作者。

---

# 第二十五篇：V2 Coverage Matrix —— Codex 必须逐项打勾

| 领域 | 功能 | 前端 | Application/Domain | 数据/投影 | 必须测试 |
|---|---|---|---|---|---|
| Reader | 男女频 | 首页/书库/榜单 | Search/Recommendation | channel fields | 不强制用户选性别 |
| Reader | 评分 | 作品详情 | Community/Rating | book_user_ratings | 未达有效阅读不能评分 |
| Reader | 关注用户/作者 | 用户页/作者页 | Library/Social | follow_relations | privacy |
| Reader | 用户成长 | 个人中心 | Library/Social | growth events/profile | 与会员/粉丝分离 |
| Reader | 纠错举报 | Reader/Community | Governance | correction/report | reporter privacy |
| Reader | 未成年人 | 账号/消费 | IAM/Risk/Commerce | policy/profile | policy-version |
| Writer | 改笔名 | 设置 | Author | pen_name_history | signed approval |
| Writer | 首审N章/N字 | 提交页 | Review | policy version | fixed-version review |
| Writer | 创作日历 | Dashboard | Author | daily stats/goals | derived stats |
| Writer | 作者任务 | Task Center | Author/Operation | task progress | reward idempotency |
| Writer | 成长等级 | Dashboard | Author | growth profile | versioned rules |
| Writer | 创作活动 | Activity | Operation | campaigns | risk before reward |
| Writer | 创作学院 | Learning | Operation/Author | learning content | permission/content safety |
| Writer | 逐章漏斗 | Analytics | Metric/Reading | fact projections | metric consistency |
| Admin | 审核员质量 | Review Admin | Review/Metric | quality metrics | appeal overturn |
| Admin | 作者异常预警 | Editor | Metric/Risk | alerts | no L3 exposure |
| Admin | 用户360 | User Admin | Query Service | read models | field masking |
| Admin | 举报聚合 | Governance | Support/Governance | case+submissions | 500 reports one case |
| Admin | 客服看板/CSAT | Support | Support/Metric | surveys | SLA |
| Finance | 未入账修复 | Finance | Payment/Wallet | reconciliation | channel success + credit fail |
| Finance | 日对账 | Finance | Wallet/Payment | batches/items | mismatch classes |
| Finance | 发票/票据 | Finance/Reader | Finance | invoice_* | lifecycle |
| Risk | 登录/SMS/刷量 | Risk | Risk | rules/signals/cases | observe/enforce |
| Risk | 自刷订阅/礼物 | Risk | Risk+Finance | edges/revenue state | order fact preserved |
| Platform | 管理驾驶舱 | Admin | Metric | read models | read-only |
| Platform | 员工生命周期 | Admin | IAM/Platform | staff assignments | offboarding |
| Platform | Staff Risk | Admin | Risk | risk events | sensitive access |
| Platform | 全局状态同步 | all | Outbox/Event | projections | takedown propagation |
| IAM | 注销/违规终止 | Account/Admin | IAM/Risk | real-name slots | blocked slot not released |

> Codex 在最终交付报告中必须输出本 Coverage Matrix 的完成情况，不得只说“主要功能完成”。
