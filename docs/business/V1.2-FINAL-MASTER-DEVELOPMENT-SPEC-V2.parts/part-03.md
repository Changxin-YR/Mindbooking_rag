礼物订单独立。

可以根据场景配置：

```text
gift+recharge allowed
或
recharge-only
```

GiftCoin 用于礼物消费时：

> 100%进入作者收益计费基数，再按合同分成。

---

## 27. 月票 / 推荐票

票不是 Wallet Coin。

```text
TicketAccount
TicketLot
TicketTransaction
BookTicketVote
```

风险状态：

```text
NORMAL
FROZEN
INVALIDATED
```

正式榜单只统计：

```text
NORMAL
```

---

## 28. 通知中心

读者类别：

```text
SYSTEM
BOOK_UPDATE
COMMENT_REPLY
AUTHOR
ASSET
ACTIVITY
SECURITY
```

渠道：

```text
IN_APP
WEB_PUSH
SMS
```

### SMS冻结

普通：

- 更新
- 评论
- 会员提醒
- 活动

不发日常 SMS。

P0：

```text
重大账号/资金安全
→ IN_APP + SMS
```

且不能被营销设置关闭。

---

## 29. 客服

Reader 可以：

```text
FAQ
Help Center
创建工单
查看工单
回复
附件
退款咨询
账号找回
处罚申诉入口
版权投诉入口
```

客服永远不能索要：

```text
密码
短信验证码
支付密码
```

---

# 第三篇：Writer Center —— 完整产品功能 + 数据实现

## 30. 作者申请

```text
PlatformAccount
↓
Real Name
↓
Author Application
↓
Pen Name
↓
AuthorProfile
```

一个账号一个笔名。

`author_profiles.account_id UNIQUE`

`normalized_pen_name UNIQUE`

---

## 31. Writer Dashboard

展示：

```text
作品
审核待办
更新
编辑消息
数据摘要
签约
收益
结算
提现
活动
通知
```

---

## 32. 创建作品

字段参考商业 Writer Assistant：

```text
书名
频道
分类
标签
简介
封面
AI使用披露
```

第一本书第一次公开：

```text
必须人审
```

### 不能做

创建作品不等于：

```text
直接PUBLIC
```

必须：

```text
DRAFT
↓
First Listing Review
↓
PUBLIC
```

---

## 33. Book状态必须分维度

不能只有：

```text
book.status
```

一个字段。

至少：

```text
lifecycle:
DRAFT
SERIALIZING
PAUSED
COMPLETION_PENDING
COMPLETED

visibility:
PRIVATE
PENDING_FIRST_REVIEW
PUBLIC
TEMP_OFFLINE
PERMANENT_OFFLINE
```

审核、签约、商业状态属于各自 Domain。

---

## 34. Metadata版本

作者改书名/简介：

```text
Metadata V1 public
↓
Author edits V2
↓
V2 reviewing
```

Reader 继续看到：

```text
V1
```

审核通过：

```text
public_metadata_version_id → V2
```

不能审核中的新简介立即覆盖公开版本。

---

## 35. 卷 / 章节 / 草稿

```text
Book
↓
Volume
↓
Chapter
↓
Draft Head
↓
Draft Snapshots
↓
Chapter Version
```

草稿支持：

```text
自动保存
手动保存
undo/redo
revision conflict
历史恢复
```

---

## 36. Chapter Version

发布时：

```text
Draft
↓
Snapshot fixed version
↓
Review
↓
Publish
```

发布版本 immutable。

已发布后修改：

```text
new ChapterVersion
```

不能：

```sql
UPDATE old_published_content
```

---

## 37. 已发布章节删除

禁止物理 DELETE。

可以：

```text
TEMP_OFFLINE
PERMANENT_OFFLINE
```

付费 canonical chapter ID 不允许删除再重新用一个新ID冒充原章节。

---

## 38. 章节拆分/合并

需要：

```text
chapter_structure_relations
SPLIT_TO
MERGED_INTO
```

Commerce/Entitlement 执行继承/迁移。

不能让用户：

```text
以前买过一章
↓
章节拆成两章
↓
又要重新付两次钱
```

---

## 39. 编辑器

支持：

```text
字数
计费字数
查找替换
拼写/错别字
标点
敏感词提示
格式
夜间
专注
自动保存
历史版本
恢复
```

使用受控段落模型。

不允许任意：

```html
<script>
<iframe>
```

---

## 40. 创作知识库

```text
世界观
人物
势力
地点
关系
能力
物品
时间线
伏笔
大纲
```

默认私有。

---

## 41. AI辅助

AI可以：

```text
建议
总结
检查一致性
润色建议
```

AI不能：

```text
自动发布
自动改正文并保存公开版本
绕过审核
```

---

## 42. 审核

Writer看到：

```text
审核中
通过
退回
整改要求
临时下架
恢复
申诉
```

不展示：

```text
内部Risk Score
内部审查规则阈值
审核员内部私密备注
```

---

## 43. 签约

```text
Author Apply / Editor Invite
↓
Evaluation
↓
Proposal
↓
Approval
↓
Contract
↓
E-sign
↓
ACTIVE
```

合同：

```text
独家分成
非独家分成
保底
买断
特殊
```

---

## 44. VIP / 倒V

作者不能直接点：

```text
“本章设为VIP”
```

正确：

```text
签约
↓
责任编辑/平台
↓
VIP Policy
↓
必要倒V Proposal
↓
Approval
↓
生效
```

---

## 45. 完结

```text
Author Apply Completion
↓
系统检查
↓
Editor Confirm
↓
COMPLETED
```

不能作者直接改：

```text
status = COMPLETED
```

---

## 46. 数据分析

统一 Metric：

```text
有效读者
有效阅读时长
追读
完读
收藏
订阅
月票
推荐票
礼物
会员阅读
曝光
搜索
章节表现
```

不能 Writer 自己有一套“有效读者”算法。

---

## 47. 收益

状态：

```text
ESTIMATED
RISK_PENDING
CONFIRMED
SETTLEMENT_PENDING
SETTLED
FROZEN
REVERSED
```

来源：

```text
VIP
GIFT
MEMBERSHIP_POOL
FREE_READING_POOL
ACTIVITY
GUARANTEE
BUYOUT
COPYRIGHT
ADJUSTMENT
```

---

## 48. Settlement

每个周期：

```text
Revenue
↓
Risk
↓
Confirmed
↓
Settlement
↓
Tax
↓
Withdrawable
```

Settlement LOCKED 后不能手改。

错误修复：

```text
later Adjustment
```

---

## 49. 提现

支持：

```text
银行卡
支付宝
```

要求：

```text
holder real-name match
```

作者账号找回后：

```text
不能同时直接修改提现账户并立即大额提现
```

正确：

```text
先恢复账号
↓
安全检查/冷静期
↓
另走Payout Account Change
```

---

## 50. 作者编辑工作消息

独立：

```text
editor_conversations
editor_messages
```

这不是社区私信。

Notification 只发：

```text
“你有一条新的责任编辑工作消息”
```

正文仍在 Work Messaging。

---

# 第四篇：Admin Console —— 完整功能 + 权限 + 数据实现

## 51. Staff体系

Staff 和 Reader 彻底分离。

不能：

```text
platform_accounts.is_admin = true
```

正确：

```text
staff_accounts
```

独立：

```text
credential
session
device
MFA
role
permission
```

---

## 52. RBAC + Data Scope

能登录后台：

```text
≠ 能看所有数据
≠ 能执行所有操作
≠ 能自己审批自己
